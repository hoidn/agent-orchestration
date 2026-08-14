"""Controller-owned F1v2 configuration-ownership evaluator.

Candidate records name paths and claims.  This module alone executes probes,
walks consumers, classifies bypasses, and derives hard-clause observations.
"""

from __future__ import annotations

import ast
import base64
import builtins
from collections.abc import Callable, Mapping, Sequence
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
from typing import Any, NoReturn, cast

from scripts.experiments.es.task_package import (
    F1_BYPASS_CLASSES,
    F1_CONFIG_RESOLUTION_ROLES,
    F1_HARD_CLAUSE_IDS,
    F1_PROVIDER_VISIBLE_DESELECTORS,
    F1_PROVIDER_VISIBLE_SELECTORS,
    F1_REQUIRED_OUTCOMES,
    TaskPackageError,
    _is_configuration_name,
    load_candidate_config_evidence,
    load_configuration_consumer_census,
    load_config_resolution_probe_request,
    load_config_resolution_probe_result,
    load_task_profile,
    load_visible_check_manifest,
    load_visible_task_contract,
    scan_workspace_configuration_consumers,
)


HARD_CLAUSE_IDS = F1_HARD_CLAUSE_IDS
CONFIG_RESOLUTION_ROLES = F1_CONFIG_RESOLUTION_ROLES
BYPASS_CLASSES = F1_BYPASS_CLASSES
DISPOSITIONS = (
    "PRODUCT_DEFECT",
    "ORACLE_DEFECT",
    "SPEC_AMBIGUITY",
    "INFRASTRUCTURE",
    "UNRESOLVED",
)
REVIEWER_PERSPECTIVES = (
    "SCIENTIFIC_APPLICATION_SEMANTICS",
    "API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
)

CALIBRATION_DEFECT_CLAUSES = {
    "ambient_configuration_read": ("F1-H10-BYPASS-ORACLE",),
    "bridge_field_lost": ("F1-H05-STRICT-INPUT-CONTRACT",),
    "cross_surface_divergence": ("F1-H09-CROSS-SURFACE-COHERENCE",),
    "duplicated_public_field_table": ("F1-H06-DERIVED-PUBLIC-FIELDS",),
    "facade_only_resolver": ("F1-H07-CONSUMER-CLOSURE",),
    "ill_typed_field_coerced": ("F1-H05-STRICT-INPUT-CONTRACT",),
    "legacy_state_mutation": ("F1-H10-BYPASS-ORACLE",),
    "lost_provenance": ("F1-H08-PROVENANCE-ROUNDTRIP",),
    "noncanonical_mode_coercion": ("F1-H09-CROSS-SURFACE-COHERENCE",),
    "partial_transaction_mutation": ("F1-H04-TRANSACTIONAL-APPLICATION",),
    "reversed_precedence": ("F1-H03-PUBLIC-RESOLUTION",),
    "sampling_field_lost": ("F1-H05-STRICT-INPUT-CONTRACT",),
    "study_direct_construction": ("F1-H07-CONSUMER-CLOSURE",),
    "tolerant_compatibility_loader": ("F1-H10-BYPASS-ORACLE",),
    "unknown_field_accepted": ("F1-H05-STRICT-INPUT-CONTRACT",),
    "wrapper_deep_old_path": ("F1-H10-BYPASS-ORACLE",),
}
CALIBRATION_POSITIVE_CASE_IDS = (
    "cli_patch",
    "file_mapping",
    "fresh_process_provenance",
    "precedence",
    "public_cli",
    "study_script",
    "strict_roundtrip",
    "tensorflow_backend",
    "torch_backend",
    "workflow_component",
)

_CANDIDATE_AUTHORITY_FIELDS = frozenset(
    {"decision", "disposition", "evaluator_observations", "hard_findings", "passed", "satisfied"}
)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_F1_ROOT = _REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es"
_F1_EVIDENCE_ROOT = (
    _REPOSITORY_ROOT
    / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2"
)
_F1_CALIBRATION_CASES = (
    _REPOSITORY_ROOT / "tests/experiments/fixtures/es_f1/calibration-cases.json"
)
_F1_FIXTURE_ADAPTER = (
    _REPOSITORY_ROOT
    / "tests/experiments/fixtures/es_f1/config_resolution_adapter.py"
)
_SHA256_PREFIX = "sha256:"
_FORBIDDEN_IMPORT_PREFIXES = (
    "PtychoNN",
    "notebooks.archive.ePIE_recon_simulation",
    "ptycho.FRC",
    "ptycho.evaluation",
    "scripts.orchestration",
)

_AUDITED_PROJECTION_WRAPPER = r'''import json,os,pathlib,runpy,sys
events=[]
recording=True
roots=tuple(pathlib.Path(value).resolve(strict=True) for value in json.loads(sys.argv[1]))
program=pathlib.Path(sys.argv[2]).resolve(strict=True)
audit_path=pathlib.Path(sys.argv[3])
workspace=pathlib.Path(sys.argv[4]).resolve(strict=True)
cwd=pathlib.Path(sys.argv[5]).resolve(strict=True)
forbidden=("PtychoNN","notebooks.archive.ePIE_recon_simulation","ptycho.FRC","ptycho.evaluation","scripts.orchestration")
child_events={"subprocess.Popen","os.system","os.posix_spawn","os.posix_spawnp","os.exec","os.fork","os.forkpty","pty.spawn"}
def audit(event,args):
    if not recording:return
    if event=="import" and args:
        value=str(args[0])
        if any(value==prefix or value.startswith(prefix+".") for prefix in forbidden):
            events.append({"event":"forbidden_import","value":value})
            raise PermissionError("candidate import is excluded")
    elif event=="open" and args:
        value=args[0]
        if isinstance(value,(str,bytes)):
            decoded=value.decode(errors="replace") if isinstance(value,bytes) else value
            path=pathlib.Path(decoded)
            if not path.is_absolute():path=pathlib.Path.cwd()/path
            resolved=path.resolve(strict=False)
            mode=args[1] if len(args)>1 else None
            flags=args[2] if len(args)>2 else None
            writing=(isinstance(mode,str) and any(token in mode for token in "wax+")) or (isinstance(flags,int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
            if writing and any(resolved.is_relative_to(root) for root in roots):
                events.append({"event":"workspace_write_attempt","value":str(resolved)})
                raise PermissionError("candidate workspace is evaluator-read-only")
    elif event in child_events:
        events.append({"event":"unaudited_child_process","value":event})
        raise PermissionError("candidate child process is outside the evaluator audit boundary")
sys.addaudithook(audit)
sys.path.insert(0,str(workspace))
os.chdir(cwd)
try:runpy.run_path(str(program),run_name="__main__")
finally:
    recording=False
    forbidden_loaded=sorted(name for name in sys.modules if any(name==prefix or name.startswith(prefix+".") for prefix in forbidden))
    for name in forbidden_loaded:events.append({"event":"forbidden_module_loaded","value":name})
    outside=[]
    for name,module in tuple(sys.modules.items()):
        if not (name=="ptycho" or name.startswith("ptycho.") or name=="ptycho_torch" or name.startswith("ptycho_torch.")):continue
        values=[]
        origin=getattr(getattr(module,"__spec__",None),"origin",None)
        if isinstance(origin,str):values.append(origin)
        module_file=getattr(module,"__file__",None)
        if isinstance(module_file,str):values.append(module_file)
        for value in values:
            path=pathlib.Path(value)
            if path.is_absolute() and not path.resolve(strict=False).is_relative_to(workspace):outside.append([name,str(path.resolve(strict=False))])
    for value in sorted(outside):events.append({"event":"outside_project_owned_origin","value":value})
    audit_path.write_text(json.dumps({"events":events},sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
'''

_ORIGIN_PROBE_SUFFIX = r'''
forbidden_prefixes=("PtychoNN","notebooks.archive.ePIE_recon_simulation","ptycho.FRC","ptycho.evaluation","scripts.orchestration")
forbidden=sorted(name for name in sys.modules if any(name==prefix or name.startswith(prefix+".") for prefix in forbidden_prefixes))
outside=[]
for name,module in tuple(sys.modules.items()):
    if not (name=="ptycho" or name.startswith("ptycho.") or name=="ptycho_torch" or name.startswith("ptycho_torch.")):continue
    values=[]
    origin=getattr(getattr(module,"__spec__",None),"origin",None)
    if isinstance(origin,str):values.append(origin)
    module_file=getattr(module,"__file__",None)
    if isinstance(module_file,str):values.append(module_file)
    for value in values:
        path=pathlib.Path(value)
        if path.is_absolute() and not path.resolve(strict=False).is_relative_to(workspace):outside.append([name,str(path.resolve(strict=False))])
pathlib.Path(os.environ["ES_F1_ORIGIN_REPORT"]).write_bytes((json.dumps({"loaded_forbidden_modules":forbidden,"outside_project_owned_origins":sorted(outside)},sort_keys=True,separators=(",",":"))+"\n").encode())
'''

_HOOK_CALL_PROGRAM = r'''import copy,importlib,inspect,json,os,pathlib
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
request_path=pathlib.Path(os.environ["ES_F1_HOOK_REQUEST"])
result_path=pathlib.Path(os.environ["ES_F1_HOOK_RESULT"])
symbol=os.environ["ES_F1_HOOK_SYMBOL"]
module_name,separator,name=symbol.rpartition(".")
if not separator:raise TypeError("hook symbol is not dotted")
hook=getattr(importlib.import_module(module_name),name)
if not callable(hook):raise TypeError("hook symbol is not callable")
source=inspect.getsourcefile(hook)
if not isinstance(source,str) or not pathlib.Path(source).resolve(strict=True).is_relative_to(workspace):
    raise TypeError("hook origin is outside the candidate workspace")
request=json.loads(request_path.read_bytes())
before=copy.deepcopy(request)
result=hook(request)
if request!=before:raise TypeError("hook mutated its request")
authority={"decision","disposition","evaluator_observations","hard_findings","passed","satisfied"}
def validate(value):
    if value is None or type(value) in (bool,int,float,str):return
    if type(value) is list:
        for item in value:validate(item)
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):raise TypeError("hook returned a non-string key")
        if authority.intersection(value):raise TypeError("hook returned an evaluator authority field")
        for item in value.values():validate(item)
        return
    raise TypeError("hook returned a non-JSON value")
if type(result) is not dict:raise TypeError("hook result is not one object")
validate(result)
result_path.write_bytes((json.dumps(result,allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode())
'''

_SURFACE_PROOF_PROGRAM = r'''import copy,importlib,inspect,json,os,pathlib,sys
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
descriptor=json.loads(pathlib.Path(os.environ["ES_F1_SURFACE_DESCRIPTOR"]).read_bytes())
cases=json.loads(pathlib.Path(os.environ["ES_F1_SURFACE_CASES"]).read_bytes())
target_path=pathlib.Path(os.environ["ES_F1_SURFACE_TRANSCRIPT"])
hook_symbol=os.environ["ES_F1_SURFACE_HOOK"]
def code(value):
    return getattr(value,"__code__",getattr(getattr(value,"__func__",None),"__code__",None))
ambient_codes={
    code(os.getenv):("os.getenv",False),
    code(os.environ.get):("os.environ.get",True),
    code(os.environ.__getitem__):("os.environ.__getitem__",True),
}
ambient_codes.pop(None,None)
active=None
runtime_events=[]
def profile(frame,event,arg):
    if active is None or event!="call" or frame.f_code not in ambient_codes:return
    symbol,requires_environ=ambient_codes[frame.f_code]
    if requires_environ and frame.f_locals.get("self") is not os.environ:return
    runtime_events.append({"class_id":"AMBIENT_CONFIGURATION_READ","consumer_id":active[0],"symbol":symbol})
sys.setprofile(profile)
def dotted(symbol):
    module_name,separator,name=symbol.rpartition(".")
    if not separator:raise TypeError("surface symbol is not dotted")
    module=importlib.import_module(module_name)
    value=getattr(module,name)
    source=inspect.getsourcefile(value)
    if not callable(value) or not isinstance(source,str) or not pathlib.Path(source).resolve(strict=True).is_relative_to(workspace):
        raise TypeError("surface target is not candidate product code")
    return module,name,value
_,_,hook=dotted(hook_symbol)
rows=[]
for surface,symbol in descriptor.items():
    module,name,target=dotted(symbol)
    for case in cases:
        request={"op":"RESOLVE","surface":surface,"file_mapping":copy.deepcopy(case["file_mapping"]),"cli_patch":copy.deepcopy(case["cli_patch"])}
        before=copy.deepcopy(request)
        active=(surface+":"+case["case_id"]+":direct",symbol)
        try:
            try:direct=target(copy.deepcopy(case["file_mapping"]),copy.deepcopy(case["cli_patch"]))
            finally:active=None
        except Exception as exc:
            direct_result={"exception_type":type(exc).__module__+"."+type(exc).__qualname__,"kind":"raised"}
        else:
            direct_result={"kind":"returned","value":direct}
        active=(surface+":"+case["case_id"]+":hook",hook_symbol)
        try:
            try:via_hook=hook(request)
            finally:active=None
        except Exception as exc:
            hook_result={"exception_type":type(exc).__module__+"."+type(exc).__qualname__,"kind":"raised"}
        else:
            hook_result={"kind":"returned","value":via_hook}
        if request!=before:raise TypeError("surface hook mutated its request")
        rows.append({"case_id":case["case_id"],"direct":direct_result,"hook":hook_result,"surface":surface})
    sentinel={"resolved":{"__es_f1_sentinel__":surface},"source_by_pointer":{"/__es_f1_sentinel__":"DERIVED"}}
    original=getattr(module,name)
    setattr(module,name,lambda file_mapping,cli_patch,value=sentinel:value)
    active=(surface+":sentinel:hook",hook_symbol)
    try:
        try:forwarded=hook({"op":"RESOLVE","surface":surface,"file_mapping":{},"cli_patch":{}})
        finally:active=None
    finally:
        setattr(module,name,original)
    rows.append({"sentinel_forwarded":forwarded==sentinel,"surface":surface})
sys.setprofile(None)
def validate(value):
    if value is None or type(value) in (bool,int,float,str):return
    if type(value) is list:
        for item in value:validate(item)
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):raise TypeError("surface result has a non-string key")
        for item in value.values():validate(item)
        return
    raise TypeError("surface result is not JSON-safe")
validate(rows)
validate(runtime_events)
target_path.write_bytes((json.dumps({"rows":rows,"runtime_bypass_events":runtime_events},allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode())
'''

_DERIVATION_PROOF_PROGRAM = r'''import dataclasses,importlib,inspect,json,os,pathlib,sys
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
descriptor=json.loads(pathlib.Path(os.environ["ES_F1_DERIVATION_DESCRIPTOR"]).read_bytes())
simulation=json.loads(pathlib.Path(os.environ["ES_F1_DERIVATION_INPUT"]).read_bytes())
target_path=pathlib.Path(os.environ["ES_F1_DERIVATION_TRANSCRIPT"])
def dotted(symbol):
    module_name,separator,name=symbol.rpartition(".")
    if not separator:raise TypeError("derivation symbol is not dotted")
    value=getattr(importlib.import_module(module_name),name)
    source=inspect.getsourcefile(value)
    if not isinstance(source,str) or not pathlib.Path(source).resolve(strict=True).is_relative_to(workspace):
        raise TypeError("derivation target is not candidate product code")
    return value
resolver=dotted(descriptor["resolver_symbol"])
owners=[(row,dotted(row["owner_symbol"]),dotted(row["deriver_symbol"])) for row in descriptor["owners"]]
called=set()
codes={deriver.__code__:row["deriver_symbol"] for row,_,deriver in owners if inspect.isfunction(deriver)}
def profile(frame,event,arg):
    if event=="call" and frame.f_code in codes:called.add(codes[frame.f_code])
sys.setprofile(profile)
try:value=resolver(simulation,{})
finally:sys.setprofile(None)
def contains(value,owner,seen=None):
    seen=set() if seen is None else seen
    if isinstance(value,owner):return True
    identity=id(value)
    if identity in seen:return False
    seen.add(identity)
    if dataclasses.is_dataclass(value) and not isinstance(value,type):
        return any(contains(getattr(value,field.name),owner,seen) for field in dataclasses.fields(value))
    if isinstance(value,dict):return any(contains(item,owner,seen) for item in value.values())
    if isinstance(value,(list,tuple)):return any(contains(item,owner,seen) for item in value)
    return False
rows=[]
for row,owner,deriver in owners:
    direct=list(deriver(owner))
    if dataclasses.is_dataclass(owner):
        synthetic=dataclasses.make_dataclass("EsF1Synthetic",[("__es_f1_sentinel__",int,dataclasses.field(default=1))],bases=(owner,))
    elif isinstance(getattr(owner,"__annotations__",None),dict):
        synthetic=type("EsF1Synthetic",(owner,),{"__annotations__":{"__es_f1_sentinel__":int}})
    else:raise TypeError("structural owner kind cannot be extended")
    extended=list(deriver(synthetic))
    rows.append({
        "called_by_resolver":row["deriver_symbol"] in called,
        "direct_fields":direct,
        "owner_present":contains(value,owner),
        "owner_symbol":row["owner_symbol"],
        "sentinel_derived":"__es_f1_sentinel__" in extended and all(field in extended for field in direct),
    })
target_path.write_bytes((json.dumps({"rows":rows},allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode())
'''

_TRANSACTION_PROOF_PROGRAM = r'''import ast,dataclasses,enum,importlib,inspect,json,math,os,pathlib,sys,types
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
descriptor=json.loads(pathlib.Path(os.environ["ES_F1_TRANSACTION_DESCRIPTOR"]).read_bytes())
inputs=json.loads(pathlib.Path(os.environ["ES_F1_TRANSACTION_INPUT"]).read_bytes())
target_path=pathlib.Path(os.environ["ES_F1_TRANSACTION_TRANSCRIPT"])
scenario=os.environ["ES_F1_TRANSACTION_SCENARIO"]
def dotted(symbol):
    module_name,separator,name=symbol.rpartition(".")
    if not separator:raise TypeError("transaction symbol is not dotted")
    module=importlib.import_module(module_name)
    value=getattr(module,name)
    source=inspect.getsourcefile(value) if callable(value) else inspect.getsourcefile(module)
    if not isinstance(source,str) or not pathlib.Path(source).resolve(strict=True).is_relative_to(workspace):
        raise TypeError("transaction target is not candidate product state")
    return module,name,value
apply_module,apply_name,apply=dotted(descriptor["apply_symbol"])
commit_module,commit_name,commit=dotted(descriptor["commit_symbol"])
states={symbol:dotted(symbol)[2] for symbol in descriptor["state_symbols"]}
def normalize(value,seen=None):
    seen=set() if seen is None else seen
    if isinstance(value,enum.Enum):return normalize(value.value,seen)
    if isinstance(value,pathlib.PurePath):return value.as_posix()
    if value is None or type(value) in (bool,int,str):return value
    if type(value) is float:
        if not math.isfinite(value):raise TypeError("non-finite state")
        return value
    identity=id(value)
    if identity in seen:raise TypeError("cyclic state")
    seen.add(identity)
    try:
        if isinstance(value,dict):return {str(key):normalize(item,seen) for key,item in sorted(value.items(),key=lambda row:str(row[0]))}
        if isinstance(value,(list,tuple)):return [normalize(item,seen) for item in value]
        if isinstance(value,set):return sorted((normalize(item,seen) for item in value),key=repr)
        if dataclasses.is_dataclass(value) and not isinstance(value,type):return {field.name:normalize(getattr(value,field.name),seen) for field in dataclasses.fields(value)}
        values=getattr(value,"__dict__",None)
        if isinstance(values,dict):return {name:normalize(item,seen) for name,item in sorted(values.items()) if not name.startswith("_") and not callable(item)}
        raise TypeError("opaque state")
    finally:seen.remove(identity)
def module_state():
    result={}
    for module_name,module in sorted(sys.modules.items()):
        source=getattr(module,"__file__",None)
        if not isinstance(source,str) or not pathlib.Path(source).resolve(strict=False).is_relative_to(workspace):continue
        for name,value in sorted(vars(module).items()):
            if name.startswith("__") or isinstance(value,types.ModuleType) or callable(value):continue
            try:result[module_name+"."+name]=normalize(value)
            except TypeError:continue
    return result
def mutation_roots(function,module_name):
    tree=ast.parse(inspect.getsource(function))
    roots=set()
    mutators={"append","clear","extend","insert","pop","remove","setdefault","update","add","discard"}
    def root(node):
        while isinstance(node,(ast.Attribute,ast.Subscript)):node=node.value
        return node.id if isinstance(node,ast.Name) else None
    for node in ast.walk(tree):
        targets=[]
        if isinstance(node,ast.Assign):targets=node.targets
        elif isinstance(node,(ast.AnnAssign,ast.AugAssign)):targets=[node.target]
        elif isinstance(node,ast.Delete):targets=node.targets
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in mutators:targets=[node.func.value]
        for target in targets:
            name=root(target)
            if name and name in function.__globals__ and not callable(function.__globals__[name]):roots.add(module_name+"."+name)
    return roots
derived=sorted(mutation_roots(apply,apply_module.__name__)|mutation_roots(commit,commit_module.__name__))
before=module_state()
counter={"value":0}
original=getattr(commit_module,commit_name)
def counted(value):
    counter["value"]+=1
    original(value)
    if scenario=="post_commit_failure":raise RuntimeError("injected post-commit failure")
setattr(commit_module,commit_name,counted)
try:
    try:
        result=apply(inputs["file_mapping"],inputs["cli_patch"])
    except Exception as exc:
        outcome={"exception_type":type(exc).__module__+"."+type(exc).__qualname__,"kind":"raised"}
    else:
        outcome={"kind":"returned","value":normalize(result)}
finally:setattr(commit_module,commit_name,original)
after=module_state()
changed=sorted(key for key in set(before)|set(after) if before.get(key)!=after.get(key))
record={"after":after,"before":before,"changed_symbols":changed,"commit_count":counter["value"],"derived_state_symbols":derived,"outcome":outcome,"scenario":scenario,"state_values":{symbol:normalize(dotted(symbol)[2]) for symbol in descriptor["state_symbols"]}}
target_path.write_bytes((json.dumps(record,allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode())
'''

_TRAINING_PROBE_FILE = {
    "model": {
        "N": 64,
        "generator_output_mode": "amp_phase",
        "rect_s1s2_init": "ones",
    },
    "n_groups": 5,
    "n_subsample": 3,
    "subsample_seed": 17,
    "enable_oversampling": True,
    "neighbor_pool_size": 5,
    "sequential_sampling": True,
}
_SIMULATION_PROBE_FILE = {
    "N": 64,
    "seed": 17,
    "probe": {"source": "ideal", "ideal_scale": 0.7},
    "object": {
        "kind": "lines",
        "image_size": [128, 128],
        "objects_per_probe": 1,
        "diffractions_per_object": 4,
        "set_phi": True,
        "patch_amplitude_normalization": "none",
    },
    "scan": {
        "kind": "grid",
        "grid_size": [2, 2],
        "offset": 4,
        "outer_offset_train": 8,
        "outer_offset_test": 20,
        "train_groups": 3,
        "test_groups": 2,
        "buffer": 0,
        "position_layout": "uniform_random",
    },
    "detector": {
        "photons_per_pattern": 1_000_000.0,
        "beamstop_diameter": 0.0,
    },
}


def _direct_resolver_cases() -> tuple[dict[str, Any], ...]:
    simulation_ill_typed = json.loads(json.dumps(_SIMULATION_PROBE_FILE))
    simulation_ill_typed["N"] = "64"
    simulation_unknown = json.loads(json.dumps(_SIMULATION_PROBE_FILE))
    simulation_unknown["probe"]["__es_f1_unknown_field__"] = 1
    simulation_invalid = json.loads(json.dumps(_SIMULATION_PROBE_FILE))
    simulation_invalid["scan"]["grid_size"] = [2]
    return (
        {"case_id": "strict-unknown", "role": "TRAINING", "file_mapping": _TRAINING_PROBE_FILE, "cli_patch": {"__es_f1_unknown_field__": 1}},
        {"case_id": "strict-illtyped", "role": "TRAINING", "file_mapping": _TRAINING_PROBE_FILE, "cli_patch": {"n_groups": True}},
        {"case_id": "strict-retention", "role": "TRAINING", "file_mapping": _TRAINING_PROBE_FILE, "cli_patch": {"model": {"N": 128}, "n_groups": 7}},
        {"case_id": "simulation-valid", "role": "SIMULATION", "file_mapping": _SIMULATION_PROBE_FILE, "cli_patch": {}},
        {"case_id": "simulation-illtyped", "role": "SIMULATION", "file_mapping": simulation_ill_typed, "cli_patch": {}},
        {"case_id": "simulation-unknown", "role": "SIMULATION", "file_mapping": simulation_unknown, "cli_patch": {}},
        {"case_id": "simulation-invalid-mapping", "role": "SIMULATION", "file_mapping": simulation_invalid, "cli_patch": {}},
    )


DIRECT_RESOLVER_CASES = _direct_resolver_cases()
DIRECT_RESOLVER_CASE_IDS = tuple(row["case_id"] for row in DIRECT_RESOLVER_CASES)

_DIRECT_RESOLVER_RUNNER = r'''import dataclasses,enum,importlib,json,math,os,pathlib,sys
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
calls=json.loads(pathlib.Path(os.environ["ES_F1_DIRECT_CALLS"]).read_bytes())
routes=json.loads(os.environ["ES_F1_DIRECT_ROUTES"])
target=pathlib.Path(os.environ["ES_F1_DIRECT_TRANSCRIPT"])
def dotted(symbol):
    module,sep,name=symbol.rpartition(".")
    if not sep:raise TypeError("resolver symbol is not dotted")
    value=getattr(importlib.import_module(module),name)
    if not callable(value):raise TypeError("resolver symbol is not callable")
    return value
resolved_routes={role:dotted(symbol) for role,symbol in routes.items()}
def normalize(value,path="$",catalog=None,stack=None):
    catalog=[] if catalog is None else catalog
    stack=set() if stack is None else stack
    if isinstance(value,enum.Enum):return normalize(value.value,path,catalog,stack)
    if isinstance(value,pathlib.PurePath):return value.as_posix()
    if value is None or type(value) in (bool,int,str):return value
    if type(value) is float:
        if not math.isfinite(value):raise TypeError("non-finite value")
        return value
    identity=id(value)
    if identity in stack:raise TypeError("cyclic value")
    stack.add(identity)
    try:
        if isinstance(value,dict) or hasattr(value,"items"):
            items=list(value.items())
            if any(type(key) is not str for key,_ in items):raise TypeError("non-string mapping key")
            if len({key for key,_ in items})!=len(items):raise TypeError("duplicate mapping key")
            fields=sorted(key for key,_ in items)
            catalog.append({"fields":fields,"kind":"mapping","path":path})
            return {key:normalize(item,path+"."+key,catalog,stack) for key,item in sorted(items)}
        if dataclasses.is_dataclass(value) and not isinstance(value,type):
            items=[(field.name,getattr(value,field.name)) for field in dataclasses.fields(value)]
            catalog.append({"fields":sorted(name for name,_ in items),"kind":"dataclass","path":path})
            return {name:normalize(item,path+"."+name,catalog,stack) for name,item in items}
        if isinstance(value,tuple) and hasattr(value,"_fields"):
            names=tuple(value._fields)
            if any(type(name) is not str for name in names):raise TypeError("invalid namedtuple fields")
            catalog.append({"fields":sorted(names),"kind":"namedtuple","path":path})
            return {name:normalize(getattr(value,name),path+"."+name,catalog,stack) for name in names}
        if callable(getattr(value,"model_dump",None)) and isinstance(getattr(type(value),"model_fields",None),dict):
            names=sorted(type(value).model_fields)
            catalog.append({"fields":names,"kind":"pydantic","path":path})
            dumped=value.model_dump(mode="python")
            if not isinstance(dumped,dict) or set(dumped)!=set(names):raise TypeError("pydantic field drift")
            return {name:normalize(dumped[name],path+"."+name,catalog,stack) for name in names}
        if isinstance(value,(list,tuple)):
            return [normalize(item,path+"["+str(index)+"]",catalog,stack) for index,item in enumerate(value)]
        values=getattr(value,"__dict__",None)
        if isinstance(values,dict):
            items=sorted((name,item) for name,item in values.items() if type(name) is str and not name.startswith("_") and not callable(item))
            if not items:raise TypeError("opaque value")
            catalog.append({"fields":[name for name,_ in items],"kind":"object","path":path})
            return {name:normalize(item,path+"."+name,catalog,stack) for name,item in items}
        raise TypeError("opaque value")
    finally:stack.remove(identity)
rows=[]
for call in calls:
    file_mapping=json.loads(json.dumps(call["file_mapping"]))
    cli_patch=json.loads(json.dumps(call["cli_patch"]))
    before={"file_mapping":normalize(file_mapping),"cli_patch":normalize(cli_patch)}
    try:
        value=resolved_routes[call["role"]](file_mapping,cli_patch)
    except Exception as exc:
        outcome={"exception_type":type(exc).__module__+"."+type(exc).__qualname__,"kind":"raised"}
    else:
        catalog=[]
        normalized=normalize(value,catalog=catalog)
        outcome={"field_catalog":sorted(catalog,key=lambda row:row["path"]),"kind":"returned","value":normalized}
    after={"file_mapping":normalize(file_mapping),"cli_patch":normalize(cli_patch)}
    rows.append({"case_id":call["case_id"],"input_after":after,"input_before":before,"outcome":outcome})
target.write_bytes((json.dumps({"pid":os.getpid(),"rows":rows},allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode())
'''


class EvaluatorError(RuntimeError):
    """A controller-owned evaluation invariant failed closed."""


def _fail(detail: str) -> NoReturn:
    raise EvaluatorError(detail)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return _SHA256_PREFIX + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return _SHA256_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda constant: (_fail(f"{label} contains {constant}")),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluatorError(f"{label} is unreadable canonical JSON") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not one canonical object")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail(f"duplicate JSON key {key}")
        value[key] = item
    return value


def load_controller_asset(path: Path, *, expected_schema_version: str) -> dict[str, Any]:
    payload = _canonical_object(Path(path), label=f"controller asset {path}")
    if payload.get("schema_version") != expected_schema_version:
        _fail(f"controller asset {path} has an unsupported schema version")
    return payload


def _validate_calibration_cases(cases: object) -> list[Mapping[str, Any]]:
    if not isinstance(cases, list) or any(
        not isinstance(row, Mapping) for row in cases
    ):
        _fail("calibration cases are malformed")
    rows = cast(list[Mapping[str, Any]], cases)
    expected_ids = (
        *CALIBRATION_POSITIVE_CASE_IDS,
        *tuple(CALIBRATION_DEFECT_CLAUSES),
    )
    if tuple(row.get("case_id") for row in rows) != expected_ids:
        _fail("calibration case order or identity drifted")
    for row in rows:
        case_id = cast(str, row["case_id"])
        if case_id in CALIBRATION_POSITIVE_CASE_IDS:
            probe = row.get("probe")
            if (
                set(row)
                != {"case_id", "defect_kind", "expected_failed_clauses", "probe"}
                or row.get("defect_kind") != "none"
                or row.get("expected_failed_clauses") != []
                or not isinstance(probe, Mapping)
                or set(probe) != {"cli_patch", "file_mapping", "role"}
                or probe.get("role") not in CONFIG_RESOLUTION_ROLES
                or not isinstance(probe.get("file_mapping"), Mapping)
                or not isinstance(probe.get("cli_patch"), Mapping)
            ):
                _fail("calibration positive case is malformed")
            continue
        if (
            set(row) != {"case_id", "defect_kind", "expected_failed_clauses"}
            or row.get("defect_kind") != case_id
            or tuple(cast(Sequence[str], row.get("expected_failed_clauses", ())))
            != CALIBRATION_DEFECT_CLAUSES[case_id]
        ):
            _fail("calibration negative case is malformed")
    return rows


def _validate_retained_root_dispositions(
    dispositions: object,
    frozen_rows: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if not isinstance(dispositions, list) or not dispositions:
        _fail("retained root dispositions must be a nonempty list")
    groups: dict[tuple[object, object], list[Mapping[str, Any]]] = {}
    rows_by_id: dict[object, Mapping[str, Any]] = {}
    for row in frozen_rows:
        groups.setdefault((row.get("path"), row.get("public_entry_route")), []).append(row)
        consumer_id = row.get("consumer_id")
        if consumer_id in rows_by_id:
            _fail("frozen configuration census slots are duplicated")
        rows_by_id[consumer_id] = row
    claimed: set[str] = set()
    validated: list[Mapping[str, Any]] = []
    for disposition in dispositions:
        if not isinstance(disposition, Mapping) or set(disposition) != {
            "consumer_ids", "disposition", "path", "public_entry_route"
        }:
            _fail("retained root disposition keys are malformed")
        if disposition.get("disposition") != "RETAINED_LEGACY_ROOT":
            _fail("retained root disposition is unsupported")
        relative = _safe_relative(
            disposition.get("path"), label="retained root disposition path"
        )
        route = disposition.get("public_entry_route")
        if not isinstance(route, str) or not route:
            _fail("retained root disposition route is malformed")
        consumer_ids = disposition.get("consumer_ids")
        if (
            not isinstance(consumer_ids, list)
            or not consumer_ids
            or any(not isinstance(consumer_id, str) or not consumer_id for consumer_id in consumer_ids)
        ):
            _fail("retained root disposition consumer IDs are malformed")
        if consumer_ids != sorted(consumer_ids):
            _fail("retained root disposition consumer IDs are not sorted")
        if len(consumer_ids) != len(set(consumer_ids)):
            _fail("retained root disposition consumer IDs are not unique")
        if claimed.intersection(consumer_ids):
            _fail("retained root disposition consumer IDs are duplicated")
        if any(consumer_id not in rows_by_id for consumer_id in consumer_ids):
            _fail("retained root disposition names an unknown consumer ID")
        group = groups.get((relative, route), ())
        if sorted(row.get("consumer_id") for row in group) != consumer_ids:
            _fail("retained root disposition does not cover one complete frozen group")
        if any(row.get("match_kind") != "CONFIGURATION_READ" for row in group):
            _fail("retained root disposition must cover configuration reads only")
        if any(
            row.get("responsibility_ids")
            != ["LEGACY_STATE_ISOLATION", "CONSUMER_MIGRATION"]
            for row in group
        ):
            _fail("retained root disposition responsibilities are malformed")
        claimed.update(consumer_ids)
        validated.append(disposition)
    return validated


def load_frozen_evaluator_package(
    *,
    calibration_cases_path: Path,
    consumer_census_path: Path,
    fixture_manifest_path: Path,
    reviewer_perspectives_path: Path,
    task_profile_path: Path,
    visible_check_path: Path,
    visible_contract_path: Path,
) -> dict[str, Any]:
    """Join the F1v2 evaluator to one schema-validated Task-1 package."""

    try:
        profile = load_task_profile(task_profile_path)
        contract = load_visible_task_contract(visible_contract_path)
        checks = load_visible_check_manifest(visible_check_path)
        census = load_configuration_consumer_census(consumer_census_path)
    except (OSError, TaskPackageError) as exc:
        raise EvaluatorError("Task-1 package validation failed") from exc
    try:
        fixtures = load_controller_asset(
            fixture_manifest_path,
            expected_schema_version="es-f1-fixture-manifest.v3",
        )
    except EvaluatorError as exc:
        raise EvaluatorError("evaluator package is not the F1v2 successor") from exc
    calibration = load_controller_asset(
        calibration_cases_path,
        expected_schema_version="es-f1-calibration-cases.v4",
    )
    perspectives = load_controller_asset(
        reviewer_perspectives_path,
        expected_schema_version="es-f1-reviewer-perspectives.v1",
    )
    if (
        profile.task_id != "F1"
        or profile.hard_clause_ids != HARD_CLAUSE_IDS
        or profile.focused_selectors != F1_PROVIDER_VISIBLE_SELECTORS
        or profile.focused_deselectors != F1_PROVIDER_VISIBLE_DESELECTORS
        or profile.required_task_seed_schema_version != "es_f1_task_seed.v3"
        or contract.get("schema_version") != "es_f1_visible_task_contract.v3"
        or contract.get("task_id") != "F1"
        or tuple(row["id"] for row in contract["hard_contract"]) != HARD_CLAUSE_IDS
        or tuple(row["id"] for row in contract["visible_outcomes"])
        != F1_REQUIRED_OUTCOMES
        or tuple(contract["bypass_classes"]) != BYPASS_CLASSES
        or checks.invocation_order != ("PRE_EDIT_FOCUSED", "CANDIDATE_CONFIG")
        or checks.pre_edit_selectors != F1_PROVIDER_VISIBLE_SELECTORS
        or checks.pre_edit_deselectors != F1_PROVIDER_VISIBLE_DESELECTORS
        or checks.candidate_selector != "tests/test_es_f1_config_ownership.py"
        or checks.candidate_deselectors
    ):
        _fail("Task-1 and evaluator package identities are mixed")
    census_binding = cast(dict[str, Any], profile.raw["consumer_census"])
    if (
        census_binding["path"]
        != consumer_census_path.resolve().relative_to(_REPOSITORY_ROOT).as_posix()
        or census_binding["record_sha256"] != census["record_sha256"]
        or census["consumer_count"] != len(census["rows"])
    ):
        _fail("evaluator consumer census binding drifted")
    expected_fixture_fields = {
        "bypass_classes", "calibration_cases", "configuration_roles",
        "fixture_adapter", "hard_clause_ids", "retained_root_dispositions",
        "schema_version", "versions",
    }
    calibration_binding = fixtures.get("calibration_cases")
    if (
        set(fixtures) != expected_fixture_fields
        or tuple(fixtures["hard_clause_ids"]) != HARD_CLAUSE_IDS
        or tuple(fixtures["configuration_roles"]) != CONFIG_RESOLUTION_ROLES
        or tuple(fixtures["bypass_classes"]) != BYPASS_CLASSES
        or not isinstance(calibration_binding, Mapping)
        or calibration_binding.get("schema_version")
        != "es-f1-calibration-cases.v4"
        or calibration_binding.get("sha256") != file_sha256(calibration_cases_path)
        or calibration_binding.get("path")
        != calibration_cases_path.resolve().relative_to(_REPOSITORY_ROOT).as_posix()
    ):
        _fail("evaluator fixture binding drifted")
    versions = fixtures["versions"]
    if versions != {
        "candidate_evidence": "candidate_config_evidence.v2",
        "hard_evaluation": "es-f1-hard-evaluation.v3",
        "hard_finding": "es-f1-hard-finding.v3",
        "probe_request": "config_resolution_probe_request.v1",
        "probe_result": "config_resolution_probe_result.v1",
        "visible_result": "es-f1-visible-check-result.v3",
    }:
        _fail("evaluator fixture versions are mixed")
    expected_perspectives = [
        {
            "owned_dimensions": row["owned_dimensions"],
            "perspective_id": row["id"],
            "responsibility": row["responsibility"],
        }
        for row in contract["reviewer_perspectives"]
    ]
    if perspectives.get("perspectives") != expected_perspectives:
        _fail("reviewer perspective binding drifted")
    _validate_calibration_cases(calibration.get("cases"))
    adapter_binding = fixtures.get("fixture_adapter")
    expected_adapter_path = _F1_FIXTURE_ADAPTER.relative_to(
        _REPOSITORY_ROOT
    ).as_posix()
    if (
        not isinstance(adapter_binding, Mapping)
        or set(adapter_binding) != {"path", "policy", "sha256"}
        or adapter_binding.get("path") != expected_adapter_path
        or adapter_binding.get("policy") != "path-only.v1"
        or adapter_binding.get("sha256") != file_sha256(_F1_FIXTURE_ADAPTER)
    ):
        _fail("evaluator fixture adapter binding drifted")
    retained_root_dispositions = _validate_retained_root_dispositions(
        fixtures.get("retained_root_dispositions"), census["rows"]
    )
    return {
        "calibration_cases": calibration,
        "consumer_census": census,
        "fixture_manifest": fixtures,
        "package_conformance": {
            "candidate_evidence": versions["candidate_evidence"],
            "probe_request": versions["probe_request"],
            "probe_result": versions["probe_result"],
            "validated": True,
        },
        "retained_root_dispositions": retained_root_dispositions,
        "reviewer_perspectives": perspectives,
        "task_profile": profile,
        "visible_checks": checks,
        "visible_contract": contract,
    }


def load_checked_in_evaluator_package() -> dict[str, Any]:
    """Load the one checked-in F1v2 evaluator package."""

    return load_frozen_evaluator_package(
        calibration_cases_path=_F1_CALIBRATION_CASES,
        consumer_census_path=_F1_EVIDENCE_ROOT / "configuration-consumer-census.json",
        fixture_manifest_path=_F1_ROOT / "evaluator/fixture-manifest.json",
        reviewer_perspectives_path=_F1_ROOT / "evaluator/reviewer-perspectives.json",
        task_profile_path=_F1_ROOT / "task-profile.json",
        visible_check_path=_F1_ROOT / "task/visible-check-manifest.json",
        visible_contract_path=_F1_ROOT / "task/visible-task-contract.json",
    )


def _safe_relative(value: object, *, label: str) -> str:
    if not isinstance(value, str) or "\\" in value:
        _fail(f"{label} is not a safe relative path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail(f"{label} is not a safe relative path")
    return value


def _safe_descendant(root: Path, relative: object, *, label: str) -> Path:
    value = _safe_relative(relative, label=label)
    candidate = root.joinpath(*PurePosixPath(value).parts)
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise EvaluatorError(f"{label} escapes its root") from exc
    return candidate


def directory_digest(root: Path) -> str:
    root = root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        _fail("digest root must be one real directory")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            rows.append({"kind": "symlink", "path": relative, "target": os.readlink(path)})
        elif stat.S_ISDIR(metadata.st_mode):
            rows.append({"kind": "directory", "path": relative})
        elif stat.S_ISREG(metadata.st_mode):
            rows.append({"kind": "file", "path": relative, "sha256": file_sha256(path)})
        else:
            _fail(f"workspace contains unsupported file type at {relative}")
    return _digest(rows)


def _subprocess_environment(rows: object) -> dict[str, str]:
    environment = {
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if rows is None:
        return environment
    if not isinstance(rows, list):
        _fail("required subprocess environment is malformed")
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"name", "value"}:
            _fail("required subprocess environment row is malformed")
        name, value = row["name"], row["value"]
        if not isinstance(name, str) or not isinstance(value, str):
            _fail("required subprocess environment row is malformed")
        environment[name] = value
    return environment


def _run_audited_subprocess(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    label: str,
) -> subprocess.CompletedProcess[str]:
    if timeout_seconds < 1:
        _fail(f"{label} timeout must be positive")
    try:
        return subprocess.run(
            list(argv),
            check=False,
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvaluatorError(f"{label} did not complete") from exc


def run_candidate_probe(
    *,
    code: str,
    environment: dict[str, str],
    label: str,
    python_executable: Path,
    timeout_seconds: int,
    workspace: Path,
    protected_roots: Sequence[Path] = (),
    require_success: bool = True,
    working_directory: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run candidate code under the one protected-root/import audit spine."""

    workspace = workspace.resolve(strict=True)
    cwd = workspace if working_directory is None else working_directory.resolve(strict=True)
    roots = (workspace, *(Path(root).resolve(strict=True) for root in protected_roots))
    before = {root: directory_digest(root) for root in roots}
    with tempfile.TemporaryDirectory(prefix="es-f1-audited-") as raw:
        root = Path(raw)
        program = root / "program.py"
        audit_path = root / "audit.json"
        program.write_text(code, encoding="utf-8", newline="\n")
        protected = json.dumps([str(root) for root in roots], separators=(",", ":"))
        process = _run_audited_subprocess(
            [
                str(python_executable), "-B", "-c", _AUDITED_PROJECTION_WRAPPER,
                protected, str(program), str(audit_path), str(workspace), str(cwd),
            ],
            cwd=root,
            environment={**_subprocess_environment(None), **environment},
            timeout_seconds=timeout_seconds,
            label=label,
        )
        audit = _canonical_object(audit_path, label=f"{label} audit") if audit_path.is_file() else {"events": []}
    for root, digest in before.items():
        if directory_digest(root) != digest:
            _fail(f"{label} mutated a protected execution root")
    events = audit.get("events")
    if not isinstance(events, list):
        _fail(f"{label} audit is malformed")
    for event in events:
        if not isinstance(event, Mapping):
            _fail(f"{label} audit row is malformed")
        if event.get("event") == "forbidden_import":
            _fail(f"{label} crossed a forbidden import boundary")
        if event.get("event") == "forbidden_module_loaded":
            _fail(f"{label} loaded a forbidden project module")
        if event.get("event") == "outside_project_owned_origin":
            _fail(f"{label} loaded a project module from an outside project origin")
        if event.get("event") == "workspace_write_attempt":
            _fail(f"{label} mutated or attempted to mutate a protected execution root")
        if event.get("event") == "unaudited_child_process":
            _fail(f"{label} crossed the protected execution boundary")
    if require_success and process.returncode != 0:
        _fail(f"{label} failed: {process.stderr}")
    return process


def _run_evaluation_hook_call(
    *,
    hook_id: str,
    request: dict[str, Any],
    root: Path,
    sequence: int,
    symbol: str,
    python_executable: Path,
    timeout_seconds: int,
    workspace: Path,
) -> dict[str, Any]:
    call_root = root / f"{sequence:02d}-{hook_id.lower()}-{request['op'].lower()}"
    call_root.mkdir()
    request_path = call_root / "request.json"
    result_path = call_root / "result.json"
    request_path.write_bytes(canonical_json_bytes(request))
    run_candidate_probe(
        code=_HOOK_CALL_PROGRAM,
        environment={
            "ES_F1_HOOK_REQUEST": str(request_path),
            "ES_F1_HOOK_RESULT": str(result_path),
            "ES_F1_HOOK_SYMBOL": symbol,
            "ES_F1_WORKSPACE": str(workspace),
        },
        label=f"{hook_id} {request['op']} hook",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
        working_directory=call_root,
    )
    return _canonical_object(result_path, label=f"{hook_id} {request['op']} result")


def run_evaluation_hooks(
    *,
    candidate_evidence_path: Path,
    output_root: Path,
    python_executable: Path,
    timeout_seconds: int,
    workspace: Path,
) -> dict[str, Any]:
    """Execute the exact four candidate hooks without trusting them for verdicts."""

    workspace = workspace.resolve(strict=True)
    try:
        candidate_evidence_path.resolve(strict=True).relative_to(workspace)
    except (OSError, ValueError) as exc:
        raise EvaluatorError("candidate evidence is outside the candidate workspace") from exc
    evidence = load_candidate_config_evidence(candidate_evidence_path)
    hooks = cast(list[dict[str, str]], evidence["evaluation_hooks"])
    by_id = {row["hook_id"]: row["symbol"] for row in hooks}
    expected = (
        "CONFIG_SURFACE",
        "CONFIG_CARRIER",
        "TORCH_TRANSACTION",
        "SIMULATION_DERIVATION",
    )
    if tuple(by_id) != expected or len(set(by_id.values())) != len(by_id):
        _fail("evaluation hook identity is missing, reordered, or ambiguous")
    if output_root.resolve(strict=False).is_relative_to(workspace):
        _fail("evaluation hook output must be outside the candidate workspace")
    output_root.mkdir(parents=True, exist_ok=False)
    sequence = 0

    def call(hook_id: str, request: dict[str, Any]) -> dict[str, Any]:
        nonlocal sequence
        sequence += 1
        return _run_evaluation_hook_call(
            hook_id=hook_id,
            request=request,
            root=output_root,
            sequence=sequence,
            symbol=by_id[hook_id],
            python_executable=python_executable,
            timeout_seconds=timeout_seconds,
            workspace=workspace,
        )

    surfaces = call("CONFIG_SURFACE", {"op": "DESCRIBE"})
    surface_names = ("SIMULATION", "CORE", "TORCH", "CLI", "WORKFLOW", "STUDY")
    if (
        set(surfaces) != {"surface_symbols"}
        or not isinstance(surfaces["surface_symbols"], dict)
        or set(surfaces["surface_symbols"]) != set(surface_names)
        or not all(
            isinstance(symbol, str) and symbol
            for symbol in surfaces["surface_symbols"].values()
        )
    ):
        _fail("CONFIG_SURFACE DESCRIBE field set is invalid")

    carrier = {
        "resolved": {"value": 1},
        "source_by_pointer": {"/value": "FILE_MAPPING"},
    }
    encoded = [
        call("CONFIG_CARRIER", {"carrier": carrier, "op": "ENCODE"})
        for _ in range(2)
    ]
    for row in encoded:
        if set(row) != {"payload_b64", "payload_sha256"} or not all(
            isinstance(row[name], str) for name in row
        ):
            _fail("CONFIG_CARRIER ENCODE field set is invalid")
        try:
            payload = base64.b64decode(row["payload_b64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise EvaluatorError("CONFIG_CARRIER payload is not canonical base64") from exc
        if _SHA256_PREFIX + hashlib.sha256(payload).hexdigest() != row["payload_sha256"]:
            _fail("CONFIG_CARRIER payload digest is invalid")
    if encoded[0] != encoded[1]:
        _fail("CONFIG_CARRIER encoding is nondeterministic")
    decoded = call(
        "CONFIG_CARRIER",
        {"op": "DECODE", "payload_b64": encoded[0]["payload_b64"]},
    )
    if set(decoded) != {"carrier"} or decoded["carrier"] != carrier:
        _fail("CONFIG_CARRIER did not reconstruct the exact carrier")

    transaction = call("TORCH_TRANSACTION", {"op": "DESCRIBE"})
    if (
        set(transaction) != {"apply_symbol", "commit_symbol", "state_symbols"}
        or not all(
            isinstance(transaction[name], str) and transaction[name]
            for name in ("apply_symbol", "commit_symbol")
        )
        or not isinstance(transaction["state_symbols"], list)
        or not transaction["state_symbols"]
        or not all(isinstance(symbol, str) and symbol for symbol in transaction["state_symbols"])
    ):
        _fail("TORCH_TRANSACTION DESCRIBE field set is invalid")

    derivation = call("SIMULATION_DERIVATION", {"op": "DESCRIBE"})
    owners = derivation.get("owners")
    if (
        set(derivation) != {"owners", "resolver_symbol"}
        or not isinstance(derivation["resolver_symbol"], str)
        or not isinstance(owners, list)
        or not owners
        or any(
            not isinstance(owner, dict)
            or set(owner) != {"deriver_symbol", "owner_symbol"}
            or not all(isinstance(owner[name], str) and owner[name] for name in owner)
            for owner in owners
        )
    ):
        _fail("SIMULATION_DERIVATION DESCRIBE field set is invalid")
    catalog = call(
        "SIMULATION_DERIVATION",
        {"op": "CATALOG", "owner_symbol": owners[0]["owner_symbol"]},
    )
    fields = catalog.get("fields")
    if (
        set(catalog) != {"fields"}
        or not isinstance(fields, list)
        or fields != sorted(set(fields))
        or not all(isinstance(field, str) and field for field in fields)
    ):
        _fail("SIMULATION_DERIVATION CATALOG field set is invalid")

    return {
        "facts": {
            "F1-H04-TRANSACTIONAL-APPLICATION": False,
            "F1-H06-DERIVED-PUBLIC-FIELDS": False,
            "F1-H08-PROVENANCE-ROUNDTRIP": False,
            "F1-H09-CROSS-SURFACE-COHERENCE": False,
        },
        "transcript": [
            {"hook_id": "CONFIG_SURFACE", "operations": ["DESCRIBE"]},
            {"hook_id": "CONFIG_CARRIER", "operations": ["ENCODE", "ENCODE", "DECODE"]},
            {"hook_id": "TORCH_TRANSACTION", "operations": ["DESCRIBE"]},
            {"hook_id": "SIMULATION_DERIVATION", "operations": ["DESCRIBE", "CATALOG"]},
        ],
    }


def _merge_mappings(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        current = merged.get(key)
        merged[key] = (
            _merge_mappings(cast(Mapping[str, Any], current), cast(Mapping[str, Any], value))
            if isinstance(current, Mapping) and isinstance(value, Mapping)
            else value
        )
    return merged


def _source_pointers(
    value: Mapping[str, Any],
    file_mapping: Mapping[str, Any],
    patch: Mapping[str, Any],
    prefix: str = "",
) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, item in value.items():
        pointer = f"{prefix}/{key}"
        file_item = file_mapping.get(key)
        patch_item = patch.get(key)
        if isinstance(item, Mapping):
            result.update(
                _source_pointers(
                    cast(Mapping[str, Any], item),
                    cast(Mapping[str, Any], file_item)
                    if isinstance(file_item, Mapping)
                    else {},
                    cast(Mapping[str, Any], patch_item)
                    if isinstance(patch_item, Mapping)
                    else {},
                    pointer,
                )
            )
        else:
            result[pointer] = (
                "CLI_PATCH"
                if key in patch
                else "FILE_MAPPING"
                if key in file_mapping
                else "DEFAULT"
            )
    return result


def _lookup_pointer(value: Mapping[str, Any], pointer: str) -> Any:
    current: Any = value
    for part in pointer.split("/")[1:]:
        if not isinstance(current, Mapping) or part not in current:
            return object()
        current = current[part]
    return current


def run_surface_and_carrier_proof(
    *,
    candidate_evidence_path: Path,
    output_root: Path,
    python_executable: Path,
    timeout_seconds: int,
    workspace: Path,
) -> dict[str, Any]:
    """Prove product-target surface coherence and carrier provenance by execution."""

    workspace = workspace.resolve(strict=True)
    evidence = load_candidate_config_evidence(candidate_evidence_path)
    hooks = {
        row["hook_id"]: row["symbol"]
        for row in cast(list[dict[str, str]], evidence["evaluation_hooks"])
    }
    output_root.mkdir(parents=True, exist_ok=False)
    descriptor = _run_evaluation_hook_call(
        hook_id="CONFIG_SURFACE",
        request={"op": "DESCRIBE"},
        root=output_root,
        sequence=1,
        symbol=hooks["CONFIG_SURFACE"],
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    surface_symbols = descriptor.get("surface_symbols")
    surfaces = ("SIMULATION", "CORE", "TORCH", "CLI", "WORKFLOW", "STUDY")
    if (
        set(descriptor) != {"surface_symbols"}
        or not isinstance(surface_symbols, dict)
        or set(surface_symbols) != set(surfaces)
        or len(set(surface_symbols.values())) != len(surfaces)
        or not all(isinstance(symbol, str) and symbol for symbol in surface_symbols.values())
    ):
        _fail("CONFIG_SURFACE descriptor does not bind six distinct product targets")

    file_source = json.loads(json.dumps(_TRAINING_PROBE_FILE))
    cli_source = json.loads(json.dumps(_TRAINING_PROBE_FILE))
    cli_source["model"]["N"] = 32
    invalid_mode = json.loads(json.dumps(_TRAINING_PROBE_FILE))
    invalid_mode["model"]["generator_output_mode"] = 1
    invalid_initialization = json.loads(json.dumps(_TRAINING_PROBE_FILE))
    invalid_initialization["model"]["rect_s1s2_init"] = True
    cases = [
        {"case_id": "file-source", "file_mapping": file_source, "cli_patch": {}},
        {
            "case_id": "cli-source",
            "file_mapping": cli_source,
            "cli_patch": {"model": {"N": 64}},
        },
        {"case_id": "invalid-mode", "file_mapping": invalid_mode, "cli_patch": {}},
        {
            "case_id": "invalid-initialization",
            "file_mapping": invalid_initialization,
            "cli_patch": {},
        },
    ]
    descriptor_path = output_root / "surface-descriptor.json"
    cases_path = output_root / "surface-cases.json"
    transcript_path = output_root / "surface-transcript.json"
    descriptor_path.write_bytes(canonical_json_bytes(surface_symbols))
    cases_path.write_bytes(canonical_json_bytes(cases))
    run_candidate_probe(
        code=_SURFACE_PROOF_PROGRAM,
        environment={
            "ES_F1_SURFACE_CASES": str(cases_path),
            "ES_F1_SURFACE_DESCRIPTOR": str(descriptor_path),
            "ES_F1_SURFACE_HOOK": hooks["CONFIG_SURFACE"],
            "ES_F1_SURFACE_TRANSCRIPT": str(transcript_path),
            "ES_F1_WORKSPACE": str(workspace),
        },
        label="configuration surface proof",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
        working_directory=output_root,
    )
    transcript = _canonical_object(transcript_path, label="configuration surface transcript")
    if set(transcript) != {"rows", "runtime_bypass_events"}:
        _fail("configuration surface transcript fields are malformed")
    rows = transcript.get("rows")
    if not isinstance(rows, list) or len(rows) != len(surfaces) * (len(cases) + 1):
        _fail("configuration surface transcript is incomplete")
    runtime_events = transcript.get("runtime_bypass_events")
    if not isinstance(runtime_events, list):
        _fail("configuration surface runtime bypass events are malformed")
    runtime_bypass_classes = list(normalize_bypass_events(runtime_events))
    by_case: dict[str, list[dict[str, Any]]] = {
        case["case_id"]: [] for case in cases
    }
    sentinel_ok = True
    for row in rows:
        if not isinstance(row, dict) or row.get("surface") not in surfaces:
            _fail("configuration surface transcript row is malformed")
        if "sentinel_forwarded" in row:
            if set(row) != {"sentinel_forwarded", "surface"}:
                _fail("configuration surface sentinel row is malformed")
            sentinel_ok = sentinel_ok and row["sentinel_forwarded"] is True
            continue
        if set(row) != {"case_id", "direct", "hook", "surface"}:
            _fail("configuration surface result row is malformed")
        by_case[cast(str, row["case_id"])].append(row)

    valid_carriers: dict[str, dict[str, Any]] = {}
    coherence_ok = sentinel_ok
    for case in cases:
        case_id = cast(str, case["case_id"])
        case_rows = by_case.get(case_id, [])
        if len(case_rows) != len(surfaces):
            _fail("configuration surface case coverage is incomplete")
        if case_id.startswith("invalid-"):
            coherence_ok = coherence_ok and all(
                row["direct"].get("kind") == "raised"
                and row["hook"].get("kind") == "raised"
                for row in case_rows
            )
            continue
        outputs = []
        for row in case_rows:
            direct, via_hook = row["direct"], row["hook"]
            if (
                direct.get("kind") != "returned"
                or via_hook.get("kind") != "returned"
                or direct.get("value") != via_hook.get("value")
            ):
                coherence_ok = False
                continue
            outputs.append(direct["value"])
        coherence_ok = coherence_ok and len(outputs) == len(surfaces) and all(
            output == outputs[0] for output in outputs
        )
        if outputs:
            valid_carriers[case_id] = outputs[0]

    provenance_ok = set(valid_carriers) == {"file-source", "cli-source"}
    for case in cases[:2]:
        case_id = cast(str, case["case_id"])
        expected_resolved = _merge_mappings(
            cast(Mapping[str, Any], case["file_mapping"]),
            cast(Mapping[str, Any], case["cli_patch"]),
        )
        expected_carrier = {
            "resolved": valid_carriers.get(case_id, {}).get("resolved"),
            "source_by_pointer": _source_pointers(
                cast(Mapping[str, Any], valid_carriers.get(case_id, {}).get("resolved", {})),
                cast(Mapping[str, Any], case["file_mapping"]),
                cast(Mapping[str, Any], case["cli_patch"]),
            ),
        }
        carrier_value = valid_carriers.get(case_id)
        provenance_ok = provenance_ok and carrier_value == expected_carrier
        if carrier_value is not None:
            resolved = cast(Mapping[str, Any], carrier_value["resolved"])
            provenance_ok = provenance_ok and all(
                _lookup_pointer(resolved, pointer) == _lookup_pointer(expected_resolved, pointer)
                for pointer in _source_pointers(
                    expected_resolved,
                    cast(Mapping[str, Any], case["file_mapping"]),
                    cast(Mapping[str, Any], case["cli_patch"]),
                )
            )
    provenance_ok = provenance_ok and (
        valid_carriers.get("file-source", {}).get("resolved")
        == valid_carriers.get("cli-source", {}).get("resolved")
        and valid_carriers.get("file-source", {}).get("source_by_pointer")
        != valid_carriers.get("cli-source", {}).get("source_by_pointer")
    )
    resolution_ok = provenance_ok and sentinel_ok

    carrier = valid_carriers.get("cli-source")
    codec_rows: list[dict[str, Any]] = []
    if carrier is not None:
        for sequence in (2, 3):
            codec_rows.append(
                _run_evaluation_hook_call(
                    hook_id="CONFIG_CARRIER",
                    request={"carrier": carrier, "op": "ENCODE"},
                    root=output_root,
                    sequence=sequence,
                    symbol=hooks["CONFIG_CARRIER"],
                    python_executable=python_executable,
                    timeout_seconds=timeout_seconds,
                    workspace=workspace,
                )
            )
        if codec_rows[0] != codec_rows[1] or set(codec_rows[0]) != {
            "payload_b64",
            "payload_sha256",
        }:
            provenance_ok = False
        else:
            try:
                payload = base64.b64decode(codec_rows[0]["payload_b64"], validate=True)
            except (TypeError, ValueError):
                provenance_ok = False
            else:
                provenance_ok = provenance_ok and (
                    codec_rows[0]["payload_sha256"]
                    == _SHA256_PREFIX + hashlib.sha256(payload).hexdigest()
                )
                decoded = _run_evaluation_hook_call(
                    hook_id="CONFIG_CARRIER",
                    request={"op": "DECODE", "payload_b64": codec_rows[0]["payload_b64"]},
                    root=output_root,
                    sequence=4,
                    symbol=hooks["CONFIG_CARRIER"],
                    python_executable=python_executable,
                    timeout_seconds=timeout_seconds,
                    workspace=workspace,
                )
                provenance_ok = provenance_ok and decoded == {"carrier": carrier}

    return {
        "facts": {
            "F1-H03-PUBLIC-RESOLUTION": resolution_ok,
            "F1-H08-PROVENANCE-ROUNDTRIP": provenance_ok and sentinel_ok,
            "F1-H09-CROSS-SURFACE-COHERENCE": coherence_ok,
        },
        "surface_transcript": transcript,
        "surface_transcript_sha256": file_sha256(transcript_path),
        "runtime_bypass_classes": runtime_bypass_classes,
    }


def run_simulation_derivation_proof(
    *,
    candidate_evidence_path: Path,
    output_root: Path,
    python_executable: Path,
    timeout_seconds: int,
    workspace: Path,
) -> dict[str, Any]:
    """Prove simulation fields come from the returned structural owner."""

    workspace = workspace.resolve(strict=True)
    evidence = load_candidate_config_evidence(candidate_evidence_path)
    hooks = {
        row["hook_id"]: row["symbol"]
        for row in cast(list[dict[str, str]], evidence["evaluation_hooks"])
    }
    output_root.mkdir(parents=True, exist_ok=False)
    descriptor = _run_evaluation_hook_call(
        hook_id="SIMULATION_DERIVATION",
        request={"op": "DESCRIBE"},
        root=output_root,
        sequence=1,
        symbol=hooks["SIMULATION_DERIVATION"],
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    owners = descriptor.get("owners")
    simulation_routes = {
        row["symbol"]
        for row in cast(list[dict[str, Any]], evidence["public_resolution_routes"])
        if "SIMULATION" in row["roles"]
    }
    if (
        set(descriptor) != {"owners", "resolver_symbol"}
        or descriptor.get("resolver_symbol") not in simulation_routes
        or not isinstance(owners, list)
        or not owners
        or any(
            not isinstance(row, dict)
            or set(row) != {"deriver_symbol", "owner_symbol"}
            or not all(isinstance(row[name], str) and row[name] for name in row)
            for row in owners
        )
        or len({row["owner_symbol"] for row in owners}) != len(owners)
        or len({row["deriver_symbol"] for row in owners}) != len(owners)
    ):
        _fail("SIMULATION_DERIVATION descriptor is invalid or detached from the public route")
    descriptor_path = output_root / "descriptor.json"
    input_path = output_root / "simulation-input.json"
    transcript_path = output_root / "transcript.json"
    descriptor_path.write_bytes(canonical_json_bytes(descriptor))
    input_path.write_bytes(canonical_json_bytes(_SIMULATION_PROBE_FILE))
    run_candidate_probe(
        code=_DERIVATION_PROOF_PROGRAM,
        environment={
            "ES_F1_DERIVATION_DESCRIPTOR": str(descriptor_path),
            "ES_F1_DERIVATION_INPUT": str(input_path),
            "ES_F1_DERIVATION_TRANSCRIPT": str(transcript_path),
            "ES_F1_WORKSPACE": str(workspace),
        },
        label="simulation field derivation proof",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
        working_directory=output_root,
    )
    transcript = _canonical_object(transcript_path, label="simulation derivation transcript")
    rows = transcript.get("rows")
    if not isinstance(rows, list) or len(rows) != len(owners):
        _fail("simulation derivation transcript is incomplete")
    satisfied = True
    for sequence, (owner, row) in enumerate(zip(owners, rows, strict=True), start=2):
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "called_by_resolver",
                "direct_fields",
                "owner_present",
                "owner_symbol",
                "sentinel_derived",
            }
            or row["owner_symbol"] != owner["owner_symbol"]
            or not isinstance(row["direct_fields"], list)
            or row["direct_fields"] != sorted(set(row["direct_fields"]))
            or not all(isinstance(field, str) and field for field in row["direct_fields"])
        ):
            _fail("simulation derivation transcript row is malformed")
        catalog = _run_evaluation_hook_call(
            hook_id="SIMULATION_DERIVATION",
            request={"op": "CATALOG", "owner_symbol": owner["owner_symbol"]},
            root=output_root,
            sequence=sequence,
            symbol=hooks["SIMULATION_DERIVATION"],
            python_executable=python_executable,
            timeout_seconds=timeout_seconds,
            workspace=workspace,
        )
        satisfied = satisfied and (
            catalog == {"fields": row["direct_fields"]}
            and row["called_by_resolver"] is True
            and row["owner_present"] is True
            and row["sentinel_derived"] is True
        )
    return {
        "facts": {"F1-H06-DERIVED-PUBLIC-FIELDS": satisfied},
        "transcript": transcript,
        "transcript_sha256": file_sha256(transcript_path),
    }


def run_torch_transaction_proof(
    *,
    candidate_evidence_path: Path,
    output_root: Path,
    python_executable: Path,
    timeout_seconds: int,
    workspace: Path,
) -> dict[str, Any]:
    """Prove one complete torch commit and rollback for both failure paths."""

    workspace = workspace.resolve(strict=True)
    evidence = load_candidate_config_evidence(candidate_evidence_path)
    hooks = {
        row["hook_id"]: row["symbol"]
        for row in cast(list[dict[str, str]], evidence["evaluation_hooks"])
    }
    output_root.mkdir(parents=True, exist_ok=False)
    descriptor = _run_evaluation_hook_call(
        hook_id="TORCH_TRANSACTION",
        request={"op": "DESCRIBE"},
        root=output_root,
        sequence=1,
        symbol=hooks["TORCH_TRANSACTION"],
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    states = descriptor.get("state_symbols")
    if (
        set(descriptor) != {"apply_symbol", "commit_symbol", "state_symbols"}
        or not all(
            isinstance(descriptor.get(name), str) and descriptor[name]
            for name in ("apply_symbol", "commit_symbol")
        )
        or descriptor["apply_symbol"] == descriptor["commit_symbol"]
        or not isinstance(states, list)
        or not states
        or states != sorted(set(states))
        or not all(isinstance(symbol, str) and symbol for symbol in states)
    ):
        _fail("TORCH_TRANSACTION descriptor is malformed or incomplete")
    valid_input = {
        "file_mapping": _TRAINING_PROBE_FILE,
        "cli_patch": {"batch_size": 2, "model": {"N": 128}, "n_groups": 7},
    }
    invalid_input = {
        "file_mapping": _TRAINING_PROBE_FILE,
        "cli_patch": {"batch_size": 0, "model": {"N": 128}, "n_groups": 7},
    }
    descriptor_path = output_root / "descriptor.json"
    descriptor_path.write_bytes(canonical_json_bytes(descriptor))
    scenarios = (
        ("valid", valid_input),
        ("invalid", invalid_input),
        ("post_commit_failure", valid_input),
    )
    transcripts: list[dict[str, Any]] = []
    for sequence, (scenario, inputs) in enumerate(scenarios, start=2):
        scenario_root = output_root / scenario
        scenario_root.mkdir()
        input_path = scenario_root / "input.json"
        transcript_path = scenario_root / "transcript.json"
        input_path.write_bytes(canonical_json_bytes(inputs))
        run_candidate_probe(
            code=_TRANSACTION_PROOF_PROGRAM,
            environment={
                "ES_F1_TRANSACTION_DESCRIPTOR": str(descriptor_path),
                "ES_F1_TRANSACTION_INPUT": str(input_path),
                "ES_F1_TRANSACTION_SCENARIO": scenario,
                "ES_F1_TRANSACTION_TRANSCRIPT": str(transcript_path),
                "ES_F1_WORKSPACE": str(workspace),
            },
            label=f"torch transaction {scenario} proof",
            python_executable=python_executable,
            timeout_seconds=timeout_seconds,
            workspace=workspace,
            working_directory=scenario_root,
        )
        record = _canonical_object(
            transcript_path, label=f"torch transaction {scenario} transcript"
        )
        if set(record) != {
            "after",
            "before",
            "changed_symbols",
            "commit_count",
            "derived_state_symbols",
            "outcome",
            "scenario",
            "state_values",
        } or record["scenario"] != scenario:
            _fail("torch transaction transcript is malformed")
        transcripts.append(record)
    valid, invalid, post_commit = transcripts
    declared_states = cast(list[str], states)
    complete = all(
        row["derived_state_symbols"] == declared_states for row in transcripts
    )
    valid_state_bytes = canonical_json_bytes(valid["state_values"])
    satisfied = (
        complete
        and valid["commit_count"] == 1
        and valid["outcome"].get("kind") == "returned"
        and valid["changed_symbols"] == declared_states
        and all(token in valid_state_bytes for token in (b"128", b"7", b"2"))
        and invalid["commit_count"] == 0
        and invalid["outcome"].get("kind") == "raised"
        and invalid["before"] == invalid["after"]
        and invalid["changed_symbols"] == []
        and post_commit["commit_count"] == 1
        and post_commit["outcome"].get("kind") == "raised"
        and post_commit["before"] == post_commit["after"]
        and post_commit["changed_symbols"] == []
    )
    return {
        "facts": {"F1-H04-TRANSACTIONAL-APPLICATION": satisfied},
        "transcripts": transcripts,
        "transcripts_sha256": _digest(transcripts),
    }


def validate_project_module_origins(projection: Mapping[str, Any]) -> None:
    if projection.get("loaded_forbidden_modules"):
        _fail("candidate loaded a forbidden project module")
    if projection.get("outside_project_owned_origins"):
        _fail("candidate loaded a project module from an outside project origin")


def run_visible_checks(
    *, workspace: Path, visible_checks: Mapping[str, Any]
) -> dict[str, Any]:
    """Run declared selectors on disposable extracts via the audited route."""

    if not isinstance(visible_checks, Mapping):
        _fail("visible checks must be one object")
    checks = dict(visible_checks)
    if set(checks) != {
        "invocation_order", "invocations", "runner", "schema_version", "task_id"
    }:
        _fail("visible check field set is not exact")
    if checks["schema_version"] != "es_f1_visible_checks.v3" or checks["task_id"] != "F1":
        _fail("visible check package is not the F1v2 successor")
    order = checks["invocation_order"]
    rows = checks["invocations"]
    runner = checks["runner"]
    if not isinstance(order, list) or not isinstance(rows, list) or not isinstance(runner, Mapping):
        _fail("visible check contract is malformed")
    by_id = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "candidate_owned", "deselectors", "id", "required", "selectors"
        }:
            _fail("visible invocation row is malformed")
        if row["required"] is not True or type(row["candidate_owned"]) is not bool:
            _fail("visible invocation authority is malformed")
        by_id[row["id"]] = row
    if list(by_id) != order or len(by_id) != len(rows):
        _fail("visible invocation order is not exact")
    python = Path(cast(str, runner.get("python_executable", "")))
    prefix = runner.get("argv_prefix")
    timeout = runner.get("timeout_seconds")
    if not python.is_absolute() or not python.is_file():
        _fail("visible Python executable is invalid")
    if not isinstance(prefix, list) or not all(isinstance(arg, str) for arg in prefix):
        _fail("visible argv prefix is malformed")
    if prefix[:2] != ["-m", "pytest"]:
        _fail("visible argv prefix is unsupported")
    if not isinstance(timeout, int):
        _fail("visible timeout is malformed")
    exact_runner_fields = {
        "argv_prefix", "execution_copy_policy", "install_policy", "mutation_policy",
        "python_executable", "python_executable_sha256", "python_version",
        "required_environment", "result_policy", "timeout_seconds",
        "working_directory_policy",
    }
    if set(runner) != exact_runner_fields:
        _fail("visible runner field set is not exact")
    if (
        runner["execution_copy_policy"] != "disposable-exact-extract.v1"
        or runner["install_policy"] != "no-install-build-or-editable.v1"
        or runner["mutation_policy"] != "verify-product-digest-before-after.v1"
        or runner["result_policy"] != "every-required-invocation-exit-zero.v1"
        or runner["working_directory_policy"]
        != "external-disposable-invocation-root.v1"
        or file_sha256(python) != runner["python_executable_sha256"]
    ):
        _fail("visible runner identity or policy drifted")
    workspace = workspace.resolve(strict=True)
    source_before = directory_digest(workspace)
    results: list[dict[str, Any]] = []
    for invocation_id in order:
        row = by_id[invocation_id]
        selectors = row["selectors"]
        deselectors = row["deselectors"]
        if not isinstance(selectors, list) or not selectors:
            _fail("visible selectors are malformed")
        if not isinstance(deselectors, list) or not all(
            isinstance(node, str) and "::" in node for node in deselectors
        ):
            _fail("visible deselectors are malformed")
        for selector in selectors:
            _safe_descendant(workspace, selector, label="visible selector")
        for node in deselectors:
            path, _, _ = node.partition("::")
            _safe_descendant(workspace, path, label="visible deselector")
        with tempfile.TemporaryDirectory(prefix="es-f1-visible-") as raw:
            copy = Path(raw) / "candidate"
            shutil.copytree(workspace, copy, symlinks=True)
            copy_before = directory_digest(copy)
            if copy_before != source_before:
                _fail("visible disposable copy does not match the candidate")
            deselect_argv = [f"--deselect={node}" for node in deselectors]
            argv = [str(python), *prefix, *selectors, *deselect_argv]
            pytest_argv = ["pytest", *prefix[2:], *selectors, *deselect_argv]
            program = (
                "import runpy,sys\n"
                f"sys.argv={pytest_argv!r}\n"
                "runpy.run_module('pytest',run_name='__main__')\n"
            )
            process = run_candidate_probe(
                code=program,
                environment=_subprocess_environment(
                    runner.get("required_environment")
                ),
                label=f"visible invocation {invocation_id}",
                python_executable=python,
                require_success=False,
                timeout_seconds=timeout,
                workspace=copy,
                working_directory=copy,
            )
            if directory_digest(copy) != copy_before:
                _fail(f"visible invocation {invocation_id} mutated its candidate copy")
            if directory_digest(workspace) != source_before:
                _fail(f"visible invocation {invocation_id} mutated the source candidate")
        results.append(
            {
                "argv": argv,
                "exit_code": process.returncode,
                "invocation_id": invocation_id,
                "deselectors": list(deselectors),
                "selectors": list(selectors),
                "stderr_sha256": _SHA256_PREFIX + hashlib.sha256(process.stderr.encode()).hexdigest(),
                "stdout_sha256": _SHA256_PREFIX + hashlib.sha256(process.stdout.encode()).hexdigest(),
            }
        )
    source_after = directory_digest(workspace)
    if source_after != source_before:
        _fail("visible checks mutated the candidate")
    return {
        "copy_digest_after": source_after,
        "copy_digest_before": source_before,
        "invocations": results,
        "schema_version": "es-f1-visible-check-result.v3",
    }


def run_config_resolution_adapter(
    *,
    adapter_relative_path: str,
    expected_candidate_id: str,
    expected_case_ids: tuple[str, ...],
    output_root: Path,
    python_executable: Path,
    request_path: Path,
    timeout_seconds: int,
    workspace: Path,
) -> dict[str, Any]:
    """Run one path-only adapter and independently validate every returned path."""

    workspace = workspace.resolve(strict=True)
    adapter = _safe_descendant(workspace, adapter_relative_path, label="adapter path")
    request = load_config_resolution_probe_request(
        request_path,
        expected_candidate_id=expected_candidate_id,
        expected_case_ids=expected_case_ids,
    )
    if request["operation_version"] != "ptychopinn_public_config_resolution.v1":
        _fail("probe request operation version is unsupported")
    output_root.mkdir(parents=True, exist_ok=False)
    result_path = output_root / "result.json"
    runner = (
        "import os,runpy,sys\n"
        "sys.argv=[os.environ['ES_F1_ADAPTER'],'--request',"
        "os.environ['ES_F1_REQUEST'],'--result',os.environ['ES_F1_RESULT']]\n"
        "runpy.run_path(os.environ['ES_F1_ADAPTER'],run_name='__main__')\n"
    )
    run_candidate_probe(
        code=runner,
        environment={
            "ES_F1_ADAPTER": str(adapter),
            "ES_F1_REQUEST": str(request_path.resolve(strict=True)),
            "ES_F1_RESULT": str(result_path),
        },
        label="configuration-resolution adapter",
        protected_roots=(request_path.parent,),
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
        working_directory=output_root,
    )
    try:
        result = load_config_resolution_probe_result(
            result_path,
            expected_candidate_id=expected_candidate_id,
            expected_case_ids=expected_case_ids,
        )
    except (TaskPackageError, OSError) as exc:
        raise EvaluatorError("configuration-resolution probe result is invalid") from exc
    if result["operation_version"] != request["operation_version"]:
        _fail("configuration-resolution probe result operation version drifted")
    paths: list[Path] = []
    for row in cast(list[dict[str, str]], result["probe_results"]):
        path = _safe_descendant(output_root, row["resolved_record_path"], label="probe result path")
        if not path.is_file() or path.is_symlink():
            _fail("configuration-resolution probe artifact is missing or unsafe")
        paths.append(path)
    observations = [_load_resolution_artifact(path) for path in paths]
    return {"artifact_paths": paths, "observations": observations, "result": result}


def _load_resolution_artifact(path: Path) -> dict[str, Any]:
    """Interpret candidate bytes as raw facts; derive provenance controller-side."""

    payload = _canonical_object(path, label="configuration-resolution artifact")
    return _load_resolution_artifact_value(payload)


def _load_resolution_artifact_value(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only the raw candidate outcome; source facts remain controller-owned."""

    if set(payload) != {"resolved"}:
        _fail("configuration-resolution artifact field set is not exact")
    if not isinstance(payload["resolved"], dict):
        _fail("configuration-resolution artifact contains a non-mapping outcome")
    return dict(payload)


def _derive_resolution_observation(
    *, cli_patch: Mapping[str, Any], file_mapping: Mapping[str, Any], raw: Mapping[str, Any]
) -> dict[str, Any]:
    def merge(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
        merged = dict(left)
        for key, item in right.items():
            current = merged.get(key)
            merged[key] = (
                merge(cast(Mapping[str, Any], current), cast(Mapping[str, Any], item))
                if isinstance(current, Mapping) and isinstance(item, Mapping)
                else item
            )
        return merged

    expected = merge(file_mapping, cli_patch)

    def sources(
        value: Mapping[str, Any], patch: Mapping[str, Any], prefix: str = ""
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            patch_item = patch.get(key)
            if isinstance(item, Mapping):
                result.update(
                    sources(
                        cast(Mapping[str, Any], item),
                        cast(Mapping[str, Any], patch_item)
                        if isinstance(patch_item, Mapping)
                        else {},
                        path,
                    )
                )
            else:
                result[path] = "CLI_PATCH" if key in patch else "FILE_MAPPING"
        return result

    provenance = sources(expected, cli_patch)
    return {
        "expected": expected,
        "precedence_satisfied": raw.get("resolved") == expected,
        "provenance": provenance,
        "resolved": raw.get("resolved"),
    }


def execute_empirical_probe(
    *,
    candidate_evidence_path: Path,
    cases: Sequence[Mapping[str, Any]],
    output_root: Path,
    python_executable: Path,
    timeout_seconds: int,
    workspace: Path,
) -> dict[str, Any]:
    """Execute evaluator-owned cases through candidate-declared resolver routes."""

    workspace = workspace.resolve(strict=True)
    try:
        candidate_evidence_path = candidate_evidence_path.resolve(strict=True)
        candidate_evidence_path.relative_to(workspace)
    except (OSError, ValueError) as exc:
        raise EvaluatorError("candidate evidence is outside the candidate workspace") from exc
    evidence = load_candidate_config_evidence(candidate_evidence_path)
    output_root.mkdir(parents=True, exist_ok=False)
    request_root = output_root / "request"
    request_root.mkdir()
    evidence_copy = request_root / "es_f1_candidate_evidence.json"
    evidence_copy.write_bytes(candidate_evidence_path.read_bytes())
    inputs = request_root / "inputs"
    inputs.mkdir()
    rows: list[dict[str, Any]] = []
    case_values: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for case in cases:
        if set(case) != {"case_id", "cli_patch", "file_mapping", "role"}:
            _fail("empirical case field set is not exact")
        case_id, role = case["case_id"], case["role"]
        if not isinstance(case_id, str) or role not in CONFIG_RESOLUTION_ROLES:
            _fail("empirical case identity or role is invalid")
        if not isinstance(case["file_mapping"], Mapping) or not isinstance(
            case["cli_patch"], Mapping
        ):
            _fail("empirical case inputs are not mappings")
        file_mapping = dict(cast(Mapping[str, Any], case["file_mapping"]))
        cli_patch = dict(cast(Mapping[str, Any], case["cli_patch"]))
        file_path = inputs / f"{case_id}-file.json"
        cli_path = inputs / f"{case_id}-cli.json"
        file_path.write_bytes(canonical_json_bytes(file_mapping))
        cli_path.write_bytes(canonical_json_bytes(cli_patch))
        rows.append(
            {
                "case_id": case_id,
                "cli_patch": {
                    "path": cli_path.relative_to(request_root).as_posix(),
                    "sha256": file_sha256(cli_path),
                },
                "file_mapping": {
                    "path": file_path.relative_to(request_root).as_posix(),
                    "sha256": file_sha256(file_path),
                },
                "role": role,
            }
        )
        case_values[case_id] = (file_mapping, cli_patch)
    request = {
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": file_sha256(evidence_copy),
        "candidate_id": evidence["candidate_id"],
        "operation_version": "ptychopinn_public_config_resolution.v1",
        "probe_cases": rows,
        "schema_version": "config_resolution_probe_request.v1",
    }
    request_path = request_root / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    run = run_config_resolution_adapter(
        adapter_relative_path=cast(dict[str, str], evidence["fixed_outputs"])[
            "adapter_path"
        ],
        expected_candidate_id=cast(str, evidence["candidate_id"]),
        expected_case_ids=tuple(row["case_id"] for row in rows),
        output_root=output_root / "result",
        python_executable=python_executable,
        request_path=request_path,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    observations = []
    for row, raw in zip(rows, run["observations"], strict=True):
        file_mapping, cli_patch = case_values[row["case_id"]]
        observations.append(
            {"case_id": row["case_id"], **_derive_resolution_observation(
                cli_patch=cli_patch, file_mapping=file_mapping, raw=raw
            )}
        )
    return {"observations": observations, "result": run["result"]}


DIRECT_RESOLVER_COMPARISON_TABLE = {
    "F1-H05-STRICT-INPUT-CONTRACT": (
        "strict-unknown", "strict-illtyped", "strict-retention",
    ),
    "F1-H06-DERIVED-PUBLIC-FIELDS": (
        "simulation-valid", "simulation-illtyped", "simulation-unknown",
        "simulation-invalid-mapping",
    ),
}


def _normalized_value(value: Any) -> bool:
    if value is None or type(value) in (bool, int, str):
        return True
    if type(value) is float:
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, list):
        return all(_normalized_value(item) for item in value)
    if isinstance(value, dict):
        return all(type(key) is str and _normalized_value(item) for key, item in value.items())
    return False


def load_direct_resolver_transcript(
    path: Path, *, expected_sha256: str
) -> dict[str, Any]:
    """Load the private direct-call transcript with exact ordering and bytes."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvaluatorError("direct resolver transcript is unreadable") from exc
    actual = _SHA256_PREFIX + hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        _fail("direct resolver transcript digest changed")
    try:
        transcript = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda constant: (_fail(
                f"direct resolver transcript contains {constant}"
            )),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluatorError("direct resolver transcript is invalid JSON") from exc
    if (
        not isinstance(transcript, dict)
        or set(transcript) != {"pid", "rows"}
        or canonical_json_bytes(transcript) != raw
        or type(transcript["pid"]) is not int
        or transcript["pid"] < 1
        or not isinstance(transcript["rows"], list)
    ):
        _fail("direct resolver transcript envelope is malformed")
    rows = transcript["rows"]
    if [row.get("case_id") for row in rows if isinstance(row, Mapping)] != list(
        DIRECT_RESOLVER_CASE_IDS
    ):
        _fail("direct resolver transcript order is not exact")
    for row, expected in zip(rows, DIRECT_RESOLVER_CASES, strict=True):
        if not isinstance(row, dict) or set(row) != {
            "case_id", "input_after", "input_before", "outcome"
        }:
            _fail("direct resolver transcript row is malformed")
        expected_input = {
            "cli_patch": expected["cli_patch"],
            "file_mapping": expected["file_mapping"],
        }
        if (
            row["input_before"] != expected_input
            or not _normalized_value(row["input_before"])
            or not _normalized_value(row["input_after"])
        ):
            _fail("direct resolver transcript input binding changed")
        if row["input_after"] != row["input_before"]:
            _fail("direct resolver mutated probe input")
        outcome = row["outcome"]
        if not isinstance(outcome, dict):
            _fail("direct resolver transcript outcome is malformed")
        if outcome.get("kind") == "raised":
            if (
                set(outcome) != {"exception_type", "kind"}
                or not isinstance(outcome["exception_type"], str)
                or "." not in outcome["exception_type"]
            ):
                _fail("direct resolver raised outcome is malformed")
            continue
        if outcome.get("kind") != "returned" or set(outcome) != {
            "field_catalog", "kind", "value"
        } or not _normalized_value(outcome["value"]):
            _fail("direct resolver returned outcome is malformed")
        catalog = outcome["field_catalog"]
        if not isinstance(catalog, list):
            _fail("direct resolver field catalog is malformed")
        paths: list[str] = []
        for catalog_row in catalog:
            if not isinstance(catalog_row, dict) or set(catalog_row) != {
                "fields", "kind", "path"
            }:
                _fail("direct resolver field catalog row is malformed")
            fields = catalog_row["fields"]
            if (
                catalog_row["kind"]
                not in {"mapping", "dataclass", "namedtuple", "object", "pydantic"}
                or not isinstance(catalog_row["path"], str)
                or not catalog_row["path"].startswith("$")
                or not isinstance(fields, list)
                or fields != sorted(set(fields))
                or not all(type(field) is str for field in fields)
            ):
                _fail("direct resolver field catalog row is malformed")
            paths.append(catalog_row["path"])
        if paths != sorted(set(paths)):
            _fail("direct resolver field catalog order is not exact")
    return cast(dict[str, Any], transcript)


def _named_values(value: Any, field: str) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == field:
                values.append(item)
            values.extend(_named_values(item, field))
    elif isinstance(value, list):
        for item in value:
            values.extend(_named_values(item, field))
    return values


def _has_exact_field(value: Any, field: str, expected: Any) -> bool:
    values = _named_values(value, field)
    return bool(values) and all(type(item) is type(expected) and item == expected for item in values)


def _mapping_catalog(value: Any, path: str = "$") -> list[tuple[str, tuple[str, ...]]]:
    rows: list[tuple[str, tuple[str, ...]]] = []
    if isinstance(value, dict):
        rows.append((path, tuple(sorted(value))))
        for key, item in value.items():
            rows.extend(_mapping_catalog(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_mapping_catalog(item, f"{path}[{index}]"))
    return sorted(rows)


def compare_direct_resolver_transcript(
    transcript: Mapping[str, Any]
) -> dict[str, bool]:
    """Derive strict-input and simulation-validation facts from direct calls."""

    rows = {row["case_id"]: row for row in cast(list[dict[str, Any]], transcript["rows"])}

    def returned(case_id: str) -> bool:
        return rows[case_id]["outcome"]["kind"] == "returned"

    def raised(case_id: str) -> bool:
        return rows[case_id]["outcome"]["kind"] == "raised"

    def value(case_id: str) -> Any:
        return rows[case_id]["outcome"].get("value")

    retained = value("strict-retention")
    h05 = returned("strict-retention") and raised("strict-unknown") and raised(
        "strict-illtyped"
    ) and all(
        _has_exact_field(retained, field, expected)
        for field, expected in {
            "N": 128,
            "n_groups": 7,
            "n_subsample": 3,
            "subsample_seed": 17,
            "enable_oversampling": True,
            "neighbor_pool_size": 5,
            "sequential_sampling": True,
        }.items()
    )
    simulation = rows["simulation-valid"]["outcome"]
    observed_catalog = sorted(
        (row["path"], tuple(row["fields"]))
        for row in simulation.get("field_catalog", ())
    )
    h06 = (
        returned("simulation-valid")
        and raised("simulation-illtyped")
        and raised("simulation-unknown")
        and raised("simulation-invalid-mapping")
        and canonical_json_bytes(simulation.get("value"))
        == canonical_json_bytes(_SIMULATION_PROBE_FILE)
        and observed_catalog == _mapping_catalog(_SIMULATION_PROBE_FILE)
    )
    return {
        "F1-H05-STRICT-INPUT-CONTRACT": h05,
        "F1-H06-DERIVED-PUBLIC-FIELDS": h06,
    }


def run_direct_resolver_probe(
    *,
    candidate_evidence_path: Path,
    output_root: Path,
    python_executable: Path,
    timeout_seconds: int,
    workspace: Path,
) -> dict[str, Any]:
    """Call candidate-declared resolvers directly in one audited scratch process."""

    workspace = workspace.resolve(strict=True)
    try:
        candidate_evidence_path.resolve(strict=True).relative_to(workspace)
    except (OSError, ValueError) as exc:
        raise EvaluatorError("candidate evidence is outside the candidate workspace") from exc
    evidence = load_candidate_config_evidence(candidate_evidence_path)
    by_role: dict[str, str] = {}
    for route in cast(list[dict[str, Any]], evidence["public_resolution_routes"]):
        for role in cast(list[str], route["roles"]):
            if role in by_role:
                _fail("candidate resolver role is ambiguous")
            by_role[role] = route["symbol"]
    if set(by_role) != set(CONFIG_RESOLUTION_ROLES):
        _fail("candidate resolver role domain is incomplete")
    if output_root.resolve(strict=False).is_relative_to(workspace):
        _fail("direct resolver output must be outside the candidate workspace")
    output_root.mkdir(parents=True, exist_ok=False)
    calls_path = output_root / "calls.json"
    transcript_path = output_root / "transcript.json"
    calls_path.write_bytes(canonical_json_bytes(list(DIRECT_RESOLVER_CASES)))
    run_candidate_probe(
        code=_DIRECT_RESOLVER_RUNNER,
        environment={
            "ES_F1_DIRECT_CALLS": str(calls_path),
            "ES_F1_DIRECT_ROUTES": json.dumps(by_role, sort_keys=True, separators=(",", ":")),
            "ES_F1_DIRECT_TRANSCRIPT": str(transcript_path),
            "ES_F1_WORKSPACE": str(workspace),
        },
        label="direct configuration resolver probe",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
        working_directory=output_root,
    )
    digest = file_sha256(transcript_path)
    transcript = load_direct_resolver_transcript(
        transcript_path, expected_sha256=digest
    )
    retained = next(
        row["outcome"]["value"]
        for row in transcript["rows"]
        if row["case_id"] == "strict-retention"
        and row["outcome"]["kind"] == "returned"
    ) if any(
        row["case_id"] == "strict-retention"
        and row["outcome"]["kind"] == "returned"
        for row in transcript["rows"]
    ) else None
    facts = compare_direct_resolver_transcript(transcript)
    if retained is None:
        facts["F1-H05-STRICT-INPUT-CONTRACT"] = False
    else:
        roundtrip = fresh_process_roundtrip(
            {"resolved": retained},
            output_root=output_root / "strict-roundtrip",
            protected_workspace=workspace,
            python_executable=python_executable,
            timeout_seconds=timeout_seconds,
        )
        facts["F1-H05-STRICT-INPUT-CONTRACT"] = (
            facts["F1-H05-STRICT-INPUT-CONTRACT"]
            and canonical_json_bytes(roundtrip["resolved"])
            == canonical_json_bytes(retained)
        )
    return {
        "facts": facts,
        "transcript": transcript,
        "transcript_sha256": digest,
    }


def normalize_bypass_events(events: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        _fail("bypass events must be one sequence")
    present: set[str] = set()
    for event in events:
        if not isinstance(event, Mapping) or set(event) != {"class_id", "consumer_id", "symbol"}:
            _fail("bypass event is malformed")
        class_id = event["class_id"]
        if class_id not in BYPASS_CLASSES:
            _fail("bypass class is outside the closed enum")
        if not all(isinstance(event[name], str) and event[name] for name in ("consumer_id", "symbol")):
            _fail("bypass event identity is malformed")
        present.add(cast(str, class_id))
    return tuple(class_id for class_id in BYPASS_CLASSES if class_id in present)


def _is_legacy_configuration_symbol(name: str) -> bool:
    lower = name.lower()
    return (
        "legacy_state" in lower
        or "legacy_config" in lower
        or "legacy_params" in lower
        or "params.cfg" in lower
        or "update_legacy_dict" in lower
    )


def _is_tolerant_configuration_operation(name: str) -> bool:
    lowered = name.rsplit(".", 1)[-1].lower()
    tokens = lowered.strip("_").split("_")
    load_semantics = (
        any(token in {"load", "loader"} for token in tokens)
        or lowered.endswith(("load", "loader"))
    )
    configuration_semantics = load_semantics or any(
        token in lowered for token in ("config", "adapter", "coerce")
    )
    return (
        ("compat" in lowered or "fallback" in lowered)
        and configuration_semantics
        or "legacy" in lowered and load_semantics
        or name in {"getattr", "hasattr"}
    )


def _builtin_type_method_descriptor_receiver(call: ast.Call) -> str | None:
    if not (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
    ):
        return None
    receiver = call.func.value.id
    owner = getattr(builtins, receiver, None)
    return receiver if (
        isinstance(owner, type)
        and owner not in {object, type}
        and inspect.ismethoddescriptor(vars(owner).get(call.func.attr))
    ) else None


def _configuration_receiver_tainted(
    call: ast.Call,
    relevant: Callable[[ast.AST | None], bool],
) -> bool:
    return (
        isinstance(call.func, ast.Attribute) and relevant(call.func.value)
    ) or (
        _builtin_type_method_descriptor_receiver(call) is not None
        and bool(call.args)
        and relevant(call.args[0])
    )


def _is_tolerant_mapping_operation(name: str) -> bool:
    return name.rsplit(".", 1)[-1] in {"get", "setdefault"}


def _is_mapping_value_coercion(name: str, arguments: Sequence[ast.AST]) -> bool:
    return name in {"bool", "bytes", "float", "int", "str"} and any(
        isinstance(argument, ast.Subscript)
        and not (
            isinstance(argument.value, ast.Attribute)
            and argument.value.attr == "shape"
        )
        for argument in arguments
    )


def _is_tolerant_configuration_call(
    name: str,
    arguments: Sequence[ast.AST],
    *,
    receiver_tainted: bool,
    call_tainted: bool,
) -> bool:
    return (
        receiver_tainted and _is_tolerant_mapping_operation(name)
        or call_tainted
        and (
            _is_tolerant_configuration_operation(name)
            and not (name == "getattr" and len(arguments) == 2)
            or _is_mapping_value_coercion(name, arguments)
        )
    )


def _requires_resolution_authority(row: Mapping[str, Any]) -> bool:
    return row.get("match_kind") == "CONFIGURATION_CONSTRUCTION"


def _module_binding_counts(tree: ast.Module) -> dict[str, int]:
    counts: dict[str, int] = {}
    pending: list[ast.AST] = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Import):
            names = (alias.asname or alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = (alias.asname or alias.name for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = (node.name,)
        elif isinstance(node, ast.Lambda):
            names = ()
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
            names = (node.name,) if node.name is not None else ()
            pending.extend(ast.iter_child_nodes(node))
        elif isinstance(node, ast.MatchMapping):
            names = (node.rest,) if node.rest is not None else ()
            pending.extend(ast.iter_child_nodes(node))
        elif isinstance(node, ast.ExceptHandler):
            names = (node.name,) if node.name is not None else ()
            pending.extend(ast.iter_child_nodes(node))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names = (node.id,)
        else:
            pending.extend(ast.iter_child_nodes(node))
            continue
        for name in names:
            counts[name] = counts.get(name, 0) + 1
    return counts


def detect_ast_bypasses(
    source: str,
    *,
    _tainted_names: Sequence[str] = (),
    _qualified_names: Mapping[str, str] | None = None,
    _propagate_taint: bool = True,
) -> tuple[str, ...]:
    """Classify bypasses only where configuration values can reach them."""

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise EvaluatorError("bypass source is invalid Python") from exc
    imported: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update((alias.asname or alias.name, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.update((alias.asname or alias.name, f"{node.module}.{alias.name}") for alias in node.names)

    def qualified(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return (_qualified_names or {}).get(
                node.id, imported.get(node.id, node.id)
            )
        if isinstance(node, ast.Attribute):
            owner = qualified(node.value)
            return f"{owner}.{node.attr}" if owner else node.attr
        if isinstance(node, ast.Subscript):
            return qualified(node.value)
        return ""

    classes: set[str] = set()

    def analyze(function: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        tainted = set(_tainted_names)

        def value_tainted(node: ast.AST | None) -> bool:
            if node is None:
                return False
            if isinstance(node, ast.Name):
                return node.id in tainted
            if isinstance(node, (ast.Attribute, ast.Subscript)):
                return value_tainted(node.value)
            return any(value_tainted(child) for child in ast.iter_child_nodes(node))

        scoped_nodes: list[ast.AST] = []
        pending = list(function.body)
        while pending:
            node = pending.pop()
            scoped_nodes.append(node)
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                pending.extend(ast.iter_child_nodes(node))

        changed = True
        while changed:
            changed = False
            for node in scoped_nodes:
                value: ast.AST | None = None
                targets: list[ast.AST] = []
                if isinstance(node, ast.Assign):
                    value, targets = node.value, list(node.targets)
                elif isinstance(node, ast.AnnAssign):
                    value, targets = node.value, [node.target]
                elif isinstance(node, ast.NamedExpr):
                    value, targets = node.value, [node.target]
                if _propagate_taint and value_tainted(value):
                    for target in targets:
                        for name in (
                            child.id for child in ast.walk(target) if isinstance(child, ast.Name)
                        ):
                            if name not in tainted:
                                tainted.add(name)
                                changed = True

        for node in scoped_nodes:
            if isinstance(node, ast.Call):
                name = qualified(node.func)
                if name in {"os.getenv", "os.environ.get", "environ.get"}:
                    classes.add("AMBIENT_CONFIGURATION_READ")
                arguments = (*node.args, *(keyword.value for keyword in node.keywords))
                receiver_tainted = _configuration_receiver_tainted(
                    node, value_tainted
                )
                tainted_call = receiver_tainted or any(
                    value_tainted(argument) for argument in arguments
                )
                if _is_legacy_configuration_symbol(name) and tainted_call:
                    classes.add("LEGACY_CONFIGURATION_STATE_MUTATION")
                elif _is_tolerant_configuration_call(
                    name,
                    arguments,
                    receiver_tainted=receiver_tainted,
                    call_tainted=tainted_call,
                ):
                    classes.add("TOLERANT_OR_COMPATIBILITY_LOADER")
            elif isinstance(node, ast.Try) and any(
                value_tainted(child)
                for statement in node.body
                for child in ast.walk(statement)
            ) and any(
                isinstance(child, (ast.Return, ast.Continue, ast.Break, ast.Pass))
                for handler in node.handlers
                for child in ast.walk(handler)
            ):
                classes.add("TOLERANT_OR_COMPATIBILITY_LOADER")
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.ctx, ast.Load)
                and qualified(node.value) in {"os.environ", "environ"}
            ):
                classes.add("AMBIENT_CONFIGURATION_READ")
            elif isinstance(
                node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)
            ):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(
                    (
                        isinstance(target, (ast.Attribute, ast.Subscript))
                        and _is_legacy_configuration_symbol(qualified(target.value))
                    )
                    or (
                        isinstance(target, ast.Name)
                        and value_tainted(getattr(node, "value", None))
                        and _is_legacy_configuration_symbol(qualified(target))
                    )
                    for target in targets
                ):
                    classes.add("LEGACY_CONFIGURATION_STATE_MUTATION")

    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if functions:
        for function in functions:
            analyze(function)
    else:
        wrapper = ast.FunctionDef(
            name="resolve", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=list(tree.body), decorator_list=[]
        )
        analyze(wrapper)
    return tuple(class_id for class_id in BYPASS_CLASSES if class_id in classes)


def walk_consumer_routes(
    *,
    consumer_rows: Sequence[Mapping[str, Any]],
    call_graph: Mapping[str, Sequence[str]],
    authority_symbols: set[str],
    bypass_symbols: Mapping[str, str | Sequence[str]],
    terminal_symbols: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Follow every reachable branch until an authority, bypass, or dead end."""

    if not consumer_rows or not authority_symbols:
        _fail("consumer route inputs are incomplete")
    normalized_bypasses = {
        symbol: (classes,) if isinstance(classes, str) else tuple(classes)
        for symbol, classes in bypass_symbols.items()
    }
    if any(
        class_id not in BYPASS_CLASSES
        for classes in normalized_bypasses.values()
        for class_id in classes
    ):
        _fail("consumer graph names an unknown bypass class")
    unresolved: list[str] = []
    bypasses: set[str] = set()
    traces: list[dict[str, Any]] = []
    seen_consumers: set[str] = set()
    for row in consumer_rows:
        if set(row) not in (
            {"consumer_id", "entry_symbol"},
            {"consumer_id", "entry_symbol", "requires_authority"},
        ):
            _fail("consumer row field set is not exact")
        consumer_id, entry = row["consumer_id"], row["entry_symbol"]
        requires_authority = row.get("requires_authority", True)
        if (
            not isinstance(consumer_id, str)
            or not isinstance(entry, str)
            or type(requires_authority) is not bool
            or consumer_id in seen_consumers
        ):
            _fail("consumer row identity is invalid")
        seen_consumers.add(consumer_id)
        reached_authority = False
        reached_dead_end = False
        reached_unresolved = False
        paths: list[list[str]] = []

        def visit(symbol: str, trail: list[str]) -> None:
            nonlocal reached_authority, reached_dead_end, reached_unresolved
            if symbol in trail:
                paths.append([*trail, symbol])
                return
            current = [*trail, symbol]
            if symbol in normalized_bypasses:
                bypasses.update(normalized_bypasses[symbol])
                paths.append(current)
                return
            if symbol in authority_symbols:
                reached_authority = True
                paths.append(current)
                return
            if symbol in terminal_symbols:
                paths.append(current)
                return
            children = call_graph.get(symbol, ())
            if not children:
                if symbol not in call_graph:
                    reached_dead_end = True
                    reached_unresolved = True
                paths.append(current)
                return
            for child in children:
                if not isinstance(child, str) or not child:
                    _fail("consumer call graph edge is malformed")
                visit(child, current)

        visit(entry, [])
        consumer_bypasses = sorted(
            {
                class_id
                for path in paths
                for symbol in path
                for class_id in normalized_bypasses.get(symbol, ())
            }
        )
        closed = (
            not consumer_bypasses
            and (
                not requires_authority and not reached_unresolved
                or reached_authority and not reached_dead_end
            )
        )
        if not closed:
            unresolved.append(consumer_id)
        traces.append(
            {
                "bypass_classes": consumer_bypasses,
                "closed": closed,
                "consumer_id": consumer_id,
                "paths": paths,
            }
        )
    return {
        "bypass_classes": [class_id for class_id in BYPASS_CLASSES if class_id in bypasses],
        "closed": not unresolved and not bypasses,
        "traces": traces,
        "unresolved_consumers": unresolved,
    }


def _is_plain_generated_dataclass(
    node: ast.ClassDef,
    resolve_name: Callable[[ast.AST], str | None],
    *,
    trace_post_init: bool = False,
    trace_frozen_custom_init: bool = False,
) -> bool:
    """Return whether construction is the unwrapped stdlib-generated initializer."""

    class_binding_counts = _module_binding_counts(
        ast.Module(body=list(node.body), type_ignores=[])
    )

    def immutable_default(value: ast.AST) -> bool:
        return isinstance(value, ast.Constant) or (
            isinstance(value, ast.Tuple)
            and all(immutable_default(element) for element in value.elts)
        )

    def exact_dict_field(value: ast.AST) -> bool:
        return (
            isinstance(value, ast.Call)
            and resolve_name(value.func) == "dataclasses.field"
            and not value.args
            and len(value.keywords) == 1
            and value.keywords[0].arg == "default_factory"
            and isinstance(value.keywords[0].value, ast.Name)
            and value.keywords[0].value.id == "dict"
            and resolve_name(value.keywords[0].value) == "builtins.dict"
        )

    def metadata_only_required_field(value: ast.AST) -> bool:
        return (
            isinstance(value, ast.Call)
            and resolve_name(value.func) == "dataclasses.field"
            and not value.args
            and bool(value.keywords)
            and len(value.keywords) == len({keyword.arg for keyword in value.keywords})
            and all(
                keyword.arg in {"compare", "hash", "metadata", "repr"}
                for keyword in value.keywords
            )
        )

    def builtin_method_decorator(value: ast.AST) -> bool:
        resolved = resolve_name(value)
        return resolved in {
            "builtins.classmethod",
            "builtins.staticmethod",
        } or (
            resolved == ""
            and isinstance(value, ast.Name)
            and value.id in {"classmethod", "staticmethod"}
            and class_binding_counts.get(value.id, 0) == 0
        )

    if node.bases or node.keywords or len(node.decorator_list) != 1:
        return False
    decorator = node.decorator_list[0]
    if resolve_name(decorator.func if isinstance(decorator, ast.Call) else decorator) != (
        "dataclasses.dataclass"
    ):
        return False
    if isinstance(decorator, ast.Call):
        if decorator.args or any(keyword.arg is None for keyword in decorator.keywords):
            return False
        if trace_frozen_custom_init:
            options = {keyword.arg: keyword.value for keyword in decorator.keywords}
            if len(options) != len(decorator.keywords) or set(options) != {
                "frozen",
                "init",
                "slots",
            } or any(
                not isinstance(options[name], ast.Constant)
                or options[name].value is not expected
                for name, expected in {
                    "frozen": True,
                    "init": False,
                    "slots": True,
                }.items()
            ):
                return False
        else:
            init = [
                keyword.value
                for keyword in decorator.keywords
                if keyword.arg == "init"
            ]
            if len(init) > 1 or (
                init
                and not (
                    isinstance(init[0], ast.Constant) and init[0].value is True
                )
            ):
                return False
    elif trace_frozen_custom_init:
        return False
    field_names = {
        child.target.id
        for child in node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and child.simple == 1
    }
    custom_initializer_count = 0
    for child in node.body:
        if isinstance(child, ast.AnnAssign):
            if (
                not isinstance(child.target, ast.Name)
                or child.simple != 1
                or child.value is not None
                and not (
                    immutable_default(child.value)
                    or exact_dict_field(child.value)
                    or metadata_only_required_field(child.value)
                )
            ):
                return False
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if child.name == "__init__" and trace_frozen_custom_init:
                if (
                    isinstance(child, ast.AsyncFunctionDef)
                    or child.decorator_list
                    or child.args.posonlyargs
                    or not child.args.args
                    or child.args.args[0].arg != "self"
                ):
                    return False
                custom_initializer_count += 1
                continue
            if child.name == "__post_init__" and trace_post_init:
                if (
                    isinstance(child, ast.AsyncFunctionDef)
                    or child.decorator_list
                    or child.args.posonlyargs
                    or len(child.args.args) != 1
                    or child.args.args[0].arg != "self"
                    or child.args.vararg is not None
                    or child.args.kwonlyargs
                    or child.args.kwarg is not None
                    or child.args.defaults
                    or child.args.kw_defaults
                ):
                    return False
                continue
            if (
                child.name
                in {"__new__", "__init__", "__post_init__", "__setattr__"}
                or child.name in field_names
                or child.decorator_list
                and not (
                    len(child.decorator_list) == 1
                    and (
                        isinstance(child.decorator_list[0], ast.Name)
                        and child.decorator_list[0].id == "property"
                        or builtin_method_decorator(child.decorator_list[0])
                    )
                )
            ):
                return False
            continue
        if isinstance(child, ast.Pass) or (
            isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Constant)
            and isinstance(child.value.value, str)
        ):
            continue
        return False
    return not trace_frozen_custom_init or custom_initializer_count == 1


_PLAIN_BUILTIN_EXCEPTION = "@plain-builtin-exception"


def _is_plain_builtin_exception_subclass(
    node: ast.ClassDef, shadowed_names: Mapping[str, object]
) -> bool:
    if node.decorator_list or node.keywords or len(node.bases) != 1:
        return False
    base = node.bases[0]
    owner = getattr(builtins, base.id, None) if isinstance(base, ast.Name) else None
    return (
        isinstance(owner, type)
        and issubclass(owner, BaseException)
        and base.id not in shadowed_names
        and all(
            isinstance(child, ast.Pass)
            or isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Constant)
            and isinstance(child.value.value, str)
            for child in node.body
        )
    )


def _has_module_object_mutation(
    tree: ast.Module,
    object_names: set[str],
    *,
    reject_argument_escape: bool,
    allowed_argument_calls: frozenset[int] = frozenset(),
    allowed_alias_assignments: frozenset[int] = frozenset(),
) -> bool:
    def root_name(value: ast.AST) -> str | None:
        while isinstance(value, (ast.Attribute, ast.Subscript)):
            value = value.value
        return value.id if isinstance(value, ast.Name) else None

    def aliases_object(value: ast.AST) -> bool:
        if isinstance(value, ast.Name):
            return value.id in object_names
        if isinstance(value, ast.Attribute):
            return root_name(value) in object_names
        if isinstance(value, (ast.Starred, ast.NamedExpr)):
            return aliases_object(value.value)
        if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
            return any(aliases_object(child) for child in value.elts)
        if isinstance(value, ast.Dict):
            return any(
                child is not None and aliases_object(child)
                for child in (*value.keys, *value.values)
            )
        return False

    def eager_definition_nodes(
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda,
    ) -> tuple[ast.AST, ...]:
        type_params = tuple(getattr(node, "type_params", ()))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return (
                *node.decorator_list,
                node.args,
                *((node.returns,) if node.returns is not None else ()),
                *type_params,
            )
        if isinstance(node, ast.ClassDef):
            return (
                *node.decorator_list,
                *node.bases,
                *(keyword.value for keyword in node.keywords),
                *type_params,
            )
        return (node.args,)

    runtime_functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    pending_functions: list[ast.AST] = list(tree.body)
    while pending_functions:
        node = pending_functions.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            runtime_functions.append(node)
            continue
        if isinstance(node, (ast.ClassDef, ast.Lambda)):
            continue
        pending_functions.extend(ast.iter_child_nodes(node))

    object_closures = {
        node.name
        for node in runtime_functions
        if reject_argument_escape
        and _has_module_object_mutation(
            ast.Module(body=list(node.body), type_ignores=[]),
            object_names,
            reject_argument_escape=True,
            allowed_argument_calls=allowed_argument_calls,
        )
    }
    binding_counts = _module_binding_counts(tree)
    object_closure_aliases = {
        node.targets[0].id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and binding_counts.get(node.targets[0].id) == 1
        and isinstance(node.value, ast.Name)
        and node.value.id in object_closures
    }
    pending: list[ast.AST] = list(tree.body)
    while pending:
        child = pending.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            pending.extend(eager_definition_nodes(child))
            continue
        if isinstance(child, ast.Call):
            if (
                isinstance(child.func, ast.Name)
                and child.func.id in object_closures | object_closure_aliases
            ):
                return True
            if (
                isinstance(child.func, ast.Name)
                and child.func.id == "setattr"
                and child.args
                and root_name(child.args[0]) in object_names
            ):
                return True
            if (
                reject_argument_escape
                and id(child) not in allowed_argument_calls
                and isinstance(child.func, ast.Attribute)
                and aliases_object(child.func.value)
                and (
                    not isinstance(child.func.value, ast.Name)
                    or child.func.attr in {"__setattr__", "__delattr__"}
                )
            ):
                return True
            if (
                reject_argument_escape
                and id(child) not in allowed_argument_calls
                and any(
                    aliases_object(value)
                    for value in (
                        *child.args,
                        *(keyword.value for keyword in child.keywords),
                    )
                )
            ):
                return True
        if (
            reject_argument_escape
            and isinstance(child, (ast.Return, ast.Yield, ast.YieldFrom))
            and child.value is not None
            and aliases_object(child.value)
        ):
            return True
        if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
            targets = (
                child.targets
                if isinstance(child, (ast.Assign, ast.Delete))
                else (child.target,)
            )
            if any(
                isinstance(target, ast.Attribute)
                and root_name(target) in object_names
                for root in targets
                for target in ast.walk(root)
            ):
                return True
            value = getattr(child, "value", None)
            if (
                value is not None
                and aliases_object(value)
                and id(child) not in allowed_alias_assignments
            ):
                return True
        pending.extend(ast.iter_child_nodes(child))
    return False


def _allowed_native_isinstance_calls(
    tree: ast.Module,
    object_names: set[str],
) -> frozenset[int]:
    binding_scopes = (
        tree,
        *(
            ast.Module(body=list(node.body), type_ignores=[])
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ),
    )
    shadowed = any(
        _module_binding_counts(scope).get("isinstance", 0)
        for scope in binding_scopes
    ) or any(
        isinstance(node, ast.arg) and node.arg == "isinstance"
        for node in ast.walk(tree)
    )
    builtins_aliases = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "builtins"
    }
    if shadowed or (
        builtins_aliases
        and any(
            _has_module_object_mutation(
                scope, builtins_aliases, reject_argument_escape=True
            )
            for scope in binding_scopes
        )
    ):
        return frozenset()

    return frozenset(
        id(call)
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "isinstance"
        and len(call.args) == 2
        and not call.keywords
        and isinstance(call.args[1], ast.Name)
        and call.args[1].id in object_names
        and not any(
            isinstance(node, ast.Name) and node.id in object_names
            for node in ast.walk(call.args[0])
        )
    )


def _has_module_class_attribute_mutation(
    tree: ast.Module,
    node: ast.ClassDef,
    *,
    allow_stable_alias: bool = False,
) -> bool:
    nested_global_names = {
        name
        for scope in ast.walk(tree)
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for child in ast.walk(scope)
        if isinstance(child, ast.Global)
        for name in child.names
    }
    if node.name in nested_global_names:
        return True
    aliases = [
        child
        for child in tree.body
        if allow_stable_alias
        and isinstance(child, ast.Assign)
        and len(child.targets) == 1
        and isinstance(child.targets[0], ast.Name)
        and isinstance(child.value, ast.Name)
        and child.value.id == node.name
        and child.lineno > node.lineno
        and _module_binding_counts(tree).get(child.targets[0].id) == 1
        and child.targets[0].id not in nested_global_names
    ]
    object_names = {node.name}
    allowed_alias_assignments: frozenset[int] = frozenset()
    if len(aliases) == 1:
        object_names.add(cast(ast.Name, aliases[0].targets[0]).id)
        allowed_alias_assignments = frozenset({id(aliases[0])})
    return _has_module_object_mutation(
        tree,
        object_names,
        reject_argument_escape=True,
        allowed_argument_calls=_allowed_native_isinstance_calls(tree, object_names),
        allowed_alias_assignments=allowed_alias_assignments,
    )


def _module_functions(
    path: Path,
    module: str,
    *,
    authority_symbols: set[str],
    consumer_rows: Sequence[Mapping[str, Any]],
    current_construction_spans: frozenset[tuple[object, ...]] | None = None,
    workspace_module_roots: frozenset[str] = frozenset(),
    available_external_imports: frozenset[str] = frozenset(),
    workspace_function_nodes: Mapping[
        str,
        tuple[
            str,
            ast.FunctionDef | ast.AsyncFunctionDef | None,
            bool,
            bool,
        ],
    ] | None = None,
) -> tuple[
    dict[str, list[str]],
    dict[str, tuple[str, ...]],
    set[str],
    set[str],
    dict[str, tuple[str, tuple[str, ...]]],
]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise EvaluatorError(f"candidate consumer source is unreadable: {path}") from exc
    workspace_function_nodes = workspace_function_nodes or {}
    if current_construction_spans is None:
        current_construction_spans = frozenset(
            (
                span.get("start_line"),
                span.get("start_col"),
                span.get("end_line"),
                span.get("end_col"),
            )
            for row in consumer_rows
            if row.get("match_kind") == "CONFIGURATION_CONSTRUCTION"
            and isinstance((span := row.get("source_span")), Mapping)
        )
    parent_by_node: dict[int, tuple[ast.AST, str, bool]] = {}
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if isinstance(value, ast.AST):
                parent_by_node[id(value)] = (parent, field, False)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, ast.AST):
                        parent_by_node[id(child)] = (parent, field, True)
    workspace_root = path.parents[len(module.split(".")) - 1]
    package = module.rsplit(".", 1)[0] if "." in module else ""
    def imported_names(node: ast.Import | ast.ImportFrom) -> dict[str, str]:
        if isinstance(node, ast.Import):
            return {
                alias.asname or alias.name.split(".", 1)[0]:
                    alias.name if alias.asname else alias.name.split(".", 1)[0]
                for alias in node.names
            }
        if node.module:
            parts = package.split(".") if package else []
            base = parts[: max(0, len(parts) - node.level + 1)] if node.level else []
            imported_module = ".".join((*base, node.module)) if node.level else node.module
            return dict(
                (alias.asname or alias.name, f"{imported_module}.{alias.name}")
                for alias in node.names
            )
        if node.level:
            parts = package.split(".") if package else []
            imported_module = ".".join(
                parts[: max(0, len(parts) - node.level + 1)]
            )
            return {
                alias.asname or alias.name: f"{imported_module}.{alias.name}"
                for alias in node.names
            }
        return {}

    module_binding_counts = _module_binding_counts(tree)
    import_targets: dict[str, set[str]] = {}
    pending_imports: list[ast.AST] = list(tree.body)
    while pending_imports:
        node = pending_imports.pop()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for local, target in imported_names(node).items():
                import_targets.setdefault(local, set()).add(target)
        elif not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            pending_imports.extend(ast.iter_child_nodes(node))
    imports = {
        local: next(iter(targets))
        for local, targets in import_targets.items()
        if len(targets) == 1 and module_binding_counts.get(local) == 1
    }
    direct_fields_imports = [
        (node, alias)
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.level == 0
        and node.module == "dataclasses"
        for alias in node.names
        if alias.name == "fields"
    ]
    stable_fields_import_line = (
        direct_fields_imports[0][0].lineno
        if len(direct_fields_imports) == 1
        and direct_fields_imports[0][1].asname is None
        and imports.get("fields") == "dataclasses.fields"
        and not _has_module_object_mutation(
            tree, {"fields"}, reject_argument_escape=True
        )
        else None
    )
    module_rebounds = set(module_binding_counts) - set(imports)
    imports_by_owner: dict[str, dict[str, str]] = {}
    graph: dict[str, list[str]] = {}
    bypasses: dict[str, tuple[str, ...]] = {}
    module_bypasses = detect_ast_bypasses(
        ast.unparse(
            ast.Module(
                body=[
                    node
                    for node in tree.body
                    if not isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    )
                ],
                type_ignores=[],
            )
        )
    )
    if module_bypasses:
        bypasses[module] = module_bypasses

    def name(node: ast.AST, owner: str = "") -> str:
        visible_imports = imports_by_owner.get(owner, imports)
        if isinstance(node, ast.Name):
            if node.id in visible_imports:
                return visible_imports[node.id]
            if node.id in module_rebounds:
                return f"{module}.{node.id}"
            if hasattr(builtins, node.id):
                return ""
            return f"{module}.{node.id}"
        if isinstance(node, ast.Attribute):
            prefix = name(node.value, owner)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    def has_direct_import(local: str, target: str, before_line: int) -> bool:
        return any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            and imported_names(node).get(local) == target
            and node.lineno < before_line
            for node in tree.body
        )

    def uses_module_fields_binding(node: ast.AST, class_name: str) -> bool:
        while (parent := parent_by_node.get(id(node))) is not None:
            owner = parent[0]
            if isinstance(
                owner,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                return False
            if isinstance(
                owner, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            ):
                bound = {
                    child.id
                    for generator in owner.generators
                    for child in ast.walk(generator.target)
                    if isinstance(child, ast.Name)
                    and isinstance(child.ctx, ast.Store)
                }
                if bound & {"fields", class_name}:
                    return False
            if isinstance(owner, ast.Module):
                return True
            node = owner
        return False

    def stable_workspace_class_argument(
        value: ast.AST, factory_call: ast.Call
    ) -> bool:
        if not isinstance(value, ast.Name):
            return False
        target = name(value)
        context = workspace_function_nodes.get(target)
        if context is None or not context[2]:
            return False
        local = value.id
        if module_binding_counts.get(local) != 1:
            return False
        same_module_declaration = any(
            isinstance(node, ast.ClassDef)
            and node.name == local
            and node.lineno < factory_call.lineno
            for node in tree.body
        )
        direct_import = has_direct_import(local, target, factory_call.lineno)
        if not same_module_declaration and not (direct_import and context[3]):
            return False
        allowed_calls = {id(factory_call)}
        if stable_fields_import_line is not None:
            allowed_calls.update(
                id(node)
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "fields"
                and len(node.args) == 1
                and not node.keywords
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == local
                and stable_fields_import_line < node.lineno < factory_call.lineno
                and uses_module_fields_binding(node, local)
            )
        return not _has_module_object_mutation(
            tree,
            {local},
            reject_argument_escape=True,
            allowed_argument_calls=frozenset(allowed_calls),
        )

    def verified_factory_value(node: ast.AST, factory_call: ast.Call) -> bool:
        return (
            isinstance(node, ast.Constant)
            or isinstance(node, ast.Name) and node.id == "__name__"
            or stable_workspace_class_argument(node, factory_call)
        )

    def has_stable_external_factory(call: ast.Call) -> bool:
        root: ast.AST = call.func
        while isinstance(root, ast.Attribute):
            root = root.value
        return (
            isinstance(root, ast.Name)
            and (target := imports.get(root.id)) is not None
            and has_direct_import(root.id, target, call.lineno)
        )

    reassigned_attributes = {
        name(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, (ast.Store, ast.Del))
    }
    reassigned_attributes.update(
        f"{name(node.args[0])}.{node.args[1].value}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    )

    def verified_external_factory(call: ast.Call) -> str | None:
        factory = name(call.func)
        if not (
            factory in available_external_imports
            and has_stable_external_factory(call)
            and factory not in reassigned_attributes
            and factory.split(".", 1)[0] not in workspace_module_roots
            and all(verified_factory_value(value, call) for value in call.args)
            and all(
                keyword.arg is not None
                and verified_factory_value(keyword.value, call)
                for keyword in call.keywords
            )
            and not _has_module_object_mutation(
                tree,
                {
                    local
                    for local, imported in imports.items()
                    if imported.split(".", 1)[0] == factory.split(".", 1)[0]
                },
                reject_argument_escape=False,
            )
        ):
            return None
        return factory

    verified_external_receivers = {
        node.targets[0].id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and module_binding_counts.get(node.targets[0].id) == 1
        and isinstance(node.value, ast.Call)
        and (factory := verified_external_factory(node.value)) is not None
        and not any(
            attribute.startswith(f"{module}.{node.targets[0].id}.")
            for attribute in reassigned_attributes
        )
        and not _has_module_object_mutation(
            tree,
            {node.targets[0].id},
            reject_argument_escape=True,
        )
    }

    for node in tree.body:
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and module_binding_counts.get(node.targets[0].id) == 1
        ):
            continue
        target = name(node.value)
        if target and target.split(".", 1)[0] in {
            imported.split(".", 1)[0] for imported in imports.values()
        }:
            graph[f"{module}.{node.targets[0].id}"] = [target]

    functions: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    classes: list[tuple[str, ast.ClassDef]] = []

    def collect(nodes: Sequence[ast.stmt], owner: str) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = f"{owner}.{node.name}"
                functions.append((symbol, node))
                collect(node.body, symbol)
            elif isinstance(node, ast.ClassDef):
                symbol = f"{owner}.{node.name}"
                classes.append((symbol, node))
                collect(node.body, symbol)

    collect(tree.body, module)
    decorated_owners = (*functions, *classes)
    local_by_name: dict[str, str] = {}
    duplicates: set[str] = set()
    for symbol, node in functions:
        if node.name in local_by_name:
            duplicates.add(node.name)
        else:
            local_by_name[node.name] = symbol
    for duplicate in duplicates:
        local_by_name.pop(duplicate, None)
    function_by_symbol = dict(functions)
    class_by_symbol = dict(classes)
    rebound_by_owner: dict[str, set[str]] = {module: module_rebounds}

    def literal_dataclass_name(node: ast.AST) -> str | None:
        target = name(node)
        return None if target in {"builtins.dict", "dataclasses.field"} else target

    class_decorators = [
        (symbol, decorator, {id(child) for child in ast.walk(decorator)})
        for symbol, class_node in classes
        for decorator in class_node.decorator_list
        if isinstance(decorator, ast.Call)
    ]
    class_base: dict[str, str | None] = {}
    generated_dataclasses: set[str] = set()
    plain_exceptions: set[str] = set()
    for symbol, node in classes:
        bases = tuple(filter(None, (name(base) for base in node.bases)))
        class_base[symbol] = bases[0] if len(bases) == 1 else None
        indexed_plain_dataclass = workspace_function_nodes.get(symbol) == (
            "dataclasses.dataclass",
            None,
            True,
            True,
        )
        plain_generated_dataclass = _is_plain_generated_dataclass(
            node, literal_dataclass_name
        )
        if (
            indexed_plain_dataclass or plain_generated_dataclass
        ) and not _has_module_class_attribute_mutation(
            tree, node, allow_stable_alias=True
        ):
            generated_dataclasses.add(symbol)
        if not _has_module_class_attribute_mutation(
            tree, node
        ) and _is_plain_builtin_exception_subclass(node, module_binding_counts):
            plain_exceptions.add(symbol)
        initializer = next(
            (
                f"{symbol}.__init__"
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == "__init__"
            ),
            None,
        )
        if initializer is not None:
            graph[symbol] = [initializer]
        elif len(bases) == 1:
            graph[symbol] = [bases[0]]

    def enclosing_suites(node: ast.AST) -> set[tuple[int, str]]:
        suites: set[tuple[int, str]] = set()
        while (parent := parent_by_node.get(id(node))) is not None:
            owner_node, field, is_sequence = parent
            if is_sequence and isinstance(node, ast.stmt):
                suites.add((id(owner_node), field))
            node = owner_node
        return suites

    def import_event_suite(
        node: ast.Import | ast.ImportFrom,
        local: str,
        owner: str,
    ) -> tuple[int, str]:
        parent, field, is_sequence = parent_by_node[id(node)]
        suite = (id(parent), field)
        if not (
            is_sequence
            and field == "body"
            and isinstance(parent, ast.Try)
            and not parent.orelse
            and not parent.finalbody
            and parent.handlers
            and all(
                len(handler.body) == 1
                and (
                    isinstance(handler.body[0], ast.Raise)
                    or owner != module and isinstance(handler.body[0], ast.Return)
                )
                for handler in parent.handlers
            )
            and _module_binding_counts(
                ast.Module(body=list(parent.body), type_ignores=[])
            ).get(local) == 1
        ):
            return suite
        outer, outer_field, outer_is_sequence = parent_by_node[id(parent)]
        assert outer_is_sequence
        return id(outer), outer_field

    binding_events_by_owner: dict[
        str, dict[str, list[tuple[int, int, str, str, tuple[int, str]]]]
    ] = {}

    def scope_binding_events(
        nodes: Sequence[ast.stmt], owner: str
    ) -> dict[str, list[tuple[int, int, str, str, tuple[int, str]]]]:
        events: dict[
            str, list[tuple[int, int, str, str, tuple[int, str]]]
        ] = {}
        nested_binding_mutations: set[str] = set()

        def collect_nested_mutations(scope: ast.AST) -> None:
            declared: set[str] = set()
            mutated: set[str] = set()
            nested: list[ast.AST] = []
            pending = list(ast.iter_child_nodes(scope))
            while pending:
                child = pending.pop()
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
                ):
                    nested.append(child)
                    continue
                if isinstance(child, ast.Nonlocal):
                    declared.update(child.names)
                elif owner == module and isinstance(child, ast.Global):
                    declared.update(child.names)
                elif isinstance(child, ast.Name) and isinstance(
                    child.ctx, (ast.Store, ast.Del)
                ):
                    mutated.add(child.id)
                pending.extend(ast.iter_child_nodes(child))
            nested_binding_mutations.update(declared & mutated)
            for child in nested:
                collect_nested_mutations(child)

        def add(node: ast.AST, local: str, kind: str, target: str = "") -> None:
            parent, field, is_sequence = parent_by_node[id(node)]
            assert is_sequence
            events.setdefault(local, []).append(
                (
                    node.lineno,
                    node.col_offset,
                    kind,
                    target,
                    import_event_suite(node, local, owner)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    else (id(parent), field),
                )
            )

        def collect(suite: Sequence[ast.stmt]) -> None:
            for node in suite:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for local, target in imported_names(node).items():
                        add(node, local, "import", target)
                    continue
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    collect_nested_mutations(node)
                    target = f"{owner}.{node.name}"
                    known_node = function_by_symbol.get(target) or class_by_symbol.get(target)
                    add(
                        node,
                        node.name,
                        "local" if known_node is node else "unknown",
                        target,
                    )
                    continue
                bindings = _module_binding_counts(
                    ast.Module(body=[node], type_ignores=[])
                )
                for local in bindings:
                    target = f"{owner}.{local}"
                    if isinstance(node, ast.Assign) and target in graph:
                        add(node, local, "local", target)
                    else:
                        add(node, local, "unknown")
                for field in ("body", "orelse", "finalbody"):
                    nested = getattr(node, field, None)
                    if isinstance(nested, list):
                        collect(nested)
                if isinstance(node, (ast.Try, ast.TryStar)):
                    for handler in node.handlers:
                        collect(handler.body)
                elif isinstance(node, ast.Match):
                    for case in node.cases:
                        collect(case.body)

        collect(nodes)
        for local in nested_binding_mutations:
            local_events = events.get(local, ())
            events[local] = [
                (event[0], event[1], "invalid_import", "", event[4])
                if event[2] == "import"
                else event
                for event in local_events
            ]
        for local_events in events.values():
            imports_for_local = [event for event in local_events if event[2] == "import"]
            import_positions = sorted(event[:2] for event in imports_for_local)
            if len(import_positions) > 1:
                conflict_position = import_positions[1]
                conflicting_suites = (
                    len({event[3] for event in imports_for_local}) > 1
                    and len({event[4] for event in imports_for_local}) > 1
                )
                local_events[:] = [
                    (event[0], event[1], "invalid_import", event[3], event[4])
                    if event[2] == "import"
                    and (conflicting_suites or event[:2] >= conflict_position)
                    else event
                    for event in local_events
                ]
        return events

    binding_events_by_owner[module] = scope_binding_events(tree.body, module)
    for owner, node in functions:
        events = scope_binding_events(node.body, owner)
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            *((node.args.vararg,) if node.args.vararg is not None else ()),
            *((node.args.kwarg,) if node.args.kwarg is not None else ()),
        ):
            events.setdefault(argument.arg, []).append(
                (
                    node.lineno,
                    node.col_offset,
                    "unknown",
                    "",
                    (id(node), "body"),
                )
            )
        binding_events_by_owner[owner] = events

    def local_constructor(symbol: str) -> str | None:
        seen: set[str] = set()
        while symbol not in seen:
            seen.add(symbol)
            children = graph.get(symbol, ())
            if len(children) != 1:
                return None
            symbol = children[0]
            if symbol in function_by_symbol:
                return symbol
        return None

    def super_callee(call: ast.Call, owner: str) -> str | None:
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "__init__"
            and isinstance(call.func.value, ast.Call)
            and isinstance(call.func.value.func, ast.Name)
            and call.func.value.func.id == "super"
        ):
            return None
        class_owner = owner
        while class_owner not in class_base and "." in class_owner:
            class_owner = class_owner.rsplit(".", 1)[0]
        return class_base.get(class_owner)

    def stable_reimport_alias(
        local: str,
        owner: str,
        binding_scope: str,
    ) -> bool:
        def eager_class_bodies(body: ast.Module) -> list[ast.Module]:
            classes: list[ast.Module] = []
            pending = list(body.body)
            while pending:
                child = pending.pop()
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
                ):
                    continue
                if isinstance(child, ast.ClassDef):
                    classes.append(
                        ast.Module(body=list(child.body), type_ignores=[])
                    )
                    pending.extend(child.body)
                    continue
                pending.extend(ast.iter_child_nodes(child))
            return classes

        scope = owner
        checked: list[ast.Module] = []
        while scope.startswith(module):
            if scope == module:
                body = tree
            elif node := function_by_symbol.get(scope):
                body = ast.Module(body=list(node.body), type_ignores=[])
            else:
                body = None
            if body is not None:
                checked.append(body)
                checked.extend(eager_class_bodies(body))
            if scope == binding_scope:
                return not any(
                    _has_module_object_mutation(
                        body,
                        {local},
                        reject_argument_escape=True,
                    )
                    for body in checked
                )
            if scope == module:
                break
            scope = scope.rsplit(".", 1)[0]
        return False

    def active_name_binding(
        call: ast.Call,
        owner: str,
        binding_context: tuple[str, int] = ("runtime", 0),
    ) -> tuple[str, str] | None:
        root: ast.AST = call.func
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return None
        local = root.id
        if isinstance(call.func, ast.Attribute):
            scope = owner
            while scope.startswith(module):
                if any(
                    event[2] in {"import", "invalid_import"}
                    for event in binding_events_by_owner.get(scope, {}).get(local, ())
                ):
                    break
                if scope == module:
                    return None
                scope = scope.rsplit(".", 1)[0]
        position = (call.lineno, call.col_offset)
        call_suites = enclosing_suites(call)
        scope = owner
        while scope.startswith(module):
            events = binding_events_by_owner.get(scope, {}).get(local, ())
            if scope == module and binding_context[0] == "source":
                active = [
                    event
                    for event in events
                    if event[4] in call_suites and event[0] <= binding_context[1]
                ]
            elif scope == module and owner != module:
                active = [event for event in events if event[4] in call_suites]
            else:
                active = [
                    event
                    for event in events
                    if event[4] in call_suites and event[:2] <= position
                ]
            if active:
                _, _, kind, target, _ = max(active, key=lambda event: event[:2])
                if kind == "invalid_import":
                    imports = [
                        event
                        for event in active
                        if event[2] in {"import", "invalid_import"}
                    ]
                    if (
                        len(imports) == len(active)
                        and len(imports) >= 2
                        and target
                        and len({(event[3], event[4]) for event in imports}) == 1
                        and stable_reimport_alias(local, owner, scope)
                    ):
                        return "import", target
                    return "unknown", ""
                return kind, target
            if events:
                return "unknown", ""
            if scope == module:
                break
            scope = scope.rsplit(".", 1)[0]
        return None

    def unresolved_binding_symbol(call: ast.Call, owner: str) -> str:
        root: ast.AST = call.func
        while isinstance(root, ast.Attribute):
            root = root.value
        assert isinstance(root, ast.Name)
        candidate = f"{module}.{root.id}"
        if (
            candidate not in function_by_symbol
            and candidate not in class_by_symbol
            and candidate not in graph
        ):
            return candidate
        return f"@unresolved-binding:{owner}:{root.id}"

    def local_callee(
        call: ast.Call,
        owner: str,
        binding_context: tuple[str, int] = ("runtime", 0),
    ) -> str | None:
        binding = active_name_binding(call, owner, binding_context)
        if binding is not None and binding[0] != "local":
            return None
        base = super_callee(call, owner)
        if base is not None:
            initializer = graph.get(base, ())
            if len(initializer) == 1 and initializer[0] in function_by_symbol:
                return initializer[0]
        symbol = binding[1] if binding is not None else name(call.func, owner)
        constructor = local_constructor(symbol)
        if constructor is not None:
            return constructor
        if symbol in function_by_symbol:
            return symbol
        if isinstance(call.func, ast.Name) and binding is None:
            return local_by_name.get(call.func.id)
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
        ):
            parent = owner.rsplit(".", 1)[0]
            candidate = f"{parent}.{call.func.attr}"
            if candidate in function_by_symbol:
                return candidate
            owner_node = function_by_symbol.get(owner)
            if owner_node is not None and call.func.value.id in {
                argument.arg
                for argument in (
                    *owner_node.args.posonlyargs,
                    *owner_node.args.args,
                    *owner_node.args.kwonlyargs,
                )
            }:
                return None
            suffix = f".{call.func.value.id}.{call.func.attr}"
            candidates = sorted(
                symbol for symbol in function_by_symbol if symbol.endswith(suffix)
            )
            if len(candidates) == 1:
                return candidates[0]
        return None

    def source_node(row: Mapping[str, Any]) -> ast.AST | None:
        span = row.get("source_span")
        if not isinstance(span, Mapping):
            return None
        expected = (
            span.get("start_line"),
            span.get("start_col"),
            span.get("end_line"),
            span.get("end_col"),
        )
        matches = [
            node
            for node in ast.walk(tree)
            if not isinstance(node, ast.stmt)
            and (
                getattr(node, "lineno", None),
                getattr(node, "col_offset", None),
                getattr(node, "end_lineno", None),
                getattr(node, "end_col_offset", None),
            )
            == expected
        ]
        if len(matches) != 1:
            _fail("candidate census source span does not select one AST node")
        return matches[0]

    def row_values(node: ast.AST) -> tuple[ast.AST, ...]:
        if not isinstance(node, ast.Call):
            return (node,)
        receiver = (
            (node.func.value,) if isinstance(node.func, ast.Attribute) else ()
        )
        return (
            *receiver,
            *node.args,
            *(keyword.value for keyword in node.keywords),
        )

    scoped_by_owner: dict[str, list[ast.AST]] = {}
    tainted_by_owner: dict[str, set[str]] = {owner: set() for owner, _ in functions}
    forced_call_occurrences_by_owner: dict[str, set[int]] = {
        owner: set() for owner, _ in functions
    }
    force_all_calls_by_owner: set[str] = set()
    exact_rows: list[tuple[Mapping[str, Any], str, ast.AST]] = []
    class_decorator_rows: list[tuple[Mapping[str, Any], ast.AST, ast.Call]] = []
    context_rows: list[tuple[str, str, set[str]]] = []
    terminal_symbols: set[str] = generated_dataclasses | plain_exceptions | {
        base
        for base in class_base.values()
        if base is not None and base in available_external_imports
    } | {
        target
        for children in graph.values()
        for target in children
        if target in available_external_imports
        and (root := target.split(".", 1)[0]) not in workspace_module_roots
        and not (workspace_root / f"{root}.py").exists()
        and not (workspace_root / root / "__init__.py").exists()
    }
    for owner, node in functions:
        scoped_nodes: list[ast.AST] = []
        pending = list(node.body)
        while pending:
            child = pending.pop()
            scoped_nodes.append(child)
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                pending.extend(ast.iter_child_nodes(child))
        scoped_by_owner[owner] = scoped_nodes
        inherited_imports = imports_by_owner.get(owner.rsplit(".", 1)[0], imports)
        local_binding_counts = _module_binding_counts(
            ast.Module(body=list(node.body), type_ignores=[])
        )
        local_import_targets: dict[str, set[str]] = {}
        for child in scoped_nodes:
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for local, target in imported_names(child).items():
                    local_import_targets.setdefault(local, set()).add(target)
        local_imports = {
            local: target
            for local, target in inherited_imports.items()
            if local not in local_binding_counts
        }
        local_imports.update(
            {
                local: next(iter(targets))
                for local, targets in local_import_targets.items()
                if len(targets) == 1 and local_binding_counts.get(local) == 1
            }
        )
        imports_by_owner[owner] = local_imports
        argument_names = {
            argument.arg
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
                *((node.args.vararg,) if node.args.vararg is not None else ()),
                *((node.args.kwarg,) if node.args.kwarg is not None else ()),
            )
        }
        for argument_name in argument_names:
            local_imports.pop(argument_name, None)
        rebound_by_owner[owner] = (
            set(local_binding_counts) | argument_names
        ) - set(local_imports)
        if owner in authority_symbols:
            tainted_by_owner[owner].update(
                argument.arg
                for argument in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
                if argument.arg not in {"self", "cls"}
            )
            if node.args.vararg is not None:
                tainted_by_owner[owner].add(node.args.vararg.arg)
            if node.args.kwarg is not None:
                tainted_by_owner[owner].add(node.args.kwarg.arg)
    for row in consumer_rows:
        owner = row.get("public_entry_route")
        consumer_id = row.get("consumer_id")
        node = source_node(row)
        enclosing_decorators = [
            (class_owner, decorator)
            for class_owner, decorator, descendants in class_decorators
            if node is not None and id(node) in descendants
        ]
        if enclosing_decorators or (
            isinstance(owner, str)
            and owner in class_by_symbol
            and isinstance(consumer_id, str)
        ):
            if (
                len(enclosing_decorators) == 1
                and enclosing_decorators[0][0] == owner
                and node is not None
            ):
                class_decorator_rows.append(
                    (row, node, enclosing_decorators[0][1])
                )
            else:
                if isinstance(consumer_id, str):
                    graph[f"@consumer:{consumer_id}"] = [
                        f"@unresolved-class-decorator:{consumer_id}"
                    ]
            continue
        if isinstance(owner, str) and owner not in function_by_symbol:
            owner = local_constructor(owner) or owner
        if not isinstance(owner, str) or owner not in function_by_symbol:
            continue
        if node is None:
            function = function_by_symbol[owner]
            if row.get("trace_all_calls") is True:
                force_all_calls_by_owner.add(owner)
                tainted_by_owner[owner].update(
                    argument.arg
                    for argument in (
                        *function.args.posonlyargs,
                        *function.args.args,
                        *function.args.kwonlyargs,
                    )
                )
                continue
            context_symbol = row.get("context_symbol")
            tainted_formals = row.get("tainted_formals")
            if context_symbol is not None or tainted_formals is not None:
                formals = {
                    argument.arg
                    for argument in (
                        *function.args.posonlyargs,
                        *function.args.args,
                        *function.args.kwonlyargs,
                        *((function.args.vararg,) if function.args.vararg is not None else ()),
                        *((function.args.kwarg,) if function.args.kwarg is not None else ()),
                    )
                }
                if (
                    not isinstance(context_symbol, str)
                    or not context_symbol
                    or not isinstance(tainted_formals, list)
                    or not tainted_formals
                    or any(
                        not isinstance(formal, str) or formal not in formals
                        for formal in tainted_formals
                    )
                ):
                    _fail("candidate consumer call context is malformed")
                context_rows.append((context_symbol, owner, set(tainted_formals)))
                continue
            tainted_by_owner[owner].update(
                argument.arg
                for argument in (
                    *function.args.posonlyargs,
                    *function.args.args,
                    *function.args.kwonlyargs,
                )
                if argument.arg not in {"self", "cls"}
            )
            continue
        exact_rows.append((row, owner, node))
        for value in row_values(node):
            tainted_by_owner[owner].update(
                name_node.id
                for name_node in ast.walk(value)
                if isinstance(name_node, ast.Name)
                and name_node.id not in imports_by_owner[owner]
            )
        if row.get("match_kind") == "CONFIGURATION_CONSTRUCTION":
            if not isinstance(node, ast.Call):
                _fail("candidate construction census row is not a call")
            if (
                node.lineno,
                node.col_offset,
                node.end_lineno,
                node.end_col_offset,
            ) in current_construction_spans:
                forced_call_occurrences_by_owner[owner].add(id(node))

    def qualified_globals(owner: str) -> dict[str, str]:
        function = function_by_symbol[owner]
        explicit_globals = {
            name
            for child in scoped_by_owner[owner]
            if isinstance(child, ast.Global)
            for name in child.names
        }
        local_names = {
            argument.arg
            for argument in (
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            )
        } | {
            child.id
            for child in scoped_by_owner[owner]
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
        } - explicit_globals
        return {
            local: f"{module}.{local}"
            for local in module_rebounds | explicit_globals
            if local not in local_names
        }

    def call_tainted_formals(
        call: ast.Call,
        callee_node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        bound: bool,
        relevant: Any,
    ) -> set[str]:
        positional = [*callee_node.args.posonlyargs, *callee_node.args.args]
        if bound and positional:
            positional = positional[1:]
        result: set[str] = set()
        position = 0
        position_ambiguous = False
        for value in call.args:
            if isinstance(value, ast.Starred):
                if relevant(value.value):
                    result.update(argument.arg for argument in positional[position:])
                    if callee_node.args.vararg is not None:
                        result.add(callee_node.args.vararg.arg)
                position_ambiguous = True
                continue
            if relevant(value):
                if position_ambiguous:
                    result.update(argument.arg for argument in positional[position:])
                    if callee_node.args.vararg is not None:
                        result.add(callee_node.args.vararg.arg)
                elif position < len(positional):
                    result.add(positional[position].arg)
                elif callee_node.args.vararg is not None:
                    result.add(callee_node.args.vararg.arg)
            position += 1
        keyword_formals = {
            argument.arg
            for argument in (*callee_node.args.args, *callee_node.args.kwonlyargs)
        }
        for keyword in call.keywords:
            if not relevant(keyword.value):
                continue
            if keyword.arg is None:
                result.update(argument.arg for argument in positional)
                result.update(argument.arg for argument in callee_node.args.kwonlyargs)
                if callee_node.args.vararg is not None:
                    result.add(callee_node.args.vararg.arg)
                if callee_node.args.kwarg is not None:
                    result.add(callee_node.args.kwarg.arg)
            elif keyword.arg in keyword_formals:
                result.add(keyword.arg)
            elif callee_node.args.kwarg is not None:
                result.add(callee_node.args.kwarg.arg)
        return result

    def flow_binding(child: ast.AST) -> tuple[ast.AST | None, Sequence[ast.AST]]:
        if isinstance(child, ast.Assign):
            return child.value, child.targets
        if isinstance(child, (ast.AnnAssign, ast.NamedExpr)):
            return child.value, (child.target,)
        if isinstance(child, (ast.For, ast.AsyncFor)):
            return child.iter, (child.target,)
        return None, ()

    def returns_carrier(
        callee: str | ast.FunctionDef | ast.AsyncFunctionDef,
        seeds: set[str],
    ) -> bool:
        aliases = set(seeds)
        if isinstance(callee, str):
            scoped_nodes = scoped_by_owner[callee]
        else:
            scoped_nodes = []
            pending = list(callee.body)
            while pending:
                child = pending.pop()
                scoped_nodes.append(child)
                if not isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
                ):
                    pending.extend(ast.iter_child_nodes(child))

        def carrier_expression(value: ast.AST | None) -> bool:
            if isinstance(value, ast.Name):
                return value.id in aliases
            if isinstance(value, ast.Attribute):
                return (
                    _is_configuration_name(value.attr)
                    and carrier_expression(value.value)
                )
            if isinstance(value, ast.Subscript):
                return carrier_expression(value.value)
            if isinstance(value, ast.IfExp):
                return carrier_expression(value.body) or carrier_expression(value.orelse)
            if isinstance(value, ast.BoolOp):
                return any(carrier_expression(item) for item in value.values)
            if isinstance(value, (ast.List, ast.Set, ast.Tuple)):
                return any(carrier_expression(item) for item in value.elts)
            if isinstance(value, ast.Dict):
                return any(
                    carrier_expression(item)
                    for item in (*value.keys, *value.values)
                )
            if isinstance(value, (ast.Starred, ast.NamedExpr)):
                return carrier_expression(value.value)
            if isinstance(value, ast.Call):
                return any(
                    carrier_expression(item)
                    for item in (
                        *((value.func.value,) if isinstance(value.func, ast.Attribute) else ()),
                        *value.args,
                        *(keyword.value for keyword in value.keywords),
                    )
                )
            return False

        changed = True
        while changed:
            changed = False
            for child in scoped_nodes:
                value, targets = flow_binding(child)
                if not carrier_expression(value):
                    continue
                for target in targets:
                    for name_node in ast.walk(target):
                        if isinstance(name_node, ast.Name) and name_node.id not in aliases:
                            aliases.add(name_node.id)
                            changed = True
        return any(
            isinstance(child, ast.Return)
            and carrier_expression(child.value)
            for child in scoped_nodes
        )

    def is_bound_call(call: ast.Call, callee: str, owner: str) -> bool:
        callee_node = function_by_symbol[callee]
        decorators = {
            decorator.id
            for decorator in callee_node.decorator_list
            if isinstance(decorator, ast.Name)
        }
        invoked_on_class = (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == callee.rsplit(".", 2)[-2]
        )
        return (
            "classmethod" in decorators
            or callee.endswith(".__init__")
            and local_constructor(name(call.func, owner)) == callee
            or "staticmethod" not in decorators
            and isinstance(call.func, ast.Attribute)
            and not invoked_on_class
        )

    def call_symbol(
        call: ast.Call,
        owner: str,
        binding_context: tuple[str, int] = ("runtime", 0),
    ) -> str:
        binding = active_name_binding(call, owner, binding_context)
        if binding is not None and binding[0] == "unknown":
            return unresolved_binding_symbol(call, owner)
        if binding is not None and binding[0] == "import":
            attributes: list[str] = []
            value = call.func
            while isinstance(value, ast.Attribute):
                attributes.append(value.attr)
                value = value.value
            return ".".join((binding[1], *reversed(attributes)))
        target = (
            super_callee(call, owner)
            or (binding[1] if binding is not None else name(call.func, owner))
        )
        local = local_callee(call, owner, binding_context)
        if local is not None:
            target = local
        return target

    def workspace_return_carrier(
        call: ast.Call,
        owner: str,
        relevant: Any,
        binding_context: tuple[str, int] = ("runtime", 0),
    ) -> bool | None:
        if local_callee(call, owner, binding_context) is not None:
            return None
        context = workspace_function_nodes.get(
            call_symbol(call, owner, binding_context)
        )
        if context is None or context[1] is None:
            return None
        _, callee_node, bound, _ = context
        return returns_carrier(
            callee_node,
            call_tainted_formals(
                call, callee_node, bound=bound, relevant=relevant
            ),
        )

    def has_imported_receiver(call: ast.Call, owner: str) -> bool:
        if not isinstance(call.func, ast.Attribute):
            return False
        root: ast.AST = call.func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        return (
            isinstance(root, ast.Name)
            and root.id in imports_by_owner[owner]
        )

    stable_external_receiver_scopes: dict[tuple[str, str], bool] = {}

    def has_verified_external_receiver(call: ast.Call, owner: str) -> bool:
        if not isinstance(call.func, ast.Attribute):
            return False
        root: ast.AST = call.func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if not (
            isinstance(root, ast.Name)
            and root.id in verified_external_receivers
            and root.id not in rebound_by_owner[owner]
        ):
            return False
        key = (owner, root.id)
        if key not in stable_external_receiver_scopes:
            stable_external_receiver_scopes[key] = not _has_module_object_mutation(
                ast.Module(
                    body=list(function_by_symbol[owner].body),
                    type_ignores=[],
                ),
                {root.id},
                reject_argument_escape=True,
            )
        return stable_external_receiver_scopes[key]

    context_requests: dict[str, tuple[str, tuple[str, ...]]] = {}
    binding_scopes = (
        tree,
        *(
            ast.Module(body=list(function.body), type_ignores=[])
            for _, function in functions
        ),
        *(
            ast.Module(body=list(class_node.body), type_ignores=[])
            for _, class_node in classes
        ),
    )

    def stable_plain_workspace_class(call: ast.Call, owner: str, target: str) -> bool:
        if target in generated_dataclasses or target in plain_exceptions:
            return True
        return (
            isinstance(call.func, ast.Name)
            and imports_by_owner[owner].get(call.func.id) == target
            and not _has_module_object_mutation(
                tree, {call.func.id}, reject_argument_escape=True
            )
        )

    def stable_generated_dataclass_hook_call(
        call: ast.Call,
        owner: str,
        target: str,
        *,
        stable_class: bool,
    ) -> bool:
        if not (
            stable_class
            and isinstance(call.func, ast.Name)
            and (
                target in class_by_symbol
                and name(call.func, owner) == target
                or imports_by_owner[owner].get(call.func.id) == target
            )
        ):
            return False
        def names_target(imported: str) -> bool:
            return imported == target or target.startswith(f"{imported}.")

        aliases = {
            local
            for visible_imports in (imports, *imports_by_owner.values())
            for local, imported in visible_imports.items()
            if names_target(imported)
        } | {
            local
            for local, targets in import_targets.items()
            if any(names_target(imported) for imported in targets)
        } | {
            local
            for events in binding_events_by_owner.values()
            for local, local_events in events.items()
            if any(
                event[2] == "import" and names_target(event[3])
                for event in local_events
            )
        } | {call.func.id}
        exact_aliases = {
            local
            for visible_imports in (imports, *imports_by_owner.values())
            for local, imported in visible_imports.items()
            if imported == target
        } | {
            local
            for local, targets in import_targets.items()
            if target in targets
        } | {
            local
            for events in binding_events_by_owner.values()
            for local, local_events in events.items()
            if any(
                event[2] == "import" and event[3] == target
                for event in local_events
            )
        } | {call.func.id}
        allowed_argument_calls = _allowed_native_isinstance_calls(
            tree, exact_aliases
        )
        return not any(
            _module_binding_counts(scope).get(alias, 0) > 1
            for scope in binding_scopes
            for alias in aliases
        ) and not any(
            _has_module_object_mutation(
                scope,
                aliases,
                reject_argument_escape=True,
                allowed_argument_calls=allowed_argument_calls,
            )
            for scope in binding_scopes
        )

    def routed_call_symbol(
        call: ast.Call,
        owner: str,
        relevant: Any,
        binding_context: tuple[str, int] = ("runtime", 0),
    ) -> str:
        target = call_symbol(call, owner, binding_context)
        context = workspace_function_nodes.get(target)
        if context is None:
            return target
        binding = active_name_binding(call, owner, binding_context)
        if binding is not None and binding[0] == "unknown":
            return target
        resolved_target, callee_node, bound, stable_class = context
        if callee_node is None:
            plain_workspace_class = resolved_target in {
                _PLAIN_BUILTIN_EXCEPTION,
                "dataclasses.dataclass",
            }
            if plain_workspace_class and stable_plain_workspace_class(
                call, owner, target
            ):
                terminal_symbols.add(target)
                return target
            if not plain_workspace_class and resolved_target in available_external_imports:
                return resolved_target if not bound else target
            context_symbol = f"@unresolved-context:{target}"
            context_requests[context_symbol] = (target, ())
            return context_symbol
        generated_post_init = (
            bound
            and stable_class
            and callee_node.name == "__post_init__"
            and resolved_target.endswith(".__post_init__")
        )
        if generated_post_init:
            if not stable_generated_dataclass_hook_call(
                call, owner, target, stable_class=stable_class
            ):
                context_symbol = f"@unresolved-context:{target}"
                context_requests[context_symbol] = (target, ())
                return context_symbol
            formals = ("self",)
        else:
            formals = tuple(
                sorted(
                    call_tainted_formals(
                        call, callee_node, bound=bound, relevant=relevant
                    )
                )
            )
        if target in authority_symbols:
            return target
        if not formals:
            return target
        context_symbol = f"@context:{target}:{','.join(formals)}"
        context_requests[context_symbol] = (resolved_target, formals)
        return context_symbol

    changed = True
    while changed:
        changed = False
        for owner, node in functions:
            tainted = tainted_by_owner[owner]
            scoped_nodes = scoped_by_owner[owner]

            def relevant(value: ast.AST) -> bool:
                if isinstance(value, ast.Name):
                    return value.id in tainted
                if isinstance(value, (ast.Starred, ast.NamedExpr)):
                    return relevant(value.value)
                if isinstance(value, (ast.Attribute, ast.Subscript)):
                    return relevant(value.value)
                if isinstance(value, (ast.IfExp, ast.BoolOp, ast.Call)):
                    return any(relevant(child) for child in ast.iter_child_nodes(value))
                return False

            for child in scoped_nodes:
                value, targets = flow_binding(child)
                carries_configuration = value is not None and relevant(value)
                if isinstance(value, ast.Call):
                    carries_configuration = call_symbol(value, owner) in authority_symbols
                    callee = local_callee(value, owner)
                    if callee is not None:
                        callee_tainted = tainted_by_owner[callee]
                        carries_configuration = returns_carrier(
                            callee, callee_tainted
                        )
                    elif (
                        workspace_result := workspace_return_carrier(
                            value, owner, relevant
                        )
                    ) is not None:
                        carries_configuration = workspace_result
                if carries_configuration:
                    for target in targets:
                        for name_node in ast.walk(target):
                            if isinstance(name_node, ast.Name) and name_node.id not in tainted:
                                tainted.add(name_node.id)
                                changed = True
            for child in scoped_nodes:
                if not isinstance(child, ast.Call):
                    continue
                callee = local_callee(child, owner)
                if callee is None:
                    continue
                callee_node = function_by_symbol[callee]
                callee_tainted = tainted_by_owner[callee]
                newly_tainted = call_tainted_formals(
                    child,
                    callee_node,
                    bound=is_bound_call(child, callee, owner),
                    relevant=relevant,
                )
                for argument_name in newly_tainted - callee_tainted:
                    callee_tainted.add(argument_name)
                    changed = True

    bound_builtin_container_constructors = {
        local
        for scope in binding_scopes
        for local in _module_binding_counts(scope)
        if local in {"dict", "set"}
    }
    builtins_module_aliases = {
        alias.asname or "builtins"
        for child in ast.walk(tree)
        if isinstance(child, ast.Import)
        for alias in child.names
        if alias.name == "builtins"
    }
    builtin_container_constructor_objects_stable = not any(
        _has_module_object_mutation(
            scope,
            builtins_module_aliases,
            reject_argument_escape=True,
        )
        for scope in binding_scopes
    )

    def has_stable_builtin_type_method_descriptor(
        call: ast.Call, owner: str
    ) -> bool:
        receiver = _builtin_type_method_descriptor_receiver(call)
        if (
            receiver is None
            or module_binding_counts.get(receiver, 0) != 0
            or not builtin_container_constructor_objects_stable
            or any(
                isinstance(node, ast.Global) and receiver in node.names
                for node in ast.walk(tree)
            )
        ):
            return False
        scope = owner
        while scope != module:
            if binding_events_by_owner.get(scope, {}).get(receiver):
                return False
            scope = scope.rsplit(".", 1)[0]
        return True

    def has_stable_generated_dataclass_field_setattr(
        call: ast.Call, owner: str
    ) -> bool:
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "__setattr__"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "object"
            and len(call.args) == 3
            and not call.keywords
            and isinstance(call.args[0], ast.Name)
            and isinstance(call.args[1], ast.Constant)
            and isinstance(call.args[1].value, str)
        ):
            return False
        class_symbol = owner.rsplit(".", 1)[0]
        context = workspace_function_nodes.get(class_symbol)
        class_node = class_by_symbol.get(class_symbol)
        custom_initializer = (
            context is not None
            and context[0] == class_symbol
            and context[1] is not None
            and context[1].name == "__init__"
            and class_node is not None
            and _is_plain_generated_dataclass(
                class_node,
                literal_dataclass_name,
                trace_frozen_custom_init=True,
            )
            and all(
                len(targets) == 1
                and module_binding_counts.get(alias) == 1
                for alias, targets in import_targets.items()
                if targets & {"dataclasses", "dataclasses.dataclass"}
            )
            and not any(
                _has_module_object_mutation(
                    scope,
                    {
                        alias
                        for alias, targets in import_targets.items()
                        if targets & {"dataclasses", "dataclasses.dataclass"}
                    },
                    reject_argument_escape=True,
                )
                for scope in binding_scopes
            )
        )
        if not (
            context is not None
            and context[1] is not None
            and (
                context[0] == owner
                and context[1].name == "__post_init__"
                or custom_initializer
            )
            and context[2]
            and context[3]
            and class_node is not None
            and class_symbol.rsplit(".", 1)[0] == module
            and call.args[0].id == "self"
            and _module_binding_counts(
                ast.Module(body=list(context[1].body), type_ignores=[])
            ).get("self", 0)
            == 0
            and call.args[1].value
            in {
                child.target.id
                for child in class_node.body
                if isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
                and child.simple == 1
            }
            and _module_binding_counts(
                ast.Module(body=list(class_node.body), type_ignores=[])
            ).get("object", 0)
            == 0
            and module_binding_counts.get("object", 0) == 0
            and builtin_container_constructor_objects_stable
            and not any(
                isinstance(node, ast.Global) and "object" in node.names
                for node in ast.walk(tree)
            )
        ):
            return False
        scope = owner
        while scope != module:
            if binding_events_by_owner.get(scope, {}).get("object"):
                return False
            scope = scope.rsplit(".", 1)[0]
        return True

    def has_stable_local_builtin_container_receiver(
        call: ast.Call, owner: str
    ) -> bool:
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr in {"append", "extend", "update"}
            and isinstance(call.func.value, ast.Name)
        ):
            return False

        def supports_operation(value: ast.AST) -> bool:
            if isinstance(value, ast.List):
                kind = "list"
            elif isinstance(value, ast.Dict):
                kind = "dict"
            elif isinstance(value, ast.Set):
                kind = "set"
            elif (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in {"dict", "set"}
                and value.func.id not in bound_builtin_container_constructors
                and active_name_binding(value, owner) is None
                and builtin_container_constructor_objects_stable
            ):
                kind = value.func.id
            else:
                return False
            return call.func.attr in (
                {"append", "extend"} if kind == "list" else {"update"}
            )

        receiver = call.func.value.id
        function = function_by_symbol[owner]
        formals = {
            argument.arg
            for argument in (
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
                *((function.args.vararg,) if function.args.vararg is not None else ()),
                *((function.args.kwarg,) if function.args.kwarg is not None else ()),
            )
        }
        if receiver in formals:
            return False
        if _module_binding_counts(
            ast.Module(body=list(function.body), type_ignores=[])
        ).get(receiver) != 1:
            return False
        definitions = [
            statement
            for statement in function.body
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and statement.targets[0].id == receiver
                and supports_operation(statement.value)
                or isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == receiver
                and statement.value is not None
                and supports_operation(statement.value)
            )
            and (statement.lineno, statement.col_offset)
            < (call.lineno, call.col_offset)
        ]
        if len(definitions) != 1:
            return False
        definition = definitions[0]

        repeated_scopes = [
            {id(child) for child in ast.walk(scope)}
            for scope in ast.walk(function)
            if isinstance(scope, (ast.For, ast.AsyncFor, ast.While))
            and any(child is call for child in ast.walk(scope))
        ]

        def may_run_before_occurrence(node: ast.AST) -> bool:
            return (
                (definition.lineno, definition.col_offset)
                < (getattr(node, "lineno", call.lineno), getattr(node, "col_offset", 0))
                < (call.lineno, call.col_offset)
                or any(id(node) in scope for scope in repeated_scopes)
            )

        def contains_receiver(value: ast.AST | None) -> bool:
            return value is not None and any(
                isinstance(child, ast.Name) and child.id == receiver
                for child in ast.walk(value)
            )

        for node in scoped_by_owner[owner]:
            if not may_run_before_occurrence(node):
                continue
            if isinstance(node, (ast.Global, ast.Nonlocal)) and receiver in node.names:
                return False
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                if contains_receiver(node):
                    return False
                continue
            if isinstance(node, ast.Name) and node.id == receiver and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                if not any(node is child for child in ast.walk(definition)):
                    return False
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                if node is not definition and contains_receiver(node.value):
                    return False
            if isinstance(node, ast.Call) and node is not call and any(
                contains_receiver(value)
                for value in (
                    *node.args,
                    *(keyword.value for keyword in node.keywords),
                )
            ):
                return False
            if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)) and contains_receiver(
                node.value
            ):
                return False
        return True

    def has_stable_module_dict_literal_receiver(
        call: ast.Call, owner: str
    ) -> bool:
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr in {"get", "items"}
            and isinstance(call.func.value, ast.Name)
        ):
            return False
        receiver = call.func.value.id
        scope = owner
        while scope != module:
            if binding_events_by_owner.get(scope, {}).get(receiver):
                return False
            scope = scope.rsplit(".", 1)[0]
        if (
            module_binding_counts.get(receiver) != 1
            or receiver in rebound_by_owner[owner]
            or any(
                isinstance(node, ast.Global) and receiver in node.names
                for node in ast.walk(tree)
            )
        ):
            return False
        owner_node = function_by_symbol[owner]
        definitions = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == receiver
            and isinstance(node.value, ast.Dict)
            and (node.lineno, node.col_offset)
            < (owner_node.lineno, owner_node.col_offset)
            < (call.lineno, call.col_offset)
        ]
        return len(definitions) == 1

    def has_plain_initializer_attribute(owner: str, attribute: str) -> bool:
        class_symbol = owner.rsplit(".", 1)[0]
        class_node = class_by_symbol.get(class_symbol)
        if class_node is None or class_node.decorator_list or class_node.keywords:
            return False
        class_bindings = _module_binding_counts(
            ast.Module(body=list(class_node.body), type_ignores=[])
        )
        intercepted = {
            attribute,
            "__getattr__",
            "__getattribute__",
            "__setattr__",
        }
        if intercepted & class_bindings.keys():
            return False
        if any(
            reassigned == f"{class_symbol}.{name}"
            for reassigned in reassigned_attributes
            for name in intercepted
        ):
            return False
        class_name = class_symbol.rsplit(".", 1)[-1]
        if _has_module_object_mutation(
            tree, {class_name}, reject_argument_escape=True
        ):
            return False
        for base in class_node.bases:
            root = base
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id == "object":
                continue
            if not (
                isinstance(root, ast.Name)
                and (imported := imports.get(root.id)) is not None
                and imported.split(".", 1)[0] not in workspace_module_roots
                and name(base) not in reassigned_attributes
                and not _has_module_object_mutation(
                    tree,
                    {root.id},
                    reject_argument_escape=False,
                )
            ):
                return False
        return True

    def has_stable_initializer_attribute_receiver(
        call: ast.Call, owner: str
    ) -> bool:
        if not (
            owner.endswith(".__init__")
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Attribute)
            and isinstance(call.func.value.value, ast.Name)
        ):
            return False
        function = function_by_symbol[owner]
        positional = (*function.args.posonlyargs, *function.args.args)
        if not positional or call.func.value.value.id != positional[0].arg:
            return False
        receiver = call.func.value
        owner_name = positional[0].arg
        if not has_plain_initializer_attribute(owner, receiver.attr):
            return False

        def contains_owner(node: ast.AST | None) -> bool:
            return node is not None and any(
                isinstance(child, ast.Name) and child.id == owner_name
                for child in ast.walk(node)
            )

        initializer_definitions: dict[
            str, list[ast.Assign | ast.AnnAssign]
        ] = {}
        for statement in function.body:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target, value = statement.targets[0], statement.value
            elif isinstance(statement, ast.AnnAssign):
                target, value = statement.target, statement.value
            else:
                continue
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == owner_name
                and isinstance(value, ast.Call)
            ):
                initializer_definitions.setdefault(target.attr, []).append(statement)
        definitions = initializer_definitions.get(receiver.attr, [])
        if len(definitions) != 1:
            return False
        definition = definitions[0]
        value = definition.value
        if not (
            isinstance(value, ast.Call)
            and (definition.lineno, definition.col_offset)
            < (call.lineno, call.col_offset)
            and (factory := verified_external_factory(value)) is not None
            and call_symbol(value, owner) == factory
        ):
            return False
        verified_initializer_attributes = {
            attribute
            for attribute, candidates in initializer_definitions.items()
            if len(candidates) == 1
            and has_plain_initializer_attribute(owner, attribute)
            and isinstance(candidates[0].value, ast.Call)
            and (
                candidate_factory := verified_external_factory(candidates[0].value)
            )
            is not None
            and call_symbol(candidates[0].value, owner) == candidate_factory
        }

        repeated_scopes = [
            {id(child) for child in ast.walk(scope)}
            for scope in ast.walk(function)
            if isinstance(scope, (ast.For, ast.AsyncFor, ast.While))
            and any(child is call for child in ast.walk(scope))
        ]

        def may_run_before_occurrence(node: ast.AST) -> bool:
            return (
                (definition.lineno, definition.col_offset)
                < (node.lineno, node.col_offset)
                < (call.lineno, call.col_offset)
                or any(id(node) in scope for scope in repeated_scopes)
            )

        def mutates_owner_indirectly(node: ast.AST) -> bool:
            return contains_owner(node) and not (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == owner_name
                and node.attr != receiver.attr
            )

        for node in scoped_by_owner[owner]:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                if may_run_before_occurrence(node) and contains_owner(node):
                    return False
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                if (
                    node is not definition
                    and may_run_before_occurrence(node)
                    and (
                        any(mutates_owner_indirectly(target) for target in targets)
                        or contains_owner(node.value)
                    )
                ):
                    return False
            elif isinstance(node, (ast.AugAssign, ast.Delete)):
                targets = node.targets if isinstance(node, ast.Delete) else (node.target,)
                if may_run_before_occurrence(node) and any(
                    mutates_owner_indirectly(target) for target in targets
                ):
                    return False
            elif isinstance(node, ast.Call) and node is not call:
                call_receiver = (
                    node.func.value if isinstance(node.func, ast.Attribute) else None
                )
                distinct_verified_receiver = (
                    isinstance(call_receiver, ast.Attribute)
                    and isinstance(call_receiver.value, ast.Name)
                    and call_receiver.value.id == owner_name
                    and call_receiver.attr != receiver.attr
                    and call_receiver.attr in verified_initializer_attributes
                    and (
                        initializer_definitions[call_receiver.attr][0].lineno,
                        initializer_definitions[call_receiver.attr][0].col_offset,
                    )
                    < (node.lineno, node.col_offset)
                )
                if (
                    may_run_before_occurrence(node)
                    and (
                        contains_owner(call_receiver)
                        and not distinct_verified_receiver
                        or isinstance(call_receiver, ast.Call)
                        and isinstance(call_receiver.func, ast.Name)
                        and call_receiver.func.id == "super"
                        or any(
                            contains_owner(argument)
                            for argument in (
                                *node.args,
                                *(keyword.value for keyword in node.keywords),
                            )
                        )
                    )
                ):
                    return False
            elif (
                isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom))
                and may_run_before_occurrence(node)
                and contains_owner(node.value)
            ):
                return False
        return True

    def occurrence_terminal_symbol(
        call: ast.Call,
        owner: str,
        relevant: Any,
        target: str,
        *,
        force_receiver_tainted: bool = False,
        allow_tainted_receiver: bool = True,
    ) -> tuple[str, bool]:
        arguments = (*call.args, *(item.value for item in call.keywords))
        builtin_descriptor = has_stable_builtin_type_method_descriptor(call, owner)
        builtin_literal_descriptor = (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Constant)
            and inspect.ismethoddescriptor(
                vars(type(call.func.value.value)).get(call.func.attr)
            )
        )
        bypass_receiver_tainted = (
            force_receiver_tainted
            or _configuration_receiver_tainted(call, relevant)
        )
        receiver_tainted = force_receiver_tainted or (
            isinstance(call.func, ast.Attribute)
            and relevant(call.func.value)
        ) or (
            builtin_descriptor
            and bool(call.args)
            and relevant(call.args[0])
        )
        tolerant = not target.startswith("@") and _is_tolerant_configuration_call(
            target,
            arguments,
            receiver_tainted=bypass_receiver_tainted,
            call_tainted=bypass_receiver_tainted
            or any(relevant(argument) for argument in arguments),
        )
        verified_receiver = has_verified_external_receiver(call, owner)
        stable_receiver = (
            builtin_descriptor
            or builtin_literal_descriptor
            or has_stable_generated_dataclass_field_setattr(call, owner)
            or has_stable_local_builtin_container_receiver(call, owner)
            or has_stable_module_dict_literal_receiver(call, owner)
            or has_stable_initializer_attribute_receiver(call, owner)
        )
        if (
            isinstance(call.func, ast.Attribute)
            and (
                verified_receiver
                or stable_receiver
                or allow_tainted_receiver and receiver_tainted
            )
            and not tolerant
            and not has_imported_receiver(call, owner)
            and (
                verified_receiver
                or stable_receiver
                or not (
                    isinstance(call.func.value, ast.Name)
                    and call.func.value.id in module_rebounds
                )
            )
        ):
            target = f"@terminal:{owner}:{call.lineno}:{call.col_offset}:{target}"
            terminal_symbols.add(target)
        return target, tolerant

    def contextual_route(
        owner: str,
        seeds: set[str],
        binding_context: tuple[str, int] = ("runtime", 0),
        seen: frozenset[
            tuple[str, tuple[str, ...], tuple[str, int]]
        ] = frozenset(),
    ) -> tuple[set[str], set[str]]:
        context = (owner, tuple(sorted(seeds)), binding_context)
        if context in seen:
            return {owner}, set()
        tainted = set(seeds)

        def relevant(value: ast.AST | None) -> bool:
            if value is None:
                return False
            if isinstance(value, ast.Name):
                return value.id in tainted
            if isinstance(value, (ast.Attribute, ast.Subscript)):
                return relevant(value.value)
            return any(relevant(child) for child in ast.iter_child_nodes(value))

        def carrier_expression(value: ast.AST | None) -> bool:
            if isinstance(value, ast.Name):
                return value.id in tainted
            if isinstance(value, (ast.Attribute, ast.Subscript)):
                return carrier_expression(value.value)
            if isinstance(value, ast.BoolOp):
                return any(carrier_expression(item) for item in value.values)
            if isinstance(value, ast.IfExp):
                return carrier_expression(value.body) or carrier_expression(value.orelse)
            if not isinstance(value, ast.Call):
                return False
            if call_symbol(value, owner, binding_context) in authority_symbols:
                return True
            callee = local_callee(value, owner, binding_context)
            if callee is None:
                return workspace_return_carrier(
                    value, owner, carrier_expression, binding_context
                ) is True
            formals = call_tainted_formals(
                value,
                function_by_symbol[callee],
                bound=is_bound_call(value, callee, owner),
                relevant=carrier_expression,
            )
            return returns_carrier(callee, formals)

        changed = True
        while changed:
            changed = False
            for child in scoped_by_owner[owner]:
                value, targets = flow_binding(child)
                if not carrier_expression(value):
                    continue
                for target in targets:
                    for name_node in ast.walk(target):
                        if isinstance(name_node, ast.Name) and name_node.id not in tainted:
                            tainted.add(name_node.id)
                            changed = True

        leaves: set[str] = set()
        classes = set(
            detect_ast_bypasses(
                ast.get_source_segment(source, function_by_symbol[owner]) or "",
                _tainted_names=tuple(tainted),
                _qualified_names=qualified_globals(owner),
                _propagate_taint=False,
            )
        )
        for child in scoped_by_owner[owner]:
            if not isinstance(child, ast.Call):
                continue
            values = (
                *((child.func.value,) if isinstance(child.func, ast.Attribute) else ()),
                *child.args,
                *(keyword.value for keyword in child.keywords),
            )
            if not any(relevant(value) for value in values):
                continue
            target = call_symbol(child, owner, binding_context)
            if target in authority_symbols:
                leaves.add(target)
                continue
            callee = local_callee(child, owner, binding_context)
            if callee is None:
                target = routed_call_symbol(
                    child, owner, relevant, binding_context
                )
                target, tolerant = occurrence_terminal_symbol(
                    child, owner, relevant, target
                )
                leaves.add(target)
                if tolerant:
                    classes.add("TOLERANT_OR_COMPATIBILITY_LOADER")
                elif target in available_external_imports:
                    root = child.func
                    while isinstance(root, ast.Attribute):
                        root = root.value
                    visible_imports = imports_by_owner.get(owner, imports)
                    if isinstance(root, ast.Name) and root.id in visible_imports:
                        imported_target = visible_imports[root.id]
                        import_aliases = {
                            local
                            for local, imported in visible_imports.items()
                            if imported == imported_target
                        }
                        if (
                            target not in reassigned_attributes
                            and root.id not in rebound_by_owner[owner]
                            and root.id not in module_rebounds
                            and not _has_module_object_mutation(
                                tree,
                                import_aliases,
                                reject_argument_escape=True,
                            )
                            and not _has_module_object_mutation(
                                ast.Module(
                                    body=list(function_by_symbol[owner].body),
                                    type_ignores=[],
                                ),
                                import_aliases,
                                reject_argument_escape=True,
                            )
                        ):
                            terminal_symbols.add(target)
                continue
            formals = call_tainted_formals(
                child,
                function_by_symbol[callee],
                bound=is_bound_call(child, callee, owner),
                relevant=relevant,
            )
            nested_leaves, nested_classes = contextual_route(
                callee, formals, binding_context, seen | {context}
            )
            leaves.update(nested_leaves)
            classes.update(nested_classes)
        return leaves, classes

    for row, node, decorator in class_decorator_rows:
        consumer_id = row.get("consumer_id")
        if not isinstance(consumer_id, str):
            continue
        binding_context = ("source", decorator.lineno)
        consumer_symbol = f"@consumer:{consumer_id}"
        if not name(decorator.func):
            graph[consumer_symbol] = [
                f"@unresolved-class-decorator:{consumer_id}"
            ]
            continue
        seeds = {id(node)}
        if node is decorator:
            seeds.update(
                id(child)
                for value in row_values(decorator)
                for child in ast.walk(value)
                if isinstance(child, ast.expr)
            )

        def relevant(value: ast.AST | None) -> bool:
            return value is not None and (
                id(value) in seeds
                or any(relevant(child) for child in ast.iter_child_nodes(value))
            )

        relevant_calls = [
            child
            for child in ast.walk(decorator)
            if isinstance(child, ast.Call) and relevant(child)
        ]
        calls: set[str] = set()
        contextual_bypasses: set[str] = set()
        for child in relevant_calls:
            target = call_symbol(child, module, binding_context)
            if target in authority_symbols:
                calls.add(target)
                continue
            callee = local_callee(child, module, binding_context)
            if callee is None:
                calls.add(
                    routed_call_symbol(
                        child, module, relevant, binding_context
                    )
                    or f"@unresolved-class-decorator-call:{consumer_id}"
                )
                continue
            formals = call_tainted_formals(
                child,
                function_by_symbol[callee],
                bound=is_bound_call(child, callee, module),
                relevant=relevant,
            )
            nested_calls, nested_bypasses = contextual_route(
                callee, formals, binding_context
            )
            calls.update(nested_calls)
            contextual_bypasses.update(nested_bypasses)
        graph[consumer_symbol] = sorted(filter(None, calls))
        terminal_symbols.update(calls & available_external_imports)

        exact_bypasses: set[str] = set()
        for child in relevant_calls:
            operation = call_symbol(child, module, binding_context)
            if not operation and isinstance(child.func, ast.Name):
                operation = child.func.id
            arguments = (*child.args, *(item.value for item in child.keywords))
            receiver_tainted = (
                _configuration_receiver_tainted(child, relevant) or child is node
            )
            tainted_call = receiver_tainted or child is node or any(
                relevant(argument) for argument in arguments
            )
            if operation in {"os.getenv", "os.environ.get", "environ.get"}:
                exact_bypasses.add("AMBIENT_CONFIGURATION_READ")
            elif _is_legacy_configuration_symbol(operation) and tainted_call:
                exact_bypasses.add("LEGACY_CONFIGURATION_STATE_MUTATION")
            elif _is_tolerant_configuration_call(
                operation,
                arguments,
                receiver_tainted=receiver_tainted,
                call_tainted=tainted_call,
            ):
                exact_bypasses.add("TOLERANT_OR_COMPATIBILITY_LOADER")
        declared_bypasses = row.get("bypass_classes", ())
        classes = tuple(
            class_id
            for class_id in BYPASS_CLASSES
            if class_id in exact_bypasses
            or class_id in contextual_bypasses
            or class_id in module_bypasses
            or class_id in declared_bypasses
        )
        if classes:
            bypasses[consumer_symbol] = classes

    for context_symbol, owner, formals in context_rows:
        calls, classes = contextual_route(owner, formals)
        graph[context_symbol] = sorted(filter(None, calls))
        classes.update(module_bypasses)
        if classes:
            bypasses[context_symbol] = tuple(
                class_id for class_id in BYPASS_CLASSES if class_id in classes
            )

    for row, owner, node in exact_rows:
        consumer_id = row.get("consumer_id")
        if not isinstance(consumer_id, str):
            continue
        consumer_symbol = f"@consumer:{consumer_id}"
        origin_names = {
            name_node.id
            for value in row_values(node)
            for name_node in ast.walk(value)
            if isinstance(name_node, ast.Name)
            and name_node.id not in imports_by_owner[owner]
        }
        tainted: set[str] = set()
        unresolved_workspace_carrier_names: set[str] = set()

        def relevant(value: ast.AST | None) -> bool:
            if value is None:
                return False
            if value is node:
                return True
            if isinstance(value, ast.Name):
                return value.id in tainted
            if isinstance(value, (ast.Attribute, ast.Subscript)):
                return relevant(value.value)
            return any(relevant(child) for child in ast.iter_child_nodes(value))

        def carrier_expression(value: ast.AST | None) -> bool:
            if value is node or isinstance(value, ast.Name) and value.id in tainted:
                return True
            if isinstance(value, (ast.Attribute, ast.Subscript)):
                return carrier_expression(value.value)
            if isinstance(value, ast.IfExp):
                return carrier_expression(value.body) or carrier_expression(value.orelse)
            if isinstance(value, ast.BoolOp):
                return any(carrier_expression(item) for item in value.values)
            if not isinstance(value, ast.Call):
                return False
            if call_symbol(value, owner) in authority_symbols:
                return True
            callee = local_callee(value, owner)
            if callee is None:
                return workspace_return_carrier(
                    value, owner, carrier_expression
                ) is True
            formals = call_tainted_formals(
                value,
                function_by_symbol[callee],
                bound=is_bound_call(value, callee, owner),
                relevant=carrier_expression,
            )
            return returns_carrier(callee, formals)

        def unresolved_workspace_carrier_expression(
            value: ast.AST | None,
        ) -> bool:
            if isinstance(value, ast.Name):
                return value.id in unresolved_workspace_carrier_names
            if isinstance(value, (ast.Attribute, ast.Subscript)):
                return unresolved_workspace_carrier_expression(value.value)
            if isinstance(value, ast.IfExp):
                return unresolved_workspace_carrier_expression(
                    value.body
                ) or unresolved_workspace_carrier_expression(value.orelse)
            if isinstance(value, ast.BoolOp):
                return any(
                    unresolved_workspace_carrier_expression(item)
                    for item in value.values
                )
            if isinstance(value, (ast.List, ast.Set, ast.Tuple)):
                return any(
                    unresolved_workspace_carrier_expression(item)
                    for item in value.elts
                )
            if isinstance(value, ast.Dict):
                return any(
                    unresolved_workspace_carrier_expression(item)
                    for item in (*value.keys, *value.values)
                )
            if isinstance(value, (ast.Starred, ast.NamedExpr)):
                return unresolved_workspace_carrier_expression(value.value)
            if not isinstance(value, ast.Call):
                return False
            if call_symbol(value, owner) in authority_symbols:
                return False
            callee = local_callee(value, owner)
            if callee is None:
                return workspace_return_carrier(
                    value, owner, unresolved_workspace_carrier_expression
                ) is True
            formals = call_tainted_formals(
                value,
                function_by_symbol[callee],
                bound=is_bound_call(value, callee, owner),
                relevant=unresolved_workspace_carrier_expression,
            )
            return returns_carrier(callee, formals)

        def unresolved_workspace_carrier_value(
            value: ast.AST | None,
        ) -> bool:
            return unresolved_workspace_carrier_expression(value) or (
                isinstance(value, ast.Call)
                and call_symbol(value, owner) not in authority_symbols
                and workspace_return_carrier(
                    value, owner, carrier_expression
                ) is True
            )

        changed = True
        while changed:
            changed = False
            for child in scoped_by_owner[owner]:
                value, targets = flow_binding(child)
                unresolved_workspace_carrier = (
                    unresolved_workspace_carrier_value(value)
                )
                carries_configuration = (
                    carrier_expression(value) or unresolved_workspace_carrier
                )
                if not carries_configuration:
                    continue
                for target in targets:
                    for name_node in ast.walk(target):
                        if not isinstance(name_node, ast.Name):
                            continue
                        if name_node.id not in tainted:
                            tainted.add(name_node.id)
                            changed = True
                        if (
                            unresolved_workspace_carrier
                            and name_node.id not in unresolved_workspace_carrier_names
                        ):
                            unresolved_workspace_carrier_names.add(name_node.id)
                            changed = True

        relevant_calls = [
            child
            for child in scoped_by_owner[owner]
            if isinstance(child, ast.Call)
            and (
                child is node
                or any(
                    relevant(value)
                    for value in (
                        *((child.func.value,) if isinstance(child.func, ast.Attribute) else ()),
                        *child.args,
                        *(keyword.value for keyword in child.keywords),
                    )
                )
            )
        ]
        calls: set[str] = set()
        contextual_bypasses: set[str] = set()
        for child in relevant_calls:
            target = call_symbol(child, owner)
            if target in authority_symbols:
                calls.add(target)
                continue
            callee = local_callee(child, owner)
            if callee is None:
                target = routed_call_symbol(child, owner, relevant)
                target, tolerant = occurrence_terminal_symbol(
                    child,
                    owner,
                    relevant,
                    target,
                    force_receiver_tainted=child is node,
                )
                calls.add(target)
                if tolerant:
                    contextual_bypasses.add("TOLERANT_OR_COMPATIBILITY_LOADER")
                continue
            formals = call_tainted_formals(
                child,
                function_by_symbol[callee],
                bound=is_bound_call(child, callee, owner),
                relevant=relevant,
            )
            nested_calls, nested_bypasses = contextual_route(callee, formals)
            calls.update(nested_calls)
            contextual_bypasses.update(nested_bypasses)
        whole_carrier_origin = isinstance(node, ast.Name) or (
            isinstance(node, ast.Attribute)
            and _is_configuration_name(node.attr)
        )
        if whole_carrier_origin and any(
            isinstance(child, ast.Return)
            and unresolved_workspace_carrier_value(child.value)
            for child in scoped_by_owner[owner]
        ):
            calls.add(f"@unresolved-carrier-return:{consumer_id}")
        if owner in authority_symbols:
            calls = {owner}
        graph[consumer_symbol] = sorted(filter(None, calls))
        terminal_symbols.update(calls & available_external_imports)

        exact_bypasses: set[str] = set()
        for child in scoped_by_owner[owner]:
            if isinstance(child, ast.Call) and relevant(child):
                operation = call_symbol(child, owner)
                if not operation and isinstance(child.func, ast.Name):
                    operation = child.func.id
                arguments = (*child.args, *(item.value for item in child.keywords))
                receiver_tainted = (
                    _configuration_receiver_tainted(child, relevant)
                    or child is node
                )
                tainted_call = receiver_tainted or child is node or any(
                    relevant(argument) for argument in arguments
                )
                if operation in {"os.getenv", "os.environ.get", "environ.get"}:
                    exact_bypasses.add("AMBIENT_CONFIGURATION_READ")
                elif _is_legacy_configuration_symbol(operation) and tainted_call:
                    exact_bypasses.add("LEGACY_CONFIGURATION_STATE_MUTATION")
                elif _is_tolerant_configuration_call(
                    operation,
                    arguments,
                    receiver_tainted=receiver_tainted,
                    call_tainted=tainted_call,
                ):
                    exact_bypasses.add("TOLERANT_OR_COMPATIBILITY_LOADER")
            elif isinstance(child, ast.Try) and relevant(child) and any(
                isinstance(descendant, (ast.Return, ast.Continue, ast.Break, ast.Pass))
                for handler in child.handlers
                for descendant in ast.walk(handler)
            ):
                exact_bypasses.add("TOLERANT_OR_COMPATIBILITY_LOADER")
            elif (
                isinstance(child, ast.Subscript)
                and child is node
                and isinstance(child.ctx, ast.Load)
                and name(child.value, owner) in {"os.environ", "environ"}
            ):
                exact_bypasses.add("AMBIENT_CONFIGURATION_READ")
            elif isinstance(
                child, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)
            ):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                if relevant(child) and any(
                    (
                        isinstance(target, (ast.Attribute, ast.Subscript))
                        and _is_legacy_configuration_symbol(name(target.value, owner))
                    )
                    or (
                        isinstance(target, ast.Name)
                        and relevant(child.value)
                        and _is_legacy_configuration_symbol(
                            qualified_globals(owner).get(target.id, target.id)
                        )
                    )
                    for target in targets
                ):
                    exact_bypasses.add("LEGACY_CONFIGURATION_STATE_MUTATION")
        declared_bypasses = row.get("bypass_classes", ())
        authority_bypasses = (
            detect_ast_bypasses(
                ast.get_source_segment(source, function_by_symbol[owner]) or "",
                _tainted_names=tuple(origin_names),
                _qualified_names=qualified_globals(owner),
            )
            if owner in authority_symbols
            else ()
        )
        classes = tuple(
            class_id
            for class_id in BYPASS_CLASSES
            if class_id in exact_bypasses
            or class_id in contextual_bypasses
            or class_id in module_bypasses
            or class_id in declared_bypasses
            or class_id in authority_bypasses
        )
        if classes:
            bypasses[consumer_symbol] = classes

    for owner, node in functions:
        scoped_nodes = scoped_by_owner[owner]
        tainted = tainted_by_owner[owner]

        def relevant(value: ast.AST) -> bool:
            if isinstance(value, ast.Name):
                return value.id in tainted
            if isinstance(value, (ast.Starred, ast.NamedExpr)):
                return relevant(value.value)
            if isinstance(value, (ast.IfExp, ast.BoolOp, ast.Call)):
                return any(relevant(child) for child in ast.iter_child_nodes(value))
            return False

        calls: set[str] = set()
        for child in scoped_nodes:
            if not isinstance(child, ast.Call):
                continue
            super_target = super_callee(child, owner)
            call = call_symbol(child, owner)
            values = (
                *((child.func.value,) if isinstance(child.func, ast.Attribute) else ()),
                *child.args,
                *(keyword.value for keyword in child.keywords),
            )
            if call and (
                owner in force_all_calls_by_owner
                or
                id(child) in forced_call_occurrences_by_owner[owner]
                or call in authority_symbols
                or any(relevant(value) for value in values)
            ):
                target = call
                if call not in authority_symbols:
                    target, _ = occurrence_terminal_symbol(
                        child,
                        owner,
                        relevant,
                        call,
                        allow_tainted_receiver=False,
                    )
                calls.add(target)
                root = child.func
                while isinstance(root, ast.Attribute):
                    root = root.value
                visible_imports = imports_by_owner.get(owner, imports)
                if (
                    super_target is not None
                    and (imported_root := super_target.split(".", 1)[0])
                    not in workspace_module_roots
                    and super_target in available_external_imports
                    or isinstance(root, ast.Name)
                    and root.id in visible_imports
                    and root.id not in rebound_by_owner[owner]
                    and root.id not in module_rebounds
                    and (
                        imported_root := visible_imports[root.id].split(".", 1)[0]
                    )
                    not in workspace_module_roots
                    and not (workspace_root / f"{imported_root}.py").exists()
                    and not (workspace_root / imported_root / "__init__.py").exists()
                    and call in available_external_imports
                ):
                    terminal_symbols.add(call)
        graph[owner] = sorted(calls)
        function_source = ast.get_source_segment(source, node) or ""
        function_bypasses = detect_ast_bypasses(
            function_source,
            _tainted_names=tuple(tainted),
            _qualified_names=qualified_globals(owner),
        )
        classes = tuple(
            class_id
            for class_id in BYPASS_CLASSES
            if class_id in function_bypasses or class_id in module_bypasses
        )
        if classes and owner not in authority_symbols:
            bypasses[owner] = classes
    decorator_dependencies_by_owner: dict[str, set[str]] = {}
    for owner, node in decorated_owners:
        for index, decorator in enumerate(node.decorator_list):
            factory = decorator.func if isinstance(decorator, ast.Call) else decorator
            call = decorator if isinstance(decorator, ast.Call) else ast.copy_location(
                ast.Call(func=factory, args=[], keywords=[]), decorator
            )
            if call is not decorator:
                parent_by_node[id(call)] = parent_by_node[id(decorator)]
            binding = active_name_binding(
                call, module, ("source", decorator.lineno)
            )
            if (
                isinstance(factory, ast.Name)
                and binding is None
                and module_binding_counts.get(factory.id, 0) == 0
                and hasattr(builtins, factory.id)
            ):
                target = f"builtins.{factory.id}"
                terminal_symbols.add(target)
            else:
                target = call_symbol(call, module, ("source", decorator.lineno))
                root = factory
                while isinstance(root, ast.Attribute):
                    root = root.value
                stable_external = (
                    target in available_external_imports
                    and binding is not None
                    and binding[0] == "import"
                    and isinstance(root, ast.Name)
                    and not _has_module_object_mutation(
                        tree, {root.id}, reject_argument_escape=True
                    )
                )
                if stable_external:
                    terminal_symbols.add(target)
                elif target in function_by_symbol or target in workspace_function_nodes:
                    marker = f"@decorator:{owner}:{index}"
                    context_requests[marker] = (target, ("@trace-all",))
                    target = marker
                elif not target.startswith("@unresolved"):
                    target = f"@unresolved-decorator:{owner}:{index}"
            decorator_dependencies_by_owner.setdefault(owner, set()).add(target)
            graph[owner] = sorted(set((*graph.get(owner, ()), target)))
    occurrence_owners = [(row, owner) for row, owner, _ in exact_rows]
    occurrence_owners.extend(
        (row, cast(str, row["public_entry_route"]))
        for row, _, _ in class_decorator_rows
    )
    for row, owner in occurrence_owners:
        dependencies = set(decorator_dependencies_by_owner.get(owner, ()))
        for class_owner in class_by_symbol:
            if owner.startswith(f"{class_owner}."):
                dependencies.update(
                    decorator_dependencies_by_owner.get(class_owner, ())
                )
        if dependencies:
            consumer = f"@consumer:{row['consumer_id']}"
            graph[consumer] = sorted(set((*graph.get(consumer, ()), *dependencies)))

    return (
        graph,
        bypasses,
        set(function_by_symbol),
        terminal_symbols,
        context_requests,
    )


def reconcile_consumer_occurrences(
    frozen_rows: Sequence[Mapping[str, Any]],
    current_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Pair frozen and current occurrences without collapsing duplicates."""

    def key(row: Mapping[str, Any], fields: tuple[str, ...]) -> bytes:
        chain = row.get("transitive_wrapper_chain")
        return canonical_json_bytes(
            {
                field: (
                    chain[-1]
                    if field == "terminal" and isinstance(chain, (list, tuple)) and chain
                    else row.get(field)
                )
                for field in fields
            }
        )

    def pair(
        old: list[Mapping[str, Any]],
        current: list[Mapping[str, Any]],
        fields: tuple[str, ...],
    ) -> tuple[
        list[tuple[Mapping[str, Any], Mapping[str, Any]]],
        list[Mapping[str, Any]],
        list[Mapping[str, Any]],
    ]:
        old_groups: dict[bytes, list[Mapping[str, Any]]] = {}
        current_groups: dict[bytes, list[Mapping[str, Any]]] = {}
        for row in old:
            old_groups.setdefault(key(row, fields), []).append(row)
        for row in current:
            current_groups.setdefault(key(row, fields), []).append(row)
        paired: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        old_left: list[Mapping[str, Any]] = []
        current_left: list[Mapping[str, Any]] = []
        for group_key in sorted(old_groups.keys() | current_groups.keys()):
            old_group = sorted(old_groups.get(group_key, ()), key=canonical_json_bytes)
            current_group = sorted(
                current_groups.get(group_key, ()), key=canonical_json_bytes
            )
            count = min(len(old_group), len(current_group))
            paired.extend(zip(old_group[:count], current_group[:count]))
            old_left.extend(old_group[count:])
            current_left.extend(current_group[count:])
        return paired, old_left, current_left

    paired, old_left, current_left = pair(
        list(frozen_rows), list(current_rows), ("path", "source_span", "match_kind")
    )
    shape_paired, removed, added = pair(
        old_left,
        current_left,
        ("path", "public_entry_route", "match_kind", "terminal"),
    )
    paired.extend(shape_paired)
    return {
        "added": added,
        "added_count": len(added),
        "current_count": len(paired) + len(added),
        "old_count": len(paired) + len(removed),
        "paired": paired,
        "paired_count": len(paired),
        "removed": removed,
        "removed_count": len(removed),
    }


def _workspace_callable_index(
    workspace: Path, module_roots: frozenset[str]
) -> tuple[
    dict[str, tuple[str, str | None]],
    frozenset[str],
    dict[
        str,
        tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | None, bool, bool],
    ],
]:
    """Index functions and class constructors without importing candidate code."""

    result: dict[str, tuple[str, str | None]] = {}
    imported_targets: set[str] = set()
    function_nodes: dict[
        str,
        tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | None, bool, bool],
    ] = {}
    callable_aliases: dict[str, str] = {}
    for candidate in sorted(workspace.rglob("*.py")):
        relative = candidate.relative_to(workspace).as_posix()
        if PurePosixPath(relative).parts[0] not in module_roots:
            continue
        try:
            tree = ast.parse(candidate.read_text(encoding="utf-8"), filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise EvaluatorError(
                f"candidate consumer source is unreadable: {candidate}"
            ) from exc
        module = relative.removesuffix(".py").replace("/", ".")
        imported_by_name: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".", 1)[0]
                    target = alias.name if alias.asname else local
                    imported_targets.add(target)
                    imported_by_name.setdefault(local, set()).add(target)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    target = f"{node.module}.{alias.name}"
                    imported_targets.add(target)
                    imported_by_name.setdefault(
                        alias.asname or alias.name, set()
                    ).add(target)

        def imported_symbol(node: ast.AST) -> str | None:
            parts: list[str] = []
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if not isinstance(node, ast.Name):
                return None
            targets = imported_by_name.get(node.id, set())
            if len(targets) != 1:
                return None
            return ".".join((next(iter(targets)), *reversed(parts)))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = imported_symbol(node.func)
                if target:
                    imported_targets.add(target)
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    target = imported_symbol(base)
                    if target:
                        imported_targets.add(target)

        module_binding_counts = _module_binding_counts(tree)
        nested_global_names = {
            name
            for scope in ast.walk(tree)
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            for child in ast.walk(scope)
            if isinstance(child, ast.Global)
            for name in child.names
        }
        binding_scopes = (
            tree,
            *(
                ast.Module(body=list(scope.body), type_ignores=[])
                for scope in ast.walk(tree)
                if isinstance(
                    scope,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                )
            ),
        )
        parent_by_node = {
            id(child): parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }

        def has_enclosing_class_body_binding(node: ast.AST, name: str) -> bool:
            while (parent := parent_by_node.get(id(node))) is not None:
                if isinstance(parent, ast.ClassDef) and any(
                    node is statement for statement in parent.body
                ):
                    return _module_binding_counts(
                        ast.Module(body=list(parent.body), type_ignores=[])
                    ).get(name, 0) > 0
                node = parent
            return False

        allowed_dict_factory_calls: set[int] = set()
        for factory in ast.walk(tree):
            if not (isinstance(factory, ast.Name) and factory.id == "dict"):
                continue
            keyword = parent_by_node.get(id(factory))
            call = (
                parent_by_node.get(id(keyword))
                if isinstance(keyword, ast.keyword)
                else None
            )
            if not isinstance(call, ast.Call):
                continue
            assignment = parent_by_node.get(id(call))
            owner = (
                parent_by_node.get(id(assignment))
                if isinstance(assignment, ast.AnnAssign)
                else None
            )
            field_root = call.func
            while isinstance(field_root, ast.Attribute):
                field_root = field_root.value
            if (
                not call.args
                and len(call.keywords) == 1
                and call.keywords[0] is keyword
                and keyword.arg == "default_factory"
                and isinstance(assignment, ast.AnnAssign)
                and assignment.value is call
                and isinstance(owner, ast.ClassDef)
                and any(assignment is statement for statement in owner.body)
                and isinstance(field_root, ast.Name)
                and not has_enclosing_class_body_binding(
                    call.func, field_root.id
                )
                and imported_symbol(call.func) == "dataclasses.field"
            ):
                allowed_dict_factory_calls.add(id(call))

        def stable_imported_symbol(node: ast.AST) -> str | None:
            if (
                isinstance(node, ast.Name)
                and node.id in {"classmethod", "staticmethod"}
                and node.id not in imported_by_name
            ):
                builtin_aliases = {
                    local
                    for local, targets in imported_by_name.items()
                    if targets & {"builtins", f"builtins.{node.id}"}
                }
                aliases = {node.id, *builtin_aliases}
                if (
                    module_binding_counts.get(node.id, 0) != 0
                    or has_enclosing_class_body_binding(node, node.id)
                    or any(
                        module_binding_counts.get(alias) != 1
                        for alias in builtin_aliases
                    )
                    or any(
                        _has_module_object_mutation(
                            scope, aliases, reject_argument_escape=True
                        )
                        for scope in binding_scopes
                    )
                ):
                    return None
                return f"builtins.{node.id}"
            if isinstance(node, ast.Name) and node.id == "dict":
                keyword = parent_by_node.get(id(node))
                call = (
                    parent_by_node.get(id(keyword))
                    if isinstance(keyword, ast.keyword)
                    else None
                )
                if not (
                    module_binding_counts.get("dict", 0) == 0
                    and not has_enclosing_class_body_binding(node, "dict")
                    and isinstance(call, ast.Call)
                    and not call.args
                    and len(call.keywords) == 1
                    and call.keywords[0] is keyword
                    and keyword.arg == "default_factory"
                    and stable_imported_symbol(call.func) == "dataclasses.field"
                ):
                    return None
                builtin_aliases = {
                    local
                    for local, targets in imported_by_name.items()
                    if targets & {"builtins", "builtins.dict"}
                }
                aliases = {"dict", *builtin_aliases}
                if any(
                    module_binding_counts.get(alias) != 1
                    for alias in builtin_aliases
                ) or any(
                    _has_module_object_mutation(
                        scope,
                        aliases,
                        reject_argument_escape=True,
                        allowed_argument_calls=frozenset(
                            allowed_dict_factory_calls
                        ),
                    )
                    for scope in binding_scopes
                ):
                    return None
                return "builtins.dict"
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            target = imported_symbol(node)
            if not (
                isinstance(root, ast.Name)
                and target is not None
                and len(imported_by_name.get(root.id, ())) == 1
                and module_binding_counts.get(root.id) == 1
                and not has_enclosing_class_body_binding(node, root.id)
            ):
                return None
            aliases = {
                local
                for local, targets in imported_by_name.items()
                if any(
                    imported == target
                    or target.startswith(f"{imported}.")
                    for imported in targets
                )
            }
            if any(
                module_binding_counts.get(alias) != 1
                for alias in aliases
            ) or any(
                _has_module_object_mutation(
                    scope, aliases, reject_argument_escape=True
                )
                for scope in binding_scopes
            ):
                return None
            return target

        plain_generated_dataclass_names = {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and _is_plain_generated_dataclass(
                node, stable_imported_symbol, trace_post_init=True
            )
        }

        for node in tree.body:
            if not (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
            ):
                continue
            for alias in node.names:
                local = alias.asname or alias.name
                target = f"{node.module}.{alias.name}"
                if (
                    alias.name == "*"
                    or target.split(".", 1)[0] in module_roots
                    or imported_by_name.get(local) != {target}
                    or module_binding_counts.get(local) != 1
                    or local in nested_global_names
                    or _has_module_object_mutation(
                        tree, {local}, reject_argument_escape=True
                    )
                ):
                    continue
                symbol = f"{module}.{local}"
                result[symbol] = (relative, symbol)
                function_nodes[symbol] = (target, None, False, False)

        for node in tree.body:
            if not (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and module_binding_counts.get(node.targets[0].id) == 1
            ):
                continue
            target = imported_symbol(node.value)
            if (
                target is None
                and isinstance(node.value, ast.Name)
                and node.value.id in plain_generated_dataclass_names
            ):
                target = f"{module}.{node.value.id}"
            if target:
                symbol = f"{module}.{node.targets[0].id}"
                result[symbol] = (relative, symbol)
                callable_aliases[symbol] = target
                imported_targets.add(target)

        def collect(nodes: Sequence[ast.stmt], owner: str) -> None:
            for node in nodes:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbol = f"{owner}.{node.name}"
                    if symbol in result:
                        _fail(f"candidate callable is duplicated: {symbol}")
                    result[symbol] = (relative, symbol)
                    if owner == module:
                        function_nodes[symbol] = (
                            symbol,
                            None if node.decorator_list else node,
                            False,
                            False,
                        )
                    collect(node.body, symbol)
                elif isinstance(node, ast.ClassDef):
                    symbol = f"{owner}.{node.name}"
                    initializer_node = next(
                        (
                            child
                            for child in node.body
                            if isinstance(
                                child, (ast.FunctionDef, ast.AsyncFunctionDef)
                            )
                            and child.name == "__init__"
                        ),
                        None,
                    )
                    initializer = (
                        f"{symbol}.__init__"
                        if initializer_node is not None
                        else None
                    )
                    post_init_node = next(
                        (
                            child
                            for child in node.body
                            if isinstance(child, ast.FunctionDef)
                            and child.name == "__post_init__"
                        ),
                        None,
                    )
                    if symbol in result:
                        _fail(f"candidate callable is duplicated: {symbol}")
                    plain_generated_dataclass = (
                        owner == module
                        and node.name in plain_generated_dataclass_names
                    )
                    stable_class = (
                        module_binding_counts.get(node.name) == 1
                        and not _has_module_class_attribute_mutation(
                            tree,
                            node,
                            allow_stable_alias=plain_generated_dataclass,
                        )
                    )
                    traced_post_init = (
                        post_init_node
                        if owner == module
                        and stable_class
                        and plain_generated_dataclass
                        else None
                    )
                    post_init_symbol = (
                        f"{symbol}.__post_init__"
                        if traced_post_init is not None
                        else None
                    )
                    result[symbol] = (
                        relative,
                        initializer or post_init_symbol or symbol,
                    )
                    if owner == module and initializer_node is not None:
                        function_nodes[symbol] = (
                            symbol,
                            initializer_node,
                            True,
                            stable_class,
                        )
                    elif owner == module and traced_post_init is not None:
                        function_nodes[symbol] = (
                            cast(str, post_init_symbol),
                            traced_post_init,
                            True,
                            stable_class,
                        )
                    elif owner == module:
                        decorator = (
                            "dataclasses.dataclass"
                            if stable_class and plain_generated_dataclass
                            else None
                        )
                        base = (
                            imported_symbol(node.bases[0])
                            if len(node.bases) == 1
                            else None
                        )
                        if base is None and len(node.bases) == 1 and isinstance(
                            node.bases[0], ast.Name
                        ):
                            base = f"{module}.{node.bases[0].id}"
                        function_nodes[symbol] = (
                            (
                                _PLAIN_BUILTIN_EXCEPTION
                                if not _has_module_class_attribute_mutation(
                                    tree, node
                                )
                                and _is_plain_builtin_exception_subclass(
                                    node, module_binding_counts
                                )
                                else decorator or base or symbol
                            ),
                            None,
                            True,
                            stable_class,
                        )
                    collect(node.body, symbol)

        collect(tree.body, module)
    for alias, target in callable_aliases.items():
        seen = {alias}
        while target in callable_aliases and target not in seen:
            seen.add(target)
            target = callable_aliases[target]
        if target in seen or target not in function_nodes:
            continue
        function_nodes[alias] = function_nodes[target]
    return result, frozenset(imported_targets), function_nodes


def _available_external_imports(
    targets: frozenset[str], python_executable: Path | None
) -> frozenset[str]:
    def available(target: str) -> bool:
        parts = target.split(".")
        for length in range(len(parts), 0, -1):
            try:
                value: Any = importlib.import_module(".".join(parts[:length]))
            except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
                continue
            try:
                for attribute in parts[length:]:
                    value = getattr(value, attribute)
            except AttributeError:
                return False
            return callable(value)
        return False

    if python_executable is None:
        return frozenset(target for target in targets if available(target))
    probe = """\
import contextlib
import importlib
import io
import json
import sys

available = []
for name in json.load(sys.stdin):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        parts = name.split('.')
        for length in range(len(parts), 0, -1):
            try:
                value = importlib.import_module('.'.join(parts[:length]))
            except BaseException:
                continue
            try:
                for attribute in parts[length:]:
                    value = getattr(value, attribute)
            except BaseException:
                break
            if not callable(value):
                break
            available.append(name)
            break
print(json.dumps(available))
"""
    try:
        completed = subprocess.run(
            (str(python_executable), "-I", "-B", "-c", probe),
            check=False,
            cwd=Path("/"),
            env=_subprocess_environment(None),
            input=json.dumps(sorted(targets)),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvaluatorError("external module probe failed") from exc
    try:
        observed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EvaluatorError("external module probe returned invalid JSON") from exc
    if (
        completed.returncode != 0
        or not isinstance(observed, list)
        or any(not isinstance(target, str) or target not in targets for target in observed)
        or len(observed) != len(set(observed))
    ):
        _fail("external module probe failed")
    return frozenset(observed)


def inspect_candidate_consumers(
    *,
    candidate_evidence: Mapping[str, Any],
    consumer_census: Mapping[str, Any],
    retained_root_dispositions: Sequence[Mapping[str, Any]] = (),
    workspace: Path,
    python_executable: Path | None = None,
) -> dict[str, Any]:
    """Join every frozen slot to candidate source and follow actual AST calls."""

    rows = consumer_census.get("rows")
    if not isinstance(rows, list) or not rows:
        _fail("frozen configuration census is absent")
    disposition_rows = (
        _validate_retained_root_dispositions(retained_root_dispositions, rows)
        if retained_root_dispositions
        else []
    )
    disposed_frozen_ids = {
        consumer_id
        for disposition in disposition_rows
        for consumer_id in cast(Sequence[str], disposition["consumer_ids"])
    }
    authority_symbols = {
        row["symbol"] for row in candidate_evidence["public_resolution_routes"]
    }
    projected = project_frozen_consumer_slots(rows)
    try:
        candidate_scan = scan_workspace_configuration_consumers(workspace)
    except TaskPackageError as exc:
        raise EvaluatorError("candidate configuration-consumer scan failed") from exc
    scanned_rows = cast(list[dict[str, Any]], candidate_scan["rows"])
    if not scanned_rows and all(
        str(row.get("path", "")).startswith("candidate/") for row in rows
    ):
        # Synthetic evaluator fixtures live outside the frozen detector roots.
        scanned_rows = [
            row for row in rows
            if workspace.joinpath(*PurePosixPath(row["path"]).parts).exists()
        ]
    construction_spans_by_path: dict[str, set[tuple[object, ...]]] = {}
    for row in scanned_rows:
        relative, span = row.get("path"), row.get("source_span")
        if (
            row.get("match_kind") != "CONFIGURATION_CONSTRUCTION"
            or not isinstance(relative, str)
            or not isinstance(span, Mapping)
        ):
            continue
        construction_spans_by_path.setdefault(relative, set()).add(
            (
                span.get("start_line"),
                span.get("start_col"),
                span.get("end_line"),
                span.get("end_col"),
            )
        )
    reconciliation = reconcile_consumer_occurrences(rows, scanned_rows)
    span_cache: dict[str, dict[tuple[object, ...], int]] = {}

    def occurrence_survives(row: Mapping[str, Any]) -> bool:
        relative, span = row.get("path"), row.get("source_span")
        if not isinstance(relative, str) or not isinstance(span, Mapping):
            return False
        if relative not in span_cache:
            path = _safe_descendant(
                workspace, relative, label="candidate census source"
            )
            if not path.exists():
                span_cache[relative] = {}
            else:
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, SyntaxError) as exc:
                    raise EvaluatorError(
                        f"candidate consumer source is unreadable: {path}"
                    ) from exc
                counts: dict[tuple[object, ...], int] = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.stmt):
                        continue
                    key = (
                        getattr(node, "lineno", None),
                        getattr(node, "col_offset", None),
                        getattr(node, "end_lineno", None),
                        getattr(node, "end_col_offset", None),
                    )
                    counts[key] = counts.get(key, 0) + 1
                span_cache[relative] = counts
        expected = (
            span.get("start_line"), span.get("start_col"),
            span.get("end_line"), span.get("end_col"),
        )
        return span_cache[relative].get(expected) == 1

    surviving_removed = [
        row for row in reconciliation["removed"] if occurrence_survives(row)
    ]
    paired_rows = cast(
        list[tuple[Mapping[str, Any], Mapping[str, Any]]],
        reconciliation["paired"],
    )
    current_rows = (
        [current for _, current in paired_rows]
        + reconciliation["added"]
        + surviving_removed
    )
    retired_rows = [
        row for row in reconciliation["removed"] if row not in surviving_removed
    ]
    disposed_rows = [
        current
        for frozen, current in paired_rows
        if frozen["consumer_id"] in disposed_frozen_ids
        and current.get("path") == frozen.get("path")
        and current.get("public_entry_route") == frozen.get("public_entry_route")
    ] + [
        row for row in surviving_removed
        if row["consumer_id"] in disposed_frozen_ids
    ]
    disposed_ids = {cast(str, row["consumer_id"]) for row in disposed_rows}
    live_rows = [
        row for row in current_rows if cast(str, row["consumer_id"]) not in disposed_ids
    ]
    graph: dict[str, list[str]] = {}
    graph_paths: dict[str, str] = {}
    bypasses: dict[str, Any] = {}
    introduced: set[str] = set()
    terminal_symbols: set[str] = set()
    rows_by_path: dict[str, list[Mapping[str, Any]]] = {}
    for row in current_rows:
        rows_by_path.setdefault(cast(str, row["path"]), []).append(row)
    workspace_module_roots = frozenset(
        PurePosixPath(cast(str, row["path"])).parts[0]
        for row in [*current_rows, *rows]
    )
    workspace_shadow_roots = frozenset(
        root
        for root in workspace_module_roots
        if (workspace / f"{root}.py").exists()
        or (workspace / root / "__init__.py").exists()
    )
    callable_index, imported_targets, workspace_function_nodes = _workspace_callable_index(
        workspace, workspace_module_roots
    )
    available_external_imports = _available_external_imports(
        frozenset(
            target
            for target in imported_targets
            if target.split(".", 1)[0] not in workspace_shadow_roots
        ),
        python_executable,
    )
    synthetic_owners: dict[str, set[str]] = {}
    synthetic_decorator_owners: dict[str, set[str]] = {}
    synthetic_contexts: dict[
        str, dict[str, tuple[str, tuple[str, ...]]]
    ] = {}
    context_requests: dict[str, tuple[str, tuple[str, ...]]] = {}

    def analyze(relative: str) -> None:
        path = _safe_descendant(workspace, relative, label="candidate census source")
        module = relative.removesuffix(".py").replace("/", ".")
        synthetic_rows = [
            {"public_entry_route": owner}
            for owner in sorted(synthetic_owners.get(relative, ()))
        ] + [
            {"public_entry_route": owner, "trace_all_calls": True}
            for owner in sorted(synthetic_decorator_owners.get(relative, ()))
        ] + [
            {
                "context_symbol": context_symbol,
                "public_entry_route": owner,
                "tainted_formals": list(formals),
            }
            for context_symbol, (owner, formals) in sorted(
                synthetic_contexts.get(relative, {}).items()
            )
        ]
        (
            local_graph,
            local_bypasses,
            local_symbols,
            local_terminals,
            local_context_requests,
        ) = (
            _module_functions(
                path,
                module,
                authority_symbols=authority_symbols,
                consumer_rows=[*rows_by_path.get(relative, ()), *synthetic_rows],
                current_construction_spans=frozenset(
                    construction_spans_by_path.get(relative, ())
                ),
                workspace_module_roots=workspace_shadow_roots,
                available_external_imports=available_external_imports,
                workspace_function_nodes=workspace_function_nodes,
            )
        )
        graph.update(local_graph)
        graph_paths.update((symbol, relative) for symbol in local_graph)
        bypasses.update(local_bypasses)
        introduced.update(local_symbols)
        terminal_symbols.update(local_terminals)
        context_requests.update(local_context_requests)

    analyzed_paths: set[str] = set()
    for row in [*current_rows, *rows]:
        relative = cast(str, row["path"])
        candidate_path = workspace.joinpath(*PurePosixPath(relative).parts)
        if not candidate_path.exists() or relative in analyzed_paths:
            continue
        analyze(relative)
        analyzed_paths.add(relative)

    while True:
        changed_paths: set[str] = set()
        for parent, children in tuple(graph.items()):
            for symbol in children:
                if (
                    symbol in authority_symbols
                    or symbol in bypasses
                    or symbol in terminal_symbols
                ):
                    continue
                context = context_requests.get(symbol)
                target_symbol = context[0] if context is not None else symbol
                target = callable_index.get(target_symbol)
                if target is None:
                    continue
                relative, owner = target
                if symbol in graph and graph_paths.get(symbol) == graph_paths.get(parent):
                    continue
                if (
                    context is not None
                    and context[1] == ("@trace-all",)
                    and owner is not None
                ):
                    if symbol not in graph:
                        graph[symbol] = [target_symbol]
                        graph_paths[symbol] = relative
                    if owner not in synthetic_decorator_owners.setdefault(relative, set()):
                        synthetic_decorator_owners[relative].add(owner)
                        changed_paths.add(relative)
                elif context is not None and not context[1] and owner is not None:
                    if symbol not in graph:
                        graph[symbol] = [
                            target_symbol,
                            f"{symbol}:missing",
                        ]
                        graph_paths[symbol] = relative
                    if owner not in synthetic_owners.setdefault(relative, set()):
                        synthetic_owners[relative].add(owner)
                        changed_paths.add(relative)
                elif context is not None and owner is not None:
                    contexts = synthetic_contexts.setdefault(relative, {})
                    if symbol not in contexts:
                        contexts[symbol] = (owner, context[1])
                        changed_paths.add(relative)
                elif owner is not None and owner not in synthetic_owners.setdefault(
                    relative, set()
                ):
                    synthetic_owners[relative].add(owner)
                    changed_paths.add(relative)
                elif relative not in analyzed_paths:
                    changed_paths.add(relative)
        if not changed_paths:
            break
        for relative in sorted(changed_paths):
            analyze(relative)
            analyzed_paths.add(relative)
    for entry in sorted(
        {cast(str, row["public_entry_route"]) for row in disposed_rows}
    ):
        graph[entry] = sorted(
            set((*graph.get(entry, ()), f"@retained-legacy-root:{entry}"))
        )
    for row in current_rows:
        classes = row.get("bypass_classes", ())
        if not classes:
            continue
        if not isinstance(classes, list) or any(
            class_id not in BYPASS_CLASSES for class_id in classes
        ):
            _fail("candidate census names an unknown bypass class")
        entry = (
            f"@consumer:{row['consumer_id']}"
            if f"@consumer:{row['consumer_id']}" in graph
            else row["public_entry_route"]
        )
        bypasses[entry] = tuple(
            class_id
            for class_id in BYPASS_CLASSES
            if class_id in classes or class_id in bypasses.get(entry, ())
        )
    live_projected = [
        {
            "consumer_id": row["consumer_id"],
            "entry_symbol": (
                f"@consumer:{row['consumer_id']}"
                if f"@consumer:{row['consumer_id']}" in graph
                else row["public_entry_route"]
            ),
            "requires_authority": _requires_resolution_authority(row),
        }
        for row in live_rows
    ]
    for row in live_projected:
        entry = row["entry_symbol"]
        if entry in graph:
            continue
        suffix = "." + entry.rsplit(".", 1)[-1]
        candidates = sorted(symbol for symbol in graph if symbol.endswith(suffix))
        if len(candidates) > 1:
            _fail(f"candidate consumer entry is ambiguous: {entry}")
    for row in rows:
        entry = row["public_entry_route"]
        candidate_path = workspace.joinpath(*PurePosixPath(row["path"]).parts)
        if candidate_path.exists() and entry not in graph:
            suffix = "." + entry.rsplit(".", 1)[-1]
            if len([symbol for symbol in graph if symbol.endswith(suffix)]) > 1:
                _fail(f"candidate consumer entry is ambiguous: {entry}")
    route = (
        walk_consumer_routes(
            consumer_rows=live_projected,
            call_graph=graph,
            authority_symbols=authority_symbols,
            bypass_symbols=bypasses,
            terminal_symbols=terminal_symbols,
        )
        if live_projected
        else {
            "bypass_classes": [],
            "closed": True,
            "traces": [],
            "unresolved_consumers": [],
        }
    )
    baseline_entries = {row["public_entry_route"] for row in current_rows}
    introduced_consumers = sorted(
        symbol
        for symbol in introduced
        if symbol not in baseline_entries and symbol not in authority_symbols
        and any(child in authority_symbols for child in graph.get(symbol, ()))
    )
    return {
        **route,
        "accounted_consumer_count": len(current_rows),
        "added_consumer_count": reconciliation["added_count"],
        "introduced_consumer_symbols": sorted(
            set(introduced_consumers)
            | {row["public_entry_route"] for row in reconciliation["added"]}
        ),
        "disposed_consumer_count": len(disposed_rows),
        "disposed_consumer_ids": sorted(disposed_ids),
        "live_consumer_count": len(live_rows),
        "live_consumer_ids": sorted(
            cast(str, row["consumer_id"]) for row in live_rows
        ),
        "paired_consumer_count": reconciliation["paired_count"],
        "projected_consumer_count": len(projected),
        "removed_consumer_count": len(retired_rows),
        "retired_consumer_ids": [
            row["consumer_id"] for row in retired_rows
        ],
    }


def project_frozen_consumer_slots(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Project every frozen census row once without accepting caller substitutions."""

    projected: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("frozen configuration census row is malformed")
        consumer_id, relative, entry = row.get("consumer_id"), row.get("path"), row.get("public_entry_route")
        if not all(isinstance(value, str) and value for value in (consumer_id, relative, entry)):
            _fail("frozen configuration census identity is malformed")
        projected.append({"consumer_id": consumer_id, "entry_symbol": entry})
    if len({row["consumer_id"] for row in projected}) != len(projected):
        _fail("frozen configuration census slots are duplicated")
    return projected


_ROUNDTRIP_PROGRAM = r'''import json,os,pathlib
source=pathlib.Path(os.environ["ES_F1_ROUNDTRIP_INPUT"])
target=pathlib.Path(os.environ["ES_F1_ROUNDTRIP_OUTPUT"])
value=json.loads(source.read_bytes())
target.write_bytes((json.dumps(value,allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode())
'''


def fresh_process_roundtrip(
    value: Mapping[str, Any],
    *,
    output_root: Path,
    protected_workspace: Path,
    python_executable: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=False)
    source = output_root / "source.json"
    target = output_root / "target.json"
    source.write_bytes(canonical_json_bytes(dict(value)))
    protected_workspace = protected_workspace.resolve(strict=True)
    if output_root.resolve(strict=True).is_relative_to(protected_workspace):
        _fail("roundtrip output must be outside the protected workspace")
    run_candidate_probe(
        code=_ROUNDTRIP_PROGRAM,
        environment={
            "ES_F1_ROUNDTRIP_INPUT": str(source),
            "ES_F1_ROUNDTRIP_OUTPUT": str(target),
        },
        label="fresh-process configuration roundtrip",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=protected_workspace,
        working_directory=output_root,
    )
    observed = _canonical_object(target, label="fresh-process roundtrip result")
    if observed != value:
        _fail("fresh-process configuration roundtrip changed the value")
    return observed


def _evaluate_candidate(
    *,
    calibration_cases: Sequence[Mapping[str, Any]],
    candidate_evidence_path: Path,
    consumer_census: Mapping[str, Any],
    output_root: Path,
    package_conformance: Mapping[str, Any],
    python_executable: Path,
    retained_root_dispositions: Sequence[Mapping[str, Any]] = (),
    timeout_seconds: int,
    visible_result: Mapping[str, Any],
    workspace: Path,
) -> list[dict[str, Any]]:
    """Controller root: derive observations only from bound bytes and executions."""

    try:
        workspace = workspace.resolve(strict=True)
    except OSError as exc:
        raise EvaluatorError("candidate workspace is missing") from exc
    if not workspace.is_dir():
        _fail("candidate workspace is missing")
    evidence = load_candidate_config_evidence(candidate_evidence_path)
    if package_conformance != {
        "candidate_evidence": "candidate_config_evidence.v2",
        "probe_request": "config_resolution_probe_request.v1",
        "probe_result": "config_resolution_probe_result.v1",
        "validated": True,
    }:
        _fail("candidate package conformance is not bound")
    cases = [
        {"case_id": row["case_id"], **cast(dict[str, Any], row["probe"])}
        for row in calibration_cases
        if row.get("defect_kind") == "none"
    ]
    if not cases:
        _fail("evaluator-owned empirical cases are absent")
    execute_empirical_probe(
        candidate_evidence_path=candidate_evidence_path,
        cases=cases,
        output_root=output_root / "probe",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    run_evaluation_hooks(
        candidate_evidence_path=candidate_evidence_path,
        output_root=output_root / "hooks",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    surface = run_surface_and_carrier_proof(
        candidate_evidence_path=candidate_evidence_path,
        output_root=output_root / "surface-proof",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    transaction = run_torch_transaction_proof(
        candidate_evidence_path=candidate_evidence_path,
        output_root=output_root / "transaction-proof",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    derivation = run_simulation_derivation_proof(
        candidate_evidence_path=candidate_evidence_path,
        output_root=output_root / "derivation-proof",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    direct = run_direct_resolver_probe(
        candidate_evidence_path=candidate_evidence_path,
        output_root=output_root / "direct-probe",
        python_executable=python_executable,
        timeout_seconds=timeout_seconds,
        workspace=workspace,
    )
    route = inspect_candidate_consumers(
        candidate_evidence=evidence,
        consumer_census=consumer_census,
        retained_root_dispositions=retained_root_dispositions,
        workspace=workspace,
        python_executable=python_executable,
    )
    visible_ok, visible_evidence = _visible_observation(
        visible_result,
        {
            "PRE_EDIT_FOCUSED": F1_PROVIDER_VISIBLE_SELECTORS,
            "CANDIDATE_CONFIG": ("tests/test_es_f1_config_ownership.py",),
        },
        {
            "PRE_EDIT_FOCUSED": F1_PROVIDER_VISIBLE_DESELECTORS,
            "CANDIDATE_CONFIG": (),
        },
    )
    direct_facts = direct["facts"]
    surface_facts = surface["facts"]
    transactional_ok = transaction["facts"]["F1-H04-TRANSACTIONAL-APPLICATION"]
    strict_ok = direct_facts["F1-H05-STRICT-INPUT-CONTRACT"]
    derived_ok = (
        derivation["facts"]["F1-H06-DERIVED-PUBLIC-FIELDS"]
        and direct_facts["F1-H06-DERIVED-PUBLIC-FIELDS"]
    )
    coherence_ok = surface_facts["F1-H09-CROSS-SURFACE-COHERENCE"]
    h10_bypasses = [
        class_id
        for class_id in BYPASS_CLASSES
        if class_id in route["bypass_classes"]
        or class_id in surface["runtime_bypass_classes"]
    ]
    h10_evidence = {
        **route,
        "bypass_classes": h10_bypasses,
        "runtime_bypass_classes": surface["runtime_bypass_classes"],
    }
    facts = (
        ("F1-H01-FOCUSED-SUITES", visible_ok, visible_evidence, "frozen visible selectors pass"),
        ("F1-H02-SCHEMA-CONFORMANCE", True, package_conformance, "closed package loaders passed"),
        ("F1-H03-PUBLIC-RESOLUTION", surface_facts["F1-H03-PUBLIC-RESOLUTION"], surface, "public product targets obey precedence"),
        ("F1-H04-TRANSACTIONAL-APPLICATION", transactional_ok, transaction, "one complete commit or byte-equivalent rollback"),
        ("F1-H05-STRICT-INPUT-CONTRACT", strict_ok, direct["transcript"], "strict inputs and fields survive"),
        ("F1-H06-DERIVED-PUBLIC-FIELDS", derived_ok, derivation, "public fields derive from the returned structural owner"),
        ("F1-H07-CONSUMER-CLOSURE", route["closed"], route, "every frozen consumer reaches authority"),
        ("F1-H08-PROVENANCE-ROUNDTRIP", surface_facts["F1-H08-PROVENANCE-ROUNDTRIP"], surface, "product-carried provenance survives a fresh-process codec"),
        ("F1-H09-CROSS-SURFACE-COHERENCE", coherence_ok, surface, "six product targets preserve canonical initialization values"),
        ("F1-H10-BYPASS-ORACLE", route["closed"] and not h10_bypasses, h10_evidence, "three-class bypass oracle is empty"),
    )
    return [_observation(*fact) for fact in facts]


def evaluate_candidate(
    *,
    candidate_evidence_path: Path,
    output_root: Path,
    workspace: Path,
) -> list[dict[str, Any]]:
    """Evaluate one candidate against the exact checked-in F1v2 package."""

    package = load_checked_in_evaluator_package()
    checks = cast(Any, package["visible_checks"])
    visible_result = run_visible_checks(
        workspace=workspace,
        visible_checks=cast(Mapping[str, Any], checks.raw),
    )
    return _evaluate_candidate(
        calibration_cases=cast(dict[str, Any], package["calibration_cases"])[
            "cases"
        ],
        candidate_evidence_path=candidate_evidence_path,
        consumer_census=cast(Mapping[str, Any], package["consumer_census"]),
        output_root=output_root,
        package_conformance=cast(Mapping[str, Any], package["package_conformance"]),
        python_executable=checks.python_executable,
        retained_root_dispositions=cast(
            Sequence[Mapping[str, Any]], package["retained_root_dispositions"]
        ),
        timeout_seconds=checks.timeout_seconds,
        visible_result=visible_result,
        workspace=workspace,
    )


def _exact_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith(_SHA256_PREFIX) and all(
        character in "0123456789abcdef" for character in value[7:]
    )


def _visible_observation(
    result: Mapping[str, Any],
    expected: Mapping[str, Sequence[str]],
    expected_deselectors: Mapping[str, Sequence[str]],
) -> tuple[bool, dict[str, Any]]:
    if (
        result.get("schema_version") != "es-f1-visible-check-result.v3"
        or result.get("copy_digest_before") != result.get("copy_digest_after")
        or not _exact_digest(result.get("copy_digest_before"))
    ):
        return False, {"reason": "visible-result-header"}
    invocations = result.get("invocations")
    if not isinstance(invocations, list) or [row.get("invocation_id") for row in invocations if isinstance(row, Mapping)] != list(expected):
        return False, {"reason": "visible-invocation-order"}
    for row in invocations:
        if (
            not isinstance(row, Mapping)
            or tuple(row.get("selectors", ())) != tuple(expected[row["invocation_id"]])
            or tuple(row.get("deselectors", ()))
            != tuple(expected_deselectors[row["invocation_id"]])
            or row.get("exit_code") != 0
        ):
            return False, {"reason": "visible-invocation-result"}
    return True, {"invocation_ids": list(expected)}


def _observation(clause_id: str, satisfied: bool, evidence: object, details: str) -> dict[str, Any]:
    return {
        "clause_id": clause_id,
        "details": details,
        "evidence": [_digest(evidence)],
        "satisfied": satisfied,
    }


def _authority_path(value: Any, path: str = "$") -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            current = f"{path}.{key}"
            if key in _CANDIDATE_AUTHORITY_FIELDS:
                return current
            nested = _authority_path(item, current)
            if nested:
                return nested
    elif isinstance(value, list):
        for index, item in enumerate(value):
            nested = _authority_path(item, f"{path}[{index}]")
            if nested:
                return nested
    return None


def evaluate_observations(
    *,
    candidate_claims: Mapping[str, Any],
    evaluator_observations: Sequence[Mapping[str, Any]],
    dispositions: Mapping[str, str],
    frozen_registry: set[str],
) -> dict[str, Any]:
    """Normalize evaluator facts and derive findings; candidates author neither."""

    if type(frozen_registry) is not set or frozen_registry != set(CONFIG_RESOLUTION_ROLES):
        raise ValueError("frozen configuration-role domain is not exact")
    if not isinstance(candidate_claims, Mapping):
        raise ValueError("candidate claims must be one object")
    claims = json.loads(canonical_json_bytes(dict(candidate_claims)))
    if claims.get("schema_version") != "candidate_config_evidence.v2":
        raise ValueError("candidate configuration evidence is unsupported")
    authority = _authority_path(claims)
    if authority:
        raise ValueError(f"candidate record carries evaluator authority at {authority}")
    candidate_id = claims.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate identity is invalid")
    observations = json.loads(canonical_json_bytes(list(evaluator_observations)))
    if [row.get("clause_id") for row in observations if isinstance(row, dict)] != list(HARD_CLAUSE_IDS):
        raise ValueError("evaluator observations must cover all clauses in exact order")
    normalized: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for row in observations:
        if set(row) != {"clause_id", "details", "evidence", "satisfied"} or type(row["satisfied"]) is not bool:
            raise ValueError("evaluator observation field set is not exact")
        if not isinstance(row["details"], str) or not isinstance(row["evidence"], list) or not row["evidence"]:
            raise ValueError("evaluator observation evidence is invalid")
        evidence_digest = _digest(row["evidence"])
        normalized.append(
            {
                "clause_id": row["clause_id"],
                "details": row["details"],
                "evidence_digest": evidence_digest,
                "satisfied": row["satisfied"],
            }
        )
        if not row["satisfied"]:
            disposition = dispositions.get(row["clause_id"])
            if disposition not in DISPOSITIONS:
                raise ValueError("failed observation disposition is missing or invalid")
            findings.append(
                {
                    "candidate_id": candidate_id,
                    "clause_id": row["clause_id"],
                    "details": row["details"],
                    "disposition": disposition,
                    "evaluator_observation": {
                        "evidence_digest": evidence_digest,
                        "satisfied": False,
                    },
                    "schema_version": "es-f1-hard-finding.v3",
                }
            )
    return {
        "candidate_claims_digest": _digest(claims),
        "candidate_id": candidate_id,
        "evaluator_observations": normalized,
        "hard_findings": findings,
        "schema_version": "es-f1-hard-evaluation.v3",
    }
