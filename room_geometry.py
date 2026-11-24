"""Infer the interior wall junctions of a single approximately rectangular room."""
from itertools import combinations

import numpy as np
from scipy.spatial import cKDTree

from room_walls.planes import extract_planes
from wall_flatness.geometry import inside_polygon


def plane(wall):
    return np.asarray(wall["plane_center_m"]), np.asarray(wall["plane_normal"])


def junction(first, second, level):
    """Intersect two walls with a horizontal structural plane in a local frame."""
    a, na = plane(first)
    b, nb = plane(second)
    origin = np.asarray(level["center_m"])
    normals = np.array([na, nb, level["normal"]])
    targets = [na @ (a - origin), nb @ (b - origin), 0.0]
    return origin + np.linalg.solve(normals, targets)


def section_axis(wall, floor):
    _, normal = plane(wall)
    axis = np.cross(normal, floor["normal"])
    return axis / np.linalg.norm(axis)


def enclosing_walls(walls, floor):
    """Select two mutually transverse pairs of facing walls with observed span."""
    opposite_pairs = []
    for a, b in combinations(walls, 2):
        ca, na = plane(a)
        cb, nb = plane(b)
        if na @ nb < -np.cos(np.deg2rad(20)) and min(na @ (cb-ca), nb @ (ca-cb)) > 0.6:
            opposite_pairs.append((a, b))

    best = None
    best_score = -1
    for (a, b), (c, d) in combinations(opposite_pairs, 2):
        ring = [a, c, b, d]
        if len({w["id"] for w in ring}) < 4:
            continue
        if any(abs(plane(w)[1] @ plane(v)[1]) > np.sin(np.deg2rad(25))
               for w in (a, b) for v in (c, d)):
            continue
        # Vertex i belongs to wall i and its predecessor.
        vertices = np.array([junction(w, ring[i-1], floor) for i, w in enumerate(ring)])
        overlaps = []
        for i, w in enumerate(ring):
            center, normal = plane(w)
            if np.min((vertices-center) @ normal) < -0.04:
                break
            axis = section_axis(w, floor)
            extent = (np.array(w["corners_m"]) - center) @ axis
            lo, hi = np.sort((vertices[[i, (i+1) % 4]] - center) @ axis)
            if hi-lo < 0.6:
                break
            overlaps.append(max(0., min(hi, extent.max())-max(lo, extent.min())) / (hi-lo))
        if len(overlaps) != 4 or min(overlaps) < 0.55:
            continue
        score = sum(w["discovery_support_count"] * f for w, f in zip(ring, overlaps))
        if score > best_score:
            best = (ring, vertices)
            best_score = score
    return best


def room_interior(points, walls, slack=0.025):
    keep = np.isfinite(points).all(axis=1)
    for w in walls:
        center, normal = plane(w)
        keep &= (points-center) @ normal >= -slack
    return keep


def find_ceiling(points, inside, floor, layout, config):
    """Require areal support in the interior to reject the top rim of an open scan."""
    ring, vertices = layout
    up = np.asarray(floor["normal"])
    origin = np.asarray(floor["center_m"])
    q = points[inside]
    if len(q) < config.min_plane_points:
        return None
    heights = (q-origin) @ up
    upper = np.quantile(heights, .995)
    q = q[heights >= upper - max(.35, .2*upper)]
    if len(q) < config.min_plane_points:
        return None
    candidates, _ = extract_planes(q, config)
    u = section_axis(ring[0], floor)
    basis = np.array([u, np.cross(up, u)])
    polygon = (vertices-origin) @ basis.T
    lo, hi = polygon.min(0), polygon.max(0)
    cell = max(0.12, max(hi-lo)/150)
    dims = np.maximum(1, np.ceil((hi-lo)/cell).astype(int))
    grid = np.indices(tuple(dims)).reshape(2,-1).T
    valid_cells = inside_polygon(lo+(grid+.5)*cell, polygon).reshape(tuple(dims))
    best = None
    for p in candidates:
        n, center = p["normal"], p["center"]
        if abs(n @ up) < np.cos(np.deg2rad(config.max_floor_tilt_deg)):
            continue
        if (center-origin) @ up < upper-max(.25,.10*upper):
            continue
        support = q[p["seed_indices"]]
        ij = np.floor(((support-origin) @ basis.T-lo)/cell).astype(int)
        ij = ij[np.all((ij>=0) & (ij<dims),axis=1)]
        occupied = np.zeros(tuple(dims), dtype=bool)
        occupied[ij[:,0],ij[:,1]] = True
        coverage = float(np.sum(occupied & valid_cells)/max(1,valid_cells.sum()))
        if coverage < .35 or (best and coverage <= best["footprint_coverage"]):
            continue
        best = {"center_m":center.tolist(), "normal":(n if n @ up > 0 else -n).tolist(),
                "footprint_coverage":coverage, "discovery_points":len(support)}
    return best


def structural_corners(points, layout, floor, ceiling):
    ring, bottom = layout
    top = np.array([junction(w, ring[i-1], ceiling) for i,w in enumerate(ring)])
    heights = (top-np.asarray(floor["center_m"])) @ floor["normal"]
    if np.any(heights <= 0):
        raise ValueError("The floor and ceiling intersections have inconsistent order.")
    vertices = {}
    for i, w in enumerate(ring):
        j = (i+1) % 4
        left, right = (i,j) if (bottom[j]-bottom[i]) @ section_axis(w,floor) > 0 else (j,i)
        xyz = np.array([bottom[left],bottom[right],top[right],top[left]])
        original = w["expanded_indices"]
        distance, nearest = cKDTree(points[original]).query(xyz)
        corners = []
        for vertex, idx, gap in zip(xyz,original[nearest],distance):
            corners.append({"xyz_m":vertex.tolist(), "nearest_wall_point_index":int(idx),
                            "nearest_wall_point_xyz_m":points[idx].tolist(),
                            "nearest_distance_mm":float(gap*1000),
                            "extrapolated_over_50mm":bool(gap>.05)})
        vertices[w["id"]] = corners
    edges = np.linalg.norm(np.roll(bottom,-1,axis=0)-bottom, axis=1)
    spans = sorted([(edges[0]+edges[2])/2, (edges[1]+edges[3])/2], reverse=True)
    room = {"length_mm":float(spans[0]*1000),"width_mm":float(spans[1]*1000),
            "height_mm":float(np.mean(heights)*1000),"floor_vertices_m":bottom.tolist(),
            "ceiling_vertices_m":top.tolist(),"boundary_wall_ids":[w["id"] for w in ring]}
    return vertices, room


def room_boundaries(points, discovery, config):
    floor, candidates = discovery["floor"], discovery["walls"]
    layout = enclosing_walls(candidates, floor)
    ring = layout[0] if layout else []
    inside = room_interior(points, ring)
    ceiling = find_ceiling(points, inside, floor, layout, config) if layout else None
    corners, room, warnings = {}, None, []
    if not layout:
        warnings.append("Four sufficiently supported enclosing walls were unavailable. Review the room boundary.")
    elif ceiling is None:
        warnings.append("Insufficient ceiling observations for the two upper wall corners.")
    else:
        try:
            corners, room = structural_corners(points, layout, floor, ceiling)
        except (ValueError,np.linalg.LinAlgError) as error:
            warnings.append(str(error))
    return {"walls":sorted(ring or candidates,key=lambda w:w["id"]), "inside_ids":np.flatnonzero(inside),
            "ceiling":ceiling,"corners":corners,"room":room,"warnings":warnings}
