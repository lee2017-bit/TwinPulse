# Same-position photo / actual native scan review — 2026-09-27

## Additional top-view direction evidence

User supplied a closer top-view photo and explicitly stated **image-up = window**.
Original bytes are preserved as `artifacts/photo-scan-review-20260927/top-view-window-up.jpg`,
SHA256 `d615c5027e28bd3cda88e7fc6593dca71c00634a5201c2587d2be06ef0ff1ca1`.
Copy hash verified; `top-view-evidence.json` records this declaration against the
existing raw recording. This is a useful mounting/orientation reference, not a
calibrated heading, native sensor zero or handedness proof. Do not equate image-up
with robot-forward. The still photograph does not verify rotor stop or power-off.
No new robot connection or movement. This evidence can be analysed while the robot
is off; it does not require another live scan before the user leaves.

## Delivered

User supplied the bedroom photo and explicitly confirmed that the last scan was
captured with the robot in the same position/layout. **Photo/scan provenance binding
and a review-only alignment hypothesis are prepared. Geometric registration is not verified.**

Local deliverable: `artifacts/photo-scan-review-20260927/index.html`.
It places the unmodified original photo beside a real native scan scatter plot,
with eight display-orientation alternatives. `review.json` preserves source hashes,
user declaration, approximate photo-only observations, fitted observed segments and
uncertainty. There is no backend call, execution button, runtime deployment or robot access.

- Original photo SHA256: `a183bf7e30cb6d1ddc712aa25f484f8763bca6ccbc75d4c8977aa99cbb6f6ea0`.
- Actual raw scan SHA256: `4b6d732b717e2cc6242366e3a6040d5212b59b3271be76d525466b45a6e39e07`.
- Source: `artifacts/lidar-capture-20260927-1214/`; last complete scan73,389 usable returns.
- Uses existing `InputRevision` and `PhotoTrackManifest`, same-site confirmation true,
  no invented manual measurements. Photo-review-ready true; manual-alignment-ready false.
- `burger-photo-review-unqualified` is an input-review identifier, **not a qualified
  RobotProfile** and not passed to the App's validated scan/world/mission contracts.
- The generation script accepts only this hash-pinned confirmed pair; it cannot
  silently reuse the declaration/semantic labels with another photo or scan.

## What the photo shows / what is inferred

Visible photo observations: bed/bedding at right, open wardrobe back-right, desk
under window back-left, chair in front of desk, fan/boxes at left, bags/clothing
near both sides, robot in the central aisle. Image-region boxes are manually
estimated normalized pixels, not detections with calibrated confidence or metre dimensions.

The deterministic fitting routine extracts connected line-like returns using35mm
inlier tolerance,180mm continuity gap, at least15 supported points and500mm span.
These are **analysis parameters**, not a change to any physical safety acceptance.
It does not join separated surfaces across missing measurements, label walls, fill
unknown cells or create collision objects. TLS residual is fit quality, not global
position accuracy or sensor calibration.

| Segment | Supported points | Observed span | Fit RMS | Identity |
| --- | ---: | ---: | ---: | --- |
| A | 122 | 1.333m | 7.2mm | unassigned; bed-side hypothesis in preferred display |
| B | 50 | 0.784m | 17.8mm | unassigned; left clutter/fan-area hypothesis |
| C | 28 | 0.833m | 8.7mm | unassigned; back furniture-face hypothesis |
| D | 20 | 0.518m | 19.6mm | unassigned |

The qualitative preferred candidate `mirror1` mirrors native Y and rotates213.015°
for **display only**: A appears at the photo's right and C toward its far/window side.
It was chosen by assistant visual review of qualitative layout, **not** calibrated
camera projection, automatic photogrammetry, ICP with surveyed correspondences or
verified manufacturer mounting axes. The reflection is not a valid rigid world TF;
it represents unresolved native sensor angle handedness. Seven alternatives remain.
Never apply this transform to a ROS TF tree or movement commands as if calibrated.

The~1.33m A length is the visible return segment, **not full bed length**. Furniture
heights/full dimensions, robot heading, camera intrinsics/extrinsics, room dimensions,
photo-pixel-to-metre mapping, world pose and semantic correspondence are still unknown.
The photograph covers multiple heights; the scan measures a single horizontal slice.
The open wardrobe door, cloth edges, fan base, chair legs and occlusion need not match
their photo silhouettes. No extrapolation to full obstacle volume/free floor is made.

## Verification

- `scripts/prepare_photo_scan_review.py`: new offline recipe, no network/subprocess/ROS
  or motor interfaces. Original photo copied byte-for-byte, never edited.
- Tests7 PASS: bounded inputs, deterministic line fit, no cross-gap bridge, distance
  invariance with all8 orientations, unverified status, relative photo boxes, no
  remote/motion calls in the report, and confirmation binding rejects another pair.
- Existing photo-track8 and lidar-review4 PASS (19 focused tests total).
- Actual recipe generated8 orientation images + native image, JSON + localHTML.
  Native and preferred candidate PNGs were visually inspected; labels and units legible.
  Browser interaction was not executed this turn; dropdown local-switch wiring is
  source-reviewed/tested at markup level, not claimed as browser E2E PASS.
- Existing raw integrity and decoded sample counts revalidated before plotting.
- `git diff --check` on touched tracked paths PASS. No system/driver installation,
  external provider call, paid API, robot SSH/scan/motor action, commit or push.

## Product status / next

The final actual-site photo prerequisite is now supplied and linked, not still
waiting on a generic example photo. This candidate is a **separate review artifact**;
it is not an active Twin, App import, Isaac build or integrated demo completion.
Next software work can preserve per-beam nonuniform angles in a review adapter and
keep these photo-derived semantic hypotheses distinct from verified sensor geometry.
Before active-Twin geometry/control use, native angle handedness and sensor/base/world
alignment need independent evidence. Missing manual tape dimensions are not a block
to the current photo review; they have not been invented to satisfy an old gate.

Last physical observation stays12:14KST11.69V/voltage-estimated66.1%, torque0/speed0,
unchanged encoders; no new battery reading. Physical rotor-stop observation still
pending. Existing122ms-vs200ms stop FAIL and all other unverified motion gates unchanged.
