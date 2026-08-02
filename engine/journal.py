# -*- coding: utf-8 -*-
"""
의사결정 기록장 (Decision Journal) — 자문 K-198 최우선 권고
==========================================================
왜 이것이 다른 무엇보다 우선인가(자문 원문 요약):
  1. 과거 데이터는 전부 여러 번 들여다봐 오염됐다. **미래의 실제 의사결정만이 깨끗한 홀드아웃**이다.
  2. "앱이 X를 표시했을 때 무엇을 했고 결과가 어땠는가"를 6~12개월 뒤 답할 수 있게 한다.
  3. 매도 시 **매수 이유를 다시 보여주면 처분효과가 줄어든다** — 데이터가 쌓이기 전부터 유용.
  4. "왜 사는가"를 한 줄 쓰게 하는 것만으로 충동 매수가 준다(최저비용·최고효과 행동 개입).
  5. 보유계획과 실제 보유기간을 대조해 "3개월 계획이었는데 3주 만에 파셨습니다" 피드백 가능.

⚠ 설계 원칙: **당시 표시값을 그대로 저장하고 절대 소급 수정하지 않는다**(자문 J-188).
   신호 로직이 바뀌어도 과거 기록은 그때의 값으로 남아야 비교가 가능하다.

저장: data/journal.jsonl (한 줄 = 한 기록, append-only)
"""
from __future__ import annotations
import json
import os
from datetime import datetime, date

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(_DIR, "data", "journal.jsonl")

# 2026년 기준 매도 비용(자문 A-13): 증권거래세+농특세 0.20%, 매수는 0
SELL_TAX = 0.0020
FEE = 0.00015          # 온라인 위탁수수료 + 유관기관 제비용(대략)

PLANS = {"3m": "3개월 정도", "1y": "1년 정도", "long": "그 이상(장기)", "": "미정"}


def _load():
    if not os.path.exists(_PATH):
        return []
    out = []
    with open(_PATH, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    return out


def add_entry(code, name, side, amount, plan="", reason="", snapshot=None):
    """기록 추가. snapshot = 당시 앱 표시값(진입 band·지표 등) — 소급 수정 금지."""
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    now = datetime.now()
    amt = float(amount or 0)
    entry = {
        "id": now.strftime("%Y%m%d%H%M%S%f"),
        "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M"),
        "code": str(code), "name": name or str(code),
        "side": "sell" if side == "sell" else "buy",
        "amount": amt, "plan": plan or "", "reason": (reason or "").strip(),
        "snapshot": snapshot or {},          # 당시 화면값(동결)
    }
    if entry["side"] == "sell":              # 매도 실비용(자문 A-13·(5))
        entry["tax"] = round(amt * SELL_TAX)
        entry["fee"] = round(amt * FEE)
    else:
        entry["tax"] = 0
        entry["fee"] = round(amt * FEE)
    with open(_PATH, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def entries(code=None, limit=200):
    rows = _load()
    if code:
        rows = [r for r in rows if r.get("code") == str(code)]
    rows.sort(key=lambda r: r.get("id", ""), reverse=True)
    return rows[:limit]


def _dday(d1, d2):
    try:
        return (date.fromisoformat(d2) - date.fromisoformat(d1)).days
    except Exception:
        return None


def context_for(code):
    """이 종목을 팔려 할 때 보여줄 것: 처음 산 이유·보유계획·실제 보유일·누적 매수액."""
    rows = [r for r in _load() if r.get("code") == str(code)]
    buys = [r for r in rows if r["side"] == "buy"]
    if not buys:
        return None
    buys.sort(key=lambda r: r["id"])
    first = buys[0]
    held = _dday(first["date"], date.today().isoformat())
    total_buy = sum(r["amount"] for r in buys)
    sells = [r for r in rows if r["side"] == "sell"]
    plan_days = {"3m": 90, "1y": 365, "long": 1095}.get(first.get("plan"), None)
    early = (plan_days is not None and held is not None and held < plan_days * 0.5)
    return {
        "first_date": first["date"], "first_reason": first.get("reason", ""),
        "plan": PLANS.get(first.get("plan", ""), "미정"), "plan_days": plan_days,
        "held_days": held, "buy_count": len(buys), "sell_count": len(sells),
        "total_buy": total_buy, "early_exit": early,
        "note": (f"{first['date']}에 처음 사시면서 '{first.get('reason') or '이유 미기록'}'라고 적으셨고, "
                 f"보유계획은 '{PLANS.get(first.get('plan',''),'미정')}'였습니다. "
                 f"지금 {held}일째입니다." if held is not None else ""),
    }


def stats():
    rows = _load()
    if not rows:
        return {"n": 0}
    buys = [r for r in rows if r["side"] == "buy"]
    sells = [r for r in rows if r["side"] == "sell"]
    tax_paid = sum(r.get("tax", 0) for r in sells)
    with_reason = sum(1 for r in rows if r.get("reason"))
    return {"n": len(rows), "buys": len(buys), "sells": len(sells),
            "buy_amount": sum(r["amount"] for r in buys),
            "sell_amount": sum(r["amount"] for r in sells),
            "tax_paid": tax_paid,
            "reason_rate": round(with_reason / len(rows) * 100),
            "note": (f"매도 {len(sells)}회로 지금까지 세금·수수료 약 {tax_paid:,.0f}원을 냈습니다. "
                     "매수에는 세금이 없고 매도에만 0.20%가 붙습니다." if sells else
                     "아직 매도 기록이 없습니다. 매수에는 세금이 없습니다.")}
