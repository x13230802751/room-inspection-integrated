"""Report API v1. Render a saved measurement bundle without loading a geometry backend."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZipFile, BadZipFile

from algorithms import read_profile, select_report

TABLES=("openings.csv","wall_corners.csv","wall_rms.csv","frame_depths.csv","wall_points.npz","native_supports.txt")


def standard_reports(result_dir, summary, window_sections):
    """Render both standard English outputs from the supplied measurement records."""
    from report import make_report
    from word_report import write_word_report
    make_report(result_dir,summary,window_sections)
    write_word_report(result_dir,summary,window_sections)


def section_path(directory, summary):
    path=directory/summary.get("window_sections_file","window_sections.json")
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("The window section file must be within the measurement bundle.")
    return path


def generate_reports(directory, provider=None):
    """Invoke one report provider in a staged result directory with saved geometry."""
    directory=Path(directory)
    summary_bytes=(directory/"summary.json").read_bytes()
    summary=json.loads(summary_bytes)
    if summary.get("format_version")!=2 or "algorithms" not in summary:
        raise ValueError("Report API v1 requires a format_version 2 inspection summary with an algorithm manifest.")
    if summary.get("word_report","report.docx")!="report.docx":
        raise ValueError("Report API v1 uses report.docx as the Word filename.")
    summary["word_report"]="report.docx"
    section_file=section_path(directory,summary)
    section_digest=None
    if section_file.is_file():
        raw=section_file.read_bytes()
        sections=json.loads(raw)
        if (sections.get("schema_version")!="1.0" or sections.get("depth_positive")!="into_opening"
                or sections.get("cloud_sha256")!=summary["cloud"]["sha256"]):
            raise ValueError("Window sections do not match the source scan or supported coordinate contract.")
        section_digest=sha256(raw).hexdigest()
    elif "window_sections_file" in summary:
        raise ValueError(f"Missing the declared window section file {section_file.name}.")
    else:
        sections={"schema_version":"1.0","cloud_sha256":summary["cloud"]["sha256"],"depth_positive":"into_opening",
                  "windows":[],"availability":"not_recorded"}
    writer,descriptor=provider or select_report({})
    summary["reporting"]={"api_version":1,"writer":descriptor}
    writer(directory,summary,sections)
    with ZipFile(directory/"report.docx") as package:
        if "word/document.xml" not in package.namelist() or package.testzip() is not None:
            raise ValueError("The report provider produced an invalid Word document.")
    if not (directory/"report.html").read_text(encoding="utf8").strip():
        raise ValueError("The report provider produced an empty HTML file.")
    record={"report_api_version":1, "summary_sha256":sha256(summary_bytes).hexdigest(),
            "window_sections_sha256":section_digest, "cloud_sha256":summary["cloud"]["sha256"],
            "rms":summary["algorithms"]["stages"]["rms"],"writer":descriptor,
            "files":{"word":"report.docx","html":"report.html"}}
    (directory/"report_manifest.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf8")


def render_saved(source, target, profile="default"):
    """Publish a fresh report bundle. Source measurements are read only."""
    source,target=Path(source).resolve(),Path(target).resolve()
    if target.exists() or target.is_relative_to(source):
        raise ValueError("Choose a new report directory outside the source result directory.")
    summary=json.loads((source/"summary.json").read_bytes())
    files=[source/"summary.json",section_path(source,summary),*(source/name for name in TABLES)]
    writer=select_report(read_profile(profile))
    target.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=target.parent,prefix=".task1-render-") as temp:
        draft=Path(temp)/"result"
        draft.mkdir()
        for file in files:
            if file.is_file():
                dest=draft/file.relative_to(source)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(file,dest)
        if (source/"walls").is_dir():
            shutil.copytree(source/"walls",draft/"walls",dirs_exist_ok=True)
        generate_reports(draft,writer)
        draft.rename(target)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result",type=Path,help="completed result directory containing summary.json")
    parser.add_argument("--out",required=True,type=Path,help="new report bundle directory")
    parser.add_argument("--profile",default="default",help="use only the report property of this local profile")
    args=parser.parse_args()
    try:
        render_saved(args.result,args.out,args.profile)
    except (OSError,ValueError,KeyError,ImportError,BadZipFile) as error:
        parser.exit(1,f"Report generation failed. {error}\n")
    print("Word report:",args.out.resolve()/"report.docx")
