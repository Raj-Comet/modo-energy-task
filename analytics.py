"""
Revenue analytics and reporting for battery storage assets.

Turns raw hourly dispatch results into the metrics and aggregations
used by the Streamlit dashboard.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


REVENUE_STREAMS = {
    "rev_energy":   "Energy Arbitrage",
    "rev_ecrs":     "ECRS",
    "rev_rrs":      "RRS",
    "rev_reg_up":   "Reg-Up",
    "rev_reg_dn":   "Reg-Down",
    "rev_non_spin": "Non-Spin",
}

STREAM_COLORS = {
    "Energy Arbitrage": "#2196F3",
    "ECRS":             "#FF9800",
    "RRS":              "#4CAF50",
    "Reg-Up":           "#9C27B0",
    "Reg-Down":         "#F44336",
    "Non-Spin":         "#00BCD4",
}


def annual_summary(dispatch: pd.DataFrame, power_mw: float) -> dict:
    """
    Return a dict of KPIs for a full-year dispatch.

    All monetary values are in USD.
    """
    total = dispatch["rev_total"].sum()
    by_stream = {v: dispatch[k].sum() for k, v in REVENUE_STREAMS.items()}

    throughput = (
        dispatch["p_discharge"].sum() + dispatch["p_charge"].sum()
    )  # MWh

    return {
        "total_revenue_usd": total,
        "revenue_per_mw_year": total / power_mw,
        "revenue_per_mwh_day": total / (dispatch["timestamp"].nunique() or 365),
        "energy_arbitrage_pct": by_stream["Energy Arbitrage"] / total * 100 if total else 0,
        "ancillary_pct": (total - by_stream["Energy Arbitrage"]) / total * 100 if total else 0,
        "throughput_mwh": throughput,
        "cycles": throughput / 2,  # one cycle = full charge + discharge
        "by_stream": by_stream,
    }


def monthly_revenue(dispatch: pd.DataFrame) -> pd.DataFrame:
    """Monthly revenue breakdown by stream."""
    df = dispatch.copy()
    df["month"] = pd.to_datetime(df["timestamp"]).dt.to_period("M")
    agg = {k: "sum" for k in REVENUE_STREAMS}
    agg["rev_total"] = "sum"
    monthly = df.groupby("month").agg(agg).reset_index()
    monthly["month"] = monthly["month"].dt.to_timestamp()
    return monthly


def daily_revenue(dispatch: pd.DataFrame) -> pd.DataFrame:
    """Daily total revenue."""
    df = dispatch.copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    daily = df.groupby("date")["rev_total"].sum().reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    return daily


def price_duration_curve(lmp: pd.Series, bins: int = 100) -> pd.DataFrame:
    """Return sorted price duration curve data."""
    sorted_prices = np.sort(lmp.values)[::-1]
    percentile = np.linspace(0, 100, len(sorted_prices))
    return pd.DataFrame({"percentile": percentile, "lmp": sorted_prices})


def dispatch_heatmap(dispatch: pd.DataFrame, column: str = "rev_total") -> pd.DataFrame:
    """
    Reshape hourly data into a (days × hours) pivot for a calendar heatmap.
    """
    df = dispatch.copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    pivot = df.pivot_table(
        index="date", columns="hour", values=column, aggfunc="sum"
    )
    return pivot


def spread_analysis(dispatch: pd.DataFrame) -> pd.DataFrame:
    """
    Compute daily price spread metrics: max-min, P90-P10, etc.
    These capture arbitrage opportunity each day.
    """
    df = dispatch.copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    return (
        df.groupby("date")["lmp"]
        .agg(
            spread_max_min=lambda x: x.max() - x.min(),
            spread_p90_p10=lambda x: x.quantile(0.9) - x.quantile(0.1),
            mean_price=lambda x: x.mean(),
            max_price=lambda x: x.max(),
            min_price=lambda x: x.min(),
        )
        .reset_index()
    )


def soc_summary(dispatch: pd.DataFrame) -> dict:
    """SOC statistics."""
    soc = dispatch["soc"]
    return {
        "mean_soc": soc.mean(),
        "std_soc": soc.std(),
        "pct_at_max": (soc >= soc.max() * 0.98).mean() * 100,
        "pct_at_min": (soc <= soc.min() * 1.02).mean() * 100,
    }
