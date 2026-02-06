# Re4ctoR Fair Allocation API (MVP)

Verifiable fairness & signed receipts for agent marketplaces.

## What this service does

- Deterministic task allocation (`/allocate`)
- Receipt signing with Ed25519 (`/receipt/sign`)
- Local cryptographic verification via `verify/verify_receipt.py`

This is infrastructure for trust: allocation decisions are auditable, portable, and cryptographically verifiable.

---

## Endpoints

### `GET /health`

Basic liveness probe.

**Response**
```json
{"ok": true}
```

### `POST /allocate`

Returns deterministic winner selection from a task commitment + candidate list.

**Request**
```json
{
  "task_id": "task_001",
  "task_commit_sha256": "d33a9db4f45f9d2e2fc6b4341242da29b7f13e8bcc1cc928252563c2439ca84f",
  "candidate_order": "lexicographic",
  "candidates": ["agent_gamma", "agent_alpha", "agent_beta"]
}
```

**Response (example)**
```json
{
  "ok": true,
  "task_id": "task_001",
  "task_commit_sha256": "d33a9db4f45f9d2e2fc6b4341242da29b7f13e8bcc1cc928252563c2439ca84f",
  "candidate_order": "lexicographic",
  "candidates": ["agent_alpha", "agent_beta", "agent_gamma"],
  "winner": "agent_gamma",
  "note": "deterministic mock allocation"
}
```

### `POST /receipt/sign`

Signs an unsigned receipt payload and returns:
- `signer_pubkey_hex`
- `signature`
- `signature_scheme`

**Request**
```json
{
  "task_id": "task_001",
  "task_commit_sha256": "d33a9db4f45f9d2e2fc6b4341242da29b7f13e8bcc1cc928252563c2439ca84f",
  "candidate_order": "lexicographic",
  "candidates": ["agent_alpha", "agent_beta", "agent_gamma"],
  "winner": "agent_gamma",
  "timestamp": "2026-02-06T02:05:00Z",
  "note": "deterministic mock allocation"
}
```

**Response (example)**
```json
{
  "task_id":"task_001",
  "task_commit_sha256":"d33a9db4f45f9d2e2fc6b4341242da29b7f13e8bcc1cc928252563c2439ca84f",
  "candidate_order":"lexicographic",
  "candidates":["agent_alpha","agent_beta","agent_gamma"],
  "winner":"agent_gamma",
  "timestamp":"2026-02-06T02:05:00Z",
  "note":"deterministic mock allocation",
  "re4ctor_signature":null,
  "re4ctor_error":null,
  "signer_pubkey_hex":"<hex>",
  "signature":"<hex>",
  "signature_scheme":"ed25519(sha256(canonical_json))"
}
```

---

## Run locally

```bash
cd /mnt/c/Users/msi/re4ctor-fair-allocation
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8091 --reload
```

**OpenAPI:**
- http://127.0.0.1:8091/openapi.json
- http://127.0.0.1:8091/docs

---

## End-to-end quick test

```bash
# health
curl -sS http://127.0.0.1:8091/health

# allocate
curl -sS -X POST http://127.0.0.1:8091/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "task_id":"task_001",
    "task_commit_sha256":"d33a9db4f45f9d2e2fc6b4341242da29b7f13e8bcc1cc928252563c2439ca84f",
    "candidate_order":"lexicographic",
    "candidates":["agent_gamma","agent_alpha","agent_beta"]
  }'

# sign receipt
cat >/tmp/unsigned_receipt.json <<'JSON'
{
  "task_id":"task_001",
  "task_commit_sha256":"d33a9db4f45f9d2e2fc6b4341242da29b7f13e8bcc1cc928252563c2439ca84f",
  "candidate_order":"lexicographic",
  "candidates":["agent_alpha","agent_beta","agent_gamma"],
  "winner":"agent_gamma",
  "timestamp":"2026-02-06T02:05:00Z",
  "note":"deterministic mock allocation"
}
JSON

curl -sS -X POST "http://127.0.0.1:8091/receipt/sign" \
  -H "Content-Type: application/json" \
  -d @/tmp/unsigned_receipt.json \
  > /tmp/signed_receipt.json

# verify locally
cd /mnt/c/Users/msi/re4ctor-fair-allocation
source .venv/bin/activate
python3 verify/verify_receipt.py /tmp/signed_receipt.json
```

**Expected:**
```
OK: receipt valid
signature: ok
```

---

## Security notes

- Keep API keys and signing keys out of git (`.env`, local key files only).
- Do not commit runtime artifacts from `demo/`.
- Rotate signing keys by environment (dev/stage/prod).
- Treat signed receipts as audit artifacts; persist immutable copies for dispute resolution.
