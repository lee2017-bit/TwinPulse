# Local source checkpoint — 2026-10-23

This checkpoint publishes current source/tests and the creator-intent/RoomPlan
analysis to the existing **private main branch**. It is not a new installer
release, public launch or claim of physical readiness/accuracy qualification.

## Frozen installed baseline

- Release: `20261022T141522Z-633d315cfc23`
- Product source manifest: `633d315cfc23729d905f4908d42492cf6a734206d5fd52ec42fe8e11117d6084`
- 1674 installed files matched. The release was built from the then-dirty working
  tree based on `79da0d9422d026dce135d45df6dd431387361435`. A later source commit
  does not retroactively change that build's Git metadata or make it a clean
  rebuild. Subsequent documentation/analysis helpers are not shipped in it.
- Actual same-Electron/Isaac journeys: fresh39, cold14, lineage10, history5;
  separate original saved-geometry36-step journey. Every whole journey passed
  independently; it is not one joined continuation of a failed run.
- Ordinary Start/restart and native Home/Alt+F4 were separately checked. Whole
  controls used the explicit Test BrowserWindow, not a separate Chrome.
- Current evidence gate: `READY_FOR_SUPERVISED_POWERED_TEST`, issues0. Thirteen
  wrong/missing-evidence negatives were rejected. This is **software test-entry
  readiness**, not physical acceptance.

[Shared evidence summary](../verification/checkpoint-20261023/software-evidence.json)
records exact original hashes and limitations. Original raw UI logs, recordings,
sensor histories and installed binaries stay local; no placeholders replace
them. No old failure was rewritten.

## Product direction and accuracy

[Detailed analysis](../analysis/TWINPULSE_NARRATIVE_ROOMPLAN_ALIGNMENT_2026-10-23.md)
compares the latest source/evidence with both
[creator-supplied documents](../reference/creator-20261022/README.md).

Key distinction: individual CAD/USD assets belong in Library; measured room USD
needs an environment-import path preserving source hierarchy, units and geometry.
The supplied room USD has no authored metersPerUnit or physics. Current source
inspection rejects it for missing units. It has not been imported or driven in
TwinPulse. No new perception model or paid compute is required to analyze it.

**Photo-only quality remains unaccepted (historical complete-quality0/6).**
Text/SIM passes do not fix that cohort. Actual new Pi compilation/readback,
sensing, load/storage, braking/driving and world alignment remain NOT_RUN.
Fully offline LLM/on-prem deployment, clean-PC installation and industrial
operation-policy optimization are not claimed.

Private photos, the original room USD/derived floorplan, robot raw data,
credentials, model weights, Isaac/runtime/dependencies and build copies are not
Git content. Existing visibility and licenses/notices remain unchanged.
