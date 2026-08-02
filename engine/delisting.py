# -*- coding: utf-8 -*-
"""
상장폐지 수익률 처리 (자문 A-8)
================================
자문 지적: "상폐 종목을 유니버스에 넣어도 마지막 수익률을 NaN으로 두면 손실이 표본에서 빠지므로
넣으나 마나. **생존편향 보정이 사실상 작동하지 않았습니다.**"

처리 원칙(자문 그대로):
  1. 정리매매가 있으므로 대부분 −100%가 아니다 → **마지막 체결가**를 1순위로 사용.
  2. **합병·분할·자진상폐·완전자회사화는 '상폐'가 아니라 이벤트** → −100%를 넣으면 반대로 왜곡.
     평가 불가하므로 해당 구간을 표본에서 제외한다.
  3. 최종가를 못 구하면 Shumway(1997)식 고정 할인 — **한국은 −60~−80% 범위로 민감도 분석**.
  4. 거래정지 구간 수익률을 0으로 채우지 않는다.

또한 우리 하네스의 실제 버그: 선도수익 계산에 `t+h`가 존재해야만 표본에 넣으므로
**상폐 직전 구간(가장 나쁜 결과)이 통째로 누락**됐다. 아래 terminal_return()이 이를 메운다.
"""
from __future__ import annotations

# 사유 → 분류. (합병/승계/파생상품성 종목은 '주식 손실 사건'이 아님)
_MERGER_KEYS = ("합병", "완전자회사", "지주회사", "포괄적 주식교환", "분할")
_NONSTOCK_KEYS = ("수익증권", "신주인수권", "스팩", "존속기간 만료", "기초주권",
                  "신탁기간", "상장지수", "ETN", "ELW")
_DISTRESS_KEYS = ("감사의견", "상장폐지기준", "해산", "부도", "자본잠식", "미제출",
                  "관리종목", "횡령", "배임", "회생", "파산", "불성실")

# Shumway(1997) 한국 적용 — 민감도 분석용 기본/범위
DISCOUNT_DEFAULT = -0.70
DISCOUNT_RANGE = (-0.60, -0.80)


def classify(reason, to_symbol=None):
    """상폐 사유 분류: 'merger' | 'nonstock' | 'distress' | 'unknown'."""
    if to_symbol and str(to_symbol) not in ("nan", "None", ""):
        return "merger"                      # 승계 종목코드가 있으면 합병·교환
    r = str(reason or "")
    if r in ("nan", "None", ""):
        return "unknown"
    if any(k in r for k in _NONSTOCK_KEYS):
        return "nonstock"
    if any(k in r for k in _MERGER_KEYS):
        return "merger"
    if any(k in r for k in _DISTRESS_KEYS):
        return "distress"
    return "unknown"


def delist_map(min_year="2015"):
    """{code: {'type':..,'date':'YYYYMMDD','reason':..}} — FDR 상폐 리스트 기반."""
    try:
        import FinanceDataReader as fdr
        dl = fdr.StockListing("KRX-DELISTING")
    except Exception:
        return {}
    out = {}
    for _, r in dl.iterrows():
        d = str(r.get("DelistingDate", ""))[:10].replace("-", "")
        if not d or d < min_year:
            continue
        code = str(r.get("Symbol", "")).zfill(6)
        if not (len(code) == 6 and code.isdigit()):
            continue
        out[code] = {"type": classify(r.get("Reason"), r.get("ToSymbol")),
                     "date": d, "reason": str(r.get("Reason") or "")[:60],
                     "name": str(r.get("Name") or "")}
    return out


def terminal_return(entry_price, last_price, dtype, discount=DISCOUNT_DEFAULT):
    """상폐로 지평을 채우지 못한 진입의 최종 수익률.
    반환 None이면 '평가 불가 → 표본에서 제외'(합병·비주식)."""
    if dtype in ("merger", "nonstock"):
        return None                          # 손실 사건이 아님 — 제외(자문 A-8-2)
    if not entry_price or entry_price <= 0 or not last_price or last_price <= 0:
        return None
    # 마지막 체결가까지의 수익 + 정리매매 이후 잔여가치 할인(Shumway식)
    return (last_price * (1.0 + discount)) / entry_price - 1.0


def summarize(dmap):
    from collections import Counter
    c = Counter(v["type"] for v in dmap.values())
    return {"total": len(dmap), **dict(c)}
