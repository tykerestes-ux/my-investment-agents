"""Backtester - Test signal accuracy against historical data."""

import asyncio
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
    exit_date: str
    exit_price: float
    pnl_percent: float
    win: bool
    hold_days: int
    entry_rsi: float | None
    entry_signals: list[str]


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    period_days: int
    total_signals: int
    trades_taken: int
    
    # Performance
    win_count: int
    loss_count: int
    win_rate: float
    
    # P&L
    avg_win_pct: float
    avg_loss_pct: float
    total_pnl_pct: float
    best_trade_pct: float
    worst_trade_pct: float
    
    # Risk metrics
    profit_factor: float  # gross profit / gross loss
    avg_hold_days: float
    
    # Individual trades
    trades: list[BacktestTrade]
    
    # Summary
    strategy_name: str
    symbols_scanned: int


async def backtest_signals(
    days: int = 30,
    sectors: list[str] | None = None,
    min_score: int = 70,
    hold_days: int = 5,
    stop_loss_pct: float = -5.0,
    take_profit_pct: float = 10.0,
) -> BacktestResult:
    """
    Backtest the opportunity scanner signals.
    
    Args:
        days: How many days back to test
        sectors: Which sectors to test (None = all)
        min_score: Minimum signal score to take trade
        hold_days: Max days to hold if no stop/target hit
        stop_loss_pct: Stop loss percentage (negative)
        take_profit_pct: Take profit percentage
    """
    
    # Get symbols to test
    if sectors:
        symbols = []
        for sector in sectors:
            symbols.extend(SCAN_UNIVERSE.get(sector.lower(), []))
    else:
        symbols = []
        for sector_symbols in SCAN_UNIVERSE.values():
            symbols.extend(sector_symbols)
    symbols = list(set(symbols))
    
    logger.info(f"Backtesting {len(symbols)} symbols over {days} days...")
    
    trades: list[BacktestTrade] = []
    total_signals = 0
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + hold_days + 30)  # Extra buffer for indicators
    
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date, interval="1d")
            
            if hist is None or len(hist) < 30:
                continue
            
            # Scan each day in the backtest period
            for i in range(30, len(hist) - hold_days):
                date_idx = hist.index[i]
                
                # Only check dates within our backtest window
                if date_idx < (end_date - timedelta(days=days)):
                    continue
                
                # Calculate indicators as of this date
                hist_to_date = hist.iloc[:i+1]
                
                rsi = calculate_rsi(hist_to_date['Close'])
                macd_line, signal_line, macd_hist = calculate_macd(hist_to_date['Close'])
                
                # Calculate score (simplified version of opportunity scanner)
                score = 50
                signals = []
                
                # RSI
                if rsi and rsi < 30:
                    score += 25
                    signals.append(f"RSI oversold ({rsi:.0f})")
                elif rsi and rsi < 40:
                    score += 15
                    signals.append(f"RSI low ({rsi:.0f})")
                
                # MACD
                if macd_hist and macd_hist > 0:
                    score += 10
                    signals.append("MACD bullish")
                if macd_line and signal_line and macd_line > signal_line:
                    score += 10
                    signals.append("MACD crossover")
                
                # 5-day pullback
                if i >= 5:
                    price_5d_ago = hist_to_date['Close'].iloc[-5]
                    current = hist_to_date['Close'].iloc[-1]
                    change_5d = ((current - price_5d_ago) / price_5d_ago) * 100
                    
                    if -5 < change_5d < 0:
                        score += 10
                        signals.append("Pullback")
                
                # Volume surge
                if i >= 10:
                    avg_vol = hist_to_date['Volume'].iloc[-10:-1].mean()
                    current_vol = hist_to_date['Volume'].iloc[-1]
                    if avg_vol > 0 and current_vol > avg_vol * 1.5:
                        if hist_to_date['Close'].iloc[-1] > hist_to_date['Close'].iloc[-2]:
                            score += 10
                            signals.append("Volume surge")
                
                # Check if signal meets threshold
                if score >= min_score:
                    total_signals += 1
                    
                    entry_price = hist['Close'].iloc[i]
                    entry_date = date_idx.strftime('%Y-%m-%d')
                    
                    # Simulate the trade
                    exit_price = entry_price
                    exit_idx = i + 1
                    exit_reason = "hold"
                    
                    for j in range(i + 1, min(i + hold_days + 1, len(hist))):
                        day_high = hist['High'].iloc[j]
                        day_low = hist['Low'].iloc[j]
                        day_close = hist['Close'].iloc[j]
                        
                        # Check stop loss (using low)
                        loss_pct = ((day_low - entry_price) / entry_price) * 100
                        if loss_pct <= stop_loss_pct:
                            exit_price = entry_price * (1 + stop_loss_pct / 100)
                            exit_idx = j
                            exit_reason = "stop"
                            break
                        
                        # Check take profit (using high)
                        gain_pct = ((day_high - entry_price) / entry_price) * 100
                        if gain_pct >= take_profit_pct:
                            exit_price = entry_price * (1 + take_profit_pct / 100)
                            exit_idx = j
                            exit_reason = "target"
                            break
                        
                        exit_price = day_close
                        exit_idx = j
                    
                    exit_date = hist.index[exit_idx].strftime('%Y-%m-%d')
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                    
                    trades.append(BacktestTrade(
                        symbol=symbol,
                        entry_date=entry_date,
                        entry_price=entry_price,
                        exit_date=exit_date,
                        exit_price=exit_price,
                        pnl_percent=pnl_pct,
                        win=pnl_pct > 0,
                        hold_days=exit_idx - i,
                        entry_rsi=rsi,
                        entry_signals=signals,
                    ))
            
            await asyncio.sleep(0.2)  # Rate limiting
            
        except Exception as e:
            logger.debug(f"Error backtesting {symbol}: {e}")
    
    # Calculate results
    if not trades:
        return BacktestResult(
            period_days=days,
            total_signals=total_signals,
            trades_taken=0,
            win_count=0,
            loss_count=0,
            win_rate=0,
            avg_win_pct=0,
            avg_loss_pct=0,
            total_pnl_pct=0,
            best_trade_pct=0,
            worst_trade_pct=0,
            profit_factor=0,
            avg_hold_days=0,
            trades=[],
            strategy_name=f"Score >= {min_score}",
            symbols_scanned=len(symbols),
        )
    
    wins = [t for t in trades if t.win]
    losses = [t for t in trades if not t.win]
    
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / len(trades)) * 100 if trades else 0
    
    avg_win = sum(t.pnl_percent for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl_percent for t in losses) / len(losses) if losses else 0
    
    total_pnl = sum(t.pnl_percent for t in trades)
    
    gross_profit = sum(t.pnl_percent for t in wins)
    gross_loss = abs(sum(t.pnl_percent for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    avg_hold = sum(t.hold_days for t in trades) / len(trades)
    
    return BacktestResult(
        period_days=days,
        total_signals=total_signals,
        trades_taken=len(trades),
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_rate,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        total_pnl_pct=total_pnl,
        best_trade_pct=max(t.pnl_percent for t in trades),
        worst_trade_pct=min(t.pnl_percent for t in trades),
        profit_factor=profit_factor,
        avg_hold_days=avg_hold,
        trades=trades,
        strategy_name=f"Score >= {min_score}",
        symbols_scanned=len(symbols),
    )


def format_backtest_discord(result: BacktestResult) -> str:
    """Format backtest results for Discord."""
    
    if result.trades_taken == 0:
        return f"📊 **Backtest Results** ({result.period_days} days)\n\nNo signals generated with current criteria."
    
    # Determine grade
    if result.win_rate >= 65 and result.profit_factor >= 2:
        grade = "A"
        grade_emoji = "🏆"
    elif result.win_rate >= 55 and result.profit_factor >= 1.5:
        grade = "B"
        grade_emoji = "✅"
    elif result.win_rate >= 50 and result.profit_factor >= 1:
        grade = "C"
        grade_emoji = "🟡"
    else:
        grade = "D"
        grade_emoji = "⚠️"
    
    lines = [
        f"📊 **BACKTEST RESULTS** - {result.strategy_name}",
        f"{grade_emoji} **Grade: {grade}**",
        "═" * 40,
        "",
        f"**Period:** {result.period_days} days | **Symbols:** {result.symbols_scanned}",
        "",
        "**📈 Performance:**",
        f"├─ Win Rate: **{result.win_rate:.1f}%** ({result.win_count}W / {result.loss_count}L)",
        f"├─ Total P&L: **{result.total_pnl_pct:+.1f}%**",
        f"├─ Avg Win: +{result.avg_win_pct:.1f}% | Avg Loss: {result.avg_loss_pct:.1f}%",
        f"├─ Best: +{result.best_trade_pct:.1f}% | Worst: {result.worst_trade_pct:.1f}%",
        f"├─ Profit Factor: **{result.profit_factor:.2f}**",
        f"└─ Avg Hold: {result.avg_hold_days:.1f} days",
        "",
    ]
    
    # Top 5 winners
    if result.trades:
        winners = sorted([t for t in result.trades if t.win], key=lambda x: x.pnl_percent, reverse=True)[:5]
        if winners:
            lines.append("**🏆 Top Winners:**")
            for t in winners:
                lines.append(f"  {t.symbol}: +{t.pnl_percent:.1f}% ({t.entry_date})")
        
        lines.append("")
        
        # Recent signals
        recent = sorted(result.trades, key=lambda x: x.entry_date, reverse=True)[:5]
        lines.append("**📅 Recent Signals:**")
        for t in recent:
            emoji = "✅" if t.win else "❌"
            lines.append(f"  {emoji} {t.symbol}: {t.pnl_percent:+.1f}% ({t.entry_date})")
    
    lines.append("")
    lines.append("*Backtest assumes 5-day hold, 5% stop, 10% target*")
    
    return "\n".join(lines)


def format_backtest_summary(result: BacktestResult) -> str:
    """Short summary for quick view."""
    if result.trades_taken == 0:
        return "No signals in period."
    
    emoji = "✅" if result.win_rate >= 55 else "🟡" if result.win_rate >= 45 else "❌"
    
    return (
        f"{emoji} **{result.period_days}d Backtest:** "
        f"{result.win_rate:.0f}% win rate | "
        f"{result.total_pnl_pct:+.1f}% total | "
        f"PF: {result.profit_factor:.1f} | "
        f"{result.trades_taken} trades"
    )
