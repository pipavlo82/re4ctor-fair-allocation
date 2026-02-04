import json
import sys
from hashlib import sha256
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

if len(sys.argv) != 2:
    raise SystemExit("Usage: python3 demo/sign_receipt.py <path_to_receipt.json>")

path = sys.argv[1]
receipt = json.load(open(path, "r", encoding="utf-8"))

# Avoid self-reference fields
unsigned = dict(receipt)
unsigned.pop("signature", None)
unsigned.pop("signer_pubkey_hex", None)
unsigned.pop("signature_scheme", None)

msg = canonical_bytes(unsigned)
msg_hash = sha256(msg).digest()

sk_bytes = Path("keys/ed25519_sk.bin").read_bytes()
sk = Ed25519PrivateKey.from_private_bytes(sk_bytes)
sig = sk.sign(msg_hash)

pk_hex = Path("keys/ed25519_pk.hex").read_text(encoding="utf-8").strip()

receipt["signer_pubkey_hex"] = pk_hex
receipt["signature"] = sig.hex()
receipt["signature_scheme"] = "ed25519(sha256(canonical_json))"

json.dump(receipt, open(path, "w", encoding="utf-8"), indent=2)
print("Signed:", path)
