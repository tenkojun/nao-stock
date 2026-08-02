# -*- coding: utf-8 -*-
"""
진입 적정도 (Entry Timing Assessment) — 검증된 신호만, 정직한 관찰 서술
======================================================================
핵심 질문: "지금 이 가격에 사도 괜찮은가"(한국장 변동성, 보유 1~3개월~1년).

⚠ 원칙: 예측·확률·등급 금지(M-140/L-127). 매수 지시 금지(L-128). 검증 통과 요인만,
   불확실성·효과크기와 함께 '관찰'로만 서술. 각 관찰에 논문 근거를 붙여 공부탭이 참조.

검증 근거(자체 250종목·2019~2026 편향통제 IC, docs/검증_진입타이밍_2019.log):
  · 깊은 낙폭(60일 고점대비) → 이후 1~3개월 더 부진 (t−3.1, robust). = 모멘텀(하락 지속).
  · 얕은 과매도(RSI/볼린저) → 단기(~2주) 소폭 반등 경향 (t2.0~2.3, 약함, 다중검정 미통과).
  · 깊은 낙폭을 '싸다'고 사는 것이 개인 최대 손실원 → 이 경고가 핵심 보호장치.
"""
from __future__ import annotations
import numpy as np

# 논문 근거 (공부탭 출처 표기용) — 요인 → (제목, 저자, 출처키)
PAPER_BASIS = {
    "momentum": ("Returns to Buying Winners and Selling Losers", "Jegadeesh & Titman (1993)",
                 "https://www.jstor.org/stable/2328882"),
    "reversal": ("Short-Term Reversal / Mean Reversion", "Jegadeesh (1990); Lehmann (1990)",
                 "https://doi.org/10.1111/j.1540-6261.1990.tb05110.x"),
    "cost":     ("거래비용이 단기신호를 잠식", "López de Prado; 자체 검증 I-100",
                 "docs/검증_진입타이밍_2019.log"),
    "flow":     ("Do Foreign Investors Destabilize Stock Markets?", "Choe, Kho & Stulz (1999)",
                 "https://doi.org/10.1016/S0304-405X(99)00037-9"),
}


def _flow_risk_context(flow, mc, price):
    """진입 참고 맥락(검증된 band와 분리): 수급 온도계 + 하방 리스크. 예측 아님."""
    ctx = []
    if flow:
        f5 = flow.get("foreign_5d", 0) or 0
        o5 = flow.get("org_5d", 0) or 0
        if f5 or o5:
            fd = "순매수" if f5 > 0 else "순매도" if f5 < 0 else "중립"
            od = "순매수" if o5 > 0 else "순매도" if o5 < 0 else "중립"
            ctx.append({"label": "수급 온도계",
                        "text": f"최근 5일 외국인 {fd} · 기관 {od}. 수급은 방향을 맞히는 나침반이라기보다 "
                                "분위기 온도계입니다(예측력 약·국면따라 뒤집힘).",
                        "tone": "neutral", "basis": PAPER_BASIS["flow"]})
    if mc and price and price > 0:
        q10 = mc.get("q10")
        if q10:
            dn = q10 / price - 1.0
            ctx.append({"label": "하방 리스크",
                        "text": f"20일 나쁜 시나리오(하위 10%)면 약 {dn*100:.0f}% ({int(q10):,}원)까지 "
                                "열려 있습니다. 예측이 아니라 미리 각오할 손실입니다.",
                        "tone": "warn", "basis": None})
    return ctx


def _rsi(c, n=14):
    c = np.asarray(c, float)
    d = np.diff(c)
    if len(d) < n:
        return 50.0
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = up[-n:].mean(); ad = dn[-n:].mean()
    if ad == 0:
        return 100.0 if au > 0 else 50.0
    return 100 - 100 / (1 + au / ad)


def entry_assessment(close, high, rsi_val=None, flow=None, mc=None, price=None):
    """검증된 진입타이밍 신호를 정직한 관찰로 반환.
    반환: {band, headline, observations, context, caveat, metrics}
    band(검증된 가격신호): '낙폭주의'|'소폭눌림'|'강도유지'|'중립'  (등급·확률 아님)
    context(참고·비검증): 수급 온도계 + 하방 리스크 (band 판정엔 미반영)
    """
    c = np.asarray(close, float)
    h = np.asarray(high, float)
    if len(c) < 65:
        return {"band": "정보부족", "headline": "표본이 짧아 진입 평가를 유보합니다.",
                "observations": [], "context": _flow_risk_context(flow, mc, price),
                "caveat": "최소 65거래일 데이터 필요."}
    px = float(c[-1])
    hi60 = float(np.max(h[-60:]))
    ma20 = float(c[-20:].mean()); ma60 = float(c[-60:].mean())
    sd20 = float(c[-20:].std())
    dd60 = float(px / hi60 - 1.0) if hi60 > 0 else 0.0   # ≤0, 60일 고점대비 낙폭
    boll_z = float((px - ma20) / sd20) if sd20 > 0 else 0.0
    r = float(rsi_val) if rsi_val is not None else float(_rsi(c))

    obs = []
    # 1) 깊은 낙폭 — 2026-07-28 재검증으로 해석 수정:
    #    낙폭의 '이후 부진' 효과는 사실상 **상장폐지로 가는 종목**이 만든 것이고,
    #    생존 대형주만 보면 효과가 없었다(t≈0). 따라서 수익 예측이 아니라 **부실 위험** 신호로 서술.
    if dd60 <= -0.20:
        band, tone = "낙폭주의", "warn"
        headline = (f"60일 고점 대비 {dd60*100:.0f}% 하락한 구간입니다. "
                    "큰 낙폭 자체가 '이후 더 떨어진다'는 뜻은 아닙니다(대형주에서는 이후 수익과 "
                    "뚜렷한 관계가 없었습니다). 다만 회사에 문제가 생긴 경우와 구별이 필요합니다.")
        obs.append({"text": "저희 검증에서 '많이 빠진 종목이 더 빠진다'는 결과는 대부분 "
                            "**상장폐지로 간 부실 종목**이 만들어낸 것이었습니다. 살아남은 대형주에서는 "
                            "그런 경향이 없었습니다. 그래서 이 신호는 수익 예측이 아니라 "
                            "**회사가 괜찮은지 확인하라는 뜻**으로 보시는 게 맞습니다(실적·부채·감사의견).",
                    "tone": "warn", "strength": "중", "basis": PAPER_BASIS["momentum"]})
    # 2) 얕은 과매도 — 재검증에서 생존 대형주 기준 20~60일 지평에 가장 일관된 신호(t2.2~2.7)
    elif r <= 35 or boll_z <= -1.5:
        band, tone = "소폭눌림", "neutral"       # 2026-07-28: 다중검정 통과 실패 → '유리' 표현 제거
        headline = (f"최근 고점에서 조금 내려온 구간입니다(RSI {r:.0f}). "
                    "이런 눌림이 이후 수익에 도움이 되는지 저희가 한국 대형주로 검증해 봤지만, "
                    "**통계적으로 확인되지 않았습니다.**")
        obs.append({"text": "여러 지표를 동시에 시험한 점을 반영해 보정하면(다중검정) 살아남는 신호가 "
                            "없었습니다. 다만 이는 '효과가 없다'는 증명이 아니라 **8년 자료로는 원래 "
                            "확인이 불가능하다**는 뜻에 가깝습니다. 어느 쪽이든 이 정도 크기는 "
                            "거래비용(왕복 0.3~0.7%)을 넘지 못합니다 — 이걸 이유로 서두르지 마세요.",
                    "tone": "neutral", "strength": "없음", "basis": PAPER_BASIS["reversal"]})
    # 3) 고점 부근 강도 유지 (모멘텀 양(+) 맥락)
    elif dd60 >= -0.06 and ma20 > ma60 and r < 72:
        band, tone = "강도유지", "neutral"
        headline = ("60일 고점 부근에서 상승 흐름을 유지 중입니다. "
                    "강한 종목이 강함을 이어가는 경향은 검증되나, 이는 매수 신호가 아닙니다.")
        obs.append({"text": "고점 부근 강세 지속은 모멘텀 효과와 부합합니다. "
                            "다만 진입가가 높으므로 하방 리스크(아래)를 함께 보세요.",
                    "tone": "neutral", "strength": "약", "basis": PAPER_BASIS["momentum"]})
    else:
        band, tone = "중립", "neutral"
        headline = "뚜렷한 진입 타이밍 신호가 없는 중립 구간입니다."

    # 과열 경고(공통 부가)
    if r >= 75:
        obs.append({"text": f"단기 과열(RSI {r:.0f}) — 단기 조정 가능성. 분할 진입이 부담을 줄입니다.",
                    "tone": "warn", "strength": "약", "basis": PAPER_BASIS["reversal"]})

    # 보유기간 관점(검증된 term structure: 짧게=단기반전, 길게=모멘텀) — 보유기간은 1~3개월·1년 둘 다 가정
    # 2026-07-28 재검증 반영: 생존 대형주에서 유의한 것은 1~3개월 반전뿐,
    # 6개월+ 지평에서는 어떤 가격 신호도 유의하지 않았다 → 장기일수록 '타이밍보다 종목·비중'.
    HZ = {
        "낙폭주의": "1~3개월이든 1년이든, 낙폭 자체로는 앞날을 알 수 없습니다. 대신 회사에 문제가 없는지(실적·부채·감사의견)를 확인하고, 이미 많이 담으셨다면 추가 매수 비중을 줄이세요.",
        "소폭눌림": "며칠 눌렸다고 더 유리하다는 근거는 저희 검증에서 나오지 않았습니다. 1~3개월이든 1년이든, 타이밍보다 **얼마를 어느 종목에 넣느냐**가 성과를 좌우합니다.",
        "강도유지": "고점 부근이라고 더 오른다는 근거는 저희 검증에서 나오지 않았습니다(대형주 기준). 길게 보실수록 진입 시점보다 얼마를 넣느냐가 중요합니다.",
        "중립": "1~3개월이면 눌림 여부가 조금 참고가 되고, 6개월 이상이면 타이밍보다 종목·비중이 훨씬 중요합니다.",
    }
    horizon = HZ.get(band, "")
    caveat = ("이 평가는 '가격 위치'에 대한 관찰이며 매수 추천이 아닙니다. 장기 보유일수록 "
              "진입 시점보다 종목 자체가 중요합니다(자체 검증: 6개월+ 보유에선 타이밍 효과 소멸).")
    return {"band": band, "tone": tone, "headline": headline, "horizon": horizon,
            "observations": obs, "context": _flow_risk_context(flow, mc, price),
            "caveat": caveat,
            "metrics": {"dd60": round(dd60, 3), "rsi": round(r, 1), "boll_z": round(boll_z, 2)}}
