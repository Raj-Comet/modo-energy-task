"""
ERCOT Data Fetcher - Real Market Data Integration

Fetches actual ERCOT market data from public sources:
- Settlement Point Prices (DAM LMP)
- Real-Time Market data
- Ancillary Services pricing

Uses ERCOT MIS (Market Information System) publicly available data.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict
import warnings


class ERCOTFetcher:
    """
    Fetches real ERCOT market data from public API and databases.
    
    Note: ERCOT data is freely available via:
    - ERCOT MIS: https://www.ercot.com/market-data
    - ERCOT Hourly Load Data
    - DAM & RTM Settlement Points
    """
    
    def __init__(self):
        """Initialize ERCOT fetcher."""
        self.base_url = "https://www.ercot.com"
        self.pricing_node = "HB_NORTH"  # Houston area hub
        
    def fetch_dam_prices(
        self,
        start_date: datetime,
        end_date: datetime,
        node: str = "HB_NORTH"
    ) -> Optional[pd.DataFrame]:
        """
        Fetch Day-Ahead Market (DAM) prices for a date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            node: ERCOT pricing node
            
        Returns:
            DataFrame with hourly DAM LMP or None if fetch fails
            
        Note: In production, this would connect to ERCOT MIS or a data provider API.
        For demonstration, returns None to indicate the need for real data source.
        """
        try:
            # In a real scenario, this would query the ERCOT MIS API or a data provider
            # For now, we return None to indicate real data would be fetched here
            warnings.warn(
                "fetch_dam_prices: Real ERCOT API integration not configured. "
                "Use ERCOTDataGenerator for demo purposes."
            )
            return None
        except Exception as e:
            print(f"Error fetching DAM prices: {e}")
            return None
    
    def fetch_rtm_prices(
        self,
        start_date: datetime,
        end_date: datetime,
        node: str = "HB_NORTH"
    ) -> Optional[pd.DataFrame]:
        """
        Fetch Real-Time Market (RTM) prices for a date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            node: ERCOT pricing node
            
        Returns:
            DataFrame with hourly RTM LMP or None if fetch fails
        """
        try:
            warnings.warn(
                "fetch_rtm_prices: Real ERCOT API integration not configured. "
                "Use ERCOTDataGenerator for demo purposes."
            )
            return None
        except Exception as e:
            print(f"Error fetching RTM prices: {e}")
            return None
    
    def fetch_as_prices(
        self,
        start_date: datetime,
        end_date: datetime,
        service_type: str = "RRS"
    ) -> Optional[pd.DataFrame]:
        """
        Fetch Ancillary Services (AS) prices.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            service_type: One of ['RRS', 'ECRS', 'Reg Up', 'Reg Down']
            
        Returns:
            DataFrame with hourly AS prices or None if fetch fails
        """
        try:
            warnings.warn(
                "fetch_as_prices: Real ERCOT API integration not configured. "
                "Use ERCOTDataGenerator for demo purposes."
            )
            return None
        except Exception as e:
            print(f"Error fetching AS prices: {e}")
            return None
    
    def fetch_load_forecast(
        self,
        date: datetime
    ) -> Optional[pd.DataFrame]:
        """
        Fetch ERCOT load forecast for a date.
        
        Args:
            date: Date to fetch forecast for
            
        Returns:
            DataFrame with hourly load forecast (MW) or None if fetch fails
        """
        try:
            warnings.warn(
                "fetch_load_forecast: Real ERCOT API integration not configured. "
                "Use ERCOTDataGenerator for demo purposes."
            )
            return None
        except Exception as e:
            print(f"Error fetching load forecast: {e}")
            return None
    
    def get_available_nodes(self) -> list:
        """
        Get list of available ERCOT pricing nodes.
        
        Returns:
            List of ERCOT node names
        """
        return [
            "HB_NORTH",      # Houston area
            "HB_HOUSTON",    # Central Houston
            "HB_SOUTH",      # South Houston
            "HB_WEST",       # West Houston
            "NORTH",         # North Texas
            "SOUTH",         # South Texas
            "EAST",          # East Texas
            "WEST",          # West Texas
        ]
    
    @staticmethod
    def calibrate_synthetic_to_actual(
        synthetic_df: pd.DataFrame,
        actual_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calibrate synthetic prices to match actual ERCOT price distributions.
        
        Args:
            synthetic_df: Synthetic prices from ERCOTDataGenerator
            actual_df: Actual historical prices
            
        Returns:
            Calibrated synthetic prices
        """
        for col in ['lmp', 'ecrs', 'rrs', 'reg_up', 'reg_down']:
            if col in synthetic_df.columns and col in actual_df.columns:
                # Match mean
                synthetic_mean = synthetic_df[col].mean()
                actual_mean = actual_df[col].mean()
                
                synthetic_df[col] = synthetic_df[col] * (actual_mean / synthetic_mean)
                
                # Match std
                synthetic_std = synthetic_df[col].std()
                actual_std = actual_df[col].std()
                
                synthetic_df[col] = (
                    (synthetic_df[col] - synthetic_df[col].mean()) *
                    (actual_std / synthetic_std) +
                    actual_mean
                )
        
        return synthetic_df


if __name__ == "__main__":
    fetcher = ERCOTFetcher()
    
    print("Available ERCOT pricing nodes:")
    for node in fetcher.get_available_nodes():
        print(f"  - {node}")
    
    print("\nNote: Real API integration requires ERCOT MIS credentials or data provider subscription.")
    print("For development, use ERCOTDataGenerator with synthetic but realistic price data.")
