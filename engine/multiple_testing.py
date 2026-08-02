# -*- coding: utf-8 -*-
"""
다중검정 보정 (자문 A-10) — BH-FDR + Deflated Sharpe Ratio
==========================================================
자문 지시 그대로:
  · **Bonferroni는 쓰지 말 것** — 검정들이 강하게 상관(같은 데이터·겹치는 지평)이라 과도하게 보수적.
  · **BH-FDR(Benjamini-Hochberg)**: 요인×지평 격자(수십 셀)에 적합. "이걸 먼저 하십시오."
  · **DSR(Bailey & López de Prado 2014)**: 전략 Sharpe에 적용. 입력은 **시도 횟수 N**.
    정확한 N을 몰라도 됨 — **N=10과 N=200을 둘 다 보고**해 두 경우 모두 탈락하면 논쟁 종료.

실행: python engine/multiple_testing.py            (docs/요인IC_*.json 자동 탐색)
"""
from __future__ import annotations
import glob
import json
import math
import os
import sys

_EULER = 0.5772156649


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p):
    """역정규분포 근사(Acklam). p∈(0,1)."""
    if p <= 0 or p >= 1:
        return float("inf") if p >= 1 else float("-inf")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def p_from_t(t):
    """양측 p값(정규 근사)."""
    return 2.0 * (1.0 - _norm_cdf(abs(float(t))))


def bh_fdr(pvals, q=0.10):
    """Benjamini-Hochberg. 반환: (기각 여부 리스트, 임계 p)."""
    m = len(pvals)
    if m == 0:
        return [], 0.0
    order = sorted(range(m), key=lambda i: pvals[i])
    thresh = 0.0
    k = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            thresh = q * rank / m
            k = rank
    rej = [False] * m
    for rank, i in enumerate(order, start=1):
        if rank <= k:
            rej[i] = True
    return rej, thresh


def expected_max_sharpe(n_trials, var_sr):
    """N번 시도했을 때 기대되는 '우연의 최고 Sharpe'(Bailey-LdP)."""
    if n_trials <= 1 or var_sr <= 0:
        return 0.0
    sd = math.sqrt(var_sr)
    a = _norm_ppf(1.0 - 1.0 / n_trials)
    b = _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    return sd * ((1 - _EULER) * a + _EULER * b)


def dsr(sr_obs, n_obs, n_trials, var_sr=0.25 ** 2, skew=0.0, kurt=3.0):
    """Deflated Sharpe Ratio. sr_obs·n_obs는 **같은 주기**(예: 연 Sharpe면 n_obs=연수 아님 —
    여기서는 관측 수익 개수). 반환 확률이 0.95 이상이어야 '우연이 아님'."""
    sr_star = expected_max_sharpe(n_trials, var_sr)
    denom = math.sqrt(max(1e-12, 1 - skew * sr_obs + (kurt - 1) / 4.0 * sr_obs ** 2))
    z = (sr_obs - sr_star) * math.sqrt(max(1, n_obs - 1)) / denom
    return _norm_cdf(z), sr_star


def analyze_grid(path, q=0.10):
    with open(path, encoding="utf-8") as fp:
        d = json.load(fp)
    cells = [c for c in d["cells"] if c.get("t") is not None]
    pv = [p_from_t(c["t"]) for c in cells]
    rej, thr = bh_fdr(pv, q)
    for c, p, r in zip(cells, pv, rej):
        c["p"], c["fdr_pass"] = p, r
    cells.sort(key=lambda c: c["p"])
    return d, cells, thr


def report(path, q=0.10):
    d, cells, thr = analyze_grid(path, q)
    tag = "상폐 포함" if d["tag"] == "with_delisted" else "생존 대형주만"
    print("\n" + "=" * 72)
    print(f" 다중검정 보정 (BH-FDR {int(q*100)}%) — 표본: {tag} · 셀 {len(cells)}개 · 패널 {d['n_rows']:,}행")
    print("=" * 72)
    print(f"  {'요인':<20}{'지평':>6}{'IC':>10}{'t':>8}{'p':>9}   판정")
    print("  " + "-" * 64)
    for c in cells[:14]:
        mark = "✅ 생존" if c["fdr_pass"] else "—"
        print(f"  {c['factor']:<20}{c['h']:>6}{c['ic']:>+10.4f}{c['t']:>+8.2f}{c['p']:>9.4f}   {mark}")
    n_pass = sum(1 for c in cells if c["fdr_pass"])
    n_naive = sum(1 for c in cells if abs(c["t"]) >= 2)
    print(f"\n  단순 |t|≥2: {n_naive}개 → **BH-FDR 통과: {n_pass}개** (임계 p={thr:.4f})")
    if n_pass:
        fam = {}
        for c in cells:
            if c["fdr_pass"]:
                fam.setdefault(c["factor"], []).append(c["h"])
        print("  통과 요인:", ", ".join(f"{k}({','.join(map(str,v))}일)" for k, v in fam.items()))
        print("  ⚠ 주의: 부호만 반대인 쌍(near_high_60 ↔ drawdown_60)은 **같은 정보**이므로")
        print("     독립 발견 수는 더 적습니다(자문 A-10).")
    else:
        print("  → 다중검정을 보정하면 **살아남는 셀이 없습니다.**")
    # 민감도: 셀들이 강하게 상관(같은 요인의 여러 지평·유사 요인)이라 유효 검정 수는 40보다 적다.
    # 유효 m을 낮춰도 결론이 유지되는지 확인(자문 A-10의 취지 — 과대·과소 보정 모두 피함).
    pv = sorted(c["p"] for c in cells)
    print("\n  [민감도] 유효 검정 수(m_eff)를 낮춰도 결론이 바뀌는가")
    for m_eff in (40, 20, 10, 5):
        k = 0
        for rank, p in enumerate(pv[:m_eff], start=1):
            if p <= q * rank / m_eff:
                k = rank
        print(f"    m_eff={m_eff:>3} → 통과 {k}개 (rank1 임계 p={q/m_eff:.4f}, 최소 p={pv[0]:.4f})")
    print("    ※ 셀 대부분이 '단기 눌림' 계열 한 가지 정보라, 통과해도 **독립 발견은 사실상 1개**입니다.")
    return n_pass


def report_dsr():
    """전략 수준 Sharpe에 DSR 적용 — 자문대로 N=10과 N=200 둘 다."""
    print("\n" + "=" * 72)
    print(" Deflated Sharpe Ratio — 우리 롱숏/롱온리 백테스트")
    print("=" * 72)
    cases = [("RSI 롱숏(20일 리밸)", 0.18, 90), ("RSI 롱온리", 0.58, 90)]
    print(f"  {'전략':<24}{'관측SR':>8}{'N=10 DSR':>12}{'N=200 DSR':>12}   판정")
    print("  " + "-" * 62)
    for name, sr, n in cases:
        d10, s10 = dsr(sr, n, 10)
        d200, s200 = dsr(sr, n, 200)
        ok = "통과" if min(d10, d200) >= 0.95 else "**탈락**"
        print(f"  {name:<24}{sr:>8.2f}{d10:>12.3f}{d200:>12.3f}   {ok}")
    print("\n  DSR ≥ 0.95 여야 '우연이 아님'. 두 N 모두에서 탈락하면 논쟁 종료(자문 A-10).")
    print("  ※ 관측 SR은 연율 기준, 관측 수는 리밸런스 횟수. 시도 횟수 N은 설정×격자 조합 추정.")


def main():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    files = sorted(glob.glob(os.path.join(base, "요인IC_*.json")))
    if not files:
        print("docs/요인IC_*.json 이 없습니다. 먼저 timing_factors.py를 실행하세요.")
        return
    q = 0.10
    if "--q" in sys.argv:
        q = float(sys.argv[sys.argv.index("--q") + 1])
    for f in files:
        report(f, q)
    report_dsr()


if __name__ == "__main__":
    main()
