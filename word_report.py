"""Export a reusable English single-room inspection report."""
from pathlib import Path
from course_reference import matched_reference
from report_style import document, figure, heading, table

FLOW = Path(__file__).parent / "assets" / "measurement_workflow.png"


def fmt(x, digits=2):
    return "—" if x is None else f"{x:.{digits}f}"


def write_word_report(output, data, sections):
    doc = document("Room point cloud inspection")
    cloud, walls = data["cloud"], data["walls"]
    ref = data["manual_reference"] if "manual_reference" in data else matched_reference(data)
    doc.add_paragraph("Room point cloud inspection", "Title")
    doc.add_paragraph(f'{cloud["file"]} contains {cloud["point_count"]:,} input points. The {data["algorithms"]["name"]} profile reported {len(walls)} walls.')
    heading(doc,"1  Dimensions and surface flatness")
    room=data["room"]
    if room:
        rows=[]
        for key in ("length","width","height"):
            value=room[key+"_mm"]; manual=ref["dimensions_mm"][key] if ref else None
            rows.append([key.capitalize(),fmt(value),fmt(manual),fmt(value-manual) if manual is not None else "—"])
        table(doc,"Table 1  Interior room dimensions (mm)",["Dimension","Scan","Manual","Scan − manual"],rows,[3,2,2,2.5],(1,2,3))
    else:
        doc.add_paragraph("A supported floor-to-ceiling enclosure was unavailable.")
    ops=[o for w in walls for o in w["openings"]]
    if ops:
        rows=[]
        for o in ops:
            manual=ref["openings_mm"].get(o["type"]) if ref and sum(a["type"]==o["type"] for a in ops)==1 else None
            rows.append([o["id"],o["type"].capitalize(),fmt(o["width_at_height_m"],3),fmt(o["width_mm"]),fmt(o["height_mm"]),
                         f'{manual["width"]} × {manual["height"]}' if manual else "—"])
        table(doc,"Table 2  Wall-face openings",["ID","Type","Width level (m)","Width (mm)","Height (mm)","Manual W × H (mm)"],
              rows,[1.35,1.1,1.35,1.35,1.35,1.9],(2,3,4,5))
        doc.add_paragraph("Width is projected along the local wall axis at the listed elevation above the floor. Height is taken at the centreline. The default detector fits the visible edges within 8 mm of the wall plane.")
    else:
        doc.add_paragraph("The detector found no openings with sufficient edge support.")
    table(doc,"Table 3  Whole-wall RMS",
          ["Wall","Whole RMS (mm)","Support points"],
          [[w["id"],fmt(w["whole"].get("rms_mm"),3),w["assigned_points"]] for w in walls],
          [1.5,3,3],(1,2))
    if data.get('recovery')=='none':
        doc.add_paragraph('Whole-wall RMS uses original Efficient RANSAC support points inside the structural corners. No denoising, nearby-point recovery or normal-distance slab is used. The partner pipeline excludes detected opening footprints from whole-wall measurement points; opening identities require physical verification.')
    if ref:
        r=ref["rms"]
        doc.add_paragraph(f'Manual RMS is {r["value_mm"]:.1f} mm. {r["wall_description"]}. The measured footprint in the photograph or field notes has no recorded corner coordinates.')
    for warning in data["warnings"]: doc.add_paragraph(warning)
    if sections.get("availability")=="not_recorded":
        doc.add_paragraph("This saved inspection predates the separate window-depth record.")
    if sections["windows"]:
        heading(doc,"2  Window measurement positions",new_page=True)
        for w in sections["windows"]:
            a,b=w["face"],w["deep"]
            doc.add_heading(w["opening_id"],level=2)
            doc.add_paragraph("Depth D starts at the fitted interior wall face and increases into the opening. The face endpoints are intersections on the fitted plane. The recessed search tests paired original edge returns in 12 mm thick depth slices.")
            rows=[["Wall-face aperture","0",fmt(a["height_m"],4),fmt(a["width_mm"],3),"Fitted jambs"]]
            rng=b["depth_range_mm"]
            rows.append(["Recessed candidate",f"{rng[0]}–{rng[1]}" if rng else "—",fmt(b["height_m"],4),fmt(b["width_mm"]),
                         b["status"].replace("_"," ")])
            table(doc,"Window width by physical section",["Position","D (mm)","Height (m)","Width (mm)","Evidence"],rows,[2.05,1.25,1.35,1.55,1.75],(1,2,3))
            for side,xyz in zip(("Left","Right"),a["endpoints_xyz_m"]):
                doc.add_paragraph(f'{side} fitted wall-face endpoint (XYZ in m)  '+", ".join(fmt(x,4) for x in xyz))
            if b["representative"]:
                example=b["representative"]; left,right=example["endpoints"]
                doc.add_paragraph(f'At D = {example["slice_center_depth_mm"]} mm, original rows {left["original_index"]} and {right["original_index"]} span {example["width_mm"]:.2f} mm in projection. The primary recessed width is the median of five mid-height widths. The separate median across supported height strips and depths is {b["strip_median_width_mm"]:.2f} mm.')
            m=ref["openings_mm"].get("window",{}).get("width") if ref and len(sections["windows"])==1 else None
            if m is not None:
                extra=f' and {b["width_mm"]-m:+.2f} mm at the recessed candidate' if b["width_mm"] is not None else ""
                doc.add_paragraph(f'The manual width of {m} mm gives {a["width_mm"]-m:+.3f} mm at the wall face{extra}. The tape depth and contact points were not recorded.')
    for i,w in enumerate(walls,1):
        heading(doc,f'{w["id"]}  Wall elevation and original-point support',new_page=True)
        figure(doc,output/w["elevation_file"],f'Figure {i}  {w["id"]} in wall-local coordinates.',width=5.4)
        doc.add_paragraph("The navy outline joins structural corners A–D. Orange and teal mark doors and windows. A red circle marks a corner farther than 50 mm from its nearest observed wall point.")
        if w["structural_corners"]:
            table(doc,"Structural corners and nearest assigned wall samples",["Corner","X (m)","Y (m)","Z (m)","Gap (mm)","Original row"],
                  [[key,*[fmt(t,3) for t in c["xyz_m"]],fmt(c["nearest_distance_mm"],1),c["nearest_wall_point_index"]] for key,c in zip("ABCD",w["structural_corners"])],
                  [1.2,1.25,1.25,1.25,1.5,1.6],(1,2,3,4,5))
        if w["openings"]:
            locations=[]
            for o in w["openings"]:
                for name,point in zip(("Centre","A","B","C","D"),[o["center_xyz_m"],*o["corners_xyz_m"]]):
                    locations.append([o["id"],name,*(fmt(t,4) for t in point)])
            table(doc,"Fitted opening centres and corners in scan coordinates",["Opening","Point","X (m)","Y (m)","Z (m)"],locations,[1.6,1.3,1.7,1.7,1.7],(2,3,4))
        footprints=[]
        for scope in ("whole",):
            roi=w[scope]
            coverage=roi.get("coverage_fraction")
            footprints.append([scope.capitalize(),fmt(roi.get("rms_mm"),3),fmt(roi.get("p95_abs_mm"),3),
                               "—" if coverage is None else f"{coverage:.1%}",roi["status"]])
        table(doc,"Flatness and observed coverage for this wall",["Region","RMS (mm)","Abs. P95 (mm)","Coverage","Status"],
              footprints,[1.3,1.5,1.9,1.6,1.7],(1,2,3))
        for key in ("whole",):
            item=w[key]
            if item.get("reason"): doc.add_paragraph(key.capitalize()+" footprint. "+item["reason"])
            elif item.get("warnings"): doc.add_paragraph(key.capitalize()+" footprint flags include "+", ".join(item["warnings"])+".")
    heading(doc,"Methods and reproduction",new_page=True)
    figure(doc,FLOW,f'Figure {len(walls)+1}  From a room scan to traceable measurements.',width=6.0)
    table(doc,"Algorithm entry points used for this scan",["Stage","Callable"],
          [[stage,details["call"]] for stage,details in data["algorithms"]["stages"].items()],[1.8,6.4])
    if data.get("reporting"):
        doc.add_paragraph("Report writer  "+data["reporting"]["writer"]["call"])
    doc.add_paragraph("The output folder contains opening dimensions, the four wall corners, source indices, window depth sections and signed RMS residuals. The JSON manifest records fitted planes, footprint coverage and the algorithm source fingerprints.")
    doc.add_paragraph("Input SHA-256"); doc.add_paragraph(cloud["sha256"])
    doc.save(output/data["word_report"])
