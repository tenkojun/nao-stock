# -*- coding: utf-8 -*-
"""
평단가 기준 행동 분석 — 검증된 논문만
=========================================
왜 이 주제인가
  "가격이 오를지"는 검증에서 남지 않았다. 그런데 **평단가를 기준으로 사람이 어떻게
  행동하는지**는 사정이 다르다. 수십 년간 여러 시장·여러 표본에서 반복 확인된,
  이 분야에서 가장 재현성 높은 결과들이다. 예측이 아니라 **내가 빠지기 쉬운 함정**을
  짚는 것이므로, 이 앱의 원칙(예측 금지)과 충돌하지 않는다.

쓰는 근거 (실제 논문만 · 미검증 지표 사용 안 함)
  · 처분효과      Shefrin & Statman (1985) J.Finance 40(3)
                  Odean (1998) J.Finance 53(5) — 이익은 빨리 실현, 손실은 오래 붙듦
  · 프로스펙트이론 Kahneman & Tversky (1979) Econometrica 47(2) — 손실회피·준거점
  · 준거가격 효과  Grinblatt & Han (2005) JFE 78(2) — 미실현손익(CGO)이 행동을 좌우
  · 52주 고가      George & Hwang (2004) J.Finance 59(5) — 고점 근처가 준거점이 됨
  · 과다매매 손실  Barber & Odean (2000) J.Finance 55(2)
                  Barber, Lee, Liu & Odean (2009) RFS 22(2) — 개인 매매의 순손실

⚠ 하지 않는 것: "그러니 파세요/사세요" 라는 지시. 경향을 알려주고 판단은 사용자가 한다.
"""
from __future__ import annotations

P = {
    "disposition": ("Are Investors Reluctant to Realize Their Losses?",
                    "Odean (1998) · J. of Finance",
                    "https://doi.org/10.1111/0022-1082.00072"),
    "shefrin": ("The Disposition to Sell Winners Too Early and Ride Losers Too Long",
                "Shefrin & Statman (1985) · J. of Finance",
                "https://doi.org/10.1111/j.1540-6261.1985.tb05002.x"),
    "prospect": ("Prospect Theory: An Analysis of Decision under Risk",
                 "Kahneman & Tversky (1979) · Econometrica",
                 "https://doi.org/10.2307/1914185"),
    "cgo": ("Prospect Theory, Mental Accounting, and Momentum",
            "Grinblatt & Han (2005) · J. of Financial Economics",
            "https://doi.org/10.1016/j.jfineco.2004.10.006"),
    "high52": ("The 52-Week High and Momentum Investing",
               "George & Hwang (2004) · J. of Finance",
               "https://doi.org/10.1111/j.1540-6261.2004.00695.x"),
    "overtrade": ("Trading Is Hazardous to Your Wealth",
                  "Barber & Odean (2000) · J. of Finance",
                  "https://doi.org/10.1111/0022-1082.00226"),
    "retail": ("Just How Much Do Individual Investors Lose by Trading?",
               "Barber, Lee, Liu & Odean (2009) · Review of Financial Studies",
               "https://doi.org/10.1093/rfs/hhn046"),
}


def _paper(k):
    t, w, u = P[k]
    return {"title": t, "who": w, "url": u}


def analyze(*, price=0.0, avg=0.0, high52=0.0, low52=0.0, high60=0.0,
            weight=0.0, held_days=None, trades_90d=None):
    """
    price     현재가
    avg       내 평단(0이면 분석 불가 — 억지로 추정하지 않는다)
    high52/low52/high60  KIS 일봉에서 계산한 실제 값
    weight    이 종목이 계좌에서 차지하는 비중(0~1)
    held_days 보유일수(기록장에서)
    trades_90d 최근 90일 매매 횟수(기록장에서)
    """
    if not (price and avg and avg > 0):
        return {"ok": False,
                "msg": "평단가를 입력하면 지금 위치에서 흔히 생기는 함정을 짚어 드립니다.",
                "items": []}

    pl = price / avg - 1.0                       # 미실현 손익률 = CGO 의 개인 버전
    items = []

    # ── 1) 미실현 이익 — 처분효과(너무 일찍 파는 쪽) ──
    if pl >= 0.10:
        items.append({
            "tag": "이익 구간", "tone": "warn",
            "head": f"평단보다 {pl*100:+.0f}%. 지금이 '팔고 싶어지는' 구간입니다.",
            "text": "이익이 난 종목을 손실 난 종목보다 훨씬 자주 판다는 것이 여러 시장에서 "
                    "반복 확인됐습니다(처분효과). 문제는 그 판단이 회사가 아니라 "
                    "**내 평단**을 기준으로 내려진다는 점입니다. 평단은 시장이 모르는 숫자입니다.",
            "paper": _paper("disposition")})
    elif pl >= 0.02:
        items.append({
            "tag": "이익 구간", "tone": "neutral",
            "head": f"평단보다 {pl*100:+.0f}%.",
            "text": "작은 이익에서도 '본전 이상일 때 팔자'는 쪽으로 기울기 쉽습니다. "
                    "팔 이유가 회사 사정인지, 그냥 평단을 넘겼기 때문인지 구분해 보세요.",
            "paper": _paper("shefrin")})

    # ── 2) 미실현 손실 — 손실회피(너무 오래 붙드는 쪽) ──
    elif pl <= -0.10:
        items.append({
            "tag": "손실 구간", "tone": "warn",
            "head": f"평단보다 {pl*100:+.0f}%. 지금이 '못 파는' 구간입니다.",
            "text": "같은 크기라도 손실의 아픔이 이익의 기쁨보다 크게 느껴지고(손실회피), "
                    "그래서 손실 난 종목을 필요 이상으로 오래 들고 가는 경향이 확인됩니다. "
                    "'본전만 오면 팔겠다'는 생각이 들면 그 신호입니다.",
            "paper": _paper("prospect")})
    elif pl <= -0.02:
        items.append({
            "tag": "손실 구간", "tone": "neutral",
            "head": f"평단보다 {pl*100:+.0f}%.",
            "text": "손실이 크지 않을 때가 오히려 판단하기 좋습니다. 감정이 덜 실려 있어서입니다.",
            "paper": _paper("prospect")})
    else:
        items.append({
            "tag": "본전 근처", "tone": "neutral",
            "head": f"평단과 거의 같습니다({pl*100:+.1f}%).",
            "text": "본전 근처에서 매매가 몰리는 것이 알려져 있습니다. "
                    "'본전이니까'는 회사에 대한 정보가 아닙니다.",
            "paper": _paper("cgo")})

    # ── 3) 물타기 유혹 — 손실 + 이미 큰 비중 ──
    if pl <= -0.05 and weight >= 0.25:
        items.append({
            "tag": "물타기", "tone": "warn",
            "head": f"손실 중인데 이 종목이 이미 계좌의 {weight*100:.0f}%입니다.",
            "text": "손실을 메우려 더 사면 평단은 내려가지만 **한 종목 비중은 올라갑니다.** "
                    "회복이 빨라지는 게 아니라 계좌가 한 회사에 더 묶입니다.",
            "paper": _paper("prospect")})

    # ── 4) 52주 고가 준거점 ──
    if high52 and price:
        gap = price / high52 - 1.0
        if gap >= -0.03:
            items.append({
                "tag": "52주 고가", "tone": "neutral",
                "head": f"52주 최고가 근처입니다({gap*100:+.0f}%).",
                "text": "고점 근처에서 사람들이 '너무 비싸다'고 느껴 매수를 미루는 경향이 "
                        "보고돼 있습니다. 고점이라는 사실 자체는 회사의 가치와 무관합니다.",
                "paper": _paper("high52")})
        elif gap <= -0.30:
            items.append({
                "tag": "52주 고가", "tone": "neutral",
                "head": f"52주 최고가보다 {abs(gap)*100:.0f}% 아래입니다.",
                "text": "고점 대비 많이 내려온 것을 '싸다'로 읽기 쉽습니다. "
                        "고점은 준거점일 뿐이고, 그 가격이 옳았다는 보장은 없습니다.",
                "paper": _paper("high52")})

    # ── 5) 매매 빈도 ──
    if trades_90d is not None and trades_90d >= 6:
        items.append({
            "tag": "매매 빈도", "tone": "warn",
            "head": f"최근 90일에 {trades_90d}번 매매하셨습니다.",
            "text": "많이 사고파는 계좌일수록 수익률이 낮았다는 결과가 대규모 개인 계좌 "
                    "자료에서 반복 확인됩니다. 매도마다 세금 0.20%가 확정 비용으로 나갑니다.",
            "paper": _paper("overtrade")})
    if held_days is not None and held_days <= 20 and pl >= 0.05:
        items.append({
            "tag": "보유 기간", "tone": "neutral",
            "head": f"산 지 {held_days}일 됐습니다.",
            "text": "짧게 들고 이익이 났을 때 파는 쪽으로 가장 크게 기울어집니다. "
                    "원래 계획한 보유 기간이 얼마였는지 기록장에서 확인해 보세요.",
            "paper": _paper("retail")})

    return {"ok": True, "pl_pct": round(pl * 100, 1), "items": items,
            "note": "여기 있는 내용은 가격 예측이 아니라, 평단가를 기준으로 사람들이 "
                    "실제로 어떻게 행동하는지에 대한 연구 결과입니다."}
