"""Freeze and read US regular-session Yahoo Chart observations."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

from us_watchlist.domain.models import (
    MarketSnapshot, PriceBasis, Provenance, SessionBar, SessionKind, SessionWindow, require_utc,
)
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.integrations.xnys import calendar_source, regular_windows

HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
SOURCE = "Yahoo Chart v8 · quote OHLCV (dividend-adjusted close excluded)"
SCHEMA = "us_yahoo_chart_observation_v1"
IWB_SCHEMA = "us_yahoo_chart_iwb_observation_v1"
FIELDS = ("open", "high", "low", "close", "volume")
IWB_CAPTURE_SECONDS = 600


def wait_before_recapture() -> None:
    sleep(75)


def _epoch(day: date) -> int:
    return int(datetime.combine(day, time.min, UTC).timestamp())


def _chart_url(host: str, symbol: str, start: date, end: date) -> str:
    params = urlencode({
        "period1": _epoch(start), "period2": _epoch(end + timedelta(days=1)),
        "interval": "1d", "events": "history,splits", "includePrePost": "false",
    })
    return f"https://{host}/v8/finance/chart/{quote(symbol, safe='')}?{params}"


def _fetch(symbol: str, start: date, end: date) -> tuple[dict, bytes | None]:
    attempts = []
    for host in HOSTS:
        url = _chart_url(host, symbol, start, end)
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=12) as response:
                body = response.read()
            return {
                "symbol": symbol, "url": url, "attempts": attempts,
                "received_at": datetime.now(UTC).isoformat(), "sha256": sha256(body).hexdigest(),
            }, body
        except HTTPError as error:
            attempts.append(f"{host} HTTP_{error.code}")
        except (URLError, TimeoutError, OSError) as error:
            attempts.append(f"{host} {type(error).__name__}")
    return {"symbol": symbol, "attempts": attempts}, None


def capture_yahoo(
    path: Path, target: date, symbols: tuple[str, ...], universe: Provenance, sessions: int,
    *, official_iwb: bool = False,
) -> tuple[str, int]:
    if path.exists():
        raise ValueError(f"Yahoo capture already exists: {path}")
    if not 76 <= sessions <= 252:
        raise ValueError("Yahoo capture requires 76–252 expected regular sessions")
    windows = regular_windows(target, sessions)
    started = datetime.now(UTC)
    if universe.available_at > started:
        raise ValueError("The universe archive is unavailable at capture time")
    if windows[-1].closes_at >= started:
        raise ValueError("Yahoo capture requires a completed target regular session")
    first = windows[0].trading_date
    through = started.date()
    records = []
    buffer = BytesIO()
    deadline = monotonic() + IWB_CAPTURE_SECONDS
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        with ThreadPoolExecutor(max_workers=6) as executor:
            stop_reason = ""
            for offset in range(0, len(symbols), 24):
                batch = symbols[offset:offset + 24]
                if official_iwb and not stop_reason and monotonic() >= deadline:
                    stop_reason = "NOT_REQUESTED_CAPTURE_DEADLINE"
                if stop_reason:
                    records.extend({"symbol": symbol, "attempts": [stop_reason]} for symbol in symbols[offset:])
                    break
                replies = tuple(executor.map(lambda symbol: _fetch(symbol, first, through), batch))
                for record, body in replies:
                    if body is not None:
                        archive.writestr(f"quotes/{record['symbol']}.json", body)
                    records.append(record)
                if all(
                    body is None and all(attempt.endswith("HTTP_429") for attempt in record["attempts"])
                    for record, body in replies
                ):
                    stop_reason = "NOT_REQUESTED_RATE_LIMIT"
        observed = datetime.now(UTC)
        if not official_iwb and observed.date() != through:
            raise ValueError("Yahoo capture crossed the UTC date boundary; capture again")
        identity_key = "holdings_sha256" if official_iwb else "candidate_sha256"
        archive.writestr("manifest.json", json.dumps({
            "schema": IWB_SCHEMA if official_iwb else SCHEMA, "market": "US", "calendar": calendar_source(),
            identity_key: universe.snapshot_id, "started_at": started.isoformat(),
            "observed_at": observed.isoformat(), "target": target.isoformat(),
            "requested_sessions": sessions, "symbols": records,
            "windows": [(window.trading_date.isoformat(), window.opens_at.isoformat(), window.closes_at.isoformat())
                        for window in windows],
        }, sort_keys=True))
    payload = buffer.getvalue()
    publish_once(path, payload)
    return sha256(payload).hexdigest(), sum("sha256" in record for record in records)


def _day(timestamp: int) -> date:
    if type(timestamp) is not int:
        raise ValueError("Yahoo event or quote timestamp must be integral")
    return datetime.fromtimestamp(timestamp, UTC).date()


def _quote_rows(
    symbol: str, payload: bytes, windows: dict[date, SessionWindow], through: date,
) -> tuple[dict[date, SessionBar], str]:
    chart = json.loads(payload, parse_float=Decimal)["chart"]
    if chart["error"] is not None:
        raise ValueError(f"YAHOO_CHART_ERROR {chart['error']['code']}")
    result, = chart["result"]
    meta = result["meta"]
    if (
        meta["symbol"] != symbol or meta["currency"] != "USD" or meta["instrumentType"] != "EQUITY"
        or meta["exchangeTimezoneName"] != "America/New_York" or meta["dataGranularity"] != "1d"
    ):
        raise ValueError("YAHOO_INCONSISTENT_SYMBOL_MARKET_OR_INTERVAL")

    first, target = next(iter(windows)), next(reversed(windows))
    splits = sorted(
        _day(event["date"]) for event in result.get("events", {}).get("splits", {}).values()
    )
    if any(day < first or day > through for day in splits):
        raise ValueError("YAHOO_SPLIT_EVENT_OUTSIDE_REQUEST")
    split_gap = "YAHOO_SPLIT_BASIS_UNVERIFIED " + ", ".join(map(date.isoformat, splits)) if splits else ""
    adjustment_boundary = splits[-1] if splits else date.min

    quotes, = result["indicators"]["quote"]
    stamps = result["timestamp"]
    if any(len(quotes[field]) != len(stamps) for field in FIELDS):
        raise ValueError("YAHOO_QUOTE_ARRAY_LENGTH_MISMATCH")
    days = tuple(map(_day, stamps))
    if any(earlier >= later for earlier, later in zip(days, days[1:])):
        raise ValueError("YAHOO_DUPLICATE_OR_UNORDERED_QUOTE")
    rows = {}
    for index, day in enumerate(days):
        if not first <= day <= through:
            raise ValueError("YAHOO_QUOTE_OUTSIDE_REQUEST")
        if day > target:
            continue
        if day not in windows or stamps[index] != int(windows[day].opens_at.timestamp()):
            raise ValueError(f"YAHOO_UNEXPECTED_REGULAR_SESSION {day}")
        if day <= adjustment_boundary:
            continue
        opening, high, low, close, volume = (quotes[field][index] for field in FIELDS)
        if None in (opening, high, low, close, volume):
            continue
        rows[day] = SessionBar(symbol, Decimal(opening), Decimal(high), Decimal(low), Decimal(close), volume)
    return rows, split_gap


def read_yahoo(
    payload: bytes, expected_sha256: str, target: date, symbols: tuple[str, ...], universe: Provenance,
    *, official_iwb: bool = False,
) -> tuple[tuple[MarketSnapshot, ...], datetime, str, tuple[tuple[str, str], ...]]:
    if sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("Yahoo capture SHA-256 does not match the replay manifest")
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as error:
        raise ValueError("Expected the original Yahoo capture ZIP") from error
    with archive:
        receipt = json.loads(archive.read("manifest.json"))
        schema, key = (IWB_SCHEMA, "holdings_sha256") if official_iwb else (SCHEMA, "candidate_sha256")
        if (receipt["schema"], receipt["market"], receipt["target"], receipt.get(key)) != (
            schema, "US", target.isoformat(), universe.snapshot_id,
        ):
            raise ValueError("Yahoo capture target, market or universe archive does not match")
        started = datetime.fromisoformat(receipt["started_at"])
        observed = datetime.fromisoformat(receipt["observed_at"])
        require_utc(started)
        require_utc(observed)
        if (not universe.available_at <= started <= observed <= datetime.now(UTC)
            or (not official_iwb and started.date() != observed.date())):
            raise ValueError("Yahoo capture was outside the observable universe/time window")
        windows = {}
        for day, opening, closing in receipt["windows"]:
            day = date.fromisoformat(day)
            if day in windows:
                raise ValueError("Yahoo capture contains a duplicate session")
            windows[day] = SessionWindow(
                day, SessionKind.REGULAR, datetime.fromisoformat(opening), datetime.fromisoformat(closing)
            )
        if not 76 <= len(windows) == receipt["requested_sessions"] <= 252:
            raise ValueError("Yahoo capture regular-session count differs from the request")
        if next(reversed(windows)) != target or windows[target].closes_at >= started:
            raise ValueError("Yahoo capture requires a completed target regular session")
        if official_iwb and (receipt["calendar"] != calendar_source() or
                             tuple(windows.values()) != regular_windows(target, len(windows))):
            raise ValueError("Yahoo capture differs from the XNYS regular calendar")
        records = receipt["symbols"]
        if tuple(record["symbol"] for record in records) != symbols:
            scope = "IWB listed equities" if official_iwb else "the published Candidate list"
            raise ValueError(f"Yahoo capture symbol manifest does not match {scope}")
        expected_names = {"manifest.json"} | {
            f"quotes/{record['symbol']}.json" for record in records if "sha256" in record
        }
        if set(archive.namelist()) != expected_names or len(archive.namelist()) != len(expected_names):
            raise ValueError("Yahoo capture has missing, duplicate or unexpected files")
        entries = {day: [] for day in windows}
        gaps = []
        for record in records:
            symbol = record["symbol"]
            if "sha256" not in record:
                gaps.append((symbol, "YAHOO_FETCH_FAILED " + "; ".join(record["attempts"])))
                continue
            raw = archive.read(f"quotes/{symbol}.json")
            received = datetime.fromisoformat(record["received_at"])
            require_utc(received)
            urls = {_chart_url(host, symbol, next(iter(windows)), started.date()) for host in HOSTS}
            if (
                sha256(raw).hexdigest() != record["sha256"]
                or not started <= received <= observed or record["url"] not in urls
            ):
                raise ValueError(f"Yahoo quote receipt failed SHA-256, URL or timestamp verification for {symbol}")
            try:
                rows, split_gap = _quote_rows(symbol, raw, windows, started.date())
            except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError, OSError) as error:
                gaps.append((symbol, f"YAHOO_QUOTE_REJECTED {type(error).__name__}: {error}"))
                continue
            if split_gap:
                gaps.append((symbol, split_gap))
            for day, bar in rows.items():
                entries[day].append(bar)
        history = tuple(
            MarketSnapshot(window, Provenance(SOURCE, f"{expected_sha256}/{day}", observed),
                           PriceBasis.YAHOO_CHART_QUOTE, tuple(entries[day]))
            for day, window in windows.items()
        )
        return history, observed, receipt["calendar"], tuple(gaps)
