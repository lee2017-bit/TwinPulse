# S2a — bounded image decoding and immutable measurement binding

Date: 2026-09-24 KST
Status: **PASS for S2a tested scope; S2b and full R6 remain open**

## Scope

S2a closes the A-04 upload-validation gap and makes the data used by the later generation service explicit and immutable. It does not connect the web App to a live provider and makes no paid request.

## Implemented contract

- Product uploads remain bounded to 10 MiB and 40,000,000 pixels. PNG, JPEG, lossy VP8 WebP, and VP8L WebP are opened, structurally verified, reopened, and fully pixel-decoded. Empty, truncated, header-only, animated, MIME-spoofed, unsupported, and oversized images are rejected with stable error codes.
- `ProductInput` now retains the exact immutable image bytes, SHA-256, MIME type, decoded dimensions, sidecar SHA-256, and typed `MeasurementConstraint` tuple instead of keeping only a count.
- Measurement sidecar 1.1 binds `source_image`, `source_image_sha256`, and `source_image_dimensions_px` to the actual decoded upload. Wrong hash or dimensions are rejected. Existing 1.0 name-bound sidecars remain readable for backward compatibility.
- `InputRevision` includes image MIME when available. `ApplicationService.prepare_input` adds `scene-tools-1.0` to non-secret generation settings, so prompt, image bytes/hash/MIME, input kind, typed constraints, profile, settings, and tool-catalog revision share one digest boundary.
- File names remain metadata only; the upload API does not open a client-supplied path or execute its contents.

## Decoder dependency

Pillow is the codec boundary rather than a hand-written partial JPEG/WebP parser. The app package accepts `Pillow>=12.2,<13` because Isaac Sim 6.0.1 currently bundles 12.2.0. The local product-App lock pins Pillow 12.3.0 for CPython 3.12 Windows x86-64:

```text
wheel SHA-256: a2b55dd6b2a4c4b7d87ffa56bdb33fdc5fdb9a462173861a7bc097f17d91cb09
license expression: MIT-CMU
lock: config/python-runtime-requirements.lock
```

The wheel was installed only below the git-ignored `artifacts/dependencies/runtime` verification path. System Python and Isaac Python were not modified. Company/local setup uses a repository `.venv`; both launcher and verifier auto-select it and fail with a clear dependency message when the decoder is missing.

## RED/GREEN evidence

Initial `tests.integration.test_s2a_input_integrity` produced the expected RED: header-only PNG and truncated JPEG were accepted, lossy VP8 was unsupported, sidecar 1.1 fields were rejected, and tool-catalog revision was not allowed.

After implementation:

- S2a corpus under isolated Pillow 12.3.0: 4/4 PASS.
- The same S2a corpus under Isaac bundled Pillow 12.2.0: 4/4 PASS; Isaac application/engine was not launched.
- Core/Provider/R1/R3/R4/R5/R6/S1b/S1c/S1d/S2a Python regression: 100/100 PASS.
- Original S0 A-04 header-only PNG reproduction: PASS (rejected).
- React tests: 10/10 PASS; production build PASS.
- Official `-SkipIsaac` run `20260924-091023`: FAIL because `verify_r3_application.py` replaced the isolated dependency `PYTHONPATH`. This historical failure is retained.
- Runner fix followed by official `-SkipIsaac` run `20260924-091108`: PASS.

No live provider request, API-key read, actual Isaac application launch, robot command, commit, or push was performed.

## Remaining boundary

S2a validates and binds input; it does not solve A-01. `ProductWorkflow` still returns the deterministic fixture, so distinct prompts can still produce the same draft. S2b must make `ApplicationService` the composition-root owner and connect the current immutable input to the real generation gateway without fixture fallback.
