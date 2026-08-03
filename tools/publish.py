# -*- coding: utf-8 -*-
"""
릴리스 발행 — GitHub Releases 에 zip 을 올린다.
=================================================
    python release.py 1.5.0 "무엇을 고쳤는지"     # ① zip 만들기
    git add -A && git commit && git push          # ② 코드 올리기
    python tools/publish.py                       # ③ 릴리스 발행  ← 이 파일

⚠ 순서가 중요하다. ②를 건너뛰고 ③을 하면 **태그가 이전 커밋에 붙는다**
   (실제로 v1.5.0 에서 한 번 그랬다). 그래서 아래에서 먼저 확인하고 막는다.

⚠ GitHub API 는 캐시된다. 방금 바꾼 것을 다시 조회하면 **직전 값**이 돌아온다.
   확인용 조회에는 반드시 캐시버스터(_=ts)를 붙인다 — 이 파일도 그렇게 한다.

토큰: keys.github() — 관리자 PC에만 있고 배포물에는 들어가지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
ZIP = os.path.join(ROOT, "dist", "nao_stock.zip")


def die(msg):
    print(f"\n■ 중단: {msg}")
    sys.exit(1)


def git(*a):
    return subprocess.run(["git"] + list(a), cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout.strip()


def repo_slug():
    m = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", git("remote", "get-url", "origin"))
    return m.group(1) if m else None


def main():
    import requests
    import keys

    repo = repo_slug() or die("origin 원격을 찾을 수 없습니다.")
    tok = keys.github() or die("발행용 GitHub 토큰이 없습니다(관리자 PC에서만 발행합니다).")
    H = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    bust = {"_": int(time.time() * 1000)}

    # ── 1) 순서 검사 — 코드가 먼저 올라가 있어야 태그가 제자리에 붙는다 ──
    if git("status", "--short"):
        die("커밋하지 않은 변경이 있습니다. 먼저 커밋·푸시하세요.")
    head = git("rev-parse", "HEAD")
    r = requests.get(f"https://api.github.com/repos/{repo}/commits/main",
                     headers=H, params=bust, timeout=30)
    remote = r.json().get("sha", "") if r.status_code == 200 else ""
    if head != remote:
        die(f"원격에 아직 안 올라간 커밋이 있습니다.\n"
            f"    로컬 {head[:8]} · 원격 {remote[:8] or '?'}\n"
            f"    먼저 `git push origin main` 을 하세요.")
    print(f"순서 확인: 로컬·원격 모두 {head[:8]} ✓")

    # ── 2) 패키지 검사 ──
    if not os.path.exists(ZIP):
        die("dist/nao_stock.zip 이 없습니다. `python release.py <버전> ...` 을 먼저 실행하세요.")
    v = json.load(open(os.path.join(ROOT, "version.json"), encoding="utf-8"))
    blob = open(ZIP, "rb").read()
    sha = hashlib.sha256(blob).hexdigest()
    if sha != v.get("sha256"):
        die("zip 해시가 version.json 과 다릅니다. release.py 를 다시 실행하세요.")
    tag = "v" + v["version"]
    print(f"패키지 확인: {tag} · {len(blob)/1024:.0f} KB · 해시 일치 ✓")

    if requests.get(f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
                    headers=H, params=bust, timeout=30).status_code == 200:
        die(f"{tag} 릴리스가 이미 있습니다.")

    # ── 3) 발행 ──
    body = "\n".join(f"- {n}" for n in v.get("notes", [])) + f"\n\nSHA256: {sha}\n"
    r = requests.post(f"https://api.github.com/repos/{repo}/releases", headers=H, timeout=60,
                      json={"tag_name": tag, "name": f"나오 주식 {tag}", "body": body,
                            "target_commitish": head, "draft": False, "prerelease": False})
    if r.status_code not in (200, 201):
        die(f"릴리스 생성 실패 {r.status_code}: {r.text[:200]}")
    rel = r.json()
    print("릴리스:", rel["html_url"])

    up = rel["upload_url"].split("{")[0] + "?name=nao_stock.zip"
    r = requests.post(up, headers={**H, "Content-Type": "application/zip"},
                      data=blob, timeout=300)
    if r.status_code not in (200, 201):
        die(f"zip 업로드 실패 {r.status_code}")
    print("zip 첨부 완료")

    # ── 4) 앱이 읽어낼 값 확인(캐시버스터 필수) ──
    import updater
    j = requests.get(f"https://api.github.com/repos/{repo}/releases/latest",
                     headers=H, params=bust, timeout=30).json()
    p = updater._parse_remote(j)
    t = requests.get(f"https://api.github.com/repos/{repo}/git/ref/tags/{tag}",
                     headers=H, params=bust, timeout=30).json()
    print(f"\n앱이 읽어낼 값 — {p['version']} · 해시 일치 {p['sha256'] == sha}")
    print(f"태그 대상 {t.get('object', {}).get('sha', '')[:8]} · 코드 커밋 일치 "
          f"{t.get('object', {}).get('sha') == head}")
    for n in p["notes"]:
        print("  ·", n)


if __name__ == "__main__":
    main()
