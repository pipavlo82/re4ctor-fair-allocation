#!/usr/bin/env python3
import os, json, time, hashlib, re
import requests
from dotenv import load_dotenv
from scripts.rag_repo_search import rag_context_for_text

load_dotenv()

MB_BASE = os.getenv("MB_BASE", "https://www.moltbook.com").rstrip("/")
API_KEY = os.getenv("MOLTBOOK_API_KEY", "")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
OLLAMA = os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434").rstrip("/")
POST_ID = os.getenv("POST_ID", "55e4bf7a-9f54-4a03-acc1-6951fc8ada78")

# safety knobs
SELF_NAME = os.getenv("AGENT_NAME", "Re4ctoRTrust")
MAX_REPLIES = int(os.getenv("MAX_REPLIES", "2"))     # hard cap per run
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"           # no posting when 1
SLEEP_SEC = float(os.getenv("SLEEP_SEC", "2.0"))

STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "state")
SEEN_PATH = os.path.join(STATE_DIR, "seen_comments.json")
DEDUP_PATH = os.path.join(STATE_DIR, "dedup_keys.json")
os.makedirs(STATE_DIR, exist_ok=True)

TOPIC_RE = re.compile(
    r"(fair|fairness|allocation|receipt|signed|verify|verifiab|audit|drift|telemetry|attestation|vrf|policy|replay|latency|kpi|metrics)",
    re.IGNORECASE,
)

def headers():
    if not API_KEY:
        raise SystemExit("MOLTBOOK_API_KEY is empty (did you source .env?)")
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

def get_comments(post_id: str, sort="new"):
    url = f"{MB_BASE}/api/v1/posts/{post_id}/comments?sort={sort}"
    r = requests.get(url, headers=headers(), timeout=30)
    r.raise_for_status()
    j = r.json()
    return j.get("comments", [])

def post_comment(post_id: str, content: str, parent_id: str | None = None):
    url = f"{MB_BASE}/api/v1/posts/{post_id}/comments"
    payload = {"content": content}
    if parent_id:
        payload["parent_id"] = parent_id
    r = requests.post(url, headers=headers(), data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json()

def ollama_generate(prompt: str) -> str:
    url = f"{OLLAMA}/api/generate"
    payload = {"model": MODEL, "prompt": prompt, "stream": False}
    r = requests.post(url, headers={"Content-Type":"application/json"}, data=json.dumps(payload), timeout=120)
    r.raise_for_status()
    j = r.json()
    return (j.get("response") or "").strip()

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def dedup_key(author: str, text: str) -> str:
    # stable fingerprint to avoid replying twice to same content
    h = hashlib.sha256((author.strip() + "\n" + text.strip()).encode("utf-8")).hexdigest()
    return h[:16]

SYSTEM = """You are Re4ctoRTrust, a technical but friendly agent.
Goal: be useful, stay on-topic, avoid spam and avoid flamewars.
Rules:
- If off-topic / spam / low-signal: {"action":"ignore"}.
- If hostile: reply calmly, no insults, one factual point + one redirect question.
- Keep replies <= 600 chars.
Return STRICT JSON only with keys:
- action: "reply"|"ignore"
- content: string (only if action=reply)
"""

def build_prompt(comment_author: str, comment_text: str):
    return f"""{SYSTEM}

Thread topic: verifiable fair allocation + signed receipts (VRF-backed).
Comment author: {comment_author}
Comment:
{comment_text}

Return STRICT JSON now.
"""

def is_low_signal(text: str) -> bool:
    t = text.strip()
    if len(t) < 12:
        return True
    if t.lower() in {"as an ai, i agree. 🤖", "as an ai, i agree.", "agree", "lol", "ok"}:
        return True
    if "[hb test]" in t.lower():
        return True
    return False

def is_spam(text: str) -> bool:
    t = text
    if "FREE APIs" in t or "Follow " in t or "Revealing soon" in t:
        return True
    if "curl agentmarket.cloud" in t:
        return True
    return False

def main():
    seen = load_json(SEEN_PATH, {"replied": []})
    replied = set(seen.get("replied", []))

    dedup = load_json(DEDUP_PATH, {"keys": []})
    seen_keys = set(dedup.get("keys", []))

    comments = get_comments(POST_ID, sort="new")
    if not comments:
        print("[OK] no comments")
        return

    # process oldest-first among unseen
    unseen = [c for c in reversed(comments) if c.get("id") and c["id"] not in replied]

    replies_sent = 0

    for c in unseen:
        cid = c["id"]
        author = (c.get("author") or {}).get("name") or "unknown"
        text = (c.get("content") or "").strip()

        # hard skip: never reply to self
        if author.strip() == SELF_NAME:
            print(f"[OK] ignore self {cid}")
            replied.add(cid)
            continue

        if not text:
            replied.add(cid)
            continue

        if is_spam(text):
            print(f"[SKIP] spam {cid} ({author})")
            replied.add(cid)
            continue

        if is_low_signal(text):
            print(f"[OK] ignore low-signal {cid} ({author})")
            replied.add(cid)
            continue

        # topic filter: ignore if no topic keywords
        if not TOPIC_RE.search(text):
            print(f"[OK] ignore off-topic {cid} ({author})")
            replied.add(cid)
            continue

        # dedup across author+text
        k = dedup_key(author, text)
        if k in seen_keys:
            print(f"[OK] ignore dup {cid} ({author})")
            replied.add(cid)
            continue

        # cap per run
        if replies_sent >= MAX_REPLIES:
            print(f"[OK] cap reached ({MAX_REPLIES}), stopping")
            break

        prompt = build_prompt(author, text)

    # --- Local repo context (read-only RAG) ---
    try:
        _rag = rag_context_for_text(prompt)
        if _rag:
            prompt += "\n\n# Repo context (read-only)\n" + _rag
    except Exception:
        pass
        raw = ollama_generate(prompt)

        try:
            decision = json.loads(raw)
        except Exception:
            print(f"[WARN] model non-JSON for {cid}: {raw[:120]!r}")
            continue

        if decision.get("action") != "reply":
            print(f"[OK] ignore {cid} ({author})")
            replied.add(cid)
            continue

        content = (decision.get("content") or "").strip()
        if not content or len(content) < 10:
            print(f"[WARN] empty/short reply for {cid}")
            continue

        # clamp length
        if len(content) > 600:
            content = content[:580].rstrip() + "…"

        if DRY_RUN:
            print(f"[DRY] would reply to {cid} ({author}): {content!r}")
        else:
            post_comment(POST_ID, content, parent_id=cid)
            print(f"[OK] replied to {cid} ({author})")

        replied.add(cid)
        seen_keys.add(k)
        replies_sent += 1
        time.sleep(SLEEP_SEC)

    seen["replied"] = sorted(list(replied))
    save_json(SEEN_PATH, seen)

    dedup["keys"] = sorted(list(seen_keys))
    save_json(DEDUP_PATH, dedup)

if __name__ == "__main__":
    main()
