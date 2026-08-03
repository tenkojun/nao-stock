# -*- coding: utf-8 -*-
"""
설치·실행 도우미
=================
`나오주식_실행.bat` 이 호출한다. 배치는 **순수 ASCII**로 두고 한글은 여기서 출력한다.

왜 이렇게 나눴나
  .bat 안에 한글(UTF-8)이 있는 상태에서 `chcp 65001` 로 코드페이지를 바꾸면
  cmd 가 파일에서 읽던 **바이트 위치를 잃어버려 명령이 토막난다.**
  ('on' is not recognized … 처럼 조각난 오류가 난다. 실제로 그렇게 깨졌다.)
  배치에 비ASCII 문자가 없으면 이 문제가 생기지 않는다.

하는 일: 파이썬 확인 → 라이브러리 설치 → 바탕화면 아이콘 → 프로그램 실행
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEED = ["flask", "numpy", "requests", "pandas", "finance-datareader", "pywebview"]
IMPORTS = {"flask": "flask", "numpy": "numpy", "requests": "requests",
           "pandas": "pandas", "finance-datareader": "FinanceDataReader",
           "pywebview": "webview"}

try:                                   # 콘솔이 UTF-8이 아니어도 한글이 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def say(msg=""):
    print(msg, flush=True)


def missing():
    import importlib.util as u
    return [p for p in NEED if u.find_spec(IMPORTS[p]) is None]


def install(pkgs):
    say(f"  처음 실행이라 필요한 프로그램을 설치합니다({len(pkgs)}개).")
    say("  몇 분 걸릴 수 있습니다. 창을 닫지 마세요…")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                    "--disable-pip-version-check", *pkgs])
    left = missing()
    if left:
        say(f"  [!] 설치되지 않은 것: {', '.join(left)}")
        say("      인터넷 연결을 확인한 뒤 다시 실행해 주세요.")
        return False
    say("  설치 완료.")
    return True


def make_shortcut():
    ps1 = os.path.join(ROOT, "tools", "make_shortcut.ps1")
    if not os.path.exists(ps1):
        return False
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", ps1], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode == 0


def launch():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable                      # 없으면 콘솔이 뜨더라도 실행은 되게
    app = os.path.join(ROOT, "나오주식.pyw")
    if not os.path.exists(app):
        say(f"  [!] 실행 파일을 찾지 못했습니다: {app}")
        return False
    # 부모 창이 닫혀도 살아남게 분리해서 띄운다
    flags = 0x00000008 | 0x08000000               # DETACHED_PROCESS | CREATE_NO_WINDOW
    subprocess.Popen([pyw, app], cwd=ROOT, creationflags=flags,
                     close_fds=True)
    return True


def main():
    say()
    say("  ================================")
    say("     나오 주식")
    say("  ================================")
    say()

    if sys.version_info < (3, 9):
        say(f"  [!] 파이썬 3.9 이상이 필요합니다(현재 {sys.version.split()[0]}).")
        input("  엔터를 누르면 닫힙니다…")
        return 1

    need = missing()
    if need and not install(need):
        input("  엔터를 누르면 닫힙니다…")
        return 1

    if make_shortcut():
        say("  바탕화면에 [나오 주식] 아이콘을 만들었습니다.")
        say("  다음부터는 그 아이콘을 두 번 누르면 바로 열립니다.")
    else:
        say("  (바탕화면 아이콘은 만들지 못했습니다 — 실행에는 문제 없습니다.)")
    say()
    say("  지금 시작합니다…")
    if not launch():
        input("  엔터를 누르면 닫힙니다…")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
