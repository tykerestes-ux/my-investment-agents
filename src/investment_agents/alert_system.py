"""Alert System - Get notified when conditions are met."""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
import yfinance as yf

from .technical_indicators import calculate_rsi
from .insider_trading import get_insider_transactions
from .options_flow import analyze_options_flow

if TYPE_CHECKING:
    from .discord_client import InvestmentBot

logger = logging.getLogger(__name__)

ALERTS_FILE = Path("data/alerts.json")
TRIGGERED_FILE = Path("data/triggered_alerts.json")


class AlertType(Enum):
    """Types of alerts."""
    PRICE_ABOVE = "price_above"  # Price rises above target
    PRICE_BELOW = "price_below"  # Price falls below (stop loss)
    RSI_OVERSOLD = "rsi_oversold"  # RSI < 30
    RSI_OVERBOUGHT = "rsi_overbought"  # RSI > 70
    INSIDER_BUYING = "insider_buying"  # Insider purchase detected
    UNUSUAL_OPTIONS = "unusual_options"  # Unusual options activity
    PERCENT_CHANGE = "percent_change"  # Price moves X% in a day


@dataclass
class Alert:
    """A single alert configuration."""
    id: str
    symbol: str
    alert_type: str
    condition_value: float | None  # Price target, RSI threshold, % change
    created_at: str
    active: bool = True
    triggered_at: str | None = None
    triggered_value: float | None = None
    notes: str = ""


@dataclass
class TriggeredAlert:
    """Record of a triggered alert."""
    alert_id: str
    symbol: str
    alert_type: str
    condition_value: float | None
    triggered_at: str
    triggered_value: float
    message: str


class AlertManager:
    """Manages price alerts and notifications."""

    def __init__(self) -> None:
        self.alerts: list[Alert] = []
        self.triggered: list[TriggeredAlert] = []
        self._load()

    def _load(self) -> None:
        """Load alerts from file."""
        if ALERTS_FILE.exists():
            try:
                with open(ALERTS_FILE) as f:
                    data = json.load(f)
                    self.alerts = [Alert(**a) for a in data.get("alerts", [])]
                logger.info(f"Loaded {len(self.alerts)} alerts")
            except Exception as e:
                logger.error(f"Error loading alerts: {e}")

        if TRIGGERED_FILE.exists():
            try:
                with open(TRIGGERED_FILE) as f:
                    data = json.load(f)
                    self.triggered = [TriggeredAlert(**t) for t in data.get("triggered", [])]
            except Exception as e:
                logger.error(f"Error loading triggered alerts: {e}")

    def _save(self) -> None:
        """Save alerts to file."""
        try:
            ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(ALERTS_FILE, "w") as f:
                json.dump({"alerts": [asdict(a) for a in self.alerts]}, f, indent=2)
            with open(TRIGGERED_FILE, "w") as f:
                json.dump({"triggered": [asdict(t) for t in self.triggered[-100:]]}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving alerts: {e}")

    def add_price_alert(self, symbol: str, target_price: float, alert_type: str = "above", notes: str = "") -> Alert:
        """Add a price target alert."""
        symbol = symbol.upper()
        a_type = AlertType.PRICE_ABOVE.value if alert_type == "above" else AlertType.PRICE_BELOW.value

        alert = Alert(
            id=f"{symbol}_{a_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            symbol=symbol,
            alert_type=a_type,
            condition_value=target_price,
            created_at=datetime.now().isoformat(),
            notes=notes,
        )
        self.alerts.append(alert)
        self._save()
        logger.info(f"Added price alert: {symbol} {alert_type} ${target_price}")
        return alert

    def add_rsi_alert(self, symbol: str, oversold: bool = True) -> Alert:
        """Add RSI oversold/overbought alert."""
        symbol = symbol.upper()
        a_type = AlertType.RSI_OVERSOLD.value if oversold else AlertType.RSI_OVERBOUGHT.value
        threshold = 30 if oversold else 70

        alert = Alert(
            id=f"{symbol}_{a_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            symbol=symbol,
            alert_type=a_type,
            condition_value=threshold,
            created_at=datetime.now().isoformat(),
        )
        self.alerts.append(alert)
        self._save()
        logger.info(f"Added RSI alert: {symbol} {'oversold' if oversold else 'overbought'}")
        return alert

    def add_insider_alert(self, symbol: str) -> Alert:
        """Add insider buying alert."""
        symbol = symbol.upper()

        alert = Alert(
            id=f"{symbol}_insider_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            symbol=symbol,
            alert_type=AlertType.INSIDER_BUYING.value,
            condition_value=None,
            created_at=datetime.now().isoformat(),
        )
        self.alerts.append(alert)
        self._save()
        logger.info(f"Added insider alert: {symbol}")
        return alert

    def add_percent_change_alert(self, symbol: str, percent: float) -> Alert:
        """Add percent change alert (e.g., alert if moves 5% in a day)."""
        symbol = symbol.upper()

        alert = Alert(
            id=f"{symbol}_pct_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            symbol=symbol,
            alert_type=AlertType.PERCENT_CHANGE.value,
            condition_value=abs(percent),
            created_at=datetime.now().isoformat(),
        )
        self.alerts.append(alert)
        self._save()
        logger.info(f"Added percent change alert: {symbol} {percent}%")
        return alert

    def remove_alert(self, alert_id: str) -> bool:
        """Remove an alert by ID."""
        for alert in self.alerts:
            if alert.id == alert_id:
                self.alerts.remove(alert)
                self._save()
                logger.info(f"Removed alert: {alert_id}")
                return True
        return False

    def get_active_alerts(self, symbol: str | None = None) -> list[Alert]:
        """Get active alerts, optionally filtered by symbol."""
        alerts = [a for a in self.alerts if a.active]
        if symbol:
            alerts = [a for a in alerts if a.symbol == symbol.upper()]
        return alerts

    def get_alerts_by_symbol(self, symbol: str) -> list[Alert]:
        """Get all alerts for a symbol."""
        return [a for a in self.alerts if a.symbol == symbol.upper()]

    async def check_all_alerts(self) -> list[TriggeredAlert]:
        """Check all active alerts and return triggered ones."""
        triggered_now: list[TriggeredAlert] = []

        # Group alerts by symbol to minimize API calls
        symbols = set(a.symbol for a in self.alerts if a.active)

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                change_pct = info.get("regularMarketChangePercent", 0)

                # Get historical for RSI
                hist = ticker.history(period="1mo", interval="1d")
                rsi = None
                if hist is not None and len(hist) >= 14:
                    rsi = calculate_rsi(hist['Close'])

                # Check each alert for this symbol
                symbol_alerts = [a for a in self.alerts if a.symbol == symbol and a.active]

                for alert in symbol_alerts:
                    triggered = None

                    # Price above
                    if alert.alert_type == AlertType.PRICE_ABOVE.value:
                        if current_price >= alert.condition_value:
                            triggered = TriggeredAlert(
                                alert_id=alert.id,
                                symbol=symbol,
                                alert_type=alert.alert_type,
                                condition_value=alert.condition_value,
                                triggered_at=datetime.now().isoformat(),
                                triggered_value=current_price,
                                message=f"🎯 **{symbol}** hit price target ${alert.condition_value:.2f}! Current: ${current_price:.2f}",
                            )

                    # Price below (stop loss)
                    elif alert.alert_type == AlertType.PRICE_BELOW.value:
                        if current_price <= alert.condition_value:
                            triggered = TriggeredAlert(
                                alert_id=alert.id,
                                symbol=symbol,
                                alert_type=alert.alert_type,
                                condition_value=alert.condition_value,
                                triggered_at=datetime.now().isoformat(),
                                triggered_value=current_price,
                                message=f"🛑 **{symbol}** hit stop loss ${alert.condition_value:.2f}! Current: ${current_price:.2f}",
                            )

                    # RSI oversold
                    elif alert.alert_type == AlertType.RSI_OVERSOLD.value:
                        if rsi and rsi < 30:
                            triggered = TriggeredAlert(
                                alert_id=alert.id,
                                symbol=symbol,
                                alert_type=alert.alert_type,
                                condition_value=30,
                                triggered_at=datetime.now().isoformat(),
                                triggered_value=rsi,
                                message=f"📉 **{symbol}** RSI oversold at {rsi:.1f}! Potential bounce opportunity.",
                            )

                    # RSI overbought
                    elif alert.alert_type == AlertType.RSI_OVERBOUGHT.value:
                        if rsi and rsi > 70:
                            triggered = TriggeredAlert(
                                alert_id=alert.id,
                                symbol=symbol,
                                alert_type=alert.alert_type,
                                condition_value=70,
                                triggered_at=datetime.now().isoformat(),
                                triggered_value=rsi,
                                message=f"📈 **{symbol}** RSI overbought at {rsi:.1f}! Consider taking profits.",
                            )

                    # Percent change
                    elif alert.alert_type == AlertType.PERCENT_CHANGE.value:
                        if abs(change_pct) >= alert.condition_value:
                            direction = "up" if change_pct > 0 else "down"
                            triggered = TriggeredAlert(
                                alert_id=alert.id,
                                symbol=symbol,
                                alert_type=alert.alert_type,
                                condition_value=alert.condition_value,
                                triggered_at=datetime.now().isoformat(),
                                triggered_value=change_pct,
                                message=f"🚨 **{symbol}** moved {change_pct:+.1f}% {direction}! (Alert threshold: {alert.condition_value}%)",
                            )

                    if triggered:
                        alert.active = False
                        alert.triggered_at = triggered.triggered_at
                        alert.triggered_value = triggered.triggered_value
                        self.triggered.append(triggered)
                        triggered_now.append(triggered)

                await asyncio.sleep(0.5)  # Rate limiting

            except Exception as e:
                logger.error(f"Error checking alerts for {symbol}: {e}")

        # Check insider alerts separately (more expensive)
        insider_alerts = [a for a in self.alerts if a.alert_type == AlertType.INSIDER_BUYING.value and a.active]
        for alert in insider_alerts:
            try:
                insider_data = await get_insider_transactions(alert.symbol, days=7)
                if insider_data.buy_count_30d > 0 and insider_data.signal == "BULLISH":
                    triggered = TriggeredAlert(
                        alert_id=alert.id,
                        symbol=alert.symbol,
                        alert_type=alert.alert_type,
                        condition_value=None,
                        triggered_at=datetime.now().isoformat(),
                        triggered_value=insider_data.buy_count_30d,
                        message=f"👔 **{alert.symbol}** insider buying detected! {insider_data.buy_count_30d} purchases. {insider_data.summary}",
                    )
                    alert.active = False
                    alert.triggered_at = triggered.triggered_at
                    self.triggered.append(triggered)
                    triggered_now.append(triggered)
            except Exception as e:
                logger.error(f"Error checking insider alert for {alert.symbol}: {e}")

        if triggered_now:
            self._save()

        return triggered_now

    def format_alerts_discord(self, symbol: str | None = None) -> str:
        """Format alerts for Discord."""
        alerts = self.get_active_alerts(symbol)

        if not alerts:
            return "📭 No active alerts." if not symbol else f"📭 No active alerts for {symbol}."

        lines = [f"🔔 **Active Alerts** ({len(alerts)} total)", ""]

        for alert in alerts:
            if alert.alert_type == AlertType.PRICE_ABOVE.value:
                lines.append(f"🎯 {alert.symbol}: Price above ${alert.condition_value:.2f}")
            elif alert.alert_type == AlertType.PRICE_BELOW.value:
                lines.append(f"🛑 {alert.symbol}: Price below ${alert.condition_value:.2f}")
            elif alert.alert_type == AlertType.RSI_OVERSOLD.value:
                lines.append(f"📉 {alert.symbol}: RSI oversold (<30)")
            elif alert.alert_type == AlertType.RSI_OVERBOUGHT.value:
                lines.append(f"📈 {alert.symbol}: RSI overbought (>70)")
            elif alert.alert_type == AlertType.INSIDER_BUYING.value:
                lines.append(f"👔 {alert.symbol}: Insider buying")
            elif alert.alert_type == AlertType.PERCENT_CHANGE.value:
                lines.append(f"🚨 {alert.symbol}: {alert.condition_value}% move")

            lines.append(f"   ID: `{alert.id[:30]}...`")

        return "\n".join(lines)


class AlertMonitor:
    """Monitors alerts and sends Discord notifications."""

    def __init__(self, bot: "InvestmentBot", channel_id: int) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self.manager = AlertManager()

    async def check_and_notify(self) -> None:
        """Check all alerts and send notifications for triggered ones."""
        triggered = await self.manager.check_all_alerts()

        if triggered:
            channel = self.bot.get_channel(self.channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                await channel.send("🔔 **ALERT TRIGGERED**")
                for alert in triggered:
                    await channel.send(alert.message)
                    await asyncio.sleep(0.5)


# Global instance
_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Get or create the alert manager."""
    global _manager
    if _manager is None:
        _manager = AlertManager()
    return _manager
