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

하는 일
  ① 파이썬 확인  ② 라이브러리 설치
  ③ **고정 폴더로 설치**(C:\\나오주식 → 안 되면 내 폴더\\나오주식)
  ④ 바탕화면 아이콘  ⑤ 실행

⚠ 재설치해도 `data/`(설정·보유·기록장)·`backup/`·`update_config.json` 은 덮지 않는다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEED = ["flask", "numpy", "requests", "pandas", "finance-datareader", "pywebview"]
IMPORTS = {"flask": "flask", "numpy": "numpy", "requests": "requests",
           "pandas": "pandas", "finance-datareader": "FinanceDataReader",
           "pywebview": "webview"}

FOLDER = "나오주식"
PRESERVE = {"data", "backup", "update_config.json"}       # 사용자 것 — 덮지 않는다
SKIP = {"__pycache__", ".git", "dist", ".pytest_cache", "docs", "site"}

try:                                   # 콘솔이 UTF-8이 아니어도 한글이 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def say(msg=""):
    print(msg, flush=True)


def same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def inside(child, parent):
    """이미 설치 폴더 안(예: C:\\나오주식\\nao_stock)이면 다시 옮기지 않는다 —
    옮기면 폴더가 두 겹이 되고 어느 쪽이 진짜인지 헷갈린다."""
    c = os.path.normcase(os.path.abspath(child))
    p = os.path.normcase(os.path.abspath(parent))
    return c.startswith(p + os.sep)


# ── 라이브러리 ────────────────────────────────────────────────────
def missing():
    import importlib.util as u
    return [p for p in NEED if u.find_spec(IMPORTS[p]) is None]


def install_libs(pkgs):
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


# ── 설치 위치 ─────────────────────────────────────────────────────
def pick_target():
    """찾기 쉬운 고정 폴더. C 드라이브에 못 만들면 사용자 폴더로."""
    for base in (os.path.join("C:\\", FOLDER),
                 os.path.join(os.path.expanduser("~"), FOLDER)):
        try:
            os.makedirs(base, exist_ok=True)
            probe = os.path.join(base, ".write_test")
            with open(probe, "w"):
                pass
            os.remove(probe)
            return base
        except Exception:
            continue
    return None


def copy_into(dst):
    """앱 파일을 옮긴다. 사용자 데이터는 건드리지 않는다."""
    n = 0
    for name in os.listdir(ROOT):
        if name in SKIP or name in PRESERVE:
            continue
        s, d = os.path.join(ROOT, name), os.path.join(dst, name)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(*SKIP))
            n += sum(len(f) for _, _, f in os.walk(s))
        else:
            shutil.copy2(s, d)
            n += 1
    # 배포처 설정은 **없을 때만** 가져온다(기존 설정 보호)
    src_cfg = os.path.join(ROOT, "update_config.json")
    dst_cfg = os.path.join(dst, "update_config.json")
    if os.path.exists(src_cfg) and not os.path.exists(dst_cfg):
        shutil.copy2(src_cfg, dst_cfg)
    return n


def do_install():
    """반환: (실행할 폴더, 새로 설치했는지)"""
    target = pick_target()
    if not target:
        say("  (고정 폴더를 만들지 못해 지금 위치에서 실행합니다.)")
        return ROOT, False
    if same(ROOT, target) or inside(ROOT, target):
        return ROOT, not os.path.exists(os.path.join(ROOT, "data"))   # 이미 제자리
    first = not os.path.exists(os.path.join(target, "data"))
    say(f"  설치 위치: {target}")
    try:
        n = copy_into(target)
    except Exception as e:
        say(f"  [!] 복사 실패({type(e).__name__}) — 지금 위치에서 실행합니다.")
        return ROOT, False
    say(f"  파일 {n}개 복사 완료." + ("" if first else " (기존 설정·기록은 그대로 두었습니다.)"))
    return target, first


# ── 아이콘 · 실행 ─────────────────────────────────────────────────
def make_shortcut(root):
    ps1 = os.path.join(root, "tools", "make_shortcut.ps1")
    if not os.path.exists(ps1):
        return False
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", ps1, "-Root", root], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0


def launch(root):
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    app = os.path.join(root, "나오주식.pyw")
    if not os.path.exists(app):
        say(f"  [!] 실행 파일을 찾지 못했습니다: {app}")
        return False
    flags = 0x00000008 | 0x08000000               # DETACHED_PROCESS | CREATE_NO_WINDOW
    subprocess.Popen([pyw, app], cwd=root, creationflags=flags, close_fds=True)
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
    if need and not install_libs(need):
        input("  엔터를 누르면 닫힙니다…")
        return 1

    root, first = do_install()

    if make_shortcut(root):
        say("  바탕화면에 [나오 주식] 아이콘을 만들었습니다.")
        say("  다음부터는 그 아이콘을 두 번 누르면 바로 열립니다.")
    else:
        say("  (바탕화면 아이콘은 만들지 못했습니다 — 실행에는 문제 없습니다.)")

    say()
    say(f"  프로그램 폴더는 여기입니다 →  {root}")
    say("  (탐색기 주소창에 붙여넣으면 바로 열립니다)")
    say()
    say("  지금 시작합니다…")
    if not launch(root):
        input("  엔터를 누르면 닫힙니다…")
        return 1
    if first:
        try:
            os.startfile(root)                    # 첫 설치 때 한 번만 폴더를 보여준다
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
