"""Risk Audit system with Shield Filters for hype detection."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .market_data import HistoricalMetrics, IntradayData, MarketDataFetcher
from .sec_filings import DilutionAlert, SECFilingScanner

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


class AlertType(Enum):
    INSTITUTIONAL_OFFLOADING = "institutional_offloading"
    PRICED_IN = "priced_in"
    EXIT_LIQUIDITY = "exit_liquidity"
    BULL_TRAP = "bull_trap"
    MORNING_HYPE = "morning_hype"
    HEALTHY = "healthy"


@dataclass
class ShieldFilterResult:
    name: str
    triggered: bool
    severity: int
    message: str
    data: dict[str, Any]


@dataclass
class RiskAuditResult:
    symbol: str
    timestamp: datetime
    hype_score: int
    overall_signal: str
    filters_triggered: list[ShieldFilterResult]
    summary: str
    recommendation: str
    support_level: float | None
    resistance_level: float | None
    current_price: float | None
    vwap: float | None

    def to_discord_message(self) -> str:
        if self.hype_score >= 8:
            emoji = "🟢"
            status = "HEALTHY"
        elif self.hype_score >= 5:
            emoji = "🟡"
            status = "CAUTION"
        else:
            emoji = "🔴"
            status = "WARNING"

        lines = [
            f"{emoji} **Risk Audit: {self.symbol}** | Hype Score: {self.hype_score}/10 ({status})",
            "",
        ]

        if self.current_price and self.vwap:
            vwap_diff = self.current_price - self.vwap
            above_below = "above" if vwap_diff > 0 else "below"
            lines.append(f"**Price:** ${self.current_price:.2f} (${abs(vwap_diff):.2f} {above_below} VWAP)")

        if self.filters_triggered:
            lines.append("")
            lines.append("**Alerts:**")
            for f in self.filters_triggered:
                severity_bar = "🔴" if f.severity >= 7 else "🟡" if f.severity >= 4 else "🟢"
                lines.append(f"{severity_bar} {f.message}")

        lines.append("")
        lines.append(f"**Summary:** {self.summary}")
        lines.append(f"**Recommendation:** {self.recommendation}")

        if self.support_level:
            lines.append(f"**Support:** ${self.support_level:.2f}")

        return "\n".join(lines)


class RiskAuditor:
    def __init__(self) -> None:
        self.market_data = MarketDataFetcher()
        self.sec_scanner = SECFilingScanner()

    async def run_audit(self, symbol: str) -> RiskAuditResult:
        symbol = symbol.upper()
        filters_triggered: list[ShieldFilterResult] = []
        hype_deductions = 0

        loop = asyncio.get_event_loop()
        intraday = await loop.run_in_executor(_executor, self.market_data.get_intraday_data, symbol)
        historical = await loop.run_in_executor(_executor, self.market_data.get_historical_metrics, symbol)
        first_hour = await loop.run_in_executor(_executor, self.market_data.get_first_hour_data, symbol)
        dilution_alert = await self.sec_scanner.check_dilution_risk(symbol)

        current_price = intraday.current_price if intraday else None
        vwap = intraday.vwap if intraday else None
        support = historical.support_level if historical else None
        resistance = historical.resistance_level if historical else None

        # Filter 1: VWAP Integrity
        if intraday and intraday.vwap > 0:
            vwap_result = self._check_vwap_integrity(intraday)
            if vwap_result.triggered:
                filters_triggered.append(vwap_result)
                hype_deductions += vwap_result.severity

        # Filter 2: Sell The News
        if historical:
            news_result = self._check_sell_the_news(historical)
            if news_result.triggered:
                filters_triggered.append(news_result)
                hype_deductions += news_result.severity

        # Filter 3: Dilution Check
        if dilution_alert:
            dilution_result = self._check_dilution(dilution_alert)
            if dilution_result.triggered:
                filters_triggered.append(dilution_result)
                hype_deductions += dilution_result.severity

        # Filter 4: Volume Exhaustion
        if intraday:
            volume_result = self._check_volume_exhaustion(intraday)
            if volume_result.triggered:
                filters_triggered.append(volume_result)
                hype_deductions += volume_result.severity

        # Filter 5: 10:30 AM Rule
        if first_hour and intraday:
            morning_result = self._check_morning_hype(intraday, first_hour)
            if morning_result.triggered:
                filters_triggered.append(morning_result)
                hype_deductions += morning_result.severity

        hype_score = max(1, 10 - hype_deductions)

        if hype_score >= 8:
            signal = "BUY"
            summary = "Move backed by volume and healthy technicals."
            recommendation = "Entry conditions favorable."
        elif hype_score >= 5:
            signal = "HOLD"
            summary = "Mixed signals. Some concerns but not critical."
            recommendation = "Proceed with caution; smaller position size."
        elif any(f.name == "morning_hype" for f in filters_triggered):
            signal = "NO_ENTRY"
            summary = "Morning volatility - wait for stabilization."
            recommendation = f"Wait for retest of ${support:.2f} support." if support else "Wait for 10:30 AM."
        else:
            signal = "AVOID"
            summary = "Multiple risk factors. Move likely driven by hype."
            recommendation = f"Avoid; wait for ${support:.2f} support." if support else "Avoid new positions."

        if filters_triggered:
            alert_names = [f.name.replace("_", " ").title() for f in filters_triggered]
            summary = f"Triggered: {', '.join(alert_names)}. {summary}"

        return RiskAuditResult(
            symbol=symbol, timestamp=datetime.now(), hype_score=hype_score,
            overall_signal=signal, filters_triggered=filters_triggered,
            summary=summary, recommendation=recommendation,
            support_level=support, resistance_level=resistance,
            current_price=current_price, vwap=vwap,
        )

    def _check_vwap_integrity(self, data: IntradayData) -> ShieldFilterResult:
        price_vs_vwap = data.current_price - data.vwap
        pct_below = (price_vs_vwap / data.vwap * 100) if data.vwap else 0
        triggered = pct_below < -0.5

        if triggered:
            severity = min(9, int(abs(pct_below)))
            message = (f"Price ${data.current_price:.2f} is ${abs(price_vs_vwap):.2f} below VWAP "
                      f"(${data.vwap:.2f}). Matches 'Institutional Offloading' profile. No-Buy Zone for calls.")
        else:
            severity = 0
            message = "Price holding above VWAP - institutional support intact."

        return ShieldFilterResult(name="vwap_integrity", triggered=triggered, severity=severity,
                                  message=message, data={"vwap": data.vwap, "diff_pct": pct_below})

    def _check_sell_the_news(self, data: HistoricalMetrics) -> ShieldFilterResult:
        triggered = data.price_change_7d_percent > 15
        if triggered:
            severity = min(8, int(data.price_change_7d_percent / 5))
            pullback_prob = min(85, 50 + int(data.price_change_7d_percent))
            message = (f"Stock rallied {data.price_change_7d_percent:.1f}% in 7 days. "
                      f"Flagged as 'Priced In'. Pullback probability: {pullback_prob}%.")
        else:
            severity = 0
            message = "No excessive pre-rally detected."

        return ShieldFilterResult(name="sell_the_news", triggered=triggered, severity=severity,
                                  message=message, data={"change_7d_pct": data.price_change_7d_percent})

    def _check_dilution(self, alert: DilutionAlert) -> ShieldFilterResult:
        triggered = alert.risk_level in ["high", "medium"]
        if alert.risk_level == "high":
            severity = 8
            message = (f"Recent {alert.filing_type} filing ({alert.days_ago} days ago). "
                      f"Treat price spikes as potential 'Exit Liquidity' for institutions.")
        elif alert.risk_level == "medium":
            severity = 5
            message = f"Active shelf registration ({alert.filing_type}). Company can issue shares."
        else:
            severity = 0
            message = "No recent dilution filings."

        return ShieldFilterResult(name="dilution_check", triggered=triggered, severity=severity,
                                  message=message, data={"filing_type": alert.filing_type})

    def _check_volume_exhaustion(self, data: IntradayData) -> ShieldFilterResult:
        is_price_up = data.change_percent > 2
        volume_ratio = data.volume_15min / data.avg_volume_15min_10d if data.avg_volume_15min_10d else 1
        is_volume_declining = volume_ratio < 0.6
        triggered = is_price_up and is_volume_declining

        if triggered:
            volume_drop_pct = (1 - volume_ratio) * 100
            severity = min(7, int(volume_drop_pct / 10) + 3)
            message = (f"Price up {data.change_percent:.1f}% but volume {volume_drop_pct:.0f}% below avg. "
                      f"'Bull Trap' warning - divergence detected.")
        else:
            severity = 0
            message = "Volume supporting price action."

        return ShieldFilterResult(name="volume_exhaustion", triggered=triggered, severity=severity,
                                  message=message, data={"volume_ratio": volume_ratio})

    def _check_morning_hype(self, intraday: IntradayData, first_hour: dict[str, float]) -> ShieldFilterResult:
        now = datetime.now()
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        minutes_since_open = (now - market_open).total_seconds() / 60
        in_first_hour = 0 <= minutes_since_open <= 60

        if in_first_hour:
            triggered = True
            severity = 4
            message = f"Within first 60 minutes. Wait for 'Morning Hype' to settle. Support: ${first_hour['first_hour_low']:.2f}."
        else:
            price_above_support = intraday.current_price > first_hour["first_hour_low"]
            if price_above_support:
                triggered = False
                severity = 0
                message = "Price holding above first-hour support."
            else:
                triggered = True
                severity = 3
                message = f"Price broke below first-hour support (${first_hour['first_hour_low']:.2f})."

        return ShieldFilterResult(name="morning_hype", triggered=triggered, severity=severity,
                                  message=message, data={"first_hour_low": first_hour["first_hour_low"]})


async def run_risk_audit(symbol: str) -> RiskAuditResult:
    auditor = RiskAuditor()
    return await auditor.run_audit(symbol)
