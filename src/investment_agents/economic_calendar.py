"""Economic Calendar - Track Fed meetings, CPI, jobs reports, etc."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EconomicEvent:
    """A single economic event."""
    name: str
    date: str
    time: str | None
    importance: str  # "HIGH", "MEDIUM", "LOW"
    actual: str | None
    forecast: str | None
    previous: str | None


@dataclass
class EconomicCalendarData:
    """Economic calendar summary."""
    upcoming_events: list[EconomicEvent]
    high_impact_soon: bool
    days_until_fomc: int | None
    days_until_cpi: int | None
    days_until_jobs: int | None
    market_risk_level: str  # "HIGH", "ELEVATED", "NORMAL"
    signal: str
    signal_strength: int
    summary: str


# Known important economic events (approximate dates)
# These are static for demonstration - in production, would use an API
RECURRING_EVENTS = [
    # FOMC meetings 2024-2025 (8 per year, roughly every 6 weeks)
    {"name": "FOMC Meeting", "importance": "HIGH", "day_of_month": [1, 15], "affects": "all"},
    # CPI (monthly, usually mid-month)
    {"name": "CPI Report", "importance": "HIGH", "day_of_month": [10, 11, 12, 13, 14], "affects": "all"},
    # Jobs Report (first Friday of month)
    {"name": "Non-Farm Payrolls", "importance": "HIGH", "day_of_month": [1, 2, 3, 4, 5, 6, 7], "affects": "all"},
    # GDP (quarterly)
    {"name": "GDP Report", "importance": "MEDIUM", "day_of_month": [25, 26, 27, 28], "affects": "all"},
    # Retail Sales
    {"name": "Retail Sales", "importance": "MEDIUM", "day_of_month": [15, 16, 17], "affects": "consumer"},
]


def get_economic_calendar() -> EconomicCalendarData:
    """Get upcoming economic events that could impact trading."""
    events: list[EconomicEvent] = []
    
    today = datetime.now().date()
    
    # Check for upcoming important dates
    # In production, this would call an economic calendar API like:
    # - Trading Economics API
    # - Investing.com API
    # - Alpha Vantage Economic Calendar
    
    # For now, use known recurring patterns
    days_to_fomc = None
    days_to_cpi = None
    days_to_jobs = None
    high_impact_soon = False
    
    # Check next 14 days for important events
    for i in range(14):
        check_date = today + timedelta(days=i)
        day = check_date.day
        weekday = check_date.weekday()
        
        # First Friday = Jobs Report
        if weekday == 4 and day <= 7:  # Friday, first week
            events.append(EconomicEvent(
                name="Non-Farm Payrolls",
                date=check_date.isoformat(),
                time="8:30 AM ET",
                importance="HIGH",
                actual=None,
                forecast=None,
                previous=None,
            ))
            if days_to_jobs is None:
                days_to_jobs = i
            if i <= 3:
                high_impact_soon = True
        
        # Mid-month = CPI (usually 10th-14th)
        if 10 <= day <= 14 and weekday < 5:  # Weekday mid-month
            # Check if already added
            if not any(e.name == "CPI Report" and e.date == check_date.isoformat() for e in events):
                events.append(EconomicEvent(
                    name="CPI Report",
                    date=check_date.isoformat(),
                    time="8:30 AM ET",
                    importance="HIGH",
                    actual=None,
                    forecast=None,
                    previous=None,
                ))
                if days_to_cpi is None:
                    days_to_cpi = i
                if i <= 3:
                    high_impact_soon = True
        
        # FOMC (8 meetings per year, roughly 6 weeks apart)
        # Approximate: January, March, May, June, July, September, November, December
        fomc_months = [1, 3, 5, 6, 7, 9, 11, 12]
        if check_date.month in fomc_months and 14 <= day <= 16 and weekday == 2:  # Wednesday mid-month
            events.append(EconomicEvent(
                name="FOMC Meeting",
                date=check_date.isoformat(),
                time="2:00 PM ET",
                importance="HIGH",
                actual=None,
                forecast=None,
                previous=None,
            ))
            if days_to_fomc is None:
                days_to_fomc = i
            if i <= 3:
                high_impact_soon = True
    
    # Determine market risk level
    if high_impact_soon:
        risk_level = "HIGH"
        signal = "CAUTION"
        signal_strength = 4
        summary = "High-impact economic data within 3 days - expect volatility"
    elif any(d is not None and d <= 7 for d in [days_to_fomc, days_to_cpi, days_to_jobs]):
        risk_level = "ELEVATED"
        signal = "AWARE"
        signal_strength = 5
        summary = "Important economic events within 1 week"
    else:
        risk_level = "NORMAL"
        signal = "CLEAR"
        signal_strength = 6
        summary = "No major economic events imminent"
    
    return EconomicCalendarData(
        upcoming_events=events[:10],
        high_impact_soon=high_impact_soon,
        days_until_fomc=days_to_fomc,
        days_until_cpi=days_to_cpi,
        days_until_jobs=days_to_jobs,
        market_risk_level=risk_level,
        signal=signal,
        signal_strength=signal_strength,
        summary=summary,
    )


def format_calendar_discord(data: EconomicCalendarData) -> str:
    """Format economic calendar for Discord."""
    emoji = "⚠️" if data.market_risk_level == "HIGH" else "📅"
    
    lines = [
        f"{emoji} **Economic Calendar** - Risk Level: {data.market_risk_level}",
        "",
    ]
    
    if data.days_until_fomc is not None:
        lines.append(f"🏛️ **FOMC:** {data.days_until_fomc} days")
    if data.days_until_cpi is not None:
        lines.append(f"📊 **CPI:** {data.days_until_cpi} days")
    if data.days_until_jobs is not None:
        lines.append(f"👷 **Jobs Report:** {data.days_until_jobs} days")
    
    if data.upcoming_events:
        lines.append("\n**Upcoming Events:**")
        for event in data.upcoming_events[:5]:
            importance_emoji = "🔴" if event.importance == "HIGH" else "🟡"
            lines.append(f"{importance_emoji} {event.date}: {event.name}")
    
    lines.append("")
    lines.append(f"**Analysis:** {data.summary}")
    
    if data.high_impact_soon:
        lines.append("\n⚠️ *Consider reducing position sizes before major events*")
    
    return "\n".join(lines)
