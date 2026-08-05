# -*- coding: utf-8 -*-
"""
뉴스 피드 — 종목 뉴스 + 시장 실시간 속보
========================================
· 종목 뉴스: 네이버 금융 종목뉴스(제목·출처·시각·링크)
· 시장 속보: 한국경제 RSS(실시간, 50건 내외)
⚠ 전문가 M-136: 뉴스는 노이즈·조작 위험이 크다. **원문 링크와 출처를 반드시 표시**하고
   감성분석·자동 해석으로 매매 신호를 만들지 않는다(제목 그대로 전달).
"""
from __future__ import annotations
import html
import re
from datetime import datetime

import requests

_H = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}
# 실제로 응답하는 것만 남긴다(후보 9곳을 때려보고 3곳 확인 · 2026-08-04).
# 연합뉴스·아시아경제가 한국경제보다 훨씬 빨리 올라온다(6분 전 vs 54분 전).
_MARKET_RSS = [
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("아시아경제", "https://www.asiae.co.kr/rss/stock.htm"),
    ("한국경제", "https://www.hankyung.com/feed/finance"),
]
_HOT = ("급등", "급락", "폭락", "폭등", "서킷", "사이드카", "상한가", "하한가", "쇼크",
        "어닝", "실적", "적자", "흑자", "금리", "FOMC", "환율", "관세", "규제", "리콜",
        "공시", "유상증자", "무상증자", "합병", "상장폐지", "횡령", "배임")


def _clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def stock_news(code: str, limit: int = 12):
    """네이버 금융 종목뉴스."""
    try:
        r = requests.get(f"https://finance.naver.com/item/news_news.naver?code={code}&page=1",
                         headers=_H, timeout=7)
        r.encoding = "euc-kr"
        t = r.text
    except Exception:
        return []
    titles = re.findall(r'<a[^>]+href="([^"]*news_read[^"]*)"[^>]*>([^<]{6,})</a>', t)
    infos = re.findall(r'class="info">([^<]+)</td>\s*<td class="date">([^<]+)</td>', t)
    out = []
    for i, (href, title) in enumerate(titles[:limit]):
        src, dt = (infos[i] if i < len(infos) else ("", ""))
        url = href if href.startswith("http") else ("https://finance.naver.com" + href.replace("&amp;", "&"))
        out.append({"title": _clean(title), "source": _clean(src), "date": _clean(dt), "url": url})
    return out


def _pubdate(s):
    """RSS pubDate → datetime(로컬). 소스마다 형식이 달라 여러 개를 시도한다."""
    s = (s or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            d = datetime.strptime(s[:31] if "%z" in fmt else s[:25], fmt)
            return d.astimezone().replace(tzinfo=None) if d.tzinfo else d
        except Exception:
            continue
    return None


def market_news(limit: int = 30):
    """시장 실시간 속보(RSS 여러 곳). 긴급 키워드는 hot=True.
    ⚠ 예전에는 '05-12 09:30' 같은 **문자열로 정렬**해 소스별 형식이 다르면 순서가 엉켰다.
       이제 실제 시각으로 정렬하고, 화면이 '몇 분 전'을 계산할 수 있게 ts 를 함께 준다."""
    out, seen = [], set()
    now = datetime.now()
    for name, url in _MARKET_RSS:
        try:
            r = requests.get(url, headers=_H, timeout=7)
            items = re.findall(r"<item>(.*?)</item>", r.text, re.S)
        except Exception:
            continue
        for it in items[:40]:
            ti = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
            lk = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", it, re.S)
            pb = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
            if not ti:
                continue
            title = _clean(ti.group(1))
            key = re.sub(r"\W", "", title)[:40]
            if not title or key in seen:              # 소스가 겹치면 같은 기사가 두 번 온다
                continue
            seen.add(key)
            d = _pubdate(pb.group(1)) if pb else None
            mins = int((now - d).total_seconds() // 60) if d else None
            out.append({"title": title, "url": _clean(lk.group(1)) if lk else "",
                        "source": name,
                        "date": d.strftime("%m-%d %H:%M") if d else "",
                        "ts": d.isoformat() if d else None,
                        "mins": mins,
                        "hot": any(k in title for k in _HOT)})
    out.sort(key=lambda x: (x["mins"] is None, x["mins"] if x["mins"] is not None else 1e9))
    return out[:limit]


def feed(code=None):
    return {"stock": stock_news(code) if code else [], "market": market_news(),
            "caveat": ("뉴스는 노이즈·조작 위험이 있어 제목과 출처를 그대로 전달합니다. "
                       "자동 해석으로 매매 신호를 만들지 않습니다 — 원문을 직접 확인하세요."),
            "updated": datetime.now().strftime("%H:%M")}
