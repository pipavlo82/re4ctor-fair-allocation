# Receipt v0 (Re4ctoR)

This repository defines a minimal, portable receipt format for:
- **fair task allocation** (VRF lottery)
- **execution attestations** (inputs/outputs hash + trace hash)

The receipt is designed to be:
- deterministic
- verifiable
- easy to embed into agent platforms and social networks.

## Fields (allocation receipt)

- `task_id` (string)
- `candidates` (string[])
- `winner` (string)
- `timestamp` (RFC3339 UTC, e.g. `...Z`)
- `note` (string, optional)

## Next (v0.1): cryptographic bindings

Add:
- `task_commit` (bytes32)
- `vrf_output` (bytes32)
- `vrf_proof` (bytes)
- `receipt_hash` (bytes32)
- `signature` (bytes)
- `signer_pubkey_id` (string)

## Verification rules

- `winner` MUST be a member of `candidates`
- `timestamp` MUST be UTC (`Z`)
- when `signature` is present, the verifier MUST validate it over canonical JSON serialization
