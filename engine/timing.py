# -*- coding: utf-8 -*-
"""
지금 뭘 해야 하나 — 살 때 / 지켜볼 때 / 덜어낼 때
====================================================
왜 만들었나
  "내용이 너무 어렵고 뭘 봐야 할지 모르겠다."
  화면에 지표를 늘리는 대신, **한 줄로 답**하고 그 근거를 숫자로 보여준다.

⚠ 무엇으로 판정하나 — 여기가 핵심이다
  이 앱의 검증 결론은 **"가격을 미리 맞히는 신호는 비용을 빼면 남지 않았다"** 였다.
  그래서 "오를 것 같으니 사라"는 만들지 않는다. 대신 **계산하면 확실한 것**으로 판정한다.

    · 내 계좌에서 이 종목이 목표보다 모자란가 / 넘치는가   (비중 계산)
    · 지금 팔면 세금·수수료를 빼고 실제로 얼마가 남는가     (비용 계산)
    · 평단 대비 지금 얼마인가                              (산수)
    · 60일 고점 대비 크게 빠져 있는가                       (회사 확인 필요 신호)

  즉 "이 종목이 오를까?"가 아니라 **"내 계좌 입장에서 지금 무엇이 합리적인가"** 에 답한다.
  판정 근거를 화면에 그대로 적어 사용자가 스스로 검토할 수 있게 한다.
"""
from __future__ import annotations

BUY, WATCH, TRIM = "buy", "watch", "trim"

# 한 종목이 계좌에서 차지해도 괜찮다고 보는 상한(자문 기준과 동일)
MAX_W = 0.25
OVER = 1.5          # 목표의 1.5배를 넘으면 '쏠림'
UNDER = 0.7         # 목표의 0.7배 미만이면 '모자람'


def _cost_pct(price, market="KOSPI", marcap=None):
    """왕복 비용을 **퍼센트**로. ⚠ round_trip_pct 는 소수(0.0034)를 준다 — 100을 곱해야 한다."""
    try:
        from costs import round_trip_pct
        return float(round_trip_pct(price, market, marcap)) * 100.0
    except Exception:
        return 0.55                                  # 대략치(세금 0.20% + 스프레드)


def _sell_take(price, amount, market="KOSPI", marcap=None):
    """지금 팔면 손에 쥐는 금액(세금·수수료 뺀 값)."""
    try:
        from costs import trade_cost
        c = trade_cost(amount, price, side="sell", market=market, marcap=marcap)
        fee = c.get("total", 0) if isinstance(c, dict) else float(c or 0)
        return max(0.0, amount - fee), fee
    except Exception:
        fee = amount * 0.0025
        return amount - fee, fee


def judge(*, code, name="", price=0.0, avg=0.0, my_amount=0.0,
          total_amount=0.0, n_holdings=0, band="", market="KOSPI", marcap=None):
    """
    price       현재가
    avg         내 평단(0이면 모름)
    my_amount   이 종목에 넣은 금액(원)
    total_amount 계좌 전체 금액(원)
    n_holdings  보유 종목 수
    band        entry_timing 의 band('낙폭주의' 등) — 있으면 경고에 반영
    """
    price = float(price or 0)
    my_amount = float(my_amount or 0)
    total_amount = float(total_amount or 0)
    held = my_amount > 0

    w = (my_amount / total_amount) if total_amount > 0 else 0.0
    n = max(1, int(n_holdings or (1 if held else 0)))
    target = min(1.0 / n, MAX_W) if held else min(1.0 / (n + 1), MAX_W)

    pl = (price / avg - 1.0) if (avg and avg > 0 and price > 0) else None
    cost = _cost_pct(price, market, marcap)

    reasons, nums = [], {"weight": round(w * 100, 1), "target": round(target * 100, 1),
                         "cost_pct": round(cost, 2)}
    if pl is not None:
        nums["pl_pct"] = round(pl * 100, 1)

    warn_band = band in ("낙폭주의",)

    # ── 판정 ─────────────────────────────────────────────────────
    if not held:
        if warn_band:
            v = WATCH
            title = "지켜볼 때"
            lead = "아직 안 가진 종목인데, 60일 고점에서 많이 내려와 있습니다."
            reasons.append({"icon": "🔎", "tone": "warn",
                            "text": "많이 빠진 것 자체가 싸다는 뜻은 아닙니다. 회사에 문제가 "
                                    "생긴 경우와 구별이 필요합니다(실적·부채·감사의견 먼저 확인)."})
        else:
            v = BUY
            title = "살 만한 자리"
            lead = "아직 안 가진 종목이라, 넣으면 계좌가 한쪽으로 쏠리는 걸 줄여 줍니다."
            reasons.append({"icon": "🧺", "tone": "good",
                            "text": f"새로 담으면 목표 비중은 {target*100:.0f}% 정도가 됩니다. "
                                    "한 종목에 몰지 않는 것이 가장 확실한 위험 관리입니다."})
    elif w > target * OVER:
        v = TRIM
        title = "덜어낼 만한 자리"
        lead = f"이 한 종목이 계좌의 {w*100:.0f}%입니다. 목표({target*100:.0f}%)보다 많이 큽니다."
        reasons.append({"icon": "⚖️", "tone": "warn",
                        "text": "한 종목 비중이 크면 그 회사 하나에 계좌 전체가 걸립니다. "
                                "맞고 틀리고를 떠나 흔들림이 커집니다."})
        take, fee = _sell_take(price, my_amount, market, marcap)
        over_amt = my_amount - target * total_amount
        nums["trim_amount"] = int(max(0, over_amt))
        nums["sell_fee"] = int(fee)
        reasons.append({"icon": "🧮", "tone": "neutral",
                        "text": f"목표까지 맞추려면 약 {int(max(0,over_amt)):,}원어치입니다. "
                                f"팔면 세금·수수료로 왕복 {cost:.2f}% 정도가 나갑니다."})
    elif w < target * UNDER:
        v = BUY
        title = "채울 만한 자리"
        lead = f"이 종목이 계좌의 {w*100:.0f}%로, 목표({target*100:.0f}%)보다 모자랍니다."
        reasons.append({"icon": "🧺", "tone": "good",
                        "text": "이번 달 여윳돈으로 모자란 쪽부터 채우면 쏠림이 줄어듭니다. "
                                "파는 게 아니라 사는 것이라 매도 세금이 들지 않습니다."})
    else:
        v = WATCH
        title = "그냥 두어도 될 때"
        lead = f"계좌에서 {w*100:.0f}%로, 목표({target*100:.0f}%)와 비슷합니다."
        reasons.append({"icon": "🫱", "tone": "neutral",
                        "text": "굳이 손댈 이유가 보이지 않습니다. 사고파는 횟수를 줄이는 것이 "
                                f"장기 성과에 가장 크게 남습니다(왕복 비용 {cost:.2f}%)."})

    # ── 항상 붙이는 맥락 ─────────────────────────────────────────
    if held and pl is not None:
        if pl > 0:
            take, fee = _sell_take(price, my_amount, market, marcap)
            reasons.append({"icon": "💰", "tone": "neutral",
                            "text": f"평단 대비 {pl*100:+.1f}%입니다. 지금 다 팔면 세금·수수료를 빼고 "
                                    f"약 {int(take):,}원이 남습니다."})
        else:
            reasons.append({"icon": "📉", "tone": "neutral",
                            "text": f"평단 대비 {pl*100:+.1f}%입니다. 손실을 메우려고 더 사는 것(물타기)은 "
                                    "한 종목 비중만 키우는 경우가 많습니다. 비중을 먼저 보세요."})
    if warn_band and held:
        reasons.append({"icon": "🔎", "tone": "warn",
                        "text": "60일 고점에서 크게 내려온 구간입니다. 회사에 문제가 생긴 것은 "
                                "아닌지 확인해 보세요(실적·부채·감사의견)."})

    return {
        "verdict": v, "title": title, "lead": lead, "reasons": reasons, "numbers": nums,
        "basis": "이 판단은 가격이 오를지 내릴지 맞힌 것이 아닙니다. "
                 "내 계좌에서의 비중과 세금·수수료로 계산한 결과입니다.",
        "code": code, "name": name,
    }
