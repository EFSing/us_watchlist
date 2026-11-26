"""Self-contained offline companion for the IWB research ledger."""

from decimal import Decimal
from html import escape

from us_watchlist.domain.company_catalog import catalog_sector_style, company_name
from us_watchlist.domain.paper import POSITION_PROTOCOL, STRATEGIES, Mode, Status

_LABELS = {
    **STRATEGIES, Status.PENDING: "待开盘检查", Status.NOT_FILLED: "未成交",
    Status.OPEN: "模拟持仓", Status.CLOSED: "已退出", Status.UNAVAILABLE: "无法确认",
    "B_NUMERIC_QUALIFIED": "B 数值门槛通过", "B_NUMERIC_REJECTED": "B 数值门槛未通过",
    "B_NUMERIC_UNAVAILABLE": "B 数值门槛缺证",
    "C_PRICE_RESEARCH": "C 价格结构研究", "WARNING": "有风险警示", "CLEAR": "无风险警示",
    "UNKNOWN": "风险警示未定义或缺失", "CONDITIONAL_T1": "符合样本配置，待核对开盘",
    "POLICY_UNSET": "模拟资格未配置", "NO_REFERENCE_LEVELS": "参考价位缺失",
    "PLAN_CREATED": "新建计划", "FILLED_AT_T1_OPEN": "T+1 开盘模拟成交",
    "COHORT_NOT_ENABLED": "该资格样本未启用",
    "OPEN_AT_OR_BELOW_STOP": "开盘价达到或跌破止损", "OPEN_BELOW_TRIGGER": "开盘价低于触发价",
    "OPEN_AT_OR_ABOVE_TARGET": "开盘价达到或超过目标", "ENTRY_POLICY_UNSET": "入场条件待确认",
    "OPEN_ABOVE_CONFIGURED_PREMIUM": "开盘溢价超过配置上限",
    "TARGET_UPSIDE_BELOW_CONFIGURED_MINIMUM": "目标余量低于配置下限",
    "RR_BELOW_CONFIGURED_MINIMUM": "实际 RR 低于配置下限",
    "CLOSE_MARK": "按收盘价更新", "FIXED_STOP_TOUCHED": "触及生效止损", "GAP_THROUGH_STOP": "开盘达到或跌破止损",
    "PROFIT_PROTECTION_ARMED": "收盘跌破保护线，等待下一交易日开盘退出",
    "PROFIT_PROTECTION_NEXT_OPEN": "利润保护开盘退出", "STOP_RAISED_FOR_NEXT_SESSION": "上调下一交易日止损",
    "MISSING_OR_SPLIT_UNVERIFIED_YAHOO_BAR": "Yahoo 行情缺失或拆股基准未验证",
    "PRIOR_PRICE_BASIS_CHANGED": "上一日价格在新快照中发生变化",
    "UNRESOLVED_PRIOR_GAP": "此前行情缺口未恢复", "SIGNAL_NOT_KNOWN_BEFORE_T1_OPEN": "信号晚于 T+1 开盘",
    "REFERENCE_LEVELS_UNAVAILABLE": "参考计划缺失", "STRUCTURE_NOT_AVAILABLE": "结构观察不可用",
    "SIGNAL_PRICE_BASIS_UNAVAILABLE": "信号日价格基准缺失",
    "W2_TO_W3_TRANSITION_PROXY": "2→3 价格结构代理", "C_CLOSE_REBOUND_CONFIRMED": "C 收盘反弹形态",
    "POSITION_STRUCTURE_UNAVAILABLE": "缺少有效的持仓结构锚点",
    "OPEN_AT_OR_BELOW_STRUCTURE": "开盘达到或跌破结构失效线",
    "ACTIVE_STOP_TOUCHED": "盘中触及生效止损",
    "STRUCTURE_EXIT_ARMED": "收盘确认结构破坏，等待下一交易日开盘退出",
    "STRUCTURE_NEXT_OPEN": "结构破坏后开盘退出",
    "LATE_CLOSE_EVIDENCE": "收盘证据在下一交易日开盘时尚未可用，持仓停更",
    "INITIAL_STOP": "初始执行止损", "STRUCTURE_STOP": "结构移动止损", "PROFIT_STOP": "R 利润保护",
}

_STYLES = """
:root{color-scheme:light;--ink:#172738;--muted:#486072;--line:#dce5eb;--navy:#122c41;--teal:#096257}
*{box-sizing:border-box}body{margin:0;background:#edf2f6;color:var(--ink);
font:15px/1.55 "Microsoft YaHei","Noto Sans CJK SC",system-ui,sans-serif}
header{background:var(--navy);color:#fff;padding:32px 0 48px}header p{color:#c1dbeb;margin:0 0 8px}
main,.wrap{width:min(1120px,calc(100% - 32px));margin:auto}main{margin-top:-26px;padding-bottom:32px}
h1,h2,h3,p,dl,dd{margin:0}h1{font-size:clamp(25px,5vw,42px);line-height:1.2;margin-bottom:12px}
h2{font-size:20px;margin-bottom:14px}h3{font-size:17px}a{color:inherit}
nav{margin-top:14px;display:flex;gap:8px 20px;flex-wrap:wrap}
.metrics,.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(225px,100%),1fr));gap:12px}
.metric,.panel,.card{background:#fff;border:1px solid var(--line);border-radius:12px}
.metric{padding:12px 16px;color:var(--muted)}.metric strong{display:block;font-size:25px;color:var(--teal)}
.panel{margin-top:16px;padding:18px}.card{padding:12px;background:#f8fafb}
.cards{grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr))}
.small,dt,summary{color:var(--muted)}.small,dt{font-size:13px}
dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 12px;margin-top:10px}
dd,code{overflow-wrap:anywhere}ul{margin:8px 0 0;padding-left:20px}
.notice{margin-top:12px;padding:10px 12px;border-left:4px solid #bd8224;background:#fff5de;color:#754800}
.activity{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;
align-items:start;padding:9px 0;border-bottom:1px solid var(--line)}
.activity:last-child{border-bottom:0}.status{color:var(--teal);font-weight:600}
summary{cursor:pointer;margin-top:8px}.activity details{grid-column:1/-1}
table{width:100%;border-collapse:collapse;text-align:right;font-variant-numeric:tabular-nums}
th,td{padding:7px 5px;border-bottom:1px solid var(--line);vertical-align:top}
th:first-child,td:first-child{text-align:left}.pending{margin-top:10px}footer{padding:16px 0}
@media(max-width:600px){header{padding-top:22px}.panel{padding:12px}.metric{padding:8px 12px}
.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}table{font-size:12px}th,td{padding:6px 3px}}
"""

_COMBINED_STYLES = """
#paper-research .metrics, #paper-research .cards, #paper-research dl {
  display: grid; gap: 8px;
}
#paper-research .metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 12px; }
#paper-research .cards { grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr)); }
#paper-research dl { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 8px; }
#paper-research .metric, #paper-research .card {
  min-width: 0; padding: 9px 12px; border: 1px solid var(--border); background: var(--surface-2);
}
#paper-research .metric { color: var(--muted); font-size: 14px; }
#paper-research .metric strong { display: block; color: var(--text); font-size: 20px; }
#paper-research .small { color: var(--muted); font-size: 14px; }
#paper-research .notice { margin-top: 8px; padding: 8px; background: #fff8e8; color: var(--warning); }
#paper-research .activity {
  display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 8px;
  padding: 8px 0; border-bottom: 1px solid var(--border);
}
#paper-research .activity details { grid-column: 1 / -1; }
#paper-research .paper-table { overflow-x: auto; margin-top: 6px; }
#paper-research .paper-table table { min-width: 560px; }
#paper-research .card details, #paper-research .paper-audit { margin-top: 8px; }
@media (max-width: 600px) {
  #paper-research .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
"""


def _label(value: str) -> str:
    return escape(_LABELS.get(value, value))


def _fmt(value, suffix: str = "") -> str:
    return "—" if value is None else f"{Decimal(value):,.2f}{suffix}"


def _percent(value) -> str:
    return _fmt(Decimal(str(value)) * 100 if value is not None else None, "%")


def _facts(items) -> str:
    return "<dl>" + "".join(f"<div><dt>{label}</dt><dd>{value}</dd></div>" for label, value in items) + "</dl>"


def _name(plan: dict, *, company_labels: bool) -> str:
    symbol = plan["symbol"]
    company = ""
    if company_labels:
        sector, style = catalog_sector_style(symbol)
        if style != "未分类":
            company = f" · {escape(company_name(symbol))} · {sector}（{style}）"
    return f"{escape(symbol)}{company} · {_label(plan['strategy_version'])}"


def _qualification(plan: dict) -> str:
    return f"{_label(plan['qualification'])} · {_label(plan['risk_warning'])}"


def _history_mark(state: dict) -> str:
    mark = f' · {_fmt(state["latest_price"])} USD · {_fmt(state["r"], "R")}'
    if "active_stop_at_open" not in state:
        return f'{mark} · 止损 {_fmt(state["stop"])} USD'
    mark += f' · 当日生效止损 {_fmt(state["active_stop_at_open"])} USD'
    if state["next_stop_session"] and Decimal(state["stop"]) > Decimal(state["active_stop_at_open"]):
        mark += f' · 次日止损 {_fmt(state["stop"])} USD'
    return mark


def _history(row: dict) -> str:
    events = "".join(
        f"<li>{escape(event['trade_date'])} · {_label(event['reason'])}"
        + (f" · 开盘 {_fmt(event['opening'])} USD · 实际 RR {_fmt(event.get('actual_rr'))}"
           if 'opening' in event else "")
        + (_history_mark(event["position"]) if "position" in event else "")
        + (f" · {escape(event['diagnostic'])}" if event.get("diagnostic") else "")
        + "</li>"
        for event in row["history"]
    )
    return f"<details><summary>状态历史</summary><ul>{events}</ul></details>"


def _position(row: dict, *, company_labels: bool) -> str:
    plan, state = row["plan"], row["position"]
    warning = (f'<p class="notice">状态未更新 · {_label(row["history"][-1]["reason"])}</p>'
               if row.get("suspended_at") else "")
    stop_facts = (("当前止损", _fmt(state["stop"], " USD")),)
    if plan.get("protocol") == POSITION_PROTOCOL:
        stop_facts = (
            ("初始执行止损", _fmt(state["initial_stop"], " USD")),
            ("结构底线", _fmt(state["structural_floor"], " USD")),
            ("最近估值日生效止损", _fmt(state["active_stop_at_open"], " USD")),
            ("下一会话止损", _fmt(state["stop"], " USD") + " · " + escape(state["next_stop_session"])
             if state["next_stop_session"] else "—"),
            ("逐笔最大峰值回吐", _fmt(state["max_mfe_drawdown_r"], "R")),
        )
        protection = state.get("pending_exit")
        if protection is not None:
            why = " · ".join(_label(reason) for reason in protection["reasons"])
            warning += f'<p class="notice">预约开盘退出 · {escape(protection["session"])} · {why}</p>'
        low = state.get("protected_low")
        if low is not None:
            stop_facts += (("最近确认结构低点", _fmt(low["price"], " USD") + " · " + escape(low["confirmed_on"])),)
    facts = _facts((
        ("模拟入场日", escape(state["entry_date"])), ("实际入场 RR", _fmt(state["initial_rr"])),
        ("入场价", _fmt(state["entry"], " USD")), ("最新价", _fmt(state["latest_price"], " USD")),
        *stop_facts, ("参考目标", _fmt(plan["levels"]["target"], " USD")),
        ("浮动盈亏 / 单位", _fmt(state["pnl_per_unit"], " USD") + " · " + _percent(state["return"])),
        ("浮动 R", _fmt(state["r"], "R")), ("MFE / MAE", f'{_fmt(state["mfe_r"], "R")} / {_fmt(state["mae_r"], "R")}'),
        ("最近有效估值", escape(state["priced_on"])), ("当前结构观察", _label(state["structure"])),
        ("目标里程碑", "已观察到" if state["target_seen"] else "尚未确认"),
    ))
    return (f'<article class="card"><h3>{_name(plan, company_labels=company_labels)}</h3><p class="small">{_qualification(plan)}</p>'
            f'{facts}{warning}{_history(row)}</article>')


def _pending(row: dict, *, company_labels: bool) -> str:
    plan = row["plan"]
    levels = plan["levels"]
    facts = _facts((
        ("下一 XNYS 交易日", escape(plan["expected_entry"])), ("参考 RR", _fmt(levels["rr"])),
        ("触发 / 止损 / 目标（USD）", " / ".join(_fmt(levels[key]) for key in ("trigger", "stop", "target"))),
        ("模拟成交资格", _label(plan["simulation_eligibility"])),
    ))
    title = _name(plan, company_labels=company_labels)
    return f'<article class="card"><h3>{title}</h3><p class="small">{_qualification(plan)}</p>{facts}</article>'


def _activity(row: dict, event: dict, *, company_labels: bool) -> str:
    plan = row["plan"]
    reason = _label(event["reason"])
    if event["status"] == Status.CLOSED:
        position = event["position"]
        reason += (f' · {_fmt(position["exit_price"], " USD")} · '
                   f'{_percent(position["return"])} · {_fmt(position["r"], "R")}')
        if "exit_reasons" in position:
            reason += "".join(f" · {_label(item)}" for item in position["exit_reasons"][1:])
            if event["reason"] in ("ACTIVE_STOP_TOUCHED", "GAP_THROUGH_STOP"):
                reason += " · " + " / ".join(_label(item) for item in position["active_stop_sources"])
    state = event.get("observation", event["status"])
    return (f'<article class="activity"><div><strong>{_name(plan, company_labels=company_labels)}</strong><p class="small">'
            f'{reason} · {_qualification(plan)}</p></div><span class="status">{_label(state)}</span>'
            f'{_history(row)}</article>')


def _sections(view: dict):
    day = view["trade_date"]
    rows = view["records"].values()
    positions = [row for row in rows if row["status"] == Status.OPEN]
    pending = [row for row in rows if row["status"] == Status.PENDING]
    activity = [(row, event) for row in rows for event in row["history"]
                if event["trade_date"] == day and event["reason"] != "CLOSE_MARK"]
    return positions, pending, activity


def paper_mail_text(view: dict) -> str:
    positions, pending, activity = _sections(view)
    stale = sum(bool(row.get("suspended_at")) for row in positions)
    closed = sum(row["status"] == Status.CLOSED for row in view["records"].values())
    gaps = sum(event.get("observation", event["status"]) == Status.UNAVAILABLE for _, event in activity)
    mode = view["study"]["mode"]
    note = " · 模拟资格未配置" if not view["study"]["policy"] else ""
    filled = sum(event["reason"] == "FILLED_AT_T1_OPEN" for _, event in activity)
    missed = sum(event["status"] == Status.NOT_FILLED for _, event in activity)
    exited = sum(event["status"] == Status.CLOSED for _, event in activity)
    pending_exits = ""
    if view["study"]["protocol"] == POSITION_PROTOCOL:
        exits = [row["position"]["pending_exit"] for row in positions if row["position"]["pending_exit"]]
        structure = sum(exit["reasons"][0] == "STRUCTURE_NEXT_OPEN" for exit in exits)
        pending_exits = f"待开盘退出 {len(exits)} 笔（结构 {structure} · 利润保护 {len(exits) - structure}）\n"
    return (
        f'研究模拟持仓 · {view["trade_date"]} · {mode}{note}\n'
        f"当前模拟持仓 {len(positions)} 只（按策略与信号计） · 状态未更新 {stale} 笔 · 待检查 {len(pending)} 笔\n"
        f"当日成交 {filled} 笔 · 未成交 {missed} 笔 · 退出 {exited} 笔 · 无法确认 {gaps} 笔\n"
        f"{pending_exits}"
        f"累计已结束 {closed} 笔。资格、价格与状态来源见独立研究报告。\n"
    )


def _paper_sections(view: dict, *, combined: bool = False, company_labels: bool = True) -> str:
    study = view["study"]
    positions, pending, activity = _sections(view)
    closed = sum(row["status"] == Status.CLOSED for row in view["records"].values())
    issues = sum(event.get("observation", event["status"]) == Status.UNAVAILABLE for _, event in activity)
    metrics = "".join(f'<div class="metric">{label}<strong>{value}</strong></div>' for label, value in (
        ("当前模拟持仓", f"{len(positions)} 只"), ("待开盘检查", f"{len(pending)} 笔"),
        ("累计已结束", f"{closed} 笔"), ("当日无法确认", f"{issues} 笔"),
    ))
    position_cards = "".join(_position(row, company_labels=company_labels) for row in positions)
    pending_cards = "".join(_pending(row, company_labels=company_labels) for row in pending)
    events = "".join(_activity(row, event, company_labels=company_labels) for row, event in activity)
    empty_reason = "模拟资格未配置，保留开盘检查证据。" if not study["policy"] else "本轮没有符合条件且仍未退出的模拟成交。"
    rows = "".join(
        f"<tr><th scope='row'>{_label(stat['group'])}</th><td>{stat[Status.CLOSED]}</td>"
        f"<td>{_percent(stat['win_rate'])}</td><td>{_fmt(stat['mean_r'])}</td><td>{_fmt(stat['total_r'])}</td>"
        f"<td>{stat[Status.OPEN]} / {stat[Status.PENDING]} / {stat[Status.NOT_FILLED]} / {stat[Status.UNAVAILABLE]}</td></tr>"
        for stat in view["performance"]
    )
    source = view["source"]
    missing = escape("、".join(source.get("missing_target_bars", ())))
    coverage = f'<p class="notice">原日报目标日行情缺失 · {missing}</p>' if missing else ""
    positions_html = f'<div class="cards">{position_cards}</div>' if position_cards else f'<p>{empty_reason}</p>'
    pending_html = f'<div class="cards">{pending_cards}</div>' if pending_cards else '<p>当前没有待检查的计划。</p>'
    activity_html = coverage + (events or '<p>当日无状态变化或影响账本的行情缺口。</p>')
    performance_note = '<p class="small">各行按独立样本组统计，组间可能重叠。胜率、平均 R 和累计 R 仅使用已结束记录。</p>'
    performance_table = f"""
<table><thead><tr><th scope="col">样本组</th><th scope="col">已结束</th><th scope="col">胜率</th>
<th scope="col">平均 R</th><th scope="col">累计 R</th><th scope="col">持有 / 待查 / 未成交 / 缺证</th></tr></thead>
<tbody>{rows}</tbody></table>"""
    notes = '<p>形态和资格用于研究。价格以 USD 计，每个策略和信号为一个模拟单位，展示毛收益。</p>'
    audit = _facts((
        ("原日报标识", escape(source["report_id"])), ("原日报 SHA-256", escape(source["report_sha256"])),
        ("账本 SHA-256", escape(view["ledger_sha256"])), ("模拟协议", escape(study["protocol"])),
        ("日报采集时间（UTC）", escape(source["observed_at"])), ("研究版本", escape(source["research_version"])),
    ))

    if combined:
        mode = "冻结日报历史复算" if study["mode"] == Mode.HISTORICAL_REPLAY else "合成数据验证"
        return f"""<section id="paper-research" class="panel" aria-labelledby="paper-heading">
<div class="section-head"><div><h2 id="paper-heading">模拟持仓</h2><p class="section-note">{mode}</p></div></div>
<div class="metrics">{metrics}</div>
{positions_html}
<details class="fold"><summary>待检查计划 · {len(pending)} 笔</summary><div class="fold-content">{pending_html}</div></details>
<details class="fold"><summary>当日记录</summary><div class="fold-content">{activity_html}</div></details>
<details class="fold"><summary>研究绩效</summary><div class="fold-content">{performance_note}
<div class="paper-table" role="region" tabindex="0" aria-label="模拟持仓分组统计">{performance_table}</div></div></details>
<details class="fold paper-audit"><summary>模拟持仓审计与来源</summary><div class="fold-content">{notes}{audit}</div></details>
</section>"""

    return f"""<div class="metrics">{metrics}</div>
<section class="panel" id="positions"><h2>当前模拟持仓 {len(positions)} 只</h2>
{positions_html}</section>
<section class="panel" id="pending"><h2>待检查计划</h2>
{pending_html}</section>
<section class="panel" id="activity"><h2>当日记录</h2>{activity_html}</section>
<section class="panel" id="performance"><h2>研究绩效</h2>
{performance_note}{performance_table}</section>
<footer>{notes}
<details><summary>审计与来源</summary>
{audit}
</details></footer>"""


def render_paper(view: dict, *, company_labels: bool = True) -> str:
    day, study = view["trade_date"], view["study"]
    mode = "冻结日报历史复算" if study["mode"] == Mode.HISTORICAL_REPLAY else "合成数据验证"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>研究模拟持仓 · {day}</title><style>{_STYLES}</style></head><body>
<header><div class="wrap"><p>IWB B+C · XNYS · {day}</p><h1>研究模拟持仓</h1>
<p>{mode} · {study["mode"]}</p>
<nav aria-label="报告目录"><a href="#positions">当前持仓</a><a href="#pending">待检查</a>
<a href="#activity">当日记录</a><a href="#performance">研究绩效</a></nav></div></header>
<main>{_paper_sections(view, company_labels=company_labels)}</main></body></html>
"""


def render_combined_paper(daily: bytes, view: dict, *, company_labels: bool = True) -> bytes:
    """Insert the simulated positions into the frozen layout without re-rendering its records."""
    head_end = b"</head>"
    overview_link = '<a href="#overview">今日总览</a>'.encode("utf-8")
    candidates = b'<section id="candidates" class="panel">'
    markers = (head_end, overview_link, candidates)
    if (any(daily.count(marker) != 1 for marker in markers) or b'id="paper-research"' in daily
            or [daily.index(marker) for marker in markers] != sorted(daily.index(marker) for marker in markers)):
        raise ValueError("PAPER_COMBINED_UNSUPPORTED_DAILY_LAYOUT")
    content = daily.replace(head_end, f"<style>{_COMBINED_STYLES}</style></head>".encode("utf-8"), 1)
    content = content.replace(overview_link, overview_link + '<a href="#paper-research">模拟持仓</a>'.encode("utf-8"), 1)
    section = _paper_sections(view, combined=True, company_labels=company_labels).encode("utf-8")
    return content.replace(candidates, section + b"\n" + candidates, 1)
