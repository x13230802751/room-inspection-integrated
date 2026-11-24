"""Look up optional course references after inference on a matching unmodified input."""
import json
from pathlib import Path


def matched_reference(summary):
    cloud = summary["cloud"]
    if cloud["input_unit"] != "m" or list(summary["discovery_config"]["up"]) != [0, 0, 1]:
        return None
    file = Path(__file__).parent / "references" / "manual_reference.json"
    if not file.is_file():
        return None
    refs = json.loads(file.read_text(encoding="utf8"))["rooms"]
    return next((r for r in refs.values() if r["sha256"] == cloud["sha256"]), None)
