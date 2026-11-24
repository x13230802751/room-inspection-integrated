"""Install the exact two upstream measurement backends used by this edition."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def canonical(source, entry):
    data = source.replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    if digest == entry["english_sha256"]:
        return data
    if digest == entry["upstream_sha256"] and data.startswith(b"# "):
        # The English source edition omits the verified one-line module description.
        body = data.partition(b"\n")[2]
        if hashlib.sha256(body).hexdigest() == entry["english_sha256"]:
            return body
    raise ValueError(f'Unexpected source fingerprint for {entry["install"]}.')


def install(offline=None):
    groups = json.loads((ROOT/"upstream.lock.json").read_text(encoding="utf8"))["packages"]
    target = ROOT/"third_party"
    if offline:
        offline = offline.resolve()
        if (offline/"third_party").is_dir():
            offline = offline/"third_party"
    with TemporaryDirectory(dir=ROOT, prefix=".backend-setup-") as tmp:
        pending = Path(tmp)/"verified"
        for group in groups:
            for entry in group["files"]:
                rel = entry["install"]
                existing = target/rel
                if existing.is_file():
                    canonical(existing.read_bytes(), entry)
                    continue
                if offline:
                    source = (offline/rel).read_bytes()
                else:
                    url = f'https://raw.githubusercontent.com/{group["repository"]}/{group["commit"]}/{entry["source"]}'
                    try:
                        with urlopen(Request(url,headers={"User-Agent":"Task1-backend-setup"}),timeout=20) as reply:
                            source = reply.read()
                    except (URLError,TimeoutError) as error:
                        raise ValueError("Could not retrieve the pinned upstream file. "
                                         "Use --from-handoff PATH with the complete partner project. "
                                         f"Source URL {url}. {error}") from error
                location = pending/rel
                location.parent.mkdir(parents=True,exist_ok=True)
                location.write_text(canonical(source,entry).decode("utf8"),encoding="utf8")
        if pending.exists():
            if not target.exists():
                pending.rename(target)
            else:
                for source in sorted(pending.rglob("*.py")):
                    dest=target/source.relative_to(pending)
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    if dest.exists():
                        if source.read_bytes().replace(b"\r\n",b"\n")!=dest.read_bytes().replace(b"\r\n",b"\n"):
                            raise ValueError(f"Concurrent change at {dest}.")
                    else:
                        source.rename(dest)
    print("Verified all nine modules from the two pinned upstream backends.")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-handoff",type=Path,help="complete project directory or its third_party folder, for offline setup")
    args=parser.parse_args()
    try:
        install(args.from_handoff)
    except (OSError,ValueError) as error:
        parser.exit(1,f"Backend setup failed. {error}\n")
