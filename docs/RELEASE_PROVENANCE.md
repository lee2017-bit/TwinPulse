# Release provenance and public-content review

The existing local offline bundle and a reviewed public distribution are different things. A passing local build is not permission to publish its assets, photos, logs or embedded personal paths. TwinPulse's Apache-2.0 policy applies to its own code only; this review adds no conditions to that license.

## SIM alpha builder and repeatable check

The selected SIM alpha source uses `scripts/build_windows_exe.py` and `packaging/windows/TwinPulse.spec`. It copies the reviewed source closure, compiled web assets, nine public Burger layers and original dependency notices, then writes a complete size/hash release manifest and SHA256SUMS for the one-folder ZIP. Legacy local offline-bundle audit scripts are not included in this selected source tree and are not a prerequisite for this builder.

The Node inventory checks the installed pnpm lock against the source lock, walks actual production dependency edges, records all locally installed transitive package metadata/notices, and separately lists locked packages not installed on this platform. Development tools are not misreported as browser runtime packages. Browser notices must retain the original bytes, not only names or SPDX strings. The shipped Pillow wheel must match the existing hash lock, with its original bundled-library notices intact. Optional extra requirements are not silently installed.

Build success and hash verification are not public-content clearance. Review private inputs, logs, history and asset notices separately before publication. This adds no restriction to Apache-2.0 reuse. The builder performs no publication.

To build a new immutable candidate after the locked web build:

```powershell
python scripts/build_windows_exe.py --output-dir artifacts/windows-exe/NEW_BUILD --channel sim-alpha
```

Choose a new output path every time. Existing reports/raw/assets remain unchanged. This is a technical inventory, not a SPDX/CycloneDX-conformant SBOM or blanket legal clearance.

## Isaac source, runtime, and converted assets

NVIDIA distinguishes its Apache-licensed Isaac source from additional Kit components, models and textures with separate terms. Its FAQ distinguishes internal use/custom code or USD outputs from redistribution of the Isaac/Kit runtime or a turnkey service. See [official licensing](https://docs.isaacsim.omniverse.nvidia.com/latest/common/licenses-isaac-sim.html), [FAQ](https://docs.isaacsim.omniverse.nvidia.com/latest/common/license-faq.html), and [additional terms](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/). These do not automatically clear every asset used in a scene.

Read-only local inspection on 2026-10-11 found Isaac `6.0.1-rc.7+release.42383.32955d8d.gl`. The installed URDF extension config is marked `LicenseRef-NvidiaProprietary`; its bundled `urdf-usd-converter` 0.1.3 metadata declares Apache-2.0 and preserves `licenses/LICENSE.md`. The converted Burger layers record that converter. This identifies the tool, not ownership of its inputs or blanket output rights. The original ROBOTIS source/mesh lineage and Apache notice remain separate. No NVIDIA runtime, importer binaries, model weights or asset packs are shipped by the local builder.

Before publishing the existing converted Burger assets, review the exact source/embedded-resource closure and conversion terms, retain upstream notices, and create a separately reviewed public copy if personal conversion paths need removal. Do not overwrite the pinned nine USD originals or historical acceptance hashes. The current gate flags the converted asset group rather than claiming that all USD files are prohibited or automatically Apache.

### SIM-alpha asset copy, 2026-10-14

`assets/simulation/turtlebot3_burger/SOURCE.json` identifies the ROBOTIS source commit `90a68bd2e3c61c12966779da89d8eeaec82730e9`, URDF/mesh inputs, original converted hashes and the nine public-copy hashes. The unmodified upstream license is adjacent. `scripts/prepare_public_sim_assets.py` removes private exporter documentation from a separate copy and adds a prominent modification/provenance notice. It checks the local layer/reference closure and compares composed prims (including instance proxies), attributes, relationships and connections with the originals. Originals remain unchanged; equal authored-scene fingerprints do not claim that arbitrary other assets are cleared.

No Isaac/Kit/importer binaries, NVIDIA asset packs or model weights are included. The original Apache notices cover the ROBOTIS source and the documented TwinPulse modifications; other components retain their own licenses. Public source and each final ZIP still require the hash-bound privacy/content review below. The two new public test photographs and private regression input are not included in the package or source by this asset preparation.

## Content-specific release checklist

1. Decide the actual public files, with hashes and origins. Inspect the audit's unclassified/converted-asset findings. Own source/header matches are candidates, not proof of all content rights or privacy.
2. Keep credentials, `.env`, private keys, private photos/floorplans, saved projects, original raw captures, datasets and unreviewed reports out of the release. Excluded files are flagged by path without opening their contents.
3. Resolve embedded personal absolute paths and potential credential-material findings. Reports store only the path and category, never the matched credential or personal-path text. Pattern scans are bounded safeguards, not proof that every possible secret or PII is absent.
4. For any separately approved public photo/report, record creator, original URL, license, changes and required attribution/share-alike terms. A benchmark's external-transmission approval is not a publication grant. Generated scenes/reports are assessed by their actual contents, not automatically relicensed Apache-2.0.
5. Preserve component-original notices and verify every release-manifest byte/hash, including extra/unmanifested files. Confirm privacy/rights review separately from technical integrity and product acceptance.

No public switch, upload, commit/push, runtime deployment or full demo acceptance is authorized by these checks. Remaining product acceptance follows the existing Physical AI plan after the licensing checks.
