# -*- coding: utf-8 -*-
"""
MARKET FLOW OS — 시장의 돈 흐름을 한 화면에 (비전 문서 → 실데이터 구현)
=====================================================================
"숫자를 읽는 게 아니라 흐름을 느끼게" 하되, 이 프로젝트 원칙대로 **근거 있는 것만**.

  ① 시장 날씨(Risk-On/Off)  ← breadth·지수·변동성 (근거: 시장 breadth는 글로벌 주식
     수익 예측력이 문헌으로 확인됨 — 사이즈·모멘텀·52주고가와 독립적 정보.
     Herding for profits: Market breadth and the cross-section of global equity returns)
  ② 시장 맥박(Pulse)        ← 모멘텀·유동성·breadth·리스크 게이지
  ③ 유동성 강(Flow River)   ← 투자자(외국인·기관·개인) → 섹터 → 종목 자금 경로 (KIS 실수급)
  ④ 섹터 히트맵             ← 섹터별 순매수·등락
  ⑤ 고래 탐지(Whale)        ← 대형 순매수/순매도 이벤트
  ⑥ AI 내러티브             ← 규칙기반 자연어(환각 없음, 계산된 사실만 서술)

⚠ 정직성: 날씨·맥박은 '현재 상태 요약'이지 예측이 아니다. 수급은 온도계(F-62).
데이터: KIS 외국인기관 매매종목 가집계 + FDR 전종목 스냅샷(breadth·섹터).
"""
from __future__ import annotations
import numpy as np

BREADTH_PAPER = ("Herding for profits: Market breadth and the cross-section of global equity returns",
                 "Economic Modelling (2020)",
                 "https://www.sciencedirect.com/science/article/pii/S0264999319312982")

# discover.py의 broad 섹터 매핑 재사용
try:
    from discover import _broad
except Exception:                                   # 단독 실행 대비
    def _broad(x):
        return "기타"


def market_breadth():
    """전종목 등락 스냅샷 → ADR·상승/하락 종목수·거래대금 편중 (M-134 breadth)."""
    import FinanceDataReader as fdr
    df = fdr.StockListing("KRX")
    df = df[df["Market"].isin(["KOSPI", "KOSDAQ"])]
    chg = df["ChagesRatio"].astype(float)
    up = int((chg > 0).sum()); dn = int((chg < 0).sum()); flat = int((chg == 0).sum())
    adr = round(up / max(dn, 1), 2)
    strong_up = int((chg >= 5).sum()); strong_dn = int((chg <= -5).sum())
    return {"up": up, "down": dn, "flat": flat, "adr": adr,
            "up_pct": round(up / max(up + dn + flat, 1) * 100, 1),
            "strong_up": strong_up, "strong_dn": strong_dn,
            "median_chg": round(float(chg.median()), 2),
            "paper": BREADTH_PAPER}


def _index_snapshot():
    """KOSPI·KOSDAQ 최근 흐름(등락률·실현변동성)."""
    import FinanceDataReader as fdr
    out = {}
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        try:
            d = fdr.DataReader(sym).tail(60)
            c = d["Close"].to_numpy(float)
            r = np.diff(np.log(c))
            out[name] = {"last": round(float(c[-1]), 2),
                         "chg": round(float(c[-1] / c[-2] - 1) * 100, 2),
                         "vol20": round(float(np.std(r[-20:]) * np.sqrt(252) * 100), 1),
                         "ret20": round(float(c[-1] / c[-21] - 1) * 100, 1)}
        except Exception:
            out[name] = None
    return out


def market_weather(breadth, idx, net_foreign=0.0):
    """시장 날씨 판별 — 규칙 기반(예측 아님, 현재 상태 요약)."""
    ks = idx.get("KOSPI") or {}
    chg = ks.get("chg", 0) or 0
    vol = ks.get("vol20", 0) or 0
    adr = breadth["adr"]; upp = breadth["up_pct"]
    panic = chg <= -2.5 and upp < 25
    if panic:
        w = ("⛈", "패닉", "지수 급락에 하락 종목이 압도적입니다. 지금은 방어가 우선입니다.")
    elif chg <= -1.2 and adr < 0.6:
        w = ("🌧", "리스크오프", "위험자산 회피 분위기 — 대부분 종목이 밀리고 있습니다.")
    elif vol >= 28:
        w = ("⚡", "고변동", "변동성이 큰 국면 — 같은 판단이라도 손실 폭이 커질 수 있습니다.")
    elif chg >= 1.2 and adr >= 1.5:
        w = ("☀", "리스크온", "상승 종목이 압도적입니다 — 위험선호 분위기.")
    elif chg >= 0.4 and adr >= 1.1:
        w = ("🌤", "완만한 강세", "지수와 종목 폭이 함께 양호합니다.")
    elif abs(chg) < 0.5 and 0.8 <= adr <= 1.3:
        w = ("🌫", "관망", "방향성이 뚜렷하지 않은 구간입니다.")
    elif chg >= 0 and adr < 0.8:
        w = ("🌪", "순환매", "지수는 버티지만 종목별 온도차가 큽니다 — 자금이 이동 중입니다.")
    else:
        w = ("🌥", "혼조", "뚜렷한 방향 없이 엇갈리는 흐름입니다.")
    return {"icon": w[0], "label": w[1], "desc": w[2],
            "note": "현재 상태 요약이며 앞으로의 방향 예측이 아닙니다."}


def market_pulse(breadth, idx, flows):
    """맥박 게이지 0~100 (해석 가능한 값만)."""
    ks = idx.get("KOSPI") or {}
    # tanh 스케일 — 극단값에서도 포화되지 않고 차이가 보이게
    sq = lambda x, s: 50 + 48 * float(np.tanh(x / s))
    mom = sq(ks.get("ret20", 0) or 0, 12)                       # 20일 지수 모멘텀(±12%≈±36p)
    brd = breadth["up_pct"]                                     # 상승 종목 비율
    vol = ks.get("vol20", 20) or 20
    risk = sq(vol - 18, 14)                                     # 실현변동성(18% 기준)
    net = sum(f["frgn"] + f["org"] for f in flows) if flows else 0
    liq = sq(net, 4000)                                         # 큰손 순매수 억원
    cl = lambda x: int(max(0, min(100, round(x))))
    return [{"k": "모멘텀", "v": cl(mom), "d": "최근 20일 지수 흐름"},
            {"k": "시장폭", "v": cl(brd), "d": "상승 종목 비율(breadth)"},
            {"k": "유동성", "v": cl(liq), "d": "외국인·기관 순매수 방향"},
            {"k": "리스크", "v": cl(risk), "d": "실현 변동성(높을수록 주의)", "inv": True}]


def flow_graph(flows, sectors=None, top=26):
    """투자자 → 섹터 → 종목 자금 경로. 노드/링크(억원)."""
    sectors = sectors or {}
    for f in flows:
        f["sector"] = sectors.get(f["code"], "기타")
    picked = sorted(flows, key=lambda f: -abs(f["frgn"] + f["org"]))[:top]
    sec_agg = {}
    for f in picked:
        s = sec_agg.setdefault(f["sector"], {"frgn": 0.0, "org": 0.0, "indi": 0.0, "names": []})
        s["frgn"] += f["frgn"]; s["org"] += f["org"]; s["indi"] += f.get("indi", 0.0)
        s["names"].append(f["name"])
    sect_nodes = [{"name": k, "frgn": round(v["frgn"], 1), "org": round(v["org"], 1),
                   "indi": round(v["indi"], 1),
                   "sum": round(v["frgn"] + v["org"], 1), "n": len(v["names"])}
                  for k, v in sec_agg.items()]
    sect_nodes.sort(key=lambda x: -abs(x["sum"]))
    links = []
    for s in sect_nodes:
        for who, key in (("외국인", "frgn"), ("기관", "org"), ("개인", "indi")):
            if abs(s.get(key, 0)) >= 1:
                links.append({"from": who, "to": s["name"], "amt": s[key]})
    for f in picked:
        amt = round(f["frgn"] + f["org"], 1)
        if abs(amt) >= 1:
            links.append({"from": f["sector"], "to": f["name"], "amt": amt,
                          "code": f["code"], "chg": f["chg"]})
    return {"sectors": sect_nodes, "links": links,
            "stocks": [{"code": f["code"], "name": f["name"], "sector": f["sector"],
                        "amt": round(f["frgn"] + f["org"], 1), "frgn": f["frgn"],
                        "org": f["org"], "indi": f.get("indi", 0.0),
                        "frgn_pct": f.get("frgn_pct"), "org_pct": f.get("org_pct"),
                        "indi_pct": f.get("indi_pct"), "chg": f["chg"]} for f in picked]}


def whales(flows, threshold=300.0):
    """고래 탐지: |외국인+기관 순매수| ≥ threshold(억원)."""
    out = []
    for f in flows:
        amt = f["frgn"] + f["org"]
        if abs(amt) >= threshold:
            out.append({"code": f["code"], "name": f["name"], "amt": round(amt, 1),
                        "side": "buy" if amt > 0 else "sell", "chg": f["chg"]})
    out.sort(key=lambda x: -abs(x["amt"]))
    return out[:8]


def narrative(weather, breadth, idx, graph, wh):
    """규칙기반 자연어 브리핑 — 계산된 사실만 서술(환각 없음)."""
    ks = idx.get("KOSPI") or {}
    s = []
    s.append(f"코스피 {ks.get('chg',0):+.2f}% · 상승 {breadth['up']}종목 vs 하락 {breadth['down']}종목"
             f"(ADR {breadth['adr']}) — {weather['label']} 국면입니다.")
    secs = graph["sectors"]
    inflow = [x for x in secs if x["sum"] > 0][:2]
    outflow = [x for x in secs if x["sum"] < 0][:2]
    if inflow:
        s.append("자금이 들어오는 곳: " + ", ".join(f"{x['name']}(+{x['sum']:.0f}억)" for x in inflow) + ".")
    if outflow:
        s.append("빠지는 곳: " + ", ".join(f"{x['name']}({x['sum']:.0f}억)" for x in outflow) + ".")
    if wh:
        w = wh[0]
        s.append(f"가장 큰 움직임은 {w['name']} {'순매수' if w['side']=='buy' else '순매도'} "
                 f"{abs(w['amt']):.0f}억입니다.")
    # 주체별 큰 그림 (누가 팔고 누가 받는가)
    tf = sum(x.get("frgn", 0) for x in graph["stocks"])
    to = sum(x.get("org", 0) for x in graph["stocks"])
    ti = sum(x.get("indi", 0) for x in graph["stocks"])
    if abs(tf) + abs(to) > 100:
        who_sell = "외국인" if tf < 0 else ("기관" if to < 0 else None)
        if who_sell and ti > 0:
            s.append(f"큰 그림은 {who_sell}이 내놓는 물량({abs(tf if who_sell=='외국인' else to):,.0f}억)을 "
                     f"개인이 받아내는 구도입니다(개인 추정 +{ti:,.0f}억).")
        else:
            s.append(f"주체별로는 외국인 {tf:+,.0f}억 · 기관 {to:+,.0f}억 · 개인(추정) {ti:+,.0f}억입니다.")
    s.append("수급은 방향을 맞히는 나침반이 아니라 분위기 온도계입니다 — 매수 추천이 아닙니다.")
    return " ".join(s)


def build_flow_os(flows, sectors=None):
    """전체 조립. flows = server /api/flowmap 아이템(억원 환산 완료)."""
    br = market_breadth()
    idx = _index_snapshot()
    g = flow_graph(flows, sectors)
    wh = whales(flows)
    w = market_weather(br, idx)
    return {"weather": w, "breadth": br, "index": idx,
            "pulse": market_pulse(br, idx, flows), "graph": g, "whales": wh,
            "narrative": narrative(w, br, idx, g, wh),
            "caveat": "현재 상태 요약이며 예측이 아닙니다. 수급은 온도계(예측력 약·국면따라 뒤집힘)."}
