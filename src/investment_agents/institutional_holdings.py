"""Institutional Holdings - Track 13F filings and major holders."""

import logging
from dataclasses import dataclass

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class InstitutionalHolder:
    """A single institutional holder."""
    name: str
    shares: int
    value: float | None
    percent_held: float | None
    date_reported: str | None


@dataclass
class InstitutionalData:
    """Institutional holdings summary."""
    symbol: str
    institutional_percent: float | None  # % held by institutions
    num_institutions: int
    top_holders: list[InstitutionalHolder]
    shares_outstanding: int | None
    float_shares: int | None
    insider_percent: float | None
    signal: str  # "HIGH_INSTITUTIONAL", "MODERATE", "LOW"
    signal_strength: int
    summary: str


def get_institutional_holdings(symbol: str) -> InstitutionalData:
    """Get institutional holdings data for a symbol."""
    symbol = symbol.upper()
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Get institutional data
        inst_percent = info.get("heldPercentInstitutions")
        if inst_percent and inst_percent < 1:
            inst_percent = inst_percent * 100  # Convert to percentage
        
        insider_percent = info.get("heldPercentInsiders")
        if insider_percent and insider_percent < 1:
            insider_percent = insider_percent * 100
        
        shares_outstanding = info.get("sharesOutstanding")
        float_shares = info.get("floatShares")
        
        # Get top institutional holders
        top_holders: list[InstitutionalHolder] = []
        try:
            inst_holders = ticker.institutional_holders
            if inst_holders is not None and not inst_holders.empty:
                for _, row in inst_holders.head(10).iterrows():
                    top_holders.append(InstitutionalHolder(
                        name=str(row.get("Holder", "Unknown"))[:40],
                        shares=int(row.get("Shares", 0) or 0),
                        value=row.get("Value"),
                        percent_held=row.get("% Out") if row.get("% Out") else None,
                        date_reported=str(row.get("Date Reported", ""))[:10] if row.get("Date Reported") else None,
                    ))
        except Exception as e:
            logger.debug(f"Error getting institutional holders: {e}")
        
        # Determine signal
        if inst_percent and inst_percent > 80:
            signal = "HIGH_INSTITUTIONAL"
            signal_strength = 6
            summary = f"{inst_percent:.0f}% institutional ownership - heavily managed"
        elif inst_percent and inst_percent > 60:
            signal = "MODERATE_INSTITUTIONAL"
            signal_strength = 7
            summary = f"{inst_percent:.0f}% institutional ownership - well-supported"
        elif inst_percent and inst_percent > 30:
            signal = "BALANCED"
            signal_strength = 6
            summary = f"{inst_percent:.0f}% institutional - balanced ownership"
        elif inst_percent:
            signal = "LOW_INSTITUTIONAL"
            signal_strength = 5
            summary = f"Only {inst_percent:.0f}% institutional - more retail/insider driven"
        else:
            signal = "UNKNOWN"
            signal_strength = 5
            summary = "Institutional data not available"
        
        return InstitutionalData(
            symbol=symbol,
            institutional_percent=inst_percent,
            num_institutions=len(top_holders),
            top_holders=top_holders,
            shares_outstanding=shares_outstanding,
            float_shares=float_shares,
            insider_percent=insider_percent,
            signal=signal,
            signal_strength=signal_strength,
            summary=summary,
        )
        
    except Exception as e:
        logger.error(f"Error getting institutional data for {symbol}: {e}")
        return InstitutionalData(
            symbol=symbol,
            institutional_percent=None,
            num_institutions=0,
            top_holders=[],
            shares_outstanding=None,
            float_shares=None,
            insider_percent=None,
            signal="UNKNOWN",
            signal_strength=5,
            summary=f"Error retrieving data",
        )


def format_institutional_discord(data: InstitutionalData) -> str:
    """Format institutional data for Discord."""
    emoji = "🏛️"
    
    lines = [
        f"{emoji} **Institutional Holdings: {data.symbol}**",
        "",
    ]
    
    if data.institutional_percent:
        lines.append(f"**Institutional Ownership:** {data.institutional_percent:.1f}%")
    
    if data.insider_percent:
        lines.append(f"**Insider Ownership:** {data.insider_percent:.1f}%")
    
    if data.shares_outstanding:
        lines.append(f"**Shares Outstanding:** {data.shares_outstanding:,}")
    
    if data.float_shares:
        lines.append(f"**Float:** {data.float_shares:,}")
    
    if data.top_holders:
        lines.append("\n**Top Institutional Holders:**")
        for holder in data.top_holders[:5]:
            pct = f" ({holder.percent_held:.1f}%)" if holder.percent_held else ""
            lines.append(f"• {holder.name}: {holder.shares:,} shares{pct}")
    
    lines.append("")
    lines.append(f"**Analysis:** {data.summary}")
    
    return "\n".join(lines)
