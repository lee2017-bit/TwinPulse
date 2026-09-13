# M2-A provider boundary and Copilot UI

## Result

M2-A is complete for local implementation and mock verification. It does not claim that a.biz, Nebius, or another real provider has been verified.

## Implemented

- Provider-neutral text+image request, capability, response, and credential-name-only configuration contracts.
- Cancellation token, one-attempt timeout, stale/late-response rejection, typed rate-limit and capability failures.
- Deterministic mock provider returning a validated TwinPulse `SpecBundle`.
- A real HTTPS JSON transport adapter that remains gated until its endpoint contract and model capability are supplied and approved.
- Credential-free example at `config/provider.example.json`; no key value is stored or logged.
- Copilot-inspired prompt-first Extension panel with workflow stages, structured draft preview, explicit local/mock status, and retained simulation controls.

## Verification

- Core contract tests: 10/10 PASS.
- Provider tests: 6/6 PASS — success, invalid structure, timeout/no retry, rate limit, unsupported image, and cancelled late response.
- Isaac headless regression: PASS — three lifecycle cycles and three run/pause/reset cycles; 28 owned prims, camera/light/goal contract true.
- UI widgets constructed successfully during Isaac Extension startup. The first Full-app review exposed broken non-ASCII glyphs and oversized auto-layout spacing. The UI was corrected to ASCII-only labels and explicit `ui.Pixel` dimensions; the corrected visual appearance still requires a user-visible reload.

## Blocker for a real provider

Required before any external call: non-secret endpoint/protocol documentation, exact model ID, verified vision and structured-output capability, authentication placement, and an approved provider/cost/call count. The adapter intentionally does not guess that a.biz is OpenAI-compatible.

## M2-B handoff

Implement the actual image picker and preview, invoke an approved image-capable provider, show the approximate-model warning once per generation, and compile the returned validated bundle into `/World/TwinPulse`. Mock success is not evidence of multimodal completion.
