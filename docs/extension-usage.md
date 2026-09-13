# TwinPulse Extension usage

## Launch

From PowerShell:

```powershell
Set-Location C:\Users\<user>\Documents\TwinPulse
.\scripts\launch_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

Equivalent direct command:

```powershell
& "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64\isaac-sim.bat" --ext-folder "$PWD\extensions" --enable twinpulse.extension
```

The Extension opens a **TwinPulse Copilot** window. Restart Isaac Sim after updating the Extension source so the complete styled panel is rebuilt.

## Controls

- **Settings** stores Base URL, Model ID, and reasoning effort in persistent Kit settings. A newly entered API key is stored separately in Windows Credential Manager and is never written to the project.
- **Attach image** accepts one local PNG, JPG/JPEG, or WEBP file up to 10 MB and shows a preview. The image is the primary scene evidence and is read and transmitted only after **Generate with LLM** is clicked.
- The text box is optional when an image is attached. Use it for constraints such as AGV count, aisle intent, or omitted details; it no longer contains a hidden fixed-scene default.
- **Generate with LLM** sends image first and optional text constraints to a modern Responses-compatible endpoint. The LLM must return a strict plan made only from TwinPulse's allowlisted scene tools. TwinPulse validates the plan, expands templates such as multi-bay rack rows, and validates the resulting `SpecBundle` before USD mutation.
- The provider header reports `KEY SAVED` until a generation request succeeds, then `LLM CONNECTED`. During a request the Generate button changes to `Generating...`, is temporarily disabled, and shows progress or the exact error directly below the button.
- **Build Generated Scene** is disabled until a validated generated draft exists. It never substitutes the M1 sample fixture. The latest valid plan is persisted outside the project and restored after an Extension or Isaac Sim restart.
- **Focus Scene** switches the active viewport back to the TwinPulse overview camera.
- **Run / Resume** drives the two powered wheels through PhysX while two passive support casters stabilize the vetted robot profile. Route deviation or excessive roll/pitch causes a Reset-required safety stop.
- **Pause** stops wheel commands and pauses the timeline.
- **Reset** stops the timeline and restores the initial physics pose without deleting an active articulation.

TwinPulse owns only `/World/TwinPulse`. Generated replacements preserve the live PhysicsScene prim and replace only TwinPulse-owned environment, robot, presentation, and task content.

The preview and build status show the actual source, image count, tool count, expanded object count, request ID, and plan hash. The built `/World/TwinPulse` root is marked `generated_tool_plan`; API keys, prompts, image bytes, and image paths are not persisted in the draft record.

## Provider setup

The default is `https://api.openai.com/v1/`, model `gpt-5.6-luna`, reasoning `low`. Open **Settings**, enter the Base URL, Model ID, and API key, then select **Save Settings**. The next Extension startup reloads the non-secret values and the saved Windows credential automatically.

For an OpenAI development key, use a dedicated project and choose **Restricted** rather than **All**. Grant only the request/write capability needed for Responses if that endpoint appears in the permission editor. A Read Only key cannot create a response. Configure a small project budget/usage alert before the first E2E test.

Only endpoints compatible with `POST /responses`, image inputs, and strict JSON Schema output are supported by this adapter. A custom a.biz Base URL is not sufficient unless that protocol and those capabilities are actually compatible.

## Automated verification

```powershell
.\scripts\verify_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

The finite test uses MinimalRendering and CPU physics. It checks three run/pause/reset cycles, three Extension enable/disable cycles, Settings/warning construction, allowlisted tool-plan compilation, generated-scene replacement, rejection of an implicit sample fallback, two-drive/two-support structure, roll/pitch, vertical stability, cross-track error, and geometric collider overlap. Results are written below `artifacts/runs/<run-id>` so normal regression work does not require manually transcribing the viewport.

Interactive rendering is accepted from a single Full-app instance: Build must focus the overview camera and visibly show the warehouse, AGV, lighting, and green goal marker. The headless RTX capture experiment was removed because `--no-window` capture stalled on this below-minimum 8 GB host; it is not used as evidence of Extension failure.
