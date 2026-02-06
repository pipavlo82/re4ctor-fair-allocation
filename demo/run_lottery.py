import json, os, requests
from pathlib import Path
from datetime import datetime, timezone
from hashlib import sha256
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
TASK_MAIN = ROOT / "demo" / "task.json"
TASK_LOCAL = ROOT / "demo" / "task.local.json"
OUT_PATH = ROOT / "demo" / "sample_receipt.json"

load_dotenv(dotenv_path=ROOT / ".env")

def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

main = load_json(TASK_MAIN)
local = load_json(TASK_LOCAL)

# merge: local overrides main
task = {**main, **local}

task_id = task.get("task_id", "task_001")
task_commit = task.get("task_commit_sha256")
cands = task.get("candidates")

if not task_commit:
    raise RuntimeError("task_commit_sha256 missing (run demo/make_task_commit.py first)")
if not isinstance(cands, list) or not cands or not all(isinstance(x, str) for x in cands):
    raise RuntimeError("candidates missing/invalid in demo/task.local.json or demo/task.json")

cands = sorted(cands)

base = os.getenv("R4_BASE_URL", "https://re4ctor.com").rstrip("/")
api_key = (
    os.getenv("R4_API_KEY")
    or os.getenv("RE4CTOR_API_KEY")
    or os.getenv("PLANKEY")
    or os.getenv("X_API_KEY")
    or ""
).strip()

if not api_key:
    raise RuntimeError("Missing API key env (R4_API_KEY | RE4CTOR_API_KEY | PLANKEY | X_API_KEY)")

url = f"{base}/api/v1/vrf?sig=ecdsa"
r = requests.get(url, headers={"X-API-Key": api_key}, timeout=20)
if r.status_code != 200:
    raise RuntimeError(f"VRF HTTP {r.status_code}: {r.text[:300]}")

vrf = r.json()
seed = f"{task_commit}|{vrf['random']}"
idx = int.from_bytes(sha256(seed.encode()).digest()[:8], "big") % len(cands)
winner = cands[idx]

receipt = {
    "task_id": task_id,
    "task_commit_sha256": task_commit,
    "candidate_order": "lexicographic",
    "candidates": cands,
    "winner": winner,
    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "note": "Re4ctoR VRF-backed allocation (commit + vrf_random).",
    "re4ctor_random": vrf.get("random"),
    "re4ctor_timestamp": vrf.get("timestamp"),
    "re4ctor_msg_hash": vrf.get("msg_hash"),
    "re4ctor_signature": {
        "type": vrf.get("signature_type"),
        "v": vrf.get("v"),
        "r": vrf.get("r"),
        "s": vrf.get("s"),
        "signer_addr": vrf.get("signer_addr"),
        "pq_scheme": vrf.get("pq_scheme"),
        "mode": vrf.get("mode"),
        "version": vrf.get("version"),
    }
}

OUT_PATH.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print("Winner:", winner)
print("Receipt written to", OUT_PATH)
