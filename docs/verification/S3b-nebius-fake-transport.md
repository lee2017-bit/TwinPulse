# S3b Nebius two-stage fake-transport verification

- Date: 2026-09-25 KST
- Status: **PASS for the fake-transport and local-validation boundary**
- Live/paid Nebius requests: **0**
- Isaac Sim launches: **0**
- Credential reads or writes: **0**

## Implemented boundary

`NebiusChatCompletionsPipelineProvider` implements the S3a decision as two explicit OpenAI-compatible Chat Completions stages:

1. `google/gemma-3-27b-it` receives the single image plus user context and must return a bounded `ObservationArtifact` under a strict JSON schema.
2. `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` receives text-only user intent, the validated observation, trusted measurement constraints, robot profile, and tool-catalog identity. It must return the complete strict `SceneToolPlan`.
3. Existing local parsing, measurement validation, allowlisted registry execution, and `SpecBundle` validation remain the final authority.

The observer cannot choose tools or dynamics. The planner makes the material geometry, placement, predefined-AGV, and task decisions; it is therefore not a decorative summary stage. `openbmb/MiniCPM-V-4_5` is representable only as an explicitly selected observer. An observer failure never triggers automatic fallback or retry.

## Safety and provenance

- The adapter requires exactly one supported image, structured-output capability, `chat/completions`, one configured planner model, and `max_attempts=1`.
- Response model IDs must exactly match the requested stage model IDs.
- Redirects are rejected. HTTP 401/403, 429, 5xx, other request failures, timeout, refusal, truncation, malformed JSON, invalid observations, cancellation, and late results are typed failures.
- Real transport responses are bounded to 2 MiB. No response body, API key, Authorization header, or image data URI is logged.
- Persisted provenance contains stage request/model/finish/usage receipts, observation hash/schema, and image MIME/SHA-256/byte count. The draft-store sanitizer rejects secret-bearing and image-bearing fields.
- Generated draft record schema is now `3.0`; schema `2.0` records remain loadable and are promoted without fabricated provider provenance.

## Verification

| Gate | Result |
|---|---|
| S3b fake transport: happy path, strict schemas, image-only observer handoff, text-only planner handoff | PASS |
| Invalid observation and response-model mismatch stop before planner | PASS |
| Manual fallback has one attempt and no automatic retry | PASS |
| Timeout, cancellation, late response, refusal, truncation, 401/403, 429, 5xx, redirect | PASS |
| Secret/data-URI exclusion and bounded provenance persistence | PASS |
| Core tests | 26/26 PASS |
| Provider tests | 21/21 PASS, including S3b 8/8 |
| Preserved R1/R3/S2 regression sample | 35/35 PASS |
| Official non-Isaac runner | `artifacts/runs/20260925-000253`, PASS: 112 Python tests, React 10/10, production build |

The official runner was changed from one provider test file to provider test discovery so the S3b suite cannot be silently skipped.

## Explicitly not proven

- Nebius has not received a request from this implementation. Model availability, exact JSON-schema behavior, vision quality, usage/cost fields, latency, and output quality remain unverified.
- The product settings/UI/backend still use the earlier provider selection path. Wiring the selected adapter and exact observer/planner identities into product settings is part of the S3c readiness change, before any live request.
- No generated S3b plan was built in Isaac; no cloud GPU, endpoint, physical robot, commit, or push was used.

## Next gate

S3c must first add the product configuration/wiring without calling the provider. A live gate then requires an explicit finite approval covering exact models, maximum request count, output/token limits, timeout, retry count zero, and maximum spend. One small image should be observed, planned, locally validated, built, and tied to the recorded receipts before any additional request.
