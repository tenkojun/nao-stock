# -*- coding: utf-8 -*-
"""
원격 업데이트 (배포 후에도 계속 개선하기 위한 장치)
====================================================
흐름:
  1) 앱이 시작하면 백그라운드로 배포처의 version.json 확인
  2) 새 버전이 있으면 화면에 "업데이트 하시겠습니까?" 배너
  3) 승낙하면 zip 내려받아 **검증 → 백업 → 교체** 후 재시작 안내

안전장치(자문 J-187/J-188 반영):
  · **사용자 데이터는 절대 건드리지 않는다** — data/(기록장·보유·캐시), 설정, 비밀키는 보존.
  · 교체 전 **자동 백업**(backup/) → 문제 시 롤백 가능.
  · 다운로드 크기·해시 검증. 실패하면 아무것도 바꾸지 않는다.
  · **신호 로직이 바뀌면 변경내역을 사용자에게 보여준다**(과거 판단과의 불일치 고지).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import time
import zipfile
from datetime import datetime

import requests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VERSION_FILE = os.path.join(_ROOT, "version.json")
_CONFIG_FILE = os.path.join(_ROOT, "update_config.json")
_BACKUP_DIR = os.path.join(_ROOT, "backup")

# 업데이트 시 보존할 것(사용자 데이터·비밀·캐시)
_PRESERVE = ("data", "backup", "update_config.json", "krx api.txt", ".claude")

_state = {"checked": 0, "latest": None, "error": None}


def _local_version():
    try:
        with open(_VERSION_FILE, encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {"version": "0.0.0"}


def _config():
    """배포처 설정. update_config.json 예:
       {"url": "https://raw.githubusercontent.com/<user>/<repo>/main/nao_stock/version.json",
        "zip_url_template": "https://github.com/<user>/<repo>/releases/download/v{ver}/nao_stock.zip"}"""
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {}


def _parse_remote(j):
    """배포처 응답 정규화.
    · GitHub Releases API 응답이면 tag_name·body·assets 에서 뽑는다(CDN 캐시 없음, 권장)
    · 그냥 version.json 이면 그대로 사용"""
    if not isinstance(j, dict):
        return None
    if "tag_name" in j:                       # GitHub Releases API
        body = j.get("body") or ""
        m = re.search(r"SHA256[:\s`]*([0-9a-fA-F]{64})", body)
        notes = [l.lstrip("- ").strip() for l in body.splitlines()
                 if l.strip().startswith("-")]
        zurl = None
        for a in j.get("assets", []):
            if a.get("name", "").endswith(".zip"):
                zurl = a.get("browser_download_url")
                break
        return {"version": str(j["tag_name"]).lstrip("v"),
                "released": (j.get("published_at") or "")[:10],
                "notes": notes, "sha256": m.group(1) if m else None,
                "zip_url": zurl}
    return j


def _vtuple(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except Exception:
        return (0, 0, 0)


def check(force=False):
    """새 버전 확인. 30분 캐시. 반환: {current, latest, has_update, notes, error}"""
    cur = _local_version()
    out = {"current": cur.get("version", "0.0.0"), "latest": None,
           "has_update": False, "notes": [], "error": None}
    cfg = _config()
    url = cfg.get("url")
    if not url:
        out["error"] = "배포처가 설정되지 않았습니다(update_config.json)."
        return out
    if not force and time.time() - _state["checked"] < 1800 and _state["latest"]:
        remote = _state["latest"]
    else:
        try:
            r = requests.get(url, timeout=10, params={"_": int(time.time())},
                             headers={"Cache-Control": "no-cache",
                                      "Accept": "application/vnd.github+json"})
            remote = _parse_remote(r.json()) if r.status_code == 200 else None
            _state["checked"] = time.time()
            _state["latest"] = remote
        except Exception as e:
            out["error"] = f"확인 실패: {type(e).__name__}"
            return out
    if not remote:
        out["error"] = "배포처 응답이 없습니다."
        return out
    out["latest"] = remote.get("version")
    out["notes"] = remote.get("notes", [])
    out["released"] = remote.get("released", "")
    out["has_update"] = _vtuple(out["latest"]) > _vtuple(out["current"])
    return out


def _backup():
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(_BACKUP_DIR, stamp)
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(_ROOT):
        if name in _PRESERVE or name == "backup":
            continue
        src = os.path.join(_ROOT, name)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(dest, name),
                                ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, os.path.join(dest, name))
        except Exception:
            continue
    # 오래된 백업 정리(최근 3개만)
    backups = sorted(os.listdir(_BACKUP_DIR))
    for old in backups[:-3]:
        shutil.rmtree(os.path.join(_BACKUP_DIR, old), ignore_errors=True)
    return dest


def apply_update():
    """새 버전 zip을 받아 적용. 반환 {ok, msg, backup}"""
    info = check(force=True)
    if info.get("error"):
        return {"ok": False, "msg": info["error"]}
    if not info["has_update"]:
        return {"ok": False, "msg": "이미 최신 버전입니다."}
    cfg = _config()
    remote = _state.get("latest") or {}
    zurl = remote.get("zip_url")                      # Releases API가 준 실제 자산 주소 우선
    if not zurl:
        tmpl = cfg.get("zip_url_template")
        if not tmpl:
            return {"ok": False, "msg": "업데이트 파일 주소가 설정되지 않았습니다."}
        zurl = tmpl.format(ver=info["latest"])
    try:
        r = requests.get(zurl, timeout=60)
        if r.status_code != 200 or len(r.content) < 1000:
            return {"ok": False, "msg": f"내려받기 실패(HTTP {r.status_code})."}
        blob = r.content
        sha = hashlib.sha256(blob).hexdigest()
        expect = (_state.get("latest") or {}).get("sha256")   # 배포처 version.json의 해시
        if expect and expect != sha:
            return {"ok": False, "msg": "파일 검증 실패(위변조 의심) — 업데이트를 중단했습니다."}
        if not expect:
            return {"ok": False, "msg": "배포처에 검증 해시가 없어 중단했습니다."}
        zf = zipfile.ZipFile(io.BytesIO(blob))
        bad = [n for n in zf.namelist() if n.startswith("/") or ".." in n]
        if bad:
            return {"ok": False, "msg": "안전하지 않은 파일이 포함되어 중단했습니다."}
    except Exception as e:
        return {"ok": False, "msg": f"내려받기 오류: {type(e).__name__}"}

    bak = _backup()
    try:
        for n in zf.namelist():
            rel = n.split("/", 1)[1] if "/" in n and n.split("/", 1)[0].startswith("nao_stock") else n
            if not rel or rel.endswith("/"):
                continue
            top = rel.split("/")[0]
            if top in _PRESERVE:            # 사용자 데이터 보존
                continue
            dst = os.path.join(_ROOT, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with zf.open(n) as s, open(dst, "wb") as d:
                shutil.copyfileobj(s, d)
        return {"ok": True, "backup": bak,
                "msg": f"v{info['latest']} 적용 완료. 앱을 다시 시작하면 반영됩니다.",
                "notes": info.get("notes", [])}
    except Exception as e:
        return {"ok": False, "msg": f"적용 중 오류: {type(e).__name__}. 백업: {bak}"}


def rollback():
    """가장 최근 백업으로 되돌리기."""
    if not os.path.isdir(_BACKUP_DIR):
        return {"ok": False, "msg": "백업이 없습니다."}
    backups = sorted(os.listdir(_BACKUP_DIR))
    if not backups:
        return {"ok": False, "msg": "백업이 없습니다."}
    src = os.path.join(_BACKUP_DIR, backups[-1])
    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(_ROOT, name)
        try:
            if os.path.isdir(s):
                shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)
        except Exception:
            continue
    return {"ok": True, "msg": f"{backups[-1]} 백업으로 되돌렸습니다. 앱을 다시 시작하세요."}
