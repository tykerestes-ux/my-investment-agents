"""Watchlist management for tracking investments."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WatchlistItem:
    symbol: str
    name: str | None = None
    notes: str | None = None
    target_price: float | None = None
    alert_above: float | None = None
    alert_below: float | None = None
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: list[str] = field(default_factory=list)


@dataclass
class Watchlist:
    items: list[WatchlistItem] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())


class WatchlistManager:
    def __init__(self, data_path: Path | str = "data/watchlist.json") -> None:
        self.data_path = Path(data_path)
        self.watchlist = Watchlist()
        self._load()

    def _load(self) -> None:
        if self.data_path.exists():
            try:
                with open(self.data_path) as f:
                    data = json.load(f)
                    items = [WatchlistItem(**item) for item in data.get("items", [])]
                    self.watchlist = Watchlist(
                        items=items,
                        last_updated=data.get("last_updated", datetime.now().isoformat()),
                    )
                logger.info(f"Loaded {len(self.watchlist.items)} items from watchlist")
            except Exception as e:
                logger.error(f"Failed to load watchlist: {e}")
                self.watchlist = Watchlist()
        else:
            logger.info("No existing watchlist found, starting fresh")

    def _save(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.watchlist.last_updated = datetime.now().isoformat()
        data = {
            "items": [asdict(item) for item in self.watchlist.items],
            "last_updated": self.watchlist.last_updated,
        }
        try:
            with open(self.data_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save watchlist: {e}")

    def add(self, symbol: str, name: str | None = None, notes: str | None = None,
            target_price: float | None = None, tags: list[str] | None = None) -> WatchlistItem:
        symbol = symbol.upper()
        existing = self.get(symbol)
        if existing:
            self.remove(symbol)
        item = WatchlistItem(symbol=symbol, name=name, notes=notes,
                            target_price=target_price, tags=tags or [])
        self.watchlist.items.append(item)
        self._save()
        logger.info(f"Added {symbol} to watchlist")
        return item

    def remove(self, symbol: str) -> bool:
        symbol = symbol.upper()
        original_len = len(self.watchlist.items)
        self.watchlist.items = [i for i in self.watchlist.items if i.symbol != symbol]
        if len(self.watchlist.items) < original_len:
            self._save()
            return True
        return False

    def get(self, symbol: str) -> WatchlistItem | None:
        symbol = symbol.upper()
        for item in self.watchlist.items:
            if item.symbol == symbol:
                return item
        return None

    def get_all(self) -> list[WatchlistItem]:
        return self.watchlist.items.copy()

    def update(self, symbol: str, **kwargs: Any) -> WatchlistItem | None:
        item = self.get(symbol)
        if not item:
            return None
        for key, value in kwargs.items():
            if hasattr(item, key) and key != "symbol":
                setattr(item, key, value)
        self._save()
        return item

    def set_alert(self, symbol: str, above: float | None = None,
                  below: float | None = None) -> WatchlistItem | None:
        item = self.get(symbol)
        if not item:
            return None
        if above is not None:
            item.alert_above = above
        if below is not None:
            item.alert_below = below
        self._save()
        return item

    def clear(self) -> None:
        self.watchlist.items = []
        self._save()

    def import_symbols(self, symbols: list[str]) -> int:
        count = 0
        for symbol in symbols:
            symbol = symbol.strip().upper()
            if symbol and not self.get(symbol):
                self.add(symbol)
                count += 1
        return count

    def export_symbols(self) -> list[str]:
        return [item.symbol for item in self.watchlist.items]
