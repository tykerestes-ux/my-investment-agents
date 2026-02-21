"""Analyst Ratings - Track upgrades, downgrades, and price targets."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class AnalystRating:
    """A single analyst rating change."""
    firm: str
    action: str  # "Upgrade", "Downgrade", "Initiated", "Reiterated"
    from_grade: str | None
    to_grade: str | None
    date: str


@dataclass
class AnalystSummary:
    """Summary of analyst ratings."""
    symbol: str
    current_price: float
    target_mean: float | None
    target_low: float | None
    target_high: float | None
    upside_percent: float | None
    recommendation: str | None  # "Buy", "Hold", "Sell"
    num_analysts: int
    recent_upgrades: int
    recent_downgrades: int
    recent_ratings: list[AnalystRating]
    signal: str  # "BULLISH", "BEARISH", "NEUTRAL"
    signal_strength: int  # 1-10
    summary: str


def get_analyst_ratings(symbol: str) -> AnalystSummary:
    """Get analyst ratings and price targets."""
    symbol = symbol.upper()
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Get current price
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        
        # Get price targets
        target_mean = info.get("targetMeanPrice")
        target_low = info.get("targetLowPrice")
        target_high = info.get("targetHighPrice")
        
        # Calculate upside
        upside = None
        if target_mean and current_price:
            upside = ((target_mean - current_price) / current_price) * 100
        
        # Get recommendation
        recommendation = info.get("recommendationKey", "").replace("_", " ").title()
        num_analysts = info.get("numberOfAnalystOpinions", 0)
        
        # Get recent rating changes
        recent_ratings = []
        upgrades = 0
        downgrades = 0
        
        try:
            # yfinance has recommendations history
            recs = ticker.recommendations
            if recs is not None and hasattr(recs, 'empty') and not recs.empty:
                cutoff = datetime.now() - timedelta(days=90)
                
                for idx, row in recs.iterrows():
                    try:
                        date = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
                        if date < cutoff:
                            continue
                        
                        firm = row.get("Firm", "Unknown")
                        to_grade = row.get("To Grade", "")
                        from_grade = row.get("From Grade", "")
                        action = row.get("Action", "")
                        
                        # Determine if upgrade or downgrade
                        upgrade_terms = ["upgrade", "buy", "outperform", "overweight"]
                        downgrade_terms = ["downgrade", "sell", "underperform", "underweight"]
                        
                        if any(term in str(action).lower() or term in str(to_grade).lower() for term in upgrade_terms):
                            upgrades += 1
                        elif any(term in str(action).lower() or term in str(to_grade).lower() for term in downgrade_terms):
                            downgrades += 1
                        
                        recent_ratings.append(AnalystRating(
                            firm=str(firm)[:30],
                            action=str(action),
                            from_grade=from_grade if from_grade else None,
                            to_grade=to_grade if to_grade else None,
                            date=str(date)[:10],
                        ))
                        
                    except Exception:
                        continue
                        
        except Exception as e:
            logger.debug(f"Error getting recommendations history: {e}")
        
        # Determine signal
        if upside and upside > 30:
            signal = "BULLISH"
            signal_strength = 9
            summary = f"Analysts see {upside:.0f}% upside to ${target_mean:.2f}"
        elif upside and upside > 15:
            signal = "BULLISH"
            signal_strength = 7
            summary = f"Analysts see {upside:.0f}% upside - consensus {recommendation}"
        elif upside and upside < -10:
            signal = "BEARISH"
            signal_strength = 3
            summary = f"Trading above analyst targets - {upside:.0f}% downside"
        elif upside and upside < 0:
            signal = "BEARISH"
            signal_strength = 4
            summary = f"Near/above price targets - limited upside"
        else:
            signal = "NEUTRAL"
            signal_strength = 5
            summary = f"In line with analyst expectations"
        
        # Adjust for recent upgrades/downgrades
        if upgrades > downgrades + 2:
            signal_strength = min(10, signal_strength + 1)
            summary += f" | Recent: {upgrades} upgrades, {downgrades} downgrades"
        elif downgrades > upgrades + 2:
            signal_strength = max(1, signal_strength - 1)
            summary += f" | Recent: {downgrades} downgrades, {upgrades} upgrades"
        
        return AnalystSummary(
            symbol=symbol,
            current_price=current_price,
            target_mean=target_mean,
            target_low=target_low,
            target_high=target_high,
            upside_percent=upside,
            recommendation=recommendation if recommendation else None,
            num_analysts=num_analysts,
            recent_upgrades=upgrades,
            recent_downgrades=downgrades,
            recent_ratings=recent_ratings[:10],
            signal=signal,
            signal_strength=signal_strength,
            summary=summary,
        )
        
    except Exception as e:
        logger.error(f"Error getting analyst data for {symbol}: {e}")
        return AnalystSummary(
            symbol=symbol,
            current_price=0,
            target_mean=None,
            target_low=None,
            target_high=None,
            upside_percent=None,
            recommendation=None,
            num_analysts=0,
            recent_upgrades=0,
            recent_downgrades=0,
            recent_ratings=[],
            signal="UNKNOWN",
            signal_strength=5,
            summary="Unable to retrieve analyst data",
        )


def format_analyst_discord(data: AnalystSummary) -> str:
    """Format analyst data for Discord."""
    if data.signal == "BULLISH":
        emoji = "🟢"
    elif data.signal == "BEARISH":
        emoji = "🔴"
    else:
        emoji = "🟡"
    
    lines = [
        f"{emoji} **Analyst Ratings: {data.symbol}** - {data.signal}",
        f"Signal Strength: {data.signal_strength}/10",
        "",
    ]
    
    if data.current_price:
        lines.append(f"**Current Price:** ${data.current_price:.2f}")
    
    if data.target_mean:
        lines.append(f"**Price Target (Avg):** ${data.target_mean:.2f}")
    
    if data.target_low and data.target_high:
        lines.append(f"**Target Range:** ${data.target_low:.2f} - ${data.target_high:.2f}")
    
    if data.upside_percent:
        direction = "↑" if data.upside_percent > 0 else "↓"
        lines.append(f"**Upside/Downside:** {direction} {abs(data.upside_percent):.1f}%")
    
    if data.recommendation:
        lines.append(f"**Consensus:** {data.recommendation}")
    
    if data.num_analysts:
        lines.append(f"**# of Analysts:** {data.num_analysts}")
    
    if data.recent_upgrades or data.recent_downgrades:
        lines.append(f"\n**Recent Activity (90d):**")
        lines.append(f"• Upgrades: {data.recent_upgrades}")
        lines.append(f"• Downgrades: {data.recent_downgrades}")
    
    if data.recent_ratings:
        lines.append("\n**Latest Ratings:**")
        for r in data.recent_ratings[:3]:
            grade = f"{r.from_grade} → {r.to_grade}" if r.from_grade and r.to_grade else r.to_grade or r.action
            lines.append(f"• {r.firm}: {grade} ({r.date})")
    
    lines.append("")
    lines.append(f"**Summary:** {data.summary}")
    
    return "\n".join(lines)
