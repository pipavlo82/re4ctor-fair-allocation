from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from hashlib import sha256
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


app = FastAPI(title="Re4ctoR Fair Allocation API", version="0.1.0")


# ---------- models ----------
CandidateOrder = Literal["as-listed", "lexicographic"]


class AllocateRequest(BaseModel):
    task_id: str
    task_commit_sha256: str = Field(min_length=64, max_length=64)
    candidate_order: CandidateOrder = "lexicographic"
    candidates: List[str]


class AllocateResponse(BaseModel):
    ok: bool = True
    task_id: str
    task_commit_sha256: str
    candidate_order: CandidateOrder
    candidates: List[str]
    winner: str
    note: str


class ReceiptSignRequest(BaseModel):
    task_id: str
    task_commit_sha256: str
    candidate_order: CandidateOrder
    candidates: List[str]
    winner: str
    timestamp: Optional[str] = None
    note: Optional[str] = None
    # не блокуємо службові поля, якщо прийдуть
    re4ctor_signature: Optional[dict] = None
    re4ctor_error: Optional[str] = None


# ---------- helpers ----------
def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _load_signing_key() -> Ed25519PrivateKey:
    """
    Джерела ключа (у порядку пріоритету):
      1) RECEIPT_SIGNER_SK_HEX - hex приватного ключа (32 байти seed або 64 байти)
      2) RECEIPT_SIGNER_SK_PATH - шлях до bin-файлу (за замовчуванням keys/ed25519_sk.bin)
    """
    sk_hex = (os.getenv("RECEIPT_SIGNER_SK_HEX") or "").strip()
    if sk_hex:
        raw = bytes.fromhex(sk_hex)
        if len(raw) == 32:
            return Ed25519PrivateKey.from_private_bytes(raw)
        if len(raw) == 64:
            return Ed25519PrivateKey.from_private_bytes(raw[:32])
        raise ValueError("RECEIPT_SIGNER_SK_HEX must be 32 or 64 bytes hex")

    sk_path = os.getenv("RECEIPT_SIGNER_SK_PATH", "keys/ed25519_sk.bin")
    p = Path(sk_path)
    if not p.exists():
        raise FileNotFoundError(f"Signing key not found: {sk_path}")
    raw = p.read_bytes()
    if len(raw) == 32:
        return Ed25519PrivateKey.from_private_bytes(raw)
    if len(raw) == 64:
        return Ed25519PrivateKey.from_private_bytes(raw[:32])
    raise ValueError(f"Unsupported key length in {sk_path}: {len(raw)}")


def _pubkey_hex_from_sk(sk: Ed25519PrivateKey) -> str:
    pk = sk.public_key().public_bytes_raw()
    return pk.hex()


def _pick_winner(task_commit_sha256: str, candidates: List[str]) -> str:
    idx = int(task_commit_sha256, 16) % len(candidates)
    return candidates[idx]


# ---------- routes ----------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/allocate", response_model=AllocateResponse)
def allocate(req: AllocateRequest):
    if not req.candidates or len(req.candidates) == 0:
        raise HTTPException(status_code=400, detail="candidates must be non-empty")

    cands = list(req.candidates)
    if req.candidate_order == "lexicographic":
        cands = sorted(cands)

    winner = _pick_winner(req.task_commit_sha256, cands)

    return AllocateResponse(
        ok=True,
        task_id=req.task_id,
        task_commit_sha256=req.task_commit_sha256,
        candidate_order=req.candidate_order,
        candidates=cands,
        winner=winner,
        note="deterministic mock allocation",
    )


@app.post("/receipt/sign")
def receipt_sign(req: ReceiptSignRequest):
    if req.candidate_order == "lexicographic" and req.candidates != sorted(req.candidates):
        raise HTTPException(status_code=400, detail="Candidates not lexicographically sorted")
    if req.winner not in req.candidates:
        raise HTTPException(status_code=400, detail="Winner is not in candidates list")

    receipt = req.model_dump()
    if not receipt.get("timestamp"):
        receipt["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # приберемо старий підпис, якщо прислали
    receipt.pop("signature", None)
    receipt.pop("signer_pubkey_hex", None)
    receipt.pop("signature_scheme", None)

    try:
        sk = _load_signing_key()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"signing_key_error: {e}")

    unsigned = dict(receipt)
    msg = canonical_bytes(unsigned)
    msg_hash = sha256(msg).digest()
    sig = sk.sign(msg_hash).hex()
    pk_hex = _pubkey_hex_from_sk(sk)

    receipt["signer_pubkey_hex"] = pk_hex
    receipt["signature"] = sig
    receipt["signature_scheme"] = "ed25519(sha256(canonical_json))"

    return receipt
