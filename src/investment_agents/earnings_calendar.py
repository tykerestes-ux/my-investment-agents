"""Earnings Calendar - Detect upcoming earnings to avoid high-volatility periods."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

# Days before earnings to lockout entries
EARNINGS_LOCKOUT_DAYS = 5


@dataclass
class EarningsInfo:
    """Earnings date information for a symbol."""
    symbol: str
    earnings_date: datetime | None
    days_until_earnings: int | None
    is_lockout: bool
    lockout_reason: str | None


def get_earnings_date(symbol: str) -> EarningsInfo:
    """Get next earnings date for a symbol."""
    try:
        ticker = yf.Ticker(symbol)
        
        earnings_date = None
        
        # Try to get earnings dates from calendar
        try:
            calendar = ticker.calendar
            
            if calendar is not None:
                # Handle dict format (newer yfinance)
                if isinstance(calendar, dict):
                    if 'Earnings Date' in calendar:
                        ed = calendar['Earnings Date']
                        if isinstance(ed, list) and len(ed) > 0:
                            earnings_date = ed[0]
                        elif ed is not None:
                            earnings_date = ed
                # Handle DataFrame format (older yfinance)
                elif hasattr(calendar, 'empty') and not calendar.empty:
                    if 'Earnings Date' in calendar.index:
                        earnings_dates = calendar.loc['Earnings Date']
                        if hasattr(earnings_dates, 'iloc') and len(earnings_dates) > 0:
                            earnings_date = earnings_dates.iloc[0]
                        elif earnings_dates is not None:
                            earnings_date = earnings_dates
        except Exception:
            pass
        
        # Also check earnings_dates property
        if earnings_date is None:
            try:
                earnings_df = ticker.earnings_dates
                if earnings_df is not None and hasattr(earnings_df, 'empty') and not earnings_df.empty:
                    # Get future dates only
                    now = datetime.now()
                    future_dates = [d for d in earnings_df.index if d.to_pydatetime() > now]
                    if future_dates:
                        earnings_date = min(future_dates).to_pydatetime()
            except Exception:
                pass
        
        if earnings_date is None:
            return EarningsInfo(
                symbol=symbol,
                earnings_date=None,
                days_until_earnings=None,
                is_lockout=False,
                lockout_reason=None,
            )
        
        # Normalize to datetime if needed
        if hasattr(earnings_date, 'to_pydatetime'):
            earnings_date = earnings_date.to_pydatetime()
        elif isinstance(earnings_date, str):
            earnings_date = datetime.fromisoformat(earnings_date)
        
        # Calculate days until earnings
        now = datetime.now()
        delta = earnings_date - now
        days_until = delta.days
        
        # Check if in lockout period
        is_lockout = 0 <= days_until <= EARNINGS_LOCKOUT_DAYS
        lockout_reason = None
        
        if is_lockout:
            lockout_reason = f"Earnings in {days_until} days ({earnings_date.strftime('%b %d')})"
        
        return EarningsInfo(
            symbol=symbol,
            earnings_date=earnings_date,
            days_until_earnings=days_until,
            is_lockout=is_lockout,
            lockout_reason=lockout_reason,
        )
        
    except Exception as e:
        logger.error(f"Error getting earnings for {symbol}: {e}")
        return EarningsInfo(
            symbol=symbol,
            earnings_date=None,
            days_until_earnings=None,
            is_lockout=False,
            lockout_reason=None,
        )


def check_earnings_lockout(symbol: str) -> tuple[bool, str | None]:
    """Check if a symbol is in earnings lockout period.
    
    Returns:
        (is_lockout, reason)
    """
    info = get_earnings_date(symbol)
    return info.is_lockout, info.lockout_reason


def format_earnings_discord(info: EarningsInfo) -> str:
    """Format earnings info for Discord."""
    if info.earnings_date is None:
        return f"📅 **{info.symbol}**: No earnings date found"
    
    emoji = "🔒" if info.is_lockout else "📅"
    date_str = info.earnings_date.strftime("%B %d, %Y")
    
    if info.is_lockout:
        return f"{emoji} **{info.symbol}**: EARNINGS LOCKOUT - {info.days_until_earnings} days ({date_str})"
    elif info.days_until_earnings is not None and info.days_until_earnings <= 14:
        return f"⚠️ **{info.symbol}**: Earnings in {info.days_until_earnings} days ({date_str})"
    else:
        return f"{emoji} **{info.symbol}**: Earnings on {date_str}"
