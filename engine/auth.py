# -*- coding: utf-8 -*-
"""
로그인 (관리자 + 사용자 계정)
=============================
성격: 개인 PC에서 도는 앱이므로 '보안 방벽'이라기보다 **누가 쓰는지 구분**하는 장치.
  · 사용자 계정 — 비밀번호 없이 클릭 한 번으로 입장(사용 편의 우선)
  · 어드민 계정 — 비밀번호 필요. 앞으로 관리 기능(공지 작성 등)을 여기에 건다.
  · API 키는 PC에 있는 것을 **두 계정 모두 동일하게** 사용한다(개발자 키 공유 방침).

저장: data/users.json (비밀번호는 PBKDF2-SHA256 해시, 평문 저장 안 함)
세션: 토큰을 발급해 클라이언트가 보관. 만료 30일(매번 로그인하지 않도록).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_USERS = os.path.join(_DIR, "data", "users.json")
_SESSION_DAYS = 30
_ITER = 120_000

_sessions = {}          # token -> {"user":..., "exp":...}


def _hash(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt.encode("utf-8"), _ITER)
    return salt, dk.hex()


def _load():
    if os.path.exists(_USERS):
        try:
            with open(_USERS, encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            pass
    return None


def _save(d):
    os.makedirs(os.path.dirname(_USERS), exist_ok=True)
    with open(_USERS, "w", encoding="utf-8") as fp:
        json.dump(d, fp, ensure_ascii=False, indent=1)


def ensure_users(admin_pw=None):
    """최초 실행 시 계정 생성. 어드민 비밀번호는 최초 1회 설정."""
    d = _load()
    if d:
        return d
    d = {"users": {
        "father": {"name": "내 계정", "role": "user", "no_password": True,
                   "salt": "", "hash": "", "created": time.strftime("%Y-%m-%d")},
        "admin": {"name": "관리자", "role": "admin", "no_password": admin_pw is None,
                  "salt": "", "hash": "", "created": time.strftime("%Y-%m-%d")},
    }}
    if admin_pw:
        s, h = _hash(admin_pw)
        d["users"]["admin"].update({"salt": s, "hash": h, "no_password": False})
    _save(d)
    return d


def set_password(user_id, pw):
    d = ensure_users()
    u = d["users"].get(user_id)
    if not u:
        return {"ok": False, "msg": "없는 계정입니다."}
    if pw:
        s, h = _hash(pw)
        u.update({"salt": s, "hash": h, "no_password": False})
    else:
        u.update({"salt": "", "hash": "", "no_password": True})
    _save(d)
    return {"ok": True, "msg": "비밀번호가 변경되었습니다."}


def accounts():
    """로그인 화면에 보여줄 계정 목록(해시는 제외)."""
    d = ensure_users()
    return [{"id": k, "name": v["name"], "role": v["role"],
             "no_password": bool(v.get("no_password"))}
            for k, v in d["users"].items()]


def login(user_id, pw=""):
    d = ensure_users()
    u = d["users"].get(user_id)
    if not u:
        return {"ok": False, "msg": "없는 계정입니다."}
    if not u.get("no_password"):
        if not pw:
            return {"ok": False, "msg": "비밀번호를 입력하세요."}
        _, h = _hash(pw, u["salt"])
        if not hmac.compare_digest(h, u["hash"]):
            return {"ok": False, "msg": "비밀번호가 맞지 않습니다."}
    token = secrets.token_urlsafe(24)
    _sessions[token] = {"user": user_id, "exp": time.time() + _SESSION_DAYS * 86400}
    return {"ok": True, "token": token, "user": {"id": user_id, "name": u["name"],
                                                 "role": u["role"]}}


def whoami(token):
    s = _sessions.get(token or "")
    if not s or s["exp"] < time.time():
        _sessions.pop(token, None)
        return None
    d = ensure_users()
    u = d["users"].get(s["user"])
    if not u:
        return None
    return {"id": s["user"], "name": u["name"], "role": u["role"]}


def logout(token):
    _sessions.pop(token or "", None)
    return {"ok": True}


def key_status():
    """어떤 API 키를 쓰고 있는지(값은 노출하지 않는다).
    실제 판정은 keys.py 한 곳에서만 — 모듈마다 경로를 따로 적던 것을 없앴다."""
    import keys
    s = keys.status()
    return {"kis": s["kis"]["set"], "krx": s["krx"]["set"],
            "note": "이 PC에 저장된 API 키를 사용합니다(계정 공용). "
                    "설정 → API 연결에서 바꿀 수 있습니다."}
