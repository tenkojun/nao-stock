# -*- coding: utf-8 -*-
"""
EXE 만들기 (PyInstaller · onedir)
==================================
    python tools/build_exe.py

결과: dist_exe/나오주식/나오주식.exe + _internal/

⚠ 앱 소스(server.py·engine·index.html)는 **일부러 넣지 않는다.**
   exe 는 파이썬 본체와 라이브러리만 담고, 앱 소스는 디스크에 두어야
   기존 업데이트(파일 교체)가 그대로 동작한다.
   그래서 PyInstaller 가 소스를 훑어 라이브러리를 찾아낼 수 없고,
   **필요한 라이브러리를 아래에 직접 적어 줘야 한다.**
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist_exe")
NAME = "나오주식"

# 앱이 실제로 쓰는 서드파티 — 디스크 소스를 훑지 못하므로 직접 나열
HIDDEN = [
    "flask", "jinja2", "werkzeug", "click", "itsdangerous", "markupsafe",
    "numpy", "pandas", "requests", "urllib3", "certifi", "charset_normalizer",
    "idna", "FinanceDataReader", "webview",
    "sqlite3", "json", "hashlib", "hmac", "secrets", "zipfile", "base64",
    "csv", "datetime", "importlib.util", "importlib.metadata",
]
COLLECT = ["webview", "FinanceDataReader", "pandas", "requests"]


def main():
    if shutil.which("pyinstaller") is None:
        try:
            import PyInstaller  # noqa: F401
        except Exception:
            print("PyInstaller 가 없습니다:  pip install pyinstaller")
            return 1

    if os.path.exists(OUT):
        shutil.rmtree(OUT, ignore_errors=True)

    cmd = [sys.executable, "-m", "PyInstaller",
           "--noconfirm", "--clean",
           "--name", NAME,
           "--windowed",                       # 콘솔 창 없음
           "--distpath", OUT,
           "--workpath", os.path.join(ROOT, "build_exe"),
           "--specpath", os.path.join(ROOT, "build_exe"),
           ]
    ico = os.path.join(ROOT, "assets", "nao.ico")
    if os.path.exists(ico):
        cmd += ["--icon", ico]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    for c in COLLECT:
        cmd += ["--collect-all", c]
    cmd.append(os.path.join(ROOT, "tools", "exe_entry.py"))

    print("빌드 시작 — 몇 분 걸립니다…\n")
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print("\n빌드 실패")
        return r.returncode

    app = os.path.join(OUT, NAME)
    exe = os.path.join(app, NAME + ".exe")
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(app) for f in fs) / 1024 / 1024
    print(f"\n완료 · {time.time()-t0:.0f}초")
    print(f"  {exe}")
    print(f"  전체 {size:.0f} MB")
    print("\n다음: 이 폴더에 앱 소스(server.py·engine·index.html 등)를 함께 두면 실행됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
