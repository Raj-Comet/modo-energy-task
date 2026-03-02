"""
ERCOT Data Generator - Synthetic Market Data for Battery Revenue Analysis

Generates realistic ERCOT price data including:
- Locational Marginal Prices (LMP)
- Ancillary Services (ECRS, RRS, Reg Up, Reg Down)
- Real-time and day-ahead spreads

Uses calibrated seasonal and temporal patterns from historical ERCOT market data.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple, Dict


class ERCOTDataGenerator:
    """
    Generates synthetic but realistic ERCOT market data for battery optimization.
    
    Prices are calibrated to 2024 ERCOT market conditions with:
    - Seasonal demand curves (summer peak, winter shoulder)
    - Intra-day patterns (peak hours 16-22)
    - Realistic ancillary service pricing
    - Correlated spreads for arbitrage
    """
    
    def __init__(self, seed: int = 42):
        """Initialize generator with optional random seed."""
        np.random.seed(seed)
        self.seed = seed
        
    def seasonal_shape(self, day_of_year: int) -> float:
        """
        Seasonal demand multiplier for price levels.
        
        Summer (Jun-Sep): Peak demand, high prices
        Winter (Dec-Feb): Shoulder demand, lower baseline
        Spring/Fall: Moderate
        """
        # Summer peak: June (152) to September (243)
        summer = day_of_year - 152
        if 0 <= summer < 91:
            # Peak shaped curve with max in August
            return 1.4 + 0.3 * np.sin((summer / 91) * np.pi)
        
        # Winter shoulder: December (335) and January (31)
        winter = day_of_year - 335
        if winter >= -31 or winter <= 31:
            return 0.8
        
        # Spring/Fall shoulder
        return 1.0
    
    def hourly_pattern(self, hour: int) -> float:
        """
        Intra-day demand pattern - peak hours 16-22 (4PM-10PM).
        
        Shapes energy prices within the day:
        - Night (0-5): 0.85x (low demand)
        - Morning ramp (6-11): 0.95x
        - Afternoon (12-15): 1.05x
        - Evening peak (16-22): 1.35x (critical peak, solar ramping)
        - Night (23): 0.90x
        """
        if 0 <= hour < 6:
            return 0.85
        elif 6 <= hour < 12:
            return 0.95
        elif 12 <= hour < 16:
            return 1.05
        elif 16 <= hour <= 22:
            # Sharp peak at hours 17-18 (4-5 PM) when solar ramps down
            if 17 <= hour <= 18:
                return 1.45
            return 1.35
        else:  # 23
            return 0.90
    
    def generate_daily_prices(self, date: datetime) -> Dict[str, np.ndarray]:
        """
        Generate 24-hour price profile for a single day.
        
        Returns dict with keys:
        - 'lmp': 24-hour locational marginal prices ($/MWh)
        - 'ecrs': energy storage services ($/MW/h)
        - 'rrs': responsive reserve services ($/MW/h)
        - 'reg_up': regulation up ($/MW/h)
        - 'reg_down': regulation down ($/MW/h)
        """
        day_of_year = date.timetuple().tm_yday
        seasonal = self.seasonal_shape(day_of_year)
        
        # Base LMP from seasonal pattern
        base_lmp = 35 + seasonal * 25  # $35-$90/MWh range
        
        # Add daily volatility and hour-specific patterns
        hours = np.arange(24)
        hourly_mult = np.array([self.hourly_pattern(h) for h in hours])
        
        # Brownian motion for realistic price paths
        noise = np.cumsum(np.random.normal(0, 2, 24))
        noise = (noise - noise.mean()) / (noise.std() + 1e-6) * 5  # Normalize
        
        lmp = base_lmp * hourly_mult + noise
        lmp = np.clip(lmp, 15, 150)  # Realistic ERCOT bounds
        
        # AS pricing: inversely correlated with LMP (more needed when prices high)
        # But also shows own dynamics for scarcity events
        as_multiplier = 1.5 / (lmp / base_lmp + 0.5)  # Inverse relationship
        
        prices = {
            'lmp': lmp,
            'ecrs': (2 + 0.5 * as_multiplier + np.random.normal(0, 0.3, 24)),
            'rrs': (3 + 0.8 * as_multiplier + np.random.normal(0, 0.4, 24)),
            'reg_up': (4 + 1.0 * as_multiplier + np.random.normal(0, 0.5, 24)),
            'reg_down': (3 + 0.8 * as_multiplier + np.random.normal(0, 0.4, 24)),
        }
        
        # Ensure all prices are positive
        for key in prices:
            prices[key] = np.clip(prices[key], 0.1, None)
        
        return prices
    
    def generate_year(self, year: int = 2024, node: str = "HB_NORTH") -> pd.DataFrame:
        """
        Generate full year of hourly market data for optimization.
        
        Args:
            year: Calendar year
            node: ERCOT pricing node (default HB_NORTH - Houston area)
            
        Returns:
            DataFrame with 8760 rows (hourly) and columns:
            ['datetime', 'hour', 'lmp', 'ecrs', 'rrs', 'reg_up', 'reg_down']
        """
        start_date = datetime(year, 1, 1)
        dates = [start_date + timedelta(days=d) for d in range(365)]
        
        data = []
        
        for date in dates:
            daily_prices = self.generate_daily_prices(date)
            
            for hour in range(24):
                row = {
                    'datetime': date + timedelta(hours=hour),
                    'hour': hour,
                    'lmp': daily_prices['lmp'][hour],
                    'ecrs': daily_prices['ecrs'][hour],
                    'rrs': daily_prices['rrs'][hour],
                    'reg_up': daily_prices['reg_up'][hour],
                    'reg_down': daily_prices['reg_down'][hour],
                    'node': node,
                }
                data.append(row)
        
        df = pd.DataFrame(data)
        return df
    
    def generate_month(self, year: int, month: int, node: str = "HB_NORTH") -> pd.DataFrame:
        """Generate one month of hourly market data."""
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        dates = []
        current = start_date
        while current < end_date:
            dates.append(current)
            current += timedelta(days=1)
        
        data = []
        
        for date in dates:
            daily_prices = self.generate_daily_prices(date)
            
            for hour in range(24):
                row = {
                    'datetime': date + timedelta(hours=hour),
                    'hour': hour,
                    'lmp': daily_prices['lmp'][hour],
                    'ecrs': daily_prices['ecrs'][hour],
                    'rrs': daily_prices['rrs'][hour],
                    'reg_up': daily_prices['reg_up'][hour],
                    'reg_down': daily_prices['reg_down'][hour],
                    'node': node,
                }
                data.append(row)
        
        df = pd.DataFrame(data)
        return df


if __name__ == "__main__":
    # Quick validation
    gen = ERCOTDataGenerator(seed=42)
    df = gen.generate_month(2024, 1)
    
    print(f"Generated {len(df)} hours of data")
    print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    print(f"\nPrice statistics:")
    print(df[['lmp', 'ecrs', 'rrs', 'reg_up', 'reg_down']].describe())
