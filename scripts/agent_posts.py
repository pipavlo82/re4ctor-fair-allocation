#!/usr/bin/env python3
import os, json, time, hashlib, re
from pathlib import Path
from datetime import datetime, timezone

WATCHLIST_PATH = Path("state/watchlist.json")
BACKLOG_PATH = Path("state/posts_backlog.jsonl")
SEEN_POSTS_PATH = Path("state/seen_posts.json")

DEFAULT_INPUT = "/tmp/mb_posts_new.jsonl"

def _load_json(p: Path, default):
    try:
        return json.load(open(p, "r", encoding="utf-8"))
    except FileNotFoundError:
        return default

def _save_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)

def _norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _score_post(post: dict, watch: dict):
    title = _norm_text(post.get("title",""))
    content = _norm_text(post.get("content",""))
    submolt = _norm_text((post.get("submolt") or {}).get("name",""))
    author = _norm_text((post.get("author") or {}).get("name",""))
    txt = f"{title} {content} submolt:{submolt} author:{author}"

    # ignore topics: if matches, hard ignore
    for it in watch.get("ignore_topics", []):
        for kw in it.get("keywords", []):
            if kw.lower() in txt:
                return {"score": -1e9, "reasons":[f"IGNORE:{it.get('name')}:{kw}"]}

    score = 0.0
    reasons = []

    # submolt boost if in subscribe list
    subs = set([_norm_text(x) for x in (watch.get("subscribe_submolts") or [])])
    if submolt and submolt in subs:
        score += 0.5
        reasons.append(f"submolt:+0.5({submolt})")

    # keyword scoring per topic
    for t in watch.get("topics", []):
        tname = t.get("name","topic")
        hits = 0
        for kw in t.get("keywords", []):
            kwl = kw.lower()
            if kwl in txt:
                hits += 1
        if hits:
            # diminishing returns: 1->1.5, 2->2.6, 3->3.4, 4->4.0 ...
            add = 1.2 + 1.0 * (1 - (0.65 ** hits))
            score += add
            reasons.append(f"{tname}:+{add:.2f}(hits={hits})")

    # comment_count boost (engagement)
    cc = int(post.get("comment_count") or 0)
    if cc > 0:
        add = min(2.5, 0.35 * cc)
        score += add
        reasons.append(f"comments:+{add:.2f}({cc})")

    return {"score": score, "reasons": reasons}

def _stable_key(post: dict) -> str:
    # stable id if present, else hash title+author+created_at
    pid = post.get("id")
    if pid:
        return f"id:{pid}"
    base = f"{post.get('title','')}|{(post.get('author') or {}).get('name','')}|{post.get('created_at','')}"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return f"h:{h}"

def main():
    input_path = os.getenv("POSTS_FILE", DEFAULT_INPUT)
    topn = int(os.getenv("TOP_N", "12"))
    dry_run = os.getenv("DRY_RUN", "1") == "1"

    if not WATCHLIST_PATH.exists():
        raise SystemExit("watchlist missing: state/watchlist.json")
    watch = _load_json(WATCHLIST_PATH, {})

    # load seen
    seen = _load_json(SEEN_POSTS_PATH, {"seen": []})
    seen_set = set(seen.get("seen", []) or [])

    posts = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                posts.append(json.loads(line))
            except Exception:
                continue

    scored = []
    best_by_pid = {}  # pid -> (score, key, post, reasons)
    for p in posts:
        pid = p.get('id') or ''
        key = _stable_key(p)
        # global seen (cross-run)
        if key in seen_set:
            continue
        res = _score_post(p, watch)
        if res["score"] < -1e8:
            continue
        # per-run dedup: keep max score per post_id
        if pid:
            cur = best_by_pid.get(pid)
            tup = (res["score"], key, p, res["reasons"])
            if (cur is None) or (tup[0] > cur[0]):
                best_by_pid[pid] = tup
        else:
            scored.append((res["score"], key, p, res["reasons"]))

    # materialize per-run dedup bucket
    if best_by_pid:
        scored.extend(best_by_pid.values())
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = scored[:topn]

    # write backlog jsonl
    BACKLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(BACKLOG_PATH, "a", encoding="utf-8") as out:
        for score, key, p, reasons in picked:
            rec = {
                "ts": ts,
                "key": key,
                "score": score,
                "reasons": reasons,
                "post": {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "submolt": (p.get("submolt") or {}).get("name"),
                    "author": (p.get("author") or {}).get("name"),
                    "comment_count": p.get("comment_count"),
                    "created_at": p.get("created_at"),
                    "content": p.get("content","")[:1200]
                }
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # print top
    print(f"[OK] loaded_posts={len(posts)} new_scored={len(scored)} picked={len(picked)} backlog={BACKLOG_PATH}")
    for i,(score,key,p,reasons) in enumerate(picked, start=1):
        print(f"\n#{i} score={score:.2f} comments={p.get('comment_count',0)} submolt={(p.get('submolt') or {}).get('name')} author={(p.get('author') or {}).get('name')}")
        print(f"    id={p.get('id')}")
        print(f"    title={p.get('title')}")
        if os.getenv("DEBUG","0") == "1":
            print("    reasons:", "; ".join(reasons) if reasons else "-")

    # mark seen (so we don't spam backlog repeatedly)
    for _, key, _, _ in picked:
        seen_set.add(key)
    seen["seen"] = sorted(seen_set)
    _save_json(SEEN_POSTS_PATH, seen)

    if dry_run:
        print("\n[DRY_RUN] backlog written; no replies posted.")
    else:
        print("\n[WARN] posting is not implemented in this script yet. Use agent_brain style posting per-post.")

if __name__ == "__main__":
    main()
