# -*- coding: utf-8 -*-
"""
공지 게시판 — GitHub 중계 방식
================================
이 앱은 PC마다 **자기 Flask 서버**를 띄운다. 공유 서버가 없으므로 한 PC에서 쓴 글은
그 PC 디스크에만 남는다. 그래서 이미 쓰고 있는 GitHub를 통로로 재활용한다.

  관리자 PC ── 글 작성 ──▶ GitHub 저장소의 notices.json ──▶ 다른 PC 앱이 주기적으로 받아감

  · 읽기: 공개 저장소라 **토큰이 필요 없다**. 아버지 PC에는 아무 비밀도 두지 않는다.
  · 쓰기: 관리자 PC의 GitHub 토큰이 있어야 한다(keys.github()).
  · 지연: 진짜 실시간(푸시)이 아니라 **폴링**이다. 앱을 켜는 순간 + 몇 분 간격.
    상시 접속 서버 없이 push 알림을 만들 수는 없다.

⚠ 저장소가 **공개**이므로 여기에 쓰는 글은 누구나 볼 수 있다.
   개인정보·계좌·수익률은 쓰지 말 것. UI에도 같은 경고를 띄운다.

캐시: data/notices_cache.json (받아온 글) · data/notices_read.json (읽음 표시)
"""
from __future__ import annotations

import base64
import json
import os
import re
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG = os.path.join(_ROOT, "update_config.json")
_CACHE = os.path.join(_ROOT, "data", "notices_cache.json")
_READ = os.path.join(_ROOT, "data", "notices_read.json")
_PATH_IN_REPO = "notices.json"
_MAX = 50                      # 오래된 글은 잘라낸다(파일이 무한정 커지지 않게)
_TTL = 150                     # 같은 요청을 2분 반 안에 반복하지 않는다

_state = {"at": 0, "data": None}


# ── 공통 ──────────────────────────────────────────────────────────
def _repo():
    """update_config.json 의 배포처 URL에서 owner/repo 를 뽑는다(설정 파일 하나로 유지)."""
    try:
        with open(_CONFIG, encoding="utf-8") as fp:
            url = json.load(fp).get("url", "")
    except Exception:
        return None
    m = re.search(r"repos/([^/]+/[^/]+)/", url) or re.search(r"github\.com/([^/]+/[^/]+)", url)
    return m.group(1).replace(".git", "") if m else None


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _api(repo, token=None):
    # ⚠ Contents API 도 캐시된다. 캐시버스터(_=ts) 없이 조회하면 **삭제·수정 직전 내용**이
    #    그대로 돌아온다(실측 확인). no-cache 헤더까지 같이 보낸다.
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
         "Cache-Control": "no-cache", "Pragma": "no-cache"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return f"https://api.github.com/repos/{repo}/contents/{_PATH_IN_REPO}", h


# ── 받아오기 ──────────────────────────────────────────────────────
def _remote(repo):
    """저장소에서 공지 파일을 읽는다. raw.githubusercontent 는 CDN 캐시가 있어 쓰지 않는다.
    반환: (목록, sha) — 파일이 없으면 ([], None)."""
    import requests
    from keys import github as _tok
    url, h = _api(repo, _tok() or None)
    r = requests.get(url, headers=h, params={"ref": "main", "_": int(time.time())},
                     timeout=12)
    if r.status_code == 404:
        return [], None
    r.raise_for_status()
    j = r.json()
    raw = base64.b64decode(j.get("content", "") or "").decode("utf-8") or "{}"
    return (json.loads(raw).get("notices") or []), j.get("sha")


def fetch(force=False):
    """공지를 받아 로컬 캐시에 저장. 실패해도 캐시로 계속 동작한다."""
    if not force and time.time() - _state["at"] < _TTL and _state["data"] is not None:
        return _state["data"]
    repo = _repo()
    if not repo:
        return {"ok": False, "msg": "배포처가 설정되지 않았습니다(update_config.json).",
                "notices": _load(_CACHE, {}).get("notices", [])}
    try:
        items, _sha = _remote(repo)
    except Exception as e:
        return {"ok": False, "msg": f"불러오지 못했습니다({type(e).__name__}).",
                "notices": _load(_CACHE, {}).get("notices", [])}
    items = sorted(items, key=lambda x: str(x.get("at", "")), reverse=True)[:_MAX]
    _save(_CACHE, {"notices": items, "fetched": time.strftime("%Y-%m-%d %H:%M")})
    out = {"ok": True, "notices": items}
    _state.update(at=time.time(), data=out)
    return out


# ── 읽음 표시 ─────────────────────────────────────────────────────
def _read_ids(user):
    return set(_load(_READ, {}).get(user, []))


def mark_read(user, ids=None):
    d = _load(_READ, {})
    cur = set(d.get(user, []))
    cur |= set(ids or [n["id"] for n in fetch().get("notices", []) if n.get("id")])
    d[user] = sorted(cur)[-200:]
    _save(_READ, d)
    return {"ok": True, "unread": 0}


def board(user="father", force=False, kind=None):
    """화면에 줄 최종 형태 — 글 목록 + 안 읽은 개수.
    kind: 'notice'(짧은 알림) | 'article'(정보글). None 이면 전부."""
    got = fetch(force)
    seen = _read_ids(user)
    items = []
    for n in got.get("notices", []):
        k = n.get("kind") or "notice"          # 옛 글은 kind 가 없다 → 공지로 본다
        if kind and k != kind:
            continue
        items.append({**n, "kind": k, "unread": bool(n.get("id") and n["id"] not in seen)})
    return {"ok": got.get("ok", False), "msg": got.get("msg"), "kind": kind,
            "notices": items, "unread": sum(1 for i in items if i["unread"]),
            "fetched": _load(_CACHE, {}).get("fetched")}


# ── 발행(관리자 PC 전용) ──────────────────────────────────────────
def publish(title, body, author="관리자", kind="notice"):
    """글을 저장소에 올린다. **공개 저장소이므로 내용이 공개된다.**
    kind: 'notice'(짧은 알림) | 'article'(정보글 — 길게 써도 된다)"""
    title, body = (title or "").strip(), (body or "").strip()
    kind = "article" if kind == "article" else "notice"
    limit = 20000 if kind == "article" else 4000
    if not title:
        return {"ok": False, "msg": "제목을 입력해 주세요."}
    if len(title) > 80:
        return {"ok": False, "msg": "제목은 80자 이내로 써 주세요."}
    if len(body) > limit:
        return {"ok": False, "msg": f"내용이 너무 깁니다({limit:,}자 이내)."}
    repo = _repo()
    if not repo:
        return {"ok": False, "msg": "배포처가 설정되지 않았습니다(update_config.json)."}

    from keys import github as _tok
    token = _tok()
    if not token:
        return {"ok": False, "msg": "이 PC에는 발행용 GitHub 토큰이 없습니다(관리자 PC에서만 씁니다)."}

    import requests
    try:
        items, sha = _remote(repo)
    except Exception as e:
        return {"ok": False, "msg": f"기존 글을 읽지 못했습니다({type(e).__name__})."}

    items.insert(0, {"id": f"n{int(time.time())}", "at": time.strftime("%Y-%m-%d %H:%M"),
                     "title": title, "body": body, "author": author, "kind": kind})
    items = items[:_MAX]
    payload = json.dumps({"notices": items}, ensure_ascii=False, indent=1)

    url, h = _api(repo, token)
    data = {"message": f"{'정보글' if kind == 'article' else '공지'}: {title[:50]}",
            "content": base64.b64encode(payload.encode("utf-8")).decode("ascii"),
            "branch": "main"}
    if sha:
        data["sha"] = sha                       # 기존 파일 갱신 — 없으면 새로 만든다
    r = requests.put(url, headers=h, json=data, timeout=30)
    if r.status_code not in (200, 201):
        detail = ""
        try:
            detail = r.json().get("message", "")
        except Exception:
            pass
        return {"ok": False, "msg": f"올리지 못했습니다(HTTP {r.status_code}). {detail}"[:160]}

    _state["at"] = 0                            # 캐시 무효화 → 바로 다시 받아온다
    fetch(force=True)
    return {"ok": True, "msg": "공지를 올렸습니다. 다른 PC에는 몇 분 안에 나타납니다."}


def remove(nid):
    """공지 삭제(관리자)."""
    repo = _repo()
    from keys import github as _tok
    token = _tok()
    if not repo or not token:
        return {"ok": False, "msg": "관리자 PC에서만 삭제할 수 있습니다."}
    import requests
    try:
        items, sha = _remote(repo)
    except Exception as e:
        return {"ok": False, "msg": f"읽지 못했습니다({type(e).__name__})."}
    left = [n for n in items if n.get("id") != nid]
    if len(left) == len(items):
        return {"ok": False, "msg": "이미 없는 글입니다."}
    url, h = _api(repo, token)
    r = requests.put(url, headers=h, timeout=30, json={
        "message": "공지 삭제", "branch": "main", "sha": sha,
        "content": base64.b64encode(
            json.dumps({"notices": left}, ensure_ascii=False, indent=1).encode()).decode("ascii")})
    if r.status_code not in (200, 201):
        return {"ok": False, "msg": f"삭제하지 못했습니다(HTTP {r.status_code})."}
    _state["at"] = 0
    fetch(force=True)
    return {"ok": True, "msg": "삭제했습니다."}
