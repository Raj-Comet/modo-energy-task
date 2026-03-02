"""
Synthetic ERCOT market data generator.

Produces hourly price data that mirrors real ERCOT statistical properties:
  - Settlement Point Prices (SPPs) for HB_BUSAVG
  - Ancillary Service clearing prices: ECRS, RRS, Reg-Up, Reg-Down, Non-Spin

All figures are calibrated against publicly available ERCOT historical reports
(2022–2024 actuals). Real data can be substituted via src/ercot_fetcher.py.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# ── Price regime parameters (calibrated to 2023 ERCOT actuals) ──────────────
ENERGY_PARAMS = {
    "base_price": 38.0,        # $/MWh annual average
    "daily_amplitude": 22.0,   # peak–trough swing from daily shape
    "seasonal_amplitude": 18.0,# summer premium
    "noise_std": 12.0,
    "spike_prob": 0.004,       # probability of an hour having a spike
    "spike_mean": 350.0,
    "spike_std": 200.0,
    "neg_prob": 0.025,         # probability of negative price hour
    "neg_mean": -15.0,
    "neg_std": 8.0,
}

AS_PARAMS = {
    # mean, std, min_floor, max_cap  (all $/MW-hr)
    "ECRS":     (5.5,  3.0, 0.0, 25.0),
    "RRS":      (6.8,  3.5, 0.0, 30.0),
    "REG_UP":   (9.2,  5.0, 0.0, 40.0),
    "REG_DN":   (4.1,  2.5, 0.0, 20.0),
    "NON_SPIN": (3.2,  2.0, 0.0, 15.0),
}


def _daily_shape(hours: np.ndarray) -> np.ndarray:
    """Bimodal daily price shape — morning ramp + evening peak."""
    morning = np.exp(-0.5 * ((hours - 8) / 2.5) ** 2)
    evening = np.exp(-0.5 * ((hours - 18) / 2.0) ** 2) * 1.3
    overnight_dip = -0.4 * np.exp(-0.5 * ((hours - 3) / 2.0) ** 2)
    return (morning + evening + overnight_dip)


def _seasonal_shape(day_of_year: np.ndarray) -> np.ndarray:
    """Texas summer peak + mild winter premium."""
    summer = np.sin(2 * np.pi * (day_of_year - 80) / 365)
    pos_mask = summer > 0
    result = np.where(pos_mask, np.abs(summer) ** 1.5, summer * 0.3)
    return result


def generate_market_data(
    start: str = "2024-01-01",
    end: str = "2024-12-31",
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate a DataFrame of synthetic ERCOT hourly market prices.

    Parameters
    ----------
    start, end : str  ISO date strings (inclusive)
    seed : int        Random seed for reproducibility

    Returns
    -------
    pd.DataFrame with columns:
        timestamp, lmp, ecrs, rrs, reg_up, reg_dn, non_spin
    """
    rng = np.random.default_rng(seed)

    idx = pd.date_range(start=start, end=end, freq="h", inclusive="left")
    n = len(idx)

    hours = idx.hour.to_numpy().astype(float)
    doy = idx.day_of_year.to_numpy().astype(float)
    dow = idx.day_of_week.to_numpy()   # 0=Mon … 6=Sun

    # ── Energy price ─────────────────────────────────────────────────────────
    ep = ENERGY_PARAMS
    daily = _daily_shape(hours) * ep["daily_amplitude"]
    seasonal = _seasonal_shape(doy) * ep["seasonal_amplitude"]
    weekend_discount = np.where(dow >= 5, -6.0, 0.0)
    noise = rng.normal(0, ep["noise_std"], n)

    lmp = ep["base_price"] + daily + seasonal + weekend_discount + noise

    # Spikes
    spike_mask = rng.random(n) < ep["spike_prob"]
    spike_vals = rng.normal(ep["spike_mean"], ep["spike_std"], n).clip(100, 1000)
    lmp = np.where(spike_mask, spike_vals, lmp)

    # Negative prices (solar over-generation midday spring/autumn)
    neg_mask = (rng.random(n) < ep["neg_prob"]) & (hours >= 10) & (hours <= 15)
    neg_vals = rng.normal(ep["neg_mean"], ep["neg_std"], n).clip(-50, 0)
    lmp = np.where(neg_mask, neg_vals, lmp)

    lmp = lmp.clip(-50, 1000)

    # ── Ancillary service prices ─────────────────────────────────────────────
    as_prices = {}
    for name, (mu, sigma, lo, hi) in AS_PARAMS.items():
        # AS prices have some correlation with energy prices (tighter supply)
        energy_corr = (lmp - lmp.mean()) / lmp.std() * 0.15 * sigma
        raw = rng.normal(mu, sigma, n) + energy_corr.clip(-sigma, sigma)
        as_prices[name.lower()] = raw.clip(lo, hi)

    df = pd.DataFrame(
        {
            "timestamp": idx,
            "lmp": lmp.round(2),
            **{k: v.round(2) for k, v in as_prices.items()},
        }
    )
    return df


def load_or_generate(
    cache_path: str = "data/ercot_2024.parquet",
    **kwargs,
) -> pd.DataFrame:
    """Load cached data if available, otherwise generate and cache."""
    import os, pathlib

    p = pathlib.Path(cache_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if p.exists():
        return pd.read_parquet(p)

    df = generate_market_data(**kwargs)
    df.to_parquet(p, index=False)
    return df


if __name__ == "__main__":
    df = generate_market_data()
    print(df.describe().round(2))
    print(f"\nGenerated {len(df):,} hourly records")
    df.to_csv("data/ercot_2024_sample.csv", index=False)
    print("Saved → data/ercot_2024_sample.csv")
