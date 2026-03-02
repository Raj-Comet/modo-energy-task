"""
ERCOT Battery Revenue Stack Analyzer
=====================================
Streamlit dashboard to explore how a grid-scale battery storage asset
can stack revenues across energy arbitrage and ancillary services in ERCOT.

Run:
    streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analytics import (
    REVENUE_STREAMS,
    STREAM_COLORS,
    annual_summary,
    daily_revenue,
    dispatch_heatmap,
    monthly_revenue,
    price_duration_curve,
    spread_analysis,
)
from src.battery_optimizer import BatteryAsset, run_full_year
from src.data_generator import generate_market_data

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ERCOT Battery Revenue Stack Analyzer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #313244;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #cdd6f4;
        margin-bottom: 0.5rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/ERCOT_logo.svg/200px-ERCOT_logo.svg.png",
        width=120,
    )
    st.title("⚡ Configuration")
    st.markdown("---")

    st.subheader("📅 Analysis Period")
    year = st.selectbox("Year", [2024, 2023, 2022], index=0)

    st.subheader("🔋 Battery Asset")
    power_mw = st.slider("Power (MW)", 10, 500, 100, 10)
    duration_hr = st.slider("Duration (hrs)", 1, 6, 2, 1)
    energy_mwh = power_mw * duration_hr

    st.caption(f"Energy capacity: **{energy_mwh:,} MWh**")

    st.subheader("⚙️ Efficiency")
    rte = st.slider("Round-Trip Efficiency (%)", 75, 97, 86, 1) / 100
    eta = rte ** 0.5   # split equally between charge / discharge

    st.subheader("💰 Market Strategy")
    use_energy = st.checkbox("Energy Arbitrage", value=True)
    use_ecrs   = st.checkbox("ECRS", value=True)
    use_rrs    = st.checkbox("RRS", value=True)
    use_reg    = st.checkbox("Regulation (Up & Down)", value=True)
    use_nsp    = st.checkbox("Non-Spinning Reserve", value=True)

    st.subheader("💵 Cost Assumptions")
    deg_cost = st.slider(
        "Degradation cost ($/MWh throughput)", 0.0, 3.0, 0.50, 0.25
    )

    st.markdown("---")
    run_btn = st.button("▶ Run Optimisation", type="primary", use_container_width=True)


# ── State management ──────────────────────────────────────────────────────────
if "dispatch" not in st.session_state:
    st.session_state.dispatch = None
if "market_df" not in st.session_state:
    st.session_state.market_df = None
if "asset" not in st.session_state:
    st.session_state.asset = None


def _run_optimisation():
    """Run full-year LP optimisation with progress bar."""
    with st.spinner("Generating ERCOT market data…"):
        market_df = generate_market_data(
            start=f"{year}-01-01",
            end=f"{year}-12-31",
            seed=year,
        )
        # Zero out streams not selected
        if not use_energy:
            market_df["lmp"] = 0.0
        if not use_ecrs:
            market_df["ecrs"] = 0.0
        if not use_rrs:
            market_df["rrs"] = 0.0
        if not use_reg:
            market_df["reg_up"] = 0.0
            market_df["reg_dn"] = 0.0
        if not use_nsp:
            market_df["non_spin"] = 0.0

        st.session_state.market_df = market_df

    asset = BatteryAsset(
        power_mw=power_mw,
        energy_mwh=energy_mwh,
        eta_charge=eta,
        eta_discharge=eta,
        degradation_cost=deg_cost,
    )
    st.session_state.asset = asset

    progress = st.progress(0, text="Optimising daily dispatch…")

    def cb(current, total):
        pct = int(current / total * 100)
        progress.progress(pct, text=f"Optimising day {current}/{total}…")

    dispatch = run_full_year(market_df, asset, progress_callback=cb)
    st.session_state.dispatch = dispatch
    progress.empty()
    st.success("✅ Optimisation complete!")


# Auto-run on first load
if st.session_state.dispatch is None:
    _run_optimisation()

if run_btn:
    _run_optimisation()

# ── Retrieve state ─────────────────────────────────────────────────────────────
dispatch   = st.session_state.dispatch
market_df  = st.session_state.market_df
asset      = st.session_state.asset

if dispatch is None:
    st.warning("Run the optimisation using the sidebar button.")
    st.stop()

# ── Compute analytics ─────────────────────────────────────────────────────────
summary    = annual_summary(dispatch, power_mw)
monthly    = monthly_revenue(dispatch)
daily      = daily_revenue(dispatch)
spreads    = spread_analysis(dispatch)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("⚡ ERCOT Battery Revenue Stack Analyzer")
st.caption(
    f"**{power_mw} MW / {energy_mwh} MWh** asset · ERCOT Hub Average · "
    f"RTE {rte*100:.0f}% · Analysis year {year}"
)
st.markdown("---")

# ── KPI row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)

total_rev  = summary["total_revenue_usd"]
rev_per_mw = summary["revenue_per_mw_year"]

k1.metric(
    "Total Annual Revenue",
    f"${total_rev:,.0f}",
    help="Sum of all revenue streams, net of degradation cost",
)
k2.metric(
    "Revenue / MW-year",
    f"${rev_per_mw:,.0f}",
    help="Normalised to power capacity — the key benchmark metric",
)
k3.metric(
    "Energy Arbitrage Share",
    f"{summary['energy_arbitrage_pct']:.1f}%",
    help="Fraction of total revenue from energy price spread",
)
k4.metric(
    "Ancillary Services Share",
    f"{summary['ancillary_pct']:.1f}%",
    help="Fraction of total revenue from AS capacity payments",
)
k5.metric(
    "Equivalent Cycles",
    f"{summary['cycles']:.0f}",
    help="Total MWh throughput / (2 × energy capacity) ≈ full cycles",
)

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_rev, tab_prices, tab_dispatch, tab_method = st.tabs(
    ["📊 Revenue Analysis", "📈 Market Prices", "🔋 Dispatch Detail", "📖 Methodology"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – Revenue Analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab_rev:
    col_left, col_right = st.columns([3, 2])

    with col_left:
        # Stacked monthly revenue bar chart
        stream_labels = {k: v for k, v in REVENUE_STREAMS.items()}
        fig = go.Figure()
        for col, label in stream_labels.items():
            fig.add_trace(
                go.Bar(
                    x=monthly["month"].dt.strftime("%b"),
                    y=monthly[col] / 1000,
                    name=label,
                    marker_color=STREAM_COLORS[label],
                )
            )
        fig.update_layout(
            barmode="stack",
            title="Monthly Revenue by Stream ($000s)",
            xaxis_title=None,
            yaxis_title="Revenue ($000s)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            height=380,
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        # Donut chart — revenue stream breakdown
        by_stream = summary["by_stream"]
        labels = list(by_stream.keys())
        values = [max(v, 0) for v in by_stream.values()]
        colors = [STREAM_COLORS[l] for l in labels]

        fig_pie = go.Figure(
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker_colors=colors,
                textinfo="percent+label",
                textfont_size=11,
            )
        )
        fig_pie.update_layout(
            title="Revenue Mix (full year)",
            height=380,
            template="plotly_dark",
            showlegend=False,
            annotations=[
                dict(
                    text=f"${total_rev/1e6:.2f}M",
                    x=0.5, y=0.5,
                    font_size=18,
                    showarrow=False,
                )
            ],
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # Daily revenue heatmap
    st.markdown("### Daily Revenue Calendar Heatmap")
    daily["dow"] = daily["date"].dt.day_name().str[:3]
    daily["week"] = daily["date"].dt.isocalendar().week.astype(int)
    daily["month_label"] = daily["date"].dt.strftime("%b")

    fig_cal = px.scatter(
        daily,
        x="week",
        y="dow",
        color="rev_total",
        color_continuous_scale="RdYlGn",
        size=[6] * len(daily),
        size_max=16,
        hover_data={"date": True, "rev_total": ":.0f", "week": False, "dow": False},
        labels={"rev_total": "Revenue ($)", "week": "Week of Year", "dow": "Day"},
        title=f"Daily Total Revenue — {year}  (green = high earnings, red = low/negative)",
        height=280,
    )
    fig_cal.update_layout(template="plotly_dark", yaxis=dict(
        categoryorder="array",
        categoryarray=["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    ))
    st.plotly_chart(fig_cal, use_container_width=True)

    # Revenue percentile table
    st.markdown("### Best & Worst Days")
    top_days = (
        daily.nlargest(5, "rev_total")[["date", "rev_total"]]
        .assign(date=lambda x: x["date"].dt.strftime("%d %b %Y"))
        .rename(columns={"date": "Date", "rev_total": "Revenue ($)"})
    )
    bot_days = (
        daily.nsmallest(5, "rev_total")[["date", "rev_total"]]
        .assign(date=lambda x: x["date"].dt.strftime("%d %b %Y"))
        .rename(columns={"date": "Date", "rev_total": "Revenue ($)"})
    )
    c1, c2 = st.columns(2)
    c1.markdown("**🏆 Top 5 Revenue Days**")
    c1.dataframe(top_days.reset_index(drop=True), hide_index=True)
    c2.markdown("**📉 Bottom 5 Revenue Days**")
    c2.dataframe(bot_days.reset_index(drop=True), hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – Market Prices
# ══════════════════════════════════════════════════════════════════════════════
with tab_prices:
    # Monthly avg prices
    mkt = market_df.copy()
    mkt["month"] = pd.to_datetime(mkt["timestamp"]).dt.to_period("M").dt.to_timestamp()
    monthly_prices = mkt.groupby("month")[["lmp", "ecrs", "rrs", "reg_up", "reg_dn"]].mean()

    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(
        x=monthly_prices.index, y=monthly_prices["lmp"].round(2),
        name="LMP ($/MWh)", line=dict(color="#2196F3", width=3),
        yaxis="y1",
    ))
    for col, name, color in [
        ("ecrs", "ECRS", "#FF9800"),
        ("rrs", "RRS", "#4CAF50"),
        ("reg_up", "Reg-Up", "#9C27B0"),
        ("reg_dn", "Reg-Down", "#F44336"),
    ]:
        fig_p.add_trace(go.Scatter(
            x=monthly_prices.index,
            y=monthly_prices[col].round(2),
            name=f"{name} ($/MW-hr)",
            yaxis="y2",
            line=dict(color=color, dash="dot"),
        ))

    fig_p.update_layout(
        title="Monthly Average Market Prices",
        yaxis=dict(title="LMP ($/MWh)", side="left"),
        yaxis2=dict(title="AS Price ($/MW-hr)", overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=420,
        template="plotly_dark",
    )
    st.plotly_chart(fig_p, use_container_width=True)

    col_a, col_b = st.columns(2)

    with col_a:
        # Price duration curve
        pdc = price_duration_curve(mkt["lmp"])
        fig_pdc = px.line(
            pdc,
            x="percentile",
            y="lmp",
            title="LMP Price Duration Curve",
            labels={"percentile": "% of Hours ≥ Price", "lmp": "LMP ($/MWh)"},
            template="plotly_dark",
            height=320,
        )
        fig_pdc.update_traces(line_color="#2196F3")
        fig_pdc.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="$0")
        st.plotly_chart(fig_pdc, use_container_width=True)

    with col_b:
        # Average daily price shape
        mkt["hour"] = pd.to_datetime(mkt["timestamp"]).dt.hour
        avg_shape = mkt.groupby("hour")["lmp"].mean().reset_index()
        fig_shape = px.bar(
            avg_shape,
            x="hour",
            y="lmp",
            title="Average Hourly Price Shape (Annual)",
            labels={"hour": "Hour of Day", "lmp": "Avg LMP ($/MWh)"},
            template="plotly_dark",
            height=320,
            color="lmp",
            color_continuous_scale="Blues",
        )
        fig_shape.update_coloraxes(showscale=False)
        st.plotly_chart(fig_shape, use_container_width=True)

    # Price spread vs arbitrage revenue scatter
    st.markdown("### Price Spread vs Arbitrage Revenue")
    merged = spreads.copy()
    merged["date"] = pd.to_datetime(merged["date"])
    daily_rev_map = daily.set_index("date")["rev_total"]
    merged["rev_total"] = merged["date"].map(daily_rev_map)
    merged["month"] = merged["date"].dt.strftime("%b")

    fig_scat = px.scatter(
        merged,
        x="spread_max_min",
        y="rev_total",
        color="month",
        hover_data=["date", "mean_price"],
        labels={
            "spread_max_min": "Daily Max–Min Price Spread ($/MWh)",
            "rev_total": "Daily Total Revenue ($)",
        },
        title="Daily Price Spread vs Total Battery Revenue",
        template="plotly_dark",
        height=360,
        opacity=0.7,
    )
    fig_scat.update_traces(marker_size=5)
    corr = merged[["spread_max_min", "rev_total"]].corr().iloc[0, 1]
    st.caption(f"Pearson correlation: **{corr:.2f}** — as expected, high-spread days drive revenue")
    st.plotly_chart(fig_scat, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – Dispatch Detail
# ══════════════════════════════════════════════════════════════════════════════
with tab_dispatch:
    st.markdown("### Explore a Single Day's Dispatch")

    sel_date = st.date_input(
        "Select date",
        value=pd.Timestamp(f"{year}-07-15").date(),
        min_value=pd.Timestamp(f"{year}-01-01").date(),
        max_value=pd.Timestamp(f"{year}-12-31").date(),
    )

    day_disp = dispatch[
        pd.to_datetime(dispatch["timestamp"]).dt.date == sel_date
    ].copy()

    if day_disp.empty:
        st.warning("No dispatch data for this date.")
    else:
        day_disp = day_disp.reset_index(drop=True)
        hours = day_disp["timestamp"].dt.hour

        # Four-panel chart
        fig_day = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            subplot_titles=("LMP ($/MWh)", "Battery Power & AS (MW)", "State of Charge (MWh)"),
            row_heights=[0.33, 0.40, 0.27],
            vertical_spacing=0.08,
        )

        # LMP
        fig_day.add_trace(
            go.Scatter(x=hours, y=day_disp["lmp"], name="LMP", line=dict(color="#2196F3", width=2)),
            row=1, col=1,
        )
        fig_day.add_hline(y=0, line_dash="dash", line_color="gray", row=1, col=1)

        # Power
        fig_day.add_trace(
            go.Bar(x=hours, y=day_disp["p_discharge"], name="Discharge", marker_color="#4CAF50"),
            row=2, col=1,
        )
        fig_day.add_trace(
            go.Bar(x=hours, y=-day_disp["p_charge"], name="Charge", marker_color="#F44336"),
            row=2, col=1,
        )
        for col_as, name_as, color_as in [
            ("q_ecrs", "ECRS", "#FF9800"),
            ("q_rrs", "RRS", "#9C27B0"),
            ("q_reg_up", "Reg-Up", "#00BCD4"),
        ]:
            fig_day.add_trace(
                go.Scatter(
                    x=hours, y=day_disp[col_as],
                    name=name_as, mode="lines",
                    line=dict(color=color_as, dash="dot"),
                ),
                row=2, col=1,
            )

        # SOC
        fig_day.add_trace(
            go.Scatter(
                x=hours,
                y=day_disp["soc"],
                name="SOC",
                fill="tozeroy",
                line=dict(color="#FFD700", width=2),
                fillcolor="rgba(255, 215, 0, 0.15)",
            ),
            row=3, col=1,
        )
        fig_day.add_hline(
            y=asset.soc_min_mwh, line_dash="dash", line_color="red",
            annotation_text="Min SOC", row=3, col=1,
        )
        fig_day.add_hline(
            y=asset.soc_max_mwh, line_dash="dash", line_color="green",
            annotation_text="Max SOC", row=3, col=1,
        )

        fig_day.update_layout(
            height=600,
            template="plotly_dark",
            title=f"Dispatch: {sel_date}  |  Day Revenue: ${day_disp['rev_total'].sum():,.0f}",
            showlegend=True,
            legend=dict(orientation="h", y=-0.08),
            barmode="relative",
        )
        fig_day.update_xaxes(title_text="Hour of Day", row=3, col=1)
        st.plotly_chart(fig_day, use_container_width=True)

        # Revenue bar for the day
        day_stream_rev = {REVENUE_STREAMS[k]: day_disp[k].sum() for k in REVENUE_STREAMS}
        fig_rev_day = go.Figure(
            go.Bar(
                x=list(day_stream_rev.keys()),
                y=list(day_stream_rev.values()),
                marker_color=[STREAM_COLORS[l] for l in day_stream_rev],
                text=[f"${v:,.0f}" for v in day_stream_rev.values()],
                textposition="outside",
            )
        )
        fig_rev_day.update_layout(
            title=f"Revenue by Stream — {sel_date}",
            yaxis_title="Revenue ($)",
            template="plotly_dark",
            height=280,
        )
        st.plotly_chart(fig_rev_day, use_container_width=True)

    # Full-year SOC profile (sampled)
    st.markdown("### Full-Year State of Charge Profile")
    soc_weekly = dispatch.set_index("timestamp")["soc"].resample("6h").mean().reset_index()
    fig_soc = go.Figure(
        go.Scatter(
            x=soc_weekly["timestamp"],
            y=soc_weekly["soc"],
            fill="tozeroy",
            line=dict(color="#FFD700", width=1),
            fillcolor="rgba(255,215,0,0.1)",
            name="SOC (6-hr avg)",
        )
    )
    fig_soc.add_hline(
        y=asset.soc_max_mwh * 0.95, line_dash="dash", line_color="green",
        annotation_text="95% SOC cap",
    )
    fig_soc.add_hline(
        y=asset.soc_min_mwh * 1.05, line_dash="dash", line_color="red",
        annotation_text="5% SOC floor",
    )
    fig_soc.update_layout(
        title="Battery State of Charge — Full Year (6-hr average)",
        yaxis_title="SOC (MWh)",
        template="plotly_dark",
        height=300,
    )
    st.plotly_chart(fig_soc, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 – Methodology
# ══════════════════════════════════════════════════════════════════════════════
with tab_method:
    st.markdown(
        """
        ## Methodology

        ### Problem Statement
        Battery storage assets in ERCOT can earn revenue from multiple simultaneous
        sources — a practice called **revenue stacking**. The challenge is optimally
        allocating limited power and energy capacity across competing revenue streams
        in real time. This tool quantifies that opportunity and shows *how* an asset
        should dispatch hour-by-hour to maximise total revenue.

        ---

        ### Revenue Streams Modelled

        | Stream | Description | ERCOT Product |
        |--------|-------------|---------------|
        | **Energy Arbitrage** | Charge when prices are low, discharge when high | Real-Time LMP at HB_BUSAVG |
        | **ECRS** | Contingency reserve — must respond within 10 minutes | ERCOT Contingency Reserve Service |
        | **RRS** | Primary frequency response within 30 seconds | Responsive Reserve Service |
        | **Reg-Up** | Fast upward frequency regulation (AGC) | Regulation Up |
        | **Reg-Down** | Fast downward frequency regulation (AGC) | Regulation Down |
        | **Non-Spin** | Offline reserve, available within 30 minutes | Non-Spinning Reserve |

        AS capacity payments are made regardless of whether the service is called —
        the battery earns the clearing price simply by being *available*.

        ---

        ### Optimisation Model

        Each day is solved as a **Linear Programme (LP)** with perfect foresight over
        the 24-hour window (analogous to a day-ahead market bid):

        **Objective:** maximise total daily revenue across all streams, net of a
        degradation cost per MWh throughput.

        **Decision variables** (per hour):
        - `p_charge`, `p_discharge` — energy charge/discharge power (MW)
        - `soc` — state of charge (MWh)
        - `q_ecrs, q_rrs, q_reg_up, q_reg_dn, q_non_spin` — AS capacity offered (MW)

        **Key constraints:**
        - SOC dynamics: `soc[t] = soc[t-1] + η_c·p_c[t] − (1/η_d)·p_d[t]`
        - Power limit: discharge + all AS discharge products ≤ P_max
        - AS headroom: SOC must cover committed AS capacity × reserve duration
        - Simultaneous charge/discharge prevented by shared power limit

        The LP is solved daily using [HiGHS](https://highs.dev/) via `scipy.optimize.linprog`
        — an open-source, high-performance LP solver.

        ---

        ### Data
        Market prices are generated from a **calibrated statistical model** based on
        publicly reported ERCOT 2023–2024 actuals:
        - Energy prices: bimodal daily shape + Texas summer seasonal premium + 
          stochastic spikes (∼0.4% of hours) + negative price events (∼2.5% midday)
        - AS prices: log-normal with mild correlation to energy price tightness

        To use real ERCOT data, run `python -m src.ercot_fetcher --year 2024`.
        All ERCOT data used is publicly available via the
        [ERCOT MIS portal](https://www.ercot.com/misapp/).

        ---

        ### Limitations & Next Steps
        - **Perfect foresight**: Real-world dispatch uses forecasts, not actuals.
          Adding a forecasting layer (e.g. LSTM on price time-series) is the natural
          next step.
        - **AS dispatch probability**: The model assumes AS capacity is never called.
          In reality, partial dispatch reduces net revenue — modelling call rates would
          refine the estimates.
        - **Market impact**: A large battery affects prices at the margin. Price-taking
          is a reasonable approximation for assets ≤500 MW in ERCOT.
        - **Co-optimisation with Day-Ahead**: ERCOT runs a separate DAM — a full model
          would co-optimise DA vs RT exposure.

        ---
        *Built as a take-home project for Modo Energy · March 2026*
        """
    )
