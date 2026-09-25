# S2c provider settings hardening verification

- Date: 2026-09-24 KST
- Result: **PASS for the local non-paid boundary**
- Paid provider requests: **0**
- Isaac application launch: **NOT RUN**
- Physical robot commands: **0**

## Implemented boundary

- Provider settings schema 2.0 identifies the adapter kind, provider profile, endpoint path, capability set, and non-secret credential reference separately from model options.
- Legacy schema 1.0 auto-migration is limited to the known OpenAI origin. A custom legacy origin requires an explicit profile migration instead of inheriting the OpenAI credential silently.
- An endpoint/origin binding change requires either a new key or explicit credential reapproval. Empty-key keep behavior remains available only when the binding is unchanged, or when the user explicitly reapproves the existing key for the changed endpoint.
- Settings writes are serialized and use a unique temporary file, flush/fsync, and atomic replace. Credential-save failure leaves settings unchanged; settings-save failure rolls the credential back.
- Corrupt settings JSON is preserved and reported as `provider_settings_corrupt` rather than overwritten.
- The API/UI reports `settings_saved`, `capability_checked`, `credential_configured`, and `live_request_succeeded` independently. A saved key is not labeled as a successful live connection.
- The live gateway derives endpoint and capability limits from the validated profile and rejects a credential-reference mismatch.

## Acceptance evidence

`tests/integration/test_s2c_provider_settings.py` passed 7/7:

1. Schema 2.0 profile identity and OpenAI-only legacy migration.
2. Concurrent atomic writes leave one valid document and no shared temporary file.
3. Origin changes require a new key or explicit reapproval.
4. Credential-store failure does not alter settings.
5. Settings-store failure restores the previous credential and never serializes the canary.
6. Corrupt JSON is preserved and surfaced as a structured error.
7. Saved settings, capability validation, key presence, and live success remain separate states.

Related regression:

- R3 + R5 + S2b + S2c: 32/32 PASS.
- Core: 24/24 PASS.
- Provider: 13/13 PASS.
- React/Vitest: 10/10 PASS.
- React production build: PASS.
- Official non-Isaac verification `artifacts/runs/20260924-143027`: PASS with 99 Python checks, React 10/10, and production build.

The first sandboxed test attempt could not create files below the canonical repository and was not a product failure. The identical suite passed after granting the test process write access to its isolated artifact directory. No secret value, Authorization header, paid request, or live endpoint was used.

## Remaining boundary

- S2c does not establish that any Nebius/OpenAI endpoint supports the declared model or modality. Live success remains false until a validated request succeeds.
- S2d is next: replay the three stored M2-C outputs through service → broker → manager → actual Isaac with zero provider calls, then keep any paid live smoke as a separately approved action.
- S3 model list, Base URL, and API key configuration wait for the user-provided Nebius/NVIDIA details.
