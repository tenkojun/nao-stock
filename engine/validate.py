# -*- coding: utf-8 -*-
"""
NAO STOCK — 검증 하네스 v1 (전문가 J-103/104/111/118/120 처방)
================================================================
목적: "이 결합 알고리즘이 무작위보다 나은가"를 판별하는 최소 실험.
전문가 명령: "만들기를 멈추고 검증을 시작하라" (M-139/140)

설계 (J-103 최소 골격):
  1. 파이프라인 동결 — analyze()를 그대로 호출(파라미터 변경 금지)
  2. 신호 시점 → 다음 봉 '시가' 진입(J-111) + 왕복 비용 0.40%(I-100: 매도세 0.20+수수료+슬리피지)
  3. 고정 20봉 보유 후 청산 (규칙 단순화 — 우선 신호 자체의 알파만 측정)
  4. 벤치마크: (a) 동일 종목 무작위 진입(순열검정 J-120) (b) 상시보유
  5. 캘리브레이션: prob_up_raw vs 실제 상승 빈도 (Brier, B-24)
  6. ablation 훅(J-118): 특정 Evidence 끄고 재실행 비교

정직한 한계 (전문가 지적 그대로):
  - 유니버스가 관심종목 수 개 → 통계적 유의성 불가(J-119). 이 결과는
    "예비 신호"일 뿐이며, 수백 종목 point-in-time 유니버스 확보 전엔 결론 금지.
  - KIS 일봉 조회가 최근 ~100봉 수준이면 표본이 짧음(MinTRL 미달 가능).
  - 생존편향 존재(상폐 종목 없음). purge/embargo·DSR은 v2에서.

실행:
  python engine/validate.py               # KIS 실데이터 (로컬)
  python engine/validate.py --synth       # 합성 데이터로 하네스 자체 점검
"""
from __future__ import annotations

import sys
import numpy as np

from analyze import analyze

COST = 0.004          # (구) 단일 왕복비용 — 자문 A-13에서 "대형엔 과대, 코스닥 소형엔 과소"로 지적됨.
                      # 아래 cost_for()가 종목·연도별 실비용을 쓰고, 이 값은 폴백으로만 남긴다.


def cost_for(price, market="KOSPI", marcap=None, date_str=None):
    """종목·연도별 왕복 비용률(자문 A-13). date_str='YYYYMMDD'면 그 해 세율 적용."""
    try:
        from costs import round_trip_pct, DEFAULT_YEAR
        year = int(str(date_str)[:4]) if date_str and len(str(date_str)) >= 4 else DEFAULT_YEAR
        return round_trip_pct(price, market, marcap, year)
    except Exception:
        return COST
HOLD = 20             # 고정 보유 봉수
MIN_HISTORY = 60      # 신호 평가에 필요한 최소 과거 봉수
N_PERM = 2000         # 순열검정 반복수
IC_MIN_NAMES = 30     # 횡단면 IC 최소 종목수 — 자문 A-6: N=9면 IC의 SE≈0.41로 검정 무의미.
                      # 실무 하한 30(SE≈0.19), 권장 100+(SE≈0.10). 미달 날짜는 버린다.


# ── 통계 헬퍼 (횡단면 IC 검정용, scipy 비의존) ───────────────────────
def _rankdata(a):
    """평균순위(동점 처리) — scipy.stats.rankdata 동등 구현."""
    a = np.asarray(a, float)
    sorter = np.argsort(a, kind="mergesort")
    inv = np.empty(len(a), int)
    inv[sorter] = np.arange(len(a))
    a_sorted = a[sorter]
    obs = np.r_[True, a_sorted[1:] != a_sorted[:-1]]
    dense = obs.cumsum()[inv]
    count = np.r_[np.nonzero(obs)[0], len(a)]
    return 0.5 * (count[dense] + count[dense - 1] + 1)


def _spearman(x, y):
    """스피어만 순위상관. 표본<3 또는 상수벡터면 None."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3:
        return None
    rx, ry = _rankdata(x), _rankdata(y)
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return None
    return float(np.mean((rx - rx.mean()) * (ry - ry.mean())) / (sx * sy))


def _nw_tstat(series, lag):
    """Newey-West 보정 t값 (평균이 0인가). 중첩수익발 자기상관 처리."""
    x = np.asarray(series, float)
    T = len(x)
    if T < 3:
        return None
    mu = x.mean()
    d = x - mu
    gamma0 = np.mean(d * d)
    var = gamma0
    for l in range(1, min(lag, T - 1) + 1):
        w = 1.0 - l / (lag + 1.0)
        cov = np.mean(d[l:] * d[:-l])
        var += 2.0 * w * cov
    if var <= 0:
        return None
    se = np.sqrt(var / T)
    return float(mu / se) if se > 0 else None


def _block_boot_ci(series, block, n=2000, seed=17, lo=2.5, hi=97.5):
    """이동블록 부트스트랩 — 평균의 신뢰구간(중첩 자기상관 보존)."""
    x = np.asarray(series, float)
    T = len(x)
    if T < block or block < 1:
        return None
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(T / block))
    starts_max = T - block
    means = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, starts_max + 1, nb)
        samp = np.concatenate([x[s:s + block] for s in starts])[:T]
        means[i] = samp.mean()
    return float(np.percentile(means, lo)), float(np.percentile(means, hi))


ZERO_FLOW = {"foreign_5d": 0, "org_5d": 0, "foreign_dir": "-", "org_dir": "-"}
# v1.1 정직성 수정: KIS 수급 이력이 최근 20일뿐이라 과거 시점에 '현재' 수급을 넣으면
# look-ahead 오염(J-105/110). → 과거 검증은 수급 제외(가격·추세·모멘텀 전용)로 평가하고
# 결과에 "가격 전용" 명시. 수급 포함 검증은 수급 이력 축적 후(v2).


def _frozen_signal(ohlc_upto: dict, flow: dict) -> dict:
    """파이프라인 동결 호출: 그 시점까지의 데이터만 사용 (look-ahead 금지, J-110)."""
    q = {"code": "TEST", "price": float(ohlc_upto["close"][-1]), "change_pct": 0.0}
    res = analyze(q, ohlc_upto, flow, mc_paths=0, mc_steps=HOLD)  # MC 생략(판단 미사용, H-90) → 대량검증 가속
    return res


def build_date_grid(all_dates, step=3):
    """공통 거래일 그리드 — 종목별 인덱스 샘플링은 길이가 다르면 날짜가 어긋나
    (자문 A-6/A-20 커버리지 버그). 전 종목이 '같은 날'에 샘플되도록 달력 기준으로 뽑는다."""
    ds = sorted(set(all_dates))
    return set(ds[::max(1, int(step))])


def walk_signals(ohlc: dict, flow: dict, step: int = 2, date_grid=None,
                 market="KOSPI", marcap=None):
    """시계열을 훑으며 각 시점의 동결 판정과 이후 실현수익 수집.
    date_grid가 주어지면 그 날짜(진입일)에만 샘플 → 종목 간 날짜 정렬(커버리지 보장).
    수익 = 다음봉 시가 진입 → HOLD봉 뒤 종가 청산 − 비용."""
    n = len(ohlc["close"])
    out = []
    o = {k: list(map(float, ohlc[k])) for k in ("open", "high", "low", "close", "volume")}
    dates = ohlc.get("date")                            # 있으면 진입일 태그(블록순열용)
    rng = range(MIN_HISTORY, n - HOLD - 1) if date_grid else range(MIN_HISTORY, n - HOLD - 1, step)
    for t in rng:
        if date_grid is not None:
            if not dates or t + 1 >= len(dates) or dates[t + 1] not in date_grid:
                continue
        entry = o["open"][t + 1]                       # 다음봉 시가 (J-111)
        exitp = o["close"][t + 1 + HOLD - 1]
        if entry <= 0 or exitp <= 0:                    # 정지·상폐 결측봉 방어
            continue
        upto = {k: o[k][:t + 1] for k in o}
        res = _frozen_signal(upto, flow)
        # 자문 A-13: 단일 0.40% 대신 종목(가격·시장·시총)·연도별 실비용
        cst = cost_for(entry, market, marcap, dates[t + 1] if dates and t + 1 < len(dates) else None)
        ret = (exitp / entry - 1) - cst
        out.append({
            "t": t, "signal": res["verdict"]["signal"],
            "simple3": res["verdict"]["simple3"],
            "net": res["resolved"]["net_score"],
            "prob": res.get("prob_up_raw", 0.5),
            "ret": ret, "up": 1 if ret > 0 else 0,
            "date": dates[t + 1] if dates and t + 1 < len(dates) else None,
        })
    return out


def permutation_test(sig_rets, all_rets, n_perm=N_PERM, seed=11):
    """J-120: '긍정 신호 시점의 평균수익'이 무작위 진입 분포의 상위 몇 %인가."""
    if not sig_rets:
        return None
    rng = np.random.default_rng(seed)
    obs = float(np.mean(sig_rets))
    k = len(sig_rets)
    pool = np.asarray(all_rets, float)
    null = np.array([np.mean(rng.choice(pool, k, replace=False)) for _ in range(n_perm)])
    p = float(np.mean(null >= obs))
    return {"obs_mean": obs, "null_mean": float(null.mean()),
            "p_value": p, "n_signals": k}


def brier(rows):
    """B-24: prob_up_raw의 캘리브레이션 (낮을수록 좋음, 0.25=무정보)."""
    if not rows:
        return None
    p = np.array([r["prob"] for r in rows])
    y = np.array([r["up"] for r in rows])
    return float(np.mean((p - y) ** 2))


def _stats(rows):
    if not rows:
        return None
    all_rets = [r["ret"] for r in rows]
    pos = [r["ret"] for r in rows if r["simple3"] == "긍정 관찰"]
    neg = [r["ret"] for r in rows if r["simple3"] == "주의"]
    return {
        "n_obs": len(rows), "base_mean": float(np.mean(all_rets)),
        "pos": permutation_test(pos, all_rets),
        "neg": permutation_test([-r for r in neg], [-r for r in all_rets]) if neg else None,
        "brier": brier(rows),
        "sig_counts": {s: sum(1 for r in rows if r["simple3"] == s)
                       for s in ("긍정 관찰", "중립", "주의")},
    }


def _holdout_cut(ohlc: dict) -> int:
    n_total = len(ohlc["close"])
    return MIN_HISTORY + int((n_total - MIN_HISTORY - HOLD) * 0.7)


def run_symbol(name: str, ohlc: dict, flow: dict) -> dict:
    # v1.2: 중첩(표본 많음·p 부풀림)과 비중첩(정직한 p) 병행
    # v1.3: 홀드아웃 분리(J-105) — 앞 70% 개발구간 vs 뒤 30% 홀드아웃 별도 보고
    rows_ov = walk_signals(ohlc, flow, step=2)
    rows_nv = walk_signals(ohlc, flow, step=HOLD)
    if not rows_ov:
        return {"name": name, "error": "표본 부족"}
    cut = _holdout_cut(ohlc)
    out = dict(_stats(rows_ov))
    out["name"] = name
    out["nonoverlap"] = _stats(rows_nv)
    out["holdout"] = _stats([r for r in rows_nv if r["t"] >= cut])
    out["dev"] = _stats([r for r in rows_nv if r["t"] < cut])
    # 풀링용 원시 홀드아웃 행(비중첩) — 날짜 태그 포함(횡단면 블록순열용, J-119)
    out["_holdout_rows"] = [r for r in rows_nv if r["t"] >= cut]
    # 횡단면 IC용 중첩 행(step=2) — 이미 계산됨, 재활용(추가비용 0). 개발/홀드아웃 구분.
    for r in rows_ov:
        r["holdout"] = r["t"] >= cut
    out["_ov_rows"] = rows_ov
    return out


def pooled_cross_section(rows, n_perm=N_PERM, seed=13):
    """유니버스 전체의 홀드아웃 '긍정 관찰' 수익을 풀링해 단일 순열검정(J-119).
    두 p를 병기: naive(개별 낙관적) + clustered(날짜단위 축약 — 횡단면 상관 제거)."""
    from collections import defaultdict
    rows = [r for r in rows if r.get("ret") is not None]
    if not rows:
        return None
    all_rets = [r["ret"] for r in rows]
    pos = [r["ret"] for r in rows if r["simple3"] == "긍정 관찰"]
    naive = permutation_test(pos, all_rets, n_perm, seed) if pos else None

    by_date_pos, by_date_all = defaultdict(list), defaultdict(list)
    for r in rows:
        d = r.get("date")
        if d is None:
            continue
        by_date_all[d].append(r["ret"])
        if r["simple3"] == "긍정 관찰":
            by_date_pos[d].append(r["ret"])
    clustered = None
    if by_date_pos and by_date_all:
        pos_daily = [float(np.mean(v)) for v in by_date_pos.values()]
        all_daily = np.array([float(np.mean(v)) for v in by_date_all.values()])
        k = len(pos_daily)
        if len(all_daily) >= k:
            obs = float(np.mean(pos_daily))
            rng = np.random.default_rng(seed)
            null = np.array([np.mean(rng.choice(all_daily, k, replace=False))
                             for _ in range(n_perm)])
            clustered = {"obs_mean": obs, "null_mean": float(null.mean()),
                         "p_value": float(np.mean(null >= obs)), "n_dates": k}
    return {"naive": naive, "clustered": clustered, "n_rows": len(rows),
            "n_pos": len(pos), "n_symbols": len({r.get("sym") for r in rows}),
            "pos_hit": float(np.mean([1 if r > 0 else 0 for r in pos])) if pos else None}


def cross_sectional_ic(rows, min_names=IC_MIN_NAMES):
    """일별 횡단면 Rank IC: 그날 유니버스 전 종목의 net_score vs 이후 20봉 수익 순위상관.
    반환: [(date, ic, n_names)] 오름차순. 표본을 '비중첩 이벤트'가 아니라 '거래일'로 확장(J-118·F-63)."""
    from collections import defaultdict
    by_date = defaultdict(list)
    for r in rows:
        d, ret = r.get("date"), r.get("ret")
        if d is not None and ret is not None:
            by_date[d].append((r["net"], ret))
    daily = []
    for d in sorted(by_date):
        pairs = by_date[d]
        if len(pairs) < min_names:
            continue
        ic = _spearman([p[0] for p in pairs], [p[1] for p in pairs])
        if ic is not None:
            daily.append((d, ic, len(pairs)))
    return daily


def _ic_block(daily, label):
    if not daily:
        print(f"   [{label}] 거래일 부족 — IC 산출 불가")
        return
    ics = np.array([x[1] for x in daily])
    n = len(ics)
    mean_ic = float(ics.mean())
    hit = float(np.mean(ics > 0))
    t = _nw_tstat(ics, lag=HOLD)
    ci = _block_boot_ci(ics, block=HOLD)
    line = (f"   [{label}] 거래일 {n} · 평균 IC {mean_ic:+.4f} · "
            f"IC>0 비율 {hit*100:.1f}% · 종목/일 {int(np.median([x[2] for x in daily]))}")
    print(line)
    tt = f"{t:+.2f}" if t is not None else "n/a"
    verdict = "유의 신호 가능성" if (t is not None and abs(t) >= 2) else "무정보(0과 구별 안 됨)"
    print(f"       NW t={tt} (lag={HOLD}, 중첩보정)"
          + (f" · 블록부트 95%CI [{ci[0]:+.4f}, {ci[1]:+.4f}]" if ci else "")
          + f"  → {verdict}")


def ic_report(ov_rows):
    print("\n" + "=" * 62)
    print(" NAO STOCK 횡단면 Rank IC 검증  (net_score → 이후 20봉 수익, 거래일 단위)")
    print("=" * 62)
    full = cross_sectional_ic(ov_rows)
    hold = cross_sectional_ic([r for r in ov_rows if r.get("holdout")])
    dev = cross_sectional_ic([r for r in ov_rows if not r.get("holdout")])
    print(f"  총 관측행 {len(ov_rows)} (중첩 step=2, 재활용)")
    _ic_block(full, "전체")
    _ic_block(dev, "개발 70%")
    _ic_block(hold, "홀드아웃 30%")
    print("\n  ⚠ 판정 기준: 홀드아웃 IC의 NW t (또는 블록부트 CI)로만 결론. |t|≥2 & CI가 0 제외라야 예비신호."
          "\n    IC는 중첩(20봉)이라 자기상관 → 반드시 NW/블록보정. 부호 IC>0=점수 높을수록 수익↑.")


def pooled_report(results, pooled):
    ok = [r for r in results if not r.get("error")]
    err = [r for r in results if r.get("error")]
    print("\n" + "=" * 62)
    print(" NAO STOCK 유니버스 홀드아웃 풀링 검증  (비중첩 · 다음봉시가 · 비용0.40% · 20봉)")
    print("=" * 62)
    print(f"  수집 성공 {len(ok)}종목 / 실패 {len(err)}종목")
    if err:
        print("   실패:", ", ".join(f"{e['name']}={e['error']}" for e in err[:8])
              + (" …" if len(err) > 8 else ""))
    ps = pooled_cross_section(pooled)
    if not ps:
        print("  풀링 표본 없음.")
        return
    print(f"\n  [풀링 홀드아웃] {ps['n_symbols']}종목 · 총 {ps['n_rows']}관측 · "
          f"'긍정 관찰' {ps['n_pos']}건"
          + (f" · 긍정 적중률 {ps['pos_hit']*100:.1f}%" if ps['pos_hit'] is not None else ""))
    if ps["naive"]:
        p = ps["naive"]
        print(f"   naive 순열(개별·낙관): 긍정 {p['obs_mean']*100:+.2f}% "
              f"vs 무작위 {p['null_mean']*100:+.2f}%  p={p['p_value']:.3f}")
    if ps["clustered"]:
        p = ps["clustered"]
        print(f"   clustered 순열(날짜단위·정직): 긍정일 평균 {p['obs_mean']*100:+.2f}% "
              f"vs 무작위 {p['null_mean']*100:+.2f}%  p={p['p_value']:.3f}  (거래일 {p['n_dates']})")
    print("\n  ⚠ clustered p를 1차 지표로 볼 것 — 같은 장날 여러 종목 동반등락(횡단면 상관)이"
          "\n    naive p를 부풀린다. 다중검정·생존편향·DSR은 아직 미보정(v2). 결론 금지.")


def report(results):
    print("\n" + "=" * 62)
    print(" NAO STOCK 검증 하네스 v1  (다음봉 시가 진입 · 왕복비용 0.40% · 보유 20봉)")
    print("=" * 62)
    for r in results:
        if r.get("error"):
            print(f"  {r['name']}: {r['error']}")
            continue
        print(f"\n [{r['name']}]  관측 {r['n_obs']}  신호분포 {r['sig_counts']}")
        print(f"   기저 평균수익(무작위 진입): {r['base_mean']*100:+.2f}%")
        if r["pos"]:
            p = r["pos"]
            print(f"   '긍정 관찰' 후 평균수익: {p['obs_mean']*100:+.2f}% "
                  f"(무작위 {p['null_mean']*100:+.2f}%, n={p['n_signals']}, p={p['p_value']:.3f})")
        if r["neg"]:
            p = r["neg"]
            print(f"   '주의' 후 하락 정보: p={p['p_value']:.3f} (n={p['n_signals']})")
        print(f"   Brier(미캘리브레이션 확률): {r['brier']:.3f}  (0.25=무정보)")
        nv = r.get("nonoverlap")
        if nv and nv.get("pos"):
            p = nv["pos"]
            print(f"   [비중첩 step=20 · 정직한 p] 긍정 {p['obs_mean']*100:+.2f}% "
                  f"(n={p['n_signals']}, p={p['p_value']:.3f})"
                  + (f" · 주의 p={nv['neg']['p_value']:.3f}" if nv.get("neg") else ""))
        for tag, key in (("개발 70%", "dev"), ("홀드아웃 30%", "holdout")):
            s = r.get(key)
            if s and s.get("pos"):
                p = s["pos"]
                print(f"     · {tag}: 긍정 {p['obs_mean']*100:+.2f}% (n={p['n_signals']}, p={p['p_value']:.3f})")
            elif s:
                print(f"     · {tag}: 긍정 신호 없음 (관측 {s['n_obs']})")
    print("\n ⚠ 해석 주의 (전문가 J-119): 소수 종목·짧은 표본 → 유의성 결론 금지.")
    print("   p<0.05라도 다중검정 미보정. 이 결과는 '더 큰 검증이 필요한지'의 예비 신호일 뿐.")
    print("   다음 단계: 수백 종목 유니버스 · purge/embargo 워크포워드 · DSR (v2)\n")


def _synth_universe():
    rng = np.random.default_rng(3)
    out = []
    for i, name in enumerate(["추세상승주", "횡보주", "하락주"]):
        drift = [0.0012, 0.0, -0.0012][i]
        r = rng.standard_normal(400) * 0.02 + drift
        c = 50000 * np.exp(np.cumsum(r))
        ohlc = {"close": c.tolist(), "high": (c * 1.012).tolist(),
                "low": (c * 0.988).tolist(),
                "open": np.roll(c, 1).tolist(),
                "volume": (rng.random(400) * 1e6 + 3e5).tolist()}
        flow = {"foreign_5d": float(rng.standard_normal() * 2e5),
                "org_5d": float(rng.standard_normal() * 2e5),
                "foreign_dir": "-", "org_dir": "-"}
        out.append((name, ohlc, flow))
    return out


def build_universe(kis, size=50, source="volume"):
    """주도주 자동 유니버스(J-119). source: volume(거래대금)·fluct(등락률)·both."""
    seen, uni = set(), []

    def add(items):
        for x in items or []:
            c = str(x.get("code", ""))
            if len(c) == 6 and c.isdigit() and c not in seen:
                seen.add(c)
                uni.append((c, x.get("name", c)))
    try:
        if source in ("volume", "both"):
            add(kis.ranking_volume(top=30))
        if source in ("fluct", "both"):
            add(kis.ranking_fluctuation(top=30, rise=True))
    except Exception as e:
        print(f"  유니버스 조회 오류: {str(e)[:60]}")
    return uni[:size]


def _argval(flag, default=None, cast=str):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return cast(sys.argv[i + 1])
    return default


EV_HORIZONS = (5, 10, 20, 60)


def walk_evidence(ohlc, step, horizons=EV_HORIZONS, date_grid=None):
    """각 시점의 개별 증거값 + 다지평 선도수익 수집(primitive-discovery, J-118·F-63).
    반환행: {date, ev:{source:dir*mag}, r5,r10,r20,r60}. 비용 생략(IC는 순위라 상수무관)."""
    o = {k: list(map(float, ohlc[k])) for k in ("open", "high", "low", "close", "volume")}
    dates = ohlc.get("date")
    n = len(o["close"])
    hmax = max(horizons)
    out = []
    rng = range(MIN_HISTORY, n - hmax - 1) if date_grid else range(MIN_HISTORY, n - hmax - 1, step)
    for t in rng:
        if date_grid is not None:
            if not dates or t + 1 >= len(dates) or dates[t + 1] not in date_grid:
                continue
        entry = o["open"][t + 1]
        if entry <= 0:
            continue
        upto = {k: o[k][:t + 1] for k in o}
        res = _frozen_signal(upto, ZERO_FLOW)
        row = {"date": dates[t + 1] if dates and t + 1 < len(dates) else None,
               "ev": res.get("evidence", {})}
        ok = True
        for h in horizons:
            exitp = o["close"][t + h]
            if exitp <= 0:
                ok = False
                break
            row["r%d" % h] = exitp / entry - 1
        if ok and row["date"] is not None:
            out.append(row)
    return out


def per_evidence_ic(panel, horizons=EV_HORIZONS, min_names=IC_MIN_NAMES):
    """증거 × 지평별 횡단면 Rank IC + NW t. panel행: {date, ev, r{h}} (+sym는 무관)."""
    from collections import defaultdict
    sources = set()
    for r in panel:
        sources.update(r["ev"].keys())
    result = {}
    for src in sorted(sources):
        result[src] = {}
        for h in horizons:
            key = "r%d" % h
            by_date = defaultdict(list)
            for r in panel:
                v = r["ev"].get(src)
                ret = r.get(key)
                if v is not None and ret is not None:
                    by_date[r["date"]].append((v, ret))
            ics = []
            for d in by_date:
                pairs = by_date[d]
                if len(pairs) < min_names:
                    continue
                ic = _spearman([p[0] for p in pairs], [p[1] for p in pairs])
                if ic is not None:
                    ics.append(ic)
            if ics:
                ics = np.array(ics)
                result[src][h] = (float(ics.mean()), _nw_tstat(ics, lag=h), len(ics))
            else:
                result[src][h] = (float("nan"), None, 0)
    return result


def quantile_backtest(panel, source, h=20, q=0.2, cost=COST, gap_days=28):
    """비중첩 h일 리밸런스 롱숏 분위 백테스트(비용 반영, I-100).
    상위 q 분위(증거값 큼) 매수 − 하위 q 분위 매도. 부호 IC>0이면 롱숏 양(+)이어야."""
    from collections import defaultdict
    from datetime import datetime
    key = "r%d" % h
    by_date = defaultdict(list)
    for r in panel:
        v = r["ev"].get(source)
        ret = r.get(key)
        if v is not None and ret is not None:
            by_date[r["date"]].append((v, ret))
    dates = sorted(by_date)
    # 비중첩 리밸런스일 선택: 직전 선택일로부터 gap_days(≈h거래일) 이상 경과
    picks, last = [], None
    for d in dates:
        dt = datetime.strptime(d, "%Y%m%d")
        if last is None or (dt - last).days >= gap_days:
            if len(by_date[d]) >= 10:               # 분위 형성 최소 종목수
                picks.append(d)
                last = dt
    ls_net, long_net = [], []
    for d in picks:
        pairs = sorted(by_date[d], key=lambda p: p[0])
        n = len(pairs)
        k = max(1, int(n * q))
        low = pairs[:k]           # 증거값 낮음(과매수 쪽)
        high = pairs[-k:]         # 증거값 높음(과매도 쪽)
        r_high = np.mean([p[1] for p in high])
        r_low = np.mean([p[1] for p in low])
        ls_net.append((r_high - r_low) - 2 * cost)   # 롱숏: 양다리 왕복비용
        long_net.append(r_high - cost)               # 롱온리: 상위분위 − 비용
    if len(ls_net) < 5:
        return None
    ls = np.asarray(ls_net); lo = np.asarray(long_net)
    per_yr = 252.0 / h
    def _ann(x):
        m = x.mean(); s = x.std(ddof=1)
        sharpe = (m / s * np.sqrt(per_yr)) if s > 0 else float("nan")
        t = (m / (s / np.sqrt(len(x)))) if s > 0 else float("nan")
        return m, m * per_yr, sharpe, t
    return {"n_rebal": len(ls), "ls": _ann(ls), "long": _ann(lo)}


def evidence_report(panel, horizons=EV_HORIZONS):
    print("\n" + "=" * 72)
    print(" NAO STOCK 개별 증거 IC 매트릭스  (증거값 → 선도수익, 거래일 횡단면, NW t)")
    print("=" * 72)
    if not panel:
        print("  패널 비어있음.")
        return
    res = per_evidence_ic(panel, horizons)
    hdr = "  {:<20}".format("증거\\지평") + "".join(f"{h:>14}일" for h in horizons)
    print(hdr)
    print("  " + "-" * (18 + 15 * len(horizons)))
    for src in sorted(res):
        cells = []
        for h in horizons:
            ic, t, nd = res[src][h]
            if t is None:
                cells.append(f"{'  n/a':>15}")
            else:
                star = "*" if abs(t) >= 2 else " "
                cells.append(f"{ic:+.3f}/t{t:+.1f}{star}".rjust(15))
        print(f"  {src:<20}" + "".join(cells))
    print("\n  * = |NW t|≥2 (예비신호 후보). IC 부호: +면 증거값 클수록 수익↑ (증거가 방향을 맞춤).")
    print("    음수 유의 = 역방향(증거가 거꾸로). 다중검정(증거×지평 다수) 미보정 — DSR 필요(J-106).")

    # 비용 반영 실전성 테스트(I-100): 지평별 롱숏 분위 백테스트 (장기보유=비용 1회/보유기간)
    print("\n" + "=" * 72)
    print(" 비용 반영 롱숏 분위 백테스트  (비중첩 H일 리밸런스=보유 · 왕복 0.40%/leg · 상하위 20%)")
    print(" → 장기보유 관점: H 클수록 비용이 희석. 각 증거가 어느 보유기간에 유효한지 확인")
    print("=" * 72)
    for src in sorted(res):
        # 지평 중 하나라도 IC 유의하면 백테스트
        if not any((res[src].get(h, (0, None, 0))[1] or 0) and abs(res[src][h][1]) >= 2
                   for h in horizons):
            continue
        print(f"  [{src}]")
        for h in horizons:
            bt = quantile_backtest(panel, src, h=h, gap_days=int(h * 1.45) + 2)
            if not bt:
                continue
            lm, lann, lsh, lt = bt["ls"]
            gm, gann, gsh, gt = bt["long"]
            print(f"    H={h:>3}일 (리밸 {bt['n_rebal']:>3}회): "
                  f"롱숏 회당 {lm*100:+.2f}%·연 {lann*100:+.1f}%·Sh {lsh:+.2f}·t{lt:+.2f}  |  "
                  f"롱온리 연 {gann*100:+.1f}%·Sh {gsh:+.2f}·t{gt:+.2f}")
    print("\n  ⚠ 롱숏 Sharpe>0.5 & t≥2라야 실전 후보(롱온리 연수익은 시장베타 착시 주의).")
    print("    DSR(J-106)·생존편향 잔여·슬리피지 추가고려. 장기보유는 H=120/250 컬럼이 장기보유 용도에 근접.")


def _run_fdr():
    """point-in-time·상폐포함 유니버스로 IC 검증 (J-109). FDR 소스."""
    import time
    from fdr_adapter import build_pit_universe, load_ohlcv
    start = _argval("--start", "20190101")
    end = _argval("--end", None) or __import__("datetime").datetime.now().strftime("%Y%m%d")
    top = _argval("--top", 120, int)
    step = _argval("--step", 3, int)
    incl_del = "--no-delisted" not in sys.argv
    ev_mode = "--evidence" in sys.argv        # 개별 증거 IC 매트릭스(primitive-discovery)
    hz = _argval("--horizons", None)
    horizons = tuple(int(x) for x in hz.split(",")) if hz else EV_HORIZONS
    universe = build_pit_universe(start, top_n=top, include_delisted=incl_del)

    results, pooled, ov_pool, ev_panel = [], [], [], []
    min_bars = MIN_HISTORY + max(max(horizons), HOLD) + 30
    ok = skip = 0
    # ① 전 종목 선적재 → ② 공통 거래일 그리드 구축(자문 A-6: 인덱스 샘플링은 날짜가 어긋남)
    loaded = []
    alldates = set()
    for i, (code, name) in enumerate(universe):
        ohlc = load_ohlcv(code, start, end)
        if not ohlc or len(ohlc["close"]) < min_bars:
            skip += 1
            continue
        loaded.append((code, name, ohlc))
        alldates.update(ohlc.get("date") or [])
        if (i + 1) % 50 == 0:
            print(f"    …적재 {i+1}/{len(universe)} (수집 {len(loaded)}, 제외 {skip})")
    grid = build_date_grid(alldates, step)
    print(f"  [FDR] 적재 {len(loaded)}종목 · 공통 거래일 그리드 {len(grid)}일(step={step})")

    for i, (code, name, ohlc) in enumerate(loaded):
        if ev_mode:
            ev_panel.extend(walk_evidence(ohlc, step, horizons, date_grid=grid))
        else:
            r = run_symbol_fast(f"{name}({code})", ohlc, step, date_grid=grid)
            for orow in r.pop("_ov_rows", []):
                orow["sym"] = code
                ov_pool.append(orow)
            for hr in r.pop("_holdout_rows", []):
                hr["sym"] = code
                pooled.append(hr)
            results.append(r)
        ok += 1
        if (i + 1) % 25 == 0:
            print(f"    …{i+1}/{len(universe)} 처리 (수집 {ok}, 제외 {skip})")
        time.sleep(0.05)
    print(f"  [FDR] 수집 {ok}종목 / 데이터부족·상폐무데이터 제외 {skip}")
    if ev_mode:
        evidence_report(ev_panel, horizons)
    else:
        ic_report(ov_pool)
        pooled_report(results, pooled)


def run_symbol_fast(name, ohlc, step, date_grid=None):
    """IC 대량검증용 경량 run_symbol: 중첩(step) 워크 1회만, 종목별 상세통계 생략."""
    rows = walk_signals(ohlc, flow=ZERO_FLOW, step=step, date_grid=date_grid)
    if not rows:
        return {"name": name, "error": "표본부족", "_ov_rows": [], "_holdout_rows": []}
    cut = _holdout_cut(ohlc)
    for r in rows:
        r["holdout"] = r["t"] >= cut
    # 비중첩 홀드아웃(풀링 이벤트스터디용)은 step 배수로 근사 추출
    nv = [r for r in rows if r["holdout"] and (r["t"] % HOLD == 0)]
    return {"name": name, "_ov_rows": rows, "_holdout_rows": nv}


def main():
    if "--synth" in sys.argv:
        report([run_symbol(n, o, f) for n, o, f in _synth_universe()])
        return
    if "--fdr" in sys.argv:
        _run_fdr()
        return

    import time
    from kis_kr import KISKorea
    kis = KISKorea()

    uni_n = _argval("--universe", None, int)
    source = _argval("--source", "volume")
    if uni_n:
        if uni_n > 30 and source == "volume":
            source = "both"
        universe = build_universe(kis, uni_n, source)
        print(f"  유니버스 자동구성: {source} 상위 {len(universe)}종목 (거래대금/등락률 주도주)")
    else:
        universe = [("005930", "삼성전자"), ("000660", "SK하이닉스"),
                    ("035420", "NAVER"), ("005380", "현대차"),
                    ("035720", "카카오"), ("247540", "에코프로비엠")]

    results, pooled, ov_pool = [], [], []
    min_bars = MIN_HISTORY + HOLD + 30
    for code, name in universe:
        for attempt in range(3):               # EGW00201 초당 제한 → 재시도
            try:
                rows = kis.daily_ohlcv_long(code, 600)   # 장기 이력(청크 수집)
                if len(rows) < min_bars:
                    results.append({"name": f"{name}({code})",
                                    "error": f"표본부족 {len(rows)}봉"})
                    break
                keys = ("open", "high", "low", "close", "volume")
                ohlc = {k: [float(r[k]) for r in rows] for k in keys}
                ohlc["date"] = [r["date"] for r in rows]
                if not uni_n:
                    print(f"  {name}: 일봉 {len(rows)}봉 (가격 전용 — 수급은 v2)")
                r = run_symbol(f"{name}({code})", ohlc, ZERO_FLOW)
                for hr in r.pop("_holdout_rows", []):
                    hr["sym"] = code
                    pooled.append(hr)
                for orow in r.pop("_ov_rows", []):
                    orow["sym"] = code
                    ov_pool.append(orow)
                results.append(r)
                break
            except Exception as e:
                if "EGW00201" in str(e) and attempt < 2:
                    time.sleep(1.5)
                    continue
                results.append({"name": f"{name}({code})", "error": str(e)[:60]})
                break
        time.sleep(0.3)

    if uni_n:
        ic_report(ov_pool)                     # 1차: 횡단면 IC (거래일 단위·고검정력)
        pooled_report(results, pooled)         # 2차: 이벤트스터디 풀링(교차확인)
    else:
        report(results)                        # 소수 고정: 종목별 상세
        if pooled:
            pooled_report(results, pooled)


if __name__ == "__main__":
    main()
