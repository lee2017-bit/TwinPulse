# TwinPulse Library workspace API contract

Implementation contract for the authorized core/Library task. Python owns state, workers, artifacts, and scene transactions. React owns input routing and visible actions. Existing scene/image APIs retain their current shape.

## Source wall-relative long-axis evidence (candidate16)

Fresh Site2.2 photo observation requests raw1.5, exact-version pinned before cache or stage acceptance. Each entity has `footprint_alignment={reference_wall_id,relation,confidence,visual_basis}`. The relation compares the horizontal footprint long axis to the direction **along** a separately observed wall, not its normal, object height, screen horizontal or calibrated world axis. Known relations require an existing typed wall reference and positive finite confidence. Square/round/occluded axes or missing wall/view correspondence remain unknown; unknown uses null reference/zero confidence and a short limitation. This does not authorize automatic yaw, extra repair scope or a new geometry error.

Raw1.5 expands into host-only1.6 with source SHA unchanged. A grouped observation's alignment is retained in `unresolved_alignments`; derived individuals receive unknown/null/zero rather than copied orientation. Legacy raw1.0/1.1/1.2/1.4 and host1.3 field shapes and serialization remain unchanged. Raw1.6 is rejected. Planner/current-render critic see the observation; compact repair retains referenced wall context read-only alongside actual compiled axes. Existing geometry, frame checks, repair limits and source uncertainty remain. Actual model output, evidence propagation, compiled direction and visual quality require separate acceptance; schema presence alone is not success.

Candidate18 congruence correction: raw1.5 uses disjoint full entity branches. Only role object/unknown may report a known footprint axis; structure/opening/free_space/robot use unknown/null/0. This is the same host rule, not a relaxed metadata role. Actual16 had spent one observer repair on a free-space known-axis value that the previous wire/prompt appeared to allow. Ingress/export entity nested values now deep-copy so changing the raw request, exported observation or compact repair context cannot mutate the verified artifact/SHA.67 focused supplementary tests cover these boundaries. Candidate16's desk axis was delivered intact but misinterpreted by both designer and critic; the role/copy fixes do not claim to solve that model-quality failure.

## Files

Final-candidate ownership: the UI helper has completed its handoff. The primary now owns integration and all listed files; no simultaneous writers remain. The assignment below records the initial split, not permission for concurrent editing.

Primary owns Python, API server, schemas, Isaac, packaging, integration and report drivers. UI child owns `api.ts`, `ModelLibrary.tsx`, `model-library-types.ts`, `model-library.css`, new `LibraryWorkspace.tsx`/tests/types and the necessary `ChatWorkspace.tsx`/tests/style integration. SimulationRunCard changes are frozen for the first S1 package. Primary does not edit these UI files while assigned.

## HTTP

GET `/v1/product/library-workspace` returns Workspace. POST to the same authenticated context-bound endpoint receives `{action, ...fields}` and returns Workspace, optionally with `placement_preview`. No request directly runs arbitrary shell or LLM code.

Workspace:

```
schema_version: 'library-workspace-1.0'
project_id: string
current_scene_revision: string | null
assets: Asset[]
jobs: Job[]
extensions: Extension[]
placement_preview?: existing SceneEditPreview | null
message?: string | null
```

Asset:

```
asset_id: string
version: string (immutable SHA)
title: string
kind: 'recipe' | 'usd' | 'cad' | 'brep'
source_name: string
source_sha256: string
dimensions_m: [number, number, number]
units: 'm'
up_axis: 'Z'
origin: string
license: string
visual_status: string
physics_status: string
reusable: boolean
recipe_model_id?: string | null
preview_parts?: existing LibraryModel.preview_parts
```

Job:

```
job_id: string
request_id: string (stable idempotency identity, including after unknown delivery)
project_id: string
purpose: 'asset_create' | 'asset_import' | 'analysis'
status: 'queued' | 'running' | 'ready' | 'registered' | 'failed' | 'cancelled' | 'unknown'
phase: string
message: string
tool_id: string
execution_id: string
input_sha256: string
created_at: string
can_cancel: boolean
can_register: boolean
error: string | null
asset_id?: string | null
asset_version?: string | null
result?: object | null (typed tables/text, no executable HTML)
```

Extension:

```
extension_id: string
title: string
transport: 'builtin' | 'cli' | 'mcp'
available: boolean
enabled: boolean
reason: string | null
version: string | null
executable_configurable: boolean
tools: {tool_id:string, title:string, input_schema:object, output_kind:string}[]
```

## Actions

- `create_recipe`: `request_id`, `prompt`, optional `reference` attachment. Starts the configured Nemotron recipe job; never creates a room or sends a Run. A reference image has role `asset_reference`, uses normal image validation and the existing authorized route.
- `import_asset`: `request_id`, `attachment`, `source`, `license`. Attachment is `{name,media_type,bytes_base64,role:'asset_source'}`. CAD is handled only here, never passed to scene photo APIs. USD import and optional CAD conversion are distinct available capabilities.
- `register_job`: `job_id`, `request_id`. Registers only a ready validated result, retaining immutable source and result hashes. No stage mutation.
- `cancel_job`: `job_id`. Cancels only an owned current-project job; late results remain unregistered.
- `preview_placement`: `asset_id`, `version`, `expected_scene_revision`, `instance_id`, `position_m:[x,y,z]`, `yaw_deg`, `request_id`. Returns the existing scene edit preview plus `preview_id`. The project-scoped immutable record preserves the exact original operation, recipe/mesh snapshots, source/input binding and digest. The browser must not reserialize the operation for Apply (Python/JavaScript number spellings differ). POST `/v1/product/scene-edit/apply` with exactly `{schema_version:'scene-edit-apply-2.0',library_placement_id:preview_id,preview_digest}` resolves the pinned operation and delegates to the existing transaction; no override fields or legacy fallback. Same-ID recovery preserves the operation and record, including after UNKNOWN. The UI confirms that exact operation/result revision, ACK, durable save and current frame. Placement is separate from registration. Local preview history is bounded (128 records / 256 MiB, 16 MiB each), with no automatic deletion of active/unknown records; exhaustion is explicit.
- `configure_extension`: `extension_id`, `executable`, `enabled`. Only reviewed adapters, not arbitrary user-entered shell strings. Does not install software or invoke a converter automatically.
- `check_extension`: `extension_id`. Explicit bounded capability/version probe; no LLM, Cloud or robot.
- `run_tool`: `request_id`, `tool_id`, `inputs`, optional `attachment` with role `tool_input`. Executes a registered tool with structured inputs through the same Job contract. Local CSV analysis and MCP transport use actual calculation, never a canned result.

Attachment controls must preserve the unsent scene prompt and image when opening/cancelling a Library import. A CAD attachment from the scene composer routes to Library import with the original filename; Send does not submit CAD as a scene image. Library images are asset references; scene photos remain environment references. Library-only work never replaces a saved scene.

## Existing mesh instances and natural-language feedback

The host binds feedback to the complete current plan and context SHA. The model
receives a compact read-only context: immutable asset version, source/inspection
identity, dimensions, transform and conservative collider remain, while repeated
mesh coordinates/triangles and recipe expression trees are omitted. Compact text
is not an executable asset snapshot. Before dispatch the host recomputes it from
the retained full context and rejects a mismatch.

For an existing `place_library_asset` instance, feedback may update only its
world position and yaw through the context-bound change/restore grammar. The
exact asset version is required; the host reinserts and validates the unchanged
full snapshot. A substituted snapshot/version, arbitrary scale, new asset or
unrelated operation is rejected. New mesh placement still uses explicit Library
preview/Apply. Apply/ACK/durable save/current frame/Undo use the same transaction
as other edits, and do not rewrite Library originals or other projects.

## Photo repair scheduling revision

`observed-quality-repair-1.6` selects the next existing repair slot from a current
candidate/plan-bound diagnosis. Hard rendered layout, observed-region and
relative-order contradictions select semantic pose repair before capability
replacement. Otherwise an eligible untried bounded layout objective may use
that slot; numerical support problems still remain in the full diagnosis and
can select capability later. No geometry, scope, stall, request or repair limit
is relaxed. An explored pose still requires compile and a fresh critic.

Older quality-history checkpoints retain their original revision and budget.
They are not silently replayed with a new repair strategy or reset allowance;
an incompatible continuation is explicit. Existing saved scenes remain readable.

`current-render-review-1.2` also records a model-specific transport policy:
only the exact Nebius `deepseek-ai/DeepSeek-V4.1-Flash` finite render classifier
requests `reasoning_effort=none`. The actual prior critic consumed 40,000 hidden
reasoning tokens with no final JSON. Initial observation, other models and the
planner are unchanged. The full materialized-ID table, layout/support/appearance,
confidence threshold and deterministic geometry checks are unchanged. Hosted
behavior and visual quality require separate actual-run qualification; successful
JSON is not source fidelity. Old 1.0/1.1 saved refinement records remain readable.

Official references: [Nebius request field](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion),
[DeepSeek mode semantics](https://api-docs.deepseek.com/guides/thinking_mode/).

## Versioned support observations

Candidate19 final-abstention recovery: a host-validated typed quality abstention with exact `SEMANTIC_PATCH_NO_CHANGE`, on the actual final allowed repair, is classified before the first terminal latch as `QUALITY_REPAIR_LIMIT_REACHED`. Original failed/no-change patch evidence and abstention remain; no patch is applied and no progress is claimed. Only the existing current-reviewed support-subset retention path can accept an editable partial: current capture/candidate/plan/frame, fresh full compile, unchanged support witness/lineage and settled budget are mandatory. Non-final abstention, unrelated schema errors, stale frames and failed floor projections do not gain this fallback. No terminal is cleared and no extra call or relaxed geometry is introduced.76 focused supplementary tests passed; actual occurrence of this branch remains separately qualified in the installed-run report.

 New detailed photo observation requests now use raw1.5 as described above. The raw1.4 addition introduced `on` and
`supported_by` name a supported subject and its directly observed support object.
Raw1.0/1.1/1.2 readers retain their original relation set. Raw1.3 is still rejected:
it is the existing host-only expanded inventory. Even a small1.4 observation is
expanded into host1.3 so new relations are not silently downcast to1.1.

Fresh responses/cache entries must match the one requested raw schema version.
Original source evidence and its SHA remain separate from derived instances.
Group relations remain unresolved rather than being copied onto every expanded
instance. Unknown counts and unverified individual support remain explicit.

An explicit visible support relation to a typed floor may satisfy the existing
unknown-floor recipe eligibility check. A description, object name, `near`, or
support by furniture cannot grant that permission. This adds no measured pose,
automatic reparenting, physical support validation, geometry relaxation or
permission to shrink a conservative collider. Existing on/supported_by relations
that are not metrically testable stay unverified. Actual model and photo quality
qualification are separate from the supplementary contract checks.

## UI

### Partial retention revalidation (source22)

Partial saving still requires the exact current capture, freshly checked subset,
same compiled plan and same support witness. Only comparison copies discard
`geometry_checks` when both reports use the exact
`photo-support-bounded-search-1.0 / BOUNDED_SEARCH_FAILED /
TIME_BUDGET_EXHAUSTED` contract and the probe count is a non-bool integer within
its unchanged maximum. Elapsed duration is existing runtime telemetry. Every
other field, including domains, search phase/outcome/limits, risk, IDs,
parent/part, source and geometry remains exact. Other termination causes keep
exact counts. Original witness and both revalidation search statistics are
persisted; this does not prove global infeasibility or improve photo quality.

The optional public `retention_revalidation` summary contains only
`validation: passed|failed`, `gate: exact_plan_and_support_witness`, boolean
`same_plan`, boolean `same_witness`, and `physical_authority: false`. A passed
summary must have both comparisons true; inconsistent or untyped payloads are
not exported. Full hashes/search records remain local diagnostic evidence, not
raw model prose in the UI. The UI distinguishes this partial-retention check
from complete generation, photo fidelity, live-frame readiness and simulation.

The original21 failure and all UNKNOWN charges remain unchanged. Supplementary
tests and pure recompilation of immutable real evidence are not installed
user-flow acceptance; a separate explicit UI resume is required.

### Assembly geometry evidence1.0 / current render review1.3

Provider discovery/parameter context and current-plan critic/repair share a bounded host descriptor compiled from the exact immutable recipe, actual parameters, current yaw/centre and outer plan SHA. It aggregates all compiler-allowed expanded128 parts, reports boundary-face coverage/world normals/owner IDs, actual major vertical panels and supports, parameter domains and explicit output truncation. It is read-only geometry, not source measurements, semantic-front proof, a support grant or edit scope. Least-covered sides are opening candidates only. The descriptor cannot rotate geometry, enlarge parameter ranges or place floor-only recipes on furniture. A pose cannot remedy an incompatible recipe domain; an eligible immutable replacement is distinct.

Current render response version is1.3. Core/App readers retain1.0–1.2 saved reviews and add exactly1.3. Old render-history continuations remain rejected by the existing revision check; changed definition-body hashes remain rejected. Saved-scene reading/editing is not a promise of old-generation execution compatibility. Source observations/recipe IDs/scene hashes/geometry/scope/confidence/navigation checks are unchanged. Actual-solid floor admission and typed mounted assemblies are separate unimplemented contracts, not enabled by this metadata change.

The first supplementary run exposed missing1.3 reader entries and one wrong fixture ID; corrected without changing validity criteria. Independent Astra found a64-vs128 expanded-part mismatch, corrected by using core MAX_PARTS. Focused54 supplementary checks pass; old13 assemblies were described0HTTP/read-only. Fresh installed/model qualification is still required.

Keep the existing Library catalog tab intact. Add create/import/my assets/connections using shared input and progress cards. Missing optional tools explain availability without blocking built-in creation. Basic forms follow tool input schemas. Source/asset/instance and visual/physics readiness are displayed distinctly. Never call a geometric check physical certification.

All fetches use the existing API request/context handling. Poll only the workspace while a job is active; stop on close/context change. Do not log credentials or full uploaded data. Names are text, result tables use native React rendering. Imported asset selection and placement must preserve asset version and target revision.
