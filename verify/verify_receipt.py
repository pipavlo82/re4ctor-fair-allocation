import json
import sys
from hashlib import sha256
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


if len(sys.argv) != 2:
    raise SystemExit("Usage: python3 verify/verify_receipt.py <path_to_receipt.json>")

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

# Fail-closed: receipt with upstream error is invalid
if receipt.get("re4ctor_error"):
    raise Exception(f"Receipt has re4ctor_error: {receipt['re4ctor_error']}")

# Signature verification (required)
sig = receipt.get("signature")
pk_hex = receipt.get("signer_pubkey_hex")
scheme = receipt.get("signature_scheme")

if not (sig and pk_hex and scheme):
    raise Exception("Missing required signature fields: signature, signer_pubkey_hex, signature_scheme")

if scheme != "ed25519(sha256(canonical_json))":
    raise Exception(f"Unsupported signature_scheme: {scheme!r}")

unsigned = dict(receipt)
unsigned.pop("signature", None)
unsigned.pop("signer_pubkey_hex", None)
unsigned.pop("signature_scheme", None)

msg = canonical_bytes(unsigned)
msg_hash = sha256(msg).digest()

pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pk_hex))
pk.verify(bytes.fromhex(sig), msg_hash)

print("OK: receipt valid")
print("task_id:", receipt["task_id"])
print("candidate_order:", order)
print("winner:", winner)
print("signature: ok")
