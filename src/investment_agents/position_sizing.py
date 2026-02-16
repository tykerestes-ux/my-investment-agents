"""Position Sizing - Calculate optimal position size based on confidence and risk."""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level categories."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class PositionSize:
    """Position sizing recommendation."""
    symbol: str
    confidence: int
    signal_type: str
    
    # Risk factors
    earnings_lockout: bool
    sector_crowding: bool
    news_negative: bool
    timeframe_aligned: bool
    
    # Sizing
    base_position_percent: float  # % of portfolio for this trade
    adjusted_position_percent: float  # After risk adjustments
    risk_multiplier: float  # 0.25 to 1.5
    
    # Stop loss
    recommended_stop_percent: float
    max_loss_percent: float  # Max loss on portfolio
    
    # Rationale
    sizing_rationale: str
    warnings: list[str]


def calculate_position_size(
    symbol: str,
    confidence: int,
    signal_type: str,
    account_size: float = 10000,  # Default $10k account
    max_position_percent: float = 25,  # Max 25% in any single position
    earnings_lockout: bool = False,
    sector_crowding: bool = False,
    news_negative: bool = False,
    timeframe_alignment_score: int = 4,  # Out of 4
    risk_level: RiskLevel = RiskLevel.MODERATE,
) -> PositionSize:
    """Calculate recommended position size based on confidence and risk factors.
    
    Args:
        symbol: Ticker symbol
        confidence: Signal confidence (0-100)
        signal_type: "STRONG_BUY", "BUY", etc.
        account_size: Total account value
        max_position_percent: Maximum % of account for single position
        earnings_lockout: If earnings are imminent
        sector_crowding: If sector has too many buy signals
        news_negative: If negative news detected
        timeframe_alignment_score: 0-4 alignment score
        risk_level: User's risk tolerance
    
    Returns:
        PositionSize with recommendations
    """
    warnings = []
    
    # Base position size by signal type
    if signal_type == "STRONG_BUY":
        base_percent = 20.0
    elif signal_type == "BUY":
        base_percent = 15.0
    elif signal_type == "WAIT":
        base_percent = 5.0
    else:
        base_percent = 0.0
        warnings.append("No entry recommended - position size is 0%")
    
    # Adjust by confidence
    # 70% confidence = 70% of base size
    # 100% confidence = 100% of base size
    confidence_multiplier = confidence / 100
    
    # Risk factor adjustments
    risk_multiplier = 1.0
    
    # Earnings lockout - reduce significantly
    if earnings_lockout:
        risk_multiplier *= 0.25
        warnings.append("Earnings imminent - position reduced by 75%")
    
    # Sector crowding - reduce moderately
    if sector_crowding:
        risk_multiplier *= 0.6
        warnings.append("Sector crowding detected - position reduced by 40%")
    
    # Negative news - reduce or skip
    if news_negative:
        risk_multiplier *= 0.3
        warnings.append("Negative news detected - position reduced by 70%")
    
    # Timeframe alignment bonus
    if timeframe_alignment_score == 4:
        risk_multiplier *= 1.2
        warnings.append("All timeframes aligned - position increased by 20%")
    elif timeframe_alignment_score <= 1:
        risk_multiplier *= 0.7
        warnings.append("Poor timeframe alignment - position reduced by 30%")
    
    # Adjust by risk level
    if risk_level == RiskLevel.CONSERVATIVE:
        risk_multiplier *= 0.6
    elif risk_level == RiskLevel.AGGRESSIVE:
        risk_multiplier *= 1.3
    
    # Calculate final position
    adjusted_percent = base_percent * confidence_multiplier * risk_multiplier
    
    # Cap at maximum
    adjusted_percent = min(adjusted_percent, max_position_percent)
    
    # Calculate stop loss
    if signal_type in ["STRONG_BUY", "BUY"]:
        # Tighter stop for lower confidence
        if confidence >= 85:
            stop_percent = 5.0
        elif confidence >= 70:
            stop_percent = 4.0
        else:
            stop_percent = 3.0
    else:
        stop_percent = 2.0
    
    # Max loss on portfolio
    max_loss_percent = adjusted_percent * (stop_percent / 100)
    
    # Generate rationale
    rationale_parts = [
        f"Base: {base_percent:.0f}%",
        f"Confidence adj: x{confidence_multiplier:.2f}",
        f"Risk adj: x{risk_multiplier:.2f}",
        f"Final: {adjusted_percent:.1f}%",
    ]
    sizing_rationale = " → ".join(rationale_parts)
    
    return PositionSize(
        symbol=symbol,
        confidence=confidence,
        signal_type=signal_type,
        earnings_lockout=earnings_lockout,
        sector_crowding=sector_crowding,
        news_negative=news_negative,
        timeframe_aligned=timeframe_alignment_score == 4,
        base_position_percent=base_percent,
        adjusted_position_percent=adjusted_percent,
        risk_multiplier=risk_multiplier,
        recommended_stop_percent=stop_percent,
        max_loss_percent=max_loss_percent,
        sizing_rationale=sizing_rationale,
        warnings=warnings,
    )


def format_position_size_discord(sizing: PositionSize, account_size: float = 10000) -> str:
    """Format position sizing for Discord."""
    dollar_amount = account_size * (sizing.adjusted_position_percent / 100)
    
    lines = [
        f"💰 **Position Sizing: {sizing.symbol}**",
        f"Signal: {sizing.signal_type} ({sizing.confidence}%)",
        "",
        f"**Recommended Position:**",
        f"• Size: {sizing.adjusted_position_percent:.1f}% of portfolio",
        f"• Dollar Amount: ${dollar_amount:,.0f} (on ${account_size:,.0f} account)",
        f"• Stop Loss: {sizing.recommended_stop_percent}%",
        f"• Max Portfolio Risk: {sizing.max_loss_percent:.2f}%",
        "",
        f"**Calculation:** {sizing.sizing_rationale}",
    ]
    
    if sizing.warnings:
        lines.append("\n**Risk Adjustments:**")
        for warning in sizing.warnings:
            lines.append(f"• {warning}")
    
    return "\n".join(lines)


def get_quick_size(confidence: int, signal_type: str) -> str:
    """Get quick position size recommendation as text."""
    if signal_type == "STRONG_BUY" and confidence >= 85:
        return "Full position (20%)"
    elif signal_type == "STRONG_BUY" and confidence >= 70:
        return "3/4 position (15%)"
    elif signal_type == "BUY" and confidence >= 70:
        return "1/2 position (10%)"
    elif signal_type == "BUY":
        return "1/4 position (5%)"
    else:
        return "No position (0%)"
