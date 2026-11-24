"""Measure openings and wall flatness in a new, single-room metric point cloud."""
import argparse
import csv
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "third_party"))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
from room_walls.config import Config
from wall_flatness.io import read_cloud
from algorithms import CloudContext, load_profile
from course_reference import matched_reference
from frame_sections import depth_checks
from openings import position_openings
from wall_rms import measure_scope, wall_pool, write_json
from report import plot_wall
from reporting import generate_reports
from window_sections import measure_windows


def save_tables(output, summary):
    def table(name, header, rows):
        with (output / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)

    xyz = ["x_m", "y_m", "z_m"]
    openings, corners, rms, sections = [], [], [], []
    for w in summary["walls"]:
        for o in w["openings"]:
            openings.append([o["wall"], o["id"], o["type"], o["width_mm"], o["height_mm"],
                             o["width_at_height_m"], o["sill_m"], o["head_m"], *o["center_xyz_m"],
                             *(v for point in o["corners_xyz_m"] for v in point)])
            for row in o["depth_sections"]:
                sections.append([o["id"],row["depth_mm"],row["width_median_mm"],len(row["width_samples"]),
                                 row["height_median_mm"],len(row["height_samples"])])
        for label, corner in zip("ABCD", w["structural_corners"]):
            corners.append([w["id"], label, *corner["xyz_m"], corner["nearest_wall_point_index"],
                            *corner["nearest_wall_point_xyz_m"], corner["nearest_distance_mm"],
                            corner["extrapolated_over_50mm"]])
        for scope in ("whole",):
            r = w[scope]
            rms.append([w["id"], scope, r["status"], r.get("rms_mm"), r.get("n_selected"),
                        r.get("coverage_fraction"), r.get("p95_abs_mm"), r.get("max_abs_mm"),
                        r.get("reason", ""), ",".join(r.get("warnings",[])), r.get("roi_file", ""), r.get("residual_file", "")])
    table("openings.csv", ["wall", "opening", "type", "width_mm", "height_mm", "width_at_height_m",
                          "sill_m", "head_m", *["center_"+k for k in xyz],
                          *[label+"_"+k for label in "ABCD" for k in xyz]], openings)
    table("wall_corners.csv", ["wall", "corner", *xyz, "nearest_original_index",
                              *["nearest_"+k for k in xyz], "nearest_distance_mm", "extrapolated_over_50mm"], corners)
    table("wall_rms.csv", ["wall", "scope", "status", "rms_mm", "n_points", "coverage_fraction",
                          "p95_abs_mm", "max_abs_mm", "reason", "warnings", "roi_file", "residual_file"], rms)
    table("frame_depths.csv", ["opening","depth_mm_positive_into_room","width_median_mm","width_supported_sections",
                              "height_median_mm","height_supported_sections"], sections)


def inspect(source, output, unit, up, node, algorithms=None):
    algorithms = algorithms or load_profile()
    source_name = Path(str(source).split("::")[-1]).name
    print(f"Reading scan  {source_name}", flush=True)
    points, digest = read_cloud(source, with_hash=True)
    if unit == "mm":
        points *= .001
    config = Config(up=tuple(up))
    archive, separator, member = str(source).partition("::")
    context = CloudContext(str(Path(archive).resolve())+separator+member,unit,config.up,digest,len(points))
    algorithms = algorithms.for_cloud(context)
    print(f"Discovering floor and walls  {len(points):,} input points", flush=True)
    discovery = algorithms.walls(points, config)
    native=discovery.get('mode')=='efficient_ransac'
    floor = discovery["floor"]
    candidates = discovery["walls"]
    named = set()
    for wall in candidates:
        wid = wall["id"]
        if not isinstance(wid,str) or not re.fullmatch("[A-Za-z0-9_-]+",wid) or wid in named:
            raise ValueError("Wall IDs must be unique and contain only letters, digits, underscores or hyphens.")
        named.add(wid)
        ids = np.asarray(wall["expanded_indices"])
        if (ids.ndim!=1 or ids.dtype.kind not in "iu" or len(ids)<3 or np.any(ids<0) or np.any(ids>=len(points))
                or len(np.unique(ids))!=len(ids) or not np.isfinite(points[ids]).all()):
            raise ValueError(f"{wid} requires distinct valid original point indices.")
        wall["expanded_indices"]=ids
        wall.setdefault("discovery_support_count",len(ids))
    bounds = algorithms.corners(points, discovery, config)
    walls, inside_ids, corners = bounds["walls"], np.asarray(bounds["inside_ids"]), bounds["corners"]
    ceiling, room, warnings = bounds["ceiling"],bounds["room"],bounds["warnings"]
    if inside_ids.ndim!=1 or inside_ids.dtype.kind not in "iu" or np.any(inside_ids<0) or np.any(inside_ids>=len(points)):
        raise ValueError("The room boundary stage must return valid original point indices.")
    measured_ids = {w["id"] for w in walls}
    if len(measured_ids)!=len(walls) or not measured_ids.issubset(named):
        raise ValueError("Boundary walls must be distinct members of the candidate set.")
    summary = {
        "format_version":2, "algorithms":algorithms.manifest, "word_report":"report.docx",
        "cloud":{"file":source_name, "sha256":digest, "input_unit":unit,
                                    "point_count":len(points), "invalid_rows":int((~np.isfinite(points).all(axis=1)).sum())},
        "coordinates":"Original coordinate axes and origin, expressed in metres. Original row indices start at 0.",
        "corner_order":"A lower left, B lower right, C upper right, D upper left in the plotted elevation; horizontal axis = inward wall normal cross upward floor normal.",
        "floor":floor, "ceiling":ceiling, "room":room,
        "discovery_config":config.to_dict(), "discovery_warnings":discovery.get("warnings",[]),
        "candidate_wall_count":len(candidates), "other_candidate_ids":[w["id"] for w in candidates if w["id"] not in measured_ids],
        "warnings":warnings, "walls":[], "integrations":{"room_walls":"149d280662e9f6256608efd1896b1744e82cf5d4",
                        "wall_flatness":"952259ce8037f042155139ca3fb7af58cd9e2d5f"}
    }
    if algorithms.manifest["stages"]["corners"]["call"]=="room_geometry:room_boundaries":
        summary["ceiling_footprint_min_fraction"] = .35
    if algorithms.manifest["stages"]["openings"]["call"]=="openings:profile_candidates":
        summary["opening_face_half_thickness_mm"] = 8
    if native:
        provenance=dict(discovery['native_detection']);native_text=provenance.pop('support_text')
        (output/'native_supports.txt').write_text(native_text,encoding='utf-8')
        summary.update(native_detection=provenance,native_config=discovery['config'],
            native_structure=bounds.get('native_structure'),filter='none',recovery='none',
            support_definition='Original native supports inside structural corners after masking detected openings')
        summary['integrations']['native_framework']=discovery['backend_source_sha256']
        summary['warnings'].append('Detected opening footprints are masked for whole-wall RMS.')
    assignments = {}
    for wall in walls:
        wid = wall["id"]
        print(f"{wid}  Measuring openings, wall corners and RMS", flush=True)
        structural = corners.get(wid, [])
        opening_list, checks = algorithms.openings(points, inside_ids, wall, floor, structural, node)
        opening_list = position_openings(opening_list, wall, floor)
        if native:
            for opening in opening_list:opening.setdefault('status','candidate')
        depth_checks(points, wall, floor, opening_list)
        raw_ids = wall_pool(points, wall, floor, opening_list)
        assigned = wall["expanded_indices"]
        assignments[wid+"_assigned"] = assigned
        assignments[wid+"_eligible"] = raw_ids
        boundary = [c["xyz_m"] for c in structural]
        if boundary:
            whole = measure_scope(output, points, raw_ids, boundary, source_name, wid, "whole", algorithms.rms)
            if whole["status"]!="unavailable" and any(c["extrapolated_over_50mm"] for c in structural):
                whole["status"] = "warning"
                whole["warnings"].append("STRUCTURAL_CORNER_EXTRAPOLATION")
        else:
            whole = {"status":"unavailable", "reason":warnings[0] if warnings else "Review the four structural wall corners."}
        result = {"id":wid, "plane_center_m":wall["plane_center_m"], "plane_normal":wall["plane_normal"],
                  "structural_corners":structural, "assigned_points":len(assigned),
                  "excluded_opening_points":len(assigned)-len(raw_ids), "openings":opening_list,
                  "opening_checks":checks, "whole":whole,
                  "wall_recovery_edge_fraction":wall.get("recovery_edge_fraction")}
        if native:
            result["native_plane_ids"]=wall["native_plane_ids"]
        result["elevation_file"] = plot_wall(output, points[assigned], wall, floor, result)
        summary["walls"].append(result)
    np.savez_compressed(output/"wall_points.npz", **assignments)
    measure_windows(points, summary, output)
    summary["window_sections_file"] = "window_sections.json"
    summary["manual_reference"] = matched_reference(summary)
    save_tables(output, summary)
    write_json(output/"summary.json", summary)
    generate_reports(output,algorithms.report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cloud", help="PCD, CSV (x,y,z) or archive.zip::member.pcd")
    parser.add_argument("--unit", choices=["m","mm"], default="m", help="input coordinate unit (default: m)")
    parser.add_argument("--up", nargs=3, type=float, default=(0,0,1), metavar=("X","Y","Z"))
    parser.add_argument("--out", type=Path, help="new result directory, created after processing succeeds")
    parser.add_argument("--open-report", action="store_true")
    parser.add_argument("--open-word", action="store_true", help="open the generated Word report")
    parser.add_argument("--profile",default="default",help="installed algorithm profile name or local JSON file")
    args = parser.parse_args()
    node = shutil.which(os.environ.get("TASK1_NODE") or "node")
    name = Path(args.cloud.split("::")[-1]).stem
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid4().hex[:8]
    target = (args.out or HERE/"results"/(name+"_"+suffix)).resolve()
    try:
        algorithms = load_profile(args.profile)
        if target.exists():
            raise FileExistsError(f"Output directory already exists. Choose a new directory. {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=target.parent, prefix=".task1-") as stage:
            output = Path(stage)/"result"
            output.mkdir()
            inspect(args.cloud, output, args.unit, args.up, node, algorithms)
            output.rename(target)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError, RuntimeError, np.linalg.LinAlgError) as error:
        parser.exit(1, f"Measurement failed. {error}\n")
    print(f"Word report  {target/'report.docx'}\nHTML report  {target/'report.html'}", flush=True)
    if args.open_word:
        if os.name=="nt":
            os.startfile(str(target/"report.docx"))
        else:
            import webbrowser
            webbrowser.open((target/"report.docx").as_uri())
    if args.open_report:
        import webbrowser
        webbrowser.open((target/"report.html").as_uri())


if __name__ == "__main__":
    main()
