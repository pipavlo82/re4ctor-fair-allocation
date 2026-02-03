import json
import hashlib
import random
from datetime import datetime, timezone

agents = json.load(open("demo/agents.json", "r", encoding="utf-8"))
task = json.load(open("demo/task.json", "r", encoding="utf-8"))

# deterministic "mock VRF" seed (later we replace with real Re4ctoR VRF output)
seed = hashlib.sha256(task["task_id"].encode("utf-8")).digest()
random.seed(seed)

winner = random.choice(agents)

receipt = {
    "task_id": task["task_id"],
    "candidates": agents,
    "winner": winner,
    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    "note": "Mock VRF. Replace with Re4ctoR VRF proof later."
}

with open("demo/sample_receipt.json", "w", encoding="utf-8") as f:
    json.dump(receipt, f, indent=2)

print("Winner:", winner)
print("Receipt written to demo/sample_receipt.json")
