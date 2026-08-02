# -*- coding: utf-8 -*-
"""
NAO STOCK — 종합판단 분석기 (KIS 실데이터 → JIQT Evidence 파이프라인)
====================================================================
흐름: KIS 국내 실데이터(시세·일봉·투자자 수급)
      → 지표 계산(추세·모멘텀·변동성·레벨)
      → 표준 Evidence 생성 + ★한투 실수급 Evidence 주입
      → confidence_engine → conflict_resolver(국면 게이트) → verdict_mapper
      → 종합판단(등급·시그널·근거 기여도)

핵심 설계: 아빠차트 지표의 '추정 수급'을 KIS **실수급**으로 대체해 Evidence에 주입.
급등(변동성 급증)은 강세 거부권(모멘텀 크래시 위험, Daniel-Moskowitz)으로 반영.

실행:
  python engine/analyze.py 005930          # KIS 실데이터로 분석(로컬)
  python engine/analyze.py --synth         # 합성 데이터로 파이프라인 자체 테스트
"""
from __future__ import annotations

import sys
import numpy as np

from signal_engine import (Evidence, EvidenceRegistry, recalibrate,
                            resolve, map_verdict)
from entry_timing import entry_assessment


# ── 지표 유틸 ──────────────────────────────────────────────────
def ema(a, n):
    a = np.asarray(a, float)
    k = 2 / (n + 1)
    out = np.empty_like(a)
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = a[i] * k + out[i - 1] * (1 - k)
    return out


def rsi(a, n=14):
    a = np.asarray(a, float)
    d = np.diff(a)
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ru = np.mean(up[:n]) if len(up) >= n else np.mean(up) if len(up) else 0
    rd = np.mean(dn[:n]) if len(dn) >= n else np.mean(dn) if len(dn) else 0
    for i in range(n, len(d)):
        ru = (ru * (n - 1) + up[i]) / n
        rd = (rd * (n - 1) + dn[i]) / n
    if rd == 0:
        return 100.0
    return 100 - 100 / (1 + ru / rd)


def atr(h, l, c, n=14):
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-n:])) if len(tr) >= 1 else 0.0


def efficiency_ratio(c, n=20):
    c = np.asarray(c, float)
    if len(c) <= n:
        return 0.0
    change = abs(c[-1] - c[-n])
    vol = np.sum(np.abs(np.diff(c[-n:])))
    return float(change / vol) if vol else 0.0


def monte_carlo(c, steps=20, paths=2000, mean_block=10):
    """Stationary bootstrap (Politis-Romano) — 전문가 H-84/85/86 교정.
    고정 블록=5 폐기: 기하분포 랜덤 블록(평균 10)로 변동성 군집을 더 보존,
    경로 2000+로 꼬리(q10/q90) 안정화. 용도: 리스크 시각화 전용(판단 미사용)."""
    c = np.asarray(c, float)
    if paths <= 0 or len(c) < 30:              # paths<=0: 검증 하네스용 MC 생략(H-90, 판단 미사용)
        return {"prob_up": 50.0, "q10": float(c[-1]), "q50": float(c[-1]),
                "q90": float(c[-1])}
    r = np.diff(np.log(c))
    n = len(r)
    px0 = float(c[-1])
    rng = np.random.default_rng(7)
    p_restart = 1.0 / mean_block
    term = np.empty(paths)
    for p in range(paths):
        acc = 0.0
        i = int(rng.integers(0, n))
        for _ in range(steps):
            acc += r[i]
            if rng.random() < p_restart:
                i = int(rng.integers(0, n))       # 새 블록 시작
            else:
                i = (i + 1) % n                    # 블록 이어가기(원형)
        term[p] = px0 * np.exp(acc)
    return {"prob_up": float(np.mean(term > px0) * 100),
            "q10": float(np.percentile(term, 10)),
            "q50": float(np.percentile(term, 50)),
            "q90": float(np.percentile(term, 90))}


def key_levels(h, l, c):
    """키레벨(Pine ⑧-2b 이식): 피벗(전일 HLC) · 전주/전월 고저 · 1년 고저."""
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    ph, pl, pc = float(h[-2]), float(l[-2]), float(c[-2])   # 전일
    pp = (ph + pl + pc) / 3
    out = {"pp": round(pp), "r1": round(2 * pp - pl), "s1": round(2 * pp - ph),
           "y_hi": round(float(np.max(h[-252:]))), "y_lo": round(float(np.min(l[-252:])))}
    if len(h) > 6:
        out["pw_hi"] = round(float(np.max(h[-6:-1])))   # 전주(직전 5봉) 고
        out["pw_lo"] = round(float(np.min(l[-6:-1])))
    if len(h) > 21:
        out["pm_hi"] = round(float(np.max(h[-21:-1])))  # 전월(직전 20봉) 고
        out["pm_lo"] = round(float(np.min(l[-21:-1])))
    return out


# 전문가 L-128: 지시형("사세요/파세요") 제거 → 관찰 서술. 매매 판단은 사용자 몫.
_PLAIN = {
    "STRONG BUY": "여러 지표가 긍정적 신호를 보이고 있습니다.",
    "BUY": "지표가 대체로 긍정적입니다.",
    "TACTICAL BUY": "긍정 신호와 위험 신호가 함께 관찰됩니다.",
    "HOLD": "뚜렷한 방향이 관찰되지 않습니다.",
    "REDUCE": "약세 신호가 관찰됩니다.",
    "SELL": "약세 신호가 뚜렷합니다. 원금 보호를 먼저 생각할 구간입니다.",
    "MIXED": "신호가 엇갈립니다. 판단을 유보할 구간입니다.",
}


def simple3(signal):
    """전문가 A-11/L: 초보자 노출은 3단계로 (내부 7단계는 유지·상세보기용)."""
    if "BUY" in signal and "TACTICAL" not in signal:
        return "긍정 관찰"
    if "SELL" in signal or "REDUCE" in signal:
        return "주의"
    return "중립"


def plain_verdict(signal):
    for k, v in _PLAIN.items():
        if signal.startswith(k):
            return v
    return "판단 근거를 함께 확인하세요."


def _rma(x, n):
    x = np.asarray(x, float)
    r = np.empty(len(x))
    if len(x) == 0:
        return r
    r[0] = x[0]
    a = 1.0 / n
    for i in range(1, len(x)):
        r[i] = r[i - 1] * (1 - a) + x[i] * a
    return r


def adx(h, l, c, n=14):
    """Wilder ADX(1978) — 추세 '강도'(0~100). 방향 무관."""
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    if len(c) < n + 2:
        return 0.0
    up = h[1:] - h[:-1]
    dn = l[:-1] - l[1:]
    pDM = np.where((up > dn) & (up > 0), up, 0.0)
    mDM = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr = _rma(tr, n)
    atr = np.where(atr == 0, 1e-9, atr)
    pdi = 100 * _rma(pDM, n) / atr
    mdi = 100 * _rma(mDM, n) / atr
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, 1e-9, pdi + mdi)
    return float(_rma(dx, n)[-1])


def hurst(c, maxlag=40):
    """Hurst 지수 — 추세 지속성. >0.5 지속, 0.5 랜덤, <0.5 평균회귀 (분산법)."""
    c = np.asarray(c, float)
    if len(c) < 30:
        return 0.5
    lags = range(2, min(maxlag, len(c) // 2))
    tau = []
    for lag in lags:
        d = c[lag:] - c[:-lag]
        tau.append(max(np.std(d), 1e-9))
    poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
    return float(np.clip(poly[0], 0.0, 1.0))


def _tf_state(adxv, h):
    """전문가 C-28/29: Hurst는 표본<200이면 점추정 금지 → h=None이면 ADX 단독 분류."""
    if h is None:
        if adxv > 25:
            return "STRONG_TREND", "강한추세"
        if adxv < 20:
            return "RANGE", "레인지"
        return "TRANSITION", "전환구간"
    if adxv > 25 and h > 0.55:
        return "STRONG_TREND", "강한추세"
    if adxv < 20 and h < 0.50:
        return "RANGE", "레인지"
    return "TRANSITION", "전환구간"


def _resample(o, h, l, c, v, k):
    O = []; H = []; L = []; C = []; V = []
    n = len(c)
    for i in range(0, n, k):
        j = min(i + k, n)
        O.append(o[i]); H.append(max(h[i:j])); L.append(min(l[i:j]))
        C.append(c[j - 1]); V.append(sum(v[i:j]))
    return O, H, L, C, V


def tf_recommendation(o, h, l, c, v, wk=None):
    """연구 문서(3장) 이식 + 전문가 교정(C-27/28):
    주봉 ADX는 KIS 실제 주봉(wk)으로 직접 계산(리샘플 폐기), 14주 미만이면 표본부족 명시.
    Hurst는 표본<200이면 점추정 금지 → ADX 단독 분류."""
    a20 = atr(h, l, c, 20)
    a120 = atr(h, l, c, min(120, len(c) - 1))
    rshift = a20 / a120 if a120 else 1.0
    # 일봉
    dAdx = adx(h, l, c)
    dH = hurst(c) if len(c) >= 200 else None
    dState, dLbl = _tf_state(dAdx, dH)
    # 주봉 — 실제 주봉 데이터 우선 (전문가 C-27)
    wnote = ""
    if wk and len(wk.get("close", [])) >= 15:
        wh2, wl2, wc2 = wk["high"], wk["low"], wk["close"]
        wAdx = adx(wh2, wl2, wc2)
        wH = hurst(wc2) if len(wc2) >= 200 else None
        wsrc = f"주봉 실데이터 {len(wc2)}주"
    else:
        wo, wh2, wl2, wc2, wv2 = _resample(o, h, l, c, v, 5)
        wAdx = adx(wh2, wl2, wc2)
        wH = None
        wsrc = f"리샘플 {len(wc2)}주"
        wnote = " ⚠표본부족"
    wState, wLbl = _tf_state(wAdx, wH)
    # 판단축: 상위(주봉)부터 STRONG_TREND 확인
    if wState == "STRONG_TREND":
        judge, entry = "주봉", "일봉"
    elif dState == "STRONG_TREND":
        judge, entry = "일봉", ("일봉" if rshift < 1.3 else "60분봉")
    else:
        judge, entry = "일봉", ("60분봉" if rshift >= 1.3 else "일봉")
    mode = "추세추종" if (wState == "STRONG_TREND" or dState == "STRONG_TREND") \
        else "레인지·평균회귀"
    trend_tf = "월봉" if judge == "주봉" else "주봉"
    hs = lambda x: f"·H {x:.2f}" if x is not None else "·H 표본부족"
    reason = (f"주봉 {wLbl}(ADX {wAdx:.0f}{hs(wH)}·{wsrc}{wnote}) · "
              f"일봉 {dLbl}(ADX {dAdx:.0f}{hs(dH)}) · "
              f"국면전환 {rshift:.2f}" + ("(의심)" if rshift >= 1.3 else "(정상)"))
    return {"mode": mode, "judge": judge, "entry": entry, "trend": trend_tf,
            "stack": f"방향 {trend_tf} → 판단 {judge} → 진입 {entry}",
            "d_adx": round(dAdx, 1), "d_hurst": round(dH, 2) if dH else None,
            "w_adx": round(wAdx, 1), "w_hurst": round(wH, 2) if wH else None,
            "regime_shift": round(rshift, 2), "reason": reason,
            "d_state": dLbl, "w_state": wLbl}


def rsi_series(c, n=14):
    c = np.asarray(c, float)
    out = np.full(len(c), 50.0)
    if len(c) < n + 1:
        return out
    d = np.diff(c)
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ru = np.mean(up[:n]); rd = np.mean(dn[:n])
    for i in range(n, len(c)):
        ru = (ru * (n - 1) + up[i - 1]) / n
        rd = (rd * (n - 1) + dn[i - 1]) / n
        out[i] = 100.0 if rd == 0 else 100 - 100 / (1 + ru / rd)
    return out


def signals(ohlc):
    """레짐 적응 매수·매도 참고 신호(Pine ⑥ 이식): 눌림목 / 과매도·과열."""
    o = np.asarray(ohlc["open"], float); c = np.asarray(ohlc["close"], float)
    h = np.asarray(ohlc["high"], float); l = np.asarray(ohlc["low"], float)
    if len(c) < 60:
        return []
    e20 = ema(c, 20); e60 = ema(c, 60); e120 = ema(c, min(120, len(c) - 1))
    rs = rsi_series(c, 2)
    out = []
    for i in range(2, len(c)):
        if c[i] > e60[i] and l[i] <= e20[i] and c[i] > e20[i] and c[i] > o[i]:
            out.append({"i": i, "type": "buy", "why": "눌림목"})
        elif rs[i] < 10 and c[i] > e120[i]:
            out.append({"i": i, "type": "buy", "why": "과매도"})
        elif c[i] < e60[i] and h[i] >= e20[i] and c[i] < e20[i] and c[i] < o[i]:
            out.append({"i": i, "type": "sell", "why": "반등소진"})
        elif rs[i] > 90 and c[i] < e120[i]:
            out.append({"i": i, "type": "sell", "why": "과열"})
    return out[-14:]


def market_state(ohlc):
    """시장 상태(Pine ④): 추세장(상승/하락) / 횡보장."""
    c = np.asarray(ohlc["close"], float)
    h = np.asarray(ohlc["high"], float); l = np.asarray(ohlc["low"], float)
    e20 = ema(c, 20); e60 = ema(c, min(60, len(c) - 1))
    e120 = ema(c, min(120, len(c) - 1))
    trending = adx(h, l, c) > 22 or efficiency_ratio(c) > 0.35
    up = e20[-1] > e60[-1] > e120[-1]
    dn = e20[-1] < e60[-1] < e120[-1]
    if trending and up:
        return "추세장 (상승) 🌊"
    if trending and dn:
        return "추세장 (하락) 🌊"
    return "횡보장 (박스권) ↔"


def divergence(c):
    """다이버전스(Pine ⑦): 가격과 RSI 방향 어긋남 = 추세 약화 경고."""
    c = np.asarray(c, float)
    if len(c) < 24:
        return {"type": "none", "text": "없음"}
    ra = rsi_series(c, 14)
    w = c[-20:]; rw = ra[-20:]
    i1 = int(np.argmax(w[:10])); i2 = 10 + int(np.argmax(w[10:]))
    if w[i2] > w[i1] and rw[i2] < rw[i1] - 2:
        return {"type": "bear", "text": "고점 힘 빠짐 (가격↑·RSI↓)"}
    j1 = int(np.argmin(w[:10])); j2 = 10 + int(np.argmin(w[10:]))
    if w[j2] < w[j1] and rw[j2] > rw[j1] + 2:
        return {"type": "bull", "text": "저점 힘 붙음 (가격↓·RSI↑)"}
    return {"type": "none", "text": "없음"}


def category_consensus(evs):
    """카테고리별 신뢰도가중 투표(Pine 합의도 이식). 상관 이중계산 회피."""
    by = {}
    for e in evs:
        if e.veto:
            continue
        by.setdefault(e.category, 0.0)
        by[e.category] += e.signed_strength
    cats = []
    bull = bear = 0
    for name, s in sorted(by.items(), key=lambda x: -abs(x[1])):
        d = 1 if s > 0.03 else -1 if s < -0.03 else 0
        if d > 0:
            bull += 1
        elif d < 0:
            bear += 1
        cats.append({"name": name, "dir": d, "score": round(s, 2)})
    diff = abs(bull - bear)
    txt = ("강한 합의" if diff >= 3 else "우세" if diff >= 2 else "혼조")
    lead = "매수" if bull > bear else "매도" if bear > bull else ""
    return {"categories": cats, "bull": bull, "bear": bear,
            "text": (lead + " " + txt) if lead else "혼조 (관망)"}


# ── 분석 코어 ─────────────────────────────────────────────────
def analyze(quote: dict, ohlc: dict, flow: dict,
            mc_paths: int = 500, mc_steps: int = 20, wk_ohlc: dict = None) -> dict:
    """
    quote: {price, change_pct, ...}
    ohlc : {open,high,low,close,volume} 각 리스트(과거→현재)
    flow : {foreign_5d, org_5d, foreign_dir, org_dir}  (KIS 실수급)
    """
    c = np.asarray(ohlc["close"], float)
    h = np.asarray(ohlc["high"], float)
    l = np.asarray(ohlc["low"], float)
    px = float(quote.get("price", c[-1]))
    reg = EvidenceRegistry(scope=quote.get("code", ""))

    e20, e60 = ema(c, 20), ema(c, min(60, len(c) - 1))
    e120 = ema(c, min(120, len(c) - 1))
    slope = (e20[-1] / e20[-6] - 1) * 100 if len(e20) > 6 else 0.0
    er = efficiency_ratio(c)
    a = atr(h, l, c)
    r = rsi(c)
    hi52 = float(np.max(h[-252:])) if len(h) else px
    lo52 = float(np.min(l[-252:])) if len(l) else px
    ret20 = (c[-1] / c[-21] - 1) * 100 if len(c) > 21 else 0.0
    volp = a / px * 100 if px else 0.0

    # ── 국면(레짐) ──
    trending = er > 0.35 or abs(slope) > 3
    regime_state = "stable" if trending else "transition"

    # 종목 적합성 게이트 (검증결과 반영: NAVER·카카오형 비추세 종목에서 신호 무정보~역정보)
    # 전문가 C-30/D-49/G-83: 추세성 낮은 종목엔 판단 유보가 최선의 서비스
    adx_d = adx(h, l, c)
    suitable = adx_d >= 18 or er > 0.35

    # ── 증거 생성 ──
    # 추세 블록 (전문가 A-3/C-31: 배열·기울기·ADX·효율비는 동일 정보 → 대표 1개만)
    d_tr = 1 if e20[-1] > e60[-1] else -1
    tmag = max(min(1, abs(e20[-1] - e60[-1]) / (a + 1e-9)),
               min(1, abs(slope) / 5))
    reg.add(Evidence("trend_block", d_tr, tmag, 0.65, category="추세",
                     rationale=("정배열(20>60)" if d_tr > 0 else "역배열(20<60)")
                               + f" · 기울기 {slope:+.1f}%"))

    # 모멘텀: RSI (+극단 과매수 거부권)
    if r >= 70:
        reg.add(Evidence("rsi", -1, min(1, (r-70)/30), 0.6, category="모멘텀",
                         rationale=f"RSI {r:.0f} 과매수"))
        if r >= 80:
            reg.add(Evidence("rsi_veto", -1, 1.0, 0.7, category="모멘텀",
                             veto=True, veto_target=1,
                             rationale=f"RSI {r:.0f} 극단 과매수 → 강세 강등"))
    elif r <= 30:
        reg.add(Evidence("rsi", 1, min(1, (30-r)/30), 0.55, category="모멘텀",
                         rationale=f"RSI {r:.0f} 과매도 → 반등 가능"))
    else:
        reg.add(Evidence("rsi", 0, 0.2, 0.4, category="모멘텀",
                         rationale=f"RSI {r:.0f} 중립"))

    # 52주 신고가 근접 (George-Hwang 2004)
    prox = px / hi52 if hi52 else 0
    if prox >= 0.95:
        reg.add(Evidence("high52", 1, min(1, (prox-0.9)/0.1), 0.6,
                         category="모멘텀",
                         rationale=f"52주 신고가 {(prox-1)*100:+.0f}% 근접(장기 미반전)"))

    # ★ KIS 실수급 Evidence (외국인·기관) — 전문가 교정:
    #  F-64: 절대수량 대신 평균거래량 대비 비율로 표준화 (종목 간 비교가능)
    #  F-68: 수급은 가격모멘텀과 상관(양의 피드백) → 추세와 방향 일치 시 conf ×0.85 할인
    #  F-62: 예측력은 국면의존적('나침반이 아니라 온도계') → conf 상한 0.65로 하향
    f5, o5 = flow.get("foreign_5d", 0), flow.get("org_5d", 0)
    avg_vol = float(np.mean(np.asarray(ohlc["volume"], float)[-20:])) or 1.0
    def _flow_mag(x):
        return float(min(1.0, abs(x) / (5 * avg_vol) * 20))   # 5일합/5일평균거래량 비율 스케일
    for src, val, who in (("flow_foreign", f5, "외국인"), ("flow_org", o5, "기관")):
        if not val:
            continue
        d = 1 if val > 0 else -1
        conf = 0.65 if src == "flow_foreign" else 0.62
        note = ""
        if d == d_tr:                      # 추세와 같은 방향 = 정보 일부 중복
            conf *= 0.85
            note = "·추세와 동방향(중복 할인)"
        reg.add(Evidence(src, d, _flow_mag(val), conf, category="수급",
                         rationale=f"{who} 5일 {val:+,.0f} [KIS]{note}"))

    # 급등 → 모멘텀 크래시 거부권 (Daniel-Moskowitz 2016)
    # 전문가 G-77: 종목 과열 + '시장 레짐'(하락 후 고변동 반등기) 조건 결합
    surge = ret20 > 60 and volp > 4
    mkt = quote.get("_mkt_closes")             # 서버가 넣어주는 KOSPI 종가 시계열(선택)
    mkt_panic = False
    if mkt is not None and len(mkt) > 40:
        m = np.asarray(mkt, float)
        mret60 = m[-1] / m[0] - 1
        mvol = float(np.std(np.diff(np.log(m))[-20:]) * np.sqrt(252))
        mkt_panic = mret60 < 0 and mvol > 0.25   # 시장 하락 + 고변동 = DM 크래시 국면
    if surge:
        conf = 0.75 if mkt_panic else 0.6
        why = "시장 패닉국면 동반" if mkt_panic else "종목 과열"
        reg.add(Evidence("surge_crash_veto", -1, 1.0, conf, category="시나리오",
                         veto=True, veto_target=1,
                         rationale=f"20일 {ret20:+.0f}% 급등·고변동({why}) → 크래시 위험, 강세 강등"))

    # 몬테카를로 — 전문가 H-90/M-138: 판단 Evidence에서 제거(가격→확률→가격 순환논리).
    # 리스크 시각화 전용(q10 손실각오)으로만 사용. 확률 %는 캘리브레이션 검증 전 비노출.
    mc = monte_carlo(c, steps=int(mc_steps), paths=int(mc_paths))

    # ── 파이프라인 ──
    ctx = {"data_confidence": "high",           # KIS 실데이터
           "sample_enough": len(c) >= 120, "ml_accuracy": None}
    evs = recalibrate(reg.items, ctx)
    resolved = resolve(evs, regime_state=regime_state)
    verdict = map_verdict(resolved)

    stop = px - a * 3
    verdict["plain"] = plain_verdict(verdict["signal"])
    verdict["simple3"] = simple3(verdict["signal"])
    if not suitable:                            # 적합성 게이트: 비추세 종목 → 판단 유보
        verdict["simple3"] = "중립"
        verdict["plain"] = (f"이 종목은 현재 추세성이 낮아(ADX {adx_d:.0f}) 판단을 "
                            "유보합니다. 비추세 구간에서는 신호 신뢰도가 낮습니다(검증 결과).")
        verdict["gated"] = True

    # 전문가 A-2: 로그오즈 결합(내부·검증용, UI 비노출 — 캘리브레이션 B-24 전까지)
    # 각 증거의 signed_strength를 소규모 LLR 근사로 보고 합산 → 확률 해석 가능 출력
    llr = sum(e.signed_strength for e in evs if not e.veto) * 1.5
    prob_up_raw = float(1 / (1 + np.exp(-llr)))
    return {
        "code": quote.get("code", ""), "price": px,
        "change_pct": quote.get("change_pct", 0.0),
        "verdict": verdict, "resolved": resolved,
        "regime": regime_state, "rsi": round(r, 1),
        "er": round(er, 2), "vol_pct": round(volp, 2),
        "ret20": round(ret20, 1), "high52": hi52, "low52": lo52,
        "stop": round(stop, 0), "surge": bool(surge),
        "mc": mc, "keylevels": key_levels(h, l, c),
        "tf_reco": tf_recommendation(
            ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"], ohlc["volume"],
            wk=wk_ohlc),
        "consensus": category_consensus(evs),
        "entry": entry_assessment(c, h, rsi_val=r, flow=flow, mc=mc, price=px),   # ⭐진입 적정도 + 수급온도계·리스크
        "prob_up_raw": round(prob_up_raw, 4),   # 미캘리브레이션 — validate.py 전용
        "evidence": {e.source: e.direction * e.magnitude for e in evs},  # 원시 증거값(primitive-discovery J-118)
        "signals": signals(ohlc),
        "market_state": market_state(ohlc),
        "divergence": divergence(c),
        "contributions": resolved.get("contributions", []),
    }


def _print(res: dict):
    v = res["verdict"]
    print(f"\n{'='*54}")
    print(f" 종목 {res['code']}  현재가 {res['price']:,.0f}  ({res['change_pct']:+.2f}%)")
    print(f" 국면 {res['regime']} · RSI {res['rsi']} · 효율비 {res['er']} · 변동성 {res['vol_pct']}%")
    print(f"{'='*54}")
    print(f" 종합판단  {v['grade']}  ·  {v['signal']}  (점수 {v['score']})")
    print(f"   {v['verdict']}")
    if v.get("ceiling_notes"):
        print("   ⚠ " + " / ".join(v["ceiling_notes"]))
    print(f" net_score {res['resolved']['net_score']:+.2f} · "
          f"충돌 {res['resolved']['conflict_ratio']} · "
          f"거부권 {res['resolved'].get('blocked_dirs')}")
    print(" 판단 근거 Top:")
    for src, s, rat, cat in res["contributions"][:6]:
        print(f"   [{cat}] {src} {s:+.3f} — {rat}")
    print(f" 손절 참고선 {res['stop']:,.0f}\n")


def _synth_flow():
    return {"foreign_5d": -246017, "org_5d": -587661,
            "foreign_dir": "순매도", "org_dir": "순매도"}


if __name__ == "__main__":
    if "--synth" in sys.argv:
        # 파이프라인 자체 검증 (하락 추세 + 실제 수급 -,- 로 약세 판정 기대)
        np.random.seed(1)
        c = np.cumsum(np.random.randn(200) * 2 - 0.6) + 300
        c = np.maximum(c, 50) * 900
        ohlc = {"close": c.tolist(), "high": (c*1.01).tolist(),
                "low": (c*0.99).tolist(), "open": c.tolist(),
                "volume": (np.random.rand(200)*1e6).tolist()}
        quote = {"code": "005930", "price": float(c[-1]), "change_pct": -8.77}
        _print(analyze(quote, ohlc, _synth_flow()))
    else:
        code = sys.argv[1] if len(sys.argv) > 1 else "005930"
        from kis_kr import KISKorea
        kis = KISKorea()
        q = kis.quote(code)
        df = kis.daily_ohlcv(code, 200)
        ohlc = {k: df[k].tolist() for k in ("open", "high", "low", "close", "volume")}
        fl = kis.investor_flow(code)
        _print(analyze(q, ohlc, fl))
