"""Bridge current cloud geometry to the validated door/window profile detector."""
import json
from pathlib import Path
import subprocess

import numpy as np
from room_geometry import plane, section_axis


def wall_profile(points, inside_ids, wall, floor, ceiling_corners):
    center, normal = plane(wall)
    floor_center = np.asarray(floor["center_m"])
    up = np.asarray(floor["normal"])
    axis = section_axis(wall, floor)
    ids = inside_ids[np.abs((points[inside_ids]-center) @ normal) < .008]
    u = (points[ids]-center) @ axis
    h = (points[ids]-floor_center) @ up
    # Bound the search to the finite wall, including jambs excluded from plane assignments.
    limits = np.array(ceiling_corners or wall["corners_m"])
    width_limits = (limits-center) @ axis
    height_limit = np.max((limits-floor_center) @ up) + .10
    keep = (u >= width_limits.min()-.025) & (u <= width_limits.max()+.025) & (h >= -.025) & (h <= height_limit)
    return np.column_stack([u[keep],h[keep],ids[keep]]).astype("<f8",copy=False)


def profile_candidates(points, inside_ids, wall, floor, corners, node):
    if not node:
        raise ValueError("The default opening detector requires Node.js. Set TASK1_NODE to its executable if needed.")
    corner_xyz = [c["xyz_m"] for c in corners] if corners else None
    profile = wall_profile(points, inside_ids, wall, floor, corner_xyz)
    process = subprocess.run([node,str(Path(__file__).with_name("detect_profile.cjs"))],
                             input=profile.tobytes(), capture_output=True)
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf8",errors="replace").strip() or "The opening detector failed.")
    response = json.loads(process.stdout)
    return response["openings"], response["candidates"]


def apply_opening_detector(points, inside_ids, wall, floor, corners, node):
    items, diagnostics = profile_candidates(points, inside_ids, wall, floor, corners, node)
    return position_openings(items, wall, floor), diagnostics


def position_openings(items, wall, floor):
    """Complete an alternative detector's four wall-local vertices in the common frame."""
    center, normal = plane(wall)
    up = np.asarray(floor["normal"])
    axis = section_axis(wall,floor)
    tilt = up @ normal
    vertical = (up-tilt*normal)/(1-tilt**2)
    center_height = (center-floor["center_m"]) @ up

    def world(point):
        u,h = point
        return (center + u*axis + (h-center_height)*vertical).tolist()

    for i,o in enumerate(items,1):
        q = np.asarray(o["corners_uv_m"],dtype=float)
        if o["type"] not in ("door","window") or q.shape!=(4,2) or not np.isfinite(q).all():
            raise ValueError("An opening requires a door or window type and four finite wall-local 2D vertices.")
        a,b,c,d = q
        if min(b[0]-a[0],c[0]-d[0],d[1]-a[1],c[1]-b[1])<=1e-8:
            raise ValueError("Supply the lower-left, lower-right, upper-right and upper-left elevation vertices in order.")
        def side(first,last):
            slope=(last[0]-first[0])/(last[1]-first[1])
            return {"slope":float(slope),"x_at_1m":float(first[0]+(1-first[1])*slope)}
        def cross(first,last):
            slope=(last[1]-first[1])/(last[0]-first[0])
            return {"slope":float(slope),"h_at_u0":float(first[1]-first[0]*slope)}
        left,right = side(a,d),side(b,c)
        low,high = cross(a,b),cross(d,c)
        u = float(q[:,0].mean())
        sill,head = [edge["h_at_u0"]+edge["slope"]*u for edge in (low,high)]
        mid = (sill+head)/2
        level = float(o.get("width_at_height_m",1. if o["type"]=="door" else mid))
        if not sill<level<head:
            raise ValueError("The requested width elevation falls outside the opening.")
        span = (right["x_at_1m"]-left["x_at_1m"])+(level-1)*(right["slope"]-left["slope"])
        o.update(corners_uv_m=q.tolist(),center_uv_m=[u,mid],sill_m=sill,head_m=head,
                 width_at_height_m=level,width_mm=1000*span,height_mm=1000*(head-sill),
                 left_line=left,right_line=right,upper_line=high,lower_line=low)
        o.update(wall=wall["id"], id=f"{wall['id']}-{i:02d}", center_xyz_m=world(o["center_uv_m"]),
                 corners_xyz_m=[world(p) for p in o["corners_uv_m"]])
    return items
