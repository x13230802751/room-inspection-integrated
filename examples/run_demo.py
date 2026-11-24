"""Create a synthetic modular room, inspect it, and leave the editable report on disk."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests"))
from check_pipeline import synthetic, audit


def run(destination):
    destination=destination.resolve()
    if destination.exists():
        raise ValueError(f"Choose an unused output directory. Existing directory: {destination}")
    destination.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=destination.parent,prefix=".demo-") as tmp:
        staging=Path(tmp)/"demo"
        staging.mkdir()
        scan=staging/"synthetic_room.csv"
        synthetic(scan,True,recessed=True)
        result=staging/"inspection"
        subprocess.run([sys.executable,str(ROOT/"inspect_room.py"),str(scan),
                        "--unit","mm","--up","0","1","0","--out",str(result)],check=True)
        summary=audit(str(scan),result)
        windows=json.loads((result/"window_sections.json").read_text(encoding="utf8"))["windows"]
        if len(windows)!=1:
            raise ValueError("Expected one synthetic window.")
        face,deep=windows[0]["face"],windows[0]["deep"]
        doors=[o for w in summary["walls"] for o in w["openings"] if o["type"]=="door"]
        if len(doors)!=2 or abs(face["width_mm"]-1500)>25 or deep["status"]!="candidate" or abs(deep["width_mm"]-1440)>10:
            raise ValueError(f"Synthetic acceptance check failed. Face {face['width_mm']}, recessed {deep['width_mm']}, doors {len(doors)}.")
        staging.rename(destination)
    print(f"Synthetic window: face {face['width_mm']:.2f} mm, recessed {deep['width_mm']:.2f} mm "
          f"at slice centres {deep['depth_range_mm']} mm.")
    print("Editable report:",destination/"inspection"/"report.docx")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=ROOT/"results"/"synthetic-demo")
    args=p.parse_args()
    try:
        run(args.out)
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        p.exit(1,f"{error}\n")
