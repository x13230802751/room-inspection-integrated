# 将完整点云的原版 Efficient RANSAC 支持点和无滤波 SVD RMS 接入 Task 1 五接口。
"""Native-support bridge; isolated imports prevent collision with the legacy SDK."""
import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
from scipy.spatial import cKDTree
from wall_flatness.geometry import fit_plane, roi_frame, inside_polygon, coverage


def framework_root():
    explicit=os.environ.get('TASK1_RMS_FRAMEWORK')
    bundled=Path(__file__).resolve().parents[1]/'native_backend'
    candidates=[Path(explicit)] if explicit else [bundled]+[
        p/name for p in Path(__file__).resolve().parents
        for name in ('room_wall_rms_framework','room-wall-rms-framework')]
    for root in candidates:
        if (root/'room_walls/efficient_ransac.py').is_file() and (root/'room_measurement/corners.py').is_file():
            return root.resolve()
    raise ValueError('Bundled native_backend is missing. Restore the complete repository; no legacy fallback is used.')


def backends():
    root=framework_root()
    name='_task1_native_'+hashlib.sha256(str(root).encode()).hexdigest()[:12]
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,root/'room_walls/__init__.py',submodule_search_locations=[str(root/'room_walls')])
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    corner_name=name+'_corners'
    if corner_name not in sys.modules:
        spec=importlib.util.spec_from_file_location(corner_name,root/'room_measurement/corners.py')
        module=importlib.util.module_from_spec(spec);sys.modules[corner_name]=module;spec.loader.exec_module(module)
    return root,importlib.import_module(name+'.efficient_ransac'),importlib.import_module(name+'.config').Config,sys.modules[corner_name]


def walls(points,config):
    root,engine,NativeConfig,_=backends()
    # The partner SDK's recovery/radius/voxel settings are deliberately not passed.
    cfg=NativeConfig(up=tuple(config.up),seed=config.seed)
    found=engine.discover_native(points,cfg)
    original=np.flatnonzero(np.isfinite(points).all(1));up=np.asarray(cfg.up)
    supports=engine.parse_supports(found['native_detection']['support_text'],len(original))
    low,high=np.quantile(points[original]@up,[.01,.99]);ceilings=[]
    for i,ids in enumerate(supports):
        if len(ids)<3:continue
        try:c,n,_=fit_plane(points[original[ids]])
        except ValueError:continue
        if abs(n@up)>=np.cos(np.deg2rad(15)) and c@up>=high-.2*(high-low):
            if n@up<0:n=-n
            ceilings.append(dict(center_m=c.tolist(),normal=n.tolist(),n_support=len(ids),native_plane_id=i,support_indices=original[ids]))
    ceiling=max(ceilings,key=lambda c:c['n_support']) if ceilings else None
    if ceiling is not None:
        p=points[ceiling['support_indices']];c=np.asarray(ceiling['center_m']);_,_,v=np.linalg.svd(p-c,full_matrices=False)
        area=float(np.prod(np.ptp((p-c)@v[:2].T,axis=0)))
        if area<max(1.,.15*max(w['width_m']*w['height_m'] for w in found['walls'])):ceiling=None
    for wall in found['walls']:
        # Compatibility field only: exact native support, NEVER expanded.
        wall['expanded_indices']=wall['support_indices'].copy()
    found['_native_room']=SimpleNamespace(xyz_m=points,walls=found['walls'],floor=found['floor'],ceiling=ceiling,up=cfg.up)
    found['backend_source_sha256']={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
        ['room_walls/efficient_ransac.py','room_walls/discovery.py','room_walls/config.py','room_measurement/corners.py']}
    return found


def corners(points,discovery,config):
    from room_geometry import section_axis,room_interior
    _,_,_,backend=backends();room=discovery['_native_room'];result=backend.structural_corners(room)
    out={};dimensions=None
    for wall in room.walls:
        entry=result.get('walls',{}).get(wall['id'])
        if entry is None:continue
        q=np.asarray(entry['corners_m'])
        if (q[1]-q[0])@section_axis(wall,room.floor)<0:q=q[[1,0,3,2]]
        ids=wall['support_indices'];dist,nearest=cKDTree(points[ids]).query(q)
        out[wall['id']]=[dict(xyz_m=p.tolist(),nearest_wall_point_index=int(ids[j]),nearest_wall_point_xyz_m=points[ids[j]].tolist(),
            nearest_distance_mm=float(d*1000),extrapolated_over_50mm=bool(d>.05)) for p,j,d in zip(q,nearest,dist)]
    if result.get('room_dimensions'):
        d=result['room_dimensions'];dimensions={k+'_mm':d[k+'_m']*1000 for k in ['length','width','height']}
    ceiling=None if room.ceiling is None else {k:v for k,v in room.ceiling.items() if k!='support_indices'}
    return dict(walls=room.walls,inside_ids=np.flatnonzero(room_interior(points,room.walls)),corners=out,
        ceiling=ceiling,room=dimensions,warnings=[] if result['status']=='ok' else [result['reason']],native_structure=result)


def measure(xyz,roi):
    """Keep all finite supplied points in the 2D footprint; no normal-distance gate."""
    p=np.asarray(xyz,dtype=float)
    if roi.get('unit')!='m':raise ValueError('The native adapter requires metre coordinates and corners')
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all():raise ValueError('Require finite N x 3 native support coordinates')
    if roi.get('slab_half_thickness_mm') is not None:raise ValueError('Native-support RMS does not accept a slab threshold')
    if roi.get('corners') is None:
        ids=np.arange(len(p));cov=None;reference=None
    else:
        c,reference,u,v,polygon,_=roi_frame(np.asarray(roi['corners'],dtype=float),.01)
        uv=np.c_[(p-c)@u,(p-c)@v];ids=np.flatnonzero(inside_polygon(uv,polygon))
        cov=coverage(uv[ids],polygon,.05) if len(ids) else None
    if len(ids)<3:raise ValueError('Fewer than three native points in the measurement region')
    c,n,_=fit_plane(p[ids])
    if reference is not None and n@reference<0:n=-n
    signed=(p[ids]-c)@n*1000
    return dict(indices=ids,signed_mm=signed,plane_center_m=c.tolist(),plane_normal=n.tolist(),
        coverage_fraction=cov,status='ok',warnings=[])


measure.no_slab=True
