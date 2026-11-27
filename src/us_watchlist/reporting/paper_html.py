"""Self-contained offline companion for the IWB research ledger."""

from decimal import Decimal
from html import escape

from us_watchlist.domain.company_catalog import catalog_sector_style, company_name
from us_watchlist.domain.paper import (
    ACCOUNT_POLICY, POSITION_PROTOCOL, STRATEGY_LABELS, Mode, Status, entry_priority, preview_account_orders,
)
from us_watchlist.domain.screening import B_SHAPE_V1, B_VERSIONS
from us_watchlist.reporting.replay_assets import STYLE, WORKBENCH_STYLE
from us_watchlist.reporting.replay_labels import REASON as SCREENING_REASON
from us_watchlist.reporting.workbench_html import scroll_table, style_badge

_LABELS = {
    **STRATEGY_LABELS, Status.PENDING: "待开盘检查", Status.NOT_FILLED: "未成交",
    B_SHAPE_V1: "B 突破回踩",  # Preserve the rendered bytes of archived paper views.
    Status.OPEN: "模拟持仓", Status.CLOSED: "已退出", Status.UNAVAILABLE: "无法确认",
    "B_NUMERIC_QUALIFIED": "B 数值门槛通过", "B_NUMERIC_REJECTED": "B 数值门槛未通过",
    "B_NUMERIC_UNAVAILABLE": "B 数值门槛缺证",
    "C_PRICE_RESEARCH": "C 价格结构研究", "WARNING": "有风险警示", "CLEAR": "无风险警示",
    "UNKNOWN": "风险警示未定义或缺失", "CONDITIONAL_T1": "符合样本配置，待核对开盘",
    "POLICY_UNSET": "模拟资格未配置", "NO_REFERENCE_LEVELS": "参考价位缺失",
    "PLAN_CREATED": "新建计划", "FILLED_AT_T1_OPEN": "T+1 开盘模拟成交",
    "COHORT_NOT_ENABLED": "该资格样本未启用",
    "OUTSIDE_CORE_SHORTLIST": "未列入日报核心精选",
    "ALREADY_HOLDING_SYMBOL": "已有同股或同发行人持仓",
    "RECENT_EXIT_COOLDOWN": "同股或同发行人仍在平仓冷却期",
    "MAX_OPEN_POSITIONS_REACHED": "已达到持仓上限",
    "DAILY_NEW_ENTRY_LIMIT_REACHED": "已达到当日新开仓上限",
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

_ACCOUNT_STYLE = """
.paper-account .breadth-grid > div { min-width: 0; background: #fff; }
.paper-account .breadth-grid { margin-bottom: 12px; }
.paper-account .breadth-grid dd { line-height: 1.3; white-space: nowrap; }
.paper-account .breadth-grid small { display: block; margin-top: 3px; line-height: 1.45; white-space: normal; }
.paper-account .keep-together { white-space: nowrap; }
.paper-positions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.paper-position {
  --edge: #a2b4be; --rail-fill: #bcd9e4;
  min-width: 0; padding: 10px 12px; background: #fff;
  border: 1px solid var(--border); border-left: 3px solid var(--edge); border-radius: 9px;
}
.paper-position.gain { --edge: #61ac99; --rail-fill: #a8dec9; }
.paper-position.loss { --edge: #c7717e; --rail-fill: #f1b8be; }
.paper-position.scheduled { border-left-color: #d49035; }
.paper-position-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: start; }
.paper-company { color: #134e68; font-weight: 800; white-space: nowrap; }
.paper-position-head h3 { line-height: 1.3; }
.paper-position-head .company-name { font-size: 14px; }
.paper-position-head .pill { padding: 1px 6px; font-size: 12px; white-space: nowrap; }
.paper-pnl { text-align: right; white-space: nowrap; font-size: 12px; }
.paper-pnl strong { display: block; font-size: 21px; line-height: 1.15; }
.paper-rail { margin: 8px 0 7px; }
.paper-rail-labels { display: flex; justify-content: space-between; align-items: baseline; gap: 4px; font-size: 12px; }
.paper-rail-labels span { white-space: nowrap; }
.paper-rail-track { height: 7px; margin: 5px 5px 0; position: relative; border-radius: 99px; background: #edf2f5; }
.paper-rail-track > span { position: absolute; }
.paper-rail-band, .paper-rail-move { inset-block: 0; border-radius: inherit; }
.paper-rail-band { background: #dcebf1; border-inline: 1px solid #94b1bf; }
.paper-rail-move { background: var(--rail-fill); }
.paper-rail-entry { top: -3px; height: 13px; border-left: 2px solid #345466; transform: translateX(-50%); }
.paper-rail-last {
  top: 50%; width: 10px; height: 10px; transform: translate(-50%,-50%);
  border: 2px solid #fff; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 1px currentColor;
}
.paper-prices {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 4px;
  padding: 5px 6px; background: var(--surface-2); border-radius: 6px;
}
.paper-prices dt { font-size: 11px; white-space: nowrap; }
.paper-prices dd { margin: 0; font-size: 13px; overflow-wrap: normal; white-space: nowrap; }
.paper-prices small { display: block; color: var(--warning); font-size: 11px; white-space: normal; }
.paper-prices .number { white-space: nowrap; }
.paper-structure, .paper-alert { font-size: 12px; }
.paper-structure { margin: 5px 0; color: var(--muted); }
.paper-alert { padding: 4px 7px; margin-bottom: 5px; border-radius: 5px; background: #fff3db; color: var(--warning); }
.paper-position .raw-details { margin-top: 5px; padding-top: 5px; border-top: 1px solid var(--border); font-size: 12px; }
.paper-position .raw-details summary span { color: var(--muted); }
.paper-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px 10px; margin-top: 8px; }
.paper-facts dd { font-size: 13px; }
.paper-timeline { margin: 7px 0 0; padding-left: 1.45em; color: var(--muted); font-size: 12px; }
.paper-account .fold { border-radius: 8px; margin-top: 8px; }
.paper-account .fold > summary small { display: inline-block; color: var(--muted); font-weight: normal; margin-left: 8px; }
.paper-account .paper-orders table { min-width: 620px; }
.paper-orders thead th { white-space: nowrap; }
.paper-orders .company-name { white-space: nowrap; }
.paper-orders .priority { background: #edf8f4; }
.paper-orders .pill { padding: 0 5px; margin-left: 5px; font-size: 11px; }
.paper-orders-hint { display: none; }
.paper-event-counts { gap: 4px; margin-bottom: 5px; }
.paper-event-counts .pill { padding: 1px 6px; font-size: 12px; white-space: nowrap; }
.paper-account .pill.up { color: #096345; border-color: #a8d6c5; background: #eef9f5; }
.paper-account .pill.down { color: #a6273a; border-color: #e5bfc6; background: #fff3f4; }
.paper-events { margin: 0; padding: 0; list-style: none; }
.paper-event { padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
.paper-event .pill { padding: 0 6px; margin-right: 5px; font-size: 12px; }
.paper-event .note { font-size: 13px; }
.paper-event .number { white-space: nowrap; }
@media (max-width: 1100px) {
  .paper-positions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .paper-positions { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 680px) {
  .paper-orders-hint { display: block; font-size: 12px; }
  .paper-orders th[scope=row] .company-name { display: block; font-size: 12px; }
  .paper-orders .pill { display: block; width: fit-content; margin-left: 0; }
}
@media (max-width: 480px) {
  .paper-position { padding: 8px; }
  .paper-account .breadth-grid > div { padding: 7px 8px; }
  .paper-account .breadth-grid dt { font-size: 12px; }
  .paper-position-head .quote-labels { gap: 3px 4px; }
  .paper-prices { padding-inline: 4px; gap: 2px; }
  .paper-prices dd { font-size: 12px; }
}
@media (max-width: 360px) {
  .paper-prices dt { font-size: 10px; }
}
"""

_ACCOUNT_LIMITS = {
    "ALREADY_HOLDING_SYMBOL", "RECENT_EXIT_COOLDOWN", "MAX_OPEN_POSITIONS_REACHED",
    "DAILY_NEW_ENTRY_LIMIT_REACHED", "OUTSIDE_CORE_SHORTLIST",
}
_ORDINARY_MISSES = {"OPEN_BELOW_TRIGGER", "COHORT_NOT_ENABLED"}
_EXIT_ALERTS = {
    "STRUCTURE_NEXT_OPEN": "收盘确认结构破坏",
    "PROFIT_PROTECTION_NEXT_OPEN": "收盘跌破利润保护线",
}


def _label(value: str) -> str:
    return escape(_LABELS.get(value, value))


def _fmt(value, suffix: str = "") -> str:
    return "—" if value is None else f"{Decimal(value):,.2f}{suffix}"


def _percent(value) -> str:
    return _fmt(Decimal(str(value)) * 100 if value is not None else None, "%")


def _facts(items, *, css_class: str = "") -> str:
    attribute = f' class="{css_class}"' if css_class else ""
    return f"<dl{attribute}>" + "".join(f"<div><dt>{label}</dt><dd>{value}</dd></div>" for label, value in items) + "</dl>"


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
    structure = state["structure"]
    structure_label = escape(SCREENING_REASON[structure]) if "issuer_key" in plan and structure in SCREENING_REASON else _label(structure)
    facts = _facts((
        ("模拟入场日", escape(state["entry_date"])), ("实际入场 RR", _fmt(state["initial_rr"])),
        ("入场价", _fmt(state["entry"], " USD")), ("最新价", _fmt(state["latest_price"], " USD")),
        *stop_facts, ("参考目标", _fmt(plan["levels"]["target"], " USD")),
        ("浮动盈亏 / 单位", _fmt(state["pnl_per_unit"], " USD") + " · " + _percent(state["return"])),
        ("浮动 R", _fmt(state["r"], "R")), ("MFE / MAE", f'{_fmt(state["mfe_r"], "R")} / {_fmt(state["mae_r"], "R")}'),
        ("最近有效估值", escape(state["priced_on"])), ("当前结构观察", structure_label),
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


def account_mail_text(view: dict) -> str:
    positions, pending, activity = _sections(view)
    closed = [Decimal(row["position"]["r"]) for row in view["records"].values() if row["status"] == Status.CLOSED]
    win_rate = f"{sum(value > 0 for value in closed) / len(closed):.1%}" if closed else "—"
    filled = sum(event["reason"] == "FILLED_AT_T1_OPEN" for _, event in activity)
    exited = sum(event["status"] == Status.CLOSED for _, event in activity)
    lines = [f"当前持仓 {len(positions)} 只 · 待检查 {len(pending)} 笔",
             f"当日成交 {filled} 笔 · 退出 {exited} 笔",
             f"累计胜率 {win_rate} · 已实现 {sum(closed, Decimal(0)):+.2f} R"]
    for row in sorted(positions, key=lambda item: item["plan"]["symbol"]):
        symbol = row["plan"]["symbol"]
        stale = "（估值停更）" if row.get("suspended_at") else ""
        lines.append(f"{symbol} {company_name(symbol)} {Decimal(row['position']['r']):+.2f} R{stale}")
    return "\n".join(lines) + "\n"


def _mode_label(study: dict, *, include_account: bool = True) -> str:
    mode = {
        Mode.HISTORICAL_REPLAY: "冻结日报历史复算",
        Mode.SYNTHETIC: "合成数据验证",
        Mode.PROSPECTIVE: "前瞻单账户模拟跟踪",
    }[study["mode"]]
    account = study["policy"].get(ACCOUNT_POLICY)
    if account is None or not include_account:
        return mode
    deduplication = "同发行人去重" if account["deduplicate_issuer"] else "同股去重"
    core = " · 限核心精选" if account["core_only"] else ""
    account_label = deduplication if study["mode"] == Mode.PROSPECTIVE else f"单账户 · {deduplication}"
    return (f"{mode} · {account_label} · 上限 {account['max_open_positions']} 仓 · "
            f"单日最多新开 {account['max_new_entries_per_session']} 仓 · 平仓冷却 {account['cooldown_sessions']} 个交易日{core}")


def _price(value) -> str:
    return "—" if value is None else f"${Decimal(value):,.2f}"


def _r(value: Decimal) -> str:
    return f"{value:+,.2f} R" if value else "0.00 R"


def _tone(value: Decimal) -> str:
    return "up" if value > 0 else "down" if value < 0 else ""


def _company(symbol: str) -> str:
    name = company_name(symbol)
    label = f' <span class="company-name">{escape(name)}</span>' if name != symbol else ""
    return f'<span class="paper-company">{escape(symbol)}</span>{label}'


def _effective_stop(state: dict) -> Decimal:
    return Decimal(state.get("active_stop_at_open", state["stop"]))


def _next_stop(state: dict, effective: Decimal) -> Decimal | None:
    stop = Decimal(state["stop"])
    return stop if state.get("next_stop_session") and stop > effective else None


def _price_rail(stop: Decimal, entry: Decimal, latest: Decimal, target: Decimal, tone: str) -> str:
    # The stop-to-target band retains its scale when a price falls outside it.
    start, end = min(stop, entry, latest, target), max(stop, entry, latest, target)
    span = end - start
    stop_x, entry_x, last_x, target_x = ((value - start) * 100 / span for value in (stop, entry, latest, target))
    left, right = f"止损 {_price(stop)}", f"目标 {_price(target)}"
    if target < stop:
        left, right = right, left
    locked = '<span class="up">已锁盈</span>' if stop > entry else ""
    description = f"止损 {_price(stop)}，入场 {_price(entry)}，现价 {_price(latest)}，目标 {_price(target)}"
    return f"""<div class="paper-rail" role="img" aria-label="{description}{'，已锁盈' if locked else ''}">
<div class="paper-rail-labels" aria-hidden="true"><span>{left}</span>{locked}<span>{right}</span></div>
<div class="paper-rail-track" aria-hidden="true">
<span class="paper-rail-band" style="left:{min(stop_x, target_x):.4f}%;width:{abs(target_x - stop_x):.4f}%"></span>
<span class="paper-rail-move" style="left:{min(entry_x, last_x):.4f}%;width:{abs(last_x - entry_x):.4f}%"></span>
<span class="paper-rail-entry" style="left:{entry_x:.4f}%"></span>
<span class="paper-rail-last {tone}" style="left:{last_x:.4f}%"></span></div></div>"""


def _account_timeline(row: dict) -> str:
    items = []
    for event in row["history"]:
        facts = [escape(event["trade_date"]), _label(event["reason"])]
        if "opening" in event:
            facts.append(f'开盘 {_price(event["opening"])}')
        if "position" in event:
            state = event["position"]
            stop = _effective_stop(state)
            facts.extend((_price(state["latest_price"]), _r(Decimal(state["r"])), f"生效止损 {_price(stop)}"))
            next_stop = _next_stop(state, stop)
            if next_stop is not None:
                facts.append(f"次日止损 {_price(next_stop)}")
        if event.get("diagnostic"):
            facts.append(escape(event["diagnostic"]))
        items.append(f"<li>{' · '.join(facts)}</li>")
    return f'<ol class="paper-timeline" aria-label="状态历史时间线">{"".join(items)}</ol>'


def _account_position(row: dict) -> str:
    plan, state = row["plan"], row["position"]
    symbol = plan["symbol"]
    entry, latest, target, r = map(Decimal, (state["entry"], state["latest_price"], plan["levels"]["target"], state["r"]))
    effective = _effective_stop(state)
    proposed = _next_stop(state, effective)
    proposed_html = f'<small>→ 次日 <span class="number">{_price(proposed)}</span></small>' if proposed is not None else ""
    tone = _tone(r)
    movement = {"up": "gain", "down": "loss", "": ""}[tone]
    flags = style_badge(*catalog_sector_style(symbol))
    flags += f'<span class="pill">{escape(state["entry_date"][5:])} 入场</span>'
    if plan["strategy_version"] not in B_VERSIONS:
        flags += f'<span class="pill">{_label(plan["strategy_version"])}</span>'
    if plan["risk_warning"] == "WARNING":
        flags += '<span class="pill warning">有风险警示</span>'
    pf = Decimal(state["pnl_per_unit"])
    pnl = f'{Decimal(state["return"]):+.2%} ({"+" if pf > 0 else "-" if pf < 0 else ""}{_price(abs(pf))})'

    alert = ""
    pending_exit = state.get("pending_exit")
    if pending_exit:
        why = " · ".join(escape(_EXIT_ALERTS.get(reason, _LABELS.get(reason, reason))) for reason in pending_exit["reasons"])
        alert = (f'<p class="paper-alert"><strong>预约次日开盘退出</strong> · {why}'
                 f' · {escape(pending_exit["session"])}</p>')
    floor = state.get("structural_floor")
    if row.get("suspended_at"):
        structure = f'估值停更 · {_label(row["history"][-1]["reason"])}'
    elif floor is None:
        structure = "结构底线缺证"
    else:
        cushion = latest / Decimal(floor) - 1
        label = "结构完好 · 高于底线" if cushion > 0 else "收盘跌破结构底线" if cushion < 0 else "收盘触及结构底线"
        structure = f'{label} <strong class="{_tone(cushion)}">{_price(floor)} ({cushion:+.2%})</strong>'
    mfe, mae = (_r(Decimal(state[key])) for key in ("mfe_r", "mae_r"))
    prices = _facts((
        ("入场价", _price(entry)), ("最新价", _price(latest)),
        ("生效止损", _price(effective) + proposed_html), ("初始入场 RR", _fmt(state["initial_rr"], "x")),
    ), css_class="paper-prices")
    risk_facts = _facts((
        ("结构底线", _price(floor)), ("初始执行止损", _price(state["initial_stop"])),
        ("参考目标", _price(target)), ("MFE / MAE", f"{mfe} / {mae}"),
        ("最大峰值回吐", _fmt(state.get("max_mfe_drawdown_r"), " R")), ("最近估值日", escape(state["priced_on"])),
    ), css_class="paper-facts")
    return f"""<article class="paper-position {movement}{' scheduled' if pending_exit else ''}">{alert}
<div class="paper-position-head"><div><h3>{_company(symbol)}</h3><div class="quote-labels">{flags}</div></div>
<div class="paper-pnl {tone}"><strong>{_r(r)}</strong><span>{pnl}</span></div></div>
{_price_rail(effective, entry, latest, target, tone)}{prices}
<p class="paper-structure">{structure}</p><details class="raw-details"><summary>风控锚点与历史
<span>（<span class="keep-together">结构底线 {_price(floor)}</span> ·
<span class="keep-together">MFE {mfe} / MAE {mae}）</span></span></summary>
{risk_facts}{_account_timeline(row)}</details></article>"""


_ORDER_PREVIEW_STYLE = """
.paper-orders .yielded { background: #f8fafc; color: var(--muted); }
.paper-orders .yielded .paper-company { color: var(--muted); }
.paper-account .order-capacity { white-space: normal; }
"""

_ORDER_BADGES = {
    "priority": '<span class="pill up">优先候选</span>',
    "held": '<span class="pill">已持仓中</span>',
    "cooling": '<span class="pill warning">冷却期</span>',
    "duplicate": '<span class="pill">同批重复</span>',
    "outside_core": '<span class="pill">非核心精选</span>',
    "": "",
}


def _account_orders(rows: list[tuple[dict, str]]) -> str:
    if not rows:
        return '<p class="note">当前没有合格的待查委托。</p>'
    entries = []
    for rank, (row, status) in enumerate(rows, 1):
        plan = row["plan"]
        symbol, levels = plan["symbol"], plan["levels"]
        badge = _ORDER_BADGES[status]
        cells = "".join(f'<td class="number">{_price(levels[key])}</td>' for key in ("trigger", "stop", "target"))
        modifier = ' class="priority"' if status == "priority" else ' class="yielded"' if status else ""
        entries.append(
            f'<tr{modifier}><td class="number">{rank}{badge}</td>'
            f'<th scope="row">{_company(symbol)}</th><td>{style_badge(*catalog_sector_style(symbol))}</td>'
            f'{cells}<td class="number">{_fmt(levels["rr"], "x")}</td></tr>'
        )
    table = scroll_table(
        "次日待开盘检查合格委托", ("优先顺位", "公司", "板块·风格", "触发价", "止损价", "目标价", "参考 RR"),
        f'<tbody>{"".join(entries)}</tbody>', extra_class="paper-orders",
    )
    return '<p class="note paper-orders-hint">横向滑动查看价位</p>' + table


def _account_event(row: dict, event: dict, label: str, tone: str) -> str:
    reason = event["reason"]
    facts = [_label(reason)]
    if reason == "FILLED_AT_T1_OPEN":
        facts = [f'成交价 {_price(event["opening"])}']
    elif event["status"] == Status.CLOSED:
        state = event["position"]
        facts.extend((_price(state["exit_price"]), _r(Decimal(state["r"]))))
        facts.extend(_label(item) for item in state.get("exit_reasons", ())[1:])
    elif "opening" in event:
        facts.append(f'开盘 {_price(event["opening"])}')
    elif reason == "STOP_RAISED_FOR_NEXT_SESSION":
        facts.append(f'次日 {_price(event["position"]["stop"])}')
    return (f'<li class="paper-event"><span class="pill {tone}">{label}</span>{_company(row["plan"]["symbol"])}'
            f'<p class="note">{" · ".join(facts)}</p></li>')


def _account_activity(view: dict, activity: list) -> tuple[dict, str]:
    counts = dict(filled=0, exited=0, limited=0, missed=0)
    events, ordinary = [], []
    for row, event in activity:
        reason = event["reason"]
        if reason == "PLAN_CREATED":
            continue
        if reason == "FILLED_AT_T1_OPEN":
            counts["filled"] += 1
            label, tone = "开盘成交", "up"
        elif event["status"] == Status.CLOSED:
            counts["exited"] += 1
            label, tone = "退出", "down"
        elif event.get("observation", event["status"]) == Status.UNAVAILABLE:
            label, tone = "数据缺口", "warning"
        elif reason in _ACCOUNT_LIMITS:
            counts["limited"] += 1
            label, tone = "风控跳过", "warning"
        elif reason in _ORDINARY_MISSES:
            missed = reason == "OPEN_BELOW_TRIGGER"
            counts["missed"] += missed
            ordinary.append(_account_event(row, event, "未触价" if missed else "未启用", ""))
            continue
        elif reason in ("STRUCTURE_EXIT_ARMED", "PROFIT_PROTECTION_ARMED"):
            label, tone = "预约退出", "warning"
        elif reason == "STOP_RAISED_FOR_NEXT_SESSION":
            label, tone = "上调止损", "up"
        else:
            label, tone = "入场条件未达", ""
        events.append(_account_event(row, event, label, tone))

    counters = "".join(f'<span class="pill {tone}">{label} {counts[key]} 笔</span>' for key, label, tone in (
        ("filled", "开盘成交", "up"), ("exited", "止损/保护退出", "down"),
        ("limited", "风控限额/冷却跳过", "warning"), ("missed", "未触价", ""),
    ))
    missing = view["source"].get("missing_target_bars")
    coverage = f'<p class="paper-alert">原日报目标日行情缺失 · {escape("、".join(missing))}</p>' if missing else ""
    primary = f'<ul class="paper-events">{"".join(events)}</ul>' if events else '<p class="note">当日无重要状态变化。</p>'
    secondary = (f'<details class="raw-details"><summary>展开未触价与未启用明细<span class="keep-together">（{len(ordinary)} 笔）</span></summary>'
                 f'<ul class="paper-events">{"".join(ordinary)}</ul></details>') if ordinary else ""
    return counts, f'<div class="pills paper-event-counts">{counters}</div>{coverage}{primary}{secondary}'


def _account_sections(view: dict, *, combined: bool, legacy_order_badges: bool) -> str:
    study = view["study"]
    account = study["policy"][ACCOUNT_POLICY]
    limit = account["max_new_entries_per_session"]
    positions, pending, activity = _sections(view)
    records = view["records"]
    available_slots = limit
    if legacy_order_badges:
        # Reproduce the original account HTML for immutable report restoration.
        eligible = sorted(
            (row for row in pending if row["plan"]["simulation_eligibility"] == "CONDITIONAL_T1"), key=entry_priority,
        )
        orders = [
            (row, "priority" if rank <= limit and (not account["core_only"] or row["plan"]["core_rank"] is not None) else "")
            for rank, row in enumerate(eligible, 1)
        ]
    else:
        session_index = view.get("session_index")
        if session_index is None:
            session_index = max((row.get("exit_session_index", 0) for row in records.values()), default=0)
        available_slots, orders = preview_account_orders(records, account, session_index + 1)
    other_count = sum(row["plan"]["simulation_eligibility"] == "COHORT_NOT_ENABLED" for row in pending)
    closed = [Decimal(row["position"]["r"]) for row in view["records"].values() if row["status"] == Status.CLOSED]
    unrealized = [Decimal(row["position"]["r"]) for row in positions]
    total, realized = sum(unrealized, Decimal(0)), sum(closed, Decimal(0))
    mean = _r(total / len(unrealized)) if unrealized else "—"
    wins, losses = sum(r > 0 for r in unrealized), sum(r < 0 for r in unrealized)
    win_rate = f"{sum(r > 0 for r in closed) / len(closed):.1%}" if closed else "—"
    counts, events = _account_activity(view, activity)
    priority_note = "仅限核心精选" if account["core_only"] else "核心精选优先"
    capacity_note = f"单日最多新开 {limit} 仓"
    if available_slots < limit:
        capacity_note = f'<span class="order-capacity">可用空仓 {available_slots} / 单日上限 {limit}</span>'
    kpis = (
        ("当前持仓占用", f'{len(positions)} / {account["max_open_positions"]} 仓', "",
         (f'今日新开 {counts["filled"]}', f'今日平仓 {counts["exited"]}')),
        ("持仓总浮动 R", _r(total), _tone(total), (f"单仓均值 {mean}", f"{wins} 盈 {losses} 亏")),
        ("累计已实现绩效", _r(realized), _tone(realized), (f"已结 {len(closed)} 笔", f"胜率 {win_rate}")),
        ("次日合格待查委托", f"{len(orders)} 笔", "", (capacity_note, priority_note)),
    )
    metrics = []
    for label, value, tone, notes in kpis:
        note = " · ".join(f'<span class="keep-together">{part}</span>' for part in notes)
        metrics.append(f'<div><dt>{label}</dt><dd class="{tone}">{value}<small>{note}</small></dd></div>')
    cards = "".join(_account_position(row) for row in sorted(positions, key=lambda row: row["plan"]["symbol"]))
    holdings = f'<div class="paper-positions">{cards}</div>' if cards else '<p class="empty">当前没有未平仓的模拟持仓。</p>'
    other = f'<small>另 {other_count} 笔观察组未启用模拟</small>' if other_count else ""
    heading = "h2" if combined else "h1"
    date_label = f'{escape(view["trade_date"])} · ' if not combined else ""
    return f"""<section id="paper-research" class="panel paper-account workbench" aria-labelledby="paper-heading">
<div class="section-head"><div><{heading} id="paper-heading">模拟持仓</{heading}>
<p class="section-note">{date_label}{_mode_label(study, include_account=False)}</p></div></div>
<dl class="breadth-grid">{"".join(metrics)}</dl>
{holdings}
<details class="fold" id="paper-orders"><summary>次日待开盘检查合格委托 · {len(orders)} 笔{other}</summary>
<div class="fold-content">{_account_orders(orders)}</div></details>
<details class="fold" id="paper-activity"><summary>当日成交流水</summary><div class="fold-content">{events}</div></details>
<details class="fold"><summary>模拟持仓审计与来源</summary><div class="fold-content">
<p class="note">{_mode_label(study)}</p><p class="note">展示模拟毛收益。停更持仓按最近有效收盘价估值。</p>
{_audit(view, css_class="paper-facts")}</div></details></section>"""


def _audit(view: dict, *, css_class: str = "") -> str:
    source = view["source"]
    availability = (("日报可用时间（UTC）", escape(source["available_at"])),) if "available_at" in source else ()
    return _facts((
        ("原日报标识", escape(source["report_id"])), ("原日报 SHA-256", escape(source["report_sha256"])),
        ("账本 SHA-256", escape(view["ledger_sha256"])), ("模拟协议", escape(view["study"]["protocol"])),
        ("日报采集时间（UTC）", escape(source["observed_at"])), *availability,
        ("研究版本", escape(source["research_version"])),
    ), css_class=css_class)


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
    audit = _audit(view)

    if combined:
        mode = _mode_label(study)
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


def render_paper(
    view: dict, *, company_labels: bool = True, legacy_layout: bool = False, legacy_order_badges: bool = False,
) -> str:
    day, study = view["trade_date"], view["study"]
    if company_labels and not legacy_layout and ACCOUNT_POLICY in study["policy"]:
        styles = _ACCOUNT_STYLE if legacy_order_badges else _ACCOUNT_STYLE + _ORDER_PREVIEW_STYLE
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>研究模拟持仓 · {day}</title><style>{STYLE}{WORKBENCH_STYLE}{styles}</style></head>
<body class="workbench"><main>{_account_sections(view, combined=False, legacy_order_badges=legacy_order_badges)}</main></body></html>
"""
    mode = _mode_label(study)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>研究模拟持仓 · {day}</title><style>{_STYLES}</style></head><body>
<header><div class="wrap"><p>IWB B+C · XNYS · {day}</p><h1>研究模拟持仓</h1>
<p>{mode} · {study["mode"]}</p>
<nav aria-label="报告目录"><a href="#positions">当前持仓</a><a href="#pending">待检查</a>
<a href="#activity">当日记录</a><a href="#performance">研究绩效</a></nav></div></header>
<main>{_paper_sections(view, company_labels=company_labels)}</main></body></html>
"""


def render_combined_paper(
    daily: bytes, view: dict, *, company_labels: bool = True, legacy_layout: bool = False, legacy_order_badges: bool = False,
) -> bytes:
    """Insert the simulated positions into the frozen layout without re-rendering its records."""
    head_end = b"</head>"
    overview_link = '<a href="#overview">今日总览</a>'.encode("utf-8")
    candidates = b'<section id="candidates" class="panel">'
    markers = (head_end, overview_link, candidates)
    if (any(daily.count(marker) != 1 for marker in markers) or b'id="paper-research"' in daily
            or [daily.index(marker) for marker in markers] != sorted(daily.index(marker) for marker in markers)):
        raise ValueError("PAPER_COMBINED_UNSUPPORTED_DAILY_LAYOUT")
    if company_labels and not legacy_layout and ACCOUNT_POLICY in view["study"]["policy"]:
        styles = _ACCOUNT_STYLE if legacy_order_badges else _ACCOUNT_STYLE + _ORDER_PREVIEW_STYLE
        if b'<body class="workbench">' not in daily:
            styles = f"@scope (#paper-research) {{ {WORKBENCH_STYLE} }}" + styles
        section = _account_sections(view, combined=True, legacy_order_badges=legacy_order_badges)
    else:
        styles = _COMBINED_STYLES
        section = _paper_sections(view, combined=True, company_labels=company_labels)
    content = daily.replace(head_end, f"<style>{styles}</style></head>".encode("utf-8"), 1)
    content = content.replace(overview_link, overview_link + '<a href="#paper-research">模拟持仓</a>'.encode("utf-8"), 1)
    return content.replace(candidates, section.encode("utf-8") + b"\n" + candidates, 1)
