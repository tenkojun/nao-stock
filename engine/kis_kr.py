# -*- coding: utf-8 -*-
"""
NAO STOCK — 한국투자증권(KIS) 국내주식 데이터 어댑터
====================================================
기존 user_data/_kis_etf_paper.py의 검증된 패턴(토큰 23h 캐시 · 초당 throttle ·
헤더 · rt_cd 에러처리)을 그대로 계승하되, 대상만 **국내주식 실시간 시세·투자자별 수급**으로.

무지연 실시간·수급은 KIS **국내 실전 계좌**가 필요하므로, kis_secret.json에
아래 섹션을 추가하세요(값은 junhwa님만; 채팅·커밋 금지):

  "kr_stocks": {
    "appkey":    "국내_실전_APPKEY",
    "appsecret": "국내_실전_APPSECRET",
    "account":   "12345678-01",
    "paper":     false          // 실전=false(무지연) · 국내 모의=true(지연/제한)
  }

TR_ID 출처: github.com/koreainvestment/open-trading-api (domestic-stock).
※ [확인] 표시 TR은 KIS 문서와 대조 권장.

사용:
  from engine.kis_kr import KISKorea
  kis = KISKorea()
  kis.quote("005930")               # 현재가
  kis.daily_ohlcv("005930", 120)    # 일봉 DataFrame
  kis.investor_flow("005930")       # 외국인·기관·개인 순매수
"""
from __future__ import annotations

import os
import json
import time
import threading
from datetime import datetime, timedelta

import requests

try:
    import pandas as pd
except Exception:                     # pandas 없이도 dict 반환은 동작
    pd = None

# ── 설정 ──────────────────────────────────────────────────────────
import keys as _keys                                        # 키 위치는 keys.py 가 정한다

SECRET_FILE = _keys.kis_path()      # 환경변수 → 사용자 폴더 → 앱 폴더(설정 화면 저장분)
SECTION = os.environ.get("KIS_SECTION", "kr_stocks")        # 국내 실전 섹션
_REAL = "https://openapi.koreainvestment.com:9443"          # 실전(무지연)
_PAPER = "https://openapivts.koreainvestment.com:29443"     # 모의(지연/제한)


class KISKorea:
    def __init__(self, secret_file: str = SECRET_FILE, section: str = SECTION):
        self.secret_file = secret_file
        self.section = section
        s = self._load_secret()
        self.appkey = s["appkey"]
        self.appsecret = s["appsecret"]
        self.paper = bool(s.get("paper", False))
        self.base = _PAPER if self.paper else _REAL
        acct = str(s.get("account", "")).replace(" ", "")
        self.cano, self.prdt = (acct.split("-") + [""])[:2] if "-" in acct \
            else (acct, "01")
        self._token_cache = os.path.join(
            os.path.dirname(os.path.abspath(secret_file)),
            f".kis_token_{section}.json")
        self._last_call = [0.0]
        self._lock = threading.Lock()

    # ── 인증 ──
    def _load_secret(self) -> dict:
        if not os.path.exists(self.secret_file):
            raise FileNotFoundError(
                f"kis_secret.json 없음: {self.secret_file}")
        d = json.load(open(self.secret_file, encoding="utf-8"))
        if self.section not in d:
            raise KeyError(
                f"'{self.section}' 섹션이 kis_secret.json에 없습니다. "
                f"국내 실전 계좌 섹션을 추가하세요(파일 상단 안내 참고). "
                f"현재 섹션: {list(k for k in d if not k.startswith('_'))}")
        return d[self.section]

    def _get_token(self) -> str:
        if os.path.exists(self._token_cache):
            try:
                c = json.load(open(self._token_cache, encoding="utf-8"))
                if c.get("expire", 0) > time.time() + 600 \
                        and c.get("appkey") == self.appkey[:12]:
                    return c["token"]
            except Exception:
                pass
        r = requests.post(self.base + "/oauth2/tokenP", json={
            "grant_type": "client_credentials",
            "appkey": self.appkey, "appsecret": self.appsecret}, timeout=10)
        r.raise_for_status()
        tok = r.json()["access_token"]
        json.dump({"token": tok, "expire": time.time() + 23 * 3600,
                   "appkey": self.appkey[:12]},
                  open(self._token_cache, "w", encoding="utf-8"))
        return tok

    def _hdr(self, tr: str) -> dict:
        return {"authorization": f"Bearer {self._get_token()}",
                "appkey": self.appkey, "appsecret": self.appsecret,
                "tr_id": tr, "custtype": "P",
                "content-type": "application/json; charset=utf-8"}

    def _throttle(self):
        with self._lock:
            wait = self._last_call[0] + 0.6 - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_call[0] = time.time()

    def _get(self, path: str, tr: str, params: dict) -> dict:
        self._throttle()
        r = requests.get(self.base + path, headers=self._hdr(tr),
                         params=params, timeout=10)
        j = r.json()
        if j.get("rt_cd") != "0":
            raise RuntimeError(
                f"{tr} rt_cd={j.get('rt_cd')} {j.get('msg_cd')} "
                f"{j.get('msg1', '').strip()}")
        return j

    # ── 시세 ──
    def quote(self, code: str) -> dict:
        """현재가·등락·거래량 (TR FHKST01010100)."""
        j = self._get("/uapi/domestic-stock/v1/quotations/inquire-price",
                       "FHKST01010100",
                       {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code})
        o = j["output"]
        return {
            "code": code,
            "price": float(o["stck_prpr"]),           # 현재가
            "change": float(o["prdy_vrss"]),          # 전일 대비
            "change_pct": float(o["prdy_ctrt"]),      # 등락률
            "open": float(o["stck_oprc"]), "high": float(o["stck_hgpr"]),
            "low": float(o["stck_lwpr"]), "volume": float(o["acml_vol"]),
            "name": o.get("hts_kor_isnm", ""),
        }

    def daily_ohlcv(self, code: str, days: int = 120, period: str = "D"):
        """일/주/월봉 (TR FHKST03010100). period: D/W/M. DataFrame 반환."""
        end = datetime.now()
        start = end - timedelta(days=int(days * 1.6) + 10)
        j = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            "FHKST03010100",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code,
             "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
             "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
             "FID_PERIOD_DIV_CODE": period, "FID_ORG_ADJ_PRC": "0"})
        rows = []
        for x in j.get("output2", []):
            if not x.get("stck_bsop_date"):
                continue
            rows.append({
                "date": x["stck_bsop_date"], "open": float(x["stck_oprc"]),
                "high": float(x["stck_hgpr"]), "low": float(x["stck_lwpr"]),
                "close": float(x["stck_clpr"]), "volume": float(x["acml_vol"]),
            })
        rows.reverse()
        if pd is None:
            return rows[-days:]
        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        return df.tail(days)

    def foreign_inst_flow(self, sort: str = "0"):
        """외국인·기관 매매종목 가집계 (FHPTJ04400000). sort 0=순매수상위, 1=순매도상위.
        종목별 외국인/기관 순매수량 + 기관 세부(연기금·투신 등). 수급 흐름 지도용."""
        j = self._get("/uapi/domestic-stock/v1/quotations/foreign-institution-total",
                      "FHPTJ04400000",
                      {"FID_COND_MRKT_DIV_CODE": "V", "FID_COND_SCR_DIV_CODE": "16449",
                       "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0",
                       "FID_RANK_SORT_CLS_CODE": sort, "FID_ETC_CLS_CODE": "0"})
        out = []
        for x in j.get("output", []):
            px = _f(x.get("stck_prpr"))
            out.append({
                "code": x.get("mksc_shrn_iscd", ""), "name": x.get("hts_kor_isnm", ""),
                "price": px, "chg": _f(x.get("prdy_ctrt")),
                "frgn": _f(x.get("frgn_ntby_qty")), "org": _f(x.get("orgn_ntby_qty")),
                "fund": _f(x.get("fund_ntby_qty")), "insu": _f(x.get("insu_ntby_qty")),
                "bank": _f(x.get("bank_ntby_qty")), "mrbn": _f(x.get("mrbn_ntby_qty")),
                "etc_org": _f(x.get("etc_orgt_ntby_vol")),
                "vol": _f(x.get("acml_vol")),        # 오늘 누적 거래량(거래량 대비 % 계산용)
                "total": _f(x.get("ntby_qty")),
            })
        return out

    def minute_bars(self, code: str, interval: int = 5, pages: int = 12):
        """당일 1분봉을 페이지네이션 수집 → interval분봉으로 집계 (저타임프레임 분석용).
        반환: 오름차순 [{time'HHMM', open, high, low, close, volume}]. (당일 위주, ~1세션)"""
        raw = {}
        hour = "153000"
        for _ in range(max(1, pages)):
            j = self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                "FHKST03010200",
                {"FID_ETC_CLS_CODE": "", "FID_COND_MRKT_DIV_CODE": "J",
                 "FID_INPUT_ISCD": code, "FID_INPUT_HOUR_1": hour, "FID_PW_DATA_INCU_YN": "N"})
            out = [x for x in j.get("output2", []) if x.get("stck_cntg_hour")]
            if not out:
                break
            for x in out:
                t = x["stck_cntg_hour"]                     # HHMMSS
                raw[t] = {"o": float(x["stck_oprc"]), "h": float(x["stck_hgpr"]),
                          "l": float(x["stck_lwpr"]), "c": float(x["stck_prpr"]),
                          "v": float(x["cntg_vol"])}
            earliest = min(out, key=lambda x: x["stck_cntg_hour"])["stck_cntg_hour"]
            if earliest <= "090100":
                break
            em = int(earliest[:4]) - 1                       # 직전 분부터 다음 페이지
            hour = "%04d00" % em
        if not raw:
            return []
        # interval분 집계 (HHMM을 interval으로 내림)
        buckets = {}
        for t in sorted(raw):
            hhmm = int(t[:4]); m = (hhmm % 100); h = hhmm // 100
            tot = h * 60 + m
            key = (tot // interval) * interval
            kk = "%02d%02d" % (key // 60, key % 60)
            b = buckets.get(kk)
            r = raw[t]
            if b is None:
                buckets[kk] = {"time": kk, "open": r["o"], "high": r["h"],
                               "low": r["l"], "close": r["c"], "volume": r["v"]}
            else:
                b["high"] = max(b["high"], r["h"]); b["low"] = min(b["low"], r["l"])
                b["close"] = r["c"]; b["volume"] += r["v"]
        return [buckets[k] for k in sorted(buckets)]

    def minute_bars_days(self, code: str, interval: int = 5, days: int = 3):
        """**여러 거래일** 분봉. 당일치만 주는 inquire-time-itemchartprice 대신
        일자별 TR(FHKST03010230)을 날짜별로 페이지네이션한다(한 번에 120건).

        반환: 오름차순 [{date'YYYYMMDD', time'HHMM', open, high, low, close, volume}]
        ⚠ 날짜를 함께 돌려줘야 화면에서 여러 날을 이어 붙일 수 있다."""
        import datetime as _dt
        raw = {}                                     # (date, HHMMSS) -> ohlcv
        day = _dt.date.today()
        got_days = 0
        guard = 0
        while got_days < max(1, days) and guard < 20:
            guard += 1
            if day.weekday() >= 5:                   # 주말 건너뛰기
                day -= _dt.timedelta(days=1)
                continue
            ds = day.strftime("%Y%m%d")
            hour, seen = "153000", 0
            for _ in range(6):                       # 09:00~15:30 ≈ 390분 → 120건씩 4~5회
                j = self._get(
                    "/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice",
                    "FHKST03010230",
                    {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code,
                     "FID_INPUT_HOUR_1": hour, "FID_INPUT_DATE_1": ds,
                     "FID_PW_DATA_INCU_YN": "N", "FID_FAKE_TICK_INCU_YN": "N"})
                out = [x for x in j.get("output2", []) if x.get("stck_cntg_hour")]
                if not out:
                    break
                for x in out:
                    t = x["stck_cntg_hour"]
                    raw[(x.get("stck_bsop_date", ds), t)] = {
                        "o": _f(x["stck_oprc"]), "h": _f(x["stck_hgpr"]),
                        "l": _f(x["stck_lwpr"]), "c": _f(x["stck_prpr"]),
                        "v": _f(x["cntg_vol"])}
                seen += len(out)
                earliest = min(out, key=lambda x: x["stck_cntg_hour"])["stck_cntg_hour"]
                if earliest <= "090100":
                    break
                hour = "%04d00" % (int(earliest[:4]) - 1)
            if seen:
                got_days += 1
            day -= _dt.timedelta(days=1)

        if not raw:
            return []
        buckets = {}
        for (ds, t) in sorted(raw):
            hhmm = int(t[:4])
            tot = (hhmm // 100) * 60 + (hhmm % 100)
            key = (tot // interval) * interval
            kk = "%02d%02d" % (key // 60, key % 60)
            b = buckets.get((ds, kk))
            r = raw[(ds, t)]
            if b is None:
                buckets[(ds, kk)] = {"date": ds, "time": kk, "open": r["o"], "high": r["h"],
                                     "low": r["l"], "close": r["c"], "volume": r["v"]}
            else:
                b["high"] = max(b["high"], r["h"])
                b["low"] = min(b["low"], r["l"])
                b["close"] = r["c"]
                b["volume"] += r["v"]
        return [buckets[k] for k in sorted(buckets)]

    def ranking_volume(self, top: int = 15):
        """거래대금 상위(주도주). TR FHPST01710000 volume-rank. [확인]"""
        j = self._get("/uapi/domestic-stock/v1/quotations/volume-rank",
                       "FHPST01710000",
                       {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
                        "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0",
                        "FID_BLNG_CLS_CODE": "3", "FID_TRGT_CLS_CODE": "111111111",
                        "FID_TRGT_EXLS_CLS_CODE": "000000", "FID_INPUT_PRICE_1": "",
                        "FID_INPUT_PRICE_2": "", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""})
        out = []
        for x in (j.get("output") or [])[:top]:
            out.append({
                "code": x.get("mksc_shrn_iscd", ""),
                "name": x.get("hts_kor_isnm", ""),
                "price": _f(x.get("stck_prpr")),
                "chg": _f(x.get("prdy_ctrt")),
                "amount": _f(x.get("acml_tr_pbmn")),   # 누적 거래대금(백만)
                "volume": _f(x.get("acml_vol")),
            })
        return out

    def ranking_fluctuation(self, top: int = 15, rise: bool = True):
        """등락률 상위(상승/하락). TR FHPST01700000. [확인]"""
        j = self._get("/uapi/domestic-stock/v1/ranking/fluctuation",
                       "FHPST01700000",
                       {"fid_cond_mrkt_div_code": "J", "fid_cond_scr_div_code": "20170",
                        "fid_input_iscd": "0000",
                        "fid_rank_sort_cls_code": "0" if rise else "1",
                        "fid_input_cnt_1": "0", "fid_prc_cls_code": "0",
                        "fid_input_price_1": "", "fid_input_price_2": "",
                        "fid_vol_cnt": "", "fid_trgt_cls_code": "0",
                        "fid_trgt_exls_cls_code": "0", "fid_div_cls_code": "0",
                        "fid_rsfl_rate1": "", "fid_rsfl_rate2": ""})
        out = []
        for x in (j.get("output") or [])[:top]:
            out.append({
                "code": x.get("stck_shrn_iscd", ""),
                "name": x.get("hts_kor_isnm", ""),
                "price": _f(x.get("stck_prpr")),
                "chg": _f(x.get("prdy_ctrt")),
                "amount": _f(x.get("acml_tr_pbmn")),
                "volume": _f(x.get("acml_vol")),
            })
        return out

    def index_quote(self, idx: str = "0001"):
        """지수 현재가·공식 등락률 (output1의 bstp_nmix_prpr·prdy_ctrt 사용)."""
        end = datetime.now(); start = end - timedelta(days=8)
        j = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
            "FHKUP03500100",
            {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": idx,
             "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
             "FID_INPUT_DATE_2": end.strftime("%Y%m%d"), "FID_PERIOD_DIV_CODE": "D"})
        o = j.get("output1") or {}
        val = _f(o.get("bstp_nmix_prpr"))
        chg = _f(o.get("bstp_nmix_prdy_ctrt"))
        if not val:                       # 일부 지수는 output1이 비어 output2로 폴백
            o2 = j.get("output2") or []
            if o2:
                val = _f(o2[0].get("bstp_nmix_prpr"))
                if len(o2) > 1:
                    pv = _f(o2[1].get("bstp_nmix_prpr"))
                    chg = round((val / pv - 1) * 100, 2) if pv else 0.0
        return {"value": val, "chg": chg}

    def index_daily(self, idx: str = "0001", days: int = 40):
        """국내 지수 일봉 (KOSPI=0001, KOSDAQ=1001). 상대강도 계산용. [확인]"""
        end = datetime.now()
        start = end - timedelta(days=int(days * 1.7) + 10)
        j = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
            "FHKUP03500100",
            {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": idx,
             "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
             "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
             "FID_PERIOD_DIV_CODE": "D"})
        closes = []
        for x in j.get("output2", []):
            v = x.get("bstp_nmix_prpr") or x.get("stck_clpr")
            if v:
                closes.append(float(v))
        closes.reverse()
        return closes[-days:]

    def daily_ohlcv_long(self, code: str, days: int = 600, period: str = "D"):
        """장기 일봉 수집 — KIS가 1회 ~100건 제한이라 날짜 창을 뒤로 옮기며 청크 수집.
        (검증 하네스용, 전문가 J-103: 표본 확보)"""
        out = []
        end = datetime.now()
        for _ in range(12):                    # 최대 12청크(~1200봉 한도)
            start = end - timedelta(days=170)
            j = self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                "FHKST03010100",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code,
                 "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                 "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
                 "FID_PERIOD_DIV_CODE": period, "FID_ORG_ADJ_PRC": "0"})
            rows = [x for x in j.get("output2", []) if x.get("stck_bsop_date")]
            if not rows:
                break
            for x in rows:
                out.append({"date": x["stck_bsop_date"],
                            "open": float(x["stck_oprc"]), "high": float(x["stck_hgpr"]),
                            "low": float(x["stck_lwpr"]), "close": float(x["stck_clpr"]),
                            "volume": float(x["acml_vol"])})
            oldest = min(x["stck_bsop_date"] for x in rows)
            end = datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)
            if len(out) >= days:
                break
        seen = {}
        for r in out:
            seen[r["date"]] = r
        rows = [seen[k] for k in sorted(seen)]
        return rows[-days:]

    def investor_flow(self, code: str) -> dict:
        """종목별 투자자 순매수 — 외국인·기관·개인 (TR FHKST01010900) [확인].
        핵심: 지표의 '추정 수급'을 실데이터로 대체하는 부분."""
        j = self._get("/uapi/domestic-stock/v1/quotations/inquire-investor",
                       "FHKST01010900",
                       {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code})
        out = j.get("output", [])
        if not out:
            return {"code": code, "rows": []}
        rows = []
        for x in out[:20]:
            rows.append({
                "date": x.get("stck_bsop_date", ""),
                "foreign_net": _f(x.get("frgn_ntby_qty")),   # 외국인 순매수량
                "org_net": _f(x.get("orgn_ntby_qty")),       # 기관 순매수량
                "person_net": _f(x.get("prsn_ntby_qty")),    # 개인 순매수량
            })
        # 최근 5일 합으로 방향 요약
        f5 = sum(r["foreign_net"] for r in rows[:5])
        o5 = sum(r["org_net"] for r in rows[:5])
        return {"code": code, "rows": rows,
                "foreign_5d": f5, "org_5d": o5,
                "foreign_dir": _dir(f5), "org_dir": _dir(o5)}


def _f(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0.0


def _dir(x):
    return "순매수" if x > 0 else "순매도" if x < 0 else "중립"


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "005930"
    try:
        kis = KISKorea()
        print(f"도메인: {'모의' if kis.paper else '실전(무지연)'}  섹션: {kis.section}")
        q = kis.quote(code)
        print(f"[현재가] {q['name']} {q['code']}  {q['price']:,.0f}원  "
              f"({q['change_pct']:+.2f}%)  거래량 {q['volume']:,.0f}")
        df = kis.daily_ohlcv(code, 10)
        print(f"[일봉] 최근 {len(df)}개 수신")
        fl = kis.investor_flow(code)
        print(f"[수급] 외국인 5일 {fl.get('foreign_5d',0):+,.0f}({fl.get('foreign_dir')}) "
              f"· 기관 5일 {fl.get('org_5d',0):+,.0f}({fl.get('org_dir')})")
        print("\n✅ 3종 모두 수신 성공 → JIQT 파이프라인 Evidence 주입 준비 완료.")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        print("→ kr_stocks 섹션 추가 여부·실전/모의 도메인·키를 확인하세요.")
