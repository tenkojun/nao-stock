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
_MARKET_RSS = [("한국경제", "https://www.hankyung.com/feed/finance")]
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


def market_news(limit: int = 20):
    """시장 실시간 속보(RSS). 긴급 키워드는 hot=True로 표시."""
    out = []
    for name, url in _MARKET_RSS:
        try:
            r = requests.get(url, headers=_H, timeout=7)
            items = re.findall(r"<item>(.*?)</item>", r.text, re.S)
        except Exception:
            continue
        for it in items[:limit]:
            ti = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
            lk = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", it, re.S)
            pb = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
            if not ti:
                continue
            title = _clean(ti.group(1))
            when = ""
            if pb:
                try:
                    d = datetime.strptime(pb.group(1).strip()[:25], "%a, %d %b %Y %H:%M:%S")
                    when = d.strftime("%m-%d %H:%M")
                except Exception:
                    when = pb.group(1).strip()[:16]
            out.append({"title": title, "url": _clean(lk.group(1)) if lk else "",
                        "source": name, "date": when,
                        "hot": any(k in title for k in _HOT)})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:limit]


def feed(code=None):
    return {"stock": stock_news(code) if code else [], "market": market_news(),
            "caveat": ("뉴스는 노이즈·조작 위험이 있어 제목과 출처를 그대로 전달합니다. "
                       "자동 해석으로 매매 신호를 만들지 않습니다 — 원문을 직접 확인하세요."),
            "updated": datetime.now().strftime("%H:%M")}
