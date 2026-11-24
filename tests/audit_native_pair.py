# 独立审计 M04/M26 完整输出，并与独立框架的八面墙支持点 RMS 对照。
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'third_party')]
from check_native_support import audit
from extensions.native_support import framework_root


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cloud-root',type=Path,required=True);args=parser.parse_args()
    baseline=json.loads((ROOT/'validation/native_baseline.json').read_text(encoding='utf-8'))
    records=[];max_delta=0.
    for name in ['M04','M26']:
        r=audit(str(args.cloud_root/(name+'.pcd')),ROOT/'results'/f'{name}_native')
        ref=next(x for x in baseline['records'] if x['room']==name);assert r['sha256']==ref['source_sha256']
        for row in r['walls']:
            other=next(x for x in ref['walls'] if x['wall']==row['wall'])
            assert row['n_support']==other['n_support']
            delta=abs(row['support_rms_mm']-other['support_rms_mm']);assert delta<1e-9
            max_delta=max(max_delta,delta)
        result=json.loads((ROOT/'results'/f'{name}_native'/'summary.json').read_text(encoding='utf-8'))
        r['opening_candidates']=[{'wall':w['id'],'type':o['type'],'status':o['status']} for w in result['walls'] for o in w['openings']]
        r['valid_patches']=sum(w['patch']['status']!='unavailable' for w in result['walls'])
        r['room_dimensions_mm']=result['room'];r['whole_statuses']={w['id']:w['whole']['status'] for w in result['walls']};records.append(r)
    output=dict(status='passed',records=records,max_baseline_difference_mm=max_delta,
        physical_accuracy_validated=False,definition='Exact native-support RMS; geometry-only eligibility and ROI masking for separate whole/patch measurements')
    (ROOT/'validation/integration_verification.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print('Verified all eight native support sets and RMS values; maximum difference (mm):',max_delta)


if __name__=='__main__':main()
