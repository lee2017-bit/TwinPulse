# H3b — Photo ↔ physical test site (2026-09-26)

> Later user clarification: do not block initial photo generation, robot connection or sensor collection on manual room measurements. `ready_for_photo_review` has no measurement requirement. The original alignment flag is now explicitly a compatibility alias for **optional manual-evidence review**. Scan-based metric alignment is a future H4 path; independent measurements are useful for accuracy evaluation, not mandatory for every upload. See [connection preparation](robot-connection-preparation.md).

## Decision and boundary

The user chose **a direct photograph of the actual TurtleBot test site**, not a scaled reproduction of an industrial photograph. The final site photograph and on-site dimensions have **not** been supplied. No real track geometry is asserted.

H3b adds the pure, additive `PhotoTrackManifest` contract. It records a stable site ID, the immutable photo `InputRevision` digest and image hash, explicit same-site confirmation, two independently measured horizontal spans (metres, method, uncertainty), and two distinct floor markers defining a local origin and +X direction. `verify_input` rejects a changed photo/input revision. A manifest revision hashes the full record and rejects tampering on load. Monocular inference is not an accepted measurement method. There is deliberately no pixel-to-metre scale field.

`ready_for_alignment_review` means only that evidence fields have been filled; it **does not** grant scan alignment, Isaac Build, route planning, or robot Run. Human confirmation alone is not proof that image content depicts the claimed site; later H4 must independently align scan landmarks in the same frame and quantify residual and unobserved areas. The existing v1/v2 scene and draft serializations are unchanged. No UI/API/runtime persistence was added.

## Synthetic test corpus and real-site gate

| Case | Input | Expected result |
| --- | --- | --- |
| Pending actual demo | No photo or measurements | Missing-evidence list; not reviewable |
| Synthetic same-site | Fake bytes, confirmed site, measured X/Y, markers | Round-trip and input bind pass; reviewable only |
| Different photo or text | Same manifest with other input revision | Rejected |
| Partial evidence | Missing Y span, markers, or site confirmation | Not reviewable |
| Model-inferred dimension / scaled relation | Unsupported method/relation | Rejected |
| Tampered origin or fake confirmation | Changed body digest / confirmation without photo | Rejected |

The corpus index at `fixtures/h3b/corpus.json` explicitly distinguishes the existing structured warehouse fixture, synthetic generic-obstacle non-warehouse contract test, and the pending final physical site. These are **not** three completed photo-fidelity tests. The real-site acceptance is **pending**: obtain a photo of the actual test site, two on-site horizontal spans with measurement method and uncertainty, and two identifiable floor markers. Give the site a stable ID and confirm that the photo shows that same site before binding its `InputRevision`. Height seen only in the photo or not seen by a later 2D scan stays unverified. Neither the synthetic test nor prior warehouse pictures satisfy this real-site gate.

## Verification

- `.venv\Scripts\python.exe -m unittest discover -s packages\twinpulse_core\tests -p test_*.py -q` → **52/52 passed**, including 7 H3b synthetic/corpus cases. The new tests use standard-library `unittest`, so offline installs do not need pytest.
- `pytest` was initially absent after reboot; it was installed into this development `.venv` during diagnosis, but is not required by the final H3b tests. First sandboxed download failed on Windows temporary-directory permissions; approved retry succeeded.
- No live Nebius request, Isaac Build, actual photo ingest, hardware action, commit, or push. H3b **contract/synthetic corpus PASS; real-site acceptance PENDING; H3 overall PARTIAL**.
