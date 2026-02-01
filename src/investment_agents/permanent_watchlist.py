"""Permanent watchlist with automatic risk audits."""

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from apscheduler.triggers.cron import CronTrigger

from .risk_audit import RiskAuditor, RiskAuditResult
from .scheduler import DailyUpdateScheduler

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)

PERMANENT_WATCHLIST = ["LRCX", "KLAC", "ASML", "ONDS"]


class PermanentWatchlistMonitor:
    def __init__(self, bot: "InvestmentBot", channel_id: int, scheduler: DailyUpdateScheduler) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self.scheduler = scheduler
        self.auditor = RiskAuditor()
        self.symbols = list(PERMANENT_WATCHLIST)

    def schedule_all_auto_audits(self) -> None:
        """Schedule all automatic audits."""
        tz = self.scheduler.timezone

        # 1. Friday afternoon audit (before weekend)
        self.scheduler.scheduler.add_job(
            self._run_scheduled_audit,
            CronTrigger(day_of_week=4, hour=15, minute=0, timezone=tz),
            id="friday_risk_audit",
            replace_existing=True,
            args=["Weekly Friday Risk Audit"],
        )
        logger.info("Scheduled: Friday 3:00 PM risk audit")

        # 2. Market open audit (9:35 AM, 5 min after open to let prices settle)
        self.scheduler.scheduler.add_job(
            self._run_scheduled_audit,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=35, timezone=tz),
            id="market_open_audit",
            replace_existing=True,
            args=["Market Open Audit"],
        )
        logger.info("Scheduled: Market open audit (9:35 AM Mon-Fri)")

        # 3. Mid-day check (12:00 PM)
        self.scheduler.scheduler.add_job(
            self._run_scheduled_audit,
            CronTrigger(day_of_week="mon-fri", hour=12, minute=0, timezone=tz),
            id="midday_audit",
            replace_existing=True,
            args=["Mid-Day Check"],
        )
        logger.info("Scheduled: Mid-day audit (12:00 PM Mon-Fri)")

        # 4. Pre-close audit (3:30 PM, 30 min before close)
        self.scheduler.scheduler.add_job(
            self._run_scheduled_audit,
            CronTrigger(day_of_week="mon-fri", hour=15, minute=30, timezone=tz),
            id="preclose_audit",
            replace_existing=True,
            args=["Pre-Close Audit"],
        )
        logger.info("Scheduled: Pre-close audit (3:30 PM Mon-Fri)")

    def schedule_friday_audits(self) -> None:
        """Legacy method - now schedules all audits."""
        self.schedule_all_auto_audits()

    async def _run_scheduled_audit(self, reason: str = "Scheduled Risk Audit") -> None:
        await self.run_full_audit(reason=reason)

    async def _run_scheduled_audit(self) -> None:
        await self.run_full_audit(reason="Weekly Friday Risk Audit")

    async def run_full_audit(self, reason: str = "Risk Audit") -> None:
        logger.info(f"Running {reason} for {len(self.symbols)} symbols")

        header = f"📊 **{reason}** - {datetime.now().strftime('%B %d, %Y %I:%M %p')}\n"
        header += f"Symbols: {', '.join(self.symbols)}\n" + "─" * 40
        await self._send_message(header)

        for symbol in self.symbols:
            try:
                result = await self.auditor.run_audit(symbol)
                await self._send_message(result.to_discord_message())
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error auditing {symbol}: {e}")
                await self._send_message(f"❌ Error auditing {symbol}: {str(e)[:100]}")

    async def run_single_audit(self, symbol: str) -> RiskAuditResult:
        return await self.auditor.run_audit(symbol)

    async def catalyst_audit(self, symbol: str, catalyst: str) -> None:
        header = f"⚡ **Pre-Catalyst Risk Audit: {symbol}**\nCatalyst: {catalyst}\n" + "─" * 40
        await self._send_message(header)
        try:
            result = await self.auditor.run_audit(symbol)
            await self._send_message(result.to_discord_message())
        except Exception as e:
            await self._send_message(f"❌ Error: {str(e)[:200]}")

    async def _send_message(self, content: str) -> None:
        channel = self.bot.get_channel(self.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            if len(content) > 2000:
                for i in range(0, len(content), 1990):
                    await channel.send(content[i:i+1990])
            else:
                await channel.send(content)


def get_permanent_symbols() -> list[str]:
    return list(PERMANENT_WATCHLIST)
