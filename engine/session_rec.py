# -*- coding: utf-8 -*-
"""
장중 세션 기록기 — 오늘장을 스스로 쌓는다
==========================================
왜 필요한가
  KIS 는 **과거 시간대별 수급을 주지 않는다.** 시간대 가집계(HHPTJ04160200)는
  '오늘' 것만 나오고, 일별 수급(FHKST01010900)은 하루 한 줄뿐이다.
  그래서 지나가면 영영 못 본다 → **장이 열려 있는 동안 우리가 직접 기록**한다.

무엇을 남기나 (5분마다)
  · 시간대별 외국인·기관 추정 순매수 (HHPTJ04160200 · 5구간)
  · 종목 현재가·등락률·누적거래량
  · 지수(코스피·코스닥) 스냅샷
개인(prsn)은 시간대로는 안 나오고 **일별로만** 나오므로 마감 뒤 일별에서 채운다.

어디에 남기나
  data/sessions/YYYYMMDD.json   ← data/ 는 업데이트 보존·패키징 제외
  하루치가 수십 KB 수준이라 몇 년 쌓아도 부담이 없다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR = os.path.join(_ROOT, "data", "sessions")
_LOCK = threading.Lock()

OPEN_HHMM, CLOSE_HHMM = 900, 1540        # 09:00 ~ 15:40 (마감 동시호가 여유)
EVERY = 300                              # 5분
MAX_CODES = 10                           # 호출량 상한


# ── 시각 ──────────────────────────────────────────────────────────
def now_kst():
    """이 앱은 한국 PC 에서 도는 것을 전제한다(로컬시각 = KST)."""
    return dt.datetime.now()


def is_market_open(t=None):
    t = t or now_kst()
    if t.weekday() >= 5:
        return False
    return OPEN_HHMM <= t.hour * 100 + t.minute <= CLOSE_HHMM


def today():
    return now_kst().strftime("%Y%m%d")


# ── 저장 ──────────────────────────────────────────────────────────
def _path(date):
    return os.path.join(_DIR, f"{date}.json")


def load(date):
    try:
        with open(_path(date), encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return None


def _save(date, data):
    os.makedirs(_DIR, exist_ok=True)
    p = _path(date)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)


def dates():
    """기록이 있는 날짜 — 최신 우선."""
    if not os.path.isdir(_DIR):
        return []
    out = []
    for f in os.listdir(_DIR):
        if f.endswith(".json") and len(f) == 13 and f[:8].isdigit():
            out.append(f[:8])
    return sorted(out, reverse=True)


# ── 수집 ──────────────────────────────────────────────────────────
def _codes():
    """추적 대상 — 보유·관심 종목. 없으면 대표 종목."""
    got = []
    try:
        import prefs
        for uid in ("father", "admin"):
            p = prefs.load(uid) or {}
            got += list((p.get("portfolio") or {}).keys())
            for w in (p.get("watchlist") or []):
                got.append(w[1] if isinstance(w, (list, tuple)) and len(w) > 1 else w)
    except Exception:
        pass
    seen, out = set(), []
    for c in got:
        c = str(c).strip()
        if len(c) == 6 and c.isdigit() and c not in seen:
            seen.add(c)
            out.append(c)
    if not out:
        out = ["005930", "000660"]
    return out[:MAX_CODES]


def _hour_flow(kis, code):
    """시간대별 외국인·기관 추정 순매수. bsop_hour_gb 는 구간 번호."""
    try:
        j = kis._get("/uapi/domestic-stock/v1/quotations/investor-trend-estimate",
                     "HHPTJ04160200", {"MKSC_SHRN_ISCD": code})
        rows = []
        for x in (j.get("output2") or []):
            rows.append({"gb": str(x.get("bsop_hour_gb", "")),
                         "frgn": _num(x.get("frgn_fake_ntby_qty")),
                         "orgn": _num(x.get("orgn_fake_ntby_qty")),
                         "sum": _num(x.get("sum_fake_ntby_qty"))})
        return rows
    except Exception:
        return []


def _num(v):
    """'-00000000005727000' 같은 0 채움 문자열 → -5727000.
    (int() 가 앞의 0 과 부호를 알아서 처리한다. 직접 lstrip 하면 부호가 뒤집힌다.)"""
    try:
        return int(float(str(v).replace(",", "").strip() or 0))
    except Exception:
        return 0


def snapshot():
    """지금 시점 한 컷. 장 마감 뒤에도 호출은 되지만 값이 갱신되지 않는다."""
    from kis_kr import KISKorea
    kis = KISKorea()
    t = now_kst()
    snap = {"at": t.strftime("%H:%M"), "stocks": {}}
    for code in _codes():
        item = {}
        try:
            q = kis.quote(code)
            item["price"] = q.get("price")
            item["chg"] = q.get("change_pct")
            item["name"] = q.get("name")
        except Exception:
            pass
        hf = _hour_flow(kis, code)
        if hf:
            item["hour"] = hf
        if item:
            snap["stocks"][code] = item
    try:
        idx = {}
        for name, cd in (("KOSPI", "0001"), ("KOSDAQ", "1001")):
            iq = kis.index_quote(cd)
            idx[name] = {"v": iq.get("value"), "chg": iq.get("chg")}
        snap["index"] = idx
    except Exception:
        pass
    return snap


def record_once():
    """스냅샷 한 번을 오늘 파일에 덧붙인다. 반환: 남긴 스냅샷 개수."""
    date = today()
    with _LOCK:
        day = load(date) or {"date": date, "snaps": [], "daily": {}}
        snap = snapshot()
        if snap["stocks"]:
            day["snaps"].append(snap)
            day["updated"] = snap["at"]
            _save(date, day)
        return len(day["snaps"])


def close_day(date=None):
    """마감 정리 — 시간대로는 안 나오는 **개인** 수급을 일별에서 채운다."""
    date = date or today()
    with _LOCK:
        day = load(date)
        if not day:
            return False
        try:
            from kis_kr import KISKorea
            kis = KISKorea()
            for code in list(day.get("snaps", [{}])[-1].get("stocks", {}) if day.get("snaps") else []):
                fl = kis.investor_flow(code)
                row = next((r for r in fl.get("rows", []) if r.get("date") == date), None)
                if row:
                    day.setdefault("daily", {})[code] = {
                        "frgn": row.get("foreign_net", 0),
                        "orgn": row.get("org_net", 0),
                        "prsn": row.get("person_net", 0)}
        except Exception:
            pass
        day["closed"] = True
        _save(date, day)
        return True


# ── 백그라운드 ────────────────────────────────────────────────────
_state = {"thread": None, "last": None, "count": 0, "error": None}


def status():
    d = today()
    day = load(d)
    return {"running": bool(_state["thread"] and _state["thread"].is_alive()),
            "market_open": is_market_open(),
            "today": d,
            "snaps_today": len(day.get("snaps", [])) if day else 0,
            "last": _state["last"], "error": _state["error"],
            "dates": dates()[:30]}


def _loop():
    closed_for = None
    while True:
        try:
            if is_market_open():
                _state["count"] = record_once()
                _state["last"] = now_kst().strftime("%H:%M")
                _state["error"] = None
                closed_for = None
            else:
                d = today()
                day = load(d)
                if day and not day.get("closed") and closed_for != d:
                    close_day(d)                  # 마감 직후 한 번 개인 수급 채우기
                    closed_for = d
        except Exception as e:
            _state["error"] = f"{type(e).__name__}"
        time.sleep(EVERY)


def start():
    """서버가 뜰 때 한 번 호출. 장중에만 실제로 기록한다."""
    if _state["thread"] and _state["thread"].is_alive():
        return False
    t = threading.Thread(target=_loop, daemon=True, name="session_rec")
    t.start()
    _state["thread"] = t
    return True
