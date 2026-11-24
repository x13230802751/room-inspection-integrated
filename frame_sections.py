"""Independent depth sections for checking visible frame edges around a detected opening."""
import numpy as np

from room_geometry import plane, section_axis


def bracket(values, ids, low, high):
    """Bracket the middle of the expected opening, requiring local support on both sides."""
    middle = (low+high)/2
    a = np.flatnonzero((values<middle) & (values>=low-.18))
    b = np.flatnonzero((values>middle) & (values<=high+.18))
    if len(a)<3 or len(b)<3:
        return None
    i, j = a[np.argmax(values[a])], b[np.argmin(values[b])]
    x, y = values[i], values[j]
    if abs(x-low)>.12 or abs(y-high)>.12 or y-x<.35:
        return None
    if np.sum(values[a]>=x-.080)<3 or np.sum(values[b]<=y+.080)<3:
        return None
    return {"span_mm":float(1000*(y-x)), "first_index":int(ids[i]), "last_index":int(ids[j])}


def depth_checks(points, wall, floor, openings):
    if not openings:
        return
    center, normal = plane(wall)
    up = np.asarray(floor["normal"])
    finite = np.flatnonzero(np.isfinite(points).all(axis=1))
    d = (points[finite]-center) @ normal
    near = (d>=-.207) & (d<=.047)
    d,ids = d[near],finite[near]
    u = (points[ids]-center) @ section_axis(wall,floor)
    h = (points[ids]-floor["center_m"]) @ up
    for o in openings:
        corners = np.asarray(o["corners_uv_m"])
        bounds = (u>=min(corners[:,0])-.18)&(u<=max(corners[:,0])+.18)&(h>=o["sill_m"]-.18)&(h<=o["head_m"]+.18)
        x,z,t,ix = u[bounds],h[bounds],d[bounds],ids[bounds]
        rows = []
        for depth_mm in range(-200,41,20):
            depth = abs(t-depth_mm/1000)<=.006
            if depth.sum()<6:
                continue
            x0,z0,i0 = x[depth],z[depth],ix[depth]
            widths,heights = [],[]
            for fraction in (.2,.35,.5,.65,.8):
                level = o["sill_m"]+fraction*(o["head_m"]-o["sill_m"])
                a,b = [o[k]["x_at_1m"]+o[k]["slope"]*(level-1) for k in ("left_line","right_line")]
                band = abs(z0-level)<=.025
                found = bracket(x0[band],i0[band],a,b)
                if found:
                    widths.append(dict(height_m=float(level),**found))
                col = (1-fraction)*o["left_line"]["x_at_1m"]+fraction*o["right_line"]["x_at_1m"]
                low,high = [o[k]["h_at_u0"]+o[k]["slope"]*col for k in ("lower_line","upper_line")]
                band = abs(x0-col)<=.025
                found = bracket(z0[band],i0[band],low,high)
                if found:
                    heights.append(dict(u_m=float(col),**found))
            if len(widths)>=3 or len(heights)>=3:
                def estimate(samples):
                    return float(np.median([s["span_mm"] for s in samples])) if len(samples)>=3 else None
                rows.append({"depth_mm":depth_mm,"width_median_mm":estimate(widths),"height_median_mm":estimate(heights),
                             "width_samples":widths,"height_samples":heights})
        o["depth_sections"] = rows
        checks = {}
        for kind in ("width","height"):
            v = [r[kind+"_median_mm"] for r in rows if r[kind+"_median_mm"] is not None]
            checks[kind+"_spread_mm"] = float(max(v)-min(v)) if len(v)>=2 else None
        o["depth_check"] = checks
