"""Backtest Mode - Simulate past predictions to validate filters."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """A single backtested trade."""
    symbol: str
    entry_date: datetime
    entry_price: float
    exit_date: datetime
    exit_price: float
    pnl_percent: float
    was_profitable: bool
    signal_type: str
    confidence: int
    conditions_at_entry: dict[str, bool]


@dataclass
class BacktestResult:
    """Complete backtest results."""
    symbol: str
    period_days: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl_percent: float
    avg_pnl_percent: float
    max_win_percent: float
    max_loss_percent: float
    sharpe_ratio: float | None
    trades: list[BacktestTrade] = field(default_factory=list)
    
    def to_discord_message(self) -> str:
        """Format backtest results for Discord."""
        emoji = "🟢" if self.win_rate >= 60 else "🟡" if self.win_rate >= 50 else "🔴"
        
        lines = [
            f"{emoji} **Backtest Results: {self.symbol}**",
            f"Period: Last {self.period_days} days",
            "",
            f"**Performance:**",
            f"• Total Trades: {self.total_trades}",
            f"• Win Rate: {self.win_rate:.1f}%",
            f"• Total P&L: {self.total_pnl_percent:+.1f}%",
            f"• Avg P&L per Trade: {self.avg_pnl_percent:+.2f}%",
            f"• Max Win: {self.max_win_percent:+.1f}%",
            f"• Max Loss: {self.max_loss_percent:+.1f}%",
        ]
        
        if self.sharpe_ratio is not None:
            lines.append(f"• Sharpe Ratio: {self.sharpe_ratio:.2f}")
        
        # Show recent trades
        if self.trades:
            lines.append("\n**Recent Trades:**")
            for trade in self.trades[-5:]:
                t_emoji = "✅" if trade.was_profitable else "❌"
                lines.append(
                    f"{t_emoji} {trade.entry_date.strftime('%m/%d')}: "
                    f"{trade.pnl_percent:+.1f}% ({trade.signal_type})"
                )
        
        return "\n".join(lines)


class Backtester:
    """Runs backtests on historical data to validate trading signals."""
    
    def __init__(self, holding_period_days: int = 5) -> None:
        self.holding_period = holding_period_days
    
    def run_backtest(
        self,
        symbol: str,
        days: int = 90,
    ) -> BacktestResult:
        """Run backtest for a symbol over specified period.
        
        Simulates our entry conditions on historical data.
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Get historical data with extra buffer for calculations
            df = ticker.history(period=f"{days + 60}d", interval="1d")
            
            if df is None or len(df) < 60:
                return self._empty_result(symbol, days)
            
            trades: list[BacktestTrade] = []
            
            # Calculate indicators for entire history
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA50'] = df['Close'].rolling(window=50).mean()
            df['Volume_Avg'] = df['Volume'].rolling(window=10).mean()
            df['Price_7d_Change'] = df['Close'].pct_change(periods=5) * 100
            
            # Calculate daily VWAP approximation (using typical price)
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP_Approx'] = (df['Typical_Price'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
            
            # Start from day 60 to have enough history
            df = df.iloc[60:]
            
            # Limit to requested period
            if len(df) > days:
                df = df.tail(days)
            
            # Simulate entries
            i = 0
            while i < len(df) - self.holding_period:
                row = df.iloc[i]
                
                # Check entry conditions (simplified version of our filters)
                conditions = {
                    "above_vwap": row['Close'] > row['VWAP_Approx'] if pd.notna(row['VWAP_Approx']) else False,
                    "above_ma20": row['Close'] > row['MA20'] if pd.notna(row['MA20']) else False,
                    "above_ma50": row['Close'] > row['MA50'] if pd.notna(row['MA50']) else False,
                    "volume_ok": row['Volume'] > row['Volume_Avg'] * 0.8 if pd.notna(row['Volume_Avg']) else False,
                    "not_overextended": row['Price_7d_Change'] < 12 if pd.notna(row['Price_7d_Change']) else True,
                }
                
                # Count conditions met
                conditions_met = sum(conditions.values())
                
                # Determine signal
                if conditions_met >= 4:
                    signal_type = "STRONG_BUY"
                    confidence = 85
                elif conditions_met >= 3:
                    signal_type = "BUY"
                    confidence = 70
                else:
                    # Skip this day - no entry signal
                    i += 1
                    continue
                
                # Simulate trade
                entry_date = df.index[i].to_pydatetime()
                entry_price = row['Close']
                
                exit_idx = min(i + self.holding_period, len(df) - 1)
                exit_row = df.iloc[exit_idx]
                exit_date = df.index[exit_idx].to_pydatetime()
                exit_price = exit_row['Close']
                
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
                
                trade = BacktestTrade(
                    symbol=symbol,
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    pnl_percent=pnl_percent,
                    was_profitable=pnl_percent > 0,
                    signal_type=signal_type,
                    confidence=confidence,
                    conditions_at_entry=conditions,
                )
                trades.append(trade)
                
                # Skip holding period before next potential entry
                i += self.holding_period
            
            # Calculate summary stats
            if not trades:
                return self._empty_result(symbol, days)
            
            winning = [t for t in trades if t.was_profitable]
            losing = [t for t in trades if not t.was_profitable]
            
            pnls = [t.pnl_percent for t in trades]
            total_pnl = sum(pnls)
            avg_pnl = total_pnl / len(trades)
            max_win = max(pnls) if pnls else 0
            max_loss = min(pnls) if pnls else 0
            
            # Calculate Sharpe ratio (simplified)
            if len(pnls) > 1:
                import statistics
                mean_return = statistics.mean(pnls)
                std_return = statistics.stdev(pnls)
                sharpe_ratio = mean_return / std_return if std_return > 0 else None
            else:
                sharpe_ratio = None
            
            return BacktestResult(
                symbol=symbol,
                period_days=days,
                total_trades=len(trades),
                winning_trades=len(winning),
                losing_trades=len(losing),
                win_rate=len(winning) / len(trades) * 100,
                total_pnl_percent=total_pnl,
                avg_pnl_percent=avg_pnl,
                max_win_percent=max_win,
                max_loss_percent=max_loss,
                sharpe_ratio=sharpe_ratio,
                trades=trades,
            )
            
        except Exception as e:
            logger.error(f"Backtest error for {symbol}: {e}")
            return self._empty_result(symbol, days)
    
    def _empty_result(self, symbol: str, days: int) -> BacktestResult:
        """Return empty result when backtest fails."""
        return BacktestResult(
            symbol=symbol,
            period_days=days,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            total_pnl_percent=0,
            avg_pnl_percent=0,
            max_win_percent=0,
            max_loss_percent=0,
            sharpe_ratio=None,
            trades=[],
        )
    
    def run_portfolio_backtest(
        self,
        symbols: list[str],
        days: int = 90,
    ) -> dict[str, Any]:
        """Run backtest for entire portfolio/watchlist."""
        results = {}
        total_trades = 0
        total_wins = 0
        total_pnl = 0
        
        for symbol in symbols:
            result = self.run_backtest(symbol, days)
            results[symbol] = result
            total_trades += result.total_trades
            total_wins += result.winning_trades
            total_pnl += result.total_pnl_percent
        
        portfolio_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "individual_results": results,
            "portfolio_stats": {
                "total_trades": total_trades,
                "total_wins": total_wins,
                "portfolio_win_rate": portfolio_win_rate,
                "total_pnl_percent": total_pnl,
                "avg_pnl_per_symbol": total_pnl / len(symbols) if symbols else 0,
            }
        }


def run_quick_backtest(symbol: str, days: int = 90) -> BacktestResult:
    """Convenience function for quick backtest."""
    backtester = Backtester()
    return backtester.run_backtest(symbol, days)
