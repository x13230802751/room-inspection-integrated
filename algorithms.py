"""Resolve locally installed measurement algorithms from named JSON profiles."""
from dataclasses import dataclass, replace
from functools import partial
import hashlib
from importlib import import_module
import inspect
import json
from pathlib import Path
import re

PROFILES = Path(__file__).resolve().parent / "profiles"
DEFAULTS = {
    "walls": ("extensions.native_support:walls", "Efficient RANSAC exact native supports; no recovery", 2),
    "corners": ("room_geometry:room_boundaries", "Partner room enclosure and structural intersections", 3),
    "openings": ("openings:profile_candidates", "Horizontal and vertical profile fitting", 6),
    "patch": ("wall_rms:supported_patch", "Supported patch nearest the wall centre", 5),
    "rms": ("extensions.native_support:measure", "Original-coordinate SVD RMS; no slab or filtering", 2),
}


def profile_names():
    return ["default", *sorted(p.stem for p in PROFILES.glob("*.json") if p.stem!="default")]


@dataclass
class Algorithms:
    walls: object
    corners: object
    openings: object
    patch: object
    rms: object
    manifest: dict
    report: tuple | None = None

    def for_cloud(self, context):
        hooks={}
        for stage in DEFAULTS:
            function=getattr(self,stage)
            if "context" in inspect.signature(function).parameters:
                hooks[stage]=partial(function,context=context)
        return replace(self,**hooks) if hooks else self


@dataclass(frozen=True)
class CloudContext:
    source: str
    input_unit: str
    up: tuple
    sha256: str
    point_count: int


def read_profile(name="default"):
    profile = {}
    if name!="default":
        path = Path(name)
        if path.suffix!=".json":
            if name not in profile_names():
                raise ValueError(f"Unknown algorithm profile {name}")
            path = PROFILES / (name+".json")
        profile = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(profile,dict) or profile.get("api_version")!=1:
            raise ValueError("The algorithm profile requires api_version 1.")
    return profile


def resolve_callable(stage, default_spec, override, *, use_cloud_context=False):
    default,label,arity=default_spec
    if not isinstance(override,dict) or set(override)-{"call","label","options"}:
        raise ValueError(f"{stage} accepts call, label and options.")
    address=override.get("call",default)
    options=override.get("options",{})
    if (not isinstance(address,str) or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*",address)
            or not isinstance(options,dict) or "context" in options):
        raise ValueError(f"{stage} requires a module:function address and a JSON options object.")
    module,qualname=address.split(":")
    try:
        function=getattr(import_module(module),qualname)
        signature=inspect.signature(function)
        extra={"context":None} if use_cloud_context and "context" in signature.parameters else {}
        signature.bind(*([None]*arity),**extra,**options)
    except (AttributeError,ImportError,TypeError,ValueError) as error:
        raise ValueError(f"{stage} could not load or bind {address}. {error}") from error
    file=inspect.getsourcefile(function)
    spec={"call":address, "label":override.get("label",label if address==default else address), "options":options,
          "source_sha256":hashlib.sha256(Path(file).read_bytes()).hexdigest() if file else None}
    return partial(function,**options),spec


def select_report(profile):
    return resolve_callable("report",("reporting:standard_reports","English Word and HTML",3),profile.get("report",{}))


def load_profile(name="default"):
    profile=read_profile(name)
    stages = profile.get("stages",{})
    if not isinstance(stages,dict) or set(stages)-DEFAULTS.keys():
        raise ValueError("The algorithm profile contains an unknown stage.")
    functions = {}
    manifest = {"api_version":1, "name":profile.get("name", "Default" if name=="default" else Path(name).stem), "stages":{}}
    for stage,default_spec in DEFAULTS.items():
        functions[stage],manifest["stages"][stage]=resolve_callable(stage,default_spec,stages.get(stage,{}),use_cloud_context=True)
    return Algorithms(**functions,manifest=manifest,report=select_report(profile))
