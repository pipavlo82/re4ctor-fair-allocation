import os
import json
import hashlib
from datetime import datetime, timezone

TASK_PATH = "demo/task.json"

task = json.load(open(TASK_PATH, "r", encoding="utf-8"))

nonce = os.urandom(32).hex()

payload = f'{task.get("task_id","")}||{task.get("description","")}||{task.get("reward","")}'
task_commit = hashlib.sha256((payload + "||" + nonce).encode("utf-8")).hexdigest()

task["nonce_hex"] = nonce
task["task_commit_sha256"] = task_commit
task["commit_timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

with open(TASK_PATH, "w", encoding="utf-8") as f:
    json.dump(task, f, indent=2)

print("Updated:", TASK_PATH)
print("task_commit_sha256:", task_commit)
