"""Draw the workflow figure shared by the inspection and course reports."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def draw(path):
    fig, ax=plt.subplots(figsize=(8.2,3.65))
    ax.set(xlim=(0,10),ylim=(0,5)); ax.axis("off")
    def box(x,y,w,h,top,body,fill):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.035,rounding_size=.08",
                                    facecolor=fill,edgecolor="#506573",linewidth=.95))
        ax.text(x+w/2,y+h*.69,top,fontsize=10.5,weight="bold",ha="center",va="center",color="#203747")
        ax.text(x+w/2,y+h*.32,body,fontsize=9,ha="center",va="center",color="#243a41")
    def arrow(a,b):
        ax.annotate("",b,a,arrowprops=dict(arrowstyle="-|>",color="#4a626c",lw=1.1,shrinkA=1,shrinkB=1))
    box(.08,2.02,2.02,1.11,"Room scan","XYZ and row IDs","#edf3f6")
    box(2.56,2.02,2.08,1.11,"Room geometry","Floor, walls, corners","#edf3f6")
    box(5.12,3.43,2.38,1.11,"Opening edges","Wall-face width / height","#edf5f3")
    box(5.12,1.99,2.38,1.11,"Window depth","Paired returns by slice","#fff3e5")
    box(5.12,.55,2.38,1.11,"Wall flatness","Masked area and plane","#edf5f3")
    box(8.03,2.02,1.9,1.11,"Report","Word, JSON, CSV","#edf3f6")
    arrow((2.12,2.57),(2.54,2.57))
    for end in ((5.10,3.98),(5.10,1.11)):
        arrow((4.65,2.57),end)
    arrow((6.31,3.40),(6.31,3.13))
    for y in (3.98,2.55,1.10):
        arrow((7.54,y),(8.0,2.57))
    fig.subplots_adjust(left=.008,right=.992,top=.99,bottom=.01)
    path.parent.mkdir(exist_ok=True,parents=True); fig.savefig(path,dpi=185,bbox_inches="tight",pad_inches=.04); plt.close(fig)

if __name__=="__main__":
    target=Path(__file__).resolve().parents[1]/"assets"/"measurement_workflow"
    plt.rcParams["svg.fonttype"]="none"
    draw(target.with_suffix(".png"))
    draw(target.with_suffix(".svg"))
