"""Discord bot commands for watchlist management."""

import logging
from typing import TYPE_CHECKING

from discord import Message
from discord.ext import commands

from .watchlist import WatchlistManager

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)


def format_watchlist_text(items: list) -> str:
    if not items:
        return "Watchlist is empty."
    lines = ["**Current Watchlist:**", ""]
    for i, item in enumerate(items, 1):
        line = f"{i}. {item.symbol}"
        if item.name:
            line += f" ({item.name})"
        if item.target_price:
            line += f" - Target: ${item.target_price:.2f}"
        lines.append(line)
    return "\n".join(lines)


class WatchlistCommands(commands.Cog):
    def __init__(self, bot: "InvestmentBot", watchlist: WatchlistManager) -> None:
        self.bot = bot
        self.watchlist = watchlist

    @commands.command(name="watchlist", aliases=["wl", "list"])
    async def show_watchlist(self, ctx: commands.Context[commands.Bot]) -> None:
        items = self.watchlist.get_all()
        await ctx.send(format_watchlist_text(items))

    @commands.command(name="add")
    async def add_symbol(self, ctx: commands.Context[commands.Bot], symbol: str, *, notes: str = "") -> None:
        symbol = symbol.upper()
        self.watchlist.add(symbol, notes=notes if notes else None)
        await ctx.send(f"✅ Added **{symbol}** to watchlist")

    @commands.command(name="remove", aliases=["rm", "delete"])
    async def remove_symbol(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        symbol = symbol.upper()
        if self.watchlist.remove(symbol):
            await ctx.send(f"✅ Removed **{symbol}** from watchlist")
        else:
            await ctx.send(f"❌ **{symbol}** not found")

    @commands.command(name="target")
    async def set_target(self, ctx: commands.Context[commands.Bot], symbol: str, price: float) -> None:
        symbol = symbol.upper()
        if self.watchlist.update(symbol, target_price=price):
            await ctx.send(f"✅ Set target for **{symbol}** to ${price:.2f}")
        else:
            await ctx.send(f"❌ **{symbol}** not found")

    @commands.command(name="import")
    async def import_symbols(self, ctx: commands.Context[commands.Bot], *, symbols: str) -> None:
        symbol_list = [s.strip() for s in symbols.replace(",", " ").split()]
        count = self.watchlist.import_symbols(symbol_list)
        await ctx.send(f"✅ Imported {count} new symbols")

    @commands.command(name="clear")
    async def clear_watchlist(self, ctx: commands.Context[commands.Bot]) -> None:
        count = len(self.watchlist.get_all())
        self.watchlist.clear()
        await ctx.send(f"✅ Cleared {count} items")


async def setup_commands(bot: "InvestmentBot", watchlist: WatchlistManager) -> None:
    await bot.add_cog(WatchlistCommands(bot, watchlist))
    logger.info("Watchlist commands registered")


async def handle_watchlist_messages(message: Message, watchlist: WatchlistManager) -> None:
    content = message.content.lower()
    if content.startswith("$") and len(content) <= 6:
        symbol = content[1:].upper()
        if symbol.isalpha():
            watchlist.add(symbol)
            await message.add_reaction("✅")
