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


def _fin(v):
    """NaN·무한대를 걸러낸다.
    ⚠ 파이썬 json 은 NaN 을 그대로 내보내는데 그건 **유효한 JSON 이 아니다.**
       브라우저 JSON.parse 가 통째로 실패해 매크로·캘린더가 조용히 안 떴다."""
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except Exception:
        return None


def macro_snapshot():
    """FDR 기반 매크로 스냅샷. 실패 항목은 건너뛴다(부분 실패 허용)."""
    import FinanceDataReader as fdr
    out = []
    for label, sym, kind in _TICKERS:
        try:
            d = fdr.DataReader(sym).tail(3)
            if d is None or len(d) < 2:
                continue
            c = _fin(d["Close"].iloc[-1])
            p = _fin(d["Close"].iloc[-2])
            if c is None:
                continue                       # 값이 없으면 항목 자체를 뺀다
            chg = _fin((c / p - 1) * 100) if p else 0.0
            out.append({"label": label, "value": round(c, 2),
                        "chg": round(chg, 2) if chg is not None else 0.0,
                        "kind": kind})
        except Exception:
            continue
    return out


def _second_thursday(y, m):
    d = date(y, m, 1)
    th = [d + timedelta(days=i) for i in range(31)
          if (d + timedelta(days=i)).month == m and (d + timedelta(days=i)).weekday() == 3]
    return th[1] if len(th) > 1 else None


def recent_holidays(back=60):
    """지난 휴장일 — 평일인데 지수 데이터가 없는 날. **확인된 사실**이다.
    ⚠ 앞으로의 휴장일은 넣지 않는다. KRX 에 휴장일 API 가 없어 확인할 방법이 없고,
       음력 명절을 추측해 넣으면 틀릴 수 있다."""
    try:
        import FinanceDataReader as fdr
        import pandas as pd
        start = (date.today() - timedelta(days=back)).strftime("%Y-%m-%d")
        df = fdr.DataReader("KS11", start)
        got = {d.strftime("%Y-%m-%d") for d in df.index}
        if not got:
            return []
        allw = pd.bdate_range(min(got), max(got)).strftime("%Y-%m-%d").tolist()
        return [d for d in allw if d not in got]
    except Exception:
        return []


def _last_bday(y, m):
    """그 달 마지막 평일(배당락 기준일 근처 — 실제 휴장은 반영 못 한다)."""
    d = date(y, m, 28)
    while True:
        n = d + timedelta(days=1)
        if n.month != m:
            break
        d = n
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def calendar_events(days=100):
    """앞으로 days일 이내의 '계산 가능한' 확정 일정만."""
    today = date.today()
    end = today + timedelta(days=days)
    ev = []
    # 분기 배당락 — 국내도 분기배당이 늘어 3·6·9월 말도 함께 본다
    for m0 in (3, 6, 9):
        for y in (today.year, today.year + 1):
            t = _last_bday(y, m0) - timedelta(days=1)
            if today <= t <= end:
                ev.append({"date": t.isoformat(), "title": f"{m0}월 분기배당 기준일(전후)",
                           "kind": "배당",
                           "note": "분기배당을 주는 회사는 이 무렵 배당락이 있습니다. "
                                   "배당만큼 주가가 조정되는 것이라 하락과 다릅니다."})
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
        e["soon"] = 0 <= e["dday"] <= 7          # 이번 주 안에 있는 일정
    return ev[:8]


def calendar():
    """화면용 — 앞으로의 일정 + 지난 휴장일(사실) + 다음 거래일."""
    hol = recent_holidays()
    today = date.today()
    nxt = today
    for _ in range(10):                          # 다음 평일(휴장 반영은 못 함)
        nxt += timedelta(days=1)
        if nxt.weekday() < 5:
            break
    return {"events": calendar_events(),
            "recent_holidays": hol[-5:],
            "next_bday": nxt.isoformat(),
            "note": "계산으로 확정되는 일정만 넣었습니다. 앞으로의 휴장일은 확인할 "
                    "수 있는 공개 자료가 없어 넣지 않았습니다."}
