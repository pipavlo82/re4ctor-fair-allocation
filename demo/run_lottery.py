import json
import random
from datetime import datetime, timezone

agents = json.load(open("demo/agents.json", "r", encoding="utf-8"))
task = json.load(open("demo/task.json", "r", encoding="utf-8"))

# deterministic mock-VRF seed derived from task_commit (commit-reveal style)
commit = task.get("task_commit_sha256")
if not commit:
    raise SystemExit("Missing task_commit_sha256 in demo/task.json. Run: python3 demo/make_task_commit.py")

seed = bytes.fromhex(commit)
random.seed(seed)

winner = random.choice(agents)

receipt = {
    "task_id": task.get("task_id"),
    "task_commit_sha256": commit,
    "candidate_order": "as-listed",
    "candidates": agents,
    "winner": winner,
    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "note": "Mock VRF seed=task_commit_sha256. Replace with Re4ctoR VRF proof later."
}

with open("demo/sample_receipt.json", "w", encoding="utf-8") as f:
    json.dump(receipt, f, indent=2)

print("Winner:", winner)
print("Receipt written to demo/sample_receipt.json")
