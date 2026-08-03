# -*- coding: utf-8 -*-
"""
USB 로 전달할 EXE 설치본 만들기
================================
    python tools/build_exe.py     # ① exe 굽기(라이브러리 번들)
    python tools/pack_exe.py      # ② 앱 소스와 합쳐 전달용 폴더 만들기

결과: dist_exe/나오주식_설치본/  ← 이 폴더를 통째로 USB 에 복사하면 끝.
      받는 쪽은 원하는 위치에 두고 `나오주식.exe` 를 누르면 된다(파이썬 불필요).

⚠ 키(data/keys)·기록(data/)은 **넣지 않는다.** 키는 받는 PC 에서
   설정 → API 연결 → USB 에서 키 파일 가져오기로 넣는다.
"""
from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEDIR = os.path.join(ROOT, "dist_exe", "나오주식")
OUT = os.path.join(ROOT, "dist_exe", "나오주식_설치본")

FILES = ["나오주식.pyw", "server.py", "index.html", "report.html", "corr3d.html",
         "version.json", "update_config.json", "LICENSE"]
DIRS = ["engine", "assets", "tools"]
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "build_exe.py", "pack_exe.py")

README = """나오 주식 — 설치 안내

1. 이 폴더를 통째로 원하는 곳에 복사하세요.
   (예: C:\\나오주식)

2. 폴더 안의  나오주식.exe  를 두 번 누르면 실행됩니다.
   파이썬을 따로 설치할 필요가 없습니다.

3. 시세를 보려면 열쇠(API 키)가 필요합니다.
   프로그램에서  설정(⚙) → API 연결 → USB에서 키 파일 가져오기  를 눌러
   kis_secret.json, krx_secret.json 파일을 고르면 됩니다.

4. 바탕화면 아이콘을 만들려면
   나오주식.exe 를 오른쪽 클릭 → 보내기 → 바탕화면(바로 가기 만들기)

문제가 생기면 개발자에게 알려주세요.  개발 정준화
"""


def main():
    if not os.path.isdir(EXEDIR):
        print("먼저 EXE 를 구우세요:  python tools/build_exe.py")
        return 1
    if os.path.exists(OUT):
        shutil.rmtree(OUT, ignore_errors=True)

    shutil.copytree(EXEDIR, OUT)                       # exe + _internal
    for f in FILES:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            shutil.copy2(p, OUT)
    for d in DIRS:
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            shutil.copytree(p, os.path.join(OUT, d), dirs_exist_ok=True, ignore=SKIP)

    with open(os.path.join(OUT, "읽어보세요.txt"), "w", encoding="utf-8") as fp:
        fp.write(README)

    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    sz = sum(os.path.getsize(os.path.join(dp, f))
             for dp, _, fs in os.walk(OUT) for f in fs) / 1024 / 1024
    has_keys = os.path.isdir(os.path.join(OUT, "data"))
    print(f"설치본: {OUT}")
    print(f"  파일 {n}개 · {sz:.0f} MB")
    print(f"  실행 파일: {'있음' if os.path.exists(os.path.join(OUT, '나오주식.exe')) else '⚠ 없음'}")
    print(f"  키·기록 포함 여부: {'⚠ 포함됨!' if has_keys else '없음 ✓'}")
    print("\n이 폴더를 USB 에 복사해 전달하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
