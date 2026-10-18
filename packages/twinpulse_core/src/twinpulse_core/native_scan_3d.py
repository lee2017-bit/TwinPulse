# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Deterministic, dependency-free USD evidence export. Never a world TF or map.

One frame only, with original IDs/angles/ranges retained on its usable points.
z=0 means the sensor's drawing plane, NOT the floor or sensor mounting height.
No referenced files, executable data, materials, physics, robot or scene edits.
"""
import hashlib
import json

from .native_scan import NativeScanBundle


def export_native_frame_3d(bundle: NativeScanBundle, frame_index: int) -> dict:
    # Revalidate even a directly constructed dataclass; no trusting _json callers.
    checked = NativeScanBundle.from_text(bundle._json)
    frame = checked.frame_preview(frame_index)
    source = checked.to_dict()["source"]
    points = frame["points"]

    def number(value):
        return format(float(value), ".17g")

    def array(values):
        return "[" + ", ".join(str(value) for value in values) + "]"

    xyz = array(f"({number(p['x_m'])}, {number(p['y_m'])}, 0)" for p in points)
    ids = array(p["node_index"] for p in points)
    used = {p["node_index"] for p in points}
    excluded = array(b["node_index"] for b in checked.to_dict()["frames"][frame_index]["beams"]
                     if b["node_index"] not in used)
    # Only allowlisted strings and validated finite numbers enter USDA syntax.
    text = f'''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)
def Xform "World" {{
    def Xform "TwinPulse" {{
        def Xform "NativeEvidence" (
            customData = {{
                string owner = "TwinPulse"
                string evidenceSchema = "native-evidence-3d-1.0"
                string bundleDigest = "{checked.digest}"
                string rawSha256 = "{source['raw_sha256']}"
                string nodesSha256 = "{source['nodes_sha256']}"
                string sourceKind = "{source['kind']}"
                string observationStartUtc = "{source['observation_start_utc']}"
                string observationEndUtc = "{source['observation_end_utc']}"
                string frame = "sensor_native_unverified_axes"
                string plane = "z0_is_sensor_drawing_plane_not_floor"
                string timestampBasis = "host_observation_window_not_beam_time"
                string physicalValidation = "NOT_RUN"
                string clearance = "UNKNOWN"
                bool worldAlignmentVerified = false
                bool motionAuthorized = false
                bool sourceBytesVerified = false
                int frameIndex = {frame_index}
                int originalSamples = {frame['samples']}
                int excludedReturns = {frame['invalid_returns']}
            }}
        ) {{
            custom int[] excludedNodeIndices = {excluded}
            def Points "Returns" {{
                point3f[] points = {xyz}
                int64[] ids = {ids}
                float[] widths = [0.018] (interpolation = "constant")
                color3f[] primvars:displayColor = [(0.12, 0.85, 0.65)] (interpolation = "constant")
                custom double[] nativeAngleDegrees = {array(number(p['angle_deg']) for p in points)}
                custom double[] nativeRangeMeters = {array(number(p['distance_m']) for p in points)}
                custom int[] nativeQuality = {array(p['quality'] for p in points)}
                custom int[] sourceByteCursor = {array(p['source_byte_cursor'] for p in points)}
            }}
            def BasisCurves "NativeAxes" {{
                token type = "linear"
                token wrap = "nonperiodic"
                int[] curveVertexCounts = [2, 2]
                point3f[] points = [(0, 0, 0), (0.5, 0, 0), (0, 0, 0), (0, 0.5, 0)]
                float[] widths = [0.008] (interpolation = "constant")
                color3f[] primvars:displayColor = [(1, 0.25, 0.15), (0.2, 0.5, 1)] (interpolation = "uniform")
                custom string description = "Red=angle0 Blue=angle90. Not confirmed robot/world axes."
            }}
        }}
    }}
}}
'''
    return {"schema_version": "native-evidence-export-1.0", "filename": f"native-frame-{frame_index:03d}.usda",
            "media_type": "text/plain", "usda": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "bundle_digest": checked.digest, "frame_index": frame_index,
            "point_count": len(points), "excluded_count": frame["invalid_returns"],
            "coordinate_frame": "sensor_native_unverified_axes", "world_tf": None,
            "motion_authorized": False, "physical_validation": "NOT_RUN",
            "notice": "Open as a separate evidence stage. z=0 is the sensor drawing plane, not the floor. No world alignment, collision geometry or navigation permission."}
