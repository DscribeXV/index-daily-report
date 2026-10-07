# -*- coding: utf-8 -*-
"""Global major indices daily report.

- 240-day daily kline + 1-min intraday kline for 6 indices
- Generates a PDF with two charts per index, summary, and brief analysis
- Outputs to <base>/output/<date> 指数分析/ inside the project folder
"""
from __future__ import annotations

import io
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import requests
from matplotlib import font_manager, rcParams
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)



# Force UTF-8 on stdout/stderr when running under a Windows console (chcp 65001)
# so progress lines like [上证指数] render correctly in the cmd window.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    from html_report import build_html, write_browser_launcher
except Exception as _e:  # HTML output is optional
    build_html = None
    write_browser_launcher = None
    print(f"  (html_report unavailable: {_e})", flush=True)

from data_source import IndexSpec, INDICES, fetch_kline, fetch_intraday as _tencent_intraday

# ----- Paths -----
BASE_DIR = Path(__file__).resolve().parent
TODAY = datetime.now()
OUTPUT_ROOT = BASE_DIR / "output"
TODAY_DIR = OUTPUT_ROOT / f"{TODAY.strftime('%Y-%m-%d')} 指数分析"
CHART_DIR = TODAY_DIR / "charts"
PDF_PATH = TODAY_DIR / f"{TODAY.strftime('%Y-%m-%d')} 全球主要指数分析.pdf"
TODAY_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR.mkdir(parents=True, exist_ok=True)


# ----- Fonts -----
def setup_fonts() -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    simhei = r"C:\Windows\Fonts\simhei.ttf"
    if os.path.exists(simhei):
        font_manager.fontManager.addfont(simhei)
        rcParams["font.sans-serif"] = ["SimHei"]
    else:
        rcParams["font.sans-serif"] = ["DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False


# ----- Stats -----
def compute_daily_stats(history: list[dict]) -> dict:
    if not history:
        return {}
    closes = [r["close"] for r in history]
    last = history[-1]
    prev = history[-2] if len(history) > 1 else last
    win5 = history[-6:-1] if len(history) > 5 else history[:-1]
    win20 = history[-21:-1] if len(history) > 20 else history[:-1]
    win60 = history[-61:-1] if len(history) > 60 else history[:-1]
    win120 = history[-121:-1] if len(history) > 120 else history[:-1]

    def pct(a, b):
        if not a:
            return 0.0
        return (b - a) / a * 100.0

    avg_vol_20 = sum(r["volume"] for r in win20) / len(win20) if win20 else 0.0
    return {
        "last": last["close"],
        "prev_close": prev["close"],
        "change": last["close"] - prev["close"],
        "change_pct": pct(prev["close"], last["close"]),
        "open": last["open"],
        "high": last["high"],
        "low": last["low"],
        "date": last["date"][:10],
        "period_high": max(closes),
        "period_low": min(closes),
        "period_high_date": history[closes.index(max(closes))]["date"][:10],
        "period_low_date": history[closes.index(min(closes))]["date"][:10],
        "5d_chg": pct(win5[0]["close"], last["close"]) if win5 else 0.0,
        "20d_chg": pct(win20[0]["close"], last["close"]) if win20 else 0.0,
        "60d_chg": pct(win60[0]["close"], last["close"]) if win60 else 0.0,
        "120d_chg": pct(win120[0]["close"], last["close"]) if win120 else 0.0,
        "n": len(history),
        "amplitude": last.get("amplitude", 0.0),
        "volume": last.get("volume", 0.0),
        "amount": last.get("amount", 0.0),
        "avg_vol_20": avg_vol_20,
    }


def compute_intraday_stats(intra: list[dict], daily_stats: dict) -> dict:
    """Aggregate today's intraday bars and compute intra-day indicators."""
    if not intra:
        return {}
    # Use last bar as current price
    last = intra[-1]
    first = intra[0]
    day_high = max(r["high"] for r in intra)
    day_low = min(r["low"] for r in intra)
    total_vol = sum(r["volume"] for r in intra)
    total_amt = sum(r["amount"] for r in intra)
    avg_price = (total_amt / total_vol) if total_vol else last["close"]
    n = len(intra)

    # Volume profile: split morning + afternoon by time
    morning = [r for r in intra if r["dt"].hour < 12 or (r["dt"].hour == 11 and r["dt"].minute <= 30) or (r["dt"].hour == 12 and r["dt"].minute == 0)]
    afternoon = [r for r in intra if r not in morning]
    morning_vol = sum(r["volume"] for r in morning) if morning else 0
    afternoon_vol = sum(r["volume"] for r in afternoon) if afternoon else 0

    # VWAP
    # For an index, amount/volume doesn't equal price (it equals weighted constituent price).
    # Use close*volume to get a volume-weighted average index level (VWAP in points).
    cum_pv = 0.0
    cum_vol = 0.0
    above_vwap = 0
    for r in intra:
        cum_pv += r["close"] * r["volume"]
        cum_vol += r["volume"]
        vwap = cum_pv / cum_vol if cum_vol else r["close"]
        if r["close"] > vwap:
            above_vwap += 1
    pct_above_vwap = above_vwap / n * 100.0 if n else 0.0

    prev_close = daily_stats.get("prev_close", first["open"])
    intraday_pct = ((last["close"] - prev_close) / prev_close * 100.0) if prev_close else 0.0
    intraday_amp = (day_high - day_low) / prev_close * 100.0 if prev_close else 0.0

    return {
        "bars": n,
        "first_time": first["dt"],
        "last_time": last["dt"],
        "open": first["open"],
        "high": day_high,
        "low": day_low,
        "last": last["close"],
        "prev_close": prev_close,
        "change": last["close"] - prev_close,
        "change_pct": intraday_pct,
        "amplitude": intraday_amp,
        "volume": total_vol,
        "amount": total_amt,
        "avg_price": avg_price,
        "morning_vol": morning_vol,
        "afternoon_vol": afternoon_vol,
        "morning_share": (morning_vol / total_vol * 100.0) if total_vol else 0.0,
        "vwap": cum_pv / cum_vol if cum_vol else 0.0,
        "pct_above_vwap": pct_above_vwap,
        "avg_vol_20": daily_stats.get("avg_vol_20", 0.0),
        "vol_ratio": (total_vol / daily_stats["avg_vol_20"]) if daily_stats.get("avg_vol_20") else 0.0,
    }


def format_num(v, digits=2):
    if v is None or v == 0:
        return "-"
    if abs(v) >= 1e8:
        return f"{v/1e8:.{digits}f} 亿"
    if abs(v) >= 1e4:
        return f"{v/1e4:.{digits}f} 万"
    return f"{v:,.{digits}f}"


def format_volume(v):
    """Format trading volume in a human-friendly way (shares/contracts)."""
    if v is None or v == 0:
        return "-"
    if abs(v) >= 1e8:
        return f"{v/1e8:,.2f} 亿"
    if abs(v) >= 1e4:
        return f"{v/1e4:,.2f} 万"
    return f"{v:,.0f}"


# ----- Analysis -----
def build_analysis(spec: IndexSpec, daily: dict, intra: dict) -> str:
    if not daily:
        return f"{spec.cn_name}：数据获取失败，请稍后重试或检查网络。"
    s = daily
    name = spec.cn_name
    last = intra.get("last") if intra else s["last"]
    chg_pct = intra.get("change_pct", s["change_pct"])
    chg = intra.get("change", s["change"])
    hi = s["period_high"]; lo = s["period_low"]
    high_date = s["period_high_date"]; low_date = s["period_low_date"]
    d5 = s["5d_chg"]; d20 = s["20d_chg"]; d60 = s["60d_chg"]
    direction = "上涨" if chg_pct >= 0 else "下跌"
    sign = "+" if chg_pct >= 0 else ""
    head = (f"截至 {s['date']} 收盘，{name}报 {last:,.2f} {spec.unit}，"
            f"今日{direction} {abs(chg):,.2f} 点（{sign}{chg_pct:.2f}%），"
            f"日内振幅 {intra.get('amplitude', s['amplitude']):.2f}%。")
    rng = (f"近 {s['n']} 个交易日区间高点 {hi:,.2f}（{high_date}），"
           f"低点 {lo:,.2f}（{low_date}），")
    mom = f"5 日 {sgn(d5)}{d5:.2f}%，20 日 {sgn(d20)}{d20:.2f}%，60 日 {sgn(d60)}{d60:.2f}%。"
    pos = (last - lo) / max(hi - lo, 1e-9) * 100.0
    regimes = []
    if d20 > 3 and d60 > 5:
        regimes.append("中短期趋势偏多，呈现震荡上行")
    elif d20 < -3 and d60 < -5:
        regimes.append("中短期趋势偏空，处于震荡回落阶段")
    else:
        regimes.append("中短期趋势以震荡为主，未见明确方向")
    if pos >= 80:
        regimes.append("当前价格已处于区间高位")
    elif pos <= 20:
        regimes.append("当前价格位于区间低位")
    else:
        regimes.append(f"当前价格处于区间 {pos:.0f}% 位置（中段）")
    regime = "；" + "，".join(regimes) + "。"

    volume_part = ""
    if intra:
        v = intra
        vol_ratio = v.get("vol_ratio", 0.0)
        if vol_ratio >= 1.5:
            vol_desc = f"显著放量（量比 {vol_ratio:.2f}，约为 20 日均量的 {vol_ratio:.1f} 倍）"
        elif vol_ratio >= 1.0:
            vol_desc = f"温和放量（量比 {vol_ratio:.2f}）"
        elif vol_ratio >= 0.6:
            vol_desc = f"成交偏低（量比 {vol_ratio:.2f}）"
        else:
            vol_desc = f"明显缩量（量比 {vol_ratio:.2f}，不足 20 日均量的六成）"
        morning_share = v.get("morning_share", 0.0)
        if morning_share > 60:
            vol_desc += f"，上午成交占 {morning_share:.0f}%，尾盘参与度有限"
        elif morning_share < 40:
            vol_desc += f"，下午成交占 {100 - morning_share:.0f}%，午后发力明显"
        vwap = v.get("vwap", 0.0)
        above_pct = v.get("pct_above_vwap", 0.0)
        if last > vwap and above_pct > 50:
            vol_desc += f"，多数时间在 VWAP {vwap:,.2f} 上方运行，趋势偏多"
        elif last < vwap and above_pct < 50:
            vol_desc += f"，多数时间在 VWAP {vwap:,.2f} 下方运行，趋势偏空"
        volume_part = f"今日成交 {vol_desc}。"

    if spec.key == "gold":
        tail = "黄金受美元实际利率、地缘风险与央行购金等因素影响较大，需结合宏观环境综合判断。"
    elif spec.key in ("sh", "chinext"):
        tail = "需结合成交量与板块轮动判断持续性，关注政策面与流动性变化。"
    elif spec.key in ("hsi", "hstech"):
        tail = "港股受海外资金面与南向资金影响显著，跟踪美联储动向与国内经济数据。"
    else:
        tail = "估值与盈利预期是决定中期方向的核心，建议结合宏观与利率环境评估。"

    return head + rng + mom + regime + volume_part + tail


def sgn(v):
    return "+" if v >= 0 else ""


# ----- Charts -----
def draw_daily_chart(spec: IndexSpec, history: list[dict], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 3.4), dpi=140)
    if not history:
        ax.text(0.5, 0.5, "无数据", ha="center", va="center", transform=ax.transAxes)
        fig.savefig(path, bbox_inches="tight"); plt.close(fig); return
    dates = [datetime.strptime(r["date"][:10], "%Y-%m-%d") for r in history]
    closes = [r["close"] for r in history]
    ax.plot(dates, closes, color=spec.color, linewidth=1.5, label=spec.cn_name)
    ax.fill_between(dates, closes, min(closes), color=spec.color, alpha=0.08)
    ax.set_title(f"{spec.cn_name}  近 {len(history)} 个交易日走势", fontsize=12)
    ax.set_ylabel(spec.unit, fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.autofmt_xdate(rotation=0, ha="center")
    ax.scatter([dates[-1]], [closes[-1]], color=spec.color, s=22, zorder=3)
    pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] else 0
    sign = "+" if pct >= 0 else ""
    ax.annotate(f"{closes[-1]:,.2f}\n{sign}{pct:.2f}%",
                xy=(dates[-1], closes[-1]), xytext=(8, 8),
                textcoords="offset points", fontsize=9, color=spec.color)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def draw_intraday_chart(spec: IndexSpec, intra: list[dict], path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8.6, 4.0), dpi=140,
        gridspec_kw={"height_ratios": [3, 1]}, sharex=True,
    )
    if not intra:
        ax1.text(0.5, 0.5, "无日内数据", ha="center", va="center", transform=ax1.transAxes)
        fig.savefig(path, bbox_inches="tight"); plt.close(fig); return
    times = [r["dt"] for r in intra]
    prices = [r["close"] for r in intra]
    opens = [r["open"] for r in intra]
    highs = [r["high"] for r in intra]
    lows = [r["low"] for r in intra]
    vols = [r["volume"] for r in intra]
    base = intra[0]["open"]
    ax1.axhline(base, color="#888", linewidth=0.6, linestyle="--", alpha=0.6)
    ax1.plot(times, prices, color=spec.color, linewidth=1.4)
    ax1.fill_between(times, prices, base, where=[p >= base for p in prices],
                     color="#C0392B", alpha=0.12, interpolate=True)
    ax1.fill_between(times, prices, base, where=[p < base for p in prices],
                     color="#27AE60", alpha=0.12, interpolate=True)
    ax1.scatter([times[-1]], [prices[-1]], color=spec.color, s=22, zorder=3)
    ax1.set_title(f"{spec.cn_name}  今日日内分时  {intra[0]['dt'].strftime('%Y-%m-%d')}",
                  fontsize=12)
    ax1.set_ylabel(spec.unit, fontsize=10)
    ax1.grid(True, linestyle="--", alpha=0.35)
    last_pct = (prices[-1] - base) / base * 100
    sign = "+" if last_pct >= 0 else ""
    ax1.annotate(f"{prices[-1]:,.2f}\n{sign}{last_pct:.2f}%",
                 xy=(times[-1], prices[-1]), xytext=(8, 8),
                 textcoords="offset points", fontsize=9, color=spec.color)

    # Volume bars
    bar_colors = [spec.color if prices[i] >= opens[i] else "#27AE60"
                  for i in range(len(intra))]
    ax2.bar(times, vols, color=bar_colors, width=0.0008, alpha=0.6)
    ax2.set_ylabel("成交量", fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.3)
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ----- PDF -----
def _weekday_cn(d):
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()]


def build_pdf(items: list[dict], meta: dict) -> None:
    doc = SimpleDocTemplate(
        str(PDF_PATH), pagesize=A4,
        leftMargin=16*mm, rightMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm,
        title="全球主要指数分析", author="Codex 自动化生成",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="STSong-Light",
                        fontSize=20, leading=24, alignment=1, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="STSong-Light",
                        fontSize=14, leading=18, spaceBefore=4, spaceAfter=4,
                        textColor=colors.HexColor("#1A1A2E"))
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="STSong-Light",
                          fontSize=10, leading=15, spaceAfter=3, alignment=4)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontName="STSong-Light",
                           fontSize=9, leading=12, spaceAfter=2)
    caption = ParagraphStyle("cap", parent=styles["Italic"], fontName="STSong-Light",
                             fontSize=8.5, leading=11, textColor=colors.HexColor("#666666"),
                             spaceAfter=2, alignment=1)

    story = []
    story.append(Paragraph("全球主要指数 · 每日分析报告", h1))
    story.append(Paragraph(
        f"报告日期：{TODAY.strftime('%Y 年 %m 月 %d 日')}（{_weekday_cn(TODAY)}）　·　"
        f"生成时间：{TODAY.strftime('%H:%M')}",
        caption,
    ))
    story.append(Paragraph(
        "数据源：东方财富（push2his.eastmoney.com）+ 新浪财经（hq.sinajs.cn）补充。"
        "本报告由 Codex 自动生成，仅作研究参考，不构成投资建议。",
        caption,
    ))
    story.append(Spacer(1, 4*mm))

    # ---- Summary table ----
    header = ["指数", "最新点位", "今日涨跌", "振幅", "今日成交量", "量比",
              "近 5 日", "近 20 日", "近 60 日"]
    rows = [header]
    for it in items:
        s = it["daily"]; v = it["intra_stats"]
        if not s:
            rows.append([it["spec"].cn_name] + ["-"] * 8); continue
        sign = lambda x: f"{'+' if x >= 0 else ''}{x:.2f}%"
        chg = v.get("change", s["change"]) if v else s["change"]
        chg_pct = v.get("change_pct", s["change_pct"]) if v else s["change_pct"]
        amp = v.get("amplitude", s["amplitude"]) if v else s["amplitude"]
        vol_str = format_volume(v["volume"]) if v else format_volume(s.get("volume", 0))
        vol_ratio = v.get("vol_ratio", 0.0) if v else 0.0
        ratio_str = f"{vol_ratio:.2f}" if vol_ratio else "-"
        rows.append([it["spec"].cn_name,
                     f"{v.get('last', s['last']):,.2f}" if v else f"{s['last']:,.2f}",
                     f"{'▲' if chg >= 0 else '▼'} {abs(chg):,.2f}（{sgn(chg_pct)}{chg_pct:.2f}%）",
                     f"{amp:.2f}%", vol_str, ratio_str,
                     sign(s["5d_chg"]), sign(s["20d_chg"]), sign(s["60d_chg"])])

    tbl = Table(rows, colWidths=[26*mm, 22*mm, 32*mm, 14*mm, 24*mm, 12*mm, 18*mm, 18*mm, 18*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A1A2E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("FONTSIZE", (0, 1), (-1, -1), 8.8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#F4F6F8")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "量比 = 今日成交量 ÷ 近 20 日均量；▲/▼ 表示涨/跌。",
        caption,
    ))
    story.append(Spacer(1, 5*mm))

    # ---- Per-index sections ----
    for idx, it in enumerate(items):
        spec = it["spec"]
        s = it["daily"]; v = it["intra_stats"]
        story.append(Paragraph(f"{idx + 1}. {spec.cn_name}（{spec.en_name}）", h2))
        story.append(Paragraph(f"交易时段：{spec.market_hours}", small))

        # Key data line
        last = v.get("last", s["last"]) if v else s["last"]
        chg = v.get("change", s["change"]) if v else s["change"]
        chg_pct = v.get("change_pct", s["change_pct"]) if v else s["change_pct"]
        amp = v.get("amplitude", s["amplitude"]) if v else s["amplitude"]
        vol_ratio = v.get("vol_ratio", 0.0) if v else 0.0

        kv = (f"<b>收盘 {last:,.2f}</b> {spec.unit}　"
              f"<b>{sgn(chg)}{chg:,.2f}</b>（<b>{sgn(chg_pct)}{chg_pct:.2f}%</b>）　"
              f"振幅 {amp:.2f}%　"
              f"成交 {format_volume(v['volume']) if v else '-'}　"
              f"量比 {vol_ratio:.2f}" if v else
              f"<b>收盘 {last:,.2f}</b> {spec.unit}　"
              f"日内数据不可用，仅展示日线。")
        story.append(Paragraph(kv, body))

        if v:
            extra = (f"区间高 {v['high']:,.2f}　区间低 {v['low']:,.2f}　"
                     f"VWAP {v['vwap']:,.2f}　"
                     f"VWAP 上方时间占比 {v['pct_above_vwap']:.0f}%　"
                     f"上午成交占 {v['morning_share']:.0f}%")
            story.append(Paragraph(extra, small))

        rng = (f"240 日区间高 {s['period_high']:,.2f}（{s['period_high_date']}）　"
               f"低 {s['period_low']:,.2f}（{s['period_low_date']}）　"
               f"5 日 {sgn(s['5d_chg'])}{s['5d_chg']:.2f}%　"
               f"20 日 {sgn(s['20d_chg'])}{s['20d_chg']:.2f}%　"
               f"60 日 {sgn(s['60d_chg'])}{s['60d_chg']:.2f}%")
        story.append(Paragraph(rng, small))
        story.append(Spacer(1, 1*mm))

        # Charts
        daily_chart = it["daily_chart"]
        if Path(daily_chart).exists():
            story.append(Image(daily_chart, width=174*mm, height=68*mm))
            story.append(Paragraph(f"图 {idx * 2 + 1}：{spec.cn_name} 近 240 个交易日日线",
                                   caption))
        intra_chart = it["intra_chart"]
        if Path(intra_chart).exists():
            story.append(Image(intra_chart, width=174*mm, height=72*mm))
            story.append(Paragraph(f"图 {idx * 2 + 2}：{spec.cn_name} 今日日内分时（含成交量）",
                                   caption))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(it["analysis"], body))
        story.append(Spacer(1, 4*mm))

    # ---- Notes page ----
    story.append(PageBreak())
    story.append(Paragraph("数据口径与说明", h2))
    notes = [
        "1. 收盘价：来自日内 1 分钟分时的最后一根 K 线（即真实收盘价，非盘中快照）。",
        "2. 240 日日线：使用东方财富前复权（fqt=1）数据，便于跨期比较。",
        "3. 日内分时：A 股与港股来自东方财富 1 分钟 K 线；美股 / 黄金来自 1 分钟 K 线（COMEX 为近 24h 交易）。",
        "4. 成交量：对于指数，单位为“手”（A 股 1 手 = 100 股）；对于 COMEX 黄金，单位为“合约”。",
        "5. 量比：今日成交 ÷ 近 20 个交易日日均成交。1.0 以上为放量，以下为缩量。",
        "6. VWAP：日内成交量加权均价；上方时间占比反映价格相对均价的强弱。",
        "7. 纳斯达克：东方财富代码 100.NDX 显示名为“纳斯达克”，对应 Nasdaq 100；如需 Nasdaq Composite (IXIC) 可参考新浪 int_nasdaq。",
        "8. 本报告全部数据由 Codex 通过公开财经 API 自动采集与整理，仅用于研究学习，不构成投资建议。",
    ]
    for line in notes:
        story.append(Paragraph(line, body))

    doc.build(story)


# ----- Main -----
def open_output_folder() -> None:
    """Open today's output folder in Explorer (best-effort, Windows only)."""
    if sys.platform != "win32":
        return
    try:
        os.startfile(str(TODAY_DIR))  # type: ignore[attr-defined]
    except Exception as e:
        print(f"  (open folder skipped: {e})", flush=True)


def main() -> int:
    setup_fonts()
    items = []
    for spec in INDICES:
        print(f"[{spec.cn_name}] fetching ...", flush=True)
        if spec.proxy_note:
            print(f"  {spec.proxy_note}", flush=True)
        try:
            history = fetch_kline(spec.daily_endpoint, spec.daily_code, count=240)
        except Exception as e:
            print(f"  kline error: {e}", flush=True)
            history = []
        try:
            intra = _tencent_intraday(spec.intra_code, TODAY)
        except Exception as e:
            print(f"  intraday error: {e}", flush=True)
            intra = []
        daily_stats = compute_daily_stats(history)
        intra_stats = compute_intraday_stats(intra, daily_stats)
        daily_chart = CHART_DIR / f"{spec.key}_240d.png"
        intra_chart = CHART_DIR / f"{spec.key}_intraday.png"
        try:
            draw_daily_chart(spec, history, daily_chart)
        except Exception as e:
            print(f"  daily chart error: {e}", flush=True)
        try:
            draw_intraday_chart(spec, intra, intra_chart)
        except Exception as e:
            print(f"  intraday chart error: {e}", flush=True)
        analysis = build_analysis(spec, daily_stats, intra_stats)
        items.append({
            "spec": spec, "history": history, "intra": intra,
            "daily": daily_stats, "intra_stats": intra_stats,
            "daily_chart": str(daily_chart), "intra_chart": str(intra_chart),
            "analysis": analysis,
        })
    print("Building PDF ...", flush=True)
    build_pdf(items, meta={"date": TODAY.strftime("%Y-%m-%d")})
    print(f"Saved: {PDF_PATH}")
    if build_html is not None:
        print("Building HTML ...", flush=True)
        html_path = build_html(items, meta={"date": TODAY.strftime("%Y-%m-%d")})
        print(f"Saved: {html_path}")
        bat_path = write_browser_launcher()
        print(f"Launcher: {bat_path}")
    return 0


if __name__ == "__main__":
    rc = main()
    if rc == 0:
        open_output_folder()
    sys.exit(rc)





