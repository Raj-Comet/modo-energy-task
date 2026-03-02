"""
ERCOT Battery Revenue Stack Analyzer
A comprehensive tool for modeling grid-scale battery storage revenues across
energy arbitrage and ancillary services in ERCOT.
"""

__version__ = "1.0.0"
__author__ = "Energy Market Analyst"

from .battery_optimizer import BatteryOptimizer
from .data_generator import ERCOTDataGenerator
from .analytics import RevenueAnalytics
from .ercot_fetcher import ERCOTFetcher

__all__ = [
    "BatteryOptimizer",
    "ERCOTDataGenerator",
    "RevenueAnalytics",
    "ERCOTFetcher",
]
