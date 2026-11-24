"""Render the whole-wall measurement workflow for reports and presentations."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import FancyBboxPatch


def main():
    fig, ax = plt.subplots(figsize=(15, 8))
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    ax.set(xlim=(0, 15), ylim=(-.15, 8))
    ax.axis("off")
    ax.text(.4, 7.65, "房间点云自动测量流程", fontsize=25, weight="bold", color="#17343d")
    ax.text(14.6, 7.68, "CIVL 7023  /  TASK 1", ha="right", fontsize=14, color="#375763")

    def box(x, y, w, h, title, body, color="#edf5f4"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=.08",
                                    ec="#77969e", fc=color, lw=1.3, zorder=2))
        ax.text(x+w/2, y+h*.70, title, ha="center", va="center", fontsize=15,
                weight="bold", color="#17343d", zorder=3)
        ax.text(x+w/2, y+h*.32, body, ha="center", va="center", fontsize=11,
                color="#375763", zorder=3)

    def arrow(a, b):
        ax.annotate("", b, a, arrowprops={"arrowstyle":"-|>", "color":"#537681", "lw":1.6})

    box(.45, 6.0, 4.1, 1.02, "单房间点云", "PCD 或 CSV，指定单位与向上方向")
    box(5.0, 6.0, 9.5, 1.02, "分墙接口", "完整点云 → Efficient RANSAC 原版支持点 → 墙体规则")
    arrow((4.63,6.51),(4.91,6.51))
    box(.45, 4.25, 4.1, 1.1, "门窗接口", "沿墙切片拟合洞口，输出中心、四角、宽高")
    box(5.45, 4.25, 4.1, 1.1, "原始墙点", "按墙号取出实测 XYZ 和原始点号")
    box(10.45, 4.25, 4.05, 1.1, "墙角接口", "检查四墙闭合与顶面支持", "#edf2fa")
    for x in (2.5,7.5,12.48):
        ax.plot([x,x],[5.43,5.72],color="#537681",lw=1.6)
        arrow((x,5.58),(x,5.43))
    ax.plot([2.5,12.48],[5.72,5.72],color="#537681",lw=1.6)
    ax.plot([9.75,9.75],[5.72,5.92],color="#537681",lw=1.6)
    box(.45, 2.52, 9.1, 1.02, "保留洞口以外的原始墙点", "排除已检出洞口投影内的点，未检出时沿用原始归属点")
    box(10.45, 2.52, 4.05, 1.02, "整墙结构四角", "墙面与地面、顶面求交，检查最近墙点", "#edf2fa")
    for x in (2.5,7.5):
        arrow((x,4.17),(x,3.62))
    arrow((12.48,4.17),(12.48,3.62))
    ax.text(12.75,3.88,"通过",fontsize=10,color="#375763")
    arrow((14.60,4.75),(14.88,4.75))
    ax.plot([14.88,14.88],[.68,4.75],color="#537681",lw=1.4)
    ax.text(14.77,3.92,"待复核",rotation=90,ha="center",fontsize=10,color="#945917")
    box(.45, 1.08, 14.05, .86, "整墙 RMS 接口", "结构四角内的可用原始墙点 → SVD 平面拟合 → 正交距离 RMS（mm）")
    for x in (5,12.48):
        arrow((x,2.44),(x,2.02))
    box(.45, .04, 14.05, .55, "生成测量报告", "房间尺寸、洞口尺寸、墙角坐标、整墙 RMS 与复核标记")
    arrow((7.5,1.00),(7.5,.68))
    arrow((14.88,.68),(14.58,.37))
    fig.subplots_adjust(left=.015,right=.985,bottom=.025,top=.98)
    target = Path(__file__).resolve().parents[1]/"assets"/"measurement_workflow.png"
    fig.savefig(target,dpi=180,facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
