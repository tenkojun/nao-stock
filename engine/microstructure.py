# -*- coding: utf-8 -*-
"""
저타임프레임 미시구조 분석 (5분봉 등) — Volume Profile/TPO · SMC · 오더플로우(근사)
==================================================================================
정직성:
  · Volume Profile(POC/VAH/VAL)·FVG·오더블럭·구조는 OHLCV로 규칙 기반 계산(정통 도구).
  · SMC(Smart Money Concepts)는 널리 쓰이나 학술 검증된 게 아닌 재량적 프레임워크 — 그대로 표기.
  · 진짜 오더플로우(풋프린트)는 호가별 체결(틱) 필요. KIS 분봉은 OHLCV뿐 → '거래량 델타'(캔들
    방향 기반)로 근사하고 한계 명시.
입력: bars = 오름차순 [{time,open,high,low,close,volume}]
"""
from __future__ import annotations
import numpy as np


def volume_profile(bars, bins=48, va_pct=0.70):
    if len(bars) < 5:
        return None
    lo = min(b["low"] for b in bars); hi = max(b["high"] for b in bars)
    if hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1)
    vh = np.zeros(bins)
    for b in bars:                                   # 봉 범위에 거래량 균등 분배
        a = max(0, int((b["low"] - lo) / (hi - lo) * bins))
        z = min(bins - 1, int((b["high"] - lo) / (hi - lo) * bins))
        span = z - a + 1
        for k in range(a, z + 1):
            vh[k] += b["volume"] / span
    poc_i = int(np.argmax(vh))
    poc = (edges[poc_i] + edges[poc_i + 1]) / 2
    total = vh.sum(); target = total * va_pct
    lo_i = hi_i = poc_i; acc = vh[poc_i]
    while acc < target and (lo_i > 0 or hi_i < bins - 1):
        up = vh[hi_i + 1] if hi_i < bins - 1 else -1
        dn = vh[lo_i - 1] if lo_i > 0 else -1
        if up >= dn:
            hi_i += 1; acc += max(0, up)
        else:
            lo_i -= 1; acc += max(0, dn)
    return {"poc": round(poc), "vah": round(edges[hi_i + 1]), "val": round(edges[lo_i]),
            "hi": round(hi), "lo": round(lo)}


def fvgs(bars, max_keep=6):
    """Fair Value Gap(3봉 불균형). 아직 안 메워진 것만 최신순."""
    out = []
    px = bars[-1]["close"]
    for i in range(1, len(bars) - 1):
        a, c = bars[i - 1], bars[i + 1]
        if a["high"] < c["low"]:                     # 상승 FVG
            g_lo, g_hi, typ = a["high"], c["low"], "bull"
        elif a["low"] > c["high"]:                   # 하락 FVG
            g_lo, g_hi, typ = c["high"], a["low"], "bear"
        else:
            continue
        # 이후 봉이 갭을 완전히 메웠으면 제외
        filled = any(bars[j]["low"] <= g_lo and bars[j]["high"] >= g_hi
                     for j in range(i + 2, len(bars)))
        if not filled:
            out.append({"lo": round(g_lo), "hi": round(g_hi), "type": typ,
                        "mid": round((g_lo + g_hi) / 2)})
    out.sort(key=lambda z: -abs(z["mid"] - px))
    return out[-max_keep:]


def order_blocks(bars, max_keep=4, move=0.004):
    """오더블럭: 강한 임펄스 직전의 반대색 마지막 봉."""
    obs = []
    for i in range(1, len(bars) - 2):
        b, nx = bars[i], bars[i + 1]
        leg = nx["close"] / nx["open"] - 1 if nx["open"] else 0
        down = b["close"] < b["open"]
        if down and leg > move:                      # 하락봉 뒤 강한 상승 → 강세 OB
            obs.append({"lo": round(b["low"]), "hi": round(b["high"]), "type": "bull"})
        up = b["close"] > b["open"]
        if up and leg < -move:                       # 상승봉 뒤 강한 하락 → 약세 OB
            obs.append({"lo": round(b["low"]), "hi": round(b["high"]), "type": "bear"})
    return obs[-max_keep:]


def vol_delta(bars):
    """오더플로우 근사: 캔들 방향 기반 누적 거래량 델타(진짜 풋프린트 아님)."""
    cum = 0.0; series = []
    for b in bars:
        d = b["volume"] if b["close"] >= b["open"] else -b["volume"]
        cum += d
        series.append(round(cum))
    up = sum(b["volume"] for b in bars if b["close"] >= b["open"])
    dn = sum(b["volume"] for b in bars if b["close"] < b["open"])
    tot = up + dn or 1
    return {"cum": series, "last": round(cum), "buy_ratio": round(up / tot * 100, 1)}


def _swings(bars, w=2):
    hi, lo = [], []
    for i in range(w, len(bars) - w):
        if bars[i]["high"] >= max(bars[j]["high"] for j in range(i - w, i + w + 1)):
            hi.append(i)
        if bars[i]["low"] <= min(bars[j]["low"] for j in range(i - w, i + w + 1)):
            lo.append(i)
    return hi, lo


def structure(bars):
    """단순 구조: 최근 스윙 고/저 + 마지막 돌파(BOS) 방향."""
    hi, lo = _swings(bars)
    if not hi or not lo:
        return None
    last_sh = bars[hi[-1]]["high"]; last_sl = bars[lo[-1]]["low"]
    px = bars[-1]["close"]
    bos = "up" if px > last_sh else "down" if px < last_sl else "none"
    return {"swing_high": round(last_sh), "swing_low": round(last_sl), "bos": bos}


def analyze_micro(bars, interval=5):
    if not bars or len(bars) < 6:
        return {"bars": bars or [], "note": "분봉 표본 부족"}
    return {
        "bars": bars, "interval": interval,
        "vp": volume_profile(bars),
        "fvg": fvgs(bars),
        "ob": order_blocks(bars),
        "delta": vol_delta(bars),
        "structure": structure(bars),
        "note": ("Volume Profile·FVG·오더블럭은 규칙 기반 계산. SMC는 재량적 프레임워크(검증된 알파 아님). "
                 "오더플로우는 캔들 방향 기반 '거래량 델타' 근사이며 진짜 호가별 풋프린트가 아닙니다."),
    }
