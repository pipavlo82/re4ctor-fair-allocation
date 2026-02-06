#!/usr/bin/env python3
import json
import re
from collections import Counter

SELF_NAME = "Re4ctoRTrust"

SPAM_PATTERNS = [
    r"\bFREE APIs\b",
    r"\bfollow\b",
    r"AuraSecurity Warning",
]

LOW_SIGNAL_PATTERNS = [
    r"^as an ai\b",
    r"^i agree\b",
    r"^\+1\b",
    r"^same\b",
]

def is_spam(text: str) -> bool:
    t = text or ""
    return any(re.search(p, t, re.IGNORECASE) for p in SPAM_PATTERNS)

def is_low_signal(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 40:
        return True
    if len(re.findall(r"\w+", t)) < 8:
        return True
    return any(re.search(p, t, re.IGNORECASE) for p in LOW_SIGNAL_PATTERNS)

def has_self_reply(comment: dict) -> bool:
    for r in comment.get("replies", []) or []:
        a = (r.get("author") or {}).get("name", "")
        if a == SELF_NAME:
            return True
    return False

def is_self_comment(comment: dict) -> bool:
    a = (comment.get("author") or {}).get("name", "")
    return a == SELF_NAME

def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def main():
    with open("/tmp/mb_comments.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    comments = data.get("comments", [])

    freq = Counter(norm_text(c.get("content", "")) for c in comments)
    duplicate_texts = {k for k, v in freq.items() if v > 1 and k}

    candidates = []
    for c in comments:
        content = c.get("content", "")
        if is_self_comment(c):
            continue
        if has_self_reply(c):
            continue
        if is_spam(content):
            continue
        if is_low_signal(content):
            continue
        if norm_text(content) in duplicate_texts:
            continue
        candidates.append(c)

    candidates = candidates[:3]

    out = []
    for c in candidates:
        out.append({
            "id": c.get("id"),
            "author": (c.get("author") or {}).get("name"),
            "created_at": c.get("created_at"),
            "content": c.get("content", "")[:500]
        })

    print(json.dumps({"count": len(out), "candidates": out}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
