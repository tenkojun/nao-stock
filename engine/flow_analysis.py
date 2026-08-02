# -*- coding: utf-8 -*-
"""
수급 전문 분석 (전문가 F-62~F-73 반영) — 외국인·기관·개인 순매수의 '전문적' 해석
==========================================================================
개선점(원시 순매수량 → 전문 해석):
  · F-64 표준화: 순매수량을 '평균 거래량 대비 %'로 → 종목 간 비교 가능(절대량은 대형주 편향).
  · F-63 다중 창: 5일(단기) + 20일(중기) 병행.
  · F-65/F-72 주체 분리: 외국인·기관·개인 각각(개인은 보통 역방향).
  · 연속 순매수/순매도 일수(streak): 지속적 매집/분산 여부.
  · F-62 프레이밍: 수급은 나침반 아닌 '온도계'(예측력 약·국면의존) — 정직 고지.
데이터: KIS investor_flow rows(최근 20거래일, 일별 순매수량) + 평균 거래량.
"""
from __future__ import annotations

_BASIS = ("Do Foreign Investors Destabilize Stock Markets?", "Choe, Kho & Stulz (1999)",
          "https://doi.org/10.1016/S0304-405X(99)00037-9")
_ACTORS = [("외국인", "foreign_net"), ("기관", "org_net"), ("개인", "person_net")]


def _streak(rows, key):
    """최근부터 같은 방향(순매수/매도) 연속 일수. +매수일 / -매도일."""
    s, sign = 0, None
    for r in rows:
        v = r.get(key, 0) or 0
        if v == 0:
            break
        cur = 1 if v > 0 else -1
        if sign is None:
            sign = cur
        if cur == sign:
            s += 1
        else:
            break
    return s * (sign or 0)


def analyze_flow(rows, avg_volume=None):
    """전문 수급 해석. rows: 최근순 [{date, foreign_net, org_net, person_net}]."""
    if not rows:
        return None
    actors = []
    for name, key in _ACTORS:
        n5 = sum(r.get(key, 0) or 0 for r in rows[:5])
        n20 = sum(r.get(key, 0) or 0 for r in rows[:20])
        pct5 = round(n5 / (avg_volume * 5) * 100, 1) if avg_volume else None
        actors.append({
            "name": name, "net5": int(n5), "net20": int(n20), "pct5": pct5,
            "dir5": "순매수" if n5 > 0 else "순매도" if n5 < 0 else "중립",
            "streak": _streak(rows, key),
        })
    f, o = actors[0], actors[1]
    if f["net5"] > 0 and o["net5"] > 0:
        combo, tone = "외국인·기관 동반 순매수 (수요 우위)", "plus"
    elif f["net5"] < 0 and o["net5"] < 0:
        combo, tone = "외국인·기관 동반 순매도 (매물 우위)", "warn"
    else:
        combo, tone = "외국인·기관 방향 엇갈림 (혼조)", "neutral"
    return {
        "actors": actors, "combo": combo, "tone": tone,
        "caveat": "수급은 방향을 맞히는 나침반이 아니라 분위기 온도계입니다"
                  "(예측력 약·국면따라 뒤집힘). '거래량 대비 %'로 표준화해 종목 간 비교가 가능합니다.",
        "basis": _BASIS,
    }
