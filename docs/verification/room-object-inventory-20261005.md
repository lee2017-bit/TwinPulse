# Room objects and photo obstacle inventory

The user's room must not be reduced to seven furniture types. The current implementation adds 19 typed room items to the existing seven furniture presets, records 24 grouped observations from the supplied room photo, and connects their approximate geometry and synthetic risk areas to generation, saved edits, the chat inventory and SIM planning. These are parametric primitives, not 26 downloaded or photorealistic models.

This increment does not measure the room, call a paid model or operate the robot. The reviewed inventory belongs only to the exact supplied photo whose SHA256 is `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`. Other images are not silently assigned this room's contents. Occluded and unrecognized items remain unresolved; the list is not proof that every real obstacle has been discovered.

## Supplied photo observations

The list is a human review of the user's photograph, not automatic vision output. Several similar objects are grouped. Capture time, dimensions and coordinates are unknown. A visually supported label does not establish exact identity or robot-local position.

| Saved ID | Item | Interpretation |
| --- | --- | --- |
| bed | Bed base and mattress | Visible furniture |
| wardrobe | Wardrobe body | Visible furniture |
| desk | Desk including legs | Visible furniture |
| office_chair | Rolling chair including wheel base | Visible floor obstacle |
| wood_frame | Wooden frame or clothes rack | Identity uncertain |
| floor_fan | Fan stand and base | Partly occluded |
| entry_door | Entry door and opening | Photo state only |
| wardrobe_door | Open wardrobe door | Photo state only |
| hanging_clothes | Hanging clothes and lower edges | Possible entanglement |
| clothing_pile | Clothes on the floor | Entanglement risk area |
| bedding_overhang | Bedding extending past the bed | Conservative floor keepout |
| floor_bags | Bags at the left floor edge | Partly occluded |
| underdesk_bag | Bag or soft item by the desk | Identity uncertain |
| boxes | Boxes at the entry and left edge | Grouped floor obstacles |
| basket | Basket or container and contents | Grouped floor obstacle |
| cables | Loose floor cables | Entanglement risk area |
| power_adapter | Floor power adapter | Floor obstacle |
| power_strip | Floor power equipment | Exact type uncertain |
| small_equipment | Small floor equipment or parts | Unknown with keepout |
| monitor | Desk display or electronic device | Partly occluded prop |
| tabletop_items | Desk electronics and small items | Grouped props |
| window_blind | Window and blind | Visual structure |
| ceiling_light | Ceiling light | Partly occluded prop |
| top_storage | Storage box above the wardrobe | Elevated prop |

The first 19 rows require representation before this specific photo's SIM route preparation. The final five remain in the inventory but are not mandatory floor-risk coverage. Coverage requires the exact item ID, category and complete expected geometry with collision flags retained. Unrelated same-ID objects, missing keepouts and partial assemblies do not count as represented. Coverage does not constitute physical validation or clearance.

## Product behavior

`SiteToolPlan 2.2` adds `place_room_item` with a pinned `room-items-1.0` catalog. The selected site provider now receives this schema and the exact-photo reviewed inventory when applicable. Existing 1.0, 2.0 and 2.1 contracts retain their prior schemas and serialization. The 2.2 call limit is 40; the existing 64-object ceiling remains. A test represents all 24 photo entries within this ceiling.

Office chairs, fans and clothes racks use small multi-part assemblies. Other props use adjustable box approximations. Floor fabric, cables and unknown items have non-colliding visual volumes plus a separate colliding orange envelope, enlarged by 0.10 m per side and 0.35 m high. This envelope is a design choice, not a measured volume, scan return or physically qualified safety distance. A low monitor or small prop still blocks SIM navigation; elevated decor may be visual only. Bounds checks reject an item outside the floor instead of clipping it.

The chat has a collapsible **Room inventory** with represented and unplaced items, evidence, geometry and unknown observation times. The list scrolls independently to avoid hiding the conversation. **Edit inventory placement** opens the existing advanced editor. **Add room item / hazard** and **Change room item / hazard** provide type, label, X/Y/Z, dimensions and yaw. The unplaced-photo dropdown preserves reviewed IDs. Preview and explicit save use the existing source-bound edit sidecar, keep the original unchanged and invalidate old Build/route approval. This increment supports numeric placement and rotation for the new props; it does not claim new-prop drag-and-drop acceptance.

For the exact reviewed photo, missing required items reject preview, explicit plan, chat goal and SIM Run with `room_inventory_incomplete` and the missing IDs. The generated draft remains available for review and explicit static Build; incomplete inventory does not become movement authorization. Automatic SIM preparation and its Build sequence cannot continue until coverage is complete. A different newly selected input cannot borrow coverage from an old saved photo. No route gate claims generalized completeness for arbitrary future images.

## Verified evidence

| Check | Result |
| --- | --- |
| Related Python suite | 215 tests PASS across provider compatibility, chat, startup, simulation, edits and manual rooms |
| Focused room inventory suite | Final seven tests PASS; six overlap the related run, and the added seventh covers all 24 entries within the object budget |
| Web tests | 38 files and 296 tests PASS, including missing hazard labels and explicit cable edit preview |
| Production build | TypeScript and Vite PASS; existing bundle-size warning remains |
| Actual local Web API and Isaac | `artifacts/chat-room-items-20261005-final/result.json` PASS: all 19 new categories, automatic room Build, static Burger, explicit PhysX Run and arrival, current-pose next goal, chat Stop, folded viewer, reload without resume, explicit Reset and mobile layout |
| Final binding | Actual receipt's 43 source and four built Web hashes match the final checkout; test-owned backend and engine stopped |
| Existing six browser cases | `artifacts/chat-room-items-c1-20261005-final/verification.json` PASS for image, text, REAL selection, failed generation, cancellation and saved edits; this separate harness does not qualify Isaac or physical driving |
| Whitespace | `git diff --check` PASS; existing CRLF warnings are not failures |

The actual Isaac acceptance uses invented local fixture coordinates and an explicit 2.2 provider response. Browser, backend, USD rendering and PhysX movement are real installed paths. It is not paid photo interpretation, recreation of the supplied photo or physical collision avoidance. The visible orange proxy labels and bounded list layout were inspected in the final saved screenshot.

Initial sandbox test runs could not create some temporary files or start Vite child processes. Scoped approved local test execution resolved those environment restrictions without changing permissions or system settings. Early new tests also used an unsupported source label and incorrect existing API signatures; those test definitions were corrected. No failed result was converted to physical success. The earlier `...-01` actual receipt is an intermediate source snapshot; `...-final` binds the final implementation.

## Reproduction and remaining scope

Use the existing local Python runtime for `python -m unittest tests.integration.test_room_items tests.integration.test_chat_conversation`. In `apps/twinpulse-web`, run `pnpm test` and `pnpm build`. Actual acceptance is `python scripts/verify_chat_sim_journey.py artifacts/<fresh-directory> --case text --layout cluttered_room`; the existing script owns and closes its isolated local processes. No robot or paid provider is implied.

The implementation and scoped offline acceptance above are complete. Accurate photo dimensions, occluded obstacle discovery, authorized real-provider interpretation, generic pending-item discovery for other photos, photorealistic assets and actual scan/physical route validation remain separate. C1/C2 remain PARTIAL and whole-demo readiness remains false; this does not complete REAL chat qualification, survey, route execution or loop tasks. Existing dirty work, photo/raw originals, prior failures, old contracts and physical mission locks remain preserved. Physical guard limits remain scan 200 ms, input 250 ms, segment 50 ms, 0.03 m/s, 0.20 rad/s and 45 s. Robot connections, paid calls, installs, deployment, commit/push and new agents: zero. The heartbeat remains PAUSED.
