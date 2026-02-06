#!/usr/bin/env bash
set -euo pipefail

# Load env
set -a
[ -f ./.env ] && source ./.env
set +a

: "${POST_ID:?POST_ID missing}"
: "${MOLTBOOK_API_KEY:?MOLTBOOK_API_KEY missing}"
MB_BASE="${MB_BASE:-https://www.moltbook.com}"
TMP=/tmp/mb_comments.json

mkdir -p state

curl -sS "${MB_BASE%/}/api/v1/posts/$POST_ID/comments?sort=new" \
  -H "Authorization: Bearer $MOLTBOOK_API_KEY" \
  -o "$TMP"

python3 - <<'PY'
import json, os
TMP="/tmp/mb_comments.json"
live = json.load(open(TMP,"r",encoding="utf-8")).get("comments",[]) or []

seen_path="state/seen_comments.json"
seen={"replied":[]}
try:
    seen=json.load(open(seen_path,"r",encoding="utf-8"))
except FileNotFoundError:
    pass

replied=set(seen.get("replied",[]) or [])
live_ids=[c.get("id") for c in live if c.get("id")]
new=[cid for cid in live_ids if cid not in replied]

print(f"[MB] live_count={len(live_ids)} replied_count={len(replied)} new_unreplied={len(new)}")
if new:
    print("[MB] new_ids_first10:", new[:10])
# exit code: 0 if no new, 2 if new exist (so bash can decide)
raise SystemExit(2 if new else 0)
PY

echo "[MB] no new comments -> skip agent_brain"
exit 0

# If we got here, python exited with code 2 (new comments exist)
python scripts/agent_brain.py
