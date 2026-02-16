"""Discord commands for risk audit functionality."""

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from .entry_signals import EntrySignalAnalyzer, EntrySignal
from .permanent_watchlist import PermanentWatchlistMonitor, get_permanent_symbols
from .prediction_journal import get_journal, PredictionType, Outcome
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

    @commands.command(name="journal", aliases=["j"])
    async def show_journal(self, ctx: commands.Context[commands.Bot], days: int = 7) -> None:
        """Show prediction journal stats. Usage: !journal or !journal 30"""
        journal = get_journal()
        stats = journal.get_stats(days=days)

        msg = (
            f"📔 **Prediction Journal** (Last {days} days)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**Total Predictions:** {stats['total_predictions']}\n"
            f"**Resolved:** {stats['resolved']} | **Pending:** {stats['pending']}\n"
            f"**Accuracy:** {stats['accuracy']:.1f}%\n"
            f"**Total P&L:** {stats['total_pnl_percent']:+.1f}%\n"
            f"**Avg P&L:** {stats['avg_pnl_percent']:+.1f}%"
        )
        await ctx.send(msg)

    @commands.command(name="predictions", aliases=["preds"])
    async def show_predictions(self, ctx: commands.Context[commands.Bot], limit: int = 5) -> None:
        """Show recent predictions. Usage: !predictions or !predictions 10"""
        journal = get_journal()
        recent = journal.get_recent_predictions(limit=min(limit, 10))

        if not recent:
            await ctx.send("📔 No predictions recorded yet.")
            return

        await ctx.send(f"📔 **Recent Predictions** (Last {len(recent)}):")
        for pred in recent:
            await ctx.send(journal.format_prediction_discord(pred))

    @commands.command(name="audit_variance", aliases=["variance", "va"])
    async def show_variance(self, ctx: commands.Context[commands.Bot]) -> None:
        """Run and show variance analysis."""
        journal = get_journal()
        await ctx.send("🔄 Running variance analysis...")

        audit = journal.run_variance_analysis()
        await ctx.send(journal.format_audit_discord(audit))

    @commands.command(name="outcome", aliases=["result"])
    async def update_outcome(
        self,
        ctx: commands.Context[commands.Bot],
        pred_id: str,
        result: str,
        price: float,
    ) -> None:
        """Update prediction outcome. Usage: !outcome KLAC_20260216_100000 correct 125.50"""
        journal = get_journal()

        outcome_map = {
            "correct": Outcome.CORRECT,
            "incorrect": Outcome.INCORRECT,
            "partial": Outcome.PARTIAL,
            "c": Outcome.CORRECT,
            "i": Outcome.INCORRECT,
            "p": Outcome.PARTIAL,
        }

        outcome = outcome_map.get(result.lower())
        if not outcome:
            await ctx.send("❌ Invalid result. Use: correct, incorrect, or partial")
            return

        if journal.update_outcome(pred_id, outcome, price):
            await ctx.send(f"✅ Updated {pred_id} to {outcome.value} at ${price:.2f}")
        else:
            await ctx.send(f"❌ Prediction {pred_id} not found")

    @commands.command(name="helpaudit", aliases=["riskhelp", "commands"])
    async def help_audit(self, ctx: commands.Context[commands.Bot]) -> None:
        help_text = """
**🎯 Entry Signals:**
`!entry SYMBOL` - Check if good time to enter
`!scan` - Scan watchlist for best entries

**📊 Risk Audit:**
`!audit SYMBOL` - Full risk audit
`!auditall` - Audit permanent watchlist
`!hype SYMBOL` - Quick hype score
`!vwap SYMBOL` - VWAP check

**📔 Prediction Journal:**
`!journal [days]` - Show prediction stats
`!predictions [limit]` - Show recent predictions
`!variance` - Run variance analysis
`!outcome ID result price` - Update prediction outcome

**📌 Permanent Watchlist:**
`!permanent` - Show watchlist
`!permadd SYMBOL` - Add symbol
`!permremove SYMBOL` - Remove symbol

**⏰ Scheduled Tasks (Auto):**
• 4:00 AM - Pre-Market Digestion
• 10:00 AM - VWAP Integrity Scan
• 2:00 PM - 2 O'Clock Sweep
• 8:00 PM - Recursive Audit
"""
        await ctx.send(help_text)


async def setup_risk_commands(bot: "InvestmentBot", monitor: PermanentWatchlistMonitor) -> None:
    await bot.add_cog(RiskCommands(bot, monitor))
    logger.info("Risk audit commands registered")
