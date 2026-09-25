# S0 audit baseline

- Recorded: 2026-09-22 11:34 KST
- S0 status: **PASS — audit baseline captured; three intended RED regressions reproduced**
- Canonical root: `C:\Users\jaewo\Documents\TwinPulse`
- HEAD: `500f19992350d5b96877a9001d429656dfc7f748`
- Product source changed by S0: **No**
- Paid request / Isaac launch / installation / physical command / push: **NOT RUN**

S0 is an audit gate, not a claim that the three defects are fixed. The new tests encode the desired behavior and are intentionally RED at this checkpoint. Their repairs belong to S1a, S2a, and S2b.

## Environment snapshot

| Component | Observed value |
|---|---|
| General Python | `3.12.10` at `C:\Users\jaewo\AppData\Local\Programs\Python\Python312\python.exe` |
| Node.js | `v24.19.0` at the existing Codex bundled runtime |
| Isaac Sim | `6.0.1-rc.7+release.42383.32955d8d.gl` from `C:\isaacsim\VERSION` |

## Preserved R6 evidence

The two most recent relevant results are both retained; the later failure does not overwrite the earlier success.

| Run | Stored result | Direct observations |
|---|---|---|
| `20260922-100347` | `PASS` | browser PASS, engine PASS, 32 prims, exact applied revision `67c662fa...9806`, observed `idle/paused/ready/running`, movement `0.3291361054787657 m`, capture PASS at 960×640 and 484,381 bytes |
| `20260922-102341` | `FAIL` | browser PASS; engine acceptance FAIL because capture evidence was incomplete at evaluation time; 32 prims, same applied revision, same four states, movement `0.26276206774373395 m` |

The later run subsequently contains `r6-app/runtime/isaac-viewport.png`: 960×640, 486,730 bytes, SHA-256 `E00C4BC1E981AD184F97722023243960FF39942463643407CE7747584024D774`. This is evidence of a late capture completion and is **not** used to rewrite the stored FAIL result.

The earlier run has no top-level `manifest.json`; its authoritative stored record is `r6-app/result.json`. The later run's top-level manifest explicitly reports `FAIL` with `R6 managed-launcher browser/actual-Isaac acceptance failed`.

## Reproduction command and actual output

The tests use a dedicated temporary root and no real process, current runtime state directory, provider, browser, or Isaac instance.

```powershell
$env:TWINPULSE_TEST_TMP='C:\Users\jaewo\Documents\Codex\2026-09-12\dl\work\s0-test-tmp'
python -m unittest discover -s tests\integration -p 'test_s0_audit_regressions.py' -v
```

Actual result: exit code `1`, `Ran 3 tests in 0.011s`, `FAILED (failures=3)`.

| Defect | Expected boundary | Reproduced current behavior | S0 result | Repair owner |
|---|---|---|---|---|
| A-01 | Different immutable inputs must not silently resolve to the same generated draft | Two different prompt revisions returned the identical `fixed_warehouse_v1` draft and revision | RED reproduced | S2b |
| A-02 | A manager that did not acquire the launcher lock must not mutate shared owner runtime files | After `launcher_already_running`, `stop()` created `engine-stop.request`; owner lock remained | RED reproduced | S1a |
| A-04 | An uploaded image must have decodable pixel content | A checksum-valid 45-byte PNG containing IHDR+IEND but no IDAT was accepted as 1×1 PNG | RED reproduced | S2a |

These are product defects rather than environment failures. The tests ran completely and failed at the intended assertions.

## Dirty source manifest at the S0 test boundary

The workspace was already dirty before S0. S0 preserved every prior change and added only the audit regression plus this summary/checkpoint. SHA-256 values below were captured after adding the regression test and before writing the two self-referential evidence documents. No secret-bearing runtime files are included.

| State | SHA-256 | Path |
|---|---|---|
| M | `26C076639C0ECBFE5018AE3550FE9A25A5229BCF093828428A32D7161B263C36` | `README.md` |
| M | `8C5DB825D3CC35E2350F2EB71B0FFB99A1B7FD6AFE01AF4BBA79FC1D13A99304` | `apps/twinpulse-web/src/App.test.tsx` |
| M | `FEFB12DA396506A281DC24054BC711A96899DF36C77DF776C24541CC7B6B193A` | `apps/twinpulse-web/src/App.tsx` |
| M | `A173F63BFFC5B1A7A066FFF00F88F62A802227BEF2CB6B7FA7FCC63659C0D0AB` | `apps/twinpulse-web/src/api.ts` |
| M | `98F8168F8E315AB045E9BBEF4754DCBDC97F8F4F2475A62559E5969F2A9330BA` | `apps/twinpulse-web/src/styles.css` |
| M | `0A0F3063CBE26CF3F49DA49CFEBAB588F9834F2388E4011FA500F7230EE8AFB1` | `apps/twinpulse-web/src/types.ts` |
| M | `988CD09C9E90DBDE88622D08EEFEB08CDE9DB2CC38D529FD7AF49EBB44FCD7B0` | `docs/COMPANY_PC_INSTALL.md` |
| M | `AD604E41D51EFFBCAE71D5269822A54F85FB5E4F62D574FB9651001BCE4F7157` | `docs/planning/TWINPULSE_APP_MIGRATION_PLAYBOOK.md` |
| M | `9664EA9E64C2A19C4FC975CA31BB6277C9671A5E2044A4422C99D8BA7420156C` | `docs/planning/TWINPULSE_BASELINE.md` |
| M | `C6126C44A44D5F97A28B9E42D670562A7D8A269C0E82F790AE8CF73E3D0A33F2` | `docs/planning/TWINPULSE_PROJECT_MEMORY.md` |
| M | `C7DFAB04EF81C34495BEDA34B64453CD745E69FDB432AE6FBEA13CC4B4E8D7D2` | `docs/progress.md` |
| M | `0D4FCB7E7FE115F116491EC6E35F575FFCCA7EE5E645E3C5712E734449FAFB6D` | `packages/twinpulse_app/src/twinpulse_app/__init__.py` |
| M | `7DD5F2DEB2813A87A421D44C58F391749D1F91FAA67A02B3E68BC831010FAD52` | `packages/twinpulse_app/src/twinpulse_app/api.py` |
| M | `14C634F0085AD722D46B72C65669EE2043D3CCEB35D4861C3A9E959E4278FBFA` | `packages/twinpulse_app/src/twinpulse_app/command_broker.py` |
| M | `C7E705E8EDAF6B734AD36E52C2DA598B5DD351C38B86A882EFEFCF2D0146215D` | `packages/twinpulse_app/src/twinpulse_app/credentials.py` |
| M | `B51D3153692C960CE5C7ED6FEAD35CBD7686BECA04187E4BEF8243F8EC54CC41` | `scripts/twinpulse_backend.py` |
| M | `2C395BC704FCC3AA50B521E7A9566613C36E1DA8C8B85DFEE34744CF478070C5` | `scripts/verify_twinpulse.ps1` |
| M | `87AFED0BAB1934D9BA5E762318813781F11EA44BB28E05D7254A769198E92C34` | `tests/integration/test_r5_product_api.py` |
| ?? | `CD3155B76FE9BDAD61A8CDCD8D2DF3938D3FE98A77C0B09DD9AAC4FD832EDE96` | `docs/planning/TWINPULSE_ASTRA_REVIEW_2026-09-22.md` |
| ?? | `E0DB556735ACCBDC391F02E0FAF66DA88433609E8652FB31D703D15FE1F451A8` | `docs/planning/TWINPULSE_SOL_EXECUTION_PLAN_2026-09-22.md` |
| ?? | `0E9DC8CBBFADDCFF7236B4625A6984AC93BEDE3F0001C5D4A522D36DFBEEE28D` | `docs/planning/TWINPULSE_TURTLEBOT3_EXPERIMENT_PLAN.md` |
| ?? | `EC3C0C649CF53EDDA85187842072873CBA279C3C96A46A055B3DDB2920D91837` | `docs/verification/R6-automatic-app-e2e.md` |
| ?? | `9CE2B7F62626E67DF8473DD20EB11F43BCD229C7F37CFE5A3518909A30E38852` | `packages/twinpulse_app/src/twinpulse_app/process_manager.py` |
| ?? | `79C07080F5CD925196D3494EE3CBD6F38F0596AF4673DD12716238314019ADEE` | `scripts/launch_twinpulse_app.ps1` |
| ?? | `14DFA59AE839E481C0754F06D25438D10036D572D190B28CA50B2C2599A9F982` | `scripts/twinpulse_engine_host.py` |
| ?? | `CB3A97E01269AADD4BC215DAE6CED297800D245A85833563492776DDB9294F29` | `scripts/twinpulse_launcher.py` |
| ?? | `1FA109036B02301F6620DDF47A278772F298A034872AC3C61BDEB1B81AA2F913` | `scripts/verify_app_e2e.py` |
| ?? | `ACB1A92A4C7B0062E295A8E11669DF3BC8450C35E169E0ED20BD6D0BB48F29AF` | `tests/integration/test_r6_process_manager.py` |
| ?? | `078051CC5EBF9502F46EEECF7D8571B3FC34561FAE26175B1470472AEABAE849` | `tests/integration/test_s0_audit_regressions.py` |

The R6 implementation is not fully represented by HEAD: its process manager, launcher/engine-host/verifier scripts, process-manager test, and verification document are untracked. They must not be lost or assumed published.

## NOT RUN in S0

- full Python/Core/Provider/R1–R6 regression suite
- React unit tests and production build
- any new managed-launcher or Isaac run
- three stored M2-C managed-path replays
- fresh-clone/company-PC verification
- live provider or any paid request
- dependency installation
- Git commit or push
- TurtleBot/ROS/physical command

## S0 file changes

- `tests/integration/test_s0_audit_regressions.py` — three desired-behavior RED regressions
- `docs/verification/S0-audit-baseline.md` — this evidence summary
- `docs/planning/TWINPULSE_EXECUTION_CHECKPOINT.md` — resumable checkpoint

## Next gate

Proceed to **S1a: ownership-safe shutdown**. First extend the A-02 test so the pre-existing ready/status bytes are also proven unchanged and repeated `stop()` is idempotent. Then minimally change manager/launcher ownership semantics and turn only the S1a tests green. Do not launch Isaac in S1a unless separately approved.
