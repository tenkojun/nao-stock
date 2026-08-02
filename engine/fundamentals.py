# -*- coding: utf-8 -*-
"""
종목 자체 평가 (Phase 2 4b) — 가치·퀄리티·모멘텀 ("이 종목이 살 만한가", 장기보유)
======================================================================================
정직성:
  · 모멘텀(near_high_60) = 이 앱이 KR 데이터로 직접 검증(t3.5@120일). '검증됨' 표기.
  · 가치(저PBR/PER)·퀄리티(고ROE) = 문헌 근거는 탄탄(Fama-French·Novy-Marx)하나
    현재값 스냅샷이고 KR 독립 백테스트는 데이터상 보류 → '문헌 근거·현재값' 표기.
  · 등급·점수·매수지시 없음. 관찰 + 논문 출처.

데이터: 네이버 종목 메인(PER/PBR/EPS/배당, id 기반 파싱). ROE ≈ PBR/PER×100 유도(근사치).
"""
from __future__ import annotations
import re
import numpy as np
import requests

_HDR = {"User-Agent": "Mozilla/5.0"}
PAPER = {
    "value":   ("The Cross-Section of Expected Stock Returns", "Fama & French (1992)",
                "https://doi.org/10.1111/j.1540-6261.1992.tb04398.x"),
    "quality": ("The Other Side of Value: The Gross Profitability Premium", "Novy-Marx (2013)",
                "https://doi.org/10.1016/j.jfineco.2013.01.003"),
    "momentum": ("Returns to Buying Winners and Selling Losers", "Jegadeesh & Titman (1993)",
                 "https://www.jstor.org/stable/2328882"),
}


def fetch_fundamentals(code: str):
    """네이버 종목 메인에서 PER/PBR/EPS/배당 파싱. ROE는 PBR/PER로 유도(근사)."""
    try:
        r = requests.get(f"https://finance.naver.com/item/main.naver?code={code}",
                         headers=_HDR, timeout=6)
        t = r.text
    except Exception:
        return None

    def g(pat):
        m = re.search(pat, t)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    per = g(r'id="_per"[^>]*>([\d,\.\-]+)')
    pbr = g(r'id="_pbr"[^>]*>([\d,\.\-]+)')
    eps = g(r'id="_eps"[^>]*>([\d,\.\-]+)')
    dvr = g(r'id="_dvr"[^>]*>([\d,\.\-]+)')
    roe = round(pbr / per * 100, 1) if (per and pbr and per > 0) else None
    if per is None and pbr is None:
        return None
    return {"per": per, "pbr": pbr, "eps": eps, "div_yield": dvr, "roe": roe}


def stock_evaluation(code: str, close=None, high=None):
    """가치·퀄리티·배당·모멘텀 관찰 반환. items:[{factor,value,read,tone,note,basis,verified}]"""
    f = fetch_fundamentals(code)
    items = []
    if f and f.get("pbr") is not None:
        pbr = f["pbr"]
        read = "순자산 대비 싼 편" if pbr < 1 else "보통" if pbr < 2.5 else "비싼 편"
        val = f"PBR {pbr:.2f}" + (f" · PER {f['per']:.1f}" if f.get("per") else "")
        items.append({"factor": "가치 (저PBR)", "value": val, "read": read,
                      "tone": "plus" if pbr < 1 else "warn" if pbr > 3 else "neutral",
                      "note": "주가가 회사 순자산 대비 싼지 봅니다. 낮을수록 '싸다'. 역사적으로 싼 주식이 장기 수익 우위(가치효과).",
                      "basis": PAPER["value"], "verified": False})
    if f and f.get("roe") is not None:
        roe = f["roe"]
        read = "우량" if roe >= 15 else "양호" if roe >= 8 else "낮음"
        items.append({"factor": "퀄리티 (고ROE)", "value": f"ROE 약 {roe:.0f}%", "read": read,
                      "tone": "plus" if roe >= 15 else "warn" if roe < 5 else "neutral",
                      "note": "회사가 자기자본으로 얼마나 잘 버는지. 높을수록 우량. 수익성 높은 기업이 장기 우위. ※PBR/PER로 추정한 근사치입니다.",
                      "basis": PAPER["quality"], "verified": False})
    if f and f.get("div_yield") and f["div_yield"] > 0:
        items.append({"factor": "배당", "value": f"배당수익률 {f['div_yield']:.2f}%", "read": "",
                      "tone": "neutral",
                      "note": "보유하는 동안 받는 현금입니다. 장기 보유에 도움이 됩니다.",
                      "basis": None, "verified": False})
    if close is not None and high is not None and len(close) >= 60:
        px = float(np.asarray(close, float)[-1])
        hi = float(np.max(np.asarray(high, float)[-60:]))
        nh = px / hi - 1.0 if hi > 0 else 0.0
        read = "강함 (고점 부근)" if nh >= -0.06 else "중간" if nh >= -0.20 else "약함 (낙폭 큼)"
        items.append({"factor": "모멘텀 (강도)", "value": f"60일 고점 대비 {nh*100:.0f}%", "read": read,
                      "tone": "neutral",          # 자문 B-26/B-27: 판정 근거로 쓰지 않음
                      "note": ("현재 주가가 최근 60일 고점에서 얼마나 떨어져 있는지를 보여주는 '위치' 값입니다. "
                               "⚠ 해외에서 알려진 모멘텀 효과는 **한국에서는 오히려 반대(반전 우세)**라는 연구가 "
                               "많습니다(Chui-Titman-Wei 2010 등). 저희 자체 검증에서 나온 양(+)의 결과는 "
                               "유니버스 구성 편향 가능성이 지적되어 **판단 근거에서 내렸습니다**. 참고 수치로만 보세요."),
                      "basis": PAPER["momentum"], "verified": False})
    caveat = ("가치·퀄리티는 논문 근거는 탄탄하나 이 앱이 한국 데이터로 독립 검증한 것은 아닙니다"
              "(현재값 표시). 모멘텀만 자체 검증됨. 종목 평가는 참고이며 매수 추천이 아닙니다.")
    return {"code": code, "fundamentals": f, "items": items, "caveat": caveat}
