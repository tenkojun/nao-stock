# -*- coding: utf-8 -*-
"""
배포 전 자동 점검 — 눈으로 못 잡는 것을 기계가 잡는다
=======================================================
실제로 있었던 사고: index.html의 두 줄짜리 함수를 한 줄만 지워서 남은 잔해가
인라인 <script> 전체를 문법 오류로 만들었다. 화면은 멀쩡해 보였지만 버튼이
하나도 동작하지 않았다. 아래 검사는 그런 종류를 배포 전에 걸러낸다.

  1) 파이썬 파일 전부 컴파일되는가
  2) HTML 안 인라인 <script> 가 문법적으로 온전한가 (node 있을 때)
  3) HTML 골격에 중복 id 가 없는가
  4) window.open 이 남아있지 않은가 — 프로그램 창에서는 외부 브라우저로 새어 나간다
  5) 프로그램 실행에 필요한 파일이 다 있는가
  6) .ps1 이 한글 깨짐 없이 읽히는 인코딩인가 (바로가기 만들기가 이것 때문에 실패했었다)
  7) .gitignore 에 꼬리 주석이 붙어 규칙이 죽지 않았는가 (실제로 하나가 죽어 있었다)

사용:  python tools/check.py      (문제 있으면 종료코드 1)
"""
from __future__ import annotations

import io
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = ("index.html", "report.html", "corr3d.html")
NEEDED = ("나오주식.pyw", "server.py", "index.html",
          os.path.join("assets", "nao.ico"),
          os.path.join("tools", "make_shortcut.ps1"))
SKIP_DIRS = {"data", "backup", "dist", "__pycache__", ".git", ".claude", "krx_cache"}

problems: list[str] = []


def _say(ok, label, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'}  {label}{('  — ' + detail) if detail else ''}")
    if not ok:
        problems.append(f"{label}: {detail}")


def _read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


def check_python():
    print("\n[1] 파이썬 문법")
    bad, n = [], 0
    # Windows 의 nul 은 py_compile 대상이 될 수 없어 임시 폴더에 받아둔다
    with tempfile.TemporaryDirectory() as tmpd:
        out = os.path.join(tmpd, "out.pyc")
        for dp, dns, fns in os.walk(ROOT):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                if not (fn.endswith(".py") or fn.endswith(".pyw")):
                    continue
                n += 1
                try:
                    py_compile.compile(os.path.join(dp, fn), doraise=True, cfile=out)
                except py_compile.PyCompileError as e:
                    rel = os.path.relpath(os.path.join(dp, fn), ROOT)
                    bad.append(f"{rel}: {e.msg.strip()[:120]}")
    _say(not bad, f"파이썬 {n}개 파일", "; ".join(bad[:3]) if bad else "모두 정상")


def check_js():
    print("\n[2] HTML 안 자바스크립트 문법")
    if not shutil.which("node"):
        print("  SKIP  node 가 없어 건너뜀 (설치하면 이 검사가 활성화됩니다)")
        return
    for rel in HTML:
        if not os.path.exists(os.path.join(ROOT, rel)):
            continue
        blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", _read(rel), re.S)
        errs = []
        for i, body in enumerate(blocks, 1):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                             encoding="utf-8") as fp:
                fp.write(body)
                tmp = fp.name
            r = subprocess.run(["node", "--check", tmp], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            os.unlink(tmp)
            if r.returncode:
                first = next((ln for ln in (r.stderr or "").splitlines()
                              if "Error" in ln), "문법 오류")
                errs.append(f"블록{i} {first.strip()[:110]}")
        _say(not errs, f"{rel} (script {len(blocks)}개)",
             "; ".join(errs) if errs else "정상")


def check_ids():
    print("\n[3] 중복 id")
    for rel in HTML:
        if not os.path.exists(os.path.join(ROOT, rel)):
            continue
        # 스크립트가 만들어내는 동적 HTML은 제외하고 골격만 본다
        skeleton = re.sub(r"<script.*?</script>", "", _read(rel), flags=re.S)
        ids = re.findall(r'\bid="([^"]+)"', skeleton)
        dup = sorted({i for i in ids if ids.count(i) > 1})
        _say(not dup, f"{rel} (id {len(ids)}개)",
             "중복: " + ", ".join(dup) if dup else "중복 없음")


def check_no_popups():
    print("\n[4] window.open 잔존 여부 (프로그램 창 필수 조건)")
    for rel in HTML:
        if not os.path.exists(os.path.join(ROOT, rel)):
            continue
        hits = [f"{i}행" for i, ln in enumerate(_read(rel).split("\n"), 1)
                if "window.open(" in ln and "//" not in ln.split("window.open(")[0][-4:]]
        _say(not hits, rel,
             "새 창 호출 남음 → " + ", ".join(hits) if hits else "없음")


def check_files():
    print("\n[5] 프로그램 실행 파일")
    miss = [f for f in NEEDED if not os.path.exists(os.path.join(ROOT, f))]
    _say(not miss, f"필수 {len(NEEDED)}개", "누락: " + ", ".join(miss) if miss else "모두 존재")


def check_encoding():
    """Windows PowerShell 5.1 은 BOM 없는 .ps1 을 ANSI 로 읽어 한글이 깨진다.
    실제로 바로가기 만들기가 이것 때문에 실패했다."""
    print("\n[6] PowerShell 파일 인코딩(한글 깨짐 방지)")
    found = False
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if not fn.endswith(".ps1"):
                continue
            found = True
            full = os.path.join(dp, fn)
            raw = io.open(full, "rb").read()
            rel = os.path.relpath(full, ROOT)
            ascii_only = True
            try:
                raw.decode("ascii")
            except UnicodeDecodeError:
                ascii_only = False
            ok = ascii_only or raw.startswith(b"\xef\xbb\xbf")
            _say(ok, rel, "BOM 있음" if raw.startswith(b"\xef\xbb\xbf")
                 else ("영문 전용" if ascii_only else "한글이 있는데 UTF-8 BOM 이 없음"))
    if not found:
        print("  --    .ps1 파일 없음")


def check_gitignore():
    """.gitignore 는 **줄 맨 앞의 # 만** 주석이다. 꼬리 주석을 붙이면 패턴에 섞여
    규칙이 통째로 무효가 된다. 실제로 update_config.json 이 이것 때문에
    무시되지 않고 공개 저장소에 계속 올라가 있었다."""
    print("\n[7] .gitignore 꼬리 주석(규칙 무효화)")
    gi = os.path.join(ROOT, ".gitignore")
    if not os.path.exists(gi):
        print("  --    .gitignore 없음")
        return
    bad = []
    for i, ln in enumerate(io.open(gi, encoding="utf-8").read().split("\n"), 1):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if "#" in s:
            bad.append(f"{i}행 `{s[:46]}`")
    _say(not bad, ".gitignore",
         "꼬리 주석 → 규칙 무효: " + "; ".join(bad) if bad else "이상 없음")


def main():
    print("=" * 60)
    print("  나오 주식 — 배포 전 점검")
    print("=" * 60)
    check_python()
    check_js()
    check_ids()
    check_no_popups()
    check_files()
    check_encoding()
    check_gitignore()
    print("\n" + "=" * 60)
    if problems:
        print(f"  문제 {len(problems)}건 — 배포하면 안 됩니다")
        for p in problems:
            print(f"    · {p}")
        print("=" * 60)
        return 1
    print("  모두 통과 — 배포해도 좋습니다")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
