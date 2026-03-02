"""
Battery Dispatch Optimizer using Linear Programming

Solves a daily energy balance problem to maximize battery revenue across:
1. Energy arbitrage (buy low, sell high)
2. Ancillary services (ECRS, RRS, Reg Up, Reg Down)

Uses scipy.optimize.linprog with constraints for:
- State of charge (SOC) limits
- Power ramp rates
- Reservoir energy balance
"""

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from typing import Dict, Tuple, Optional


class BatteryOptimizer:
    """
    Daily optimal dispatch for grid-scale lithium battery storage.
    
    Solves: maximize revenue from energy arbitrage + ancillary services
    subject to: physical constraints (power, energy, ramps)
    
    Model structure:
    - Decision variables: Pch, Pdis, Preg_up, Preg_down per hour
    - Energy reservoir: SOC(t+1) = SOC(t) + ηch*Pch - Pdis/ηdis
    - AS provision reduces available energy for arbitrage
    """
    
    def __init__(
        self,
        power_capacity_mw: float = 100,
        energy_capacity_mwh: float = 200,
        charge_efficiency: float = 0.95,
        discharge_efficiency: float = 0.95,
        min_soc_pct: float = 0.1,
        max_soc_pct: float = 0.9,
        ramp_rate_mw_per_min: float = 0.5,
    ):
        """
        Initialize battery parameters.
        
        Args:
            power_capacity_mw: Maximum charge/discharge power (MW)
            energy_capacity_mwh: Energy reservoir size (MWh)
            charge_efficiency: Round-trip efficiency
            discharge_efficiency: Discharge efficiency
            min_soc_pct: Minimum state of charge (% of capacity)
            max_soc_pct: Maximum state of charge (% of capacity)
            ramp_rate_mw_per_min: Power ramp rate constraint
        """
        self.power_cap = power_capacity_mw
        self.energy_cap = energy_capacity_mwh
        self.eta_ch = charge_efficiency
        self.eta_dis = discharge_efficiency
        self.min_soc = min_soc_pct * energy_capacity_mwh
        self.max_soc = max_soc_pct * energy_capacity_mwh
        self.ramp_rate = ramp_rate_mw_per_min
        
    def optimize_day(
        self,
        prices: pd.DataFrame,
        initial_soc_mwh: Optional[float] = None,
        as_obligation_mw: Optional[Dict[str, float]] = None,
    ) -> Dict:
        """
        Optimize battery dispatch for a single 24-hour day.
        
        Args:
            prices: DataFrame with 24 rows and columns [lmp, ecrs, rrs, reg_up, reg_down]
            initial_soc_mwh: Starting state of charge (default: middle of range)
            as_obligation_mw: Dict with keys reg_up, reg_down specifying AS obligations
            
        Returns:
            Dict with optimized dispatch and revenue breakdown
        """
        if initial_soc_mwh is None:
            initial_soc_mwh = (self.min_soc + self.max_soc) / 2
        
        if as_obligation_mw is None:
            as_obligation_mw = {'reg_up': 0, 'reg_down': 0}
        
        n_hours = 24
        
        # Decision variables per hour: [Pch, Pdis, Preg_up, Preg_down, SOC]
        # Total: 24 hours × 5 variables = 120 variables
        n_vars = n_hours * 5
        
        # Objective: maximize revenue (minimize negative revenue)
        # Revenue = LMP * (Pdis - Pch) + ECRS*0 + RRS*(Preg_up+Preg_down) + ...
        c = np.zeros(n_vars)
        
        for h in range(n_hours):
            idx_ch = h * 5 + 0
            idx_dis = h * 5 + 1
            idx_reg_up = h * 5 + 2
            idx_reg_down = h * 5 + 3
            
            # Energy arbitrage revenue: sell high minus buy low
            c[idx_ch] = prices.iloc[h]['lmp'] * self.eta_ch  # Cost of charging (negative revenue)
            c[idx_dis] = -prices.iloc[h]['lmp'] / self.eta_dis  # Revenue from discharging
            
            # Ancillary service revenue (positive)
            c[idx_reg_up] = -prices.iloc[h]['reg_up']
            c[idx_reg_down] = -prices.iloc[h]['reg_down']
        
        # Inequality constraints: A_ub @ x <= b_ub
        A_ub = []
        b_ub = []
        
        for h in range(n_hours):
            idx_ch = h * 5 + 0
            idx_dis = h * 5 + 1
            idx_reg_up = h * 5 + 2
            idx_reg_down = h * 5 + 3
            idx_soc = h * 5 + 4
            
            # Power limits
            # Pch <= power_cap
            constraint = np.zeros(n_vars)
            constraint[idx_ch] = 1
            A_ub.append(constraint)
            b_ub.append(self.power_cap)
            
            # Pdis <= power_cap
            constraint = np.zeros(n_vars)
            constraint[idx_dis] = 1
            A_ub.append(constraint)
            b_ub.append(self.power_cap)
            
            # Preg_up <= power_cap
            constraint = np.zeros(n_vars)
            constraint[idx_reg_up] = 1
            A_ub.append(constraint)
            b_ub.append(self.power_cap)
            
            # Preg_down <= power_cap
            constraint = np.zeros(n_vars)
            constraint[idx_reg_down] = 1
            A_ub.append(constraint)
            b_ub.append(self.power_cap)
            
            # Energy-constrained AS: can't provide more than available
            # Preg_up + Preg_down <= 50MW (typical hourly AS requirement)
            constraint = np.zeros(n_vars)
            constraint[idx_reg_up] = 1
            constraint[idx_reg_down] = 1
            A_ub.append(constraint)
            b_ub.append(50)
            
            # SOC limits
            # SOC <= max_soc
            constraint = np.zeros(n_vars)
            constraint[idx_soc] = 1
            A_ub.append(constraint)
            b_ub.append(self.max_soc)
            
            # SOC >= min_soc
            # -SOC <= -min_soc
            constraint = np.zeros(n_vars)
            constraint[idx_soc] = -1
            A_ub.append(constraint)
            b_ub.append(-self.min_soc)
        
        # Equality constraints: energy balance
        A_eq = []
        b_eq = []
        
        # Hour 0 energy balance: SOC(1) = SOC(0) + Pch(0)*eta - Pdis(0)/eta
        constraint = np.zeros(n_vars)
        constraint[0 * 5 + 0] = self.eta_ch  # Pch
        constraint[0 * 5 + 1] = -1 / self.eta_dis  # Pdis
        constraint[0 * 5 + 4] = 1  # SOC(1)
        A_eq.append(constraint)
        b_eq.append(initial_soc_mwh)
        
        # Hours 1-23 energy balance
        for h in range(1, n_hours):
            constraint = np.zeros(n_vars)
            constraint[h * 5 + 0] = self.eta_ch
            constraint[h * 5 + 1] = -1 / self.eta_dis
            constraint[h * 5 + 4] = 1  # SOC(h)
            constraint[(h - 1) * 5 + 4] = -1  # -SOC(h-1)
            A_eq.append(constraint)
            b_eq.append(0)
        
        A_ub = np.array(A_ub)
        b_ub = np.array(b_ub)
        A_eq = np.array(A_eq)
        b_eq = np.array(b_eq)
        
        # Solve
        bounds = [(0, self.power_cap)] * (n_hours * 4) + [(self.min_soc, self.max_soc)] * n_hours
        
        result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method='highs')
        
        if not result.success:
            return {
                'success': False,
                'message': result.message,
                'dispatch': None,
                'revenue': 0,
            }
        
        # Parse solution
        dispatch = []
        for h in range(n_hours):
            idx_ch = h * 5 + 0
            idx_dis = h * 5 + 1
            idx_reg_up = h * 5 + 2
            idx_reg_down = h * 5 + 3
            idx_soc = h * 5 + 4
            
            dispatch.append({
                'hour': h,
                'pch': max(0, result.x[idx_ch]),
                'pdis': max(0, result.x[idx_dis]),
                'preg_up': max(0, result.x[idx_reg_up]),
                'preg_down': max(0, result.x[idx_reg_down]),
                'soc': max(self.min_soc, min(self.max_soc, result.x[idx_soc])),
            })
        
        # Calculate revenue
        revenue_energy = 0
        revenue_as = 0
        
        for h, row in enumerate(dispatch):
            revenue_energy += prices.iloc[h]['lmp'] * (row['pdis'] - row['pch'])
            revenue_as += prices.iloc[h]['reg_up'] * row['preg_up']
            revenue_as += prices.iloc[h]['reg_down'] * row['preg_down']
        
        return {
            'success': True,
            'dispatch': pd.DataFrame(dispatch),
            'revenue_energy': revenue_energy,
            'revenue_as': revenue_as,
            'revenue_total': revenue_energy + revenue_as,
            'initial_soc': initial_soc_mwh,
            'final_soc': dispatch[-1]['soc'],
        }


if __name__ == "__main__":
    # Quick validation
    from data_generator import ERCOTDataGenerator
    from datetime import datetime
    
    gen = ERCOTDataGenerator(seed=42)
    prices = gen.generate_daily_prices(datetime(2024, 1, 15))
    
    prices_df = pd.DataFrame({
        'lmp': prices['lmp'],
        'ecrs': prices['ecrs'],
        'rrs': prices['rrs'],
        'reg_up': prices['reg_up'],
        'reg_down': prices['reg_down'],
    })
    
    optimizer = BatteryOptimizer(power_capacity_mw=100, energy_capacity_mwh=200)
    result = optimizer.optimize_day(prices_df)
    
    print(f"Success: {result['success']}")
    print(f"Revenue - Energy: ${result['revenue_energy']:.2f}")
    print(f"Revenue - AS: ${result['revenue_as']:.2f}")
    print(f"Revenue - Total: ${result['revenue_total']:.2f}")
