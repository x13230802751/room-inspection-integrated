"""Build the experimental report from a fresh, independently audited run."""
import argparse
import json
from math import sqrt
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

from guide_style import new_document, table

ROOT = Path(__file__).resolve().parents[1]
ROOMS = ('M04', 'M26')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def scores(errors):
    return f'MAE {mean(map(abs, errors)):.2f} mm，RMSE {sqrt(mean(x*x for x in errors)):.2f} mm'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    records = {name: load(args.run/name/'summary.json') for name in ROOMS}
    audits = load(args.run/'audit.json')
    doc = new_document('Task 1 房间点云自动测量实验报告')
    p, h = doc.add_paragraph, doc.add_heading

    p('本次实验用最新组合版重新处理课程 M04 和 M26 的完整点云，评估房间长宽高、门窗尺寸和墙面平整度。门窗和结构角点沿用伙伴项目的实现。墙面粗糙度使用原版 Efficient RANSAC 支持点与无滤波 SVD 拟合。')
    h('一 实验设置与测量流程', 1)
    run_rows = []
    for name, record in records.items():
        cloud = record['cloud']
        audit = audits[name]
        assert audit['sha256'] == cloud['sha256'] == record['manual_reference']['sha256']
        assert audit['exact_native_membership'] and record['filter'] == record['recovery'] == 'none'
        assert record['algorithms']['stages']['rms']['call'] == 'extensions.native_support:measure'
        assert record['native_detection']['n_detector_input'] == cloud['point_count'] - cloud['invalid_rows']
        run_rows.append([name, f"{cloud['point_count']:,}", record['native_detection']['n_detector_input'],
                         record['candidate_wall_count'], len(record['walls'])])
    table(doc, ['房间', '原始点数', '实际检测点数', '墙候选数', '输出墙数'], run_rows)
    p('输入为课程原始 PCD，单位为米，向上方向为 +Z。原版检测器提取平面，墙体几何规则筛选墙候选。系统按原始点号提取 XYZ，依次计算墙角、门窗剖面和测区，再生成每个房间的 Word、HTML 和逐点残差。')
    p('整墙 RMS 使用结构四角内的原版墙支持点，排除检出洞口投影内的点。每面墙独立用 SVD 拟合，取点到平面的正交距离均方根并转换为毫米。全程无额外降采样、去噪、附近点恢复或 RMS 厚度筛选。')
    p(f"组合项目提交 {audits['git_commit']}。检测随机种子 {records['M04']['native_detection']['seed']}。输入校验、支持点来源和运行参数见本次输出的 summary.json 与 audit.json。人工参考来自课程数据说明。")

    doc.add_page_break()
    h('二 房间和门窗尺寸', 1)
    room_rows, opening_rows, room_errors, opening_errors = [], [], [], []
    for name, record in records.items():
        ref = record['manual_reference']
        for key, label in [('length','长'), ('width','宽'), ('height','高')]:
            gt = ref['dimensions_mm'][key]
            value = record['room'][key+'_mm']
            room_errors.append(value-gt)
            room_rows.append([name, label, f'{value:.2f}', gt, f'{value-gt:+.2f}'])
        openings = [o for w in record['walls'] for o in w['openings']]
        for kind, label in [('door','门'), ('window','窗')]:
            gt = ref['openings_mm'].get(kind)
            if gt is None:
                continue
            found = [o for o in openings if o['type'] == kind]
            assert len(found) == 1
            o = found[0]
            for key, direction in [('width','宽'), ('height','高')]:
                value = o[key+'_mm']
                opening_errors.append(value-gt[key])
                opening_rows.append([f'{name} {label}{direction}', o['id'], f'{value:.2f}', gt[key], f'{value-gt[key]:+.2f}'])
    table(doc, ['房间', '维度', '实测 mm', 'GT mm', '实测减 GT mm'], room_rows)
    p(f'房间尺寸共 {len(room_errors)} 个参考项。{scores(room_errors)}。')
    table(doc, ['房间和维度', '洞口号', '实测 mm', 'GT mm', '实测减 GT mm'], opening_rows)
    p(f'门窗按墙面洞口口径统计，共 {len(opening_errors)} 个参考项。{scores(opening_errors)}。')
    window = load(args.run/'M26/window_sections.json')['windows'][0]
    deep = window['deep']
    if deep['width_mm'] is not None:
        gt = records['M26']['manual_reference']['openings_mm']['window']['width']
        low, high = deep['depth_range_mm']
        p(f"M26 窗宽在墙面处为 {window['face']['width_mm']:.2f} mm，在深度 {low}–{high} mm 的内侧窗框候选处为 {deep['width_mm']:.2f} mm。后者比人工参考 {gt} mm 大 {deep['width_mm']-gt:.2f} mm。人工测量深度未记录，因此内侧候选宽度单独列示。")

    doc.add_page_break()
    h('三 墙面 RMS 与官方参考', 1)
    def region(result):
        value = result.get('rms_mm')
        if value is None:
            return '未测出'
        return f"{value:.6f}"+(' *' if result['status']=='warning' else '')

    walls = []
    comparison = []
    for name, record in records.items():
        ref = record['manual_reference']['rms']
        for wall in record['walls']:
            label = f"{name} {wall['id']}"
            whole = wall['whole']
            walls.append([label, wall['assigned_points'], whole.get('n_selected', '—'), region(whole)])
            if wall['id'] == ref['wall_id_in_this_scan']:
                value, gt = whole['rms_mm'], ref['value_mm']
                comparison.append([label, f'{gt:.1f}', f'{value:.6f}', f'{value-gt:+.6f}', f'{abs(value-gt)/gt:.2%}'])
    assert len(comparison) == 2
    table(doc, ['房间和墙号', '支持点数', '整墙入选点数', '整墙 RMS mm'], walls)
    p('星号表示结构角点离最近实测墙点超过 50 mm，整墙结果附外推警示。')
    table(doc, ['参考墙', 'GT mm', '整墙 RMS mm', '计算减 GT mm', '相对绝对差'], comparison)
    p('M04 W01 对应配图标出的墙候选，M26 W03 对应门对面的墙候选。官方参考未提供精确测区四角，因此表内差值按参考差异解释。相对绝对差为绝对差除以 GT。表格多位小数用于复核计算。')

    doc.add_page_break()
    h('四 复核与实验局限', 1)
    p('对两个房间逐墙检查原始索引。每面墙的支持点精确等于其对应原版检测平面支持集的并集。使用原始 XYZ 构造协方差矩阵，根据最小特征值独立复算整墙 RMS，并核对残差文件。')
    for name, record in records.items():
        notes = []
        for w in record['walls']:
            if w['whole']['status']=='warning':
                gap = max(c['nearest_distance_mm'] for c in w['structural_corners'])
                notes.append(f"{w['id']} 最大角点外推 {gap:.1f} mm")
        p(f'{name} 共 {len(record["walls"])} 面墙。' + ('，'.join(notes)+'。' if notes else ''))
    p('支持点范围由原版检测器决定。较大鼓包、缺测和遮挡都可能影响支持点覆盖，因此需要同测区的独立测量来评价实体墙平整度。门窗轮廓和窗框深度来自几何检测，人工测量与点云使用的接触位置也会影响尺寸差异。')
    h('运行证据', 2)
    p('两套输入的 SHA-256 可用于确认原始数据。')
    for name, record in records.items():
        p(f"{name}  {record['cloud']['sha256']}")
    p('本次实验目录下各房间的 report.docx 和 report.html 包含立面图、角点、门窗和各测区结果。summary.json 保存完整数值。wall_points.npz、native_supports.txt、逐域 residuals.npz 和 audit.json 支持复查原始点来源和 RMS。')
    p('复现入口为 inspect_room.py。输入 M04.pcd 或 M26.pcd，指定 --unit m --up 0 0 1 --profile default --out 新目录。')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(args.output)
    with ZipFile(args.output) as package:
        assert package.testzip() is None
    print(args.output)


if __name__ == '__main__':
    main()
