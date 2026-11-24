"""Compare visible-opening edges with independent fits to surfaces inside the reveal."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import sys

import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
PROJECT = ROOT
sys.path[:0] = [str(PROJECT), str(PROJECT / "third_party")]
from frame_sections import depth_checks
from room_geometry import section_axis
from contour_fit import estimate as estimate_contour


def load_course_cloud(room, baseline, cloud_dir):
    cloud = cloud_dir / f"{room}.pcd"
    if hashlib.sha256(cloud.read_bytes()).hexdigest() != baseline["cloud"]["sha256"]:
        raise ValueError(f"{cloud} does not match the point cloud used for {room}/summary.json")
    with cloud.open("rb") as f:
        for line in f:
            if line.strip() == b"DATA binary":
                return np.fromfile(f, dtype="<f4").reshape(-1, 7)
    raise ValueError(f"Missing binary PCD header in {cloud}")


def fit_surface(xyz, normals, ids, axis, along_fraction, depth):
    """Orthogonal RANSAC on 7 of 10 edge segments, SVD refit, blind check on the rest."""
    norm = np.linalg.norm(normals[ids],axis=1)
    ids = ids[(norm > 0) & (np.abs(normals[ids] @ axis) >= np.cos(np.deg2rad(30))*norm)]
    blocks = np.minimum(9, (along_fraction[ids]*10).astype(int))
    hold = np.isin(blocks,[2,5,8])
    train, test = xyz[ids[~hold]], xyz[ids[hold]]
    info = dict(selected=len(ids), train=len(train), holdout=len(test))
    if len(train)<30 or len(test)<12:
        return None, dict(info,reason="too_few_oriented_points")
    rng = np.random.default_rng(7023)
    best = np.zeros(len(train),dtype=bool)
    for _ in range(320):
        a,b,c = train[rng.choice(len(train),3,replace=False)]
        n = np.cross(b-a,c-a)
        length = np.linalg.norm(n)
        if length < 1e-8 or abs(n @ axis)<0.866*length:
            continue
        support = abs((train-a) @ n) <= .003*length
        if support.sum()>best.sum():
            best=support
    if best.sum()<20:
        return None, dict(info,reason="insufficient_consensus")
    for _ in range(2):
        p=train[best]
        c=p.mean(axis=0)
        n=np.linalg.svd(p-c,full_matrices=False)[2][-1]
        best=abs((train-c)@n)<=.003
    residual=abs((test-c)@n)
    test_ok=residual<=.003
    support_ids = np.r_[ids[~hold][best],ids[hold][test_ok]]
    q=np.quantile(depth[support_ids],[.05,.95])
    info.update(train_fraction=float(best.mean()), holdout_fraction=float(test_ok.mean()),
                holdout_median_mm=float(np.median(residual)*1000),
                depth_span_mm=(q*1000).tolist(),blocks_supported=len(np.unique((along_fraction[support_ids]*10).astype(int))))
    if (min(best.mean(),test_ok.mean())<.70 or abs(n@axis)<.866 or q[1]-q[0]<.020 or q[1]<-.020
            or info["blocks_supported"]<8):
        return None, dict(info,reason="weak_or_multilayer_support")
    return (n, float(n@c)),dict(info,reason="supported")


def section_intersect(w, face, cut):
    coef=np.array([w[0],face[0],cut[0]])
    if np.linalg.cond(coef)>20:
        raise ValueError("Poorly conditioned plane intersection")
    return np.linalg.solve(coef,[w[1],face[1],cut[1]])


def evaluate(p, normals, wall, floor, o):
    center,n=np.array(wall["plane_center_m"]),np.array(wall["plane_normal"])
    up,fc=np.array(floor["normal"]),np.array(floor["center_m"])
    axis=section_axis(wall,floor)
    u,d,h=(p-center)@axis,(p-center)@n,(p-fc)@up
    left,right=[o[k]["x_at_1m"]+o[k]["slope"]*(h-1) for k in ("left_line","right_line")]
    lower,upper=[o[k]["h_at_u0"]+o[k]["slope"]*u for k in ("lower_line","upper_line")]
    along_side=(h-o["sill_m"])/(o["head_m"]-o["sill_m"])
    along_cross=(u-left)/np.maximum(right-left,.01)
    planes, diagnostics={},{}
    for name,orientation,delta,fraction in [
            ("left",axis,u-left,along_side),("right",axis,u-right,along_side),
            ("bottom",up,h-lower,along_cross),("top",up,h-upper,along_cross)]:
        ids=np.flatnonzero((d>=-.050)&(d<=-.005)&(abs(delta)<.080)&(fraction>=.1)&(fraction<=.9))
        planes[name],diagnostics[name]=fit_surface(p,normals,ids,orientation,fraction,d)
    wall_plane=(n,float(n@center))
    results={}
    for metric,first,last,direction,cut in [
            ("width","left","right",axis,(up,float(up@fc)+o["width_at_height_m"])),
            ("height","bottom","top",up,(axis,float(axis@center)+o["center_uv_m"][0]))]:
        results[metric]=None
        if planes[first] and planes[last]:
            a=section_intersect(wall_plane,planes[first],cut)
            b=section_intersect(wall_plane,planes[last],cut)
            results[metric]=dict(span_mm=float((b-a)@direction)*1000,
                                 endpoints_xyz_m=[a.tolist(),b.tolist()])
    corners=None
    if all(planes.values()):
        corners=[section_intersect(wall_plane,planes[v],planes[t]).tolist()
                 for v,t in [("left","bottom"),("right","bottom"),("right","top"),("left","top")]]
    return results, diagnostics, corners


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=ROOT / "evidence",
                        help="Directory with M26/summary.json and M04/summary.json from Task1-Inspection")
    parser.add_argument("--cloud-dir", type=Path, required=True, help="Directory containing the original M26.pcd and M04.pcd")
    parser.add_argument("--output-dir", type=Path, required=True, help="Destination for CSV and JSON")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    details=[]
    course_file=ROOT/"evidence"/"manual_reference.json"
    if not course_file.is_file():
        parser.error("This two-room comparison uses the course companion's evidence/manual_reference.json. For the self-contained synthetic demonstration, run examples/run_demo.py.")
    course_refs=json.loads(course_file.read_text(encoding="utf8"))["rooms"]
    for room in ("M26","M04"):
        baseline=json.loads((args.baseline_dir/room/"summary.json").read_text(encoding="utf-8-sig"))
        if (baseline["cloud"]["sha256"] != course_refs[room]["sha256"] or baseline["cloud"]["input_unit"] != "m"
                or list(baseline["discovery_config"]["up"]) != [0, 0, 1]):
            raise ValueError(f"Expected the original {room} course scan, in metres with +Z up.")
        data = load_course_cloud(room, baseline, args.cloud_dir)
        p,normals=data[:,:3].astype(float),data[:,3:6].astype(float)
        interior=np.ones(len(p),bool)
        for w in baseline["walls"]:
            interior &= (p-np.array(w["plane_center_m"]))@np.array(w["plane_normal"])>=-.025
        for wall in baseline["walls"]:
            depth_checks(p,wall,baseline["floor"],wall["openings"])
            for opening in wall["openings"]:
                estimates, diag, corners=evaluate(p,normals,wall,baseline["floor"],opening)
                c,n=np.array(wall["plane_center_m"]),np.array(wall["plane_normal"])
                face=p[interior & (abs((p-c)@n)<.008)]
                uv=np.column_stack([(face-c)@section_axis(wall,baseline["floor"]),
                          (face-baseline["floor"]["center_m"])@baseline["floor"]["normal"]])
                contour, contour_audit=estimate_contour(uv,opening)
                details.append(dict(room=room, type=opening["type"],wall=wall["id"],
                                    baseline_mm=[opening["width_mm"],opening["height_mm"]],
                                    surfaces=diag, estimates=estimates,corners_xyz_m=corners,
                                    contour_mm=contour,contour_audit=contour_audit,
                                    sections=[{k:v for k,v in r.items() if not k.endswith("_samples")} for r in opening["depth_sections"]]))
    (args.output_dir/"fit_diagnostics.json").write_text(json.dumps(details,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf8")
    # Compare to the course manual dimensions only after all estimation has finished.
    with (args.output_dir/"same_section.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["room","opening","wall","dimension","manual_mm","profile_mm","profile_error_mm","plane_mm","plane_error_mm","contour_mm","contour_error_mm"])
        for r in details:
            paired=course_refs[r["room"]]["openings_mm"][r["type"]]
            ref=(paired["width"],paired["height"])
            for i,k in enumerate(("width","height")):
                base=r["baseline_mm"][i]; e=r["estimates"][k]; alt=e["span_mm"] if e else None
                contour=r["contour_mm"][k]
                writer.writerow([r["room"],r["type"],r["wall"],k,ref[i],round(base,3),round(base-ref[i],3),
                                 round(alt,3) if e else "",round(alt-ref[i],3) if e else "",
                                 round(contour,3) if contour is not None else "",round(contour-ref[i],3) if contour is not None else ""])
            print(r["room"],r["type"],{k:v["reason"] for k,v in r["surfaces"].items()})

if __name__=="__main__":
    main()
