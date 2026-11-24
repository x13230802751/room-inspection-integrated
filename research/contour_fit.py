"""Single-wall alpha-shape boundary and oriented line fitting (distances in metres)."""
import numpy as np
from scipy.spatial import Delaunay


def contour_edges(uv, alpha_radius=.025):
    # Preserve observed points, thin dense cells, then keep 2-D alpha-complex triangles.
    _, idx=np.unique(np.floor(uv/.005).astype(int),axis=0,return_index=True)
    p=uv[idx]
    tri=Delaunay(p).simplices
    a,b,c=p[tri[:,0]],p[tri[:,1]],p[tri[:,2]]
    ab,bc,ca=b-a,c-b,a-c
    cross=ab[:,0]*(-ca[:,1])-ab[:,1]*(-ca[:,0])
    product=np.linalg.norm(ab,axis=1)*np.linalg.norm(bc,axis=1)*np.linalg.norm(ca,axis=1)
    tri=tri[(cross>0)&(product<=2*alpha_radius*cross)]
    pairs=np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]])
    _,first,count=np.unique(np.sort(pairs,axis=1),axis=0,return_index=True,return_counts=True)
    pair=pairs[first[count==1]]
    edge=p[pair[:,1]]-p[pair[:,0]]
    normal=np.column_stack((edge[:,1],-edge[:,0]))/np.linalg.norm(edge,axis=1)[:,None]
    return p[pair].mean(axis=1),normal


def estimate(uv,o):
    edges,n=contour_edges(uv)
    u,h=edges.T
    l,r=[o[key]["x_at_1m"]+o[key]["slope"]*(h-1) for key in ("left_line","right_line")]
    b,t=[o[key]["h_at_u0"]+o[key]["slope"]*u for key in ("lower_line","upper_line")]
    rows=(h-o["sill_m"])/(o["head_m"]-o["sill_m"])
    cols=(u-l)/np.maximum(.01,r-l)
    heights=o["width_at_height_m"]; horizontal=o["center_uv_m"][0]
    values={}; audit={}
    for name,delta,fraction,alignment,at,x,y in [
        ("left",u-l,rows,n[:,0],heights,h,u),("right",u-r,rows,-n[:,0],heights,h,u),
        ("bottom",h-b,cols,n[:,1],horizontal,u,h),("top",h-t,cols,-n[:,1],horizontal,u,h)]:
        selected=(abs(delta)<.080)&(fraction>=.10)&(fraction<=.90)&(alignment>=.707)
        xy=np.column_stack([x[selected]-at,y[selected]])
        blocks=(10*fraction[selected]).astype(int)
        test=np.isin(blocks,[2,5,8]); train=xy[~test]
        audit[name]={"samples":len(xy),"held_out":int(test.sum())}
        if len(train)<20 or test.sum()<10: continue
        rng=np.random.default_rng(7023); best=np.zeros(len(train),dtype=bool)
        for _ in range(220):
            a,b=train[rng.choice(len(train),2,replace=False)]
            d=b-a
            if abs(d[0])<.05 or abs(d[1])>.58*abs(d[0]): continue
            residual=np.abs((train[:,1]-a[1])*d[0]-(train[:,0]-a[0])*d[1])/np.linalg.norm(d)
            if (residual<=.006).sum()>best.sum(): best=residual<=.006
        if best.sum()<10 or best.mean()<.70: continue
        center=train[best].mean(0)
        normal=np.linalg.svd(train[best]-center,full_matrices=False)[2][-1]
        residual=abs((xy-center)@normal)
        if np.mean(residual[test]<=.006)<.70 or len(np.unique(blocks[residual<=.006]))<7: continue
        audit[name]["holdout_median_mm"]=float(np.median(residual[test])*1000)
        values[name]=float(center@normal/normal[1])
    return {k:(values[last]-values[first])*1000 if first in values and last in values else None
            for k,first,last in [("width","left","right"),("height","bottom","top")]},audit
