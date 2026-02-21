"""Global Sovereign Quant Scheduler - 24/7 automated workflow."""

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from apscheduler.triggers.cron import CronTrigger

from .adaptive_params import get_param_manager
from .entry_signals import EntrySignalAnalyzer, EntrySignal
from .prediction_journal import get_journal, PredictionType, Outcome
from .market_data import MarketDataFetcher
from .permanent_watchlist import get_permanent_symbols
from .scheduler import DailyUpdateScheduler

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)


class SovereignScheduler:
    """The Global Sovereign Quant automated workflow scheduler."""

    def __init__(self, bot: "InvestmentBot", channel_id: int, scheduler: DailyUpdateScheduler) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self.scheduler = scheduler
        self.entry_analyzer = EntrySignalAnalyzer()
        self.market_data = MarketDataFetcher()
        self.journal = get_journal()

    def schedule_sovereign_tasks(self) -> None:
        """Schedule all sovereign quant tasks."""
        tz = self.scheduler.timezone

        # 4:00 AM - Pre-Market Digestion (disabled weekends)
        self.scheduler.scheduler.add_job(
            self._premarket_digestion,
            CronTrigger(day_of_week="mon-fri", hour=4, minute=0, timezone=tz),
            id="premarket_digestion",
            replace_existing=True,
        )
        logger.info("Scheduled: 4:00 AM Pre-Market Digestion")

        # 9:30 AM - VWAP Integrity Scan
        self.scheduler.scheduler.add_job(
            self._vwap_integrity_scan,
            CronTrigger(day_of_week="mon-fri", hour=10, minute=0, timezone=tz),  # 30 min after open
            id="vwap_integrity_scan",
            replace_existing=True,
        )
        logger.info("Scheduled: 10:00 AM VWAP Integrity Scan")

        # 2:00 PM - The 2 O'Clock Sweep
        self.scheduler.scheduler.add_job(
            self._two_oclock_sweep,
            CronTrigger(day_of_week="mon-fri", hour=14, minute=0, timezone=tz),
            id="two_oclock_sweep",
            replace_existing=True,
        )
        logger.info("Scheduled: 2:00 PM Sweep")

        # 8:00 PM - Recursive Variance Audit
        self.scheduler.scheduler.add_job(
            self._recursive_audit,
            CronTrigger(day_of_week="mon-fri", hour=20, minute=0, timezone=tz),
            id="recursive_audit",
            replace_existing=True,
        )
        logger.info("Scheduled: 8:00 PM Recursive Audit")

    async def _premarket_digestion(self) -> None:
        """4:00 AM - Pre-market analysis and data refresh."""
        logger.info("Running pre-market digestion...")

        await self._send_message(
            f"🌅 **Pre-Market Digestion** - {datetime.now().strftime('%B %d, %Y')}\n"
            "─" * 40
        )

        symbols = get_permanent_symbols()

        # Check for any overnight news/gaps
        summary_lines = ["**Overnight Analysis:**"]

        for symbol in symbols[:10]:  # Limit to prevent rate limiting
            try:
                historical = self.market_data.get_historical_metrics(symbol)
                if historical:
                    change = historical.price_change_7d_percent
                    emoji = "🟢" if change > 0 else "🔴"
                    summary_lines.append(f"{emoji} {symbol}: {change:+.1f}% (7d)")
            except Exception as e:
                logger.error(f"Pre-market error for {symbol}: {e}")

            await asyncio.sleep(0.5)

        await self._send_message("\n".join(summary_lines))

        # Check pending predictions that need outcome updates
        pending = self.journal.get_pending_predictions(older_than_hours=24)
        if pending:
            await self._send_message(
                f"\n⚠️ **{len(pending)} predictions need outcome updates:**\n"
                + "\n".join([f"• {p.symbol} ({p.signal}) from {p.timestamp[:10]}" for p in pending[:5]])
            )

    async def _vwap_integrity_scan(self) -> None:
        """10:00 AM - VWAP Integrity Scan (30 min after open)."""
        logger.info("Running VWAP integrity scan...")

        await self._send_message(
            f"📊 **VWAP Integrity Scan** - {datetime.now().strftime('%I:%M %p')}\n"
            "Only tickers holding VWAP qualify for entry.\n"
            "─" * 40
        )

        symbols = get_permanent_symbols()
        passed = []
        failed = []

        for symbol in symbols:
            try:
                analysis = await self.entry_analyzer.analyze_entry(symbol)

                # Log to journal
                self.journal.log_prediction(
                    symbol=symbol,
                    prediction_type=PredictionType.VWAP_INTEGRITY,
                    signal=analysis.signal.value,
                    confidence=analysis.confidence,
                    reasoning=analysis.summary,
                    conditions_met=[c.name for c in analysis.conditions if c.passed],
                    conditions_failed=[c.name for c in analysis.conditions if not c.passed],
                    entry_price=analysis.entry_price,
                    target_price=analysis.target_price,
                    stop_loss=analysis.stop_loss,
                )

                # Check VWAP condition
                vwap_cond = next((c for c in analysis.conditions if "VWAP" in c.name), None)
                if vwap_cond and vwap_cond.passed:
                    passed.append((symbol, analysis))
                else:
                    failed.append((symbol, analysis))

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"VWAP scan error for {symbol}: {e}")

        # Report passed
        if passed:
            msg = "✅ **Holding VWAP (Potential Entries):**\n"
            for symbol, analysis in passed:
                msg += f"• {symbol}: {analysis.signal.value} ({analysis.confidence}%)\n"
            await self._send_message(msg)

        # Report failed
        if failed:
            msg = "❌ **Below VWAP (No Entry):**\n"
            for symbol, analysis in failed:
                msg += f"• {symbol}: Avoid - below VWAP\n"
            await self._send_message(msg)

        # Highlight strong buys
        strong = [s for s, a in passed if a.signal == EntrySignal.STRONG_BUY]
        if strong:
            await self._send_message(f"🚨 **STRONG BUY SIGNALS:** {', '.join(strong)}")

    async def _two_oclock_sweep(self) -> None:
        """2:00 PM - The 2 O'Clock Sweep."""
        logger.info("Running 2 o'clock sweep...")

        await self._send_message(
            f"🔍 **2 O'Clock Sweep** - {datetime.now().strftime('%I:%M %p')}\n"
            "Analyzing afternoon momentum for EOD positioning.\n"
            "─" * 40
        )

        symbols = get_permanent_symbols()
        bullish = []
        bearish = []
        neutral = []

        for symbol in symbols:
            try:
                intraday = self.market_data.get_intraday_data(symbol)
                if not intraday:
                    continue

                # Determine afternoon bias
                if intraday.change_percent > 1 and intraday.current_price > intraday.vwap:
                    bullish.append((symbol, intraday.change_percent))
                elif intraday.change_percent < -1 or intraday.current_price < intraday.vwap:
                    bearish.append((symbol, intraday.change_percent))
                else:
                    neutral.append((symbol, intraday.change_percent))

                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"2PM sweep error for {symbol}: {e}")

        # Report
        if bullish:
            bullish.sort(key=lambda x: x[1], reverse=True)
            msg = "📈 **Bullish into Close:**\n"
            for symbol, change in bullish[:5]:
                msg += f"• {symbol}: +{change:.1f}%\n"
            await self._send_message(msg)

        if bearish:
            bearish.sort(key=lambda x: x[1])
            msg = "📉 **Bearish into Close:**\n"
            for symbol, change in bearish[:5]:
                msg += f"• {symbol}: {change:.1f}%\n"
            await self._send_message(msg)

        await self._send_message(
            f"\n**Summary:** {len(bullish)} bullish, {len(bearish)} bearish, {len(neutral)} neutral"
        )

    async def _recursive_audit(self) -> None:
        """8:00 PM - Recursive Variance Audit."""
        logger.info("Running recursive variance audit...")

        await self._send_message(
            f"🔄 **Recursive Variance Audit** - {datetime.now().strftime('%B %d, %Y')}\n"
            "Analyzing prediction accuracy and adjusting parameters.\n"
            "─" * 40
        )

        # Update pending predictions with end-of-day prices
        pending = self.journal.get_pending_predictions(older_than_hours=8)

        updates_made = 0
        for pred in pending[:10]:  # Limit to prevent rate limiting
            try:
                intraday = self.market_data.get_intraday_data(pred.symbol)
                if intraday:
                    # Determine if prediction was correct
                    if pred.signal in ["STRONG_BUY", "BUY", "strong_buy", "buy"]:
                        # For buy signals, correct if price went up
                        if pred.entry_price:
                            pnl = ((intraday.current_price - pred.entry_price) / pred.entry_price) * 100
                            if pnl > 1:
                                outcome = Outcome.CORRECT
                            elif pnl < -2:
                                outcome = Outcome.INCORRECT
                            else:
                                outcome = Outcome.PARTIAL
                        else:
                            outcome = Outcome.PARTIAL
                    else:
                        # For avoid signals, correct if price went down
                        outcome = Outcome.CORRECT if intraday.change_percent < 0 else Outcome.PARTIAL

                    self.journal.update_outcome(
                        pred.id,
                        outcome,
                        intraday.current_price,
                        f"EOD auto-update: {intraday.change_percent:+.1f}%"
                    )
                    updates_made += 1

                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Audit update error for {pred.symbol}: {e}")

        if updates_made > 0:
            await self._send_message(f"✅ Updated {updates_made} prediction outcomes")

        # Run variance analysis
        audit = self.journal.run_variance_analysis()
        await self._send_message(self.journal.format_audit_discord(audit))

        # Generate improvement suggestions
        param_manager = get_param_manager()
        suggestions = param_manager.generate_suggestions_from_audit(
            accuracy=audit.accuracy_rate,
            common_failures=audit.common_failures,
            weight_adjustments=audit.weight_adjustments,
        )

        if suggestions:
            await self._send_message(
                f"\n🧠 **Learning System Generated {len(suggestions)} Suggestions**\n"
                f"Use `!suggestions` to view and `!approveall` to apply."
            )
            # Show brief summary
            for s in suggestions[:3]:
                await self._send_message(
                    f"• {s.parameter}: {s.current_value} → {s.suggested_value}\n"
                    f"  Reason: {s.reason}"
                )
            if len(suggestions) > 3:
                await self._send_message(f"... and {len(suggestions) - 3} more. Use `!suggestions` to see all.")

        # Show stats
        stats = self.journal.get_stats(days=7)
        await self._send_message(
            f"\n**7-Day Performance:**\n"
            f"• Accuracy: {stats['accuracy']:.1f}%\n"
            f"• Total P&L: {stats['total_pnl_percent']:+.1f}%\n"
            f"• Predictions: {stats['total_predictions']}"
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
