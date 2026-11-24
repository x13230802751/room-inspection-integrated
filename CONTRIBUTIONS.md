# Work transferred with this project

**Integrated edition:** the detailed map below describes the partner project's contributions. Current wall discovery and RMS are replaced by `extensions/native_support.py` and the bundled `native_backend`. See [current source fingerprints](docs/source_map.json) and [current project guide](docs/project_guide.md). Historical course reports are not redistributed in this repository.

Use this map when presenting the work, reviewing an implementation or assigning the next change. It describes software responsibilities. The original commit history and author identities belong to their respective repositories.

| Project work | What the recipient can inspect or reproduce |
|---|---|
| Assemble room geometry and local measurement axes | The fitted ground normal supplies height. Intersections of neighbouring walls with the floor and ceiling give four corners per wall. The report retains nearest original rows and extrapolation distances. [Room geometry](room_geometry.py) |
| Locate doors and windows and measure visible openings | Track supported gaps, fit sides and horizontal borders, project widths at the selected height and export centres and corner coordinates. [Detector bridge](openings.py) · [Profile fitter](opening-geometry.js) |
| Distinguish a wall-face aperture from a recessed frame candidate | Search successively deeper slabs, test independent edge support, label the first stable narrowing and retain raw endpoint indices, heights and depths. [Depth rule](depth_profile.py) · [Section exporter](window_sections.py) |
| Compare edge estimators at a fixed section | Keep the opening and section fixed while fitting reveal planes or a 2D contour. Withhold a result if either side fails its support check. [Comparison driver](research/compare_edges.py) · [Contour fitting](research/contour_fit.py) |
| Connect detected wall corners to the RMS calculation | Exclude openings, select the whole-wall four-corner footprint, map residuals back to original rows and carry unavailable states through the results. The two pinned backends supply wall discovery and four-point plane fitting. [Adapter](wall_rms.py) · [Upstream revisions and file hashes](upstream.lock.json) |
| Deliver repeatable reports and interchangeable algorithms | The CLI and local upload page use the same measurement pipeline. A separate writer reads saved geometry and RMS records, exports Word and HTML, and can be replaced without changing detection. [Measurement interfaces](INTERFACE_SPEC.md) · [Report API](REPORT_API.md) |
| Evaluate and hand over the work | The synthetic demonstration exercises the full pipeline with known window widths and two doors. [Synthetic demonstration](examples/run_demo.py) · [Current integration guide](docs/project_guide.md) |

## Upstream attribution

The historical Python SDK remains pinned for partner geometry helpers. It is not the current default wall detector or RMS selector. The default native backend attribution and research/GPL restrictions are recorded in [native provenance](native_backend/PROVENANCE.md). [Historical wall SDK, commit 149d280](https://github.com/x13230802751/wall-rms-pipeline-v3/tree/149d280662e9f6256608efd1896b1744e82cf5d4) · [Geometry helpers, commit 952259c](https://github.com/x13230802751/wall-flatness-v3/tree/952259ce8037f042155139ca3fb7af58cd9e2d5f)

## Continuity with the earlier source ZIP

| Earlier source group | Location in this edition |
|---|---|
| Windows launcher, local upload page and CLI | `run.cmd`, `launch.ps1`, `local_web.py`, `inspect_room.py` |
| Door/window geometry and shallow depth checks | `detect_profile.cjs`, `opening-geometry.js`, `openings.py`, `frame_sections.py` |
| Algorithm loader, example profile, wall and RMS adapters | `algorithms.py`, `profiles/`, `extensions/`, `room_geometry.py`, `wall_rms.py` |
| Nine upstream source modules | `third_party/` in the full kit, with an equivalent pinned installation in the upload edition |
| HTML and editable Word generators | `report.py`, `word_report.py`, accessed through `reporting.py` |
| Editable workflow illustration and printable image | [PNG](assets/measurement_workflow.png) · [Generator](research/draw_whole_wall_workflow.py) |
| README, interface notes, dependency list, ignore file and tests | `README.md`, `INTERFACE_SPEC.md`, `requirements.txt`, `.gitignore`, `tests/` |
