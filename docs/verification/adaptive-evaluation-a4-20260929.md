# Adaptive A4 — separated synthetic evaluation, first product-path increment

Status: **PARTIAL**. This is a read-only projection of the existing bedroom comparison, not a common cross-provider benchmark or a physical/Isaac physics score.

## Product connection

- `evaluate_bedroom_comparison` recomputes and revalidates both existing route records, comparison conditions, and the comparison revision before reporting. It leaves the original comparison schema/hash unchanged.
- `BedroomReview.evaluate` runs the same current, explicitly acknowledged room review and comparison path; the authenticated/CSRF `POST /v1/product/bedroom/evaluate` returns the separate report. It does not acquire a lease, Build/Run, change the active project, or authorize robot motion.
- Scene fidelity is `NOT_MEASURED` without a surveyed room; simulation quality is `NOT_RUN` without Isaac physics; task success is explicitly **synthetic kinematic**; provider latency, cost and model tool validity remain unknown/not evaluated. Collision count stays `null`/`NOT_MEASURED`; no overall score can mask a failed axis. Synthetic duration/distance comparison is only present if both candidates arrive under the existing identical conditions.

## Important historical export failure retained

The preserved `artifacts/bedroom-comparison-browser-20260928-r2/comparison-export.json` does **not** round-trip through the canonical Python hash: its outer revision and both record revisions differ from recomputation after browser JSON serialization (notably floating `0.0` becoming `0`). The A4 evaluator rejects that archive; it was not repaired, rewritten, or described as authenticated evidence. A current Python-generated comparison survives JSON encode/decode and is evaluated. The authenticated product endpoint avoids re-attesting imported browser bytes by recomputing from the current reviewed source. This remains a separate export-format defect to address before historical browser archives can be evaluated.

## Verification

- Focused bedroom review/rehearsal suite: 22 PASS. Positive current JSON roundtrip and authenticated API; negative tampered metric/conditions/authority, failed-arrival efficiency suppression, and historical browser export refusal.
- Full offline `scripts/verify_twinpulse.ps1 -SkipIsaac`: PASS at `artifacts/runs/20260929-065358`, core 176, web 126, production build PASS. Existing M2-D 27/29 FAIL, physical stop FAIL and all prior validations retain their recorded status.
- Robot remained OFF. No SSH/serial/sensor/motor/deployment, no paid model/API call. Actual Isaac physics and physical evaluation: **NOT_RUN**.

## Remaining A4 acceptance

Add source-specific adapters for M2-D fixed ground truth, provider tool validity and usage/cost receipts, and separate Isaac/contact and physical observations. Build held-out/multi-photo fixed fixtures, repetitions and latency distributions. Compare model routing only with fixed input/scene/map/start-goal/profile/controller/limits/seed/scorer; do not treat map correction as model gain. Resolve browser export identity loss without weakening canonical validation. A4 is not ready for automatic model selection.
