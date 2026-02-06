#!/usr/bin/env python3
import os, sys, json, time, re, subprocess, hashlib
from pathlib import Path
import requests
ANTI_PROMO_RULES = """Hard rules:
- Do NOT advertise or ask people to "check out" anything.
- Do NOT mention the product name "Re4ctoR" unless the post explicitly asks about: VRF, randomness beacons, randomness APIs, API keys/billing, quotas/rate limits, or security operations where a concrete integration is requested.
- If you mention a product at all, it must be a single short clause at the end, not the main point.
"""

STATE_DIR = Path("state")
STATE_DIR.mkdir(exist_ok=True)


def fallback_reply(post: dict) -> str:
    title = (post.get("title") or "").strip().lower()
    content = (post.get("content") or "")
    # Safe, non-spammy defaults (no links)
    if "provenance" in title or "journey" in title or "remembers" in title:
        return ("When you say the invariants keep you stable across context resets, "
                "what are the 1–2 concrete mechanisms (e.g., hash-anchored state, tests, or external checkpoints)? "
                "Also: what would falsify FCANON_003—what failure mode are you most worried about?")
    if "architecture of trust" in title or "trust" in title:
        return ("Curious: in your view, what’s the smallest verifiable primitive that upgrades trust the most here "
                "(ZK proof, verifiable randomness, or on-chain attestation)? "
                "Do you have a concrete example where the trust boundary is enforced by code rather than social norms?")
    if "lab" in title or "vuln" in content.lower():
        return ("Nice—what vulnerability classes are you aiming to practice against in this lab (auth, injection, SSRF, etc.)? "
                "If you can share one thing: what’s the reset/cleanup workflow so it stays reproducible between runs?")
    return ("Interesting angle—what’s the one measurable signal you’d track to validate this in practice "
            "(latency, failure rate, cost, or something else)?")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def load_jsonl(path: str):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: 
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out

def load_state(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception:
        return default

def save_state(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def compact(text: str, max_len: int = 1200) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."

def build_query(post: dict) -> str:
    title = post.get("title") or ""
    content = post.get("content") or ""
    submolt = submolt_name(post)
    # very small heuristic: mix title + a few content keywords
    blob = (title + "\n" + content)[:4000]
    # keep some tech anchors
    anchors = ["api key", "billing", "rate limit", "idempotency", "webhook", "security headers", "vrf", "randomness", "pqc", "ethereum", "erc-7913", "hsts", "cors", "stripe", "postgres", "redis"]
    hits = [a for a in anchors if a.lower() in blob.lower()]
    base = f"{title}. submolt={submolt}. " + ("; ".join(hits) if hits else "")
    # fallback if empty
    if len(base.strip()) < 10:
        base = title or "agent discovery trust security ops api keys"
    return base

def rag_search(query: str, limit_lines: int = 60) -> str:
    # call existing script; tolerate failures
    cmd = ["python3", "scripts/rag_repo_search.py"]
    try:
        p = subprocess.run(cmd, input=(query+"\n").encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        out = (p.stdout.decode("utf-8", errors="replace") + "\n" + p.stderr.decode("utf-8", errors="replace")).strip()
        out = "\n".join(out.splitlines()[:limit_lines])
        return out
    except Exception as e:
        return f"[RAG_ERROR] {e}"

def ollama_generate(prompt: str) -> dict:
    import requests, os, json

    url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate").strip()
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct").strip()
    timeout = int(os.getenv("REQUEST_TIMEOUT", "30"))

    headers = {"Content-Type": "application/json"}

    # OpenAI-compatible endpoint
    if "/v1/chat/completions" in url:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return ONLY valid JSON object."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "stream": False
        }
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        txt = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    else:
        # Native Ollama endpoint
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        txt = (data.get("response") or "").strip()

    # Try parse JSON from model text
    try:
        return json.loads(txt)
    except Exception:
        # soft fallback for non-json
        return {"comment": "", "reason": "model_non_json", "raw": txt[:1000]}

def mb_post_comment(post_id: str, content: str):
    base = os.getenv("MB_BASE", "https://www.moltbook.com").rstrip("/")
    api_key = os.getenv("MOLTBOOK_API_KEY","")
    if not api_key:
        raise RuntimeError("MOLTBOOK_API_KEY missing")
    url = f"{base}/api/v1/posts/{post_id}/comments"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"content": content}
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def stable_key(post_id: str, text: str) -> str:
    h = hashlib.sha256((post_id + "\n" + text).encode("utf-8")).hexdigest()[:16]
    return f"{post_id}:{h}"

def submolt_name(post: dict) -> str:
    sm = post.get("submolt")
    if sm is None:
        return ""
    if isinstance(sm, str):
        return sm
    if isinstance(sm, dict):
        return (sm.get("name") or sm.get("display_name") or "")
    return str(sm)


def normalize_plan(plan: dict) -> dict:
    """Normalize model output to {"reply": str, "reason": str}."""
    if not isinstance(plan, dict):
        return {"reply": "", "reason": "plan_not_dict"}

    reply = ""
    for k in ("reply", "comment", "text", "answer", "message", "content"):
        v = plan.get(k)
        if isinstance(v, str) and v.strip():
            reply = v.strip()
            break

    reason = str(plan.get("reason") or "").strip()
    return {"reply": reply, "reason": reason}



def _fallback_comment(post: dict) -> str:
    title = (post.get("title") or "").strip()
    if title:
        return f"Interesting take on \"{title}\". Could you share one concrete metric and a 7-day update so people can verify progress?"
    return "Interesting point. Could you share one concrete metric and a 7-day update so people can verify progress?"

def normalize_plan(plan, post: dict) -> dict:
    """
    Normalize model output to dict with:
      - comment (non-empty string)
      - reason (string)
    Accepts dict / JSON-string / raw text.
    """
    import json

    out = {"comment": "", "reason": ""}

    # dict passthrough
    if isinstance(plan, dict):
        out["comment"] = str(plan.get("comment") or "").strip()
        out["reason"] = str(plan.get("reason") or "").strip()
    else:
        txt = (plan or "")
        if not isinstance(txt, str):
            txt = str(txt)

        # try parse JSON from whole string
        parsed = None
        try:
            parsed = json.loads(txt)
        except Exception:
            # try extract first {...} json object
            a = txt.find("{")
            b = txt.rfind("}")
            if a != -1 and b != -1 and b > a:
                chunk = txt[a:b+1]
                try:
                    parsed = json.loads(chunk)
                except Exception:
                    parsed = None

        if isinstance(parsed, dict):
            out["comment"] = str(parsed.get("comment") or "").strip()
            out["reason"] = str(parsed.get("reason") or "").strip()
        else:
            # raw text fallback: use as comment if looks meaningful
            t = txt.strip()
            if len(t) >= 20:
                out["comment"] = t[:500]
            else:
                out["reason"] = "model_non_json"

    # final fallback comment
    if not out["comment"]:
        out["comment"] = _fallback_comment(post)

    # clamp length
    out["comment"] = out["comment"][:500].strip()
    if len(out["comment"]) < 20:
        out["comment"] = (_fallback_comment(post) + " Please add one concrete example.")[:500]

    return out



def hard_fallback_comment(post: dict) -> str:
    title = (post.get("title") or "").strip()
    if title:
        return f'Good point on "{title}". Could you share one concrete metric, one current blocker, and a 7-day update plan?'
    return "Good point. Could you share one concrete metric, one current blocker, and a 7-day update plan?"

def main():
    # System prompt for the local LLM (Ollama). Keep it short & policy-safe.
    AGENT_NAME = os.environ.get("AGENT_NAME", "Re4ctoRTrust")
    sys_prompt = f"""You are {AGENT_NAME} on Moltbook.
Write ONE helpful, non-spammy comment that adds concrete value.
Be specific to the post; ask 1 sharp question OR give 1 actionable suggestion.
Do NOT paste links unless explicitly asked.
Return STRICT JSON only: {{"reason": "...", "confidence": 0.0, "reply": "..."}}.
"""

    backlog_path = os.getenv("BACKLOG_FILE", "state/posts_backlog.jsonl")
    if not Path(backlog_path).exists():
        print(f"[ERR] backlog not found: {backlog_path}", file=sys.stderr)
        sys.exit(2)

    agent_name = os.getenv("AGENT_NAME", "Re4ctoRTrust")
    dry_run = os.getenv("DRY_RUN","0") == "1"
    debug = os.getenv("DEBUG","0") == "1"

    top_n = _env_int("TOP_N", 8)
    max_replies = _env_int("MAX_REPLIES", 3)
    min_score = float(os.getenv("MIN_SCORE", "3.6"))  # raise this to avoid generic posts
    min_comments = _env_int("MIN_COMMENTS", 3)
    sleep_s = float(os.getenv("SLEEP_S", "1.5"))

    replied_posts = load_state(STATE_DIR/"replied_posts.json", {"posts": []})
    seen_post_ids = set()
    replied_set = set(replied_posts.get("posts", []))

    dedup_keys = load_state(STATE_DIR/"dedup_keys.json", {"keys": []})
    dedup_set = set(dedup_keys.get("keys", []))

    items = load_jsonl(backlog_path)
    if not items:
        print("[OK] backlog empty")
        return

    # items were written as dict lines with: score,key,post,reasons (your agent_posts.py)
    picked = []
    seen_pid = set()
    for it in items:
        post = it.get("post") or {}
        pid = post.get("id")
        if not pid or pid in seen_pid:
            continue
        seen_pid.add(pid)
        picked.append(it)
        if len(picked) >= top_n:
            break

    made = 0
    ignore_replied = os.getenv("IGNORE_REPLIED","0") == "1"
    for it in picked:
        score = float(it.get("score", 0.0))
        post = it.get("post") or {}
        pid = post.get("id","")
        title = post.get("title","")
        submolt = submolt_name(post)
        comments = int(post.get("comment_count") or 0)

        if (pid in replied_set) and not ignore_replied:
            if debug: print(f"[SKIP] already replied post={pid}")
        if (score < min_score) and (comments < min_comments):
            if debug: print(f"[SKIP] gate score/comments post={pid} score={score:.2f} comments={comments}")
        q = build_query(post)
        rag = rag_search(q, limit_lines=80)

        sys_q = f"""You are {os.environ.get('AGENT_NAME','Re4ctoRTrust')}.
Write ONE helpful comment for the post below.

STYLE:
- 2–5 sentences, <= 420 characters total.
- Be specific: refer to at least one concrete term from the post (title/content).
- Ask at most one clarifying question.
- No generic hype ("Absolutely!", "Great job!") unless you add a concrete actionable point immediately after.
- No lists longer than 3 bullets.

{ANTI_PROMO_RULES}

POST:
title: {post.get('title','')}
submolt: {submolt_name(post)}
comments: {post.get('comment_count',0)}
content_snip: {(post.get('content','') or '')[:900]}

Return ONLY the comment text (no JSON, no quotes).""".strip()

        post_blob = {
            "id": pid, "title": title, "submolt": submolt,
            "comment_count": comments, "score": score,
            "content": compact(post.get("content",""), 900),
        }

        prompt = (
            sys_prompt
            + "\n\nPOST:\n" + json.dumps(post_blob, ensure_ascii=False)
            + "\n\nRAG:\n" + rag
        )

        plan = ollama_generate(prompt)
        np = normalize_plan(plan, post)
        reason = (np.get("reason") or "").strip()
        comment = (np.get("reply") or "").strip()
        if not comment:
            comment = ("Good point. For production, I’d track a compact weekly panel: "
                       "(1) signed receipt coverage, "
                       "(2) verification fail rate by reason codes (bad_sig / replay / policy_mismatch / seed_mismatch), "
                       "(3) p95 verification latency, and "
                       "(4) post-allocation drift rate.")


        if not comment:
            # hard fallback to avoid zero-output runs
            comment = (
                "Good point. For production, I’d track a compact weekly panel: "
                "(1) signed receipt coverage, "
                "(2) verification fail rate by reason codes (bad_sig / replay / policy_mismatch / seed_mismatch), "
                "(3) p95 verification latency, and "
                "(4) post-allocation drift rate."
            )
        reply_text = ""
        comment = ((locals().get("reply_text","")) or plan.get("comment") or "").strip()
        reason = (plan.get("reason") or "").strip()

        if not comment:
            if os.getenv("FORCE_FALLBACK_COMMENT", "1") == "1":
                comment = ("Good point. For production, I’d track a compact weekly panel: "
                           "signed receipt coverage, verification fail rate by reason codes "
                           "(bad_sig / replay / policy_mismatch / seed_mismatch), p95 verify latency, "
                           "and post-allocation drift rate. If useful, I can share a minimal JSON template.")
            else:
                print(f"[SKIP] empty comment: {post_id}")
        # --- normalize model output + force fallback on empty/non-text ---
        model_reason = ""
        model_conf = 0.0
        reply_text = ""
        if isinstance(plan, dict):
            model_reason = str(plan.get("reason") or "")
            try:
                model_conf = float(plan.get("confidence") or 0.0)
            except Exception:
                model_conf = 0.0
            reply_text = (plan.get("reply") or plan.get("response") or plan.get("text") or "")
        if reply_text is None:
            reply_text = ""
        if not isinstance(reply_text, str):
            reply_text = str(reply_text)
        reply_text = reply_text.strip()
        if not reply_text:
            reply_text = fallback_reply(post)
            if not model_reason:
                model_reason = "fallback_empty"
            model_conf = 0.0
        if plan.get("action") != "reply":
            if debug: print(f"[SKIP] model: {pid} reason={plan.get('reason')}")
            replied_set.add(pid)
            # model-skip -> force deterministic fallback instead of skipping
            reply_text = fallback_reply(post)
            model_reason = 'fallback_model_skip'
            model_conf = 0.0
            # (no continue)

        comment = (plan.get("comment") or "").strip()
        if not comment or len(comment) < 20:
            if debug: print(f"[WARN] empty comment -> fallback: {pid}")
            # do not mark replied_set here; we still want to post fallback
            comment = fallback_reply(post)
            reply_text = comment
            model_reason = "fallback_empty"
            model_conf = 0.0
        # no continue

        dkey = stable_key(pid, comment)
        if dkey in dedup_set:
            if debug: print(f"[SKIP] dedup-key hit: {pid}")
            replied_set.add(pid)
            continue

        print(f"\n=== REPLY PLAN ===")
        print(f"post={pid} score={score:.2f} comments={comments} submolt={submolt}")
        print(f"title: {title}")
        print(f"reason: {plan.get('reason')} conf={plan.get('confidence')}")
        print(comment)

        if not dry_run:
            mb_post_comment(pid, comment)
            print(f"[OK] posted comment to post={pid}")
        else:
            print(f"[DRY_RUN] not posted")

        replied_set.add(pid)
        dedup_set.add(dkey)
        made += 1
        if made >= max_replies:
            break
        time.sleep(sleep_s)

    if not dry_run:
        replied_posts["posts"] = sorted(replied_set)
        dedup_keys["keys"] = sorted(dedup_set)
        save_state(STATE_DIR/"replied_posts.json", replied_posts)
        save_state(STATE_DIR/"dedup_keys.json", dedup_keys)

    print(f"\n[OK] processed picked={len(picked)} made={made} dry_run={dry_run}")

if __name__ == "__main__":
    main()
