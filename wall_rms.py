"""Pass geometric corners and eligible original measurements to wall-flatness-v3."""
import json
import numpy as np

from room_geometry import plane, section_axis
from wall_flatness.geometry import inside_polygon
from extensions.native_support import measure


def write_json(path, data):
    def numpy_value(value):
        if isinstance(value,np.ndarray):
            return value.tolist()
        if isinstance(value,np.generic):
            return value.item()
        raise TypeError(f"Cannot serialize measurement type {type(value).__name__}")
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2, default=numpy_value), encoding="utf8")


def wall_pool(points, wall, floor, openings, *, confirmed_only=False):
    assigned = np.asarray(wall["expanded_indices"], dtype=np.int64)
    if not openings:
        return assigned
    center, _ = plane(wall)
    xyz = points[assigned]
    uv = np.column_stack(((xyz-center) @ section_axis(wall,floor),
                          (xyz-floor["center_m"]) @ floor["normal"]))
    keep = np.ones(len(xyz), dtype=bool)
    for opening in openings:
        if confirmed_only and opening.get('status')!='confirmed':continue
        keep &= ~inside_polygon(uv,np.asarray(opening["corners_uv_m"]))
    return assigned[keep]


def measure_scope(output, points, ids, corners, room_name, wall_id, scope, algorithm=measure):
    directory = output/"walls"/wall_id/scope
    directory.mkdir(parents=True, exist_ok=True)
    roi = {"unit":"m","room_id":room_name,"roi_id":f"{wall_id}_{scope}",
           "corners":corners,"slab_half_thickness_mm":None}
    write_json(directory/"roi.json",roi)
    try:
        # The upstream function scales both XYZ and corners together. Both are in metres here.
        measured = algorithm(points[ids],roi)
    except (ValueError, np.linalg.LinAlgError) as error:
        return {"status":"unavailable","reason":str(error),"corners_m":corners,
                "roi_file":(directory/"roi.json").relative_to(output).as_posix()}
    required={"indices","signed_mm","plane_center_m","plane_normal","coverage_fraction","status","warnings"}
    if not isinstance(measured,dict) or not required.issubset(measured):
        raise RuntimeError("RMS backend must return the documented residual, indices, plane, coverage, status and warnings fields.")
    if not isinstance(measured["warnings"],list) or not all(isinstance(w,str) for w in measured["warnings"]):
        raise RuntimeError("RMS backend warnings must be a list of strings.")
    index = np.asarray(measured["indices"])
    residual = np.asarray(measured["signed_mm"],dtype=float)
    if (index.ndim!=1 or index.dtype.kind not in "iu" or len(index)<3 or len(np.unique(index))!=len(index)
            or np.any(index<0) or np.any(index>=len(ids)) or residual.shape!=index.shape or not np.isfinite(residual).all()):
        raise RuntimeError("RMS indices or residuals do not match the current region.")
    center,normal = [np.asarray(measured[k],dtype=float) for k in ("plane_center_m","plane_normal")]
    coverage = measured["coverage_fraction"]
    if (center.shape!=(3,) or normal.shape!=(3,) or not np.isfinite(center).all()
            or not np.isclose(np.linalg.norm(normal),1.,atol=1e-5)
            or measured["status"] not in ("ok","warning") or (coverage is not None and not 0<=coverage<=1)):
        raise RuntimeError("Invalid plane, status or coverage from the RMS algorithm.")
    original = ids[index]
    np.savez_compressed(directory/"residuals.npz",point_index=original,signed_mm=measured["signed_mm"])
    result = {k:measured[k] for k in ("status","coverage_fraction","plane_center_m","plane_normal","warnings")}
    result.update(n_selected=len(index),rms_mm=float(np.sqrt(np.mean(residual**2))),
                  p95_abs_mm=float(np.percentile(np.abs(residual),95)),max_abs_mm=float(np.max(np.abs(residual))))
    result.update(corners_m=corners, roi_file=(directory/"roi.json").relative_to(output).as_posix(),
                  residual_file=(directory/"residuals.npz").relative_to(output).as_posix())
    return result
