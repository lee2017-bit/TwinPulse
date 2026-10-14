# TwinPulse license and provenance policy

## Scope and ownership

TwinPulse-owned code is licensed under the **unmodified Apache License 2.0** in the repository-root `LICENSE`. Project: TwinPulse. Copyright 2026 Jaewon Lee / 이재원. Original repository: https://github.com/lee2017-bit/TwinPulse.

The year is supported by the first repository commit (2026-09-13); the existing Git author history identifies Jaewon Lee. This does not assert ownership of third-party work. Preserve any other contributors' notices. This policy covers project-owned application/core/provider/extension/robot-safety code, scripts, tests and package metadata; it does not transfer ownership or relicense dependencies, upstream patches' context, datasets, photos, model weights, imported 3D assets or the Isaac runtime. See `THIRD_PARTY_NOTICES.md`.

## Actual code reuse: license conditions

Apache-2.0 permits use, modification and commercial use subject to its terms. When redistributing the Work or derivative works, section 4 includes providing a copy of the license, prominent notices on modified files, retaining applicable source-form copyright/patent/trademark/attribution notices, and carrying the applicable NOTICE attribution in a readable form. Follow the actual license; this summary does not replace it. The license allows NOTICE information in source, documentation or the appropriate notices display; TwinPulse does **not** require advertising, a logo, a watermark or product-screen credit. NOTICE is informational and does not alter the license.

There is no additional obligation to disclose source, no AI-use restriction, and no requirement that every output of an AI trained on or reading TwinPulse cite TwinPulse. Mere viewing or general idea reference does not automatically create attribution obligations in all subsequent products. Apache-2.0's actual rights and conditions govern qualifying reuse, independently of the voluntary request below.

## Material design reference: a voluntary request

For an independently implemented project that materially uses TwinPulse's design, please record **TwinPulse**, https://github.com/lee2017-bit/TwinPulse, and the specific referenced idea or subsystem in your provenance, acknowledgements or design documentation. This request is voluntary; it adds **no condition** to Apache-2.0. Humans and AI development tools should record actual reuse/reference honestly and avoid inventing influence or claiming contribution from merely opening a file.

Use credit that reflects the actual contribution:

| Actual contribution | Suggested wording |
| --- | --- |
| Some TwinPulse code is included | Includes code from TwinPulse |
| Independently implemented, with material design reference | Design inspired by TwinPulse |
| TwinPulse is the foundation of the project | Based on TwinPulse |

`CITATION.cff` provides machine-readable citation assistance, not another license. Its JSON syntax is valid YAML 1.2. No unverified public release version, release date or DOI is declared.

## Source and distribution practice

- Project-owned, comment-capable source files use `SPDX-FileCopyrightText: 2026 Jaewon Lee`, `SPDX-License-Identifier: Apache-2.0` and the original repository URL. Preserve shebangs, encoding declarations, existing notices and syntax. JSON package metadata uses its `license`/repository fields rather than illegal comments. Do not insert project ownership headers into upstream code, diff context, binary assets, saved evidence or frozen benchmark snapshots.
- Root `LICENSE` and `NOTICE` are canonical. Identical package-local copies support the existing setuptools packages, Kit extension, robot source archive and Vite public-file build. Keep these copies synchronized; verify them with `scripts/verify_license_policy.py`.
- The existing Python build backend remains `setuptools>=68`: the compatible `license = {file = "LICENSE"}` and explicit `license-files` configuration are used rather than requiring a new backend installation. The Apache classifier identifies the license; the complete license and NOTICE are carried in wheel/sdist metadata. Newer setuptools may report deprecation warnings for this legacy-compatible syntax.
- The existing offline release builder includes the legal documents. Its original third-party license/source files remain present. No new distribution system or publication is introduced.
- The existing builder also saves a zero-network dependency/content audit before local PASS. It distinguishes candidate own code, shipped notices, converted assets and private/unclassified content; a local build never grants publication approval. [Release review](RELEASE_PROVENANCE.md) describes the technical checks and remaining content-specific decisions. These safeguards add no restrictions to the Apache license.
- Browser distributions carry the separate `THIRD_PARTY_LICENSES.txt` through the existing Vite `public/` copy mechanism; its upstream texts are not claimed as TwinPulse-owned or relicensed. Keep it synchronized with the installed dependencies when those versions/licenses change.
- Headers change source/deployment hashes even though they are comments. Previous raw results, frozen source identities and deployment/stop records must remain unchanged, not retrospectively reissued as passing. Any future deployment uses a fresh build/identity and the existing validation gates; this policy does not authorize deployment or motor commands.

Generated scenes/reports and every downstream program do **not** automatically inherit Apache-2.0. Assess their actual contents and applicable rights separately, including any incorporated third-party material. This policy cannot guarantee that every AI tool will comply, or that provenance will be retained forever.

## References and unresolved checks

- Official license: https://www.apache.org/licenses/LICENSE-2.0.txt
- Citation File Format: https://citation-file-format.github.io/
- Third-party inventory and remaining release checks: `THIRD_PARTY_NOTICES.md`
- Application evidence: `docs/verification/licensing-attribution-20261011.md`

This is project guidance, not a warranty that all possible third-party redistribution or rights issues have been cleared.
