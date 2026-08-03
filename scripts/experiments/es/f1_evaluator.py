"""Controller-owned hard evaluator for the ES F1 calibration package.

The evaluator is intentionally outside candidate workspaces.  It consumes
closed, canonical records and derives observations independently of candidate
claims; candidates never author a clause result.
"""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


HARD_CLAUSE_IDS = (
    "F1-H01-FOCUSED-SUITES",
    "F1-H02-SCHEMA-CONFORMANCE",
    "F1-H03-BUILTIN-SIGNATURES",
    "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
    "F1-H05-NOMINATED-LIFECYCLE",
    "F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP",
    "F1-H07-STRUCTURAL-IDENTITY-REJECTION",
    "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",
    "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
    "F1-H10-OWNERSHIP-BOUNDARY",
)

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

ARTIFACT_ERA_IDS = (
    "torch-model-spec-v1",
    "torch-model-spec-v2",
    "torch-artifact-v1",
    "torch-artifact-v2",
    "legacy-config-only-checkpoint",
    "current-model-spec-v2-checkpoint",
    "metadata-free-legacy-bundle",
    "transitional-ci-entrypoints-v1-bundle",
    "torch-artifact-v1-bundle",
    "torch-artifact-v2-bundle",
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_LIFECYCLE_REQUEST_SCHEMA = (
    _REPOSITORY_ROOT
    / "experiments/orc_effectiveness/f1_es/task/lifecycle-probe-request.schema.json"
)
_LIFECYCLE_RESULT_SCHEMA = (
    _REPOSITORY_ROOT
    / "experiments/orc_effectiveness/f1_es/task/lifecycle-probe-result.schema.json"
)
_CANDIDATE_EVIDENCE_SCHEMA = (
    _REPOSITORY_ROOT
    / "experiments/orc_effectiveness/f1_es/task/candidate-extension-evidence.schema.json"
)
_VISIBLE_CHECK_SCHEMA = (
    _REPOSITORY_ROOT
    / "experiments/orc_effectiveness/f1_es/task/visible-check-manifest.schema.json"
)

_CANDIDATE_AUTHORITY_FIELDS = frozenset(
    {
        "passed",
        "satisfied",
        "hard_findings",
        "evaluator_observations",
        "disposition",
        "decision",
    }
)

_PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS = {
    "compute_loss": "ptycho_torch.model.PtychoPINN_Lightning.compute_loss",
    "loss_forward": "ptycho_torch.model.PoissonLoss.forward",
    "model_forward": "ptycho_torch.model.PtychoPINN.forward",
    "physics_forward": "ptycho_torch.model.ForwardModel.forward",
    "scaling": "ptycho_torch.model.IntensityScalerModule.scale",
}

_PUBLIC_SCIENTIFIC_BOUNDARY_CONTRACT = {
    "loss_function": "Poisson",
    "measurement_domain": "normalized_amplitude",
    "physics_forward_mode": "amplitude",
    "scale_contract_version": "legacy_v1",
    "torch_loss_mode": "poisson",
}

_TOP_LEVEL_FIELDS = {
    "example.v1": frozenset({"schema_version", "values"}),
    "es-f1-fixture-manifest.v1": frozenset(
        {
            "schema_version",
            "hard_clause_ids",
            "registry_baseline",
            "artifact_eras",
            "artifact_fixture_origin",
            "calibration_cases",
            "external_fixture_store",
        }
    ),
    "es-f1-reviewer-perspectives.v1": frozenset(
        {"schema_version", "perspectives"}
    ),
    "es-f1-calibration-cases.v2": frozenset({"schema_version", "cases"}),
    "es_f1_visible_checks.v1": frozenset(
        {
            "schema_version",
            "task_id",
            "runner",
            "invocation_order",
            "invocations",
        }
    ),
}

CALIBRATION_DEFECT_CLAUSES = {
    "none": (),
    "missing_identity": ("F1-H07-STRUCTURAL-IDENTITY-REJECTION",),
    "extra_identity": ("F1-H07-STRUCTURAL-IDENTITY-REJECTION",),
    "unknown_identity": ("F1-H07-STRUCTURAL-IDENTITY-REJECTION",),
    "unsupported_identity": ("F1-H07-STRUCTURAL-IDENTITY-REJECTION",),
    "schema_version_drift": ("F1-H02-SCHEMA-CONFORMANCE",),
    "route_disagreement": ("F1-H09-CONSTRUCTION-REBUILD-EQUALITY",),
    "missing_persisted_builder": ("F1-H09-CONSTRUCTION-REBUILD-EQUALITY",),
    "same_process_reload": ("F1-H05-NOMINATED-LIFECYCLE",),
    "injection_dependent_reload": ("F1-H05-NOMINATED-LIFECYCLE",),
    "checkpoint_field_loss": ("F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP",),
    "bundle_field_loss": ("F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP",),
    "identity_insensitive": ("F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",),
    "forbidden_import": ("F1-H10-OWNERSHIP-BOUNDARY",),
    "forbidden_path": ("F1-H10-OWNERSHIP-BOUNDARY",),
    "copy_mutation": ("F1-H10-OWNERSHIP-BOUNDARY",),
    "architecture_owned_boundary": ("F1-H10-OWNERSHIP-BOUNDARY",),
}

def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 JSON with one trailing LF."""

    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def build_lifecycle_probe_inputs(
    *, seed: int
) -> tuple[dict[str, dict[str, str]], dict[str, bytes]]:
    """Build the two canonical evaluator-owned F1 lifecycle inputs."""

    if type(seed) is not int or not 0 <= seed <= 2_147_483_647:
        raise ValueError("lifecycle seed must be a 31-bit non-negative integer")
    payloads = {
        "base_config": canonical_json_bytes(
            {
                "schema_version": "es-f1-base-config.v1",
                "N": 64,
                "batch_size": 1,
                "device": "cpu",
                "epochs": 1,
                "fno_blocks": 3,
                "fno_cnn_blocks": 1,
                "fno_modes": 2,
                "fno_width": 4,
                "gridsize": 1,
                "measurement_domain": "normalized_amplitude",
                "n_filters_scale": 1,
                "n_groups": 1,
                "object_big": False,
                "probe_big": False,
                "scale_contract_version": "legacy_v1",
            }
        ),
        "cdi_fixture": canonical_json_bytes(
            {
                "schema_version": "es-f1-cdi-fixture.v1",
                "diffraction_generator": "numpy-default-rng-random-float32.v1",
                "image_size": 64,
                "probe_generator": "complex-ones.v1",
                "sample_count": 3,
                "seed": seed,
            }
        ),
    }
    paths = {
        "base_config": "evaluator-inputs/base-config.json",
        "cdi_fixture": "evaluator-inputs/cdi-fixture.json",
    }
    bindings = {
        name: {
            "path": paths[name],
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        }
        for name, payload in payloads.items()
    }
    return bindings, payloads


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def load_controller_asset(
    path: Path,
    *,
    expected_schema_version: str,
) -> dict[str, Any]:
    """Load one exact, closed controller record and reject ambiguous bytes."""

    raw = path.read_bytes()
    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid JSON scalar {token!r}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON asset {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("controller asset must be a JSON object")
    if raw != canonical_json_bytes(parsed):
        raise ValueError("controller asset bytes are not canonical LF JSON")
    version = parsed.get("schema_version")
    if version != expected_schema_version:
        raise ValueError(
            f"schema_version mismatch: expected {expected_schema_version!r}, got {version!r}"
        )
    allowed = _TOP_LEVEL_FIELDS.get(expected_schema_version)
    if allowed is None:
        raise ValueError(f"unsupported controller schema {expected_schema_version!r}")
    unexpected = set(parsed) - allowed
    missing = allowed - set(parsed)
    if unexpected or missing:
        raise ValueError(
            "controller asset field set is not exact; "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return parsed


class EvaluatorError(RuntimeError):
    """The controller could not produce a trusted evaluator observation."""


class EvaluatorObservationError(EvaluatorError):
    """A controller-owned mechanism produced one typed failed observation."""

    def __init__(
        self,
        *,
        clause_id: str,
        mechanism: str,
        evidence: Mapping[str, Any],
        detail: str,
    ) -> None:
        if clause_id not in HARD_CLAUSE_IDS:
            raise ValueError(f"unknown evaluator observation clause {clause_id!r}")
        if not isinstance(mechanism, str) or not mechanism:
            raise ValueError("evaluator observation mechanism must be non-empty")
        if not isinstance(evidence, Mapping):
            raise ValueError("evaluator observation evidence must be an object")
        if not isinstance(detail, str) or not detail:
            raise ValueError("evaluator observation detail must be non-empty")
        self.clause_id = clause_id
        self.mechanism = mechanism
        self.evidence_record = dict(evidence)
        self.observation_detail = detail
        super().__init__(f"{mechanism}: {detail}")

    def as_observation(self) -> dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "satisfied": False,
            "evidence": [
                _digest(
                    {
                        "mechanism": self.mechanism,
                        "evidence": self.evidence_record,
                    }
                )
            ],
            "details": self.observation_detail,
        }


_FORBIDDEN_IMPORT_PREFIXES = (
    "ptycho.evaluation",
    "ptycho.FRC",
    "PtychoNN",
    "notebooks.archive.ePIE_recon_simulation",
    "scripts.orchestration",
)
_FORBIDDEN_PATH_FRAGMENTS = (
    "/home/ollie/Documents/PtychoPINN",
    "/.claude/",
    "/PtychoNN/",
    "/notebooks/archive/ePIE_recon_simulation/",
    "/ptycho/FRC/",
    "/scripts/orchestration/",
)

_AUDITED_ADAPTER_WRAPPER = r'''import json,os,pathlib,platform,runpy,sys
platform.processor()
events=[]
recording=True
workspace=pathlib.Path(sys.argv[5]).resolve(strict=True)
bootstrap=pathlib.Path(sys.argv[6]).resolve(strict=True)
read_only_workspaces=(workspace,bootstrap)
mutation_specs={
    "os.rename":((0,2),(1,3)),"os.remove":((0,1),),
    "os.link":((0,2),(1,3)),"os.symlink":((0,None),(1,2)),
    "os.mkdir":((0,2),),"os.rmdir":((0,1),),
    "os.chmod":((0,2),),"os.chown":((0,3),),
    "os.utime":((0,3),),"os.truncate":((0,None),),
    "os.setxattr":((0,None),),"os.removexattr":((0,None),),
}
def resolve_operand(value,dir_fd):
    if isinstance(value,int):
        return pathlib.Path(os.readlink("/proc/self/fd/"+str(value))).resolve(strict=False)
    if isinstance(value,bytes): value=value.decode(errors="replace")
    if not isinstance(value,str): raise TypeError("mutation path operand is not path-like")
    candidate=pathlib.Path(value)
    if candidate.is_absolute(): return candidate.resolve(strict=False)
    if dir_fd in (None,-1): base=pathlib.Path.cwd()
    elif isinstance(dir_fd,int): base=pathlib.Path(os.readlink("/proc/self/fd/"+str(dir_fd)))
    else: raise TypeError("mutation dir_fd is malformed")
    return (base/candidate).resolve(strict=False)
def audit(event,args):
    if not recording:
        return
    if event == "import" and args:
        events.append({"event":"import","value":str(args[0])})
    elif event in {"open","os.listdir","os.scandir"} and args:
        value=args[0]
        if isinstance(value,(str,bytes)):
            decoded=value.decode(errors="replace") if isinstance(value,bytes) else value
            events.append({"event":"path","value":decoded})
            if event=="open":
                mode=args[1] if len(args)>1 else None
                flags=args[2] if len(args)>2 else None
                writing=(isinstance(mode,str) and any(token in mode for token in "wax+")) or (isinstance(flags,int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
                if writing:
                    candidate=pathlib.Path(decoded)
                    if not candidate.is_absolute(): candidate=pathlib.Path.cwd()/candidate
                    resolved=candidate.resolve(strict=False)
                    if any(resolved.is_relative_to(root) for root in read_only_workspaces):
                        events.append({"event":"workspace_write_attempt","value":str(resolved)})
                        raise PermissionError("candidate workspace is evaluator-read-only")
    elif event in mutation_specs:
        resolved=[]
        try:
            for value_index,dir_fd_index in mutation_specs[event]:
                dir_fd=None if dir_fd_index is None else args[dir_fd_index]
                resolved.append(resolve_operand(args[value_index],dir_fd))
        except (IndexError,OSError,RuntimeError,TypeError,ValueError) as exc:
            events.append({"event":"protected_path_mutation_attempt","value":event+":unresolved:"+type(exc).__name__})
            raise PermissionError("candidate mutation target could not be resolved")
        protected=sorted({str(path) for path in resolved if any(path.is_relative_to(root) for root in read_only_workspaces)})
        if protected:
            events.append({"event":"protected_path_mutation_attempt","value":event+":"+"|".join(protected)})
            raise PermissionError("candidate workspace is evaluator-read-only")
    elif event in {"subprocess.Popen","os.system","os.posix_spawn","os.posix_spawnp","os.exec","os.fork","os.forkpty","pty.spawn"}:
        value=str(args[0]) if args else event
        events.append({"event":"unaudited_child_process","value":value})
        raise PermissionError("candidate child process is outside the evaluator audit boundary")
sys.addaudithook(audit)
adapter,request,result,audit_path=sys.argv[1:5]
sys.argv=[adapter,"--request",request,"--result",result]
sys.path.insert(0,str(workspace))
try:
    runpy.run_path(adapter,run_name="__main__")
finally:
    recording=False
    with open(audit_path,"w",encoding="utf-8",newline="\n") as stream:
        json.dump({"events":events},stream,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        stream.write("\n")
'''

_AUDITED_PROJECTION_WRAPPER = r'''import hashlib,json,os,pathlib,platform,runpy,sys
# Evaluator-owned deterministic dependency initialization: NumPy 1.x probes
# SVE support with lscpu while importing numpy.testing.
if os.environ.get("ES_F1_PRELOAD_NUMPY_TESTING")=="1":
    import numpy.testing
platform.processor()
approved_python_executable=sys.executable
events=[]
recording=True
read_only_workspaces=tuple(pathlib.Path(value).resolve(strict=True) for value in json.loads(sys.argv[1]))
protected_roots_literal=sys.argv[1]
program=pathlib.Path(sys.argv[2]).resolve(strict=True)
audit_path=pathlib.Path(sys.argv[3])
candidate_workspace=pathlib.Path(sys.argv[4]).resolve(strict=True)
program_cwd=pathlib.Path(sys.argv[5]).resolve(strict=True)
forbidden_imports=("ptycho.evaluation","ptycho.FRC","PtychoNN","notebooks.archive.ePIE_recon_simulation","scripts.orchestration")
forbidden_paths=("/home/ollie/Documents/PtychoPINN","/.claude/","/PtychoNN/","/notebooks/archive/ePIE_recon_simulation/","/ptycho/FRC/","/scripts/orchestration/")
child_events={"subprocess.Popen","os.system","os.posix_spawn","os.posix_spawnp","os.exec","os.fork","os.forkpty","pty.spawn"}
mutation_specs={
    "os.rename":((0,2),(1,3)),"os.remove":((0,1),),
    "os.link":((0,2),(1,3)),"os.symlink":((0,None),(1,2)),
    "os.mkdir":((0,2),),"os.rmdir":((0,1),),
    "os.chmod":((0,2),),"os.chown":((0,3),),
    "os.utime":((0,3),),"os.truncate":((0,None),),
    "os.setxattr":((0,None),),"os.removexattr":((0,None),),
}
nested_wrapper_literal=os.environ.get("ES_F1_NESTED_WRAPPER")
controlled_root_literal=os.environ.get("ES_F1_CONTROLLED_CHILD_ROOT")
controlled_digest_literal=os.environ.get("ES_F1_CONTROLLED_CHILD_SHA256")
controlled_specs_literal=os.environ.get("ES_F1_CONTROLLED_CHILD_SPECS","{}")
controlled_specs=json.loads(controlled_specs_literal)
baseline_child_environment=dict(os.environ)
def exact_string_dict(value):
    return type(value) is dict and all(type(key) is str and type(item) is str for key,item in value.items())
def resolve_operand(value,dir_fd):
    if isinstance(value,int):
        return pathlib.Path(os.readlink("/proc/self/fd/"+str(value))).resolve(strict=False)
    if isinstance(value,bytes): value=value.decode(errors="replace")
    if not isinstance(value,str): raise TypeError("mutation path operand is not path-like")
    candidate=pathlib.Path(value)
    if candidate.is_absolute(): return candidate.resolve(strict=False)
    if dir_fd in (None,-1): base=pathlib.Path.cwd()
    elif isinstance(dir_fd,int): base=pathlib.Path(os.readlink("/proc/self/fd/"+str(dir_fd)))
    else: raise TypeError("mutation dir_fd is malformed")
    return (base/candidate).resolve(strict=False)
def controlled_child(args):
    if len(args)!=4 or type(args[0]) is not str: return False
    argv=args[1]
    if type(argv) is not list or len(argv)!=9 or any(type(value) is not str for value in argv): return False
    if type(nested_wrapper_literal) is not str or type(protected_roots_literal) is not str: return False
    expected=[approved_python_executable,"-B","-c",nested_wrapper_literal,protected_roots_literal]
    if argv[:5]!=expected or args[0]!=approved_python_executable: return False
    child_root=controlled_root_literal
    if type(child_root) is not str or not child_root: return False
    root=pathlib.Path(child_root).resolve(strict=True)
    try:
        child_program=pathlib.Path(argv[5]).resolve(strict=True)
        child_audit=pathlib.Path(argv[6]).resolve(strict=False)
    except (OSError,RuntimeError): return False
    if not child_program.is_file() or not child_program.is_relative_to(root) or not child_audit.is_relative_to(root): return False
    spec=controlled_specs.get(str(child_program))
    if type(spec) is not dict or any(type(key) is not str for key in spec) or set(spec)!={"audit_path","cwd","environment_updates"}: return False
    if type(spec["audit_path"]) is not str or type(spec["cwd"]) is not str or not exact_string_dict(spec["environment_updates"]): return False
    if spec["audit_path"]!=str(child_audit): return False
    if argv[7]!=str(candidate_workspace) or argv[8]!=spec["cwd"]: return False
    expected_digest=controlled_digest_literal
    if type(expected_digest) is not str or not expected_digest or hashlib.sha256(child_program.read_bytes()).hexdigest()!=expected_digest: return False
    child_cwd=args[2]
    if type(child_cwd) is not str or pathlib.Path(child_cwd).resolve(strict=True)!=pathlib.Path(spec["cwd"]).resolve(strict=True): return False
    child_env=args[3]
    if not exact_string_dict(baseline_child_environment) or not exact_string_dict(child_env): return False
    expected_env={**baseline_child_environment,**spec["environment_updates"]}
    if not exact_string_dict(expected_env) or child_env!=expected_env: return False
    del controlled_specs[str(child_program)]
    return True
def audit(event,args):
    if not recording: return
    if event=="import" and args:
        value=str(args[0])
        if any(value==prefix or value.startswith(prefix+".") for prefix in forbidden_imports):
            events.append({"event":"forbidden_import","value":value})
            raise PermissionError("candidate import is excluded")
    elif event in {"open","os.listdir","os.scandir"} and args:
        value=args[0]
        if not isinstance(value,(str,bytes)): return
        decoded=value.decode(errors="replace") if isinstance(value,bytes) else value
        candidate=pathlib.Path(decoded)
        if not candidate.is_absolute(): candidate=pathlib.Path.cwd()/candidate
        resolved=candidate.resolve(strict=False)
        rendered=str(resolved)
        if any(fragment in rendered for fragment in forbidden_paths):
            events.append({"event":"forbidden_path","value":rendered})
            raise PermissionError("candidate path is excluded")
        if event=="open":
            mode=args[1] if len(args)>1 else None
            flags=args[2] if len(args)>2 else None
            writing=(isinstance(mode,str) and any(token in mode for token in "wax+")) or (isinstance(flags,int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
            if writing and any(resolved.is_relative_to(root) for root in read_only_workspaces):
                events.append({"event":"workspace_write_attempt","value":rendered})
                raise PermissionError("candidate workspace is evaluator-read-only")
    elif event in mutation_specs:
        resolved=[]
        try:
            for value_index,dir_fd_index in mutation_specs[event]:
                dir_fd=None if dir_fd_index is None else args[dir_fd_index]
                resolved.append(resolve_operand(args[value_index],dir_fd))
        except (IndexError,OSError,RuntimeError,TypeError,ValueError) as exc:
            events.append({"event":"protected_path_mutation_attempt","value":event+":unresolved:"+type(exc).__name__})
            raise PermissionError("candidate mutation target could not be resolved")
        protected=sorted({str(path) for path in resolved if any(path.is_relative_to(root) for root in read_only_workspaces)})
        if protected:
            events.append({"event":"protected_path_mutation_attempt","value":event+":"+"|".join(protected)})
            raise PermissionError("candidate workspace is evaluator-read-only")
    elif event in child_events:
        if event=="subprocess.Popen" and controlled_child(args): return
        value=str(args[0]) if args else event
        events.append({"event":"unaudited_child_process","value":value})
        raise PermissionError("candidate child process is outside the evaluator audit boundary")
sys.addaudithook(audit)
sys.argv=[str(program)]
sys.path.insert(0,str(candidate_workspace))
os.chdir(program_cwd)
try:
    runpy.run_path(str(program),run_name="__main__")
finally:
    recording=False
    with open(audit_path,"w",encoding="utf-8",newline="\n") as stream:
        json.dump({"events":events},stream,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        stream.write("\n")
'''

_VISIBLE_CHECK_PROBE = r'''import json,os,pathlib,runpy,sys
product=pathlib.Path(os.environ["ES_F1_VISIBLE_PRODUCT_ROOT"]).resolve(strict=True)
selectors=set(json.loads(os.environ["ES_F1_VISIBLE_SELECTORS"]))
argv=json.loads(os.environ["ES_F1_VISIBLE_ARGV"])
for index,value in enumerate(argv):
    path,separator,node=value.partition("::")
    if path in selectors:
        argv[index]=str(product/path)+(separator+node if separator else "")
sys.path.insert(0,str(product))
sys.argv=argv
runpy.run_module("pytest",run_name="__main__")
'''

_REGISTRY_SIGNATURE_PROBE = r'''import gc,hashlib,importlib,json,os,pathlib,sys
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
report=pathlib.Path(os.environ["ES_F1_REPORT"])
editable_prefix="__editable___ptychopinn_"
sys.meta_path[:]=[hook for hook in sys.meta_path if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path_hooks[:]=[hook for hook in sys.path_hooks if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path[:]=[value for value in sys.path if not str(value).startswith("__editable__.ptychopinn-")]
sys.path_importer_cache.clear()
for name in tuple(sys.modules):
    if name.startswith(editable_prefix):
        sys.modules.pop(name,None)
sys.path.insert(0,str(workspace))

import torch
from ptycho.config.config import ModelConfig as CanonicalModelConfig
from ptycho.config.config import TrainingConfig as CanonicalTrainingConfig
from ptycho_torch.application_factory import build_ptychopinn_application
from ptycho_torch.config_bridge import to_model_config
from ptycho_torch.config_params import DataConfig,InferenceConfig,ModelConfig,TrainingConfig
from ptycho_torch.generators.registry import _REGISTRY,resolve_generator
from ptycho_torch.model_spec import derive_model_spec

def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def fq(value):
    kind=type(value)
    return kind.__module__+"."+kind.__qualname__
def state_signature(model):
    return [
        {"dtype":str(value.dtype).removeprefix("torch."),"name":name,"shape":list(value.shape)}
        for name,value in sorted(model.state_dict().items())
    ]

rows=[]
builtin_architectures=json.loads(os.environ["ES_F1_BUILTIN_ARCHITECTURES"])
if not isinstance(builtin_architectures,list) or len(set(builtin_architectures))!=len(builtin_architectures): raise RuntimeError("frozen built-in selector is malformed")
if any(architecture not in _REGISTRY for architecture in builtin_architectures): raise RuntimeError("frozen built-in architecture is missing")
for architecture in builtin_architectures:
    image_size=128 if architecture=="neuralop_uno" else 64
    data=DataConfig(N=image_size,C=1,grid_size=(1,1),probe_scale=4.0)
    model=ModelConfig(
        architecture=architecture,C_model=1,C_forward=1,object_big=False,
        probe_big=False,n_filters_scale=1,fno_width=4,fno_modes=2,
        fno_blocks=3,fno_cnn_blocks=1,hybrid_resnet_blocks=1,
        hybrid_downsample_steps=1,spectral_bottleneck_blocks=1,
        spectral_bottleneck_modes=2,
    )
    training=TrainingConfig(device="cpu",torch_loss_mode="poisson")
    inference=InferenceConfig()
    canonical_model=to_model_config(data,model)
    canonical_training=CanonicalTrainingConfig(
        model=CanonicalModelConfig(N=image_size,gridsize=1,architecture=architecture)
    )
    configs={"data_config":data,"model_config":model,"training_config":training,"inference_config":inference}
    torch.manual_seed(1717)
    public=resolve_generator(canonical_training).build_model(configs)
    torch.manual_seed(1717)
    persisted=build_ptychopinn_application(
        derive_model_spec(canonical_model,model,data),data,training,inference
    )
    public_impl=fq(public.model.autoencoder)
    persisted_impl=fq(persisted.model.autoencoder)
    public_state=state_signature(public)
    persisted_state=state_signature(persisted)
    if public_impl!=persisted_impl or public_state!=persisted_state:
        raise RuntimeError("public/persisted construction mismatch for "+architecture)
    rows.append({
        "N":image_size,
        "architecture":architecture,
        "implementation_identity":public_impl,
        "parameter_count":sum(value.numel() for value in public.state_dict().values()),
        "state_entry_count":len(public_state),
        "state_signature":"sha256:"+hashlib.sha256(canonical(public_state)).hexdigest(),
    })
    del public,persisted
    gc.collect()

forbidden_prefixes=("ptycho.evaluation","ptycho.FRC","PtychoNN","notebooks.archive.ePIE_recon_simulation","scripts.orchestration")
forbidden=sorted(name for name in sys.modules if any(name==prefix or name.startswith(prefix+".") for prefix in forbidden_prefixes))
outside=[]
for name,module in tuple(sys.modules.items()):
    if not (name=="ptycho" or name.startswith("ptycho.") or name=="ptycho_torch" or name.startswith("ptycho_torch.")):
        continue
    origins=[]
    spec=getattr(module,"__spec__",None)
    origin=getattr(spec,"origin",None)
    if isinstance(origin,str): origins.append(origin)
    module_file=getattr(module,"__file__",None)
    if isinstance(module_file,str): origins.append(module_file)
    for value in origins:
        path=pathlib.Path(value)
        if path.is_absolute() and not path.resolve(strict=False).is_relative_to(workspace):
            outside.append([name,str(path.resolve(strict=False))])
cache=sorted(
    path.relative_to(workspace).as_posix() for path in workspace.rglob("*")
    if path.name=="__pycache__" or path.suffix in {".pyc",".pyo"}
)
payload={
    "schema_version":"es-f1-registry-signature-probe.v1",
    "registry_baseline":rows,
    "loaded_forbidden_modules":forbidden,
    "outside_project_origin_rows":sorted(outside),
    "cache_artifacts":cache,
}
report.write_bytes(canonical(payload))
'''

_FRESH_RELOAD_PROBE = r'''import copy,hashlib,importlib,json,os,pathlib,sys
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
report=pathlib.Path(os.environ["ES_F1_CHILD_REPORT"])
editable_prefix="__editable___ptychopinn_"
sys.meta_path[:]=[hook for hook in sys.meta_path if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path_hooks[:]=[hook for hook in sys.path_hooks if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path[:]=[value for value in sys.path if not str(value).startswith("__editable__.ptychopinn-")]
sys.path_importer_cache.clear()
for name in tuple(sys.modules):
    if name.startswith(editable_prefix): sys.modules.pop(name,None)
sys.path.insert(0,str(workspace))
import torch
from ptycho_torch.config_bridge import to_model_config
from ptycho_torch.model_spec import ModelSpec,derive_model_spec
mode=os.environ["ES_F1_RELOAD_MODE"]
artifact=pathlib.Path(os.environ["ES_F1_RELOAD_ARTIFACT"])
structural_fields=json.loads(os.environ.get("ES_F1_STRUCTURAL_FIELDS","[]"))
if mode=="checkpoint":
    from ptycho_torch.model import PtychoPINN_Lightning
    model=PtychoPINN_Lightning.load_from_checkpoint(artifact,map_location="cpu")
    roles=[]
else:
    from ptycho_torch.workflows.components import load_inference_bundle_torch
    models,_=load_inference_bundle_torch(artifact)
    roles=sorted(models)
    model=models["diffraction_to_obj"]
def canonical(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def fq(value): return type(value).__module__+"."+type(value).__qualname__
def callable_owner(value):
    target=getattr(value,"__func__",value)
    return target.__module__+"."+target.__qualname__
def boundary_owners(value):
    return {
        "compute_loss":callable_owner(value.compute_loss),
        "loss_forward":callable_owner(value.Loss.forward),
        "model_forward":callable_owner(value.model.forward),
        "physics_forward":callable_owner(value.model.forward_model.forward),
        "scaling":callable_owner(value.model.scaler.scale),
    }
def boundary_contract(value):
    return {
        "loss_function":value.model_config.loss_function,
        "measurement_domain":value.data_config.measurement_domain,
        "physics_forward_mode":value.model_config.physics_forward_mode,
        "scale_contract_version":value.data_config.scale_contract_version,
        "torch_loss_mode":value.training_config.torch_loss_mode,
    }
def tensor_record(value):
    item=value.detach().cpu().contiguous()
    return {"dtype":str(item.dtype).removeprefix("torch."),"shape":list(item.shape),"sha256":"sha256:"+hashlib.sha256(item.numpy().tobytes()).hexdigest()}
def input_digest(values):
    return "sha256:"+hashlib.sha256(canonical({name:tensor_record(value) for name,value in sorted(values.items())})).hexdigest()
def state_signature(value):
    rows=[{"dtype":str(item.dtype).removeprefix("torch."),"name":name,"shape":list(item.shape)} for name,item in sorted(value.state_dict().items())]
    return "sha256:"+hashlib.sha256(canonical(rows)).hexdigest()
def keyed_values(value,key):
    rows=[]
    if isinstance(value,dict):
        for name,item in value.items():
            if name==key: rows.append(item)
            rows.extend(keyed_values(item,key))
    elif isinstance(value,list):
        for item in value: rows.extend(keyed_values(item,key))
    return rows
def consistent_value(value,key):
    rows=keyed_values(value,key)
    if not rows or any(type(item) is not type(rows[0]) or item!=rows[0] for item in rows[1:]):
        raise RuntimeError("retained ModelSpec identity binding is absent or ambiguous")
    return rows[0]
torch.manual_seed(20260802)
x=torch.rand((1,1,64,64),dtype=torch.float32)
positions=torch.zeros((1,1,1,2),dtype=torch.float32)
probe=torch.ones((1,1,1,64,64),dtype=torch.complex64)
scale=torch.ones((1,1,1,1),dtype=torch.float32)
boundary_inputs={"images":x,"positions":positions,"probe":probe,"input_scale_factor":scale}
boundary_input_digest_before=input_digest(boundary_inputs)
with torch.no_grad(): prediction=model.forward_predict(x,positions,probe,scale)
boundary_input_digest_after=input_digest(boundary_inputs)
forbidden_prefixes=("ptycho.evaluation","ptycho.FRC","PtychoNN","notebooks.archive.ePIE_recon_simulation","scripts.orchestration")
forbidden=sorted(name for name in sys.modules if any(name==prefix or name.startswith(prefix+".") for prefix in forbidden_prefixes))
outside=[]
for name,module in tuple(sys.modules.items()):
    if not (name=="ptycho" or name.startswith("ptycho.") or name=="ptycho_torch" or name.startswith("ptycho_torch.")): continue
    values=[]
    origin=getattr(getattr(module,"__spec__",None),"origin",None)
    if isinstance(origin,str): values.append(origin)
    module_file=getattr(module,"__file__",None)
    if isinstance(module_file,str): values.append(module_file)
    for value in values:
        path=pathlib.Path(value)
        if path.is_absolute() and not path.resolve(strict=False).is_relative_to(workspace): outside.append([name,str(path.resolve(strict=False))])
retained_model_spec_payload=model.hparams.get("model_spec")
if isinstance(retained_model_spec_payload,dict):
    model_spec=ModelSpec.from_payload(copy.deepcopy(retained_model_spec_payload))
else:
    model_spec=derive_model_spec(
        to_model_config(model.data_config,model.model_config),
        model.model_config,model.data_config,
        parity_scale_mode=getattr(model,"parity_scale_mode","off"),
        parity_fixed_delta=float(model.hparams.get("parity_fixed_delta",0.0)),
        parity_init_scheme=model.hparams.get("parity_init_scheme","default"),
    )
model_spec_payload=model_spec.to_payload()
payload={"architecture_id":model_spec.architecture,"boundary_contract":boundary_contract(model),"boundary_input_digest_after":boundary_input_digest_after,"boundary_input_digest_before":boundary_input_digest_before,"boundary_owners":boundary_owners(model),"fresh_pid":os.getpid(),"implementation_identity":fq(model.model.autoencoder),"inference_shape":list(prediction.shape),"roles":roles,"state_signature":state_signature(model),"structural_values":{name:consistent_value(model_spec_payload,name) for name in structural_fields},"loaded_forbidden_modules":forbidden,"outside_project_origin_rows":sorted(outside)}
report.write_bytes((json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8"))
'''

_PREEDIT_LIFECYCLE_PROBE = r'''import hashlib,importlib,json,os,pathlib,subprocess,sys
child_launch_environment=dict(os.environ)
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
output=pathlib.Path(os.environ["ES_F1_OUTPUT"]).resolve(strict=False)
report=pathlib.Path(os.environ["ES_F1_REPORT"])
child_code=os.environ["ES_F1_CHILD_CODE"]
output.mkdir(parents=True,exist_ok=True)
editable_prefix="__editable___ptychopinn_"
sys.meta_path[:]=[hook for hook in sys.meta_path if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path_hooks[:]=[hook for hook in sys.path_hooks if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path[:]=[value for value in sys.path if not str(value).startswith("__editable__.ptychopinn-")]
sys.path_importer_cache.clear()
for name in tuple(sys.modules):
    if name.startswith(editable_prefix): sys.modules.pop(name,None)
sys.path.insert(0,str(workspace))

import numpy as np
import torch
from lightning.pytorch import Trainer
from ptycho.config.config import PyTorchExecutionConfig
from ptycho.raw_data import RawData
from ptycho_torch.application_factory import build_ptychopinn_application
from ptycho_torch.artifact_schema import encode_artifact_identity,to_json_payload
from ptycho_torch.config_factory import create_training_payload
from ptycho_torch.generators.registry import resolve_generator
from ptycho_torch.workflows.components import run_cdi_example_torch

def canonical(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def fq(value): return type(value).__module__+"."+type(value).__qualname__
def state_signature(model):
    rows=[{"dtype":str(value.dtype).removeprefix("torch."),"name":name,"shape":list(value.shape)} for name,value in sorted(model.state_dict().items())]
    return "sha256:"+hashlib.sha256(canonical(rows)).hexdigest()

data_path=output/"train.npz"
rng=np.random.default_rng(20260802)
diffraction=rng.random((3,64,64),dtype=np.float32)
probe_guess=np.ones((64,64),dtype=np.complex64)
np.savez(data_path,diffraction=diffraction,probeGuess=probe_guess)
payload=create_training_payload(
    data_path,output/"training",
    overrides={
        "N":64,"n_groups":1,"gridsize":1,"architecture":"ffno",
        "fno_width":4,"fno_modes":2,"fno_blocks":3,"fno_cnn_blocks":1,
        "n_filters_scale":1,"object_big":False,"probe_big":False,
        "batch_size":1,"epochs":1,"device":"cpu",
        "scale_contract_version":"legacy_v1","measurement_domain":"normalized_amplitude",
    },
)
configs={"data_config":payload.pt_data_config,"model_config":payload.pt_model_config,"training_config":payload.pt_training_config,"inference_config":payload.pt_inference_config}
torch.manual_seed(20260802)
public=resolve_generator(payload.tf_training_config).build_model(configs)
torch.manual_seed(20260802)
persisted=build_ptychopinn_application(payload.model_spec,payload.pt_data_config,payload.pt_training_config,payload.pt_inference_config)
public_impl=fq(public.model.autoencoder)
persisted_impl=fq(persisted.model.autoencoder)
public_state=state_signature(public)
persisted_state=state_signature(persisted)
if public_impl!=persisted_impl or public_state!=persisted_state: raise RuntimeError("public/persisted construction mismatch")

torch.manual_seed(20260802)
images=torch.rand((1,1,64,64),dtype=torch.float32)
positions=torch.zeros((1,1,1,2),dtype=torch.float32)
probe=torch.ones((1,1,1,64,64),dtype=torch.complex64)
rms=torch.ones((1,1,1,1),dtype=torch.float32)
physics=torch.ones((1,1,1,1),dtype=torch.float32)
experiment=torch.zeros(1,dtype=torch.long)
scale=torch.ones(1,dtype=torch.float32)
batch=({"images":images,"coords_relative":positions,"rms_scaling_constant":rms,"physics_scaling_constant":physics,"experiment_id":experiment},probe,scale)
persisted.train()
prediction,_,_=persisted(images,positions,probe,rms,rms,experiment)
loss=persisted.compute_loss(batch)
optimizer=persisted.configure_optimizers()["optimizer"]
tracked=next(parameter for parameter in persisted.parameters() if parameter.requires_grad)
before=tracked.detach().clone()
optimizer.zero_grad(); loss.backward(); optimizer.step()
changed=not torch.equal(before,tracked.detach())

checkpoint=output/"representative.ckpt"
trainer=Trainer(max_epochs=0,enable_checkpointing=True,logger=False,enable_progress_bar=False,accelerator="cpu",default_root_dir=output)
trainer.strategy._lightning_module=persisted
trainer.save_checkpoint(checkpoint)
coords=np.arange(3,dtype=np.float64)
raw_data=RawData(
    xcoords=coords,ycoords=coords,xcoords_start=coords,ycoords_start=coords,
    diff3d=diffraction,probeGuess=probe_guess,scan_index=np.arange(3,dtype=int),
)
execution=PyTorchExecutionConfig(
    accelerator="cpu",deterministic=True,num_workers=0,
    enable_progress_bar=False,enable_checkpointing=False,logger_backend=None,
)
torch.manual_seed(20260802)
_,_,workflow_results=run_cdi_example_torch(
    raw_data,None,payload.tf_training_config,do_stitching=False,
    execution_config=execution,
    overrides={
        "scale_contract_version":"legacy_v1",
        "measurement_domain":"normalized_amplitude",
    },
)
bundle_model=workflow_results["models"]["diffraction_to_obj"]
bundle_impl=fq(bundle_model.model.autoencoder)
if bundle_impl!=persisted_impl: raise RuntimeError("public bundle implementation mismatch")
bundle_dir=pathlib.Path(payload.tf_training_config.output_dir)
if not (bundle_dir/"wts.h5.zip").is_file(): raise RuntimeError("public workflow produced no bundle")

def reload(mode,artifact,name):
    child_report=output/(name+".json")
    child_program=output/(name+"-program.py")
    child_audit=output/(name+"-audit.json")
    child_program.write_text(child_code,encoding="utf-8",newline="\n")
    spec=json.loads(os.environ["ES_F1_CONTROLLED_CHILD_SPECS"])[str(child_program)]
    env=dict(child_launch_environment); env.update(spec["environment_updates"])
    proc=subprocess.run([sys.executable,"-B","-c",os.environ["ES_F1_NESTED_WRAPPER"],os.environ["ES_F1_PROTECTED_ROOTS"],str(child_program),str(child_audit),str(workspace),spec["cwd"]],cwd=spec["cwd"],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    nested=json.loads(child_audit.read_bytes()) if child_audit.is_file() else {"events":[]}
    if nested.get("events"): raise RuntimeError("fresh "+mode+" crossed candidate-process audit boundary")
    if proc.returncode!=0: raise RuntimeError("fresh "+mode+" reload failed: "+proc.stderr)
    return json.loads(child_report.read_bytes())
checkpoint_result=reload("checkpoint",checkpoint,"checkpoint-reload")
bundle_result=reload("bundle",bundle_dir,"bundle-reload")
identity=to_json_payload(encode_artifact_identity(payload.model_spec,payload.pt_data_config,payload.pt_training_config,payload.pt_inference_config))
structural_identity="sha256:"+hashlib.sha256(canonical(identity)).hexdigest()

forbidden_prefixes=("ptycho.evaluation","ptycho.FRC","PtychoNN","notebooks.archive.ePIE_recon_simulation","scripts.orchestration")
forbidden=sorted(set(name for name in sys.modules if any(name==prefix or name.startswith(prefix+".") for prefix in forbidden_prefixes))|set(checkpoint_result["loaded_forbidden_modules"])|set(bundle_result["loaded_forbidden_modules"]))
outside=[]
for name,module in tuple(sys.modules.items()):
    if not (name=="ptycho" or name.startswith("ptycho.") or name=="ptycho_torch" or name.startswith("ptycho_torch.")): continue
    values=[]
    origin=getattr(getattr(module,"__spec__",None),"origin",None)
    if isinstance(origin,str): values.append(origin)
    module_file=getattr(module,"__file__",None)
    if isinstance(module_file,str): values.append(module_file)
    for value in values:
        path=pathlib.Path(value)
        if path.is_absolute() and not path.resolve(strict=False).is_relative_to(workspace): outside.append([name,str(path.resolve(strict=False))])
outside.extend(checkpoint_result["outside_project_origin_rows"]); outside.extend(bundle_result["outside_project_origin_rows"])
cache=sorted(path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.name=="__pycache__" or path.suffix in {".pyc",".pyo"})
result={
    "schema_version":"es-f1-preedit-lifecycle-probe.v1","architecture":"ffno",
    "construction_pid":os.getpid(),"public_implementation":public_impl,
    "persisted_implementation":persisted_impl,"public_state_signature":public_state,
    "persisted_state_signature":persisted_state,"structural_identity":structural_identity,
    "forward_shape":list(prediction.shape),"loss_finite":bool(torch.isfinite(loss).item()),
    "optimizer_changed_parameter":changed,"checkpoint_reload":checkpoint_result,
    "bundle_persistence_route":"ptycho_torch.workflows.components.run_cdi_example_torch",
    "bundle_implementation":bundle_impl,"bundle_reload":bundle_result,
    "loaded_forbidden_modules":forbidden,
    "outside_project_origin_rows":sorted({tuple(row) for row in outside}),"cache_artifacts":cache,
}
report.write_bytes(canonical(result))
'''

_SEMANTIC_LIFECYCLE_PROBE = r'''import copy,hashlib,importlib,json,os,pathlib,subprocess,sys
child_launch_environment=dict(os.environ)
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
output=pathlib.Path(os.environ["ES_F1_OUTPUT"]).resolve(strict=False)
report=pathlib.Path(os.environ["ES_F1_REPORT"])
child_code=os.environ["ES_F1_CHILD_CODE"]
evidence=json.loads(pathlib.Path(os.environ["ES_F1_CANDIDATE_EVIDENCE"]).read_bytes())
base=json.loads(pathlib.Path(os.environ["ES_F1_BASE_CONFIG"]).read_bytes())
fixture=json.loads(pathlib.Path(os.environ["ES_F1_CDI_FIXTURE"]).read_bytes())
seed=int(os.environ["ES_F1_SEED"])
output.mkdir(parents=True,exist_ok=True)
editable_prefix="__editable___ptychopinn_"
sys.meta_path[:]=[hook for hook in sys.meta_path if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path_hooks[:]=[hook for hook in sys.path_hooks if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path[:]=[value for value in sys.path if not str(value).startswith("__editable__.ptychopinn-")]
sys.path_importer_cache.clear()
for name in tuple(sys.modules):
    if name.startswith(editable_prefix): sys.modules.pop(name,None)
sys.path.insert(0,str(workspace))

import numpy as np
import torch
from lightning.pytorch import Trainer
from ptycho.config.config import ModelConfig as CanonicalModelConfig,PyTorchExecutionConfig,TrainingConfig as CanonicalTrainingConfig
from ptycho.raw_data import RawData
from ptycho_torch.artifact_schema import decode_artifact_identity,encode_artifact_identity,from_json_payload,to_json_payload
from ptycho_torch.config_factory import create_training_payload
from ptycho_torch.model_spec import ModelSpec
from ptycho_torch.workflows.components import run_cdi_example_torch

def canonical(value): return (json.dumps(value,allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def fq(value): return type(value).__module__+"."+type(value).__qualname__
def callable_owner(value):
    target=getattr(value,"__func__",value)
    return target.__module__+"."+target.__qualname__
def boundary_owners(value):
    return {
        "compute_loss":callable_owner(value.compute_loss),
        "loss_forward":callable_owner(value.Loss.forward),
        "model_forward":callable_owner(value.model.forward),
        "physics_forward":callable_owner(value.model.forward_model.forward),
        "scaling":callable_owner(value.model.scaler.scale),
    }
def boundary_contract(value):
    return {
        "loss_function":value.model_config.loss_function,
        "measurement_domain":value.data_config.measurement_domain,
        "physics_forward_mode":value.model_config.physics_forward_mode,
        "scale_contract_version":value.data_config.scale_contract_version,
        "torch_loss_mode":value.training_config.torch_loss_mode,
    }
def tensor_record(value):
    item=value.detach().cpu().contiguous()
    return {"dtype":str(item.dtype).removeprefix("torch."),"shape":list(item.shape),"sha256":"sha256:"+hashlib.sha256(item.numpy().tobytes()).hexdigest()}
def input_digest(values):
    return "sha256:"+hashlib.sha256(canonical({name:tensor_record(value) for name,value in sorted(values.items())})).hexdigest()
def state_signature(model):
    rows=[{"dtype":str(value.dtype).removeprefix("torch."),"name":name,"shape":list(value.shape)} for name,value in sorted(model.state_dict().items())]
    return "sha256:"+hashlib.sha256(canonical(rows)).hexdigest()
def identity_digest(value): return "sha256:"+hashlib.sha256(canonical(value)).hexdigest()
def operation_failure(stage,exc,audit_events=None):
    detail=str(exc)
    payload={"schema_version":"es-f1-semantic-lifecycle-failure.v1","stage":stage,"exception_type":type(exc).__name__,"exception_detail_sha256":"sha256:"+hashlib.sha256(detail.encode("utf-8")).hexdigest()}
    if audit_events is not None: payload["audit_events"]=audit_events
    report.write_bytes(canonical(payload))
    raise SystemExit(0)
def resolve_route(route):
    if not isinstance(route,str) or not route or route.startswith(".") or route.endswith(".") or ".." in route:
        raise ValueError("declared route is malformed")
    parts=route.split(".")
    module=None
    split_at=0
    for index in range(len(parts),0,-1):
        try:
            module=importlib.import_module(".".join(parts[:index]))
        except ModuleNotFoundError as exc:
            if exc.name!=".".join(parts[:index]): raise
            continue
        split_at=index
        break
    if module is None: raise ValueError("declared route module does not exist")
    target=module
    for name in parts[split_at:]: target=getattr(target,name)
    if not callable(target): raise TypeError("declared route is not callable")
    return target

structural_rows=evidence["structural_fields"]
structural_names=[row["name"] for row in structural_rows]
baseline={row["name"]:row["baseline_value"] for row in structural_rows}
alternate={row["name"]:row["alternate_value"] for row in structural_rows}
if len(set(structural_names))!=len(structural_names): raise RuntimeError("declared structural fields are not unique")
common={name:value for name,value in base.items() if name!="schema_version"}
rng=np.random.default_rng(fixture["seed"])
diffraction=rng.random((fixture["sample_count"],fixture["image_size"],fixture["image_size"]),dtype=np.float32)
probe_guess=np.ones((fixture["image_size"],fixture["image_size"]),dtype=np.complex64)
data_path=output/"train.npz"
np.savez(data_path,diffraction=diffraction,probeGuess=probe_guess)
coords=np.arange(fixture["sample_count"],dtype=np.float64)
raw_data=RawData(xcoords=coords,ycoords=coords,xcoords_start=coords,ycoords_start=coords,diff3d=diffraction,probeGuess=probe_guess,scan_index=np.arange(fixture["sample_count"],dtype=int))
execution=PyTorchExecutionConfig(accelerator="cpu",deterministic=True,num_workers=0,enable_progress_bar=False,enable_checkpointing=False,logger_backend=None)

def make_payload(architecture,directory):
    overrides={**common,"architecture":architecture}
    return create_training_payload(data_path,directory,overrides=overrides,execution_config=execution)

def keyed_paths(value,key,path=()):
    rows=[]
    if isinstance(value,dict):
        for name,item in value.items():
            child=path+(name,)
            if name==key: rows.append(child)
            rows.extend(keyed_paths(item,key,child))
    elif isinstance(value,list):
        for index,item in enumerate(value): rows.extend(keyed_paths(item,key,path+(index,)))
    return rows
def value_at(value,path):
    target=value
    for part in path: target=target[part]
    return target
def parent_at(value,path):
    target=value
    for part in path[:-1]: target=target[part]
    return target
def consistent_binding(value,key,expected,error="declared structural field location is absent or ambiguous"):
    paths=keyed_paths(value,key)
    if not paths: raise RuntimeError(error)
    observed=[value_at(value,path) for path in paths]
    if any(type(item) is not type(expected) or item!=expected for item in observed):
        raise RuntimeError(error)
    return paths,observed[0]
def reload(mode,artifact,name):
    child_report=output/(name+".json")
    child_program=output/(name+"-program.py")
    child_audit=output/(name+"-audit.json")
    child_program.write_text(child_code,encoding="utf-8",newline="\n")
    spec=json.loads(os.environ["ES_F1_CONTROLLED_CHILD_SPECS"])[str(child_program)]
    env=dict(child_launch_environment); env.update(spec["environment_updates"])
    proc=subprocess.run([sys.executable,"-B","-c",os.environ["ES_F1_NESTED_WRAPPER"],os.environ["ES_F1_PROTECTED_ROOTS"],str(child_program),str(child_audit),str(workspace),spec["cwd"]],cwd=spec["cwd"],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    nested=json.loads(child_audit.read_bytes()) if child_audit.is_file() else {"events":[]}
    if nested.get("events"):
        operation_failure("OWNERSHIP_BOUNDARY",RuntimeError("nested candidate-process audit rejected the reload"),nested["events"])
    if proc.returncode!=0: raise RuntimeError("fresh "+mode+" reload failed: "+proc.stderr)
    return json.loads(child_report.read_bytes())

identities={}
model_spec_payloads={}
structural_paths_by_role={}
roles={}
resolved_routes={}
for role,architecture_key in (("representative","representative_architecture"),("witness","witness_architecture")):
    declaration=evidence[architecture_key]
    architecture=declaration["public_id"]
    try:
        construction_route=resolve_route(declaration["construction_route"])
        persisted_rebuild_route=resolve_route(declaration["persisted_rebuild_route"])
    except Exception as exc:
        operation_failure("ROUTE_RESOLUTION",exc)
    resolved_routes[role]={"construction":construction_route,"persisted":persisted_rebuild_route}
    role_output=output/role
    payload=make_payload(architecture,role_output/"configuration")
    public_model_spec_payload=payload.model_spec.to_payload()
    role_structural_paths={}
    role_structural_values={}
    if payload.model_spec.architecture!=architecture: raise RuntimeError("public ModelSpec architecture identity drifted")
    if role=="witness":
        for name in structural_names:
            paths,value=consistent_binding(public_model_spec_payload,name,baseline[name])
            role_structural_paths[name]=paths
            role_structural_values[name]=value
    configs={"data_config":payload.pt_data_config,"model_config":payload.pt_model_config,"training_config":payload.pt_training_config,"inference_config":payload.pt_inference_config}
    torch.manual_seed(seed)
    try:
        public=construction_route(payload.tf_training_config).build_model(configs)
    except Exception as exc:
        operation_failure("PUBLIC_BUILD",exc)
    torch.manual_seed(seed)
    try:
        persisted=persisted_rebuild_route(payload.model_spec,payload.pt_data_config,payload.pt_training_config,payload.pt_inference_config)
    except Exception as exc:
        operation_failure("PERSISTED_BUILD",exc)
    public_impl=fq(public.model.autoencoder)
    persisted_impl=fq(persisted.model.autoencoder)
    public_state=state_signature(public)
    persisted_state=state_signature(persisted)
    torch.manual_seed(seed)
    images=torch.rand((1,1,fixture["image_size"],fixture["image_size"]),dtype=torch.float32)
    positions=torch.zeros((1,1,1,2),dtype=torch.float32)
    probe=torch.ones((1,1,1,fixture["image_size"],fixture["image_size"]),dtype=torch.complex64)
    rms=torch.ones((1,1,1,1),dtype=torch.float32)
    physics=torch.ones((1,1,1,1),dtype=torch.float32)
    experiment=torch.zeros(1,dtype=torch.long)
    scale=torch.ones(1,dtype=torch.float32)
    batch=({"images":images,"coords_relative":positions,"rms_scaling_constant":rms,"physics_scaling_constant":physics,"experiment_id":experiment},probe,scale)
    boundary_inputs={"experiment_id":experiment,"images":images,"input_scale_factor":rms,"output_scale_factor":rms,"physics_scaling_constant":physics,"positions":positions,"probe":probe,"probe_scaling":scale}
    boundary_input_digest_before=input_digest(boundary_inputs)
    persisted.train()
    prediction,_,_=persisted(images,positions,probe,rms,rms,experiment)
    loss=persisted.compute_loss(batch)
    optimizer=persisted.configure_optimizers()["optimizer"]
    tracked=next(parameter for parameter in persisted.parameters() if parameter.requires_grad)
    before=tracked.detach().clone()
    optimizer.zero_grad(); loss.backward(); optimizer.step()
    changed=not torch.equal(before,tracked.detach())
    boundary_input_digest_after=input_digest(boundary_inputs)
    checkpoint=role_output/"evaluator.ckpt"
    checkpoint.parent.mkdir(parents=True,exist_ok=True)
    trainer=Trainer(max_epochs=0,enable_checkpointing=True,logger=False,enable_progress_bar=False,accelerator="cpu",default_root_dir=role_output)
    trainer.strategy._lightning_module=persisted
    trainer.save_checkpoint(checkpoint)
    torch.manual_seed(seed)
    _,_,workflow_results=run_cdi_example_torch(raw_data,None,payload.tf_training_config,do_stitching=False,execution_config=execution,overrides={"scale_contract_version":base["scale_contract_version"],"measurement_domain":base["measurement_domain"]})
    bundle_model=workflow_results["models"]["diffraction_to_obj"]
    bundle_dir=pathlib.Path(payload.tf_training_config.output_dir)
    bundle_path=bundle_dir/"wts.h5.zip"
    if not bundle_path.is_file(): raise RuntimeError("public workflow produced no bundle")
    checkpoint_reload=reload("checkpoint",checkpoint,role+"-checkpoint-reload")
    bundle_reload=reload("bundle",bundle_dir,role+"-bundle-reload")
    identity=to_json_payload(encode_artifact_identity(payload.model_spec,payload.pt_data_config,payload.pt_training_config,payload.pt_inference_config))
    decoded=decode_artifact_identity(from_json_payload(identity))
    rebuilt=persisted_rebuild_route(decoded.model_spec,decoded.data_config,decoded.training_config,decoded.inference_config)
    identities[role]=identity
    model_spec_payloads[role]=public_model_spec_payload
    structural_paths_by_role[role]=role_structural_paths
    roles[role]={"architecture_id":payload.model_spec.architecture,"construction_route":declaration["construction_route"],"persisted_rebuild_route":declaration["persisted_rebuild_route"],"boundary_contract":boundary_contract(persisted),"boundary_input_digest_after":boundary_input_digest_after,"boundary_input_digest_before":boundary_input_digest_before,"persisted_boundary_owners":boundary_owners(persisted),"public_boundary_owners":boundary_owners(public),"public_implementation":public_impl,"persisted_implementation":persisted_impl,"public_state_signature":public_state,"persisted_state_signature":persisted_state,"forward_shape":list(prediction.shape),"loss_finite":bool(torch.isfinite(loss).item()),"optimizer_changed_parameter":changed,"structural_values":role_structural_values,"bundle_implementation":fq(bundle_model.model.autoencoder),"persisted_rebuild_implementation":fq(rebuilt.model.autoencoder),"evaluator_checkpoint_reload":checkpoint_reload,"evaluator_bundle_reload":bundle_reload}

decoded_witness=decode_artifact_identity(from_json_payload(identities["witness"]))
witness_model_spec_payload=model_spec_payloads["witness"]
witness_builder=resolved_routes["witness"]["persisted"]
structural_paths=structural_paths_by_role["witness"]

sensitivity={}
for field in structural_names:
    baseline_identity=identities["witness"]
    alt_model_spec_payload=copy.deepcopy(witness_model_spec_payload)
    for path in structural_paths[field]:
        parent_at(alt_model_spec_payload,path)[path[-1]]=alternate[field]
    consistent_binding(alt_model_spec_payload,field,alternate[field])
    alt_model_spec=ModelSpec.from_payload(copy.deepcopy(alt_model_spec_payload))
    alt_identity=to_json_payload(encode_artifact_identity(alt_model_spec,decoded_witness.data_config,decoded_witness.training_config,decoded_witness.inference_config))
    alt_model_spec_repeat=ModelSpec.from_payload(copy.deepcopy(alt_model_spec_payload))
    alt_identity_repeat=to_json_payload(encode_artifact_identity(alt_model_spec_repeat,decoded_witness.data_config,decoded_witness.training_config,decoded_witness.inference_config))
    baseline_digest=identity_digest(baseline_identity)
    alternate_digest=identity_digest(alt_identity)
    sensitivity[field]={"alternate_digest":alternate_digest,"baseline_digest":baseline_digest,"changed":baseline_digest!=alternate_digest,"deterministic":alt_identity==alt_identity_repeat}

def rejection(model_spec_payload):
    try:
        model_spec=ModelSpec.from_payload(copy.deepcopy(model_spec_payload))
        witness_builder(model_spec,decoded_witness.data_config,decoded_witness.training_config,decoded_witness.inference_config)
    except Exception as exc:
        detail=str(exc)
        exception_type=type(exc).__name__
        return {"exception_detail_sha256":"sha256:"+hashlib.sha256(detail.encode("utf-8")).hexdigest(),"exception_type":exception_type,"module_returned":False,"rejected":True}
    return {"exception_detail_sha256":"sha256:"+hashlib.sha256(b"").hexdigest(),"exception_type":None,"module_returned":True,"rejected":False}
def unsupported(value):
    if type(value) is bool: return None
    if isinstance(value,(int,float)) and not isinstance(value,bool): return 0 if value!=0 else -1
    if isinstance(value,str): return "es_f1_unsupported_value"
    return None

missing={}
for field in structural_names:
    value=copy.deepcopy(witness_model_spec_payload)
    for path in structural_paths[field]: parent_at(value,path).pop(path[-1])
    missing[field]=rejection(value)
extra=copy.deepcopy(witness_model_spec_payload)
structural_containers={path[:-1] for paths in structural_paths.values() for path in paths}
for path in structural_containers: value_at(extra,path)["es_f1_extra_structural_field"]=1
try:
    unknown_training=CanonicalTrainingConfig(model=CanonicalModelConfig(architecture="es_f1_unknown_architecture"))
    unknown_generator=resolved_routes["witness"]["construction"](unknown_training)
    unknown_generator.build_model(configs)
except Exception as exc:
    detail=str(exc)
    unknown_rejection={"exception_detail_sha256":"sha256:"+hashlib.sha256(detail.encode("utf-8")).hexdigest(),"exception_type":type(exc).__name__,"module_returned":False,"rejected":True}
else:
    unknown_rejection={"exception_detail_sha256":"sha256:"+hashlib.sha256(b"").hexdigest(),"exception_type":None,"module_returned":True,"rejected":False}
unsupported_value=copy.deepcopy(witness_model_spec_payload)
unsupported_field=structural_names[0]
for path in structural_paths[unsupported_field]:
    unsupported_parent=parent_at(unsupported_value,path)
    unsupported_parent[path[-1]]=unsupported(unsupported_parent[path[-1]])
rejections={"missing":missing,"extra":rejection(extra),"unknown_architecture":unknown_rejection,"unsupported_value":rejection(unsupported_value)}
forbidden_prefixes=("ptycho.evaluation","ptycho.FRC","PtychoNN","notebooks.archive.ePIE_recon_simulation","scripts.orchestration")
forbidden=sorted(set(name for name in sys.modules if any(name==prefix or name.startswith(prefix+".") for prefix in forbidden_prefixes))|set().union(*(set(value["evaluator_checkpoint_reload"]["loaded_forbidden_modules"])|set(value["evaluator_bundle_reload"]["loaded_forbidden_modules"]) for value in roles.values())))
outside=[]
for name,module in tuple(sys.modules.items()):
    if not (name=="ptycho" or name.startswith("ptycho.") or name=="ptycho_torch" or name.startswith("ptycho_torch.")): continue
    values=[]
    origin=getattr(getattr(module,"__spec__",None),"origin",None)
    if isinstance(origin,str): values.append(origin)
    module_file=getattr(module,"__file__",None)
    if isinstance(module_file,str): values.append(module_file)
    for value in values:
        path=pathlib.Path(value)
        if path.is_absolute() and not path.resolve(strict=False).is_relative_to(workspace): outside.append([name,str(path.resolve(strict=False))])
for value in roles.values(): outside.extend(value["evaluator_checkpoint_reload"]["outside_project_origin_rows"]); outside.extend(value["evaluator_bundle_reload"]["outside_project_origin_rows"])
cache=sorted(path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.name=="__pycache__" or path.suffix in {".pyc",".pyo"})
result={"schema_version":"es-f1-semantic-lifecycle.v1","construction_pid":os.getpid(),"declared_structural_fields":structural_names,"roles":roles,"identity_rejections":rejections,"identity_sensitivity":sensitivity,"loaded_forbidden_modules":forbidden,"outside_project_origin_rows":sorted({tuple(row) for row in outside}),"cache_artifacts":cache}
report.write_bytes(canonical(result))
'''

_ARTIFACT_FIXTURE_BUILD_PROBE = r'''import hashlib,io,json,os,pathlib,sys,zipfile
from dataclasses import asdict
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
output=pathlib.Path(os.environ["ES_F1_OUTPUT"]).resolve(strict=True)
report=pathlib.Path(os.environ["ES_F1_REPORT"])
editable_prefix="__editable___ptychopinn_"
sys.meta_path[:]=[hook for hook in sys.meta_path if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path_hooks[:]=[hook for hook in sys.path_hooks if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path[:]=[value for value in sys.path if not str(value).startswith("__editable__.ptychopinn-")]
sys.path_importer_cache.clear()
for name in tuple(sys.modules):
    if name.startswith(editable_prefix): sys.modules.pop(name,None)
sys.path.insert(0,str(workspace))

import dill
import torch
from lightning.pytorch import Trainer
from ptycho.config.config import ModelConfig as CanonicalModelConfig
from ptycho.config.config import TrainingConfig as CanonicalTrainingConfig
from ptycho_torch.application_factory import build_ptychopinn_application
from ptycho_torch.artifact_schema import ARTIFACT_SCHEMA_V1_VERSION,CURRENT_ARTIFACT_SCHEMA_VERSION,ARTIFACT_V1_DATA_FIELDS,ARTIFACT_V1_TRAINING_FIELDS,ARTIFACT_V1_INFERENCE_FIELDS,encode_artifact_identity,to_json_payload
from ptycho_torch.config_bridge import to_model_config
from ptycho_torch.config_params import DataConfig,InferenceConfig,ModelConfig,TrainingConfig
from ptycho_torch.model import PtychoPINN_Lightning
from ptycho_torch.model_manager import create_torch_model_with_gridsize,save_torch_bundle
from ptycho_torch.model_spec import MODEL_SPEC_V1_MODEL_FIELDS,derive_model_spec

def canonical(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def write_json(name,value):
    path=output/name
    path.write_bytes(canonical(to_json_payload(value)))
    return path
def v1_spec(spec):
    model=spec.to_model_config()
    return {
        "schema_version":"torch-model-spec-v1",
        "model_config":{name:getattr(model,name) for name in MODEL_SPEC_V1_MODEL_FIELDS},
        "parity_scale_mode":spec.parity_scale_mode,
        "parity_fixed_delta":spec.parity_fixed_delta,
        "parity_init_scheme":spec.parity_init_scheme,
    }
def subset(value,names): return {name:getattr(value,name) for name in names}
def save_checkpoint(model,path):
    trainer=Trainer(max_epochs=0,enable_checkpointing=True,logger=False,enable_progress_bar=False,accelerator="cpu",default_root_dir=output)
    trainer.strategy._lightning_module=model
    trainer.save_checkpoint(path)
def replace_bundle_metadata(path,*,metadata=None,artifact_schema=None):
    with zipfile.ZipFile(path,"r") as archive:
        members={info.filename:archive.read(info.filename) for info in archive.infolist() if info.filename not in {"manifest.dill","torch_scaling_metadata.pt"}}
        manifest=dill.loads(archive.read("manifest.dill"))
    if artifact_schema is None:
        manifest.pop("artifact_schema_version",None)
    else:
        manifest.update(backend="pytorch",artifact_schema_version=artifact_schema)
    temporary=path.with_suffix(path.suffix+".tmp")
    with zipfile.ZipFile(temporary,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.dill",dill.dumps(manifest))
        for name in sorted(members): archive.writestr(name,members[name])
        if metadata is not None:
            buffer=io.BytesIO(); torch.save(metadata,buffer)
            archive.writestr("torch_scaling_metadata.pt",buffer.getvalue())
    os.replace(temporary,path)

data=DataConfig(N=64,C=1,grid_size=(1,1),probe_scale=4.0)
model=ModelConfig(architecture="ffno",C_model=1,C_forward=1,n_filters_scale=1,fno_width=4,fno_modes=2,fno_blocks=3,fno_cnn_blocks=1,object_big=False,probe_big=False)
training=TrainingConfig(device="cpu",torch_loss_mode="poisson")
inference=InferenceConfig()
canonical_model=CanonicalModelConfig(N=64,gridsize=1,architecture="ffno",n_filters_scale=1,fno_width=4,fno_modes=2,fno_blocks=3,fno_cnn_blocks=1,object_big=False,probe_big=False)
spec=derive_model_spec(to_model_config(data,model),model,data)
model_v1=v1_spec(spec)
model_v2=spec.to_payload()
artifact_v2=encode_artifact_identity(spec,data,training,inference)
artifact_v1={
    "backend":"pytorch","schema_version":ARTIFACT_SCHEMA_V1_VERSION,
    "model_spec":model_v1,"data_config":subset(data,ARTIFACT_V1_DATA_FIELDS),
    "training_config":subset(training,ARTIFACT_V1_TRAINING_FIELDS),
    "inference_config":subset(inference,ARTIFACT_V1_INFERENCE_FIELDS),
    "ci_statistics":None,
}
paths={
    "torch-model-spec-v1":write_json("torch-model-spec-v1.json",model_v1),
    "torch-model-spec-v2":write_json("torch-model-spec-v2.json",model_v2),
    "torch-artifact-v1":write_json("torch-artifact-v1.json",artifact_v1),
    "torch-artifact-v2":write_json("torch-artifact-v2.json",artifact_v2),
}

torch.manual_seed(20260802)
legacy_checkpoint_model=PtychoPINN_Lightning(model_config=model,data_config=data,training_config=training,inference_config=inference)
legacy_checkpoint=output/"legacy-config-only.ckpt"
save_checkpoint(legacy_checkpoint_model,legacy_checkpoint)
torch.manual_seed(20260802)
current_model=build_ptychopinn_application(spec,data,training,inference)
current_checkpoint=output/"current-model-spec-v2.ckpt"
save_checkpoint(current_model,current_checkpoint)
paths["legacy-config-only-checkpoint"]=legacy_checkpoint
paths["current-model-spec-v2-checkpoint"]=current_checkpoint

legacy_config=CanonicalTrainingConfig(
    model=CanonicalModelConfig(N=64,gridsize=1,model_type="pinn"),
    train_data_file=output/"unused.npz",n_groups=1,neighbor_count=1,
    nepochs=0,output_dir=output/"metadata-free-legacy",
)
legacy_params={"N":64,"gridsize":1,"model_type":"pinn"}
torch.manual_seed(20260802)
legacy_bundle_model=create_torch_model_with_gridsize(1,64,legacy_params)
legacy_dir=output/"metadata-free-legacy"; legacy_base=legacy_dir/"wts.h5"
save_torch_bundle({"autoencoder":legacy_bundle_model,"diffraction_to_obj":legacy_bundle_model},str(legacy_base),legacy_config)
legacy_bundle=legacy_base.with_suffix(".h5.zip")
replace_bundle_metadata(legacy_bundle)
paths["metadata-free-legacy-bundle"]=legacy_bundle

current_config=CanonicalTrainingConfig(
    model=canonical_model,train_data_file=output/"unused.npz",n_groups=1,
    neighbor_count=1,nepochs=0,output_dir=output,
)
transitional={
    "schema_version":"ci-entrypoints-v1","data_config":asdict(data),
    "model_config":asdict(current_model.model_config),
    "training_config":asdict(training),"inference_config":asdict(inference),
    "ci_statistics":None,
}
for era,metadata,schema in (
    ("transitional-ci-entrypoints-v1-bundle",transitional,None),
    ("torch-artifact-v1-bundle",artifact_v1,ARTIFACT_SCHEMA_V1_VERSION),
    ("torch-artifact-v2-bundle",artifact_v2,CURRENT_ARTIFACT_SCHEMA_VERSION),
):
    directory=output/era; base=directory/"wts.h5"
    save_torch_bundle({"autoencoder":current_model,"diffraction_to_obj":current_model},str(base),current_config)
    bundle=base.with_suffix(".h5.zip")
    replace_bundle_metadata(bundle,metadata=metadata,artifact_schema=schema)
    paths[era]=bundle

rows=[]
for era in (
    "torch-model-spec-v1","torch-model-spec-v2","torch-artifact-v1","torch-artifact-v2",
    "legacy-config-only-checkpoint","current-model-spec-v2-checkpoint",
    "metadata-free-legacy-bundle","transitional-ci-entrypoints-v1-bundle",
    "torch-artifact-v1-bundle","torch-artifact-v2-bundle",
):
    path=paths[era]
    rows.append({"era_id":era,"kind":"json" if path.suffix==".json" else ("checkpoint" if path.suffix==".ckpt" else "bundle"),"path":path.relative_to(output).as_posix()})
report.write_bytes(canonical({"schema_version":"es-f1-artifact-fixture-build.v1","artifact_eras":rows}))
'''

_ARTIFACT_FIXTURE_VERIFY_PROBE = r'''import json,os,pathlib,shutil,sys,tempfile
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
rows_path=pathlib.Path(os.environ["ES_F1_FIXTURE_ROWS"])
report=pathlib.Path(os.environ["ES_F1_REPORT"])
editable_prefix="__editable___ptychopinn_"
sys.meta_path[:]=[hook for hook in sys.meta_path if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path_hooks[:]=[hook for hook in sys.path_hooks if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path[:]=[value for value in sys.path if not str(value).startswith("__editable__.ptychopinn-")]
sys.path_importer_cache.clear()
for name in tuple(sys.modules):
    if name.startswith(editable_prefix): sys.modules.pop(name,None)
sys.path.insert(0,str(workspace))

from ptycho.config.config import ModelConfig as CanonicalModelConfig
from ptycho_torch.application_factory import build_ptychopinn_application
from ptycho_torch.artifact_schema import decode_artifact_identity,from_json_payload
from ptycho_torch.config_bridge import to_model_config
from ptycho_torch.config_params import DataConfig,InferenceConfig,ModelConfig,TrainingConfig
from ptycho_torch.model import PtychoPINN_Lightning
from ptycho_torch.model_spec import ModelSpec
from ptycho_torch.workflows.components import load_inference_bundle_torch

def canonical(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def fq(model): return type(model.model.autoencoder).__module__+"."+type(model.model.autoencoder).__qualname__
data=DataConfig(N=64,C=1,grid_size=(1,1),probe_scale=4.0)
model=ModelConfig(architecture="ffno",C_model=1,C_forward=1,n_filters_scale=1,fno_width=4,fno_modes=2,fno_blocks=3,fno_cnn_blocks=1,object_big=False,probe_big=False)
training=TrainingConfig(device="cpu",torch_loss_mode="poisson")
inference=InferenceConfig()
rows=json.loads(rows_path.read_bytes())["artifact_eras"]
observed=[]
with tempfile.TemporaryDirectory(prefix="es-f1-era-load-") as raw_temp:
    temporary=pathlib.Path(raw_temp)
    for row in rows:
        era=row["era_id"]; path=pathlib.Path(row["absolute_path"])
        if era.startswith("torch-model-spec-"):
            payload=from_json_payload(json.loads(path.read_bytes()))
            spec=ModelSpec.from_payload(payload)
            loaded=build_ptychopinn_application(spec,data,training,inference)
            implementation=fq(loaded)
        elif era in {"torch-artifact-v1","torch-artifact-v2"}:
            identity=decode_artifact_identity(from_json_payload(json.loads(path.read_bytes())))
            loaded=build_ptychopinn_application(identity.model_spec,identity.data_config,identity.training_config,identity.inference_config)
            implementation=fq(loaded)
        elif row["kind"]=="checkpoint":
            loaded=PtychoPINN_Lightning.load_from_checkpoint(path,map_location="cpu")
            implementation=fq(loaded)
        else:
            bundle_dir=temporary/era; bundle_dir.mkdir()
            shutil.copyfile(path,bundle_dir/"wts.h5.zip")
            kwargs={}
            if era=="metadata-free-legacy-bundle":
                kwargs={"scale_contract_version":"legacy_v1","measurement_domain":"normalized_amplitude"}
            models,_=load_inference_bundle_torch(bundle_dir,**kwargs)
            if sorted(models)!=["autoencoder","diffraction_to_obj"]: raise RuntimeError("bundle roles drifted")
            implementation=fq(models["diffraction_to_obj"])
        observed.append({"era_id":era,"implementation_identity":implementation,"strict_load":True})

forbidden_prefixes=("ptycho.evaluation","ptycho.FRC","PtychoNN","notebooks.archive.ePIE_recon_simulation","scripts.orchestration")
forbidden=sorted(name for name in sys.modules if any(name==prefix or name.startswith(prefix+".") for prefix in forbidden_prefixes))
outside=[]
for name,module in tuple(sys.modules.items()):
    if not (name=="ptycho" or name.startswith("ptycho.") or name=="ptycho_torch" or name.startswith("ptycho_torch.")): continue
    values=[]
    origin=getattr(getattr(module,"__spec__",None),"origin",None)
    if isinstance(origin,str): values.append(origin)
    module_file=getattr(module,"__file__",None)
    if isinstance(module_file,str): values.append(module_file)
    for value in values:
        path=pathlib.Path(value)
        if path.is_absolute() and not path.resolve(strict=False).is_relative_to(workspace): outside.append([name,str(path.resolve(strict=False))])
cache=sorted(path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.name=="__pycache__" or path.suffix in {".pyc",".pyo"})
report.write_bytes(canonical({"schema_version":"es-f1-artifact-fixture-verification.v1","artifact_eras":observed,"loaded_forbidden_modules":forbidden,"outside_project_origin_rows":sorted(outside),"cache_artifacts":cache}))
'''


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _workspace_digest(root: Path) -> str:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            rows.append(
                {"kind": "symlink", "mode": mode, "path": relative, "target": os.readlink(path)}
            )
        elif path.is_dir():
            rows.append({"kind": "directory", "mode": mode, "path": relative})
        elif path.is_file():
            rows.append(
                {
                    "kind": "file",
                    "mode": mode,
                    "path": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        else:
            raise EvaluatorError(f"unsupported candidate entry type: {relative}")
    return _digest(rows)


def _safe_candidate_path(workspace: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise EvaluatorError("adapter path must be a safe product-relative path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise EvaluatorError("adapter path must be a safe product-relative path")
    resolved_root = workspace.resolve(strict=True)
    resolved = (resolved_root / candidate).resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise EvaluatorError("adapter path escapes candidate workspace") from exc
    if not resolved.is_file():
        raise EvaluatorError("adapter path must name a regular file")
    return resolved


def _load_canonical_unversioned(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid JSON scalar {token!r}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EvaluatorError(f"adapter emitted invalid JSON: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise EvaluatorError("adapter result is not canonical LF JSON")
    return value


def _load_canonical_schema(path: Path) -> dict[str, Any]:
    try:
        schema = _load_canonical_unversioned(path)
        Draft202012Validator.check_schema(schema)
    except EvaluatorError:
        raise
    except (OSError, SchemaError, ValueError) as exc:
        raise EvaluatorError(f"JSON schema is unavailable or invalid: {path}") from exc
    return schema


def _validate_schema_record(
    value: Mapping[str, Any],
    *,
    schema_path: Path,
    label: str,
) -> None:
    schema = _load_canonical_schema(schema_path)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    if errors:
        raise EvaluatorError(f"{label} schema violation: {errors[0].message}")


def _file_sha256(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EvaluatorError(f"bound evaluator asset is unreadable: {path}") from exc


def load_frozen_evaluator_package(
    *,
    visible_contract_path: Path,
    visible_contract_schema_path: Path,
    visible_check_path: Path,
    visible_check_schema_path: Path,
    fixture_manifest_path: Path,
    reviewer_perspectives_path: Path,
) -> dict[str, Any]:
    """Join evaluator assets to the one schema-validated visible task authority."""

    contract = _load_canonical_unversioned(visible_contract_path)
    _validate_schema_record(
        contract,
        schema_path=visible_contract_schema_path,
        label="visible task contract",
    )
    if tuple(row["id"] for row in contract["hard_contract"]) != HARD_CLAUSE_IDS:
        raise EvaluatorError("visible hard-clause vocabulary drifted")
    if tuple(contract["finding_dispositions"]) != DISPOSITIONS:
        raise EvaluatorError("visible finding-disposition vocabulary drifted")
    if tuple(row["id"] for row in contract["reviewer_perspectives"]) != (
        REVIEWER_PERSPECTIVES
    ):
        raise EvaluatorError("visible reviewer-perspective vocabulary drifted")

    check_binding = contract["visible_checks"]
    if _file_sha256(visible_check_path) != check_binding["sha256"]:
        raise EvaluatorError("visible check manifest digest binding drifted")
    if _file_sha256(visible_check_schema_path) != check_binding["schema_sha256"]:
        raise EvaluatorError("visible check schema digest binding drifted")
    checks = _load_canonical_unversioned(visible_check_path)
    _validate_schema_record(
        checks,
        schema_path=visible_check_schema_path,
        label="visible check manifest",
    )
    if checks["invocation_order"] != ["PRE_EDIT_FOCUSED", "CANDIDATE_EXTENSION"]:
        raise EvaluatorError("visible check invocation order drifted")
    by_id = {row["id"]: row for row in checks["invocations"]}
    if set(by_id) != {"PRE_EDIT_FOCUSED", "CANDIDATE_EXTENSION"}:
        raise EvaluatorError("visible check invocation set drifted")
    if by_id["PRE_EDIT_FOCUSED"]["selectors"] != contract["focused_selectors"]:
        raise EvaluatorError("visible focused selector binding drifted")
    if by_id["CANDIDATE_EXTENSION"]["selectors"] != [
        "tests/torch/test_es_f1_extension_boundary.py"
    ]:
        raise EvaluatorError("visible candidate selector binding drifted")
    if _digest(contract["focused_selectors"]) != contract["environment"][
        "focused_selectors_sha256"
    ]:
        raise EvaluatorError("visible focused selector digest drifted")

    perspectives = load_controller_asset(
        reviewer_perspectives_path,
        expected_schema_version="es-f1-reviewer-perspectives.v1",
    )
    expected_perspectives = [
        {
            "owned_dimensions": row["owned_dimensions"],
            "perspective_id": row["id"],
            "responsibility": row["responsibility"],
        }
        for row in contract["reviewer_perspectives"]
    ]
    if perspectives["perspectives"] != expected_perspectives:
        raise EvaluatorError("reviewer perspective asset drifted from visible authority")
    dimensions = [
        dimension
        for row in perspectives["perspectives"]
        for dimension in row["owned_dimensions"]
    ]
    if len(dimensions) != len(set(dimensions)) or set(dimensions) != set(
        contract["review_dimensions"]
    ):
        raise EvaluatorError("reviewer perspective dimension partition is not exact")

    fixtures = load_controller_asset(
        fixture_manifest_path,
        expected_schema_version="es-f1-fixture-manifest.v1",
    )
    if fixtures["hard_clause_ids"] != list(HARD_CLAUSE_IDS):
        raise EvaluatorError("fixture manifest hard-clause binding drifted")
    if fixtures["artifact_fixture_origin"] != {
        "generator": (
            "scripts.experiments.es.f1_evaluator.build_artifact_fixture_pack"
        ),
        "source_projection_commit": (
            "8f191031f233d50a4d020d8a988036e99487f570"
        ),
        "source_projection_tree": "e64f3c05f5a0894f41c047d128a9040a2cda6764",
    }:
        raise EvaluatorError("artifact fixture origin binding drifted")
    calibration_binding = fixtures["calibration_cases"]
    if not isinstance(calibration_binding, Mapping) or set(calibration_binding) != {
        "path",
        "schema_version",
        "sha256",
    }:
        raise EvaluatorError("calibration fixture binding is malformed")
    if calibration_binding["path"] != (
        "tests/experiments/fixtures/es_f1/calibration-cases.json"
    ):
        raise EvaluatorError("calibration fixture path binding drifted")
    calibration_path = _REPOSITORY_ROOT / calibration_binding["path"]
    if (
        calibration_binding["schema_version"] != "es-f1-calibration-cases.v2"
        or _file_sha256(calibration_path) != calibration_binding["sha256"]
    ):
        raise EvaluatorError("calibration fixture digest/schema binding drifted")
    return {
        "fixture_manifest": fixtures,
        "reviewer_perspectives": perspectives,
        "visible_checks": checks,
        "visible_contract": contract,
    }


def run_visible_checks(
    *,
    workspace: Path,
    visible_checks: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute only the schema-bound visible invocations on an immutable copy."""

    if not isinstance(visible_checks, Mapping):
        raise EvaluatorError("visible checks must be an object")
    checks = dict(visible_checks)
    _validate_schema_record(
        checks,
        schema_path=_VISIBLE_CHECK_SCHEMA,
        label="visible check manifest",
    )
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise EvaluatorError("visible check workspace must be a directory")
    runner = checks["runner"]
    python_executable = Path(runner["python_executable"])
    if (
        not python_executable.is_absolute()
        or not python_executable.is_file()
        or _file_sha256(python_executable) != runner["python_executable_sha256"]
    ):
        raise EvaluatorError("visible check Python identity drifted")
    by_id = {row["id"]: row for row in checks["invocations"]}
    if set(by_id) != set(checks["invocation_order"]):
        raise EvaluatorError("visible check invocation join is not exact")
    for invocation in checks["invocations"]:
        for selector in invocation["selectors"]:
            _safe_candidate_path(workspace, selector)
    if (
        runner["execution_copy_policy"] != "disposable-exact-extract.v1"
        or runner["mutation_policy"] != "verify-product-digest-before-after.v1"
        or runner["working_directory_policy"]
        != "external-disposable-invocation-root.v1"
    ):
        raise EvaluatorError("visible check execution policy is unsupported")
    before = _workspace_digest(workspace)
    results: list[dict[str, Any]] = []
    for invocation_id in checks["invocation_order"]:
        invocation = by_id[invocation_id]
        argv = [
            str(python_executable),
            *runner["argv_prefix"],
            *invocation["selectors"],
        ]
        with tempfile.TemporaryDirectory(
            prefix=f"es-f1-visible-{invocation_id.lower()}-"
        ) as raw_temp:
            execution_workspace = Path(raw_temp) / "candidate"
            invocation_workspace = Path(raw_temp) / "invocation"

            def ignore_root_git(directory: str, names: list[str]) -> set[str]:
                if Path(directory).resolve() == workspace and ".git" in names:
                    return {".git"}
                return set()

            shutil.copytree(
                workspace,
                execution_workspace,
                symlinks=True,
                copy_function=shutil.copy2,
                ignore=ignore_root_git,
            )
            invocation_workspace.mkdir()
            execution_before = _workspace_digest(execution_workspace)
            if execution_before != before:
                raise EvaluatorError(
                    "visible check disposable extract does not match the source candidate"
                )
            if _workspace_digest(workspace) != before:
                raise EvaluatorError(
                    "visible check source candidate changed during disposable extraction"
                )
            try:
                process = _run_projection_probe(
                    workspace=execution_workspace,
                    working_directory=invocation_workspace,
                    protected_workspaces=(workspace, execution_workspace),
                    python_executable=python_executable,
                    code=_VISIBLE_CHECK_PROBE,
                    environment={
                        **{
                            row["name"]: row["value"]
                            for row in runner["required_environment"]
                        },
                        "ES_F1_VISIBLE_ARGV": json.dumps(["pytest", *argv[3:]]),
                        "ES_F1_VISIBLE_PRODUCT_ROOT": str(execution_workspace),
                        "ES_F1_VISIBLE_SELECTORS": json.dumps(
                            invocation["selectors"]
                        ),
                        "ES_F1_PRELOAD_NUMPY_TESTING": "1",
                    },
                    timeout_seconds=runner["timeout_seconds"],
                    label=f"visible check invocation {invocation_id}",
                    check_process=False,
                )
            finally:
                source_after_invocation = _workspace_digest(workspace)
                execution_after_invocation = _workspace_digest(
                    execution_workspace
                )
                if source_after_invocation != before:
                    raise EvaluatorObservationError(
                        clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                        mechanism="candidate-source-digest-ratchet",
                        evidence={
                            "copy_digest_before": before,
                            "copy_digest_after": source_after_invocation,
                            "invocation_id": invocation_id,
                        },
                        detail="visible checks mutated the source candidate",
                    )
                if execution_after_invocation != execution_before:
                    raise EvaluatorObservationError(
                        clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                        mechanism="candidate-process-write-audit",
                        evidence={
                            "copy_digest_before": execution_before,
                            "copy_digest_after": execution_after_invocation,
                            "invocation_id": invocation_id,
                        },
                        detail="visible checks mutated the execution product copy",
                    )
        results.append(
            {
                "argv": argv,
                "exit_code": process.returncode,
                "invocation_id": invocation_id,
                "stderr_sha256": "sha256:"
                + hashlib.sha256(process.stderr.encode("utf-8")).hexdigest(),
                "stdout_sha256": "sha256:"
                + hashlib.sha256(process.stdout.encode("utf-8")).hexdigest(),
            }
        )
    after = _workspace_digest(workspace)
    if after != before:
        raise EvaluatorError("visible checks mutated the candidate evaluation copy")
    return {
        "schema_version": "es-f1-visible-check-result.v1",
        "copy_digest_after": after,
        "copy_digest_before": before,
        "invocations": results,
    }


def _safe_external_result_path(root: Path, relative: Any, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise EvaluatorError(f"{label} is not a safe result-relative path")
    path = Path(relative)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise EvaluatorError(f"{label} is not a safe result-relative path")
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)) or not resolved.is_file():
        raise EvaluatorError(f"{label} escaped the evaluator output root")
    return resolved


def _safe_evaluator_input_target(root: Path, relative: Any, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise EvaluatorError(f"{label} is not a safe request-relative path")
    path = Path(relative)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise EvaluatorError(f"{label} is not a safe request-relative path")
    resolved_root = root.resolve(strict=True)
    resolved = (resolved_root / path).resolve(strict=False)
    if not resolved.is_relative_to(resolved_root):
        raise EvaluatorError(f"{label} escaped the evaluator request root")
    return resolved


def _fresh_artifact_semantic_probe(
    *,
    workspace: Path,
    python_executable: Path,
    artifact: Path,
    mode: str,
    report: Path,
    structural_fields: list[str],
    timeout_seconds: int,
    expect_success: bool,
) -> dict[str, Any] | None:
    load_target = artifact.parent if mode == "bundle" and artifact.is_file() else artifact
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(
        {
            "ES_F1_WORKSPACE": str(workspace),
            "ES_F1_CHILD_REPORT": str(report),
            "ES_F1_RELOAD_MODE": mode,
            "ES_F1_RELOAD_ARTIFACT": str(load_target),
            "ES_F1_STRUCTURAL_FIELDS": json.dumps(structural_fields),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PTYCHO_DISABLE_MEMOIZE": "1",
        }
    )
    process = _run_projection_probe(
        workspace=workspace,
        python_executable=python_executable,
        code=_FRESH_RELOAD_PROBE,
        environment=env,
        timeout_seconds=timeout_seconds,
        label=f"semantic lifecycle {mode} probe",
        check_process=False,
    )
    if expect_success:
        if process.returncode != 0:
            raise EvaluatorError(
                f"semantic lifecycle {mode} load failed: "
                f"exit={process.returncode}, stdout={process.stdout!r}, "
                f"stderr={process.stderr!r}"
            )
        if not report.is_file():
            raise EvaluatorError(f"semantic lifecycle {mode} produced no report")
        payload = _load_canonical_unversioned(report)
        if (
            not isinstance(payload.get("fresh_pid"), int)
            or not payload.get("inference_shape")
        ):
            raise EvaluatorError(f"semantic lifecycle {mode} report is incomplete")
        return payload
    if process.returncode == 0:
        raise EvaluatorError(f"semantic lifecycle tampered {mode} artifact was accepted")
    return None


def _verify_adapter_artifacts(
    *,
    workspace: Path,
    python_executable: Path,
    artifacts: Mapping[str, Mapping[str, Path]],
    structural_fields: list[str],
    output_root: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    for role in ("representative", "witness"):
        role_observations: dict[str, Any] = {}
        for kind, mode in (("checkpoint", "checkpoint"), ("bundle", "bundle")):
            artifact = artifacts[role][kind]
            report = output_root / f"{role}-{kind}-fresh-load.json"
            try:
                loaded = _fresh_artifact_semantic_probe(
                    workspace=workspace,
                    python_executable=python_executable,
                    artifact=artifact,
                    mode=mode,
                    report=report,
                    structural_fields=(
                        structural_fields if role == "witness" else []
                    ),
                    timeout_seconds=timeout_seconds,
                    expect_success=True,
                )
            except EvaluatorError as exc:
                raise EvaluatorObservationError(
                    clause_id="F1-H05-NOMINATED-LIFECYCLE",
                    mechanism="fresh-artifact-reload",
                    evidence={
                        "artifact_kind": kind,
                        "artifact_role": role,
                        "error_type": type(exc).__name__,
                        "error_detail_sha256": "sha256:"
                        + hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
                    },
                    detail="a nominated lifecycle artifact failed fresh-process reload",
                ) from exc
            if kind == "bundle":
                tampered = output_root / f"{role}-{kind}-tampered" / "wts.h5.zip"
                tampered.parent.mkdir()
            else:
                tampered = output_root / f"{role}-{kind}-tampered{artifact.suffix}"
            payload = artifact.read_bytes()
            tampered.write_bytes(payload[: max(1, len(payload) // 2)])
            _fresh_artifact_semantic_probe(
                workspace=workspace,
                python_executable=python_executable,
                artifact=tampered,
                mode=mode,
                report=output_root / f"{role}-{kind}-tampered-report.json",
                structural_fields=(structural_fields if role == "witness" else []),
                timeout_seconds=timeout_seconds,
                expect_success=False,
            )
            role_observations[kind] = loaded
        observations[role] = role_observations
    return observations


def _run_semantic_lifecycle_probe(
    *,
    workspace: Path,
    python_executable: Path,
    candidate_evidence: Path,
    base_config: Path,
    cdi_fixture: Path,
    adapter_observations: Mapping[str, Any],
    output_root: Path,
    seed: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    semantic_root = output_root / "evaluator-semantic-lifecycle"
    semantic_root.mkdir(parents=True, exist_ok=False)
    report_path = semantic_root / "report.json"
    child_pairs = tuple(
        (f"{role}-{kind}-reload-program.py", f"{role}-{kind}-reload-audit.json")
        for role in ("representative", "witness")
        for kind in ("checkpoint", "bundle")
    )
    structural_names = [
        row["name"]
        for row in _load_canonical_unversioned(candidate_evidence)["structural_fields"]
    ]
    child_environments: dict[tuple[str, str], dict[str, str]] = {}
    for role in ("representative", "witness"):
        for kind in ("checkpoint", "bundle"):
            name = f"{role}-{kind}-reload"
            pair = (f"{name}-program.py", f"{name}-audit.json")
            artifact = semantic_root / role / (
                "evaluator.ckpt" if kind == "checkpoint" else "configuration"
            )
            child_environments[pair] = {
                "ES_F1_CHILD_REPORT": str(semantic_root / f"{name}.json"),
                "ES_F1_RELOAD_MODE": kind,
                "ES_F1_RELOAD_ARTIFACT": str(artifact),
                "ES_F1_STRUCTURAL_FIELDS": json.dumps(
                    structural_names if role == "witness" else [],
                    separators=(",", ":"),
                ),
                "ES_F1_FRESH_RELOAD": "1",
            }
    _run_projection_probe(
        workspace=workspace,
        controlled_child_root=semantic_root,
        controlled_child_pairs=child_pairs,
        controlled_child_environment_updates=child_environments,
        python_executable=python_executable,
        code=_SEMANTIC_LIFECYCLE_PROBE,
        environment={
            "ES_F1_BASE_CONFIG": str(base_config),
            "ES_F1_CANDIDATE_EVIDENCE": str(candidate_evidence),
            "ES_F1_CDI_FIXTURE": str(cdi_fixture),
            "ES_F1_CHILD_CODE": _FRESH_RELOAD_PROBE,
            "ES_F1_OUTPUT": str(semantic_root),
            "ES_F1_REPORT": str(report_path),
            "ES_F1_SEED": str(seed),
            "ES_F1_WORKSPACE": str(workspace),
        },
        timeout_seconds=timeout_seconds,
        label="semantic lifecycle",
    )
    if not report_path.is_file():
        raise EvaluatorError("semantic lifecycle produced no report")
    report = _load_canonical_unversioned(report_path)
    if report.get("schema_version") == "es-f1-semantic-lifecycle-failure.v1":
        base_failure_fields = {
            "schema_version",
            "stage",
            "exception_type",
            "exception_detail_sha256",
        }
        stage = report.get("stage")
        expected_failure_fields = (
            base_failure_fields | {"audit_events"}
            if stage == "OWNERSHIP_BOUNDARY"
            else base_failure_fields
        )
        if set(report) != expected_failure_fields or stage not in {
            "ROUTE_RESOLUTION",
            "PUBLIC_BUILD",
            "PERSISTED_BUILD",
            "OWNERSHIP_BOUNDARY",
        }:
            raise EvaluatorError("semantic lifecycle failure report is malformed")
        if (
            not isinstance(report.get("exception_type"), str)
            or not report["exception_type"]
            or not isinstance(report.get("exception_detail_sha256"), str)
            or not report["exception_detail_sha256"].startswith("sha256:")
            or len(report["exception_detail_sha256"]) != 71
        ):
            raise EvaluatorError("semantic lifecycle failure evidence is malformed")
        if stage == "OWNERSHIP_BOUNDARY":
            audit_events = report.get("audit_events")
            if (
                not isinstance(audit_events, list)
                or not audit_events
                or any(
                    not isinstance(row, Mapping)
                    or set(row) != {"event", "value"}
                    or row.get("event")
                    not in {
                        "forbidden_import",
                        "forbidden_path",
                        "unaudited_child_process",
                        "workspace_write_attempt",
                    }
                    or not isinstance(row.get("value"), str)
                    or not row["value"]
                    for row in audit_events
                )
            ):
                raise EvaluatorError("semantic lifecycle nested audit is malformed")
            raise EvaluatorObservationError(
                clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                mechanism="nested-candidate-process-audit",
                evidence=report,
                detail="fresh reload crossed an excluded candidate-process boundary",
            )
        raise EvaluatorObservationError(
            clause_id="F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
            mechanism={
                "ROUTE_RESOLUTION": "declared-construction-route-resolution",
                "PUBLIC_BUILD": "declared-public-construction-boundary",
                "PERSISTED_BUILD": "declared-persisted-construction-boundary",
            }[stage],
            evidence=report,
            detail="a declared public construction route did not construct the nominated architecture",
        )
    if set(report) != {
        "schema_version",
        "construction_pid",
        "declared_structural_fields",
        "roles",
        "identity_rejections",
        "identity_sensitivity",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    } or report.get("schema_version") != "es-f1-semantic-lifecycle.v1":
        raise EvaluatorError("semantic lifecycle report is not exact")
    roles = report.get("roles")
    if not isinstance(roles, Mapping) or set(roles) != {"representative", "witness"}:
        raise EvaluatorError("semantic lifecycle role set is incomplete or ambiguous")
    for role in ("representative", "witness"):
        observed = roles[role]
        if not isinstance(observed, dict):
            raise EvaluatorError("semantic lifecycle role observation is malformed")
        checkpoint = adapter_observations[role]["checkpoint"]
        bundle = adapter_observations[role]["bundle"]
        observed["adapter_checkpoint_reload"] = checkpoint
        observed["adapter_bundle_reload"] = bundle
    return report


def derive_lifecycle_observations(
    *,
    semantic_report: Mapping[str, Any],
    adapter_process_id: int,
) -> list[dict[str, Any]]:
    """Derive F1-H05..H10 solely from evaluator-owned lifecycle mechanics."""

    roles = semantic_report.get("roles")
    if not isinstance(roles, Mapping) or set(roles) != {"representative", "witness"}:
        raise EvaluatorError("semantic lifecycle roles are not exact")
    construction_pid = semantic_report.get("construction_pid")
    if type(construction_pid) is not int or construction_pid <= 0:
        raise EvaluatorError("semantic lifecycle construction process is malformed")

    top_level_keys = {
        "schema_version",
        "construction_pid",
        "declared_structural_fields",
        "roles",
        "identity_rejections",
        "identity_sensitivity",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    }
    if (
        set(semantic_report) != top_level_keys
        or semantic_report.get("schema_version") != "es-f1-semantic-lifecycle.v1"
        or not isinstance(semantic_report.get("loaded_forbidden_modules"), list)
        or not isinstance(semantic_report.get("outside_project_origin_rows"), list)
        or not isinstance(semantic_report.get("cache_artifacts"), list)
    ):
        raise EvaluatorError("semantic lifecycle report shape is malformed")

    def digest_shape(value: Any) -> bool:
        return (
            isinstance(value, str)
            and value.startswith("sha256:")
            and len(value) == 71
        )

    role_keys = {
        "architecture_id",
        "construction_route",
        "persisted_rebuild_route",
        "boundary_contract",
        "boundary_input_digest_after",
        "boundary_input_digest_before",
        "persisted_boundary_owners",
        "public_boundary_owners",
        "public_implementation",
        "persisted_implementation",
        "public_state_signature",
        "persisted_state_signature",
        "forward_shape",
        "loss_finite",
        "optimizer_changed_parameter",
        "structural_values",
        "bundle_implementation",
        "persisted_rebuild_implementation",
        "evaluator_checkpoint_reload",
        "evaluator_bundle_reload",
        "adapter_checkpoint_reload",
        "adapter_bundle_reload",
    }
    reload_keys = {
        "architecture_id",
        "boundary_contract",
        "boundary_input_digest_after",
        "boundary_input_digest_before",
        "boundary_owners",
        "fresh_pid",
        "implementation_identity",
        "inference_shape",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "roles",
        "state_signature",
        "structural_values",
    }
    contract_keys = set(_PUBLIC_SCIENTIFIC_BOUNDARY_CONTRACT)
    owner_keys = set(_PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS)

    def validate_boundary_record(
        value: Any, *, owner_field: str, require_routes: bool
    ) -> None:
        if not isinstance(value, Mapping):
            raise EvaluatorError("semantic lifecycle boundary record is malformed")
        expected_keys = role_keys if require_routes else reload_keys
        if set(value) != expected_keys:
            raise EvaluatorError("semantic lifecycle boundary record is not exact")
        if (
            not isinstance(value.get("architecture_id"), str)
            or not value["architecture_id"]
            or not isinstance(value.get("boundary_contract"), Mapping)
            or set(value["boundary_contract"]) != contract_keys
            or not isinstance(value.get(owner_field), Mapping)
            or set(value[owner_field]) != owner_keys
            or not digest_shape(value.get("boundary_input_digest_before"))
            or not digest_shape(value.get("boundary_input_digest_after"))
            or not isinstance(value.get("structural_values"), Mapping)
        ):
            raise EvaluatorError("semantic lifecycle boundary evidence is malformed")
        if require_routes:
            scalar_strings = (
                "construction_route",
                "persisted_rebuild_route",
                "public_implementation",
                "persisted_implementation",
                "bundle_implementation",
                "persisted_rebuild_implementation",
            )
            if (
                any(
                    not isinstance(value.get(name), str) or not value[name]
                    for name in scalar_strings
                )
                or not digest_shape(value.get("public_state_signature"))
                or not digest_shape(value.get("persisted_state_signature"))
                or not isinstance(value.get("forward_shape"), list)
                or type(value.get("loss_finite")) is not bool
                or type(value.get("optimizer_changed_parameter")) is not bool
            ):
                raise EvaluatorError("semantic lifecycle role evidence is malformed")
        else:
            if (
                type(value.get("fresh_pid")) is not int
                or not isinstance(value.get("implementation_identity"), str)
                or not value["implementation_identity"]
                or not isinstance(value.get("inference_shape"), list)
                or not isinstance(value.get("loaded_forbidden_modules"), list)
                or not isinstance(value.get("outside_project_origin_rows"), list)
                or not isinstance(value.get("roles"), list)
                or not digest_shape(value.get("state_signature"))
            ):
                raise EvaluatorError("semantic lifecycle reload evidence is malformed")

    for role_name in ("representative", "witness"):
        validate_boundary_record(
            roles[role_name], owner_field="public_boundary_owners", require_routes=True
        )
        if (
            not isinstance(roles[role_name].get("persisted_boundary_owners"), Mapping)
            or set(roles[role_name]["persisted_boundary_owners"]) != owner_keys
        ):
            raise EvaluatorError("semantic lifecycle persisted owner evidence is malformed")
        for reload_name in (
            "evaluator_checkpoint_reload",
            "evaluator_bundle_reload",
            "adapter_checkpoint_reload",
            "adapter_bundle_reload",
        ):
            validate_boundary_record(
                roles[role_name][reload_name],
                owner_field="boundary_owners",
                require_routes=False,
            )

    lifecycle_ok = True
    structural_ok = True
    construction_ok = True
    ownership_ok = (
        semantic_report.get("loaded_forbidden_modules") == []
        and semantic_report.get("outside_project_origin_rows") == []
        and semantic_report.get("cache_artifacts") == []
    )
    role_boundary_digests: set[str] = set()
    reload_boundary_digests: set[str] = set()
    declared = semantic_report.get("declared_structural_fields")
    if (
        not isinstance(declared, list)
        or not declared
        or len(set(declared)) != len(declared)
        or any(not isinstance(name, str) or not name for name in declared)
    ):
        raise EvaluatorError("semantic lifecycle declared structural fields are malformed")
    fields = set(declared)
    sensitivity_evidence = semantic_report.get("identity_sensitivity")
    if (
        not isinstance(sensitivity_evidence, Mapping)
        or set(sensitivity_evidence) != fields
        or any(
            not isinstance(row, Mapping)
            or set(row)
            != {
                "alternate_digest",
                "baseline_digest",
                "changed",
                "deterministic",
            }
            or not digest_shape(row.get("alternate_digest"))
            or not digest_shape(row.get("baseline_digest"))
            or type(row.get("changed")) is not bool
            or type(row.get("deterministic")) is not bool
            for row in sensitivity_evidence.values()
        )
    ):
        raise EvaluatorError("semantic lifecycle sensitivity evidence is malformed")
    rejection_evidence = semantic_report.get("identity_rejections")
    if not isinstance(rejection_evidence, Mapping) or set(rejection_evidence) != {
        "missing",
        "extra",
        "unknown_architecture",
        "unsupported_value",
    }:
        raise EvaluatorError("semantic lifecycle rejection evidence is malformed")
    missing_evidence = rejection_evidence["missing"]
    if not isinstance(missing_evidence, Mapping) or set(missing_evidence) != fields:
        raise EvaluatorError("semantic lifecycle missing-field evidence is malformed")
    rejection_rows = [
        *missing_evidence.values(),
        rejection_evidence["extra"],
        rejection_evidence["unknown_architecture"],
        rejection_evidence["unsupported_value"],
    ]
    for row in rejection_rows:
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {
                "exception_detail_sha256",
                "exception_type",
                "module_returned",
                "rejected",
            }
            or not digest_shape(row.get("exception_detail_sha256"))
            or type(row.get("module_returned")) is not bool
            or type(row.get("rejected")) is not bool
            or not (
                (
                    row["rejected"] is True
                    and row["module_returned"] is False
                    and isinstance(row.get("exception_type"), str)
                    and bool(row["exception_type"])
                )
                or (
                    row["rejected"] is False
                    and row["module_returned"] is True
                    and row.get("exception_type") is None
                )
            )
        ):
            raise EvaluatorError("semantic lifecycle rejection row is malformed")
    for role in ("representative", "witness"):
        observed = roles[role]
        if not isinstance(observed, Mapping):
            raise EvaluatorError("semantic lifecycle role observation is malformed")
        values = observed.get("structural_values")
        expected_structural_names = fields if role == "witness" else set()
        if not isinstance(values, Mapping):
            structural_ok = False
            names: set[str] = set()
        else:
            names = set(values)
        structural_ok = structural_ok and names == expected_structural_names
        expected_implementation = observed.get("persisted_implementation")
        expected_state = observed.get("persisted_state_signature")
        expected_architecture = observed.get("architecture_id")
        construction_ok = construction_ok and all(
            (
                isinstance(observed.get("construction_route"), str),
                bool(observed.get("construction_route")),
                isinstance(observed.get("persisted_rebuild_route"), str),
                bool(observed.get("persisted_rebuild_route")),
                isinstance(expected_implementation, str),
                observed.get("public_implementation") == expected_implementation,
                observed.get("bundle_implementation") == expected_implementation,
                observed.get("persisted_rebuild_implementation")
                == expected_implementation,
                isinstance(expected_state, str),
                observed.get("public_state_signature") == expected_state,
            )
        )
        lifecycle_ok = lifecycle_ok and (
            observed.get("loss_finite") is True
            and observed.get("optimizer_changed_parameter") is True
            and isinstance(observed.get("forward_shape"), list)
            and bool(observed.get("forward_shape"))
        )
        boundary_before = observed.get("boundary_input_digest_before")
        boundary_after = observed.get("boundary_input_digest_after")
        ownership_ok = ownership_ok and (
            observed.get("boundary_contract")
            == _PUBLIC_SCIENTIFIC_BOUNDARY_CONTRACT
            and observed.get("public_boundary_owners")
            == _PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS
            and observed.get("persisted_boundary_owners")
            == _PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS
            and isinstance(boundary_before, str)
            and boundary_before.startswith("sha256:")
            and boundary_after == boundary_before
        )
        if isinstance(boundary_before, str):
            role_boundary_digests.add(boundary_before)
        for reload_name, expected_roles in (
            ("evaluator_checkpoint_reload", []),
            ("evaluator_bundle_reload", ["autoencoder", "diffraction_to_obj"]),
            ("adapter_checkpoint_reload", []),
            ("adapter_bundle_reload", ["autoencoder", "diffraction_to_obj"]),
        ):
            reload = observed.get(reload_name)
            if not isinstance(reload, Mapping):
                lifecycle_ok = False
                structural_ok = False
                construction_ok = False
                ownership_ok = False
                continue
            fresh_pid = reload.get("fresh_pid")
            lifecycle_ok = lifecycle_ok and (
                type(fresh_pid) is int
                and fresh_pid > 0
                and fresh_pid != construction_pid
                and fresh_pid != adapter_process_id
                and isinstance(reload.get("inference_shape"), list)
                and bool(reload.get("inference_shape"))
                and reload.get("roles") == expected_roles
            )
            structural_ok = structural_ok and reload.get("structural_values") == values
            lifecycle_ok = lifecycle_ok and reload.get("architecture_id") == expected_architecture
            construction_ok = construction_ok and (
                reload.get("implementation_identity") == expected_implementation
            )
            ownership_ok = ownership_ok and (
                reload.get("loaded_forbidden_modules") == []
                and reload.get("outside_project_origin_rows") == []
                and reload.get("boundary_contract")
                == _PUBLIC_SCIENTIFIC_BOUNDARY_CONTRACT
                and reload.get("boundary_owners")
                == _PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS
                and isinstance(reload.get("boundary_input_digest_before"), str)
                and str(reload.get("boundary_input_digest_before")).startswith("sha256:")
                and reload.get("boundary_input_digest_after")
                == reload.get("boundary_input_digest_before")
            )
            reload_boundary_digest = reload.get("boundary_input_digest_before")
            if isinstance(reload_boundary_digest, str):
                reload_boundary_digests.add(reload_boundary_digest)

    ownership_ok = ownership_ok and (
        len(role_boundary_digests) == 1 and len(reload_boundary_digests) == 1
    )

    sensitivity = sensitivity_evidence
    sensitivity_ok = set(sensitivity) == fields
    if sensitivity_ok:
        sensitivity_ok = all(
            isinstance(row, Mapping)
            and row.get("changed") is True
            and row.get("deterministic") is True
            and isinstance(row.get("baseline_digest"), str)
            and isinstance(row.get("alternate_digest"), str)
            and row.get("baseline_digest") != row.get("alternate_digest")
            for row in sensitivity.values()
        )

    def valid_rejection(row: Any) -> bool:
        if not isinstance(row, Mapping) or set(row) != {
            "exception_detail_sha256",
            "exception_type",
            "module_returned",
            "rejected",
        }:
            return False
        detail_digest = row.get("exception_detail_sha256")
        return (
            row.get("rejected") is True
            and row.get("module_returned") is False
            and isinstance(row.get("exception_type"), str)
            and bool(row.get("exception_type"))
            and isinstance(detail_digest, str)
            and detail_digest.startswith("sha256:")
            and len(detail_digest) == 71
        )

    rejections = rejection_evidence
    rejection_ok = set(rejections) == {
        "missing",
        "extra",
        "unknown_architecture",
        "unsupported_value",
    }
    if rejection_ok:
        missing = missing_evidence
        rejection_ok = (
            isinstance(missing, Mapping)
            and set(missing) == fields
            and all(valid_rejection(row) for row in missing.values())
            and valid_rejection(rejections["extra"])
            and valid_rejection(rejections["unknown_architecture"])
            and valid_rejection(rejections["unsupported_value"])
        )

    facts = {
        "F1-H05-NOMINATED-LIFECYCLE": lifecycle_ok,
        "F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP": structural_ok,
        "F1-H07-STRUCTURAL-IDENTITY-REJECTION": rejection_ok,
        "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY": sensitivity_ok,
        "F1-H09-CONSTRUCTION-REBUILD-EQUALITY": construction_ok,
        "F1-H10-OWNERSHIP-BOUNDARY": ownership_ok,
    }
    return [
        {
            "clause_id": clause_id,
            "satisfied": facts[clause_id],
            "evidence": [
                _digest(
                    {
                        "clause_id": clause_id,
                        "semantic_report": semantic_report,
                    }
                )
            ],
            "details": "evaluator-owned public lifecycle verification",
        }
        for clause_id in HARD_CLAUSE_IDS[4:]
    ]


def run_lifecycle_adapter(
    *,
    workspace: Path,
    adapter_path: str,
    request: Mapping[str, Any],
    python_executable: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run the candidate seam once in an evaluator-owned fresh process.

    Request/result files and the audit ledger live outside the candidate copy.
    The copy is hashed before and after, so an adapter cannot satisfy the
    lifecycle by altering evaluator input bytes.
    """

    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise EvaluatorError("timeout_seconds must be a positive integer")
    if not isinstance(request, Mapping):
        raise EvaluatorError("lifecycle request must be an object")
    request_record = dict(request)
    _validate_schema_record(
        request_record,
        schema_path=_LIFECYCLE_REQUEST_SCHEMA,
        label="lifecycle request",
    )
    workspace = workspace.resolve(strict=True)
    adapter = _safe_candidate_path(workspace, adapter_path)
    candidate_evidence_source = _safe_candidate_path(
        workspace, "es_f1_candidate_evidence.json"
    )
    candidate_evidence_bytes = candidate_evidence_source.read_bytes()
    candidate_evidence_record = _load_canonical_unversioned(
        candidate_evidence_source
    )
    try:
        _validate_schema_record(
            candidate_evidence_record,
            schema_path=_CANDIDATE_EVIDENCE_SCHEMA,
            label="candidate evidence",
        )
    except EvaluatorError as exc:
        raise EvaluatorObservationError(
            clause_id="F1-H02-SCHEMA-CONFORMANCE",
            mechanism="candidate-evidence-schema-validation",
            evidence={
                "candidate_evidence_sha256": "sha256:"
                + hashlib.sha256(candidate_evidence_bytes).hexdigest(),
                "error_type": type(exc).__name__,
                "error_detail_sha256": "sha256:"
                + hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
            },
            detail="candidate evidence failed the closed public schema",
        ) from exc
    candidate_evidence_digest = "sha256:" + hashlib.sha256(
        candidate_evidence_bytes
    ).hexdigest()
    if request_record["candidate_evidence_sha256"] != candidate_evidence_digest:
        raise EvaluatorError("lifecycle candidate evidence digest binding drifted")
    if candidate_evidence_record["candidate_id"] != request_record["candidate_id"]:
        raise EvaluatorError("lifecycle candidate evidence identity drifted")
    if (
        candidate_evidence_record["representative_architecture"]["public_id"]
        != request_record["representative_architecture"]
        or candidate_evidence_record["witness_architecture"]["public_id"]
        != request_record["witness_architecture"]
    ):
        raise EvaluatorError("lifecycle candidate architecture binding drifted")
    structural_fields = [
        row["name"] for row in candidate_evidence_record["structural_fields"]
    ]
    input_bindings, input_payloads = build_lifecycle_probe_inputs(
        seed=request_record["seed"]
    )
    if request_record["evaluator_inputs"] != input_bindings:
        raise EvaluatorError("lifecycle evaluator input binding drifted")
    if not python_executable.is_absolute() or not python_executable.is_file():
        raise EvaluatorError("python executable must be an existing absolute file")
    before = _workspace_digest(workspace)
    with tempfile.TemporaryDirectory(prefix="es-f1-evaluator-") as raw_temp:
        temp = Path(raw_temp)
        request_path = temp / "request.json"
        result_path = temp / "result.json"
        audit_path = temp / "audit.json"
        bootstrap = temp / "bootstrap"
        bootstrap.mkdir()
        for input_name, payload in input_payloads.items():
            binding = input_bindings[input_name]
            input_path = temp / binding["path"]
            input_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_bytes(payload)
        candidate_evidence = _safe_evaluator_input_target(
            temp,
            request_record["candidate_evidence_path"],
            label="lifecycle candidate evidence path",
        )
        if candidate_evidence.exists():
            raise EvaluatorError("lifecycle candidate evidence path collides with evaluator input")
        candidate_evidence.parent.mkdir(parents=True, exist_ok=True)
        candidate_evidence.write_bytes(candidate_evidence_bytes)
        request_path.write_bytes(canonical_json_bytes(request_record))
        env = dict(os.environ)
        env.update(
            {
                "PYTHONPATH": "",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PTYCHO_DISABLE_MEMOIZE": "1",
            }
        )
        process = subprocess.Popen(
            [
                str(python_executable),
                "-I",
                "-B",
                "-c",
                _AUDITED_ADAPTER_WRAPPER,
                str(adapter),
                str(request_path),
                str(result_path),
                str(audit_path),
                str(workspace),
                str(bootstrap),
            ],
            cwd=bootstrap,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise EvaluatorError("lifecycle adapter timed out") from exc

        audit = _load_canonical_unversioned(audit_path) if audit_path.exists() else {"events": []}
        events = audit.get("events")
        if not isinstance(events, list):
            raise EvaluatorError("lifecycle audit ledger is malformed")
        forbidden_import_values: set[str] = set()
        forbidden_path_values: set[str] = set()
        workspace_write_values: set[str] = set()
        protected_mutation_values: set[str] = set()
        child_launch_values: set[str] = set()
        for row in events:
            if not isinstance(row, Mapping):
                continue
            value = row.get("value")
            if not isinstance(value, str):
                continue
            if row.get("event") == "import" and any(
                value == prefix or value.startswith(prefix + ".")
                for prefix in _FORBIDDEN_IMPORT_PREFIXES
            ):
                forbidden_import_values.add(value)
            if row.get("event") == "path" and any(
                fragment in value for fragment in _FORBIDDEN_PATH_FRAGMENTS
            ):
                forbidden_path_values.add(value)
            if row.get("event") == "workspace_write_attempt":
                workspace_write_values.add(value)
            if row.get("event") == "protected_path_mutation_attempt":
                protected_mutation_values.add(value)
            if row.get("event") == "unaudited_child_process":
                child_launch_values.add(value)
        forbidden_imports = sorted(forbidden_import_values)
        if forbidden_imports:
            raise EvaluatorObservationError(
                clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                mechanism="adapter-import-audit",
                evidence={"forbidden_imports": forbidden_imports},
                detail="candidate adapter crossed a forbidden import boundary",
            )
        forbidden_paths = sorted(forbidden_path_values)
        if forbidden_paths:
            raise EvaluatorObservationError(
                clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                mechanism="adapter-path-audit",
                evidence={"forbidden_paths": forbidden_paths},
                detail="candidate adapter crossed a forbidden path boundary",
            )
        workspace_writes = sorted(workspace_write_values)
        if workspace_writes:
            raise EvaluatorObservationError(
                clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                mechanism="candidate-copy-write-audit",
                evidence={"workspace_write_attempts": workspace_writes},
                detail="candidate adapter attempted to mutate the evaluator copy",
            )
        protected_mutations = sorted(protected_mutation_values)
        if protected_mutations:
            raise EvaluatorObservationError(
                clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                mechanism="adapter-mutation-audit",
                evidence={"observed_values": protected_mutations},
                detail="candidate adapter attempted a transient protected-root mutation",
            )
        child_launches = sorted(child_launch_values)
        if child_launches:
            raise EvaluatorObservationError(
                clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                mechanism="candidate-process-child-launch-audit",
                evidence={"observed_values": child_launches},
                detail="candidate adapter attempted to launch an unaudited child process",
            )
        if process.returncode != 0:
            raise EvaluatorError(
                "lifecycle adapter failed: "
                f"exit={process.returncode}, stdout={stdout!r}, stderr={stderr!r}"
            )
        if not result_path.exists():
            raise EvaluatorError("lifecycle adapter produced no result")
        adapter_result = _load_canonical_unversioned(result_path)
        _validate_schema_record(
            adapter_result,
            schema_path=_LIFECYCLE_RESULT_SCHEMA,
            label="lifecycle result",
        )
        if adapter_result["candidate_id"] != request_record["candidate_id"]:
            raise EvaluatorError("lifecycle result candidate identity drifted")
        if adapter_result["operation_version"] != request_record["operation_version"]:
            raise EvaluatorError("lifecycle result operation version drifted")
        artifacts: dict[str, dict[str, Path]] = {}
        for role in ("representative", "witness"):
            artifact_record = adapter_result["artifacts"][role]
            artifacts[role] = {
                "checkpoint": _safe_external_result_path(
                    temp,
                    artifact_record["checkpoint_path"],
                    label=f"lifecycle {role} checkpoint",
                ),
                "bundle": _safe_external_result_path(
                    temp,
                    artifact_record["bundle_path"],
                    label=f"lifecycle {role} bundle",
                ),
            }
        semantic_observations = _verify_adapter_artifacts(
            workspace=workspace,
            python_executable=python_executable,
            artifacts=artifacts,
            structural_fields=structural_fields,
            output_root=temp,
            timeout_seconds=timeout_seconds,
        )
        semantic_report = _run_semantic_lifecycle_probe(
            workspace=workspace,
            python_executable=python_executable,
            candidate_evidence=candidate_evidence,
            base_config=temp / input_bindings["base_config"]["path"],
            cdi_fixture=temp / input_bindings["cdi_fixture"]["path"],
            adapter_observations=semantic_observations,
            output_root=temp,
            seed=request_record["seed"],
            timeout_seconds=timeout_seconds,
        )
    after = _workspace_digest(workspace)
    if after != before:
        raise EvaluatorObservationError(
            clause_id="F1-H10-OWNERSHIP-BOUNDARY",
            mechanism="candidate-copy-digest-ratchet",
            evidence={"copy_digest_before": before, "copy_digest_after": after},
            detail="candidate evaluation copy mutated during lifecycle",
        )
    lifecycle_observations = derive_lifecycle_observations(
        semantic_report=semantic_report,
        adapter_process_id=process.pid,
    )
    return {
        "adapter_result": adapter_result,
        "audit_digest": _digest(audit),
        "copy_digest_after": after,
        "copy_digest_before": before,
        "adapter_process_id": process.pid,
        "semantic_observations": semantic_observations,
        "semantic_report": semantic_report,
        "lifecycle_observations": lifecycle_observations,
    }


def derive_registry_observation(
    *,
    expected_registry_baseline: list[Mapping[str, Any]],
    registry_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare only the 14 frozen built-ins; candidate additions are out of scope."""

    if (
        not isinstance(expected_registry_baseline, list)
        or len(expected_registry_baseline) != 14
        or any(not isinstance(row, Mapping) for row in expected_registry_baseline)
    ):
        raise EvaluatorError("frozen registry baseline is malformed")
    architectures = [row.get("architecture") for row in expected_registry_baseline]
    if (
        any(not isinstance(value, str) or not value for value in architectures)
        or len(set(architectures)) != len(architectures)
    ):
        raise EvaluatorError("frozen registry baseline selector is malformed")
    if not isinstance(registry_report, Mapping) or set(registry_report) != {
        "schema_version",
        "registry_baseline",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    }:
        raise EvaluatorError("registry signature report is not exact")
    registry_rows = registry_report.get("registry_baseline")
    expected_keys = {
        "N",
        "architecture",
        "implementation_identity",
        "parameter_count",
        "state_entry_count",
        "state_signature",
    }
    def valid_row(row: Any) -> bool:
        return (
            isinstance(row, Mapping)
            and set(row) == expected_keys
            and type(row.get("N")) is int
            and row["N"] > 0
            and isinstance(row.get("architecture"), str)
            and bool(row["architecture"])
            and isinstance(row.get("implementation_identity"), str)
            and bool(row["implementation_identity"])
            and type(row.get("parameter_count")) is int
            and row["parameter_count"] >= 0
            and type(row.get("state_entry_count")) is int
            and row["state_entry_count"] >= 0
            and isinstance(row.get("state_signature"), str)
            and row["state_signature"].startswith("sha256:")
            and len(row["state_signature"]) == 71
        )
    if (
        registry_report.get("schema_version")
        != "es-f1-registry-signature-probe.v1"
        or not isinstance(registry_rows, list)
        or len(registry_rows) != len(expected_registry_baseline)
        or any(not valid_row(row) for row in expected_registry_baseline)
        or any(not valid_row(row) for row in registry_rows)
        or [row["architecture"] for row in registry_rows] != architectures
        or registry_report.get("loaded_forbidden_modules") != []
        or registry_report.get("outside_project_origin_rows") != []
        or registry_report.get("cache_artifacts") != []
    ):
        raise EvaluatorError("registry signature report is malformed")
    return {
        "clause_id": "F1-H03-BUILTIN-SIGNATURES",
        "satisfied": registry_rows == expected_registry_baseline,
        "evidence": [
            _digest(
                {
                    "expected_registry": expected_registry_baseline,
                    "registry_report": registry_report,
                }
            )
        ],
        "details": "exact frozen built-in registry signature comparison",
    }


def derive_complete_observations(
    *,
    visible_checks: Mapping[str, Any],
    visible_check_result: Mapping[str, Any],
    candidate_evidence: Mapping[str, Any],
    lifecycle_request: Mapping[str, Any],
    lifecycle_result: Mapping[str, Any],
    fixture_manifest: Mapping[str, Any],
    registry_report: Mapping[str, Any],
    artifact_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Join complete controller-owned evidence into H01 through H10."""

    def require_digest(value: Any, *, label: str) -> str:
        if (
            not isinstance(value, str)
            or not value.startswith("sha256:")
            or len(value) != 71
        ):
            raise EvaluatorError(f"{label} digest is malformed")
        return value

    def observation(
        clause_id: str,
        *,
        satisfied: bool,
        evidence: Mapping[str, Any],
        details: str,
    ) -> dict[str, Any]:
        return {
            "clause_id": clause_id,
            "satisfied": satisfied,
            "evidence": [_digest(evidence)],
            "details": details,
        }

    if not isinstance(visible_checks, Mapping):
        raise EvaluatorError("complete observation visible manifest is malformed")
    visible_manifest = dict(visible_checks)
    _validate_schema_record(
        visible_manifest,
        schema_path=_VISIBLE_CHECK_SCHEMA,
        label="complete observation visible manifest",
    )
    if not isinstance(visible_check_result, Mapping) or set(visible_check_result) != {
        "schema_version",
        "copy_digest_after",
        "copy_digest_before",
        "invocations",
    }:
        raise EvaluatorError("complete observation visible result is not exact")
    if visible_check_result.get("schema_version") != "es-f1-visible-check-result.v1":
        raise EvaluatorError("complete observation visible result version drifted")
    visible_before = require_digest(
        visible_check_result.get("copy_digest_before"), label="visible copy before"
    )
    visible_after = require_digest(
        visible_check_result.get("copy_digest_after"), label="visible copy after"
    )
    if visible_before != visible_after:
        raise EvaluatorError("complete observation visible checks mutated the copy")
    declared_invocations = {
        row["id"]: row for row in visible_manifest["invocations"]
    }
    observed_invocations = visible_check_result.get("invocations")
    if not isinstance(observed_invocations, list) or len(observed_invocations) != len(
        visible_manifest["invocation_order"]
    ):
        raise EvaluatorError("complete observation visible invocation count drifted")
    runner = visible_manifest["runner"]
    visible_satisfied = True
    for invocation_id, observed in zip(
        visible_manifest["invocation_order"], observed_invocations, strict=True
    ):
        if not isinstance(observed, Mapping) or set(observed) != {
            "argv",
            "exit_code",
            "invocation_id",
            "stderr_sha256",
            "stdout_sha256",
        }:
            raise EvaluatorError("complete observation visible invocation is not exact")
        expected_argv = [
            runner["python_executable"],
            *runner["argv_prefix"],
            *declared_invocations[invocation_id]["selectors"],
        ]
        if (
            observed.get("invocation_id") != invocation_id
            or observed.get("argv") != expected_argv
            or type(observed.get("exit_code")) is not int
        ):
            raise EvaluatorError("complete observation visible invocation drifted")
        visible_satisfied = visible_satisfied and observed["exit_code"] == 0
        require_digest(observed.get("stderr_sha256"), label="visible stderr")
        require_digest(observed.get("stdout_sha256"), label="visible stdout")
    h01 = observation(
        "F1-H01-FOCUSED-SUITES",
        satisfied=visible_satisfied,
        evidence={
            "visible_checks": visible_manifest,
            "visible_check_result": visible_check_result,
        },
        details="exact candidate-visible invocation results on an immutable copy",
    )

    if not isinstance(candidate_evidence, Mapping):
        raise EvaluatorError("complete observation candidate evidence is malformed")
    candidate_record = dict(candidate_evidence)
    if not isinstance(lifecycle_request, Mapping):
        raise EvaluatorError("complete observation lifecycle request is malformed")
    request_record = dict(lifecycle_request)
    if not isinstance(lifecycle_result, Mapping) or set(lifecycle_result) != {
        "adapter_result",
        "audit_digest",
        "copy_digest_after",
        "copy_digest_before",
        "adapter_process_id",
        "semantic_observations",
        "semantic_report",
        "lifecycle_observations",
    }:
        raise EvaluatorError("complete observation lifecycle result is not exact")
    adapter_result = lifecycle_result.get("adapter_result")
    if not isinstance(adapter_result, Mapping):
        raise EvaluatorError("complete observation adapter result is malformed")
    _validate_schema_record(
        candidate_record,
        schema_path=_CANDIDATE_EVIDENCE_SCHEMA,
        label="complete observation candidate evidence",
    )
    _validate_schema_record(
        request_record,
        schema_path=_LIFECYCLE_REQUEST_SCHEMA,
        label="complete observation lifecycle request",
    )
    _validate_schema_record(
        adapter_result,
        schema_path=_LIFECYCLE_RESULT_SCHEMA,
        label="complete observation lifecycle result",
    )
    candidate_digest = "sha256:" + hashlib.sha256(
        canonical_json_bytes(candidate_record)
    ).hexdigest()
    if (
        request_record["candidate_evidence_sha256"] != candidate_digest
        or candidate_record["candidate_id"] != request_record["candidate_id"]
        or adapter_result["candidate_id"] != request_record["candidate_id"]
        or adapter_result["operation_version"] != request_record["operation_version"]
        or candidate_record["representative_architecture"]["public_id"]
        != request_record["representative_architecture"]
        or candidate_record["witness_architecture"]["public_id"]
        != request_record["witness_architecture"]
    ):
        raise EvaluatorError("complete observation schema bindings drifted")
    h02 = observation(
        "F1-H02-SCHEMA-CONFORMANCE",
        satisfied=True,
        evidence={
            "candidate_evidence": candidate_record,
            "lifecycle_request": request_record,
            "lifecycle_result": adapter_result,
        },
        details="candidate evidence and lifecycle request/result passed exact schemas",
    )

    expected_fixture_fields = _TOP_LEVEL_FIELDS["es-f1-fixture-manifest.v1"]
    if (
        not isinstance(fixture_manifest, Mapping)
        or set(fixture_manifest) != expected_fixture_fields
        or fixture_manifest.get("schema_version") != "es-f1-fixture-manifest.v1"
        or fixture_manifest.get("hard_clause_ids") != list(HARD_CLAUSE_IDS)
    ):
        raise EvaluatorError("complete observation fixture manifest is not exact")
    expected_registry_rows = fixture_manifest.get("registry_baseline")
    if not isinstance(expected_registry_rows, list):
        raise EvaluatorError("complete observation frozen registry is malformed")
    h03 = derive_registry_observation(
        expected_registry_baseline=expected_registry_rows,
        registry_report=registry_report,
    )

    if not isinstance(artifact_report, Mapping) or set(artifact_report) != {
        "schema_version",
        "artifact_eras",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    }:
        raise EvaluatorError("complete observation artifact report is not exact")
    artifact_rows = artifact_report.get("artifact_eras")
    expected_eras = [row["era_id"] for row in fixture_manifest["artifact_eras"]]
    if (
        artifact_report.get("schema_version")
        != "es-f1-artifact-fixture-verification.v1"
        or not isinstance(artifact_rows, list)
        or [row.get("era_id") if isinstance(row, Mapping) else None for row in artifact_rows]
        != expected_eras
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"era_id", "implementation_identity", "strict_load"}
            or not isinstance(row.get("implementation_identity"), str)
            or not row["implementation_identity"]
            or type(row.get("strict_load")) is not bool
            for row in artifact_rows
        )
        or artifact_report.get("loaded_forbidden_modules") != []
        or artifact_report.get("outside_project_origin_rows") != []
        or artifact_report.get("cache_artifacts") != []
    ):
        raise EvaluatorError("complete observation artifact-era verification drifted")
    h04 = observation(
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
        satisfied=all(row["strict_load"] for row in artifact_rows),
        evidence={
            "expected_artifact_eras": fixture_manifest["artifact_eras"],
            "artifact_report": artifact_report,
        },
        details="strict public loading results for every frozen artifact era",
    )

    lifecycle_before = require_digest(
        lifecycle_result.get("copy_digest_before"), label="lifecycle copy before"
    )
    lifecycle_after = require_digest(
        lifecycle_result.get("copy_digest_after"), label="lifecycle copy after"
    )
    require_digest(lifecycle_result.get("audit_digest"), label="lifecycle audit")
    if lifecycle_before != lifecycle_after:
        raise EvaluatorError("complete observation lifecycle mutated the copy")
    adapter_process_id = lifecycle_result.get("adapter_process_id")
    if type(adapter_process_id) is not int or adapter_process_id <= 0:
        raise EvaluatorError("complete observation adapter process is malformed")
    semantic_report = lifecycle_result.get("semantic_report")
    semantic_observations = lifecycle_result.get("semantic_observations")
    if not isinstance(semantic_report, Mapping) or not isinstance(
        semantic_observations, Mapping
    ):
        raise EvaluatorError("complete observation semantic evidence is malformed")
    roles = semantic_report.get("roles")
    if not isinstance(roles, Mapping) or set(roles) != {"representative", "witness"}:
        raise EvaluatorError("complete observation semantic roles are malformed")
    if semantic_report.get("declared_structural_fields") != [
        row["name"] for row in candidate_record["structural_fields"]
    ]:
        raise EvaluatorError("complete observation structural declaration drifted")
    if (
        roles["representative"].get("architecture_id")
        != request_record["representative_architecture"]
        or roles["witness"].get("architecture_id")
        != request_record["witness_architecture"]
        or set(semantic_observations) != {"representative", "witness"}
    ):
        raise EvaluatorError("complete observation semantic role bindings drifted")
    for role in ("representative", "witness"):
        declaration = candidate_record[f"{role}_architecture"]
        if (
            roles[role].get("construction_route")
            != declaration["construction_route"]
            or roles[role].get("persisted_rebuild_route")
            != declaration["persisted_rebuild_route"]
        ):
            raise EvaluatorError("complete observation semantic route binding drifted")
        observed_role = semantic_observations[role]
        if not isinstance(observed_role, Mapping) or set(observed_role) != {
            "checkpoint",
            "bundle",
        }:
            raise EvaluatorError("complete observation adapter semantics are not exact")
        if (
            observed_role["checkpoint"]
            != roles[role].get("adapter_checkpoint_reload")
            or observed_role["bundle"] != roles[role].get("adapter_bundle_reload")
        ):
            raise EvaluatorError("complete observation adapter semantics drifted")
    derived_lifecycle = derive_lifecycle_observations(
        semantic_report=semantic_report,
        adapter_process_id=adapter_process_id,
    )
    if lifecycle_result.get("lifecycle_observations") != derived_lifecycle:
        raise EvaluatorError("complete observation lifecycle derivation drifted")
    if [row["clause_id"] for row in derived_lifecycle] != list(HARD_CLAUSE_IDS[4:]):
        raise EvaluatorError("complete observation lifecycle clause set drifted")
    return [h01, h02, h03, h04, *derived_lifecycle]


def run_registry_signature_probe(
    *,
    workspace: Path,
    python_executable: Path,
    expected_registry_baseline: list[Mapping[str, Any]],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Capture the exact pre-edit public/persisted signature for all 14 built-ins."""

    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise EvaluatorError("registry probe workspace must be a directory")
    if not python_executable.is_absolute() or not python_executable.is_file():
        raise EvaluatorError("registry probe Python must be an existing absolute file")
    if (
        not isinstance(expected_registry_baseline, list)
        or not expected_registry_baseline
        or any(
            not isinstance(row, Mapping)
            or not isinstance(row.get("architecture"), str)
            or not row["architecture"]
            for row in expected_registry_baseline
        )
    ):
        raise EvaluatorError("registry probe frozen baseline selector is malformed")
    architectures = [row["architecture"] for row in expected_registry_baseline]
    if len(set(architectures)) != len(architectures):
        raise EvaluatorError("registry probe frozen baseline selector is ambiguous")
    before = _workspace_digest(workspace)
    with tempfile.TemporaryDirectory(prefix="es-f1-registry-") as raw_temp:
        report = Path(raw_temp) / "report.json"
        _run_projection_probe(
            workspace=workspace,
            python_executable=python_executable,
            code=_REGISTRY_SIGNATURE_PROBE,
            environment={
                "ES_F1_BUILTIN_ARCHITECTURES": json.dumps(architectures),
                "ES_F1_REPORT": str(report),
                "ES_F1_WORKSPACE": str(workspace),
            },
            timeout_seconds=timeout_seconds,
            label="registry signature probe",
        )
        if not report.is_file():
            raise EvaluatorError("registry signature probe produced no report")
        payload = _load_canonical_unversioned(report)
    if _workspace_digest(workspace) != before:
        raise EvaluatorError("registry signature probe mutated the pre-edit copy")
    if payload.get("schema_version") != "es-f1-registry-signature-probe.v1":
        raise EvaluatorError("registry signature probe schema mismatch")
    return payload


def run_preedit_representative_lifecycle_probe(
    *,
    workspace: Path,
    python_executable: Path,
    output_root: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Exercise the landed F1 representative lifecycle through production APIs."""

    workspace = workspace.resolve(strict=True)
    output_root = output_root.resolve(strict=False)
    if output_root.is_relative_to(workspace):
        raise EvaluatorError("lifecycle probe output must be outside the evaluated copy")
    output_root.mkdir(parents=True, exist_ok=False)
    before = _workspace_digest(workspace)
    report = output_root / "lifecycle-report.json"
    child_pairs = (
        ("checkpoint-reload-program.py", "checkpoint-reload-audit.json"),
        ("bundle-reload-program.py", "bundle-reload-audit.json"),
    )
    child_environments = {
        pair: {
            "ES_F1_CHILD_REPORT": str(
                output_root / pair[0].removesuffix("-program.py")
            )
            + ".json",
            "ES_F1_RELOAD_MODE": kind,
            "ES_F1_RELOAD_ARTIFACT": str(output_root / artifact),
            "ES_F1_FRESH_RELOAD": "1",
        }
        for pair, kind, artifact in (
            (child_pairs[0], "checkpoint", "representative.ckpt"),
            (child_pairs[1], "bundle", "training"),
        )
    }
    _run_projection_probe(
        workspace=workspace,
        controlled_child_root=output_root,
        controlled_child_pairs=child_pairs,
        controlled_child_environment_updates=child_environments,
        python_executable=python_executable,
        code=_PREEDIT_LIFECYCLE_PROBE,
        environment={
            "ES_F1_CHILD_CODE": _FRESH_RELOAD_PROBE,
            "ES_F1_OUTPUT": str(output_root),
            "ES_F1_REPORT": str(report),
            "ES_F1_WORKSPACE": str(workspace),
        },
        timeout_seconds=timeout_seconds,
        label="pre-edit representative lifecycle probe",
    )
    if not report.is_file():
        raise EvaluatorError("pre-edit representative lifecycle produced no report")
    payload = _load_canonical_unversioned(report)
    if _workspace_digest(workspace) != before:
        raise EvaluatorError("pre-edit lifecycle probe mutated the evaluated copy")
    if payload.get("schema_version") != "es-f1-preedit-lifecycle-probe.v1":
        raise EvaluatorError("pre-edit lifecycle report schema mismatch")
    return payload


def _run_projection_probe(
    *,
    workspace: Path,
    read_only_workspace: Path | None = None,
    protected_workspaces: Sequence[Path] | None = None,
    working_directory: Path | None = None,
    controlled_child_root: Path | None = None,
    controlled_child_pairs: tuple[tuple[str, str], ...] = (),
    controlled_child_environment_updates: dict[
        tuple[str, str], dict[str, str]
    ] | None = None,
    python_executable: Path,
    code: str,
    environment: dict[str, str],
    timeout_seconds: int,
    label: str,
    check_process: bool = True,
) -> subprocess.CompletedProcess[str]:
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise EvaluatorError("timeout_seconds must be a positive integer")
    if not python_executable.is_absolute() or not python_executable.is_file():
        raise EvaluatorError(f"{label} Python must be an existing absolute file")
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise EvaluatorError(f"{label} workspace must be an existing directory")
    if read_only_workspace is not None and protected_workspaces is not None:
        raise EvaluatorError(f"{label} supplied conflicting read-only workspaces")
    raw_protected = (
        protected_workspaces
        if protected_workspaces is not None
        else (workspace if read_only_workspace is None else read_only_workspace,)
    )
    audited_workspaces = tuple(path.resolve(strict=True) for path in raw_protected)
    if not audited_workspaces or any(not path.is_dir() for path in audited_workspaces):
        raise EvaluatorError(f"{label} read-only workspace must be an existing directory")
    process_workspace = (
        workspace
        if working_directory is None
        else working_directory.resolve(strict=True)
    )
    if not process_workspace.is_dir():
        raise EvaluatorError(f"{label} working directory must be an existing directory")
    child_root = (
        None if controlled_child_root is None else controlled_child_root.resolve(strict=True)
    )
    if child_root is not None and not child_root.is_dir():
        raise EvaluatorError(f"{label} controlled child root must be a directory")
    protected_roots = json.dumps(
        [str(path) for path in audited_workspaces], separators=(",", ":")
    )
    if type(environment) is not dict or any(
        type(name) is not str or type(value) is not str
        for name, value in environment.items()
    ):
        raise EvaluatorError(
            f"{label} environment must be an exact built-in dict of exact built-in strings"
        )
    if type(controlled_child_pairs) is not tuple or any(
        type(pair) is not tuple
        or len(pair) != 2
        or any(type(value) is not str for value in pair)
        for pair in controlled_child_pairs
    ):
        raise EvaluatorError(
            f"{label} controlled child pairs must use exact built-in tuples and strings"
        )
    if controlled_child_environment_updates is not None and (
        type(controlled_child_environment_updates) is not dict
        or any(
            type(pair) is not tuple
            or len(pair) != 2
            or any(type(value) is not str for value in pair)
            or type(updates) is not dict
            or any(
                type(name) is not str or type(value) is not str
                for name, value in updates.items()
            )
            for pair, updates in controlled_child_environment_updates.items()
        )
    ):
        raise EvaluatorError(
            f"{label} controlled child environments must use exact built-in dicts and strings"
        )
    env = dict(os.environ)
    env.update(environment)
    env.update(
        {
            "PYTHONPATH": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PTYCHO_DISABLE_MEMOIZE": "1",
            "ES_F1_NESTED_WRAPPER": _AUDITED_PROJECTION_WRAPPER,
            "ES_F1_PROTECTED_ROOTS": protected_roots,
            "ES_F1_WORKSPACE": str(workspace),
        }
    )
    if child_root is not None:
        child_code = environment.get("ES_F1_CHILD_CODE")
        if type(child_code) is not str:
            raise EvaluatorError(f"{label} controlled child code is not bound")
        env["ES_F1_CONTROLLED_CHILD_ROOT"] = str(child_root)
        env["ES_F1_CONTROLLED_CHILD_SHA256"] = hashlib.sha256(
            child_code.encode("utf-8")
        ).hexdigest()
        update_rows = (
            {}
            if controlled_child_environment_updates is None
            else {
                pair: dict(updates)
                for pair, updates in controlled_child_environment_updates.items()
            }
        )
        if set(update_rows) != set(controlled_child_pairs):
            raise EvaluatorError(
                f"{label} controlled child environments do not match the approved pairs"
            )
        absolute_pairs: list[list[str]] = []
        child_bootstraps: list[Path] = []
        controlled_specs: dict[str, dict[str, Any]] = {}
        for index, pair in enumerate(controlled_child_pairs):
            if any(not value for value in pair):
                raise EvaluatorError(f"{label} controlled child pair is malformed")
            resolved_pair = [
                str((child_root / value).resolve(strict=False)) for value in pair
            ]
            if any(
                not Path(value).is_relative_to(child_root)
                for value in resolved_pair
            ):
                raise EvaluatorError(f"{label} controlled child pair escaped its root")
            absolute_pairs.append(resolved_pair)
            updates = update_rows[pair]
            immutable_child_fields = {
                "PYTHONPATH",
                "PYTHONDONTWRITEBYTECODE",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
                "PTYCHO_DISABLE_MEMOIZE",
                "ES_F1_NESTED_WRAPPER",
                "ES_F1_PROTECTED_ROOTS",
                "ES_F1_WORKSPACE",
                "ES_F1_CONTROLLED_CHILD_ROOT",
                "ES_F1_CONTROLLED_CHILD_SHA256",
                "ES_F1_CONTROLLED_CHILD_SPECS",
            }
            if immutable_child_fields.intersection(updates):
                raise EvaluatorError(
                    f"{label} controlled child environment overrides a fixed field"
                )
            child_cwd = child_root / (
                f".evaluator-bootstrap-{index}-{Path(pair[0]).stem}"
            )
            child_cwd.mkdir()
            child_bootstraps.append(child_cwd.resolve(strict=True))
            controlled_specs[resolved_pair[0]] = {
                "audit_path": resolved_pair[1],
                "cwd": str(child_cwd),
                "environment_updates": dict(updates),
            }
        if not absolute_pairs or len({tuple(pair) for pair in absolute_pairs}) != len(
            absolute_pairs
        ):
            raise EvaluatorError(f"{label} controlled child pairs are absent or ambiguous")
        env["ES_F1_CONTROLLED_CHILD_SPECS"] = json.dumps(
            controlled_specs, separators=(",", ":"), sort_keys=True
        )
    else:
        if controlled_child_pairs:
            raise EvaluatorError(f"{label} controlled child pairs have no root")
        if controlled_child_environment_updates:
            raise EvaluatorError(f"{label} controlled child environments have no root")
        env.pop("ES_F1_CONTROLLED_CHILD_ROOT", None)
        env.pop("ES_F1_CONTROLLED_CHILD_SHA256", None)
        env.pop("ES_F1_CONTROLLED_CHILD_SPECS", None)
        child_bootstraps = []
    with tempfile.TemporaryDirectory(prefix="es-f1-candidate-process-") as raw_temp:
        process_root = Path(raw_temp)
        bootstrap = process_root / "bootstrap"
        bootstrap.mkdir()
        protected_roots = json.dumps(
            [
                str(path)
                for path in (*audited_workspaces, *child_bootstraps, bootstrap)
            ],
            separators=(",", ":"),
        )
        env["ES_F1_PROTECTED_ROOTS"] = protected_roots
        program_path = process_root / "program.py"
        audit_path = process_root / "audit.json"
        program_path.write_text(code, encoding="utf-8", newline="\n")
        try:
            process = subprocess.run(
                [
                    str(python_executable),
                    "-B",
                    "-c",
                    _AUDITED_PROJECTION_WRAPPER,
                    protected_roots,
                    str(program_path),
                    str(audit_path),
                    str(workspace),
                    str(process_workspace),
                ],
                cwd=bootstrap,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise EvaluatorError(f"{label} timed out") from exc
        audit = (
            _load_canonical_unversioned(audit_path)
            if audit_path.is_file()
            else {"events": []}
        )
    events = audit.get("events")
    if not isinstance(events, list):
        raise EvaluatorError(f"{label} candidate-process audit is malformed")
    for event_name, mechanism, detail in (
        (
            "forbidden_import",
            "candidate-process-import-audit",
            "candidate code crossed a forbidden import boundary",
        ),
        (
            "forbidden_path",
            "candidate-process-path-audit",
            "candidate code crossed a forbidden path boundary",
        ),
        (
            "workspace_write_attempt",
            "candidate-process-write-audit",
            "candidate code attempted to mutate an evaluator read-only workspace",
        ),
        (
            "protected_path_mutation_attempt",
            "candidate-process-mutation-audit",
            "candidate code attempted a transient mutation of an evaluator read-only workspace",
        ),
        (
            "unaudited_child_process",
            "candidate-process-child-launch-audit",
            "candidate code attempted to launch an unaudited child process",
        ),
    ):
        observed_values: set[str] = set()
        for row in events:
            if not isinstance(row, Mapping) or row.get("event") != event_name:
                continue
            value = row.get("value")
            if isinstance(value, str):
                observed_values.add(value)
        values = sorted(observed_values)
        if values:
            raise EvaluatorObservationError(
                clause_id="F1-H10-OWNERSHIP-BOUNDARY",
                mechanism=mechanism,
                evidence={"label": label, "observed_values": values},
                detail=detail,
            )
    if check_process and process.returncode != 0:
        raise EvaluatorError(
            f"{label} failed: exit={process.returncode}, "
            f"stdout={process.stdout!r}, stderr={process.stderr!r}"
        )
    return process


def build_artifact_fixture_pack(
    *,
    workspace: Path,
    python_executable: Path,
    store_root: Path,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    """Build the ten frozen pre-edit era artifacts into an external SHA-256 CAS."""

    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise EvaluatorError("artifact builder workspace must be a directory")
    store_root = store_root.resolve(strict=False)
    if not store_root.is_absolute() or store_root.is_relative_to(workspace):
        raise EvaluatorError("artifact fixture store must be external and absolute")
    store_root.mkdir(parents=True, exist_ok=True)
    before = _workspace_digest(workspace)
    with tempfile.TemporaryDirectory(prefix="es-f1-artifact-build-") as raw_temp:
        output = Path(raw_temp).resolve(strict=True)
        report_path = output / "build-report.json"
        _run_projection_probe(
            workspace=workspace,
            python_executable=python_executable,
            code=_ARTIFACT_FIXTURE_BUILD_PROBE,
            environment={
                "ES_F1_OUTPUT": str(output),
                "ES_F1_REPORT": str(report_path),
                "ES_F1_WORKSPACE": str(workspace),
            },
            timeout_seconds=timeout_seconds,
            label="artifact fixture build",
        )
        if not report_path.is_file():
            raise EvaluatorError("artifact fixture build produced no report")
        report = _load_canonical_unversioned(report_path)
        if set(report) != {"schema_version", "artifact_eras"} or report.get(
            "schema_version"
        ) != "es-f1-artifact-fixture-build.v1":
            raise EvaluatorError("artifact fixture build report is not exact")
        source_rows = report.get("artifact_eras")
        if not isinstance(source_rows, list) or [
            row.get("era_id") if isinstance(row, Mapping) else None
            for row in source_rows
        ] != list(ARTIFACT_ERA_IDS):
            raise EvaluatorError("artifact fixture build era set/order drifted")
        rows: list[dict[str, Any]] = []
        contracts = {
            "json": "decode-and-build.v1",
            "checkpoint": "lightning-strict-load.v1",
            "bundle": "public-bundle-strict-load.v1",
        }
        for source_row in source_rows:
            if not isinstance(source_row, Mapping) or set(source_row) != {
                "era_id",
                "kind",
                "path",
            }:
                raise EvaluatorError("artifact fixture build row is not exact")
            kind = source_row["kind"]
            if kind not in contracts:
                raise EvaluatorError(f"unknown artifact fixture kind {kind!r}")
            relative = source_row["path"]
            if not isinstance(relative, str):
                raise EvaluatorError("artifact fixture build path is malformed")
            source = (output / relative).resolve(strict=True)
            if not source.is_file() or not source.is_relative_to(output):
                raise EvaluatorError("artifact fixture build path escaped output root")
            payload = source.read_bytes()
            digest_hex = hashlib.sha256(payload).hexdigest()
            relative_cas = f"{digest_hex}/payload"
            destination = store_root / relative_cas
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if not destination.is_file() or destination.read_bytes() != payload:
                    raise EvaluatorError("artifact fixture CAS collision or corruption")
            else:
                shutil.copyfile(source, destination)
                destination.chmod(0o444)
            rows.append(
                {
                    "bytes": len(payload),
                    "cas_relative_path": relative_cas,
                    "era_id": source_row["era_id"],
                    "kind": kind,
                    "load_contract": contracts[kind],
                    "sha256": "sha256:" + digest_hex,
                }
            )
    if _workspace_digest(workspace) != before:
        raise EvaluatorError("artifact fixture build mutated the pre-edit copy")
    return rows


def verify_artifact_fixture_pack(
    *,
    workspace: Path,
    python_executable: Path,
    fixture_manifest: Mapping[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Digest-check and strict-load every frozen era in one fresh projection process."""

    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise EvaluatorError("artifact verifier workspace must be a directory")
    if not isinstance(fixture_manifest, Mapping):
        raise EvaluatorError("artifact fixture manifest must be an object")
    external = fixture_manifest.get("external_fixture_store")
    if not isinstance(external, Mapping) or set(external) != {"algorithm", "root"}:
        raise EvaluatorError("external artifact fixture store binding is malformed")
    if external["algorithm"] != "sha256" or not isinstance(external["root"], str):
        raise EvaluatorError("external artifact fixture store algorithm/root drifted")
    store_root = Path(external["root"])
    if not store_root.is_absolute() or not store_root.is_dir():
        raise EvaluatorError("external artifact fixture store is unavailable")
    manifest_rows = fixture_manifest.get("artifact_eras")
    if not isinstance(manifest_rows, list) or [
        row.get("era_id") if isinstance(row, Mapping) else None for row in manifest_rows
    ] != list(ARTIFACT_ERA_IDS):
        raise EvaluatorError("artifact fixture manifest era set/order drifted")
    probe_rows: list[dict[str, Any]] = []
    expected_fields = {
        "bytes",
        "cas_relative_path",
        "era_id",
        "kind",
        "load_contract",
        "sha256",
    }
    for row in manifest_rows:
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            raise EvaluatorError("artifact fixture manifest row is not exact")
        digest = row["sha256"]
        if (
            not isinstance(digest, str)
            or not digest.startswith("sha256:")
            or len(digest) != 71
        ):
            raise EvaluatorError("artifact fixture digest is malformed")
        expected_relative = f"{digest.removeprefix('sha256:')}/payload"
        if row["cas_relative_path"] != expected_relative:
            raise EvaluatorError("artifact fixture CAS path/digest binding drifted")
        path = (store_root / expected_relative).resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(store_root.resolve(strict=True)):
            raise EvaluatorError("artifact fixture CAS path escaped or is not a file")
        payload = path.read_bytes()
        if len(payload) != row["bytes"] or hashlib.sha256(payload).hexdigest() != digest[7:]:
            raise EvaluatorError(f"artifact fixture bytes drifted for {row['era_id']}")
        probe_rows.append(
            {
                "absolute_path": str(path),
                "era_id": row["era_id"],
                "kind": row["kind"],
            }
        )
    before = _workspace_digest(workspace)
    with tempfile.TemporaryDirectory(prefix="es-f1-artifact-verify-") as raw_temp:
        temporary = Path(raw_temp)
        rows_path = temporary / "rows.json"
        report_path = temporary / "report.json"
        rows_path.write_bytes(
            canonical_json_bytes(
                {
                    "schema_version": "es-f1-artifact-fixture-input.v1",
                    "artifact_eras": probe_rows,
                }
            )
        )
        _run_projection_probe(
            workspace=workspace,
            python_executable=python_executable,
            code=_ARTIFACT_FIXTURE_VERIFY_PROBE,
            environment={
                "ES_F1_FIXTURE_ROWS": str(rows_path),
                "ES_F1_REPORT": str(report_path),
                "ES_F1_WORKSPACE": str(workspace),
            },
            timeout_seconds=timeout_seconds,
            label="artifact fixture verification",
        )
        if not report_path.is_file():
            raise EvaluatorError("artifact fixture verification produced no report")
        report = _load_canonical_unversioned(report_path)
    if _workspace_digest(workspace) != before:
        raise EvaluatorError("artifact fixture verification mutated the pre-edit copy")
    if set(report) != {
        "schema_version",
        "artifact_eras",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    } or report.get("schema_version") != "es-f1-artifact-fixture-verification.v1":
        raise EvaluatorError("artifact fixture verification report is not exact")
    if [
        row.get("era_id") if isinstance(row, Mapping) else None
        for row in report.get("artifact_eras", [])
    ] != list(ARTIFACT_ERA_IDS):
        raise EvaluatorError("artifact fixture verification era set/order drifted")
    return report


def _find_authority_field(value: Any, path: str = "$") -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _CANDIDATE_AUTHORITY_FIELDS:
                return f"{path}.{key}"
            found = _find_authority_field(item, f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_authority_field(item, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _validate_architecture_roles(
    candidate_claims: Mapping[str, Any],
    frozen_registry: set[str],
) -> None:
    roles = candidate_claims.get("nominated_architectures")
    if not isinstance(roles, Mapping) or set(roles) != {"representative", "witness"}:
        raise ValueError("candidate architecture roles must name representative and witness")
    representative = roles["representative"]
    witness = roles["witness"]
    if not isinstance(representative, str) or representative not in frozen_registry:
        raise ValueError("representative must be one frozen registry architecture")
    if not isinstance(witness, str) or not witness or witness in frozen_registry:
        raise ValueError("witness must be candidate-declared and absent from frozen registry")
    if witness == representative:
        raise ValueError("witness and representative must be distinct")


def evaluate_observations(
    *,
    candidate_claims: Mapping[str, Any],
    evaluator_observations: list[Mapping[str, Any]],
    dispositions: Mapping[str, str],
    frozen_registry: set[str],
) -> dict[str, Any]:
    """Normalize evaluator facts without granting authority to candidate claims."""

    if not isinstance(candidate_claims, Mapping):
        raise ValueError("candidate claims must be an object")
    authority_field = _find_authority_field(candidate_claims)
    if authority_field is not None:
        raise ValueError(
            f"candidate record cannot carry evaluator authority at {authority_field}"
        )
    candidate_id = candidate_claims.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate_id must be a non-empty string")
    _validate_architecture_roles(candidate_claims, frozen_registry)

    by_id: dict[str, Mapping[str, Any]] = {}
    for row in evaluator_observations:
        if not isinstance(row, Mapping):
            raise ValueError("evaluator observation must be an object")
        if set(row) != {"clause_id", "satisfied", "evidence", "details"}:
            raise ValueError("evaluator observation field set is not exact")
        clause_id = row["clause_id"]
        if clause_id not in HARD_CLAUSE_IDS:
            raise ValueError(f"unknown hard clause {clause_id!r}")
        if clause_id in by_id:
            raise ValueError(f"duplicate hard clause observation {clause_id!r}")
        if type(row["satisfied"]) is not bool:
            raise ValueError("observation satisfied must be a boolean")
        evidence = row["evidence"]
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(
                not isinstance(item, str)
                or not item.startswith("sha256:")
                or len(item) != 71
                for item in evidence
            )
        ):
            raise ValueError("observation evidence must be a non-empty SHA-256 list")
        if not isinstance(row["details"], str):
            raise ValueError("observation details must be a string")
        by_id[clause_id] = row
    if set(by_id) != set(HARD_CLAUSE_IDS):
        raise ValueError("evaluator observations must cover all ten hard clauses exactly")

    failed = {clause_id for clause_id, row in by_id.items() if not row["satisfied"]}
    if set(dispositions) != failed:
        raise ValueError("dispositions must cover exactly the failed hard clauses")
    invalid_dispositions = set(dispositions.values()) - set(DISPOSITIONS)
    if invalid_dispositions:
        raise ValueError(f"unknown finding dispositions: {sorted(invalid_dispositions)}")

    normalized = []
    findings = []
    for clause_id in HARD_CLAUSE_IDS:
        raw = by_id[clause_id]
        evidence_digest = _digest(raw["evidence"])
        observation = {
            "clause_id": clause_id,
            "details": raw["details"],
            "evidence_digest": evidence_digest,
            "satisfied": raw["satisfied"],
        }
        normalized.append(observation)
        if not raw["satisfied"]:
            findings.append(
                {
                    "candidate_id": candidate_id,
                    "clause_id": clause_id,
                    "details": raw["details"],
                    "disposition": dispositions[clause_id],
                    "evaluator_observation": {
                        "evidence_digest": evidence_digest,
                        "satisfied": False,
                    },
                    "schema_version": "es-f1-hard-finding.v1",
                }
            )
    return {
        "schema_version": "es-f1-hard-evaluation.v1",
        "candidate_id": candidate_id,
        "candidate_claims_digest": _digest(candidate_claims),
        "evaluator_observations": normalized,
        "hard_findings": findings,
    }


def validate_calibration_case(case: Mapping[str, Any]) -> None:
    """Validate one operation-backed calibration declaration without deriving facts."""

    if not isinstance(case, Mapping) or set(case) != {
        "case_id",
        "defect_kind",
        "operation_fixture",
        "intended_failed_clauses",
    }:
        raise ValueError("calibration case field set is not exact")
    if not isinstance(case["case_id"], str) or not case["case_id"]:
        raise ValueError("calibration case_id must be a non-empty string")
    defect_kind = case["defect_kind"]
    if defect_kind not in CALIBRATION_DEFECT_CLAUSES:
        raise ValueError(f"unknown calibration defect kind {defect_kind!r}")
    if case["operation_fixture"] != f"public-lifecycle:{defect_kind}":
        raise ValueError("calibration operation fixture is not bound to its defect")
    intended = case["intended_failed_clauses"]
    if intended != list(CALIBRATION_DEFECT_CLAUSES[defect_kind]):
        raise ValueError("calibration intended clauses drifted from operation contract")


def derive_calibration_error_observation(
    case: Mapping[str, Any], error: EvaluatorError
) -> dict[str, Any]:
    """Expose a typed mechanism failure without consulting the defect label."""

    validate_calibration_case(case)
    if not isinstance(error, EvaluatorObservationError):
        raise ValueError("calibration failure is not a typed mechanism observation")
    return error.as_observation()
