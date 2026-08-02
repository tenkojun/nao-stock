# -*- coding: utf-8 -*-
"""
거래비용·세금 모델 (자문 A-13 / 0장(5))
=========================================
자문 지적:
  · 단일 0.40% 왕복은 **대형주엔 과대, 코스닥 소형엔 과소**. 시장·가격대별 테이블로 교체.
  · **매수 세금 0%, 매도 0.20%** — 매도가 매수보다 약 10배 비싸다. 앱은 매도에 마찰을 걸어야 한다.
  · 백테스트는 **연도별 세율**을 써야 한다(2019~2026 사이 여러 번 변경).

⚠ 세율은 시행 시점 원문 확인이 필요합니다(아래는 2026-07 기준 공개 정보로 구성).
   이 모듈은 '계산'이라 통계 검정이 필요 없고, 효과 크기가 확실합니다.
"""
from __future__ import annotations

# 연도별 (증권거래세 + 농어촌특별세) 합계 — 매도에만 부과. (코스피, 코스닥)
# 코스피는 거래세 인하분을 농특세 0.15%가 보전하는 구조라 합계가 코스닥과 유사하게 움직임.
TAX_BY_YEAR = {
    2019: (0.0025, 0.0025), 2020: (0.0025, 0.0025), 2021: (0.0023, 0.0023),
    2022: (0.0023, 0.0023), 2023: (0.0020, 0.0020), 2024: (0.0018, 0.0018),
    2025: (0.0015, 0.0015), 2026: (0.0020, 0.0020),   # 2026.1.1~ 코스피 0.05+농특0.15, 코스닥 0.20
}
DEFAULT_YEAR = 2026

FEE_ONLINE = 0.00015        # 온라인 위탁수수료(증권사별 0.0036~0.015%) 보수적 중간값
FEE_INFRA = 0.000036        # 유관기관 제비용


def tax_rate(year=DEFAULT_YEAR, market="KOSPI"):
    y = TAX_BY_YEAR.get(int(year), TAX_BY_YEAR[DEFAULT_YEAR])
    return y[1] if str(market).upper().startswith("KOSDAQ") else y[0]


def tick_size(price, market="KOSPI"):
    """KRX 호가단위(2023 개편 기준). 스프레드 대용치 계산에 사용."""
    p = float(price or 0)
    kosdaq = str(market).upper().startswith("KOSDAQ")
    if p < 2000:
        return 1
    if p < 5000:
        return 5
    if p < 20000:
        return 10
    if p < 50000:
        return 50
    if kosdaq:
        return 100
    if p < 200000:
        return 100
    if p < 500000:
        return 500
    return 1000


def spread_pct(price, market="KOSPI", marcap=None):
    """실효 스프레드 추정. 반틱을 기본으로 하되 **유동성 등급으로 상·하한**을 건다.
    (자문 A-13 실무 범위: 대형 0.02~0.05%, 중소형 0.1~0.3%. 대형주는 호가가 깊어
     반틱이 실효 비용을 과대평가하므로 상한을 둔다.)"""
    p = float(price or 0)
    if p <= 0:
        return 0.0015
    half = (tick_size(p, market) / 2) / p
    kosdaq = str(market).upper().startswith("KOSDAQ")
    if marcap is None:
        marcap = 2e11 if kosdaq else 1e12        # 미상시 보수적 가정
    if marcap >= 5e12:                            # 초대형(5조+)
        lo, hi, add = 0.0002, 0.0005, 0.0
    elif marcap >= 1e12:                          # 대형(1~5조)
        lo, hi, add = 0.0003, 0.0010, 0.0002
    elif marcap >= 3e11:                          # 중형(3천억~1조)
        lo, hi, add = 0.0008, 0.0020, 0.0005
    else:                                         # 소형
        lo, hi, add = 0.0015, 0.0040, 0.0015
    return max(lo, min(hi, half + add))


def trade_cost(amount, price, side="buy", market="KOSPI", marcap=None, year=DEFAULT_YEAR):
    """한 번의 매매 비용. amount=거래금액(원). 반환: 원 단위 + 비율."""
    amt = float(amount or 0)
    fee = (FEE_ONLINE + FEE_INFRA) * amt
    tax = tax_rate(year, market) * amt if side == "sell" else 0.0
    slip = spread_pct(price, market, marcap) * amt
    total = fee + tax + slip
    return {"side": side, "amount": round(amt), "fee": round(fee), "tax": round(tax),
            "slippage": round(slip), "total": round(total),
            "pct": round(total / amt * 100, 3) if amt else 0.0,
            "tax_pct": round(tax_rate(year, market) * 100, 3) if side == "sell" else 0.0}


def round_trip(amount, price, market="KOSPI", marcap=None, year=DEFAULT_YEAR):
    """왕복(매수+매도) 비용 — 백테스트·손익분기 계산용."""
    b = trade_cost(amount, price, "buy", market, marcap, year)
    s = trade_cost(amount, price, "sell", market, marcap, year)
    tot = b["total"] + s["total"]
    return {"buy": b, "sell": s, "total": round(tot),
            "pct": round(tot / amount * 100, 3) if amount else 0.0,
            "breakeven_note": "이 비율만큼 올라야 본전입니다."}


def round_trip_pct(price, market="KOSPI", marcap=None, year=DEFAULT_YEAR):
    """왕복 비용률(소수). 반올림 없이 비율로 직접 계산 — 검증 하네스의 종목별 COST."""
    fees = 2 * (FEE_ONLINE + FEE_INFRA)
    slip = 2 * spread_pct(price, market, marcap)
    return fees + slip + tax_rate(year, market)


def explain(price, market="KOSPI", marcap=None, amount=10_000_000, year=DEFAULT_YEAR):
    """사용자 화면용 설명 — 매수/매도 비대칭을 명확히."""
    rt = round_trip(amount, price, market, marcap, year)
    b, s = rt["buy"], rt["sell"]
    return {
        "amount": amount, "buy_total": b["total"], "sell_total": s["total"],
        "buy_pct": b["pct"], "sell_pct": s["pct"], "round_trip_pct": rt["pct"],
        "tax": s["tax"], "tax_pct": s["tax_pct"],
        "headline": (f"{amount//10000:,}만원 기준 — 살 때 약 {b['total']:,}원, "
                     f"팔 때 약 {s['total']:,}원(이 중 세금 {s['tax']:,}원)."),
        "asymmetry": (f"매도 비용이 매수의 약 {round(s['total']/max(b['total'],1))}배입니다. "
                      "매수에는 세금이 없고 매도에만 붙기 때문입니다 — "
                      "**자주 파는 것이 자주 사는 것보다 훨씬 비쌉니다.**"),
        "breakeven": f"사고팔아 본전이 되려면 약 {rt['pct']:.2f}% 올라야 합니다.",
    }
