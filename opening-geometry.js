// Door detection receives geometric observations only. Survey references stay in the caller.
const openingGeometry = (() => {
  const checkBands = [8, 10, 12]; // height in decimetres
  function median(values) {
    const a = [...values].sort((x,y) => x-y);
    const i = Math.floor(a.length/2);
    return a.length % 2 ? a[i] : (a[i-1]+a[i])/2;
  }
  function gaps(points, band) {
    const found = [];
    for (let i=3; i<=points.length-3; i++) {
      const left = points[i-1], right = points[i];
      const a = left.local[0], b = right.local[0];
      // At least three observed points close to each edge.
      if (b-a < 0.35 || a-points[i-3].local[0] > 0.08 || points[i+2].local[0]-b > 0.08) continue;
      found.push({left,right,band});
    }
    return found;
  }
  function fit(rows, side) {
    const samples = rows.map(row => row[side].local);
    const line=fitLine(samples.map(([u,,h])=>[h,u]),1);
    return {x_at_1m:line.intercept,slope:line.slope};
  }
  function fitLine(samples, anchor) {
    const slopes = [];
    for (let i=0;i<samples.length;i++) {
      for (let j=0;j<i;j++) {
        const dx=samples[i][0]-samples[j][0];
        if (Math.abs(dx)>1e-8) slopes.push((samples[i][1]-samples[j][1])/dx);
      }
    }
    if (!slopes.length) throw new Error("Samples have insufficient span along the fit direction.");
    const slope = median(slopes);
    const intercept = median(samples.map(([x,y]) => y-slope*(x-anchor)));
    return {intercept,slope};
  }
  function xAt(line, h) { return line.x_at_1m + line.slope*(h-1); }
  function lintel(rows, left, right) {
    // Two consecutive levels with observations across the middle 80% of the opening.
    let previous = false;
    for (let band=19;band<rows.length;band++) {
      const a=xAt(left,band/10), b=xAt(right,band/10), bins=new Set();
      for (const p of rows[band]) {
        const t=(p.local[0]-a)/(b-a);
        if (t>=0.1 && t<0.9) bins.add(Math.min(9, Math.floor((t-0.1)/0.08)));
      }
      const covered=bins.size>=8;
      if (previous && covered) return (band-1)/10;
      previous=covered;
    }
    return null;
  }
  function analyze(rows) {
    for (const row of rows) row.sort((p,q)=>p.local[0]-q.local[0]);
    const candidates = rows.map(gaps);
    const tracks=[];
    for (let band=1;band<=18;band++) {
      if (checkBands.includes(band)) continue;
      for (const gap of candidates[band]) {
        const track=tracks.find(t => Math.abs(t[0].left.local[0]-gap.left.local[0]) <= 0.06 &&
          Math.abs(t[0].right.local[0]-gap.right.local[0]) <= 0.06);
        if (track) track.push(gap);
        else tracks.push([gap]);
      }
    }
    const accepted=[];
    let continuous=0;
    for (const track of tracks) {
      if (track.length<11 || track[0].band>2 || track.at(-1).band<16) continue;
      continuous++;
      const left=fit(track,"left"), right=fit(track,"right");
      const headerBand=lintel(rows,left,right);
      if (headerBand===null) continue;
      const sections=checkBands.map(band => {
        const h=band/10;
        const predicted=(xAt(right,h)-xAt(left,h))*1000;
        const observed=candidates[band].find(g =>
          Math.abs(g.left.local[0]-xAt(left,h))<=0.06 && Math.abs(g.right.local[0]-xAt(right,h))<=0.06);
        return {height_m:h, count:rows[band].length, left:observed?.left ?? null, right:observed?.right ?? null,
          width_mm:observed ? 1000*(observed.right.local[0]-observed.left.local[0]) : null, fitted_width_mm:predicted};
      });
      accepted.push({sections, left_line:left,right_line:right, fit_band_count:track.length,
        upper_coverage_band_m:headerBand,fitted_width_mm:1000*(right.x_at_1m-left.x_at_1m),
        fit_points:track.map(g=>({height_m:g.band/10,left_index:g.left.index,right_index:g.right.index}))});
    }
    return {accepted, trace:{gap_tracks:tracks.length, floor_connected_tracks:continuous, verified_openings:accepted.length}};
  }
  // Windows have an elevated sill. Vertical profiles independently verify it below.
  function windowTracks(rows) {
    const tracks=[];
    for (let band=1;band<rows.length;band++) {
      for (const g of gaps(rows[band],band)) {
        const track=tracks.find(t => Math.abs(t[0].left.local[0]-g.left.local[0])<=0.06 &&
          Math.abs(t[0].right.local[0]-g.right.local[0])<=0.06);
        if (track) track.push(g); else tracks.push([g]);
      }
    }
    return tracks.filter(t=>t[0].band>=2 && t.length>=5 &&
      t.length >= 0.75*(t.at(-1).band-t[0].band+1)).map(t=>({
        left_line:fit(t,"left"),right_line:fit(t,"right"),seed_height:median(t.map(g=>g.band/10)),
        fit_band_count:t.length,fit_points:t.map(g=>({height_m:g.band/10,left_index:g.left.index,right_index:g.right.index}))
      }));
  }
  // Nine narrow columns test whether the same well-bounded void exists vertically.
  function outline(face, seed, type) {
    const left=seed.left_line, right=seed.right_line, probe=seed.seed_height ?? 1;
    const l=xAt(left,probe),r=xAt(right,probe), samples=[];
    for (let i=1;i<=9;i++) {
      const u=l+(r-l)*i/10;
      const col=face.filter(p=>Math.abs(p.u-u)<0.02).sort((a,b)=>a.h-b.h);
      const k=col.findIndex(p=>p.h>probe);
      if (k<1) continue;
      const bottom=col[k-1], top=col[k];
      if (top.h-bottom.h<0.35) continue;
      if (type==="window" ? bottom.h<0.15 : Math.abs(bottom.h)>0.12) continue;
      samples.push({bottom,top,column:i});
    }
    if (samples.length<6) return null;
    const fitSamples=samples.filter(s=>![3,5,7].includes(s.column));
    const checkSamples=samples.filter(s=>[3,5,7].includes(s.column));
    if (fitSamples.length<5 || checkSamples.length<2) return null;
    const edge = side => {
      const observations=fitSamples.map(s=>[s[side].u,s[side].h]);
      const fit=fitLine(observations,0);
      return {h_at_u0:fit.intercept,slope:fit.slope};
    };
    const bottom=edge("bottom"), top=edge("top");
    const consistent=samples.filter(s=>[["bottom",bottom],["top",top]].every(([k,e])=>
      Math.abs(s[k].h-e.h_at_u0-e.slope*s[k].u)<=0.04));
    if (consistent.length<6 || consistent.filter(s=>[3,5,7].includes(s.column)).length<2) return null;
    const heightChecks=checkSamples.map(s=>({
      width_fraction:s.column/10,lower_index:s.bottom.index,upper_index:s.top.index,
      observed_mm:(s.top.h-s.bottom.h)*1000,
      predicted_mm:(top.h_at_u0+top.slope*s.top.u-bottom.h_at_u0-bottom.slope*s.bottom.u)*1000
    }));
    function intersect(side, horizontal) {
      const den=1-side.slope*horizontal.slope;
      if (Math.abs(den)<1e-4) return null;
      const u=(side.x_at_1m+side.slope*(horizontal.h_at_u0-1))/den;
      return [u,horizontal.h_at_u0+horizontal.slope*u];
    }
    const corners=[intersect(left,bottom),intersect(right,bottom),intersect(right,top),intersect(left,top)];
    if (corners.some(p=>p===null)) return null;
    const u=corners.reduce((s,p)=>s+p[0],0)/4;
    const sill=bottom.h_at_u0+bottom.slope*u, head=top.h_at_u0+top.slope*u;
    const mid=(sill+head)/2, widthHeight=type==="door"?1:mid;
    if (head<=sill || widthHeight<=sill || widthHeight>=head) return null;
    return {type,corners_uv_m:corners,center_uv_m:[u,mid],width_at_height_m:widthHeight,
      width_mm:1000*(xAt(right,widthHeight)-xAt(left,widthHeight)),height_mm:1000*(head-sill),
      sill_m:sill,head_m:head,side_bands:seed.fit_band_count,vertical_columns:consistent.length,
      horizontal_evidence:seed.fit_points, vertical_evidence:consistent.map(s=>({column:s.column,bottom_index:s.bottom.index,top_index:s.top.index})),
      height_checks:heightChecks,
      upper_line:top,lower_line:bottom,left_line:left,right_line:right};
  }
  return {analyze, median, xAt, windowTracks, outline};
})();
if (typeof module === "object" && module.exports) module.exports = openingGeometry;
