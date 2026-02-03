# HTTP Tool Examples (v0)

These examples assume a platform/agent runner that can do HTTP requests.
Replace `RE4CTOR_BASE_URL` and `X-API-Key` as needed.

> Note: endpoints are a proposed shape. If your deployed gateway differs, map accordingly.

---

## 1) Allocate (VRF lottery)

**Request**  
POST `RE4CTOR_BASE_URL/api/v1/allocate`

**Headers:**
- `X-API-Key: <your_key>`
- `Content-Type: application/json`

**Body**
```json
{
  "task_commit_sha256": "7b4bce...de577",
  "epoch": "2026-02-03",
  "candidate_order": "lexicographic",
  "candidates": ["agent_alpha","agent_beta","agent_gamma"]
}
```

**Response (expected)**
```json
{
  "winner": "agent_beta",
  "vrf_output": "0x...",
  "vrf_proof": "0x...",
  "allocation_receipt": {
    "task_id": "task_001",
    "task_commit_sha256": "7b4bce...de577",
    "candidate_order": "lexicographic",
    "candidates": ["agent_alpha","agent_beta","agent_gamma"],
    "winner": "agent_beta",
    "timestamp": "2026-02-03T20:28:06Z",
    "signature": "0x...",
    "signer_pubkey_id": "re4ctor-key-1"
  }
}
```

---

## 2) Verify receipt

**Request**  
POST `RE4CTOR_BASE_URL/api/v1/receipt/verify`

**Body**
```json
{
  "receipt": { "...": "..." }
}
```

**Response**
```json
{
  "valid": true,
  "reason": "ok"
}
```

---

## 3) Sign execution receipt (optional)

**Request**  
POST `RE4CTOR_BASE_URL/api/v1/receipt/sign`

**Body**
```json
{
  "task_id": "task_001",
  "task_commit_sha256": "7b4bce...de577",
  "agent_id": "agent_beta",
  "inputs_hash": "0x...",
  "outputs_hash": "0x...",
  "tools_trace_hash": "0x..."
}
```

**Response**
```json
{
  "receipt": { "...": "..." },
  "signature": "0x...",
  "signer_pubkey_id": "re4ctor-key-1"
}
```

