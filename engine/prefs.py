# -*- coding: utf-8 -*-
"""
사용자 설정·보유종목 서버 저장 (업데이트에도 안 날아가게)
=========================================================
문제: 설정(nao_set)·보유종목(nao_pf)·이번 달 금액(nao_budget)이 **브라우저 localStorage**에만
      있어 ①브라우저 데이터를 지우면 사라지고 ②백업도 안 되고 ③복구 수단이 없었다.
해결: `data/prefs.json` 에 서버 저장. `data/`는 업데이트 시 **보존 대상**(updater._PRESERVE)이라
      새 버전으로 교체돼도 그대로 남는다. localStorage 는 오프라인 캐시로만 사용.

저장 항목: settings(화면설정) · portfolio(보유종목) · budget(이번 달 금액) · watchlist(관심종목)
저장하지 않는 것: 로그인 토큰(브라우저에만) — 계정 보안상 서버에 두지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil
import time

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(_DIR, "data", "prefs.json")
_BAK = os.path.join(_DIR, "data", "prefs.bak.json")

_ALLOWED = ("settings", "portfolio", "budget", "watchlist", "avg_prices")


def load(user="father"):
    if not os.path.exists(_PATH):
        return {}
    try:
        with open(_PATH, encoding="utf-8") as fp:
            d = json.load(fp)
        return d.get(user, {})
    except Exception:
        # 손상 시 백업본 시도
        if os.path.exists(_BAK):
            try:
                with open(_BAK, encoding="utf-8") as fp:
                    return json.load(fp).get(user, {})
            except Exception:
                pass
        return {}


def save(user="father", patch=None):
    """부분 갱신(patch). 허용된 키만 저장하고, 쓰기 전 백업을 남긴다."""
    patch = patch or {}
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    all_d = {}
    if os.path.exists(_PATH):
        try:
            with open(_PATH, encoding="utf-8") as fp:
                all_d = json.load(fp)
        except Exception:
            all_d = {}
        try:
            shutil.copy2(_PATH, _BAK)          # 덮어쓰기 전 백업
        except Exception:
            pass
    cur = all_d.get(user, {})
    for k, v in patch.items():
        if k in _ALLOWED:
            cur[k] = v
    cur["updated"] = time.strftime("%Y-%m-%d %H:%M")
    all_d[user] = cur
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:      # 원자적 쓰기(중간에 꺼져도 손상 없음)
        json.dump(all_d, fp, ensure_ascii=False, indent=1)
    os.replace(tmp, _PATH)
    return cur


def status():
    """저장 상태 요약 — 화면에 '안전하게 보관 중'을 보여주기 위한 정보."""
    if not os.path.exists(_PATH):
        return {"exists": False}
    try:
        st = os.stat(_PATH)
        with open(_PATH, encoding="utf-8") as fp:
            d = json.load(fp)
        users = {}
        for u, v in d.items():
            users[u] = {"portfolio": len(v.get("portfolio") or {}),
                        "watchlist": len(v.get("watchlist") or []),
                        "updated": v.get("updated", "")}
        return {"exists": True, "path": "data/prefs.json",
                "size": st.st_size, "users": users,
                "note": "업데이트해도 이 파일은 그대로 유지됩니다."}
    except Exception as e:
        return {"exists": True, "error": f"{type(e).__name__}"}
