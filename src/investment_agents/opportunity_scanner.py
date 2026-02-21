"""Opportunity Scanner - Find authentic buying opportunities across the market."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import List

import yfinance as yf

from .technical_indicators import calculate_rsi, calculate_macd
from .analyst_ratings import get_analyst_ratings
from .short_interest import get_short_interest
from .insider_trading import get_insider_transactions
from .earnings_calendar import get_earnings_date

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=8)

# Expanded universe of quality stocks to scan
SCAN_UNIVERSE = {
    # Semiconductors
    "semiconductors": ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU", "MRVL", "ON", "NXPI", 
                       "KLAC", "LRCX", "ASML", "AMAT", "TSM", "MPWR", "SWKS", "QRVO", "ADI", "MCHP"],
    # Tech
    "tech": ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "CRM", "ORCL", "ADBE", "NOW", "SNOW",
             "PLTR", "NET", "DDOG", "ZS", "CRWD", "PANW", "FTNT", "OKTA", "MDB", "TEAM"],
    # Financials
    "financials": ["JPM", "BAC", "WFC", "GS", "MS", "C", "USB", "PNC", "SCHW", "BLK",
                   "AXP", "V", "MA", "PYPL", "SQ", "COIN", "HOOD", "SOFI", "NU", "AFRM"],
    # Healthcare
    "healthcare": ["UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "DHR", "BMY",
                   "AMGN", "GILD", "REGN", "VRTX", "BIIB", "MRNA", "ISRG", "MDT", "SYK", "ZTS"],
    # Energy
    "energy": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "PXD",
               "DVN", "FANG", "HAL", "BKR", "KMI", "WMB", "OKE", "TRGP", "LNG", "ET"],
    # Consumer
    "consumer": ["COST", "WMT", "TGT", "HD", "LOW", "NKE", "SBUX", "MCD", "CMG", "YUM",
                 "DPZ", "LULU", "DECK", "CROX", "TPR", "EL", "TJX", "ROST", "DG", "DLTR"],
    # Industrials  
    "industrials": ["CAT", "DE", "BA", "LMT", "RTX", "NOC", "GD", "GE", "HON", "MMM",
                    "UPS", "FDX", "CSX", "UNP", "NSC", "DAL", "UAL", "AAL", "LUV", "UBER"],
}


@dataclass
class Opportunity:
    """A potential buying opportunity."""
    symbol: str
    sector: str
    current_price: float
    
    # Score components
    technical_score: int  # 0-100
    fundamental_score: int  # 0-100
    catalyst_score: int  # 0-100
    total_score: int  # 0-100
    
    # Signals
    signals: list[str]  # Bullish signals detected
    warnings: list[str]  # Caution flags
    
    # Key metrics
    rsi: float | None
    change_1d: float
    change_5d: float
    volume_ratio: float  # vs 10-day average
    
    # Targets
    analyst_target: float | None
    upside_pct: float | None
    
    # Confidence
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    entry_type: str  # "STRONG_BUY", "BUY", "SPECULATIVE"


async def scan_for_opportunities(
    sectors: list[str] | None = None,
    min_score: int = 60,
    max_results: int = 20,
) -> list[Opportunity]:
    """Scan market for buying opportunities."""
    
    # Determine which symbols to scan
    if sectors:
        symbols = []
        for sector in sectors:
            symbols.extend(SCAN_UNIVERSE.get(sector.lower(), []))
    else:
        # Scan all sectors
        symbols = []
        for sector_symbols in SCAN_UNIVERSE.values():
            symbols.extend(sector_symbols)
    
    # Remove duplicates
    symbols = list(set(symbols))
    logger.info(f"Scanning {len(symbols)} symbols for opportunities...")
    
    opportunities: list[Opportunity] = []
    
    loop = asyncio.get_event_loop()
    
    for symbol in symbols:
        try:
            opp = await _analyze_symbol(symbol, loop)
            if opp and opp.total_score >= min_score:
                opportunities.append(opp)
            
            await asyncio.sleep(0.3)  # Rate limiting
            
        except Exception as e:
            logger.debug(f"Error analyzing {symbol}: {e}")
    
    # Sort by score descending
    opportunities.sort(key=lambda x: x.total_score, reverse=True)
    
    return opportunities[:max_results]


async def _analyze_symbol(symbol: str, loop) -> Opportunity | None:
    """Analyze a single symbol for opportunity."""
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Get price data
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not current_price:
            return None
        
        # Get historical data
        hist = ticker.history(period="1mo", interval="1d")
        if hist is None or len(hist) < 10:
            return None
        
        # Calculate metrics
        change_1d = info.get("regularMarketChangePercent", 0)
        
        # 5-day change
        if len(hist) >= 5:
            price_5d_ago = hist['Close'].iloc[-5]
            change_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100
        else:
            change_5d = 0
        
        # Volume ratio
        current_vol = info.get("regularMarketVolume", 0)
        avg_vol = info.get("averageDailyVolume10Day", 1)
        volume_ratio = current_vol / avg_vol if avg_vol > 0 else 1
        
        # RSI
        rsi = calculate_rsi(hist['Close']) if len(hist) >= 14 else None
        
        # MACD
        macd_line, signal_line, macd_hist = calculate_macd(hist['Close'])
        macd_bullish = macd_hist is not None and macd_hist > 0
        macd_crossover = (macd_line is not None and signal_line is not None and 
                         macd_line > signal_line)
        
        # Determine sector
        sector = "unknown"
        for sec, syms in SCAN_UNIVERSE.items():
            if symbol in syms:
                sector = sec
                break
        
        # === SCORING ===
        signals = []
        warnings = []
        
        # Technical Score (0-100)
        tech_score = 50
        
        # RSI signals
        if rsi:
            if rsi < 30:
                tech_score += 25
                signals.append(f"RSI oversold ({rsi:.0f})")
            elif rsi < 40:
                tech_score += 15
                signals.append(f"RSI low ({rsi:.0f})")
            elif rsi > 70:
                tech_score -= 15
                warnings.append(f"RSI overbought ({rsi:.0f})")
        
        # MACD
        if macd_bullish:
            tech_score += 10
            signals.append("MACD bullish")
        if macd_crossover:
            tech_score += 10
            signals.append("MACD crossover")
        
        # Price momentum
        if -5 < change_5d < 0:
            tech_score += 10
            signals.append("Pullback from highs")
        elif change_5d < -10:
            tech_score += 5
            signals.append("Deep pullback")
            warnings.append("Extended decline")
        
        # Volume
        if volume_ratio > 1.5 and change_1d > 0:
            tech_score += 10
            signals.append(f"Volume surge ({volume_ratio:.1f}x)")
        
        # 52-week position
        high_52w = info.get("fiftyTwoWeekHigh", current_price)
        low_52w = info.get("fiftyTwoWeekLow", current_price)
        range_52w = high_52w - low_52w if high_52w != low_52w else 1
        position_52w = (current_price - low_52w) / range_52w * 100
        
        if position_52w < 30:
            tech_score += 15
            signals.append(f"Near 52-week low ({position_52w:.0f}%)")
        elif position_52w > 90:
            tech_score -= 10
            warnings.append(f"Near 52-week high ({position_52w:.0f}%)")
        
        tech_score = max(0, min(100, tech_score))
        
        # Fundamental Score (0-100)
        fund_score = 50
        
        # Analyst ratings
        try:
            analysts = get_analyst_ratings(symbol)
            analyst_target = analysts.target_mean_price
            if analyst_target and current_price:
                upside = ((analyst_target - current_price) / current_price) * 100
                if upside > 30:
                    fund_score += 20
                    signals.append(f"Analyst upside {upside:.0f}%")
                elif upside > 15:
                    fund_score += 10
                    signals.append(f"Analyst upside {upside:.0f}%")
                elif upside < 0:
                    fund_score -= 10
                    warnings.append("Below analyst target")
            else:
                analyst_target = None
                upside = None
        except:
            analyst_target = None
            upside = None
        
        # Short interest
        try:
            short_data = get_short_interest(symbol)
            if short_data.short_percent_of_float:
                if short_data.short_percent_of_float > 20:
                    fund_score += 10
                    signals.append(f"High short interest ({short_data.short_percent_of_float:.0f}%) - squeeze potential")
                elif short_data.short_percent_of_float > 10:
                    signals.append(f"Elevated shorts ({short_data.short_percent_of_float:.0f}%)")
        except:
            pass
        
        # P/E ratio
        pe = info.get("forwardPE") or info.get("trailingPE")
        if pe:
            if pe < 15:
                fund_score += 10
                signals.append(f"Low P/E ({pe:.1f})")
            elif pe > 50:
                fund_score -= 10
                warnings.append(f"High P/E ({pe:.1f})")
        
        fund_score = max(0, min(100, fund_score))
        
        # Catalyst Score (0-100)
        catalyst_score = 50
        
        # Insider buying
        try:
            insider = await get_insider_transactions(symbol, days=30)
            if insider.signal == "BULLISH" and insider.buy_count_30d > 0:
                catalyst_score += 25
                signals.append(f"Insider buying ({insider.buy_count_30d} buys)")
        except:
            pass
        
        # Earnings proximity
        try:
            earnings = get_earnings_date(symbol)
            if earnings.days_until_earnings is not None:
                if 7 <= earnings.days_until_earnings <= 21:
                    catalyst_score += 10
                    signals.append(f"Earnings in {earnings.days_until_earnings} days")
                elif 0 <= earnings.days_until_earnings < 3:
                    catalyst_score -= 10
                    warnings.append("Earnings imminent - high risk")
        except:
            pass
        
        catalyst_score = max(0, min(100, catalyst_score))
        
        # === TOTAL SCORE ===
        # Weight: Technical 40%, Fundamental 35%, Catalyst 25%
        total_score = int(tech_score * 0.40 + fund_score * 0.35 + catalyst_score * 0.25)
        
        # Bonus for multiple strong signals
        if len(signals) >= 5:
            total_score += 10
        elif len(signals) >= 3:
            total_score += 5
        
        # Penalty for warnings
        total_score -= len(warnings) * 3
        
        total_score = max(0, min(100, total_score))
        
        # Determine confidence and entry type
        if total_score >= 80 and len(signals) >= 4:
            confidence = "HIGH"
            entry_type = "STRONG_BUY"
        elif total_score >= 70:
            confidence = "HIGH"
            entry_type = "BUY"
        elif total_score >= 60:
            confidence = "MEDIUM"
            entry_type = "BUY"
        else:
            confidence = "LOW"
            entry_type = "SPECULATIVE"
        
        return Opportunity(
            symbol=symbol,
            sector=sector,
            current_price=current_price,
            technical_score=tech_score,
            fundamental_score=fund_score,
            catalyst_score=catalyst_score,
            total_score=total_score,
            signals=signals,
            warnings=warnings,
            rsi=rsi,
            change_1d=change_1d,
            change_5d=change_5d,
            volume_ratio=volume_ratio,
            analyst_target=analyst_target,
            upside_pct=upside,
            confidence=confidence,
            entry_type=entry_type,
        )
        
    except Exception as e:
        logger.debug(f"Failed to analyze {symbol}: {e}")
        return None


def format_opportunities_discord(opportunities: list[Opportunity]) -> list[str]:
    """Format opportunities for Discord (may need multiple messages)."""
    
    if not opportunities:
        return ["📭 No opportunities found matching criteria."]
    
    messages = []
    
    header = f"""
🔍 **OPPORTUNITY SCAN** - {datetime.now().strftime('%B %d, %Y %I:%M %p')}
Found **{len(opportunities)}** potential setups
═══════════════════════════════════════════
"""
    messages.append(header)
    
    current_msg = ""
    
    for i, opp in enumerate(opportunities, 1):
        # Entry type emoji
        type_emoji = "🟢" if opp.entry_type == "STRONG_BUY" else "🟡" if opp.entry_type == "BUY" else "🟠"
        
        entry = f"""
{type_emoji} **#{i} {opp.symbol}** - {opp.entry_type} ({opp.confidence} confidence)
├─ Score: **{opp.total_score}/100** (Tech:{opp.technical_score} Fund:{opp.fundamental_score} Cat:{opp.catalyst_score})
├─ Price: ${opp.current_price:.2f} | 1D: {opp.change_1d:+.1f}% | 5D: {opp.change_5d:+.1f}%
├─ RSI: {f'{opp.rsi:.0f}' if opp.rsi else 'N/A'} | Volume: {opp.volume_ratio:.1f}x avg
"""
        if opp.upside_pct:
            entry += f"├─ Target: ${opp.analyst_target:.2f} ({opp.upside_pct:+.0f}% upside)\n"
        
        entry += f"├─ ✅ {', '.join(opp.signals[:4])}\n"
        
        if opp.warnings:
            entry += f"├─ ⚠️ {', '.join(opp.warnings)}\n"
        
        entry += f"└─ Sector: {opp.sector.title()}\n"
        
        # Check message length
        if len(current_msg) + len(entry) > 1800:
            messages.append(current_msg)
            current_msg = entry
        else:
            current_msg += entry
    
    if current_msg:
        messages.append(current_msg)
    
    return messages


def format_quick_opportunities(opportunities: list[Opportunity], limit: int = 10) -> str:
    """Format a quick summary of top opportunities."""
    
    if not opportunities:
        return "📭 No opportunities found."
    
    lines = [
        f"🔍 **TOP {min(limit, len(opportunities))} OPPORTUNITIES**",
        "═" * 35,
    ]
    
    for opp in opportunities[:limit]:
        emoji = "🟢" if opp.entry_type == "STRONG_BUY" else "🟡" if opp.entry_type == "BUY" else "🟠"
        rsi_str = f"{opp.rsi:.0f}" if opp.rsi else "?"
        signal_str = opp.signals[0] if opp.signals else ""
        lines.append(
            f"{emoji} **{opp.symbol}** ({opp.total_score}) ${opp.current_price:.2f} "
            f"| RSI:{rsi_str} | {signal_str}"
        )
    
    lines.append("")
    lines.append("Use `!opportunities full` for detailed analysis")
    
    return "\n".join(lines)
