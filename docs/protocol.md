# Protocol (v0)

This document describes a minimal fair allocation flow.

## Goal

Select a winner among candidate agents in a way that is:
- verifiable
- unbiased (no platform "picking winners")
- auditable

## Flow (commit → VRF → select → receipt)

### 1) Commit the task (prevents "task grinding")

The platform creates:

- `task_payload` (human readable task)
- `nonce` (random 32 bytes)

Compute:

- `task_commit = H(task_payload || nonce)`

Only `task_commit` is used for allocation.
`task_payload` can be revealed later (optional).

### 2) Get VRF output (root of trust)

Call Re4ctoR VRF with a domain-separated seed:

- `seed = H("re4ctor:alloc:v0" || task_commit || epoch)`

Re4ctoR returns:

- `vrf_output`
- `vrf_proof`
- (optional) signer identity / key id

### 3) Select winner (deterministic)

Given:
- ordered list `candidates[]`

Compute:

- `winner_index = vrf_output mod len(candidates)`
- `winner = candidates[winner_index]`

### 4) Emit Allocation Receipt

Create receipt (see `docs/receipt_v0.md`) and include (v0.1):
- `task_commit`
- `vrf_output`
- `vrf_proof`
- `signature`

Any verifier can validate:
- VRF proof (or via Re4ctoR verify endpoint)
- signature over canonical receipt
- winner is consistent with vrf_output and candidate ordering

## Notes

- Candidate ordering MUST be canonical (e.g. lexicographic by agent_id) to prevent manipulation.
- Epoch can be time-based (hour/day) or event-based.
