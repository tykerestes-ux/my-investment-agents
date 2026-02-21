"""Insider Trading Data - Track executive buys/sells via SEC Form 4."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
import aiohttp

logger = logging.getLogger(__name__)

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_HEADERS = {"User-Agent": "InvestmentBot/1.0 (contact@example.com)"}


@dataclass
class InsiderTransaction:
    """A single insider transaction."""
    filer_name: str
    filer_relation: str  # CEO, CFO, Director, etc.
    transaction_type: str  # "P" = Purchase, "S" = Sale
    shares: int
    price_per_share: float | None
    total_value: float | None
    transaction_date: str
    filing_date: str


@dataclass
class InsiderSummary:
    """Summary of recent insider activity."""
    symbol: str
    transactions: list[InsiderTransaction]
    net_shares_30d: int  # Positive = net buying, Negative = net selling
    buy_count_30d: int
    sell_count_30d: int
    total_buy_value_30d: float
    total_sell_value_30d: float
    signal: str  # "BULLISH", "BEARISH", "NEUTRAL"
    signal_strength: int  # 1-10
    summary: str


async def get_cik_for_ticker(ticker: str) -> str | None:
    """Get CIK number for a ticker symbol."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SEC_COMPANY_TICKERS_URL, headers=SEC_HEADERS) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for entry in data.values():
                        if entry.get("ticker", "").upper() == ticker.upper():
                            cik = str(entry.get("cik_str", ""))
                            return cik.zfill(10)  # Pad to 10 digits
    except Exception as e:
        logger.error(f"Error getting CIK for {ticker}: {e}")
    return None


async def get_insider_transactions(symbol: str, days: int = 90) -> InsiderSummary:
    """Get insider trading data for a symbol."""
    symbol = symbol.upper()
    transactions: list[InsiderTransaction] = []
    
    try:
        # For now, use yfinance which has some insider data
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        
        # Get insider transactions
        insider_transactions = ticker.insider_transactions
        
        if insider_transactions is not None and not insider_transactions.empty:
            cutoff = datetime.now() - timedelta(days=days)
            
            for _, row in insider_transactions.iterrows():
                try:
                    trans_date = row.get("Start Date")
                    if trans_date and hasattr(trans_date, 'to_pydatetime'):
                        trans_date = trans_date.to_pydatetime()
                        if trans_date < cutoff:
                            continue
                    
                    # Determine transaction type
                    text = str(row.get("Text", "")).lower()
                    shares = int(row.get("Shares", 0) or 0)
                    
                    if "purchase" in text or "buy" in text:
                        trans_type = "P"
                    elif "sale" in text or "sell" in text:
                        trans_type = "S"
                        shares = -abs(shares)  # Make negative for sales
                    else:
                        continue
                    
                    transactions.append(InsiderTransaction(
                        filer_name=str(row.get("Insider", "Unknown")),
                        filer_relation=str(row.get("Position", "Unknown")),
                        transaction_type=trans_type,
                        shares=abs(shares),
                        price_per_share=row.get("Value"),
                        total_value=abs(shares) * (row.get("Value") or 0),
                        transaction_date=str(trans_date)[:10] if trans_date else "",
                        filing_date=str(trans_date)[:10] if trans_date else "",
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing insider row: {e}")
                    continue
    
    except Exception as e:
        logger.error(f"Error getting insider data for {symbol}: {e}")
    
    # Calculate summary
    buy_count = len([t for t in transactions if t.transaction_type == "P"])
    sell_count = len([t for t in transactions if t.transaction_type == "S"])
    
    total_buy_shares = sum(t.shares for t in transactions if t.transaction_type == "P")
    total_sell_shares = sum(t.shares for t in transactions if t.transaction_type == "S")
    net_shares = total_buy_shares - total_sell_shares
    
    total_buy_value = sum(t.total_value or 0 for t in transactions if t.transaction_type == "P")
    total_sell_value = sum(t.total_value or 0 for t in transactions if t.transaction_type == "S")
    
    # Determine signal
    if buy_count > 0 and sell_count == 0:
        signal = "BULLISH"
        signal_strength = min(10, 5 + buy_count)
        summary = f"Insiders buying only - {buy_count} purchases, no sales"
    elif buy_count > sell_count * 2:
        signal = "BULLISH"
        signal_strength = 7
        summary = f"Strong insider buying - {buy_count} buys vs {sell_count} sells"
    elif sell_count > buy_count * 2:
        signal = "BEARISH"
        signal_strength = 3
        summary = f"Heavy insider selling - {sell_count} sells vs {buy_count} buys"
    elif sell_count > 0 and buy_count == 0:
        signal = "BEARISH"
        signal_strength = max(1, 5 - sell_count)
        summary = f"Insiders selling only - {sell_count} sales, no purchases"
    else:
        signal = "NEUTRAL"
        signal_strength = 5
        summary = f"Mixed insider activity - {buy_count} buys, {sell_count} sells"
    
    return InsiderSummary(
        symbol=symbol,
        transactions=transactions[:10],  # Keep last 10
        net_shares_30d=net_shares,
        buy_count_30d=buy_count,
        sell_count_30d=sell_count,
        total_buy_value_30d=total_buy_value,
        total_sell_value_30d=total_sell_value,
        signal=signal,
        signal_strength=signal_strength,
        summary=summary,
    )


def format_insider_discord(data: InsiderSummary) -> str:
    """Format insider data for Discord."""
    emoji = "🟢" if data.signal == "BULLISH" else "🔴" if data.signal == "BEARISH" else "🟡"
    
    lines = [
        f"{emoji} **Insider Trading: {data.symbol}** - {data.signal}",
        f"Signal Strength: {data.signal_strength}/10",
        "",
        f"**Last 90 Days:**",
        f"• Buys: {data.buy_count_30d} (${data.total_buy_value_30d:,.0f})",
        f"• Sells: {data.sell_count_30d} (${data.total_sell_value_30d:,.0f})",
        f"• Net Shares: {data.net_shares_30d:+,}",
        "",
        f"**Summary:** {data.summary}",
    ]
    
    if data.transactions:
        lines.append("\n**Recent Transactions:**")
        for t in data.transactions[:5]:
            action = "BUY" if t.transaction_type == "P" else "SELL"
            lines.append(f"• {t.filer_name} ({t.filer_relation}): {action} {t.shares:,} shares")
    
    return "\n".join(lines)
