"""Entry Signal System - Identifies optimal entry points with high confidence."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import TYPE_CHECKING

import discord

from .market_data import MarketDataFetcher, IntradayData, HistoricalMetrics
from .sec_filings import SECFilingScanner
from .permanent_watchlist import get_permanent_symbols

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


class EntrySignal(Enum):
    """Entry signal types."""
    STRONG_BUY = "strong_buy"      # All conditions met - high confidence
    BUY = "buy"                     # Most conditions met - good entry
    WAIT = "wait"                   # Some conditions met - wait for better setup
    NO_ENTRY = "no_entry"           # Conditions not favorable


@dataclass
class EntryCondition:
    """Individual entry condition result."""
    name: str
    passed: bool
    weight: int  # 1-10, higher = more important
    reason: str


@dataclass 
class EntryAnalysis:
    """Complete entry analysis for a symbol."""
    symbol: str
    timestamp: datetime
    signal: EntrySignal
    confidence: int  # 0-100%
    conditions: list[EntryCondition]
    entry_price: float | None
    target_price: float | None
    stop_loss: float | None
    risk_reward_ratio: float | None
    summary: str
    recommendation: str

    def to_discord_message(self) -> str:
        """Format as Discord message."""
        if self.signal == EntrySignal.STRONG_BUY:
            emoji = "🟢🟢🟢"
            signal_text = "STRONG BUY"
        elif self.signal == EntrySignal.BUY:
            emoji = "🟢"
            signal_text = "BUY"
        elif self.signal == EntrySignal.WAIT:
            emoji = "🟡"
            signal_text = "WAIT"
        else:
            emoji = "🔴"
            signal_text = "NO ENTRY"

        lines = [
            f"{emoji} **ENTRY SIGNAL: {self.symbol}** - {signal_text}",
            f"**Confidence:** {self.confidence}%",
            "",
        ]

        if self.entry_price:
            lines.append(f"**Entry Price:** ${self.entry_price:.2f}")
        if self.target_price:
            lines.append(f"**Target:** ${self.target_price:.2f}")
        if self.stop_loss:
            lines.append(f"**Stop Loss:** ${self.stop_loss:.2f}")
        if self.risk_reward_ratio:
            lines.append(f"**Risk/Reward:** 1:{self.risk_reward_ratio:.1f}")

        # Show conditions
        lines.append("")
        lines.append("**Conditions:**")
        for cond in self.conditions:
            icon = "✅" if cond.passed else "❌"
            lines.append(f"{icon} {cond.name}: {cond.reason}")

        lines.append("")
        lines.append(f"**Summary:** {self.summary}")
        lines.append(f"**Action:** {self.recommendation}")

        return "\n".join(lines)


class EntrySignalAnalyzer:
    """Analyzes stocks for optimal entry points."""

    def __init__(self) -> None:
        self.market_data = MarketDataFetcher()
        self.sec_scanner = SECFilingScanner()

    async def analyze_entry(self, symbol: str) -> EntryAnalysis:
        """Analyze a symbol for entry opportunity."""
        symbol = symbol.upper()
        conditions: list[EntryCondition] = []

        # Fetch data
        loop = asyncio.get_event_loop()
        intraday = await loop.run_in_executor(_executor, self.market_data.get_intraday_data, symbol)
        historical = await loop.run_in_executor(_executor, self.market_data.get_historical_metrics, symbol)
        first_hour = await loop.run_in_executor(_executor, self.market_data.get_first_hour_data, symbol)
        dilution = await self.sec_scanner.check_dilution_risk(symbol)

        if not intraday or not historical:
            return EntryAnalysis(
                symbol=symbol, timestamp=datetime.now(), signal=EntrySignal.NO_ENTRY,
                confidence=0, conditions=[], entry_price=None, target_price=None,
                stop_loss=None, risk_reward_ratio=None,
                summary="Insufficient data", recommendation="Cannot analyze - no market data"
            )

        # === CONDITION 1: Price above VWAP (Weight: 10) ===
        price_vs_vwap = intraday.current_price - intraday.vwap
        vwap_pct = (price_vs_vwap / intraday.vwap * 100) if intraday.vwap else 0
        vwap_passed = vwap_pct > 0.2  # At least 0.2% above VWAP

        conditions.append(EntryCondition(
            name="VWAP Position",
            passed=vwap_passed,
            weight=10,
            reason=f"{'Above' if vwap_passed else 'Below'} VWAP by {abs(vwap_pct):.1f}%"
        ))

        # === CONDITION 2: Volume confirmation (Weight: 9) ===
        vol_ratio = intraday.volume / intraday.avg_volume_10d if intraday.avg_volume_10d else 0
        volume_passed = vol_ratio >= 0.8  # At least 80% of average volume

        conditions.append(EntryCondition(
            name="Volume Confirmation",
            passed=volume_passed,
            weight=9,
            reason=f"Volume at {vol_ratio*100:.0f}% of 10-day average"
        ))

        # === CONDITION 3: Not overextended (Weight: 8) ===
        not_overextended = historical.price_change_7d_percent < 12  # Less than 12% in 7 days

        conditions.append(EntryCondition(
            name="Not Overextended",
            passed=not_overextended,
            weight=8,
            reason=f"7-day change: {historical.price_change_7d_percent:+.1f}%"
        ))

        # === CONDITION 4: No dilution risk (Weight: 8) ===
        no_dilution = dilution is None or dilution.risk_level == "low"

        conditions.append(EntryCondition(
            name="No Dilution Risk",
            passed=no_dilution,
            weight=8,
            reason="No recent S-3/offering" if no_dilution else f"Active {dilution.filing_type} filing"
        ))

        # === CONDITION 5: Morning hype settled (Weight: 7) ===
        now = datetime.now()
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        minutes_since_open = (now - market_open).total_seconds() / 60
        morning_settled = minutes_since_open > 60 or minutes_since_open < 0  # After 10:30 AM or pre-market

        conditions.append(EntryCondition(
            name="Morning Settled",
            passed=morning_settled,
            weight=7,
            reason="Past 10:30 AM rule" if morning_settled else f"Only {minutes_since_open:.0f}min since open"
        ))

        # === CONDITION 6: Above first hour support (Weight: 7) ===
        if first_hour:
            above_support = intraday.current_price > first_hour["first_hour_low"]
            conditions.append(EntryCondition(
                name="Above Support",
                passed=above_support,
                weight=7,
                reason=f"Price {'above' if above_support else 'below'} first-hour low ${first_hour['first_hour_low']:.2f}"
            ))
        else:
            above_support = True
            conditions.append(EntryCondition(
                name="Above Support",
                passed=True,
                weight=7,
                reason="First hour data unavailable"
            ))

        # === CONDITION 7: Positive momentum (Weight: 6) ===
        positive_momentum = intraday.change_percent > 0

        conditions.append(EntryCondition(
            name="Positive Momentum",
            passed=positive_momentum,
            weight=6,
            reason=f"Today: {intraday.change_percent:+.1f}%"
        ))

        # === CONDITION 8: Near support (good R/R) (Weight: 6) ===
        distance_to_support = ((intraday.current_price - historical.support_level) / intraday.current_price * 100)
        near_support = distance_to_support < 5  # Within 5% of support

        conditions.append(EntryCondition(
            name="Near Support",
            passed=near_support,
            weight=6,
            reason=f"{distance_to_support:.1f}% above support (${historical.support_level:.2f})"
        ))

        # === CONDITION 9: Volume increasing (not exhausted) (Weight: 5) ===
        vol_15_ratio = intraday.volume_15min / intraday.avg_volume_15min_10d if intraday.avg_volume_15min_10d else 1
        volume_healthy = vol_15_ratio >= 0.6  # Recent volume not dying

        conditions.append(EntryCondition(
            name="Volume Healthy",
            passed=volume_healthy,
            weight=5,
            reason=f"Last 15min volume at {vol_15_ratio*100:.0f}% of average"
        ))

        # === CONDITION 10: Low volatility day (Weight: 4) ===
        intraday_range = ((intraday.high - intraday.low) / intraday.current_price * 100)
        low_volatility = intraday_range < 5  # Less than 5% range today

        conditions.append(EntryCondition(
            name="Controlled Volatility",
            passed=low_volatility,
            weight=4,
            reason=f"Intraday range: {intraday_range:.1f}%"
        ))

        # Calculate confidence score
        total_weight = sum(c.weight for c in conditions)
        passed_weight = sum(c.weight for c in conditions if c.passed)
        confidence = int((passed_weight / total_weight) * 100)

        # Determine signal
        critical_conditions = [vwap_passed, volume_passed, not_overextended, no_dilution]
        critical_passed = sum(critical_conditions)

        if confidence >= 85 and critical_passed == 4:
            signal = EntrySignal.STRONG_BUY
        elif confidence >= 70 and critical_passed >= 3:
            signal = EntrySignal.BUY
        elif confidence >= 50:
            signal = EntrySignal.WAIT
        else:
            signal = EntrySignal.NO_ENTRY

        # Calculate entry, target, stop loss
        entry_price = intraday.current_price
        stop_loss = historical.support_level * 0.98  # 2% below support
        target_price = entry_price + (entry_price - stop_loss) * 2  # 2:1 R/R minimum

        risk = entry_price - stop_loss
        reward = target_price - entry_price
        risk_reward = reward / risk if risk > 0 else 0

        # Generate summary and recommendation
        if signal == EntrySignal.STRONG_BUY:
            summary = "All major conditions met. High-confidence entry setup."
            recommendation = f"Enter at ${entry_price:.2f} with stop at ${stop_loss:.2f}. Target ${target_price:.2f}."
        elif signal == EntrySignal.BUY:
            summary = "Most conditions favorable. Good entry opportunity."
            failed = [c.name for c in conditions if not c.passed][:2]
            recommendation = f"Consider entry. Watch: {', '.join(failed)}."
        elif signal == EntrySignal.WAIT:
            summary = "Mixed signals. Wait for better setup."
            failed = [c.name for c in conditions if not c.passed and c.weight >= 7]
            recommendation = f"Wait for: {', '.join(failed)}."
        else:
            summary = "Conditions not favorable. High risk of pullback."
            recommendation = "Avoid entry. Wait for conditions to improve."

        return EntryAnalysis(
            symbol=symbol,
            timestamp=datetime.now(),
            signal=signal,
            confidence=confidence,
            conditions=conditions,
            entry_price=entry_price if signal in [EntrySignal.STRONG_BUY, EntrySignal.BUY] else None,
            target_price=target_price if signal in [EntrySignal.STRONG_BUY, EntrySignal.BUY] else None,
            stop_loss=stop_loss if signal in [EntrySignal.STRONG_BUY, EntrySignal.BUY] else None,
            risk_reward_ratio=risk_reward if signal in [EntrySignal.STRONG_BUY, EntrySignal.BUY] else None,
            summary=summary,
            recommendation=recommendation,
        )

    async def scan_for_entries(self, symbols: list[str] | None = None) -> list[EntryAnalysis]:
        """Scan multiple symbols for entry opportunities."""
        if symbols is None:
            symbols = get_permanent_symbols()

        results = []
        for symbol in symbols:
            try:
                analysis = await self.analyze_entry(symbol)
                results.append(analysis)
                await asyncio.sleep(0.5)  # Rate limiting
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")

        # Sort by confidence (highest first)
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results


class EntrySignalMonitor:
    """Monitors for entry signals and alerts."""

    def __init__(self, bot: "InvestmentBot", channel_id: int) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self.analyzer = EntrySignalAnalyzer()
        self._last_signals: dict[str, EntrySignal] = {}

    async def scan_and_alert(self) -> None:
        """Scan watchlist and alert on good entries."""
        logger.info("Scanning for entry signals...")

        results = await self.analyzer.scan_for_entries()

        # Filter for actionable signals
        actionable = [r for r in results if r.signal in [EntrySignal.STRONG_BUY, EntrySignal.BUY]]

        if actionable:
            header = f"🎯 **Entry Signal Scan** - {datetime.now().strftime('%I:%M %p')}\n"
            header += f"Found {len(actionable)} potential entries\n" + "─" * 40
            await self._send_message(header)

            for analysis in actionable:
                # Only alert if signal changed or is STRONG_BUY
                prev_signal = self._last_signals.get(analysis.symbol)
                if analysis.signal == EntrySignal.STRONG_BUY or prev_signal != analysis.signal:
                    await self._send_message(analysis.to_discord_message())
                    self._last_signals[analysis.symbol] = analysis.signal
                    await asyncio.sleep(1)
        else:
            # Optionally send "no entries found" message
            logger.info("No actionable entry signals found")

    async def _send_message(self, content: str) -> None:
        channel = self.bot.get_channel(self.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            if len(content) > 2000:
                for i in range(0, len(content), 1990):
                    await channel.send(content[i:i+1990])
            else:
                await channel.send(content)


async def analyze_entry(symbol: str) -> EntryAnalysis:
    """Convenience function to analyze a single symbol."""
    analyzer = EntrySignalAnalyzer()
    return await analyzer.analyze_entry(symbol)
