# S1c authentication lifetime and safe reopen

- Date: 2026-09-23 KST
- Root: `C:\Users\jaewo\Documents\TwinPulse`
- Git HEAD at test boundary: `500f19992350d5b96877a9001d429656dfc7f748`
- Scope: authentication lifetime, reload/new-tab recovery, stale-session handling only
- Paid provider requests: none
- Isaac runs: none

## Contract implemented

- Product and engine sessions use a 30-minute renewable idle lifetime and an 8-hour non-renewable absolute lifetime.
- Every authenticated request renews idle expiry only up to the absolute deadline.
- The `HttpOnly; SameSite=Strict` product cookie uses the 8-hour absolute `Max-Age`, so the browser never discards an otherwise renewable server session after only 30 minutes.
- `GET /v1/product/session` lets a same-origin page recover the existing CSRF token from its HttpOnly-cookie session. This supports reload and a second tab without replaying the one-time bootstrap.
- The process owner keeps a root secret in memory and calls `POST /v1/bootstrap/product/issue` to mint a short-lived one-time browser ticket. The root owner secret no longer enters the browser URL, and a consumed ticket cannot be replayed.
- The initial fragment bootstrap is removed with `history.replaceState` before the network request. Actual Chrome verified that the rendered page URL no longer contains the bootstrap value.
- A 401 clears browser CSRF state and becomes the finite `session_reopen_required` error. State-changing requests are not retried, preventing stale command replay.
- Existing Host, Origin, role, CSRF, and one-time bootstrap checks remain active.

## RED evidence

1. Fake-clock API tests initially failed 3/3 because `LocalApiServer` did not yet accept idle and absolute TTLs. The added expired-session owner-ticket test separately failed with the expected 404 before the issuer existed.
2. Browser unit tests then failed 3 new cases: new-tab recovery, stale-tab rejection, and 401 normalization/no retry. The existing fragment-scrub test passed.

## GREEN evidence

| Gate | Result |
|---|---|
| `python -m unittest tests.integration.test_r4_bridge_api tests.integration.test_r5_product_api tests.integration.test_s1c_auth_lifetime -v` | PASS 20/20; rerun outside sandbox because R5 `%TEMP%` writes were denied in the restricted run |
| `python -m unittest tests.integration.test_r6_process_manager -v` | PASS 10/10 |
| `pnpm test` with bundled runtime | PASS 9/9 across 2 files |
| `pnpm build` with bundled runtime | PASS; TypeScript and Vite production bundle |
| Actual headless Chrome `s1c-session.mjs` | PASS: `bootstrap_scrubbed`, `reload_recovered`, `new_tab_recovered` |
| Artifact secret scan for `bootstrap=`, `Bearer `, and `sk-` | 0 matches |
| Temporary backend after browser gate | stopped |

Actual-browser result: `artifacts/runs/20260923-s1c-auth/browser-result.json`.

## Source hashes at boundary

| File | SHA-256 |
|---|---|
| `packages/twinpulse_app/src/twinpulse_app/api.py` | `D29A3195F3DF8DBC892BBF52BB2ABE64CE4322EFC976CDE2C49664A6ABB229EE` |
| `packages/twinpulse_app/src/twinpulse_app/process_manager.py` | `A0856B9F134ABCC00D1A63C5A0CC404F3C95FE2BD1E1981B342C85FD2CDD8E4D` |
| `apps/twinpulse-web/src/api.ts` | `34DA5933706D1A9FE5662B26901C14A3D0186C1DFA5599A557628F934A007FC2` |
| `apps/twinpulse-web/src/api.test.ts` | `DE3188AC9D2A2146CBF4E998B16A0C38135F7EF7DD26A4A3F6870415B0DBBFC5` |
| `apps/twinpulse-web/e2e/s1c-session.mjs` | `232B578F31E8D302A1FD8297BC03B636D5ECBA7334D69C6886EC89E84C55330E` |
| `tests/integration/test_s1c_auth_lifetime.py` | `8FD7AAF0525890829C5D4A3CD8ADEF4FFDDC5ECC93464A7773F7DB51BB7ED185` |

## Boundary

S1c is PASS. This does not close full R6: S1d process-boundary/state-isolation work, stored M2-C managed replay, fresh-clone/company-PC validation, and the later live-provider gate remain open. No commit or push was made.
