"""Create the portable result page and metric wall elevations."""
from html import escape

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure



def plot_wall(output, xyz, wall, floor, result):
    from room_geometry import plane, section_axis
    center, _ = plane(wall)
    u = section_axis(wall, floor)
    up = np.asarray(floor["normal"])
    floor_center = np.asarray(floor["center_m"])

    def project(xyz):
        q = np.asarray(xyz)
        return np.column_stack(((q-center) @ u, (q-floor_center) @ up))

    fig = Figure(figsize=(6.8, 3.9), dpi=125, layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    if len(xyz)>12000:
        xyz = xyz[np.random.default_rng(7023).choice(len(xyz),12000,replace=False)]
    uv = project(xyz)
    ax.scatter(uv[:,0], uv[:,1], s=1, color="#899ca9", alpha=.5, linewidths=0)

    def poly(vertices, color, style="-", label=None):
        p = np.asarray(vertices)
        loop = np.vstack((p,p[0]))
        ax.plot(loop[:,0], loop[:,1], style, lw=2.1, color=color)
        if label:
            ax.text(*p.mean(0), label, color=color, ha="center", va="center", fontsize=9,
                    bbox={"facecolor":"white","edgecolor":"none","alpha":.85,"pad":1.8})

    if result["structural_corners"]:
        vertices = project([c["xyz_m"] for c in result["structural_corners"]])
        poly(vertices, "#24465b")
        unsupported = [i for i,c in enumerate(result["structural_corners"]) if c["extrapolated_over_50mm"]]
        if unsupported:
            ax.scatter(vertices[unsupported,0], vertices[unsupported,1], s=48, facecolors="white",
                       edgecolors="#a22c32", lw=1.8, zorder=4)
        for label, (x,y) in zip("ABCD",vertices):
            ax.annotate(label,(x,y),xytext=(3,3),textcoords="offset points",color="#123244",fontsize=8)
    for o in result["openings"]:
        poly(o["corners_uv_m"], "#ad4a0a" if o["type"]=="door" else "#006a83",label=o["id"])
    ax.axhline(0, lw=.5, color="#b8c4ca", zorder=0)
    ax.set(xlabel="Along wall, u (m)", ylabel="Height above floor (m)", aspect="equal")
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(colors="#495960", labelsize=8)
    ax.margins(.07, .12)
    directory = output/"walls"/wall["id"]
    directory.mkdir(parents=True, exist_ok=True)
    image = directory/"elevation.png"
    fig.savefig(image, facecolor="white")
    fig.clear()
    return image.relative_to(output).as_posix()


STYLE = """
:root{font:16px/1.55 "Segoe UI",sans-serif;color:#1a3441;background:#f1f5f5}
*{box-sizing:border-box}body{max-width:1140px;margin:auto;padding:2.5rem 1.5rem 4rem}
h1,h2,h3,p{margin:0 0 .6rem}h1{font-size:clamp(2rem,4vw,3rem);line-height:1.16}
h2{font-size:1.35rem}h3{font-size:1.07rem}header,section,article{margin-bottom:1.3rem}
section,article{background:white;border:1px solid #d6e1e2;border-radius:12px;padding:1.1rem 1.4rem}
header{border-top:5px solid #136269;padding-top:1rem}nav{display:flex;gap:1rem;flex-wrap:wrap}
a{color:#075e71;text-underline-offset:3px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:.44rem .6rem;border-bottom:1px solid #e1e8e8;white-space:nowrap}
th{font-size:.85rem;color:#42606a;font-weight:600}.scroll{overflow-x:auto}.muted{color:#51646b}
.caution{background:#fff1d4;color:#703f0a;padding:.5rem .7rem;border-radius:5px}
.wall{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(230px,1fr);gap:1rem;align-items:center}
img{width:100%;height:auto}summary{cursor:pointer;color:#075e71}.n{font-variant-numeric:tabular-nums}
@media(max-width:720px){body{padding:1rem .6rem}.wall{grid-template-columns:1fr}section,article{padding:.9rem}}
@media print{body{padding:0;background:white}article,section{break-inside:avoid}nav{display:none}}
"""


def make_report(output, summary, sections):
    def e(value):
        return escape(str(value),quote=True)
    def link(path, label):
        return f'<a href="{e(path)}">{e(label)}</a>'
    def table(labels, rows):
        head="".join(f"<th>{e(label)}</th>" for label in labels)
        body="".join("<tr>"+"".join(f"<td>{e(x)}</td>" for x in r)+"</tr>" for r in rows)
        return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    def n(value,digits=2):
        return "—" if value is None else f"{value:.{digits}f}"
    cloud=summary["cloud"]
    walls=summary["walls"]
    title=e(cloud["file"])+" · Room inspection"
    parts=[f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{STYLE}</style><body><header><h1>{title}</h1>',
           f'<p>{cloud["point_count"]:,} points · {len(walls)} walls · {e(summary["algorithms"]["name"])}</p>',
           '<nav><a id="word" href="report.docx" download>Download Word report</a>']
    for name,label in (("openings.csv","Openings"),("wall_corners.csv","Wall corners"),("wall_rms.csv","Wall RMS"),
                       ("frame_depths.csv","Shallow sections"),("window_sections.json","Window positions"),("summary.json","Full result")):
        parts.append(link(name,label))
    parts.append("</nav></header>")
    if summary["room"]:
        r=summary["room"]
        parts.append("<section><h2>Room dimensions</h2><p>"+" · ".join(f'{k.capitalize()} {n(r[k+"_mm"])} mm' for k in ("length","width","height"))+"</p></section>")
    for msg in summary["warnings"]: parts.append(f'<p class="caution">{e(msg)}</p>')
    parts.append("<section><h2>Wall-face openings</h2>")
    ops=[o for w in walls for o in w["openings"]]
    if ops:
        parts.append(table(["ID","Type","Width (mm)","Height (mm)","Width level (m)","Sill (m)"],
                           [[o["id"],o["type"],n(o["width_mm"]),n(o["height_mm"]),n(o["width_at_height_m"],4),n(o["sill_m"],4)] for o in ops]))
        for o in ops:
            parts.append(f'<details><summary>{e(o["id"])} · Shallow depth checks</summary><p>Positive depth is towards the room in this table.</p>')
            parts.append(table(["Depth (mm)","Width median (mm)","Supported strips","Height median (mm)","Supported columns"],
                               [[s["depth_mm"],n(s["width_median_mm"]),len(s["width_samples"]),n(s["height_median_mm"]),len(s["height_samples"])] for s in o["depth_sections"]]))
            parts.append("</details>")
    else: parts.append("<p>No supported opening was found.</p>")
    parts.append("</section>")
    if sections.get("availability")=="not_recorded":
        parts.append("<p>This saved inspection predates the separate window-depth record.</p>")
    for item in sections["windows"]:
        face,deep=item["face"],item["deep"]
        parts.append(f'<section><h2>{e(item["opening_id"])} · Window width by position</h2><p>Here D increases from the interior face into the opening. Width is projected along the wall.</p>')
        depths=deep["depth_range_mm"]
        parts.append(table(["Section","D (mm)","Height (m)","Width (mm)","Support"],
                           [["Wall-face aperture","0",n(face["height_m"],4),n(face["width_mm"],3),"Fitted endpoints"],
                            ["Recessed frame candidate","—" if not depths else f"{depths[0]}–{depths[1]}",n(deep["height_m"],4),n(deep["width_mm"]),deep["status"].replace("_"," ")]]))
        parts.append(link(item["profile_file"],"Original-point depth profile")+"</section>")
    parts.append("<section><h2>Wall flatness</h2>"+table(["Wall","Whole RMS (mm)","Support points"],
                 [[w["id"],n(w["whole"].get("rms_mm"),3),w["assigned_points"]] for w in walls])+"</section>")
    if summary.get('recovery')=='none':
        parts.append('<p>Whole-wall RMS uses original supports within the structural corners, excluding detected opening footprints. Opening outlines still require physical verification. No 50 mm recovery band or RMS slab is used.</p>')
    for w in walls:
        parts.append(f'<article><h2>{e(w["id"])}</h2><div class="wall"><img src="{e(w["elevation_file"])}" alt="{e(w["id"])} wall elevation"><div>')
        parts.append(table(["Corner","X (m)","Y (m)","Z (m)","Nearest point (mm)"],
                           [[l,*[n(t,3) for t in c["xyz_m"]],n(c["nearest_distance_mm"],1)] for l,c in zip("ABCD",w["structural_corners"])]))
        for scope in ("whole",):
            item=w[scope]
            if item.get("roi_file"):
                links=[link(item["roi_file"],scope.capitalize()+" footprint")]
                if item.get("residual_file"):
                    links.append(link(item["residual_file"],"Residuals and source rows"))
                parts.append("<p>"+" · ".join(links)+"</p>")
            if item.get("reason"): parts.append("<p>"+e(item["reason"])+"</p>")
            if item.get("warnings"): parts.append("<p>"+e(", ".join(item["warnings"]))+"</p>")
        parts.append("</div></div></article>")
    parts.append("""<script>if(new URLSearchParams(location.search).get('word')==='1'){history.replaceState(null,'',location.pathname);document.getElementById('word').click();}</script></body></html>""")
    (output/"report.html").write_text("\n".join(parts),encoding="utf8")


