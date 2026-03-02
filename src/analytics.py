"""
Revenue Analytics - Aggregation and Analysis Tools

Computes:
- Daily/monthly/annual revenue rollups
- Revenue stream breakdown (energy vs ancillary services)
- Duration sensitivity analysis
- Performance metrics
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple


class RevenueAnalytics:
    """
    Aggregates and analyzes battery dispatch optimization results.
    """
    
    def __init__(self):
        """Initialize analytics engine."""
        pass
    
    def daily_summary(self, dispatch: pd.DataFrame, prices: pd.DataFrame) -> Dict:
        """
        Summarize one day's dispatch and revenue.
        
        Args:
            dispatch: DataFrame from optimizer.optimize_day()['dispatch']
            prices: DataFrame with hourly [lmp, reg_up, reg_down] columns
            
        Returns:
            Dict with daily metrics
        """
        if dispatch.empty:
            return {
                'revenue_energy': 0,
                'revenue_as': 0,
                'revenue_total': 0,
                'energy_charged': 0,
                'energy_discharged': 0,
                'soc_min': 0,
                'soc_max': 0,
            }
        
        revenue_energy = np.sum(prices['lmp'].values * (dispatch['pdis'].values - dispatch['pch'].values))
        revenue_as = np.sum(
            prices['reg_up'].values * dispatch['preg_up'].values +
            prices['reg_down'].values * dispatch['preg_down'].values
        )
        
        return {
            'revenue_energy': revenue_energy,
            'revenue_as': revenue_as,
            'revenue_total': revenue_energy + revenue_as,
            'energy_charged': dispatch['pch'].sum(),
            'energy_discharged': dispatch['pdis'].sum(),
            'as_provided': dispatch['preg_up'].sum() + dispatch['preg_down'].sum(),
            'soc_min': dispatch['soc'].min(),
            'soc_max': dispatch['soc'].max(),
            'cycles': dispatch['pdis'].sum() / 200,  # Rough cycle estimate
        }
    
    def aggregate_results(self, daily_results: List[Dict]) -> Dict:
        """
        Aggregate daily results to annual level.
        
        Args:
            daily_results: List of dicts from daily_summary()
            
        Returns:
            Annual aggregated metrics
        """
        df = pd.DataFrame(daily_results)
        
        return {
            'revenue_energy': df['revenue_energy'].sum(),
            'revenue_as': df['revenue_as'].sum(),
            'revenue_total': df['revenue_total'].sum(),
            'revenue_per_mw_year': df['revenue_total'].sum() / 100,  # Assuming 100 MW
            'energy_throughput': df['energy_discharged'].sum(),
            'avg_daily_revenue': df['revenue_total'].mean(),
            'revenue_as_pct': df['revenue_as'].sum() / (df['revenue_as'].sum() + df['revenue_energy'].sum() + 1e-9) * 100,
            'days_analyzed': len(df),
        }
    
    def monthly_breakdown(self, all_days_results: List[Dict], dates: List[pd.Timestamp]) -> pd.DataFrame:
        """
        Break down annual results by month.
        
        Args:
            all_days_results: List of daily summaries
            dates: List of datetime for each daily result
            
        Returns:
            DataFrame with monthly aggregates
        """
        df = pd.DataFrame(all_days_results)
        df['date'] = pd.to_datetime(dates)
        df['month'] = df['date'].dt.month
        df['month_name'] = df['date'].dt.strftime('%B')
        
        monthly = df.groupby('month').agg({
            'revenue_energy': 'sum',
            'revenue_as': 'sum',
            'revenue_total': 'sum',
            'energy_discharged': 'sum',
            'soc_max': 'mean',
        }).reset_index()
        
        monthly['month_name'] = ['January', 'February', 'March', 'April', 'May', 'June',
                                  'July', 'August', 'September', 'October', 'November', 'December']
        
        return monthly
    
    def duration_sensitivity(
        self,
        results_dict: Dict[float, float]
    ) -> pd.DataFrame:
        """
        Analyze how revenue scales with duration (energy capacity).
        
        Args:
            results_dict: Dict mapping duration_hours -> annual_revenue
            
        Returns:
            DataFrame with duration analysis
        """
        durations = sorted(results_dict.keys())
        revenues = [results_dict[d] for d in durations]
        
        incremental = [0]  # 1st duration baseline
        for i in range(1, len(revenues)):
            pct_increase = ((revenues[i] - revenues[i-1]) / revenues[i-1]) * 100
            incremental.append(pct_increase)
        
        df = pd.DataFrame({
            'duration_hours': durations,
            'annual_revenue': revenues,
            'revenue_per_mw_year': [r / 100 for r in revenues],
            'incremental_gain_pct': incremental,
        })
        
        return df
    
    def revenue_stream_breakdown(self, daily_results: List[Dict]) -> Dict:
        """
        Decompose total revenue into energy arbitrage vs ancillary services.
        
        Args:
            daily_results: List of daily summary dicts
            
        Returns:
            Dict with revenue components and percentages
        """
        df = pd.DataFrame(daily_results)
        
        total_energy = df['revenue_energy'].sum()
        total_as = df['revenue_as'].sum()
        total = total_energy + total_as
        
        return {
            'revenue_energy': total_energy,
            'revenue_as': total_as,
            'revenue_total': total,
            'pct_energy': (total_energy / total * 100) if total > 0 else 0,
            'pct_as': (total_as / total * 100) if total > 0 else 0,
            'breakdown': {
                'energy_arbitrage': {
                    'amount': total_energy,
                    'pct': (total_energy / total * 100) if total > 0 else 0,
                    'description': 'Buy low, sell high arbitrage',
                },
                'ancillary_services': {
                    'amount': total_as,
                    'pct': (total_as / total * 100) if total > 0 else 0,
                    'description': 'Regulation, contingency, ramping services',
                },
            },
        }
    
    def efficiency_metrics(self, daily_results: List[Dict]) -> Dict:
        """
        Calculate battery utilization and efficiency metrics.
        
        Args:
            daily_results: List of daily summaries
            
        Returns:
            Dict with efficiency metrics
        """
        df = pd.DataFrame(daily_results)
        
        total_charged = df['energy_charged'].sum()
        total_discharged = df['energy_discharged'].sum()
        total_revenue = df['revenue_total'].sum()
        
        # Round-trip energy
        roundtrip = total_discharged / (total_charged + 1e-9) if total_charged > 0 else 0
        
        # Revenue per MWh cycled
        total_energy_cycled = (total_charged + total_discharged) / 2
        rev_per_mwh = total_revenue / (total_energy_cycled + 1e-9)
        
        return {
            'roundtrip_efficiency': roundtrip,
            'total_charged_mwh': total_charged,
            'total_discharged_mwh': total_discharged,
            'avg_soc_max': df['soc_max'].mean(),
            'avg_soc_min': df['soc_min'].mean(),
            'revenue_per_mwh_cycled': rev_per_mwh,
            'days_analyzed': len(df),
        }


if __name__ == "__main__":
    # Quick validation
    analytics = RevenueAnalytics()
    
    # Mock data
    mock_results = [
        {
            'revenue_energy': 500,
            'revenue_as': 400,
            'energy_discharged': 100,
            'soc_max': 180,
            'soc_min': 20,
        }
        for _ in range(365)
    ]
    
    summary = analytics.aggregate_results(mock_results)
    print("Annual Summary:")
    print(f"Total Revenue: ${summary['revenue_total']:.0f}")
    print(f"Per MW-year: ${summary['revenue_per_mw_year']:.2f}")
    
    breakdown = analytics.revenue_stream_breakdown(mock_results)
    print(f"\nEnergy: {breakdown['pct_energy']:.1f}%")
    print(f"AS: {breakdown['pct_as']:.1f}%")
