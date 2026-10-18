# H2b-2 — persisted site draft and review-only App state

- Date: 2026-09-26 KST. Status: **H2b-2 LOCAL_UNIT_AND_WEB_PASS / H2b_PARTIAL / ACTUAL_ISAAC_NOT_RUN**.
- [One-page image](H2b-2-review-only-flow.png) ([source SVG](H2b-2-review-only-flow.svg)) is an implementation map, **not a live UI or Isaac screenshot**.

## Scope and behavior

- `ApplicationService` remains the sole generation owner. A typed `SiteGenerationResult` from a fake gateway becomes a `SiteDraftRecord` 2.0; the existing live Nebius adapter still returns the v1 `GenerationResult`. H2b-2 does **not** select the new provider JSON schema or make a paid call.
- `ProjectRecord` 2.0 stores either a v1 draft or a v2 site draft, reads valid 1.0 files without rewriting them on load, and rejects mixed active drafts. The v2 record binds the input digest, plan hash, source, and deterministic expanded scene. Load re-expands it and rejects tampering; no credentials or API response body are stored.
- Workflow API snapshot 1.2 adds `site_draft` beside the v1 `draft`. The site summary includes optional robot/mission values and explicit `review_required`, `build_allowed=false`, `run_allowed=false`. On restart it is review-required; reselecting exactly the same input restores review, not approval.
- React displays the site summary and objects in the Review screen. Its Build control is disabled, and no acknowledgement or broker artifact is created. The v1 Build/Run path remains unchanged. This is **not yet** a v2 Isaac scene compiler or model-capability handshake.

## Checks

- H2b-2 integration: **4/4 PASS** (persist/restore/tamper, v1 1.0 reader, optional robot/mission roundtrip, workflow no broker/ack/Build/Run).
- Existing R3 **9/9**, S2b **7/7**, R5 **10/10**, core **42/42**, provider **28/28** PASS.
- Web unit **19/19** PASS (new v2 review-only case), TypeScript + Vite production build PASS. `git diff --check` PASS; only Windows LF→CRLF warnings.
- First sandboxed Python temporary-directory writes and Vite process start were blocked by Windows sandbox permissions; the same bounded tests passed in approved standard execution. This is not a product test failure.

## Remaining boundaries

H2b remains **PARTIAL**. H2b-3 must explicitly negotiate provider output selection, broker/engine/TypeScript capabilities and a validated v2 scene-only Build path; only then can H2c run actual Isaac acceptance. Do not interpret this review card or its SVG as a 3D build. No live provider, Isaac, ROS, real robot, installer, commit, or push occurred in H2b-2.
