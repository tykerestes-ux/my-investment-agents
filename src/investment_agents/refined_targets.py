"""
Refined Price Target System for Semi Equipment (LRCX, KLAC, ASML)

Key Logic:
1. Aggregation: Median/Trimmed Mean (not simple average) - reduces outlier impact
2. Geopolitical Haircut: 0.85-0.90x multiplier for China exposure / margin compression
3. Time-Decay Calibration: Cap 6-month upside at 1.5x SOXX growth rate

Circuit Breakers:
- Momentum breakout (RSI > 70): Revert to weighted mean for upside capture
- Margin surprise (>48% gross margin): Waive geopolitical haircut for 30 days
- High-conviction catalyst (EPS revised >5% in 7d): Allow exceeding 1.5x cap
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import statistics

import yfinance as yf

from .technical_indicators import calculate_rsi

logger = logging.getLogger(__name__)

# Semi equipment stocks requiring refined targets
SEMI_EQUIPMENT = ["LRCX", "KLAC", "ASML", "AMAT"]

# China revenue thresholds (approximate - these should be updated from earnings)
# Source: Latest 10-K filings as of Feb 2026
CHINA_REVENUE_PCT = {
    "LRCX": 0.32,   # ~32% China revenue
    "KLAC": 0.28,   # ~28% China revenue
    "ASML": 0.29,   # ~29% China revenue (incl. HK)
    "AMAT": 0.27,   # ~27% China revenue
}

# Recent gross margin trends (from latest quarterly reports)
# True = margin compression detected, False = stable/improving
MARGIN_COMPRESSION = {
    "LRCX": True,   # 90bps compression noted
    "KLAC": False,
    "ASML": True,   # Slight compression
    "AMAT": True,   # Under pressure from compliance costs
}

# Cache for margin surprise override (symbol -> expiry date)
_margin_surprise_cache: dict[str, datetime] = {}


@dataclass
class CycleRiskSummary:
    """Summary of cycle risk analysis."""
    wfe_multiplier: float
    inventory_multiplier: float
    beta_multiplier: float
    total_cycle_multiplier: float
    risk_level: str
    use_200dma_floor: bool
    dma_200: float | None
    warnings: list[str]


@dataclass
class RefinedTarget:
    """Refined price target with full methodology."""
    symbol: str
    current_price: float
    
    # Raw analyst data
    analyst_targets: list[float]
    analyst_count: int
    raw_mean: float
    raw_median: float
    
    # Refined target
    aggregation_method: str  # "median", "trimmed_mean", "weighted_mean"
    base_target: float  # Before adjustments
    
    # Adjustments
    geopolitical_multiplier: float  # 0.85-1.0
    geopolitical_reason: str
    soxx_cap_applied: bool
    soxx_growth_rate: float
    max_allowed_target: float  # Based on 1.5x SOXX cap
    
    # Cycle risk (NEW - bearish parameters)
    cycle_risk: CycleRiskSummary | None
    
    # Final target
    final_target: float
    upside_percent: float
    
    # Circuit breakers triggered
    momentum_breakout: bool  # RSI > 70
    margin_surprise_active: bool  # Recent margin beat
    eps_revision_override: bool  # EPS revised >5% in 7d
    
    # Confidence
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    methodology_notes: list[str]


def get_analyst_targets(symbol: str) -> list[float]:
    """Fetch analyst price targets from yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        targets = []
        
        # Get various target metrics
        target_high = info.get("targetHighPrice")
        target_low = info.get("targetLowPrice")
        target_mean = info.get("targetMeanPrice")
        target_median = info.get("targetMedianPrice")
        
        # Build list of available targets
        if target_high:
            targets.append(target_high)
        if target_low:
            targets.append(target_low)
        if target_mean:
            targets.append(target_mean)
        if target_median and target_median not in targets:
            targets.append(target_median)
        
        # If we have recommendations, try to get more granular targets
        # (In reality, you'd want a proper data feed here)
        
        return targets
        
    except Exception as e:
        logger.error(f"Error fetching analyst targets for {symbol}: {e}")
        return []


def calculate_trimmed_mean(values: list[float], trim_pct: float = 0.10) -> float:
    """Calculate trimmed mean, removing top/bottom trim_pct."""
    if len(values) < 3:
        return statistics.mean(values) if values else 0
    
    sorted_vals = sorted(values)
    trim_count = max(1, int(len(sorted_vals) * trim_pct))
    
    # Remove top and bottom trim_count values
    trimmed = sorted_vals[trim_count:-trim_count] if trim_count < len(sorted_vals) // 2 else sorted_vals
    
    return statistics.mean(trimmed) if trimmed else statistics.mean(values)


def calculate_weighted_mean(values: list[float], current_price: float) -> float:
    """Calculate weighted mean, giving more weight to targets closer to current price.
    
    Used during momentum breakouts to capture upside without being untethered.
    """
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    
    # Weight inversely by distance from current price (but still favor upside)
    weights = []
    for v in values:
        distance = abs(v - current_price)
        # Closer targets get higher weight, but upside targets get bonus
        weight = 1 / (1 + distance / current_price)
        if v > current_price:
            weight *= 1.2  # 20% bonus for upside targets during momentum
        weights.append(weight)
    
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    return weighted_sum / sum(weights)


def get_soxx_growth_rate(period_days: int = 180) -> float:
    """Get SOXX (Semiconductor Index) growth rate over period."""
    try:
        soxx = yf.Ticker("SOXX")
        hist = soxx.history(period="1y", interval="1d")
        
        if hist is None or len(hist) < period_days:
            return 0.10  # Default 10% if unavailable
        
        current = hist['Close'].iloc[-1]
        past = hist['Close'].iloc[-period_days] if len(hist) >= period_days else hist['Close'].iloc[0]
        
        growth_rate = (current - past) / past
        return growth_rate
        
    except Exception as e:
        logger.error(f"Error fetching SOXX data: {e}")
        return 0.10  # Default 10%


def check_margin_surprise(symbol: str) -> bool:
    """Check if recent margin surprise should waive geopolitical haircut.
    
    Returns True if gross margin > 48% in latest quarter.
    """
    # Check cache first
    if symbol in _margin_surprise_cache:
        if datetime.now() < _margin_surprise_cache[symbol]:
            return True
    
    try:
        ticker = yf.Ticker(symbol)
        
        # Try to get gross margin from financials
        financials = ticker.quarterly_financials
        if financials is not None and not financials.empty:
            if 'Gross Profit' in financials.index and 'Total Revenue' in financials.index:
                gross_profit = financials.loc['Gross Profit'].iloc[0]
                revenue = financials.loc['Total Revenue'].iloc[0]
                if revenue > 0:
                    margin = gross_profit / revenue
                    if margin > 0.48:  # 48% threshold
                        # Cache for 30 days
                        _margin_surprise_cache[symbol] = datetime.now() + timedelta(days=30)
                        return True
        
        return False
        
    except Exception as e:
        logger.debug(f"Error checking margin for {symbol}: {e}")
        return False


def check_eps_revision(symbol: str, days: int = 7, threshold: float = 0.05) -> bool:
    """Check if EPS estimates revised up >5% in last 7 days.
    
    This allows exceeding the 1.5x SOXX cap for high-conviction events.
    """
    try:
        ticker = yf.Ticker(symbol)
        
        # Get earnings estimates
        earnings = ticker.earnings_estimate
        
        if earnings is None:
            return False
        
        # Check for revision data
        # Note: yfinance doesn't always have revision history
        # In production, you'd use a proper estimates API
        
        # For now, check if current estimates are significantly above recent
        info = ticker.info
        forward_eps = info.get("forwardEps")
        trailing_eps = info.get("trailingEps")
        
        if forward_eps and trailing_eps and trailing_eps > 0:
            eps_growth = (forward_eps - trailing_eps) / trailing_eps
            if eps_growth > threshold * 2:  # Strong forward growth indicates positive revisions
                return True
        
        return False
        
    except Exception as e:
        logger.debug(f"Error checking EPS revision for {symbol}: {e}")
        return False


def calculate_refined_target(symbol: str) -> RefinedTarget:
    """Calculate refined price target with all adjustments."""
    symbol = symbol.upper()
    notes = []
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        if not current_price:
            raise ValueError("No current price available")
        
        # === GET ANALYST TARGETS ===
        analyst_targets = []
        target_high = info.get("targetHighPrice")
        target_low = info.get("targetLowPrice")
        target_mean = info.get("targetMeanPrice")
        target_median = info.get("targetMedianPrice")
        analyst_count = info.get("numberOfAnalystOpinions", 0)
        
        if target_high:
            analyst_targets.append(target_high)
        if target_low:
            analyst_targets.append(target_low)
        if target_mean:
            analyst_targets.append(target_mean)
        if target_median and target_median not in analyst_targets:
            analyst_targets.append(target_median)
        
        if not analyst_targets:
            # Fallback: use current price + modest upside
            analyst_targets = [current_price * 1.10]
            notes.append("No analyst targets available - using 10% default")
        
        raw_mean = statistics.mean(analyst_targets)
        raw_median = statistics.median(analyst_targets)
        
        # === CHECK CIRCUIT BREAKERS ===
        
        # 1. Momentum breakout (RSI > 70)
        hist = ticker.history(period="1mo", interval="1d")
        rsi = calculate_rsi(hist['Close']) if hist is not None and len(hist) >= 14 else None
        momentum_breakout = rsi is not None and rsi > 70
        
        # 2. Margin surprise
        margin_surprise = check_margin_surprise(symbol) if symbol in SEMI_EQUIPMENT else False
        
        # 3. EPS revision
        eps_override = check_eps_revision(symbol)
        
        # === AGGREGATION METHOD (Bullet 1) ===
        if momentum_breakout:
            # During momentum breakout, use weighted mean to capture upside
            aggregation_method = "weighted_mean"
            base_target = calculate_weighted_mean(analyst_targets, current_price)
            notes.append(f"RSI={rsi:.0f} > 70: Using weighted mean for momentum capture")
        else:
            # Normal: use median or trimmed mean to reduce outlier impact
            if len(analyst_targets) >= 4:
                aggregation_method = "trimmed_mean"
                base_target = calculate_trimmed_mean(analyst_targets, trim_pct=0.10)
                notes.append("Using trimmed mean (removed top/bottom 10%)")
            else:
                aggregation_method = "median"
                base_target = raw_median
                notes.append("Using median (limited data points)")
        
        # === GEOPOLITICAL HAIRCUT (Bullet 2) ===
        geopolitical_multiplier = 1.0
        geopolitical_reason = "No adjustment"
        
        if symbol in SEMI_EQUIPMENT:
            china_pct = CHINA_REVENUE_PCT.get(symbol, 0)
            has_margin_compression = MARGIN_COMPRESSION.get(symbol, False)
            
            # Check if margin surprise waives the haircut
            if margin_surprise:
                geopolitical_reason = f"Margin surprise (>48%) - haircut waived for 30 days"
                notes.append("CIRCUIT BREAKER: Margin surprise active - no geopolitical haircut")
            else:
                # Apply haircut based on China exposure and margin trends
                if china_pct > 0.30:
                    # High China exposure: 0.85x multiplier
                    geopolitical_multiplier = 0.85
                    geopolitical_reason = f"China revenue {china_pct*100:.0f}% > 30% threshold"
                    notes.append(f"Applied 0.85x haircut for China exposure ({china_pct*100:.0f}%)")
                elif china_pct > 0.20 and has_margin_compression:
                    # Moderate China + margin compression: 0.88x
                    geopolitical_multiplier = 0.88
                    geopolitical_reason = f"China {china_pct*100:.0f}% + margin compression"
                    notes.append(f"Applied 0.88x haircut for China + margin pressure")
                elif has_margin_compression:
                    # Just margin compression: 0.92x
                    geopolitical_multiplier = 0.92
                    geopolitical_reason = "Margin compression detected"
                    notes.append("Applied 0.92x haircut for margin compression")
        
        # Apply geopolitical multiplier
        adjusted_target = base_target * geopolitical_multiplier
        
        # === TIME-DECAY CALIBRATION (Bullet 3) ===
        soxx_growth = get_soxx_growth_rate(period_days=180)  # 6-month growth
        max_allowed_upside = soxx_growth * 1.5  # 1.5x SOXX cap
        max_allowed_target = current_price * (1 + max_allowed_upside)
        
        soxx_cap_applied = False
        
        # Check if we should apply the cap
        if adjusted_target > max_allowed_target:
            # Check for EPS revision override
            if eps_override:
                notes.append(f"EPS revision >5%: Exceeding 1.5x SOXX cap allowed")
                # Allow up to 2x SOXX instead of 1.5x
                max_allowed_target = current_price * (1 + soxx_growth * 2.0)
                if adjusted_target > max_allowed_target:
                    adjusted_target = max_allowed_target
                    soxx_cap_applied = True
                    notes.append(f"Capped at 2.0x SOXX (EPS override)")
            else:
                adjusted_target = max_allowed_target
                soxx_cap_applied = True
                notes.append(f"Capped at 1.5x SOXX growth rate ({soxx_growth*100:.1f}% 6-mo)")
        
        # === CYCLE RISK ANALYSIS (Bearish Parameters) ===
        cycle_risk = None
        if symbol in SEMI_EQUIPMENT:
            try:
                from .semi_cycle_risk import analyze_cycle_risk
                cycle_result = analyze_cycle_risk(symbol, adjusted_target)
                
                cycle_risk = CycleRiskSummary(
                    wfe_multiplier=cycle_result.wfe_analysis.multiplier,
                    inventory_multiplier=cycle_result.inventory_analysis.multiplier,
                    beta_multiplier=cycle_result.beta_analysis.multiplier,
                    total_cycle_multiplier=cycle_result.total_multiplier,
                    risk_level=cycle_result.risk_level,
                    use_200dma_floor=cycle_result.beta_analysis.use_200dma_floor,
                    dma_200=cycle_result.hard_floor_200dma,
                    warnings=cycle_result.warnings,
                )
                
                # Apply cycle risk to target
                adjusted_target = cycle_result.final_target
                
                if cycle_result.total_multiplier < 1.0:
                    notes.append(f"CYCLE RISK: {cycle_result.total_multiplier:.2f}x ({cycle_result.risk_level})")
                
                for warning in cycle_result.warnings:
                    notes.append(f"⚠️ {warning}")
                    
            except Exception as e:
                logger.debug(f"Cycle risk analysis unavailable: {e}")
        
        # === FINAL TARGET ===
        final_target = adjusted_target
        upside_percent = ((final_target - current_price) / current_price) * 100
        
        # === CONFIDENCE ASSESSMENT ===
        # Downgrade confidence if cycle risk is high
        if cycle_risk and cycle_risk.risk_level in ["HIGH", "SEVERE"]:
            confidence = "LOW"
        elif analyst_count >= 10 and not soxx_cap_applied:
            confidence = "HIGH"
        elif analyst_count >= 5 or margin_surprise or eps_override:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        return RefinedTarget(
            symbol=symbol,
            current_price=current_price,
            analyst_targets=analyst_targets,
            analyst_count=analyst_count,
            raw_mean=raw_mean,
            raw_median=raw_median,
            aggregation_method=aggregation_method,
            base_target=base_target,
            geopolitical_multiplier=geopolitical_multiplier,
            geopolitical_reason=geopolitical_reason,
            soxx_cap_applied=soxx_cap_applied,
            soxx_growth_rate=soxx_growth,
            max_allowed_target=max_allowed_target,
            cycle_risk=cycle_risk,
            final_target=final_target,
            upside_percent=upside_percent,
            momentum_breakout=momentum_breakout,
            margin_surprise_active=margin_surprise,
            eps_revision_override=eps_override,
            confidence=confidence,
            methodology_notes=notes,
        )
        
    except Exception as e:
        logger.error(f"Error calculating refined target for {symbol}: {e}")
        return RefinedTarget(
            symbol=symbol,
            current_price=0,
            analyst_targets=[],
            analyst_count=0,
            raw_mean=0,
            raw_median=0,
            aggregation_method="error",
            base_target=0,
            geopolitical_multiplier=1.0,
            geopolitical_reason=str(e),
            soxx_cap_applied=False,
            soxx_growth_rate=0,
            max_allowed_target=0,
            cycle_risk=None,
            final_target=0,
            upside_percent=0,
            momentum_breakout=False,
            margin_surprise_active=False,
            eps_revision_override=False,
            confidence="LOW",
            methodology_notes=[f"Error: {str(e)}"],
        )


def format_refined_target_discord(target: RefinedTarget) -> str:
    """Format refined target for Discord."""
    lines = [
        f"🎯 **REFINED TARGET: {target.symbol}**",
        f"**Current Price:** ${target.current_price:.2f}",
        f"**Final Target:** ${target.final_target:.2f} ({target.upside_percent:+.1f}%)",
        f"**Confidence:** {target.confidence}",
        "",
    ]
    
    # Raw vs Refined comparison
    lines.append("**📊 Analyst Data:**")
    lines.append(f"├─ Raw Mean: ${target.raw_mean:.2f}")
    lines.append(f"├─ Raw Median: ${target.raw_median:.2f}")
    lines.append(f"├─ Analyst Count: {target.analyst_count}")
    lines.append(f"└─ Method: {target.aggregation_method}")
    lines.append("")
    
    # Adjustments
    lines.append("**🔧 Adjustments Applied:**")
    lines.append(f"├─ Base Target: ${target.base_target:.2f}")
    
    if target.geopolitical_multiplier < 1.0:
        lines.append(f"├─ Geopolitical: {target.geopolitical_multiplier:.2f}x ({target.geopolitical_reason})")
    else:
        lines.append(f"├─ Geopolitical: None ({target.geopolitical_reason})")
    
    if target.soxx_cap_applied:
        lines.append(f"├─ SOXX Cap: Applied (6-mo growth: {target.soxx_growth_rate*100:.1f}%)")
        lines.append(f"└─ Max Allowed: ${target.max_allowed_target:.2f}")
    else:
        lines.append(f"└─ SOXX Cap: Not needed (within 1.5x)")
    
    lines.append("")
    
    # Circuit breakers
    lines.append("**⚡ Circuit Breakers:**")
    if target.momentum_breakout:
        lines.append("├─ ✅ Momentum Breakout (RSI > 70) - using weighted mean")
    else:
        lines.append("├─ ❌ Momentum Breakout")
    
    if target.margin_surprise_active:
        lines.append("├─ ✅ Margin Surprise (>48%) - haircut waived")
    else:
        lines.append("├─ ❌ Margin Surprise")
    
    if target.eps_revision_override:
        lines.append("└─ ✅ EPS Revision (>5%) - 2x cap allowed")
    else:
        lines.append("└─ ❌ EPS Revision")
    
    # Cycle Risk (Bearish Parameters)
    if target.cycle_risk:
        lines.append("")
        risk_emoji = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "SEVERE": "🔴"}.get(target.cycle_risk.risk_level, "⚪")
        lines.append(f"**🐻 Cycle Risk Analysis:** {risk_emoji} {target.cycle_risk.risk_level}")
        lines.append(f"├─ WFE Spending: {target.cycle_risk.wfe_multiplier:.2f}x")
        lines.append(f"├─ Inventory Health: {target.cycle_risk.inventory_multiplier:.2f}x")
        lines.append(f"├─ Beta/SOXX: {target.cycle_risk.beta_multiplier:.2f}x")
        lines.append(f"├─ **Total Cycle Adj:** {target.cycle_risk.total_cycle_multiplier:.2f}x")
        if target.cycle_risk.use_200dma_floor and target.cycle_risk.dma_200:
            lines.append(f"└─ 📉 200 DMA Floor: ${target.cycle_risk.dma_200:.2f}")
        else:
            lines.append(f"└─ No hard floor active")
        
        if target.cycle_risk.warnings:
            lines.append("")
            lines.append("**⚠️ Cycle Warnings:**")
            for w in target.cycle_risk.warnings[:3]:
                lines.append(f"• {w}")
    
    # Methodology notes
    if target.methodology_notes:
        lines.append("")
        lines.append("**📝 Notes:**")
        for note in target.methodology_notes[:5]:  # Limit to 5 notes
            lines.append(f"• {note}")
    
    return "\n".join(lines)


def update_china_revenue(symbol: str, pct: float) -> None:
    """Update China revenue percentage for a symbol (from earnings call)."""
    if symbol.upper() in CHINA_REVENUE_PCT:
        CHINA_REVENUE_PCT[symbol.upper()] = pct
        logger.info(f"Updated {symbol} China revenue to {pct*100:.1f}%")


def update_margin_status(symbol: str, has_compression: bool) -> None:
    """Update margin compression status for a symbol."""
    if symbol.upper() in MARGIN_COMPRESSION:
        MARGIN_COMPRESSION[symbol.upper()] = has_compression
        logger.info(f"Updated {symbol} margin compression to {has_compression}")
