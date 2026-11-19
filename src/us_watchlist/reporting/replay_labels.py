"""Chinese labels for the replay projection, leaving machine values intact."""

import re
from decimal import Decimal
from html import escape

from us_watchlist.domain.screening import Metrics


STATUS = {
    "AVAILABLE": "可用",
    "LOCAL_IWB": "本地冻结版本",
    "PARTIAL": "部分覆盖",
    "SUCCESS": "完成",
    "PARTIAL_COVERAGE": "部分覆盖",
    "FAILED": "执行失败",
    "FAILED_STRATEGY": "有规则执行失败",
    "DATA_UNAVAILABLE": "没有足够历史数据",
    "NO_CANDIDATES_IN_UNIVERSE": "股票池为空",
    "SUCCESS_WITH_MATCHES": "完成，有匹配",
    "SUCCESS_NO_MATCH": "完成，无匹配",
    "YAHOO_TARGET_COVERAGE_BELOW_FLOOR": "当日行情覆盖低于要求",
    "YAHOO_STRATEGY_HISTORY_UNAVAILABLE": "有规则缺少足够历史",
}

REASON = {
    "SHAPE_MATCH": "突破回踩形态匹配",
    "NO_QUALIFYING_BREAKOUT": "未找到符合条件的放量突破",
    "FIRST_BREAKOUT_RETEST_FAILED": "首次合格突破后的回踩未达条件",
    "INCOMPLETE_HISTORY": "所需历史行情不足",
    "NO_DISTINCT_HIGHER_LOW_PAIR": "未找到间隔足够的两个递高低点",
    "NO_PRE_PULLBACK_PEAK": "未找到回踩前高",
    "PULLBACK_DEPTH_OUTSIDE_CANDIDATE": "回踩时长或深度未达条件",
    "NO_CONFIRMED_REBOUND_HIGH": "未找到幅度合格且已确认的反弹高点",
    "TREND_NOT_QUALIFIED": "上涨趋势未达条件",
    "REBOUND_NOT_CONFIRMED": "当日收盘未确认反弹",
    "TREND_PULLBACK_REBOUND_SUPPORT_MATCH": "趋势、回踩、支撑与反弹确认均匹配",
    "IWB_UNLISTED_OR_NO_MARKET": "无有效上市市场",
    "IWB_WHEN_ISSUED": "待发行证券",
    "T_CLOSE_BREAK": "当日收盘跌破支撑下沿",
    "PULLBACK_SUPPORT_DESTROYED": "回踩期间收盘跌破支撑下沿",
}

_VALUES = {
    **REASON,
    "T_INTRADAY_PUNCTURE_RECOVERED": "当日盘中跌破支撑后收回",
    "PULLBACK_INTRADAY_PUNCTURE_RECOVERED": "回踩期间盘中跌破支撑后收回",
    "INTACT": "支撑完好",
    "Zero baseline": "基准均量为零",
    "Zero breakout volume": "突破日成交量为零",
    "ZERO_BASELINE": "基准中位成交量为零",
    "ZERO_MAD": "基准成交量离差为零",
    "ZERO_REFERENCE_VOLUME": "参考期中位成交量为零",
    "UNDETERMINED": "量能变化无法判定",
    "UNAVAILABLE": "数据不足或基准为零",
    "CONTRACTED_OBSERVABLE": "观察到缩量",
    "EXPANDED_OBSERVABLE": "观察到放量",
    "MIXED_OBSERVABLE": "量能变化不明显",
    "INSUFFICIENT_DIRECTIONAL_DAYS": "上涨日或下跌日少于两天",
    "ZERO_DOWN_DIRECTIONAL_VOLUME": "下跌日中位成交量为零",
}

# Unit and precision are defined by field, since several ratios are not percentages.
METRIC = {
    "Breakout date": ("突破日", ""),
    "Platform": ("突破前平台价", "price"),
    "Close / platform": ("收盘价相对平台价", "percent"),
    "Near platform": ("回踩位置达标", ""),
    "Turn strength": ("收盘转强条件达标", ""),
    "Breakout volume / prior 20d mean": ("突破日量／前 20 日均量", "ratio"),
    "Retest mean volume / breakout": ("回踩均量／突破日量", "ratio"),
    "Retest contracted": ("回踩缩量条件达标", ""),
    "Trend qualified": ("上涨趋势达标", ""),
    "MA20": ("20 日均线", "price"),
    "Slow MA": ("慢速均线", "price"),
    "Log slope per session": ("收盘价对数趋势斜率", "slope"),
    "Up-close fraction": ("上涨收盘占比", "percent"),
    "Peak date": ("回踩前高日期", ""),
    "Prior high": ("回踩前高", "price"),
    "Pullback depth": ("回踩深度", "percent"),
    "First low date": ("第一低点日期", ""),
    "Second low date": ("第二低点日期", ""),
    "Support floor": ("支撑下沿", "price"),
    "Support ceiling": ("支撑上沿", "price"),
    "Support status": ("支撑状态", ""),
    "Support display buffer": ("支撑展示容差", "price"),
    "Rebound date": ("反弹高点日期", ""),
    "Rebound high": ("反弹高点", "price"),
    "Rebound size": ("反弹幅度", "percent"),
    "T close location": ("收盘在日内区间的位置", "percent"),
    "Confirmation": ("收盘确认反弹", ""),
    "Stage resistance distance": ("阶段前高相对收盘的距离", "percent"),
    "Near stage resistance": ("接近阶段前高", ""),
    "RV_T": ("当日量／前 20 日中位量", "ratio"),
    "RV_T ≥ 2": ("当日量达到基准的 2 倍", ""),
    "Robust volume z": ("量能偏离程度（稳健 z 值）", "score"),
    "Robust volume z ≥ 3": ("稳健 z 值达到 3", ""),
    "Pullback / baseline median volume": ("回踩中位量／回踩前参考中位量", "ratio"),
    "Pullback volume path": ("回踩量能变化", ""),
    "Second / first half median volume": ("回踩后半段／前半段中位量", "ratio"),
    "Up / down median volume": ("上涨日／下跌日中位量", "ratio"),
    "Up days": ("回踩期间上涨日数", "days"),
    "Down days": ("回踩期间下跌日数", "days"),
}

_DIAGNOSTICS = (
    (r"YAHOO_SPLIT_BASIS_UNVERIFIED (.+)", "拆股调整未验证，已剔除末次拆股日及以前行情。拆股日期 {0}"),
    (r"YAHOO_TARGET_CLOSE_UNCONFIRMED", "Yahoo 行情时间未能确认当日已收盘，已剔除该日行情"),
    (r"YAHOO_REGULAR_HISTORY_GAP (\d+)/(\d+)", "采集窗口 {1} 个交易日中有 {0} 根合资格日线"),
    (r"Only (\d+) of (\d+) expected calendar sessions supplied", "所需 {1} 个交易日，仅提供 {0} 个"),
    (r"(\d+) missing session\(s\), latest (.+)", "缺少 {0} 个交易日的行情，最近缺失日期 {1}"),
    (r"YAHOO_FETCH_FAILED(?: .*)?", "行情未能取得"),
    (r"YAHOO_QUOTE_REJECTED(?: .*)?", "行情未通过校验"),
)


def data_gap(text: str) -> str:
    descriptions = []
    for part in text.split(" · ") if text else ():
        for pattern, label in _DIAGNOSTICS:
            if match := re.fullmatch(pattern, part):
                descriptions.append(label.format(*match.groups()))
                break
        else:
            descriptions.append("其他行情缺口，原始诊断见审计记录")
    return "；".join(descriptions)


def _metric_value(value: str | int | float | Decimal | bool, unit: str) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, str):
        return _VALUES.get(value, value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else "见原始记录")
    if unit == "percent":
        return f"{value:.2%}"
    if unit == "price":
        return f"${value:,.4f}" if 0 < abs(value) < 1 else f"${value:,.2f}"
    if unit == "ratio":
        return f"{value:.2f} 倍"
    if unit == "slope":
        return f"{value * 10000:.2f} 基点／日"
    if unit == "days":
        return f"{value:,} 日"
    return f"{value:,}" if isinstance(value, int) else f"{value:.2f}"


def metric_cells(metrics: Metrics, *, bars: bool = False) -> str:
    cells = []
    for name, value in metrics:
        label, unit = METRIC.get(name, ("其他指标（见原始记录）", ""))
        bar = ""
        if bars and unit == "ratio" and isinstance(value, (Decimal, float, int)):
            width = max(0, min(100, value * 50))
            bar = (f'<span class="ratio-track" title="刻度 0 至 2 倍，中线为 1 倍" aria-hidden="true">'
                   f'<i style="width:{width:.2f}%"></i></span>')
        cells.append(f"<div><dt>{label}</dt><dd>{escape(_metric_value(value, unit))}{bar}</dd></div>")
    return "".join(cells)
