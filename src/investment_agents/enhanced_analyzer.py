"""Enhanced Entry Analyzer - Integrates all 6 advanced filters."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .entry_signals import EntrySignalAnalyzer, EntrySignal, EntryAnalysis, EntryCondition
from .earnings_calendar import get_earnings_date, check_earnings_lockout, EarningsInfo
from .sector_correlation import analyze_sector_correlation, get_sector, SectorAnalysis
from .multi_timeframe import get_multi_timeframe_data, MultiTimeframeData
from .news_sentiment import analyze_news_sentiment, NewsAnalysis
from .backtest import run_quick_backtest, BacktestResult
from .position_sizing import calculate_position_size, PositionSize, RiskLevel
from .permanent_watchlist import get_permanent_symbols

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


@dataclass
class EnhancedAnalysis:
    """Complete enhanced analysis with all 6 filters."""
    symbol: str
    timestamp: datetime
    
    # Base analysis
    base_analysis: EntryAnalysis
    
    # Enhanced filters
    earnings_info: EarningsInfo
    sector_analysis: SectorAnalysis
    timeframe_data: MultiTimeframeData
    news_analysis: NewsAnalysis
    backtest_result: BacktestResult | None
    position_sizing: PositionSize
    
    # Final recommendation
    final_signal: EntrySignal
    final_confidence: int
    risk_flags: list[str]
    enhanced_recommendation: str
    
    def to_discord_message(self) -> str:
        """Format enhanced analysis for Discord."""
        # Signal emoji
        signal_emojis = {
            EntrySignal.STRONG_BUY: "🟢🟢🟢",
            EntrySignal.BUY: "🟢",
            EntrySignal.WAIT: "🟡",
            EntrySignal.NO_ENTRY: "🔴",
        }
        emoji = signal_emojis.get(self.final_signal, "❓")
        
        lines = [
            f"{emoji} **ENHANCED ANALYSIS: {self.symbol}**",
            f"Final Signal: **{self.final_signal.value.upper()}** ({self.final_confidence}%)",
            "",
        ]
        
        # Risk flags
        if self.risk_flags:
            lines.append("**⚠️ Risk Flags:**")
            for flag in self.risk_flags:
                lines.append(f"• {flag}")
            lines.append("")
        
        # Position sizing
        lines.append(f"**Position Size:** {self.position_sizing.adjusted_position_percent:.1f}% of portfolio")
        if self.base_analysis.entry_price:
            lines.append(f"**Entry:** ${self.base_analysis.entry_price:.2f}")
        if self.base_analysis.stop_loss:
            lines.append(f"**Stop:** ${self.base_analysis.stop_loss:.2f} ({self.position_sizing.recommended_stop_percent}%)")
        if self.base_analysis.target_price:
            lines.append(f"**Target:** ${self.base_analysis.target_price:.2f}")
        lines.append("")
        
        # Filter summary
        lines.append("**Filter Checks:**")
        
        # Earnings
        earn_emoji = "❌" if self.earnings_info.is_lockout else "✅"
        if self.earnings_info.days_until_earnings is not None:
            lines.append(f"{earn_emoji} Earnings: {self.earnings_info.days_until_earnings}d away")
        else:
            lines.append(f"{earn_emoji} Earnings: Not scheduled")
        
        # Sector
        sect_emoji = "⚠️" if self.sector_analysis.is_crowded else "✅"
        lines.append(f"{sect_emoji} Sector: {self.sector_analysis.sector or 'Unknown'}")
        
        # Timeframe
        tf_emoji = "✅" if self.timeframe_data.all_timeframes_aligned else "⚠️"
        lines.append(f"{tf_emoji} Timeframes: {self.timeframe_data.alignment_score}/4 aligned")
        
        # News
        news_emoji = "❌" if self.news_analysis.should_pause else "✅"
        lines.append(f"{news_emoji} News: Score {self.news_analysis.sentiment_score:+d}")
        
        # Backtest
        if self.backtest_result and self.backtest_result.total_trades > 0:
            bt_emoji = "✅" if self.backtest_result.win_rate >= 60 else "⚠️"
            lines.append(f"{bt_emoji} Backtest: {self.backtest_result.win_rate:.0f}% win rate")
        
        lines.append("")
        lines.append(f"**Recommendation:** {self.enhanced_recommendation}")
        
        return "\n".join(lines)


class EnhancedEntryAnalyzer:
    """Entry analyzer with all 6 advanced filters integrated."""
    
    def __init__(self) -> None:
        self.base_analyzer = EntrySignalAnalyzer()
    
    async def analyze(
        self,
        symbol: str,
        all_signals: dict[str, str] | None = None,
        run_backtest: bool = False,
        account_size: float = 10000,
        risk_level: RiskLevel = RiskLevel.MODERATE,
    ) -> EnhancedAnalysis:
        """Run complete enhanced analysis on a symbol."""
        symbol = symbol.upper()
        risk_flags: list[str] = []
        
        loop = asyncio.get_event_loop()
        
        # 1. Run base analysis
        base_analysis = await self.base_analyzer.analyze_entry(symbol)
        
        # 2. Check earnings calendar
        earnings_info = await loop.run_in_executor(_executor, get_earnings_date, symbol)
        if earnings_info.is_lockout:
            risk_flags.append(f"EARNINGS LOCKOUT: {earnings_info.lockout_reason}")
        
        # 3. Check sector correlation
        if all_signals is None:
            all_signals = {symbol: base_analysis.signal.value}
        sector_analysis = analyze_sector_correlation(symbol, all_signals)
        if sector_analysis.is_crowded:
            risk_flags.append(f"SECTOR CROWDING: {sector_analysis.sector}")
        
        # 4. Check multi-timeframe alignment
        timeframe_data = await loop.run_in_executor(_executor, get_multi_timeframe_data, symbol)
        if not timeframe_data.all_timeframes_aligned:
            if timeframe_data.alignment_score <= 1:
                risk_flags.append(f"POOR TIMEFRAME ALIGNMENT: Only {timeframe_data.alignment_score}/4")
        
        # 5. Check news sentiment
        news_analysis = await loop.run_in_executor(_executor, analyze_news_sentiment, symbol)
        if news_analysis.should_pause:
            risk_flags.append(f"NEGATIVE NEWS: {news_analysis.warning_message}")
        
        # 6. Run backtest (optional, slower)
        backtest_result = None
        if run_backtest:
            backtest_result = await loop.run_in_executor(_executor, run_quick_backtest, symbol, 90)
            if backtest_result.total_trades > 0 and backtest_result.win_rate < 50:
                risk_flags.append(f"WEAK BACKTEST: {backtest_result.win_rate:.0f}% win rate")
        
        # Calculate final signal (adjusted for risk flags)
        final_signal = base_analysis.signal
        final_confidence = base_analysis.confidence
        
        # Degrade signal based on risk flags
        critical_flags = [f for f in risk_flags if "LOCKOUT" in f or "NEGATIVE NEWS" in f]
        moderate_flags = [f for f in risk_flags if f not in critical_flags]
        
        if critical_flags:
            # Critical flags downgrade to NO_ENTRY
            if final_signal in [EntrySignal.STRONG_BUY, EntrySignal.BUY]:
                final_signal = EntrySignal.WAIT
                final_confidence = min(final_confidence, 50)
        
        if len(moderate_flags) >= 2:
            # Multiple moderate flags downgrade one level
            if final_signal == EntrySignal.STRONG_BUY:
                final_signal = EntrySignal.BUY
                final_confidence = min(final_confidence, 75)
            elif final_signal == EntrySignal.BUY:
                final_signal = EntrySignal.WAIT
                final_confidence = min(final_confidence, 60)
        
        # Boost signal if all timeframes aligned and no risk flags
        if not risk_flags and timeframe_data.all_timeframes_aligned:
            final_confidence = min(100, final_confidence + 5)
        
        # Calculate position sizing
        position_sizing = calculate_position_size(
            symbol=symbol,
            confidence=final_confidence,
            signal_type=final_signal.value.upper(),
            account_size=account_size,
            earnings_lockout=earnings_info.is_lockout,
            sector_crowding=sector_analysis.is_crowded,
            news_negative=news_analysis.should_pause,
            timeframe_alignment_score=timeframe_data.alignment_score,
            risk_level=risk_level,
        )
        
        # Generate enhanced recommendation
        if final_signal == EntrySignal.STRONG_BUY and not risk_flags:
            enhanced_recommendation = (
                f"STRONG ENTRY - All filters passed. "
                f"Position: {position_sizing.adjusted_position_percent:.1f}%"
            )
        elif final_signal == EntrySignal.BUY:
            if risk_flags:
                enhanced_recommendation = (
                    f"CAUTIOUS ENTRY - {len(risk_flags)} risk flag(s). "
                    f"Reduced position: {position_sizing.adjusted_position_percent:.1f}%"
                )
            else:
                enhanced_recommendation = (
                    f"GOOD ENTRY - Most conditions met. "
                    f"Position: {position_sizing.adjusted_position_percent:.1f}%"
                )
        elif final_signal == EntrySignal.WAIT:
            enhanced_recommendation = (
                f"WAIT - {len(risk_flags)} risk flag(s) detected. "
                f"Monitor for improvement."
            )
        else:
            enhanced_recommendation = "NO ENTRY - Conditions unfavorable. Preserve capital."
        
        return EnhancedAnalysis(
            symbol=symbol,
            timestamp=datetime.now(),
            base_analysis=base_analysis,
            earnings_info=earnings_info,
            sector_analysis=sector_analysis,
            timeframe_data=timeframe_data,
            news_analysis=news_analysis,
            backtest_result=backtest_result,
            position_sizing=position_sizing,
            final_signal=final_signal,
            final_confidence=final_confidence,
            risk_flags=risk_flags,
            enhanced_recommendation=enhanced_recommendation,
        )
    
    async def scan_enhanced(
        self,
        symbols: list[str] | None = None,
        run_backtest: bool = False,
        account_size: float = 10000,
    ) -> list[EnhancedAnalysis]:
        """Scan multiple symbols with enhanced analysis."""
        if symbols is None:
            symbols = get_permanent_symbols()
        
        # First pass: get all base signals for sector correlation
        all_signals: dict[str, str] = {}
        for symbol in symbols:
            try:
                base = await self.base_analyzer.analyze_entry(symbol)
                all_signals[symbol] = base.signal.value
            except Exception:
                pass
            await asyncio.sleep(0.3)
        
        # Second pass: run enhanced analysis
        results: list[EnhancedAnalysis] = []
        for symbol in symbols:
            try:
                analysis = await self.analyze(
                    symbol,
                    all_signals=all_signals,
                    run_backtest=run_backtest,
                    account_size=account_size,
                )
                results.append(analysis)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Enhanced analysis error for {symbol}: {e}")
        
        # Sort by final confidence
        results.sort(key=lambda x: x.final_confidence, reverse=True)
        return results


async def enhanced_analyze(symbol: str, run_backtest: bool = False) -> EnhancedAnalysis:
    """Convenience function for single symbol enhanced analysis."""
    analyzer = EnhancedEntryAnalyzer()
    return await analyzer.analyze(symbol, run_backtest=run_backtest)
