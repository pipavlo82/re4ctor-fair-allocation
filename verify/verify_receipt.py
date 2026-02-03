import json
import sys

def die(msg: str, code: int = 1):
    raise SystemExit(msg)

if len(sys.argv) != 2:
    die("Usage: python3 verify/verify_receipt.py <path_to_receipt.json>", 2)

path = sys.argv[1]
receipt = json.load(open(path, "r", encoding="utf-8"))

required = ["task_id", "task_commit_sha256", "candidate_order", "candidates", "winner", "timestamp"]
for k in required:
    if k not in receipt:
        raise Exception(f"Missing field: {k}")

order = receipt.get("candidate_order")
if order not in ("as-listed", "lexicographic"):
    raise Exception(f"Unsupported candidate_order: {order!r}")

cands = receipt["candidates"]
if not isinstance(cands, list) or not all(isinstance(x, str) for x in cands):
    raise Exception("candidates must be a list[str]")

if order == "lexicographic":
    if cands != sorted(cands):
        raise Exception("Candidates not lexicographically sorted")

winner = receipt["winner"]
if winner not in cands:
    raise Exception("Winner is not in candidates list")

print("OK: receipt structure valid")
print("task_id:", receipt["task_id"])
print("candidate_order:", order)
print("winner:", winner)
