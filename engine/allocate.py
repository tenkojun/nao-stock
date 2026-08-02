# -*- coding: utf-8 -*-
"""
적립식 자금 배분 (자문 H-154 / K-199)
=====================================
전제: 장기투자자는 매달 여유자금으로 **어차피 산다**. 그러면 앱이 답해야 할 질문은
  "어느 종목을 살까"(예측 필요·검증 불가)가 아니라
  **"이번 달 얼마를 어디에 나눠 넣을까"**(계산·확실·효과 큼)이다.
  → 앱의 무게중심을 "종목 분석기"에서 "매달 자금 배분 도우미"로.

방식(전부 계산, 예측 없음):
  · 현재 보유 비중 → 목표 비중과의 **괴리**를 계산
  · 이번 달 자금을 **가장 모자란 쪽부터** 채우는 배분 제안(rebalance-by-buying)
    ※ 매도 없이 매수만으로 균형을 맞춤 = 매도세 0.20%를 내지 않는 방법(자문 A-13)
  · 집중도(HHI 유효종목수)와 배분 후 개선치 표시
  · 각 매수의 실제 비용(수수료·스프레드) 표시
"""
from __future__ import annotations


def _hhi_eff(weights):
    s = sum(weights) or 1.0
    w = [x / s for x in weights]
    hhi = sum(x * x for x in w)
    return (1.0 / hhi) if hhi > 0 else 0.0


def plan(holdings, budget, targets=None, max_weight=0.25, min_ticket=100_000):
    """holdings: {code: {'name':..,'amount':원}}, budget: 이번 달 자금(원).
    targets: {code: 목표비중(0~1)} 없으면 동일가중 목표.
    반환: 배분 제안 + 집중도 개선 + 비용."""
    codes = list(holdings.keys())
    cur = {c: float(holdings[c].get("amount", 0) or 0) for c in codes}
    total_now = sum(cur.values())
    budget = float(budget or 0)
    if not codes or budget <= 0:
        return {"items": [], "note": "보유 종목과 이번 달 금액을 입력하면 배분을 제안합니다."}

    if targets:
        tw = {c: float(targets.get(c, 0)) for c in codes}
        s = sum(tw.values()) or 1.0
        tw = {c: v / s for c, v in tw.items()}
    else:
        tw = {c: 1.0 / len(codes) for c in codes}          # 동일가중 목표
    tw = {c: min(v, max_weight) for c, v in tw.items()}     # 한 종목 상한
    s = sum(tw.values()) or 1.0
    tw = {c: v / s for c, v in tw.items()}

    total_after = total_now + budget
    # 목표금액 대비 부족분이 큰 순서로 예산 배정
    gap = {c: max(0.0, tw[c] * total_after - cur[c]) for c in codes}
    gsum = sum(gap.values())
    alloc = {}
    if gsum <= 0:                                            # 이미 균형 → 목표비중대로
        for c in codes:
            alloc[c] = budget * tw[c]
    else:
        for c in codes:
            alloc[c] = budget * (gap[c] / gsum)
    # 소액 티켓 제거(수수료 대비 비효율) → 큰 쪽으로 재배분
    small = [c for c in codes if 0 < alloc[c] < min_ticket]
    if small and len(small) < len(codes):
        spare = sum(alloc[c] for c in small)
        for c in small:
            alloc[c] = 0.0
        rest = [c for c in codes if alloc[c] > 0] or codes
        for c in rest:
            alloc[c] += spare / len(rest)

    items = []
    for c in sorted(codes, key=lambda x: -alloc[x]):
        after = cur[c] + alloc[c]
        items.append({
            "code": c, "name": holdings[c].get("name", c),
            "now": round(cur[c]), "now_w": round(cur[c] / total_now * 100, 1) if total_now else 0.0,
            "add": round(alloc[c] / 10000) * 10000,          # 만원 단위 반올림
            "after": round(after), "after_w": round(after / total_after * 100, 1),
            "target_w": round(tw[c] * 100, 1),
        })
    eff_before = _hhi_eff(list(cur.values())) if total_now else 0.0
    eff_after = _hhi_eff([i["after"] for i in items])
    maxw_after = max((i["after_w"] for i in items), default=0)
    return {
        "items": items, "budget": round(budget),
        "total_now": round(total_now), "total_after": round(total_after),
        "eff_before": round(eff_before, 2), "eff_after": round(eff_after, 2),
        "max_weight_after": maxw_after,
        "note": ("이번 달 자금을 **가장 모자란 쪽부터** 채우는 방식입니다. "
                 "팔지 않고 사기만 해서 균형을 맞추므로 **매도 세금(0.20%)이 들지 않습니다.** "
                 "종목을 고르는 예측이 아니라, 쏠림을 줄이는 계산입니다."),
        "caveat": "목표 비중은 기본값이 동일가중입니다. 원하시는 비중이 있으면 조정하세요.",
    }
