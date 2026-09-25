# S1b capture completion contract verification

- Recorded: 2026-09-23 06:21 KST
- Status: **PASS — pure failure corpus 8/8 and actual Isaac gate 3/3**
- Canonical root: `C:\Users\jaewo\Documents\TwinPulse`
- HEAD: `500f19992350d5b96877a9001d429656dfc7f748`
- Live/paid provider requests: **0**
- Installation / physical command / commit / push: **NOT RUN**

## Contract implemented

The Isaac capture task returning and the PNG becoming complete are now separate events. One `CaptureAttempt` records:

- request time, frame, stage epoch, applied revision, camera, timeout, and settle interval;
- capture-task return time and outcome;
- first file observation, stable size, successful decode, and completion timestamps;
- observed byte count, decode attempts, decoder error, and decoded image evidence.

The Kit update loop polls the state machine without blocking. Each attempt has a 15-second deadline and 0.25-second file-settle interval. A failed attempt may be retried once only; a stage/revision change is terminal and cannot be retried. Attempt output is isolated as `isaac-viewport.attempt-N.png`, and only a fully decoded PASS is atomically promoted to the run's final `isaac-viewport.png`. A timed-out or failed attempt cannot be replaced by another run's file.

Shutdown waits only for a capture that is already pending and uses the same finite 15-second boundary. Existing failure causes are retained. Engine and top-level E2E JSON results use atomic replacement.

## Pure RED → GREEN evidence

Initial RED command:

```powershell
python -m unittest discover -s tests\integration -p 'test_s1b_capture_contract.py' -v
```

Before the helper existed, the test module failed to import with `ModuleNotFoundError: twinpulse_capture_contract` (exit `1`). After implementation, 8/8 passed in 0.014 seconds:

- task returns before a late file appears;
- partial-file decoder error followed by complete bytes;
- empty-file finite timeout;
- black/constant frame rejection;
- missing viewport;
- capture task exception;
- never-completing task plus one-retry maximum;
- stage/applied-revision change with retry forbidden.

The preserved S1a manager suite also remained 10/10 PASS. Python compilation and both script `--help` import/argument smokes passed.

## Actual Isaac gate

Each run used a unique artifact directory and executed the deterministic product path with no provider request:

```powershell
python scripts\verify_app_e2e.py --isaac-root C:\isaacsim --artifact-dir <unique-run>\r6-app --timeout-s 180
```

| Run | Browser | Engine/capture | Attempts | Capture | Dynamic range | Movement | Prims |
|---|---|---|---:|---|---:|---:|---:|
| `20260923-s1b-01` | PASS | PASS | 1 | 960×640, 120,342 bytes, SHA-256 `BC6F8E45...84FFB` | 215 | 0.337496 m | 32 |
| `20260923-s1b-02` | PASS | PASS | 1 | 960×640, 485,287 bytes, SHA-256 `3BCF45DC...FEDD3` | 216 | 0.374946 m | 32 |
| `20260923-s1b-03` | PASS | PASS | 1 | 960×640, 484,330 bytes, SHA-256 `97E0F4DD...04711` | 216 | 0.362503 m | 32 |

All three runs:

- applied revision `67c662fa927c9b818ace344fc1ac7975f7049850254dec09767eb121a5eb9806`;
- observed `idle`, `ready`, `running`, and `paused`;
- completed browser stages `authenticated_ready`, `draft_reviewed_acknowledged`, `actual_revision_applied`, `run_pause`, `reset_focus`, and responsive/zoom/keyboard checks;
- recorded every required capture timestamp and matched capture request identity to the final engine stage/revision;
- exited without a remaining launcher lock or Isaac/Kit process;
- left no atomic-write temporary files in their artifact directories.

Run 1 directly demonstrates why the repair is needed: `first_file_seen_at` preceded `task_returned_at`, while stable-size and decode completion occurred later. The new contract waited for both task completion and stable successful decode instead of treating either event alone as success.

No actual run needed its one allowed retry. Retry behavior was exercised in the pure finite tests rather than induced artificially in Isaac.

## Source hashes

| SHA-256 | Path |
|---|---|
| `E307E0E7048CFE6E1667A84D61718FE861C37D1D212988009AECDDECAB172A57` | `scripts/twinpulse_capture_contract.py` |
| `2D3500E26A675A51B03C54721B38B1C5E62F386CEABDB84FC36546DFD50EA8C2` | `scripts/twinpulse_engine_host.py` |
| `DF40EE309F66C2E9FFD6F40574B9B6D2D3D04ED81DA2627B9F548E9B8E7BD9C1` | `scripts/verify_app_e2e.py` |
| `D11FA7AB4A2092EF906A154A15D0AAC4177A7DD3DC0D82EB9EE4DE61951BC35F` | `tests/integration/test_s1b_capture_contract.py` |

## Remaining boundary

S1b closes the capture-timing defect and its required actual three-run gate. It does **not** close all R6 acceptance: the three stored M2-C managed-path replays, fresh-clone/company-PC reproduction, and approved live-provider App smoke remain separate. Next is S1c authentication lifetime and safe reopen.
