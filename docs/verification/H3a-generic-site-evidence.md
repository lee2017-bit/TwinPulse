# H3a — generic site evidence boundary

- Date: 2026-09-26 KST. Scope: local contracts, fake transport and deterministic expansion only. After the user's reboot, TwinPulse/Isaac were not running; this step did not restart them because no runtime action was needed.
- Status: **H3a_CONTRACT_AND_FAKE_TRANSPORT_PASS / H3_OVERALL_PARTIAL**. No paid Nebius request, actual Isaac Build, interactive screenshot, TurtleBot command, commit or push.
- [One-page flow image](H3a-site-evidence-flow.png) ([editable SVG](H3a-site-evidence-flow.svg)).

## Changed behavior

- The v2 observer recognizes `robot_candidate`, `static_obstacle`, `free_space`, and `unknown` in addition to legacy warehouse categories. Its prompt explicitly avoids classifying a non-warehouse obstacle as a rack or claiming occluded space is free.
- The v2-only `create_box_obstacle` catalog operation compiles a bounded static box. The v1 scene tool catalog and v1 planner path are unchanged. Site catalog revision is `site-tools-2.1`; plan version remains 2.0.
- New provider plans must include one `call_evidence` record per call: basis (`visual`, `user`, `inferred`, `trusted_measurement`), observed entity IDs and a short note. Visual references are checked against the parsed observer output before local plan validation. A driven robot/mission cannot claim visual evidence alone as its authority; both require a user-evidence basis and remain review-required, not Run-ready.
- Each visually grounded static call becomes `SceneRevision.observation_bindings` from observation ID to every deterministically expanded scene-object ID. This includes multiple children of one rack or pallet call. `SiteDraftRecord` still keeps the input digest, plan and deterministic scene; old v2 records without `call_evidence` retain their original serialization and hash.

## Evidence and limitations

- Core 45/45; Provider 33/33; H2b-2 integration 5/5 PASS. The fake non-warehouse test-track response uses a floor, generic barrier, robot candidate and hidden corner. It accepts only floor + barrier calls; no driven robot is created. Invented visual observation IDs are rejected. Existing legacy v2 round trips still pass. Unsupported v2 trusted-measurement input now fails before any paid transport call.
- Full integration discovery ran 96 tests twice and failed once each on different pre-existing local HTTP tests with Windows `ConnectionAbortedError [WinError 10053]`; R4's failed test passed alone (6/6), while S1c's test reproduced alone (1 error in 5). This is **not** a full-suite PASS. The S1c connection abort needs a separate diagnosis; no unrelated HTTP code was changed here.
- The evidence note is a bounded model-generated explanation, **not** a measurement or proof of object identity. The original observer artifact is not persisted in the v2 draft, so this step establishes a traceable ID/basis chain but not a full auditor-readable observation archive. `trusted_measurement` is represented in the evidence vocabulary but v2 requests carrying measurement constraints are currently rejected before provider invocation. The explicit user basis is still a planner claim rather than a machine-verifiable user approval. Those gates must be hardened before real robot selection or autonomous motion.
- A box is an approximate primitive, not photo-accurate reconstruction. No cylinder primitive, real non-warehouse photo/drawing fidelity gate, actual Isaac check of the new primitive, or browser evidence inspector was performed. H3b's photo-to-test-track relation and H3c's TurtleBot profile remain separate next stages.
