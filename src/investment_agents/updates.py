"""Daily update generation."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import discord

from .watchlist import WatchlistItem, WatchlistManager

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)


class DailyUpdateGenerator:
    def __init__(self, bot: "InvestmentBot", watchlist_manager: WatchlistManager, channel_id: int | None = None) -> None:
        self.bot = bot
        self.watchlist = watchlist_manager
        self.channel_id = channel_id

    async def send_daily_update(self) -> None:
        logger.info("Generating daily update...")
        items = self.watchlist.get_all()

        if not items:
            embed = discord.Embed(
                title="📊 Daily Watchlist Update",
                description="Your watchlist is empty.",
                color=discord.Color.yellow(),
                timestamp=datetime.now(),
            )
        else:
            embed = discord.Embed(
                title="📊 Daily Watchlist Update",
                description=f"As of {datetime.now().strftime('%B %d, %Y')}",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )

            symbols_text = ""
            for item in items[:25]:
                line = f"**{item.symbol}**"
                if item.name:
                    line += f" - {item.name}"
                if item.target_price:
                    line += f" (Target: ${item.target_price:.2f})"
                symbols_text += line + "\n"

            if symbols_text:
                embed.add_field(name=f"Watchlist ({len(items)} items)", value=symbols_text[:1024], inline=False)

        channel_id = self.channel_id or self.bot.default_channel_id
        if channel_id:
            await self.bot.send_to_channel(content="", channel_id=channel_id, embed=embed)
            logger.info(f"Daily update sent with {len(items)} items")
