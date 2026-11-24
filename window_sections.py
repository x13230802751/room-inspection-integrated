"""Record fitted wall-plane widths and independently observed recessed candidates."""
import csv
from pathlib import Path

import numpy as np
from depth_profile import examine_depths, first_narrower_layer
from room_geometry import section_axis
from wall_rms import write_json


def write_profile(path, rows):
    core = ["depth_mm", "width_median_mm", "width_strips", "height_median_mm", "height_strips"]
    extra = sorted({key for row in rows for key in row}.difference(core))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=core + extra)
        writer.writeheader()
        writer.writerows(rows)


def face_section(opening, half_band_mm):
    uv = np.asarray(opening["corners_uv_m"])
    xyz = np.asarray(opening["corners_xyz_m"])
    height = opening["width_at_height_m"]
    ends = []
    for bottom, top in ((0, 3), (1, 2)):
        t = (height - uv[bottom, 1]) / (uv[top, 1] - uv[bottom, 1])
        ends.append((xyz[bottom] + t * (xyz[top] - xyz[bottom])).tolist())
    return {"kind": "wall_face_aperture", "depth_mm": 0, "fit_band_half_mm": half_band_mm,
            "height_m": height, "width_mm": opening["width_mm"],
            "endpoint_kind": "fitted", "endpoints_xyz_m": ends}


def candidate_section(rows, height, points, u, h, d):
    layer = first_narrower_layer(rows)
    result = {"kind": "recessed_frame_candidate", "status": "no_stable_layer", "height_m": height,
              "depth_range_mm": None, "width_mm": None, "strip_median_width_mm": None,
              "mid_height_samples_mm": [], "representative": None}
    if not layer:
        return result
    result.update(depth_range_mm=[layer[0]["depth_mm"], layer[-1]["depth_mm"]],
                  strip_median_width_mm=float(np.median([r["width_median_mm"] for r in layer])))
    if any("width_0.50" not in r for r in layer):
        result["status"] = "insufficient_mid_height"
        return result
    readings = [r["width_0.50"] for r in layer]
    middle = layer[len(layer) // 2]
    endpoints = []
    for side in ("left", "right"):
        i = int(middle[f"mid_{side}_index"])
        endpoints.append({"side": side, "original_index": i, "xyz_m": points[i].tolist(),
                          "u_mm": float(u[i] * 1000), "height_m": float(h[i]),
                          "actual_depth_mm": float(d[i] * 1000)})
    result.update(status="candidate", width_mm=float(np.median(readings)), mid_height_samples_mm=readings,
                  representative={"slice_center_depth_mm": middle["depth_mm"], "width_mm": middle["width_0.50"],
                                  "endpoints": endpoints})
    return result


def measure_windows(points, summary, output):
    floor = summary["floor"]
    records = []
    for wall in summary["walls"]:
        windows = [o for o in wall["openings"] if o["type"] == "window"]
        if not windows:
            continue
        relative = points - wall["plane_center_m"]
        u = relative @ section_axis(wall, floor)
        h = (points - floor["center_m"]) @ floor["normal"]
        d = -(relative @ wall["plane_normal"])
        for opening in windows:
            rows = examine_depths(u, h, d, opening)
            location = Path("walls") / wall["id"] / (opening["id"] + "_depth_profile.csv")
            (output / location).parent.mkdir(parents=True, exist_ok=True)
            write_profile(output / location, rows)
            height = (opening["sill_m"] + opening["head_m"]) / 2
            records.append({"wall_id": wall["id"], "opening_id": opening["id"],
                            "profile_file": location.as_posix(), "face": face_section(opening, summary.get("opening_face_half_thickness_mm")),
                            "deep": candidate_section(rows, height, points, u, h, d)})
    sections = {"schema_version": "1.0", "cloud_sha256": summary["cloud"]["sha256"],
                "depth_positive": "into_opening", "windows": records}
    write_json(output / "window_sections.json", sections)
    return sections
