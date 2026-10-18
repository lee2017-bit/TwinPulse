# H1a-2 English setup and backend wording — local verification

- Date: 2026-09-25 KST.
- Source boundary: local `main` HEAD `5c42899a95a0bf2422550bd17df7556a92ab3232` plus pre-existing uncommitted work, including offline-release scripts and company-install guide. No reset, commit, or push.
- Result: **H1a-2 COPY_AND_DOCS_UNIT_PASS / INSTALLER_NOT_RUN / ACTUAL_ISAAC_NOT_RUN**. This is not a clean-release or company-workstation acceptance.

## Changes in scope

- Changed three empty-input backend/user-facing messages from warehouse-specific to site-neutral wording. The existing `input_empty` API code and HTTP 400 behavior remain unchanged; one R5 API regression now asserts both.
- Reviewed the launcher, online/offline installer, installed start script, `.cmd` entrypoints, and backend for Korean visible strings. Their existing user-visible installer messages are already English; machine-readable `TWINPULSE_*` markers, flags, process/credential/network/path behavior were left unchanged.
- Replaced the README's warehouse-only introduction with an accurate **Today / planned** boundary and linked a new English [Quick Start](../QUICKSTART.md). The Quick Start explains online source install, prebuilt offline transfer to the separate RTX workstation, the actual web workflow, costs/credentials, limits, and failure recovery. It explicitly says the offline release is not yet published and company Isaac/connectivity are unverified.
- Updated the longer Korean company guide's *quoted UI button names* to match the now-English web app; kept the detailed Korean guide for Korean readers. Included the English Quick Start in the offline release's documentation file list only. No installer behavior was changed or exercised.

## Verification

| Check | Result |
|---|---|
| `python -m unittest discover -s tests\integration -p test_r3_application.py -v` | PASS, 9/9 after sandbox tempfile-permission workaround |
| `python -m unittest discover -s tests\integration -p test_r5_product_api.py -v` | PASS, 10/10 including unchanged `input_empty` code and English message |
| `python -m unittest discover -s tests\integration -p test_s2b_generation_ownership.py -v` | PASS, 7/7 |
| PowerShell parser on online/offline install, installed start, app launch, offline release-builder scripts | PASS |
| Korean-character scan of launcher/installer/`.cmd`/app backend files | No matches; scan exit 1 means no match |
| `git diff --check` for touched tracked code/docs | PASS |

The first R3/R5 test attempt could not write to the default Windows temp folder in the sandbox. R5 then passed using a repository-local test temp path. R3's `TemporaryDirectory` cleanup still failed under sandbox permissions; the same existing suite passed 9/9 with an approved elevated test process. This was a test-environment permission issue, not a product assertion failure. No test was skipped or weakened.

## Not claimed

- No installer or release build/packaging execution, dependency reinstall, GitHub upload, actual Isaac scene, provider request, or physical command. Existing H1a-1 browser screenshots are not a new H1a-2 installer validation.
- Backend diagnostics/receipts and model output may still contain technical or source-language text. H1b will handle state truthfulness; H2/H3 will handle protocol/provider semantics and broader site input. The older warehouse fixtures and historical evidence remain unchanged.
- Next separately authorized work is **H1b only**. Do not proceed to H2 or real robot work automatically.
