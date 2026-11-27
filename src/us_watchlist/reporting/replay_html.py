"""Project offline screening results and evidence into a standalone Chinese report."""

import json
from collections import Counter
from dataclasses import asdict, dataclass
from html import escape

from us_watchlist.domain.replay_research import CandidateResearch, ReplayResearch
from us_watchlist.domain.screening import B_SHAPE_V1, B_US_V2, B_VERSIONS, Evaluation, Metrics, ReplayEvidence, ScreeningResult
from us_watchlist.domain.workbench import QuoteSummary, Workbench
from us_watchlist.reporting.replay_assets import RESEARCH_STYLE, SCRIPT, STYLE, WORKBENCH_STYLE
from us_watchlist.reporting.replay_labels import REASON, STATUS, data_gap, metric_cells
from us_watchlist.reporting.research_html import candidate_research, research_definitions, research_summary, workbench_research
from us_watchlist.reporting.workbench_html import b_sections, market_pulse, quote_heading


_RULES = {
    B_SHAPE_V1: (
        "B · 76 日突破回踩形态", "形态匹配",
        "在 76 个交易日的窗口内检查首次合格放量突破，以及其后的回踩位置、缩量和收盘转强。",
    ),
    B_US_V2: (
        "B · 美股突破回踩 V2", "形态匹配",
        "在 76 个交易日内检查首次通过 ATR 涨幅与放量门槛的突破，并核对回踩、MA50 趋势、峰值回撤和收盘转强。",
    ),
    "us_c_trend_pullback_balanced_a_v1": (
        "C · 均衡规则", "研究规则匹配",
        "要求至少 60 个连续交易日，检查上涨趋势、回踩、支撑与收盘反弹确认。量能仅供观察。",
    ),
    "us_c_trend_pullback_conservative_b_v1": (
        "C · 保守规则", "研究规则匹配",
        "要求至少 90 个连续交易日，独立检查上涨趋势、回踩、支撑与收盘反弹确认。量能仅供观察。",
    ),
}
_HIGHLIGHTS = {
    "B": (
        ("Breakout date", "Platform", "Close / platform"),
        ("Breakout volume / prior 20d mean", "Retest mean volume / breakout"),
    ),
    "C": (
        ("Pullback depth", "Support floor", "Support ceiling", "Support status", "Rebound high", "Rebound size"),
        ("RV_T", "Pullback / baseline median volume", "Pullback volume path", "Robust volume z"),
    ),
}
_MODE = {
    "iwb_yahoo_observation": "收盘后行情观察",
    "yahoo_observation": "收盘后行情观察",
    "offline_replay": "外部声明的点时回放",
    "synthetic": "合成样本",
}
_PRICE = {
    "raw": "原始行情",
    "adjusted": "复权行情",
    "split_adjusted": "拆股调整行情",
    "yahoo_chart_quote": "Yahoo 报价日线，未使用股息复权收盘价",
}


@dataclass(frozen=True)
class _Rule:
    result: ScreeningResult
    version: str
    label: str
    match_label: str
    description: str
    matches: tuple[Evaluation, ...]
    others: tuple[Evaluation, ...]
    reasons: Counter[str]
    status: str

    @classmethod
    def from_result(cls, result: ScreeningResult) -> "_Rule":
        version = result.strategy.version
        label, match_label, description = _RULES.get(version, ("规则结果", "规则匹配", ""))
        matches = tuple(row for row in result.evaluations if row.signal is not None)
        others = tuple(row for row in result.evaluations if row.signal is None)
        reasons = Counter(row.reason for row in others)
        if result.error is not None:
            status = "FAILED"
        elif not result.evaluations:
            status = "NO_CANDIDATES_IN_UNIVERSE"
        elif reasons["INCOMPLETE_HISTORY"] == len(result.evaluations):
            status = "DATA_UNAVAILABLE"
        elif reasons["INCOMPLETE_HISTORY"]:
            status = "PARTIAL_COVERAGE"
        else:
            status = "SUCCESS_WITH_MATCHES" if matches else "SUCCESS_NO_MATCH"
        return cls(result, escape(version), label, match_label, description, matches, others, reasons, status)


def _reason(code: str) -> str:
    return REASON.get(code, "其他情形（见原始记录）")


def _json_record(record: dict, *, strategy: str = "", record_id: str = "record-input") -> str:
    payload = json.dumps(record, default=str, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    attribute = f'data-strategy="{strategy}"' if strategy else f'id="{record_id}"'
    return f'<script type="application/json" {attribute}>{payload}</script>'


def _strategy_record(rule: _Rule, evidence: ReplayEvidence) -> str:
    result = rule.result
    return _json_record({
        "schema": "us_offline_screening_v1", "strategy": result.strategy.name,
        "version": result.strategy.version, "trade_date": evidence.trade_date.isoformat(),
        "cutoff": evidence.cutoff.isoformat(), "mode": evidence.mode, "status": rule.status,
        "manifest_sha256": evidence.input_sha256, "error": result.error,
        "evaluations": [{
            "symbol": row.symbol, "reason": row.reason, "matched": row.signal is not None,
            "sessions_available": row.sessions_available, "data_gap": row.data_gap,
            "structure": dict(row.structure), "volume": dict(row.volume),
        } for row in result.evaluations],
    }, strategy=rule.version)


def _facts(items: tuple[tuple[str, object], ...]) -> str:
    return "".join(f"<div><dt>{label}</dt><dd>{escape(str(value))}</dd></div>" for label, value in items)


def _pill(label: str, *, warning: bool = False) -> str:
    tone = " warning" if warning else ""
    return f'<span class="pill{tone}">{label}</span>'


def _overview(
    evidence: ReplayEvidence, rules: tuple[_Rule, ...], risk: str, research: ReplayResearch | None,
    workbench: Workbench | None,
) -> str:
    if iwb := evidence.iwb:
        coverage = (
            ("IWB 权益基池", f"{evidence.seed_size:,} 只"),
            ("有有效上市市场", f"{evidence.active_size:,} 只"),
            ("当日行情覆盖", f"{iwb.target_bars:,} / {evidence.active_size:,}"),
        )
        if iwb.full_history_symbols is not None:
            coverage += ((f"{evidence.expected_sessions} 日完整历史",
                          f"{iwb.full_history_symbols:,} / {evidence.active_size:,}"),)
        facts = _facts(coverage)
        lead = "IWB 官方基池覆盖"
        status = STATUS.get(iwb.status, "见审计记录")
    else:
        facts = _facts((
            ("IWB 权益基池", f"{evidence.seed_size:,} 只"),
            ("IWB 活跃权益", f"{evidence.active_size:,} 只"),
            ("本轮候选股票池", f"{evidence.candidate_size:,} 只"),
        ))
        lead = "上游候选股票池覆盖"
        status = STATUS.get(evidence.candidate_status, "见审计记录")
    if workbench is not None:
        c_rules = rules[1:]
        c_count = len({row.symbol for rule in c_rules for row in rule.matches})
        if c_rules and all(rule.status in {"FAILED", "DATA_UNAVAILABLE", "NO_CANDIDATES_IN_UNIVERSE"} for rule in c_rules):
            c_count = "—"
        sections = market_pulse(workbench, c_count, b_failed=rules[0].result.error is not None)
        study = ""
        risk += " 参考计划供次交易日起观察，未计费用、滑点和成交。"
    else:
        cards = []
        for rule in rules:
            if rule.status in {"FAILED", "DATA_UNAVAILABLE", "NO_CANDIDATES_IN_UNIVERSE"}:
                count, note = "—", STATUS[rule.status]
            else:
                count = f"{len(rule.matches):,} 只"
                note = f"历史不足 {rule.reasons['INCOMPLETE_HISTORY']:,} 只"
            cards.append(f'<a href="#{rule.version}"><span>{rule.label}</span>'
                         f'<strong>{count}</strong><small>{rule.match_label} · {note}</small></a>')
        sections = f'<div class="decision-grid" style="--rule-count:{len(rules)}">{"".join(cards)}</div>'
        study = research_summary(research, rules[0].version) + "\n" if research is not None else ""
    return f"""<section id="overview" class="panel">
<div class="section-head"><h2>今日总览</h2>{_pill(f"数据状态 · {status}", warning=status != "完成")}</div>
{study}<div class="overview-grid">
  <div class="overview-lead"><p class="section-kicker">股票池与行情</p><strong>{lead}</strong>
  <p class="note">持仓日期 {evidence.seed_date} · 使用美股常规交易时段日线</p></div>
  <dl class="overview-facts">{facts}</dl>
</div>
{sections}
<div class="callout warning"><strong>研究效果未验证</strong><p>{risk}</p></div>
</section>"""


def _risk(evidence: ReplayEvidence) -> tuple[str, str]:
    if evidence.mode in {"yahoo_observation", "iwb_yahoo_observation"}:
        return (
            "历史点时与拆股量能未验证。各规则只使用满足其历史要求的行情。",
            "Yahoo 提供采集时可取得的历史日线，历史修订时间未核实。对有拆股记录的股票，"
            "剔除末次已知拆股日及以前的行情。拆股后的成交量是否已按一致口径调整仍未验证。",
        )
    if evidence.mode == "offline_replay":
        return "点时可用性由外部来源声明。", "交易日历及拆股调整的外部证据仍需核查。"
    return "本页使用合成样本检验流程。", "股票池与行情均为合成输入。"


def _candidates(
    rules: tuple[_Rule, ...], c_rules: tuple[_Rule, ...], *, has_research: bool, workbench: Workbench | None,
) -> str:
    groups = []
    if workbench is not None:
        core = "".join(
            f'<a href="#{rules[0].version}-{escape(row.quote.symbol)}">{escape(row.quote.symbol)} '
            f'<small>{escape(row.quote.name)} · {row.quote.sector}</small></a>' for row in workbench.core
        ) or '<span class="muted">本轮无核心精选</span>'
        groups.append(f'<div class="candidate-group"><h3>今日核心精选</h3><div class="ticker-list">{core}</div></div>')
    for rule in rules:
        symbols = "".join(
            f'<a href="#{rule.version}-{escape(row.symbol)}">{escape(row.symbol)}</a>'
            for row in rule.matches
        ) or f'<span class="muted">{STATUS[rule.status] if rule.status != "PARTIAL_COVERAGE" else "本轮无匹配"}</span>'
        label = rule.label
        if workbench is not None:
            if rule.version in B_VERSIONS:
                label = "B 全部形态匹配"
            else:
                label = "C 研究匹配 · " + rule.label.removeprefix("C · ")
                symbols = f'<a href="#{rule.version}">查看规则 · {len(rule.matches)} 只</a>' + symbols
        groups.append(f'<div class="candidate-group"><h3>{label}</h3><div class="ticker-list">{symbols}</div></div>')
    c_note = ""
    if len(c_rules) == 1:
        rule, = c_rules
        c_note = f" C {rule.label.removeprefix('C · ')}匹配 {len(rule.matches):,} 只。"
    elif c_rules:
        if any(len(rule.others) != rule.reasons["INCOMPLETE_HISTORY"] or rule.matches for rule in c_rules):
            unique = {row.symbol for rule in c_rules for row in rule.matches}
            c_note = f" C {len(c_rules)} 套规则合计 {len(unique):,} 只（按代码去重）。"
        else:
            c_note = " C 暂无可用的规则结果。"
    focus_note = "" if has_research else '\n<p class="callout"><strong>重点观察</strong> · 暂无经过审查的优选规则。</p>'
    title = "核心精选与候选" if workbench is not None else "今日候选"
    return f"""<section id="candidates" class="panel">
<div class="section-head"><div><h2>{title}</h2>
<p class="section-note">按规则列出全部匹配，点击代码查看个股。{c_note}</p></div></div>
{"".join(groups)}{focus_note}
</section>"""


def _metrics_for(metrics: Metrics, keys: tuple[str, ...]) -> tuple[Metrics, Metrics]:
    by_name = dict(metrics)
    return (
        tuple((key, by_name[key]) for key in keys if key in by_name),
        tuple((key, value) for key, value in metrics if key not in keys),
    )


def _legacy_card_body(row: Evaluation, *, is_b: bool) -> str:
    structure_keys, volume_keys = _HIGHLIGHTS["B" if is_b else "C"]
    structure, extra_structure = _metrics_for(row.structure, structure_keys)
    volume, extra_volume = _metrics_for(row.volume, volume_keys)
    volume_note = "检查突破放量和回踩缩量。" if is_b else "量能描述当日与回踩期间的交易活跃度。"
    more = ""
    if extra_structure or extra_volume or row.data_gap:
        gap = f"<p>{escape(data_gap(row.data_gap))}</p>" if row.data_gap else ""
        more = f"""<details><summary>展开其余结构与量能指标</summary>
<dl class="metrics">{metric_cells(extra_structure + extra_volume)}</dl>{gap}</details>"""
    return f"""<div class="watch-columns">
 <div class="watch-facts"><strong>价格结构</strong><dl class="metrics">{metric_cells(structure)}</dl></div>
 <div class="volume-card"><strong>量能</strong><p class="note">{volume_note}</p>
 <dl class="metrics">{metric_cells(volume, bars=True)}</dl></div>
</div>
{more}"""


def _card(row: Evaluation, rule: _Rule, study: CandidateResearch | None, quote: QuoteSummary | None = None) -> str:
    is_b = rule.result.strategy.version in B_VERSIONS
    heading = "h3" if is_b else "h4"
    symbol = escape(row.symbol)
    if study is None:
        body = _legacy_card_body(row, is_b=is_b)
    else:
        if quote is not None:
            plan, observation = workbench_research(study, is_b=is_b)
            body = f'<div class="workbench-card-grid">{plan}{observation}</div>'
        else:
            body = candidate_research(study, is_b=is_b)
        body += f"""
<details><summary>原始结构、补充量能与计算定义</summary>
{research_definitions(study, is_b=is_b)}
<dl class="metrics">{metric_cells(row.structure + row.volume)}</dl>
</details>"""
    header = (quote_heading(quote, heading) if quote else
              f'<div class="watch-head"><{heading}>{symbol}</{heading}>{_pill(_reason(row.reason))}</div>')
    return f"""<article class="watch-card" id="{rule.version}-{symbol}">
{header}
{body}
</article>"""


def _other_results(rule: _Rule, *, exclude: frozenset[str] = frozenset()) -> str:
    others = tuple(row for row in rule.others if row.symbol not in exclude)
    if not others:
        return ""
    reasons = Counter(row.reason for row in others)
    counts = "".join(f"<li>{_reason(code)} <strong>{count:,}</strong></li>"
                     for code, count in sorted(reasons.items(), key=lambda pair: (-pair[1], pair[0])))
    rows = []
    for row in others:
        reason = _reason(row.reason)
        gap = data_gap(row.data_gap)
        terms = escape(f"{row.symbol} {reason} {gap}".lower())
        gap_html = f"<small>{escape(gap)}</small>" if gap else ""
        rows.append(f'<tr data-search="{terms}"><th scope="row">{escape(row.symbol)}</th>'
                    f"<td>{reason}{gap_html}</td><td>{row.sessions_available:,}</td></tr>")
    return f"""<details class="fold other-results">
<summary>其他未匹配股票 · {len(others):,} 只</summary><div class="fold-content">
<ul class="reason-list" aria-label="未匹配原因汇总">{counts}</ul>
<div class="toolbar" hidden>
<label for="search-{rule.version}">搜索</label>
<input id="search-{rule.version}" type="search" placeholder="输入股票代码或原因">
<output for="search-{rule.version}" aria-live="polite"></output>
</div>
<table><thead><tr><th scope="col">股票代码</th><th scope="col">未匹配原因</th>
<th scope="col">可用交易日</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
</div></details>"""


def _rule_section(
    rule: _Rule, heading: str, studies: dict[tuple[str, str], CandidateResearch], quotes: dict[str, QuoteSummary] | None = None,
) -> str:
    version = rule.result.strategy.version
    content = "".join(_card(row, rule, studies.get((version, row.symbol)), (quotes or {}).get(row.symbol))
                      for row in rule.matches)
    if not content:
        message = {
            "FAILED": "该规则执行失败。原始异常见审计区。",
            "DATA_UNAVAILABLE": "该规则所需历史行情不足。",
            "NO_CANDIDATES_IN_UNIVERSE": "本轮股票池为空。",
        }.get(rule.status, "本轮没有匹配的股票。")
        content = f'<p class="empty">{message}</p>'
    return f"""<div class="rule-group" id="{rule.version}">
<div class="section-head"><div><{heading}>{rule.label}</{heading}>
<p class="section-note">{rule.description}</p></div>{_pill(STATUS[rule.status])}</div>
<div class="watch-list">{content}</div>
{_other_results(rule)}
</div>"""


def _audit(evidence: ReplayEvidence, rules: tuple[_Rule, ...], risk: str, research: ReplayResearch | None) -> str:
    seed_label = "IWB 官方持仓" if evidence.iwb else "上游候选归档"
    history_source = evidence.history.source
    if history_source.startswith("Yahoo Chart v8"):
        history_source = "Yahoo Chart v8 日线报价"
    elif evidence.mode == "synthetic":
        history_source = "合成日线样本"
    metadata = (
        ("数据模式", _MODE[evidence.mode]), ("决策或观察截止（UTC）", evidence.cutoff.isoformat()),
        (f"{seed_label}版本", f"{evidence.candidate_date} · {STATUS.get(evidence.candidate_status, '见原始记录')}"),
        ("IWB 持仓日期", evidence.seed_date), (f"{seed_label}取得时间（UTC）", evidence.seed.available_at.isoformat()),
        (f"{seed_label}来源", evidence.seed.source), (f"{seed_label} SHA-256", evidence.seed.snapshot_id),
        ("交易日历与日线范围", f"{evidence.calendar_source} · {evidence.first_session} 至 {evidence.trade_date}"
         f" · {evidence.expected_sessions:,} 个交易日"),
        ("行情来源与取得时间（UTC）", f"{history_source} · {evidence.history.available_at.isoformat()}"),
        ("行情输入 SHA-256", evidence.history.snapshot_id.rpartition("/")[0]),
        ("价格与量能口径", _PRICE.get(evidence.price_basis, "见原始记录")),
        ("拆股调整可用时间（UTC）", evidence.adjustments_known_at.isoformat()
         if evidence.adjustments_known_at else "目标收盘时未验证"),
        ("输入清单 SHA-256", evidence.input_sha256),
    )
    if iwb := evidence.iwb:
        metadata += (
            ("持仓日期距交易日", f"{(evidence.trade_date - evidence.seed_date).days} 日 · 上限 {iwb.max_age_days} 日"),
            ("基池外非权益记录", f"{iwb.non_equity_rows:,} 条"),
            ("上市资格排除", "；".join(f"{symbol}（{_reason(reason)}）" for symbol, reason in iwb.inactive) or "无"),
        )
    versions = "".join(f"<li>{rule.label} · <code>{rule.version}</code></li>" for rule in rules)
    downloads = "".join(f'<button type="button" hidden data-record="{rule.version}">{rule.label}</button>'
                        for rule in rules)
    errors = "".join(f'<p class="raw-error">{rule.label} · {escape(rule.result.error)}</p>'
                     for rule in rules if rule.result.error is not None)
    study_record = ""
    if research is not None:
        metadata += (("结构量能及参考计划版本", research.version), ("A 股公式参考提交", research.reference_commit))
        downloads += '<button type="button" hidden data-record="record-research">结构量能与参考计划</button>'
        study_record = "\n" + _json_record({
            **asdict(research), "manifest_sha256": evidence.input_sha256, "trade_date": evidence.trade_date,
            "cutoff": evidence.cutoff.isoformat(), "mode": evidence.mode, "price_basis": evidence.price_basis,
            "research_effectiveness": "UNVERIFIED", "formal_us_b_qualification": "NOT_ESTABLISHED",
        }, record_id="record-research")
    return f"""<details id="audit" class="panel fold">
<summary>数据来源与技术审计</summary>
<div class="fold-content">
<p class="callout warning">{risk}</p>
<dl class="audit-grid">{_facts(metadata)}</dl>
<h3>策略版本</h3><ul>{versions}</ul>
{errors}
<h3>原始机器记录</h3>
<p class="note">包含输入身份、规则状态，以及逐股原因、历史缺口、结构与量能的原始字段和精度。</p>
<div class="toolbar"><button type="button" hidden data-record="record-input">输入证据</button>{downloads}</div>
{_json_record(asdict(evidence))}
{"".join(_strategy_record(rule, evidence) for rule in rules)}{study_record}
</div></details>"""


def render_replay(
    evidence: ReplayEvidence, results: tuple[ScreeningResult, ...], *, title: str = "美股 B 形态日报",
    summary: str = "", research: ReplayResearch | None = None, workbench: Workbench | None = None,
) -> str:
    rules = tuple(_Rule.from_result(result) for result in results)
    # The joint entry point supplies B first, then each independently evaluated C rule.
    c_rules = rules[1:]
    risk, audit_risk = _risk(evidence)
    links = [("overview", "今日总览"), ("candidates", "核心精选与候选" if workbench else "今日候选")]
    studies = {(row.strategy_version, row.symbol): row for row in research.candidates} if research else {}
    sections = ""
    if rules:
        links.append((rules[0].version, "B 观察台" if workbench else "B 形态"))
        if workbench is None:
            sections = f'<section class="panel">{_rule_section(rules[0], "h2", studies)}</section>'
        else:
            watch_symbols = frozenset(row.quote.symbol for row in workbench.watch)
            diagnostics = _other_results(rules[0], exclude=watch_symbols)
            sections = b_sections(workbench, diagnostics, version=rules[0].version,
                                  failed=rules[0].result.error is not None)
    if c_rules:
        links.append(("c-results", "C 研究"))
        if workbench is None:
            c_sections = "".join(_rule_section(rule, "h3", studies) for rule in c_rules)
        else:
            quotes = {quote.symbol: quote for quote in workbench.c_quotes}
            c_sections = "".join(
                f'<details class="fold"><summary>{rule.label} · {len(rule.matches)} 只匹配</summary>'
                f'<div class="fold-content">{_rule_section(rule, "h3", studies, quotes)}</div></details>' for rule in c_rules
            )
        sections += f'<section id="c-results" class="panel"><h2>C 研究规则</h2>{c_sections}</section>'
    links.append(("audit", "数据审计"))
    nav = "".join(f'<a href="#{anchor}">{label}</a>' for anchor, label in links)
    styles = STYLE + (RESEARCH_STYLE if research or workbench else "") + (WORKBENCH_STYLE if workbench else "")
    body_class = ' class="workbench"' if workbench else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · {evidence.trade_date}</title>
<style>{styles}</style>
</head>
<body{body_class}><main>
<header class="site-header">
 <div><p class="eyebrow">美股策略复盘</p><h1>{escape(title)}</h1>
 <div class="pills">{_pill("常规交易时段")}{_pill(_MODE[evidence.mode])}</div></div>
 <p class="date">交易日 <strong>{evidence.trade_date}</strong></p>
</header>
<nav class="section-nav" aria-label="日报章节导航">{nav}</nav>
{_overview(evidence, rules, risk, research, workbench)}
{_candidates(rules, c_rules, has_research=research is not None, workbench=workbench)}
{summary}
{sections}
{_audit(evidence, rules, audit_risk, research)}
</main><script>{SCRIPT}</script></body></html>
"""


def render_joint_replay(
    evidence: ReplayEvidence, b: ScreeningResult, c: tuple[ScreeningResult, ...], *,
    research: ReplayResearch | None = None, workbench: Workbench | None = None,
) -> str:
    title = "美股收盘日报 · IWB" if evidence.iwb else "美股 B+C 离线日报"
    return render_replay(evidence, (b, *c), title=title, research=research, workbench=workbench)
