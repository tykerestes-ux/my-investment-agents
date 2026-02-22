"""
Semiconductor Cycle Risk Model - Bearish Parameters for Semi Equipment

Accounts for:
1. WFE Spending Reversion (Macro) - Industry capex downcycle
2. Inventory-to-Sales Ratio (Fundamental) - Demand cliff detection
3. SOXX Correlation Crash (Market) - High-beta downside protection

Target Stocks: LRCX, KLAC, ASML, AMAT (semi equipment with cycle exposure)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# ===== CONFIGURATION =====

# WFE Spending thresholds (in billions USD)
# 2026 consensus is ~$135B, bearish threshold at $120B
WFE_SPENDING_CONSENSUS = 135.0  # Current consensus estimate
WFE_BEARISH_THRESHOLD = 120.0  # Trigger bearish overlay below this
WFE_CURRENT_ESTIMATE = 130.0   # Current estimate (update from industry data)

# HBM (High Bandwidth Memory) growth threshold
HBM_GROWTH_SHIELD_THRESHOLD = 20.0  # If HBM >20% YoY, reduce haircut

# Memory-exposed companies (benefit from HBM)
MEMORY_EXPOSED = ["LRCX", "AMAT"]  # Lam and AMAT have memory exposure

# Product ramp companies (high inventory is positive)
PRODUCT_RAMP_ACTIVE = {
    "ASML": "High-NA EUV rollout",  # High inventory = upcoming shipments
    # Add others as needed
}

# Beta thresholds
HIGH_BETA_THRESHOLD = 1.5
SOXX_CRASH_THRESHOLD = -5.0  # Weekly decline %

# Inventory increase threshold
INVENTORY_INCREASE_THRESHOLD = 15.0  # % QoQ increase


@dataclass
class WFEAnalysis:
    """Wafer Fab Equipment spending analysis."""
    current_estimate: float  # $B
    consensus_estimate: float  # $B
    bearish_threshold: float  # $B
    is_bearish: bool
    multiplier: float  # 0.80 - 1.0
    hbm_shield_active: bool
    reason: str


@dataclass
class InventoryAnalysis:
    """Inventory-to-Sales ratio analysis."""
    current_inventory_days: float | None
    previous_inventory_days: float | None
    qoq_change_pct: float | None
    is_warning: bool
    multiplier: float  # 0.85 - 1.0
    product_ramp_override: bool
    reason: str


@dataclass
class BetaAnalysis:
    """SOXX correlation and beta analysis."""
    stock_beta: float | None
    soxx_weekly_change: float
    stock_weekly_change: float
    is_crash_mode: bool
    relative_strength: float  # Stock vs SOXX performance
    use_200dma_floor: bool
    dma_200: float | None
    multiplier: float  # Applied to target
    reason: str


@dataclass
class CycleRiskResult:
    """Complete cycle risk assessment."""
    symbol: str
    timestamp: datetime
    
    # Individual analyses
    wfe_analysis: WFEAnalysis
    inventory_analysis: InventoryAnalysis
    beta_analysis: BetaAnalysis
    
    # Combined impact
    total_multiplier: float  # Product of all multipliers
    is_bearish_cycle: bool  # Any bearish trigger active
    
    # Price floors
    original_target: float
    adjusted_target: float
    hard_floor_200dma: float | None
    final_target: float  # Min of adjusted target and floor if crash mode
    
    # Summary
    risk_level: str  # "LOW", "MODERATE", "HIGH", "SEVERE"
    warnings: list[str]
    
    def format_discord(self) -> str:
        """Format for Discord output."""
        risk_emoji = {
            "LOW": "🟢",
            "MODERATE": "🟡", 
            "HIGH": "🟠",
            "SEVERE": "🔴",
        }
        emoji = risk_emoji.get(self.risk_level, "⚪")
        
        lines = [
            f"📉 **CYCLE RISK ANALYSIS: {self.symbol}** {emoji}",
            f"**Risk Level:** {self.risk_level}",
            f"**Total Adjustment:** {self.total_multiplier:.2f}x",
            "",
        ]
        
        # WFE Analysis
        lines.append("**1️⃣ WFE Spending (Macro):**")
        wfe = self.wfe_analysis
        wfe_status = "⚠️ BEARISH" if wfe.is_bearish else "✅ Normal"
        lines.append(f"├─ Estimate: ${wfe.current_estimate:.0f}B vs ${wfe.bearish_threshold:.0f}B threshold")
        lines.append(f"├─ Status: {wfe_status}")
        if wfe.hbm_shield_active:
            lines.append(f"├─ 🛡️ HBM Shield Active (memory demand strong)")
        lines.append(f"└─ Multiplier: {wfe.multiplier:.2f}x")
        lines.append("")
        
        # Inventory Analysis
        lines.append("**2️⃣ Inventory Health (Fundamental):**")
        inv = self.inventory_analysis
        if inv.current_inventory_days:
            inv_status = "⚠️ WARNING" if inv.is_warning else "✅ Healthy"
            lines.append(f"├─ Inventory Days: {inv.current_inventory_days:.0f}")
            if inv.qoq_change_pct:
                lines.append(f"├─ QoQ Change: {inv.qoq_change_pct:+.1f}%")
            lines.append(f"├─ Status: {inv_status}")
            if inv.product_ramp_override:
                lines.append(f"├─ 🔄 Product Ramp Override (high inv = shipments coming)")
            lines.append(f"└─ Multiplier: {inv.multiplier:.2f}x")
        else:
            lines.append("└─ Data unavailable")
        lines.append("")
        
        # Beta Analysis
        lines.append("**3️⃣ SOXX Correlation (Market):**")
        beta = self.beta_analysis
        if beta.stock_beta:
            beta_status = "🔴 CRASH MODE" if beta.is_crash_mode else "✅ Normal"
            lines.append(f"├─ Stock Beta: {beta.stock_beta:.2f}")
            lines.append(f"├─ SOXX Weekly: {beta.soxx_weekly_change:+.1f}%")
            lines.append(f"├─ Stock Weekly: {beta.stock_weekly_change:+.1f}%")
            lines.append(f"├─ Relative Strength: {beta.relative_strength:+.1f}%")
            lines.append(f"├─ Status: {beta_status}")
            if beta.use_200dma_floor and beta.dma_200:
                lines.append(f"├─ 📉 200 DMA Floor: ${beta.dma_200:.2f}")
            lines.append(f"└─ Multiplier: {beta.multiplier:.2f}x")
        else:
            lines.append("└─ Data unavailable")
        lines.append("")
        
        # Final target
        lines.append("**📊 Target Impact:**")
        lines.append(f"├─ Original Target: ${self.original_target:.2f}")
        lines.append(f"├─ After Cycle Risk: ${self.adjusted_target:.2f}")
        if self.hard_floor_200dma and self.beta_analysis.use_200dma_floor:
            lines.append(f"├─ 200 DMA Floor: ${self.hard_floor_200dma:.2f}")
        lines.append(f"└─ **Final Target: ${self.final_target:.2f}**")
        
        # Warnings
        if self.warnings:
            lines.append("")
            lines.append("**⚠️ Warnings:**")
            for w in self.warnings:
                lines.append(f"• {w}")
        
        return "\n".join(lines)


def get_wfe_analysis(symbol: str) -> WFEAnalysis:
    """
    Analyze WFE (Wafer Fab Equipment) spending cycle.
    
    If 2026 WFE spending < $120B, apply 0.80x multiplier.
    If HBM demand >20% YoY and symbol is memory-exposed, reduce to 0.90x.
    """
    # In production, this would pull from industry data APIs
    # For now, use configured estimates
    
    current = WFE_CURRENT_ESTIMATE
    threshold = WFE_BEARISH_THRESHOLD
    consensus = WFE_SPENDING_CONSENSUS
    
    is_bearish = current < threshold
    
    # Default multiplier
    if is_bearish:
        multiplier = 0.80
        reason = f"WFE spending ${current:.0f}B below ${threshold:.0f}B threshold"
    else:
        multiplier = 1.0
        reason = f"WFE spending ${current:.0f}B within healthy range"
    
    # HBM shield for memory-exposed companies
    hbm_shield = False
    if is_bearish and symbol in MEMORY_EXPOSED:
        # Check HBM growth (simulated - would need real data)
        # For now, assume HBM is growing >20% based on AI demand
        hbm_growth_estimate = 25.0  # Placeholder
        
        if hbm_growth_estimate > HBM_GROWTH_SHIELD_THRESHOLD:
            hbm_shield = True
            multiplier = 0.90  # Reduced haircut
            reason += f"; HBM shield active (growth {hbm_growth_estimate:.0f}%)"
    
    return WFEAnalysis(
        current_estimate=current,
        consensus_estimate=consensus,
        bearish_threshold=threshold,
        is_bearish=is_bearish,
        multiplier=multiplier,
        hbm_shield_active=hbm_shield,
        reason=reason,
    )


def get_inventory_analysis(symbol: str) -> InventoryAnalysis:
    """
    Analyze inventory-to-sales ratio for demand cliff detection.
    
    If Inventory Days increase >15% QoQ, apply 0.85x multiplier.
    Override if company is in product ramp phase.
    """
    try:
        ticker = yf.Ticker(symbol)
        
        # Get quarterly financials
        balance = ticker.quarterly_balance_sheet
        income = ticker.quarterly_income_stmt
        
        if balance is None or balance.empty or income is None or income.empty:
            return InventoryAnalysis(
                current_inventory_days=None,
                previous_inventory_days=None,
                qoq_change_pct=None,
                is_warning=False,
                multiplier=1.0,
                product_ramp_override=False,
                reason="Financial data unavailable",
            )
        
        # Calculate inventory days
        # Inventory Days = (Inventory / COGS) * 365
        inventory_current = None
        inventory_previous = None
        cogs_current = None
        
        # Try to get inventory
        for inv_key in ['Inventory', 'Total Inventory', 'Inventories']:
            if inv_key in balance.index:
                inv_series = balance.loc[inv_key].dropna()
                if len(inv_series) >= 2:
                    inventory_current = float(inv_series.iloc[0])
                    inventory_previous = float(inv_series.iloc[1])
                break
        
        # Try to get COGS
        for cogs_key in ['Cost Of Revenue', 'Cost of Revenue', 'COGS']:
            if cogs_key in income.index:
                cogs_series = income.loc[cogs_key].dropna()
                if len(cogs_series) >= 1:
                    cogs_current = float(cogs_series.iloc[0])
                break
        
        if inventory_current is None or cogs_current is None or cogs_current == 0:
            return InventoryAnalysis(
                current_inventory_days=None,
                previous_inventory_days=None,
                qoq_change_pct=None,
                is_warning=False,
                multiplier=1.0,
                product_ramp_override=False,
                reason="Inventory/COGS data unavailable",
            )
        
        # Calculate inventory days (annualized COGS)
        annual_cogs = cogs_current * 4  # Quarterly to annual
        inv_days_current = (inventory_current / annual_cogs) * 365
        inv_days_previous = (inventory_previous / annual_cogs) * 365 if inventory_previous else None
        
        # Calculate QoQ change
        qoq_change = None
        if inv_days_previous and inv_days_previous > 0:
            qoq_change = ((inv_days_current - inv_days_previous) / inv_days_previous) * 100
        
        # Check for warning
        is_warning = qoq_change is not None and qoq_change > INVENTORY_INCREASE_THRESHOLD
        
        # Product ramp override
        product_ramp = symbol in PRODUCT_RAMP_ACTIVE
        
        if is_warning and product_ramp:
            multiplier = 1.0  # Override - high inventory is positive
            reason = f"Inventory up {qoq_change:.1f}% but {PRODUCT_RAMP_ACTIVE[symbol]} active"
        elif is_warning:
            multiplier = 0.85  # 15% reduction
            reason = f"Inventory days up {qoq_change:.1f}% QoQ - demand cliff warning"
        else:
            multiplier = 1.0
            reason = f"Inventory healthy at {inv_days_current:.0f} days"
        
        return InventoryAnalysis(
            current_inventory_days=inv_days_current,
            previous_inventory_days=inv_days_previous,
            qoq_change_pct=qoq_change,
            is_warning=is_warning and not product_ramp,
            multiplier=multiplier,
            product_ramp_override=product_ramp and is_warning,
            reason=reason,
        )
        
    except Exception as e:
        logger.error(f"Error analyzing inventory for {symbol}: {e}")
        return InventoryAnalysis(
            current_inventory_days=None,
            previous_inventory_days=None,
            qoq_change_pct=None,
            is_warning=False,
            multiplier=1.0,
            product_ramp_override=False,
            reason=f"Error: {str(e)[:50]}",
        )


def get_beta_analysis(symbol: str) -> BetaAnalysis:
    """
    Analyze SOXX correlation and beta for crash protection.
    
    If Beta > 1.5 and SOXX down >5% weekly, use 200 DMA as hard floor.
    Exception: If stock outperforming SOXX by >2%, maintain original target.
    """
    try:
        # Get stock data
        ticker = yf.Ticker(symbol)
        stock_hist = ticker.history(period="1y", interval="1d")
        
        if stock_hist is None or len(stock_hist) < 200:
            return BetaAnalysis(
                stock_beta=None,
                soxx_weekly_change=0,
                stock_weekly_change=0,
                is_crash_mode=False,
                relative_strength=0,
                use_200dma_floor=False,
                dma_200=None,
                multiplier=1.0,
                reason="Insufficient data",
            )
        
        # Get SOXX data
        soxx = yf.Ticker("SOXX")
        soxx_hist = soxx.history(period="1y", interval="1d")
        
        if soxx_hist is None or len(soxx_hist) < 200:
            return BetaAnalysis(
                stock_beta=None,
                soxx_weekly_change=0,
                stock_weekly_change=0,
                is_crash_mode=False,
                relative_strength=0,
                use_200dma_floor=False,
                dma_200=None,
                multiplier=1.0,
                reason="SOXX data unavailable",
            )
        
        # Calculate beta (covariance / variance)
        stock_returns = stock_hist['Close'].pct_change().dropna()
        soxx_returns = soxx_hist['Close'].pct_change().dropna()
        
        # Align dates
        common_dates = stock_returns.index.intersection(soxx_returns.index)
        stock_returns = stock_returns.loc[common_dates]
        soxx_returns = soxx_returns.loc[common_dates]
        
        if len(stock_returns) < 50:
            return BetaAnalysis(
                stock_beta=None,
                soxx_weekly_change=0,
                stock_weekly_change=0,
                is_crash_mode=False,
                relative_strength=0,
                use_200dma_floor=False,
                dma_200=None,
                multiplier=1.0,
                reason="Insufficient return data",
            )
        
        covariance = stock_returns.cov(soxx_returns)
        variance = soxx_returns.var()
        beta = covariance / variance if variance > 0 else 1.0
        
        # Calculate weekly changes
        stock_weekly = ((stock_hist['Close'].iloc[-1] - stock_hist['Close'].iloc[-5]) / 
                       stock_hist['Close'].iloc[-5]) * 100
        soxx_weekly = ((soxx_hist['Close'].iloc[-1] - soxx_hist['Close'].iloc[-5]) / 
                      soxx_hist['Close'].iloc[-5]) * 100
        
        # Relative strength
        relative_strength = stock_weekly - soxx_weekly
        
        # Calculate 200 DMA
        dma_200 = stock_hist['Close'].rolling(window=200).mean().iloc[-1]
        
        # Determine crash mode
        is_crash = beta > HIGH_BETA_THRESHOLD and soxx_weekly < SOXX_CRASH_THRESHOLD
        
        # Relative strength exception
        use_floor = is_crash and relative_strength < 2.0  # Not outperforming by >2%
        
        if use_floor:
            multiplier = 0.85  # Also apply multiplier in crash mode
            reason = f"CRASH MODE: Beta {beta:.2f}, SOXX {soxx_weekly:+.1f}%, using 200 DMA floor"
        elif is_crash:
            multiplier = 0.95  # Minor reduction but relative strength is good
            reason = f"High beta ({beta:.2f}) but outperforming SOXX by {relative_strength:+.1f}%"
        else:
            multiplier = 1.0
            reason = f"Beta {beta:.2f} within normal range"
        
        return BetaAnalysis(
            stock_beta=beta,
            soxx_weekly_change=soxx_weekly,
            stock_weekly_change=stock_weekly,
            is_crash_mode=is_crash,
            relative_strength=relative_strength,
            use_200dma_floor=use_floor,
            dma_200=dma_200,
            multiplier=multiplier,
            reason=reason,
        )
        
    except Exception as e:
        logger.error(f"Error analyzing beta for {symbol}: {e}")
        return BetaAnalysis(
            stock_beta=None,
            soxx_weekly_change=0,
            stock_weekly_change=0,
            is_crash_mode=False,
            relative_strength=0,
            use_200dma_floor=False,
            dma_200=None,
            multiplier=1.0,
            reason=f"Error: {str(e)[:50]}",
        )


def analyze_cycle_risk(symbol: str, original_target: float) -> CycleRiskResult:
    """
    Complete cycle risk analysis for a semi equipment stock.
    
    Combines:
    1. WFE Spending analysis (macro)
    2. Inventory analysis (fundamental)
    3. Beta analysis (market)
    """
    symbol = symbol.upper()
    timestamp = datetime.now()
    warnings = []
    
    # Run all analyses
    wfe = get_wfe_analysis(symbol)
    inventory = get_inventory_analysis(symbol)
    beta = get_beta_analysis(symbol)
    
    # Collect warnings
    if wfe.is_bearish:
        warnings.append(f"WFE downcycle: ${wfe.current_estimate:.0f}B estimate")
    if inventory.is_warning:
        warnings.append(f"Inventory cliff: +{inventory.qoq_change_pct:.0f}% QoQ")
    if beta.is_crash_mode:
        warnings.append(f"High-beta crash: {beta.stock_beta:.2f}β, SOXX {beta.soxx_weekly_change:+.1f}%")
    
    # Calculate total multiplier
    total_multiplier = wfe.multiplier * inventory.multiplier * beta.multiplier
    
    # Calculate adjusted target
    adjusted_target = original_target * total_multiplier
    
    # Apply 200 DMA floor if in crash mode
    hard_floor = beta.dma_200 if beta.use_200dma_floor else None
    
    if hard_floor and adjusted_target < hard_floor:
        final_target = hard_floor
        warnings.append(f"Target floored at 200 DMA: ${hard_floor:.2f}")
    elif hard_floor:
        final_target = min(adjusted_target, hard_floor * 1.1)  # Max 10% above 200 DMA in crash
    else:
        final_target = adjusted_target
    
    # Determine risk level
    is_bearish = wfe.is_bearish or inventory.is_warning or beta.is_crash_mode
    
    if beta.is_crash_mode and wfe.is_bearish:
        risk_level = "SEVERE"
    elif beta.is_crash_mode or (wfe.is_bearish and inventory.is_warning):
        risk_level = "HIGH"
    elif wfe.is_bearish or inventory.is_warning:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"
    
    return CycleRiskResult(
        symbol=symbol,
        timestamp=timestamp,
        wfe_analysis=wfe,
        inventory_analysis=inventory,
        beta_analysis=beta,
        total_multiplier=total_multiplier,
        is_bearish_cycle=is_bearish,
        original_target=original_target,
        adjusted_target=adjusted_target,
        hard_floor_200dma=hard_floor,
        final_target=final_target,
        risk_level=risk_level,
        warnings=warnings,
    )


def update_wfe_estimate(estimate: float) -> None:
    """Update the WFE spending estimate (call when new data available)."""
    global WFE_CURRENT_ESTIMATE
    WFE_CURRENT_ESTIMATE = estimate
    logger.info(f"Updated WFE estimate to ${estimate:.0f}B")


def update_product_ramp(symbol: str, description: str | None) -> None:
    """Update product ramp status for a symbol."""
    global PRODUCT_RAMP_ACTIVE
    if description:
        PRODUCT_RAMP_ACTIVE[symbol.upper()] = description
        logger.info(f"Added product ramp for {symbol}: {description}")
    elif symbol.upper() in PRODUCT_RAMP_ACTIVE:
        del PRODUCT_RAMP_ACTIVE[symbol.upper()]
        logger.info(f"Removed product ramp for {symbol}")
