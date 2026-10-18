# Compact photo contract experiment — 2026-10-07 / v317

후속 v318: 사용자 사진 전송 승인을 받아 실제3회 검사를 수행했고 grammar/객체 누락/가짜 근거 오류를 발견·보완했다. 후속1.1의 실제 모델 검사는 아직 하지 않았다. [현재 결과·수정·잔여](photo-compact-live-20261007.md). 아래 거절/48회 상태는 v317 당시 이력이다.

## Outcome

**Opt-in implementation and offline integration only. Production default unchanged. Actual new-source photo inference/Chrome/Isaac NOT_RUN. Robot/deployment/sensor/motor/installation/commit/push/new agents: 0. H5/H6/C3–C6 PARTIAL; whole_demo_ready=false.** Prior v316 photo FAIL and actual text/Isaac evidence remain historical, not new-source acceptance.

## Connected code and invariants

`photo_layout.py` accepts strict `photo-layout-1.0`: room dimensions, object IDs/categories, nine approximate regions, discrete yaw and actual observation IDs. No executable/model-generated tool commands. Explicit constructor `compact_photo_layout=True` uses this only for Site2.2 photos; normal text/photo/legacy composition stays unchanged. `verify_agent_reliability.py --compact-photo` is explicit and preserves existing models, 4000/8000 caps, 90s deadline and shared repair1. Repair reuses the observer and the same compact schema.

The compiler expands through the existing catalogue and pure executor, then the existing GenerationService/chat/artifact/SIM-review path. Preserve all 24 reviewed inventory IDs/categories, not just19 route risks. Without reviewed inventory, require each non-background observed entity. Reject invented IDs/objects, invalid types/nonfinite numbers, missing observations, ambiguous room dimensions and changed explicit user floor. Furniture sizes cannot become room dimensions. If selected regions cannot fit all footprints/risk envelopes, reject; never omit objects, enlarge the floor or cross regions to force success.

Provider result/experiment trace records compiler version/layout digest/estimated placements, physical_authority=false, production_default=false and placement_relationships=NOT_RECONSTRUCTED. **Persisted SiteDraftRecord serialization/hash is unchanged and does not store the new provider trace.** The saved plan summary itself states estimated inventory proxies, not reconstructed geometry.

## Fidelity limitation — not a completed photo replica

Existing furniture validation considers XY collision solids even at different Z. This compiler does not reconstruct host/child support: box above wardrobe, clothing inside it, attached bedding and true measured surfaces. Independently spaced inventory proxies, catalogue sizes and estimated height offsets cannot count as faithful photo geometry, true scale, verified free space or physical readiness. The 24-item8×8 fixture is a capacity test, **not this user's room dimensions**. Do not adopt this experimental policy based on latency alone; placement/attachment fidelity and actual same-photo product/Isaac proof are required.

## Tests and failures retained

- Final provider suite **54 / 0.855s PASS**, including9 compact contract tests.
- Core Site suites **17 / 0.024s PASS**, unchanged guard/geometry rules.
- Related integration **115 / 64.105s PASS**; final frozen-source chat/reliability **69 / 25.032s PASS**. These suites overlap/import tests; counts are not unique totals.
- Chat integration alone **47 / 24.512s PASS** after a test-only accessor correction. New compact fixture goes through photo request→artifact→SIM review, broker operations=[]/physical_authority=false. Not an actual model or Isaac test.
- Initial8 compact tests had unit-parser failure and fixture errors (non-digest source reference; all24 forced into one small centre region). Fixed unit matching and the fixtures; no floor enlargement/threshold relaxation. First chat test used nonexistent application.project; changed to public application.site_draft. No model failures were disguised as successes.
- Web source unchanged; Web/build/browser/Isaac not rerun. Prior v316 results historical. git diff --check PASS with pre-existing CRLF warnings.

## Blocked before dispatch — private photo transfer

One bounded P01 evaluation command using the original JPEG and existing Nebius Gemma/Nano/shared ledger was rejected **before process launch** by auto-review: explicit approval for this specific private interior photo's external transfer was not sufficient. No workaround/alternate endpoint/retry. This is a privacy authorization blocker, not a model/authentication error and not a paid FAIL sample.

Ledger checked after rejection: **48/60 requests, 0 pending**, estimated known usage+unknown reservation **USD0.07615086**, invoice/balance unverified. Extra paid calls0. User decision needed: approve sending the provided bedroom photo to the existing Nebius Gemma/Nemotron endpoint for this bounded experiment; no robot authority or budget expansion implied.

## Next

After explicit photo-transfer approval, one bounded actual P01 test (same global repair1 and campaign)→retain raw/usage/any rejection→separately resolve spatial/support fidelity→adopt only a verified production policy→same-photo chat/Isaac Build/current-frame/Run/Stop/reload. Matrix and physical stages remain separate. No automatic retry while awaiting approval.

## Frozen six-file SHA256

photo_layout.py: `918d91433f185cc6a8d0a19bcf9aaa594da1c0365639cbb0259d8fa89129bf92`

nebius_pipeline.py: `6bb4ef05613c1729cc09ca7a82ac82ab4410136652fbbf638a3a5f877f05782b`

service.py: `e2c4d1266db4d68401e6d5ccd6d40162234a5d95cc8c8edf28eaf92780871893`

test_photo_layout.py: `7b75666e7a5b85764dabbb5ccd9e6233fa5d96463d7e6a621c10e868903bfe07`

test_chat_site_text_generation.py: `5392cb00d0fa40289e47065533d979657b0a2ae022b9b65c40f62c100d76b9fe`

verify_agent_reliability.py: `3e523507dc6c7a26e99d5d2e37fc1e6f4e234179ab4fcae9b9ba684b984055fd`
