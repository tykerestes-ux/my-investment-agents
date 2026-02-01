"""Market data fetching for risk analysis."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class IntradayData:
    symbol: str
    current_price: float
    vwap: float
    volume: int
    avg_volume_10d: int
    volume_15min: int
    avg_volume_15min_10d: int
    open_price: float
    high: float
    low: float
    prev_close: float
    change_percent: float
    timestamp: datetime


@dataclass
class HistoricalMetrics:
    symbol: str
    price_7d_ago: float
    price_change_7d_percent: float
    avg_daily_volume_3m: int
    volatility_3m: float
    support_level: float
    resistance_level: float


class MarketDataFetcher:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._cache_ttl = timedelta(minutes=5)

    def get_intraday_data(self, symbol: str) -> IntradayData | None:
        try:
            ticker = yf.Ticker(symbol)
            intraday = ticker.history(period="1d", interval="1m")
            if intraday.empty:
                logger.warning(f"No intraday data for {symbol}")
                return None

            hist_5d = ticker.history(period="5d", interval="15m")
            hist_10d = ticker.history(period="10d", interval="1d")

            # Calculate VWAP
            intraday["TP"] = (intraday["High"] + intraday["Low"] + intraday["Close"]) / 3
            intraday["TPV"] = intraday["TP"] * intraday["Volume"]
            cumulative_tpv = intraday["TPV"].cumsum()
            cumulative_vol = intraday["Volume"].cumsum()
            vwap = (cumulative_tpv / cumulative_vol).iloc[-1] if cumulative_vol.iloc[-1] > 0 else 0

            current_price = intraday["Close"].iloc[-1]
            volume = int(intraday["Volume"].sum())
            open_price = intraday["Open"].iloc[0]
            high = intraday["High"].max()
            low = intraday["Low"].min()

            avg_volume_10d = int(hist_10d["Volume"].mean()) if not hist_10d.empty else 0

            recent_15min = intraday.tail(15)
            volume_15min = int(recent_15min["Volume"].sum())

            avg_volume_15min_10d = int(hist_5d["Volume"].mean()) if not hist_5d.empty else volume_15min

            info = ticker.info
            prev_close = info.get("previousClose", open_price)
            change_percent = ((current_price - prev_close) / prev_close * 100) if prev_close else 0

            return IntradayData(
                symbol=symbol, current_price=current_price, vwap=vwap, volume=volume,
                avg_volume_10d=avg_volume_10d, volume_15min=volume_15min,
                avg_volume_15min_10d=avg_volume_15min_10d, open_price=open_price,
                high=high, low=low, prev_close=prev_close, change_percent=change_percent,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error fetching intraday data for {symbol}: {e}")
            return None

    def get_historical_metrics(self, symbol: str) -> HistoricalMetrics | None:
        try:
            ticker = yf.Ticker(symbol)
            hist_3m = ticker.history(period="3mo", interval="1d")
            if hist_3m.empty:
                return None

            price_7d_ago = hist_3m["Close"].iloc[-7] if len(hist_3m) >= 7 else hist_3m["Close"].iloc[0]
            current_price = hist_3m["Close"].iloc[-1]
            price_change_7d = ((current_price - price_7d_ago) / price_7d_ago * 100) if price_7d_ago else 0

            avg_volume_3m = int(hist_3m["Volume"].mean())
            returns = hist_3m["Close"].pct_change().dropna()
            volatility = returns.std() * 100 if len(returns) > 0 else 0

            recent = hist_3m.tail(20)
            support = recent["Low"].min()
            resistance = recent["High"].max()

            return HistoricalMetrics(
                symbol=symbol, price_7d_ago=price_7d_ago,
                price_change_7d_percent=price_change_7d, avg_daily_volume_3m=avg_volume_3m,
                volatility_3m=volatility, support_level=support, resistance_level=resistance,
            )
        except Exception as e:
            logger.error(f"Error fetching historical metrics for {symbol}: {e}")
            return None

    def get_first_hour_data(self, symbol: str) -> dict[str, float] | None:
        try:
            ticker = yf.Ticker(symbol)
            intraday = ticker.history(period="1d", interval="5m")
            if intraday.empty or len(intraday) < 12:
                return None

            first_hour = intraday.head(12)
            return {
                "first_hour_high": first_hour["High"].max(),
                "first_hour_low": first_hour["Low"].min(),
                "first_hour_close": first_hour["Close"].iloc[-1],
                "first_hour_volume": int(first_hour["Volume"].sum()),
            }
        except Exception as e:
            logger.error(f"Error fetching first hour data for {symbol}: {e}")
            return None
