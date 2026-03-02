"""
Battery storage dispatch optimizer.

Formulates and solves a daily LP to dispatch a grid-scale battery across
multiple ERCOT revenue streams simultaneously:

    Revenue streams:
        1. Real-time energy arbitrage (buy low / sell high)
        2. ECRS  – ERCOT Contingency Reserve Service   (capacity payment)
        3. RRS   – Responsive Reserve Service          (capacity payment)
        4. Reg-Up / Reg-Down                           (capacity payments)
        5. Non-Spinning Reserve                        (capacity payment)

    Battery physics modelled:
        • State-of-charge (SOC) dynamics with one-way efficiency losses
        • Simultaneous charge / discharge prevented via binary variable
          (approximated by a penalty in the LP — avoids MIP complexity)
        • SOC headroom requirement for committed ancillary capacity
        • Minimum SOC floor for committed Reg-Down capacity

The optimiser solves one 24-hour window per day (perfect foresight, i.e.
day-ahead prices) and returns a detailed hourly dispatch schedule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import linprog


# ── Asset parameters ─────────────────────────────────────────────────────────

@dataclass
class BatteryAsset:
    """Physical and operational parameters of the storage asset."""

    power_mw: float = 100.0       # nameplate charge / discharge power (MW)
    energy_mwh: float = 200.0     # usable energy capacity (MWh)
    eta_charge: float = 0.93      # charging efficiency
    eta_discharge: float = 0.93   # discharging efficiency
    soc_min_pct: float = 0.05     # minimum SOC as fraction of capacity
    soc_max_pct: float = 0.95     # maximum SOC as fraction of capacity
    initial_soc_pct: float = 0.50 # starting SOC
    degradation_cost: float = 0.50  # $/MWh throughput (wear cost)

    # Ancillary service availability fractions
    # (fraction of power_mw that can be committed to each AS product)
    max_ecrs_pct: float = 0.60
    max_rrs_pct: float = 0.50
    max_reg_up_pct: float = 0.40
    max_reg_dn_pct: float = 0.40
    max_non_spin_pct: float = 0.50

    # AS SOC commitment requirement: hours of capacity held in reserve
    as_discharge_reserve_hrs: float = 1.0
    as_charge_reserve_hrs: float = 0.5

    @property
    def soc_min_mwh(self) -> float:
        return self.soc_min_pct * self.energy_mwh

    @property
    def soc_max_mwh(self) -> float:
        return self.soc_max_pct * self.energy_mwh

    @property
    def initial_soc_mwh(self) -> float:
        return self.initial_soc_pct * self.energy_mwh


# ── Optimiser ────────────────────────────────────────────────────────────────

def _build_lp(
    lmp: np.ndarray,
    p_ecrs: np.ndarray,
    p_rrs: np.ndarray,
    p_reg_up: np.ndarray,
    p_reg_dn: np.ndarray,
    p_non_spin: np.ndarray,
    asset: BatteryAsset,
    initial_soc: float,
) -> dict:
    """
    Build LP matrices for a single 24-hour dispatch window.

    Variable layout (T = 24 hours):
        [0  : T  ) → p_charge    (MW, ≥0)
        [T  : 2T ) → p_discharge (MW, ≥0)
        [2T : 3T ) → soc         (MWh, bounded)
        [3T : 4T ) → q_ecrs      (MW, ≥0)
        [4T : 5T ) → q_rrs       (MW, ≥0)
        [5T : 6T ) → q_reg_up    (MW, ≥0)
        [6T : 7T ) → q_reg_dn    (MW, ≥0)
        [7T : 8T ) → q_non_spin  (MW, ≥0)

    Returns scipy.optimize.linprog kwargs dict.
    """
    T = len(lmp)
    N = 8 * T   # total variables

    # Index helpers
    idx_pc   = slice(0 * T, 1 * T)
    idx_pd   = slice(1 * T, 2 * T)
    idx_soc  = slice(2 * T, 3 * T)
    idx_ecrs = slice(3 * T, 4 * T)
    idx_rrs  = slice(4 * T, 5 * T)
    idx_rup  = slice(5 * T, 6 * T)
    idx_rdn  = slice(6 * T, 7 * T)
    idx_nsp  = slice(7 * T, 8 * T)

    a = asset

    # ── Objective (minimise negative revenue) ────────────────────────────────
    # energy revenue: lmp * (pd - pc) minus degradation on throughput
    deg = a.degradation_cost
    c = np.zeros(N)
    c[idx_pc]   = (lmp + deg)        # buying costs money
    c[idx_pd]   = -(lmp - deg)       # selling earns money
    c[idx_ecrs] = -p_ecrs
    c[idx_rrs]  = -p_rrs
    c[idx_rup]  = -p_reg_up
    c[idx_rdn]  = -p_reg_dn
    c[idx_nsp]  = -p_non_spin

    # ── Equality constraints (SOC dynamics) ──────────────────────────────────
    # soc[t] = soc[t-1] + eta_c * pc[t] - (1/eta_d) * pd[t]
    # Rearranged: soc[t] - soc[t-1] - eta_c*pc[t] + (1/eta_d)*pd[t] = 0
    A_eq = np.zeros((T, N))
    b_eq = np.zeros(T)

    for t in range(T):
        A_eq[t, idx_soc.start + t]   =  1.0
        A_eq[t, idx_pc.start  + t]   = -a.eta_charge
        A_eq[t, idx_pd.start  + t]   =  1.0 / a.eta_discharge
        if t == 0:
            b_eq[t] = initial_soc
        else:
            A_eq[t, idx_soc.start + t - 1] = -1.0

    # ── Inequality constraints (A_ub @ x ≤ b_ub) ────────────────────────────
    A_ub_list = []
    b_ub_list = []

    def add_ub(row: np.ndarray, b: float):
        A_ub_list.append(row)
        b_ub_list.append(b)

    for t in range(T):
        row_base = np.zeros(N)

        # ── Discharge-side power limit: pd + q_ecrs + q_rrs + q_rup + q_nsp ≤ P_max
        row = np.zeros(N)
        row[idx_pd.start  + t] =  1.0
        row[idx_ecrs.start + t] = 1.0
        row[idx_rrs.start  + t] = 1.0
        row[idx_rup.start  + t] = 1.0
        row[idx_nsp.start  + t] = 1.0
        add_ub(row, a.power_mw)

        # ── Charge-side power limit: pc + q_rdn ≤ P_max
        row = np.zeros(N)
        row[idx_pc.start  + t] = 1.0
        row[idx_rdn.start + t] = 1.0
        add_ub(row, a.power_mw)

        # ── Simultaneous charge & discharge penalty (linear approx)
        # pc + pd ≤ P_max  (encourages one-way operation; not perfectly binding)
        row = np.zeros(N)
        row[idx_pc.start + t] = 1.0
        row[idx_pd.start + t] = 1.0
        add_ub(row, a.power_mw)

        # ── AS discharge headroom: SOC must cover committed AS discharge capacity
        # soc[t] ≥ (q_ecrs + q_rrs + q_rup + q_nsp) * reserve_hrs
        # → -(soc) + reserve_hrs*(q_...) ≤ 0
        row = np.zeros(N)
        row[idx_soc.start  + t] = -1.0
        for idx_as in [idx_ecrs, idx_rrs, idx_rup, idx_nsp]:
            row[idx_as.start + t] = a.as_discharge_reserve_hrs
        add_ub(row, -a.soc_min_mwh)

        # ── AS charge headroom: SOC must have room for Reg-Down
        # soc[t] ≤ soc_max - q_rdn * reserve_hrs
        # → soc[t] + q_rdn * reserve_hrs ≤ soc_max
        row = np.zeros(N)
        row[idx_soc.start + t] = 1.0
        row[idx_rdn.start + t] = a.as_charge_reserve_hrs
        add_ub(row, a.soc_max_mwh)

        # ── Per-product AS capacity limits
        for idx_as, max_pct in [
            (idx_ecrs,  a.max_ecrs_pct),
            (idx_rrs,   a.max_rrs_pct),
            (idx_rup,   a.max_reg_up_pct),
            (idx_rdn,   a.max_reg_dn_pct),
            (idx_nsp,   a.max_non_spin_pct),
        ]:
            row = np.zeros(N)
            row[idx_as.start + t] = 1.0
            add_ub(row, a.power_mw * max_pct)

    A_ub = np.array(A_ub_list)
    b_ub = np.array(b_ub_list)

    # ── Bounds ────────────────────────────────────────────────────────────────
    bounds = [(None, None)] * N
    for t in range(T):
        bounds[idx_pc.start  + t] = (0, a.power_mw)
        bounds[idx_pd.start  + t] = (0, a.power_mw)
        bounds[idx_soc.start + t] = (a.soc_min_mwh, a.soc_max_mwh)
        bounds[idx_ecrs.start + t] = (0, a.power_mw * a.max_ecrs_pct)
        bounds[idx_rrs.start  + t] = (0, a.power_mw * a.max_rrs_pct)
        bounds[idx_rup.start  + t] = (0, a.power_mw * a.max_reg_up_pct)
        bounds[idx_rdn.start  + t] = (0, a.power_mw * a.max_reg_dn_pct)
        bounds[idx_nsp.start  + t] = (0, a.power_mw * a.max_non_spin_pct)

    return dict(
        c=c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
        method="highs",
        options={"disp": False},
        indices=(idx_pc, idx_pd, idx_soc, idx_ecrs, idx_rrs, idx_rup, idx_rdn, idx_nsp),
    )


def optimise_day(
    day_df: pd.DataFrame,
    asset: BatteryAsset,
    initial_soc: Optional[float] = None,
) -> pd.DataFrame:
    """
    Optimise dispatch for a single 24-hour period.

    Parameters
    ----------
    day_df   : DataFrame with columns [timestamp, lmp, ecrs, rrs, reg_up, reg_dn, non_spin]
    asset    : BatteryAsset instance
    initial_soc : float, MWh; defaults to asset.initial_soc_mwh

    Returns
    -------
    DataFrame with the input columns plus dispatch variables and revenues
    """
    if initial_soc is None:
        initial_soc = asset.initial_soc_mwh

    T = len(day_df)
    if T == 0:
        return day_df

    lp = _build_lp(
        lmp=day_df["lmp"].values,
        p_ecrs=day_df["ecrs"].values,
        p_rrs=day_df["rrs"].values,
        p_reg_up=day_df["reg_up"].values,
        p_reg_dn=day_df["reg_dn"].values,
        p_non_spin=day_df["non_spin"].values,
        asset=asset,
        initial_soc=initial_soc,
    )

    indices = lp.pop("indices")
    idx_pc, idx_pd, idx_soc, idx_ecrs, idx_rrs, idx_rup, idx_rdn, idx_nsp = indices

    result = linprog(**lp)

    out = day_df.copy()
    if result.status == 0:   # optimal
        x = result.x
        out["p_charge"]   = x[idx_pc].clip(0)
        out["p_discharge"] = x[idx_pd].clip(0)
        out["soc"]         = x[idx_soc].clip(asset.soc_min_mwh, asset.soc_max_mwh)
        out["q_ecrs"]      = x[idx_ecrs].clip(0)
        out["q_rrs"]       = x[idx_rrs].clip(0)
        out["q_reg_up"]    = x[idx_rup].clip(0)
        out["q_reg_dn"]    = x[idx_rdn].clip(0)
        out["q_non_spin"]  = x[idx_nsp].clip(0)
    else:
        for col in ["p_charge", "p_discharge", "soc", "q_ecrs", "q_rrs",
                    "q_reg_up", "q_reg_dn", "q_non_spin"]:
            out[col] = 0.0

    # Revenue attribution
    out["rev_energy"] = (out["p_discharge"] - out["p_charge"]) * out["lmp"]
    out["rev_ecrs"]   = out["q_ecrs"]    * out["ecrs"]
    out["rev_rrs"]    = out["q_rrs"]     * out["rrs"]
    out["rev_reg_up"] = out["q_reg_up"]  * out["reg_up"]
    out["rev_reg_dn"] = out["q_reg_dn"]  * out["reg_dn"]
    out["rev_non_spin"] = out["q_non_spin"] * out["non_spin"]
    out["rev_total"]  = (
        out["rev_energy"] + out["rev_ecrs"] + out["rev_rrs"]
        + out["rev_reg_up"] + out["rev_reg_dn"] + out["rev_non_spin"]
    )

    return out


def run_full_year(
    market_df: pd.DataFrame,
    asset: BatteryAsset,
    progress_callback=None,
) -> pd.DataFrame:
    """
    Run optimisation for every day in market_df.

    Parameters
    ----------
    market_df : DataFrame with [timestamp, lmp, ecrs, rrs, reg_up, reg_dn, non_spin]
    asset     : BatteryAsset
    progress_callback : callable(current, total) or None

    Returns
    -------
    DataFrame with dispatch schedule and revenue columns
    """
    market_df = market_df.copy()
    market_df["date"] = pd.to_datetime(market_df["timestamp"]).dt.date
    days = sorted(market_df["date"].unique())

    frames = []
    soc = asset.initial_soc_mwh

    for i, day in enumerate(days):
        day_slice = market_df[market_df["date"] == day].copy()
        result = optimise_day(day_slice, asset, initial_soc=soc)

        # Carry SOC forward to next day
        if len(result) > 0 and "soc" in result.columns:
            soc = result["soc"].iloc[-1]

        frames.append(result)
        if progress_callback:
            progress_callback(i + 1, len(days))

    full = pd.concat(frames, ignore_index=True).drop(columns=["date"])
    return full
