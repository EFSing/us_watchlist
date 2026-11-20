"""Read the existing machine records without rendering or changing the IWB report."""

import json
from hashlib import sha256
from html.parser import HTMLParser

from us_watchlist.domain.models import MarketSnapshot
from us_watchlist.domain.paper import STRATEGIES


class _Records(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.records = {}
        self.current = None
        self.fragments = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag != "script" or attrs.get("type") != "application/json":
            return
        identity = attrs.get("data-strategy", attrs.get("id"))
        if identity in STRATEGIES or identity == "record-research":
            if identity in self.records:
                raise ValueError(f"PAPER_DUPLICATE_REPORT_RECORD {identity}")
            self.current = identity

    def handle_data(self, data):
        if self.current is not None:
            self.fragments.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.records[self.current] = json.loads("".join(self.fragments))
            self.current = None
            self.fragments.clear()


def read_report_records(body: bytes, report_sha256: str) -> dict:
    if sha256(body).hexdigest() != report_sha256:
        raise ValueError("PAPER_REPORT_SHA_MISMATCH")
    parser = _Records()
    parser.feed(body.decode("utf-8"))
    parser.close()
    if set(parser.records) != STRATEGIES.keys() | {"record-research"}:
        raise ValueError("PAPER_MISSING_REPORT_RECORD")
    return parser.records


def quote_prices(snapshot: MarketSnapshot) -> dict[str, list[str]]:
    """Freeze only validated OHLC rows with evidence of trading."""
    return {bar.symbol: [str(bar.open), str(bar.high), str(bar.low), str(bar.close)]
            for bar in snapshot.bars if bar.volume > 0}
