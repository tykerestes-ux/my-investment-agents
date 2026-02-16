"""Sector Correlation Filter - Detect sector crowding and correlation risks."""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Sector mappings for common tickers
SECTOR_MAP: dict[str, str] = {
    # Semiconductors
    "LRCX": "semiconductors",
    "KLAC": "semiconductors",
    "ASML": "semiconductors",
    "NVDA": "semiconductors",
    "AMD": "semiconductors",
    "INTC": "semiconductors",
    "AVGO": "semiconductors",
    "QCOM": "semiconductors",
    "MU": "semiconductors",
    "MRVL": "semiconductors",
    "AMAT": "semiconductors",
    "TSM": "semiconductors",
    "TXN": "semiconductors",
    "ONDS": "semiconductors",
    
    # Big Tech
    "AAPL": "big_tech",
    "MSFT": "big_tech",
    "GOOGL": "big_tech",
    "GOOG": "big_tech",
    "META": "big_tech",
    "AMZN": "big_tech",
    
    # Financials
    "JPM": "financials",
    "BAC": "financials",
    "WFC": "financials",
    "GS": "financials",
    "MS": "financials",
    "C": "financials",
    "BLK": "financials",
    "SCHW": "financials",
    
    # Energy
    "XOM": "energy",
    "CVX": "energy",
    "COP": "energy",
    "SLB": "energy",
    "EOG": "energy",
    "PXD": "energy",
    "MPC": "energy",
    "VLO": "energy",
    
    # Healthcare
    "JNJ": "healthcare",
    "UNH": "healthcare",
    "PFE": "healthcare",
    "ABBV": "healthcare",
    "MRK": "healthcare",
    "LLY": "healthcare",
    "TMO": "healthcare",
    
    # Industrials
    "CAT": "industrials",
    "DE": "industrials",
    "BA": "industrials",
    "HON": "industrials",
    "UPS": "industrials",
    "RTX": "industrials",
    "LMT": "industrials",
    "GE": "industrials",
    
    # Consumer
    "WMT": "consumer",
    "COST": "consumer",
    "HD": "consumer",
    "NKE": "consumer",
    "SBUX": "consumer",
    "MCD": "consumer",
    "TGT": "consumer",
    
    # EV/Auto
    "TSLA": "ev_auto",
    "F": "ev_auto",
    "GM": "ev_auto",
    "RIVN": "ev_auto",
    "LCID": "ev_auto",
}

# Crowding threshold - if this many tickers in same sector show BUY, flag crowding
CROWDING_THRESHOLD = 3


@dataclass
class SectorAnalysis:
    """Sector correlation analysis result."""
    symbol: str
    sector: str | None
    sector_signals: dict[str, str]  # {symbol: signal}
    is_crowded: bool
    crowding_warning: str | None
    correlation_score: float  # 0-1, higher = more correlated/risky


def get_sector(symbol: str) -> str | None:
    """Get sector for a symbol."""
    return SECTOR_MAP.get(symbol.upper())


def analyze_sector_correlation(
    target_symbol: str,
    all_signals: dict[str, str],  # {symbol: signal} e.g., {"KLAC": "BUY", "LRCX": "STRONG_BUY"}
) -> SectorAnalysis:
    """Analyze if a sector is crowded with buy signals.
    
    Args:
        target_symbol: The symbol being evaluated
        all_signals: Dict of all current signals for watchlist
    
    Returns:
        SectorAnalysis with crowding detection
    """
    target_sector = get_sector(target_symbol)
    
    if not target_sector:
        return SectorAnalysis(
            symbol=target_symbol,
            sector=None,
            sector_signals={},
            is_crowded=False,
            crowding_warning=None,
            correlation_score=0.0,
        )
    
    # Find all symbols in same sector with their signals
    sector_signals = {}
    buy_signals = 0
    
    for symbol, signal in all_signals.items():
        if get_sector(symbol) == target_sector:
            sector_signals[symbol] = signal
            if signal in ["BUY", "STRONG_BUY", "buy", "strong_buy"]:
                buy_signals += 1
    
    # Check for crowding
    is_crowded = buy_signals >= CROWDING_THRESHOLD
    crowding_warning = None
    
    if is_crowded:
        sector_name = target_sector.replace("_", " ").title()
        crowding_warning = (
            f"SECTOR CROWDING: {buy_signals} {sector_name} tickers showing BUY signals. "
            f"May indicate sector-wide hype rather than individual strength."
        )
    
    # Calculate correlation score (0-1)
    # Higher when more tickers in same sector have same direction
    if len(sector_signals) > 1:
        same_direction = sum(1 for s in sector_signals.values() if s in ["BUY", "STRONG_BUY", "buy", "strong_buy"])
        correlation_score = same_direction / len(sector_signals)
    else:
        correlation_score = 0.0
    
    return SectorAnalysis(
        symbol=target_symbol,
        sector=target_sector,
        sector_signals=sector_signals,
        is_crowded=is_crowded,
        crowding_warning=crowding_warning,
        correlation_score=correlation_score,
    )


def get_sector_summary(watchlist: list[str]) -> dict[str, list[str]]:
    """Get summary of watchlist by sector."""
    sectors: dict[str, list[str]] = {}
    
    for symbol in watchlist:
        sector = get_sector(symbol)
        if sector:
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append(symbol)
    
    return sectors


def format_sector_discord(analysis: SectorAnalysis) -> str:
    """Format sector analysis for Discord."""
    if not analysis.sector:
        return f"📊 **{analysis.symbol}**: Sector unknown"
    
    sector_name = analysis.sector.replace("_", " ").title()
    
    if analysis.is_crowded:
        return (
            f"⚠️ **SECTOR CROWDING: {analysis.symbol}** ({sector_name})\n"
            f"• {len(analysis.sector_signals)} tickers in sector\n"
            f"• Correlation: {analysis.correlation_score:.0%}\n"
            f"• {analysis.crowding_warning}"
        )
    else:
        return (
            f"📊 **{analysis.symbol}** ({sector_name})\n"
            f"• Sector peers: {', '.join(analysis.sector_signals.keys())}\n"
            f"• Correlation: {analysis.correlation_score:.0%}"
        )
