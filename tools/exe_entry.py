# -*- coding: utf-8 -*-
"""
EXE 진입점 — PyInstaller 로 얼릴 대상.

구조
  exe 안  : 파이썬 본체 + 서드파티 라이브러리(flask·numpy·pandas·pywebview…)
  디스크  : 앱 소스(나오주식.pyw · server.py · engine/ · index.html)

이렇게 나눈 이유는 **업데이트를 지금 방식 그대로 쓰기 위해서**다.
앱 소스가 파일로 남아 있으면 updater 가 예전처럼 교체할 수 있다.
exe 는 라이브러리만 담고 있어 자주 바뀌지 않는다.
"""
import os
import runpy
import sys

if getattr(sys, "frozen", False):
    APP = os.path.dirname(sys.executable)          # exe 가 놓인 폴더 = 앱 폴더
else:
    APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 디스크의 앱 소스를 먼저 찾게 한다(라이브러리는 얼린 것을 쓴다)
sys.path.insert(0, os.path.join(APP, "engine"))
sys.path.insert(0, APP)
os.chdir(APP)

LAUNCHER = os.path.join(APP, "나오주식.pyw")

if not os.path.exists(LAUNCHER):
    try:                                            # 사용자에게 조용히 실패하지 않게
        import webview
        webview.create_window("나오 주식", html=(
            "<div style='font-family:sans-serif;padding:40px;text-align:center'>"
            "<h2>프로그램 파일을 찾지 못했습니다</h2>"
            f"<p>{LAUNCHER}<br>설치 폴더가 손상된 것 같습니다. 다시 설치해 주세요.</p></div>"))
        webview.start()
    except Exception:
        pass
    sys.exit(1)

runpy.run_path(LAUNCHER, run_name="__main__")
