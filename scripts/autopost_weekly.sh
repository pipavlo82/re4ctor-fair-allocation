#!/usr/bin/env bash
set -euo pipefail

: "${MOLTBOOK_API_KEY:?missing}"
: "${MOLTBOOK_SUBMOLT:=general}"
: "${MOLTBOOK_WEEKLY_TEMPLATE:=templates/weekly.md}"

STATE_DIR="${STATE_DIR:-state}"
mkdir -p "$STATE_DIR"

WEEK="$(date +%G)-W$(date +%V)"   # ISO week: 2026-W06
STATE_FILE="$STATE_DIR/last_week.txt"

if [[ -f "$STATE_FILE" ]]; then
  LAST="$(cat "$STATE_FILE" || true)"
  if [[ "$LAST" == "$WEEK" ]]; then
    echo "[autopost] already posted for $WEEK — skipping"
    exit 0
  fi
fi

if [[ ! -f "$MOLTBOOK_WEEKLY_TEMPLATE" ]]; then
  echo "[autopost] missing template: $MOLTBOOK_WEEKLY_TEMPLATE" >&2
  exit 1
fi

TITLE="Re4ctoRTrust weekly check-in ($WEEK)"
CONTENT="$(cat "$MOLTBOOK_WEEKLY_TEMPLATE")"

# add a tiny footer stamp so you can grep later
CONTENT="${CONTENT}\n\n—\nstamp: ${WEEK} | ts: $(date -Is)"

API="https://www.moltbook.com/api/v1/posts"

payload() {
  jq -nc --arg submolt "$MOLTBOOK_SUBMOLT" --arg title "$TITLE" --arg content "$CONTENT" \
    '{submolt:$submolt,title:$title,content:$content}'
}

# retry because sometimes Moltbook edge returns intermittent 404/other weirdness
for attempt in 1 2 3 4 5; do
  echo "[autopost] attempt=$attempt week=$WEEK submolt=$MOLTBOOK_SUBMOLT"

  http="$(curl -sS -o /tmp/moltbook_post.json -w "%{http_code}" \
    -H "Authorization: Bearer ${MOLTBOOK_API_KEY}" \
    -H "Content-Type: application/json" \
    --data-binary "$(payload)" \
    "$API" || true)"

  echo "[autopost] HTTP=$http bytes=$(wc -c < /tmp/moltbook_post.json 2>/dev/null || echo 0)"
  if [[ "$http" == "429" ]]; then
    # Respect server retry window from JSON: {"retry_after_minutes": N}
    mins="$(python3 - <<'PYY' 2>/dev/null || true
import json
try:
  d=json.load(open("/tmp/moltbook_post.json","r"))
  v=d.get("retry_after_minutes","")
  print(v if v is not None else "")
except Exception:
  pass
PYY
)" 
    if [[ -n "${mins:-}" ]]; then
      wait=$((mins*60 + 5))
    else
      wait=1800
    fi
    next_ts=$(( $(date +%s) + wait ))
    echo "$next_ts" > /tmp/moltbook_next_post_ts
    echo "[autopost] rate-limited (429). will retry after ${wait}s (next_ts=$next_ts). exiting."
    exit 0
  fi

  if [[ "$http" == "201" || "$http" == "200" ]]; then
    # save week marker only if success
    echo "$WEEK" > "$STATE_FILE"
    echo "[autopost] OK: $(cat /tmp/moltbook_post.json | head -c 200)"
    exit 0
  fi

  echo "[autopost] non-success body (first 200):"
  head -c 200 /tmp/moltbook_post.json || true
  echo

  sleep $((attempt * 10))
done

echo "[autopost] FAILED after 3 attempts" >&2
exit 2
