"""Trace paired reveal-edge samples at successive positive-into-opening depths."""
import numpy as np
from frame_sections import bracket


def examine_depths(u, h, d, o):
    """Keep each strip measurement so a step in the median can be checked on both jambs."""
    corners = np.asarray(o["corners_uv_m"])
    near = ((u >= corners[:, 0].min() - .18) & (u <= corners[:, 0].max() + .18)
            & (h >= o["sill_m"] - .18) & (h <= o["head_m"] + .18) & (d >= -.01) & (d <= 1.41))
    ids = np.flatnonzero(near)
    rows = []
    for depth in range(0, 1401, 5):
        slab = ids[np.abs(d[ids] - depth / 1000) <= .006]
        if len(slab) < 6:
            continue
        row = {"depth_mm": depth}
        for metric, edges, cuts, coord, perp in [
            ("width", ("left_line", "right_line"), ("sill_m", "head_m"), u, h),
            ("height", ("lower_line", "upper_line"), ("left_line", "right_line"), h, u),
        ]:
            spans = []
            for fraction in (.2, .35, .5, .65, .8):
                if metric == "width":
                    at = (1 - fraction) * o[cuts[0]] + fraction * o[cuts[1]]
                    low, high = [o[key]["x_at_1m"] + o[key]["slope"] * (at - 1) for key in edges]
                else:
                    at = (1 - fraction) * o[cuts[0]]["x_at_1m"] + fraction * o[cuts[1]]["x_at_1m"]
                    low, high = [o[key]["h_at_u0"] + o[key]["slope"] * at for key in edges]
                band = slab[np.abs(perp[slab] - at) <= .025]
                result = bracket(coord[band], band, low, high)
                if result:
                    spans.append(result["span_mm"])
                    row[f"{metric}_{fraction:.2f}"] = round(result["span_mm"], 2)
                    row[f"{metric}_low_{fraction:.2f}"] = round(coord[result["first_index"]] * 1000, 2)
                    row[f"{metric}_high_{fraction:.2f}"] = round(coord[result["last_index"]] * 1000, 2)
                    if metric == "width" and fraction == .5:
                        row["mid_left_index"] = result["first_index"]
                        row["mid_right_index"] = result["last_index"]
            row[metric + "_strips"] = len(spans)
            if len(spans) >= 3:
                row[metric + "_median_mm"] = round(float(np.median(spans)), 2)
        if row["width_strips"] or row["height_strips"]:
            rows.append(row)
    return rows


def first_narrower_layer(rows):
    """Detect a step into a second width plateau, without consulting reference dimensions."""
    widths = {r["depth_mm"]: r["width_median_mm"] for r in rows if r.get("width_strips", 0) >= 3}
    for start in sorted(widths):
        preceding = [widths[d] for d in range(start - 30, start - 5, 5) if d in widths]
        levels = list(range(start, start + 21, 5))
        if len(preceding) < 4 or not all(d in widths for d in levels):
            continue
        current = [widths[d] for d in levels]
        if np.ptp(current) <= 5 and np.median(preceding) - np.median(current) >= 30:
            return [r for r in rows if r["depth_mm"] in levels]
    return []


