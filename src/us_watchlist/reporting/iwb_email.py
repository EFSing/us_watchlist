"""Email-safe Chinese summary projected solely from the validated IWB receipt."""

from html import escape

_RULES = (
    ("us_breakout_retest_shape_v1", "B 突破回踩"),
    ("us_c_trend_pullback_balanced_a_v1", "C 均衡"),
    ("us_c_trend_pullback_conservative_b_v1", "C 保守"),
)


def render_email_summary(report: dict) -> tuple[str, str, str]:
    day = report["trade_date"]
    status = "部分覆盖" if report["status"] == "PARTIAL_COVERAGE" else "完成"
    rows = [(label, report["strategies"][version]["matches"]) for version, label in _RULES]
    full_history = report.get("full_history_symbols")
    history_coverage = (
        f"{full_history:,}/{report['listed_equities']:,}"
        if full_history is not None else "旧版归档未记录"
    )
    facts = [
        ("交易日", day),
        ("报告状态", status),
        ("IWB 股票池", f"{report['base_equities']:,} 只，符合上市条件 {report['listed_equities']:,} 只"),
        ("目标日行情", f"{report['target_bars']:,}/{report['listed_equities']:,}"),
        ("120 日完整历史", history_coverage),
        *((label, f"{count} 只") for label, count in rows),
    ]
    summary = "\n".join(f"{label}：{value}" for label, value in facts)
    footer = "完整候选、2→3 结构、量能、参考触发／止损／目标及 RR 见 HTML 附件。研究效果未验证，不构成交易指令。"
    plain = f"美股 IWB B+C 研究日报\n\n{summary}\n\n{footer}\n"
    html_rows = "".join(
        f'<tr><th style="text-align:left;padding:6px 14px 6px 0">{escape(label)}</th>'
        f'<td style="padding:6px 0">{escape(str(value))}</td></tr>'
        for label, value in facts
    )
    html_body = (
        '<div style="font-family:Arial,sans-serif;color:#172033;line-height:1.6">'
        f'<h2>美股 IWB B+C 研究日报 · {escape(day)}</h2>'
        f'<table style="border-collapse:collapse">{html_rows}</table>'
        f'<p>{escape(footer)}</p></div>'
    )
    return f"美股 IWB B+C 研究日报｜{day}｜{status}", plain, html_body
