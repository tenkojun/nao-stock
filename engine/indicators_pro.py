# -*- coding: utf-8 -*-
"""
논문 근거 인디케이터 엔진 (Evidence-graded)
============================================
2026-07 리서치 기반. 각 지표에 **증거 등급**을 붙여 정직하게 노출한다.

  [A] 강한 실증 근거 — 다수 피어리뷰·재현
      · HAR-RV 변동성 예측 (Corsi 2009, J.Fin.Econometrics; 2100+ 인용.
        GARCH·ARFIMA 대비 우수, 변동성 예측의 표준 벤치마크)
      · 오더플로우 불균형 OFI (Cont-Kukanov-Stoikov 2014, J.Fin.Econometrics.
        단기 가격변화와 선형관계, 기울기 ∝ 1/시장깊이. 종목·시간축 걸쳐 안정)
      · Amihud 비유동성 (Amihud 2002, J.Fin.Markets. 거래대금당 가격충격)
  [B] 실무 표준이나 예측력 논쟁 — 참고용
      · VWAP (Berkowitz-Logue-Noser 1988): 집행 품질 '벤치마크'로 도입된 것이지
        예측 지표가 아님. 앵커드 VWAP은 실무 관찰뿐(학술 재현 부족).
      · Volume Profile / POC: Market Profile 관행, 학술 검증 빈약.
      · VPIN (Easley-LdP-O'Hara 2012)은 Andersen-Bondarenko(2014)가 반박 — 미채택.
  [C] 약한 근거 — 비용 반영 시 소멸 경향
      · 고전 TA 규칙 전반 (Park & Irwin 2007 리뷰: 현대연구 95편 중 56편 양(+)이나
        데이터스누핑·사후선택 문제, 시간이 갈수록 수익 감소, 손익분기비용 0.22~0.39%)
"""
from __future__ import annotations
import numpy as np

EVIDENCE = {
    "har_rv": ("A", "A Simple Long Memory Model of Realized Volatility", "Corsi (2009)",
               "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=626064"),
    "ofi": ("A", "The Price Impact of Order Book Events", "Cont, Kukanov & Stoikov (2014)",
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712822"),
    "amihud": ("A", "Illiquidity and Stock Returns", "Amihud (2002)",
               "https://doi.org/10.1016/S1386-4181(01)00024-6"),
    "vwap": ("B", "The Total Cost of Transactions on the NYSE (VWAP 도입)",
             "Berkowitz, Logue & Noser (1988)", "https://doi.org/10.1111/j.1540-6261.1988.tb04593.x"),
    "vp": ("B", "Market Profile / Volume at Price (실무 관행)", "CME 교육자료",
           "https://www.cmegroup.com/education.html"),
    "ta": ("C", "What Do We Know About the Profitability of Technical Analysis?",
           "Park & Irwin (2007)", "https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-6419.2007.00519.x"),
}


# ── [A] HAR-RV 변동성 예측 ─────────────────────────────────────────
def _rv_parkinson(h, l):
    """Parkinson 범위기반 일간 실현변동성 추정(종가-종가보다 효율적)."""
    h = np.asarray(h, float); l = np.asarray(l, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log(np.where(l > 0, h / l, 1.0))
    return np.nan_to_num(r ** 2 / (4 * np.log(2)))       # 일간 분산


def har_rv_forecast(high, low, close, horizon=20):
    """Corsi(2009) HAR: RV_{t+1} = b0 + b_d·RV_d + b_w·RV_w + b_m·RV_m (OLS).
    반환: {sigma_1d, sigma_h, band_lo, band_hi, r2, horizon} — 1일·h일 예상 변동성(%)."""
    c = np.asarray(close, float)
    rv = _rv_parkinson(high, low)
    n = len(rv)
    if n < 60:
        return None
    rv_d = rv.copy()
    rv_w = np.convolve(rv, np.ones(5) / 5, mode="full")[:n]
    rv_m = np.convolve(rv, np.ones(22) / 22, mode="full")[:n]
    X, y = [], []
    for t in range(22, n - 1):
        X.append([1.0, rv_d[t], rv_w[t], rv_m[t]])
        y.append(rv[t + 1])
    if len(y) < 30:
        return None
    X = np.asarray(X); y = np.asarray(y)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = float(np.dot([1.0, rv_d[-1], rv_w[-1], rv_m[-1]], beta))
    pred = max(pred, 1e-8)
    yhat = X @ beta
    ss = float(np.sum((y - yhat) ** 2)); st = float(np.sum((y - y.mean()) ** 2)) or 1.0
    sig1 = float(np.sqrt(pred))                          # 1일 변동성(로그수익 표준편차)
    sigh = sig1 * np.sqrt(horizon)                       # h일 스케일
    px = float(c[-1])
    return {"sigma_1d": round(sig1 * 100, 2), "sigma_h": round(sigh * 100, 2),
            "band_lo": int(px * np.exp(-1.28 * sigh)),   # ≈하위 10%
            "band_hi": int(px * np.exp(1.28 * sigh)),
            "r2": round(1 - ss / st, 3), "horizon": horizon,
            "evidence": EVIDENCE["har_rv"]}


# ── [A] 오더플로우 불균형 (OHLCV 대용치) ───────────────────────────
def ofi_proxy(bars, window=12):
    """Cont-Kukanov-Stoikov의 OFI 개념을 OHLCV 바에 적용한 대용치.
    봉 내 종가 위치로 매수/매도 체결 비중을 추정(Chaikin money-flow multiplier)해
    부호화 거래량을 누적. ⚠ 진짜 호가창 이벤트가 아니므로 '대용치'로 표기."""
    if not bars or len(bars) < 3:
        return None
    sv = []
    for b in bars:
        rng = (b["high"] - b["low"]) or 1e-9
        mult = ((b["close"] - b["low"]) - (b["high"] - b["close"])) / rng   # -1~+1
        sv.append(mult * b["volume"])
    sv = np.asarray(sv, float)
    cum = np.cumsum(sv)
    recent = float(sv[-window:].sum())
    tot = float(np.abs(sv[-window:]).sum()) or 1.0
    return {"cum": [int(x) for x in cum], "recent": int(recent),
            "imbalance_pct": round(recent / tot * 100, 1),
            "evidence": EVIDENCE["ofi"]}


# ── [A] Amihud 비유동성 ────────────────────────────────────────────
def amihud_illiquidity(close, volume, window=60):
    """ILLIQ = mean(|일간수익률| / 거래대금). 높을수록 소액에도 가격이 크게 흔들림."""
    c = np.asarray(close, float); v = np.asarray(volume, float)
    if len(c) < window + 2:
        return None
    r = np.abs(np.diff(np.log(np.maximum(c, 1e-9))))[-window:]
    val = (c[1:] * v[1:])[-window:]                       # 거래대금(원)
    with np.errstate(divide="ignore", invalid="ignore"):
        il = np.where(val > 0, r / val, np.nan)
    m = float(np.nanmean(il)) * 1e14                      # 스케일 조정(대형주≈0.x, 소형주≫)
    lvl = "높음(주의)" if m > 20 else "보통" if m > 4 else "낮음(양호)"
    return {"illiq": round(m, 2), "level": lvl,
            "note": "값이 클수록 적은 금액에도 가격이 크게 밀립니다(체결 불리·슬리피지 위험).",
            "evidence": EVIDENCE["amihud"]}


# ── VWAP (등급 B — 집행 벤치마크) ──────────────────────────────────
def vwap_bands(high, low, close, volume, window=20):
    """세션/기간 VWAP과 ±1σ 밴드. 예측 지표가 아니라 '기관 평균 체결가' 기준선."""
    h = np.asarray(high, float)[-window:]; l = np.asarray(low, float)[-window:]
    c = np.asarray(close, float)[-window:]; v = np.asarray(volume, float)[-window:]
    if len(c) < 5 or v.sum() <= 0:
        return None
    tp = (h + l + c) / 3
    vw = float((tp * v).sum() / v.sum())
    var = float((v * (tp - vw) ** 2).sum() / v.sum())
    sd = float(np.sqrt(max(var, 0)))
    return {"vwap": int(vw), "upper": int(vw + sd), "lower": int(vw - sd),
            "evidence": EVIDENCE["vwap"]}


def analyze_pro(high, low, close, volume, horizon=20):
    """일봉용 논문 근거 지표 묶음."""
    return {
        "har": har_rv_forecast(high, low, close, horizon),
        "amihud": amihud_illiquidity(close, volume),
        "vwap": vwap_bands(high, low, close, volume),
        "grade_note": ("A=강한 실증 근거 · B=실무 표준이나 예측력 논쟁 · C=약함(비용 반영 시 소멸). "
                       "고전 기술적 지표 다수는 C입니다(Park & Irwin 2007)."),
    }
