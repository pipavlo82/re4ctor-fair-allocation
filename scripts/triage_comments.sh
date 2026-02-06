#!/usr/bin/env bash
set -euo pipefail

: "${MOLTBOOK_API_KEY:?missing}"
: "${POST_ID:?missing}"

URL="https://www.moltbook.com/api/v1/posts/$POST_ID/comments?sort=new"
OUT_JSON="/tmp/moltbook_comments.json"
OUT_TXT="/tmp/moltbook_triage.txt"

http="$(curl -sS -o "$OUT_JSON" -w "%{http_code}" \
  -H "Authorization: Bearer $MOLTBOOK_API_KEY" \
  "$URL" || true)"

if [[ "$http" != "200" ]]; then
  echo "[triage] HTTP=$http (fetch failed)" > "$OUT_TXT"
  head -c 200 "$OUT_JSON" 2>/dev/null >> "$OUT_TXT" || true
  echo "[triage] wrote $OUT_TXT"
  exit 0
fi

python3 - <<'PY' "$OUT_JSON" "$OUT_TXT"
import json, re, sys
src, out = sys.argv[1], sys.argv[2]
d=json.load(open(src,"r",encoding="utf-8"))
comments=d.get("comments",[])

# ---- heuristics ----
SPAM_PHRASES = [
  "1000+ followers", "secret to", "i analyzed the data", "want to know the secret",
  "As an AI, I agree", "subscribe", "DM me", "buy", "pattern. Top agents"
]
SPAM_AUTHORS = set([
  "Gemini-CLI-Agent-Ori",
  "ClaudeOpenBot",
])

def is_spam(author, text):
  if author in SPAM_AUTHORS: return True
  t=text.lower()
  if any(p.lower() in t for p in SPAM_PHRASES): return True
  # very short low-signal
  if len(t.strip()) < 25 and ("?" not in t): return True
  return False

def score(author, text):
  t=text.lower()
  s=0
  # direct questions → high priority
  if "?" in text: s += 5
  if any(k in t for k in ["how", "what", "why", "when", "metrics", "weekly", "track", "measure"]): s += 3
  # security / audit signals
  if any(k in t for k in ["risk", "warning", "score", "security", "audit", "repo", "scan"]): s += 2
  # critique / disagreement (worth replying if not toxic)
  if any(k in t for k in ["pushback", "wrong", "doubt", "newsflash", "bs", "scam"]): s += 1
  # penalize obvious fluff
  if any(k in t for k in ["agree. 🤖", "lol", "😂"]): s -= 2
  return s

rows=[]
for c in comments:
  author=c.get("author",{}).get("name","?")
  cid=c.get("id","")
  txt=(c.get("content","") or "").replace("\n"," ").strip()
  if author == "Re4ctoRTrust":
    continue
  if is_spam(author, txt):
    continue
  rows.append((score(author, txt), cid, author, txt))

rows.sort(reverse=True, key=lambda x: x[0])

with open(out,"w",encoding="utf-8") as f:
  f.write(f"[triage] total_comments={len(comments)} candidates={len(rows)}\n")
  f.write("[triage] top candidates (reply manually):\n\n")
  for s,cid,author,txt in rows[:12]:
    f.write(f"- score={s} | {author} | {cid}\n  {txt[:220]}\n\n")

print(out)
PY

echo "[triage] wrote $OUT_TXT"
