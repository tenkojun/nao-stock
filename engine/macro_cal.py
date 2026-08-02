# -*- coding: utf-8 -*-
"""
매크로 시세 + 증시 캘린더 (실데이터)
====================================
· 매크로: FDR로 환율·미국지수·VIX·유가·미국채. 한국 증시는 대외 변수 영향이 커
  (외국인 자금·환율 연동) 맥락 지표로 표시. 예측 아님.
· 캘린더: 결정적으로 계산 가능한 일정(선물·옵션 만기=매월 두번째 목요일, 배당락,
  분기 실적시즌)과 확인된 고정 일정만. 추측성 일정은 넣지 않는다.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta

_TICKERS = [
    ("원/달러", "USD/KRW", 1), ("S&P 500", "US500", 0), ("NASDAQ", "IXIC", 0),
    ("VIX", "VIX", 2), ("WTI", "CL=F", 2), ("미국채10Y", "US10YT=X", 3),
]


def macro_snapshot():
    """FDR 기반 매크로 스냅샷. 실패 항목은 건너뛴다(부분 실패 허용)."""
    import FinanceDataReader as fdr
    out = []
    for label, sym, kind in _TICKERS:
        try:
            d = fdr.DataReader(sym).tail(3)
            if d is None or len(d) < 2:
                continue
            c = float(d["Close"].iloc[-1]); p = float(d["Close"].iloc[-2])
            chg = (c / p - 1) * 100 if p else 0
            out.append({"label": label, "value": round(c, 2), "chg": round(chg, 2),
                        "kind": kind})
        except Exception:
            continue
    return out


def _second_thursday(y, m):
    d = date(y, m, 1)
    th = [d + timedelta(days=i) for i in range(31)
          if (d + timedelta(days=i)).month == m and (d + timedelta(days=i)).weekday() == 3]
    return th[1] if len(th) > 1 else None


def calendar_events(days=100):
    """앞으로 days일 이내의 '계산 가능한' 확정 일정만."""
    today = date.today()
    end = today + timedelta(days=days)
    ev = []
    # 선물·옵션 동시만기 (매월 두 번째 목요일)
    for k in range(0, 3):
        m = today.month + k; y = today.year + (m - 1) // 12; m = (m - 1) % 12 + 1
        t = _second_thursday(y, m)
        if t and today <= t <= end:
            q = m in (3, 6, 9, 12)
            ev.append({"date": t.isoformat(), "title": ("선물·옵션 동시만기" if q else "옵션 만기"),
                       "kind": "만기",
                       "note": "만기일 전후에는 프로그램 매매로 수급이 왜곡될 수 있습니다."
                               if q else "옵션 만기 — 단기 변동성 유의."})
    # 분기 실적시즌 (대략적 시작: 1·4·7·10월 중순)
    for m0 in (1, 4, 7, 10):
        for y in (today.year, today.year + 1):
            t = date(y, m0, 15)
            if today <= t <= end:
                ev.append({"date": t.isoformat(), "title": f"{((m0-1)//3) or 4}분기 실적시즌 시작",
                           "kind": "실적",
                           "note": "실적 발표 전후로 주가 변동이 커집니다(발표 후에도 방향이 이어지는 경향)."})
    # 연말 배당락
    for y in (today.year, today.year + 1):
        t = date(y, 12, 27)
        if today <= t <= end:
            ev.append({"date": t.isoformat(), "title": "12월 결산 배당락(전후)", "kind": "배당",
                       "note": "배당락일에는 배당만큼 주가가 조정됩니다 — 하락으로 오해하지 마세요."})
    ev.sort(key=lambda x: x["date"])
    for e in ev:
        d = datetime.fromisoformat(e["date"]).date()
        e["dday"] = (d - today).days
        e["label"] = d.strftime("%m·%d")
    return ev[:8]
