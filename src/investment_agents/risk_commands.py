"""Discord commands for risk audit functionality."""

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from .entry_signals import EntrySignalAnalyzer, EntrySignal
from .permanent_watchlist import PermanentWatchlistMonitor, get_permanent_symbols
from .risk_audit import RiskAuditor

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)


class RiskCommands(commands.Cog):
    def __init__(self, bot: "InvestmentBot", monitor: PermanentWatchlistMonitor) -> None:
        self.bot = bot
        self.monitor = monitor
        self.auditor = RiskAuditor()
        self.entry_analyzer = EntrySignalAnalyzer()

    @commands.command(name="audit", aliases=["risk", "check"])
    async def audit_symbol(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        symbol = symbol.upper()
        await ctx.send(f"🔍 Running risk audit for **{symbol}**...")
        try:
            result = await self.auditor.run_audit(symbol)
            await ctx.send(result.to_discord_message())
        except Exception as e:
            logger.error(f"Error auditing {symbol}: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="auditall", aliases=["riskall", "friday"])
    async def audit_all(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.send("🔍 Running full risk audit...")
        await self.monitor.run_full_audit(reason="Manual Risk Audit")

    @commands.command(name="catalyst")
    async def catalyst_audit(self, ctx: commands.Context[commands.Bot], symbol: str, *, catalyst: str) -> None:
        symbol = symbol.upper()
        await self.monitor.catalyst_audit(symbol, catalyst)

    @commands.command(name="hype")
    async def hype_score(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        symbol = symbol.upper()
        try:
            result = await self.auditor.run_audit(symbol)
            emoji = "🟢" if result.hype_score >= 8 else "🟡" if result.hype_score >= 5 else "🔴"
            msg = f"{emoji} **{symbol}** Hype Score: **{result.hype_score}/10**\nSignal: {result.overall_signal}"
            if result.filters_triggered:
                alerts = [f.name.replace("_", " ").title() for f in result.filters_triggered]
                msg += f"\nAlerts: {', '.join(alerts)}"
            await ctx.send(msg)
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="permanent", aliases=["perm"])
    async def show_permanent(self, ctx: commands.Context[commands.Bot]) -> None:
        symbols = get_permanent_symbols()
        await ctx.send(f"📌 **Permanent Watchlist:** {', '.join(symbols)}")

    @commands.command(name="permadd", aliases=["padd"])
    async def add_permanent(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Add a symbol to permanent watchlist. Usage: !permadd NVDA"""
        symbol = symbol.upper()
        if self.monitor.add_symbol(symbol):
            await ctx.send(f"✅ Added **{symbol}** to permanent watchlist")
        else:
            await ctx.send(f"⚠️ **{symbol}** is already in permanent watchlist")

    @commands.command(name="permremove", aliases=["prm"])
    async def remove_permanent(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Remove a symbol from permanent watchlist. Usage: !permremove NVDA"""
        symbol = symbol.upper()
        if self.monitor.remove_symbol(symbol):
            await ctx.send(f"✅ Removed **{symbol}** from permanent watchlist")
        else:
            await ctx.send(f"❌ **{symbol}** not found in permanent watchlist")

    @commands.command(name="vwap")
    async def vwap_check(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        symbol = symbol.upper()
        try:
            from .market_data import MarketDataFetcher
            fetcher = MarketDataFetcher()
            data = fetcher.get_intraday_data(symbol)
            if not data:
                await ctx.send(f"❌ No data for {symbol}")
                return

            diff = data.current_price - data.vwap
            emoji = "🟢" if diff > 0 else "🔴"
            above_below = "above" if diff > 0 else "below"
            msg = f"{emoji} **{symbol}** VWAP\nPrice: ${data.current_price:.2f}\nVWAP: ${data.vwap:.2f}\n${abs(diff):.2f} {above_below}"
            if diff < 0 and data.change_percent > 0:
                msg += "\n⚠️ Rising but below VWAP - 'Institutional Offloading'"
            await ctx.send(msg)
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="entry", aliases=["signal", "buy"])
    async def entry_signal(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check if now is a good time to enter. Usage: !entry KLAC"""
        symbol = symbol.upper()
        await ctx.send(f"🎯 Analyzing entry for **{symbol}**...")
        try:
            analysis = await self.entry_analyzer.analyze_entry(symbol)
            await ctx.send(analysis.to_discord_message())
        except Exception as e:
            logger.error(f"Entry analysis error for {symbol}: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="scan", aliases=["scanall", "entries"])
    async def scan_entries(self, ctx: commands.Context[commands.Bot]) -> None:
        """Scan all permanent watchlist for entry opportunities."""
        await ctx.send("🔍 Scanning watchlist for entry signals...")
        try:
            results = await self.entry_analyzer.scan_for_entries()
            
            # Show best opportunities first
            strong = [r for r in results if r.signal == EntrySignal.STRONG_BUY]
            good = [r for r in results if r.signal == EntrySignal.BUY]
            
            if strong:
                await ctx.send(f"🟢🟢🟢 **STRONG BUY signals:** {len(strong)}")
                for r in strong:
                    await ctx.send(r.to_discord_message())
            
            if good:
                await ctx.send(f"🟢 **BUY signals:** {len(good)}")
                for r in good:
                    await ctx.send(r.to_discord_message())
            
            if not strong and not good:
                await ctx.send("No actionable entry signals found. All positions: WAIT or NO ENTRY.")
                # Show summary
                summary = "\n".join([f"• {r.symbol}: {r.signal.value} ({r.confidence}%)" for r in results])
                await ctx.send(f"**Summary:**\n{summary}")
        except Exception as e:
            logger.error(f"Scan error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="helpaudit", aliases=["riskhelp", "help"])
    async def help_audit(self, ctx: commands.Context[commands.Bot]) -> None:
        help_text = """
**🎯 Entry Signals:**
`!entry SYMBOL` - Check if good time to enter
`!scan` - Scan watchlist for best entries

**📊 Risk Audit:**
`!audit SYMBOL` - Full risk audit
`!auditall` - Audit permanent watchlist
`!catalyst SYMBOL reason` - Pre-catalyst audit
`!hype SYMBOL` - Quick hype score
`!vwap SYMBOL` - VWAP check

**📌 Permanent Watchlist:**
`!permanent` - Show watchlist
`!permadd SYMBOL` - Add symbol
`!permremove SYMBOL` - Remove symbol

**Conditions for Entry:** VWAP above, Volume confirmed, Not overextended, No dilution, Morning settled, Above support, Positive momentum
"""
        await ctx.send(help_text)


async def setup_risk_commands(bot: "InvestmentBot", monitor: PermanentWatchlistMonitor) -> None:
    await bot.add_cog(RiskCommands(bot, monitor))
    logger.info("Risk audit commands registered")
