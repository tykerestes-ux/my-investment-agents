"""
Bearish Overlay System - Semiconductor Cyclicality & Overcapacity Risks

Three Key Bearish Triggers:
1. WFE Spending Reversion (Macro) - Industry capex budget shrinking
2. Inventory-to-Sales Ratio (Fundamental) - Demand cliff indicator
3. SOXX Correlation Crash (Market) - High-beta selloff protection

Each trigger has circuit breakers to avoid false positives.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf
import numpy as np

logger = logging.getLogger(__name__)

# Semi equipment stocks subject to bearish overlay
SEMI_EQUIPMENT = ["LRCX", "KLAC", "ASML", "AMAT"]

# 2026 WFE Spending Forecasts (in billions USD)
# These should be updated from industry reports (SEMI, Gartner, etc.)
WFE_CONSENSUS_2026 = 135.0  # Current consensus
WFE_BEARISH_THRESHOLD = 120.0  # Below this triggers macro haircut
HBM_GROWTH_THRESHOLD = 20.0  # HBM YoY growth that shields from full haircut

# Memory-centric companies (shielded if HBM is strong)
MEMORY_CENTRIC = ["LRCX", "AMAT"]  # High exposure to memory fabs

# Companies in product ramp phase (inventory exception)
PRODUCT_RAMP_PHASE = {
    "ASML": "High-NA EUV rollout",
    # Add others as needed
}


@dataclass
class WFESpendingData:
    """Wafer Fab Equipment spending data."""
    current_forecast: float  # 2026 WFE forecast in billions
    previous_forecast: float  # Prior forecast for comparison
    hbm_growth_yoy: float  # HBM demand growth %
    forecast_trend: str  # "rising", "stable", "falling"
    data_date: str


@dataclass
class InventoryData:
    """Inventory metrics for a company."""
    inventory_days_current: float | None
    inventory_days_prior: float | None
    inventory_change_pct: float | None
    in_product_ramp: bool
    product_ramp_reason: str | None


@dataclass 
class SOXXCorrelationData:
    """SOXX correlation and beta data."""
    beta_vs_soxx: float | None
    soxx_weekly_change: float
    stock_weekly_change: float
    relative_strength: float  # Stock return - SOXX return
    dma_200: float | None
    current_price: float


@dataclass
class BearishTrigger:
    """A single bearish trigger result."""
    name: str
    triggered: bool
    multiplier: float  # 0.80 - 1.0
    reason: str
    circuit_breaker_active: bool
    circuit_breaker_reason: str | None


@dataclass
class BearishOverlay:
    """Complete bearish overlay analysis."""
    symbol: str
    timestamp: datetime
    
    # Trigger results
    wfe_trigger: BearishTrigger
    inventory_trigger: BearishTrigger
    soxx_trigger: BearishTrigger
    
    # Combined multiplier
    combined_multiplier: float
    
    # Price floors
    current_price: float
    
    # Final assessment
    risk_level: str  # "LOW", "MODERATE", "HIGH", "SEVERE"
    
    # Optional fields with defaults must come last
    hard_floor_price: float | None = None  # 200 DMA if SOXX crash
    warnings: list[str] = field(default_factory=list)


def get_wfe_spending_data() -> WFESpendingData:
    """Get current WFE spending forecasts.
    
    In production, this would pull from:
    - SEMI industry reports
    - Gartner/IDC forecasts
    - Company earnings call guidance
    
    For now, we use estimated values that can be updated.
    """
    # TODO: Integrate with actual data source
    # These values should be updated quarterly from industry reports
    
    return WFESpendingData(
        current_forecast=130.0,  # Current 2026 estimate (conservative)
        previous_forecast=135.0,  # Prior estimate
        hbm_growth_yoy=35.0,  # HBM still growing strongly
        forecast_trend="stable",  # Could be "rising", "stable", "falling"
        data_date="2026-02-01",
    )


def get_inventory_data(symbol: str) -> InventoryData:
    """Get inventory metrics for a company."""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try to get quarterly financials
        balance = ticker.quarterly_balance_sheet
        income = ticker.quarterly_income_stmt
        
        if balance is None or balance.empty or income is None or income.empty:
            return InventoryData(
                inventory_days_current=None,
                inventory_days_prior=None,
                inventory_change_pct=None,
                in_product_ramp=symbol in PRODUCT_RAMP_PHASE,
                product_ramp_reason=PRODUCT_RAMP_PHASE.get(symbol),
            )
        
        # Calculate inventory days (Inventory / COGS * 365)
        inventory_current = None
        inventory_prior = None
        cogs_current = None
        
        if 'Inventory' in balance.index:
            inv_series = balance.loc['Inventory'].dropna()
            if len(inv_series) >= 2:
                inventory_current = inv_series.iloc[0]
                inventory_prior = inv_series.iloc[1]
        
        if 'Cost Of Revenue' in income.index:
            cogs_series = income.loc['Cost Of Revenue'].dropna()
            if len(cogs_series) >= 1:
                cogs_current = cogs_series.iloc[0]
        
        inv_days_current = None
        inv_days_prior = None
        change_pct = None
        
        if inventory_current and cogs_current and cogs_current > 0:
            # Annualize quarterly COGS
            annual_cogs = cogs_current * 4
            inv_days_current = (inventory_current / annual_cogs) * 365
            
            if inventory_prior:
                inv_days_prior = (inventory_prior / annual_cogs) * 365
                if inv_days_prior > 0:
                    change_pct = ((inv_days_current - inv_days_prior) / inv_days_prior) * 100
        
        return InventoryData(
            inventory_days_current=inv_days_current,
            inventory_days_prior=inv_days_prior,
            inventory_change_pct=change_pct,
            in_product_ramp=symbol in PRODUCT_RAMP_PHASE,
            product_ramp_reason=PRODUCT_RAMP_PHASE.get(symbol),
        )
        
    except Exception as e:
        logger.error(f"Error getting inventory data for {symbol}: {e}")
        return InventoryData(
            inventory_days_current=None,
            inventory_days_prior=None,
            inventory_change_pct=None,
            in_product_ramp=symbol in PRODUCT_RAMP_PHASE,
            product_ramp_reason=PRODUCT_RAMP_PHASE.get(symbol),
        )


def get_soxx_correlation_data(symbol: str) -> SOXXCorrelationData:
    """Calculate stock's beta vs SOXX and weekly performance."""
    try:
        # Get stock data
        stock = yf.Ticker(symbol)
        stock_hist = stock.history(period="1y", interval="1d")
        
        # Get SOXX data
        soxx = yf.Ticker("SOXX")
        soxx_hist = soxx.history(period="1y", interval="1d")
        
        if stock_hist is None or len(stock_hist) < 50 or soxx_hist is None or len(soxx_hist) < 50:
            return SOXXCorrelationData(
                beta_vs_soxx=None,
                soxx_weekly_change=0,
                stock_weekly_change=0,
                relative_strength=0,
                dma_200=None,
                current_price=0,
            )
        
        # Current price
        current_price = stock_hist['Close'].iloc[-1]
        
        # 200 DMA
        dma_200 = stock_hist['Close'].rolling(window=200).mean().iloc[-1] if len(stock_hist) >= 200 else None
        
        # Weekly changes (last 5 trading days)
        stock_weekly = ((stock_hist['Close'].iloc[-1] - stock_hist['Close'].iloc[-5]) / stock_hist['Close'].iloc[-5]) * 100
        soxx_weekly = ((soxx_hist['Close'].iloc[-1] - soxx_hist['Close'].iloc[-5]) / soxx_hist['Close'].iloc[-5]) * 100
        
        # Calculate beta (using daily returns)
        stock_returns = stock_hist['Close'].pct_change().dropna()
        soxx_returns = soxx_hist['Close'].pct_change().dropna()
        
        # Align the series
        min_len = min(len(stock_returns), len(soxx_returns))
        stock_returns = stock_returns.iloc[-min_len:]
        soxx_returns = soxx_returns.iloc[-min_len:]
        
        # Beta = Cov(stock, soxx) / Var(soxx)
        covariance = np.cov(stock_returns.values, soxx_returns.values)[0, 1]
        variance = np.var(soxx_returns.values)
        beta = covariance / variance if variance > 0 else 1.0
        
        # Relative strength
        relative_strength = stock_weekly - soxx_weekly
        
        return SOXXCorrelationData(
            beta_vs_soxx=beta,
            soxx_weekly_change=soxx_weekly,
            stock_weekly_change=stock_weekly,
            relative_strength=relative_strength,
            dma_200=dma_200,
            current_price=current_price,
        )
        
    except Exception as e:
        logger.error(f"Error getting SOXX correlation for {symbol}: {e}")
        return SOXXCorrelationData(
            beta_vs_soxx=None,
            soxx_weekly_change=0,
            stock_weekly_change=0,
            relative_strength=0,
            dma_200=None,
            current_price=0,
        )


def check_wfe_trigger(symbol: str, wfe_data: WFESpendingData) -> BearishTrigger:
    """
    Trigger 1: WFE Spending Reversion
    
    If WFE forecast < $120B, apply 0.80x multiplier.
    Circuit breaker: If HBM growth > 20% and company is memory-centric, use 0.90x instead.
    """
    if wfe_data.current_forecast >= WFE_BEARISH_THRESHOLD:
        return BearishTrigger(
            name="WFE Spending Reversion",
            triggered=False,
            multiplier=1.0,
            reason=f"WFE forecast ${wfe_data.current_forecast}B above ${WFE_BEARISH_THRESHOLD}B threshold",
            circuit_breaker_active=False,
            circuit_breaker_reason=None,
        )
    
    # WFE below threshold - check circuit breaker
    is_memory_centric = symbol in MEMORY_CENTRIC
    hbm_strong = wfe_data.hbm_growth_yoy > HBM_GROWTH_THRESHOLD
    
    if is_memory_centric and hbm_strong:
        return BearishTrigger(
            name="WFE Spending Reversion",
            triggered=True,
            multiplier=0.90,  # Reduced haircut
            reason=f"WFE at ${wfe_data.current_forecast}B (below ${WFE_BEARISH_THRESHOLD}B)",
            circuit_breaker_active=True,
            circuit_breaker_reason=f"HBM growth {wfe_data.hbm_growth_yoy:.0f}% shields memory-centric {symbol}",
        )
    
    return BearishTrigger(
        name="WFE Spending Reversion",
        triggered=True,
        multiplier=0.80,  # Full haircut
        reason=f"WFE forecast ${wfe_data.current_forecast}B < ${WFE_BEARISH_THRESHOLD}B threshold",
        circuit_breaker_active=False,
        circuit_breaker_reason=None,
    )


def check_inventory_trigger(symbol: str, inv_data: InventoryData) -> BearishTrigger:
    """
    Trigger 2: Inventory-to-Sales Ratio
    
    If inventory days increase >15% QoQ, apply 15% target reduction (0.85x).
    Circuit breaker: Ignore if company is in product ramp phase.
    """
    if inv_data.inventory_change_pct is None:
        return BearishTrigger(
            name="Inventory-to-Sales Ratio",
            triggered=False,
            multiplier=1.0,
            reason="Inventory data unavailable",
            circuit_breaker_active=False,
            circuit_breaker_reason=None,
        )
    
    if inv_data.inventory_change_pct <= 15:
        return BearishTrigger(
            name="Inventory-to-Sales Ratio",
            triggered=False,
            multiplier=1.0,
            reason=f"Inventory days changed {inv_data.inventory_change_pct:+.1f}% (within 15% threshold)",
            circuit_breaker_active=False,
            circuit_breaker_reason=None,
        )
    
    # Inventory rising >15% - check circuit breaker
    if inv_data.in_product_ramp:
        return BearishTrigger(
            name="Inventory-to-Sales Ratio",
            triggered=False,
            multiplier=1.0,
            reason=f"Inventory days up {inv_data.inventory_change_pct:.1f}%",
            circuit_breaker_active=True,
            circuit_breaker_reason=f"Product ramp phase: {inv_data.product_ramp_reason}",
        )
    
    return BearishTrigger(
        name="Inventory-to-Sales Ratio",
        triggered=True,
        multiplier=0.85,
        reason=f"Inventory days up {inv_data.inventory_change_pct:.1f}% QoQ (demand cliff warning)",
        circuit_breaker_active=False,
        circuit_breaker_reason=None,
    )


def check_soxx_trigger(symbol: str, soxx_data: SOXXCorrelationData) -> BearishTrigger:
    """
    Trigger 3: SOXX Correlation Crash
    
    If beta > 1.5 AND SOXX down >5% weekly, set hard floor at 200 DMA.
    Circuit breaker: If stock outperforming SOXX by >2%, maintain original target.
    """
    if soxx_data.beta_vs_soxx is None:
        return BearishTrigger(
            name="SOXX Correlation Crash",
            triggered=False,
            multiplier=1.0,
            reason="Beta data unavailable",
            circuit_breaker_active=False,
            circuit_breaker_reason=None,
        )
    
    high_beta = soxx_data.beta_vs_soxx > 1.5
    soxx_crashing = soxx_data.soxx_weekly_change < -5
    
    if not (high_beta and soxx_crashing):
        return BearishTrigger(
            name="SOXX Correlation Crash",
            triggered=False,
            multiplier=1.0,
            reason=f"Beta {soxx_data.beta_vs_soxx:.2f}, SOXX weekly {soxx_data.soxx_weekly_change:+.1f}%",
            circuit_breaker_active=False,
            circuit_breaker_reason=None,
        )
    
    # High beta + SOXX crash - check relative strength circuit breaker
    if soxx_data.relative_strength > 2:
        return BearishTrigger(
            name="SOXX Correlation Crash",
            triggered=False,
            multiplier=1.0,
            reason=f"Beta {soxx_data.beta_vs_soxx:.2f}, SOXX {soxx_data.soxx_weekly_change:+.1f}%",
            circuit_breaker_active=True,
            circuit_breaker_reason=f"Relative strength +{soxx_data.relative_strength:.1f}% (outperforming)",
        )
    
    # Calculate multiplier based on distance to 200 DMA
    if soxx_data.dma_200 and soxx_data.current_price > 0:
        # Target = 200 DMA (hard floor)
        # Multiplier = 200 DMA / current price (capped at 1.0)
        floor_multiplier = min(1.0, soxx_data.dma_200 / soxx_data.current_price)
    else:
        floor_multiplier = 0.85  # Default 15% haircut if no 200 DMA
    
    return BearishTrigger(
        name="SOXX Correlation Crash",
        triggered=True,
        multiplier=floor_multiplier,
        reason=f"High beta ({soxx_data.beta_vs_soxx:.2f}) + SOXX crash ({soxx_data.soxx_weekly_change:+.1f}%)",
        circuit_breaker_active=False,
        circuit_breaker_reason=None,
    )


def calculate_bearish_overlay(symbol: str) -> BearishOverlay:
    """Calculate complete bearish overlay for a symbol."""
    symbol = symbol.upper()
    timestamp = datetime.now()
    warnings = []
    
    # Get data
    wfe_data = get_wfe_spending_data()
    inv_data = get_inventory_data(symbol)
    soxx_data = get_soxx_correlation_data(symbol)
    
    # Check triggers
    wfe_trigger = check_wfe_trigger(symbol, wfe_data)
    inv_trigger = check_inventory_trigger(symbol, inv_data)
    soxx_trigger = check_soxx_trigger(symbol, soxx_data)
    
    # Combine multipliers (multiplicative, not additive)
    combined = wfe_trigger.multiplier * inv_trigger.multiplier * soxx_trigger.multiplier
    
    # Collect warnings
    if wfe_trigger.triggered:
        warnings.append(f"WFE MACRO: {wfe_trigger.reason}")
    if inv_trigger.triggered:
        warnings.append(f"INVENTORY: {inv_trigger.reason}")
    if soxx_trigger.triggered:
        warnings.append(f"SOXX CRASH: {soxx_trigger.reason}")
    
    # Determine hard floor
    hard_floor = None
    if soxx_trigger.triggered and soxx_data.dma_200:
        hard_floor = soxx_data.dma_200
    
    # Determine risk level
    triggered_count = sum([wfe_trigger.triggered, inv_trigger.triggered, soxx_trigger.triggered])
    if triggered_count >= 3 or combined < 0.70:
        risk_level = "SEVERE"
    elif triggered_count >= 2 or combined < 0.80:
        risk_level = "HIGH"
    elif triggered_count >= 1 or combined < 0.90:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"
    
    return BearishOverlay(
        symbol=symbol,
        timestamp=timestamp,
        wfe_trigger=wfe_trigger,
        inventory_trigger=inv_trigger,
        soxx_trigger=soxx_trigger,
        combined_multiplier=combined,
        current_price=soxx_data.current_price,
        risk_level=risk_level,
        hard_floor_price=hard_floor,
        warnings=warnings,
    )


def format_bearish_overlay_discord(overlay: BearishOverlay) -> str:
    """Format bearish overlay for Discord."""
    # Risk level emoji
    risk_emoji = {
        "LOW": "🟢",
        "MODERATE": "🟡",
        "HIGH": "🟠",
        "SEVERE": "🔴",
    }
    emoji = risk_emoji.get(overlay.risk_level, "⚪")
    
    lines = [
        f"🐻 **BEARISH OVERLAY: {overlay.symbol}** {emoji}",
        f"**Risk Level:** {overlay.risk_level}",
        f"**Combined Multiplier:** {overlay.combined_multiplier:.2f}x",
        "",
    ]
    
    # WFE Trigger
    lines.append("**1️⃣ WFE Spending Reversion (Macro):**")
    wfe_icon = "🔴" if overlay.wfe_trigger.triggered else "🟢"
    lines.append(f"   {wfe_icon} {overlay.wfe_trigger.reason}")
    if overlay.wfe_trigger.circuit_breaker_active:
        lines.append(f"   ⚡ Circuit breaker: {overlay.wfe_trigger.circuit_breaker_reason}")
    lines.append(f"   Multiplier: {overlay.wfe_trigger.multiplier:.2f}x")
    lines.append("")
    
    # Inventory Trigger
    lines.append("**2️⃣ Inventory-to-Sales Ratio (Fundamental):**")
    inv_icon = "🔴" if overlay.inventory_trigger.triggered else "🟢"
    lines.append(f"   {inv_icon} {overlay.inventory_trigger.reason}")
    if overlay.inventory_trigger.circuit_breaker_active:
        lines.append(f"   ⚡ Circuit breaker: {overlay.inventory_trigger.circuit_breaker_reason}")
    lines.append(f"   Multiplier: {overlay.inventory_trigger.multiplier:.2f}x")
    lines.append("")
    
    # SOXX Trigger
    lines.append("**3️⃣ SOXX Correlation Crash (Market):**")
    soxx_icon = "🔴" if overlay.soxx_trigger.triggered else "🟢"
    lines.append(f"   {soxx_icon} {overlay.soxx_trigger.reason}")
    if overlay.soxx_trigger.circuit_breaker_active:
        lines.append(f"   ⚡ Circuit breaker: {overlay.soxx_trigger.circuit_breaker_reason}")
    lines.append(f"   Multiplier: {overlay.soxx_trigger.multiplier:.2f}x")
    lines.append("")
    
    # Hard floor if applicable
    if overlay.hard_floor_price:
        lines.append(f"**📉 Hard Floor (200 DMA):** ${overlay.hard_floor_price:.2f}")
        lines.append("")
    
    # Warnings
    if overlay.warnings:
        lines.append("**⚠️ Active Warnings:**")
        for w in overlay.warnings:
            lines.append(f"• {w}")
    else:
        lines.append("**✅ No bearish triggers active**")
    
    return "\n".join(lines)


def format_bearish_compact(overlay: BearishOverlay) -> str:
    """Compact format for summaries."""
    emoji = "🟢" if overlay.risk_level == "LOW" else "🟡" if overlay.risk_level == "MODERATE" else "🔴"
    
    triggers = []
    if overlay.wfe_trigger.triggered:
        triggers.append("WFE")
    if overlay.inventory_trigger.triggered:
        triggers.append("INV")
    if overlay.soxx_trigger.triggered:
        triggers.append("SOXX")
    
    trigger_str = f" [{', '.join(triggers)}]" if triggers else ""
    
    return f"{emoji} **{overlay.symbol}** Bear: {overlay.combined_multiplier:.2f}x{trigger_str}"


# Configuration update functions
def update_wfe_forecast(forecast_billions: float) -> None:
    """Update the WFE spending forecast (call after industry reports)."""
    global WFE_CONSENSUS_2026
    WFE_CONSENSUS_2026 = forecast_billions
    logger.info(f"Updated WFE forecast to ${forecast_billions}B")


def add_product_ramp(symbol: str, reason: str) -> None:
    """Add a company to product ramp phase (inventory exception)."""
    PRODUCT_RAMP_PHASE[symbol.upper()] = reason
    logger.info(f"Added {symbol} to product ramp phase: {reason}")


def remove_product_ramp(symbol: str) -> None:
    """Remove a company from product ramp phase."""
    if symbol.upper() in PRODUCT_RAMP_PHASE:
        del PRODUCT_RAMP_PHASE[symbol.upper()]
        logger.info(f"Removed {symbol} from product ramp phase")
