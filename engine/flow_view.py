# -*- coding: utf-8 -*-
"""
종목 수급 — 외국인·기관·개인을 한 곳에서
==========================================
지금까지 화면에는 '외국인(5일) / 기관(5일)' 두 줄뿐이고 **개인은 아예 없었다**.
누가 사고 누가 파는지 보려면 세 주체를 같은 자리에서 같은 단위로 봐야 한다.

세 곳을 합친다
  ① KIS 일별 투자자 (FHKST01010900) — 최근 30일, 외인·기관·**개인**
  ② data/flow/<code>.csv — 조회할 때마다 쌓아둔 과거분(KIS 는 최근치만 준다)
  ③ data/sessions/ — 장중 기록기가 남긴 **오늘 시간대별**(외인·기관)

개인은 시간대로는 나오지 않는다. 일별에서만 온다.
"""
from __future__ import annotations

import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FLOWDIR = os.path.join(_ROOT, "data", "flow")


def _from_csv(code):
    """예전에 쌓아둔 일별 수급(있으면)."""
    p = os.path.join(_FLOWDIR, f"{code}.csv")
    out = {}
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f.read().splitlines()[1:]:
                c = ln.split(",")
                if len(c) >= 4 and c[0].isdigit():
                    out[c[0]] = {"date": c[0], "frgn": float(c[1] or 0),
                                 "orgn": float(c[2] or 0), "prsn": float(c[3] or 0)}
    except Exception:
        pass
    return out


def _from_kis(code):
    try:
        from kis_kr import KISKorea
        fl = KISKorea().investor_flow(code)
        return {r["date"]: {"date": r["date"], "frgn": r.get("foreign_net", 0),
                            "orgn": r.get("org_net", 0), "prsn": r.get("person_net", 0)}
                for r in fl.get("rows", []) if r.get("date")}, fl
    except Exception:
        return {}, {}


def _sum(rows, n, key):
    return sum(r[key] for r in rows[-n:]) if rows else 0


def _intraday_of(code, date):
    """그날 기록에서 이 종목의 시간대별 수급을 꺼낸다.
    스냅샷은 누적값이므로 **구간 증분**까지 계산해 준다."""
    try:
        import session_rec as S
    except Exception:
        return None, None, None
    day = S.load(date)
    if not day:
        return None, None, None
    hour = None
    for s in reversed(day.get("snaps") or []):        # 값이 있던 마지막 스냅샷
        h = ((s.get("stocks") or {}).get(code) or {}).get("hour")
        if h:
            hour = h
            break
    if not hour:
        return None, None, day.get("updated")
    hour = sorted(hour, key=lambda x: str(x.get("gb")))
    step, pf, po = [], 0, 0
    for h in hour:
        step.append({"gb": h["gb"], "frgn": h["frgn"] - pf, "orgn": h["orgn"] - po})
        pf, po = h["frgn"], h["orgn"]
    return hour, step, day.get("updated")


def build(code, days=20, date=None):
    """화면이 바로 쓸 수 있는 형태로. date 를 주면 **그날** 시간대별을 보여준다."""
    kis_rows, raw = _from_kis(code)
    merged = _from_csv(code)
    merged.update(kis_rows)                       # 최신값 우선
    rows = [merged[k] for k in sorted(merged)][-max(days, 20):]

    out = {"code": code, "days": rows, "have": len(merged)}
    for key, label in (("frgn", "외국인"), ("orgn", "기관"), ("prsn", "개인")):
        out[key] = {"label": label,
                    "d1": _sum(rows, 1, key), "d5": _sum(rows, 5, key),
                    "d20": _sum(rows, 20, key)}

    # 시간대별 — 장중 기록기가 남긴 것. 날짜를 고르면 그날 것(캘린더).
    try:
        import session_rec as S
        out["session_dates"] = S.dates()[:40]     # 기록이 있는 날 = 캘린더에 켜지는 날
        sel = date or S.today()
        out["session_date"] = sel
        hour, step, at = _intraday_of(code, sel)
        if hour:
            out["intraday"] = hour
            out["intraday_step"] = step
            out["intraday_at"] = at
    except Exception:
        pass

    if raw:
        out["dirs"] = {"frgn": raw.get("foreign_dir"), "orgn": raw.get("org_dir")}
    return out
