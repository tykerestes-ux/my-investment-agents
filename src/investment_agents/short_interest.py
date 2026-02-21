"""Short Interest Data - Track short selling activity."""

import logging
from dataclasses import dataclass

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class ShortInterestData:
    """Short interest data for a symbol."""
    symbol: str
    short_shares: int | None
    short_percent_of_float: float | None  # As percentage
    short_ratio: float | None  # Days to cover
    previous_short_shares: int | None
    short_change_percent: float | None
    signal: str  # "SQUEEZE_POTENTIAL", "HIGH_SHORT", "NORMAL", "LOW_SHORT"
    signal_strength: int  # 1-10
    summary: str


def get_short_interest(symbol: str) -> ShortInterestData:
    """Get short interest data for a symbol."""
    symbol = symbol.upper()
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        short_shares = info.get("sharesShort")
        short_percent = info.get("shortPercentOfFloat")
        short_ratio = info.get("shortRatio")  # Days to cover
        prev_short = info.get("sharesShortPriorMonth")
        
        # Convert to percentage if needed
        if short_percent and short_percent < 1:
            short_percent = short_percent * 100
        
        # Calculate change
        short_change = None
        if short_shares and prev_short and prev_short > 0:
            short_change = ((short_shares - prev_short) / prev_short) * 100
        
        # Determine signal
        if short_percent and short_percent > 20:
            if short_ratio and short_ratio > 5:
                signal = "SQUEEZE_POTENTIAL"
                signal_strength = 8
                summary = f"High short interest ({short_percent:.1f}%) with {short_ratio:.1f} days to cover - squeeze potential"
            else:
                signal = "HIGH_SHORT"
                signal_strength = 4
                summary = f"High short interest ({short_percent:.1f}%) - bears are betting against"
        elif short_percent and short_percent > 10:
            signal = "ELEVATED"
            signal_strength = 5
            summary = f"Elevated short interest ({short_percent:.1f}%)"
        elif short_percent and short_percent < 3:
            signal = "LOW_SHORT"
            signal_strength = 7
            summary = f"Low short interest ({short_percent:.1f}%) - minimal bearish pressure"
        else:
            signal = "NORMAL"
            signal_strength = 5
            summary = f"Normal short interest levels"
        
        return ShortInterestData(
            symbol=symbol,
            short_shares=short_shares,
            short_percent_of_float=short_percent,
            short_ratio=short_ratio,
            previous_short_shares=prev_short,
            short_change_percent=short_change,
            signal=signal,
            signal_strength=signal_strength,
            summary=summary,
        )
        
    except Exception as e:
        logger.error(f"Error getting short interest for {symbol}: {e}")
        return ShortInterestData(
            symbol=symbol,
            short_shares=None,
            short_percent_of_float=None,
            short_ratio=None,
            previous_short_shares=None,
            short_change_percent=None,
            signal="UNKNOWN",
            signal_strength=5,
            summary="Unable to retrieve short interest data",
        )


def format_short_interest_discord(data: ShortInterestData) -> str:
    """Format short interest data for Discord."""
    if data.signal == "SQUEEZE_POTENTIAL":
        emoji = "🚀"
    elif data.signal == "HIGH_SHORT":
        emoji = "🔴"
    elif data.signal == "LOW_SHORT":
        emoji = "🟢"
    else:
        emoji = "🟡"
    
    lines = [
        f"{emoji} **Short Interest: {data.symbol}** - {data.signal}",
        "",
    ]
    
    if data.short_percent_of_float:
        lines.append(f"**Short % of Float:** {data.short_percent_of_float:.1f}%")
    
    if data.short_shares:
        lines.append(f"**Shares Short:** {data.short_shares:,}")
    
    if data.short_ratio:
        lines.append(f"**Days to Cover:** {data.short_ratio:.1f}")
    
    if data.short_change_percent:
        direction = "↑" if data.short_change_percent > 0 else "↓"
        lines.append(f"**Monthly Change:** {direction} {abs(data.short_change_percent):.1f}%")
    
    lines.append("")
    lines.append(f"**Analysis:** {data.summary}")
    
    return "\n".join(lines)
