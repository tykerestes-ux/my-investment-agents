"""Main entry point for the Discord investment bot."""

import asyncio
import logging
import sys
from pathlib import Path

import discord

from .commands import handle_watchlist_messages, setup_commands
from .config import get_settings, setup_logging
from .discord_client import InvestmentBot
from .permanent_watchlist import PermanentWatchlistMonitor, get_permanent_symbols
from .risk_commands import setup_risk_commands
from .scheduler import DailyUpdateScheduler
from .sovereign_scheduler import SovereignScheduler
from .updates import DailyUpdateGenerator
from .watchlist import WatchlistManager

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info("Starting Investment Agents Bot...")

    if not settings.discord_bot_token:
        logger.error("DISCORD_BOT_TOKEN not configured. Check your .env file.")
        sys.exit(1)

    if not settings.discord_channel_id:
        logger.error("DISCORD_CHANNEL_ID not configured. Check your .env file.")
        sys.exit(1)

    bot = InvestmentBot(command_prefix="!", default_channel_id=settings.discord_channel_id)
    watchlist = WatchlistManager(Path("data/watchlist.json"))
    scheduler = DailyUpdateScheduler(timezone=settings.timezone)

    update_generator = DailyUpdateGenerator(
        bot=bot, watchlist_manager=watchlist, channel_id=settings.discord_channel_id,
    )

    permanent_monitor = PermanentWatchlistMonitor(
        bot=bot, channel_id=settings.discord_channel_id, scheduler=scheduler,
    )

    sovereign_scheduler = SovereignScheduler(
        bot=bot, channel_id=settings.discord_channel_id, scheduler=scheduler,
    )

    @bot.event
    async def on_ready() -> None:
        logger.info(f"Bot is ready! Logged in as {bot.user}")

        await setup_commands(bot, watchlist)
        await setup_risk_commands(bot, permanent_monitor)

        scheduler.add_daily_update(
            callback=update_generator.send_daily_update,
            hour=settings.daily_update_hour,
            minute=settings.daily_update_minute,
            job_id="daily_watchlist_update",
        )

        permanent_monitor.schedule_friday_audits()
        sovereign_scheduler.schedule_sovereign_tasks()
        scheduler.start()

        jobs = scheduler.list_jobs()
        for job in jobs:
            logger.info(f"Scheduled: {job['id']} - Next: {job['next_run']}")

        symbols = get_permanent_symbols()
        channel = bot.get_channel(settings.discord_channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            await channel.send(
                "🤖 **Global Sovereign Quant Online!**\n"
                f"📌 Watchlist: {', '.join(symbols)}\n"
                "⏰ **Schedule:**\n"
                "• 4:00 AM - Pre-Market Digestion\n"
                "• 10:00 AM - VWAP Integrity Scan\n"
                "• 2:00 PM - 2 O'Clock Sweep\n"
                "• 8:00 PM - Recursive Audit\n"
                "Type `!commands` for help"
            )

    async def message_handler(message: discord.Message) -> None:
        await handle_watchlist_messages(message, watchlist)

    bot.add_message_handler(message_handler)

    try:
        await bot.start(settings.discord_bot_token)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        scheduler.stop()
        await bot.close()


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\nBot stopped.")


if __name__ == "__main__":
    main()
