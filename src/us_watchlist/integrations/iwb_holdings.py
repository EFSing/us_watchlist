"""Freeze dated iShares IWB holdings and read the local version history."""

import csv
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

from us_watchlist.domain.models import MARKET, Provenance, UniverseMember, UniverseSnapshot
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.integrations.xnys import is_session

LATEST = "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/latest-holdings.csv"
HISTORICAL = (
    "https://www.ishares.com/ch/professionals/en/products/239707/"
    "ishares-russell-1000-etf/1495092304805.ajax"
)
SCHEMA = "us_iwb_official_holdings_v1"
MAX_AGE_DAYS = 10
MAX_CSV_BYTES = 2_000_000
REQUIRED = {"Ticker", "Asset Class", "Exchange", "Market Currency"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
US_EXCHANGES = {
    "NASDAQ", "NYSE", "NEW YORK STOCK EXCHANGE INC.", "NYSE ARCA", "NYSE AMERICAN", "NYSE MKT LLC",
    "CBOE BZX", "TXE",
}


@dataclass(frozen=True)
class HoldingsVersion:
    snapshot: UniverseSnapshot
    non_equity_rows: int
    inactive: tuple[tuple[str, str], ...]

    @property
    def day(self) -> date:
        return self.snapshot.effective_date


def _source(requested: date | None) -> str:
    if requested is None:
        return LATEST
    return HISTORICAL + "?" + urlencode({
        "fileType": "csv", "fileName": "IWB_holdings", "dataType": "fund",
        "asOfDate": requested.strftime("%Y%m%d"),
    })


def _holdings_date(value: str) -> date:
    us = re.fullmatch(r"([A-Za-z]{3}) ([0-9]{1,2}), ([0-9]{4})", value)
    if us:
        month, day, year = us.groups()
    else:
        historical = re.fullmatch(r"([0-9]{1,2})/([A-Za-z]{3})/([0-9]{4})", value)
        if historical is None:
            raise ValueError("IWB_HOLDINGS_DATE_MISSING_OR_INVALID")
        day, month, year = historical.groups()
    return date(int(year), MONTHS.index(month.title()) + 1, int(day))


def parse_holdings(raw: bytes, provenance: Provenance) -> HoldingsVersion:
    try:
        rows = list(csv.reader(StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    except csv.Error as error:
        raise ValueError("IWB_INVALID_CSV") from error
    if not rows or rows[0] != ["iShares Russell 1000 ETF"]:
        raise ValueError("IWB_UNEXPECTED_FUND")
    header = next((i for i, row in enumerate(rows) if REQUIRED.issubset(row)), None)
    if header is None or len(set(rows[header])) != len(rows[header]):
        raise ValueError("IWB_INVALID_CSV_HEADER")
    dates = [row[1] for row in rows[:header] if len(row) == 2 and row[0] == "Fund Holdings as of"]
    if len(dates) != 1:
        raise ValueError("IWB_EXPECTED_ONE_HOLDINGS_DATE")
    day = _holdings_date(dates[0])
    if day > provenance.available_at.date():
        raise ValueError("IWB_HOLDINGS_DATE_IN_FUTURE")

    members = {}
    inactive = {}
    non_equity = 0
    fields = rows[header]
    footer = False
    for row in rows[header + 1:]:
        if not row or (len(row) == 1 and not row[0].strip()):
            continue
        if len(row) == 1 and row[0].startswith("The content contained herein"):
            footer = True
            continue
        if footer or len(row) != len(fields):
            raise ValueError("IWB_MALFORMED_HOLDINGS_ROW")
        entry = dict(zip(fields, row, strict=True))
        if entry["Asset Class"] != "Equity":
            if not entry["Asset Class"].strip():
                raise ValueError("IWB_MISSING_ASSET_CLASS")
            non_equity += 1
            continue
        if entry["Market Currency"] != "USD":
            raise ValueError("IWB_UNEXPECTED_EQUITY_MARKET_CURRENCY")
        ticker = entry["Ticker"].strip()
        # iShares class separators are rendered as hyphens by Yahoo Chart.
        symbol = re.sub(r"[ .]", "-", ticker)
        exchange = entry["Exchange"].strip().upper()
        reason = ""
        if exchange in {"", "-", "NO MARKET (E.G. UNLISTED)"}:
            reason = "IWB_UNLISTED_OR_NO_MARKET"
        elif "WHEN ISSUED" in exchange or ticker.endswith((" WHEN ISSUED", " WI", ".WI", "-WI")):
            reason = "IWB_WHEN_ISSUED"
            if symbol.endswith("-WHEN-ISSUED"):
                symbol = symbol.removesuffix("-WHEN-ISSUED") + "-WI"
        elif exchange not in US_EXCHANGES:
            raise ValueError(f"IWB_UNKNOWN_EQUITY_EXCHANGE {symbol} {exchange}")
        if symbol in members:
            raise ValueError(f"IWB_DUPLICATE_SYMBOL {symbol}")
        weight = re.sub(r"[,\s]+", "", entry.get("Market Weight", ""))
        try:
            market_weight = Decimal(weight) if weight not in {"", "-"} else None
        except InvalidOperation as error:
            raise ValueError(f"IWB_INVALID_MARKET_WEIGHT {symbol}") from error
        members[symbol] = UniverseMember(
            symbol, not reason, " ".join(entry.get("Name", "").split()),
            " ".join(entry.get("Sector", "").split()), market_weight,
        )
        if reason:
            inactive[symbol] = reason

    # Fail closed on an empty/truncated download and a materially unexpected fund size.
    if not 900 <= len(members) <= 1200 or not 900 <= len(members) - len(inactive):
        raise ValueError(f"IWB_UNEXPECTED_EQUITY_COUNT {len(members)} ({len(inactive)} inactive)")
    return HoldingsVersion(
        UniverseSnapshot(day, provenance, tuple(members[symbol] for symbol in sorted(members))),
        non_equity, tuple(sorted(inactive.items())),
    )


def read_holdings(path: Path) -> HoldingsVersion:
    try:
        with ZipFile(path) as archive:
            if sorted(archive.namelist()) != ["holdings.csv", "receipt.json"]:
                raise ValueError("IWB_UNEXPECTED_ARCHIVE_ENTRIES")
            if archive.getinfo("holdings.csv").file_size > MAX_CSV_BYTES or archive.getinfo("receipt.json").file_size > 4096:
                raise ValueError("IWB_ARCHIVE_ENTRY_TOO_LARGE")
            raw = archive.read("holdings.csv")
            receipt = json.loads(archive.read("receipt.json"))
    except BadZipFile as error:
        raise ValueError("IWB_INVALID_ARCHIVE") from error
    digest = sha256(raw).hexdigest()
    requested = date.fromisoformat(receipt["requested_date"]) if receipt["requested_date"] else None
    if (receipt["schema"], receipt["market"], receipt["source"], receipt["sha256"]) != (
        SCHEMA, MARKET, _source(requested), digest,
    ):
        raise ValueError("IWB_ARCHIVE_SOURCE_OR_SHA_MISMATCH")
    acquired = datetime.fromisoformat(receipt["acquired_at"])
    provenance = Provenance(receipt["source"], digest, acquired)
    version = parse_holdings(raw, provenance)
    if (
        acquired > datetime.now(UTC) or version.day.isoformat() != receipt["holdings_date"]
        or (requested is not None and requested != version.day)
    ):
        raise ValueError("IWB_ARCHIVE_DATE_MISMATCH")
    return version


def versions(root: Path, through: date) -> tuple[tuple[date, Path], ...]:
    dated = []
    for path in root.glob("IWB_*.zip"):
        day = date.fromisoformat(path.stem.removeprefix("IWB_"))
        if day <= through:
            dated.append((day, path))
    return tuple(sorted(dated))


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*;q=0.1"})
    for attempt in range(2):
        try:
            with urlopen(request, timeout=20) as response:
                if response.geturl() != url or response.headers.get_content_type() not in {
                    "text/csv", "text/plain", "application/csv", "application/octet-stream",
                }:
                    raise ValueError("IWB_UNEXPECTED_DOWNLOAD_SOURCE_OR_TYPE")
                raw = response.read(MAX_CSV_BYTES + 1)
            if len(raw) > MAX_CSV_BYTES:
                raise ValueError("IWB_DOWNLOAD_TOO_LARGE")
            return raw
        except HTTPError as error:
            if attempt or error.code not in {429, 500, 502, 503, 504}:
                raise ValueError(f"IWB_HTTP_{error.code}") from None
        except (URLError, TimeoutError, OSError) as error:
            if attempt:
                raise ValueError(f"IWB_NETWORK_{type(error).__name__}") from None
        sleep(5)
    raise AssertionError("IWB request exhausted its retry loop")


def refresh_holdings(root: Path, requested: date | None, through: date) -> tuple[Path, HoldingsVersion]:
    if requested is not None and requested > through:
        raise ValueError("IWB_REQUEST_LATER_THAN_TARGET")
    url = _source(requested)
    raw = _download(url)
    acquired = datetime.now(UTC)
    digest = sha256(raw).hexdigest()
    version = parse_holdings(raw, Provenance(url, digest, acquired))
    if ((requested is not None and requested != version.day)
        or not 0 <= (through - version.day).days <= MAX_AGE_DAYS or not is_session(version.day)):
        raise ValueError(f"IWB_DOWNLOAD_DATE_UNUSABLE {version.day} for {through}")
    root_path = root / f"IWB_{version.day}.zip"
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("holdings.csv", raw)
        archive.writestr("receipt.json", json.dumps({
            "schema": SCHEMA, "market": MARKET, "requested_date": requested.isoformat() if requested else None,
            "source": url, "sha256": digest, "holdings_date": version.day.isoformat(),
            "acquired_at": acquired.isoformat(),
        }, sort_keys=True))
    try:
        publish_once(root_path, output.getvalue())
    except ValueError:
        existing = read_holdings(root_path)
        if existing.day != version.day or existing.snapshot.provenance.snapshot_id != digest:
            raise ValueError(f"IWB_SAME_DATE_CONTENT_CONFLICT {version.day}") from None
        return root_path, existing
    return root_path, version
