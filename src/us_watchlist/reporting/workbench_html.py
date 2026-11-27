"""Self-contained report components for the display-only workbench."""

from decimal import Decimal
from html import escape

from us_watchlist.domain.replay_research import TRANSITION
from us_watchlist.domain.screening import B_US_V2
from us_watchlist.domain.workbench import BCandidate, Breadth, MarketGroup, QuoteSummary, Workbench
from us_watchlist.reporting.replay_labels import metric_cells
from us_watchlist.reporting.research_html import b_gate_label, research_definitions, workbench_research

_STYLE = {"防御": "defensive", "成长": "growth", "周期": "cyclical", "未分类": "unclassified"}


def _pct(value: Decimal | None, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value:+.2%}" if signed and value else f"{value:.2%}"


def _change(value: Decimal | None) -> str:
    tone = "up" if value and value > 0 else "down" if value and value < 0 else "flat"
    return f'<span class="change {tone}">{_pct(value, signed=True)}</span>'


def _breadth(value: Breadth) -> str:
    return f'{_pct(value.ratio)} <small>{value.count:,}/{value.sample:,}</small>'


def style_badge(sector: str, style: str) -> str:
    return f'<span class="style-badge {_STYLE[style]}">{sector} · {style}</span>'


def _links(symbol: str) -> str:
    return ('<span class="quote-links">'
            f'<a href="https://www.tradingview.com/chart/?symbol={escape(symbol)}" '
            'target="_blank" rel="noopener noreferrer">TradingView</a>'
            f'<a href="https://finance.yahoo.com/quote/{escape(symbol)}/" '
            'target="_blank" rel="noopener noreferrer">Yahoo Finance</a></span>')


def quote_heading(quote: QuoteSummary, heading: str) -> str:
    company = f' <span class="company-name">{escape(quote.name)}</span>' if quote.name != quote.symbol else ""
    english = f'<small class="english-name">{escape(quote.english_name)}</small>' if quote.english_name else ""
    weight = f'<span class="note">IWB 权重 {quote.market_weight:.2f}%</span>' if quote.market_weight is not None else ""
    return f"""<div class="quote-head">
<div><{heading}><span class="ticker">{escape(quote.symbol)}</span>{company}</{heading}>{english}
<div class="quote-labels">{style_badge(quote.sector, quote.style)}{weight}</div></div>
<div class="quote-current"><strong>${quote.close:,.2f}</strong> {_change(quote.daily_change)}{_links(quote.symbol)}</div></div>"""


def scroll_table(label: str, headings: tuple[str, ...], body: str, *, extra_class: str = "") -> str:
    columns = "".join(f'<th scope="col">{heading}</th>' for heading in headings)
    return (f'<div class="table-scroll {extra_class}" role="region" aria-label="{label}" tabindex="0">'
            f'<table aria-label="{label}"><thead><tr>{columns}</tr></thead>{body}</table></div>')


def _group_cells(group: MarketGroup) -> str:
    return (f'<td>{group.sample:,}</td><td>{_change(group.daily_median)}</td>'
            f'<td>{_change(group.change_20_median)}</td><td>{_breadth(group.above_ma20)}</td>'
            f'<td>{group.b_matches:,}</td>')


def market_pulse(view: Workbench, c_count: int | str, *, b_failed: bool) -> str:
    pulse = view.pulse
    coverage = pulse.up + pulse.down + pulse.flat
    styles = "".join(
        f'<article class="style-card {_STYLE[group.style]}"><h4>{group.name} <small>{group.sample:,} 只</small></h4>'
        f'<dl><div><dt>当日中位</dt><dd>{_change(group.daily_median)}</dd></div>'
        f'<div><dt>近 20 日中位</dt><dd>{_change(group.change_20_median)}</dd></div>'
        f'<div><dt>站上 MA20</dt><dd>{_breadth(group.above_ma20)}</dd></div>'
        f'<div><dt>B 形态匹配</dt><dd>{group.b_matches:,} 只</dd></div></dl></article>'
        for group in pulse.styles
    )
    sectors = "".join(f'<tr><th scope="row">{style_badge(group.name, group.style)}</th>{_group_cells(group)}</tr>'
                      for group in pulse.sectors)
    sector_table = scroll_table("板块热度榜", ("板块", "样本", "当日中位", "近 20 日中位", "站上 MA20", "B 匹配"),
                          f'<tbody>{sectors}</tbody>', extra_class="sector-table")
    leaders = [group.name for group in pulse.sectors if group.daily_median and group.daily_median > 0]
    leading_sectors = "、".join(leaders[:3]) or "无板块中位涨幅为正"
    clusters = sorted((group for group in pulse.sectors if group.b_matches),
                      key=lambda group: (-group.b_matches, group.name))[:3]
    clustered_sectors = "、".join(f"{group.name} {group.b_matches} 只" for group in clusters) or "本轮无 B 匹配"
    if b_failed:
        clustered_sectors = "B 规则执行失败，见审计"
    stats = (
        ("b-core", "核心精选", len(view.core)), ("b-other", "B 形态匹配", "—" if b_failed else len(view.core) + len(view.other)),
        ("b-watch", "待转强预备池", len(view.watch)), ("c-results", "C 研究", c_count),
    )
    tiles = "".join(f'<a href="#{anchor}"><span>{label}</span><strong>{count}</strong></a>'
                    for anchor, label, count in stats)
    return f"""<section class="market-pulse" aria-label="市场与板块温度计">
<div class="section-head"><h3>市场与板块温度计</h3><strong class="market-state">{pulse.environment}</strong></div>
<dl class="breadth-grid">
<div><dt>上涨 / 下跌 / 平盘</dt><dd><span class="up">{pulse.up:,}</span> / <span class="down">{pulse.down:,}</span> / {pulse.flat:,}</dd>
<small title="涨跌需连续两根日线">{coverage:,} 只可比 · {pulse.observed:,}/{pulse.eligible:,} 只有当日行情</small></div>
<div><dt>站上 MA20</dt><dd>{_breadth(pulse.above_ma20)}</dd></div>
<div><dt>站上 MA60</dt><dd>{_breadth(pulse.above_ma60)}</dd></div>
<div><dt>距 60 日高点 ≤ 5%</dt><dd>{_breadth(pulse.near_high60)}</dd></div>
</dl>
<div class="style-grid">{styles}</div>
<p class="sector-leaders"><strong>领涨</strong> {leading_sectors}<br><strong>信号集中</strong> {clustered_sectors}</p>
<details class="fold"><summary>查看板块热度榜 · 按当日中位涨跌排序</summary><div class="fold-content">{sector_table}</div></details>
</section><div class="decision-grid" style="--rule-count:4">{tiles}</div>"""


def chart_svg(row: BCandidate) -> str:
    bars = row.chart
    if not bars:
        return ""
    plan = row.research.trade.plan
    guides = [("平台", row.platform, "platform")]
    if plan is not None:
        guides.extend((("触发", plan.trigger, "trigger"), ("止损", plan.stop, "stop")))
    prices = [price for item in bars for price in (item.bar.high, item.bar.low)]
    prices.extend(item.ma20 for item in bars if item.ma20 is not None)
    prices.extend(price for _, price, _ in guides)
    minimum, maximum = min(prices), max(prices)
    span = maximum - minimum or maximum * Decimal("0.02")
    bottom = minimum - span * Decimal("0.10")
    span *= Decimal("1.20")
    step = 310 / max(1, len(bars) - 1)

    def coords(index, price) -> str:
        return f"{12 + step * index:.2f},{y(price):.2f}"

    def y(price) -> float:
        return 119 - float((price - bottom) / span) * 107

    high = [coords(i, item.bar.high) for i, item in enumerate(bars)]
    low = [coords(i, item.bar.low) for i, item in enumerate(bars)]
    close = " ".join(coords(i, item.bar.close) for i, item in enumerate(bars))
    moving = " ".join(coords(i, item.ma20) for i, item in enumerate(bars) if item.ma20 is not None)
    max_volume = max(item.bar.volume for item in bars) or 1
    volumes = "".join(
        f'<rect x="{10 + step * i:.2f}" y="{158 - 25 * item.bar.volume / max_volume:.2f}" '
        f'width="{min(step * 0.7, 5):.2f}" height="{25 * item.bar.volume / max_volume:.2f}"/>'
        for i, item in enumerate(bars)
    )
    markers = []
    next_label = 17
    for label, price, modifier in sorted(guides, key=lambda guide: (-guide[1], guide[0])):
        price_y = y(price)
        label_y = max(next_label, min(83, price_y))
        next_label = label_y + 27
        markers.append(
            f'<path class="guide {modifier}" d="M12,{price_y:.2f} H323 L330,{label_y:.2f} H335"/>'
            f'<text class="guide-label {modifier}" x="339" y="{label_y:.2f}" dominant-baseline="middle">'
            f'{label} {price:,.2f}</text>'
        )
    return f"""<figure class="mini-chart">
<svg viewBox="0 0 480 182" role="img" aria-label="{escape(row.quote.symbol)} 近 {len(bars)} 个连续交易日日线">
<polygon class="price-band" points="{' '.join(high + low[::-1])}"/>
<polyline class="price-close" points="{close}"/><polyline class="price-ma20" points="{moving}"/>
{''.join(markers)}<g class="volumes">{volumes}</g>
<text x="12" y="176">{bars[0].day:%m-%d}</text><text x="322" y="176" text-anchor="end">{bars[-1].day:%m-%d}</text>
</svg><figcaption><span class="key-band">高低价带</span><span class="key-close">收盘</span>
<span class="key-ma20">MA20</span><span class="key-vol">成交量</span></figcaption></figure>"""


def _b_details(row: BCandidate) -> str:
    plan, study = workbench_research(row.research, is_b=True)
    position = _pct(row.position_120)
    definitions = research_definitions(row.research, is_b=True)
    original = metric_cells(row.evaluation.structure + row.evaluation.volume, bars=True)
    return f"""<div class="workbench-card-grid"><div>{chart_svg(row)}{plan}
<p class="note range-position">120 日区间位置 <strong>{position}</strong></p></div>{study}</div>
<details class="raw-details"><summary>原始结构、量能与计算定义</summary>{definitions}
<dl class="metrics">{original}</dl></details>"""


def _signal_badges(row: BCandidate, version: str) -> str:
    if version != B_US_V2:
        return ""
    turn = ('<span class="pill signal-fresh">今日新转强</span>' if row.fresh_turn else
            '<span class="pill signal-continuing">延续站稳</span>')
    if row.regime_aligned:
        label = "顺应防御轮动" if row.quote.style == "防御" else "顺应强势风格"
        turn += f'<span class="pill signal-aligned">{label}</span>'
    return turn


def _core_card(row: BCandidate, version: str) -> str:
    symbol = escape(row.quote.symbol)
    gate = b_gate_label(version) if version == B_US_V2 else "B 数值门槛"
    flags = _signal_badges(row, version)
    flags += ('<span class="pill warning">精选观察递补（数值门槛未过）</span>' if row.supplemental else
              f'<span class="pill">{gate}通过</span>')
    if row.research.structure.stage == TRANSITION:
        flags += '<span class="pill">2→3 切换</span>'
    return f"""<article class="watch-card core-card" id="{version}-{symbol}" data-core-symbol="{symbol}"
data-core-name="{escape(row.quote.name)}" data-core-sector="{row.quote.sector}">
{quote_heading(row.quote, "h4")}<div class="pills selection-flags">{flags}</div>{_b_details(row)}</article>"""


def _other_table(rows: tuple[BCandidate, ...], version: str) -> str:
    if not rows:
        return '<p class="empty">本轮所有 B 形态匹配均已列在上方，或本轮无匹配。</p>'
    bodies = []
    for row in rows:
        quote = row.quote
        symbol = escape(quote.symbol)
        plan = row.research.trade.plan
        rr = plan.rr if plan is not None else None
        flags = [
            label for condition, label in (
                (row.research.passed_b_numeric_gate, "数值门槛通过"),
                (row.research.structure.stage == TRANSITION, "2→3 切换"), (row.same_issuer, "同公司多类股"),
            ) if condition
        ]
        badges = _signal_badges(row, version) + "".join(f'<span class="pill">{label}</span>' for label in flags)
        sector = style_badge(quote.sector, quote.style)
        search = escape(f"{quote.symbol} {quote.name} {quote.english_name} {quote.sector} {' '.join(flags)}".lower())
        fields = (quote.daily_change, row.distance_to_platform, row.risk_to_close, rr, row.retest_ratio)
        sort_data = " ".join(f'data-value-{i}="{value if value is not None else ""}"' for i, value in enumerate(fields))
        bodies.append(f"""<tbody data-other-entry><tr id="{version}-{symbol}" data-search="{search}"
data-style="{quote.style}" data-flags="{' '.join(label for label in flags if label != '同公司多类股')}" {sort_data}>
<th scope="row"><a href="#{version}-{symbol}">{symbol}</a><small>{escape(quote.name) if quote.name != quote.symbol else ""}</small></th>
<td>{sector}<div class="row-flags">{badges}</div></td>
<td class="number">${quote.close:,.2f}<br>{_change(quote.daily_change)}</td>
<td class="number">{_pct(row.distance_to_platform, signed=True)}</td><td class="number">{_pct(row.risk_to_close)}</td>
<td class="number">{f"{rr:.2f}" if rr is not None else "—"}</td>
<td class="number">{_pct(row.retest_ratio)}</td><td class="number"><a class="detail-link" href="#{version}-{symbol}">详情</a></td></tr>
<tr class="detail-row"><td colspan="8"><details class="candidate-details"><summary>{symbol} 参考计划、量能与走势图</summary>
{_links(quote.symbol)}{_b_details(row)}</details></td></tr></tbody>""")
    sorts = tuple(f'<button type="button" data-sort="{i}">{label}<span aria-hidden="true"> ↕</span></button>'
                  for i, label in enumerate(("收盘 / 涨跌", "距平台", "止损距离", "计划 RR", "回踩缩量比")))
    table = scroll_table("其余 B 形态匹配", ("公司", "板块与标记", *sorts, "详情"), "".join(bodies), extra_class="b-candidate-table")
    filters = "".join(f'<button type="button" data-filter="{label}" aria-pressed="{str(i == 0).lower()}">{label}</button>'
                      for i, label in enumerate(("全部", "防御", "成长", "周期", "数值门槛通过", "2→3 切换")))
    return f"""<div class="toolbar match-toolbar" hidden><div class="filter-buttons" role="group" aria-label="B 匹配筛选">{filters}</div>
<label for="search-b-matches" class="sr-only">搜索 B 形态匹配</label>
<input id="search-b-matches" type="search" placeholder="搜索代码、公司名或板块">
<output for="search-b-matches" aria-live="polite"></output></div>{table}"""


def b_sections(view: Workbench, diagnostics: str, *, version: str, failed: bool) -> str:
    core = "".join(_core_card(row, version) for row in view.core)
    if not core:
        core = ('<p class="empty">该规则执行失败。原始异常见审计区。</p>' if failed else
                '<p class="empty">本轮没有满足精选条件的股票。</p>')
    watch = "".join(
        f'<tr><th scope="row">{escape(row.quote.symbol)}<small>{escape(row.quote.name)}</small></th>'
        f'<td>{style_badge(row.quote.sector, row.quote.style)}</td><td class="number">${row.quote.close:,.2f}</td>'
        f'<td>{_change(row.quote.daily_change)}</td><td class="number">${row.platform:,.2f}</td>'
        f'<td class="number">{_pct(row.distance_to_platform, signed=True)}</td><td>{_pct(row.retest_ratio)}</td>'
        f'<td>{_links(row.quote.symbol)}</td></tr>' for row in view.watch
    )
    watch_table = scroll_table("待转强预备池", ("公司", "板块·风格", "收盘", "当日涨跌", "平台", "距平台", "回踩均量 / 突破量", "行情"),
                         f'<tbody>{watch}</tbody>', extra_class="watch-table") if watch else '<p class="empty">本轮无预备池股票。</p>'
    guardrails = "通过 MA50 趋势与峰值回撤检查，" if version == B_US_V2 else ""
    return f"""<section class="panel" id="{version}"><h2>B 观察台</h2>
<section id="b-core" class="workbench-subsection"><h3>今日核心精选 <span class="count">{len(view.core)} 只</span></h3>
<div class="watch-list">{core}</div></section>
<section id="b-other" class="workbench-subsection"><h3>其余 B 形态匹配 <span class="count">{len(view.other)} 只</span></h3>
{_other_table(view.other, version)}</section>
<section id="b-watch" class="workbench-subsection"><h3>回踩到位 · 待转强预备池 <span class="count">{len(view.watch)} 只</span></h3>
<p class="section-note">{guardrails}已完成放量突破且缩量回踩在平台支撑带内，仅当日未转强，供下一交易日盯盘观察。</p>
{watch_table}</section>{diagnostics}</section>"""
