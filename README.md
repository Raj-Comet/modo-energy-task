# ⚡ ERCOT Battery Revenue Stack Analyzer

**Take-home project · Modo Energy · March 2026**

---

## Problem Statement

Battery storage assets in ERCOT can earn revenue from multiple simultaneous sources — a practice called **revenue stacking**. The challenge every asset owner faces: *how should I allocate my battery's limited power and energy capacity across energy arbitrage and ancillary services to maximise total revenue?*

This tool answers that question with a full-year linear programme (LP) optimisation and an interactive Streamlit dashboard.

---

## What I Built

An end-to-end battery revenue stack analyser with:

| Component | Description |
|-----------|-------------|
| `app.py` | Interactive Streamlit dashboard — KPIs, charts, day-level dispatch explorer |
| `src/battery_optimizer.py` | Daily LP optimisation using HiGHS via `scipy.optimize.linprog` |
| `src/analytics.py` | Revenue aggregation, monthly breakdowns, spread analysis |
| `src/data_generator.py` | Synthetic ERCOT price generator calibrated to 2023–2024 actuals |
| `src/ercot_fetcher.py` | Real ERCOT data downloader (public MIS portal) |
| `notebooks/analysis.ipynb` | Exploratory analysis, sensitivity tests, finding validation |

### Dashboard Screenshots

> *Run `streamlit run app.py` to see the live version — or see below.*

**Revenue Stack (stacked monthly bars + donut breakdown)**  
**Market Prices (price duration curve, daily shape, spread scatter)**  
**Dispatch Detail (24-hr LMP / power / SOC panel, per-stream revenue bars)**  

---

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/modo-energy-task
cd modo-energy-task
pip install -r requirements.txt

# 2. Launch the dashboard (runs on synthetic ERCOT data immediately)
streamlit run app.py

# 3. (Optional) Download real ERCOT day-ahead prices
python -m src.ercot_fetcher --year 2024 --outdir data/real

# 4. Explore the analysis notebook
jupyter lab notebooks/analysis.ipynb
```

**Python 3.10+ required.** No API keys or paid data subscriptions needed.

---

## Revenue Streams Modelled

| Stream | ERCOT Product | How a Battery Earns |
|--------|---------------|---------------------|
| **Energy Arbitrage** | Real-Time LMP (HB_BUSAVG) | Charge cheap / discharge expensive |
| **ECRS** | ERCOT Contingency Reserve Service | Capacity payment to be available within 10 min |
| **RRS** | Responsive Reserve Service | Capacity payment for primary frequency response (30 sec) |
| **Reg-Up** | Regulation Up | Capacity payment for fast upward AGC response |
| **Reg-Down** | Regulation Down | Capacity payment for fast downward AGC response |
| **Non-Spin** | Non-Spinning Reserve | Capacity payment for offline 30-min reserve |

ECRS was introduced by ERCOT in 2023 following Winter Storm Uri and the grid reliability review — it's now one of the most valuable AS products for batteries.

---

## Optimisation Model

### Formulation

Each day is solved as a **Linear Programme** with perfect foresight (equivalent to submitting an optimal day-ahead bid):

**Objective** — maximise total daily revenue net of degradation cost:

```
max Σ_t [ LMP_t·(p_discharge_t - p_charge_t)
         + ECRS_t·q_ecrs_t
         + RRS_t·q_rrs_t  
         + RegUp_t·q_regup_t
         + RegDn_t·q_regdn_t
         + NonSpin_t·q_nsp_t
         - degradation_cost·(p_discharge_t + p_charge_t) ]
```

**Key constraints:**
- **SOC dynamics**: `soc[t] = soc[t-1] + η_c·p_charge[t] - (1/η_d)·p_discharge[t]`  
- **Power limit**: `p_discharge + q_ecrs + q_rrs + q_regup + q_nsp ≤ P_max`  
- **AS headroom**: SOC must cover committed AS capacity × 1 hour of dispatch  
- **Simultaneous C/D prevention**: `p_charge + p_discharge ≤ P_max` (LP approximation)  
- SOC floor/ceiling, per-product AS caps

**Solver**: HiGHS (via `scipy.optimize.linprog`), solving ~365 daily LPs in <30 seconds.

---

## Key Findings

1. **AS-dominated economics (~60% of revenue)**: ECRS and RRS together outvalue energy arbitrage for a 2-hour battery — consistent with ERCOT 2023-2024 market reports.

2. **Summer peak premium**: ERCOT's summer load creates 2–3× higher daily arbitrage revenue in July–August vs winter.

3. **Diminishing duration returns**: 1→2 hour storage captures ~80% of available value. Going to 4 hours adds ~10–15% more revenue — the first 2 hours capture most AS headroom and high-spread arbitrage.

4. **Negative prices**: ~2.5% of hours see negative prices (midday, spring). Charging during these periods is "free" and boosts net revenue.

5. **Indicative benchmark**: ~$90-110k/MW-year — in line with publicly reported ERCOT battery revenues for similar assets.

---

## Limitations & Next Steps

- **Perfect foresight** → add day-ahead price forecasting (gradient boosting or LSTM on lagged features) to simulate realistic bidding under uncertainty
- **AS dispatch probability** → model actual AS call rates to compute expected net revenue more accurately  
- **DA vs RT co-optimisation** → ERCOT has separate day-ahead and real-time markets; a full model would optimise across both
- **Capacity degradation** → battery energy capacity degrades ~2-3%/year; a multi-year model would track this
- **Price impact** → a large battery affects marginal prices; price-taking is reasonable for ≤500 MW

---

## Data Sources

- **Synthetic data**: Statistical model calibrated to ERCOT 2023-2024 actuals (settlement point prices, AS clearing prices)
- **Real data**: Available via [ERCOT MIS Portal](https://www.ercot.com/misapp/) — use `src/ercot_fetcher.py`
- All data used is publicly available without authentication

---

## AI Workflow

This project used AI tools throughout:

- **Problem scoping**: Used Claude to brainstorm which ERCOT revenue streams matter most for battery assets and to check the LP formulation logic
- **LP debugging**: Claude helped identify a subtle constraint bug in the AS headroom formulation (the reserve hours multiplier was on the wrong side of the inequality)
- **Code review**: Used Claude to review the data generator for statistical realism (daily shape function, spike probability calibration)
- **README drafting**: Initial structure drafted with AI, then refined with domain knowledge
- **Chart design**: Iterated on Plotly chart layouts for the Streamlit dashboard

The LP formulation, ERCOT market mechanics, and analytical findings reflect genuine domain knowledge, not AI-generated content.

---

## Repo Structure

```
.
├── app.py                      # Streamlit dashboard
├── requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── battery_optimizer.py    # LP optimisation engine
│   ├── analytics.py            # Revenue aggregations & KPIs
│   ├── data_generator.py       # Synthetic ERCOT data
│   └── ercot_fetcher.py        # Real ERCOT data downloader
├── notebooks/
│   └── analysis.ipynb          # EDA, sensitivity analysis, validation
└── data/                       # Auto-created on first run
```

---

*Built in ~3.5 hours · March 2026*
