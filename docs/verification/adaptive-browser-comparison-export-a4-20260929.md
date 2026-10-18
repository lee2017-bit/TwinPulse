# A4 current comparison export: preserve canonical numeric identity

Status: **PASS for the current offline product export path; A4 overall PARTIAL** (2026-09-29 07:25 KST). No historical archive rewrite or physical/Isaac result.

## Defect and bounded change

The preserved `artifacts/bedroom-comparison-browser-20260928-r2/comparison-export.json` loses Python canonical number types when the browser calls `JSON.stringify` (for example `0.0` → `0`). Its outer and nested revisions fail existing recomputation. It remains rejected and unchanged.

Current explicit comparison still uses the existing authenticated/CSRF `POST /v1/product/bedroom/compare`. The download button now requests `POST /v1/product/bedroom/compare-export` with the currently reviewed source revision and displayed comparison revision. The server recomputes both fixed synthetic routes, rejects stale/mismatched revisions, runs the existing A4 comparison validator, then returns Python-serialized UTF-8 JSON text plus its byte SHA-256. The browser checks the returned revision and byte digest before downloading those bytes unchanged. It does not locally stringify the parsed comparison. No Build, lease, robot or model request is added. This is a current-source export, not authentication of arbitrary imported bytes.

Changed product path: `bedroom_review.py` → `api.py` → `api.ts` → `BedroomTwin.tsx`. Tests: `test_bedroom_rehearsal.py`, `test_bedroom_review.py`, `BedroomTwin.test.tsx`. Existing comparison schema, nested record hashes, evaluation axes, motion lock, and failure criteria are unchanged. The separate mission-record browser export still needs the same byte-preservation treatment before it can be used as canonical imported evidence.

## Evidence

- Focused Python comparison/review suite: 23 PASS. New current export survives JSON load and A4 revalidation; stale revision, absent acknowledgement, missing auth/CSRF, unexpected fields are rejected. Historical r2 browser export remains rejected.
- Focused React suite: 14 PASS including stale exported revision displayed as error rather than download.
- Full `scripts/verify_twinpulse.ps1 -SkipIsaac`: **PASS**, `artifacts/runs/20260929-072320/manifest.json` and `verification-console.txt`; core 176, Web 127, production build PASS. `git diff --check` exit 0 (Windows LF/CRLF advisory warnings only).
- Before the approved-permission rerun, the Python HTTP test failed to create a Windows sandbox temp file and Vitest failed at `spawn EPERM`; neither was an assertion failure. The same focused tests passed in the normal permitted execution context. No tests were weakened.
- File SHA-256: `bedroom_review.py` `19f4d27282ccbcced05e44f47ea305de083b6d41c66d38a8a00e2325edf1c3ca`; `BedroomTwin.tsx` `2d8c135e717e3fd8fea90beab3bf3008652a29e28a81e0f069fb145302372bca`.

Actual browser download against the product server and actual Isaac: **NOT_RUN in this increment**. Robot OFF, no SSH/serial/sensor/motor/deployment, no cloud or paid API. Synthetic result is not physical success; collision stays unmeasured. M2-D historical 27/29 FAIL and physical stop FAIL remain. Next: real browser export roundtrip, mission export identity, stored provider receipts/held-out evaluation; A4 is not eligible for auto-routing.
