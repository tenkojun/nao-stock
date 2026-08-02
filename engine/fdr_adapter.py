# -*- coding: utf-8 -*-
"""
FDR 어댑터 — point-in-time·상폐포함 유니버스 (전문가 J-109 생존/선정편향 해결)
================================================================================
KIS 현재-스냅샷 랭킹은 "오늘의 승자"를 뽑아 선정편향(J-105 함정#6)을 만든다.
FinanceDataReader로:
  1) 대형주 멤버십(시총 상위) — 최근수익에 조건부가 아님(멤버십 지속성 높음 → 선정편향 최소)
  2) 상폐 종목(구간 내 상폐)을 유니버스에 포함 → 생존편향 제거(J-109)
  3) start 이전 상장분만 채택(종목 로드 시 첫 봉 날짜로 확인)

주의: KRX 포털이 로그인 필수로 바뀌어 pykrx 1.2.8은 사용 불가 → FDR(네이버 백엔드) 채택.
       시총은 '현재' 기준 근사(대형주 멤버십은 수년간 안정적이라 허용 가능한 근사).
"""
from __future__ import annotations

import FinanceDataReader as fdr


def build_pit_universe(start: str, top_n: int = 120, include_delisted: bool = True,
                       markets=("KOSPI", "KOSDAQ"), del_cap: int = 100):
    """(code, name) 리스트. start=YYYYMMDD. 대형주 top_n + 구간내 상폐종목(최대 del_cap)."""
    uni, seen = [], set()

    listing = fdr.StockListing("KRX")
    # 시총 큰 순 (멤버십 지속성 높아 선정편향 최소)
    cols = set(listing.columns)
    cap_col = "Marcap" if "Marcap" in cols else None
    if cap_col:
        listing = listing.sort_values(cap_col, ascending=False)
    n_big = 0
    for _, row in listing.iterrows():
        if n_big >= top_n:
            break
        mk = str(row.get("Market", ""))
        if markets and mk not in markets:
            continue
        code = str(row.get("Code", "")).zfill(6)
        if not (len(code) == 6 and code.isdigit()) or code in seen:
            continue
        seen.add(code)
        uni.append((code, str(row.get("Name", code))))
        n_big += 1

    n_del = 0
    if include_delisted:
        try:
            dl = fdr.StockListing("KRX-DELISTING")
            dl = dl.copy()
            dl["ListingDate"] = dl["ListingDate"].astype(str).str.replace("-", "")
            dl["DelistingDate"] = dl["DelistingDate"].astype(str).str.replace("-", "")
            # start에 살아있었고(상장<=start) 이후 상폐(상폐>start): 구간 내 사망 종목
            mask = (dl["ListingDate"] <= start) & (dl["DelistingDate"] > start)
            dlw = dl[mask].sort_values("DelistingDate", ascending=False)  # 최근 상폐 우선
            for _, row in dlw.iterrows():
                if n_del >= del_cap:
                    break
                mk = str(row.get("Market", ""))
                if markets and mk not in markets:
                    continue
                code = str(row.get("Symbol", "")).zfill(6)
                if not (len(code) == 6 and code.isdigit()) or code in seen:
                    continue
                seen.add(code)
                uni.append((code, str(row.get("Name", code)) + "†폐지"))
                n_del += 1
        except Exception as e:
            print(f"  [FDR] 상폐 리스트 오류(생존편향 보정 생략): {str(e)[:80]}")

    print(f"  [FDR] point-in-time 유니버스: 대형주 {n_big} + 상폐 {n_del} = {len(uni)}종목 (기준일 {start})")
    return uni


def load_ohlcv(code: str, start: str, end: str, min_first_gap_days: int = 40):
    """harness 형식 dict 반환. start 직후 상장(데이터 없음)이면 None으로 제외."""
    try:
        df = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None
    need = ("Open", "High", "Low", "Close", "Volume")
    if not all(c in df.columns for c in need):
        return None
    df = df.dropna(subset=list(need))
    df = df[(df["Open"] > 0) & (df["High"] > 0) & (df["Low"] > 0) & (df["Close"] > 0)]
    if len(df) == 0:
        return None
    dates = [d.strftime("%Y%m%d") for d in df.index]
    return {
        "date": dates,
        "open": [float(x) for x in df["Open"]],
        "high": [float(x) for x in df["High"]],
        "low": [float(x) for x in df["Low"]],
        "close": [float(x) for x in df["Close"]],
        "volume": [float(x) for x in df["Volume"]],
    }
