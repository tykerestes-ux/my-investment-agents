"""Global Sovereign Quant Scheduler - 24/7 automated analysis workflow."""

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from apscheduler.triggers.cron import CronTrigger

from .entry_signals import EntrySignalAnalyzer, EntrySignal
from .market_data import MarketDataFetcher
from .permanent_watchlist import get_permanent_symbols
from .prediction_journal import PredictionJournal, PredictionType, Outcome, get_journal
from .risk_audit import RiskAuditor
from .scheduler import DailyUpdateScheduler

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)


class QuantScheduler:
    """Manages the 24/7 quant workflow with 4 daily analysis phases."""

    def __init__(
        self,
        bot: "InvestmentBot",
        channel_id: int,
        scheduler: DailyUpdateScheduler,
    ) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self.scheduler = scheduler
        self.journal = get_journal()
        self.auditor = RiskAuditor()
        self.entry_analyzer = EntrySignalAnalyzer()
        self.market_data = MarketDataFetcher()

    def schedule_all_tasks(self) -> None:
        """Schedule all 4 daily quant tasks + existing audits."""
        tz = self.scheduler.timezone

        # 1. 4:00 AM - Pre-Market Digestion
        self.scheduler.scheduler.add_job(
            self._premarket_digestion,
            CronTrigger(day_of_week="mon-fri", hour=4, minute=0, timezone=tz),
            id="premarket_digestion",
            replace_existing=True,
        )
        logger.info("Scheduled: 4:00 AM Pre-Market Digestion")

        # 2. 9:30 AM - VWAP Integrity Scan (actually 10:00 to let VWAP establish)
        self.scheduler.scheduler.add_job(
            self._vwap_integrity_scan,
            CronTrigger(day_of_week="mon-fri", hour=10, minute=0, timezone=tz),
            id="vwap_integrity_scan",
            replace_existing=True,
        )
        logger.info("Scheduled: 10:00 AM VWAP Integrity Scan")

        # 3. 2:00 PM - The 2 O'Clock Sweep
        self.scheduler.scheduler.add_job(
            self._two_oclock_sweep,
            CronTrigger(day_of_week="mon-fri", hour=14, minute=0, timezone=tz),
            id="two_oclock_sweep",
            replace_existing=True,
        )
        logger.info("Scheduled: 2:00 PM Two O'Clock Sweep")

        # 4. 8:00 PM - Recursive Audit (Variance Analysis)
        self.scheduler.scheduler.add_job(
            self._recursive_audit,
            CronTrigger(day_of_week="mon-fri", hour=20, minute=0, timezone=tz),
            id="recursive_audit",
            replace_existing=True,
        )
        logger.info("Scheduled: 8:00 PM Recursive Audit")

        # 5. 4:00 PM - Update pending prediction outcomes
        self.scheduler.scheduler.add_job(
            self._update_prediction_outcomes,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=5, timezone=tz),
            id="outcome_update",
            replace_existing=True,
        )
        logger.info("Scheduled: 4:05 PM Outcome Updates")

    async def _premarket_digestion(self) -> None:
        """4:00 AM - Pre-market analysis and data refresh."""
        logger.info("Running Pre-Market Digestion...")

        header = (
            "☀️ **PRE-MARKET DIGESTION** - "
            f"{datetime.now().strftime('%B %d, %Y')}\n"
            "─" * 40
        )
        await self._send_message(header)

        symbols = get_permanent_symbols()
        analysis_lines = ["**Watchlist Status:**"]

        for symbol in symbols[:10]:  # Limit to prevent rate limiting
            try:
                # Get yesterday's close vs current pre-market if available
                historical = self.market_data.get_historical_metrics(symbol)
                if historical:
                    analysis_lines.append(
                        f"• **{symbol}**: Support ${historical.support_level:.2f} | "
                        f"Resistance ${historical.resistance_level:.2f} | "
                        f"7d: {historical.price_change_7d_percent:+.1f}%"
                    )
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Pre-market error for {symbol}: {e}")

        analysis_lines.append("")
        analysis_lines.append("📋 *Full analysis runs at market open (10:00 AM)*")

        await self._send_message("\n".join(analysis_lines))

    async def _vwap_integrity_scan(self) -> None:
        """10:00 AM - Scan for tickers holding VWAP after first 30 minutes."""
        logger.info("Running VWAP Integrity Scan...")

        header = (
            "📊 **VWAP INTEGRITY SCAN** - "
            f"{datetime.now().strftime('%I:%M %p')}\n"
            "Only showing tickers holding Daily VWAP\n"
            "─" * 40
        )
        await self._send_message(header)

        symbols = get_permanent_symbols()
        holding_vwap = []
        below_vwap = []

        for symbol in symbols:
            try:
                intraday = self.market_data.get_intraday_data(symbol)
                if not intraday:
                    continue

                vwap_diff = ((intraday.current_price - intraday.vwap) / intraday.vwap * 100)

                if vwap_diff > 0.2:  # At least 0.2% above VWAP
                    holding_vwap.append({
                        "symbol": symbol,
                        "price": intraday.current_price,
                        "vwap": intraday.vwap,
                        "diff": vwap_diff,
                        "change": intraday.change_percent,
                    })
                else:
                    below_vwap.append({
                        "symbol": symbol,
                        "diff": vwap_diff,
                    })

                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"VWAP scan error for {symbol}: {e}")

        # Report findings
        if holding_vwap:
            lines = ["🟢 **HOLDING VWAP (Potential Entries):**"]
            for item in sorted(holding_vwap, key=lambda x: x["diff"], reverse=True):
                lines.append(
                    f"• **{item['symbol']}** ${item['price']:.2f} | "
                    f"+{item['diff']:.1f}% above VWAP | Today: {item['change']:+.1f}%"
                )

                # Log as potential entry signal
                self.journal.log_prediction(
                    symbol=item["symbol"],
                    prediction_type=PredictionType.VWAP_INTEGRITY,
                    signal="VWAP_HOLD",
                    confidence=min(70 + int(item["diff"] * 5), 95),
                    reasoning=f"Holding VWAP by {item['diff']:.1f}% at market open scan",
                    conditions_met=["VWAP Support", "Morning Stability"],
                    conditions_failed=[],
                    entry_price=item["price"],
                )

            await self._send_message("\n".join(lines))
        else:
            await self._send_message("⚠️ No tickers currently holding VWAP. Wait for better setups.")

        if below_vwap:
            warn_lines = ["\n🔴 **Below VWAP (Avoid):**"]
            for item in below_vwap[:5]:
                warn_lines.append(f"• {item['symbol']}: {item['diff']:+.1f}% from VWAP")
            await self._send_message("\n".join(warn_lines))

    async def _two_oclock_sweep(self) -> None:
        """2:00 PM - Afternoon momentum check and entry scan."""
        logger.info("Running 2 O'Clock Sweep...")

        header = (
            "🔔 **2 O'CLOCK SWEEP** - "
            f"{datetime.now().strftime('%I:%M %p')}\n"
            "Scanning for afternoon momentum plays\n"
            "─" * 40
        )
        await self._send_message(header)

        # Run full entry analysis on watchlist
        symbols = get_permanent_symbols()
        strong_signals = []
        buy_signals = []

        for symbol in symbols:
            try:
                analysis = await self.entry_analyzer.analyze_entry(symbol)

                if analysis.signal == EntrySignal.STRONG_BUY:
                    strong_signals.append(analysis)
                    # Log prediction
                    self.journal.log_prediction(
                        symbol=symbol,
                        prediction_type=PredictionType.ENTRY_SIGNAL,
                        signal="STRONG_BUY",
                        confidence=analysis.confidence,
                        reasoning=analysis.summary,
                        conditions_met=[c.name for c in analysis.conditions if c.passed],
                        conditions_failed=[c.name for c in analysis.conditions if not c.passed],
                        entry_price=analysis.entry_price,
                        target_price=analysis.target_price,
                        stop_loss=analysis.stop_loss,
                    )
                elif analysis.signal == EntrySignal.BUY:
                    buy_signals.append(analysis)
                    self.journal.log_prediction(
                        symbol=symbol,
                        prediction_type=PredictionType.ENTRY_SIGNAL,
                        signal="BUY",
                        confidence=analysis.confidence,
                        reasoning=analysis.summary,
                        conditions_met=[c.name for c in analysis.conditions if c.passed],
                        conditions_failed=[c.name for c in analysis.conditions if not c.passed],
                        entry_price=analysis.entry_price,
                        target_price=analysis.target_price,
                        stop_loss=analysis.stop_loss,
                    )

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"2PM sweep error for {symbol}: {e}")

        # Report findings
        if strong_signals:
            await self._send_message("🟢🟢🟢 **STRONG BUY SIGNALS:**")
            for sig in strong_signals:
                await self._send_message(sig.to_discord_message())

        if buy_signals:
            await self._send_message("🟢 **BUY SIGNALS:**")
            for sig in buy_signals:
                await self._send_message(sig.to_discord_message())

        if not strong_signals and not buy_signals:
            await self._send_message(
                "📋 No actionable signals at this time.\n"
                "All positions showing WAIT or NO_ENTRY."
            )

    async def _recursive_audit(self) -> None:
        """8:00 PM - Run variance analysis and self-improvement audit."""
        logger.info("Running Recursive Audit (Variance Analysis)...")

        header = (
            "🔍 **RECURSIVE AUDIT** - "
            f"{datetime.now().strftime('%B %d, %Y')}\n"
            "Daily Variance Analysis & Self-Improvement\n"
            "─" * 40
        )
        await self._send_message(header)

        # Run variance analysis
        audit = self.journal.run_variance_analysis()

        # Send audit report
        await self._send_message(self.journal.format_audit_discord(audit))

        # If weight adjustments recommended, report them
        if audit.weight_adjustments:
            adj_lines = ["\n**📐 Suggested Weight Adjustments:**"]
            for condition, change in sorted(audit.weight_adjustments.items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
                direction = "↑" if change > 0 else "↓"
                adj_lines.append(f"• {condition}: {direction} {abs(change):.1f}%")
            await self._send_message("\n".join(adj_lines))

        # Show recent prediction performance
        stats = self.journal.get_stats(days=7)
        stats_msg = (
            f"\n**📈 7-Day Performance:**\n"
            f"• Total Predictions: {stats['total_predictions']}\n"
            f"• Resolved: {stats['resolved']} (Pending: {stats['pending']})\n"
            f"• Accuracy: {stats['accuracy']:.1f}%\n"
            f"• Net P&L: {stats['total_pnl_percent']:+.1f}%"
        )
        await self._send_message(stats_msg)

    async def _update_prediction_outcomes(self) -> None:
        """4:05 PM - Update outcomes for pending predictions."""
        logger.info("Updating prediction outcomes...")

        pending = self.journal.get_pending_predictions(older_than_hours=6)

        if not pending:
            logger.info("No pending predictions to update")
            return

        updated = 0
        for pred in pending[:20]:  # Limit to prevent rate limiting
            try:
                # Get current price
                intraday = self.market_data.get_intraday_data(pred.symbol)
                if not intraday:
                    continue

                current_price = intraday.current_price

                # Determine outcome based on signal type
                if pred.signal in ["STRONG_BUY", "BUY", "VWAP_HOLD"]:
                    # For buy signals, check if price went up from entry
                    if pred.entry_price:
                        pnl_pct = ((current_price - pred.entry_price) / pred.entry_price) * 100

                        if pnl_pct >= 1.0:  # 1%+ gain = correct
                            outcome = Outcome.CORRECT
                        elif pnl_pct <= -2.0:  # 2%+ loss = incorrect
                            outcome = Outcome.INCORRECT
                        elif pnl_pct > -2.0 and pnl_pct < 1.0:
                            outcome = Outcome.PARTIAL
                        else:
                            continue  # Still pending

                        self.journal.update_outcome(
                            pred.id,
                            outcome,
                            current_price,
                            f"Auto-updated at close. P&L: {pnl_pct:+.1f}%"
                        )
                        updated += 1

                elif pred.signal in ["AVOID", "HYPE_WARNING"]:
                    # For avoid signals, correct if price went down
                    if pred.entry_price:
                        pnl_pct = ((current_price - pred.entry_price) / pred.entry_price) * 100

                        if pnl_pct <= -1.0:  # Price dropped = we were right to avoid
                            outcome = Outcome.CORRECT
                        elif pnl_pct >= 2.0:  # Price rose = we missed opportunity
                            outcome = Outcome.INCORRECT
                        else:
                            outcome = Outcome.PARTIAL

                        self.journal.update_outcome(
                            pred.id,
                            outcome,
                            current_price,
                            f"Auto-updated. Price change: {pnl_pct:+.1f}%"
                        )
                        updated += 1

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error updating outcome for {pred.id}: {e}")

        if updated > 0:
            await self._send_message(
                f"📋 Updated {updated} prediction outcomes. "
                f"Run `!journal` to see results."
            )

    async def _send_message(self, content: str) -> None:
        """Send message to Discord channel."""
        channel = self.bot.get_channel(self.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            if len(content) > 2000:
                for i in range(0, len(content), 1990):
                    await channel.send(content[i:i+1990])
            else:
                await channel.send(content)
