# -*- coding: utf-8 -*-
"""
배포 패키지 만들기 — 설치본이 받아갈 nao_stock.zip 생성
===========================================================
사용법:
  python release.py 1.1.0 "무엇을 고쳤는지 한 줄" ["추가 설명" ...]

하는 일:
  1) version.json 갱신(버전·날짜·변경내역)
  2) 비밀·개인데이터를 **제외**하고 zip 패키징
  3) 패키지 SHA256을 version.json에 기록(앱이 무결성 검증에 사용)
  4) 커밋/푸시 안내 출력

⚠ 안전: data/(기록장·보유), backup/, *secret*, update_config.json, 캐시는 절대 포함하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "dist")
PKG = "nao_stock.zip"

EXCLUDE_DIRS = {"data", "backup", "__pycache__", "dist", ".git", ".claude",
                ".pytest_cache", "krx_cache",
                "docs",                      # 내부 문서(자문 원문·질문지·진행로그)는 배포 대상 아님
                "site"}                      # GitHub Pages 소개 페이지 — 앱 실행과 무관
EXCLUDE_FILES = {"update_config.json", "krx api.txt", "kis_secret.json",
                 "krx_secret.json", ".gitignore",
                 "CLAUDE.md", "version.json.bak",
                 "퀀트전문가_질문지.md", "개발방안_및_판단로직정리.md"}
EXCLUDE_EXT = {".pyc", ".pyo", ".zip", ".log"}


def _skip(rel):
    parts = rel.replace("\\", "/").split("/")
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    name = parts[-1]
    if name in EXCLUDE_FILES or os.path.splitext(name)[1] in EXCLUDE_EXT:
        return True
    if "secret" in name.lower() or name.startswith("요인IC_"):
        return True
    return False


def build(version, notes):
    # 문법이 깨진 채로 배포되는 사고를 막는다 — 화면은 멀쩡해 보여도
    # 인라인 script 가 죽으면 버튼이 하나도 안 눌린다(실제로 겪었음)
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check.py")])
    if r.returncode != 0:
        print("\n  점검 실패 — 배포를 중단합니다. 위 문제를 고친 뒤 다시 실행하세요.")
        sys.exit(1)

    vpath = os.path.join(ROOT, "version.json")
    try:
        with open(vpath, encoding="utf-8") as fp:
            v = json.load(fp)
    except Exception:
        v = {}
    v["version"] = version
    v["released"] = date.today().isoformat()
    v["notes"] = notes or v.get("notes", [])
    v.pop("sha256", None)          # zip 안에는 해시를 넣지 않는다(자기 해시 순환 방지)
    with open(vpath, "w", encoding="utf-8") as fp:
        json.dump(v, fp, ensure_ascii=False, indent=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    zpath = os.path.join(OUT_DIR, PKG)
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT)
                if _skip(rel):
                    continue
                zf.write(full, os.path.join("nao_stock", rel))
                n += 1
    # 완성된 zip의 해시를 **저장소용 version.json에만** 기록한다.
    # (앱은 배포처 version.json의 해시로 내려받은 zip을 검증한다)
    sha = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
    v["sha256"] = sha
    with open(vpath, "w", encoding="utf-8") as fp:
        json.dump(v, fp, ensure_ascii=False, indent=1)

    size = os.path.getsize(zpath) / 1024
    print(f"\n  패키지 생성: {zpath}")
    print(f"  파일 {n}개 · {size:.0f} KB · v{version}")
    print(f"  SHA256: {sha[:16]}…")
    # 유출 점검
    with zipfile.ZipFile(zpath) as zf:
        bad = [x for x in zf.namelist()
               if "secret" in x.lower() or "/data/" in x or x.endswith("krx api.txt")]
    print("  비밀·개인데이터 포함 여부:", "⚠ 발견! " + str(bad) if bad else "없음 ✓")
    print("\n  다음 단계:")
    print("    git add -A && git commit -m \"v%s\" && git push" % version)
    print("    → GitHub Releases 에 태그 v%s 로 dist/%s 업로드" % (version, PKG))
    return zpath


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python release.py <버전> [변경내역...]")
        print("예:     python release.py 1.1.0 \"진입 카드 문구 개선\" \"비용 계산 정확도 향상\"")
        sys.exit(1)
    build(sys.argv[1], sys.argv[2:])
