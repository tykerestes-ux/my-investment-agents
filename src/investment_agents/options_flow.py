"""Options Flow Analysis - Put/Call ratio and unusual activity."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class OptionsFlowData:
    """Options flow analysis data."""
    symbol: str
    put_call_ratio: float | None
    total_call_volume: int
    total_put_volume: int
    total_call_oi: int  # Open interest
    total_put_oi: int
    near_term_bias: str  # "BULLISH", "BEARISH", "NEUTRAL"
    unusual_activity: list[str]
    signal: str
    signal_strength: int  # 1-10
    summary: str


def analyze_options_flow(symbol: str) -> OptionsFlowData:
    """Analyze options flow for a symbol."""
    symbol = symbol.upper()
    
    try:
        ticker = yf.Ticker(symbol)
        
        # Get options expiration dates
        expirations = ticker.options
        if not expirations:
            return _empty_result(symbol, "No options data available")
        
        total_call_volume = 0
        total_put_volume = 0
        total_call_oi = 0
        total_put_oi = 0
        unusual_activity = []
        
        # Analyze near-term expirations (next 2)
        for exp_date in expirations[:2]:
            try:
                chain = ticker.option_chain(exp_date)
                calls = chain.calls
                puts = chain.puts
                
                # Sum volumes and OI
                call_vol = calls['volume'].sum() if 'volume' in calls else 0
                put_vol = puts['volume'].sum() if 'volume' in puts else 0
                call_oi = calls['openInterest'].sum() if 'openInterest' in calls else 0
                put_oi = puts['openInterest'].sum() if 'openInterest' in puts else 0
                
                total_call_volume += int(call_vol or 0)
                total_put_volume += int(put_vol or 0)
                total_call_oi += int(call_oi or 0)
                total_put_oi += int(put_oi or 0)
                
                # Check for unusual activity (volume > 2x open interest)
                for _, row in calls.iterrows():
                    vol = row.get('volume', 0) or 0
                    oi = row.get('openInterest', 0) or 0
                    strike = row.get('strike', 0)
                    if vol > 1000 and oi > 0 and vol > oi * 2:
                        unusual_activity.append(f"High call volume at ${strike:.0f} strike ({int(vol):,} vol vs {int(oi):,} OI)")
                
                for _, row in puts.iterrows():
                    vol = row.get('volume', 0) or 0
                    oi = row.get('openInterest', 0) or 0
                    strike = row.get('strike', 0)
                    if vol > 1000 and oi > 0 and vol > oi * 2:
                        unusual_activity.append(f"High put volume at ${strike:.0f} strike ({int(vol):,} vol vs {int(oi):,} OI)")
                        
            except Exception as e:
                logger.debug(f"Error processing {exp_date}: {e}")
                continue
        
        # Calculate put/call ratio
        put_call_ratio = None
        if total_call_volume > 0:
            put_call_ratio = total_put_volume / total_call_volume
        
        # Determine bias
        if put_call_ratio is not None:
            if put_call_ratio < 0.5:
                bias = "BULLISH"
                signal = "BULLISH"
                signal_strength = 8
                summary = f"Strong call buying - P/C ratio {put_call_ratio:.2f}"
            elif put_call_ratio < 0.7:
                bias = "BULLISH"
                signal = "BULLISH"
                signal_strength = 6
                summary = f"Call-heavy flow - P/C ratio {put_call_ratio:.2f}"
            elif put_call_ratio > 1.5:
                bias = "BEARISH"
                signal = "BEARISH"
                signal_strength = 3
                summary = f"Heavy put buying - P/C ratio {put_call_ratio:.2f}"
            elif put_call_ratio > 1.0:
                bias = "BEARISH"
                signal = "BEARISH"
                signal_strength = 4
                summary = f"Put-heavy flow - P/C ratio {put_call_ratio:.2f}"
            else:
                bias = "NEUTRAL"
                signal = "NEUTRAL"
                signal_strength = 5
                summary = f"Balanced options flow - P/C ratio {put_call_ratio:.2f}"
        else:
            bias = "NEUTRAL"
            signal = "NEUTRAL"
            signal_strength = 5
            summary = "Limited options volume"
        
        # Unusual activity can override
        if unusual_activity:
            call_unusual = len([a for a in unusual_activity if "call" in a.lower()])
            put_unusual = len([a for a in unusual_activity if "put" in a.lower()])
            
            if call_unusual > put_unusual:
                signal = "UNUSUAL_BULLISH"
                signal_strength = min(10, signal_strength + 2)
                summary = f"Unusual call activity detected - {call_unusual} strikes with heavy volume"
            elif put_unusual > call_unusual:
                signal = "UNUSUAL_BEARISH"
                signal_strength = max(1, signal_strength - 2)
                summary = f"Unusual put activity detected - {put_unusual} strikes with heavy volume"
        
        return OptionsFlowData(
            symbol=symbol,
            put_call_ratio=put_call_ratio,
            total_call_volume=total_call_volume,
            total_put_volume=total_put_volume,
            total_call_oi=total_call_oi,
            total_put_oi=total_put_oi,
            near_term_bias=bias,
            unusual_activity=unusual_activity[:5],  # Keep top 5
            signal=signal,
            signal_strength=signal_strength,
            summary=summary,
        )
        
    except Exception as e:
        logger.error(f"Error analyzing options for {symbol}: {e}")
        return _empty_result(symbol, f"Error: {str(e)[:50]}")


def _empty_result(symbol: str, message: str) -> OptionsFlowData:
    """Return empty result."""
    return OptionsFlowData(
        symbol=symbol,
        put_call_ratio=None,
        total_call_volume=0,
        total_put_volume=0,
        total_call_oi=0,
        total_put_oi=0,
        near_term_bias="NEUTRAL",
        unusual_activity=[],
        signal="UNKNOWN",
        signal_strength=5,
        summary=message,
    )


def format_options_discord(data: OptionsFlowData) -> str:
    """Format options flow for Discord."""
    if "BULLISH" in data.signal:
        emoji = "🟢"
    elif "BEARISH" in data.signal:
        emoji = "🔴"
    else:
        emoji = "🟡"
    
    lines = [
        f"{emoji} **Options Flow: {data.symbol}** - {data.signal}",
        f"Signal Strength: {data.signal_strength}/10",
        "",
    ]
    
    if data.put_call_ratio:
        lines.append(f"**Put/Call Ratio:** {data.put_call_ratio:.2f}")
    
    lines.append(f"**Call Volume:** {data.total_call_volume:,}")
    lines.append(f"**Put Volume:** {data.total_put_volume:,}")
    lines.append(f"**Call OI:** {data.total_call_oi:,}")
    lines.append(f"**Put OI:** {data.total_put_oi:,}")
    
    if data.unusual_activity:
        lines.append("\n**⚠️ Unusual Activity:**")
        for activity in data.unusual_activity[:3]:
            lines.append(f"• {activity}")
    
    lines.append("")
    lines.append(f"**Summary:** {data.summary}")
    
    return "\n".join(lines)
