"""Multi-Timeframe Confirmation - Weekly VWAP and 20-day MA analysis."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class MultiTimeframeData:
    """Multi-timeframe analysis data."""
    symbol: str
    current_price: float
    
    # Daily
    daily_vwap: float | None
    above_daily_vwap: bool
    
    # Weekly
    weekly_vwap: float | None
    above_weekly_vwap: bool
    
    # Moving Averages
    ma_20: float | None
    above_ma_20: bool
    ma_50: float | None
    above_ma_50: bool
    
    # Confirmation
    all_timeframes_aligned: bool
    alignment_score: int  # 0-4 (number of conditions met)
    confirmation_message: str


def calculate_vwap(df: pd.DataFrame) -> float | None:
    """Calculate VWAP from OHLCV data."""
    if df is None or df.empty:
        return None
    
    try:
        # Typical price = (High + Low + Close) / 3
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        
        # VWAP = cumsum(TP * Volume) / cumsum(Volume)
        cumulative_tp_vol = (typical_price * df['Volume']).sum()
        cumulative_vol = df['Volume'].sum()
        
        if cumulative_vol == 0:
            return None
            
        return cumulative_tp_vol / cumulative_vol
    except Exception as e:
        logger.error(f"Error calculating VWAP: {e}")
        return None


def get_multi_timeframe_data(symbol: str) -> MultiTimeframeData:
    """Get multi-timeframe confirmation data for a symbol."""
    try:
        ticker = yf.Ticker(symbol)
        
        # Get daily data (1 month for daily VWAP and MAs)
        daily_df = ticker.history(period="3mo", interval="1d")
        
        if daily_df is None or daily_df.empty:
            return _empty_result(symbol)
        
        current_price = daily_df['Close'].iloc[-1]
        
        # Daily VWAP (last 5 trading days)
        recent_daily = daily_df.tail(5)
        daily_vwap = calculate_vwap(recent_daily)
        above_daily_vwap = current_price > daily_vwap if daily_vwap else False
        
        # Weekly VWAP (resample to weekly)
        weekly_df = daily_df.resample('W').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        
        if len(weekly_df) >= 2:
            recent_weekly = weekly_df.tail(2)
            weekly_vwap = calculate_vwap(recent_weekly)
        else:
            weekly_vwap = None
        above_weekly_vwap = current_price > weekly_vwap if weekly_vwap else False
        
        # 20-day MA
        if len(daily_df) >= 20:
            ma_20 = daily_df['Close'].rolling(window=20).mean().iloc[-1]
        else:
            ma_20 = None
        above_ma_20 = current_price > ma_20 if ma_20 else False
        
        # 50-day MA
        if len(daily_df) >= 50:
            ma_50 = daily_df['Close'].rolling(window=50).mean().iloc[-1]
        else:
            ma_50 = None
        above_ma_50 = current_price > ma_50 if ma_50 else False
        
        # Calculate alignment score
        alignment_score = sum([
            above_daily_vwap,
            above_weekly_vwap,
            above_ma_20,
            above_ma_50,
        ])
        
        all_aligned = alignment_score == 4
        
        # Generate confirmation message
        if all_aligned:
            confirmation_message = "All timeframes aligned BULLISH - strong confirmation"
        elif alignment_score >= 3:
            confirmation_message = "Most timeframes bullish - moderate confirmation"
        elif alignment_score >= 2:
            confirmation_message = "Mixed timeframes - weak confirmation"
        else:
            confirmation_message = "Timeframes bearish - no confirmation"
        
        return MultiTimeframeData(
            symbol=symbol,
            current_price=current_price,
            daily_vwap=daily_vwap,
            above_daily_vwap=above_daily_vwap,
            weekly_vwap=weekly_vwap,
            above_weekly_vwap=above_weekly_vwap,
            ma_20=ma_20,
            above_ma_20=above_ma_20,
            ma_50=ma_50,
            above_ma_50=above_ma_50,
            all_timeframes_aligned=all_aligned,
            alignment_score=alignment_score,
            confirmation_message=confirmation_message,
        )
        
    except Exception as e:
        logger.error(f"Error getting multi-timeframe data for {symbol}: {e}")
        return _empty_result(symbol)


def _empty_result(symbol: str) -> MultiTimeframeData:
    """Return empty result when data unavailable."""
    return MultiTimeframeData(
        symbol=symbol,
        current_price=0,
        daily_vwap=None,
        above_daily_vwap=False,
        weekly_vwap=None,
        above_weekly_vwap=False,
        ma_20=None,
        above_ma_20=False,
        ma_50=None,
        above_ma_50=False,
        all_timeframes_aligned=False,
        alignment_score=0,
        confirmation_message="Data unavailable",
    )


def check_multi_timeframe_confirmation(symbol: str) -> tuple[bool, int, str]:
    """Quick check for multi-timeframe confirmation.
    
    Returns:
        (is_confirmed, alignment_score, message)
    """
    data = get_multi_timeframe_data(symbol)
    return data.all_timeframes_aligned, data.alignment_score, data.confirmation_message


def format_multi_timeframe_discord(data: MultiTimeframeData) -> str:
    """Format multi-timeframe data for Discord."""
    lines = [
        f"📊 **Multi-Timeframe Analysis: {data.symbol}**",
        f"Current Price: ${data.current_price:.2f}",
        "",
    ]
    
    # Daily VWAP
    if data.daily_vwap:
        emoji = "✅" if data.above_daily_vwap else "❌"
        lines.append(f"{emoji} Daily VWAP: ${data.daily_vwap:.2f}")
    
    # Weekly VWAP
    if data.weekly_vwap:
        emoji = "✅" if data.above_weekly_vwap else "❌"
        lines.append(f"{emoji} Weekly VWAP: ${data.weekly_vwap:.2f}")
    
    # 20 MA
    if data.ma_20:
        emoji = "✅" if data.above_ma_20 else "❌"
        lines.append(f"{emoji} 20-day MA: ${data.ma_20:.2f}")
    
    # 50 MA
    if data.ma_50:
        emoji = "✅" if data.above_ma_50 else "❌"
        lines.append(f"{emoji} 50-day MA: ${data.ma_50:.2f}")
    
    lines.append("")
    lines.append(f"**Alignment Score:** {data.alignment_score}/4")
    lines.append(f"**Status:** {data.confirmation_message}")
    
    return "\n".join(lines)
