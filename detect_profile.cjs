// Input triples are little-endian float64: position along wall (m), height (m), original row.
// The previous browser measurement code operates on these same wall-local observations.
const fs = require("node:fs");
const geometry = require("./opening-geometry.js");

function detect(input) {
  if (input.length % 24 !== 0) throw new Error("Invalid binary wall profile");
  const face = [];
  const rows = Array.from({length:19}, () => []);
  for (let offset=0; offset<input.length; offset+=24) {
    const u = input.readDoubleLE(offset);
    const h = input.readDoubleLE(offset+8);
    const index = input.readDoubleLE(offset+16);
    face.push({u,h,index});
    const band = Math.round(h*10);
    if (band<1 || Math.abs(h-band/10)>=0.015) continue;
    while (rows.length<=band) rows.push([]);
    rows[band].push({local:[u,0,h],index});
  }
  const doors = geometry.analyze(rows);
  const windows = geometry.windowTracks(rows);
  const openings = [];
  for (const [type,seeds] of [["door",doors.accepted],["window",windows]]) {
    for (const seed of seeds) {
      const opening = geometry.outline(face,seed,type);
      if (!opening) continue;
      if (type==="door") opening.width_checks = seed.sections.map(s => ({
        height_m:s.height_m, observed_mm:s.width_mm, fitted_mm:s.fitted_width_mm,
        left_index:s.left?.index ?? null, right_index:s.right?.index ?? null
      }));
      openings.push(opening);
    }
  }
  return {openings, candidates:{gap_tracks:doors.trace.gap_tracks,
    near_floor_tracks:doors.trace.floor_connected_tracks, door_seeds:doors.accepted.length,
    window_seeds:windows.length, profile_points:face.length}};
}
try {
  process.stdout.write(JSON.stringify(detect(fs.readFileSync(0))));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
