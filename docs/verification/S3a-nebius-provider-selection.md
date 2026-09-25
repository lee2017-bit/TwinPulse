# S3a — Nebius provider capability and deployment selection

- Date: 2026-09-24 KST
- Scope: no-inference provider selection and architecture decision
- Result: **PASS for S3a selection only**
- Live inference: **NOT RUN**
- Paid requests: **0**
- Dedicated endpoints created: **0**

## Evidence boundary

The following evidence is deliberately kept separate:

1. The user supplied the authenticated `GET /v1/models` response for the current Nebius Token Factory project. It proves only which public serverless model IDs the account listed at that moment.
2. `C:\Users\jaewo\Downloads\Nebius_모델_카탈로그_Codex용.md` supplies catalog metadata such as declared modality, precision, parameter count, and context size. It is a snapshot, not a successful inference result.
3. The user supplied a Token Factory UI capture showing `nvidia/Cosmos3-Super-Reasoner` only through a dedicated H100 endpoint flow in `eu-north1`, with the UI estimating USD 0.135 per replica-minute. No endpoint was deployed.
4. Nebius documentation identifies `https://api.tokenfactory.nebius.com/v1/` as the OpenAI-compatible base URL and documents image input, structured output, and function calling. Documentation-level support does not prove that every listed model supports every feature.

No API key was read, printed, serialized, or requested for this step. Exact serverless price, license, region, JSON-schema behavior, tool-calling behavior, image limits, and output limits remain unverified where the supplied account response did not contain them.

## Account-visible candidates

| Role | Exact account-visible model ID | Catalog declaration | Context | Deployment choice | Capability state |
|---|---|---|---:|---|---|
| Primary visual observer | `google/gemma-3-27b-it` | Vision, FP8, 27B | 110K | Public serverless | Model presence verified; image request and structured observation output not live-verified |
| NVIDIA constrained planner | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Text-to-text, FP8, 30B | 262K | Public serverless | Model presence verified; JSON schema/tool calling not live-verified |
| Manual visual fallback | `openbmb/MiniCPM-V-4_5` | Vision, FP16, 8B | 32K | Public serverless | Model presence verified; image request and observation quality not live-verified |
| Deferred quality experiment | `nvidia/Cosmos3-Super-Reasoner` | Vision, FP16, 33B | 256K | Dedicated only in the observed account UI | Not deployed; excluded from S3b/S3c default path |

The supplied `/v1/models` payload did not list `nvidia/Nemotron-Nano-V2-12b` or `nvidia/Cosmos3-Super-Reasoner`. They must not be configured as public serverless model IDs. The dedicated catalog does not authorize deployment or recurring GPU cost.

## ADR-S3A-001 — two-stage serverless generation

### Decision

TwinPulse will implement one explicit two-stage generation attempt:

1. **Observation stage — Gemma 3 27B**
   - Input: validated image bytes, MIME type, image hash, optional user description, and trusted measurement constraints.
   - Output: a bounded observation document containing visible entities, qualitative spatial relations, candidate dimensions with source/confidence, ambiguity, and assumptions.
   - It must not emit scene-tool calls, robot dynamics, controller values, shell/code, URLs, or external assets.
   - User statements and trusted measurement constraints remain separately attributed; they are not relabeled as visual evidence.
2. **Planning stage — NVIDIA Nemotron 3 Nano**
   - Input: immutable original prompt/constraints, the exact observation artifact, RobotProfile identity, and the versioned allowlisted scene-tool catalog/schema.
   - Output: the complete ordered `SceneToolPlan`, including geometry selection, placements, the predefined AGV placement, and the navigation task proposal.
   - Nemotron therefore performs the material planning and tool-selection decision. It is not a decorative summarizer.
3. **Local authority — TwinPulse**
   - The existing schema parser, measurement checks, tool allowlist, object/scene limits, route gate, compiler, revision ownership, and stale-result rejection remain authoritative.
   - Model output never executes Python, shell, arbitrary MCP tools, URLs, or assets.

### Protocol selection

- New adapter family: `nebius_chat_completions_pipeline`.
- Base URL: `https://api.tokenfactory.nebius.com/v1/`.
- Endpoint: `chat/completions`.
- One credential reference may be shared because both stages use the same approved provider profile and origin, but the secret remains in Windows Credential Manager.
- The current single-stage `openai_responses` adapter remains intact for its existing profile and regressions. It must not silently reinterpret a Nebius pipeline as one Responses request.
- S3b must use a fake transport before any live call. It will determine whether native JSON Schema/tool calling can be used per stage. If not, bounded JSON text plus strict local parsing and structured rejection is the only fallback; invalid output is never promoted.

### Fallback and cost policy

- `openbmb/MiniCPM-V-4_5` is a **manual observer fallback**, not an automatic retry. Selecting it creates a new generation attempt and must be visible in provenance.
- A normal live pipeline costs two provider requests: one observer request and one planner request.
- Timeout, refusal, truncation, 429, 5xx, invalid JSON, failed validation, cancellation, or a late response stops the attempt. Automatic provider retry count is zero.
- Cosmos dedicated deployment is deferred. If reconsidered, minimum replicas/scale-to-zero, region, routing key, time limit, deletion/stop procedure, and maximum budget require a separate approval.

## Required provenance

Each generated draft must bind and expose, without secrets or image data URIs:

- provider profile and API origin;
- observer and planner exact model IDs;
- image SHA-256 and byte count;
- observation schema version and SHA-256;
- tool-catalog/schema version;
- provider request IDs when available;
- per-stage status, latency, token/usage receipt when returned, and sanitized failure category;
- final plan hash, validation receipt, build revision, and source=`live_provider`.

## S3a acceptance

- [x] Account-visible public model IDs are distinguished from the broad catalog.
- [x] Public serverless and dedicated deployment are separated.
- [x] NVIDIA's material planning responsibility is recorded.
- [x] Protocol and adapter direction are selected without assuming Responses compatibility.
- [x] Unknown capability, pricing, license, and region fields remain explicitly unknown.
- [x] Live/paid inference count is zero and no endpoint was created.

## Next single step

Proceed to **S3b only**: add the versioned observation contract, composite pipeline settings/provenance, and a fake Chat Completions transport covering image encoding, observation→planner handoff, strict parsing, manual fallback, cancellation/late responses, refusal/truncation, 401/403/429/5xx, redirect rejection, timeout, and secret/data-URI redaction. Do not call Nebius and do not start Isaac in S3b.

## References

- Nebius model listing: <https://docs.tokenfactory.nebius.com/api-reference/models/list-models>
- Nebius vision example: <https://docs.tokenfactory.nebius.com/api-reference/examples/vision-capabilities>
- Nebius structured output: <https://docs.tokenfactory.nebius.com/ai-models-inference/json>
- Nebius function calling: <https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling>
