# Third-party components and provenance

TwinPulse's Apache-2.0 declaration covers its own code only. It does not replace any third-party license, copyright, attribution or service terms. The repeatable offline inventory in `scripts/audit_release_provenance.py` separates shipped dependencies from installed development tools and unresolved assets. This is not blanket legal clearance or a standards-conformant SBOM. Keep original notices with redistributed components. See `docs/RELEASE_PROVENANCE.md`.

## ROBOTIS TurtleBot3 source and nominal assets

The SIM-alpha EXE uses the separately prepared, hash-pinned copy in `assets/simulation/turtlebot3_burger`. Its unchanged upstream `ROBOTIS-LICENSE` and `SOURCE.json` record source commit, URDF/mesh lineage, original/public USD hashes and prominent TwinPulse metadata-only modifications. It does not require the private/ignored local preparation folders below. Geometry/physics were compared with the preserved originals; no Isaac runtime, importer binary, model weights or NVIDIA asset packs are shipped. Historical offline assets retain their original records.

- Origin: https://github.com/ROBOTIS-GIT/turtlebot3
- Locally pinned commit: `90a68bd2e3c61c12966779da89d8eeaec82730e9`.
- Upstream Apache-2.0 license is preserved unchanged at `artifacts/robot-models/turtlebot3-source/LICENSE`. The nominal URDF/mesh hashes and origin remain in `artifacts/robot-models/burger-prepared/source.json`.
- The existing offline release copies the upstream LICENSE, origin metadata, nominal URDF/meshes and nine locally pinned Burger USD files. Upstream assets and converted derivatives are **not** claimed as Jaewon Lee's original assets. Preserve upstream copyright/notices in the source and any required notices in derivatives.
- `packages/twinpulse_robot_safety/turtlebot3-90a68bd.patch` contains upstream source context; it is excluded from the TwinPulse-ownership header rewrite. The TwinPulse package LICENSE/NOTICE do not override the license of that context. The robot README already requires retention of upstream headers. When distributing a patched driver, retain the upstream notices and prominently identify actual modifications in that derivative; a local source archive is not authorization to deploy it.
- Read-only inspection identifies the converted layers' `URDF USD Converter v0.1.3` creator and the installed `urdf-usd-converter` 0.1.3 Apache-2.0 metadata/original license. This establishes the tool's declaration, not blanket output clearance. The audit fingerprints the five original URDF/mesh inputs and nine converted layers. Current layers contain personal conversion paths; publish only a separately reviewed copy after resource/rights/privacy review, without rewriting pinned originals or historical acceptance hashes.

## Isaac Sim, model weights and external services

NVIDIA distinguishes [Apache-licensed Isaac source](https://docs.isaacsim.omniverse.nvidia.com/latest/common/licenses-isaac-sim.html) from Kit/components/assets with [separate terms](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/); its [FAQ](https://docs.isaacsim.omniverse.nvidia.com/latest/common/license-faq.html) separately describes internal/custom-output use and runtime redistribution/services. Read-only local metadata/version evidence is captured by the optional inventory, not used as a blanket permission grant.

NVIDIA Isaac Sim/Kit, their extensions and assets retain their respective NVIDIA/upstream licenses. This repository's license does not license the Isaac runtime for redistribution. LLM model weights retain their original licenses; invoking a hosted model does not make it TwinPulse-owned or Apache-2.0. Nebius/OpenAI and other service terms are separate. No runtime, model weights, private photos, credentials or API keys are added to a public distribution by this change.

## Python and browser dependencies

The exact installed/source pnpm lock matches. The repeatable inventory records 101 installed packages: three browser production packages, one Vite browser helper and 97 development packages not shipped as packages. The lock also contains 44 packages not locally installed; this is recorded rather than claiming they were tested/shipped. Three installed development packages have no separately named license/notice file (`@rolldown/binding-win32-x64-msvc`, `saxes`, `stackback`); their declarations are recorded, not treated as original-text clearance. Review them if later shipping those tools.

The shipped, hash-pinned Pillow 12.3.0 wheel declares MIT-CMU and retains its complete original `dist-info/licenses/LICENSE`, including bundled-library notices. Its 25 Requires-Dist entries are optional extras, not unrecorded base runtime dependencies. Own Python package dependency metadata is inventoried separately. Browser original notices are checked byte-for-byte. Inventory coverage is not a legal judgment about every transitive package.

Dependencies declared in the existing Python/Node manifests (including Pillow, React, React DOM and their build/test dependencies) retain their upstream licenses. Installed libraries and `node_modules` are not rewritten. The existing offline package ships a hash-pinned Pillow wheel; that wheel's own license files must remain intact. Web bundles may incorporate dependency code: preserve any emitted upstream legal notices, and check the exact dependency licenses/notices before public redistribution. The TwinPulse LICENSE/NOTICE alone do not replace them. Exhaustive transitive-dependency notice aggregation is not completed by this bounded change.

The current minified web output removed dependency comments. To preserve the actual browser components' notices without changing runtime behavior, `apps/twinpulse-web/THIRD_PARTY_LICENSES.txt` and its `public/` copy carry the unchanged installed licenses for React 19.3.0, React DOM 19.3.0, Scheduler 0.28.0 and Vite 8.3.0 (for its injected browser helper). React/React DOM/Scheduler use MIT; the complete Vite LICENSE includes its own MIT notice and original bundled dependency notices, not a claim that every Vite build dependency is present in the application. The current `dist/` receives the same legal file, and subsequent Vite builds copy it from `public/`. Update and verify these notices when dependencies change. No product-screen display is required by this project policy.

## Photos, fixtures and saved evidence

Source-level attribution is retained in the existing fixture manifests, including `fixtures/m2c/warehouse_images.json`:

| Fixture | Recorded creator | Recorded license | Original page |
| --- | --- | --- | --- |
| Pallet racks | Jandrinov | Public domain | https://commons.wikimedia.org/wiki/File:Pallet_racks.jpg |
| Almacen interior | Aspasturias | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Almacen_interior.jpg |
| Pallets for Gustav | Jacinta Quesada / FEMA | Public domain (FEMA) | https://commons.wikimedia.org/wiki/File:Pallets_for_Gustav.jpg |

Other benchmark manifests carry their own input provenance/license records. A recorded license here is not a new independent verification of every upstream page. CC BY-SA photos/qualifying adaptations retain their own attribution/share-alike conditions; they are not relicensed Apache-2.0. Personal photos, floorplans, raw logs, generated reports and saved scene evidence are not broadly cleared for publication. The licensing work does not rewrite or publish these materials. Public distribution still requires a content-specific rights/privacy check.
