"""Risk Dashboard - Portfolio exposure, sector concentration, and risk metrics."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

from .permanent_watchlist import get_permanent_symbols
from .sector_correlation import get_sector, SECTOR_MAP
from .earnings_calendar import get_earnings_date
from .economic_calendar import get_economic_calendar
from .short_interest import get_short_interest
from .technical_indicators import get_technical_indicators

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


@dataclass
class PositionRisk:
    """Risk metrics for a single position."""
    symbol: str
    sector: str | None
    current_price: float
    change_today_pct: float
    rsi: float | None
    short_interest_pct: float | None
    days_to_earnings: int | None
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    risk_factors: list[str]


@dataclass
class RiskDashboard:
    """Complete risk dashboard."""
    timestamp: str
    
    # Watchlist overview
    total_symbols: int
    symbols_bullish: int
    symbols_bearish: int
    symbols_neutral: int
    
    # Sector concentration
    sector_breakdown: dict[str, list[str]]
    largest_sector: str | None
    sector_concentration_warning: bool
    
    # Earnings risk
    symbols_with_earnings_soon: list[tuple[str, int]]  # (symbol, days)
    earnings_warning: bool
    
    # Technical risk
    oversold_symbols: list[tuple[str, float]]  # (symbol, RSI)
    overbought_symbols: list[tuple[str, float]]  # (symbol, RSI)
    
    # Short squeeze potential
    high_short_symbols: list[tuple[str, float]]  # (symbol, short%)
    
    # Economic events
    economic_risk_level: str
    days_to_next_event: int | None
    
    # Overall
    overall_risk_level: str  # "LOW", "MODERATE", "HIGH", "EXTREME"
    risk_score: int  # 0-100
    recommendations: list[str]
    
    # Individual positions
    position_risks: list[PositionRisk]


def get_risk_dashboard() -> RiskDashboard:
    """Generate comprehensive risk dashboard."""
    symbols = get_permanent_symbols()
    timestamp = datetime.now().isoformat()
    
    # Collect data
    position_risks: list[PositionRisk] = []
    sector_breakdown: dict[str, list[str]] = {}
    earnings_soon: list[tuple[str, int]] = []
    oversold: list[tuple[str, float]] = []
    overbought: list[tuple[str, float]] = []
    high_short: list[tuple[str, float]] = []
    
    bullish = 0
    bearish = 0
    neutral = 0
    
    for symbol in symbols:
        try:
            # Get basic data
            ticker = yf.Ticker(symbol)
            info = ticker.info
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            change_pct = info.get("regularMarketChangePercent", 0)
            
            # Sector
            sector = get_sector(symbol)
            if sector:
                if sector not in sector_breakdown:
                    sector_breakdown[sector] = []
                sector_breakdown[sector].append(symbol)
            
            # Technicals
            tech = get_technical_indicators(symbol)
            rsi = tech.rsi_14
            
            if rsi:
                if rsi < 30:
                    oversold.append((symbol, rsi))
                elif rsi > 70:
                    overbought.append((symbol, rsi))
            
            # Count sentiment
            if tech.overall_signal in ["STRONG_BUY", "BUY"]:
                bullish += 1
            elif tech.overall_signal in ["SELL", "STRONG_SELL"]:
                bearish += 1
            else:
                neutral += 1
            
            # Short interest
            short_data = get_short_interest(symbol)
            short_pct = short_data.short_percent_of_float
            if short_pct and short_pct > 15:
                high_short.append((symbol, short_pct))
            
            # Earnings
            earnings = get_earnings_date(symbol)
            days_to_earnings = earnings.days_until_earnings
            if days_to_earnings is not None and 0 <= days_to_earnings <= 7:
                earnings_soon.append((symbol, days_to_earnings))
            
            # Calculate individual risk
            risk_factors = []
            risk_level = "LOW"
            
            if days_to_earnings is not None and days_to_earnings <= 3:
                risk_factors.append(f"Earnings in {days_to_earnings} days")
                risk_level = "HIGH"
            
            if rsi and rsi > 75:
                risk_factors.append(f"Overbought (RSI {rsi:.0f})")
                risk_level = "MEDIUM" if risk_level == "LOW" else risk_level
            
            if short_pct and short_pct > 20:
                risk_factors.append(f"High short interest ({short_pct:.0f}%)")
                risk_level = "MEDIUM" if risk_level == "LOW" else risk_level
            
            if change_pct < -3:
                risk_factors.append(f"Down {change_pct:.1f}% today")
                risk_level = "MEDIUM" if risk_level == "LOW" else risk_level
            
            position_risks.append(PositionRisk(
                symbol=symbol,
                sector=sector,
                current_price=current_price,
                change_today_pct=change_pct,
                rsi=rsi,
                short_interest_pct=short_pct,
                days_to_earnings=days_to_earnings,
                risk_level=risk_level,
                risk_factors=risk_factors,
            ))
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
    
    # Sector concentration (disabled for now - enable when portfolio is more diversified)
    largest_sector = max(sector_breakdown.keys(), key=lambda k: len(sector_breakdown[k])) if sector_breakdown else None
    sector_concentration_warning = False
    # TODO: Re-enable when portfolio is diversified
    # if largest_sector and len(sector_breakdown.get(largest_sector, [])) >= len(symbols) * 0.5:
    #     sector_concentration_warning = True
    
    # Economic calendar
    econ = get_economic_calendar()
    
    # Calculate overall risk score
    risk_score = 50  # Start neutral
    recommendations = []
    
    # Adjust for earnings
    if len(earnings_soon) >= 2:
        risk_score += 15
        recommendations.append(f"⚠️ {len(earnings_soon)} symbols have earnings within 7 days")
    
    # Adjust for sector concentration (disabled for now)
    # if sector_concentration_warning:
    #     risk_score += 10
    #     recommendations.append(f"⚠️ Heavy concentration in {largest_sector} sector")
    
    # Adjust for overbought
    if len(overbought) >= len(symbols) * 0.3:
        risk_score += 10
        recommendations.append("⚠️ Multiple overbought signals - consider taking profits")
    
    # Adjust for economic events
    if econ.high_impact_soon:
        risk_score += 15
        recommendations.append("⚠️ High-impact economic event imminent")
    
    # Adjust for bearish technicals
    if bearish > bullish:
        risk_score += 10
        recommendations.append("📉 More bearish than bullish signals")
    
    # Bonus for oversold (opportunities)
    if oversold:
        recommendations.append(f"📉 {len(oversold)} oversold symbols - potential bounce opportunities")
    
    # Determine overall level
    if risk_score >= 80:
        overall_risk = "EXTREME"
    elif risk_score >= 65:
        overall_risk = "HIGH"
    elif risk_score >= 45:
        overall_risk = "MODERATE"
    else:
        overall_risk = "LOW"
    
    if not recommendations:
        recommendations.append("✅ No major risk factors detected")
    
    return RiskDashboard(
        timestamp=timestamp,
        total_symbols=len(symbols),
        symbols_bullish=bullish,
        symbols_bearish=bearish,
        symbols_neutral=neutral,
        sector_breakdown=sector_breakdown,
        largest_sector=largest_sector,
        sector_concentration_warning=sector_concentration_warning,
        symbols_with_earnings_soon=earnings_soon,
        earnings_warning=len(earnings_soon) > 0,
        oversold_symbols=oversold,
        overbought_symbols=overbought,
        high_short_symbols=high_short,
        economic_risk_level=econ.market_risk_level,
        days_to_next_event=econ.days_until_fomc or econ.days_until_cpi or econ.days_until_jobs,
        overall_risk_level=overall_risk,
        risk_score=min(100, risk_score),
        recommendations=recommendations,
        position_risks=position_risks,
    )


def format_dashboard_discord(dash: RiskDashboard) -> str:
    """Format risk dashboard for Discord."""
    # Risk level emoji
    level_emoji = {
        "LOW": "🟢",
        "MODERATE": "🟡",
        "HIGH": "🟠",
        "EXTREME": "🔴",
    }
    emoji = level_emoji.get(dash.overall_risk_level, "⚪")
    
    lines = [
        f"{emoji} **RISK DASHBOARD** - {dash.overall_risk_level}",
        f"Risk Score: {dash.risk_score}/100",
        f"*{datetime.fromisoformat(dash.timestamp).strftime('%B %d, %Y %I:%M %p')}*",
        "",
        "**📊 Watchlist Overview:**",
        f"• Total: {dash.total_symbols} symbols",
        f"• Bullish: {dash.symbols_bullish} | Bearish: {dash.symbols_bearish} | Neutral: {dash.symbols_neutral}",
        "",
    ]
    
    # Sector breakdown
    if dash.sector_breakdown:
        lines.append("**🏭 Sector Breakdown:**")
        for sector, symbols in sorted(dash.sector_breakdown.items(), key=lambda x: -len(x[1])):
            sector_name = sector.replace("_", " ").title()
            warning = " ⚠️" if sector == dash.largest_sector and dash.sector_concentration_warning else ""
            lines.append(f"• {sector_name}: {', '.join(symbols)}{warning}")
        lines.append("")
    
    # Earnings warning
    if dash.earnings_warning:
        lines.append("**📅 Earnings Within 7 Days:**")
        for symbol, days in sorted(dash.symbols_with_earnings_soon, key=lambda x: x[1]):
            lines.append(f"• {symbol}: {days} days")
        lines.append("")
    
    # Overbought/Oversold
    if dash.overbought_symbols:
        lines.append("**📈 Overbought (RSI > 70):**")
        for symbol, rsi in dash.overbought_symbols:
            lines.append(f"• {symbol}: RSI {rsi:.0f}")
        lines.append("")
    
    if dash.oversold_symbols:
        lines.append("**📉 Oversold (RSI < 30):**")
        for symbol, rsi in dash.oversold_symbols:
            lines.append(f"• {symbol}: RSI {rsi:.0f}")
        lines.append("")
    
    # High short interest
    if dash.high_short_symbols:
        lines.append("**🩳 High Short Interest (>15%):**")
        for symbol, pct in sorted(dash.high_short_symbols, key=lambda x: -x[1]):
            lines.append(f"• {symbol}: {pct:.1f}%")
        lines.append("")
    
    # Economic calendar
    lines.append(f"**📅 Economic Risk:** {dash.economic_risk_level}")
    if dash.days_to_next_event:
        lines.append(f"Next major event in {dash.days_to_next_event} days")
    lines.append("")
    
    # Recommendations
    lines.append("**💡 Recommendations:**")
    for rec in dash.recommendations:
        lines.append(f"• {rec}")
    
    return "\n".join(lines)


def format_quick_dashboard_discord(dash: RiskDashboard) -> str:
    """Format a shorter risk summary."""
    emoji = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "EXTREME": "🔴"}.get(dash.overall_risk_level, "⚪")
    
    lines = [
        f"{emoji} **Risk Level: {dash.overall_risk_level}** (Score: {dash.risk_score}/100)",
        "",
        f"📊 Watchlist: {dash.symbols_bullish}↑ {dash.symbols_bearish}↓ {dash.symbols_neutral}→",
    ]
    
    if dash.earnings_warning:
        lines.append(f"📅 Earnings soon: {', '.join([s for s, d in dash.symbols_with_earnings_soon])}")
    
    if dash.overbought_symbols:
        lines.append(f"📈 Overbought: {', '.join([s for s, r in dash.overbought_symbols])}")
    
    if dash.oversold_symbols:
        lines.append(f"📉 Oversold: {', '.join([s for s, r in dash.oversold_symbols])}")
    
    lines.append("")
    lines.append(dash.recommendations[0] if dash.recommendations else "✅ No major concerns")
    
    return "\n".join(lines)
