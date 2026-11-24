"""Rebuild the English course report and figures from two completed inspection runs."""
import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from report_style import document, figure, heading, link, table

NAVY,TEAL,RUST,GREY="#233d51","#006d6b","#a84928","#647681"
ROOMS=("M26","M04")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def errors(values):
    v=np.asarray(values,dtype=float)
    return float(np.mean(np.abs(v))),float(np.sqrt(np.mean(v**2)))


def plans(scans,refs,file):
    fig,axes=plt.subplots(1,2,figsize=(7.6,3.8))
    for ax,(room,s) in zip(axes,scans.items()):
        p=np.asarray(s["room"]["floor_vertices_m"])[:,:2]
        center=p.mean(0)
        for i,wid in enumerate(s["room"]["boundary_wall_ids"]):
            a,b=p[i],p[(i+1)%len(p)]
            q=np.vstack([a,b])
            focus=wid==refs[room]["rms"]["wall_id_in_this_scan"]
            ax.plot(*q.T,color=NAVY,ls="--" if focus else "-",lw=2.0)
            mid=(a+b)/2; offset=mid-center; offset=offset/np.linalg.norm(offset)
            ax.text(*(mid+offset*.22),wid,ha="center",va="center",fontsize=9,color=NAVY)
        for w in s["walls"]:
            for o in w["openings"]:
                q=np.asarray(o["corners_xyz_m"][:2])[:,:2]
                ax.plot(*q.T,lw=4.5,color=RUST if o["type"]=="door" else TEAL,solid_capstyle="butt")
        ax.set_aspect("equal");ax.autoscale(False)
        a,b=p.min(0)-.65,p.max(0)+.65
        ax.set(xlim=(a[0],b[0]),ylim=(a[1],b[1]),xlabel="Scan X (m)",ylabel="Scan Y (m)",title=room)
        ax.spines[["top","right"]].set_visible(False)
        ax.tick_params(labelsize=8); ax.title.set_fontsize(11)
    handles=[Line2D([0],[0],color=RUST,lw=3,label="Door"),Line2D([0],[0],color=TEAL,lw=3,label="Window"),
             Line2D([0],[0],color=NAVY,ls="--",lw=2,label="Wall with manual RMS reference")]
    fig.legend(handles=handles,loc="lower center",ncol=3,frameon=False,fontsize=9)
    fig.subplots_adjust(left=.075,right=.98,top=.92,bottom=.25,wspace=.26)
    fig.savefig(file,dpi=200,bbox_inches="tight",pad_inches=.035);plt.close(fig)


def depth_figure(window,profile,file):
    ds=np.array([int(r["depth_mm"]) for r in profile])
    finite=(ds<=710)
    mid=np.array([float(r["width_0.50"]) if r.get("width_0.50") else np.nan for r in profile])
    l=np.array([float(r["width_low_0.50"]) if r.get("width_low_0.50") else np.nan for r in profile])
    r=np.array([float(r["width_high_0.50"]) if r.get("width_high_0.50") else np.nan for r in profile])
    face=window["face"];deep=window["deep"]
    fig,(a,b)=plt.subplots(1,2,figsize=(8.0,3.05),gridspec_kw={"width_ratios":[.93,1.52]},layout="constrained")
    a.scatter(l[finite],ds[finite],s=6,color=TEAL);a.scatter(r[finite],ds[finite],s=6,color=TEAL)
    a.axhspan(*deep["depth_range_mm"],color="#f4dbc8",zorder=0)
    a.set(xlim=(-1250,2050),ylim=(-55,745),title="A   Horizontal section",xlabel="Along-wall coordinate u (mm)",ylabel="Depth into opening D (mm)")
    a.set_xticks([-750,0,800,1600]);a.set_yticks([0,200,400,665])
    for y,x1,x2,t,c,dy in [(0,l[0],r[0],"Wall face",NAVY,45),(665,l[ds==665][0],r[ds==665][0],"Recessed edge",RUST,-75)]:
        a.annotate("",(x1,y),(x2,y),arrowprops=dict(arrowstyle="<->",lw=1.2,color=c))
        a.text((x1+x2)/2,y+dy,t,color=c,ha="center",va="center",fontsize=8)
    b.axvspan(*deep["depth_range_mm"],color="#f4dbc8",zorder=0)
    b.plot(ds[finite],mid[finite],".",ms=3.5,color=TEAL)
    b.axhline(2375,color=GREY,ls="--",lw=1)
    b.text(18,2371,"Manual width 2375 mm",fontsize=8,color="#46535b")
    b.scatter(0,face["width_mm"],s=35,marker="D",color=NAVY,zorder=4)
    b.annotate(f'Face fit {face["width_mm"]:.2f}',(0,face["width_mm"]),(72,2454),fontsize=8,color=NAVY,arrowprops=dict(arrowstyle="-",color=NAVY))
    b.scatter(665,deep["width_mm"],s=38,marker="D",color=RUST,zorder=4)
    b.annotate(f'Five-slice median {deep["width_mm"]:.2f}',(665,deep["width_mm"]),(130,2393),fontsize=8,color=RUST,arrowprops=dict(arrowstyle="->",color=RUST))
    b.set(xlim=(-15,720),ylim=(2364,2464),xticks=[0,200,400,600],title="B   Window width at mid-height",xlabel="Depth into opening D (mm)",ylabel="Projected width (mm)")
    for ax in (a,b):
        ax.spines[["top","right"]].set_visible(False); ax.tick_params(labelsize=8); ax.title.set_fontsize(10)
        ax.xaxis.label.set_size(9);ax.yaxis.label.set_size(9)
    fig.savefig(file,dpi=205);plt.close(fig)


def reference_list(doc):
    entries=[
        ("Boudarbala, S., Hajji, R., Gourguechon, C., Macher, H., & Landes, T. (2024). Automatic detection of doors and windows using point clouds in the context of as-built BIM. International Archives of the Photogrammetry, Remote Sensing and Spatial Information Sciences, XLVIII-2/W8-2024, 37–44.","10.5194/isprs-archives-XLVIII-2-W8-2024-37-2024"),
        ("Chen, H., Li, T., Hong, J., & Li, X. (2026). Exploiting point cloud semantic segmentation for automatic geometric measurement in modular construction. Proceedings of the 43rd ISARC, 1403–1410.","10.22260/ISARC2026/0180"),
        ("Kim, M.-K., Wang, Q., Park, J.-W., Cheng, J. C. P., Sohn, H., & Chang, C.-C. (2016). Automated dimensional quality assurance of full-scale precast concrete elements using laser scanning and BIM. Automation in Construction, 72, 102–114.","10.1016/j.autcon.2016.08.035"),
        ("Previtali, M., Díaz-Vilariño, L., & Scaioni, M. (2018). Towards automatic reconstruction of indoor scenes from incomplete point clouds: Door and window detection and regularization. International Archives of the Photogrammetry, Remote Sensing and Spatial Information Sciences, XLII-4, 507–514.","10.5194/isprs-archives-XLII-4-507-2018"),
        ("Tan, Y., Liu, X., Jin, S., Wang, Q., Wang, D., & Xie, X. (2024). A terrestrial laser scanning-based method for indoor geometric quality measurement. Remote Sensing, 16(1), 59.","10.3390/rs16010059"),
        ("Tang, P., Huber, D., & Akinci, B. (2011). Characterization of laser scanners and algorithms for detecting flatness defects on concrete surfaces. Journal of Computing in Civil Engineering, 25(1), 31–42.","10.1061/(ASCE)CP.1943-5487.0000073")]
    from docx.shared import Pt
    for text,doi in entries:
        p=doc.add_paragraph();p.paragraph_format.left_indent=Pt(15);p.paragraph_format.first_line_indent=Pt(-15)
        p.add_run(text+" ");link(p,"DOI "+doi,"https://doi.org/"+doi)


def create(evidence,destination):
    scans={r:read(evidence/r/"summary.json") for r in ROOMS}
    refs=read(evidence/"manual_reference.json")["rooms"]
    for room,s in scans.items():
        if refs[room]["sha256"]!=s["cloud"]["sha256"]: raise ValueError("Unexpected course input for "+room)
    rows=csv_rows(evidence/"comparison"/"same_section.csv")
    w=read(evidence/"M26"/"window_sections.json")["windows"][0]
    profile=csv_rows(evidence/"M26"/w["profile_file"])
    figs=destination.parent/"figures";figs.mkdir(parents=True,exist_ok=True)
    plans(scans,refs,figs/"room_plans.png")
    depth_figure(w,profile,figs/"window_sections.png")
    doc=document("Geometric inspection of two modular rooms")
    p=doc.add_paragraph
    sub=lambda t: doc.add_heading(t,level=2)
    doc.add_paragraph("Geometric inspection of two modular rooms","Title")
    p("CIVL 7023  |  Project 1, Task 1  |  Rooms M26 and M04")
    heading(doc,"1  Inspection scope and findings")
    p("The two scans contain three openings. At 1.00 m above the floor, the M26 door is 898.95 mm wide against a 900 mm tape reading. The largest discrepancy is the M26 window width. At the same height above the floor, moving the measuring section from the wall face to a recessed edge changes the reading by 65.51 mm. The manual record gives the width but omits the frame depth.")
    p("The course brief asks for room length, width and height, door and window dimensions, and wall roughness. The dataset defines its surface reference as wall flatness in millimetres RMS. This report follows that definition. Figure 1 locates the openings and the two walls described in the manual record.")
    figure(doc,figs/"room_plans.png","Figure 1  Measured floor plans. A dashed line identifies the reference wall for flatness.",6.12)
    sub("Dataset and comparisons")
    p(f'M26 contains {scans["M26"]["cloud"]["point_count"]:,} points and M04 contains {scans["M04"]["cloud"]["point_count"]:,}. The course dataset lists a 10 mm voxel size. Both scans are in metres with +Z up. Each reported difference is the point-cloud result minus the manual value. The reference dimensions are consulted after geometry estimation.')
    heading(doc,"2  Geometric measurement in the literature",new_page=True)
    sub("2.1  Dimensional inspection and reference surfaces")
    p("Kim et al. (2016) matched a scanned precast element to its design model using a coordinate transformation, principal-component alignment and explicit edge and corner extraction. Their full-scale slab tests reported errors around 3 mm. That comparison had identified design features. The present rooms have tape dimensions and a wall photograph, so the plane, elevation and physical edges used for each dimension must be recorded separately.")
    p("Tan et al. (2024) measured indoor wall flatness, verticality and openings from terrestrial laser scans. They used coordinate conversion, local denoising, spatial relationships and simulations of field measurements. Their work links the calculation to the inspector’s operation. We apply that principle by fixing the door-width elevation and recording the window depth. Smoothing the final wall samples would change the measured surface, so we fit the plane to the original selected returns.")
    sub("2.2  Finding an opening in an incomplete wall")
    p("Previtali et al. (2018) used voxel visibility to distinguish an empty opening from an occluded wall, then regularized repeated layouts. Boudarbala et al. (2024) combined geometry and radiometry to model doors and windows. These approaches address the ambiguity of a point-free patch. The course files supply XYZ, normals and RGB, but no per-return scanner trajectories. Our default detector follows a gap across several heights and requires support on both sides. A flush door, curtain or rectangular occlusion can still defeat this test.")
    p("Chen et al. (2026, §2.2.5) selected semantically labelled window points, removed noise with DBSCAN, fitted a plane with RANSAC and projected the inliers onto a supporting wall. After trimming boundary points, they fitted a minimum-area rectangle to the convex hull. This gives an extent for the labelled component. A tape can contact a narrower pair of frame edges at another depth. The M26 experiment tests that physical distinction on a single opening. We did not run or score their trained network on these two scans.")
    sub("2.3  Flatness and the size of the footprint")
    p("Tang et al. (2011) compared three algorithms and three laser scanners for detecting concrete flatness defects. Detection depended on the scanner, the algorithm and the scale of the defect. Chen et al. (2026, §2.2.3) used patch-level RMS and point-to-plane deviations. Here a whole wall and a contiguous 1 m square each receive their own fitted plane. Saving their four corners and signed residuals makes it possible to compare equivalent footprints when the field locations become available.")
    heading(doc,"3  Measurement framework and contribution",new_page=True)
    p("The fitted floor supplies the height axis. The software extracts candidate planes from a reduced cloud, restores original wall samples and seeks two opposite pairs of walls. Intersecting adjacent wall planes with the floor and ceiling gives the corners. Opposite floor-edge lengths are averaged in pairs. Room height is the mean normal distance of the four ceiling corners above the floor.")
    figure(doc,ROOT/"assets"/"measurement_workflow.png","Figure 2  Geometry and measurement stages. Window depth uses an opening found at the wall face.",6.12)
    sub("3.1  Fixing the physical measuring section")
    p("The detector searches an 8 mm band on either side of each wall plane. It tracks horizontally supported gaps through successive elevations, then fits jamb and head or sill lines with the Theil–Sen estimator. Door width is evaluated 1.00 m above the floor, window width at mid-height and opening height on its centreline. The width axis is the normalized cross product of the inward wall normal and the upward floor normal.")
    sub("3.2  Three changes relative to a projected window envelope")
    p("First, the output preserves two physical sections with separate endpoint evidence. One describes the aperture at the interior wall. A second search follows pairs of raw edge returns into the reveal and records the first supported narrowing. The manual width never enters the layer-selection rule.")
    p("Second, two alternate estimators operate on the same detected opening and prescribed section. A normal-filtered RANSAC plane fit with SVD refinement intersects the reveal with the section. A 2D alpha-shape contour followed by robust line fitting estimates edges facing the void. Held-out edge segments test support before a dimension is returned. This comparison isolates the effect of edge fitting.")
    p("Third, the same run records original point indices for edge samples, the distance from each structural corner to its nearest wall point, and the four corners and signed residuals for each flatness region. A subsequent algorithm can change one stage and retain the coordinate system, measurement section and reporting format.")
    heading(doc,"4  Dimension errors against manual measurements",new_page=True)
    rr=[];rerrs=[]
    for k in ("length","width","height"):
        vals=[]
        for room in ROOMS:
            manual=refs[room]["dimensions_mm"][k];v=scans[room]["room"][k+"_mm"];rerrs.append(v-manual)
            vals.extend([str(manual),f"{v:.2f}",f"{v-manual:+.2f}"])
        rr.append([k.capitalize(),*vals])
    table(doc,"Table 1  Interior room dimensions and signed errors (mm)",["Dimension","M26 manual","M26 scan","M26 error","M04 manual","M04 scan","M04 error"],rr,[1.55,1.2,1.2,1.12,1.2,1.15,1.12],range(1,7))
    ma,rm=errors(rerrs)
    p(f'Across six room dimensions the mean absolute error (MAE) is {ma:.2f} mm and the root-mean-square error (RMSE) is {rm:.2f} mm. The largest individual difference is the M26 room width at +5.36 mm.')
    items=sorted(rows,key=lambda x:(ROOMS.index(x["room"]),x["opening"]!="door",x["dimension"]!="width"))
    def cell(s): return "—" if s=="" else f'{float(s):.3f}'
    tabrows=[[r["room"]+" "+r["wall"],r["opening"].capitalize()+" "+r["dimension"],r["manual_mm"],cell(r["profile_mm"]),
              f'{float(r["profile_error_mm"]):+.3f}',cell(r["plane_mm"]),cell(r["contour_mm"])] for r in items]
    table(doc,"Table 2  Opening dimensions at the wall face (mm)",["Room / wall","Item","Manual","Profile","Error¹","Plane","Contour"],tabrows,[1.45,1.65,1.1,1.2,1.14,1.2,1.2],range(2,7),10.5)
    p("¹ Error is the profile estimate minus manual. A dash means that one or both required edges lacked support. M04 has no recorded window. Plane and contour fits reuse each profile-detected opening.")
    common=[r for r in rows if all(r[k+"_mm"] for k in ("profile","plane","contour"))]
    stats=[]
    for key,label in (("profile","Profile"),("plane","Plane"),("contour","Contour")):
        valid=[r for r in rows if r[key+"_mm"]]; av=errors([float(r[key+"_error_mm"]) for r in valid]); shared=errors([float(r[key+"_error_mm"]) for r in common])
        stats.append([label,f"{len(valid)}/6",*(f"{v:.2f}" for v in (*av,*shared))])
    table(doc,"Table 3  Estimator availability and error (mm)",["Method","Yield","Own MAE","Own RMSE","Shared MAE","Shared RMSE"],stats,[1.3,1,1.2,1.38,1.45,1.5],range(1,6))
    p("MAE averages absolute signed errors. RMSE is the square root of their mean square. The shared subset contains M26 window width and height and M04 door height. On the full set, the profile method returns all six dimensions. The plane method lacks supported door jambs in both rooms, and the M26 door sill fails the contour test. The M04 door-height error of +24.937 mm includes a fitted sill 8.34 mm below the floor reference.")
    p("The two fitted door widths differ from the tape by 1.05 and 2.24 mm in absolute terms. Both door heights differ by more than 10 mm. The +68.861 mm window-width difference dominates the opening RMSE. The next section tests whether changing the physical measurement position can explain that difference.")
    heading(doc,"5  Where the M26 window was measured",new_page=True)
    p("W01 contains window W01-01. Both widths use a nominal height of 1.2794 m above the fitted floor. Depth D is zero on the interior wall face and increases away from the room, into the opening. Figure 3 follows the two edges across the same horizontal band.")
    figure(doc,figs/"window_sections.png","Figure 3  Original-point pairs within ±25 mm of window mid-height. Shading marks the five selected slice centres.",6.24)
    a,b=w["face"],w["deep"]; man=refs["M26"]["openings_mm"]["window"]["width"]
    table(doc,"Table 4  Two physical sections compared with the manual width of 2375 mm",
          ["Measuring position","D (mm)","Width (mm)","Error (mm)","Endpoint evidence"],
          [["Interior wall-face aperture","0",f'{a["width_mm"]:.3f}',f'{a["width_mm"]-man:+.3f}',"Fitted jambs"],
           ["Recessed frame candidate","655–675",f'{b["width_mm"]:.2f}',f'{b["width_mm"]-man:+.2f}',"Paired raw returns"]],
          [2.4,1.26,1.41,1.36,1.64],(1,2,3))
    p("The wall fit uses points within ±8 mm of D = 0. The independent raw strip at D = 0 gives 2443.55 mm. The three fitted face estimates span only 1.34 mm, while their errors against the tape all exceed 68 mm. Changing the measurement depth has the larger observed effect.")
    p("Slices are 12 mm thick and their centres are 5 mm apart. At least three of five height strips must have paired returns. Five successive depth medians must span at most 5 mm and be at least 30 mm narrower in median than the preceding supported levels. The mid-height widths at D = 655, 660, 665, 670 and 675 mm are 2378.49, 2378.35, 2378.23, 2378.27 and 2378.80 mm. Their median is 2378.35 mm. Taking a median across supported heights at each depth first yields 2378.03 mm.")
    p("At D = 665 mm, left row 428596 and right row 401081 span 2378.23 mm along the wall axis. Their actual depths are 659.09 and 669.06 mm. The five overlapping slices have sample SD 0.23 mm within this scan. The field notes do not identify which frame edges the tape contacted.")
    locations=[]
    for side,xyz in zip(("Left","Right"),a["endpoints_xyz_m"]):
        locations.append(["Wall face",side,*(f"{v:.5f}" for v in xyz),"Fit"])
    for point in b["representative"]["endpoints"]:
        locations.append(["665 mm slice",point["side"].capitalize(),*(f"{v:.5f}" for v in point["xyz_m"]),str(point["original_index"])])
    table(doc,"Table 5  Endpoint locations in the original M26 scan coordinate system",
          ["Section","Side","X (m)","Y (m)","Z (m)","Source row"],locations,[1.6,1.05,1.45,1.45,1.55,1.3],(2,3,4,5),10.5)
    heading(doc,"6  Wall flatness and footprint uncertainty",new_page=True)
    p("The four structural corners bound the whole-wall region. The patch selector searches contiguous wall returns on a 50 mm grid with a 100 mm guard. Opening interiors are masked. For each accepted region, an SVD fit supplies a centroid c and unit normal n. For a point p in metres, the signed residual in mm is 1000 (p − c) · n. Wall RMS is the square root of the mean squared residual for points in that region.")
    lookup={r:{x["id"]:x for x in scans[r]["walls"]} for r in ROOMS}
    rtab=[]
    for wid in sorted(lookup["M26"]):
        vals=[]
        for room in ROOMS:
            wall=lookup[room][wid]
            for scope in ("whole","patch"):
                rms=wall[scope].get("rms_mm"); vals.append("—" if rms is None else f"{rms:.3f}")
        rtab.append([wid,*vals])
    table(doc,"Table 6  Whole-wall and 1 m × 1 m patch RMS (mm)",
          ["Wall","M26 whole","M26 patch","M04 whole","M04 patch"],rtab,[1.3,1.65,1.65,1.65,1.65],range(1,5))
    p("The whole-wall calculation returned eight values. Five of eight local patches had adequate support. On three walls a complete patch and its guard could not be placed. The M04 W02 upper corners are about 449–450 mm from their nearest assigned returns. Its 11.623 mm whole-wall RMS therefore warrants inspection of the extrapolated boundary.")
    rt=[]
    for room in ROOMS:
        ref=refs[room]["rms"];wid=ref["wall_id_in_this_scan"]; wr=lookup[room][wid];m=ref["value_mm"]
        rt.append([room+" "+wid,f"{m:.1f}",*[f'{wr[scope]["rms_mm"]-m:+.3f}' for scope in ("whole","patch")]])
    table(doc,"Table 7  Differences from the manual RMS on the indicated wall (mm)",
          ["Room / wall","Manual","Whole − manual","Patch − manual"],rt,[1.7,1.2,2.35,2.35],(1,2,3))
    p("In M26, W03 faces the door wall. In M04, the red box in the course photograph is on the viewer’s right when facing the doorway from inside. The inward-facing wall on that side of W02 is W01 in this reconstruction. The scan gives fully occupied coverage grids for both the whole and local fits on those two walls. Neither manual footprint has registered corners. Table 7 gives same-wall differences with different spatial support, so pooling them as instrument errors would be misleading.")
    sub("Conditions for a stronger performance claim")
    p("A repeat inspection should record tape height, recess depth, endpoint photographs and the four flatness-patch coordinates. Repeat both the scan and manual measurement independently in additional modules. Report missed openings, extra detections, and paired errors for the same physical sections. The brief supplies no numerical acceptance tolerance. These two rooms support descriptive errors and coverage counts.")
    heading(doc,"7  References and reproducibility",new_page=True)
    reference_list(doc)
    sub("Course records and implementation")
    p("The CIVL 7023 Project 1 requirements, pp. 2–4, define the data, objectives and evaluation criteria. The Task 1 dataset README supplies the manual dimensions, voxel spacing and M04 photograph. The accompanying package stores the references in evidence/manual_reference.json and the fitted measurements in each room’s summary.json.")
    p("The five algorithm entry points, their coordinate conventions and result schemas are documented in INTERFACE_SPEC.md. The comparison table and holdout diagnostics are in evidence/comparison. Each room’s window_sections.json identifies the fit, raw indices and depth convention. README.md gives reproduction commands. AI_PROMPTS.md provides handoff prompts for another analyst.")
    q=p();q.add_run("The default implementation reuses wall discovery and four-point flatness fitting. ")
    link(q,"Wall discovery, revision 149d280","https://github.com/x13230802751/wall-rms-pipeline-v3/tree/149d280662e9f6256608efd1896b1744e82cf5d4")
    q.add_run(" · "); link(q,"Four-point RMS, revision 952259c","https://github.com/x13230802751/wall-flatness-v3/tree/952259ce8037f042155139ca3fb7af58cd9e2d5f")
    doc.save(destination)

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",type=Path,default=ROOT/"evidence")
    parser.add_argument("--out",type=Path,default=ROOT/"reports"/"Task1_Evaluation.docx")
    args=parser.parse_args()
    create(args.evidence,args.out)
