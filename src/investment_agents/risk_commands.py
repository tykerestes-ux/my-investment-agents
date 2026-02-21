"""Discord commands for risk audit functionality."""

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from .adaptive_params import get_param_manager, get_params
from .analyst_ratings import get_analyst_ratings, format_analyst_discord
from .backtest import run_quick_backtest, Backtester
from .earnings_calendar import get_earnings_date, format_earnings_discord
from .economic_calendar import get_economic_calendar, format_calendar_discord
from .enhanced_analyzer import EnhancedEntryAnalyzer, enhanced_analyze
from .entry_signals import EntrySignalAnalyzer, EntrySignal
from .insider_trading import get_insider_transactions, format_insider_discord
from .institutional_holdings import get_institutional_holdings, format_institutional_discord
from .multi_timeframe import get_multi_timeframe_data, format_multi_timeframe_discord
from .news_sentiment import analyze_news_sentiment, format_news_discord
from .options_flow import analyze_options_flow, format_options_discord
from .permanent_watchlist import PermanentWatchlistMonitor, get_permanent_symbols
from .position_sizing import calculate_position_size, format_position_size_discord
from .prediction_journal import get_journal, PredictionType, Outcome
from .risk_audit import RiskAuditor
from .sector_correlation import analyze_sector_correlation, get_sector_summary, format_sector_discord
from .short_interest import get_short_interest, format_short_interest_discord
from .technical_indicators import get_technical_indicators, format_technicals_discord

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)


class RiskCommands(commands.Cog):
    def __init__(self, bot: "InvestmentBot", monitor: PermanentWatchlistMonitor) -> None:
        self.bot = bot
        self.monitor = monitor
        self.auditor = RiskAuditor()
        self.entry_analyzer = EntrySignalAnalyzer()
        self.enhanced_analyzer = EnhancedEntryAnalyzer()
        self.enhanced_analyzer = EnhancedEntryAnalyzer()

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

    # === ENHANCED ANALYSIS COMMANDS ===

    @commands.command(name="deep", aliases=["enhanced", "full"])
    async def deep_analysis(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Run enhanced analysis with all 6 filters. Usage: !deep KLAC"""
        symbol = symbol.upper()
        await ctx.send(f"🔬 Running enhanced analysis for **{symbol}**... (this may take a moment)")
        try:
            analysis = await self.enhanced_analyzer.analyze(symbol, run_backtest=True)
            await ctx.send(analysis.to_discord_message())
        except Exception as e:
            logger.error(f"Enhanced analysis error for {symbol}: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="earnings", aliases=["earn"])
    async def check_earnings(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check earnings date and lockout status. Usage: !earnings KLAC"""
        symbol = symbol.upper()
        try:
            info = get_earnings_date(symbol)
            await ctx.send(format_earnings_discord(info))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="sector", aliases=["correlation"])
    async def check_sector(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check sector correlation and crowding. Usage: !sector KLAC"""
        symbol = symbol.upper()
        try:
            # Get all current signals for context
            all_signals = {}
            for sym in get_permanent_symbols():
                analysis = await self.entry_analyzer.analyze_entry(sym)
                all_signals[sym] = analysis.signal.value
            
            sector_analysis = analyze_sector_correlation(symbol, all_signals)
            await ctx.send(format_sector_discord(sector_analysis))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="timeframe", aliases=["tf", "mtf"])
    async def check_timeframes(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check multi-timeframe alignment. Usage: !timeframe KLAC"""
        symbol = symbol.upper()
        try:
            data = get_multi_timeframe_data(symbol)
            await ctx.send(format_multi_timeframe_discord(data))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="news", aliases=["sentiment"])
    async def check_news(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check news sentiment. Usage: !news KLAC"""
        symbol = symbol.upper()
        try:
            analysis = analyze_news_sentiment(symbol)
            await ctx.send(format_news_discord(analysis))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="backtest", aliases=["bt"])
    async def run_backtest(self, ctx: commands.Context[commands.Bot], symbol: str, days: int = 90) -> None:
        """Run backtest on historical data. Usage: !backtest KLAC 90"""
        symbol = symbol.upper()
        await ctx.send(f"📊 Running {days}-day backtest for **{symbol}**...")
        try:
            result = run_quick_backtest(symbol, days)
            await ctx.send(result.to_discord_message())
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="size", aliases=["position", "possize"])
    async def calculate_size(
        self,
        ctx: commands.Context[commands.Bot],
        symbol: str,
        account: float = 10000,
    ) -> None:
        """Calculate position size. Usage: !size KLAC 10000"""
        symbol = symbol.upper()
        try:
            # Get current signal for the symbol
            analysis = await self.entry_analyzer.analyze_entry(symbol)
            
            sizing = calculate_position_size(
                symbol=symbol,
                confidence=analysis.confidence,
                signal_type=analysis.signal.value.upper(),
                account_size=account,
            )
            await ctx.send(format_position_size_discord(sizing, account))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="deepscan", aliases=["fullscan"])
    async def deep_scan(self, ctx: commands.Context[commands.Bot]) -> None:
        """Run enhanced analysis on entire watchlist."""
        await ctx.send("🔬 Running enhanced scan on watchlist... (this may take a minute)")
        try:
            results = await self.enhanced_analyzer.scan_enhanced(run_backtest=False)
            
            # Categorize results
            strong = [r for r in results if r.final_signal == EntrySignal.STRONG_BUY]
            buy = [r for r in results if r.final_signal == EntrySignal.BUY]
            wait = [r for r in results if r.final_signal == EntrySignal.WAIT]
            
            summary = (
                f"**Enhanced Scan Complete**\n"
                f"🟢🟢🟢 Strong Buy: {len(strong)}\n"
                f"🟢 Buy: {len(buy)}\n"
                f"🟡 Wait: {len(wait)}\n"
            )
            await ctx.send(summary)
            
            # Show details for actionable signals
            for r in strong + buy[:3]:
                await ctx.send(r.to_discord_message())
                
        except Exception as e:
            logger.error(f"Deep scan error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    # === ADAPTIVE PARAMETER COMMANDS ===

    @commands.command(name="suggestions", aliases=["pending", "suggest"])
    async def show_suggestions(self, ctx: commands.Context[commands.Bot]) -> None:
        """Show pending parameter change suggestions."""
        manager = get_param_manager()
        await ctx.send(manager.get_pending_summary())

    @commands.command(name="params", aliases=["parameters", "config"])
    async def show_params(self, ctx: commands.Context[commands.Bot]) -> None:
        """Show current system parameters."""
        manager = get_param_manager()
        await ctx.send(manager.get_current_params_summary())

    @commands.command(name="approve")
    async def approve_change(self, ctx: commands.Context[commands.Bot], change_id: str) -> None:
        """Approve a specific parameter change. Usage: !approve vwap_weight_20260221_120000"""
        manager = get_param_manager()
        if manager.approve_change(change_id):
            await ctx.send(f"✅ Approved and applied change: `{change_id}`")
            # Show new value
            params = get_params()
            await ctx.send(f"New parameters version: v{params.version}")
        else:
            await ctx.send(f"❌ Change not found: `{change_id}`")

    @commands.command(name="approveall")
    async def approve_all_changes(self, ctx: commands.Context[commands.Bot]) -> None:
        """Approve all pending parameter changes."""
        manager = get_param_manager()
        count = manager.approve_all()
        if count > 0:
            params = get_params()
            await ctx.send(f"✅ Approved and applied {count} changes. Parameters now at v{params.version}")
        else:
            await ctx.send("📋 No pending changes to approve.")

    @commands.command(name="reject")
    async def reject_change(self, ctx: commands.Context[commands.Bot], change_id: str) -> None:
        """Reject a specific parameter change. Usage: !reject vwap_weight_20260221_120000"""
        manager = get_param_manager()
        if manager.reject_change(change_id):
            await ctx.send(f"❌ Rejected change: `{change_id}`")
        else:
            await ctx.send(f"❌ Change not found: `{change_id}`")

    @commands.command(name="rejectall")
    async def reject_all_changes(self, ctx: commands.Context[commands.Bot]) -> None:
        """Reject all pending parameter changes."""
        manager = get_param_manager()
        count = manager.reject_all()
        await ctx.send(f"❌ Rejected {count} pending changes.")

    @commands.command(name="learn", aliases=["adapt"])
    async def run_learning(self, ctx: commands.Context[commands.Bot]) -> None:
        """Run variance analysis and generate improvement suggestions."""
        await ctx.send("🧠 Running learning cycle...")
        
        journal = get_journal()
        manager = get_param_manager()
        
        # Run variance analysis
        audit = journal.run_variance_analysis()
        await ctx.send(journal.format_audit_discord(audit))
        
        # Generate suggestions
        suggestions = manager.generate_suggestions_from_audit(
            accuracy=audit.accuracy_rate,
            common_failures=audit.common_failures,
            weight_adjustments=audit.weight_adjustments,
        )
        
        if suggestions:
            await ctx.send(f"\n🔧 Generated {len(suggestions)} improvement suggestions:")
            await ctx.send(manager.get_pending_summary())
        else:
            await ctx.send("\n✅ No parameter changes suggested - system performing well.")

    # === NEW DATA SOURCE COMMANDS ===

    @commands.command(name="insider", aliases=["insiders"])
    async def check_insider(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check insider trading activity. Usage: !insider KLAC"""
        symbol = symbol.upper()
        await ctx.send(f"👔 Checking insider activity for **{symbol}**...")
        try:
            data = await get_insider_transactions(symbol)
            await ctx.send(format_insider_discord(data))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="short", aliases=["shorts", "si"])
    async def check_short_interest(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check short interest data. Usage: !short KLAC"""
        symbol = symbol.upper()
        try:
            data = get_short_interest(symbol)
            await ctx.send(format_short_interest_discord(data))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="options", aliases=["flow", "pcr"])
    async def check_options(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check options flow and put/call ratio. Usage: !options KLAC"""
        symbol = symbol.upper()
        await ctx.send(f"📈 Analyzing options flow for **{symbol}**...")
        try:
            data = analyze_options_flow(symbol)
            await ctx.send(format_options_discord(data))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="analysts", aliases=["analyst", "ratings"])
    async def check_analysts(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check analyst ratings and price targets. Usage: !analysts KLAC"""
        symbol = symbol.upper()
        try:
            data = get_analyst_ratings(symbol)
            await ctx.send(format_analyst_discord(data))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="technicals", aliases=["ta", "tech"])
    async def check_technicals(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check technical indicators (RSI, MACD, etc). Usage: !technicals KLAC"""
        symbol = symbol.upper()
        try:
            data = get_technical_indicators(symbol)
            await ctx.send(format_technicals_discord(data))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="institutions", aliases=["inst", "holders"])
    async def check_institutions(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Check institutional holdings. Usage: !institutions KLAC"""
        symbol = symbol.upper()
        try:
            data = get_institutional_holdings(symbol)
            await ctx.send(format_institutional_discord(data))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="calendar", aliases=["econ", "economic"])
    async def check_calendar(self, ctx: commands.Context[commands.Bot]) -> None:
        """Check economic calendar for upcoming events."""
        try:
            data = get_economic_calendar()
            await ctx.send(format_calendar_discord(data))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="fullreport", aliases=["report", "all"])
    async def full_report(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Get complete report with ALL data sources. Usage: !fullreport KLAC"""
        symbol = symbol.upper()
        await ctx.send(f"📊 Generating full report for **{symbol}**... (this may take a moment)")
        
        try:
            # Technical
            tech = get_technical_indicators(symbol)
            await ctx.send(format_technicals_discord(tech))
            
            # Short Interest
            short = get_short_interest(symbol)
            await ctx.send(format_short_interest_discord(short))
            
            # Analyst Ratings
            analysts = get_analyst_ratings(symbol)
            await ctx.send(format_analyst_discord(analysts))
            
            # Options Flow
            options = analyze_options_flow(symbol)
            await ctx.send(format_options_discord(options))
            
            # Institutional
            inst = get_institutional_holdings(symbol)
            await ctx.send(format_institutional_discord(inst))
            
            # Insider Trading
            insider = await get_insider_transactions(symbol)
            await ctx.send(format_insider_discord(insider))
            
            # Final summary
            signals = []
            if tech.overall_signal in ["STRONG_BUY", "BUY"]:
                signals.append(f"✅ Technicals: {tech.overall_signal}")
            elif tech.overall_signal in ["SELL", "STRONG_SELL"]:
                signals.append(f"❌ Technicals: {tech.overall_signal}")
            
            if short.signal in ["LOW_SHORT", "SQUEEZE_POTENTIAL"]:
                signals.append(f"✅ Short Interest: {short.signal}")
            elif short.signal == "HIGH_SHORT":
                signals.append(f"⚠️ Short Interest: {short.signal}")
            
            if analysts.signal in ["STRONG_BUY", "BUY"]:
                signals.append(f"✅ Analysts: {analysts.signal}")
            elif analysts.signal == "SELL":
                signals.append(f"❌ Analysts: {analysts.signal}")
            
            if "BULLISH" in options.signal:
                signals.append(f"✅ Options Flow: {options.signal}")
            elif "BEARISH" in options.signal:
                signals.append(f"❌ Options Flow: {options.signal}")
            
            summary = f"\n📋 **SUMMARY: {symbol}**\n" + "\n".join(signals)
            await ctx.send(summary)
            
        except Exception as e:
            logger.error(f"Full report error for {symbol}: {e}")
            await ctx.send(f"❌ Error generating report: {str(e)[:200]}")

    @commands.command(name="helpaudit", aliases=["riskhelp", "commands", "help2"])
    async def help_audit(self, ctx: commands.Context[commands.Bot]) -> None:
        help_text = """
**📊 Full Analysis:**
`!fullreport SYMBOL` - Complete report with ALL data
`!deep SYMBOL` - Enhanced entry analysis

**🎯 Entry Signals:**
`!entry SYMBOL` - Quick entry check
`!scan` - Scan watchlist

**📈 Market Data:**
`!technicals SYMBOL` - RSI, MACD, Bollinger, MAs
`!short SYMBOL` - Short interest
`!options SYMBOL` - Put/Call ratio, unusual activity
`!analysts SYMBOL` - Price targets & ratings
`!insider SYMBOL` - Executive buys/sells
`!institutions SYMBOL` - 13F holdings

**📅 Calendars:**
`!earnings SYMBOL` - Earnings date
`!calendar` - Economic events (FOMC, CPI, Jobs)

**🧠 Adaptive Learning:**
`!learn` - Generate improvement suggestions
`!suggestions` - View pending changes
`!approveall` - Apply all changes

**📔 Journal:**
`!journal` - Prediction stats
"""
        await ctx.send(help_text)


async def setup_risk_commands(bot: "InvestmentBot", monitor: PermanentWatchlistMonitor) -> None:
    await bot.add_cog(RiskCommands(bot, monitor))
    logger.info("Risk audit commands registered")
