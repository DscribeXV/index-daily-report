# -*- coding: utf-8 -*-
"""Tencent-based data fetchers for the indices report.

Eastmoney (push2his.eastmoney.com) is currently unreachable from many networks,
so we switched the primary source to Tencent Finance (web.ifzq.gtimg.cn):
  - A-share / HK index daily K-line:  /appstock/app/fqkline/get   (field: qfqday)
  - US index daily K-line:            /appstock/app/usfqkline/get (field: qfqday)
  - 1-minute intraday:                /appstock/app/minute/query
  - A-share gold ETF (sh518880) is used as a stand-in for COMEX gold,
    which is not available on Tencent.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
REFERER = "https://gu.qq.com/"


def _http_get(url, params, referer=REFERER, retries=4, timeout=15):
    """GET with retries, exponential backoff, and a session for keep-alive."""
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": referer})
    last = None
    for i in range(retries):
        try:
            r = sess.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(0.6 * (i + 1))
    raise RuntimeError(f"GET {url} failed after {retries} tries: {last}")


def _normalize_kline(raw: list, today: datetime) -> list[dict]:
    """Convert Tencent's [date, open, close, high, low, volume, ...] into a list of dicts."""
    out = []
    for k in raw:
        if not isinstance(k, list) or len(k) < 6:
            continue
        try:
            date_str = str(k[0])
            o = float(k[1]); c = float(k[2]); h = float(k[3]); lo = float(k[4])
            vol = float(k[5]) if k[5] not in (None, "") else 0.0
            amt = float(k[8]) if len(k) > 8 and k[8] not in (None, "") else 0.0
        except (ValueError, TypeError):
            continue
        out.append({
            "date": date_str,
            "open": o, "close": c, "high": h, "low": lo,
            "volume": vol, "amount": amt,
            "amplitude": 0.0, "change_pct": 0.0, "change": 0.0,
        })
    # Derive change / change_pct / amplitude from consecutive closes
    for i in range(1, len(out)):
        prev_c = out[i - 1]["close"]
        cur = out[i]
        if prev_c:
            cur["change"] = cur["close"] - prev_c
            cur["change_pct"] = (cur["close"] - prev_c) / prev_c * 100.0
            cur["amplitude"] = (cur["high"] - cur["low"]) / prev_c * 100.0
    return out


def fetch_kline(endpoint: str, code: str, count: int = 240) -> list[dict]:
    """Fetch daily K-line from Tencent.

    endpoint: "fqkline" for CN/HK, "usfqkline" for US.
    code:     e.g. "sh000001", "hkHSI", "usNDX".
    """
    today = datetime.now()
    url = f"https://web.ifzq.gtimg.cn/appstock/app/{endpoint}/get"
    j = _http_get(url, {"param": f"{code},day,,,{count},qfq"})
    inner = (j.get("data") or {}).get(code) or {}
    raw = inner.get("qfqday") or inner.get("day") or []
    if isinstance(raw, list):
        return _normalize_kline(raw, today)
    return []


def fetch_intraday(code: str, today: datetime) -> list[dict]:
    """Fetch today's 1-minute bars from Tencent."""
    url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
    j = _http_get(url, {"code": code})
    inner = (j.get("data") or {}).get(code, {}).get("data") or {}
    bars_str = inner.get("data") or []
    out = []
    for b in bars_str:
        if isinstance(b, list):
            parts = b
        else:
            parts = str(b).split()
        if len(parts) < 4:
            continue
        hhmm = parts[0]
        try:
            price = float(parts[1]); volume = float(parts[2]); amount = float(parts[3])
            h = int(hhmm[:2]); m = int(hhmm[2:])
        except (ValueError, TypeError, IndexError):
            continue
        dt = today.replace(hour=h, minute=m, second=0, microsecond=0)
        out.append({
            "dt": dt, "date": dt.strftime("%Y-%m-%d %H:%M"),
            "open": price, "close": price, "high": price, "low": price,
            "volume": volume, "amount": amount,
        })
    return out


@dataclass
class IndexSpec:
    key: str
    cn_name: str
    en_name: str
    color: str
    unit: str
    market_hours: str
    # Data source
    daily_endpoint: str  # "fqkline" or "usfqkline"
    daily_code: str      # e.g. "sh000001", "usNDX"
    intra_code: str      # code for minute/query
    proxy_note: str = ""  # optional note shown in the report


INDICES: list[IndexSpec] = [
    IndexSpec("sh", "上证指数", "Shanghai Composite Index",
              "#C0392B", "点", "A 股 9:30-11:30 / 13:00-15:00 北京时间",
              "fqkline", "sh000001", "sh000001"),
    IndexSpec("chinext", "创业板指", "ChiNext Index",
              "#8E44AD", "点", "A 股 9:30-11:30 / 13:00-15:00 北京时间",
              "fqkline", "sz399006", "sz399006"),
    IndexSpec("hsi", "恒生指数", "Hang Seng Index",
              "#16A085", "点", "港股 9:30-12:00 / 13:00-16:00 港股时间",
              "fqkline", "hkHSI", "hkHSI"),
    IndexSpec("hstech", "恒生科技指数", "Hang Seng Tech Index",
              "#2980B9", "点", "港股 9:30-12:00 / 13:00-16:00 港股时间",
              "fqkline", "hkHSTECH", "hkHSTECH"),
    IndexSpec("nasdaq", "纳斯达克指数", "Nasdaq 100 Index",
              "#D35400", "点", "美股 9:30-16:00 美东时间 / 24h 期货",
              "usfqkline", "usNDX", "usNDX"),
    # Gold: COMEX gold futures (101.GC00Y on Eastmoney) is not available on Tencent.
    # We use the A-share gold ETF (华安黄金, sh518880) as a proxy.  Unit is RMB per
    # ETF share, not USD/oz.  Users can interpret the trend from this proxy.
    IndexSpec("gold", "华安黄金ETF", "Huaan Gold ETF (proxy for international gold)",
              "#B7950B", "元/份", "上交所 9:30-11:30 / 13:00-15:00 北京时间",
              "fqkline", "sh518880", "sh518880",
              proxy_note="\u26a0 COMEX \u9ec4\u91d1\u672a\u5728\u817e\u8baf\u63a5\u53e3\u4e2d\u63d0\u4f9b\uff0c\u4ee5\u4e0a\u6d77\u9ec4\u91d1ETF (sh518880) \u4f5c\u4e3a\u4ee3\u7406\u53c2\u8003\u3002"),
]