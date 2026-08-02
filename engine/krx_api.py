# -*- coding: utf-8 -*-
"""
KRX Data Marketplace OPEN API 어댑터 (자문 A-9/F-116/F-122 해결)
================================================================
왜 중요한가: 지금까지 유니버스를 **현재 시총 상위**로 구성해 왔는데, 이는 2019년 시점에
"2026년 승자 명단"을 아는 것과 같아 **가장 강한 종류의 look-ahead**였다(자문 A-9).
KRX 일별매매정보는 **각 날짜의 전 종목 + 그 시점 시가총액(MKTCAP)** 을 주므로
**진짜 point-in-time 유니버스**를 만들 수 있다.

제공 데이터(승인 확인됨, 2026-07-28):
  · 유가/코스닥 일별매매정보: BAS_DD, ISU_SRT_CD, ISU_NM, TDD_OPNPRC/HGPRC/LWPRC/CLSPRC,
                              ACC_TRDVOL, ACC_TRDVAL, **MKTCAP**
  · 유가/코스닥 종목기본정보: LIST_DD(상장일), **LIST_SHRS**(상장주식수), SECT_TP_NM

인증키: 프로젝트 밖 비밀파일에서 읽는다(코드·저장소에 키를 두지 않는다).
  기본 경로: C:\\Users\\jun\\ft_freqai\\user_data\\krx_secret.json  {"auth_key": "..."}
  환경변수 KRX_AUTH_KEY 가 있으면 그것을 우선 사용.
"""
from __future__ import annotations

import json
import os
import time

import requests

BASE = "http://data-dbg.krx.co.kr/svc/apis"
import keys as _keys                     # 키 위치는 keys.py 가 한 곳에서 정한다

_SECRET_CANDIDATES = _keys.krx_candidates() + [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "krx api.txt"),
]
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "krx_cache")
_MIN_INTERVAL = 0.35            # 호출 간격(초) — 과도한 호출 방지
_last_call = [0.0]


def _auth_key():
    k = os.environ.get("KRX_AUTH_KEY")
    if k:
        return k.strip()
    for p in _SECRET_CANDIDATES:
        if os.path.exists(p):
            try:
                if p.endswith(".json"):
                    with open(p, encoding="utf-8") as fp:
                        return str(json.load(fp).get("auth_key", "")).strip()
                with open(p, encoding="utf-8") as fp:
                    return fp.read().strip()
            except Exception:
                continue
    raise RuntimeError("KRX 인증키를 찾을 수 없습니다. krx_secret.json 또는 KRX_AUTH_KEY 설정 필요.")


def _throttle():
    wait = _last_call[0] + _MIN_INTERVAL - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def _get(path, params, cache_key=None, retries=3):
    """캐시 우선 조회 — 같은 날짜를 반복 호출하지 않는다(자문 F-113/F-122)."""
    if cache_key:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        cp = os.path.join(_CACHE_DIR, cache_key + ".json")
        if os.path.exists(cp):
            try:
                with open(cp, encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                pass
    for i in range(retries):
        try:
            _throttle()
            r = requests.get(f"{BASE}{path}", headers={"AUTH_KEY": _auth_key()},
                             params=params, timeout=20)
            if r.status_code == 200:
                rows = r.json().get("OutBlock_1", []) or []
                if cache_key:
                    with open(os.path.join(_CACHE_DIR, cache_key + ".json"), "w",
                              encoding="utf-8") as fp:
                        json.dump(rows, fp, ensure_ascii=False)
                return rows
            if r.status_code == 401:
                raise RuntimeError("KRX 401 — 인증키 또는 해당 API 이용신청 상태를 확인하세요.")
        except RuntimeError:
            raise
        except Exception:
            if i == retries - 1:
                return []
            time.sleep(1.0 + i)
    return []


def _f(v, default=0.0):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return default


def daily_market(basdd, market="ALL"):
    """일별매매정보 — 그날 상장된 전 종목. market: 'KOSPI'|'KOSDAQ'|'ALL'.
    반환: [{code,name,market,open,high,low,close,volume,value,marcap,sector}]"""
    out = []
    plans = []
    if market in ("KOSPI", "ALL"):
        plans.append(("/sto/stk_bydd_trd", "KOSPI"))
    if market in ("KOSDAQ", "ALL"):
        plans.append(("/sto/ksq_bydd_trd", "KOSDAQ"))
    for path, mk in plans:
        rows = _get(path, {"basDd": basdd}, cache_key=f"bydd_{mk}_{basdd}")
        for x in rows:
            code = str(x.get("ISU_CD", "")).strip()
            close = _f(x.get("TDD_CLSPRC"))
            if not code or close <= 0:
                continue
            out.append({
                "code": code, "name": x.get("ISU_NM", ""), "market": mk,
                "open": _f(x.get("TDD_OPNPRC")), "high": _f(x.get("TDD_HGPRC")),
                "low": _f(x.get("TDD_LWPRC")), "close": close,
                "volume": _f(x.get("ACC_TRDVOL")), "value": _f(x.get("ACC_TRDVAL")),
                "marcap": _f(x.get("MKTCAP")), "sector": x.get("SECT_TP_NM", ""),
                "date": basdd,
            })
    return out


def issue_base(basdd, market="ALL"):
    """종목기본정보 — 상장일·상장주식수. {code: {...}}"""
    out = {}
    plans = []
    if market in ("KOSPI", "ALL"):
        plans.append(("/sto/stk_isu_base_info", "KOSPI"))
    if market in ("KOSDAQ", "ALL"):
        plans.append(("/sto/ksq_isu_base_info", "KOSDAQ"))
    for path, mk in plans:
        rows = _get(path, {"basDd": basdd}, cache_key=f"base_{mk}_{basdd}")
        for x in rows:
            code = str(x.get("ISU_SRT_CD", "")).strip()
            if not code:
                continue
            out[code] = {"name": x.get("ISU_ABBRV", ""), "market": mk,
                         "list_date": str(x.get("LIST_DD", "")).strip(),
                         "shares": _f(x.get("LIST_SHRS")),
                         "sector": x.get("SECT_TP_NM", ""),
                         "kind": x.get("KIND_STKCERT_TP_NM", "")}
    return out


def pit_universe(basdd, top_n=200, market="ALL", min_value=0.0):
    """**진짜 point-in-time 유니버스** — 그 시점 시가총액 상위 N (미래 정보 없음).
    자문 A-9의 look-ahead를 근본 해결한다."""
    rows = daily_market(basdd, market)
    if min_value > 0:
        rows = [r for r in rows if r["value"] >= min_value]
    rows.sort(key=lambda r: -r["marcap"])
    return rows[:top_n]


def first_trading_day(year, market="ALL", max_probe=10):
    """해당 연도의 첫 거래일(휴장일을 건너뛰며 탐색)."""
    from datetime import date, timedelta
    d = date(year, 1, 1)
    for _ in range(max_probe):
        if d.weekday() < 5:
            s = d.strftime("%Y%m%d")
            if daily_market(s, "KOSPI"):
                return s
        d += timedelta(days=1)
    return None


def yearly_universes(y0, y1, top_n=150, market="ALL", min_value=0.0):
    """**연 1회 리밸런싱 PIT 유니버스**(자문 A-9 차선책).
    매년 첫 거래일의 시총 상위 N을 그 해 유니버스로 확정 → 미래 정보 없음.
    반환: {year: [{code,name,market,marcap}, ...]}"""
    out = {}
    for y in range(y0, y1 + 1):
        d = first_trading_day(y, market)
        if not d:
            continue
        uni = pit_universe(d, top_n, market, min_value)
        out[y] = [{"code": r["code"], "name": r["name"], "market": r["market"],
                   "marcap": r["marcap"], "asof": d} for r in uni]
        print(f"    {y}년 유니버스 {len(out[y])}종목 (기준일 {d}, "
              f"1위 {uni[0]['name'] if uni else '-'})")
    return out


def membership_map(yearly):
    """{code: set(years)} — 그 해에 유니버스 소속이었는지 판정용."""
    m = {}
    for y, rows in yearly.items():
        for r in rows:
            m.setdefault(r["code"], set()).add(y)
    return m


def trading_days(start, end, market="KOSPI", probe_step=1):
    """실제 거래일 목록 — 캐시에 있는 날짜를 우선 활용(호출 최소화)."""
    from datetime import datetime, timedelta
    d0 = datetime.strptime(start, "%Y%m%d")
    d1 = datetime.strptime(end, "%Y%m%d")
    days = []
    cur = d0
    while cur <= d1:
        if cur.weekday() < 5:                       # 주말 제외(휴장일은 조회 시 빈 응답)
            days.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=probe_step)
    return days
