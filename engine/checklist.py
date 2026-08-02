# -*- coding: utf-8 -*-
"""
정밀 체크리스트 (Pine 초기판 계승 · 증거 등급화)
==================================================
"지금 사도 되나"를 판단할 때 훑을 항목을 구조화. 각 항목은
  status: pass(양호) / caution(주의) / fail(위험) / na(정보부족)
  grade : A(강한 실증) / B(실무·논쟁) / C(약함) / V(이 앱이 KR 데이터로 자체검증)
  paper : 근거 출처

⚠ 총점·등급을 만들지 않는다. 항목별 상태만 보여주고 "통과 n/m"만 표기
   (전문가 M-140/L-127: 미검증 정밀도가 거짓 확신을 만든다).
"""
from __future__ import annotations

P = {
    "mom": ("V", "Returns to Buying Winners and Selling Losers", "Jegadeesh & Titman (1993) + 자체검증 t=3.5",
            "https://www.jstor.org/stable/2328882"),
    "rev": ("C", "Evidence of Predictable Behavior of Security Returns", "Jegadeesh (1990)",
            "https://doi.org/10.1111/j.1540-6261.1990.tb05110.x"),
    "value": ("B", "The Cross-Section of Expected Stock Returns", "Fama & French (1992)",
              "https://doi.org/10.1111/j.1540-6261.1992.tb04398.x"),
    "qual": ("B", "The Other Side of Value: Gross Profitability", "Novy-Marx (2013)",
             "https://doi.org/10.1016/j.jfineco.2013.01.003"),
    "har": ("A", "A Simple Long Memory Model of Realized Volatility", "Corsi (2009)",
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=626064"),
    "illiq": ("A", "Illiquidity and Stock Returns", "Amihud (2002)",
              "https://doi.org/10.1016/S1386-4181(01)00024-6"),
    "flow": ("B", "Do Foreign Investors Destabilize Stock Markets?", "Choe, Kho & Stulz (1999)",
             "https://doi.org/10.1016/S0304-405X(99)00037-9"),
    "vwap": ("B", "The Total Cost of Transactions on the NYSE (VWAP 도입)",
             "Berkowitz, Logue & Noser (1988)",
             "https://doi.org/10.1111/j.1540-6261.1988.tb04593.x"),
    "cost": ("A", "What Do We Know About the Profitability of Technical Analysis?",
             "Park & Irwin (2007) — 손익분기비용 0.22~0.39%",
             "https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-6419.2007.00519.x"),
    "crash": ("B", "Momentum Crashes", "Daniel & Moskowitz (2016)",
              "https://doi.org/10.1016/j.jfineco.2015.12.002"),
}


def _item(cat, label, status, value, why, key):
    g, title, who, url = P[key]
    return {"cat": cat, "label": label, "status": status, "value": value,
            "why": why, "grade": g, "paper": [title, who, url]}


def build_checklist(res, pro=None, evaluation=None, flow_pro=None):
    """res=analyze() 결과, pro=indicators_pro.analyze_pro(), evaluation=fundamentals, flow_pro=수급."""
    out = []
    px = res.get("price") or 0
    entry = res.get("entry") or {}
    m = entry.get("metrics") or {}

    # ── 1. 종목 강도 (자체검증) ──
    dd = m.get("dd60")
    if dd is not None:
        if dd >= -0.06:
            st, why = "pass", "60일 고점 부근 — 강한 종목이 강함을 이어가는 경향(자체검증 t=3.5, 장기보유 유리)."
        elif dd >= -0.20:
            st, why = "caution", "고점에서 다소 밀림 — 강도 중간."
        else:
            st, why = "fail", "고점 대비 낙폭이 큼 — 이후 1~3개월 더 부진한 경향(자체검증). '싸다'고 담는 건 위험."
        out.append(_item("종목 강도", "모멘텀 (60일 고점 대비)", st, f"{dd*100:.0f}%", why, "mom"))

    # ── 2. 진입 타이밍 ──
    rsi = m.get("rsi")
    if rsi is not None:
        if rsi <= 35:
            st, why = "pass", "과매도권 — 단기(~2주) 소폭 반등 경향(효과 작고 다중검정 미통과, 참고용)."
        elif rsi >= 75:
            st, why = "caution", "단기 과열 — 조정 가능. 분할 진입이 부담을 줄임."
        else:
            st, why = "pass", "중립 구간 — 타이밍상 특이 신호 없음."
        out.append(_item("진입 타이밍", "단기 위치 (RSI)", st, f"{rsi:.0f}", why, "rev"))

    if pro and pro.get("vwap") and px:
        vw = pro["vwap"]
        pos = px / vw["vwap"] - 1 if vw["vwap"] else 0
        st = "pass" if abs(pos) < 0.03 else ("caution" if pos > 0 else "pass")
        why = ("기관 평균체결가(VWAP) 대비 위치. VWAP은 예측 지표가 아니라 '집행 기준선'입니다"
               " — 위/아래 여부만 참고.")
        out.append(_item("진입 타이밍", "VWAP 대비 위치", st, f"{pos*100:+.1f}%", why, "vwap"))

    # ── 3. 리스크 ──
    if pro and pro.get("har"):
        h = pro["har"]
        s = h["sigma_h"]
        st = "pass" if s < 12 else ("caution" if s < 22 else "fail")
        why = (f"HAR-RV 모형 예상 {h['horizon']}일 변동성 ±{s}% (설명력 R²={h['r2']}). "
               f"나쁜 경우 {h['band_lo']:,}원까지 열림 — 예측이 아니라 '각오할 폭'입니다. "
               "GARCH·ARFIMA 대비 우수한 표준 변동성 모형.")
        out.append(_item("리스크", "예상 변동성 (HAR-RV)", st, f"±{s}%", why, "har"))

    if pro and pro.get("amihud"):
        a = pro["amihud"]
        st = "fail" if a["illiq"] > 20 else ("caution" if a["illiq"] > 4 else "pass")
        out.append(_item("리스크", "유동성 (Amihud 비유동성)", st, a["level"], a["note"], "illiq"))

    if res.get("surge"):
        out.append(_item("리스크", "급등 과열", "fail", "급등 구간",
                         "급등 후 크래시 위험 구간 — 모멘텀 크래시는 약세장 반등기·고변동에 집중.", "crash"))

    # ── 4. 가치·퀄리티 ──
    if evaluation:
        f = evaluation.get("fundamentals") or {}
        pbr, roe = f.get("pbr"), f.get("roe")
        if pbr is not None:
            st = "pass" if pbr < 1 else ("caution" if pbr <= 3 else "fail")
            out.append(_item("종목 가치", "가치 (PBR)", st, f"PBR {pbr:.2f}",
                             "순자산 대비 가격. 낮을수록 저평가(가치효과). 문헌 근거는 강하나 "
                             "이 앱이 한국 데이터로 독립 검증하지는 못했습니다.", "value"))
        if roe is not None:
            st = "pass" if roe >= 15 else ("caution" if roe >= 8 else "fail")
            out.append(_item("종목 가치", "수익성 (ROE)", st, f"ROE 약 {roe:.0f}%",
                             "자기자본 대비 이익. 높을수록 우량(퀄리티 효과). ※PBR/PER 기반 근사치.", "qual"))

    # ── 5. 수급 ──
    if flow_pro and flow_pro.get("actors"):
        fa = flow_pro["actors"][0]; oa = flow_pro["actors"][1]
        both_buy = fa["net5"] > 0 and oa["net5"] > 0
        both_sell = fa["net5"] < 0 and oa["net5"] < 0
        st = "pass" if both_buy else ("caution" if both_sell else "pass")
        out.append(_item("수급", "외국인·기관 5일", st, flow_pro["combo"],
                         "수급은 방향을 맞히는 나침반이 아니라 분위기 온도계(예측력 약·국면따라 뒤집힘).",
                         "flow"))

    # ── 6. 비용·실행 ──
    stop = res.get("stop")
    if px and stop and stop < px:
        risk = (px - stop) / px * 100
        # HAR-RV 기대 변동성과 비교: 손절폭이 1σ 안이면 노이즈에 털릴 위험(whipsaw)
        sig = (pro or {}).get("har", {}).get("sigma_h") if pro else None
        if sig:
            ratio = risk / sig
            if ratio < 0.6:
                st = "fail"
                why = (f"손절폭 -{risk:.1f}%가 예상 변동폭 ±{sig}%보다 좁습니다 — 방향이 맞아도 "
                       "일상적 흔들림에 먼저 털릴 위험(whipsaw)이 큽니다.")
            elif ratio < 1.0:
                st = "caution"
                why = (f"손절폭 -{risk:.1f}%가 예상 변동폭 ±{sig}%와 비슷합니다 — 다소 타이트합니다.")
            else:
                st = "pass"
                why = (f"손절폭 -{risk:.1f}%가 예상 변동폭 ±{sig}%보다 여유 있습니다. 다만 그만큼 "
                       "감수할 손실도 큽니다 — 매수 금액을 줄여 조절하세요.")
            try:                              # 자문 A-13: 종목별 실비용 + 매수/매도 비대칭
                from costs import explain
                cx = explain(px)
                why += (f" 이 종목은 사고팔아 본전이 되려면 약 {cx['round_trip_pct']:.2f}% 올라야 하고, "
                        f"매도 비용이 매수의 약 {round(cx['sell_total']/max(cx['buy_total'],1))}배입니다"
                        "(매수 세금 0%, 매도 0.20%) — 자주 파는 것이 가장 비쌉니다.")
            except Exception:
                why += " 왕복 비용(약 0.4%)을 못 넘는 기대이득은 무효입니다."
        else:
            st, why = ("pass" if risk >= 2 else "caution",
                       "왕복 거래비용(세금·수수료·슬리피지 약 0.4%)을 넘지 못하는 기대이득은 무효. "
                       "기술적 매매 손익분기비용 0.22~0.39% — 잦은 매매일수록 불리.")
        out.append(_item("비용·실행", "손절폭 vs 변동성·비용", st, f"손절 -{risk:.1f}%", why, "cost"))

    passed = sum(1 for x in out if x["status"] == "pass")
    return {
        "items": out, "passed": passed, "total": len(out),
        "caveat": ("항목별 관찰이며 총점·등급이 아닙니다. 통과 개수가 많다고 오른다는 뜻이 아니고, "
                   "매수 추천도 아닙니다. 등급: V=이 앱이 한국 데이터로 검증 · A=강한 실증 근거 · "
                   "B=실무 표준이나 예측력 논쟁 · C=약함(비용 반영 시 소멸)."),
    }
