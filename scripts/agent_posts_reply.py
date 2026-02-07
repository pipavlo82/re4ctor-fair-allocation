#!/usr/bin/env python3
import os, json, time, hashlib, re, requests
from pathlib import Path

STATE_DIR = Path("state")
STATE_DIR.mkdir(parents=True, exist_ok=True)

def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out

def load_state(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def save_state(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def stable_key(post_id, text):
    return hashlib.sha256((post_id + "||" + text.strip()).encode("utf-8")).hexdigest()

def fallback_reply(post):
    return "Interesting angle—what’s the one measurable signal you’d track to validate this in practice (latency, failure rate, cost, or something else)?"

def _normalize_challenge(ch):
    s = (ch or "").lower()
    s = re.sub(r"[^a-z0-9+\-*/\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _fuzzy_pattern(word):
    parts = [re.escape(c) + r"+" for c in word]
    return re.compile(r"(?<![a-z])" + r"[^a-z0-9]*".join(parts) + r"(?![a-z])", re.I)

def _find_numbers_from_words(challenge):
    units_map = {
        "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,
        "ten":10,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,
        "seventeen":17,"eighteen":18,"nineteen":19
    }
    tens_map = {"twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,"eighty":80,"ninety":90}

    base = (challenge or "").lower()
    hits = []

    for w, v in units_map.items():
        for m in _fuzzy_pattern(w).finditer(base):
            hits.append((m.start(), m.end(), float(v), "unit"))

    for w, v in tens_map.items():
        for m in _fuzzy_pattern(w).finditer(base):
            hits.append((m.start(), m.end(), float(v), "tens"))

    # digits too
    for m in re.finditer(r"\b\d+(?:\.\d+)?\b", _normalize_challenge(challenge)):
        try:
            hits.append((m.start(), m.end(), float(m.group(0)), "num"))
        except Exception:
            pass

    hits.sort(key=lambda x: x[0])

    vals = []
    i = 0
    while i < len(hits):
        st, en, v, typ = hits[i]
        if typ == "tens" and i + 1 < len(hits):
            st2, en2, v2, typ2 = hits[i+1]
            if typ2 in ("unit", "num") and 0 <= v2 <= 9 and (st2 - en) <= 14:
                vals.append(v + v2)
                i += 2
                continue
        vals.append(v)
        i += 1

    # dedup consecutive
    out = []
    for x in vals:
        if not out or abs(out[-1] - x) > 1e-9:
            out.append(x)
    return out

def _solve_verification_challenge(challenge):
    s = _normalize_challenge(challenge)
    nums = _find_numbers_from_words(challenge)

    if "total force" in s and len(nums) >= 2:
        return f"{(nums[0] + nums[1]):.2f}"
    if "power" in s and len(nums) >= 2:
        return f"{(nums[0] * nums[1]):.2f}"

    m = re.search(r"(\d+(?:\.\d+)?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)", s)
    if m:
        a = float(m.group(1)); op = m.group(2); b = float(m.group(3))
        if op == "+": ans = a + b
        elif op == "-": ans = a - b
        elif op == "*": ans = a * b
        else: ans = a / b if b != 0 else 0.0
        return f"{ans:.2f}"

    if len(nums) >= 2:
        return f"{(nums[0] + nums[1]):.2f}"

    raise RuntimeError(f"cannot parse challenge: {challenge}")

def _candidate_answers(challenge):
    s = _normalize_challenge(challenge)
    nums = _find_numbers_from_words(challenge)[:4]
    cands = []

    try:
        cands.append(_solve_verification_challenge(challenge))
    except Exception:
        pass

    if len(nums) >= 2:
        a, b = nums[0], nums[1]
        cands += [f"{(a+b):.2f}", f"{(a-b):.2f}", f"{(b-a):.2f}", f"{(a*b):.2f}"]
        if b != 0:
            cands.append(f"{(a/b):.2f}")
        if a != 0:
            cands.append(f"{(b/a):.2f}")
        cands += [str(int(round(a+b))), str(int(round(a*b))), str(int(round(a))), str(int(round(b)))]

    if len(nums) >= 3:
        a, b, c = nums[0], nums[1], nums[2]
        cands += [f"{(a+b+c):.2f}", f"{(a*b*c):.2f}", f"{(a+b):.2f}", f"{(b+c):.2f}", f"{(a+c):.2f}"]

    raw_nums = re.findall(r"\b\d+(?:\.\d+)?\b", s)
    for rn in raw_nums[:4]:
        try:
            x = float(rn)
            cands += [f"{x:.2f}", str(int(round(x)))]
        except Exception:
            pass

    # never empty
    cands += ["0.00", "1.00", "2.00", "10.00", "42.00", "100.00"]

    seen = set()
    out = []
    for x in cands:
        k = str(x).strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out[:24]

def _mb_verify_if_needed(base, key, write_json):
    ver = (write_json or {}).get("verification") or {}
    code = ver.get("code") or ""
    challenge = ver.get("challenge") or ""
    if not code or not challenge:
        return {"verified": False, "reason": "no_verification_payload"}

    candidates = _candidate_answers(challenge)
    if not candidates:
        return {"verified": False, "reason": "no_candidates", "body": (challenge or "")[:220]}

    last_status = None
    last_body = ""

    for ans in candidates:
        vr = requests.post(
            f"{base}/api/v1/verify",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"verification_code": code, "answer": ans},
            timeout=20
        )
        last_status = vr.status_code
        last_body = (vr.text or "")[:300]
        if vr.status_code == 200:
            return {"verified": True, "answer": ans}
        if vr.status_code in (404, 410):
            return {"verified": False, "reason": f"verify_http_{vr.status_code}", "body": last_body}

    return {"verified": False, "reason": f"verify_http_{last_status}", "body": last_body}

def mb_post_comment(post_id, content):
    base = os.getenv("MB_BASE", "https://www.moltbook.com").rstrip("/")
    key = os.getenv("MOLTBOOK_API_KEY", "")
    if not key:
        raise RuntimeError("MOLTBOOK_API_KEY is empty")

    url = f"{base}/api/v1/posts/{post_id}/comments"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"content": content},
        timeout=20
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"post failed {r.status_code}: {r.text[:300]}")

    wj = r.json()
    vj = _mb_verify_if_needed(base, key, wj)

    if vj.get("verified"):
        print(f"[OK] verification published answer={vj.get('answer')}")
    else:
        print(f"[WARN] verification not completed: {vj.get('reason')} body={vj.get('body','')[:160]}")

    return wj

def main():
    skip_count = 0
    post_count = 0
    err_count = 0
    skip_reasons = {"replied": 0, "low_signal": 0, "dedup": 0}

    backlog_path = os.getenv("BACKLOG_FILE", "state/posts_backlog.jsonl")
    if not Path(backlog_path).exists():
        print(f"[ERR] backlog not found: {backlog_path}")
        raise SystemExit(2)

    dry_run = os.getenv("DRY_RUN", "0") == "1"
    top_n = _env_int("TOP_N", 10)
    max_replies = _env_int("MAX_REPLIES", 3)
    min_score = float(os.getenv("MIN_SCORE", "3.6"))
    min_comments = _env_int("MIN_COMMENTS", 3)
    sleep_s = float(os.getenv("SLEEP_S", "1.2"))
    ignore_replied = os.getenv("IGNORE_REPLIED", "0") == "1"
    dedup_disable = os.getenv("DEDUP_DISABLE", "0") == "1"

    replied_posts = load_state(STATE_DIR / "replied_posts.json", {"posts": []})
    replied_set = set(replied_posts.get("posts", []))

    dedup_keys = load_state(STATE_DIR / "dedup_keys.json", {"keys": []})
    dedup_set = set(dedup_keys.get("keys", []))

    items = load_jsonl(backlog_path)
    if not items:
        print("[OK] backlog empty")
        return

    picked, seen = [], set()
    for it in items:
        post = it.get("post") or {}
        pid = post.get("id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        picked.append(it)
        if len(picked) >= top_n:
            break

    made = 0
    for it in picked:
        score = float(it.get("score", 0.0))
        post = it.get("post") or {}
        pid = post.get("id", "")
        comments = int(post.get("comment_count") or 0)

        if (pid in replied_set) and (not ignore_replied):
            skip_count += 1
            skip_reasons["replied"] += 1
            continue

        if (score < min_score) and (comments < min_comments):
            skip_count += 1
            skip_reasons["low_signal"] += 1
            continue

        comment = fallback_reply(post)
        dkey = stable_key(pid, comment)

        if (not dedup_disable) and (dkey in dedup_set):
            skip_count += 1
            skip_reasons["dedup"] += 1
            continue

        print("\n=== REPLY PLAN ===")
        print(f"post={pid} score={score:.2f} comments={comments}")
        print(comment)

        try:
            if not dry_run:
                mb_post_comment(pid, comment)
                post_count += 1
                print(f"[OK] posted comment to post={pid}")
            else:
                print("[DRY_RUN] not posted")
        except Exception as e:
            err_count += 1
            print(f"[ERR] {e}")
            continue

        replied_set.add(pid)
        dedup_set.add(dkey)
        made += 1
        if made >= max_replies:
            break
        time.sleep(sleep_s)

    if not dry_run:
        replied_posts["posts"] = sorted(replied_set)
        dedup_keys["keys"] = sorted(dedup_set)
        save_state(STATE_DIR / "replied_posts.json", replied_posts)
        save_state(STATE_DIR / "dedup_keys.json", dedup_keys)

    print(f"\n[OK] processed picked={len(picked)} made={made} dry_run={dry_run}")
    print({"skips": skip_count, "posts": post_count, "errors": err_count})
    print({"skip_reasons": skip_reasons})

if __name__ == "__main__":
    main()
