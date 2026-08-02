# -*- coding: utf-8 -*-
"""
진입 타이밍 요인 검증 (Phase 1b) — "지금 가격이 낮은가/눌림목인가"
======================================================================
아버지 니즈: 한국장 변동성이 크니 최대한 낮은 타이밍에 잡기. 보유 1~3개월~1년.
→ 단기 평균회귀·눌림목 요인들을 여러 개 만들어, 짧은 지평(10/20/40/60일)에서
   횡단면 Rank IC로 검증. 통과분만 앱 '진입 적정도'에 편입.

모든 요인은 관례상 **"높을수록 진입 매력(=오를 것으로 가설)"** 방향으로 부호 정렬.
→ IC>0 이면 요인이 방향을 맞춤. look-ahead 없음(시점 t까지 데이터만).

실행: python engine/timing_factors.py [--start YYYYMMDD] [--top N] [--step K]
"""
from __future__ import annotations
import sys
import numpy as np

from validate import (_spearman, _nw_tstat, _block_boot_ci, _argval,
                      IC_MIN_NAMES, MIN_HISTORY)


def _rsi(c, n=14):
    d = np.diff(c)
    if len(d) < n:
        return 50.0
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    au = np.mean(up[-n:]); ad = np.mean(dn[-n:])
    if ad == 0:
        return 100.0 if au > 0 else 50.0
    rs = au / ad
    return 100 - 100 / (1 + rs)


def factors_at(c, h, l):
    """시점 t(마지막봉)까지의 close/high/low 배열로 진입타이밍 요인들 계산.
    부호: 높을수록 '진입 매력'(오를 것으로 가설)."""
    c = np.asarray(c, float)
    n = len(c)
    if n < 65:
        return None
    px = c[-1]
    ma20 = c[-20:].mean()
    ma60 = c[-60:].mean()
    sd20 = c[-20:].std()
    hi60 = np.max(h[-60:])
    out = {}
    # 1) 과매도(RSI): 낮은 RSI일수록 매력 → (50-RSI)
    out["oversold_rsi"] = (50.0 - _rsi(c)) / 50.0
    # 2) 이동평균 이격(20일): MA 아래일수록 매력 → -(px/ma20-1)
    out["below_ma20"] = -(px / ma20 - 1.0) if ma20 > 0 else 0.0
    # 3) 단기 반전(5일 과거수익): 최근 하락일수록 매력 → -ret5
    out["reversal_5"] = -(px / c[-6] - 1.0) if n >= 6 and c[-6] > 0 else 0.0
    # 4) 중기 반전(20일): -ret20
    out["reversal_20"] = -(px / c[-21] - 1.0) if n >= 21 and c[-21] > 0 else 0.0
    # 5) 고점대비 낙폭(60일): 깊을수록 매력 → -(px/hi60-1) (0~+)
    out["drawdown_60"] = -(px / hi60 - 1.0) if hi60 > 0 else 0.0
    # 6) 볼린저 하단 이격(z): 밴드 아래일수록 매력 → -(px-ma20)/sd20
    out["boll_z"] = -((px - ma20) / sd20) if sd20 > 0 else 0.0
    # 7) 추세 속 눌림목: 상승추세(ma20>ma60)에서 단기 눌림(below_ma20)일 때만
    uptrend = 1.0 if ma20 > ma60 else 0.0
    out["pullback_uptrend"] = out["below_ma20"] * uptrend
    # 8~10) 모멘텀(장기보유용, Jegadeesh-Titman): 과거 수익이 높을수록 매력(승자지속 가설)
    #    최근 1개월 제외(단기반전 회피). 부호+ = 강한 종목일수록 이후 수익↑ 기대.
    if n >= 260:
        out["mom_12_1"] = c[-21] / c[-252] - 1.0 if c[-252] > 0 else 0.0   # 12-1개월
    if n >= 140:
        out["mom_6_1"] = c[-21] / c[-126] - 1.0 if c[-126] > 0 else 0.0    # 6-1개월
    out["near_high_60"] = px / hi60 - 1.0 if hi60 > 0 else 0.0             # 60일 고점 근접(+=고점부근)
    return out


def walk_factors(ohlc, step, horizons, date_grid=None, delist=None, discount=None):
    """delist={'type':...} 가 주어지면 상폐로 지평이 끊긴 진입도 **최종 수익률로 평가**
    (자문 A-8: 지금까지는 t+h가 없으면 통째로 버려 최악의 결과가 누락됐음)."""
    o = {k: np.asarray(ohlc[k], float) for k in ("high", "low", "close")}
    dates = ohlc.get("date")
    n = len(o["close"])
    hmax = max(horizons)
    rows = []
    # 상폐 종목이면 마지막 봉까지 진입을 허용하고, 지평이 끊긴 부분은 최종수익률로 평가
    dl_type = (delist or {}).get("type") if delist else None
    tradeable_end = (n - 2) if dl_type in ("distress", "unknown") else (n - hmax - 1)
    rng = range(MIN_HISTORY, max(MIN_HISTORY, tradeable_end)) if date_grid \
        else range(MIN_HISTORY, max(MIN_HISTORY, tradeable_end), step)
    last_px = float(o["close"][-1]) if n else 0.0
    for t in rng:
        if date_grid is not None:                 # 공통 거래일 그리드(자문 A-6 커버리지)
            if dates is None or t + 1 >= len(dates) or dates[t + 1] not in date_grid:
                continue
        entry = ohlc["open"][t + 1] if t + 1 < len(ohlc["open"]) else o["close"][t]
        entry = float(entry)
        if entry <= 0:
            continue
        f = factors_at(o["close"][:t + 1], o["high"][:t + 1], o["low"][:t + 1])
        if f is None:
            continue
        row = {"date": dates[t + 1] if dates and t + 1 < len(dates) else None, "f": f}
        ok = True
        for hh in horizons:
            if t + hh < n:
                ex = o["close"][t + hh]
                if ex <= 0:
                    ok = False
                    break
                row["r%d" % hh] = ex / entry - 1
            elif dl_type:                         # 상폐로 지평 미달 → 최종 수익률(자문 A-8)
                from delisting import terminal_return, DISCOUNT_DEFAULT
                tr = terminal_return(entry, last_px, dl_type,
                                     DISCOUNT_DEFAULT if discount is None else discount)
                if tr is None:                    # 합병·비주식 → 평가 불가, 제외
                    ok = False
                    break
                row["r%d" % hh] = tr
            else:
                ok = False
                break
        if ok and row["date"] is not None:
            rows.append(row)
    return rows


def factor_ic(panel, horizons, min_names=IC_MIN_NAMES):
    from collections import defaultdict
    srcs = set()
    for r in panel:
        srcs.update(r["f"].keys())
    res = {}
    for s in sorted(srcs):
        res[s] = {}
        for hh in horizons:
            key = "r%d" % hh
            byd = defaultdict(list)
            for r in panel:
                v = r["f"].get(s); ret = r.get(key)
                if v is not None and ret is not None:
                    byd[r["date"]].append((v, ret))
            ics = []
            for d in byd:
                p = byd[d]
                if len(p) < min_names:
                    continue
                ic = _spearman([x[0] for x in p], [x[1] for x in p])
                if ic is not None:
                    ics.append(ic)
            if ics:
                ics = np.array(ics)
                ci = _block_boot_ci(ics, block=hh)
                res[s][hh] = (float(ics.mean()), _nw_tstat(ics, hh), len(ics), ci)
            else:
                res[s][hh] = (float("nan"), None, 0, None)
    return res


def main():
    from fdr_adapter import build_pit_universe, load_ohlcv
    start = _argval("--start", "20190101")
    end = __import__("datetime").datetime.now().strftime("%Y%m%d")
    top = _argval("--top", 150, int)
    step = _argval("--step", 3, int)
    hz = _argval("--horizons", None)
    horizons = tuple(int(x) for x in hz.split(",")) if hz else (10, 20, 40, 60)
    incl = "--no-delisted" not in sys.argv
    # --krx: KRX OPEN API로 **연 1회 리밸런싱 진짜 PIT 유니버스**(자문 A-9 근본 해결)
    krx_mode = "--krx" in sys.argv
    member = None
    if krx_mode:
        from krx_api import yearly_universes, membership_map
        y0, y1 = int(start[:4]), int(end[:4])
        print(f"  [KRX PIT] {y0}~{y1} 연 1회 리밸런싱 유니버스 구성 중…")
        yearly = yearly_universes(y0, y1, top_n=top)
        member = membership_map(yearly)
        names = {}
        for rows in yearly.values():
            for r in rows:
                names.setdefault(r["code"], r["name"])
        uni = [(c, names.get(c, c)) for c in member]
        print(f"  [KRX PIT] 합집합 {len(uni)}종목 (연도별 소속 이력 보유)")
    else:
        uni = build_pit_universe(start, top_n=top, include_delisted=incl)
    panel = []
    ok = skip = 0
    minb = 260 + max(horizons) + 10   # 모멘텀 12-1개월 룩백(252) + 지평 여유
    # 전 종목 선적재 → 공통 거래일 그리드(자문 A-6: 인덱스 샘플링은 종목 간 날짜가 어긋남)
    from validate import build_date_grid
    from delisting import delist_map, summarize, DISCOUNT_DEFAULT
    dmap = delist_map()                      # 자문 A-8: 상폐 사유별 처리
    disc = _argval("--discount", DISCOUNT_DEFAULT, float)
    loaded, alldates = [], set()
    for i, (code, name) in enumerate(uni):
        d = load_ohlcv(code, start, end)
        if not d or len(d["close"]) < minb:
            skip += 1
            continue
        loaded.append((code, d)); alldates.update(d.get("date") or [])
        if (i + 1) % 50 == 0:
            print(f"    …적재 {i+1}/{len(uni)} (수집 {len(loaded)}, 제외 {skip})")
    grid = build_date_grid(alldates, step)
    dl_in = {c: dmap[c] for c, _ in loaded if c in dmap}
    print(f"  적재 {len(loaded)}종목 · 그리드 {len(grid)}일 · 상폐 {len(dl_in)}종목 {summarize(dl_in)}")
    print(f"  상폐 최종수익률 할인율 {disc:+.0%} (합병·비주식은 표본에서 제외)")
    for code, d in loaded:
        rows = walk_factors(d, step, horizons, date_grid=grid,
                            delist=dmap.get(code), discount=disc)
        if member is not None:                 # 그 해 유니버스 소속일 때만 유효(진짜 PIT)
            ys = member.get(code, set())
            rows = [r for r in rows if r.get("date") and int(r["date"][:4]) in ys]
        panel.extend(rows)
        ok += 1
    print(f"  수집 {ok}종목 / 제외 {skip} · 패널행 {len(panel)}")

    res = factor_ic(panel, horizons)
    # 다중검정 보정(A-10)용 결과 덤프
    try:
        import json, os
        tag = "krx_pit" if "--krx" in sys.argv else \
              ("no_delisted" if "--no-delisted" in sys.argv else "with_delisted")
        dump = {"tag": tag, "start": start, "top": top, "step": step,
                "horizons": list(horizons), "n_rows": len(panel),
                "cells": [{"factor": s, "h": hh, "ic": res[s][hh][0],
                           "t": res[s][hh][1], "days": res[s][hh][2]}
                          for s in sorted(res) for hh in horizons
                          if res[s][hh][1] is not None]}
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "docs", f"요인IC_{tag}.json")
        with open(p, "w", encoding="utf-8") as fp:
            json.dump(dump, fp, ensure_ascii=False, indent=1)
        print(f"  [덤프] {p}")
    except Exception as e:
        print("  덤프 실패:", str(e)[:60])
    print("\n" + "=" * 78)
    print(" 진입 타이밍 요인 IC  (요인값 → 이후 보유수익, 거래일 횡단면, NW t · 부호+=요인이 맞음)")
    print("=" * 78)
    print("  {:<18}".format("요인\\보유일") + "".join(f"{h:>16}일" for h in horizons))
    print("  " + "-" * (16 + 17 * len(horizons)))
    for s in sorted(res):
        cells = []
        for hh in horizons:
            ic, t, nd, ci = res[s][hh]
            if t is None:
                cells.append(f"{'n/a':>17}")
            else:
                star = "*" if abs(t) >= 2 else " "
                cells.append(f"{ic:+.3f}/t{t:+.1f}{star}".rjust(17))
        print(f"  {s:<18}" + "".join(cells))
    print("\n  * = |NW t|≥2. 부호+ = '요인 높을수록(=더 과매도/눌림) 이후 수익↑' = 진입타이밍 유효.")
    print("    다중검정(요인×지평) 미보정 — 여러 지평 일관+|t|≥2.5 정도라야 신뢰. 비용 후속검증 필요.")


if __name__ == "__main__":
    main()
