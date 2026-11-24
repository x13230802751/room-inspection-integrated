"""Local file picker and result viewer for the same measurement CLI."""
import argparse
from datetime import datetime
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
from urllib.parse import parse_qs, quote, unquote, urlsplit
from html import escape
from uuid import uuid4
import webbrowser
from algorithms import profile_names

HERE = Path(__file__).resolve().parent
UP = {"z":"0 0 1", "y":"0 1 0", "x":"1 0 0", "-z":"0 0 -1", "-y":"0 -1 0", "-x":"-1 0 0"}
PAGE = """<!DOCTYPE html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Room point cloud inspection</title><style>
:root{font:16px/1.6 "Source Sans 3","Microsoft YaHei",sans-serif;color:#1c3e48;background:#eff5f3}
*{box-sizing:border-box}body{margin:0}main{max-width:720px;margin:clamp(2rem,8vh,6rem) auto;padding:1.5rem}
h1{font-size:clamp(2rem,5vw,3.25rem);line-height:1.18;margin:.45rem 0}p{margin:.5rem 0 1.4rem;color:#435e66}
form{background:white;border:1px solid #cadad5;border-top:5px solid #116765;border-radius:10px;padding:clamp(1rem,4vw,2rem)}
label{display:block;font-weight:600;margin-bottom:.25rem}input,select,button{font:inherit}
input[type=file]{width:100%;padding:1rem .7rem;background:#f2f7f5;border:1px dashed #83a39c;border-radius:6px}
.row{display:flex;gap:1.4rem;flex-wrap:wrap;margin:1.2rem 0}.row>div{flex:1;min-width:130px}
select{width:100%;padding:.42rem;border:1px solid #9eafad;border-radius:4px;color:inherit;background:white}
button{border:0;background:#12655f;color:white;padding:.6rem 1.35rem;border-radius:5px;cursor:pointer;font-weight:600}
button:disabled{opacity:.6;cursor:wait}#status{margin:.7rem 0 0;min-height:1.55rem}small{color:#536e72}
</style><main><h1>Room point cloud inspection</h1><p>Select a single-room scan to measure openings, wall corners and wall flatness.</p>
<form id="form"><label for="file">Point cloud file</label><input id="file" type="file" accept=".pcd,.csv" required>
<small>ASCII or binary PCD and CSV with x, y and z columns. The scan is processed on this computer.</small>
<div class="row"><div><label for="unit">Input units</label><select id="unit"><option value="m">Metres (course PCD)</option><option value="mm">Millimetres</option></select></div>
<div><label for="up">Up direction</label><select id="up"><option value="z">+Z (course PCD)</option><option value="y">+Y</option><option value="x">+X</option><option value="-z">−Z</option><option value="-y">−Y</option><option value="-x">−X</option></select></div></div>
<div class="row"><div><label for="profile">Algorithm profile</label><select id="profile">PROFILE_OPTIONS</select></div></div>
<button id="run" type="submit">Measure and create Word report</button><p id="status" role="status" aria-live="polite"></p></form>
<script>const byId=id=>document.getElementById(id);
byId('form').addEventListener('submit',async event=>{
 event.preventDefault();const file=byId('file').files[0],button=byId('run'),status=byId('status');
 if(!file)return;button.disabled=true;status.textContent='Fitting walls and openings and calculating wall RMS...';
 try{const params=new URLSearchParams({name:file.name,unit:byId('unit').value,up:byId('up').value,profile:byId('profile').value});
 const response=await fetch('/inspect?'+params,{method:'POST',body:file,headers:{'X-Task1-Token':'TOKEN_VALUE'}});
 const result=await response.json();if(!response.ok)throw Error(result.error);
 location.assign(result.report+'?word=1');}catch(error){status.textContent=error.message;button.disabled=false;}
});window.addEventListener('pageshow',()=>{byId('run').disabled=false;byId('status').textContent=''});</script></main></html>"""


class Inspector(BaseHTTPRequestHandler):
    def reply(self, status, payload, kind="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf8")
        self.send_response(status)
        self.send_header("Content-Type",kind)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Host")!=self.server.authority:
            return self.reply(403,{"error":"Use the local address shown in the launcher."})
        path = unquote(urlsplit(self.path).path)
        if path=="/":
            names={"default":"Efficient RANSAC native supports (no filtering)"}
            options="".join(f'<option value="{escape(key,quote=True)}">{escape(names.get(key,key))}</option>' for key in profile_names())
            return self.reply(200,PAGE.replace("TOKEN_VALUE",self.server.token).replace("PROFILE_OPTIONS",options).encode("utf8"),"text/html; charset=utf-8")
        parts = path.split("/",3)
        if len(parts)!=4 or parts[1]!="results" or parts[2] not in self.server.served:
            return self.reply(404,{"error":"No results for this run."})
        directory = self.server.served[parts[2]]
        file = (directory/parts[3]).resolve()
        if not file.is_relative_to(directory) or not file.is_file():
            return self.reply(404,{"error":"Result file not found."})
        self.send_response(200)
        if file.name=="report.docx":
            self.send_header("Content-Type","application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Disposition","attachment; filename=report.docx; filename*=UTF-8''"+quote(directory.name.rsplit("_",3)[0]+"_Inspection.docx",safe=""))
        else:
            self.send_header("Content-Type",mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("Content-Length",str(file.stat().st_size))
        self.end_headers()
        with file.open("rb") as f:
            shutil.copyfileobj(f,self.wfile)

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path!="/inspect":
            return self.reply(404,{"error":"Unknown measurement request."})
        if self.headers.get("Host")!=self.server.authority or not hmac.compare_digest(
                self.headers.get("X-Task1-Token","").encode("utf8"),self.server.token.encode("ascii")):
            return self.reply(403,{"error":"Refresh the local inspection page."})
        if not self.server.busy.acquire(blocking=False):
            return self.reply(409,{"error":"An inspection is running. Retry when it finishes."})
        try:
            params = parse_qs(parsed.query)
            name = params.get("name",[""])[0]
            unit = params.get("unit",["m"])[0]
            up = params.get("up",["z"])[0]
            profile = params.get("profile",["default"])[0]
            if profile not in profile_names():
                raise ValueError("Choose an installed algorithm profile.")
            if (not name or len(name)>200 or re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or PureWindowsPath(name).is_reserved()
                    or Path(name).suffix.lower() not in (".pcd",".csv")):
                raise ValueError("Use a valid PCD or CSV filename.")
            if unit not in ("m","mm") or up not in UP:
                raise ValueError("Invalid input units or up direction.")
            length = int(self.headers.get("Content-Length","0"))
            if not 0<length<=2_000_000_000:
                raise ValueError("The file is empty or exceeds the 2 GB upload limit.")
            tag = datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid4().hex[:8]
            target = self.server.output/(Path(name).stem+"_"+tag)
            with TemporaryDirectory(prefix="task1-cloud-") as stage:
                source = Path(stage)/name
                with source.open("wb") as f:
                    while length:
                        block = self.rfile.read(min(length,1024*1024))
                        if not block:
                            raise ValueError("The file transfer was incomplete.")
                        f.write(block)
                        length -= len(block)
                command = [sys.executable,str(HERE/"inspect_room.py"),str(source),"--out",str(target),
                           "--unit",unit,"--up",*UP[up].split(),"--profile",profile]
                p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   encoding="utf8", errors="replace", env={**os.environ,"PYTHONIOENCODING":"utf-8"})
                if p.returncode:
                    raise ValueError(p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "The inspection did not finish.")
            self.server.served[tag] = target
            self.reply(200,{"report":"/results/"+tag+"/report.html","word":"/results/"+tag+"/report.docx"})
        except (ValueError,OSError) as error:
            self.reply(400,{"error":str(error)})
        finally:
            self.server.busy.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--results",type=Path,default=HERE/"results")
    args = parser.parse_args()
    args.results.mkdir(parents=True,exist_ok=True)
    with ThreadingHTTPServer(("127.0.0.1",0),Inspector) as site:
        site.output = args.results.resolve()
        site.served = {}
        site.busy = threading.Lock()
        site.token = secrets.token_hex(24)
        site.authority = "127.0.0.1:"+str(site.server_port)
        url = "http://"+site.authority+"/"
        print(f"Local inspection page  {url}\nResults directory  {site.output}\nClose this window to stop the local server.",flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            site.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__=="__main__":
    main()
