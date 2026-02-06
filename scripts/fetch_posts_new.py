#!/usr/bin/env python3
import os, json, time
import requests

def main():
    base = os.getenv("MB_BASE", "https://www.moltbook.com").rstrip("/")
    key  = os.getenv("MOLTBOOK_API_KEY", "")
    if not key:
        raise SystemExit("MOLTBOOK_API_KEY missing")

    sort = os.getenv("MB_POSTS_SORT", "new")
    pages = int(os.getenv("MB_POSTS_PAGES", "4"))
    page_size = int(os.getenv("MB_POSTS_PAGE_SIZE", "25"))
    out = os.getenv("MB_POSTS_OUT", "/tmp/mb_posts_new.jsonl")

    headers = {"Authorization": f"Bearer {key}"}

    with open(out, "w", encoding="utf-8") as f:
        total = 0
        for i in range(pages):
            off = i * page_size
            url = f"{base}/api/v1/posts?sort={sort}&offset={off}"
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            j = r.json()
            for p in (j.get("posts") or []):
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
                total += 1
            time.sleep(0.2)

    print(f"[OK] wrote {total} posts to {out}")

if __name__ == "__main__":
    main()
