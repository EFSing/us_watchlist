"""Render offline screening and input evidence in a standalone HTML file."""

import json
from collections import Counter
from html import escape

from us_watchlist.domain.screening import Evaluation, Metrics, ReplayEvidence, ScreeningResult


def _metrics(items: Metrics) -> str:
    return "<br>".join(
        f"{escape(label)}: {escape(format(value, '.5g') if isinstance(value, float) else str(value))}"
        for label, value in items
    )


def _table(rows: tuple[Evaluation, ...]) -> str:
    if not rows:
        return ""
    body = "\n".join(
        f"<tr><th scope='row'>{escape(row.symbol)}</th><td>{escape(row.reason)}</td>"
        f"<td>{row.sessions_available}</td><td>{_metrics(row.structure)}</td>"
        f"<td>{_metrics(row.volume)}</td><td>{escape(row.data_gap)}</td></tr>" for row in rows
    )
    return f"""<div class="scroll"><table>
<thead><tr><th>Symbol</th><th>Result</th><th>Bars in window</th><th>Structure</th>
<th>Volume</th><th>Data gaps</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def _section(result: ScreeningResult, evidence: ReplayEvidence, *, anchored: bool) -> str:
    name = escape(result.strategy.name)
    version = escape(result.strategy.version)
    matches = tuple(row for row in result.evaluations if row.signal is not None)
    others = tuple(row for row in result.evaluations if row.signal is None)
    counts = Counter(row.reason for row in others)
    missing = counts["INCOMPLETE_HISTORY"]
    if result.error is not None:
        status, body = "FAILED", f"<p>{escape(result.error)}</p>"
    else:
        if not result.evaluations:
            status = "NO_CANDIDATES_IN_UNIVERSE"
        elif missing == len(result.evaluations):
            status = "DATA_UNAVAILABLE"
        elif missing:
            status = "PARTIAL_COVERAGE"
        elif matches:
            status = "SUCCESS_WITH_MATCHES"
        else:
            status = "SUCCESS_NO_MATCH"
        coverage = " · ".join(f"{escape(reason)} {count}" for reason, count in sorted(counts.items()))
        body = f"<p>Matches: {len(matches)} · Incomplete history: {missing}</p>{_table(matches)}"
        if others:
            body += (f"<details><summary>Other results · {len(others)}</summary><p>{coverage}</p>"
                     f"{_table(others)}</details>")
    record = json.dumps({
        "schema": "us_offline_screening_v1", "strategy": result.strategy.name,
        "version": result.strategy.version, "trade_date": evidence.trade_date.isoformat(),
        "cutoff": evidence.cutoff.isoformat(), "mode": evidence.mode, "status": status,
        "manifest_sha256": evidence.input_sha256, "error": result.error,
        "evaluations": [{
            "symbol": row.symbol, "reason": row.reason, "matched": row.signal is not None,
            "sessions_available": row.sessions_available, "data_gap": row.data_gap,
            "structure": dict(row.structure), "volume": dict(row.volume),
        } for row in result.evaluations],
    }, default=str, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    anchor = f' id="{version}"' if anchored else ""
    return f"""<section{anchor}>
<h2>{name} <small>{version}</small></h2>
<p><strong>{status}</strong></p>
{body}
<script type="application/json" data-strategy="{version}">{record}</script>
</section>"""


def render_replay(
    evidence: ReplayEvidence, results: tuple[ScreeningResult, ...], *, title: str = "US B shape diagnostic",
    summary: str = "",
) -> str:
    title = escape(title)
    observed = escape(evidence.mode)
    if evidence.mode in {"yahoo_observation", "iwb_yahoo_observation"}:
        timing = (
            "Historical point-in-time status: UNVERIFIED. Yahoo serves revised history at capture time. "
            "Bars through the last observed split are withheld for each affected symbol. "
            "Volume adjustment remains unverified."
        )
    elif evidence.mode == "offline_replay":
        timing = "Historical point-in-time status: EXTERNALLY ATTESTED. Calendar and adjustment evidence require source review."
    else:
        timing = "Synthetic input."
    adjustments = (
        evidence.adjustments_known_at.isoformat() if evidence.adjustments_known_at else "Unverified at target close"
    )
    sections = "\n".join(_section(result, evidence, anchored=bool(summary)) for result in results)
    headline = f"Candidate universe: {evidence.candidate_size}"
    date_label = "Candidate report date and status"
    source_label = "Candidate archive"
    mobility = ""
    run_summary = ""
    if evidence.iwb is not None:
        iwb = evidence.iwb
        age = (evidence.trade_date - evidence.seed_date).days
        excluded = " · ".join(f"{escape(symbol)} {escape(reason)}" for symbol, reason in iwb.inactive)
        inactive = f"<p>Equities without an eligible listing · {excluded}</p>" if excluded else ""
        headline = (
            f"IWB base equities: {evidence.seed_size} · Listed equities: {evidence.active_size} · "
            f"Target-session OHLCV: {iwb.target_bars}/{evidence.active_size}"
        )
        run_summary = (
            f"<p>Run status: {escape(iwb.status)} · Holdings age: {age} days (limit {iwb.max_age_days}) · "
            f"Fund non-equity rows outside the base: {iwb.non_equity_rows}</p>{inactive}"
            "<p>Research effectiveness / 研究效果: 未验证</p>\n"
        )
        date_label = "IWB version date and status"
        source_label = "IWB official holdings CSV"
        mobility = """
@media (max-width: 680px) {
  main, section { padding: .75rem; }
  nav { display: flex; flex-wrap: wrap; gap: .5rem; }
  .scroll th, .scroll td { padding: .4rem; min-width: 6rem; }
  .scroll th:first-child { position: sticky; left: 0; background: #eef4f9; }
  .scroll td { overflow-wrap: anywhere; }
}
"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · {evidence.trade_date}</title>
<style>
body {{ margin: 0; background: #f3f6fa; color: #172638; font: 15px/1.5 system-ui, sans-serif; }}
main {{ max-width: 1320px; margin: auto; padding: 1.25rem; }}
section, details.evidence {{ background: white; border: 1px solid #cfdae5; border-radius: 8px;
  padding: 1rem; margin: 1rem 0; }}
h1, h2 {{ margin-top: 0; }}
h2 small {{ display: inline-block; color: #42566b; font-size: .7em; overflow-wrap: anywhere; }}
summary {{ cursor: pointer; color: #164d72; }}
dt {{ font-weight: 650; }}
dd {{ margin: 0 0 .65rem; overflow-wrap: anywhere; }}
.scroll {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; margin: .75rem 0; }}
th, td {{ text-align: left; vertical-align: top; padding: .5rem; border-bottom: 1px solid #dce4ed; }}
thead {{ background: #eaf1f7; }}{mobility}
</style>
</head>
<body><main>
<h1>{title} · {evidence.trade_date}</h1>
<p>Regular session · {observed} · {headline}</p>
{run_summary}<p>{timing}</p>
{summary}<details class="evidence"><summary>Input evidence</summary>
<dl>
<dt>Decision / observation cutoff (UTC)</dt><dd>{evidence.cutoff.isoformat()}</dd>
<dt>{date_label}</dt><dd>{evidence.candidate_date} · {escape(evidence.candidate_status)}</dd>
<dt>IWB holdings date</dt><dd>{evidence.seed_date}</dd>
<dt>IWB equity rows and active rows</dt><dd>{evidence.seed_size} · {evidence.active_size}</dd>
<dt>{'IWB version' if evidence.iwb else 'Candidate artifact'} available (UTC)</dt><dd>{evidence.seed.available_at.isoformat()}</dd>
<dt>{source_label}</dt><dd>{escape(evidence.seed.source)}</dd>
<dt>{source_label} SHA-256</dt><dd>{escape(evidence.seed.snapshot_id)}</dd>
<dt>Calendar and OHLCV range</dt><dd>{escape(evidence.calendar_source)} ·
{evidence.first_session} through {evidence.trade_date} · {evidence.expected_sessions} sessions</dd>
<dt>OHLCV source and availability (UTC)</dt><dd>{escape(evidence.history.source)} ·
{evidence.history.available_at.isoformat()}</dd>
<dt>OHLCV input SHA-256</dt><dd>{escape(evidence.history.snapshot_id.rpartition('/')[0])}</dd>
<dt>Price and volume basis</dt><dd>{evidence.price_basis}</dd>
<dt>Split adjustments known (UTC)</dt><dd>{adjustments}</dd>
<dt>Run manifest SHA-256</dt><dd>{evidence.input_sha256}</dd>
</dl></details>
{sections}
</main></body></html>
"""


def render_joint_replay(
    evidence: ReplayEvidence, b: ScreeningResult, c: tuple[ScreeningResult, ...],
) -> str:
    results = (b, *c)
    links = " · ".join(
        f'<a href="#{escape(item.strategy.version)}">{escape(item.strategy.name)}</a>' for item in results
    )
    c_rows = tuple(row for item in c for row in item.evaluations)
    c_matches = {row.symbol for row in c_rows if row.signal is not None}
    c_summary = (
        f"C matches from available rule results: {len(c_matches)} unique symbol(s)."
        if any(row.reason != "INCOMPLETE_HISTORY" for row in c_rows) else "C rule results unavailable."
    )
    summary = (
        "<p>B reports the 76-session breakout/retest shape. "
        "C reports trend, pullback, support and rebound confirmation with descriptive volume.</p>"
        f"<p>{c_summary}</p>"
        f'<nav aria-label="Strategy results">{links}</nav>\n'
    )
    title = "US IWB B+C daily report" if evidence.iwb else "US B+C offline daily report"
    return render_replay(evidence, results, title=title, summary=summary)
