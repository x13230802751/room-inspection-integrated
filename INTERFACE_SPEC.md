# 组合项目接口规范

沿用伙伴项目 Profile API v1、summary format_version=2、Report API v1，增加可选原版支持点结果与来源字段。

| 接口 | 默认函数及参数 | 返回与约束 |
|---|---|---|
| 分墙 | extensions.native_support.walls(points, config) | floor、walls、native_detection、config；原始 N×3 米坐标，完整有限点送入原版检测器 |
| 墙角 | room_geometry.room_boundaries(points, discovery, config) | walls、inside_ids、ceiling、corners、room、warnings；原项目四墙闭合、顶面覆盖与结构相交规则 |
| 门窗 | openings.profile_candidates(points, inside_ids, wall, floor, corners, node) | (openings, diagnostics)；四角为墙局部 u/h 坐标；原项目完善边界、世界坐标与深度剖面 |
| 局部测区 | wall_rms.supported_patch(xyz, wall, floor, boundary, size) | (four_xyz_corners, None) 或 (None, reason)；默认 1×1 m、50 mm 覆盖网格、每格至少三点及 100 mm 余量 |
| RMS | extensions.native_support.measure(xyz, roi) | indices、signed_mm、plane_center_m、plane_normal、coverage_fraction、status、warnings |

点与角点为米；RMS 返回的 indices 是传入子集的局部编号，总控再映射为原始点号。expanded_indices 是旧接口字段名，在新适配器中精确等于 support_indices，没有扩张。原始编号空间保留 NaN 行位置。

RMS roi 使用 unit="m"、循环凸四角、slab_half_thickness_mm=null。只做二维区域包含判断，不作法向距离或残差筛选。corners=null 表示完整支持集基线；至少三个点且二维不退化时可以拟合。

总控保留伙伴项目的已检出洞口投影掩膜。“可用墙点”是原版支持点经过该空间掩膜后的子集，不是在墙附近补点。support 单独在完整原版墙支持集上测量；whole/patch 使用各自几何测区。

门窗坐标轴使用 inward wall normal × floor normal；粗糙度用 ROI 的二维坐标，输入输出仍在相同世界坐标系。角点沿用 A/B/C/D 顺序，最近实测点来自原版支持集。

native_config 是原版分墙实际参数；discovery_config 是保留给伙伴 SDK 的参数，部分用于其顶面检测，不能解释为对墙面 RMS 使用了体素/半径过滤。native_detection 保存源码提交、构建指纹、完整输入数量、运行日志和支持点来源。

门窗 8 mm 面层、窗框深度切片、角点 50 mm 外推警示及顶面几何检测都沿用伙伴项目，不是 RMS 筛选阈值，也不改变 support 集合。没有闭合/可靠顶面时 whole 为 unavailable；局部覆盖不足时 patch 为 unavailable；support 仍输出。

输出包括 report.docx、report.html、summary.json、window_sections.json、四个 CSV、wall_points.npz、native_supports.txt、逐墙立面图和 support/whole/patch 的 ROI 与原始点号残差文件。

接口替换遵循 schemas/algorithm_profile.schema.json；profiles/*.json 的 stages 可覆盖默认函数。其他模型若改动点坐标或点集，必须独立标识，不能称为原版无滤波支持点基线。
