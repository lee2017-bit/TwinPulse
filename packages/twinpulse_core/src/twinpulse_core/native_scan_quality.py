# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Descriptive cross-frame audit, not scan registration or clearance checking.

Five-degree bins group measured returns for statistics only. They never synthesize
new rays. Across-frame spread can include object boundaries and scene changes;
it is not range accuracy, platform stationarity or a navigation qualification.
"""
import math
import statistics

from .native_scan import NativeScanBundle, usable_return


def _quantile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def analyze_native_scan(bundle: NativeScanBundle):
    data = bundle.to_dict()
    frames = []
    bins = [[] for _ in range(72)]
    total = excluded = 0
    for frame in data["frames"]:
        beams = frame["beams"]
        valid = [b for b in beams if usable_return(b)]
        angles = sorted(b["angle_deg"] % 360 for b in valid)
        gaps = ([b - a for a, b in zip(angles, angles[1:])] + [angles[0] + 360 - angles[-1]]) if angles else [360.]
        per_bin = [[] for _ in range(72)]
        for beam in valid:
            per_bin[int((beam["angle_deg"] % 360) // 5)].append(beam["distance_m"])
        for index, ranges in enumerate(per_bin):
            if ranges:
                bins[index].append(statistics.median(ranges))
        ranges = [b["distance_m"] for b in valid]
        total += len(beams)
        excluded += len(beams) - len(valid)
        frames.append({"frame_index": frame["index"], "samples": len(beams), "usable": len(valid),
                       "excluded": len(beams) - len(valid), "widest_usable_return_gap_deg": max(gaps),
                       "occupied_angle_bins": sum(bool(items) for items in per_bin),
                       "min_return_m": min(ranges, default=None), "max_return_m": max(ranges, default=None)})
    sectors = []
    for index, medians in enumerate(bins):
        median = statistics.median(medians) if medians else None
        sectors.append({"native_angle_start_deg": index * 5, "native_angle_end_deg": (index + 1) * 5,
                        "frames_with_returns": len(medians), "frames_total": len(frames),
                        "median_of_frame_medians_m": median,
                        "p10_frame_median_m": _quantile(medians, .1), "p90_frame_median_m": _quantile(medians, .9),
                        "median_absolute_deviation_m": statistics.median(abs(v - median) for v in medians) if len(medians) >= 2 else None})
    return {"schema_version": "native-scan-quality-1.0", "bundle_digest": bundle.digest,
            "method": "native_5deg_groups_of_recorded_returns_no_resampling",
            "assessment": "DESCRIPTIVE_ONLY", "frame_count": len(frames), "sample_count": total,
            "excluded_count": excluded, "excluded_percent": 100 * excluded / total,
            "min_usable_per_frame": min(f["usable"] for f in frames),
            "max_usable_per_frame": max(f["usable"] for f in frames),
            "worst_return_gap_deg": max(f["widest_usable_return_gap_deg"] for f in frames),
            "never_observed_angle_bins": sum(not values for values in bins),
            "frames": frames, "angle_groups": sectors,
            "clearance": "UNKNOWN", "stationarity_verified": False,
            "range_accuracy_verified": False, "world_tf_verified": False,
            "motion_authorized": False,
            "limits": ["No-return sectors are UNKNOWN, not free space.",
                       "Grouping is for statistics only; original nonuniform beams are unchanged.",
                       "Across-frame spread includes object edges and possible scene changes, not sensor accuracy.",
                       "Native directions do not identify robot-forward or world headings."]}
