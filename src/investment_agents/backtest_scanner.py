"""Backtest Scanner - Test signal accuracy on historical data."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

import yfinance as yf

from .technical_indicators import calculate_rsi, calculate_macd
from .opportunity_scanner import SCAN_UNIVERSE

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """A single backtested trade."""
    symbol: str
    entry_date: str
    entry_price: float
    entry_score: int
    entry_type: str  # STRONG_BUY, BUY, SPECULATIVE
    signals_at_entry: list[str]
    
    # Outcomes
    price_1d: float | None = None
    price_3d: float | None = None
    price_5d: float | None = None
    price_10d: float | None = None
    
    pnl_1d: float | None = None
    pnl_3d: float | None = None
    pnl_5d: float | None = None
    pnl_10d: float | None = None
    
    max_gain: float | None = None
    max_drawdown: float | None = None
    
    win_1d: bool = False
    win_3d: bool = False
    win_5d: bool = False


@dataclass
class BacktestResult:
    """Aggregated backtest results."""
    period_start: str
    period_end: str
    total_signals: int
    
    # By entry type
    strong_buy_count: int
    buy_count: int
    speculative_count: int
    
    # Win rates
    win_rate_1d: float
    win_rate_3d: float
    win_rate_5d: float
    
    # Average returns
    avg_return_1d: float
    avg_return_3d: float
    avg_return_5d: float
    avg_return_10d: float
    
    # Best/Worst
    best_trade: BacktestTrade | None
    worst_trade: BacktestTrade | None
    
    # By entry type performance
    strong_buy_win_rate: float
    buy_win_rate: float
    
    # Risk metrics
    avg_max_gain: float
    avg_max_drawdown: float
    
    # All trades for detail
    trades: list[BacktestTrade]


def run_backtest(
    days_back: int = 30,
    min_score: int = 60,
    symbols: list[str] | None = None,
) -> BacktestResult:
    """Run backtest on historical signals."""
    
    logger.info(f"Running backtest for past {days_back} days...")
    
    # Get symbols to test
    if symbols is None:
        symbols = []
        for sector_symbols in SCAN_UNIVERSE.values():
            symbols.extend(sector_symbols)
        symbols = list(set(symbols))
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back + 15)  # Extra days for outcomes
    
    trades: list[BacktestTrade] = []
    
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date, interval="1d")
            
            if hist is None or len(hist) < 20:
                continue
            
            # Scan each day for signals
            for i in range(14, len(hist) - 10):  # Need 14 days before for RSI, 10 after for outcomes
                date = hist.index[i]
                
                # Skip if too recent (need outcome data)
                if (end_date - date.to_pydatetime().replace(tzinfo=None)).days < 10:
                    continue
                
                # Calculate signals for this day
                price = hist['Close'].iloc[i]
                hist_to_date = hist.iloc[:i+1]
                
                # RSI
                rsi = calculate_rsi(hist_to_date['Close'])
                
                # MACD
                macd_line, signal_line, macd_hist = calculate_macd(hist_to_date['Close'])
                
                # Score the setup
                score = 50
                signals = []
                
                # RSI signals
                if rsi and rsi < 30:
                    score += 25
                    signals.append(f"RSI oversold ({rsi:.0f})")
                elif rsi and rsi < 40:
                    score += 15
                    signals.append(f"RSI low ({rsi:.0f})")
                elif rsi and rsi > 70:
                    score -= 15
                
                # MACD
                if macd_hist and macd_hist > 0:
                    score += 10
                    signals.append("MACD bullish")
                if macd_line and signal_line and macd_line > signal_line:
                    score += 10
                    signals.append("MACD crossover")
                
                # 5-day pullback
                if i >= 5:
                    price_5d_ago = hist['Close'].iloc[i-5]
                    change_5d = ((price - price_5d_ago) / price_5d_ago) * 100
                    if -10 < change_5d < -3:
                        score += 10
                        signals.append("Pullback")
                
                # Volume surge
                if i >= 10:
                    avg_vol = hist['Volume'].iloc[i-10:i].mean()
                    current_vol = hist['Volume'].iloc[i]
                    if avg_vol > 0 and current_vol > avg_vol * 1.5:
                        daily_change = ((price - hist['Close'].iloc[i-1]) / hist['Close'].iloc[i-1]) * 100
                        if daily_change > 0:
                            score += 10
                            signals.append("Volume surge")
                
                # Skip if below threshold
                if score < min_score or not signals:
                    continue
                
                # Determine entry type
                if score >= 80 and len(signals) >= 3:
                    entry_type = "STRONG_BUY"
                elif score >= 70:
                    entry_type = "BUY"
                else:
                    entry_type = "SPECULATIVE"
                
                # Calculate outcomes
                price_1d = hist['Close'].iloc[i+1] if i+1 < len(hist) else None
                price_3d = hist['Close'].iloc[i+3] if i+3 < len(hist) else None
                price_5d = hist['Close'].iloc[i+5] if i+5 < len(hist) else None
                price_10d = hist['Close'].iloc[i+10] if i+10 < len(hist) else None
                
                pnl_1d = ((price_1d - price) / price * 100) if price_1d else None
                pnl_3d = ((price_3d - price) / price * 100) if price_3d else None
                pnl_5d = ((price_5d - price) / price * 100) if price_5d else None
                pnl_10d = ((price_10d - price) / price * 100) if price_10d else None
                
                # Max gain/drawdown in 10 days
                future_prices = hist['Close'].iloc[i+1:i+11]
                max_price = future_prices.max() if len(future_prices) > 0 else price
                min_price = future_prices.min() if len(future_prices) > 0 else price
                max_gain = ((max_price - price) / price * 100)
                max_drawdown = ((min_price - price) / price * 100)
                
                trade = BacktestTrade(
                    symbol=symbol,
                    entry_date=date.strftime("%Y-%m-%d"),
                    entry_price=price,
                    entry_score=score,
                    entry_type=entry_type,
                    signals_at_entry=signals,
                    price_1d=price_1d,
                    price_3d=price_3d,
                    price_5d=price_5d,
                    price_10d=price_10d,
                    pnl_1d=pnl_1d,
                    pnl_3d=pnl_3d,
                    pnl_5d=pnl_5d,
                    pnl_10d=pnl_10d,
                    max_gain=max_gain,
                    max_drawdown=max_drawdown,
                    win_1d=pnl_1d > 0 if pnl_1d else False,
                    win_3d=pnl_3d > 0 if pnl_3d else False,
                    win_5d=pnl_5d > 0 if pnl_5d else False,
                )
                
                trades.append(trade)
            
        except Exception as e:
            logger.debug(f"Backtest error for {symbol}: {e}")
    
    # Aggregate results
    if not trades:
        return BacktestResult(
            period_start=(end_date - timedelta(days=days_back)).strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            total_signals=0,
            strong_buy_count=0,
            buy_count=0,
            speculative_count=0,
            win_rate_1d=0,
            win_rate_3d=0,
            win_rate_5d=0,
            avg_return_1d=0,
            avg_return_3d=0,
            avg_return_5d=0,
            avg_return_10d=0,
            best_trade=None,
            worst_trade=None,
            strong_buy_win_rate=0,
            buy_win_rate=0,
            avg_max_gain=0,
            avg_max_drawdown=0,
            trades=[],
        )
    
    # Count by type
    strong_buys = [t for t in trades if t.entry_type == "STRONG_BUY"]
    buys = [t for t in trades if t.entry_type == "BUY"]
    specs = [t for t in trades if t.entry_type == "SPECULATIVE"]
    
    # Win rates
    win_1d = sum(1 for t in trades if t.win_1d) / len(trades) * 100
    win_3d = sum(1 for t in trades if t.win_3d) / len(trades) * 100
    win_5d = sum(1 for t in trades if t.win_5d) / len(trades) * 100
    
    # Average returns
    avg_1d = sum(t.pnl_1d for t in trades if t.pnl_1d) / len([t for t in trades if t.pnl_1d])
    avg_3d = sum(t.pnl_3d for t in trades if t.pnl_3d) / len([t for t in trades if t.pnl_3d])
    avg_5d = sum(t.pnl_5d for t in trades if t.pnl_5d) / len([t for t in trades if t.pnl_5d])
    avg_10d = sum(t.pnl_10d for t in trades if t.pnl_10d) / len([t for t in trades if t.pnl_10d]) if any(t.pnl_10d for t in trades) else 0
    
    # Best/Worst
    best = max(trades, key=lambda t: t.pnl_5d or 0)
    worst = min(trades, key=lambda t: t.pnl_5d or 0)
    
    # Win rate by type
    sb_win = sum(1 for t in strong_buys if t.win_5d) / len(strong_buys) * 100 if strong_buys else 0
    buy_win = sum(1 for t in buys if t.win_5d) / len(buys) * 100 if buys else 0
    
    # Risk metrics
    avg_max_gain = sum(t.max_gain for t in trades if t.max_gain) / len(trades)
    avg_max_dd = sum(t.max_drawdown for t in trades if t.max_drawdown) / len(trades)
    
    return BacktestResult(
        period_start=(end_date - timedelta(days=days_back)).strftime("%Y-%m-%d"),
        period_end=end_date.strftime("%Y-%m-%d"),
        total_signals=len(trades),
        strong_buy_count=len(strong_buys),
        buy_count=len(buys),
        speculative_count=len(specs),
        win_rate_1d=win_1d,
        win_rate_3d=win_3d,
        win_rate_5d=win_5d,
        avg_return_1d=avg_1d,
        avg_return_3d=avg_3d,
        avg_return_5d=avg_5d,
        avg_return_10d=avg_10d,
        best_trade=best,
        worst_trade=worst,
        strong_buy_win_rate=sb_win,
        buy_win_rate=buy_win,
        avg_max_gain=avg_max_gain,
        avg_max_drawdown=avg_max_dd,
        trades=trades,
    )


def format_backtest_discord(result: BacktestResult) -> list[str]:
    """Format backtest results for Discord."""
    
    if result.total_signals == 0:
        return ["📭 No signals found in backtest period."]
    
    messages = []
    
    # Header
    header = f"""
📊 **BACKTEST RESULTS**
═══════════════════════════════════════════
Period: {result.period_start} to {result.period_end}
Total Signals: **{result.total_signals}**
├─ STRONG_BUY: {result.strong_buy_count}
├─ BUY: {result.buy_count}
└─ SPECULATIVE: {result.speculative_count}

**📈 WIN RATES:**
┌─────────────────────────────────────────┐
│ 1-Day:  **{result.win_rate_1d:.1f}%**                       │
│ 3-Day:  **{result.win_rate_3d:.1f}%**                       │
│ 5-Day:  **{result.win_rate_5d:.1f}%**                       │
└─────────────────────────────────────────┘

**💰 AVERAGE RETURNS:**
┌─────────────────────────────────────────┐
│ 1-Day:  **{result.avg_return_1d:+.2f}%**                     │
│ 3-Day:  **{result.avg_return_3d:+.2f}%**                     │
│ 5-Day:  **{result.avg_return_5d:+.2f}%**                     │
│ 10-Day: **{result.avg_return_10d:+.2f}%**                    │
└─────────────────────────────────────────┘
"""
    messages.append(header)
    
    # Performance by type
    perf = f"""
**🎯 BY SIGNAL TYPE (5-Day Win Rate):**
├─ STRONG_BUY: **{result.strong_buy_win_rate:.1f}%** ({result.strong_buy_count} signals)
└─ BUY: **{result.buy_win_rate:.1f}%** ({result.buy_count} signals)

**📉 RISK METRICS:**
├─ Avg Max Gain:     **{result.avg_max_gain:+.2f}%**
└─ Avg Max Drawdown: **{result.avg_max_drawdown:+.2f}%**
"""
    
    # Best/Worst trades
    if result.best_trade:
        perf += f"""
**🏆 BEST TRADE:**
{result.best_trade.symbol} on {result.best_trade.entry_date}
├─ Entry: ${result.best_trade.entry_price:.2f} (Score: {result.best_trade.entry_score})
├─ 5-Day P&L: **{result.best_trade.pnl_5d:+.2f}%**
└─ Signals: {', '.join(result.best_trade.signals_at_entry[:3])}
"""
    
    if result.worst_trade:
        perf += f"""
**📉 WORST TRADE:**
{result.worst_trade.symbol} on {result.worst_trade.entry_date}
├─ Entry: ${result.worst_trade.entry_price:.2f} (Score: {result.worst_trade.entry_score})
├─ 5-Day P&L: **{result.worst_trade.pnl_5d:+.2f}%**
└─ Signals: {', '.join(result.worst_trade.signals_at_entry[:3])}
"""
    
    messages.append(perf)
    
    # Interpretation
    if result.win_rate_5d >= 60:
        verdict = "✅ **SIGNALS PERFORMING WELL** - 5-day win rate above 60%"
    elif result.win_rate_5d >= 50:
        verdict = "🟡 **SIGNALS NEUTRAL** - Win rate near 50%, focus on STRONG_BUY only"
    else:
        verdict = "⚠️ **SIGNALS UNDERPERFORMING** - Consider tightening criteria"
    
    if result.strong_buy_win_rate > result.buy_win_rate + 10:
        verdict += "\n💡 **STRONG_BUY signals outperform** - prioritize these"
    
    messages.append(verdict)
    
    return messages


def format_backtest_summary(result: BacktestResult) -> str:
    """Quick summary of backtest."""
    
    if result.total_signals == 0:
        return "📭 No signals in backtest period."
    
    return f"""
📊 **Backtest: {result.period_start} to {result.period_end}**
• {result.total_signals} signals ({result.strong_buy_count} STRONG_BUY, {result.buy_count} BUY)
• Win Rate: 1D={result.win_rate_1d:.0f}% | 3D={result.win_rate_3d:.0f}% | 5D={result.win_rate_5d:.0f}%
• Avg Return: 5D={result.avg_return_5d:+.2f}%
• STRONG_BUY win rate: {result.strong_buy_win_rate:.0f}%
"""
