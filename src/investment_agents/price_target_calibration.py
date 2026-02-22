"""
Price Target Calibration - Refined targets for semi equipment makers.

Key Principles:
1. Aggregation: Trimmed mean (remove top/bottom 10%) or median instead of simple average
2. Geopolitical Haircut: 0.85-0.90x multiplier for China exposure / margin compression
3. Time-Decay: Cap 6-month upside at 1.5x SOXX growth rate
4. Circuit Breakers: Override rules for momentum breakouts and margin surprises

Target Stocks: LRCX, KLAC, ASML, AMAT (semi equipment with China exposure)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# Stocks that get the full calibration treatment
SEMI_EQUIPMENT_TICKERS = ["LRCX", "KLAC", "ASML", "AMAT"]

# China revenue thresholds (approximate - would need API for real data)
# These are estimates based on recent filings
CHINA_REVENUE_PCT = {
    "LRCX": 30,   # ~30% China exposure
    "KLAC": 25,   # ~25% China exposure
    "ASML": 15,   # ~15% China exposure (but EUV restricted)
    "AMAT": 25,   # ~25% China exposure (just paid $252M penalty)
}

# Gross margin thresholds (below this = margin compression)
HEALTHY_GROSS_MARGIN = {
    "LRCX": 46.0,
    "KLAC": 62.0,
    "ASML": 50.0,
    "AMAT": 46.0,
}


@dataclass
class CalibratedTarget:
    """A calibrated price target with full audit trail."""
    symbol: str
    timestamp: datetime
    
    # Raw analyst data
    raw_targets: list[float]
    raw_mean: float
    raw_median: float
    raw_high: float
    raw_low: float
    
    # Calibrated values
    trimmed_mean: float  # After removing top/bottom 10%
    aggregation_method: str  # "trimmed_mean" or "weighted_mean"
    base_target: float  # Before risk overlays
    
    # Risk multipliers
    china_revenue_pct: float
    gross_margin_current: float | None
    gross_margin_healthy: float
    margin_trending_down: bool
    geopolitical_multiplier: float  # 0.85-1.0
    geopolitical_reason: str | None
    
    # Time-decay calibration
    soxx_6m_growth: float
    max_allowed_upside: float  # 1.5x SOXX growth
    time_decay_applied: bool
    
    # Circuit breakers
    momentum_breakout: bool  # RSI > 70
    margin_surprise: bool  # GM > threshold + 2%
    eps_revision_pct: float | None  # EPS revision last 7 days
    circuit_breaker_active: bool
    circuit_breaker_reason: str | None
    
    # Final calibrated target
    calibrated_target: float
    current_price: float
    upside_pct: float
    
    # Confidence
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    warnings: list[str]


def calculate_trimmed_mean(values: list[float], trim_pct: float = 0.1) -> float:
    """Calculate trimmed mean, removing top/bottom percentile."""
    if len(values) < 3:
        return sum(values) / len(values) if values else 0
    
    sorted_vals = sorted(values)
    trim_count = max(1, int(len(sorted_vals) * trim_pct))
    
    # Remove top and bottom
    trimmed = sorted_vals[trim_count:-trim_count] if trim_count > 0 else sorted_vals
    
    return sum(trimmed) / len(trimmed) if trimmed else sum(values) / len(values)


def get_soxx_6m_growth() -> float:
    """Get SOXX (Semiconductor Index) 6-month growth rate."""
    try:
        soxx = yf.Ticker("SOXX")
        hist = soxx.history(period="6mo", interval="1d")
        
        if hist is None or len(hist) < 20:
            return 10.0  # Default assumption
        
        start_price = hist['Close'].iloc[0]
        end_price = hist['Close'].iloc[-1]
        
        growth_pct = ((end_price - start_price) / start_price) * 100
        return growth_pct
        
    except Exception as e:
        logger.error(f"Error getting SOXX growth: {e}")
        return 10.0  # Conservative default


def get_gross_margin(symbol: str) -> float | None:
    """Get current gross margin for a symbol."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Try different fields
        gm = info.get("grossMargins")
        if gm:
            return gm * 100  # Convert to percentage
        
        return None
        
    except Exception as e:
        logger.debug(f"Error getting gross margin for {symbol}: {e}")
        return None


def check_margin_trend(symbol: str) -> bool:
    """Check if gross margins are trending down (last 4 quarters)."""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try to get quarterly financials
        financials = ticker.quarterly_financials
        
        if financials is None or financials.empty:
            return False  # Assume no trend down if no data
        
        # Look for gross profit trend
        if 'Gross Profit' in financials.index:
            gross_profits = financials.loc['Gross Profit'].dropna().head(4)
            if len(gross_profits) >= 2:
                # Check if declining
                recent = gross_profits.iloc[0]
                older = gross_profits.iloc[-1]
                return recent < older * 0.95  # 5% decline = trending down
        
        return False
        
    except Exception as e:
        logger.debug(f"Error checking margin trend for {symbol}: {e}")
        return False


def check_rsi_breakout(symbol: str) -> bool:
    """Check if RSI > 70 (momentum breakout)."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo", interval="1d")
        
        if hist is None or len(hist) < 14:
            return False
        
        # Calculate RSI
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = rsi.iloc[-1]
        return current_rsi > 70
        
    except Exception as e:
        logger.debug(f"Error checking RSI for {symbol}: {e}")
        return False


def check_eps_revision(symbol: str) -> float | None:
    """Check EPS revision in last 7 days (placeholder - needs real data source)."""
    # NOTE: yfinance doesn't provide EPS revision history
    # In production, this would use a service like Zacks or FactSet
    # For now, return None to indicate no data
    return None


async def calibrate_price_target(symbol: str) -> CalibratedTarget:
    """Generate a fully calibrated price target for semi equipment."""
    symbol = symbol.upper()
    timestamp = datetime.now()
    warnings = []
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        
        # === STEP 1: Gather Analyst Targets ===
        raw_targets = []
        
        target_mean = info.get("targetMeanPrice")
        target_median = info.get("targetMedianPrice")
        target_high = info.get("targetHighPrice")
        target_low = info.get("targetLowPrice")
        
        # Build list of targets (use available data points)
        if target_high:
            raw_targets.append(target_high)
        if target_mean:
            raw_targets.append(target_mean)
        if target_median:
            raw_targets.append(target_median)
        if target_low:
            raw_targets.append(target_low)
        
        # Add mean/median as additional data points for trimming
        if target_mean and target_median:
            # Estimate distribution
            raw_targets.extend([target_mean] * 2)  # Weight the mean
            raw_targets.append(target_median)
        
        if not raw_targets:
            return _empty_calibration(symbol, current_price, "No analyst targets available")
        
        # === STEP 2: Calculate Aggregation ===
        raw_mean = sum(raw_targets) / len(raw_targets)
        raw_median_val = median(raw_targets)
        
        # Check for momentum breakout
        momentum_breakout = check_rsi_breakout(symbol)
        
        # Choose aggregation method
        if momentum_breakout:
            # Use weighted mean to capture upside swing
            aggregation_method = "weighted_mean"
            # Weight higher targets more during momentum
            weights = [1.2 if t > raw_median_val else 1.0 for t in raw_targets]
            base_target = sum(t * w for t, w in zip(raw_targets, weights)) / sum(weights)
            warnings.append("RSI > 70: Using weighted mean (momentum mode)")
        else:
            # Use trimmed mean (remove outliers)
            aggregation_method = "trimmed_mean"
            base_target = calculate_trimmed_mean(raw_targets, trim_pct=0.1)
        
        # === STEP 3: Geopolitical Haircut ===
        china_pct = CHINA_REVENUE_PCT.get(symbol, 0)
        healthy_margin = HEALTHY_GROSS_MARGIN.get(symbol, 45)
        current_margin = get_gross_margin(symbol)
        margin_trending_down = check_margin_trend(symbol)
        
        # Determine multiplier
        geopolitical_multiplier = 1.0
        geopolitical_reason = None
        
        # Check China exposure
        if china_pct >= 30:
            geopolitical_multiplier = 0.85
            geopolitical_reason = f"High China revenue ({china_pct}%) - 0.85x applied"
            warnings.append(f"GEOPOLITICAL RISK: {china_pct}% China exposure")
        elif china_pct >= 20:
            geopolitical_multiplier = 0.90
            geopolitical_reason = f"Elevated China revenue ({china_pct}%) - 0.90x applied"
        
        # Check margin compression
        if current_margin and margin_trending_down:
            if current_margin < healthy_margin - 2:
                # Further reduction for margin issues
                geopolitical_multiplier *= 0.95
                geopolitical_reason = (geopolitical_reason or "") + f"; Margin compression ({current_margin:.1f}% vs {healthy_margin}% healthy)"
                warnings.append(f"MARGIN COMPRESSION: {current_margin:.1f}% (healthy: {healthy_margin}%)")
        
        # Check for margin surprise (circuit breaker)
        margin_surprise = False
        if current_margin and current_margin > healthy_margin + 2:
            margin_surprise = True
            # Waive geopolitical penalty for 30 days equivalent
            geopolitical_multiplier = min(1.0, geopolitical_multiplier + 0.10)
            warnings.append(f"MARGIN SURPRISE: {current_margin:.1f}% > {healthy_margin + 2}% - penalty reduced")
        
        # Apply geopolitical multiplier
        adjusted_target = base_target * geopolitical_multiplier
        
        # === STEP 4: Time-Decay Calibration ===
        soxx_growth = get_soxx_6m_growth()
        max_allowed_upside = soxx_growth * 1.5  # 1.5x SOXX growth cap
        
        current_upside = ((adjusted_target - current_price) / current_price) * 100
        time_decay_applied = False
        
        # Check EPS revision for circuit breaker
        eps_revision = check_eps_revision(symbol)
        eps_circuit_breaker = eps_revision and eps_revision > 5
        
        if current_upside > max_allowed_upside:
            if eps_circuit_breaker:
                # Allow exceeding cap due to EPS revision
                warnings.append(f"EPS revised +{eps_revision:.1f}% - allowing above 1.5x SOXX cap")
            else:
                # Apply time-decay cap
                time_decay_applied = True
                # Cap the target
                max_target = current_price * (1 + max_allowed_upside / 100)
                adjusted_target = min(adjusted_target, max_target)
                warnings.append(f"TIME-DECAY: Capped at 1.5x SOXX growth ({max_allowed_upside:.1f}%)")
        
        # === STEP 5: Final Calibration ===
        calibrated_target = adjusted_target
        final_upside = ((calibrated_target - current_price) / current_price) * 100
        
        # Determine circuit breaker status
        circuit_breaker_active = margin_surprise or eps_circuit_breaker or momentum_breakout
        circuit_breaker_reason = None
        if circuit_breaker_active:
            reasons = []
            if margin_surprise:
                reasons.append("margin_surprise")
            if eps_circuit_breaker:
                reasons.append("eps_revision")
            if momentum_breakout:
                reasons.append("momentum_breakout")
            circuit_breaker_reason = ", ".join(reasons)
        
        # Determine confidence
        if len(warnings) == 0:
            confidence = "HIGH"
        elif len(warnings) <= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        return CalibratedTarget(
            symbol=symbol,
            timestamp=timestamp,
            raw_targets=raw_targets,
            raw_mean=raw_mean,
            raw_median=raw_median_val,
            raw_high=target_high or 0,
            raw_low=target_low or 0,
            trimmed_mean=calculate_trimmed_mean(raw_targets),
            aggregation_method=aggregation_method,
            base_target=base_target,
            china_revenue_pct=china_pct,
            gross_margin_current=current_margin,
            gross_margin_healthy=healthy_margin,
            margin_trending_down=margin_trending_down,
            geopolitical_multiplier=geopolitical_multiplier,
            geopolitical_reason=geopolitical_reason,
            soxx_6m_growth=soxx_growth,
            max_allowed_upside=max_allowed_upside,
            time_decay_applied=time_decay_applied,
            momentum_breakout=momentum_breakout,
            margin_surprise=margin_surprise,
            eps_revision_pct=eps_revision,
            circuit_breaker_active=circuit_breaker_active,
            circuit_breaker_reason=circuit_breaker_reason,
            calibrated_target=calibrated_target,
            current_price=current_price,
            upside_pct=final_upside,
            confidence=confidence,
            warnings=warnings,
        )
        
    except Exception as e:
        logger.error(f"Error calibrating target for {symbol}: {e}")
        return _empty_calibration(symbol, 0, f"Error: {str(e)[:100]}")


def _empty_calibration(symbol: str, current_price: float, reason: str) -> CalibratedTarget:
    """Return empty calibration for error cases."""
    return CalibratedTarget(
        symbol=symbol,
        timestamp=datetime.now(),
        raw_targets=[],
        raw_mean=0,
        raw_median=0,
        raw_high=0,
        raw_low=0,
        trimmed_mean=0,
        aggregation_method="none",
        base_target=0,
        china_revenue_pct=0,
        gross_margin_current=None,
        gross_margin_healthy=0,
        margin_trending_down=False,
        geopolitical_multiplier=1.0,
        geopolitical_reason=None,
        soxx_6m_growth=0,
        max_allowed_upside=0,
        time_decay_applied=False,
        momentum_breakout=False,
        margin_surprise=False,
        eps_revision_pct=None,
        circuit_breaker_active=False,
        circuit_breaker_reason=None,
        calibrated_target=0,
        current_price=current_price,
        upside_pct=0,
        confidence="LOW",
        warnings=[reason],
    )


def format_calibration_discord(cal: CalibratedTarget) -> str:
    """Format calibrated target for Discord."""
    if not cal.raw_targets:
        return f"❌ **{cal.symbol}**: {cal.warnings[0] if cal.warnings else 'No data'}"
    
    # Confidence emoji
    conf_emoji = "🟢" if cal.confidence == "HIGH" else "🟡" if cal.confidence == "MEDIUM" else "🔴"
    
    lines = [
        f"🎯 **CALIBRATED TARGET: {cal.symbol}** {conf_emoji}",
        f"**Current Price:** ${cal.current_price:.2f}",
        f"**Calibrated Target:** ${cal.calibrated_target:.2f} ({cal.upside_pct:+.1f}%)",
        "",
    ]
    
    # Raw vs Calibrated comparison
    lines.append("**📊 Target Comparison:**")
    lines.append(f"├─ Raw Mean: ${cal.raw_mean:.2f}")
    lines.append(f"├─ Raw Median: ${cal.raw_median:.2f}")
    lines.append(f"├─ Trimmed Mean: ${cal.trimmed_mean:.2f}")
    lines.append(f"└─ **Calibrated: ${cal.calibrated_target:.2f}**")
    lines.append("")
    
    # Aggregation method
    lines.append(f"**📈 Aggregation:** {cal.aggregation_method}")
    if cal.momentum_breakout:
        lines.append("   └─ ⚡ Momentum breakout detected (RSI > 70)")
    lines.append("")
    
    # Geopolitical overlay
    lines.append("**🌍 Geopolitical Overlay:**")
    lines.append(f"├─ China Revenue: {cal.china_revenue_pct}%")
    if cal.gross_margin_current:
        margin_status = "📉" if cal.margin_trending_down else "📈"
        lines.append(f"├─ Gross Margin: {cal.gross_margin_current:.1f}% {margin_status}")
    lines.append(f"├─ Multiplier: {cal.geopolitical_multiplier:.2f}x")
    if cal.geopolitical_reason:
        lines.append(f"└─ {cal.geopolitical_reason}")
    lines.append("")
    
    # Time-decay
    lines.append("**⏱️ Time-Decay Calibration:**")
    lines.append(f"├─ SOXX 6M Growth: {cal.soxx_6m_growth:+.1f}%")
    lines.append(f"├─ Max Allowed Upside: {cal.max_allowed_upside:.1f}%")
    if cal.time_decay_applied:
        lines.append("└─ ⚠️ TIME-DECAY APPLIED")
    else:
        lines.append("└─ ✅ Within bounds")
    lines.append("")
    
    # Circuit breakers
    if cal.circuit_breaker_active:
        lines.append(f"**🔌 Circuit Breaker Active:** {cal.circuit_breaker_reason}")
        lines.append("")
    
    # Warnings
    if cal.warnings:
        lines.append("**⚠️ Warnings:**")
        for w in cal.warnings:
            lines.append(f"• {w}")
    
    return "\n".join(lines)


def format_calibration_compact(cal: CalibratedTarget) -> str:
    """Compact format for summaries."""
    if not cal.raw_targets:
        return f"❌ {cal.symbol}: No data"
    
    emoji = "🟢" if cal.confidence == "HIGH" else "🟡" if cal.confidence == "MEDIUM" else "🔴"
    
    flags = []
    if cal.geopolitical_multiplier < 1.0:
        flags.append(f"GEO:{cal.geopolitical_multiplier:.2f}x")
    if cal.time_decay_applied:
        flags.append("TIME-CAP")
    if cal.momentum_breakout:
        flags.append("MOMENTUM")
    
    flag_str = f" [{', '.join(flags)}]" if flags else ""
    
    return (
        f"{emoji} **{cal.symbol}** ${cal.current_price:.2f} → ${cal.calibrated_target:.2f} "
        f"({cal.upside_pct:+.1f}%){flag_str}"
    )
