# -*- coding: utf-8 -*-
"""
중립화 재검정 (자문 B-27/B-28) — near_high_60은 진짜 모멘텀인가, 대리변수인가
==============================================================================
자문 원문 요지:
  "각 시점에서 near_high_60을 (a)시장 베타 (b)로그 시총 (c)60일 실현변동성 (d)산업 더미에
   회귀하고 **잔차만으로 IC를 재계산**하십시오. 잔차 IC가 절반 이하로 줄면 대리변수 판정입니다.
   제 예상은 t3.5 → t1.0~1.5입니다."
배경: 한국은 모멘텀이 약하거나 음수라는 문헌이 다수(Chui-Titman-Wei 2010 등).
      우리 양(+) 결과는 유니버스 look-ahead(A-9)와 베타 노출로 설명될 수 있음.

실행: python engine/neutralize_test.py [--start 20180101] [--top 150] [--step 5]
"""
from __future__ import annotations
import sys
from collections import defaultdict

import numpy as np

from validate import _spearman, _nw_tstat, _argval, build_date_grid, MIN_HISTORY

HORIZONS = (20, 60, 120, 250)
LOOKBACK_BETA = 120


def _sectors_map():
    try:
        from discover import _sectors
        return _sectors()
    except Exception:
        return {}


def _shares_map():
    """상장주식수(시총 계산용). 없으면 None."""
    try:
        import FinanceDataReader as fdr
        d = fdr.StockListing("KRX")
        return {str(r["Code"]).zfill(6): float(r.get("Stocks") or 0) for _, r in d.iterrows()}
    except Exception:
        return {}


def _kospi_returns():
    import FinanceDataReader as fdr
    d = fdr.DataReader("KS11")
    c = d["Close"].to_numpy(float)
    dates = [x.strftime("%Y%m%d") for x in d.index]
    r = np.diff(np.log(np.maximum(c, 1e-9)))
    return {dates[i + 1]: float(r[i]) for i in range(len(r))}


def build_panel(start, end, top, step, incl_del=True):
    from fdr_adapter import build_pit_universe, load_ohlcv
    uni = build_pit_universe(start, top_n=top, include_delisted=incl_del)
    sect, shares, mkt = _sectors_map(), _shares_map(), _kospi_returns()
    hmax = max(HORIZONS)
    minb = MIN_HISTORY + hmax + LOOKBACK_BETA + 10
    loaded, alldates = [], set()
    skip = 0
    for i, (code, name) in enumerate(uni):
        d = load_ohlcv(code, start, end)
        if not d or len(d["close"]) < minb:
            skip += 1
            continue
        loaded.append((code, d))
        alldates.update(d["date"])
        if (i + 1) % 50 == 0:
            print(f"    …적재 {i+1}/{len(uni)} (수집 {len(loaded)}, 제외 {skip})")
    grid = build_date_grid(alldates, step)
    print(f"  적재 {len(loaded)}종목 · 그리드 {len(grid)}일")

    rows = []
    for code, d in loaded:
        c = np.asarray(d["close"], float)
        h = np.asarray(d["high"], float)
        dates = d["date"]
        n = len(c)
        lr = np.diff(np.log(np.maximum(c, 1e-9)))
        sh = shares.get(code, 0.0)
        sec = sect.get(code, "기타")
        for t in range(max(MIN_HISTORY, LOOKBACK_BETA), n - hmax - 1):
            dt = dates[t + 1] if t + 1 < len(dates) else None
            if dt is None or dt not in grid:
                continue
            entry = float(d["open"][t + 1])
            if entry <= 0:
                continue
            hi60 = float(np.max(h[t - 59:t + 1]))
            if hi60 <= 0:
                continue
            f = float(c[t]) / hi60 - 1.0                       # near_high_60
            win = lr[max(0, t - LOOKBACK_BETA):t]              # 베타·변동성
            if len(win) < 40:
                continue
            vol = float(np.std(win) * np.sqrt(252))
            mr = np.array([mkt.get(dates[j], 0.0) for j in range(max(1, t - len(win)), t)], float)
            m = min(len(mr), len(win))
            beta = float(np.cov(win[-m:], mr[-m:])[0, 1] / (np.var(mr[-m:]) + 1e-12)) if m > 20 else 1.0
            beta = max(-1.0, min(3.0, beta))
            cap = float(c[t]) * sh if sh else 0.0
            row = {"date": dt, "code": code, "f": f, "beta": beta, "vol": vol,
                   "lcap": float(np.log(cap)) if cap > 0 else None, "sector": sec}
            ok = True
            for hh in HORIZONS:
                ex = float(c[t + hh])
                if ex <= 0:
                    ok = False
                    break
                row["r%d" % hh] = ex / entry - 1
            if ok:
                rows.append(row)
    return rows


def _resid(F, X):
    """F를 X(상수 포함)에 회귀한 잔차."""
    beta, *_ = np.linalg.lstsq(X, F, rcond=None)
    return F - X @ beta


def ic_raw_vs_neutral(rows, min_names=30):
    by = defaultdict(list)
    for r in rows:
        by[r["date"]].append(r)
    out = {h: {"raw": [], "neu": []} for h in HORIZONS}
    used = 0
    for dt, grp in by.items():
        grp = [g for g in grp if g["lcap"] is not None]
        if len(grp) < min_names:
            continue
        used += 1
        F = np.array([g["f"] for g in grp], float)
        secs = sorted({g["sector"] for g in grp})
        cols = [np.ones(len(grp)),
                np.array([g["beta"] for g in grp], float),
                np.array([g["lcap"] for g in grp], float),
                np.array([g["vol"] for g in grp], float)]
        for s in secs[:-1]:                                    # 산업 더미(마지막은 기준)
            cols.append(np.array([1.0 if g["sector"] == s else 0.0 for g in grp]))
        X = np.column_stack(cols)
        try:
            Fn = _resid(F, X)
        except Exception:
            continue
        for hh in HORIZONS:
            R = np.array([g["r%d" % hh] for g in grp], float)
            a = _spearman(F, R)
            b = _spearman(Fn, R)
            if a is not None:
                out[hh]["raw"].append(a)
            if b is not None:
                out[hh]["neu"].append(b)
    return out, used


def report(res, used):
    print("\n" + "=" * 74)
    print(" near_high_60 중립화 재검정 (원본 vs 베타·시총·변동성·산업 통제 후 잔차)")
    print("=" * 74)
    print(f"  사용 거래일 {used}일 (일별 최소 30종목)")
    print(f"  {'보유일':<8}{'원본 IC':>12}{'원본 t':>9}{'잔차 IC':>12}{'잔차 t':>9}{'감소율':>9}")
    print("  " + "-" * 62)
    verdict = []
    for h in HORIZONS:
        raw, neu = np.array(res[h]["raw"]), np.array(res[h]["neu"])
        if len(raw) < 10 or len(neu) < 10:
            print(f"  {h:<8}{'표본부족':>12}")
            continue
        tr, tn = _nw_tstat(raw, h), _nw_tstat(neu, h)
        drop = (1 - abs(neu.mean()) / max(abs(raw.mean()), 1e-9)) * 100
        print(f"  {h:<8}{raw.mean():>+12.4f}{tr:>+9.2f}{neu.mean():>+12.4f}{tn:>+9.2f}{drop:>8.0f}%")
        verdict.append((h, tr, tn, drop))
    print("\n  판정 기준(자문 B-27): 잔차 IC가 원본의 절반 이하로 줄면 **대리변수**(진짜 모멘텀 아님).")
    big = [v for v in verdict if v[3] >= 50]
    if big:
        print(f"  → {len(big)}/{len(verdict)} 지평에서 50% 이상 감소 — 베타·시총·변동성·산업으로 설명되는 부분이 큼.")
    strong = [v for v in verdict if abs(v[2]) >= 2]
    print(f"  → 중립화 후에도 |t|≥2인 지평: {len(strong)}/{len(verdict)}")


def main():
    start = _argval("--start", "20180101")
    end = _argval("--end", None) or __import__("datetime").datetime.now().strftime("%Y%m%d")
    top = _argval("--top", 150, int)
    step = _argval("--step", 5, int)
    rows = build_panel(start, end, top, step, "--no-delisted" not in sys.argv)
    print(f"  패널행 {len(rows)}")
    res, used = ic_raw_vs_neutral(rows)
    report(res, used)


if __name__ == "__main__":
    main()
