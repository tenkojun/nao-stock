# -*- coding: utf-8 -*-
"""
종목 검색 — 코드를 몰라도 이름으로 찾는다
==========================================
예전에는 종목을 고르는 방법이 관심목록·순위 클릭뿐이었고, 포트폴리오에 넣으려면
**6자리 코드를 직접 입력**해야 했다. "삼"만 쳐도 삼성전자·삼성중공업이 나오게 한다.

목록: FinanceDataReader 의 KRX 상장목록(약 2,900종목)을 하루 한 번 받아
      data/stocks.json 에 캐시한다. 네트워크가 없으면 캐시로 계속 동작한다.

정렬: ①코드 완전일치 ②이름이 검색어로 시작 ③이름에 포함 ④코드로 시작
      같은 순위 안에서는 **시가총액 큰 순** — "삼" 을 치면 삼성전자가 맨 위로 온다.
"""
from __future__ import annotations

import json
import os
import re
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE = os.path.join(_ROOT, "data", "stocks.json")
_TTL = 86400                      # 하루
_mem = {"at": 0, "items": None}


def _norm(s):
    """검색 비교용 — 공백·대소문자·특수문자 무시."""
    return re.sub(r"[\s\-_.()]", "", str(s or "")).lower()


def _from_fdr():
    import FinanceDataReader as fdr
    df = fdr.StockListing("KRX")
    cols = set(df.columns)
    cap = "Marcap" if "Marcap" in cols else None
    out = []
    for r in df.itertuples(index=False):
        d = r._asdict()
        code = str(d.get("Code", "")).strip()
        name = str(d.get("Name", "")).strip()
        if not code or not name or len(code) != 6:
            continue
        try:
            mc = float(d.get(cap) or 0) if cap else 0.0
        except Exception:
            mc = 0.0
        out.append({"code": code, "name": name,
                    "market": str(d.get("Market", "")).strip(), "cap": mc})
    return out


def _load_cache():
    try:
        with open(_CACHE, encoding="utf-8") as fp:
            j = json.load(fp)
        return j.get("items") or [], j.get("at", 0)
    except Exception:
        return [], 0


def _save_cache(items):
    os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
    tmp = _CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump({"at": time.time(), "items": items}, fp, ensure_ascii=False)
    os.replace(tmp, _CACHE)


def listing(force=False):
    """상장목록 — 메모리 → 파일 캐시 → 네트워크 순. 실패해도 옛 캐시로 버틴다."""
    if not force and _mem["items"] and time.time() - _mem["at"] < _TTL:
        return _mem["items"]
    items, at = _load_cache()
    if not force and items and time.time() - at < _TTL:
        _mem.update(at=at, items=items)
        return items
    try:
        fresh = _from_fdr()
        if fresh:
            _save_cache(fresh)
            _mem.update(at=time.time(), items=fresh)
            return fresh
    except Exception:
        pass
    _mem.update(at=at or time.time(), items=items)   # 네트워크 실패 → 옛 캐시 유지
    return items


def search(q, limit=12):
    """이름·코드로 찾기. 반환: [{code,name,market,logo}]"""
    q = (q or "").strip()
    if not q:
        return []
    nq = _norm(q)
    if not nq:
        return []
    rows = listing()
    hits = []
    for s in rows:
        code, nn = s["code"], _norm(s["name"])
        if code == q:
            rank = 0
        elif nn.startswith(nq):
            rank = 1
        elif nq in nn:
            rank = 2
        elif code.startswith(q) and q.isdigit():
            rank = 3
        else:
            continue
        hits.append((rank, -s.get("cap", 0), len(s["name"]), s))
    hits.sort(key=lambda x: x[:3])
    return [{"code": s["code"], "name": s["name"], "market": s["market"],
             "logo": logo_url(s["code"])} for *_, s in hits[:limit]]


def logo_url(code):
    """회사 로고(SVG). 없는 종목은 404 이므로 화면에서 대체 표시로 넘긴다."""
    return f"https://ssl.pstatic.net/imgstock/fn/real/logo/stock/Stock{code}.svg"


def name_of(code):
    for s in listing():
        if s["code"] == str(code):
            return s["name"]
    return ""


def status():
    items, at = _load_cache()
    return {"count": len(items),
            "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(at)) if at else None}
