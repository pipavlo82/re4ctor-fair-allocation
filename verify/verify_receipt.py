import json
import sys

if len(sys.argv) != 2:
    print("Usage: python3 verify/verify_receipt.py <path_to_receipt.json>")
    raise SystemExit(2)

path = sys.argv[1]
receipt = json.load(open(path, "r", encoding="utf-8"))

required = ["task_id", "task_commit_sha256", "candidates", "winner", "timestamp"]
for k in required:
    if k not in receipt:
        raise Exception(f"Missing field: {k}")

if receipt["winner"] not in receipt["candidates"]:
    raise Exception("Winner is not in candidates list")

print("OK: receipt structure valid")
print("task_id:", receipt["task_id"])
print("winner:", receipt["winner"])
