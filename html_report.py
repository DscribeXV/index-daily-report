# -*- coding: utf-8 -*-
"""Self-contained HTML report builder + browser launcher for the indices report.

This module is intentionally standalone: it imports only stdlib + a few helpers
from run_report (avoiding a true circular import by lazy-loading run_report inside
the build function).
"""
from __future__ import annotations

import base64
import os
import sys
from datetime import datetime
from html import escape as _html_escape
from pathlib import Path


_HTML_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: #f4f6fa; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    color: #1a1a2e;
    line-height: 1.6;
    padding: 20px;
    max-width: 1400px;
    margin: 0 auto;
    font-size: 14px;
}
header {
    background: linear-gradient(135deg, #1a1a2e 0%, #2d3561 100%);
    color: #fff;
    padding: 28px 32px;
    border-radius: 12px;
    margin-bottom: 18px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    text-align: center;
}
header h1 { font-size: 26px; font-weight: 600; margin-bottom: 6px; letter-spacing: 1px; }
header .meta { opacity: 0.85; font-size: 13px; }
header .disclaimer { opacity: 0.7; font-size: 12px; margin-top: 8px; }
nav.toc {
    background: #fff;
    padding: 12px 18px;
    border-radius: 10px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    position: sticky;
    top: 8px;
    z-index: 10;
    border: 1px solid #eef0f3;
}
nav.toc a {
    color: #1a1a2e;
    text-decoration: none;
    padding: 6px 12px;
    border-radius: 16px;
    background: #f0f2f5;
    font-size: 13px;
    transition: all 0.15s ease;
}
nav.toc a:hover { background: #1a1a2e; color: #fff; }
section.summary, section.index {
    background: #fff;
    border-radius: 12px;
    padding: 24px 28px;
    margin-bottom: 20px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
    border: 1px solid #eef0f3;
}
section h2 { color: #1a1a2e; margin-bottom: 6px; font-size: 20px; }
section .subtitle { color: #666; font-size: 13px; margin-bottom: 14px; }
.summary-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 13.5px; }
.summary-table th {
    background: #1a1a2e; color: #fff;
    padding: 10px 6px; text-align: center; font-weight: 500; font-size: 12.5px;
}
.summary-table td { padding: 9px 6px; text-align: center; border-bottom: 1px solid #f0f2f5; }
.summary-table tr:nth-child(even) td { background: #f8f9fb; }
.summary-table tr:hover td { background: #fff8e1; }
.summary-table .name { text-align: left; font-weight: 500; }
.up { color: #c0392b; }
.down { color: #16a085; }
.data-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 8px;
    margin-bottom: 16px;
}
.data-cell {
    background: #f8f9fb;
    padding: 10px 14px;
    border-radius: 6px;
    border-left: 3px solid #1a1a2e;
}
.data-cell .label { font-size: 11px; color: #888; letter-spacing: 0.3px; }
.data-cell .value { font-size: 15px; font-weight: 600; color: #1a1a2e; margin-top: 2px; }
.charts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-bottom: 16px;
}
.chart-card {
    background: #fafbfc;
    border: 1px solid #eef0f3;
    border-radius: 8px;
    padding: 10px;
}
.chart-card .chart-title {
    font-size: 12px; color: #666;
    margin-bottom: 6px; text-align: center; font-weight: 500;
}
.chart-card img { width: 100%; height: auto; display: block; border-radius: 4px; }
.chart-card.empty { text-align: center; color: #999; padding: 30px; }
.analysis {
    background: #f8f9fb;
    padding: 16px 20px;
    border-radius: 8px;
    border-left: 4px solid #1a1a2e;
    font-size: 14px;
    line-height: 1.85;
    color: #2d3561;
}
.analysis p { margin-bottom: 6px; }
.analysis p:last-child { margin-bottom: 0; }
.legend { font-size: 12px; color: #888; text-align: center; margin-top: 6px; }
footer { text-align: center; color: #999; padding: 20px; font-size: 12px; }
@media (max-width: 900px) {
    .charts { grid-template-columns: 1fr; }
    nav.toc { position: static; }
    body { padding: 10px; }
    header h1 { font-size: 20px; }
    section.summary, section.index { padding: 16px; }
}
@media print {
    body { background: #fff; padding: 0; max-width: 100%; }
    nav.toc { display: none; }
    section { box-shadow: none; page-break-after: always; }
    .chart-card { page-break-inside: avoid; }
}
"""

# Use a normal middle dot via chr() to avoid any encoding surprises in source
_MIDDLE_DOT = chr(0x00B7)


def _img_data_url(path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _analysis_paragraphs(text: str) -> str:
    if not text:
        return ""
    parts = [seg.strip() for seg in text.split("。") if seg.strip()]
    return "".join(f"<p>{_html_escape(seg)}。</p>" for seg in parts)


def _sgn(v):
    return "+" if v >= 0 else ""


def _format_volume(v):
    if v is None or v == 0:
        return "-"
    if abs(v) >= 1e8:
        return f"{v/1e8:,.2f} 亿"
    if abs(v) >= 1e4:
        return f"{v/1e4:,.2f} 万"
    return f"{v:,.0f}"


def _weekday_cn(d):
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()]


def _chg_cls(x):
    return "up" if x >= 0 else "down"


def build_html(items, meta, today_dir=None, today=None) -> Path:
    """Build the self-contained HTML report. Returns the html file path."""
    if today is None:
        today = datetime.now()
    if today_dir is None:
        # Fall back to run_report's TODAY_DIR
        import run_report
        today_dir = run_report.TODAY_DIR

    html_path = Path(today_dir) / "index.html"

    # --- Summary table rows ---
    header_cells = ["指数", "最新点位", "今日涨跌", "振幅", "今日成交量", "量比",
                    "近 5 日", "近 20 日", "近 60 日"]
    summary_rows_html = []
    for it in items:
        s = it["daily"]
        v = it["intra_stats"]
        spec = it["spec"]
        if not s:
            summary_rows_html.append(
                f"<tr><td class='name'>{_html_escape(spec.cn_name)}</td>"
                f"<td colspan='8'>数据获取失败</td></tr>"
            )
            continue
        chg = v.get("change", s["change"]) if v else s["change"]
        chg_pct = v.get("change_pct", s["change_pct"]) if v else s["change_pct"]
        amp = v.get("amplitude", s["amplitude"]) if v else s["amplitude"]
        vol_str = _format_volume(v["volume"]) if v else _format_volume(s.get("volume", 0))
        vol_ratio = v.get("vol_ratio", 0.0) if v else 0.0
        last = v.get("last", s["last"]) if v else s["last"]
        arrow = "▲" if chg >= 0 else "▼"
        sign = "+" if chg_pct >= 0 else ""
        c5, c20, c60 = s["5d_chg"], s["20d_chg"], s["60d_chg"]
        summary_rows_html.append(
            f"<tr><td class='name'>{_html_escape(spec.cn_name)}</td>"
            f"<td>{last:,.2f}</td>"
            f"<td class='{_chg_cls(chg)}'>{arrow} {abs(chg):,.2f}"
            f"（{sign}{chg_pct:.2f}%）</td>"
            f"<td>{amp:.2f}%</td>"
            f"<td>{_html_escape(vol_str)}</td>"
            f"<td>{vol_ratio:.2f}</td>"
            f"<td class='{_chg_cls(c5)}'>{_sgn(c5)}{c5:.2f}%</td>"
            f"<td class='{_chg_cls(c20)}'>{_sgn(c20)}{c20:.2f}%</td>"
            f"<td class='{_chg_cls(c60)}'>{_sgn(c60)}{c60:.2f}%</td></tr>"
        )

    summary_table_html = (
        "<table class='summary-table'><thead><tr>"
        + "".join(f"<th>{h}</th>" for h in header_cells)
        + "</tr></thead><tbody>"
        + "".join(summary_rows_html)
        + "</tbody></table>"
    )

    # --- Per-index sections ---
    toc_links = ['<a href="#summary">📊 每日汇总</a>']
    sections_html = []
    for idx, it in enumerate(items):
        spec = it["spec"]
        s = it["daily"]
        v = it["intra_stats"]
        last = v.get("last", s["last"]) if v else s["last"]
        chg = v.get("change", s["change"]) if v else s["change"]
        chg_pct = v.get("change_pct", s["change_pct"]) if v else s["change_pct"]
        amp = v.get("amplitude", s["amplitude"]) if v else s["amplitude"]
        vol_ratio = v.get("vol_ratio", 0.0) if v else 0.0
        arrow = "▲" if chg >= 0 else "▼"
        sign = "+" if chg_pct >= 0 else ""

        cells = [
            ("收盘", f"{last:,.2f} {_html_escape(spec.unit)}", ""),
            ("今日涨跌", f"{arrow} {abs(chg):,.2f}（{sign}{chg_pct:.2f}%）", _chg_cls(chg)),
            ("振幅", f"{amp:.2f}%", ""),
            ("成交量", _html_escape(_format_volume(v["volume"]) if v else "-"), ""),
            ("量比", f"{vol_ratio:.2f}", ""),
        ]
        if v:
            cells += [
                ("VWAP", f"{v['vwap']:,.2f}", ""),
                ("VWAP 上方", f"{v['pct_above_vwap']:.0f}%", ""),
                ("上午成交占", f"{v['morning_share']:.0f}%", ""),
            ]
        cells += [
            ("240 日高/低", f"{s['period_high']:,.2f} / {s['period_low']:,.2f}", ""),
            ("5 / 20 / 60 日",
             f"{_sgn(s['5d_chg'])}{s['5d_chg']:.2f}% / "
             f"{_sgn(s['20d_chg'])}{s['20d_chg']:.2f}% / "
             f"{_sgn(s['60d_chg'])}{s['60d_chg']:.2f}%", ""),
        ]
        grid_html = "".join(
            f"<div class='data-cell'><div class='label'>{lbl}</div>"
            f"<div class='value {cls}'>{val}</div></div>"
            for lbl, val, cls in cells
        )

        daily_url = _img_data_url(it["daily_chart"])
        intra_url = _img_data_url(it["intra_chart"])
        if daily_url and intra_url:
            charts_html = (
                '<div class="charts">'
                f'<div class="chart-card"><div class="chart-title">近 240 个交易日日线</div>'
                f'<img src="{daily_url}" alt="日线图"></div>'
                f'<div class="chart-card"><div class="chart-title">今日日内分时（含成交量）</div>'
                f'<img src="{intra_url}" alt="分时图"></div>'
                '</div>'
            )
        else:
            charts_html = '<div class="chart-card empty">无图表数据</div>'

        analysis_html = (
            f'<div class="analysis">{_analysis_paragraphs(it["analysis"])}</div>'
        )
        sections_html.append(
            f'<section id="{spec.key}" class="index">'
            f'<h2>{idx + 1}. {_html_escape(spec.cn_name)}</h2>'
            f'<div class="subtitle">{_html_escape(spec.en_name)} '
            f'{_MIDDLE_DOT} {_html_escape(spec.market_hours)}</div>'
            f'<div class="data-grid">{grid_html}</div>'
            f'{charts_html}'
            f'{analysis_html}'
            f'</section>'
        )
        toc_links.append(f'<a href="#{spec.key}">{_html_escape(spec.cn_name)}</a>')
    toc_links.append('<a href="#notes">📋 数据说明</a>')

    # --- Notes section ---
    notes_lines = [
        "收盘价：来自日内 1 分钟分时的最后一根 K 线（即真实收盘价，非盘中快照）。",
        "240 日日线：使用东方财富前复权（fqt=1）数据，便于跨期比较。",
        "日内分时：A 股与港股来自东方财富 1 分钟 K 线；美股 / 黄金来自 1 分钟 K 线（COMEX 为近 24h 交易）。",
        "成交量：对于指数，单位为\u201c手\u201d（A 股 1 手 = 100 股）；对于 COMEX 黄金，单位为\u201c合约\u201d。",
        "量比：今日成交 ÷ 近 20 个交易日日均成交。1.0 以上为放量，以下为缩量。",
        "VWAP：日内成交量加权均价；上方时间占比反映价格相对均价的强弱。",
        "纳斯达克：东方财富代码 100.NDX 显示名为\u201c纳斯达克\u201d，对应 Nasdaq 100；如需 Nasdaq Composite (IXIC) 可参考新浪 int_nasdaq。",
        "本报告全部数据由 Codex 通过公开财经 API 自动采集与整理，仅用于研究学习，不构成投资建议。",
    ]
    notes_html = (
        '<section id="notes" class="index">'
        '<h2>📋 数据口径与说明</h2>'
        '<div class="analysis">'
        + "".join(f"<p>{_html_escape(line)}</p>" for line in notes_lines)
        + '</div></section>'
    )

    title_date = f"{today.year} 年 {today.month:02d} 月 {today.day:02d} 日"
    weekday = _weekday_cn(today)
    title_str = f"全球主要指数分析 {today.strftime('%Y-%m-%d')}"
    main_title = f"全球主要指数{_MIDDLE_DOT}每日分析报告"

    body = (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_html_escape(title_str)}</title>\n"
        f"<style>{_HTML_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<header>\n"
        f"    <h1>{main_title}</h1>\n"
        f"    <div class='meta'>报告日期：{title_date}（{weekday}）"
        f" {_MIDDLE_DOT} 生成时间：{today.strftime('%H:%M')}"
        f" {_MIDDLE_DOT} 数据源：东方财富 + 新浪财经</div>\n"
        f"    <div class='disclaimer'>本报告由 Codex 自动生成，仅作研究参考，不构成投资建议</div>\n"
        "</header>\n\n"
        '<nav class="toc">\n'
        + "".join(link + "\n" for link in toc_links)
        + "</nav>\n\n"
        '<section id="summary" class="summary">\n'
        "    <h2>📊 每日汇总</h2>\n"
        f"    {summary_table_html}\n"
        "    <div class='legend'>量比 = 今日成交量 ÷ 近 20 日均量；▲/▼ 表示涨/跌。</div>\n"
        "</section>\n\n"
        + "".join(sections_html) + "\n"
        + notes_html + "\n"
        "<footer>自动生成于 "
        f"{today.strftime('%Y-%m-%d %H:%M:%S')}"
        " {_MIDDLE_DOT} output</footer>\n"
        "</body>\n"
        "</html>\n"
    )
    html_path.write_text(body, encoding="utf-8")
    return html_path


def write_browser_launcher(today_dir=None) -> Path:
    """Write a small .bat that opens index.html in the default browser."""
    if today_dir is None:
        import run_report
        today_dir = run_report.TODAY_DIR
    bat_path = Path(today_dir) / "在浏览器中打开.bat"
    bom = b"\xef\xbb\xbf"
    content = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        'cd /d "%~dp0"\r\n'
        'start "" "index.html"\r\n'
    )
    bat_path.write_bytes(bom + content.encode("utf-8"))
    return bat_path