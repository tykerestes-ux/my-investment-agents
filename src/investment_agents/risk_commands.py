"""Discord commands for risk audit functionality."""

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from .adaptive_params import get_param_manager, get_params
from .alert_system import get_alert_manager, AlertType
from .analyst_ratings import get_analyst_ratings, format_analyst_discord
from .refined_targets import calculate_refined_target, format_refined_target_discord, SEMI_EQUIPMENT
from .semi_cycle_risk import analyze_cycle_risk
from .verified_prediction import generate_verified_prediction, format_prediction_discord, PredictionSignal
from .backtester import backtest_signals, format_backtest_discord, format_backtest_summary
from .opportunity_scanner import scan_for_opportunities, format_opportunities_discord, format_quick_opportunities, SCAN_UNIVERSE
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
from .risk_dashboard import get_risk_dashboard, format_dashboard_discord, format_quick_dashboard_discord
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

    @commands.command(name="entry", aliases=["signal", "entrysignal"])
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

    @commands.command(name="symbolbt", aliases=["sbt", "stockbt"])
    async def symbol_backtest(self, ctx: commands.Context[commands.Bot], symbol: str, days: int = 90) -> None:
        """Backtest a single symbol. Usage: !symbolbt KLAC 90"""
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

    # === ALERT SYSTEM COMMANDS ===

    @commands.command(name="alert", aliases=["setalert"])
    async def add_alert(self, ctx: commands.Context[commands.Bot], symbol: str, alert_type: str, value: float = 0) -> None:
        """Add an alert. Usage: !alert KLAC target 150 or !alert KLAC stop 120 or !alert KLAC rsi"""
        symbol = symbol.upper()
        manager = get_alert_manager()
        
        alert_type = alert_type.lower()
        
        if alert_type in ["target", "above", "price"]:
            if value <= 0:
                await ctx.send("❌ Please provide a target price. Usage: `!alert KLAC target 150`")
                return
            alert = manager.add_price_alert(symbol, value, "above")
            await ctx.send(f"🎯 Alert set: Notify when **{symbol}** reaches **${value:.2f}**")
            
        elif alert_type in ["stop", "below", "stoploss"]:
            if value <= 0:
                await ctx.send("❌ Please provide a stop price. Usage: `!alert KLAC stop 120`")
                return
            alert = manager.add_price_alert(symbol, value, "below")
            await ctx.send(f"🛑 Alert set: Notify when **{symbol}** drops to **${value:.2f}**")
            
        elif alert_type in ["rsi", "oversold"]:
            alert = manager.add_rsi_alert(symbol, oversold=True)
            await ctx.send(f"📉 Alert set: Notify when **{symbol}** RSI goes below 30 (oversold)")
            
        elif alert_type in ["overbought", "rsihigh"]:
            alert = manager.add_rsi_alert(symbol, oversold=False)
            await ctx.send(f"📈 Alert set: Notify when **{symbol}** RSI goes above 70 (overbought)")
            
        elif alert_type in ["insider", "insiders"]:
            alert = manager.add_insider_alert(symbol)
            await ctx.send(f"👔 Alert set: Notify when **{symbol}** insider buying detected")
            
        elif alert_type in ["move", "percent", "pct"]:
            if value <= 0:
                value = 5  # Default 5%
            alert = manager.add_percent_change_alert(symbol, value)
            await ctx.send(f"🚨 Alert set: Notify when **{symbol}** moves **{value}%** in a day")
            
        else:
            await ctx.send(
                "❌ Unknown alert type. Options:\n"
                "• `!alert KLAC target 150` - Price reaches $150\n"
                "• `!alert KLAC stop 120` - Price drops to $120\n"
                "• `!alert KLAC rsi` - RSI goes oversold (<30)\n"
                "• `!alert KLAC overbought` - RSI goes overbought (>70)\n"
                "• `!alert KLAC insider` - Insider buying detected\n"
                "• `!alert KLAC move 5` - Moves 5% in a day"
            )

    @commands.command(name="alerts", aliases=["myalerts", "listalerts"])
    async def list_alerts(self, ctx: commands.Context[commands.Bot], symbol: str | None = None) -> None:
        """List all active alerts. Usage: !alerts or !alerts KLAC"""
        manager = get_alert_manager()
        await ctx.send(manager.format_alerts_discord(symbol))

    @commands.command(name="removealert", aliases=["delalert", "cancelalert"])
    async def remove_alert(self, ctx: commands.Context[commands.Bot], alert_id: str) -> None:
        """Remove an alert by ID. Usage: !removealert KLAC_price_above_..."""
        manager = get_alert_manager()
        
        # Allow partial ID match
        matching = [a for a in manager.alerts if alert_id in a.id]
        
        if not matching:
            await ctx.send(f"❌ Alert not found: `{alert_id}`")
            return
        
        if len(matching) > 1:
            await ctx.send(f"⚠️ Multiple matches. Be more specific:\n" + "\n".join([f"• `{a.id}`" for a in matching]))
            return
        
        if manager.remove_alert(matching[0].id):
            await ctx.send(f"✅ Alert removed: `{matching[0].id[:40]}...`")
        else:
            await ctx.send("❌ Failed to remove alert")

    @commands.command(name="clearalerts")
    async def clear_alerts(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Remove all alerts for a symbol. Usage: !clearalerts KLAC"""
        symbol = symbol.upper()
        manager = get_alert_manager()
        
        alerts = manager.get_alerts_by_symbol(symbol)
        if not alerts:
            await ctx.send(f"📭 No alerts found for {symbol}")
            return
        
        for alert in alerts:
            manager.remove_alert(alert.id)
        
        await ctx.send(f"✅ Removed {len(alerts)} alerts for {symbol}")

    @commands.command(name="checkalerts")
    async def check_alerts_now(self, ctx: commands.Context[commands.Bot]) -> None:
        """Manually check all alerts now."""
        await ctx.send("🔍 Checking all alerts...")
        manager = get_alert_manager()
        triggered = await manager.check_all_alerts()
        
        if triggered:
            for alert in triggered:
                await ctx.send(alert.message)
        else:
            await ctx.send("✅ No alerts triggered")

    # === RISK DASHBOARD COMMANDS ===

    @commands.command(name="dashboard", aliases=["dash", "riskdash"])
    async def show_dashboard(self, ctx: commands.Context[commands.Bot]) -> None:
        """Show full risk dashboard."""
        await ctx.send("📊 Generating risk dashboard...")
        try:
            dash = get_risk_dashboard()
            # Split into multiple messages if needed
            full_msg = format_dashboard_discord(dash)
            
            if len(full_msg) > 1900:
                # Send in chunks
                lines = full_msg.split("\n")
                chunk = ""
                for line in lines:
                    if len(chunk) + len(line) > 1900:
                        await ctx.send(chunk)
                        chunk = line + "\n"
                    else:
                        chunk += line + "\n"
                if chunk:
                    await ctx.send(chunk)
            else:
                await ctx.send(full_msg)
                
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="quickrisk", aliases=["qr", "riskcheck"])
    async def quick_risk(self, ctx: commands.Context[commands.Bot]) -> None:
        """Quick risk summary."""
        try:
            dash = get_risk_dashboard()
            await ctx.send(format_quick_dashboard_discord(dash))
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    # === OPPORTUNITY SCANNER ===

    @commands.command(name="opportunities", aliases=["findbuys", "scanner"])
    async def find_opportunities(self, ctx: commands.Context[commands.Bot], mode: str = "full") -> None:
        """Scan market for buying opportunities. Usage: !opportunities or !opportunities quick"""
        await ctx.send("🔍 **Scanning 120+ stocks for opportunities...** (this takes ~2 minutes)")
        
        try:
            # Scan all sectors
            opportunities = await scan_for_opportunities(
                sectors=None,  # All sectors
                min_score=55,  # Show more opportunities
                max_results=25,
            )
            
            if mode.lower() == "quick":
                await ctx.send(format_quick_opportunities(opportunities, limit=10))
            else:
                messages = format_opportunities_discord(opportunities)
                for msg in messages:
                    await ctx.send(msg)
                    
        except Exception as e:
            logger.error(f"Opportunity scan error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="opps", aliases=["opp", "buys"])
    async def quick_opportunities(self, ctx: commands.Context[commands.Bot], sector: str = None) -> None:
        """Quick opportunity scan. Usage: !opps or !opps tech or !opps semis"""
        
        # Map common names to sector keys
        sector_map = {
            "tech": ["tech"],
            "semis": ["semiconductors"],
            "semiconductors": ["semiconductors"],
            "finance": ["financials"],
            "financials": ["financials"],
            "banks": ["financials"],
            "health": ["healthcare"],
            "healthcare": ["healthcare"],
            "pharma": ["healthcare"],
            "energy": ["energy"],
            "oil": ["energy"],
            "consumer": ["consumer"],
            "retail": ["consumer"],
            "industrial": ["industrials"],
            "industrials": ["industrials"],
            "all": None,
        }
        
        if sector:
            sectors = sector_map.get(sector.lower())
            if sectors is None and sector.lower() != "all":
                available = ", ".join(SCAN_UNIVERSE.keys())
                await ctx.send(f"❌ Unknown sector. Available: {available}")
                return
            sector_name = sector.title()
        else:
            sectors = None
            sector_name = "All Sectors"
        
        await ctx.send(f"🔍 **Scanning {sector_name}...** (30-60 seconds)")
        
        try:
            opportunities = await scan_for_opportunities(
                sectors=sectors,
                min_score=55,
                max_results=15,
            )
            
            await ctx.send(format_quick_opportunities(opportunities, limit=10))
            
        except Exception as e:
            logger.error(f"Quick scan error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="topopps", aliases=["best", "topbuys"])
    async def top_opportunities(self, ctx: commands.Context[commands.Bot]) -> None:
        """Show only STRONG_BUY opportunities with high confidence."""
        await ctx.send("🔍 **Scanning for STRONG_BUY setups...** (~2 minutes)")
        
        try:
            opportunities = await scan_for_opportunities(
                sectors=None,
                min_score=75,  # Higher threshold
                max_results=10,
            )
            
            # Filter to only STRONG_BUY
            strong = [o for o in opportunities if o.entry_type == "STRONG_BUY"]
            
            if not strong:
                await ctx.send("📭 No STRONG_BUY setups found right now. Market may be extended or lacking clear setups.")
                return
            
            messages = format_opportunities_discord(strong)
            for msg in messages:
                await ctx.send(msg)
                
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    # === VERIFIED PREDICTIONS (No Look-Ahead Bias) ===

    @commands.command(name="predict", aliases=["vp", "verified"])
    async def verified_prediction(self, ctx: commands.Context[commands.Bot], symbol: str) -> None:
        """Generate verified prediction with no look-ahead bias. Usage: !predict KLAC"""
        symbol = symbol.upper()
        await ctx.send(f"🔍 Generating verified prediction for **{symbol}**...")
        
        try:
            prediction = await generate_verified_prediction(symbol)
            await ctx.send(format_prediction_discord(prediction))
            
        except Exception as e:
            logger.error(f"Prediction error for {symbol}: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="predictscan", aliases=["vpscan", "vscan"])
    async def verified_scan(self, ctx: commands.Context[commands.Bot]) -> None:
        """Scan watchlist with verified predictions."""
        symbols = get_permanent_symbols()
        await ctx.send(f"🔍 Running verified prediction scan on {len(symbols)} symbols...")
        
        try:
            results = []
            for symbol in symbols:
                pred = await generate_verified_prediction(symbol)
                results.append(pred)
                await asyncio.sleep(0.5)
            
            # Sort by probability
            results.sort(key=lambda x: x.probability_of_success, reverse=True)
            
            # Summary
            lines = [
                "📊 **VERIFIED PREDICTION SCAN**",
                "═" * 40,
                "",
            ]
            
            for pred in results:
                signal_emoji = {
                    PredictionSignal.STRONG_BUY: "🟢🟢",
                    PredictionSignal.BUY: "🟢",
                    PredictionSignal.NEUTRAL: "🟡",
                    PredictionSignal.AVOID: "🔴",
                    PredictionSignal.HIGH_RISK_DIVERGENCE: "⚠️",
                }.get(pred.signal, "⚪")
                
                vol_flag = " 📉vol" if pred.volume_penalty_applied else ""
                tier_pass = sum(1 for t in pred.tier_results if t.passed)
                
                lines.append(
                    f"{signal_emoji} **{pred.symbol}** - {pred.probability_of_success:.0f}% prob "
                    f"| ${pred.current_price:.2f} | T:{tier_pass}/3{vol_flag}"
                )
            
            lines.append("")
            lines.append("Use `!predict SYMBOL` for full analysis")
            
            await ctx.send("\n".join(lines))
            
        except Exception as e:
            logger.error(f"Verified scan error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    # === REFINED TARGETS (Semi Equipment) ===

    @commands.command(name="calibrate", aliases=["cal", "refinedtarget", "caltarget"])
    async def refined_target(self, ctx: commands.Context[commands.Bot], symbol: str = None) -> None:
        """Get refined price target. Usage: !calibrate or !calibrate LRCX"""
        from .refined_targets import SEMI_EQUIPMENT
        
        # No symbol = scan all semi equipment
        if not symbol:
            await ctx.send(f"🎯 Scanning {len(SEMI_EQUIPMENT)} semi equipment stocks...")
            
            try:
                lines = [
                    "🎯 **REFINED TARGET SCAN** (Semi Equipment)",
                    "═" * 40,
                    "",
                ]
                
                for sym in SEMI_EQUIPMENT:
                    target = calculate_refined_target(sym)
                    
                    if target.upside_percent > 15:
                        emoji = "🟢"
                    elif target.upside_percent > 5:
                        emoji = "🟡"
                    else:
                        emoji = "🔴"
                    
                    flags = []
                    if target.soxx_cap_applied:
                        flags.append("CAPPED")
                    if target.geopolitical_multiplier < 1.0:
                        flags.append(f"GEO:{target.geopolitical_multiplier:.2f}x")
                    if target.momentum_breakout:
                        flags.append("RSI>70")
                    
                    flag_str = f" [{', '.join(flags)}]" if flags else ""
                    
                    lines.append(
                        f"{emoji} **{sym}**: ${target.current_price:.2f} → ${target.final_target:.2f} "
                        f"({target.upside_percent:+.1f}%){flag_str}"
                    )
                
                lines.append("")
                lines.append("Use `!calibrate SYMBOL` for full breakdown")
                
                await ctx.send("\n".join(lines))
                
            except Exception as e:
                logger.error(f"Calibrate scan error: {e}")
                await ctx.send(f"❌ Error: {str(e)[:200]}")
            return
        
        # Specific symbol
        symbol = symbol.upper()
        await ctx.send(f"🎯 Calculating refined target for **{symbol}**...")
        
        try:
            target = calculate_refined_target(symbol)
            await ctx.send(format_refined_target_discord(target))
            
        except Exception as e:
            logger.error(f"Refined target error for {symbol}: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="calscan", aliases=["calibratescan"])
    async def target_scan(self, ctx: commands.Context[commands.Bot]) -> None:
        """Scan semi equipment stocks for refined targets."""
        from .refined_targets import SEMI_EQUIPMENT
        
        await ctx.send(f"🎯 Scanning {len(SEMI_EQUIPMENT)} semi equipment stocks...")
        
        try:
            lines = [
                "🎯 **REFINED TARGET SCAN** (Semi Equipment)",
                "═" * 40,
                "",
            ]
            
            for symbol in SEMI_EQUIPMENT:
                target = calculate_refined_target(symbol)
                
                # Determine emoji based on upside
                if target.upside_percent > 15:
                    emoji = "🟢"
                elif target.upside_percent > 5:
                    emoji = "🟡"
                else:
                    emoji = "🔴"
                
                # Flags
                flags = []
                if target.soxx_cap_applied:
                    flags.append("CAPPED")
                if target.geopolitical_multiplier < 1.0:
                    flags.append(f"GEO:{target.geopolitical_multiplier:.2f}x")
                if target.momentum_breakout:
                    flags.append("MOMENTUM")
                
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                
                lines.append(
                    f"{emoji} **{symbol}**: ${target.current_price:.2f} → ${target.final_target:.2f} "
                    f"({target.upside_percent:+.1f}%){flag_str}"
                )
            
            lines.append("")
            lines.append("Use `!target SYMBOL` for full breakdown")
            
            await ctx.send("\n".join(lines))
            
        except Exception as e:
            logger.error(f"Target scan error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    # === CYCLE RISK (Bearish Parameters) ===

    @commands.command(name="cycle", aliases=["cyclerisk", "bearish"])
    async def cycle_risk_cmd(self, ctx: commands.Context[commands.Bot], symbol: str = "") -> None:
        """
        Analyze semiconductor cycle risk (bearish parameters).
        
        Usage: !cycle LRCX or !cycle (scan all semis)
        
        Triggers:
        1. WFE Spending Reversion (Macro) - 0.80x if <$120B
        2. Inventory-to-Sales (Fundamental) - 0.85x if up >15% QoQ
        3. SOXX Correlation Crash (Market) - 200 DMA floor if high-beta crash
        """
        from concurrent.futures import ThreadPoolExecutor
        import asyncio
        
        def run_cycle_analysis(sym: str, base_target: float):
            return analyze_cycle_risk(sym, base_target)
        
        if not symbol:
            # Scan all semi equipment
            await ctx.send(f"🐻 **Scanning cycle risk for {len(SEMI_EQUIPMENT)} semi equipment stocks...**")
            
            try:
                lines = [
                    "🐻 **SEMICONDUCTOR CYCLE RISK SCAN**",
                    "═" * 40,
                    "",
                ]
                
                for sym in SEMI_EQUIPMENT:
                    # Get current price as base target
                    import yfinance as yf
                    ticker = yf.Ticker(sym)
                    info = ticker.info
                    current_price = info.get("currentPrice") or info.get("regularMarketPrice", 100)
                    target_mean = info.get("targetMeanPrice", current_price * 1.1)
                    
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor() as executor:
                        result = await loop.run_in_executor(
                            executor, run_cycle_analysis, sym, target_mean
                        )
                    
                    risk_emoji = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "SEVERE": "🔴"}.get(result.risk_level, "⚪")
                    
                    # Show triggers
                    triggers = []
                    if result.wfe_analysis.is_bearish:
                        triggers.append("WFE")
                    if result.inventory_analysis.is_warning:
                        triggers.append("INV")
                    if result.beta_analysis.is_crash_mode:
                        triggers.append("SOXX")
                    
                    trigger_str = f" [{', '.join(triggers)}]" if triggers else ""
                    
                    lines.append(
                        f"{risk_emoji} **{sym}**: {result.total_multiplier:.2f}x{trigger_str} "
                        f"(${current_price:.2f} → ${result.final_target:.2f})"
                    )
                
                lines.append("")
                lines.append("Use `!cycle SYMBOL` for full breakdown")
                lines.append("**Triggers:** WFE=Macro, INV=Inventory, SOXX=Beta Crash")
                
                await ctx.send("\n".join(lines))
                
            except Exception as e:
                logger.error(f"Cycle scan error: {e}")
                await ctx.send(f"❌ Error: {str(e)[:200]}")
        else:
            # Single symbol analysis
            symbol = symbol.upper()
            await ctx.send(f"🐻 Analyzing cycle risk for **{symbol}**...")
            
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                info = ticker.info
                current_price = info.get("currentPrice") or info.get("regularMarketPrice", 100)
                target_mean = info.get("targetMeanPrice", current_price * 1.1)
                
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as executor:
                    result = await loop.run_in_executor(
                        executor, run_cycle_analysis, symbol, target_mean
                    )
                
                await ctx.send(result.format_discord())
                
            except Exception as e:
                logger.error(f"Cycle risk error for {symbol}: {e}")
                await ctx.send(f"❌ Error: {str(e)[:200]}")

    # === BACKTESTER ===

    @commands.command(name="backtest", aliases=["bt", "test"])
    async def run_backtest(self, ctx: commands.Context[commands.Bot], days: int = 30, min_score: int = 70) -> None:
        """Backtest signal accuracy. Usage: !backtest or !backtest 60 75"""
        await ctx.send(f"📊 **Running {days}-day backtest** (min score: {min_score})... This takes 2-3 minutes.")
        
        try:
            result = await backtest_signals(
                days=days,
                sectors=None,  # All sectors
                min_score=min_score,
                hold_days=5,
                stop_loss_pct=-5.0,
                take_profit_pct=10.0,
            )
            
            await ctx.send(format_backtest_discord(result))
            
        except Exception as e:
            logger.error(f"Backtest error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:200]}")

    @commands.command(name="quickbt", aliases=["qbt"])
    async def quick_backtest(self, ctx: commands.Context[commands.Bot], days: int = 14) -> None:
        """Quick backtest summary."""
        await ctx.send(f"📊 Running quick {days}-day backtest...")
        
        try:
            result = await backtest_signals(
                days=days,
                min_score=70,
                hold_days=5,
            )
            
            await ctx.send(format_backtest_summary(result))
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="btcompare", aliases=["compare"])
    async def compare_thresholds(self, ctx: commands.Context[commands.Bot]) -> None:
        """Compare different signal thresholds."""
        await ctx.send("📊 **Comparing signal thresholds...** (3-5 minutes)")
        
        try:
            results = []
            for threshold in [60, 70, 80]:
                result = await backtest_signals(
                    days=30,
                    min_score=threshold,
                    hold_days=5,
                )
                results.append((threshold, result))
            
            lines = ["📊 **THRESHOLD COMPARISON** (30 days)", "═" * 40, ""]
            
            for threshold, r in results:
                if r.trades_taken > 0:
                    emoji = "✅" if r.win_rate >= 55 else "🟡" if r.win_rate >= 45 else "❌"
                    lines.append(
                        f"{emoji} **Score ≥ {threshold}:** {r.win_rate:.0f}% win | "
                        f"{r.total_pnl_pct:+.1f}% P&L | {r.trades_taken} trades | PF: {r.profit_factor:.1f}"
                    )
                else:
                    lines.append(f"⚪ **Score ≥ {threshold}:** No signals")
            
            lines.append("")
            lines.append("*Higher threshold = fewer but higher quality signals*")
            
            await ctx.send("\n".join(lines))
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @commands.command(name="cmds", aliases=["commands", "help2", "helpaudit", "riskhelp"])
    async def show_commands(self, ctx: commands.Context[commands.Bot]) -> None:
        """Show all available commands."""
        help_page1 = """
╔══════════════════════════════════════════╗
║       📋 INVESTMENT BOT COMMANDS         ║
╚══════════════════════════════════════════╝

**🔔 ALERTS**
┌─────────────────────────────────────────┐
│ `!alert SYMBOL target PRICE` │ Price target    │
│ `!alert SYMBOL stop PRICE`   │ Stop loss       │
│ `!alert SYMBOL rsi`          │ RSI oversold    │
│ `!alert SYMBOL overbought`   │ RSI overbought  │
│ `!alert SYMBOL insider`      │ Insider buying  │
│ `!alert SYMBOL move %`       │ % daily move    │
│ `!alerts`                    │ View all alerts │
│ `!removealert ID`            │ Remove alert    │
│ `!clearalerts SYMBOL`        │ Clear all       │
│ `!checkalerts`               │ Check now       │
└─────────────────────────────────────────┘

**📊 RISK DASHBOARD**
┌─────────────────────────────────────────┐
│ `!dashboard`    │ Full risk analysis      │
│ `!quickrisk`    │ Quick summary           │
└─────────────────────────────────────────┘

**📈 FULL ANALYSIS**
┌─────────────────────────────────────────┐
│ `!fullreport SYMBOL` │ ALL data sources  │
│ `!deep SYMBOL`       │ Enhanced entry    │
│ `!audit SYMBOL`      │ Risk audit        │
└─────────────────────────────────────────┘
"""
        help_page2 = """
**📉 MARKET DATA**
┌─────────────────────────────────────────┐
│ `!technicals SYMBOL` │ RSI, MACD, MAs      │
│ `!short SYMBOL`      │ Short interest      │
│ `!options SYMBOL`    │ Options flow        │
│ `!analysts SYMBOL`   │ Price targets       │
│ `!insider SYMBOL`    │ Insider trades      │
│ `!institutions SYM`  │ 13F holdings        │
│ `!earnings SYMBOL`   │ Earnings date       │
│ `!calendar`          │ Economic events     │
│ `!sector SYMBOL`     │ Sector correlation  │
│ `!news SYMBOL`       │ News sentiment      │
└─────────────────────────────────────────┘

**🎯 ENTRY & PREDICTIONS**
┌─────────────────────────────────────────┐
│ `!entry SYMBOL`   │ Quick entry check     │
│ `!scan`           │ Scan watchlist        │
│ `!predict SYMBOL` │ Verified prediction   │
│ `!predictscan`    │ Verified scan all     │
│ `!size SYM 10000` │ Position sizing       │
└─────────────────────────────────────────┘

**🎯 REFINED TARGETS** (Semi Equipment)
┌─────────────────────────────────────────┐
│ `!calibrate LRCX` │ Refined price target  │
│ `!calscan`        │ Scan LRCX/KLAC/ASML   │
└─────────────────────────────────────────┘

**🐻 CYCLE RISK** (Bearish Parameters)
┌─────────────────────────────────────────┐
│ `!cycle`          │ Scan all semi equip   │
│ `!cycle LRCX`     │ Full cycle breakdown  │
│ Triggers: WFE, Inventory, SOXX Beta     │
└─────────────────────────────────────────┘

**🔍 OPPORTUNITY SCANNER**
┌─────────────────────────────────────────┐
│ `!opportunities`  │ Full scan (120 stocks)│
│ `!opps`           │ Quick top 10          │
│ `!opps semis`     │ Semiconductors only   │
│ `!topopps`        │ STRONG_BUY only       │
└─────────────────────────────────────────┘

**📊 BACKTESTING**
┌─────────────────────────────────────────┐
│ `!backtest`       │ Full scanner backtest │
│ `!backtest 60 75` │ 60 days, score >= 75  │
│ `!symbolbt KLAC`  │ Single stock backtest │
│ `!quickbt`        │ Quick 14-day summary  │
│ `!btcompare`      │ Compare thresholds    │
└─────────────────────────────────────────┘

**📝 WATCHLIST**
┌─────────────────────────────────────────┐
│ `!watchlist`      │ View watchlist        │
│ `!permadd SYMBOL` │ Add to watchlist      │
│ `!permremove SYM` │ Remove from watchlist │
└─────────────────────────────────────────┘

**🧠 LEARNING SYSTEM**
┌─────────────────────────────────────────┐
│ `!learn`          │ Generate improvements │
│ `!suggestions`    │ View pending changes  │
│ `!approveall`     │ Apply all changes     │
│ `!journal`        │ Prediction stats      │
│ `!params`         │ Current parameters    │
└─────────────────────────────────────────┘
"""
        await ctx.send(help_page1)
        await ctx.send(help_page2)


async def setup_risk_commands(bot: "InvestmentBot", monitor: PermanentWatchlistMonitor) -> None:
    await bot.add_cog(RiskCommands(bot, monitor))
    logger.info("Risk audit commands registered")
