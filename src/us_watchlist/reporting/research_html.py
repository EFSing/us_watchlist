"""Default-visible structure, volume and reference prices for a research candidate."""

from collections import Counter
from decimal import Decimal
from html import escape

from us_watchlist.domain.replay_research import (
    PREFERENCES, TRANSITION, UNCONFIRMED, VOLUME_FIELDS, CandidateResearch, ReplayResearch,
    VolumeMeasure,
)
from us_watchlist.reporting.replay_labels import data_gap

_STAGE = {
    "EARLY_PULLBACK": "回踩早期",
    TRANSITION: "2→3 切换",
    "POST_H1_CONTINUATION_PROXY": "前高后延续",
    UNCONFIRMED: "结构待确认",
    "C_CLOSE_REBOUND_CONFIRMED": "收盘确认反弹",
}
_REASONS = {
    "BASE_OR_BREAKOUT_WINDOW_UNAVAILABLE": "突破锚点或突破前 60 个交易日的连续行情不足。",
    "NO_COMPLETE_POST_H1_PULLBACK_DAY": "前高之后、信号日之前没有完整的回踩交易日。",
    "INVALID_L0_L2_H1_ORDER_OR_DENOMINATOR": "基底低点、回踩低点和前高未满足 L0 < L2 < H1。",
    "C_STRUCTURE_ANCHORS_UNAVAILABLE": "连续行情中缺少 C 规则确认的前高、支撑或反弹高点。",
    "PULLBACK_ANCHOR_UNAVAILABLE": "连续行情中缺少回踩起点。",
    "NO_PULLBACK_WINDOW": "起点与信号日之间没有可用交易日。",
    "INVALID_PULLBACK_VOLUME_SUM": "窗口总成交量为零。",
    "NO_UP_OR_DOWN_DAY": "窗口内缺少上涨日或下跌日。",
    "INVALID_UP_OR_DOWN_VOLUME": "下跌日均量为零。",
    "PULLBACK_WINDOW_LT_4": "窗口不足 4 个交易日，无法比较前后半段。",
    "INVALID_PULLBACK_HALF_VOLUME": "前半段均量为零。",
    "B_HISTORY_LT_120": "不足 120 个连续交易日，无法核对完整价位和压力门槛。",
    "B_PLATFORM_UNAVAILABLE": "连续行情中缺少已匹配的突破平台。",
    "B_CLOSE_NOT_ABOVE_NOMINAL_2": "收盘价未高于移植数值门槛 2 美元。",
    "B_ACCELERATION_OVEREXTENDED": "10 日涨幅超过 35%，且收盘高于 20 日均线逾 15%。",
    "B_GAIN_EXHAUSTED": "区间位置超过 90%，且 20 日涨幅超过 40%。",
    "B_NO_SUPPORT_BELOW_CLOSE": "四项参考支撑均未低于信号日收盘价。",
    "B_STOP_DISTANCE_OUTSIDE_RANGE": "按收盘计算的止损距离须大于 0% 且不超过 9%。",
    "B_RR_BELOW_TWO_AT_CLOSE": "按信号日收盘计算的规则 RR 低于 2。",
    "B_OVERHANG_WITH_RR_BELOW_2_5": "上方筹码占比超过 50%，且按收盘计算的规则 RR 低于 2.5。",
    "REFERENCE_LEVEL_ORDER_INVALID": "以美分展示后，止损、触发、参考入场及目标无法构成有效的多头价位。",
    "C_STRUCTURE_OR_MA5_UNAVAILABLE": "缺少连续的 5 日均线或 C 规则的结构价位。",
}
_VOLUME_LABELS = (
    "下跌日成交量占比", "上涨／下跌日均量比", "回踩后半／前半均量比",
)
_TARGET = {
    "B_PRESSURE": "上方价格压力",
    "C_PRIOR_HIGH": "本段回踩前高",
    "B_TREND_2_5R": "信号日收盘风险的 2.5 倍",
    "C_TREND_2_5R": "信号日收盘风险的 2.5 倍",
}
_JUDGMENT = {"PREFERRED": "贴近偏好", "NEUTRAL": "居中", "DEVIATION": "与预期方向相反"}


def _fact(item: VolumeMeasure) -> str:
    value = item.value
    if value is None:
        return ""
    if item.field == VOLUME_FIELDS[0]:
        return "下跌日成交占比较高" if value >= Decimal("0.5") else "下跌日成交占比低于一半"
    if item.field == VOLUME_FIELDS[1]:
        if round(value, 2) == 1:
            return "上涨与下跌日的均量接近"
        return "上涨日均量较大" if value > 1 else "下跌日均量较大"
    if round(value, 2) == 1:
        return "回踩前后半段均量接近"
    direction = "缩量" if value < 1 else "放量"
    return f"回踩后半段{direction}约 {abs(value - 1):.0%}"


def _comparison(item: VolumeMeasure) -> str:
    coordinate = item.coordinate
    if coordinate and coordinate.judgment is not None:
        return f"同阶段{_JUDGMENT[coordinate.judgment]}（未验证） · {coordinate.sample_size} 只"
    if coordinate and coordinate.status == "INSUFFICIENT_CROSS_SECTION":
        return f"同阶段可比 {coordinate.sample_size} 只，至少需 3 只"
    if item.value is None:
        return ""
    if item.field == VOLUME_FIELDS[0]:
        return f"较 50% 基线偏差 {item.value * 100 - 50:+.1f} 个百分点"
    return f"较 1.00 倍基线偏差 {item.value - 1:+.1%}"


def _volume_row(item: VolumeMeasure, label: str, preference: str, *, is_b: bool, compact: bool = False) -> str:
    is_share = item.field == VOLUME_FIELDS[0]
    if item.value is None:
        shown, explanation, meter = "—", _REASONS[item.missing_reason], ""
    else:
        value = item.value
        shown = f"{value:.1%}" if is_share else f"{value:.2f} 倍"
        explanation = _fact(item)
        width = min(100, value * (100 if is_share else 50))
        scale_class = " share" if is_share else ""
        scale = "0% 至 100%" if is_share else "0 至 2 倍，中线为 1 倍"
        meter = (f'<span class="ratio-track{scale_class}" title="{scale}" aria-hidden="true">'
                 f'<i style="width:{width:.2f}%"></i></span>')
    if compact:
        return (f'<div class="research-metric"><dt>{label}</dt><dd>{shown}</dd>'
                f'<div class="research-meter">{meter}</div></div>')
    direction = "偏低" if preference == "LOW" else "偏高"
    hypothesis = f"{'偏好方向' if is_b else 'B 2→3 方向参考'} · {direction}（未验证）"
    if item.field == VOLUME_FIELDS[2]:
        hypothesis += "，居中也可能更合适"
    comparison = _comparison(item)
    rank = f'<span class="research-coordinate">{comparison}</span>' if comparison else ""
    return f"""<div class="research-metric"><dt>{label}</dt><dd>{shown}</dd>
<div class="research-meter">{meter}</div><p class="note">{explanation}</p>
<small>{hypothesis}</small>{rank}</div>"""


def _judgment(row: CandidateResearch, *, is_b: bool) -> str:
    if not is_b:
        return "C 结构已由本规则的收盘条件确认。量能用于描述回踩，C 同阶段偏好尚未建立。"
    if row.structure.stage != TRANSITION:
        return "同阶段预期判断适用于符合研究资格的 2→3 切换。本阶段以上述量能事实为准。"
    if not row.in_b_transition_cohort:
        return "属于 2→3 切换代理。移植数值门槛未获确认，同阶段判断暂缺。"
    judgments = [item.coordinate.judgment if item.coordinate else None for item in row.volume.measures]
    if any(value is None for value in judgments):
        return "综合判断需三项均可比较，现有样本或字段不足。"
    parts = []
    if all(value == "PREFERRED" for value in judgments):
        return "三项量能均贴近同阶段研究预期（未验证）。"
    if "PREFERRED" in judgments:
        parts.append("部分量能贴近研究预期（未验证）")
    deviations = "、".join(label for label, value in zip(_VOLUME_LABELS, judgments) if value == "DEVIATION")
    if deviations:
        parts.append(f"{deviations}与研究预期方向相反（未验证）")
    return "。".join(parts) + "。" if parts else "三项均处于同阶段中位（未验证）。"


def _plan(row: CandidateResearch, *, is_b: bool, compact: bool = False) -> str:
    trade = row.trade
    title = "参考计划" if compact else "参考计划（未验证）"
    eligibility = ""
    if is_b:
        label = {
            "B_NUMERIC_QUALIFIED": "B 移植数值门槛 · 通过",
            "B_NUMERIC_REJECTED": "B 移植数值门槛 · 未通过",
            "B_NUMERIC_UNAVAILABLE": "B 移植数值门槛 · 资料不足",
        }[trade.qualification]
        reason = (_REASONS[trade.qualification_reason]
                  if trade.qualification_reason and trade.qualification_reason != trade.missing_reason else "")
        eligibility = f'<p class="note">{label}。{reason}</p>'
    if trade.plan is None:
        reason = _REASONS[trade.missing_reason]
        gap = f"<p class='note'>{escape(data_gap(row.source_gap))}</p>" if row.source_gap else ""
        return f'<div class="watch-facts"><strong>{title}</strong>{eligibility}<p>{reason}</p>{gap}</div>'

    plan = trade.plan
    inputs = dict(trade.inputs)
    prices = "".join(f"<div><dt>{label}</dt><dd>${value:,.2f}</dd>{note}</div>" for label, value, note in (
        ("触发", plan.trigger, ""), ("止损", plan.stop,
         f'<small>收盘风险 {inputs["risk_to_close"]:.2%}</small>' if is_b and compact else ""),
        ("目标", plan.target, ""),
    ))
    entry = "信号日收盘与触发价取高者" if is_b else "C 模拟触发价"
    stop_risk = ""
    if not is_b:
        stop_risk = (f'\n<p class="note">至止损距离 · 参考入场 {inputs["risk_to_entry"]:.2%}'
                     f' · 信号日收盘 {inputs["risk_to_close"]:.2%}</p>')
        if inputs["stop_risk_warning"]:
            stop_risk += (f'\n<p class="note"><strong>研究风险警示</strong> · 至止损距离超过'
                          f' {inputs["stop_risk_warning_threshold"]:.0%}。</p>')
    timing = ("" if compact else
              '<p class="note">信号日收盘后生成，供下一交易日起参考。RR 以显示价位计算，费用、滑点及实际成交未计入。</p>')
    return f"""<div class="watch-facts"><strong>{title}</strong>{eligibility}
<dl class="plan-prices">{prices}<div><dt>计划 RR</dt><dd>{plan.rr:.2f} 倍</dd></div></dl>
<p class="note">参考入场 ${plan.entry:,.2f}（{entry}） · 目标依据为{_TARGET[plan.target_rule]}。</p>{stop_risk}
{timing}</div>"""


def candidate_research(row: CandidateResearch, *, is_b: bool) -> str:
    structure, volume = row.structure, row.volume
    recovery = f" · 恢复比例 {structure.recovery_ratio:.1%}" if structure.recovery_ratio is not None else ""
    stage_type = "价格结构代理" if is_b else "C 价格结构"
    reason = f'<p class="note">{escape(_REASONS[structure.reason])}</p>' if structure.reason else ""
    window = f"{volume.window_days} 个交易日" if volume.window_days is not None else "窗口不可用"
    anchor = "突破日" if is_b else "回踩前高日"
    metrics = "".join(_volume_row(item, label, preference, is_b=is_b)
                      for item, label, preference in zip(volume.measures, _VOLUME_LABELS, PREFERENCES))
    facts = "；".join(note for item in volume.measures if (note := _fact(item)))
    facts = f"{facts}。" if facts else "回踩成交量资料不足。"
    return f"""<div class="research-stage">
<strong>结构阶段 · {_STAGE[structure.stage]}</strong><span class="note">{stage_type}{recovery}</span>{reason}
</div>
<div class="watch-research-grid">
{_plan(row, is_b=is_b)}
<div class="volume-card research-volume"><strong>三项回踩量能</strong>
<p class="note">{anchor}之后、信号日前 · {window}</p>
<dl>{metrics}</dl>
<div class="research-conclusion"><strong>量能事实总结</strong><p>{facts}</p></div>
<div class="research-conclusion"><strong>结构与量能综合判断</strong><p>{_judgment(row, is_b=is_b)}</p></div>
</div></div>"""


def workbench_research(row: CandidateResearch, *, is_b: bool) -> tuple[str, str]:
    recovery = row.structure.recovery_ratio
    progress = ""
    if recovery is not None:
        progress = (f'<p class="note">恢复比例 {recovery:.1%}</p>'
                    f'<meter min="0" max="1" value="{max(0, min(1, recovery))}" aria-label="恢复比例"></meter>')
    metrics = "".join(_volume_row(item, label, preference, is_b=is_b, compact=True)
                      for item, label, preference in zip(row.volume.measures, _VOLUME_LABELS, PREFERENCES))
    facts = "、".join(note for item in row.volume.measures if (note := _fact(item)))
    return _plan(row, is_b=is_b, compact=True), f"""<div class="workbench-study">
<div class="research-stage"><strong>结构阶段 · {_STAGE[row.structure.stage]}</strong>{progress}</div>
<div class="volume-card"><strong>三项回踩量能</strong><dl>{metrics}</dl>
<p class="note volume-summary">{facts or "回踩成交量资料不足"}。</p></div>
</div>"""


def _tickers(rows: tuple[CandidateResearch, ...], empty: str) -> str:
    return "".join(
        f'<a href="#{escape(row.strategy_version)}-{escape(row.symbol)}">{escape(row.symbol)}</a>'
        for row in rows
    ) or f'<span class="note">{empty}</span>'


def research_summary(research: ReplayResearch, b_version: str) -> str:
    b = tuple(row for row in research.candidates if row.strategy_version == b_version)
    c = tuple(row for row in research.candidates if row.strategy_version != b_version)
    counts = Counter(row.trade.qualification for row in b)
    qualified = tuple(row for row in sorted(b, key=lambda row: row.symbol) if row.passed_b_numeric_gate)
    cohort = tuple(row for row in qualified if row.in_b_transition_cohort)
    transition_count = sum(row.structure.stage == TRANSITION for row in b)
    return f"""<div class="research-overview">
<div class="research-lists">
<section id="b-numeric-pass" class="research-list">
<h3>B 数值门槛通过 <span>{len(qualified):,}／{len(b):,} 只</span></h3>
<p class="note">在 B 形态匹配中核对移植数值门槛。未通过 {counts["B_NUMERIC_REJECTED"]:,} 只，资料不足 {counts["B_NUMERIC_UNAVAILABLE"]:,} 只。</p>
<div class="ticker-list">{_tickers(qualified, "本轮无通过记录")}</div>
</section>
<section id="b-structure-focus" class="research-list">
<h3>结构研究重点观察（未验证） <span>{len(cohort):,} 只</span></h3>
<p class="note">同时通过 B 数值门槛且处于 2→3 价格结构代理。本轮 2→3 代理共 {transition_count:,} 只。</p>
<div class="ticker-list">{_tickers(cohort, "本轮无交集记录")}</div>
</section>
</div>
<p class="note"><strong>美股正式 B 策略资格尚未建立。</strong> 两组按股票代码排列。</p>
<p class="note">可显示参考计划 · B {sum(row.trade.plan is not None for row in b):,}／{len(b):,} 只，
C {sum(row.trade.plan is not None for row in c):,}／{len(c):,} 条规则匹配。</p>
</div>"""


def research_definitions(row: CandidateResearch, *, is_b: bool) -> str:
    points = "".join(f"<li>{key} · {day} · ${price:,.4f}</li>" for key, day, price in row.structure.points)
    basis = ("L0 为突破前 60 日最低价。H1 为突破至信号日前的最高价，同价取首次。"
             "L2 为 H1 后至信号日前最低价。恢复比例为 (T 收盘 − L2) ÷ (H1 − L2)。"
             "低于 0.5 为回踩早期，0.5 至 1 为 2→3 切换，高于 1 为前高后延续。"
             "这些阶段为价格结构代理。"
             if is_b else "C 沿用各自规则的回踩前高、支撑下沿与反弹高点。")
    volume = row.volume
    dates = (f"<p>量能窗口 {volume.window_start} 至 {volume.window_end} · "
             f"上涨 {volume.up_days} 日 · 下跌 {volume.down_days} 日 · 平盘 {volume.flat_days} 日</p>"
             if volume.window_start else "")
    return f"""<p>{basis} 连续行情 {row.continuous_sessions} 个交易日。</p>
{f"<ul>{points}</ul>" if points else ""}{dates}
<p>下跌量占比以含平盘的总量为分母。涨跌按相邻收盘比较，后半／前半比使用均量，奇数窗口的中间日归后半段。
同阶段逐项按升序平均名次除以样本数，同值共享名次，最少需要三只合格 B 研究候选。</p>"""
