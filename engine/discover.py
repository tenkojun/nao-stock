# -*- coding: utf-8 -*-
"""
시장 발굴 스캐너 (Phase 3) — 검증된 모멘텀으로 '지금 강한 종목' 사전 계산·캐시
==========================================================================
라이브로 수백 종목을 매 클릭마다 스캔하면 느리므로, 이 스크립트가 미리 계산해
data/discovery.json 에 캐시한다. 앱(/api/discover)은 캐시를 즉시 조회.

방식(정직): 이 앱이 검증한 모멘텀(near_high_60 = 60일 고점 대비)이 강한 순으로 선별.
  장기 보유일수록 강한 종목이 유리(자체 검증 t3.5). 섹터(FDR)로 분류해 브라우징.
  ※ 발굴 결과는 '강한 종목 스크린'이며 매수 추천이 아님. 가치/퀄리티는 개별 '평가'에서.

실행: python engine/discover.py [--top 300] [--out data/discovery.json]
"""
from __future__ import annotations
import sys
import os
import json
import time
from datetime import datetime

import numpy as np
import FinanceDataReader as fdr


# Industry(업종) → 아버지가 브라우징하기 쉬운 broad 섹터(~12개)
_SECMAP = [
    # 더 구체적인 패턴을 먼저 (예: '통신 및 방송 장비'가 '장비'로 기계에 빨려가지 않게)
    (("반도체", "전자부품", "디스플레이", "전자집적", "통신 및 방송 장비", "영상 및 통신",
      "마그네틱 및 광학"), "반도체·전자"),
    (("항공기", "우주선", "무기", "총포"), "방산·항공"),
    (("선박", "보트"), "조선"),
    (("2차전지", "축전지", "전지 제조"), "2차전지"),
    (("의약", "바이오", "제약", "의료", "생물"), "바이오·제약"),
    (("금융", "은행", "보험", "증권", "여신", "자본", "신탁"), "금융"),
    (("자동차", "운송장비", "차부품"), "자동차·부품"),
    (("화학", "석유", "고무", "플라스틱", "정유"), "화학·정유"),
    (("기계", "장비", "정밀기기"), "기계·장비"),
    (("소프트웨어", "정보", "통신", "인터넷", "컴퓨터", "온라인"), "IT·통신"),
    (("소매", "도매", "유통", "음식료", "식료품", "음료", "섬유", "의복", "화장품"), "유통·소비재"),
    (("건설", "건축", "부동산", "토목"), "건설·부동산"),
    (("금속", "철강", "1차 금속", "비금속", "광업"), "철강·소재"),
    (("전기", "에너지", "가스", "발전", "전력"), "전기·에너지"),
    (("오락", "미디어", "방송", "엔터", "게임", "콘텐츠", "출판"), "미디어·엔터"),
]


def _broad(ind):
    if not isinstance(ind, str):
        return "기타"
    for kws, name in _SECMAP:
        if any(k in ind for k in kws):
            return name
    return "기타"


def _sectors():
    try:
        d = fdr.StockListing("KRX-DESC")
        return {str(r["Code"]).zfill(6): _broad(r.get("Industry")) for _, r in d.iterrows()}
    except Exception:
        return {}


def scan(top=300, out="data/discovery.json"):
    listing = fdr.StockListing("KRX")
    if "Marcap" in listing.columns:
        listing = listing.sort_values("Marcap", ascending=False)
    sect = _sectors()
    cands, n = [], 0
    for _, row in listing.iterrows():
        if n >= top:
            break
        mk = str(row.get("Market", ""))
        if mk not in ("KOSPI", "KOSDAQ"):
            continue
        code = str(row.get("Code", "")).zfill(6)
        if not (len(code) == 6 and code.isdigit()):
            continue
        n += 1
        try:
            df = fdr.DataReader(code, (datetime.now().replace(year=datetime.now().year - 1)).strftime("%Y%m%d"))
            df = df[df["Close"] > 0]
            if len(df) < 60:
                continue
            c = df["Close"].to_numpy(float)
            h = df["High"].to_numpy(float)
            px = float(c[-1]); hi60 = float(np.max(h[-60:]))
            nh = px / hi60 - 1.0 if hi60 > 0 else 0.0
            r20 = px / c[-21] - 1.0 if len(c) >= 21 else 0.0
            cands.append({
                "code": code, "name": str(row.get("Name", code)), "market": mk,
                "sector": sect.get(code, "기타"),
                "mom": round(nh * 100, 1), "ret20": round(r20 * 100, 1),
                "price": int(px), "marcap": int(row.get("Marcap", 0) or 0),
            })
        except Exception:
            continue
        if n % 50 == 0:
            print(f"  …{n}/{top} 스캔 (후보 {len(cands)})")
    cands.sort(key=lambda x: -x["mom"])          # 모멘텀 강한 순
    payload = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
               "count": len(cands), "items": cands}
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False)
    print(f"  저장: {path}  ({len(cands)}종목, {payload['updated']})")
    return payload


def _argval(flag, default, cast=str):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return cast(sys.argv[i + 1])
    return default


if __name__ == "__main__":
    t0 = time.time()
    scan(top=_argval("--top", 300, int), out=_argval("--out", "data/discovery.json"))
    print(f"  완료 {time.time()-t0:.0f}s")
