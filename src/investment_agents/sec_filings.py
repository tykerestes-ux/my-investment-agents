"""SEC EDGAR filing scanner for dilution/shelf detection."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiohttp

logger = logging.getLogger(__name__)

SEC_EDGAR_BASE = "https://data.sec.gov"


@dataclass
class SECFiling:
    form_type: str
    filing_date: datetime
    description: str
    url: str


@dataclass
class DilutionAlert:
    symbol: str
    filing_type: str
    filing_date: datetime
    days_ago: int
    description: str
    risk_level: str


class SECFilingScanner:
    TICKER_TO_CIK: dict[str, str] = {
        "LRCX": "0000707549",
        "KLAC": "0000319201",
        "ASML": "0000937966",
        "ONDS": "0001835022",
    }

    def __init__(self, user_agent: str = "InvestmentAgent/1.0") -> None:
        self.user_agent = user_agent
        self._cik_cache: dict[str, str] = dict(self.TICKER_TO_CIK)

    async def get_cik(self, symbol: str) -> str | None:
        symbol = symbol.upper()
        if symbol in self._cik_cache:
            return self._cik_cache[symbol]
        return None

    async def get_recent_filings(self, symbol: str, days: int = 90,
                                  form_types: list[str] | None = None) -> list[SECFiling]:
        if form_types is None:
            form_types = ["S-3", "S-3/A", "424B", "424B5", "S-1", "S-1/A", "EFFECT"]

        cik = await self.get_cik(symbol)
        if not cik:
            return []

        filings: list[SECFiling] = []
        cutoff_date = datetime.now() - timedelta(days=days)

        try:
            url = f"{SEC_EDGAR_BASE}/submissions/CIK{cik}.json"
            headers = {"User-Agent": self.user_agent}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return []

                    data = await resp.json()
                    recent = data.get("filings", {}).get("recent", {})
                    forms = recent.get("form", [])
                    dates = recent.get("filingDate", [])
                    descriptions = recent.get("primaryDocument", [])
                    accessions = recent.get("accessionNumber", [])

                    for i, form in enumerate(forms):
                        if form in form_types:
                            try:
                                filing_date = datetime.strptime(dates[i], "%Y-%m-%d")
                                if filing_date >= cutoff_date:
                                    acc_num = accessions[i].replace("-", "")
                                    doc_url = f"{SEC_EDGAR_BASE}/Archives/edgar/data/{cik}/{acc_num}/{descriptions[i]}"
                                    filings.append(SECFiling(
                                        form_type=form, filing_date=filing_date,
                                        description=descriptions[i], url=doc_url,
                                    ))
                            except (ValueError, IndexError):
                                continue

        except Exception as e:
            logger.error(f"Error fetching filings for {symbol}: {e}")

        return filings

    async def check_dilution_risk(self, symbol: str) -> DilutionAlert | None:
        filings = await self.get_recent_filings(symbol, days=30)

        high_risk_forms = ["EFFECT", "424B5", "424B"]
        medium_risk_forms = ["S-3", "S-3/A"]

        for filing in filings:
            days_ago = (datetime.now() - filing.filing_date).days

            if filing.form_type in high_risk_forms:
                return DilutionAlert(
                    symbol=symbol, filing_type=filing.form_type, filing_date=filing.filing_date,
                    days_ago=days_ago, description=f"Recent {filing.form_type} - potential offering",
                    risk_level="high",
                )

            if filing.form_type in medium_risk_forms:
                return DilutionAlert(
                    symbol=symbol, filing_type=filing.form_type, filing_date=filing.filing_date,
                    days_ago=days_ago, description=f"Shelf registration ({filing.form_type})",
                    risk_level="medium",
                )

        return None
