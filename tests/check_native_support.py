# 验证无厚度筛选、原始索引映射、候选洞口策略及完整运行的原版支持点一致性。
from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'third_party')]
from extensions.native_support import measure,backends
from wall_rms import measure_scope,wall_pool


class NativeContractTests(unittest.TestCase):
    def test_no_50mm_slab_or_residual_filter(self):
        x,y=np.meshgrid(np.linspace(0,1,6),np.linspace(0,1,6));p=np.c_[x.ravel(),y.ravel(),np.zeros(x.size)]
        p[12,2]=.08
        roi=dict(unit='m',corners=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],slab_half_thickness_mm=None)
        result=measure(p,roi)
        np.testing.assert_array_equal(result['indices'],np.arange(len(p)))
        with TemporaryDirectory() as d:
            # Non-contiguous original indices must survive the wrapper.
            cloud=np.zeros((len(p)*2,3));ids=np.arange(len(p))*2;cloud[ids]=p
            out=measure_scope(Path(d),cloud,ids,roi['corners'],'test','W01','patch',measure)
            saved=json.loads((Path(d)/out['roi_file']).read_text())
            self.assertIsNone(saved['slab_half_thickness_mm'])
            with np.load(Path(d)/out['residual_file']) as residual:np.testing.assert_array_equal(residual['point_index'],ids)

    def test_unconfirmed_openings_do_not_change_measurement_pool(self):
        p=np.array([[0,0,0],[.5,0,.5],[1,0,1],[2,0,2.]])
        wall=dict(expanded_indices=np.arange(4),plane_center_m=[0,0,0],plane_normal=[0,1,0])
        floor=dict(center_m=[0,0,0],normal=[0,0,1]);o=dict(status='candidate',corners_uv_m=[[.2,.2],[.8,.2],[.8,.8],[.2,.8]])
        np.testing.assert_array_equal(wall_pool(p,wall,floor,[o],confirmed_only=True),np.arange(4))
        o['status']='confirmed';np.testing.assert_array_equal(wall_pool(p,wall,floor,[o],confirmed_only=True),[0,2,3])

    def test_legacy_import_is_not_replaced(self):
        import room_walls.config as legacy
        _,_,config,_=backends()
        self.assertNotEqual(legacy.Config,config)
        self.assertEqual(config().backend,'efficient_ransac')


def audit(source,folder):
    from wall_flatness.io import read_cloud
    from check_pipeline import audit as common_audit
    common_audit(source,folder)
    data=json.loads((folder/'summary.json').read_text(encoding='utf-8'));points,_=read_cloud(source,with_hash=True)
    if data['cloud']['input_unit']=='mm':points*=.001
    original=np.flatnonzero(np.isfinite(points).all(1));_,engine,_,_=backends()
    native=engine.parse_supports((folder/'native_supports.txt').read_text(),len(original))
    assert data['native_detection']['n_detector_input']==len(original)
    assert data['filter']=='none' and data['recovery']=='none'
    rows=[]
    with np.load(folder/'wall_points.npz') as pools:
        for wall in data['walls']:
            ids=pools[wall['id']+'_assigned'];expected=original[np.sort(np.concatenate([native[i] for i in wall['native_plane_ids']]))]
            np.testing.assert_array_equal(ids,expected)
            m=wall['support']
            with np.load(folder/m['residual_file']) as residual:
                np.testing.assert_array_equal(residual['point_index'],ids)
                p=points[ids];q=p-p.mean(0);rms=np.sqrt(max(0,np.linalg.eigvalsh(q.T@q/len(p))[0]))*1000
                assert abs(rms-m['rms_mm'])<1e-6
            for key in ('support','whole','patch'):
                if wall[key].get('roi_file'):
                    roi=json.loads((folder/wall[key]['roi_file']).read_text());assert roi['slab_half_thickness_mm'] is None
            rows.append(dict(wall=wall['id'],support_rms_mm=m['rms_mm'],n_support=len(ids)))
    return dict(source=data['cloud']['file'],sha256=data['cloud']['sha256'],exact_native_membership=True,
        n_input=len(points),n_walls=len(rows),structural_status='ok' if data.get('room') else 'needs_review',walls=rows)


if __name__=='__main__':
    if len(sys.argv)==3:print(json.dumps(audit(sys.argv[1],Path(sys.argv[2])),indent=2))
    else:unittest.main()
