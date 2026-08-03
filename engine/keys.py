# -*- coding: utf-8 -*-
"""
API 키 보관 — 한 곳에서만 결정한다
====================================
예전에는 모듈마다 키 경로를 따로 적어 두었고, kis_kr.py 는 개발자 PC 경로를
그대로 박아 두어(`C:\\Users\\jun\\...`) **다른 사람 PC에서는 KIS가 붙지 않았다.**
이 모듈이 읽기 후보와 쓰기 위치를 한 번에 정한다.

읽기 순서
  1) 환경변수 (KIS_SECRET · KRX_AUTH_KEY · ANTHROPIC_API_KEY)
  2) 앱 폴더      data/keys/               ← 설정 화면 저장분·USB 가져오기분
  3) 사용자 폴더  ~/ft_freqai/user_data/   ← 개발 PC의 기존 관례(하위 호환)

  ⚠ 앱 폴더가 **먼저**다. 그래야 USB로 가져온 키가 개발 PC의 옛 키에 가려지지 않는다.

쓰기 위치
  항상 앱 폴더(data/keys/). `data/` 는 업데이트 보존 목록이고 패키징·git 에서
  제외되므로 키가 배포물에 섞이지 않고, 앱을 통째로 옮겨도 따라간다.

⚠ 키 값은 **절대 밖으로 내보내지 않는다.** status() 는 존재 여부와 끝 4자리만 준다.
"""
from __future__ import annotations

import json
import os

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_KEYS = os.path.join(_DIR, "data", "keys")
_USER_KEYS = os.path.join(os.path.expanduser("~"), "ft_freqai", "user_data")

KIS_FILE, KRX_FILE, NAO_FILE = "kis_secret.json", "krx_secret.json", "nao_keys.json"
KIS_SECTION = os.environ.get("KIS_SECTION", "kr_stocks")


# ── 경로 ──────────────────────────────────────────────────────────
def _candidates(fname):
    return [os.path.join(_APP_KEYS, fname), os.path.join(_USER_KEYS, fname)]


def _find(fname):
    """이미 있는 파일을 찾는다. 없으면 None."""
    for p in _candidates(fname):
        if os.path.exists(p):
            return p
    return None


def _write_target(fname):
    """새로 저장할 위치 — 항상 앱 폴더. 앱을 옮기면 키도 같이 간다."""
    os.makedirs(_APP_KEYS, exist_ok=True)
    return os.path.join(_APP_KEYS, fname)


def kis_path():
    """kis_kr.py 가 쓸 경로. 환경변수가 최우선."""
    return os.environ.get("KIS_SECRET") or _find(KIS_FILE) or _write_target(KIS_FILE)


def krx_candidates():
    """krx_api.py 가 훑을 후보 목록."""
    return _candidates(KRX_FILE)


# ── 읽기 ──────────────────────────────────────────────────────────
def _read(fname):
    p = _find(fname)
    if not p:
        return {}
    try:
        with open(p, encoding="utf-8") as fp:
            return json.load(fp) or {}
    except Exception:
        return {}


def _save(fname, data):
    """원자적 쓰기 — 중간에 꺼져도 기존 파일이 깨지지 않는다.
    ⚠ 항상 앱 폴더에 쓴다. 사용자 폴더의 원본(다른 프로젝트가 쓸 수 있다)은 건드리지 않고,
       앱 폴더가 우선순위가 높으므로 이 사본이 실제로 쓰인다."""
    p = _write_target(fname)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return p


def anthropic():
    """Claude 키 — 환경변수 우선, 없으면 저장된 값."""
    return (os.environ.get("ANTHROPIC_API_KEY")
            or str(_read(NAO_FILE).get("anthropic", "")).strip())


def krx_auth():
    return (os.environ.get("KRX_AUTH_KEY")
            or str(_read(KRX_FILE).get("auth_key", "")).strip())


def github():
    """공지 **발행용** GitHub 토큰 — 관리자 PC에만 둔다.
    공지를 '읽는' 쪽(공개 저장소)은 토큰이 필요 없다. 이 파일은 배포물에 들어가지 않는다."""
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"].strip()
    for c in (os.path.join(_APP_KEYS, "github_token.txt"),
              os.path.join(_USER_KEYS, "github_token.txt")):
        if os.path.exists(c):
            try:
                with open(c, encoding="utf-8-sig") as fp:
                    return fp.read().strip()
            except Exception:
                pass
    return ""


# ── 상태(값 노출 없음) ────────────────────────────────────────────
def _mask(v):
    v = str(v or "")
    return ("•" * 8 + v[-4:]) if len(v) > 4 else ("••••" if v else "")


def _mask_acct(v):
    v = str(v or "")
    if "-" in v:
        head, tail = v.split("-", 1)
        return (head[:4] + "*" * max(0, len(head) - 4)) + "-" + tail
    return _mask(v)


def status():
    """설정 화면에 보낼 요약. **키 값 자체는 담지 않는다.**"""
    kis = _read(KIS_FILE).get(KIS_SECTION, {}) or {}
    krx_v, cla_v = krx_auth(), anthropic()
    # 실제로 어느 파일이 쓰이고 있는지 그대로 보고한다(짐작하지 않는다)
    p = _find(KIS_FILE) or _find(KRX_FILE)
    if not p:
        where = "없음"
    elif os.path.normcase(p).startswith(os.path.normcase(_APP_KEYS)):
        where = "앱 폴더(data/keys)"
    else:
        where = "사용자 폴더(ft_freqai/user_data)"
    return {
        "kis": {"set": bool(kis.get("appkey") and kis.get("appsecret")),
                "hint": _mask(kis.get("appkey")),
                "account": _mask_acct(kis.get("account")),
                "paper": bool(kis.get("paper", False)),
                "env": bool(os.environ.get("KIS_SECRET"))},
        "krx": {"set": bool(krx_v), "hint": _mask(krx_v),
                "env": bool(os.environ.get("KRX_AUTH_KEY"))},
        "claude": {"set": bool(cla_v), "hint": _mask(cla_v),
                   "env": bool(os.environ.get("ANTHROPIC_API_KEY"))},
        "where": where,
    }


# ── 저장 ──────────────────────────────────────────────────────────
def save(provider, v):
    """빈 값으로 온 항목은 **기존 값을 유지**한다(마스킹만 보고 다시 칠 수 없으므로)."""
    v = v or {}
    if provider == "kis":
        d = _read(KIS_FILE)
        cur = d.get(KIS_SECTION, {}) or {}
        for k_in, k_out in (("appkey", "appkey"), ("appsecret", "appsecret"),
                            ("account", "account")):
            nv = str(v.get(k_in, "")).strip()
            if nv:
                cur[k_out] = nv
        if "paper" in v:
            cur["paper"] = bool(v["paper"])
        if not (cur.get("appkey") and cur.get("appsecret")):
            return {"ok": False, "msg": "APP KEY 와 APP SECRET 을 모두 입력해 주세요."}
        d[KIS_SECTION] = cur
        _save(KIS_FILE, d)
        return {"ok": True, "msg": "한국투자증권 키를 저장했습니다."}

    if provider == "krx":
        nv = str(v.get("auth_key", "")).strip()
        if not nv:
            return {"ok": False, "msg": "인증키를 입력해 주세요."}
        d = _read(KRX_FILE)
        d["auth_key"] = nv
        _save(KRX_FILE, d)
        return {"ok": True, "msg": "KRX 인증키를 저장했습니다."}

    if provider == "claude":
        nv = str(v.get("api_key", "")).strip()
        if not nv:
            return {"ok": False, "msg": "키를 입력해 주세요."}
        d = _read(NAO_FILE)
        d["anthropic"] = nv
        _save(NAO_FILE, d)
        return {"ok": True, "msg": "Claude 키를 저장했습니다."}

    return {"ok": False, "msg": "알 수 없는 항목입니다."}


def import_files(files):
    """USB 등에서 가져온 키 **파일**을 앱 폴더에 들인다.
    files: [{"name": "kis_secret.json", "text": "..."}]
    파일 이름이 달라도 내용을 보고 무엇인지 알아낸다(USB에서 이름이 바뀌는 일이 흔하다)."""
    got, skipped = [], []
    for f in (files or []):
        name = str(f.get("name") or "").strip()
        text = (f.get("text") or "").strip()
        if not text:
            skipped.append(f"{name}: 비어 있음")
            continue
        if len(text) > 200_000:
            skipped.append(f"{name}: 너무 큼")
            continue

        obj = None
        try:
            obj = json.loads(text)
        except Exception:
            obj = None

        # ── 무엇인지 판별 ──
        if isinstance(obj, dict) and any(
                isinstance(v, dict) and v.get("appkey") and v.get("appsecret")
                for v in obj.values()):
            merged = _read(KIS_FILE)
            merged.update(obj)                       # 여러 섹션이 있어도 합친다
            _save(KIS_FILE, merged)
            secs = [k for k, v in obj.items()
                    if isinstance(v, dict) and v.get("appkey")]
            got.append(f"한국투자증권 ({', '.join(secs)})")
        elif isinstance(obj, dict) and obj.get("auth_key"):
            d = _read(KRX_FILE)
            d["auth_key"] = str(obj["auth_key"]).strip()
            _save(KRX_FILE, d)
            got.append("KRX 인증키")
        elif isinstance(obj, dict) and obj.get("anthropic"):
            d = _read(NAO_FILE)
            d["anthropic"] = str(obj["anthropic"]).strip()
            _save(NAO_FILE, d)
            got.append("Claude 키")
        elif not obj and "krx" in name.lower():        # 인증키만 적힌 txt
            d = _read(KRX_FILE)
            d["auth_key"] = text.splitlines()[0].strip()
            _save(KRX_FILE, d)
            got.append("KRX 인증키(txt)")
        elif not obj and text.startswith(("sk-ant-", "sk-")):
            d = _read(NAO_FILE)
            d["anthropic"] = text.splitlines()[0].strip()
            _save(NAO_FILE, d)
            got.append("Claude 키(txt)")
        else:
            skipped.append(f"{name or '이름없음'}: 무슨 키인지 알 수 없음")

    if not got:
        return {"ok": False,
                "msg": "가져올 키를 찾지 못했습니다. " + (" / ".join(skipped) if skipped else "")}

    # 방금 넣은 KIS 로 토큰을 미리 받아둔다.
    # 안 그러면 **바로 다음 조회 한 번**이 토큰 발급을 기다리다 합성 폴백으로 떨어져,
    # 키를 넣자마자 엉뚱한 값을 보게 된다(실제로 그랬다).
    if any("한국투자증권" in g for g in got):
        try:
            import kis_kr
            kis_kr.KISKorea().quote("005930")
        except Exception:
            pass

    msg = "가져왔습니다 — " + ", ".join(got)
    if skipped:
        msg += f" (건너뜀: {len(skipped)}개)"
    return {"ok": True, "msg": msg}


def clear(provider):
    if provider == "kis":
        d = _read(KIS_FILE)
        d.pop(KIS_SECTION, None)
        _save(KIS_FILE, d)
    elif provider == "krx":
        d = _read(KRX_FILE)
        d.pop("auth_key", None)
        _save(KRX_FILE, d)
    elif provider == "claude":
        d = _read(NAO_FILE)
        d.pop("anthropic", None)
        _save(NAO_FILE, d)
    else:
        return {"ok": False, "msg": "알 수 없는 항목입니다."}
    return {"ok": True, "msg": "삭제했습니다."}


def test(provider):
    """실제로 연결되는지 확인 — 저장 직후 '되는지' 알려주기 위한 것."""
    try:
        if provider == "kis":
            import kis_kr
            q = kis_kr.KISKorea().quote("005930")
            px = (q or {}).get("price")
            return {"ok": True, "msg": f"연결 성공 — 삼성전자 {px:,.0f}원을 받았습니다."
                    if px else "연결 성공 — 응답을 받았습니다."}
        if provider == "krx":
            import datetime as _dt
            import krx_api
            d = _dt.date.today() - _dt.timedelta(days=1)
            while d.weekday() >= 5:                     # 주말은 데이터가 없다
                d -= _dt.timedelta(days=1)
            rows = krx_api.daily_market(d.strftime("%Y%m%d"), market="KOSPI")
            return {"ok": True, "msg": f"연결 성공 — {len(rows)}종목 응답."
                    if rows else "연결은 됐지만 해당 날짜 데이터가 없습니다(휴장일일 수 있습니다)."}
        if provider == "claude":
            import requests
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers={"x-api-key": anthropic(),
                                       "anthropic-version": "2023-06-01",
                                       "content-type": "application/json"},
                              json={"model": "claude-haiku-4-5-20251001",
                                    "max_tokens": 4,
                                    "messages": [{"role": "user", "content": "hi"}]},
                              timeout=25)
            if r.status_code == 200:
                return {"ok": True, "msg": "연결 성공."}
            return {"ok": False, "msg": f"응답 {r.status_code} — 키를 다시 확인해 주세요."}
    except Exception as e:
        return {"ok": False, "msg": f"연결 실패: {str(e)[:120]}"}
    return {"ok": False, "msg": "알 수 없는 항목입니다."}
