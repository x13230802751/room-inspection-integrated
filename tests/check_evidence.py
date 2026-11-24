"""Verify both course outputs, RMS residuals, method coverage and frame positions."""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"third_party")]
from depth_profile import first_narrower_layer
from room_geometry import section_axis
from wall_flatness.io import read_cloud
from window_sections import candidate_section


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def pair_stats(errors):
    e=np.asarray(errors)
    return [float(np.mean(np.abs(e))),float(np.sqrt(np.mean(e**2)))]


def verify(runs,clouds=None):
    refs=read_json(ROOT/"evidence"/"manual_reference.json")["rooms"]
    summary={r:read_json(runs/r/"summary.json") for r in refs}
    comparison=read_csv(runs/"comparison"/"same_section.csv")
    assert len(comparison)==6
    room_errors=[]; scopes=[]; methods=("profile","plane","contour")
    for room, s in summary.items():
        manual=refs[room]
        assert s["cloud"]["sha256"]==manual["sha256"]
        for k in ("length","width","height"):
            room_errors.append(s["room"][k+"_mm"]-manual["dimensions_mm"][k])
        valid_scopes=0
        for wall in s["walls"]:
            for kind in ("whole",):
                item=wall[kind]
                if "rms_mm" not in item:
                    assert item["status"]=="unavailable"
                    continue
                with np.load(runs/room/item["residual_file"]) as a:
                    rms=np.sqrt(np.mean(a["signed_mm"]**2))
                    assert len(a["point_index"])==len(np.unique(a["point_index"]))==item["n_selected"]
                np.testing.assert_allclose(rms,item["rms_mm"],rtol=0,atol=1e-8)
                valid_scopes+=1
        scopes.append(valid_scopes)
        for row in [r for r in comparison if r["room"]==room]:
            wall=next(w for w in s["walls"] if w["id"]==row["wall"])
            op=next(o for o in wall["openings"] if o["type"]==row["opening"])
            ref=manual["openings_mm"][row["opening"]][row["dimension"]]
            assert int(row["manual_mm"])==ref
            assert abs(op[row["dimension"]+"_mm"]-float(row["profile_mm"]))<.00051
            for method in methods:
                if row[method+"_mm"]:
                    np.testing.assert_allclose(float(row[method+"_mm"])-ref,float(row[method+"_error_mm"]),atol=.0011)
                else:
                    assert row[method+"_error_mm"]==""
    assert scopes==[7,6]
    shared=[r for r in comparison if all(r[m+"_mm"] for m in methods)]
    assert [(r["room"],r["dimension"]) for r in shared]==[("M26","width"),("M26","height"),("M04","height")]
    print("Room dimensions, n = 6. MAE and RMSE (mm)",np.round(pair_stats(room_errors),2))
    for method,n in zip(methods,(6,4,5)):
        errors=[float(r[method+"_error_mm"]) for r in comparison if r[method+"_mm"]]
        assert len(errors)==n
        own=pair_stats(errors)
        if method=="profile": np.testing.assert_allclose(own,[18.32,30.29],atol=.005)
        print(method,n,"of 6. Own and common MAE/RMSE (mm)",np.round(own+pair_stats([float(r[method+"_error_mm"]) for r in shared]),2))
    m26=summary["M26"]; floor=m26["floor"]
    window_file=read_json(runs/"M26"/"window_sections.json")
    assert window_file["cloud_sha256"]==refs["M26"]["sha256"] and window_file["depth_positive"]=="into_opening"
    assert not read_json(runs/"M04"/"window_sections.json")["windows"]
    w,=window_file["windows"]
    face,deep=w["face"],w["deep"]
    wall=next(x for x in m26["walls"] if x["id"]==w["wall_id"])
    axis=section_axis(wall,floor)
    fitted=np.asarray(face["endpoints_xyz_m"])
    np.testing.assert_allclose((fitted-wall["plane_center_m"])@wall["plane_normal"],0,atol=1e-8)
    np.testing.assert_allclose((fitted-floor["center_m"])@floor["normal"],face["height_m"],atol=1e-8)
    np.testing.assert_allclose((fitted[1]-fitted[0])@axis*1000,face["width_mm"],atol=1e-6)
    np.testing.assert_allclose(face["width_mm"],2443.861,atol=.00051)
    rows=[]
    for r in read_csv(runs/"M26"/w["profile_file"]):
        rows.append({k:(int(v) if k in ("depth_mm","width_strips") else float(v)) for k,v in r.items() if v})
    layer=first_narrower_layer(rows)
    assert deep["status"]=="candidate" and deep["depth_range_mm"]==[655,675]
    assert [r["depth_mm"] for r in layer]==list(range(655,676,5))
    widths=[r["width_0.50"] for r in layer]
    np.testing.assert_allclose(widths,deep["mid_height_samples_mm"])
    np.testing.assert_allclose([np.median(widths),np.median([r["width_median_mm"] for r in layer])],[2378.35,2378.03])
    np.testing.assert_allclose([deep["width_mm"],deep["strip_median_width_mm"]],[2378.35,2378.03])
    mid=deep["representative"];ends=mid["endpoints"]
    assert mid["slice_center_depth_mm"]==665 and [e["original_index"] for e in ends]==[428596,401081]
    xyz=np.asarray([e["xyz_m"] for e in ends])
    np.testing.assert_allclose((xyz[1]-xyz[0])@axis*1000,mid["width_mm"],atol=.005)
    for point in ends:
        observed_D=-1000*(np.array(point["xyz_m"])-wall["plane_center_m"])@wall["plane_normal"]
        assert abs(observed_D-point["actual_depth_mm"])<1e-6 and abs(observed_D-665)<=6
        assert abs(point["height_m"]-deep["height_m"])<=.025
    if clouds:
        raw,digest=read_cloud(str(clouds/"M26.pcd"),with_hash=True)
        assert digest==window_file["cloud_sha256"]
        np.testing.assert_allclose(raw[[428596,401081]],xyz,rtol=0,atol=1e-9)
    # Different missing-data branches cannot generate an apparently valid frame width.
    assert candidate_section([],1,None,None,None,None)["status"]=="no_stable_layer"
    sparse=[dict(r) for r in rows]
    next(r for r in sparse if r["depth_mm"]==665).pop("width_0.50")
    gap=candidate_section(sparse,1,None,None,None,None)
    assert gap["status"]=="insufficient_mid_height" and gap["width_mm"] is None and gap["representative"] is None
    print("Reproduced 13 RMS scopes, both window positions, the source-row pair and both unavailable states.")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs",type=Path,default=ROOT/"evidence")
    p.add_argument("--cloud-dir",type=Path)
    a=p.parse_args()
    verify(a.runs,a.cloud_dir)
