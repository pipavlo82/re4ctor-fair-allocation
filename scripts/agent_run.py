#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import time
import random
from pathlib import Path
from datetime import datetime, timezone

# ========= Config =========
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
AGENT_STATE_FILE = os.getenv("AGENT_STATE_FILE", "data/agent_state.json")
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "48"))
MIN_RELEVANCE_SCORE = int(os.getenv("MIN_RELEVANCE_SCORE", "2"))
REPLY_LANG = os.getenv("REPLY_LANG", "en").strip().lower()  # en | uk
DRY_RUN = int(os.getenv("DRY_RUN", "1"))
MAX_REPLIES = int(os.getenv("MAX_REPLIES", "2"))
COOLDOWN_AUTHOR_HOURS = int(os.getenv("COOLDOWN_AUTHOR_HOURS", "24"))

POST_ID = os.getenv("POST_ID", "").strip()
MB_BASE = os.getenv("MB_BASE", "https://www.moltbook.com").rstrip("/")
MOLTBOOK_API_KEY = os.getenv("MOLTBOOK_API_KEY", "").strip()

# Optional local inbox for dry-run/testing:
# data/inbox.json = [{"id":"c1","content":"...","author":"...","created_at":"..."}]
INBOX_FILE = os.getenv("INBOX_FILE", "data/inbox.json")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(path: str = AGENT_STATE_FILE) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state: dict, path: str = AGENT_STATE_FILE) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def normalize_text(s: str) -> str:
    return " ".join((s or "").strip().split())


def relevance_score(text: str) -> int:
    t = (text or "").lower()
    score = 0
    keywords = [
        "receipt", "verify", "verification", "signature", "signed", "proof",
        "drift", "allocation", "fair", "policy", "seed", "latency", "metrics",
        "dashboard", "reason code", "replay", "bad_sig", "mismatch"
    ]
    for k in keywords:
        if k in t:
            score += 1
    return score


def build_reply(text: str, lang: str = "en") -> str:
    if lang == "uk":
        variants = [
            "Дякую за коментар. Для прод-режиму рекомендую коротку щотижневу панель: coverage підписаних receipt, fail-rate за reason codes, p95 latency і post-allocation drift.",
            "Класне зауваження. Я б тримав 4 метрики: signed receipt coverage, verify fail rate (bad_sig/replay/policy_mismatch/seed_mismatch), p95 latency, drift rate.",
            "Підтримую. Мінімальний прод-набір: receipt coverage, reason-code fail rate, p95 verify latency, post-allocation drift. Можу скинути JSON-шаблон."
        ]
        return random.choice(variants)

    variants = [
        "Good point. For production, I’d track: signed receipt coverage, verify fail rate by reason code, p95 verification latency, and post-allocation drift rate.",
        "Makes sense. A compact weekly panel should include receipt coverage, reason-coded verification failures, p95 verify latency, and drift rate.",
        "Agreed. The minimum production dashboard is: signed receipt coverage, fail-rate by reason code, p95 verify latency, and post-allocation drift."
    ]
    return random.choice(variants)


def load_inbox(path: str = INBOX_FILE) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []



def _parse_iso(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def author_on_cooldown(author: str, state: dict) -> bool:
    if not author:
        return False
    last = (state.get("last_reply_at_by_author") or {}).get(author)
    if not last:
        return False
    dt = _parse_iso(last)
    if not dt:
        return False
    delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    return delta.total_seconds() < COOLDOWN_AUTHOR_HOURS * 3600

def mark_author_reply(author: str, state: dict) -> None:
    if not author:
        return
    state.setdefault("last_reply_at_by_author", {})
    state["last_reply_at_by_author"][author] = utc_now_iso()


def should_reply(comment_id: str, state: dict) -> bool:
    replied = state.get("replied_ids", [])
    if not isinstance(replied, list):
        replied = []
    return comment_id not in replied


def mark_replied(comment_id: str, state: dict) -> None:
    state.setdefault("replied_ids", [])
    if comment_id not in state["replied_ids"]:
        state["replied_ids"].append(comment_id)
    state["updated_at"] = utc_now_iso()


def process_local_inbox() -> int:
    state = load_state()
    inbox = load_inbox()
    sent = 0

    for item in inbox:
        if sent >= MAX_REPLIES:
            break

        cid = str(item.get("id", "")).strip()
        author = str(item.get("author", "")).strip().lower()
        text = normalize_text(str(item.get("content", "")))

        if not cid or not text:
            continue
        if not should_reply(cid, state):
            continue
        if author_on_cooldown(author, state):
            continue

        score = relevance_score(text)
        if score < MIN_RELEVANCE_SCORE:
            continue

        reply = build_reply(text, REPLY_LANG)

        if DRY_RUN:
            print(f"[DRY_RUN] would reply to {cid}: {reply}")
        else:
            # Placeholder for real API call (kept intentionally safe)
            print(f"[LIVE] reply to {cid}: {reply}")

        mark_replied(cid, state)
        mark_author_reply(author, state)
        sent += 1

    save_state(state)
    return sent


def validate_env_for_live() -> None:
    if not DRY_RUN:
        missing = []
        if not MOLTBOOK_API_KEY:
            missing.append("MOLTBOOK_API_KEY")
        if not POST_ID:
            missing.append("POST_ID")
        if missing:
            raise RuntimeError(f"Missing required env for live mode: {', '.join(missing)}")


def main() -> int:
    try:
        validate_env_for_live()
    except Exception as e:
        print(f"ERROR: {e}")
        return 2

    started = time.time()
    sent = process_local_inbox()
    elapsed = time.time() - started

    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": bool(DRY_RUN),
                "max_replies": MAX_REPLIES,
                "min_relevance_score": MIN_RELEVANCE_SCORE,
                "reply_lang": REPLY_LANG,
                "processed_replies": sent,
                "elapsed_sec": round(elapsed, 3),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
