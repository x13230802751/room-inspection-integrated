"""Check a Python-only replacement detector and per-cloud context without a Node process."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/"third_party")]
from algorithms import CloudContext, load_profile
from openings import position_openings


def alternate(points, inside_ids, wall, floor, corners, node, *, context, threshold):
    assert node is None and context.input_unit=="mm" and threshold==3
    assert context.point_count==len(points) and len(inside_ids)==len(points)
    return [{"type":"window","corners_uv_m":np.array([[0.,.6],[1.5,.6],[1.5,1.9],[0.,1.9]])}], {}


def check():
    with TemporaryDirectory() as d:
        spec=Path(d)/"custom.json"
        spec.write_text(json.dumps({"api_version":1,"stages":{"openings":{
            "call":"__main__:alternate","options":{"threshold":3}}}}),encoding="utf8")
        chosen=load_profile(str(spec))
        context=CloudContext("sample.csv","mm",(0.,0.,1.),"test",4)
        chosen=chosen.for_cloud(context)
        wall={"id":"W1","plane_center_m":[1,2,3],"plane_normal":[0,1,0]}
        floor={"center_m":[0,0,0],"normal":[0,0,1]}
        items,_=chosen.openings(np.zeros((4,3)),np.arange(4),wall,floor,[],None)
        o=position_openings(items,wall,floor)[0]
        assert o["id"]=="W1-01"
        np.testing.assert_allclose([o["width_mm"],o["height_mm"],o["width_at_height_m"]],[1500,1300,1.25])
        np.testing.assert_allclose(o["center_xyz_m"],[1.75,2.,1.25])
        assert chosen.manifest["stages"]["openings"]["options"]=={"threshold":3}
        assert chosen.manifest["stages"]["rms"]["call"]=="extensions.native_support:measure"
        spec.write_text('{"api_version":1,"stages":{"bad-stage":{}}}',encoding="utf8")
        try:
            load_profile(str(spec))
        except ValueError:
            pass
        else:
            raise AssertionError("Unknown algorithm stages must be rejected")
    print("Custom detector, optional context, geometry conversion and profile validation passed.")


if __name__=="__main__":
    check()
