# -*- coding: utf-8 -*-
"""
지지·저항 존 분석 (god-mode 차트용) — 스윙 고저 + 볼륨 노드 + 기간 고저 클러스터링
==============================================================================
단일 저항선이 아니라 '이전 저항까지' 다층 존을 블록으로. 전문가 자문 반영:
  · E-59 스윙 고저(프랙탈)를 거래량 가중, 터치 횟수로 강도.
  · E-50/51 볼륨 노드(매물대) — 구조적 앵커.
  · E-61 52주 고저가 가장 강한 참조. 근접 레벨은 존으로 병합(ATR 기준).
반환: [{lo, hi, mid, type:'res'|'sup', strength(0~1), touches, kind}] (강한 순).
"""
from __future__ import annotations
import numpy as np


def _atr(h, l, c, n=14):
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    if len(c) < 2:
        return 0.0
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-n:])) if len(tr) else 0.0


def _swings(h, l, w=3):
    h, l = np.asarray(h, float), np.asarray(l, float)
    n = len(h)
    hi, lo = [], []
    for i in range(w, n - w):
        if h[i] >= h[i - w:i + w + 1].max():
            hi.append(i)
        if l[i] <= l[i - w:i + w + 1].min():
            lo.append(i)
    return hi, lo


def sr_zones(o, h, l, c, volume=None, price=None, max_side=4):
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    n = len(c)
    if n < 20:
        return []
    vol = np.asarray(volume, float) if volume is not None else np.ones(n)
    vmax = vol.max() or 1.0
    px = float(price if price else c[-1])
    atr = _atr(h, l, c) or (px * 0.01)
    tol = min(max(atr * 0.5, px * 0.006), px * 0.03)   # 존 두께: ATR기반, 0.6%~3%로 클램프

    cand = []                                        # (level, weight, kind)
    hi_idx, lo_idx = _swings(h, l, 3)
    for i in hi_idx:
        cand.append((h[i], 1.0 + 0.6 * vol[i] / vmax, "스윙고점"))
    for i in lo_idx:
        cand.append((l[i], 1.0 + 0.6 * vol[i] / vmax, "스윙저점"))

    # 볼륨 노드(매물대): 가격 히스토그램 상위 3
    lo_p, hi_p = float(l.min()), float(h.max())
    if hi_p > lo_p:
        bins = 40
        vh = np.zeros(bins)
        for i in range(n):
            b = min(bins - 1, max(0, int((c[i] - lo_p) / (hi_p - lo_p) * bins)))
            vh[b] += vol[i]
        edges = np.linspace(lo_p, hi_p, bins + 1)
        for b in np.argsort(vh)[-3:]:
            cand.append(((edges[b] + edges[b + 1]) / 2, 1.6, "매물대"))

    # 기간 고저 (52주 근사 = 전체 범위) + 최근 20봉
    cand.append((hi_p, 2.0, "기간고점"))
    cand.append((lo_p, 2.0, "기간저점"))
    cand.append((float(h[-20:].max()), 1.2, "최근고점"))
    cand.append((float(l[-20:].min()), 1.2, "최근저점"))

    # 그리드 양자화 병합(체이닝 방지 → 존 두께 = 약 tol로 제한)
    groups = {}
    for lv, w, kind in cand:
        key = round(lv / tol)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"lo": lv, "hi": lv, "wsum": 0.0, "lsum": 0.0, "kinds": set()}
        g["lo"] = min(g["lo"], lv); g["hi"] = max(g["hi"], lv)
        g["wsum"] += w; g["lsum"] += lv * w; g["kinds"].add(kind)
    clusters = list(groups.values())

    # 터치 횟수(밴드 안에 들어온 고/저). 존 두께는 [mid±tol/2]로 고정(±actual 클램프)
    zones = []
    for cl in clusters:
        mid = cl["lsum"] / cl["wsum"]
        lo_z, hi_z = mid - tol / 2, mid + tol / 2      # 균일 두께(≈tol)
        touches = int(np.sum((h >= lo_z) & (h <= hi_z)) + np.sum((l >= lo_z) & (l <= hi_z)))
        strength = cl["wsum"] + touches * 0.25
        zones.append({"lo": round(lo_z), "hi": round(hi_z), "mid": round(mid),
                      "type": "res" if mid >= px else "sup",
                      "strength_raw": strength, "touches": touches,
                      "kind": " · ".join(sorted(cl["kinds"]))})

    # 현재가에서 너무 먼 레벨은 실전 무의미 → ±40% 이내만(이전 저항은 유지)
    zones = [z for z in zones if abs(z["mid"] / px - 1.0) <= 0.40]
    if not zones:
        return []
    smax = max(z["strength_raw"] for z in zones) or 1.0
    for z in zones:
        z["strength"] = round(z.pop("strength_raw") / smax, 2)

    res = sorted([z for z in zones if z["type"] == "res"], key=lambda z: -z["strength"])[:max_side]
    sup = sorted([z for z in zones if z["type"] == "sup"], key=lambda z: -z["strength"])[:max_side]
    return sorted(res + sup, key=lambda z: -z["mid"])
