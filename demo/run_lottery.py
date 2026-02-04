import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

def load_json(path: str):
    return json.load(open(path, "r", encoding="utf-8"))

def load_task():
    # Prefer local secrets file (ignored by git)
    local_path = Path("demo/task.local.json")
    if local_path.exists():
        return load_json(str(local_path)), str(local_path)

    # Fallback to public task.json (no secrets)
    return load_json("demo/task.json"), "demo/task.json"

agents = load_json("demo/agents.json")
task, task_path = load_task()

commit = task.get("task_commit_sha256")
if not commit:
    raise SystemExit("Missing task_commit_sha256. Run: python3 demo/make_task_commit.py")

# Seed winner selection deterministically from commit (commit-reveal style)
seed = bytes.fromhex(commit)
random.seed(seed)

winner = random.choice(agents)

receipt = {
    "task_id": task.get("task_id"),
    "task_commit_sha256": commit,
    "candidate_order": task.get("candidate_order", "as-listed"),
    "candidates": agents,
    "winner": winner,
    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "note": "Mock allocation seed=task_commit_sha256 (commit-reveal)."
}

# Optional: enrich receipt with live Re4ctoR VRF sample (if key is available locally)
api_key = task.get("re4ctor_api_key") or os.getenv("RE4CTOR_API_KEY")
base_url = task.get("re4ctor_base_url") or os.getenv("RE4CTOR_BASE_URL") or "https://re4ctor.com"
vrf_path = task.get("re4ctor_vrf_path") or os.getenv("RE4CTOR_VRF_PATH") or "/api/v1/vrf"

if api_key:
    try:
        import urllib.request

        url = base_url.rstrip("/") + vrf_path
        req = urllib.request.Request(url, headers={"X-API-Key": api_key})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        # Use VRF random to pick winner deterministically from candidate list
        # (This is the "root-of-trust" mode; reproducible given receipt + candidate list.)
        r = int(payload["random"])
        winner_vrf = agents[r % len(agents)]
        receipt.update({
            "winner": winner_vrf,
            "note": "Re4ctoR VRF-backed allocation (root-of-trust).",
            "re4ctor_random": payload.get("random"),
            "re4ctor_timestamp": payload.get("timestamp"),
            "re4ctor_msg_hash": payload.get("msg_hash"),
            "re4ctor_signer_addr": payload.get("signer_addr"),
            "re4ctor_mode": payload.get("mode"),
            "re4ctor_version": payload.get("version"),
            "re4ctor_sig": {
                "hash_alg": payload.get("hash_alg"),
                "signature_type": payload.get("signature_type"),
                "v": payload.get("v"),
                "r": payload.get("r"),
                "s": payload.get("s"),
                "pq_scheme": payload.get("pq_scheme"),
            },
        })
    except Exception as e:
        receipt["re4ctor_error"] = f"vrf_fetch_failed: {e.__class__.__name__}"

with open("demo/sample_receipt.json", "w", encoding="utf-8") as f:
    json.dump(receipt, f, indent=2)

print("Task loaded from:", task_path)
print("Winner:", receipt["winner"])
print("Receipt written to demo/sample_receipt.json")
