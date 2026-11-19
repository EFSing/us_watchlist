"""Translate a local synthetic fixture into US domain values."""

import tomllib
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from us_watchlist.domain.models import (
    MARKET,
    MarketSnapshot,
    PriceBasis,
    Provenance,
    SessionBar,
    SessionKind,
    SessionWindow,
    UniverseMember,
    UniverseSnapshot,
)


def read_fixture(path: Path) -> tuple[UniverseSnapshot, MarketSnapshot, datetime, str]:
    payload = path.read_bytes()
    config = tomllib.loads(payload.decode("utf-8"), parse_float=Decimal)
    if config.get("market") != MARKET or config.get("purpose") != "synthetic_smoke":
        raise ValueError("Smoke requires a US synthetic_smoke fixture")

    session_fields = config["session"]
    session = SessionWindow(
        trading_date=session_fields["trading_date"],
        kind=SessionKind(session_fields["kind"]),
        opens_at=session_fields["opens_at"],
        closes_at=session_fields["closes_at"],
    )
    universe_fields = config["universe"]
    universe = UniverseSnapshot(
        effective_date=universe_fields["effective_date"],
        provenance=Provenance(**universe_fields["provenance"]),
        members=tuple(UniverseMember(**member) for member in universe_fields["members"]),
    )
    data_fields = config["market_data"]
    market = MarketSnapshot(
        session=session,
        provenance=Provenance(**data_fields["provenance"]),
        price_basis=PriceBasis(data_fields["price_basis"]),
        bars=tuple(
            SessionBar(
                symbol=bar["symbol"],
                open=Decimal(str(bar["open"])),
                high=Decimal(str(bar["high"])),
                low=Decimal(str(bar["low"])),
                close=Decimal(str(bar["close"])),
                volume=bar["volume"],
            )
            for bar in data_fields["bars"]
        ),
    )
    return universe, market, config["cutoff"], sha256(payload).hexdigest()
