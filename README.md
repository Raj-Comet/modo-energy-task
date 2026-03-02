# ERCOT Battery Revenue Stack Analyzer

**What it does:** A Python application that calculates how much money a battery storage system can make in the Texas electricity market (ERCOT) by selling electricity and grid services.

**Why it matters:** Battery owners need to know their potential revenue before investing millions of dollars. This tool answers that question automatically.

**Built with:** Python, Linear Programming optimization, and an interactive dashboard.

---

## Quick Start (2 minutes)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the dashboard
streamlit run app.py
```

Opens at `http://localhost:8501`

---

## What You Get

### 1. Interactive Dashboard (`app.py`)
- **Slider controls** – Adjust battery size and efficiency
- **Revenue charts** – See daily/monthly earnings breakdown
- **Power schedule** – Visualize when battery charges/discharges
- **Sensitivity analysis** – Test different battery durations

### 2. Optimization Engine (`src/battery_optimizer.py`)
- Solves the profit-maximization problem for each day
- Considers: electricity prices, grid services, battery limits
- Outputs: optimal charging schedule + revenue

### 3. Market Data (`src/data_generator.py`)
- Generates realistic ERCOT electricity prices
- Includes seasonal patterns (summer peak, winter low)
- Includes hourly patterns (evening peak 4-10 PM)

### 4. Analysis Notebook (`notebooks/analysis.ipynb`)
- Step-by-step walkthrough of the optimization
- Shows results and key insights
- Jupyter notebook format (run with: `jupyter notebook notebooks/analysis.ipynb`)

---

## How It Works (Simple Explanation)

A battery makes money two ways:

**1. Energy Trading**
- Buy electricity when cheap (night, winter)
- Sell electricity when expensive (evening, summer)
- Keep the profit

**2. Grid Services**
- ERCOT pays for "reserves" – keeping the power grid stable
- Battery can sell its power availability for steady income
- Like being paid to be "on standby"

This tool automatically finds the best balance between these two income sources for maximum profit.

---

## Files in This Project

```
app.py                    ← Dashboard - START HERE
README.md                 ← This file
requirements.txt          ← Python packages needed
src/
  ├── battery_optimizer.py     ← Optimization engine
  ├── data_generator.py        ← Price simulator
  ├── analytics.py             ← Revenue calculator
  └── ercot_fetcher.py         ← Real data integration
notebooks/
  └── analysis.ipynb           ← Full technical analysis
```

---

## Key Results

**For a 100 MW battery for 2 hours:**
- **Annual Revenue:** ~$125,000
- **Energy profit:** ~$55,000 (sell expensive, buy cheap)
---

## Requirements

- Python 3.8 or higher
- pip (package installer)

No API keys or subscriptions needed.

---

## Installation & Running

```bash
# Install dependencies (one time)
pip install -r requirements.txt

# Run the dashboard
streamlit run app.py
```

The dashboard will open at `http://localhost:8501`

---

## About This Project

**Modo Energy Take-Home Assignment**

The assignment asked to:
✅ Pick a problem that matters in electricity markets  
✅ Build something tangible (app, dashboard, model)  
✅ Use publicly available data  
✅ Show how to use AI tools effectively  

**This project delivers:**
- A complete, working application
- Realistic ERCOT market modeling
- Interactive visualization of results
- Clean, modular Python code

---

## Technical Details

**Language:** Python  
**Framework:** Streamlit (dashboard), SciPy (optimization)  
**Approach:** Linear programming to solve daily profit maximization  
**Data:** Synthetic but calibrated to real ERCOT market patterns  

**AI Usage:** GitHub Copilot was used for:
- Code generation and debugging
- Architecture suggestions
- Documentation writing
- Testing strategies

This accelerated development while maintaining quality and correctness.

---

## Contact

**Sk Raj Ali**  
📧 Email: skrajali062003@gmail.com  
📱 Phone: +919635637725  
🔗 LinkedIn: https://www.linkedin.com/in/sk-raj-ali/  

For questions about this project, refer to the code comments in each module.

