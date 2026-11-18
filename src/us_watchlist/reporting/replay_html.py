"""Render a B shape replay and per-symbol coverage."""

from html import escape

from us_watchlist.domain.screening import ScreeningReport


def render_replay(report: ScreeningReport) -> str:
    matches = sum(row.signal is not None for row in report.evaluations)
    missing = sum(row.reason == "INCOMPLETE_HISTORY" for row in report.evaluations)
    rows = "\n".join(
        f"<tr><td>{escape(row.symbol)}</td><td>{escape(row.reason)}</td>"
        f"<td>{row.sessions_available}</td></tr>" for row in report.evaluations
    )
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>US B regular-session replay · {report.trade_date}</title>
<h1>US B regular-session replay · {report.trade_date}</h1>
<p>Breakout and retest shape only · {escape(report.mode)}</p>
<dl>
<dt>Strategy version</dt><dd>{escape(report.strategy.version)}</dd>
<dt>Decision cutoff (UTC)</dt><dd>{report.cutoff.isoformat()}</dd>
<dt>IWB holdings date</dt><dd>{report.seed_date}</dd>
<dt>IWB artifact available (UTC)</dt><dd>{report.seed.available_at.isoformat()}</dd>
<dt>IWB source</dt><dd>{escape(report.seed.source)}</dd>
<dt>IWB artifact SHA-256</dt><dd>{report.seed.snapshot_id}</dd>
<dt>OHLCV source</dt><dd>{escape(report.history_source)}</dd>
<dt>Price and volume basis</dt><dd>Split-adjusted</dd>
<dt>Split adjustments known (UTC)</dt><dd>{report.adjustments_known_at.isoformat()}</dd>
<dt>Run manifest SHA-256</dt><dd>{report.input_sha256}</dd>
</dl>
<p>IWB equity rows: {report.seed_size} · Eligible: {len(report.evaluations)} ·
Shape matches: {matches} · Incomplete history: {missing}</p>
<table>
<thead><tr><th>Symbol</th><th>Result</th><th>Sessions with bars</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</html>
"""
