"""Technical Indicators - RSI, MACD, Bollinger Bands, etc."""

import logging
from dataclasses import dataclass

import yfinance as yf
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Technical analysis indicators."""
    symbol: str
    current_price: float
    
    # RSI
    rsi_14: float | None
    rsi_signal: str  # "OVERSOLD", "OVERBOUGHT", "NEUTRAL"
    
    # MACD
    macd_value: float | None
    macd_signal: float | None
    macd_histogram: float | None
    macd_trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    
    # Bollinger Bands
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    bb_position: str  # "ABOVE_UPPER", "NEAR_UPPER", "MIDDLE", "NEAR_LOWER", "BELOW_LOWER"
    
    # Moving Averages
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    ema_9: float | None
    ema_21: float | None
    ma_trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    
    # Overall
    overall_signal: str  # "STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"
    signal_strength: int  # 1-10
    summary: str


def calculate_rsi(prices: pd.Series, period: int = 14) -> float | None:
    """Calculate Relative Strength Index."""
    try:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]
    except Exception:
        return None


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """Calculate MACD, Signal line, and Histogram."""
    try:
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
    except Exception:
        return None, None, None


def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple:
    """Calculate Bollinger Bands."""
    try:
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return upper.iloc[-1], middle.iloc[-1], lower.iloc[-1]
    except Exception:
        return None, None, None


def get_technical_indicators(symbol: str) -> TechnicalIndicators:
    """Calculate all technical indicators for a symbol."""
    symbol = symbol.upper()
    
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="6mo", interval="1d")
        
        if df is None or len(df) < 50:
            return _empty_result(symbol, "Insufficient data")
        
        prices = df['Close']
        current_price = prices.iloc[-1]
        
        # RSI
        rsi = calculate_rsi(prices)
        if rsi is not None:
            if rsi < 30:
                rsi_signal = "OVERSOLD"
            elif rsi > 70:
                rsi_signal = "OVERBOUGHT"
            else:
                rsi_signal = "NEUTRAL"
        else:
            rsi_signal = "UNKNOWN"
        
        # MACD
        macd_val, macd_sig, macd_hist = calculate_macd(prices)
        if macd_hist is not None:
            if macd_hist > 0 and macd_val > macd_sig:
                macd_trend = "BULLISH"
            elif macd_hist < 0 and macd_val < macd_sig:
                macd_trend = "BEARISH"
            else:
                macd_trend = "NEUTRAL"
        else:
            macd_trend = "UNKNOWN"
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(prices)
        if all([bb_upper, bb_middle, bb_lower]):
            if current_price > bb_upper:
                bb_position = "ABOVE_UPPER"
            elif current_price > bb_middle + (bb_upper - bb_middle) * 0.7:
                bb_position = "NEAR_UPPER"
            elif current_price < bb_lower:
                bb_position = "BELOW_LOWER"
            elif current_price < bb_middle - (bb_middle - bb_lower) * 0.7:
                bb_position = "NEAR_LOWER"
            else:
                bb_position = "MIDDLE"
        else:
            bb_position = "UNKNOWN"
        
        # Moving Averages
        sma_20 = prices.rolling(20).mean().iloc[-1] if len(prices) >= 20 else None
        sma_50 = prices.rolling(50).mean().iloc[-1] if len(prices) >= 50 else None
        sma_200 = prices.rolling(200).mean().iloc[-1] if len(prices) >= 200 else None
        ema_9 = prices.ewm(span=9, adjust=False).mean().iloc[-1]
        ema_21 = prices.ewm(span=21, adjust=False).mean().iloc[-1]
        
        # MA trend
        ma_bullish = 0
        ma_bearish = 0
        
        if sma_20 and current_price > sma_20:
            ma_bullish += 1
        elif sma_20:
            ma_bearish += 1
            
        if sma_50 and current_price > sma_50:
            ma_bullish += 1
        elif sma_50:
            ma_bearish += 1
            
        if sma_200 and current_price > sma_200:
            ma_bullish += 1
        elif sma_200:
            ma_bearish += 1
        
        if ma_bullish > ma_bearish:
            ma_trend = "BULLISH"
        elif ma_bearish > ma_bullish:
            ma_trend = "BEARISH"
        else:
            ma_trend = "NEUTRAL"
        
        # Overall signal
        bullish_signals = 0
        bearish_signals = 0
        
        # RSI
        if rsi_signal == "OVERSOLD":
            bullish_signals += 2  # Oversold = potential bounce
        elif rsi_signal == "OVERBOUGHT":
            bearish_signals += 1
        
        # MACD
        if macd_trend == "BULLISH":
            bullish_signals += 2
        elif macd_trend == "BEARISH":
            bearish_signals += 2
        
        # Bollinger
        if bb_position in ["BELOW_LOWER", "NEAR_LOWER"]:
            bullish_signals += 1  # Potential bounce
        elif bb_position in ["ABOVE_UPPER"]:
            bearish_signals += 1  # Overextended
        
        # MA trend
        if ma_trend == "BULLISH":
            bullish_signals += 2
        elif ma_trend == "BEARISH":
            bearish_signals += 2
        
        # Determine overall
        net_signal = bullish_signals - bearish_signals
        
        if net_signal >= 4:
            overall_signal = "STRONG_BUY"
            signal_strength = 9
        elif net_signal >= 2:
            overall_signal = "BUY"
            signal_strength = 7
        elif net_signal <= -4:
            overall_signal = "STRONG_SELL"
            signal_strength = 2
        elif net_signal <= -2:
            overall_signal = "SELL"
            signal_strength = 4
        else:
            overall_signal = "NEUTRAL"
            signal_strength = 5
        
        # Generate summary
        summary_parts = []
        if rsi:
            summary_parts.append(f"RSI {rsi:.0f} ({rsi_signal})")
        summary_parts.append(f"MACD {macd_trend}")
        summary_parts.append(f"MAs {ma_trend}")
        summary = " | ".join(summary_parts)
        
        return TechnicalIndicators(
            symbol=symbol,
            current_price=current_price,
            rsi_14=rsi,
            rsi_signal=rsi_signal,
            macd_value=macd_val,
            macd_signal=macd_sig,
            macd_histogram=macd_hist,
            macd_trend=macd_trend,
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            bb_position=bb_position,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            ema_9=ema_9,
            ema_21=ema_21,
            ma_trend=ma_trend,
            overall_signal=overall_signal,
            signal_strength=signal_strength,
            summary=summary,
        )
        
    except Exception as e:
        logger.error(f"Error calculating technicals for {symbol}: {e}")
        return _empty_result(symbol, f"Error: {str(e)[:50]}")


def _empty_result(symbol: str, message: str) -> TechnicalIndicators:
    """Return empty result."""
    return TechnicalIndicators(
        symbol=symbol,
        current_price=0,
        rsi_14=None,
        rsi_signal="UNKNOWN",
        macd_value=None,
        macd_signal=None,
        macd_histogram=None,
        macd_trend="UNKNOWN",
        bb_upper=None,
        bb_middle=None,
        bb_lower=None,
        bb_position="UNKNOWN",
        sma_20=None,
        sma_50=None,
        sma_200=None,
        ema_9=None,
        ema_21=None,
        ma_trend="UNKNOWN",
        overall_signal="UNKNOWN",
        signal_strength=5,
        summary=message,
    )


def format_technicals_discord(data: TechnicalIndicators) -> str:
    """Format technical indicators for Discord."""
    signal_emojis = {
        "STRONG_BUY": "🟢🟢",
        "BUY": "🟢",
        "NEUTRAL": "🟡",
        "SELL": "🔴",
        "STRONG_SELL": "🔴🔴",
    }
    emoji = signal_emojis.get(data.overall_signal, "❓")
    
    lines = [
        f"{emoji} **Technical Analysis: {data.symbol}** - {data.overall_signal}",
        f"Signal Strength: {data.signal_strength}/10",
        f"Price: ${data.current_price:.2f}",
        "",
        "**Indicators:**",
    ]
    
    # RSI
    if data.rsi_14:
        rsi_emoji = "🟢" if data.rsi_signal == "OVERSOLD" else "🔴" if data.rsi_signal == "OVERBOUGHT" else "🟡"
        lines.append(f"{rsi_emoji} RSI(14): {data.rsi_14:.1f} - {data.rsi_signal}")
    
    # MACD
    macd_emoji = "🟢" if data.macd_trend == "BULLISH" else "🔴" if data.macd_trend == "BEARISH" else "🟡"
    lines.append(f"{macd_emoji} MACD: {data.macd_trend}")
    
    # Bollinger
    lines.append(f"📊 Bollinger: {data.bb_position}")
    
    # Moving Averages
    ma_emoji = "🟢" if data.ma_trend == "BULLISH" else "🔴" if data.ma_trend == "BEARISH" else "🟡"
    lines.append(f"{ma_emoji} Moving Averages: {data.ma_trend}")
    
    if data.sma_20:
        above_below = "above" if data.current_price > data.sma_20 else "below"
        lines.append(f"   • SMA20: ${data.sma_20:.2f} ({above_below})")
    if data.sma_50:
        above_below = "above" if data.current_price > data.sma_50 else "below"
        lines.append(f"   • SMA50: ${data.sma_50:.2f} ({above_below})")
    if data.sma_200:
        above_below = "above" if data.current_price > data.sma_200 else "below"
        lines.append(f"   • SMA200: ${data.sma_200:.2f} ({above_below})")
    
    lines.append("")
    lines.append(f"**Summary:** {data.summary}")
    
    return "\n".join(lines)
