# Adaptive A3 — source-bound observation reference (first increment)

Status: **PARTIAL**. This is an offline source-reference and evidence-ID boundary, not world registration, live sensor fusion, physical calibration or movement authority.

06:23 follow-up: a v2 `visual` claim now requires at least one observed ID and rejects any ID whose observer kind is `unknown`, even when the model reports high confidence. A hidden region cannot be laundered into visible free-space evidence. Existing accepted visual references and inferred-without-visual-ID behavior remain unchanged. The single-stage OpenAI Responses v1 route has no separately identified observation artifact; this work deliberately did **not** invent IDs or alter its plan/provenance schema. Official OpenAI Structured Outputs documentation describes schema adherence, not grounding truth: https://developers.openai.com/api/docs/guides/structured-outputs . This is a code-path inference, not a claim about model accuracy.

## Connected product path

- `WorldObservationRef` is a strict, versioned sidecar in core. A photo-model observation and a saved native scan use the same envelope but retain different coordinate, time and metric meanings. Both reject `alignment_verified=true` and `motion_authorized=true`, including direct object construction. Unknown fields and invalid IDs/digests fail closed.
- The existing Nebius v2 plan evidence gate now checks visual IDs through the photo reference made from the existing observation digest and request image bytes. The legacy `ObservationArtifact` 1.0 serialization, planner body and output provenance are unchanged. No live provider call was made.
- Imported native scan review exposes an authenticated read-only `GET /v1/product/native-scan/reference`, bound to the review revision and recorded bundle/raw SHA. This is a recorded hash claim, **not verification of original raw bytes**. It does not change the existing snapshot, project, broker, TF or mission gate.

## Verification

- New core reference tests: 3 PASS (photo/native roundtrip; fake visual ID; invalid source/frame/time/metric, duplicate IDs and direct authority construction rejected).
- Existing Nebius pipeline tests: 19 PASS, including invented visual reference rejection.
- Authenticated native-scan API integration: 1 PASS; anonymous access denied, source and bundle hashes returned, project/lease unchanged.
- Full offline `scripts/verify_twinpulse.ps1 -SkipIsaac`: PASS at `artifacts/runs/20260929-055443`; core 176, web 126, production web build PASS. Existing failure tests retained. A first unprivileged standalone API attempt could not create its Windows temp fixture (`PermissionError`); the same test passed with approved local temp access.
- Follow-up focused Nebius suite 21 PASS, including 2 new negative tests for unknown-as-visible and visual-without-ID. Full offline regression repeated PASS at `artifacts/runs/20260929-062131`: core 176, web 126, build PASS.

## Not validated / next

- No independent fake provider adapter sharing the new envelope yet; A3 acceptance therefore **not complete**. The v2 gate blocks a direct unknown-as-visual claim but cannot prove a model-drawn region is truly free or correctly measured. No measured dimensions from photo, no scan-to-room transform, no beam timestamp, no verified footprint or physical pose. Photo observation and native scan are not merged.
- Next offline step: map the other existing provider strategy to the same sidecar without changing serialized v1/v2 plans or invoking a paid model, then add mixed-frame/unknown-space rejection fixtures against the actual draft path. A4 evaluation must keep synthetic/Isaac/physical separate.
- Robot remains OFF; SSH, serial, sensor, motor, deployment and physical tests: **NOT_RUN**. Past physical stop FAIL remains FAIL; live mission lock unchanged.
