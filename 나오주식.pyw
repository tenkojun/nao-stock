# -*- coding: utf-8 -*-
"""
나오 주식 — 프로그램 런처
==========================
예전에는 '검은 명령창 + 브라우저 탭'으로 떠서 웹사이트처럼 보였다.
이 런처는 서버를 조용히 백그라운드로 띄우고 **자체 창(주소창·탭 없음)** 으로 앱을 보여준다.

  · 확장자 `.pyw` → 파이썬이 **명령창 없이** 실행한다
  · 창이 즉시 뜨고(로딩 화면), 서버가 준비되면 앱으로 전환된다
  · 창을 닫으면 서버도 함께 끝난다

pywebview / WebView2가 없는 PC에서도 기본 브라우저로 대신 열어 앱이 항상 동작한다.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)
sys.path.insert(0, os.path.join(_DIR, "engine"))

HOST, PORT = "127.0.0.1", 8770
URL = f"http://{HOST}:{PORT}"
ICON = os.path.join(_DIR, "assets", "nao.ico")
# 로그인 토큰·브라우저 저장소를 담을 곳. data/ 는 업데이트 보존 목록에 있어 갱신해도 안 지워진다
STORE = os.path.join(_DIR, "data", "webview")

PAPER, INK, SOFT = "#e8e3d6", "#1b1917", "#6d6659"

SPLASH = f"""<!doctype html><meta charset="utf-8">
<style>
 html,body{{height:100%;margin:0;background:{PAPER};color:{INK};
   font-family:'Malgun Gothic','맑은 고딕',sans-serif;
   display:flex;align-items:center;justify-content:center}}
 .w{{text-align:center}}
 .n{{font-size:30px;letter-spacing:.30em;font-weight:700}}
 .s{{font-size:13px;color:{SOFT};margin-top:10px;letter-spacing:.06em}}
 .bar{{width:190px;height:3px;background:#d4cebd;margin:26px auto 0;overflow:hidden}}
 .bar i{{display:block;width:40%;height:100%;background:{INK};animation:go 1.15s ease-in-out infinite}}
 @keyframes go{{0%{{transform:translateX(-105%)}}100%{{transform:translateX(255%)}}}}
</style>
<div class="w"><div class="n">NAO&nbsp;STOCK</div>
<div class="s">불러오는 중입니다…</div><div class="bar"><i></i></div></div>"""

FAILED = f"""<!doctype html><meta charset="utf-8">
<style>
 html,body{{height:100%;margin:0;background:{PAPER};color:{INK};
   font-family:'Malgun Gothic','맑은 고딕',sans-serif;
   display:flex;align-items:center;justify-content:center;text-align:center}}
 h2{{font-size:20px;margin:0 0 12px}} p{{color:{SOFT};line-height:1.7;font-size:14px;margin:0}}
</style>
<div><h2>시작하지 못했습니다</h2>
<p>창을 닫고 잠시 후 다시 실행해 주세요.<br>계속 안 되면 아들에게 알려주세요.</p></div>"""


def _port_open(timeout=0.4):
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((HOST, PORT)) == 0


def _serve():
    """Flask 서버를 조용히 실행(리로더·디버그 끄고 접속 로그도 숨김)."""
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    try:
        from server import app                       # server.py 는 __main__ 가드가 있어 안전
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)
    except Exception:
        pass                                          # 창 쪽에서 '시작 실패'로 안내한다


def _wait_ready(timeout=90):
    """서버 임포트(numpy·분석 모듈)가 느린 PC도 있어 넉넉히 기다린다."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _port_open():
            return True
        time.sleep(0.2)
    return False


def _boot(window):
    """창이 뜬 뒤 백그라운드에서 실행 — 서버를 올리고 준비되면 앱으로 넘긴다."""
    if not _port_open():                              # 이미 켜져 있으면 그대로 붙는다
        threading.Thread(target=_serve, daemon=True).start()
    window.load_url(URL if _wait_ready() else "data:text/html;charset=utf-8," + FAILED)


def main():
    try:
        import webview
    except Exception:                                 # pywebview 없음 → 브라우저로 대체
        return _fallback()

    os.makedirs(STORE, exist_ok=True)
    webview.settings["ALLOW_DOWNLOADS"] = True        # 리포트 저장 허용
    win = webview.create_window(
        "나오 주식", html=SPLASH,
        width=1440, height=920, min_size=(1100, 700),
        background_color=PAPER, text_select=True, zoomable=True)
    try:
        # private_mode=False 가 핵심 — 켜져 있으면 실행할 때마다 로그인이 풀린다
        webview.start(_boot, win, private_mode=False, storage_path=STORE,
                      icon=ICON if os.path.exists(ICON) else None)
    except Exception:
        return _fallback()
    os._exit(0)                                       # 남은 스레드까지 확실히 정리


def _fallback():
    """창을 못 띄우는 PC — 서버를 올리고 기본 브라우저로 연다."""
    import webbrowser
    if not _port_open():
        threading.Thread(target=_serve, daemon=True).start()
        if not _wait_ready():
            return
    webbrowser.open(URL)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
