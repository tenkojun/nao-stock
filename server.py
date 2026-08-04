# -*- coding: utf-8 -*-
"""
NAO STOCK — 백엔드 서버 (Flask)
================================
- 정적 UI(index.html/report.html) 서빙
- /api/stock/<code> : 한투 KIS 실데이터 → analyze() → UI용 JSON
                      KIS 미연결/오류 시 합성 폴백(live=false)로 화면 항상 유지
- /api/ai          : Claude API 전망 (우리 분석 데이터+뉴스 컨텍스트 주입)
                      ANTHROPIC_API_KEY(env)로만 호출, 없으면 스텁

실행:  python server.py   →  http://127.0.0.1:8770
실시세·수급: 한투 KIS(무지연) · 뉴스: 외부 · 판단은 종가 확정값
"""
from __future__ import annotations
import os, sys, json
import numpy as np
from flask import Flask, jsonify, request, send_from_directory

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, "engine"))
from analyze import analyze                      # noqa: E402

app = Flask(__name__, static_folder=None)
MODEL = os.environ.get("NAO_CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# ── 차트 레벨 계산 (POC·VWAP·저항·지지·밸류) ──
def _levels(ohlc, price):
    c = np.asarray(ohlc["close"], float); h = np.asarray(ohlc["high"], float)
    l = np.asarray(ohlc["low"], float); v = np.asarray(ohlc["volume"], float)
    typ = (h + l + c) / 3
    vwap = float(np.sum(typ * v) / np.sum(v)) if np.sum(v) else float(c[-1])
    # POC/밸류: 가격 히스토그램(거래량 가중)
    lo, hi = float(l.min()), float(h.max())
    bins = np.linspace(lo, hi, 40)
    idx = np.clip(np.digitize(c, bins) - 1, 0, len(bins) - 2)
    vol_at = np.zeros(len(bins) - 1)
    for i, b in enumerate(idx):
        vol_at[b] += v[i]
    poc = float((bins[np.argmax(vol_at)] + bins[np.argmax(vol_at) + 1]) / 2)
    order = np.argsort(vol_at)[::-1]
    cum, tot, sel = 0.0, vol_at.sum(), []
    for o in order:
        sel.append(o); cum += vol_at[o]
        if cum >= tot * 0.7:
            break
    va_lo = float(bins[min(sel)]); va_hi = float(bins[max(sel) + 1])
    # 저항/지지: 현재가 위/아래 최근 스윙
    res = float(np.min(h[h > price])) if np.any(h > price) else float(h.max())
    sup = float(np.max(l[l < price])) if np.any(l < price) else float(l.min())
    return {"poc": round(poc), "vwap": round(vwap), "res": round(res),
            "sup": round(sup), "va_low": round(va_lo), "va_high": round(va_hi)}


def _to_ohlc(df):
    """kis_kr.daily_ohlcv 결과(DataFrame 또는 dict 리스트) → dict of float 리스트.
    서버 환경에 pandas가 없어도 동작."""
    keys = ("open", "high", "low", "close", "volume")
    if isinstance(df, list):
        return {k: [float(r[k]) for r in df] for k in keys}
    return {k: [float(x) for x in df[k].tolist()] for k in keys}


def _fmtdate(s):
    s = str(s)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else s


def _dates_of(df):
    """DataFrame(index=datetime) 또는 dict 리스트에서 'YYYY-MM-DD' 날짜 리스트."""
    if isinstance(df, list):
        return [_fmtdate(r.get("date", "")) for r in df]
    try:
        return [d.strftime("%Y-%m-%d") for d in df.index]
    except Exception:
        return [_fmtdate(str(x)) for x in df.index]


def _synth():
    import datetime as _dt
    np.random.seed(1)
    c = np.cumsum(np.random.randn(120) * 2 - 0.5) + 300
    c = np.maximum(c, 60) * 850
    ohlc = {"close": c.tolist(), "high": (c * 1.012).tolist(),
            "low": (c * 0.988).tolist(), "open": np.roll(c, 1).tolist(),
            "volume": (np.random.rand(120) * 1e6 + 3e5).tolist()}
    today = _dt.date.today()
    dates = [(today - _dt.timedelta(days=(120 - 1 - i))).strftime("%Y-%m-%d")
             for i in range(120)]
    q = {"code": "005930", "name": "삼성전자", "price": float(c[-1]),
         "change_pct": -8.77}
    fl = {"foreign_5d": -246017, "org_5d": -587661,
          "foreign_dir": "순매도", "org_dir": "순매도",
          "rows": [{"foreign_net": np.random.randn() * 1e5,
                    "org_net": np.random.randn() * 1e5} for _ in range(20)]}
    return q, ohlc, fl, dates


def _costs(price, q=None):
    """거래비용·세금 설명(자문 A-13/0장(5)). 검정이 필요 없는 '확실한' 정보."""
    try:
        from costs import explain
        mk = (q or {}).get("market") or "KOSPI"
        cap = (q or {}).get("marcap")
        return explain(price, mk, cap)
    except Exception:
        return None


def _sr(ohlc, price):
    """지지·저항 존(전체 OHLC 기준 — 이전 저항까지 포착)."""
    try:
        from levels_sr import sr_zones
        return sr_zones(ohlc.get("open"), ohlc["high"], ohlc["low"], ohlc["close"],
                        ohlc.get("volume"), price)
    except Exception:
        return []


def _flow_pro(fl, ohlc):
    """전문 수급 해석(F-64 표준화 등). 평균 거래량은 최근 20일."""
    try:
        from flow_analysis import analyze_flow
        vol = ohlc.get("volume", [])
        avg_v = sum(vol[-20:]) / max(1, len(vol[-20:])) if vol else None
        return analyze_flow(fl.get("rows", []), avg_v)
    except Exception:
        return None


def _sma(c, p):
    """단순이동평균 — 값 부족 구간은 None. 전체 close에서 계산 후 표시창으로 슬라이스."""
    out = []
    for i in range(len(c)):
        out.append(round(sum(c[i - p + 1:i + 1]) / p) if i >= p - 1 else None)
    return out


def _payload(q, ohlc, fl, live, dates, mc_paths=2000, mc_steps=20, rs=None, wk=None):
    res = analyze(q, ohlc, fl, mc_paths=mc_paths, mc_steps=mc_steps, wk_ohlc=wk)
    lv = _levels(ohlc, res["price"])
    n = len(ohlc["close"]); show = min(120, n)
    sl = slice(n - show, n)
    _c = ohlc["close"]
    ma = {p: _sma(_c, int(p))[sl] for p in (5, 20, 60, 120)}   # 전체계산→표시창 슬라이스
    fp = _flow_pro(fl, ohlc)
    try:                                     # 논문근거 지표 + 정밀 체크리스트
        from indicators_pro import analyze_pro
        from checklist import build_checklist
        pro = analyze_pro(ohlc["high"], ohlc["low"], ohlc["close"], ohlc["volume"], mc_steps)
        chk = build_checklist(res, pro, None, fp)
    except Exception:
        pro, chk = None, None
    # 수급 유입 마커: 최근 rows에서 외국인+기관 순매수>0 인 날 → 캔들 인덱스(근사)
    rows = fl.get("rows", [])[:show]
    markers = [show - 1 - i for i, r in enumerate(rows)
               if (r.get("foreign_net", 0) + r.get("org_net", 0)) > 0]
    off = n - show   # 신호 인덱스(전체 기준) → 표시창 기준으로 보정
    sig = [{"i": s["i"] - off, "type": s["type"], "why": s.get("why", "")}
           for s in res.get("signals", []) if s["i"] >= off]
    v = res["verdict"]
    return {
        "live": live, "code": res["code"], "name": q.get("name", ""),
        "price": res["price"], "change_pct": res["change_pct"],
        "ohlc": {k: ohlc[k][sl] for k in ("open", "high", "low", "close", "volume")},
        "dates": list(dates[sl]) if dates else [],
        "levels": lv, "stop": res["stop"], "flow_markers": markers,
        # 개인까지 넣는다 — 셋을 같이 봐야 "누가 사고 누가 파는지"가 보인다
        "flow": {"foreign_5d": fl.get("foreign_5d", 0), "org_5d": fl.get("org_5d", 0),
                 "person_5d": sum(r.get("person_net", 0) for r in (fl.get("rows") or [])[:5]),
                 "foreign_dir": fl.get("foreign_dir", ""), "org_dir": fl.get("org_dir", "")},
        "flow_pro": fp,
        "sr_zones": _sr(ohlc, res["price"]),
        "ma": {("ma%d" % p): v for p, v in ma.items()},
        "pro": pro,                     # 논문근거 지표(HAR-RV·Amihud·VWAP)
        "checklist": chk,               # 정밀 체크리스트(증거 등급)
        "costs": _costs(res["price"], q),   # 거래비용·세금(자문 A-13, 계산으로 확실한 정보)
        "regime": res["regime"], "rsi": res["rsi"], "vol_pct": res["vol_pct"],
        "ret20": res["ret20"], "high52": res["high52"], "surge": res.get("surge", False),
        "mc": res.get("mc", {}), "keylevels": res.get("keylevels", {}),
        "tf_reco": res.get("tf_reco", {}), "consensus": res.get("consensus", {}),
        "signals": sig, "market_state": res.get("market_state", ""),
        "divergence": res.get("divergence", {}), "rs": rs,
        "verdict": {"grade": v["grade"], "signal": v["signal"], "score": v["score"],
                    "simple3": v.get("simple3", "중립"),
                    "line": v["verdict"], "plain": v.get("plain", ""),
                    "ceiling": v.get("ceiling_notes", [])},
        "entry": res.get("entry", {}),   # ⭐검증된 진입 적정도(관찰서술)
        "contributions": res["contributions"][:6],
        "net_score": res["resolved"]["net_score"],
        "conflict": res["resolved"]["conflict_ratio"],
    }


_FLOWDIR = os.path.join(_DIR, "data", "flow")


def _log_flow(code, fl):
    """수급 이력 자동 축적 (전문가 F-71/v2 대비: look-ahead 없는 수급 검증용 데이터).
    KIS는 최근 20일만 주므로 조회 때마다 CSV에 날짜별 누적(중복 제거)."""
    try:
        os.makedirs(_FLOWDIR, exist_ok=True)
        path = os.path.join(_FLOWDIR, f"{code}.csv")
        seen = set()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                seen = {ln.split(",")[0] for ln in f.read().splitlines()[1:] if ln}
        new = [r for r in fl.get("rows", []) if r.get("date") and r["date"] not in seen]
        if new:
            hdr = not os.path.exists(path)
            with open(path, "a", encoding="utf-8") as f:
                if hdr:
                    f.write("date,foreign_net,org_net,person_net\n")
                for r in sorted(new, key=lambda x: x["date"]):
                    f.write(f"{r['date']},{r.get('foreign_net',0):.0f},"
                            f"{r.get('org_net',0):.0f},{r.get('person_net',0):.0f}\n")
    except Exception:
        pass                                    # 축적 실패는 본 기능에 영향 없음


@app.route("/")
def home():
    return send_from_directory(_DIR, "index.html")


@app.route("/<path:fn>")
def static_files(fn):
    return send_from_directory(_DIR, fn)


@app.route("/api/stock/<code>")
def api_stock(code):
    try:
        from kis_kr import KISKorea
        kis = KISKorea()
        tf = request.args.get("tf", "D")
        period = tf if tf in ("D", "W", "M") else "D"
        mcp = int(request.args.get("mc_paths", 2000))
        mcs = int(request.args.get("mc_steps", 20))
        q = kis.quote(code)
        if not q.get("name"):
            q["name"] = WL_NAMES.get(code, code)
        if period == "D":                       # MA120·존 위해 장기(≈250봉) 청크 수집
            df = kis.daily_ohlcv_long(code, 250)
        else:
            df = kis.daily_ohlcv(code, 120, period)
        ohlc = _to_ohlc(df)
        dates = _dates_of(df)
        fl = kis.investor_flow(code)
        _log_flow(code, fl)                    # v1.2: 수급 이력 축적(향후 수급 포함 검증용)
        wk = None
        try:                                   # 전문가 C-27: 주봉 ADX는 실제 주봉으로
            wk = _to_ohlc(kis.daily_ohlcv(code, 60, "W"))
        except Exception:
            wk = None
        rs = None
        try:
            kospi = kis.index_daily("0001", 30)
            cc = ohlc["close"]
            if len(kospi) > 21 and len(cc) > 21:
                sret = cc[-1] / cc[-22] - 1
                kret = kospi[-1] / kospi[-22] - 1
                rs = round((sret - kret) * 100, 1)
        except Exception:
            rs = None
        return jsonify(_payload(q, ohlc, fl, True, dates, mcp, mcs, rs, wk))
    except Exception as e:
        q, ohlc, fl, dates = _synth()
        p = _payload(q, ohlc, fl, False, dates,
                     int(request.args.get("mc_paths", 2000)),
                     int(request.args.get("mc_steps", 20)), None)
        p["error"] = f"{type(e).__name__}: {e} (합성 폴백)"
        return jsonify(p)


@app.route("/api/flowmap")
def api_flowmap():
    """수급 흐름 지도 — 오늘 외국인·기관이 어디로 자금을 넣고 빼는지(종목별 순매수 억원)."""
    try:
        from kis_kr import KISKorea
        kis = KISKorea()
        rows = {}
        for s in ("0", "1"):                     # 순매수상위 + 순매도상위
            for x in kis.foreign_inst_flow(s):
                c = x["code"]
                if c and c not in rows:
                    rows[c] = x
        items = [_flow_item(x) for x in rows.values()]
        return jsonify({"items": items,
                        "note": "개인은 '외국인+기관'의 반대편으로 추정한 값입니다(정확 집계 아님). "
                                "거래량 대비 %는 오늘 총거래량 중 해당 주체 순매수 비중.",
                        "updated": __import__("datetime").datetime.now().strftime("%m-%d %H:%M")})
    except Exception as e:
        return jsonify({"items": [], "error": f"{type(e).__name__}: {e}"})


def _flow_item(x):
    """종목별 수급 정밀화: 외국인·기관·개인(추정) 각각 억원 + 오늘 거래량 대비 %."""
    px = x["price"] or 0
    vol = x.get("vol") or 0
    amt = lambda q: round(q * px / 1e8, 1)                  # 수량 → 억원
    pct = lambda q: round(q / vol * 100, 1) if vol else None  # 오늘 거래량 대비 %
    f_q, o_q = x["frgn"], x["org"]
    p_q = -(f_q + o_q)                                       # 개인 ≈ 반대편(추정)
    return {"code": x["code"], "name": x["name"], "price": int(px), "chg": x["chg"],
            "frgn": amt(f_q), "org": amt(o_q), "indi": amt(p_q),
            "frgn_pct": pct(f_q), "org_pct": pct(o_q), "indi_pct": pct(p_q),
            "sum": round(amt(f_q) + amt(o_q), 1),
            "fund": amt(x.get("fund", 0)), "insu": amt(x.get("insu", 0)),
            "vol": int(vol)}


_SECCACHE = {"map": None, "t": 0}


def _sector_map():
    """코드→broad 섹터 (FDR KRX-DESC). 10분 캐시."""
    import time as _t
    if _SECCACHE["map"] and _t.time() - _SECCACHE["t"] < 600:
        return _SECCACHE["map"]
    try:
        from discover import _sectors
        _SECCACHE["map"] = _sectors(); _SECCACHE["t"] = _t.time()
    except Exception:
        _SECCACHE["map"] = {}
    return _SECCACHE["map"]


@app.route("/api/prefs", methods=["GET", "POST"])
def api_prefs():
    """설정·보유종목 서버 저장(업데이트에도 보존). 로그인 사용자별로 분리."""
    from auth import whoami
    from prefs import load, save, status
    u = whoami(request.headers.get("X-Auth-Token", ""))
    uid = (u or {}).get("id", "father")
    if request.method == "POST":
        j = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "prefs": save(uid, j)})
    return jsonify({"prefs": load(uid), "status": status()})


@app.route("/api/auth/accounts")
def api_auth_accounts():
    """로그인 화면용 계정 목록(비밀 정보 없음)."""
    from auth import accounts, key_status
    return jsonify({"accounts": accounts(), "keys": key_status()})


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    from auth import login
    j = request.get_json(silent=True) or {}
    return jsonify(login(j.get("id", ""), j.get("password", "")))


@app.route("/api/auth/me")
def api_auth_me():
    from auth import whoami
    tok = request.headers.get("X-Auth-Token") or request.args.get("token", "")
    u = whoami(tok)
    return jsonify({"ok": bool(u), "user": u})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    from auth import logout
    return jsonify(logout(request.headers.get("X-Auth-Token", "")))


@app.route("/api/flow/<code>")
def api_flow(code):
    """종목 수급 — 외국인·기관·개인을 같은 단위로. 일별 + 오늘 시간대별."""
    import flow_view
    try:
        return jsonify(flow_view.build(code, int(request.args.get("days", 20)),
                                       date=request.args.get("date") or None))
    except Exception as e:
        return jsonify({"code": code, "days": [], "error": f"{type(e).__name__}: {e}"})


@app.route("/api/session")
def api_session():
    """오늘장 기록 조회 / 캘린더용 날짜 목록.
    KIS 는 지난 날의 시간대별 수급을 주지 않으므로 **장중에 우리가 쌓은 것**을 읽는다."""
    import session_rec as S
    date = request.args.get("date")
    if request.args.get("dates") == "1" or not date:
        st = S.status()
        if not date:
            st["day"] = S.load(S.today())
        return jsonify(st)
    return jsonify({"date": date, "day": S.load(date), "dates": S.dates()[:60]})


@app.route("/api/session/record", methods=["POST"])
def api_session_record():
    """지금 한 컷 기록(수동) — 동작 확인용."""
    import session_rec as S
    try:
        return jsonify({"ok": True, "snaps": S.record_once(), "status": S.status()})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"{type(e).__name__}: {e}"})


@app.route("/api/search")
def api_search():
    """종목 검색 — 코드를 몰라도 이름으로 찾는다. '삼' → 삼성전자·삼성중공업…"""
    import stocks
    q = request.args.get("q", "")
    try:
        return jsonify({"ok": True, "items": stocks.search(q, int(request.args.get("n", 12))),
                        "status": stocks.status()})
    except Exception as e:
        return jsonify({"ok": False, "items": [], "msg": f"검색 오류: {type(e).__name__}"})


@app.route("/api/notice", methods=["GET", "POST"])
def api_notice():
    """공지 — 읽기는 누구나, 쓰기·삭제는 관리자만.
    PC마다 서버가 따로 도는 구조라 GitHub 저장소를 통로로 쓴다(engine/notice.py)."""
    from auth import whoami
    import notice as N
    u = whoami(request.headers.get("X-Auth-Token", ""))
    uid = (u or {}).get("id", "father")
    is_admin = bool(u and u.get("role") == "admin")
    if request.method == "GET":
        r = N.board(uid, force=request.args.get("force") == "1")
        r["admin"] = is_admin
        return jsonify(r)
    j = request.get_json(silent=True) or {}
    act = j.get("action", "publish")
    if act == "read":                      # 읽음 표시는 본인 것이므로 관리자가 아니어도 된다
        N.mark_read(uid, j.get("ids"))
        return jsonify(N.board(uid))
    if not is_admin:
        return jsonify({"ok": False, "msg": "관리자만 쓸 수 있습니다."})
    res = N.remove(j.get("id")) if act == "delete" else \
        N.publish(j.get("title"), j.get("body"), (u or {}).get("name", "관리자"))
    out = N.board(uid, force=True)          # 갱신된 목록에
    out["ok"], out["msg"] = res["ok"], res["msg"]   # 방금 한 작업의 결과를 얹는다
    out["admin"] = True                     # (순서를 바꾸면 board 의 ok/msg 가 덮어쓴다)
    return jsonify(out)


@app.route("/api/keys", methods=["GET", "POST"])
def api_keys():
    """API 키 상태 조회 / 저장 / 연결시험.
    ⚠ 응답에는 **키 값을 절대 담지 않는다**(존재 여부와 끝 4자리만).
    변경은 관리자만 — 일반 계정에서 실수로 지우는 일이 없도록."""
    from auth import whoami
    import keys as K
    u = whoami(request.headers.get("X-Auth-Token", ""))
    is_admin = bool(u and u.get("role") == "admin")
    if request.method == "GET":
        return jsonify({"ok": True, "status": K.status(), "admin": is_admin})
    if not is_admin:
        return jsonify({"ok": False, "msg": "관리자 계정에서만 변경할 수 있습니다."})
    j = request.get_json(silent=True) or {}
    prov, act = j.get("provider", ""), j.get("action", "save")
    r = (K.clear(prov) if act == "clear"
         else K.test(prov) if act == "test"
         else K.import_files(j.get("files")) if act == "import"
         else K.save(prov, j.get("values")))
    r["status"] = K.status()
    return jsonify(r)


@app.route("/api/auth/password", methods=["POST"])
def api_auth_password():
    """비밀번호 설정 — 관리자만(자기 계정 또는 사용자 계정)."""
    from auth import whoami, set_password
    u = whoami(request.headers.get("X-Auth-Token", ""))
    if not u or u.get("role") != "admin":
        return jsonify({"ok": False, "msg": "관리자만 변경할 수 있습니다."})
    j = request.get_json(silent=True) or {}
    return jsonify(set_password(j.get("id", ""), j.get("password", "")))


@app.route("/api/update/check")
def api_update_check():
    """새 버전 확인(배포 후 원격 업데이트용)."""
    from updater import check
    return jsonify(check(force=request.args.get("force") == "1"))


@app.route("/api/update/apply", methods=["POST"])
def api_update_apply():
    """업데이트 적용 — 사용자가 명시적으로 승낙했을 때만 호출된다."""
    from updater import apply_update
    return jsonify(apply_update())


@app.route("/api/allocate", methods=["POST"])
def api_allocate():
    """적립식 배분 제안(자문 H-154). 매도 없이 매수만으로 쏠림 완화."""
    from allocate import plan
    j = request.get_json(silent=True) or {}
    try:
        out = plan(j.get("holdings") or {}, j.get("budget") or 0,
                   j.get("targets"), float(j.get("max_weight") or 0.25))
        # 매수 실비용 첨부
        try:
            from costs import trade_cost
            for it in out.get("items", []):
                if it["add"] > 0:
                    c = trade_cost(it["add"], None, "buy")
                    it["cost"] = c["total"]
        except Exception:
            pass
        return jsonify(out)
    except Exception as e:
        return jsonify({"items": [], "error": f"{type(e).__name__}: {e}"})


@app.route("/api/journal", methods=["GET", "POST"])
def api_journal():
    """의사결정 기록장(자문 K-198). GET=조회, POST=기록 추가."""
    from journal import add_entry, entries, context_for, stats
    if request.method == "POST":
        j = request.get_json(silent=True) or {}
        try:
            e = add_entry(j.get("code"), j.get("name"), j.get("side"), j.get("amount"),
                          j.get("plan"), j.get("reason"), j.get("snapshot"))
            return jsonify({"ok": True, "entry": e})
        except Exception as ex:
            return jsonify({"ok": False, "msg": f"{type(ex).__name__}: {ex}"})
    code = request.args.get("code")
    return jsonify({"entries": entries(code), "context": context_for(code) if code else None,
                    "stats": stats()})


_NEWSCACHE = {}


@app.route("/api/news")
def api_news():
    """뉴스 피드 — 종목 뉴스 + 시장 실시간 속보. 2분 캐시."""
    import time as _t
    code = request.args.get("code") or None
    key = code or "_market"
    c = _NEWSCACHE.get(key)
    if c and _t.time() - c["t"] < 120:
        return jsonify(c["d"])
    try:
        from news_feed import feed
        d = feed(code)
        _NEWSCACHE[key] = {"d": d, "t": _t.time()}
        return jsonify(d)
    except Exception as e:
        return jsonify({"stock": [], "market": [], "error": f"{type(e).__name__}: {e}"})


_MACROCACHE = {"d": None, "t": 0}


@app.route("/api/macro")
def api_macro():
    """매크로 시세(환율·미국지수·VIX·유가) + 증시 캘린더. 3분 캐시."""
    import time as _t
    if _MACROCACHE["d"] and _t.time() - _MACROCACHE["t"] < 180:
        return jsonify(_MACROCACHE["d"])
    try:
        from macro_cal import macro_snapshot, calendar_events
        out = {"macro": macro_snapshot(), "calendar": calendar_events(),
               "updated": __import__("datetime").datetime.now().strftime("%H:%M")}
        _MACROCACHE["d"] = out; _MACROCACHE["t"] = _t.time()
        return jsonify(out)
    except Exception as e:
        return jsonify({"macro": [], "calendar": [], "error": f"{type(e).__name__}: {e}"})


@app.route("/api/flowos")
def api_flowos():
    """MARKET FLOW OS — 날씨·맥박·유동성강·섹터·고래·내러티브 통합."""
    try:
        from kis_kr import KISKorea
        from flow_os import build_flow_os
        kis = KISKorea()
        rows = {}
        for s in ("0", "1"):
            for x in kis.foreign_inst_flow(s):
                if x["code"] and x["code"] not in rows:
                    rows[x["code"]] = x
        flows = [_flow_item(x) for x in rows.values()]
        out = build_flow_os(flows, _sector_map())
        out["updated"] = __import__("datetime").datetime.now().strftime("%m-%d %H:%M")
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"})


@app.route("/api/intraday/<code>")
def api_intraday(code):
    """저타임프레임 미시구조 분석 (5분봉 등) — Volume Profile·SMC·오더플로우 근사."""
    interval = int(request.args.get("interval", 5))
    days = max(1, min(5, int(request.args.get("days", 3))))
    try:
        from kis_kr import KISKorea
        from microstructure import analyze_micro
        k = KISKorea()
        # 당일치만 보면 맥락이 없다 → 최근 며칠을 이어 붙인다(1분봉은 양이 많아 당일만)
        bars = (k.minute_bars(code, interval=interval) if interval < 5 or days <= 1
                else k.minute_bars_days(code, interval=interval, days=days))
        if not bars:                                  # 여러 날 실패 시 당일치로 물러선다
            bars = k.minute_bars(code, interval=interval)
        # ⚠ 차트는 여러 날을 보여주되 **분석은 최근 세션만** 쓴다.
        #    3일치로 볼륨프로파일을 내면 밸류가 202,000~250,750 처럼 화면을 통째로
        #    덮어 아무 의미가 없다(실제로 그렇게 나왔다).
        last_day = bars[-1].get("date") if bars else None
        sess = [b for b in bars if b.get("date") == last_day] if last_day else bars
        if len(sess) < 10:                        # 장 시작 직후 등 표본이 너무 적으면 전체로
            sess = bars

        out = analyze_micro(sess, interval)
        out["bars"] = bars                        # 화면에는 여러 날을 그린다
        out["session_date"] = last_day
        out["session_bars"] = len(sess)
        if sess:                                  # 인트라데이 지지·저항 존(블록용)
            try:
                from levels_sr import sr_zones
                out["sr_zones"] = sr_zones([b["open"] for b in sess], [b["high"] for b in sess],
                                           [b["low"] for b in sess], [b["close"] for b in sess],
                                           [b["volume"] for b in sess], sess[-1]["close"],
                                           max_side=2)
            except Exception:
                out["sr_zones"] = []
        return jsonify(out)
    except Exception as e:
        return jsonify({"bars": [], "error": f"{type(e).__name__}: {e}",
                        "note": "분봉 데이터를 불러오지 못했습니다."})


@app.route("/api/discover")
def api_discover():
    """시장 발굴 — 사전 계산된 모멘텀 스크린(data/discovery.json) 조회. 섹터 필터·정렬."""
    path = os.path.join(_DIR, "data", "discovery.json")
    if not os.path.exists(path):
        return jsonify({"items": [], "updated": None,
                        "msg": "아직 발굴 데이터가 없습니다. 갱신을 눌러주세요."})
    try:
        with open(path, encoding="utf-8") as fp:
            d = json.load(fp)
    except Exception as e:
        return jsonify({"items": [], "updated": None, "msg": f"읽기 오류: {e}"})
    allitems = d.get("items", [])
    for x in allitems:                                # NaN 섹터 방어(구 캐시 호환)
        if not isinstance(x.get("sector"), str):
            x["sector"] = "기타"
    sectors = sorted({x.get("sector", "기타") for x in allitems})
    items = allitems
    sector = request.args.get("sector")
    if sector and sector != "전체":
        items = [x for x in items if x.get("sector") == sector]
    limit = int(request.args.get("limit", 40))
    return jsonify({"updated": d.get("updated"), "count": len(items),
                    "sectors": sectors, "items": items[:limit]})


@app.route("/api/discover/refresh", methods=["POST"])
def api_discover_refresh():
    """발굴 스캔 재실행(백그라운드). 완료까지 수십 초~1분."""
    import subprocess
    try:
        subprocess.Popen([sys.executable, os.path.join(_DIR, "engine", "discover.py"), "--top", "250"],
                         cwd=os.path.join(_DIR, "engine"))
        return jsonify({"ok": True, "msg": "갱신 시작(약 1분 뒤 새로고침)"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})


@app.route("/api/rank")
def api_rank():
    """관심종목 내부 순위 — 검증된 모멘텀(60일 고점근접) 강한 순 + 가치·퀄리티 참고."""
    import numpy as np
    from fundamentals import fetch_fundamentals
    codes = [c.strip() for c in request.args.get("codes", "").split(",") if c.strip()][:20]
    rows = []
    try:
        from kis_kr import KISKorea
        kis = KISKorea()
    except Exception:
        kis = None
    for code in codes:
        mom = None
        try:
            o = _to_ohlc(kis.daily_ohlcv(code, 80, "D"))
            c, h = o["close"], o["high"]
            if len(c) >= 60:
                mom = round((c[-1] / max(h[-60:]) - 1) * 100, 1)
        except Exception:
            mom = None
        f = fetch_fundamentals(code) or {}
        rows.append({"code": code, "mom": mom, "pbr": f.get("pbr"), "roe": f.get("roe")})
    rows.sort(key=lambda r: (r["mom"] is None, -(r["mom"] if r["mom"] is not None else -999)))
    return jsonify({"items": rows,
                    "note": "이 앱이 검증한 모멘텀(60일 고점 대비, 강할수록 위)이 강한 순입니다. "
                            "장기 보유일수록 강한 종목이 유리(자체 검증). 가치(PBR)·퀄리티(ROE)는 문헌 근거 참고값. "
                            "순위는 참고이며 매수 추천이 아닙니다."})


@app.route("/api/evaluate/<code>")
def api_evaluate(code):
    """종목 자체 평가(가치·퀄리티·배당·모멘텀). 네이버 펀더멘털 + KIS 일봉(모멘텀)."""
    from fundamentals import stock_evaluation
    close = high = None
    try:
        from kis_kr import KISKorea
        o = _to_ohlc(KISKorea().daily_ohlcv(code, 120, "D"))
        close, high = o["close"], o["high"]
    except Exception:
        pass
    try:
        return jsonify(stock_evaluation(code, close, high))
    except Exception as e:
        return jsonify({"code": code, "items": [], "error": f"{type(e).__name__}: {e}",
                        "caveat": "평가 데이터를 불러오지 못했습니다."})


WL_NAMES = {"005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
            "035720": "카카오", "005380": "현대차", "247540": "에코프로비엠"}


@app.route("/api/correlation")
def api_correlation():
    """관심종목 일간수익 상관행렬 → 3D 좌표(고전 MDS). 델타(공행) 군집 시각화."""
    codes = request.args.get("codes", ",".join(WL_NAMES)).split(",")
    series, live = {}, True
    try:
        from kis_kr import KISKorea
        kis = KISKorea()
        for c in codes:
            df = kis.daily_ohlcv(c, 120)
            series[c] = np.diff(np.log(np.asarray(_to_ohlc(df)["close"], float)))
    except Exception:
        live = False
        rng = np.random.default_rng(3)
        base = rng.standard_normal(119)          # 공통 시장요인
        for i, c in enumerate(codes):
            beta = 0.3 + 0.5 * (i % 3) / 2
            series[c] = beta * base + rng.standard_normal(119) * 0.9
    L = min(len(v) for v in series.values())
    M = np.array([series[c][-L:] for c in codes])
    corr = np.corrcoef(M)
    n = len(codes)
    D = 1.0 - corr
    J = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * J.dot(D ** 2).dot(J)
    w, V = np.linalg.eigh(B)
    idx = np.argsort(w)[::-1][:3]
    coords = V[:, idx] * np.sqrt(np.maximum(w[idx], 1e-9))
    # 정규화
    mx = np.max(np.abs(coords)) or 1.0
    coords = coords / mx
    nodes = [{"code": codes[i], "name": WL_NAMES.get(codes[i], codes[i]),
              "x": float(coords[i, 0]), "y": float(coords[i, 1]),
              "z": float(coords[i, 2])} for i in range(n)]
    edges = [{"a": i, "b": j, "corr": round(float(corr[i, j]), 2)}
             for i in range(n) for j in range(i + 1, n)]
    return jsonify({"live": live, "nodes": nodes, "edges": edges})


@app.route("/api/market")
def api_market():
    """Market Context Phase 1: 실시간 지수 대시보드 + 거래대금 상위(주도주)."""
    out = {"live": True, "indices": [], "ranking": [], "error": ""}
    try:
        from kis_kr import KISKorea
        kis = KISKorea()
        for name, idx in (("KOSPI", "0001"), ("KOSDAQ", "1001")):
            try:
                q = kis.index_quote(idx)
                out["indices"].append({"name": name, "value": q["value"], "chg": q["chg"]})
            except Exception:
                pass
        try:
            out["ranking"] = kis.ranking_volume(15)
        except Exception as e:
            out["error"] = f"ranking: {e}"
        try:
            out["ranking_up"] = kis.ranking_fluctuation(15, rise=True)
        except Exception:
            out["ranking_up"] = sorted(out.get("ranking", []),
                                       key=lambda x: -x.get("chg", 0))[:15]
    except Exception as e:
        out["live"] = False
        out["error"] = str(e)
    if not out["ranking"]:
        rng = np.random.default_rng(5)
        out["ranking"] = [{"code": c, "name": WL_NAMES.get(c, c),
                           "price": float(rng.integers(3, 300) * 1000),
                           "chg": round(float(rng.standard_normal() * 3), 2),
                           "amount": float(rng.integers(50, 900) * 1e8),
                           "volume": float(rng.integers(1, 30) * 1e6)}
                          for c in WL_NAMES]
        out["live"] = out["live"] and False
    if not out.get("ranking_up"):
        out["ranking_up"] = sorted(out["ranking"], key=lambda x: -x.get("chg", 0))
    if not out["indices"]:
        out["indices"] = [{"name": "KOSPI", "value": 2742.1, "chg": 0.61},
                          {"name": "KOSDAQ", "value": 861.4, "chg": 0.94}]
    return jsonify(out)


# ── 검증 실행 엔드포인트 (백그라운드 잡) — Claude가 Chrome으로 트리거·결과 확인 ──
import threading
_VAL = {"status": "idle", "log": [], "result": None}


def _run_validation(codes):
    import io, contextlib
    try:
        _VAL.update(status="running", log=["시작…"], result=None)
        from kis_kr import KISKorea
        import validate as V
        kis = KISKorea()
        results = []
        import time as _t
        for code, name in codes.items():
            _VAL["log"].append(f"{name} 수집 중…")
            for attempt in range(3):           # EGW00201 재시도
                try:
                    rows = kis.daily_ohlcv_long(code, 600)
                    keys = ("open", "high", "low", "close", "volume")
                    ohlc = {k: [float(r[k]) for r in rows] for k in keys}
                    _VAL["log"].append(f"{name} {len(rows)}봉 → 평가 중…")
                    results.append(V.run_symbol(f"{name}({code})", ohlc, V.ZERO_FLOW))
                    break
                except Exception as e:
                    if "EGW00201" in str(e) and attempt < 2:
                        _t.sleep(2.0)
                        continue
                    results.append({"name": f"{name}({code})", "error": str(e)[:80]})
                    break
            _t.sleep(1.0)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            V.report(results)
        _VAL.update(status="done", result={"raw": results, "text": buf.getvalue()})
        _VAL["log"].append("완료")
    except Exception as e:
        _VAL.update(status="error", result={"text": f"{type(e).__name__}: {e}"})


@app.route("/api/validate/start")
def api_validate_start():
    if _VAL["status"] == "running":
        return jsonify({"ok": False, "msg": "이미 실행 중"})
    codes = {"005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
             "005380": "현대차", "035720": "카카오", "247540": "에코프로비엠"}
    threading.Thread(target=_run_validation, args=(codes,), daemon=True).start()
    return jsonify({"ok": True, "msg": "검증 시작(수 분 소요)"})


@app.route("/api/validate/status")
def api_validate_status():
    out = {"status": _VAL["status"], "log": _VAL["log"][-6:]}
    if _VAL["status"] in ("done", "error") and _VAL["result"]:
        out["text"] = _VAL["result"]["text"]
    return jsonify(out)


@app.route("/api/ai", methods=["POST"])
def api_ai():
    body = request.get_json(force=True)
    q = body.get("question", "")
    ctx = body.get("context", "")
    import keys as _K
    key = _K.anthropic()
    if not key:
        return jsonify({"ok": False,
            "answer": "Claude API 키가 아직 없습니다. "
                      "설정 → API 연결에서 키를 넣으면 분석 데이터+뉴스를 종합해 전망을 제공합니다.",
            "context": ctx})
    try:
        import requests
        sys_p = ("당신은 한국 주식 애널리스트입니다. 제공된 NAO STOCK 분석 데이터와 "
                 "뉴스만 근거로, 확정적 단정 없이 위험과 함께 균형있게 설명하세요. "
                 "투자 권유가 아니라 정보 제공임을 전제합니다.")
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 700, "system": sys_p,
                  "messages": [{"role": "user",
                    "content": f"[분석 데이터]\n{ctx}\n\n[질문]\n{q}"}]},
            timeout=40)
        j = r.json()
        txt = "".join(b.get("text", "") for b in j.get("content", []))
        return jsonify({"ok": True, "answer": txt or json.dumps(j)[:400]})
    except Exception as e:
        return jsonify({"ok": False, "answer": f"AI 호출 오류: {e}"})


def _start_session_recorder():
    """장중 5분마다 시간대별 수급을 기록한다.
    KIS 는 지난 날의 시간대별 수급을 주지 않으므로, 그때그때 쌓지 않으면 영영 못 본다.
    서버가 떠 있는 동안에만 돈다(앱을 안 켠 날은 기록이 없다)."""
    try:
        import session_rec
        session_rec.start()
    except Exception:
        pass


_start_session_recorder()


if __name__ == "__main__":
    print("NAO STOCK  ·  http://127.0.0.1:8770  (자동 리로드 ON — 코드 수정 시 자동 반영)")
    app.run(host="127.0.0.1", port=8770, debug=True, use_reloader=True)
