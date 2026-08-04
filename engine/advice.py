# -*- coding: utf-8 -*-
"""
지금 어떻게 할까요 — 문장으로 된 조언
=========================================
요청 예시: "지금 헤드앤숄더입니다. 평단 30만, 현재 40만. 전고점 돌파 시도했지만
           못 넘고 떨어졌습니다. 일부 정리를 추천드립니다."

말투는 저렇게 자연스럽게 간다. 다만 **주장하는 내용**은 아래 넷으로만 채운다.

  ① 사실   — 전고점을 넘었는가 못 넘었는가, 지금 어디쯤인가 (지나간 일)
  ② 계산   — 평단 대비 얼마, 팔면 세후 얼마, 계좌에서 몇 %  (산수)
  ③ 분포   — 몬테카를로: 과거 변동성대로면 한 달 뒤 어느 범위  (예측 아님, 범위)
  ④ 행동   — 지금 위치에서 사람이 흔히 하는 실수 (검증된 논문)

⚠ 하지 않는 것
  "헤드앤숄더니까 떨어집니다" 같은 **패턴 예측**. 차트 패턴이 비용을 넘는 수익으로
  이어진다는 것은 확인되지 않았다(Park & Irwin 2007). 패턴 인식이 통계적 내용을
  갖는다는 연구는 있으나(Lo, Mamaysky & Wang 2000) 수익성과는 별개다.
  그래서 모양 이름을 근거로 쓰지 않고, **넘었나 못 넘었나**라는 사실만 말한다.
"""
from __future__ import annotations

PAPERS = {
    "ta": ("What Do We Know About the Profitability of Technical Analysis?",
           "Park & Irwin (2007)",
           "https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-6419.2007.00519.x"),
    "pattern": ("Foundations of Technical Analysis",
                "Lo, Mamaysky & Wang (2000) · J. of Finance",
                "https://doi.org/10.1111/0022-1082.00265"),
    "vol": ("A Simple Approximate Long-Memory Model of Realized Volatility",
            "Corsi (2009) · J. of Financial Econometrics",
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=626064"),
}


def _n(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def recent_poc(closes, volumes, bars=60):
    """최근 구간에서 거래가 가장 몰린 값.
    ⚠ 긴 창(120일)으로 내면 크게 움직인 종목은 옛 가격대가 뽑혀 쓸모가 없다
       (삼성전자에서 현재가 240,000원인데 POC 101,154원이 나왔다)."""
    try:
        c = [float(x) for x in (closes or [])][-bars:]
        v = [float(x) for x in (volumes or [])][-bars:]
        if len(c) < 10 or len(v) < len(c):
            return 0.0
        lo, hi = min(c), max(c)
        if hi <= lo:
            return 0.0
        n = 24
        step = (hi - lo) / n
        buckets = [0.0] * n
        for px, vol in zip(c, v):
            i = min(n - 1, int((px - lo) / step))
            buckets[i] += vol
        i = buckets.index(max(buckets))
        return lo + step * (i + 0.5)
    except Exception:
        return 0.0


def build(*, name="", price=0.0, avg=0.0, my_amount=0.0, total_amount=0.0,
          high60=0.0, high52=0.0, poc=0.0, res=0.0, sup=0.0,
          mc=None, psych_items=None, market="KOSPI", marcap=None,
          closes=None, volumes=None):
    price, avg = _n(price), _n(avg)
    my_amount, total_amount = _n(my_amount), _n(total_amount)
    high60, high52, poc = _n(high60), _n(high52), _n(poc)
    res, sup = _n(res), _n(sup)
    mc = mc or {}
    if price <= 0:
        return {"ok": False, "msg": "현재가를 불러오지 못했습니다."}

    held = my_amount > 0
    w = (my_amount / total_amount) if total_amount > 0 else 0.0
    pl = (price / avg - 1.0) if avg > 0 else None

    lines, facts = [], []

    # ── ① 사실: 전고점을 넘었나 못 넘었나 ─────────────────────────
    if high60 > 0:
        gap = price / high60 - 1.0
        if gap >= -0.005:
            facts.append(f"지금 값이 최근 60일 중 가장 높은 자리({high60:,.0f}원) 근처입니다.")
        elif gap >= -0.05:
            facts.append(f"최근 60일 고점 {high60:,.0f}원 바로 아래({gap*100:.1f}%)에 있습니다. "
                         "아직 그 위로 올라선 적은 없습니다.")
        else:
            facts.append(f"최근 60일 고점 {high60:,.0f}원을 넘지 못하고 "
                         f"{abs(gap)*100:.0f}% 내려온 자리입니다.")
    if high52 > 0 and high52 > high60 * 1.02:
        facts.append(f"1년 기준 최고가는 {high52:,.0f}원입니다.")
    rp = recent_poc(closes, volumes) or poc
    if rp > 0 and abs(rp / price - 1.0) <= 0.35:      # 너무 먼 값은 지금 판단에 쓸모가 없다
        rel = "위" if price >= rp else "아래"
        facts.append(f"최근 두어 달 거래가 가장 많이 몰린 값은 {rp:,.0f}원이고, "
                     f"지금은 그보다 {rel}입니다.")
    if res > 0 and price < res:
        facts.append(f"바로 위에서 걸리는 자리는 {res:,.0f}원입니다.")
    if sup > 0 and price > sup:
        facts.append(f"바로 아래 받치는 자리는 {sup:,.0f}원입니다.")

    # ── ② 계산: 평단·비중·세후 ──────────────────────────────────
    if held and pl is not None:
        lines.append(f"평단 {avg:,.0f}원, 지금 {price:,.0f}원이니 {pl*100:+.1f}%입니다.")
        try:
            from costs import trade_cost
            c = trade_cost(my_amount, price, side="sell", market=market, marcap=marcap)
            fee = c.get("total", 0)
            lines.append(f"지금 전부 팔면 세금·수수료 {fee:,.0f}원을 빼고 "
                         f"약 {my_amount-fee:,.0f}원이 손에 들어옵니다.")
        except Exception:
            pass
        if total_amount > 0:
            lines.append(f"이 종목이 계좌의 {w*100:.0f}%를 차지합니다.")

    # ── ③ 분포: 몬테카를로(예측 아님) ───────────────────────────
    q10, q90 = _n(mc.get("q10")), _n(mc.get("q90"))
    if q10 and q90:
        lines.append(f"지난 변동폭이 그대로 이어진다고 보면 앞으로의 값은 대체로 "
                     f"{q10:,.0f}~{q90:,.0f}원 사이에서 움직였습니다. "
                     "어디로 갈지가 아니라 **얼마나 흔들릴 수 있는지**를 본 것입니다.")

    # ── ④ 결론: 무엇을 검토할 만한가 ────────────────────────────
    action, why = "watch", []
    if held:
        tgt = 0.25
        if w > tgt * 1.5:
            action = "trim"
            why.append(f"계좌의 {w*100:.0f}%로 한 종목 치고 큽니다(기준 {tgt*100:.0f}%).")
            if pl is not None and pl > 0:
                why.append("이익 구간이라 일부를 정리해도 손실 확정이 아닙니다.")
        elif pl is not None and pl < -0.10 and w > tgt:
            action = "watch"
            why.append("손실 구간에서 비중까지 큽니다. 더 담기보다 먼저 비중을 보세요.")
        elif w < tgt * 0.7:
            action = "buy"
            why.append(f"계좌의 {w*100:.0f}%로 기준보다 적습니다. 이번 달 여윳돈이 있으면 "
                       "여기부터 채우는 쪽이 쏠림을 줄입니다.")
        else:
            why.append("비중이 기준과 비슷합니다. 굳이 지금 손댈 이유가 보이지 않습니다.")
    else:
        action = "buy"
        why.append("아직 없는 종목이라, 담으면 한쪽 쏠림이 줄어듭니다.")

    verdict = {"trim": "일부 정리를 검토해 보실 만합니다.",
               "buy": "채우는 쪽을 검토해 보실 만합니다.",
               "watch": "지금은 그냥 두셔도 괜찮아 보입니다."}[action]

    return {
        "ok": True, "action": action, "name": name,
        "facts": facts, "lines": lines, "why": why, "verdict": verdict,
        "psych": psych_items or [],
        "limits": "모양(패턴)으로 앞날을 맞히지는 않았습니다. 차트 모양이 비용을 넘는 "
                  "수익으로 이어진다는 것은 확인되지 않았습니다. 위 내용은 "
                  "①지나온 사실 ②세금까지 넣은 계산 ③과거 변동폭으로 본 범위 "
                  "④사람이 흔히 하는 실수, 이 넷입니다.",
        "papers": [{"title": t, "who": w2, "url": u} for t, w2, u in PAPERS.values()],
    }
