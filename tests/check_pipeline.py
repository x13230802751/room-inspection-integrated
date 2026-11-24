"""Independent audits of real outputs and rotated synthetic rooms with and without ceilings."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"third_party"))
import numpy as np
from wall_flatness.io import read_cloud


def audit(source, output):
    data = json.loads((output/"summary.json").read_text(encoding="utf8"))
    if "word_report" in data:
        from docx import Document
        report = output/data["word_report"]
        with ZipFile(report) as package:
            assert package.testzip() is None
        doc=Document(report)
        assert len(doc.inline_shapes)==len(data["walls"])+1
        cells={c.text for table in doc.tables for row in table.rows for c in row.cells}
        for algorithm in data["algorithms"]["stages"].values():
            assert algorithm["call"] in cells
        for wall in data["walls"]:
            for o in wall["openings"]:
                assert f'{o["width_mm"]:.2f}' in cells and f'{o["height_mm"]:.2f}' in cells
            for region in (wall["whole"],):
                if "rms_mm" in region:
                    assert f'{region["rms_mm"]:.3f}' in cells
    xyz, digest = read_cloud(str(source),with_hash=True)
    assert digest==data["cloud"]["sha256"]
    if data["cloud"]["input_unit"]=="mm":
        xyz *= .001
    floor,ceiling = data["floor"],data["ceiling"]
    wall_planes = [(np.asarray(w["plane_center_m"]),np.asarray(w["plane_normal"])) for w in data["walls"]]
    totals,all_corners = 0,[]
    with np.load(output/"wall_points.npz") as pools:
        for w in data["walls"]:
            corners = np.asarray([p["xyz_m"] for p in w["structural_corners"]])
            wid = w["id"]
            assigned,eligible = pools[wid+"_assigned"],pools[wid+"_eligible"]
            assert np.isin(eligible,assigned).all() and np.isfinite(xyz[assigned]).all()
            assert len(assigned)-len(eligible)==w["excluded_opening_points"]
            if len(corners):
                assert corners.shape==(4,3)
                all_corners.extend(corners)
                for i,(p,item) in enumerate(zip(corners,w["structural_corners"])):
                    level = floor if i<2 else ceiling
                    assert abs((p-level["center_m"]) @ level["normal"])<1e-7
                    assert sum(abs((p-c) @ n)<1e-7 for c,n in wall_planes)>=2
                    raw = item["nearest_wall_point_index"]
                    assert raw in assigned
                    np.testing.assert_allclose(xyz[raw],item["nearest_wall_point_xyz_m"],atol=1e-9)
                    assert abs(np.linalg.norm(p-xyz[raw])*1000-item["nearest_distance_mm"])<1e-5
            for o in w["openings"]:
                p = np.asarray(o["corners_xyz_m"])
                assert p.shape==(4,3)
                assert np.max(np.abs((p-w["plane_center_m"]) @ w["plane_normal"]))<1e-7
                assert o["width_mm"]>0 and o["height_mm"]>0
                for group in o["depth_sections"]:
                    for direction in ("width","height"):
                        samples = group[direction+"_samples"]
                        if len(samples)>=3:
                            assert abs(np.median([s["span_mm"] for s in samples])-group[direction+"_median_mm"])<1e-7
                        for s in samples:
                            assert 0<=s["first_index"]<len(xyz) and 0<=s["last_index"]<len(xyz)
            for k in ("whole",):
                result = w[k]
                if result["status"]=="unavailable":
                    assert "rms_mm" not in result
                    continue
                roi = json.loads((output/result["roi_file"]).read_text(encoding="utf8"))
                if k=="whole":
                    np.testing.assert_allclose(roi["corners"],corners)
                with np.load(output/result["residual_file"]) as residual:
                    idx = residual["point_index"]
                    assert len(np.unique(idx))==len(idx)==result["n_selected"] and np.isin(idx,eligible).all()
                    p = xyz[idx]
                    q = p-p.mean(axis=0)
                    eigenvalues = np.linalg.eigvalsh(q.T @ q/len(p))
                    independent = np.sqrt(max(0.,eigenvalues[0]))*1000
                    assert abs(independent-result["rms_mm"])<1e-5
                    signed = (p-result["plane_center_m"]) @ result["plane_normal"] * 1000
                    np.testing.assert_allclose(signed,residual["signed_mm"],atol=1e-6)
                    totals += 1
    if all_corners:
        assert len(np.unique(np.round(all_corners,6),axis=0))==8
    print(f'{data["cloud"]["file"]}: {len(data["walls"])} walls, {totals} RMS selections independently reproduced',flush=True)
    return data


def synthetic(path, with_ceiling, *, recessed=False):
    rng = np.random.default_rng(43)
    side = [np.arange(n+1)*.02 for n in (210,160,135)]
    pieces = [np.full((1,3),np.nan)]
    for axis, high in [(0,False),(0,True),(1,False),(1,True),(2,False),(2,True)]:
        if axis==2 and high and not with_ceiling:
            continue
        free = [i for i in range(3) if i!=axis]
        a,b = np.meshgrid(*[side[i] for i in free],indexing="ij")
        p = np.zeros((a.size,3))
        p[:,free[0]],p[:,free[1]] = a.ravel(),b.ravel()
        p[:,axis] = side[axis][-1] if high else 0
        x,y,z = p.T
        if with_ceiling and axis==1 and not high:
            p = p[~((((x>.50001)&(x<1.39999))|((x>2.10001)&(x<3.09999))) & (z<2.11999))]
        if with_ceiling and axis==0 and high:
            p = p[~((y>.70001)&(y<2.19999)&(z>.64001)&(z<1.93999))]
        p[:,axis] += rng.normal(0,.00035,len(p))
        pieces.append(p)
    if recessed:
        # Add the two sides of a synthetic reveal beyond the x = 4.2 m wall.
        # At 160 mm the two jambs each step inward by 30 mm.
        depths, heights = np.meshgrid(np.arange(40,231,5)/1000, np.arange(640,1941,10)/1000)
        depths, heights = depths.ravel(), heights.ravel()
        inset = np.where(depths >= .16, .03, 0.)
        for jamb in (.70+inset, 2.20-inset):
            pieces.append(np.column_stack([4.2+depths, jamb, heights]))
    p = np.vstack(pieces)
    t = np.deg2rad(31)
    matrix = np.array([[np.cos(t),-np.sin(t),0],[0,0,1],[-np.sin(t),-np.cos(t),0]])
    xyz_mm = (p @ matrix.T+[35.2,-74.7,16])*1000
    np.savetxt(path,xyz_mm,delimiter=",",header="x,y,z",comments="",fmt="%.5f")


def smoke():
    with TemporaryDirectory(prefix="task1-test-") as temporary:
        top = Path(temporary)
        for with_ceiling,name in ((True,"two-doors"),(False,"open-top")):
            source, output = top/(name+".csv"),top/name
            synthetic(source,with_ceiling)
            cmd = [sys.executable,str(ROOT/"inspect_room.py"),str(source),"--unit","mm","--up","0","1","0","--out",str(output)]
            subprocess.run(cmd,check=True)
            data = audit(source,output)
            assert len(data["walls"])==4 and data["cloud"]["invalid_rows"]==1
            openings = [o for wall in data["walls"] for o in wall["openings"]]
            if with_ceiling:
                doors = [o for o in openings if o["type"]=="door"]
                windows = [o for o in openings if o["type"]=="window"]
                assert len(doors)==2 and len(windows)==1 and doors[0]["wall"]==doors[1]["wall"]
                np.testing.assert_allclose(sorted(o["width_mm"] for o in doors),[900,1000],atol=25)
                np.testing.assert_allclose([o["height_mm"] for o in doors],[2120,2120],atol=25)
                np.testing.assert_allclose([windows[0]["width_mm"],windows[0]["height_mm"]],[1500,1300],atol=25)
                assert all(len(w["structural_corners"])==4 and "rms_mm" in w["whole"] for w in data["walls"])
            else:
                assert not openings and data["ceiling"] is None and data["room"] is None
                assert all(not w["structural_corners"] and w["whole"]["status"]=="unavailable" for w in data["walls"])
            before = hashlib.sha256((output/"summary.json").read_bytes()).digest()
            assert subprocess.run(cmd,capture_output=True).returncode!=0
            assert hashlib.sha256((output/"summary.json").read_bytes()).digest()==before


if __name__=="__main__":
    if len(sys.argv)==3:
        audit(sys.argv[1],Path(sys.argv[2]))
    else:
        smoke()
