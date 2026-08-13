"""Controller-owned hard evaluator for the ES F1 calibration package.

The evaluator is intentionally outside candidate workspaces.  It consumes
closed, canonical records and derives observations independently of candidate
claims; candidates never author a clause result.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
from copy import deepcopy
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Mapping, Sequence
from functools import lru_cache

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from scripts.experiments.es.task_package import (
    F1_BUILTIN_ARCHITECTURES,
    F1_HARD_CLAUSE_IDS,
    F1_LIFECYCLE_STAGES,
    TaskPackageError,
    load_candidate_extension_evidence,
    load_lifecycle_probe_request,
    load_lifecycle_probe_result,
)


HARD_CLAUSE_IDS = F1_HARD_CLAUSE_IDS

F1_PUBLIC_CONSTRUCTION_ROUTE = (
    "ptycho_torch.generators.registry.resolve_generator"
)
F1_PUBLIC_PERSISTED_REBUILD_ROUTE = (
    "ptycho_torch.application_factory.build_ptychopinn_application"
)
F1_MAX_OPTIMIZER_STEP_ABS_DELTA = 1.0
F1_BUILTIN_STRUCTURAL_DECLARATIONS = tuple(
    (
        architecture_id,
        (
            (
                "architecture",
                architecture_id,
                f"{architecture_id}-alternate",
            ),
        ),
    )
    for architecture_id in F1_BUILTIN_ARCHITECTURES
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

EVALUATOR_SUCCESSOR_SCHEMA_VERSIONS = {
    "visible-check-result": (
        "es-f1-visible-check-result.v1",
        "es-f1-visible-check-result.v2",
    ),
    "preedit-lifecycle-probe": (
        "es-f1-preedit-lifecycle-probe.v1",
        "es-f1-preedit-lifecycle-probe.v2",
    ),
    "semantic-lifecycle": (
        "es-f1-semantic-lifecycle.v1",
        "es-f1-semantic-lifecycle.v2",
    ),
    "semantic-lifecycle-failure": (
        "es-f1-semantic-lifecycle-failure.v1",
        "es-f1-semantic-lifecycle-failure.v2",
    ),
    "artifact-fixture-input": (
        "es-f1-artifact-fixture-input.v1",
        "es-f1-artifact-fixture-input.v2",
    ),
    "artifact-fixture-build": (
        "es-f1-artifact-fixture-build.v1",
        "es-f1-artifact-fixture-build.v2",
    ),
    "artifact-fixture-verification": (
        "es-f1-artifact-fixture-verification.v1",
        "es-f1-artifact-fixture-verification.v2",
    ),
}

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

F1_CANDIDATE_WITNESS_PLACEHOLDER = "$candidate_witness"
F1_ARTIFACT_ARCHITECTURE_DOMAIN = (
    *F1_BUILTIN_ARCHITECTURES,
    F1_CANDIDATE_WITNESS_PLACEHOLDER,
)
_F1_FFNO_HISTORICAL_ARTIFACT_ERAS = frozenset(
    {
        "torch-model-spec-v1",
        "torch-model-spec-v2",
        "torch-artifact-v1",
        "torch-artifact-v2",
        "legacy-config-only-checkpoint",
        "current-model-spec-v2-checkpoint",
        "transitional-ci-entrypoints-v1-bundle",
        "torch-artifact-v1-bundle",
        "torch-artifact-v2-bundle",
    }
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

_LEGACY_BYPASS_AUTHORITY_ROOT = (
    _REPOSITORY_ROOT / "docs/plans/evidence/es-f1-large-scope-refreeze"
)
_LEGACY_BYPASS_AUTHORITY_BINDINGS = {
    "preedit_policy": (
        "preedit-policy-manifest.json",
        "preedit-policy-manifest.schema.json",
        "sha256:58c757172ca0c7bb667f7b1291a09d9ec8e37866fe6cd04d903037a5a8bd5c85",
    ),
    "source_census": (
        "source-census.json",
        "source-census.schema.json",
        "sha256:d1e6a55a20e0b671f1cd6ec7b265ba7acbe78f4b7bb22c976a9857dcae6b50f6",
    ),
    "selector_manifest": (
        "preedit-selector-manifest.json",
        "preedit-selector-manifest.schema.json",
        "sha256:6c19fddc893e313acb89bb14d878988699c1d1d29b0e2355d00ad69a98926305",
    ),
    "review_adoption": (
        "task0-review-adoption.json",
        "task0-review-adoption.schema.json",
        "sha256:f8e0a807709b7415458820795026695fd22672c31541ee8026acbe8a8245ac37",
    ),
}
_LEGACY_BYPASS_INVENTORY_SHA256 = (
    "sha256:3701ca66235df5733ceb5bb54fa0c118519a9ae0e3acd5515bef7af9e78c119c"
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
    "es-f1-fixture-manifest.v2": frozenset(
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
    "es-f1-calibration-cases.v3": frozenset({"schema_version", "cases"}),
    "es_f1_visible_checks.v2": frozenset(
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
    "same_process_reload": ("F1-H05-FULL-ARCHITECTURE-LIFECYCLE",),
    "injection_dependent_reload": ("F1-H05-FULL-ARCHITECTURE-LIFECYCLE",),
    "checkpoint_field_loss": ("F1-H06-STRUCTURAL-ROUNDTRIP",),
    "bundle_field_loss": ("F1-H06-STRUCTURAL-ROUNDTRIP",),
    "identity_insensitive": ("F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",),
    "forbidden_import": ("F1-H10-OWNERSHIP-BOUNDARY",),
    "forbidden_path": ("F1-H10-OWNERSHIP-BOUNDARY",),
    "copy_mutation": ("F1-H10-OWNERSHIP-BOUNDARY",),
    "architecture_owned_boundary": ("F1-H10-OWNERSHIP-BOUNDARY",),
}

CALIBRATION_CASE_SEQUENCE = (
    ("conforming_control", "none"),
    ("missing_structural_identity", "missing_identity"),
    ("extra_structural_identity", "extra_identity"),
    ("unknown_structural_identity", "unknown_identity"),
    ("unsupported_structural_identity", "unsupported_identity"),
    ("candidate_schema_version_drift", "schema_version_drift"),
    ("public_persisted_disagreement", "route_disagreement"),
    ("missing_persisted_builder", "missing_persisted_builder"),
    ("non_fresh_reload", "same_process_reload"),
    ("injection_dependent_reload", "injection_dependent_reload"),
    ("checkpoint_witness_field_loss", "checkpoint_field_loss"),
    ("bundle_witness_field_loss", "bundle_field_loss"),
    ("unchanged_identity_after_structural_change", "identity_insensitive"),
    ("forbidden_import", "forbidden_import"),
    ("forbidden_path", "forbidden_path"),
    ("copy_mutation", "copy_mutation"),
    ("architecture_owned_scientific_boundary", "architecture_owned_boundary"),
)

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
    *,
    architecture_rows: Sequence[Mapping[str, Any]],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    """Build one evaluator-owned config/input pair for every lifecycle case."""

    if type(seed) is not int or not 0 <= seed <= 2_147_483_647:
        raise ValueError("lifecycle seed must be a 31-bit non-negative integer")
    rows = list(architecture_rows)
    if len(rows) != 15 or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("lifecycle architecture rows must contain exactly fifteen records")
    architecture_ids = tuple(row.get("public_id") for row in rows)
    if (
        architecture_ids[:14] != F1_BUILTIN_ARCHITECTURES
        or not isinstance(architecture_ids[-1], str)
        or not architecture_ids[-1]
        or architecture_ids[-1] in set(F1_BUILTIN_ARCHITECTURES)
        or len(set(architecture_ids)) != 15
    ):
        raise ValueError("lifecycle architecture rows are not the exact built-in-plus-witness order")
    if any(
        row.get("construction_route") != F1_PUBLIC_CONSTRUCTION_ROUTE
        or row.get("persisted_rebuild_route") != F1_PUBLIC_PERSISTED_REBUILD_ROUTE
        for row in rows
    ):
        raise EvaluatorObservationError(
            clause_id="F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
            mechanism="declared-construction-route-authority",
            evidence={
                "declared_routes": [
                    {
                        "architecture_id": row.get("public_id"),
                        "construction_route": row.get("construction_route"),
                        "persisted_rebuild_route": row.get(
                            "persisted_rebuild_route"
                        ),
                    }
                    for row in rows
                ],
                "expected_construction_route": F1_PUBLIC_CONSTRUCTION_ROUTE,
                "expected_persisted_rebuild_route": (
                    F1_PUBLIC_PERSISTED_REBUILD_ROUTE
                ),
            },
            detail="lifecycle declarations do not use the frozen public routes",
        )
    expected_builtin_fields = {
        architecture_id: [
            {
                "name": name,
                "baseline_value": baseline_value,
                "alternate_value": alternate_value,
            }
            for name, baseline_value, alternate_value in fields
        ]
        for architecture_id, fields in F1_BUILTIN_STRUCTURAL_DECLARATIONS
    }
    for row in rows[:14]:
        architecture_id = str(row["public_id"])
        if row.get("structural_fields") != expected_builtin_fields[architecture_id]:
            raise ValueError(
                "lifecycle built-in structural declarations must match evaluator authority"
            )

    cases: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for ordinal, row in enumerate(rows, start=1):
        architecture_id = str(row["public_id"])
        N = 128 if architecture_id == "neuralop_uno" else 64
        config_path = f"evaluator-inputs/{ordinal:02d}-{architecture_id}/base-config.json"
        input_path = f"evaluator-inputs/{ordinal:02d}-{architecture_id}/cdi-fixture.json"
        config_payload = canonical_json_bytes(
            {
                "schema_version": "es-f1-base-config.v1",
                "N": N,
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
                "subsample_seed": seed,
            }
        )
        input_payload = canonical_json_bytes(
            {
                "schema_version": "es-f1-cdi-fixture.v1",
                "diffraction_generator": "numpy-default-rng-random-float32.v1",
                "image_size": N,
                "probe_generator": "complex-ones.v1",
                "sample_count": 3,
                "seed": seed,
            }
        )
        payloads[config_path] = config_payload
        payloads[input_path] = input_payload
        cases.append(
            {
                "N": N,
                "architecture_id": architecture_id,
                "config": {
                    "path": config_path,
                    "sha256": "sha256:" + hashlib.sha256(config_payload).hexdigest(),
                },
                "construction_route": row["construction_route"],
                "input": {
                    "path": input_path,
                    "sha256": "sha256:" + hashlib.sha256(input_payload).hexdigest(),
                },
                "persisted_rebuild_route": row["persisted_rebuild_route"],
                "structural_fields": deepcopy(row["structural_fields"]),
            }
        )
    return cases, payloads


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


def require_evaluator_successor_schema(
    record: Mapping[str, Any],
    *,
    record_type: str,
) -> Mapping[str, Any]:
    """Reject predecessor and unknown evaluator records at their parse boundary."""

    versions = EVALUATOR_SUCCESSOR_SCHEMA_VERSIONS.get(record_type)
    if versions is None:
        raise EvaluatorError(f"unknown evaluator successor record type {record_type!r}")
    if not isinstance(record, Mapping):
        raise EvaluatorError(f"{record_type} must be an object")
    expected = versions[1]
    observed = record.get("schema_version")
    if observed != expected:
        raise EvaluatorError(
            f"{record_type} schema version mismatch: "
            f"expected {expected!r}, got {observed!r}"
        )
    return record


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

_REGISTRY_CONSTRUCTOR_IDENTITY_PROBE = r'''import json,os,pathlib,sys
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
report=pathlib.Path(os.environ["ES_F1_REPORT"])
architectures=json.loads(os.environ["ES_F1_ARCHITECTURES"])
editable_prefix="__editable___ptychopinn_"
sys.meta_path[:]=[hook for hook in sys.meta_path if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path_hooks[:]=[hook for hook in sys.path_hooks if not getattr(hook,"__module__","").startswith(editable_prefix)]
sys.path[:]=[value for value in sys.path if not str(value).startswith("__editable__.ptychopinn-")]
sys.path_importer_cache.clear()
for name in tuple(sys.modules):
    if name.startswith(editable_prefix): sys.modules.pop(name,None)
sys.path.insert(0,str(workspace))

from ptycho.config.config import ModelConfig,TrainingConfig
from ptycho_torch.generators.registry import resolve_generator

def canonical(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
rows=[]
for architecture in architectures:
    constructor=resolve_generator(TrainingConfig(model=ModelConfig(architecture=architecture)))
    rows.append({"architecture_id":architecture,"identity":type(constructor).__module__+"."+type(constructor).__qualname__})
report.write_bytes(canonical({"registry_constructor_identities":rows}))
'''

_DECLARED_STRUCTURAL_BINDING_PROBE = r'''
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
def differing_paths(left,right,path=()):
    if isinstance(left,dict) and isinstance(right,dict):
        rows=[]
        for name in sorted(set(left)&set(right)):
            rows.extend(differing_paths(left[name],right[name],path+(name,)))
        rows.extend(path+(name,) for name in sorted(set(left)-set(right)))
        return rows
    if isinstance(left,list) and isinstance(right,list) and len(left)==len(right):
        rows=[]
        for index,(left_item,right_item) in enumerate(zip(left,right)):
            rows.extend(differing_paths(left_item,right_item,path+(index,)))
        return rows
    return [] if type(left) is type(right) and left==right else [path]
def consistent_binding(value,key,expected):
    paths=keyed_paths(value,key)
    if not paths: raise RuntimeError("declared structural field location is absent or ambiguous")
    observed=[value_at(value,path) for path in paths]
    if any(type(item) is not type(expected) or item!=expected for item in observed): raise RuntimeError("declared structural field location is absent or ambiguous")
    return paths,observed[0]
def observed_structural_value(model_spec_architecture,value,declaration):
    name=declaration["name"]
    if name=="architecture": return model_spec_architecture
    paths=keyed_paths(value,name)
    if not paths: raise RuntimeError("declared structural field location is absent or ambiguous")
    observed=[value_at(value,path) for path in paths]
    first=observed[0]
    if any(type(item) is not type(first) or item!=first for item in observed[1:]): raise RuntimeError("declared structural field location is absent or ambiguous")
    return first
def declared_structural_binding(model_spec_architecture,value,declaration,alternate_value=None):
    name=declaration["name"]
    expected=declaration["baseline_value"]
    if name=="architecture":
        observed=model_spec_architecture
        paths=[] if alternate_value is None else differing_paths(value,alternate_value)
        if alternate_value is not None and not paths: raise RuntimeError("declared structural field location is absent or ambiguous")
    else:
        paths,observed=consistent_binding(value,name,expected)
    if type(observed) is not type(expected) or observed!=expected: raise RuntimeError("declared structural field location is absent or ambiguous")
    return paths,observed
'''


_FRESH_RELOAD_PROBE = (r'''import copy,hashlib,importlib,json,os,pathlib,sys
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
artifact_file=artifact if artifact.is_file() else artifact/"wts.h5.zip"
artifact_payload=artifact_file.read_bytes()
structural_declarations=json.loads(os.environ.get("ES_F1_STRUCTURAL_FIELDS","[]"))
image_size=int(os.environ["ES_F1_IMAGE_SIZE"])
seed=int(os.environ["ES_F1_SEED"])
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
def tensor_facts(value,repeat):
    item=value.detach(); repeated=repeat.detach(); delta=float((item-repeated).abs().max().cpu().item()) if item.numel() else 0.0; tolerance=0.0
    return {"deterministic":delta<=tolerance,"dtype":str(item.dtype).removeprefix("torch."),"finite":bool(torch.isfinite(item).all().cpu().item()),"max_abs_delta":delta,"observable_digest":"sha256:"+hashlib.sha256(canonical(tensor_record(item))).hexdigest(),"shape":list(item.shape),"tolerance":tolerance}
def input_digest(values):
    return "sha256:"+hashlib.sha256(canonical({name:tensor_record(value) for name,value in sorted(values.items())})).hexdigest()
def state_signature(value):
    rows=[{"dtype":str(item.dtype).removeprefix("torch."),"name":name,"shape":list(item.shape)} for name,item in sorted(value.state_dict().items())]
    return "sha256:"+hashlib.sha256(canonical(rows)).hexdigest()
''' + _DECLARED_STRUCTURAL_BINDING_PROBE + r'''
torch.manual_seed(seed)
x=torch.rand((1,1,image_size,image_size),dtype=torch.float32)
positions=torch.zeros((1,1,1,2),dtype=torch.float32)
probe=torch.ones((1,1,1,image_size,image_size),dtype=torch.complex64)
scale=torch.ones((1,1,1,1),dtype=torch.float32)
boundary_inputs={"images":x,"positions":positions,"probe":probe,"input_scale_factor":scale}
boundary_input_digest_before=input_digest(boundary_inputs)
model.eval()
with torch.no_grad():
    prediction=model.forward_predict(x,positions,probe,scale)
    repeated_prediction=model.forward_predict(x,positions,probe,scale)
inference_facts=tensor_facts(prediction,repeated_prediction)
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
structural_values={}
for declaration in structural_declarations:
    value=observed_structural_value(model_spec.architecture,model_spec_payload,declaration)
    structural_values[declaration["name"]]=value
payload={"artifact_bytes":len(artifact_payload),"artifact_sha256":"sha256:"+hashlib.sha256(artifact_payload).hexdigest(),"architecture_id":model_spec.architecture,"boundary_contract":boundary_contract(model),"boundary_input_digest_after":boundary_input_digest_after,"boundary_input_digest_before":boundary_input_digest_before,"boundary_owners":boundary_owners(model),"fresh_pid":os.getpid(),"implementation_identity":fq(model.model.autoencoder),"inference_deterministic":inference_facts["deterministic"],"inference_dtype":inference_facts["dtype"],"inference_finite":inference_facts["finite"],"inference_max_abs_delta":inference_facts["max_abs_delta"],"inference_shape":inference_facts["shape"],"inference_tolerance":inference_facts["tolerance"],"observable_digest":inference_facts["observable_digest"],"roles":roles,"state_signature":state_signature(model),"structural_values":structural_values,"loaded_forbidden_modules":forbidden,"outside_project_origin_rows":sorted(outside)}
report.write_bytes((json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8"))
''')

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
    "schema_version":"es-f1-preedit-lifecycle-probe.v2","architecture":"ffno",
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


_FULL_MATRIX_SEMANTIC_LIFECYCLE_PROBE = (r'''import copy,hashlib,importlib,json,os,pathlib,subprocess,sys
child_launch_environment=dict(os.environ)
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
output=pathlib.Path(os.environ["ES_F1_OUTPUT"]).resolve(strict=False)
report=pathlib.Path(os.environ["ES_F1_REPORT"])
request_path=pathlib.Path(os.environ["ES_F1_REQUEST"])
request=json.loads(request_path.read_bytes())
input_root=request_path.parent
evidence=json.loads(pathlib.Path(os.environ["ES_F1_CANDIDATE_EVIDENCE"]).read_bytes())
seed=int(request["seed"])
optimizer_step_bound=float(os.environ["ES_F1_OPTIMIZER_STEP_BOUND"])
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
from ptycho.config.config import ModelConfig as CanonicalModelConfig,PyTorchExecutionConfig,TrainingConfig as CanonicalTrainingConfig
from ptycho.raw_data import RawData
from ptycho_torch.artifact_schema import decode_artifact_identity,encode_artifact_identity,from_json_payload,to_json_payload
from ptycho_torch.config_factory import create_training_payload
from ptycho_torch.model_spec import ModelSpec
from ptycho_torch.workflows.components import run_cdi_example_torch

def canonical(value): return (json.dumps(value,allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def digest(value): return "sha256:"+hashlib.sha256(canonical(value)).hexdigest()
def fq(value): return type(value).__module__+"."+type(value).__qualname__
def callable_owner(value):
    target=getattr(value,"__func__",value)
    return target.__module__+"."+target.__qualname__
def boundary_owners(value):
    return {"compute_loss":callable_owner(value.compute_loss),"loss_forward":callable_owner(value.Loss.forward),"model_forward":callable_owner(value.model.forward),"physics_forward":callable_owner(value.model.forward_model.forward),"scaling":callable_owner(value.model.scaler.scale)}
def boundary_contract(value):
    return {"loss_function":value.model_config.loss_function,"measurement_domain":value.data_config.measurement_domain,"physics_forward_mode":value.model_config.physics_forward_mode,"scale_contract_version":value.data_config.scale_contract_version,"torch_loss_mode":value.training_config.torch_loss_mode}
def tensor_record(value):
    item=value.detach().cpu().contiguous()
    return {"dtype":str(item.dtype).removeprefix("torch."),"shape":list(item.shape),"sha256":"sha256:"+hashlib.sha256(item.numpy().tobytes()).hexdigest()}
def tensor_facts(value,repeat):
    item=value.detach(); repeated=repeat.detach(); delta=float((item-repeated).abs().max().cpu().item()) if item.numel() else 0.0; tolerance=0.0
    return {"deterministic":delta<=tolerance,"dtype":str(item.dtype).removeprefix("torch."),"finite":bool(torch.isfinite(item).all().cpu().item()),"max_abs_delta":delta,"observable_digest":digest(tensor_record(item)),"shape":list(item.shape),"tolerance":tolerance}
def input_digest(values): return digest({name:tensor_record(value) for name,value in sorted(values.items())})
def state_signature(model):
    return digest([{"dtype":str(value.dtype).removeprefix("torch."),"name":name,"shape":list(value.shape)} for name,value in sorted(model.state_dict().items())])
def state_value_digest(model):
    return digest({name:tensor_record(value) for name,value in sorted(model.state_dict().items())})
def observable(model,N):
    torch.manual_seed(seed)
    images=torch.rand((1,1,N,N),dtype=torch.float32)
    positions=torch.zeros((1,1,1,2),dtype=torch.float32)
    probe=torch.ones((1,1,1,N,N),dtype=torch.complex64)
    scale=torch.ones((1,1,1,1),dtype=torch.float32)
    model.eval()
    with torch.no_grad():
        prediction=model.forward_predict(images,positions,probe,scale)
        repeated_prediction=model.forward_predict(images,positions,probe,scale)
    return tensor_facts(prediction,repeated_prediction)
def operation_failure(stage,exc,audit_events=None):
    detail=str(exc)
    payload={"schema_version":"es-f1-semantic-lifecycle-failure.v2","stage":stage,"exception_type":type(exc).__name__,"exception_detail_sha256":"sha256:"+hashlib.sha256(detail.encode("utf-8")).hexdigest()}
    if audit_events is not None: payload["audit_events"]=audit_events
    report.write_bytes(canonical(payload)); raise SystemExit(0)
def resolve_route(route):
    if not isinstance(route,str) or not route or route.startswith(".") or route.endswith(".") or ".." in route: raise ValueError("declared route is malformed")
    parts=route.split("."); module=None; split_at=0
    for index in range(len(parts),0,-1):
        try: module=importlib.import_module(".".join(parts[:index]))
        except ModuleNotFoundError as exc:
            if exc.name!=".".join(parts[:index]): raise
            continue
        split_at=index; break
    if module is None: raise ValueError("declared route module does not exist")
    target=module
    for name in parts[split_at:]: target=getattr(target,name)
    if not callable(target): raise TypeError("declared route is not callable")
    return target
''' + _DECLARED_STRUCTURAL_BINDING_PROBE + r'''
def parent_at(value,path):
    target=value
    for part in path[:-1]: target=target[part]
    return target
def add_extra_structural_field(value):
    if isinstance(value,dict):
        value["es_f1_extra_structural_field"]=1
        for item in tuple(value.values()): add_extra_structural_field(item)
    elif isinstance(value,list):
        for item in value: add_extra_structural_field(item)
def rejected(builder,payload,decoded):
    try:
        spec=ModelSpec.from_payload(copy.deepcopy(payload)); builder(spec,decoded.data_config,decoded.training_config,decoded.inference_config)
    except Exception as exc:
        return {"exception_detail_sha256":"sha256:"+hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),"exception_type":type(exc).__name__,"module_returned":False,"rejected":True}
    return {"exception_detail_sha256":"sha256:"+hashlib.sha256(b"").hexdigest(),"exception_type":None,"module_returned":True,"rejected":False}
def unsupported(value):
    if type(value) is bool: return None
    if isinstance(value,(int,float)) and not isinstance(value,bool): return 0 if value!=0 else -1
    if isinstance(value,str): return "es_f1_unsupported_value"
    return None
def reload(name):
    child_report=output/(name+".json"); child_program=output/(name+"-program.py"); child_audit=output/(name+"-audit.json")
    child_program.write_text(child_code,encoding="utf-8",newline="\n")
    spec=json.loads(os.environ["ES_F1_CONTROLLED_CHILD_SPECS"])[str(child_program)]
    env=dict(child_launch_environment); env.update(spec["environment_updates"])
    proc=subprocess.run([sys.executable,"-B","-c",os.environ["ES_F1_NESTED_WRAPPER"],os.environ["ES_F1_PROTECTED_ROOTS"],str(child_program),str(child_audit),str(workspace),spec["cwd"]],cwd=spec["cwd"],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    nested=json.loads(child_audit.read_bytes()) if child_audit.is_file() else {"events":[]}
    if nested.get("events"): operation_failure("OWNERSHIP_BOUNDARY",RuntimeError("nested candidate-process audit rejected the reload"),nested["events"])
    if proc.returncode!=0: raise RuntimeError("fresh reload failed: "+proc.stderr)
    return json.loads(child_report.read_bytes())

declarations=[*evidence["builtin_architectures"],evidence["candidate_witness"]]
cases=request["architecture_cases"]
if len(declarations)!=15 or [row["public_id"] for row in declarations]!=[row["architecture_id"] for row in cases]: raise RuntimeError("full-matrix declaration join drifted")
builtin_structural_names={field["name"] for declaration in declarations[:-1] for field in declaration["structural_fields"]}
execution=PyTorchExecutionConfig(accelerator="cpu",deterministic=True,num_workers=0,enable_progress_bar=False,enable_checkpointing=False,logger_backend=None)
architecture_results=[]; all_forbidden=set(); all_outside=[]; unknown_route=None; unknown_configs=None
for ordinal,(declaration,case) in enumerate(zip(declarations,cases),start=1):
    architecture=case["architecture_id"]; N=case["N"]
    base=json.loads((input_root/case["config"]["path"]).read_bytes())
    fixture=json.loads((input_root/case["input"]["path"]).read_bytes())
    if base["N"]!=N or fixture["image_size"]!=N: raise RuntimeError("evaluator input size drifted")
    structural_rows=case["structural_fields"]
    structural_names=[row["name"] for row in structural_rows]
    baseline={row["name"]:row["baseline_value"] for row in structural_rows}
    alternate={row["name"]:row["alternate_value"] for row in structural_rows}
    try:
        construction_route=resolve_route(case["construction_route"]); persisted_route=resolve_route(case["persisted_rebuild_route"])
    except Exception as exc: operation_failure("ROUTE_RESOLUTION",exc)
    row_output=output/(f"{ordinal:02d}-"+architecture); row_output.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(fixture["seed"])
    diffraction=rng.random((fixture["sample_count"],N,N),dtype=np.float32)
    probe_guess=np.ones((N,N),dtype=np.complex64)
    data_path=row_output/"train.npz"; np.savez(data_path,diffraction=diffraction,probeGuess=probe_guess)
    overrides={name:value for name,value in base.items() if name!="schema_version"}; overrides["architecture"]=architecture
    payload=create_training_payload(data_path,row_output/"configuration",overrides=overrides,execution_config=execution)
    public_payload=payload.model_spec.to_payload(); structural_paths={}; structural_values={}; alternate_specs={}
    for field_ordinal,structural_row in enumerate(structural_rows,start=1):
        name=structural_row["name"]
        alternate_overrides=dict(overrides); alternate_overrides[name]=alternate[name]
        alternate_training_payload=create_training_payload(data_path,row_output/(f"alternate-{field_ordinal:02d}"),overrides=alternate_overrides,execution_config=execution)
        alternate_spec=alternate_training_payload.model_spec; alternate_public_payload=alternate_spec.to_payload()
        paths,value=declared_structural_binding(payload.model_spec.architecture,public_payload,structural_row,alternate_public_payload if name=="architecture" else None)
        if name=="architecture":
            if type(alternate_spec.architecture) is not type(alternate[name]) or alternate_spec.architecture!=alternate[name]: raise RuntimeError("declared structural field location is absent or ambiguous")
        else:
            consistent_binding(alternate_public_payload,name,alternate[name])
        structural_paths[name]=paths; structural_values[name]=value; alternate_specs[name]=alternate_spec
    configs={"data_config":payload.pt_data_config,"model_config":payload.pt_model_config,"training_config":payload.pt_training_config,"inference_config":payload.pt_inference_config}
    try:
        registry_constructor=construction_route(payload.tf_training_config)
        registry_constructor_identity=fq(registry_constructor)
        torch.manual_seed(seed); public=registry_constructor.build_model(configs)
    except Exception as exc: operation_failure("PUBLIC_BUILD",exc)
    try:
        torch.manual_seed(seed); persisted=persisted_route(payload.model_spec,payload.pt_data_config,payload.pt_training_config,payload.pt_inference_config)
    except Exception as exc: operation_failure("PERSISTED_BUILD",exc)
    public_impl=fq(public.model.autoencoder); persisted_impl=fq(persisted.model.autoencoder)
    public_state=state_signature(public); persisted_state=state_signature(persisted)
    baseline_sensitivity_digest=observable(public,N)["observable_digest"]
    torch.manual_seed(seed)
    images=torch.rand((1,1,N,N),dtype=torch.float32); positions=torch.zeros((1,1,1,2),dtype=torch.float32); probe=torch.ones((1,1,1,N,N),dtype=torch.complex64)
    rms=torch.ones((1,1,1,1),dtype=torch.float32); physics=torch.ones((1,1,1,1),dtype=torch.float32); experiment=torch.zeros(1,dtype=torch.long); scale=torch.ones(1,dtype=torch.float32)
    batch=({"images":images,"coords_relative":positions,"rms_scaling_constant":rms,"physics_scaling_constant":physics,"experiment_id":experiment},probe,scale)
    boundary_inputs={"experiment_id":experiment,"images":images,"input_scale_factor":rms,"output_scale_factor":rms,"physics_scaling_constant":physics,"positions":positions,"probe":probe,"probe_scaling":scale}
    boundary_before=input_digest(boundary_inputs)
    persisted.train(); prediction,_,_=persisted(images,positions,probe,rms,rms,experiment); loss=persisted.compute_loss(batch)
    optimizer=persisted.configure_optimizers()["optimizer"]; optimizer_before=state_value_digest(persisted); optimizer.zero_grad(); loss.backward()
    gradients=[parameter.grad for parameter in persisted.parameters() if parameter.grad is not None]
    gradients_finite=bool(gradients) and all(bool(torch.isfinite(gradient).all().cpu().item()) for gradient in gradients)
    parameter_before={name:parameter.detach().clone() for name,parameter in persisted.named_parameters()}
    optimizer.step(); optimizer_after=state_value_digest(persisted)
    optimizer_deltas=[float((parameter.detach()-parameter_before[name]).abs().max().cpu().item()) for name,parameter in persisted.named_parameters() if parameter.numel()]
    optimizer_step_max_abs_delta=max(optimizer_deltas,default=0.0)
    optimizer_transition_bounded=bool(np.isfinite(optimizer_step_max_abs_delta) and 0.0<optimizer_step_max_abs_delta<=optimizer_step_bound)
    boundary_after=input_digest(boundary_inputs); inference_facts=observable(persisted,N); inference_digest=inference_facts["observable_digest"]
    checkpoint=row_output/"evaluator.ckpt"; trainer=Trainer(max_epochs=0,enable_checkpointing=True,logger=False,enable_progress_bar=False,accelerator="cpu",default_root_dir=row_output); trainer.strategy._lightning_module=persisted; trainer.save_checkpoint(checkpoint)
    coords=np.arange(fixture["sample_count"],dtype=np.float64)
    raw_data=RawData(xcoords=coords,ycoords=coords,xcoords_start=coords,ycoords_start=coords,diff3d=diffraction,probeGuess=probe_guess,scan_index=np.arange(fixture["sample_count"],dtype=int))
    torch.manual_seed(seed)
    _,_,workflow_results=run_cdi_example_torch(raw_data,None,payload.tf_training_config,do_stitching=False,execution_config=execution,overrides={"scale_contract_version":base["scale_contract_version"],"measurement_domain":base["measurement_domain"]})
    bundle_model=workflow_results["models"]["diffraction_to_obj"]; bundle_dir=pathlib.Path(payload.tf_training_config.output_dir)
    if not (bundle_dir/"wts.h5.zip").is_file(): raise RuntimeError("public workflow produced no bundle")
    checkpoint_reload=reload(f"{ordinal:02d}-{architecture}-checkpoint-reload"); bundle_reload=reload(f"{ordinal:02d}-{architecture}-bundle-reload")
    identity=to_json_payload(encode_artifact_identity(payload.model_spec,payload.pt_data_config,payload.pt_training_config,payload.pt_inference_config)); decoded=decode_artifact_identity(from_json_payload(identity)); rebuilt=persisted_route(decoded.model_spec,decoded.data_config,decoded.training_config,decoded.inference_config)
    sensitivities={}
    for field in structural_names:
        alternate_spec=alternate_specs[field]
        alternate_identity=to_json_payload(encode_artifact_identity(alternate_spec,decoded.data_config,decoded.training_config,decoded.inference_config))
        alternate_identity_repeat=to_json_payload(encode_artifact_identity(alternate_spec,decoded.data_config,decoded.training_config,decoded.inference_config))
        alternate_observable=baseline_sensitivity_digest; alternate_state=public_state; deterministic=alternate_identity==alternate_identity_repeat
        if field not in builtin_structural_names:
            torch.manual_seed(seed); alternate_model=persisted_route(alternate_spec,decoded.data_config,decoded.training_config,decoded.inference_config)
            alternate_facts=observable(alternate_model,N); alternate_observable=alternate_facts["observable_digest"]; alternate_state=state_signature(alternate_model)
            deterministic=deterministic and alternate_facts["deterministic"]
        sensitivities[field]={"alternate_identity_digest":digest(alternate_identity),"alternate_observable_digest":alternate_observable,"alternate_state_signature":alternate_state,"baseline_identity_digest":digest(identity),"baseline_observable_digest":baseline_sensitivity_digest,"baseline_state_signature":public_state,"deterministic":deterministic}
    missing={}
    for field in structural_names:
        candidate=copy.deepcopy(public_payload)
        for path in structural_paths[field]: parent_at(candidate,path).pop(path[-1])
        missing[field]=rejected(persisted_route,candidate,decoded)
    extra=copy.deepcopy(public_payload)
    for value in tuple(extra.values()): add_extra_structural_field(value)
    unsupported_payload=copy.deepcopy(public_payload); first=structural_names[0]
    for path in structural_paths[first]: parent_at(unsupported_payload,path)[path[-1]]=unsupported(parent_at(unsupported_payload,path)[path[-1]])
    identity_rejections={"missing":missing,"extra":rejected(persisted_route,extra,decoded),"unsupported_value":rejected(persisted_route,unsupported_payload,decoded)}
    row={"N":N,"architecture_id":architecture,"boundary_contract":boundary_contract(persisted),"boundary_input_digest_after":boundary_after,"boundary_input_digest_before":boundary_before,"bundle_implementation":fq(bundle_model.model.autoencoder),"completed_stages":request["required_lifecycle_stages"],"config_digest":case["config"]["sha256"],"construction_route":case["construction_route"],"registry_constructor_identity":registry_constructor_identity,"evaluator_bundle_reload":bundle_reload,"evaluator_checkpoint_reload":checkpoint_reload,"forward_deterministic":inference_facts["deterministic"],"forward_dtype":inference_facts["dtype"],"forward_finite":inference_facts["finite"],"forward_max_abs_delta":inference_facts["max_abs_delta"],"forward_shape":inference_facts["shape"],"forward_tolerance":inference_facts["tolerance"],"gradients_finite":gradients_finite,"identity_rejections":identity_rejections,"identity_sensitivity":sensitivities,"inference_digest":inference_digest,"input_digest":case["input"]["sha256"],"loss_finite":bool(torch.isfinite(loss).all().cpu().item()),"loss_scalar":bool(loss.numel()==1 and loss.ndim==0),"optimizer_state_after":optimizer_after,"optimizer_state_before":optimizer_before,"optimizer_step_bound":optimizer_step_bound,"optimizer_step_max_abs_delta":optimizer_step_max_abs_delta,"optimizer_transition_bounded":optimizer_transition_bounded,"persisted_boundary_owners":boundary_owners(persisted),"persisted_implementation":persisted_impl,"persisted_rebuild_implementation":fq(rebuilt.model.autoencoder),"persisted_rebuild_route":case["persisted_rebuild_route"],"persisted_state_signature":persisted_state,"public_boundary_owners":boundary_owners(public),"public_implementation":public_impl,"public_state_signature":public_state,"seed":seed,"structural_fields":structural_rows,"structural_values":structural_values}
    architecture_results.append(row); unknown_route=construction_route; unknown_configs=configs
    all_forbidden.update(checkpoint_reload["loaded_forbidden_modules"]); all_forbidden.update(bundle_reload["loaded_forbidden_modules"]); all_outside.extend(checkpoint_reload["outside_project_origin_rows"]); all_outside.extend(bundle_reload["outside_project_origin_rows"])

try:
    unknown_training=CanonicalTrainingConfig(model=CanonicalModelConfig(architecture="es_f1_unknown_architecture")); unknown_route(unknown_training).build_model(unknown_configs)
except Exception as exc:
    unknown_rejection={"exception_detail_sha256":"sha256:"+hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),"exception_type":type(exc).__name__,"module_returned":False,"rejected":True}
else:
    unknown_rejection={"exception_detail_sha256":"sha256:"+hashlib.sha256(b"").hexdigest(),"exception_type":None,"module_returned":True,"rejected":False}
forbidden_prefixes=("ptycho.evaluation","ptycho.FRC","PtychoNN","notebooks.archive.ePIE_recon_simulation","scripts.orchestration")
all_forbidden.update(name for name in sys.modules if any(name==prefix or name.startswith(prefix+".") for prefix in forbidden_prefixes))
for name,module in tuple(sys.modules.items()):
    if not (name=="ptycho" or name.startswith("ptycho.") or name=="ptycho_torch" or name.startswith("ptycho_torch.")): continue
    values=[]; origin=getattr(getattr(module,"__spec__",None),"origin",None); module_file=getattr(module,"__file__",None)
    if isinstance(origin,str): values.append(origin)
    if isinstance(module_file,str): values.append(module_file)
    for value in values:
        path=pathlib.Path(value)
        if path.is_absolute() and not path.resolve(strict=False).is_relative_to(workspace): all_outside.append([name,str(path.resolve(strict=False))])
cache=sorted(path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.name=="__pycache__" or path.suffix in {".pyc",".pyo"})
result={"schema_version":"es-f1-semantic-lifecycle.v2","construction_pid":os.getpid(),"architecture_results":architecture_results,"unknown_architecture_rejection":unknown_rejection,"loaded_forbidden_modules":sorted(all_forbidden),"outside_project_origin_rows":sorted({tuple(row) for row in all_outside}),"cache_artifacts":cache}
report.write_bytes(canonical(result))
''')

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
report.write_bytes(canonical({"schema_version":"es-f1-artifact-fixture-build.v2","artifact_eras":rows}))
'''

_ARTIFACT_FIXTURE_VERIFY_PROBE = r'''import json,os,pathlib,shutil,sys,tempfile
workspace=pathlib.Path(os.environ["ES_F1_WORKSPACE"]).resolve(strict=True)
rows_path=pathlib.Path(os.environ["ES_F1_FIXTURE_ROWS"])
report=pathlib.Path(os.environ["ES_F1_REPORT"])
rows_record=json.loads(rows_path.read_bytes())
if not isinstance(rows_record,dict) or rows_record.get("schema_version")!="es-f1-artifact-fixture-input.v2" or set(rows_record)!={"schema_version","artifact_eras"}: raise RuntimeError("artifact fixture input schema version/shape mismatch")
rows=rows_record["artifact_eras"]
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
observed_by_era={}
with tempfile.TemporaryDirectory(prefix="es-f1-era-load-") as raw_temp:
    temporary=pathlib.Path(raw_temp)
    for row in rows:
        era=row["era_id"]; architecture=row["architecture_id"]
        if row["expected_outcome"]=="REJECTED":
            outcome={"architecture_id":architecture,"diagnostic":"UNSUPPORTED_ARTIFACT_ARCHITECTURE","implementation_identity":None,"module_returned":False,"strict_load":False}
            observed_by_era.setdefault(era,[]).append(outcome); continue
        if row["expected_outcome"]!="LOAD": raise RuntimeError("artifact expected outcome is invalid")
        path=pathlib.Path(row["absolute_path"])
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
        outcome={"architecture_id":architecture,"diagnostic":None,"implementation_identity":implementation,"module_returned":True,"strict_load":True}
        observed_by_era.setdefault(era,[]).append(outcome)
observed=[{"era_id":era,"architecture_results":observed_by_era[era]} for era in observed_by_era]

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
report.write_bytes(canonical({"schema_version":"es-f1-artifact-fixture-verification.v2","artifact_eras":observed,"loaded_forbidden_modules":forbidden,"outside_project_origin_rows":sorted(outside),"cache_artifacts":cache}))
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


def _load_strict_formatted_object(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid JSON scalar {token!r}")
            ),
        )
        if not isinstance(value, dict):
            raise ValueError("JSON root must be an object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EvaluatorError(f"JSON document is unavailable or invalid: {path}") from exc
    return value


def _load_strict_formatted_schema(path: Path) -> dict[str, Any]:
    """Load a bound JSON schema without requiring canonical byte formatting."""

    try:
        schema = _load_strict_formatted_object(path)
        Draft202012Validator.check_schema(schema)
    except (EvaluatorError, SchemaError, ValueError) as exc:
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


def _validate_formatted_schema_record(
    value: Mapping[str, Any],
    *,
    schema_path: Path,
    label: str,
) -> None:
    schema = _load_strict_formatted_schema(schema_path)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    if errors:
        raise EvaluatorError(f"{label} schema violation: {errors[0].message}")


@lru_cache(maxsize=1)
def _task0_bypass_authority() -> dict[str, Any]:
    """Load and cross-bind the immutable Task-0 bypass authority once."""

    records: dict[str, dict[str, Any]] = {}
    for role, (record_name, schema_name, expected_digest) in (
        _LEGACY_BYPASS_AUTHORITY_BINDINGS.items()
    ):
        record_path = _LEGACY_BYPASS_AUTHORITY_ROOT / record_name
        schema_path = _LEGACY_BYPASS_AUTHORITY_ROOT / schema_name
        record = _load_canonical_unversioned(record_path)
        _validate_formatted_schema_record(
            record,
            schema_path=schema_path,
            label=f"Task-0 {role}",
        )
        observed_digest = record.get("record_sha256")
        body = dict(record)
        body.pop("record_sha256", None)
        if observed_digest != expected_digest or _digest(body) != expected_digest:
            raise EvaluatorError(f"Task-0 {role} record digest drifted")
        records[role] = record

    policy = records["preedit_policy"]
    census = records["source_census"]
    selector = records["selector_manifest"]
    adoption = records["review_adoption"]
    schema_binding_rows = policy.get("schema_bindings")
    if not isinstance(schema_binding_rows, list):
        raise EvaluatorError("Task-0 schema authority bindings are unavailable")
    schema_bindings = {
        row.get("role"): row
        for row in schema_binding_rows
        if isinstance(row, Mapping) and isinstance(row.get("role"), str)
    }
    if (
        len(schema_bindings) != len(schema_binding_rows)
        or census.get("schema_bindings") != schema_binding_rows
    ):
        raise EvaluatorError("Task-0 schema authority bindings drifted")
    for role, (_, schema_name, _) in _LEGACY_BYPASS_AUTHORITY_BINDINGS.items():
        schema_path = _LEGACY_BYPASS_AUTHORITY_ROOT / schema_name
        try:
            raw_schema = schema_path.read_bytes()
        except OSError as exc:
            raise EvaluatorError("Task-0 bound schema is unavailable") from exc
        expected_path = schema_path.relative_to(_REPOSITORY_ROOT).as_posix()
        if schema_bindings.get(role) != {
            "byte_count": len(raw_schema),
            "path": expected_path,
            "role": role,
            "sha256": "sha256:" + hashlib.sha256(raw_schema).hexdigest(),
        }:
            raise EvaluatorError(f"Task-0 {role} schema binding drifted")
    discovery_input_path = _LEGACY_BYPASS_AUTHORITY_ROOT / "preedit-discovery-input.json"
    discovery_schema_path = (
        _LEGACY_BYPASS_AUTHORITY_ROOT / "preedit-discovery-input.schema.json"
    )
    discovery_input = _load_strict_formatted_object(discovery_input_path)
    _validate_formatted_schema_record(
        discovery_input,
        schema_path=discovery_schema_path,
        label="Task-0 discovery input",
    )
    raw_discovery_input = discovery_input_path.read_bytes()
    raw_discovery_schema = discovery_schema_path.read_bytes()
    if (
        "sha256:" + hashlib.sha256(raw_discovery_input).hexdigest()
        != policy["discovery"]["input_sha256"]
        or schema_bindings.get("discovery_input")
        != {
            "byte_count": len(raw_discovery_schema),
            "path": discovery_schema_path.relative_to(_REPOSITORY_ROOT).as_posix(),
            "role": "discovery_input",
            "sha256": "sha256:" + hashlib.sha256(raw_discovery_schema).hexdigest(),
        }
    ):
        raise EvaluatorError("Task-0 discovery input authority drifted")
    bindings = {
        "legacy_bypass_inventory_sha256": _digest(
            census["legacy_bypass_inventory"]
        ),
        "preedit_policy_sha256": policy["record_sha256"],
        "review_adoption_sha256": adoption["record_sha256"],
        "selector_manifest_sha256": selector["record_sha256"],
        "source_census_sha256": census["record_sha256"],
    }
    if (
        bindings["legacy_bypass_inventory_sha256"]
        != _LEGACY_BYPASS_INVENTORY_SHA256
        or policy["legacy_bypass_consumer_ids"]
        != census["legacy_bypass_inventory"]
        or selector["preedit_policy_sha256"] != policy["record_sha256"]
        or selector["source_census_sha256"] != census["record_sha256"]
        or adoption["bindings"]["preedit_policy_sha256"]
        != policy["record_sha256"]
        or adoption["bindings"]["source_census_sha256"]
        != census["record_sha256"]
        or adoption["bindings"]["selector_manifest_sha256"]
        != selector["record_sha256"]
        or adoption["evidence_status"] != "approved"
    ):
        raise EvaluatorError("Task-0 legacy bypass authority bindings drifted")

    try:
        from scripts.experiments.es import boundary_proofs

        runner_digests = {
            row["runner_sha256"] for row in selector["coverage_witnesses"]
        }
        if len(runner_digests) != 1:
            raise EvaluatorError("Task-0 bypass proof runner binding is ambiguous")
        contract = boundary_proofs.validate_contract(
            selector,
            consumer_rows=census["consumer_rows"],
            expected_runner_sha256=next(iter(runner_digests)),
        )
    except EvaluatorError:
        raise
    except Exception as exc:
        raise EvaluatorError("Task-0 bypass proof contract is invalid") from exc

    consumers = {row["consumer_id"]: row for row in census["consumer_rows"]}
    inventory = census["legacy_bypass_inventory"]
    if (
        len(consumers) != len(census["consumer_rows"])
        or any(consumer_id not in consumers for consumer_id in inventory)
    ):
        raise EvaluatorError("Task-0 legacy bypass consumer domain is invalid")
    partition = {
        status + "_consumer_ids": [
            consumer_id
            for consumer_id in inventory
            if consumers[consumer_id]["coverage_status"] == status
        ]
        for status in ("required", "inherited", "open")
    }
    selected_ids = [spec.consumer_id for spec in contract.desired_specs]
    if (
        len(contract.desired_specs) != 23
        or len(selected_ids) != len(set(selected_ids))
        or not set(partition["required_consumer_ids"]) <= set(selected_ids)
        or sum(len(values) for values in partition.values()) != len(inventory)
    ):
        raise EvaluatorError("Task-0 bypass selected proof domain drifted")
    return {
        "bindings": bindings,
        "census": census,
        "contract": contract,
        "discovery_input": discovery_input,
        "partition": partition,
        "policy": policy,
        "runner_sha256": next(iter(runner_digests)),
        "selector": selector,
    }


_TASK0_CANDIDATE_IDENTITY_KEYS = {
    "anchor_id",
    "callee_or_dispatch_form",
    "caller_object_id",
    "caller_path",
    "consumer_id",
    "detector_id",
    "detector_version",
    "match_id",
    "responsibility_ids",
    "span",
}


def _task0_candidate_signature(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row["caller_path"],
        row["detector_id"],
        row["detector_version"],
        row["anchor_id"],
        row["callee_or_dispatch_form"],
        tuple(row["responsibility_ids"]),
    )


def _valid_task0_candidate_identity(row: Any) -> bool:
    if not isinstance(row, Mapping) or set(row) != _TASK0_CANDIDATE_IDENTITY_KEYS:
        return False
    span = row.get("span")
    caller_path = row.get("caller_path")
    path = PurePosixPath(caller_path) if isinstance(caller_path, str) else None
    return bool(
        isinstance(row.get("consumer_id"), str)
        and len(row["consumer_id"]) == 41
        and row["consumer_id"].startswith("consumer-")
        and all(character in "0123456789abcdef" for character in row["consumer_id"][9:])
        and isinstance(row.get("match_id"), str)
        and len(row["match_id"]) == 38
        and row["match_id"].startswith("match-")
        and all(character in "0123456789abcdef" for character in row["match_id"][6:])
        and isinstance(row.get("caller_object_id"), str)
        and len(row["caller_object_id"]) == 40
        and all(character in "0123456789abcdef" for character in row["caller_object_id"])
        and path is not None
        and not path.is_absolute()
        and caller_path == path.as_posix()
        and ".." not in path.parts
        and isinstance(row.get("responsibility_ids"), list)
        and bool(row["responsibility_ids"])
        and len(row["responsibility_ids"]) == len(set(row["responsibility_ids"]))
        and all(isinstance(value, str) and value for value in row["responsibility_ids"])
        and isinstance(span, Mapping)
        and set(span) == {"line_start", "column_start", "line_end", "column_end"}
        and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in span.values())
        and span["line_start"] >= 1
        and span["line_end"] >= span["line_start"]
        and all(
            isinstance(row.get(name), str) and bool(row[name])
            for name in (
                "anchor_id",
                "callee_or_dispatch_form",
                "detector_id",
                "detector_version",
            )
        )
    )


def _classify_task0_bypass_candidates(
    discovery_candidates: Sequence[Mapping[str, Any]],
    *,
    verified_construction_route: str,
) -> dict[str, Any]:
    """Classify fresh public source-census rows against the frozen Task-0 domain."""

    authority = _task0_bypass_authority()
    if verified_construction_route != F1_PUBLIC_CONSTRUCTION_ROUTE:
        raise EvaluatorError("legacy bypass construction route is not H09-verified")
    if (
        not isinstance(discovery_candidates, Sequence)
        or isinstance(discovery_candidates, (str, bytes))
        or any(not _valid_task0_candidate_identity(row) for row in discovery_candidates)
    ):
        raise EvaluatorError("legacy bypass discovery candidate domain is malformed")
    consumer_ids = [row["consumer_id"] for row in discovery_candidates]
    match_ids = [row["match_id"] for row in discovery_candidates]
    if len(consumer_ids) != len(set(consumer_ids)) or len(match_ids) != len(set(match_ids)):
        raise EvaluatorError("legacy bypass discovery candidate identities repeat")

    anchors = {
        anchor["anchor_id"]: anchor
        for detector in authority["policy"]["detectors"]
        for anchor in detector["anchors"]
    }
    direct_import_ids = {
        anchor_id
        for anchor_id, anchor in anchors.items()
        if anchor["form"] == "import"
        and "CONSTRUCTION_ARCHITECTURES" in anchor["responsibility_ids"]
        and "LEGACY_BYPASS_RETIREMENT" in anchor["responsibility_ids"]
    }
    package_anchor = anchors.get("GENERATOR_PACKAGE_IMPORT")
    registry_anchor = anchors.get("GENERATOR_REGISTRY_IMPORT")
    route_module, _, route_callable = verified_construction_route.rpartition(".")
    if (
        direct_import_ids
        != {"GENERATOR_PACKAGE_IMPORT", "GENERATOR_REGISTRY_IMPORT"}
        or not isinstance(package_anchor, Mapping)
        or not isinstance(registry_anchor, Mapping)
        or registry_anchor.get("pattern") != route_module
        or route_callable != "resolve_generator"
        or not isinstance(package_anchor.get("pattern"), str)
        or not route_module.startswith(package_anchor["pattern"] + ".")
    ):
        raise EvaluatorError("legacy bypass construction authority is inconsistent")
    boundary_root = PurePosixPath(*package_anchor["pattern"].split("."))

    frozen_by_signature: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for frozen in authority["census"]["consumer_rows"]:
        frozen_by_signature.setdefault(_task0_candidate_signature(frozen), []).append(frozen)
    absence_ids = {
        spec.consumer_id
        for spec in authority["contract"].desired_specs
        if spec.proof_kind == "reference_absence"
        and spec.expected_result == {"path_absent": True}
    }
    governed: list[dict[str, Any]] = []
    allowed: list[dict[str, Any]] = []
    disclosed: list[dict[str, Any]] = []
    novel: list[dict[str, Any]] = []
    restored: list[str] = []
    approved_route_calls = {
        (row["caller_path"], row["caller_object_id"], row["callee_or_dispatch_form"])
        for row in discovery_candidates
        if row["anchor_id"] == "RESOLVE_GENERATOR_CALL"
        and row["callee_or_dispatch_form"] == verified_construction_route
    }
    for candidate_value in discovery_candidates:
        candidate = deepcopy(dict(candidate_value))
        matching = frozen_by_signature.get(_task0_candidate_signature(candidate), [])
        if matching:
            frozen = matching.pop(0)
            governed.append(candidate)
            if frozen["consumer_id"] in absence_ids:
                restored.append(frozen["consumer_id"])
            continue
        candidate_path = PurePosixPath(candidate["caller_path"])
        is_boundary_owned = candidate_path.parts[: len(boundary_root.parts)] == boundary_root.parts
        if candidate["anchor_id"] in direct_import_ids:
            is_approved_route_import = (
                candidate["callee_or_dispatch_form"] == verified_construction_route
                and (
                    candidate["caller_path"],
                    candidate["caller_object_id"],
                    candidate["callee_or_dispatch_form"],
                )
                in approved_route_calls
            )
            (allowed if is_boundary_owned or is_approved_route_import else novel).append(
                candidate
            )
        else:
            disclosed.append(candidate)
    return {
        "allowed_boundary_matches": allowed,
        "authority_bindings": deepcopy(authority["bindings"]),
        "disclosed_matches": disclosed,
        "governed_matches": governed,
        "novel_direct_matches": novel,
        "restored_required_consumer_ids": restored,
        "schema_version": "es-f1-legacy-bypass-classification.v1",
        "verified_construction_route": verified_construction_route,
    }


def _fresh_task0_bypass_discovery(
    *,
    discovery_input: Mapping[str, Any],
    expected_tree: str | None = None,
) -> tuple[dict[str, Any], list[Mapping[str, Any]]]:
    """Run the public detector once against the frozen non-projection authority."""

    authority = _task0_bypass_authority()
    if not isinstance(discovery_input, Mapping):
        raise EvaluatorError("legacy bypass discovery contract is malformed")
    candidate_input = deepcopy(dict(discovery_input))
    frozen_input = deepcopy(authority["discovery_input"])
    projection = candidate_input.get("projection")
    candidate_input["projection"] = frozen_input["projection"]
    if candidate_input != frozen_input or not isinstance(projection, Mapping):
        raise EvaluatorError("legacy bypass detector authority drifted")
    if expected_tree is not None and projection.get("tree") != expected_tree:
        raise EvaluatorError("legacy bypass discovery tree binding drifted")
    candidate_input["projection"] = deepcopy(dict(projection))
    try:
        from scripts.experiments.es import source_census

        fresh = source_census.discover_source(
            candidate_input,
            discovery_input_sha256=_digest(candidate_input),
        )
    except Exception as exc:
        raise EvaluatorError("legacy bypass source discovery failed") from exc
    candidates = fresh.get("consumer_candidates")
    leaves = fresh.get("leaf_rows")
    if not isinstance(candidates, list) or not isinstance(leaves, list):
        raise EvaluatorError("legacy bypass discovery output is malformed")
    leaf_match_ids: list[str] = []
    leaf_keys: set[tuple[str, str, str]] = set()
    for leaf in leaves:
        if not isinstance(leaf, Mapping):
            raise EvaluatorError("legacy bypass discovery leaf domain is malformed")
        for match_id in leaf.get("match_ids", []):
            leaf_match_ids.append(match_id)
            leaf_keys.add((leaf.get("path"), leaf.get("object_id"), match_id))
    candidate_keys = {
        (row.get("caller_path"), row.get("caller_object_id"), row.get("match_id"))
        for row in candidates
        if isinstance(row, Mapping)
    }
    if (
        fresh.get("projection") != projection
        or fresh.get("candidate_set_sha256") != _digest(candidates)
        or len(candidate_keys) != len(candidates)
        or candidate_keys != leaf_keys
        or len(leaf_match_ids) != len(set(leaf_match_ids))
    ):
        raise EvaluatorError("legacy bypass discovery bindings are not exact")
    return fresh, candidates


def _validated_task0_bypass_discovery(
    *,
    discovery_input: Mapping[str, Any],
    discovery_output: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Re-run the frozen detector contract and reject partial supplied outputs."""

    if not isinstance(discovery_output, Mapping):
        raise EvaluatorError("legacy bypass discovery contract is malformed")
    fresh, candidates = _fresh_task0_bypass_discovery(
        discovery_input=discovery_input,
    )
    if fresh != deepcopy(dict(discovery_output)):
        raise EvaluatorError("legacy bypass discovery output is incomplete or drifted")
    return candidates


def classify_task0_bypass_discovery(
    *,
    discovery_input: Mapping[str, Any],
    discovery_output: Mapping[str, Any],
    verified_construction_route: str,
) -> dict[str, Any]:
    candidates = _validated_task0_bypass_discovery(
        discovery_input=discovery_input,
        discovery_output=discovery_output,
    )
    return _classify_task0_bypass_candidates(
        candidates,
        verified_construction_route=verified_construction_route,
    )


def _derive_task0_bypass_observation(
    legacy_bypass_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an evaluator-assembled Task-0 proof join and derive H05."""

    authority = _task0_bypass_authority()
    if (
        not isinstance(legacy_bypass_report, Mapping)
        or set(legacy_bypass_report)
        != {
            "bindings",
            "legacy_inventory_partition",
            "novel_matches",
            "schema_version",
            "selected_required_results",
        }
        or legacy_bypass_report.get("schema_version")
        != "es-f1-legacy-bypass-report.v1"
        or legacy_bypass_report.get("bindings") != authority["bindings"]
        or legacy_bypass_report.get("legacy_inventory_partition")
        != authority["partition"]
    ):
        raise EvaluatorError("legacy bypass report authority join is not exact")

    contract = authority["contract"]
    results = legacy_bypass_report.get("selected_required_results")
    if not isinstance(results, list) or len(results) != len(contract.desired_specs):
        raise EvaluatorError("legacy bypass selected result domain is not exact")
    runtime_kinds = {
        "pytest_runtime",
        "controller_pytest_runtime",
        "runtime_probe",
    }
    base_result_keys = {
        "consumer_id",
        "mechanically_observed",
        "observation",
        "observation_sha256",
        "ordinal",
        "passed",
        "proof_id",
        "proof_kind",
        "selector_id",
        "target_blob_id",
        "target_path",
        "target_tree",
        "witness_id",
        "witness_kind",
    }
    target_trees: set[str] = set()
    selected_passed = True
    for result, spec, witness in zip(
        results,
        contract.desired_specs,
        contract.witnesses,
        strict=True,
    ):
        expected_keys = (
            base_result_keys | {"source_event"}
            if witness.witness_kind in runtime_kinds
            else base_result_keys
        )
        if not isinstance(result, Mapping) or set(result) != expected_keys:
            raise EvaluatorError("legacy bypass desired result shape is not exact")
        observation = result["observation"]
        try:
            observation_digest = _digest(observation)
        except (TypeError, ValueError) as exc:
            raise EvaluatorError("legacy bypass observation is not canonical") from exc
        passed = observation == spec.expected_result
        target_tree = result["target_tree"]
        target_blob_id = result["target_blob_id"]
        if (
            result["proof_id"] != spec.proof_id
            or result["ordinal"] != spec.ordinal
            or result["selector_id"] != spec.selector_id
            or result["witness_id"] != spec.witness_id
            or result["consumer_id"] != spec.consumer_id
            or result["proof_kind"] != spec.proof_kind
            or result["witness_kind"] != witness.witness_kind
            or result["target_path"] != witness.consumer_path
            or result["mechanically_observed"] is not True
            or result["observation_sha256"] != observation_digest
            or result["passed"] is not passed
            or not isinstance(target_tree, str)
            or len(target_tree) != 40
            or any(character not in "0123456789abcdef" for character in target_tree)
            or (
                target_blob_id is not None
                and (
                    not isinstance(target_blob_id, str)
                    or len(target_blob_id) != 40
                    or any(
                        character not in "0123456789abcdef"
                        for character in target_blob_id
                    )
                )
            )
            or (
                observation == {"path_absent": True}
                and target_blob_id is not None
            )
            or (
                observation == {"path_absent": False}
                and target_blob_id is None
            )
            or (
                witness.witness_kind in runtime_kinds
                and result["source_event"] != observation
            )
        ):
            raise EvaluatorError("legacy bypass desired result binding drifted")
        target_trees.add(target_tree)
        selected_passed = selected_passed and passed
    if len(target_trees) != 1:
        raise EvaluatorError("legacy bypass desired results bind different trees")

    novel_matches = legacy_bypass_report.get("novel_matches")
    novel_keys = {
        "anchor_id",
        "callee_or_dispatch_form",
        "caller_object_id",
        "caller_path",
        "consumer_id",
        "detector_id",
        "detector_version",
        "match_id",
        "responsibility_ids",
        "span",
    }
    if not isinstance(novel_matches, list):
        raise EvaluatorError("legacy bypass novel match set is malformed")
    census_consumer_ids = {
        row["consumer_id"] for row in authority["census"]["consumer_rows"]
    }
    novel_consumer_ids: set[str] = set()
    novel_match_ids: set[str] = set()
    for row in novel_matches:
        if (
            not isinstance(row, Mapping)
            or set(row) != novel_keys
            or not isinstance(row["consumer_id"], str)
            or not row["consumer_id"].startswith("consumer-")
            or len(row["consumer_id"]) != 41
            or row["consumer_id"] in census_consumer_ids
            or row["consumer_id"] in novel_consumer_ids
            or not isinstance(row["match_id"], str)
            or not row["match_id"].startswith("match-")
            or len(row["match_id"]) != 38
            or row["match_id"] in novel_match_ids
            or not isinstance(row["caller_object_id"], str)
            or len(row["caller_object_id"]) != 40
            or not isinstance(row["responsibility_ids"], list)
            or "LEGACY_BYPASS_RETIREMENT" not in row["responsibility_ids"]
            or not isinstance(row["span"], Mapping)
            or set(row["span"])
            != {"line_start", "column_start", "line_end", "column_end"}
            or any(
                not isinstance(row.get(name), str) or not row[name]
                for name in (
                    "anchor_id",
                    "callee_or_dispatch_form",
                    "caller_path",
                    "detector_id",
                    "detector_version",
                )
            )
        ):
            raise EvaluatorError("legacy bypass novel match shape is not exact")
        novel_consumer_ids.add(row["consumer_id"])
        novel_match_ids.add(row["match_id"])
    return {
        "satisfied": selected_passed and not novel_matches,
        "evidence": _digest(legacy_bypass_report),
    }


def derive_authenticated_task0_bypass_observation(
    *,
    candidate_workspace: Path,
    proof_workspace: Path,
    candidate_tree: str,
    discovery_input: Mapping[str, Any],
    builtin_architecture_ids: Sequence[str],
    witness_architecture_id: str,
) -> dict[str, Any]:
    """Derive H05 only from fresh discovery and the pinned Task-0 runner."""

    if (
        not isinstance(candidate_tree, str)
        or len(candidate_tree) != 40
        or any(character not in "0123456789abcdef" for character in candidate_tree)
    ):
        raise EvaluatorError("legacy bypass candidate tree is malformed")
    workspace_value = Path(candidate_workspace)
    try:
        workspace = workspace_value.resolve(strict=True)
    except OSError as exc:
        raise EvaluatorError("legacy bypass candidate workspace is unavailable") from exc
    if not workspace_value.is_absolute() or workspace_value != workspace:
        raise EvaluatorError("legacy bypass candidate workspace is not canonical")

    fresh_discovery, candidates = _fresh_task0_bypass_discovery(
        discovery_input=discovery_input,
        expected_tree=candidate_tree,
    )
    classification = _classify_task0_bypass_candidates(
        candidates,
        verified_construction_route=F1_PUBLIC_CONSTRUCTION_ROUTE,
    )
    authority = _task0_bypass_authority()
    try:
        from scripts.experiments.es import boundary_proofs, reference_calibration

        execution_manifest = (
            reference_calibration.build_reference_desired_state_execution_manifest(
                authority["selector"],
                source_census=authority["census"],
                workspace=proof_workspace,
                expected_tree=candidate_tree,
                python=boundary_proofs.PINNED_PYTHON,
                pytest_carrier=boundary_proofs.PINNED_PYTEST_CARRIER,
                expected_pytest_carrier_sha256=(
                    boundary_proofs.PINNED_PYTEST_CARRIER_SHA256
                ),
                builtin_architecture_ids=builtin_architecture_ids,
                witness_architecture_id=witness_architecture_id,
                forbidden_roots=(),
            )
        )
        desired_rows = boundary_proofs.execute_desired_state(
            execution_manifest,
            consumer_rows=authority["census"]["consumer_rows"],
            python=boundary_proofs.PINNED_PYTHON,
            workspace=proof_workspace,
            expected_tree=candidate_tree,
            expected_runner_sha256=authority["runner_sha256"],
            pytest_carrier=boundary_proofs.PINNED_PYTEST_CARRIER,
            expected_pytest_carrier_sha256=(
                boundary_proofs.PINNED_PYTEST_CARRIER_SHA256
            ),
            forbidden_roots=(),
        )
    except (
        boundary_proofs.BoundaryProofError,
        reference_calibration.CalibrationError,
    ) as exc:
        failed_evidence = {
            "authority_bindings": deepcopy(authority["bindings"]),
            "candidate_tree": candidate_tree,
            "classification": classification,
            "discovery_candidate_set_sha256": fresh_discovery[
                "candidate_set_sha256"
            ],
            "discovery_projection": deepcopy(fresh_discovery["projection"]),
            "proof_error_code": exc.code,
            "proof_error_detail_sha256": "sha256:"
            + hashlib.sha256(str(exc.detail).encode("utf-8")).hexdigest(),
            "runner_sha256": authority["runner_sha256"],
            "schema_version": "es-f1-authenticated-task0-bypass.v1",
        }
        return {
            "satisfied": False,
            "evidence": _digest(failed_evidence),
            "proof_error_code": exc.code,
        }

    result_rows = deepcopy(list(desired_rows))
    if any(row.get("target_tree") != candidate_tree for row in result_rows):
        raise EvaluatorError("legacy bypass runner result tree binding drifted")
    report = {
        "bindings": deepcopy(authority["bindings"]),
        "legacy_inventory_partition": deepcopy(authority["partition"]),
        "novel_matches": deepcopy(classification["novel_direct_matches"]),
        "schema_version": "es-f1-legacy-bypass-report.v1",
        "selected_required_results": result_rows,
    }
    derived = _derive_task0_bypass_observation(report)
    evidence = {
        "authority_bindings": deepcopy(authority["bindings"]),
        "candidate_tree": candidate_tree,
        "classification": classification,
        "desired_state_results": result_rows,
        "discovery_candidate_set_sha256": fresh_discovery[
            "candidate_set_sha256"
        ],
        "discovery_projection": deepcopy(fresh_discovery["projection"]),
        "runner_sha256": authority["runner_sha256"],
        "schema_version": "es-f1-authenticated-task0-bypass.v1",
    }
    return {
        "satisfied": (
            derived["satisfied"]
            and not classification["restored_required_consumer_ids"]
        ),
        "evidence": _digest(evidence),
        "proof_error_code": None,
    }


def _file_sha256(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EvaluatorError(f"bound evaluator asset is unreadable: {path}") from exc


def _validate_frozen_artifact_applicability(
    artifact_rows: Any,
) -> None:
    """Validate the exact evaluator-owned historical applicability partitions."""

    expected_fields = {
        "applicable_architecture_ids",
        "bytes",
        "cas_relative_path",
        "era_id",
        "kind",
        "load_contract",
        "rejected_architecture_ids",
        "sha256",
    }
    if not isinstance(artifact_rows, list) or [
        row.get("era_id") if isinstance(row, Mapping) else None
        for row in artifact_rows
    ] != list(ARTIFACT_ERA_IDS):
        raise EvaluatorError("artifact applicability era set/order drifted")
    for row in artifact_rows:
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            raise EvaluatorError("artifact applicability row is not exact")
        expected_applicable = [
            "ffno"
            if row["era_id"] in _F1_FFNO_HISTORICAL_ARTIFACT_ERAS
            else "cnn"
        ]
        expected_rejected = [
            architecture_id
            for architecture_id in F1_ARTIFACT_ARCHITECTURE_DOMAIN
            if architecture_id not in expected_applicable
        ]
        if (
            row["applicable_architecture_ids"] != expected_applicable
            or row["rejected_architecture_ids"] != expected_rejected
        ):
            raise EvaluatorError(
                f"artifact applicability partition drifted for {row['era_id']}"
            )


def _artifact_implementation_identities(
    fixture_manifest: Mapping[str, Any],
) -> dict[str, str]:
    """Return the evaluator-owned built-in identity authority for H04 loads."""

    rows = fixture_manifest.get("registry_baseline")
    if not isinstance(rows, list) or len(rows) != len(F1_BUILTIN_ARCHITECTURES):
        raise EvaluatorError("artifact implementation identity authority is malformed")
    identities: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise EvaluatorError(
                "artifact implementation identity authority is malformed"
            )
        architecture_id = row.get("architecture")
        implementation_identity = row.get("implementation_identity")
        if (
            not isinstance(architecture_id, str)
            or architecture_id not in F1_BUILTIN_ARCHITECTURES
            or architecture_id in identities
            or not isinstance(implementation_identity, str)
            or not implementation_identity
        ):
            raise EvaluatorError(
                "artifact implementation identity authority is malformed"
            )
        identities[architecture_id] = implementation_identity
    if tuple(identities) != F1_BUILTIN_ARCHITECTURES:
        raise EvaluatorError("artifact implementation identity authority drifted")
    return identities


def resolve_artifact_applicability(
    *,
    fixture_manifest: Mapping[str, Any],
    candidate_evidence_path: Path,
) -> list[dict[str, Any]]:
    """Resolve the reserved witness placeholder only from validated evidence."""

    if not isinstance(fixture_manifest, Mapping):
        raise EvaluatorError("artifact applicability fixture manifest is malformed")
    artifact_rows = fixture_manifest.get("artifact_eras")
    _validate_frozen_artifact_applicability(artifact_rows)
    try:
        candidate_evidence = load_candidate_extension_evidence(
            candidate_evidence_path
        )
    except (OSError, TaskPackageError) as exc:
        detail = exc.detail if isinstance(exc, TaskPackageError) else str(exc)
        raise EvaluatorError(
            f"artifact applicability candidate evidence is invalid: {detail}"
        ) from exc
    witness_id = candidate_evidence["candidate_witness"]["public_id"]
    if (
        not isinstance(witness_id, str)
        or not witness_id
        or witness_id in set(F1_BUILTIN_ARCHITECTURES)
        or witness_id == F1_CANDIDATE_WITNESS_PLACEHOLDER
    ):
        raise EvaluatorError("artifact applicability candidate witness is invalid")
    assert isinstance(artifact_rows, list)
    return _resolve_artifact_witness_placeholder(
        artifact_rows=artifact_rows,
        witness_id=witness_id,
    )


def _resolve_artifact_witness_placeholder(
    *,
    artifact_rows: list[Mapping[str, Any]],
    witness_id: str,
) -> list[dict[str, Any]]:
    if (
        not isinstance(witness_id, str)
        or not witness_id
        or witness_id in set(F1_BUILTIN_ARCHITECTURES)
        or witness_id == F1_CANDIDATE_WITNESS_PLACEHOLDER
    ):
        raise EvaluatorError("artifact applicability candidate witness is invalid")
    resolved_rows = deepcopy(artifact_rows)
    for row in resolved_rows:
        for field_name in (
            "applicable_architecture_ids",
            "rejected_architecture_ids",
        ):
            row[field_name] = [
                witness_id
                if architecture_id == F1_CANDIDATE_WITNESS_PLACEHOLDER
                else architecture_id
                for architecture_id in row[field_name]
            ]
    return resolved_rows


def preflight_artifact_architecture(
    *,
    artifact_row: Mapping[str, Any],
    architecture_id: str,
) -> dict[str, Any] | None:
    """Reject an out-of-partition artifact before construction or load."""

    if not isinstance(artifact_row, Mapping) or not isinstance(
        architecture_id, str
    ):
        raise EvaluatorError("artifact architecture preflight input is malformed")
    applicable = artifact_row.get("applicable_architecture_ids")
    rejected = artifact_row.get("rejected_architecture_ids")
    if (
        not isinstance(applicable, list)
        or not isinstance(rejected, list)
        or architecture_id not in {*applicable, *rejected}
        or (architecture_id in applicable) == (architecture_id in rejected)
    ):
        raise EvaluatorError("artifact architecture preflight partition is malformed")
    if architecture_id in applicable:
        return None
    return {
        "diagnostic": "UNSUPPORTED_ARTIFACT_ARCHITECTURE",
        "implementation_identity": None,
        "module_returned": False,
        "strict_load": False,
    }


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

    try:
        fixtures = load_controller_asset(
            fixture_manifest_path,
            expected_schema_version="es-f1-fixture-manifest.v2",
        )
    except ValueError as exc:
        raise EvaluatorError(f"fixture manifest preflight failed: {exc}") from exc
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
    _validate_frozen_artifact_applicability(fixtures.get("artifact_eras"))
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
        calibration_binding["schema_version"] != "es-f1-calibration-cases.v3"
        or _file_sha256(calibration_path) != calibration_binding["sha256"]
    ):
        raise EvaluatorError("calibration fixture digest/schema binding drifted")
    try:
        calibration = load_controller_asset(
            calibration_path,
            expected_schema_version="es-f1-calibration-cases.v3",
        )
        calibration_cases = calibration["cases"]
        if not isinstance(calibration_cases, list) or [
            (
                row.get("case_id") if isinstance(row, Mapping) else None,
                row.get("defect_kind") if isinstance(row, Mapping) else None,
            )
            for row in calibration_cases
        ] != list(CALIBRATION_CASE_SEQUENCE):
            raise ValueError("calibration case identity/order drifted")
        for case in calibration_cases:
            validate_calibration_case(case)
    except (OSError, TypeError, ValueError) as exc:
        raise EvaluatorError(f"calibration fixture is malformed: {exc}") from exc
    return {
        "calibration_cases": calibration,
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
        "schema_version": "es-f1-visible-check-result.v2",
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
    try:
        resolved = (root / path).resolve(strict=True)
    except OSError as exc:
        raise EvaluatorError(f"missing lifecycle artifact: {label}") from exc
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
    structural_fields: Sequence[Mapping[str, Any]],
    image_size: int,
    seed: int,
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
            "ES_F1_STRUCTURAL_FIELDS": json.dumps(
                list(structural_fields), separators=(",", ":")
            ),
            "ES_F1_IMAGE_SIZE": str(image_size),
            "ES_F1_SEED": str(seed),
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
    structural_fields: Mapping[str, Sequence[Mapping[str, Any]]],
    image_sizes: Mapping[str, int],
    seed: int,
    output_root: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    for architecture_id, architecture_artifacts in artifacts.items():
        architecture_observations: dict[str, Any] = {}
        for kind, mode in (("checkpoint", "checkpoint"), ("bundle", "bundle")):
            artifact = architecture_artifacts[kind]
            report = output_root / f"{architecture_id}-{kind}-fresh-load.json"
            try:
                loaded = _fresh_artifact_semantic_probe(
                    workspace=workspace,
                    python_executable=python_executable,
                    artifact=artifact,
                    mode=mode,
                    report=report,
                    structural_fields=structural_fields[architecture_id],
                    image_size=image_sizes[architecture_id],
                    seed=seed,
                    timeout_seconds=timeout_seconds,
                    expect_success=True,
                )
            except EvaluatorError as exc:
                raise EvaluatorObservationError(
                    clause_id="F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
                    mechanism="fresh-artifact-reload",
                    evidence={
                        "artifact_kind": kind,
                        "architecture_id": architecture_id,
                        "error_type": type(exc).__name__,
                        "error_detail_sha256": "sha256:"
                        + hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
                    },
                    detail="a full-matrix lifecycle artifact failed fresh-process reload",
                ) from exc
            if kind == "bundle":
                tampered = (
                    output_root
                    / f"{architecture_id}-{kind}-tampered"
                    / "wts.h5.zip"
                )
                tampered.parent.mkdir()
            else:
                tampered = (
                    output_root
                    / f"{architecture_id}-{kind}-tampered{artifact.suffix}"
                )
            payload = artifact.read_bytes()
            tampered.write_bytes(payload[: max(1, len(payload) // 2)])
            _fresh_artifact_semantic_probe(
                workspace=workspace,
                python_executable=python_executable,
                artifact=tampered,
                mode=mode,
                report=(
                    output_root
                    / f"{architecture_id}-{kind}-tampered-report.json"
                ),
                structural_fields=structural_fields[architecture_id],
                image_size=image_sizes[architecture_id],
                seed=seed,
                timeout_seconds=timeout_seconds,
                expect_success=False,
            )
            architecture_observations[kind] = loaded
        observations[architecture_id] = architecture_observations
    return observations


def _run_semantic_lifecycle_probe(
    *,
    workspace: Path,
    python_executable: Path,
    candidate_evidence: Path,
    request_path: Path,
    architecture_cases: Sequence[Mapping[str, Any]],
    adapter_observations: Mapping[str, Any],
    output_root: Path,
    seed: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    semantic_root = output_root / "evaluator-semantic-lifecycle"
    semantic_root.mkdir(parents=True, exist_ok=False)
    report_path = semantic_root / "report.json"
    child_pairs = tuple(
        (
            f"{ordinal:02d}-{case['architecture_id']}-{kind}-reload-program.py",
            f"{ordinal:02d}-{case['architecture_id']}-{kind}-reload-audit.json",
        )
        for ordinal, case in enumerate(architecture_cases, start=1)
        for kind in ("checkpoint", "bundle")
    )
    child_environments: dict[tuple[str, str], dict[str, str]] = {}
    for ordinal, case in enumerate(architecture_cases, start=1):
        architecture_id = case["architecture_id"]
        for kind in ("checkpoint", "bundle"):
            name = f"{ordinal:02d}-{architecture_id}-{kind}-reload"
            pair = (f"{name}-program.py", f"{name}-audit.json")
            artifact = semantic_root / f"{ordinal:02d}-{architecture_id}" / (
                "evaluator.ckpt" if kind == "checkpoint" else "configuration"
            )
            child_environments[pair] = {
                "ES_F1_CHILD_REPORT": str(semantic_root / f"{name}.json"),
                "ES_F1_RELOAD_MODE": kind,
                "ES_F1_RELOAD_ARTIFACT": str(artifact),
                "ES_F1_STRUCTURAL_FIELDS": json.dumps(
                    case["structural_fields"],
                    separators=(",", ":"),
                ),
                "ES_F1_IMAGE_SIZE": str(case["N"]),
                "ES_F1_SEED": str(seed),
                "ES_F1_FRESH_RELOAD": "1",
            }
    _run_projection_probe(
        workspace=workspace,
        controlled_child_root=semantic_root,
        controlled_child_pairs=child_pairs,
        controlled_child_environment_updates=child_environments,
        python_executable=python_executable,
        code=_FULL_MATRIX_SEMANTIC_LIFECYCLE_PROBE,
        environment={
            "ES_F1_CANDIDATE_EVIDENCE": str(candidate_evidence),
            "ES_F1_CHILD_CODE": _FRESH_RELOAD_PROBE,
            "ES_F1_OUTPUT": str(semantic_root),
            "ES_F1_REPORT": str(report_path),
            "ES_F1_REQUEST": str(request_path),
            "ES_F1_SEED": str(seed),
            "ES_F1_OPTIMIZER_STEP_BOUND": str(
                F1_MAX_OPTIMIZER_STEP_ABS_DELTA
            ),
            "ES_F1_WORKSPACE": str(workspace),
        },
        timeout_seconds=timeout_seconds,
        label="semantic lifecycle",
    )
    if not report_path.is_file():
        raise EvaluatorError("semantic lifecycle produced no report")
    report = _load_canonical_unversioned(report_path)
    semantic_version = report.get("schema_version")
    semantic_record_type = (
        "semantic-lifecycle-failure"
        if isinstance(semantic_version, str)
        and semantic_version.startswith("es-f1-semantic-lifecycle-failure.")
        else "semantic-lifecycle"
    )
    require_evaluator_successor_schema(
        report,
        record_type=semantic_record_type,
    )
    if semantic_record_type == "semantic-lifecycle-failure":
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
        "architecture_results",
        "unknown_architecture_rejection",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    }:
        raise EvaluatorError("semantic lifecycle report is not exact")
    observed_rows = report.get("architecture_results")
    if not isinstance(observed_rows, list) or len(observed_rows) != 15:
        raise EvaluatorError("semantic lifecycle architecture matrix is incomplete")
    for case, observed in zip(architecture_cases, observed_rows, strict=True):
        architecture_id = case["architecture_id"]
        if (
            not isinstance(observed, dict)
            or observed.get("architecture_id") != architecture_id
        ):
            raise EvaluatorError("semantic lifecycle architecture join is malformed")
        checkpoint = adapter_observations[architecture_id]["checkpoint"]
        bundle = adapter_observations[architecture_id]["bundle"]
        observed["adapter_checkpoint_reload"] = checkpoint
        observed["adapter_bundle_reload"] = bundle
    return report



def derive_lifecycle_observations(
    *,
    semantic_report: Mapping[str, Any],
    adapter_process_id: int,
) -> list[dict[str, Any]]:
    """Derive H05--H10 from one exact ordered full-matrix semantic record."""

    top_level_keys = {
        "schema_version",
        "construction_pid",
        "architecture_results",
        "unknown_architecture_rejection",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    }
    require_evaluator_successor_schema(
        semantic_report,
        record_type="semantic-lifecycle",
    )
    if (
        not isinstance(semantic_report, Mapping)
        or set(semantic_report) != top_level_keys
        or type(adapter_process_id) is not int
        or adapter_process_id <= 0
    ):
        raise EvaluatorError("semantic lifecycle full-matrix report is not exact")
    construction_pid = semantic_report["construction_pid"]
    if type(construction_pid) is not int or construction_pid <= 0:
        raise EvaluatorError("semantic lifecycle construction process is malformed")
    rows = semantic_report["architecture_results"]
    if not isinstance(rows, list) or len(rows) != 15:
        raise EvaluatorError("semantic lifecycle architecture matrix is incomplete")
    architecture_ids = tuple(
        row.get("architecture_id") if isinstance(row, Mapping) else None
        for row in rows
    )
    if (
        architecture_ids[:14] != F1_BUILTIN_ARCHITECTURES
        or not isinstance(architecture_ids[-1], str)
        or not architecture_ids[-1]
        or architecture_ids[-1] in set(F1_BUILTIN_ARCHITECTURES)
        or len(set(architecture_ids)) != 15
    ):
        raise EvaluatorError("semantic lifecycle architecture matrix is not exact")

    row_keys = {
        "N",
        "architecture_id",
        "boundary_contract",
        "boundary_input_digest_after",
        "boundary_input_digest_before",
        "bundle_implementation",
        "completed_stages",
        "config_digest",
        "construction_route",
        "registry_constructor_identity",
        "evaluator_bundle_reload",
        "evaluator_checkpoint_reload",
        "adapter_bundle_reload",
        "adapter_checkpoint_reload",
        "forward_deterministic",
        "forward_dtype",
        "forward_finite",
        "forward_max_abs_delta",
        "forward_shape",
        "forward_tolerance",
        "gradients_finite",
        "identity_rejections",
        "identity_sensitivity",
        "inference_digest",
        "input_digest",
        "loss_finite",
        "loss_scalar",
        "optimizer_state_after",
        "optimizer_state_before",
        "optimizer_step_bound",
        "optimizer_step_max_abs_delta",
        "optimizer_transition_bounded",
        "persisted_boundary_owners",
        "persisted_implementation",
        "persisted_rebuild_implementation",
        "persisted_rebuild_route",
        "persisted_state_signature",
        "public_boundary_owners",
        "public_implementation",
        "public_state_signature",
        "seed",
        "structural_fields",
        "structural_values",
    }
    reload_keys = {
        "artifact_bytes",
        "artifact_sha256",
        "architecture_id",
        "boundary_contract",
        "boundary_input_digest_after",
        "boundary_input_digest_before",
        "boundary_owners",
        "fresh_pid",
        "implementation_identity",
        "inference_deterministic",
        "inference_dtype",
        "inference_finite",
        "inference_max_abs_delta",
        "inference_shape",
        "inference_tolerance",
        "loaded_forbidden_modules",
        "observable_digest",
        "outside_project_origin_rows",
        "roles",
        "state_signature",
        "structural_values",
    }
    sensitivity_keys = {
        "alternate_identity_digest",
        "alternate_observable_digest",
        "alternate_state_signature",
        "baseline_identity_digest",
        "baseline_observable_digest",
        "baseline_state_signature",
        "deterministic",
    }

    def is_digest(value: Any) -> bool:
        return (
            isinstance(value, str)
            and value.startswith("sha256:")
            and len(value) == 71
            and all(character in "0123456789abcdef" for character in value[7:])
        )

    def valid_rejection_record(value: Any) -> bool:
        if (
            not isinstance(value, Mapping)
            or set(value)
            != {
                "exception_detail_sha256",
                "exception_type",
                "module_returned",
                "rejected",
            }
            or not is_digest(value.get("exception_detail_sha256"))
        ):
            return False
        if value.get("rejected") is True:
            return (
                value.get("module_returned") is False
                and isinstance(value.get("exception_type"), str)
                and bool(value["exception_type"])
            )
        return (
            value.get("rejected") is False
            and value.get("module_returned") is True
            and value.get("exception_type") is None
        )

    def rejection_succeeded(value: Mapping[str, Any]) -> bool:
        return value["rejected"] is True

    unknown_rejection = semantic_report["unknown_architecture_rejection"]
    if not valid_rejection_record(unknown_rejection):
        raise EvaluatorError("semantic lifecycle unknown-architecture rejection is malformed")
    for field_name in (
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    ):
        if not isinstance(semantic_report[field_name], list):
            raise EvaluatorError("semantic lifecycle ownership evidence is malformed")

    lifecycle_ok = True
    structural_ok = True
    rejection_ok = True
    sensitivity_ok = True
    construction_ok = True
    ownership_ok = (
        semantic_report["loaded_forbidden_modules"] == []
        and semantic_report["outside_project_origin_rows"] == []
        and semantic_report["cache_artifacts"] == []
    )
    fresh_pids: set[int] = set()
    builtin_implementations: set[str] = set()
    builtin_registry_constructors: set[str] = set()
    builtin_field_names: set[str] = set()
    witness_implementation: str | None = None
    witness_registry_constructor: str | None = None

    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping) or set(row) != row_keys:
            raise EvaluatorError("semantic lifecycle architecture record is not exact")
        architecture_id = str(row["architecture_id"])
        N = row["N"]
        expected_N = 128 if architecture_id == "neuralop_uno" else 64
        if type(N) is not int or N not in {64, 128} or N != expected_N:
            raise EvaluatorError("semantic lifecycle architecture image size is invalid")
        structural_fields = row["structural_fields"]
        if not isinstance(structural_fields, list) or not structural_fields:
            raise EvaluatorError("semantic lifecycle structural field set is malformed")
        field_names: list[str] = []
        baseline_values: dict[str, Any] = {}
        for field in structural_fields:
            if (
                not isinstance(field, Mapping)
                or set(field) != {"name", "baseline_value", "alternate_value"}
                or not isinstance(field.get("name"), str)
                or not field["name"]
                or field["baseline_value"] == field["alternate_value"]
            ):
                raise EvaluatorError("semantic lifecycle structural field is malformed")
            field_names.append(field["name"])
            baseline_values[field["name"]] = field["baseline_value"]
        if len(field_names) != len(set(field_names)):
            raise EvaluatorError("semantic lifecycle structural fields are duplicated")
        if ordinal < 14:
            builtin_field_names.update(field_names)
        if row["structural_values"] != baseline_values:
            structural_ok = False

        lifecycle_ok = lifecycle_ok and (
            row["completed_stages"] == list(F1_LIFECYCLE_STAGES)
            and is_digest(row["config_digest"])
            and is_digest(row["input_digest"])
            and type(row["seed"]) is int
            and 0 <= row["seed"] <= 2_147_483_647
            and row["forward_shape"] == [1, 1, N, N]
            and row["forward_dtype"] == "complex64"
            and row["forward_finite"] is True
            and row["forward_deterministic"] is True
            and isinstance(row["forward_max_abs_delta"], (int, float))
            and not isinstance(row["forward_max_abs_delta"], bool)
            and math.isfinite(row["forward_max_abs_delta"])
            and isinstance(row["forward_tolerance"], (int, float))
            and not isinstance(row["forward_tolerance"], bool)
            and math.isfinite(row["forward_tolerance"])
            and row["forward_tolerance"] >= 0
            and 0 <= row["forward_max_abs_delta"] <= row["forward_tolerance"]
            and row["loss_finite"] is True
            and row["loss_scalar"] is True
            and row["gradients_finite"] is True
            and is_digest(row["inference_digest"])
            and is_digest(row["optimizer_state_before"])
            and is_digest(row["optimizer_state_after"])
            and row["optimizer_state_before"] != row["optimizer_state_after"]
            and isinstance(row["optimizer_step_max_abs_delta"], (int, float))
            and not isinstance(row["optimizer_step_max_abs_delta"], bool)
            and math.isfinite(row["optimizer_step_max_abs_delta"])
            and isinstance(row["optimizer_step_bound"], (int, float))
            and not isinstance(row["optimizer_step_bound"], bool)
            and math.isfinite(row["optimizer_step_bound"])
            and row["optimizer_step_bound"]
            == F1_MAX_OPTIMIZER_STEP_ABS_DELTA
            and 0 < row["optimizer_step_max_abs_delta"]
            <= row["optimizer_step_bound"]
            and row["optimizer_transition_bounded"] is True
        )
        ownership_ok = ownership_ok and (
            row["boundary_contract"] == _PUBLIC_SCIENTIFIC_BOUNDARY_CONTRACT
            and row["public_boundary_owners"] == _PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS
            and row["persisted_boundary_owners"] == _PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS
            and is_digest(row["boundary_input_digest_before"])
            and row["boundary_input_digest_after"]
            == row["boundary_input_digest_before"]
        )
        implementation_values = {
            row["public_implementation"],
            row["persisted_implementation"],
            row["persisted_rebuild_implementation"],
            row["bundle_implementation"],
        }
        expected_implementation = row["public_implementation"]
        construction_ok = construction_ok and (
            len(implementation_values) == 1
            and row["construction_route"] == F1_PUBLIC_CONSTRUCTION_ROUTE
            and row["persisted_rebuild_route"]
            == F1_PUBLIC_PERSISTED_REBUILD_ROUTE
            and all(
                isinstance(row[name], str) and bool(row[name])
                for name in (
                    "construction_route",
                    "registry_constructor_identity",
                    "persisted_rebuild_route",
                    "public_implementation",
                    "persisted_implementation",
                    "persisted_rebuild_implementation",
                    "bundle_implementation",
                )
            )
            and is_digest(row["public_state_signature"])
            and row["persisted_state_signature"] == row["public_state_signature"]
        )
        if ordinal < 14:
            builtin_implementations.add(str(expected_implementation))
            builtin_registry_constructors.add(
                str(row["registry_constructor_identity"])
            )
        else:
            witness_implementation = str(expected_implementation)
            witness_registry_constructor = str(
                row["registry_constructor_identity"]
            )

        rejections = row["identity_rejections"]
        if not isinstance(rejections, Mapping) or set(rejections) != {
            "missing",
            "extra",
            "unsupported_value",
        }:
            raise EvaluatorError("semantic lifecycle identity rejection set is malformed")
        missing = rejections["missing"]
        rejection_records = (
            *missing.values(),
            rejections["extra"],
            rejections["unsupported_value"],
        ) if isinstance(missing, Mapping) else ()
        if not rejection_records or not all(
            valid_rejection_record(value) for value in rejection_records
        ):
            raise EvaluatorError(
                "semantic lifecycle identity rejection record is malformed"
            )
        rejection_ok = rejection_ok and (
            isinstance(missing, Mapping)
            and set(missing) == set(field_names)
            and all(rejection_succeeded(value) for value in missing.values())
            and rejection_succeeded(rejections["extra"])
            and rejection_succeeded(rejections["unsupported_value"])
        )
        sensitivity = row["identity_sensitivity"]
        if not isinstance(sensitivity, Mapping) or set(sensitivity) != set(field_names):
            raise EvaluatorError("semantic lifecycle identity sensitivity set is malformed")
        for field_name, value in sensitivity.items():
            if not isinstance(value, Mapping) or set(value) != sensitivity_keys:
                raise EvaluatorError("semantic lifecycle identity sensitivity is malformed")
            base_sensitivity = (
                value["deterministic"] is True
                and all(is_digest(value[name]) for name in sensitivity_keys - {"deterministic"})
                and value["baseline_identity_digest"]
                != value["alternate_identity_digest"]
            )
            witness_semantics = True
            if ordinal == 14 and field_name not in builtin_field_names:
                witness_semantics = (
                    value["baseline_state_signature"]
                    != value["alternate_state_signature"]
                    and value["baseline_observable_digest"]
                    != value["alternate_observable_digest"]
                )
            sensitivity_ok = sensitivity_ok and base_sensitivity and witness_semantics

        for reload_name, expected_roles in (
            ("evaluator_checkpoint_reload", []),
            ("evaluator_bundle_reload", ["autoencoder", "diffraction_to_obj"]),
            ("adapter_checkpoint_reload", []),
            ("adapter_bundle_reload", ["autoencoder", "diffraction_to_obj"]),
        ):
            reload = row[reload_name]
            if not isinstance(reload, Mapping) or set(reload) != reload_keys:
                raise EvaluatorError("semantic lifecycle reload record is not exact")
            fresh_pid = reload["fresh_pid"]
            fresh = (
                type(fresh_pid) is int
                and fresh_pid > 0
                and fresh_pid not in {construction_pid, adapter_process_id}
                and fresh_pid not in fresh_pids
            )
            if type(fresh_pid) is int:
                fresh_pids.add(fresh_pid)
            lifecycle_ok = lifecycle_ok and (
                fresh
                and type(reload["artifact_bytes"]) is int
                and reload["artifact_bytes"] > 0
                and is_digest(reload["artifact_sha256"])
                and reload["architecture_id"] == architecture_id
                and reload["inference_shape"] == [1, 1, N, N]
                and reload["inference_dtype"] == row["forward_dtype"]
                and reload["inference_finite"] is True
                and reload["inference_deterministic"] is True
                and isinstance(reload["inference_max_abs_delta"], (int, float))
                and not isinstance(reload["inference_max_abs_delta"], bool)
                and math.isfinite(reload["inference_max_abs_delta"])
                and isinstance(reload["inference_tolerance"], (int, float))
                and not isinstance(reload["inference_tolerance"], bool)
                and math.isfinite(reload["inference_tolerance"])
                and reload["inference_tolerance"] >= 0
                and 0
                <= reload["inference_max_abs_delta"]
                <= reload["inference_tolerance"]
                and reload["roles"] == expected_roles
                and is_digest(reload["observable_digest"])
                and is_digest(reload["state_signature"])
            )
            structural_ok = structural_ok and reload["structural_values"] == baseline_values
            construction_ok = construction_ok and (
                reload["implementation_identity"] == expected_implementation
            )
            ownership_ok = ownership_ok and (
                reload["boundary_contract"] == _PUBLIC_SCIENTIFIC_BOUNDARY_CONTRACT
                and reload["boundary_owners"] == _PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS
                and reload["boundary_input_digest_after"]
                == reload["boundary_input_digest_before"]
                and is_digest(reload["boundary_input_digest_before"])
                and reload["loaded_forbidden_modules"] == []
                and reload["outside_project_origin_rows"] == []
            )

    rejection_ok = rejection_ok and rejection_succeeded(unknown_rejection)
    construction_ok = construction_ok and (
        witness_implementation is not None
        and witness_implementation not in builtin_implementations
        and witness_registry_constructor is not None
        and witness_registry_constructor not in builtin_registry_constructors
    )
    facts = {
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE": lifecycle_ok,
        "F1-H06-STRUCTURAL-ROUNDTRIP": structural_ok,
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
            "details": "evaluator-owned full-matrix public lifecycle verification",
        }
        for clause_id in HARD_CLAUSE_IDS[4:]
    ]


def _preflight_registry_constructor_identities(
    *,
    workspace: Path,
    python_executable: Path,
    architecture_ids: Sequence[str],
    output_root: Path,
    timeout_seconds: int,
) -> dict[str, str]:
    """Resolve all nominated registry constructors before candidate execution."""

    if (
        len(architecture_ids) != len(F1_BUILTIN_ARCHITECTURES) + 1
        or not isinstance(architecture_ids[-1], str)
        or not architecture_ids[-1]
        or architecture_ids[-1] in set(F1_BUILTIN_ARCHITECTURES)
        or list(architecture_ids[:-1]) != list(F1_BUILTIN_ARCHITECTURES)
    ):
        raise EvaluatorError("registry constructor preflight domain is malformed")
    output_root.mkdir(parents=True, exist_ok=False)
    report_path = output_root / "registry-constructors.json"
    _run_projection_probe(
        workspace=workspace,
        python_executable=python_executable,
        code=_REGISTRY_CONSTRUCTOR_IDENTITY_PROBE,
        environment={
            "ES_F1_ARCHITECTURES": json.dumps(
                list(architecture_ids), separators=(",", ":")
            ),
            "ES_F1_REPORT": str(report_path),
            "ES_F1_WORKSPACE": str(workspace),
        },
        timeout_seconds=timeout_seconds,
        label="registry constructor identity preflight",
    )
    if not report_path.is_file():
        raise EvaluatorError("registry constructor preflight produced no report")
    report = _load_canonical_unversioned(report_path)
    rows = report.get("registry_constructor_identities")
    if (
        set(report) != {"registry_constructor_identities"}
        or not isinstance(rows, list)
        or len(rows) != len(architecture_ids)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"architecture_id", "identity"}
            or row.get("architecture_id") != architecture_id
            or not isinstance(row.get("identity"), str)
            or not row["identity"]
            for row, architecture_id in zip(rows, architecture_ids, strict=True)
        )
    ):
        raise EvaluatorError("registry constructor preflight report is not exact")
    identities = {row["architecture_id"]: row["identity"] for row in rows}
    witness_id = architecture_ids[-1]
    if identities[witness_id] in {
        identities[architecture_id]
        for architecture_id in F1_BUILTIN_ARCHITECTURES
    }:
        raise EvaluatorObservationError(
            clause_id="F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
            mechanism="registry-constructor-identity-alias",
            evidence={"registry_constructor_identities": identities},
            detail=(
                "the nominated witness resolves to a frozen built-in registry "
                "constructor"
            ),
        )
    return identities


def _bind_registry_constructor_identities(
    *,
    preflight_identities: Mapping[str, str],
    semantic_report: Mapping[str, Any],
) -> None:
    """Reject registry behavior that changes between preflight and lifecycle."""

    rows = semantic_report.get("architecture_results")
    if not isinstance(rows, list):
        raise EvaluatorError("registry constructor semantic binding is malformed")
    semantic_identities: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise EvaluatorError("registry constructor semantic binding is malformed")
        architecture_id = row.get("architecture_id")
        identity = row.get("registry_constructor_identity")
        if (
            not isinstance(architecture_id, str)
            or architecture_id in semantic_identities
            or not isinstance(identity, str)
            or not identity
        ):
            raise EvaluatorError("registry constructor semantic binding is malformed")
        semantic_identities[architecture_id] = identity
    if (
        not isinstance(preflight_identities, Mapping)
        or list(preflight_identities) != list(semantic_identities)
        or any(
            not isinstance(identity, str) or not identity
            for identity in preflight_identities.values()
        )
    ):
        raise EvaluatorError("registry constructor preflight binding is malformed")
    if dict(preflight_identities) != semantic_identities:
        raise EvaluatorObservationError(
            clause_id="F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
            mechanism="registry-constructor-phase-drift",
            evidence={
                "preflight_identities": dict(preflight_identities),
                "semantic_identities": semantic_identities,
            },
            detail=(
                "registry constructor identities changed between evaluator "
                "preflight and lifecycle construction"
            ),
        )


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
    with tempfile.TemporaryDirectory(prefix="es-f1-package-preflight-") as raw_preflight:
        preflight = Path(raw_preflight)
        preflight_evidence = preflight / "es_f1_candidate_evidence.json"
        preflight_request = preflight / "request.json"
        preflight_evidence.write_bytes(candidate_evidence_bytes)
        preflight_request.write_bytes(canonical_json_bytes(request_record))
        try:
            loaded_evidence = load_candidate_extension_evidence(preflight_evidence)
            loaded_request = load_lifecycle_probe_request(preflight_request)
        except TaskPackageError as exc:
            diagnostic = exc.code.replace("_", " ")
            raise EvaluatorError(
                f"lifecycle package preflight {diagnostic}: {exc.detail}"
            ) from exc
    if loaded_evidence != candidate_evidence_record or loaded_request != request_record:
        raise EvaluatorError("lifecycle package canonical loader disagreement")
    architecture_rows = [
        *candidate_evidence_record["builtin_architectures"],
        candidate_evidence_record["candidate_witness"],
    ]
    if any(
        case["N"]
        != (128 if case["architecture_id"] == "neuralop_uno" else 64)
        for case in request_record["architecture_cases"]
    ):
        raise EvaluatorError("lifecycle architecture image size is invalid")
    try:
        expected_cases, input_payloads = build_lifecycle_probe_inputs(
            architecture_rows=architecture_rows,
            seed=request_record["seed"],
        )
    except ValueError as exc:
        raise EvaluatorError(f"lifecycle evaluator authority rejected input: {exc}") from exc
    if request_record["architecture_cases"] != expected_cases:
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
        for relative_path, payload in input_payloads.items():
            input_path = temp / relative_path
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
        registry_constructor_identities = _preflight_registry_constructor_identities(
            workspace=workspace,
            python_executable=python_executable,
            architecture_ids=[row["public_id"] for row in architecture_rows],
            output_root=temp / "registry-constructor-preflight",
            timeout_seconds=timeout_seconds,
        )
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
        expected_architecture_ids = tuple(
            row["architecture_id"] for row in request_record["architecture_cases"]
        )
        try:
            loaded_result = load_lifecycle_probe_result(
                result_path,
                expected_architecture_ids=expected_architecture_ids,
                expected_candidate_id=request_record["candidate_id"],
            )
        except TaskPackageError as exc:
            diagnostic = exc.code.replace("_", " ")
            raise EvaluatorError(
                f"lifecycle result preflight {diagnostic}: {exc.detail}"
            ) from exc
        if loaded_result != adapter_result:
            raise EvaluatorError("lifecycle result canonical loader disagreement")
        if adapter_result["operation_version"] != request_record["operation_version"]:
            raise EvaluatorError("lifecycle result operation version drifted")
        artifacts: dict[str, dict[str, Path]] = {}
        structural_fields: dict[str, list[Mapping[str, Any]]] = {}
        image_sizes: dict[str, int] = {}
        for case, artifact_record in zip(
            request_record["architecture_cases"],
            adapter_result["architecture_results"],
            strict=True,
        ):
            architecture_id = case["architecture_id"]
            structural_fields[architecture_id] = deepcopy(case["structural_fields"])
            image_sizes[architecture_id] = case["N"]
            artifacts[architecture_id] = {
                "checkpoint": _safe_external_result_path(
                    temp,
                    artifact_record["checkpoint_path"],
                    label=f"lifecycle {architecture_id} checkpoint",
                ),
                "bundle": _safe_external_result_path(
                    temp,
                    artifact_record["bundle_path"],
                    label=f"lifecycle {architecture_id} bundle",
                ),
            }
        semantic_observations = _verify_adapter_artifacts(
            workspace=workspace,
            python_executable=python_executable,
            artifacts=artifacts,
            structural_fields=structural_fields,
            image_sizes=image_sizes,
            seed=request_record["seed"],
            output_root=temp,
            timeout_seconds=timeout_seconds,
        )
        semantic_report = _run_semantic_lifecycle_probe(
            workspace=workspace,
            python_executable=python_executable,
            candidate_evidence=candidate_evidence,
            request_path=request_path,
            architecture_cases=request_record["architecture_cases"],
            adapter_observations=semantic_observations,
            output_root=temp,
            seed=request_record["seed"],
            timeout_seconds=timeout_seconds,
        )
        _bind_registry_constructor_identities(
            preflight_identities=registry_constructor_identities,
            semantic_report=semantic_report,
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
    candidate_workspace: Path,
    task0_proof_workspace: Path,
    candidate_tree: str,
    legacy_bypass_discovery_input: Mapping[str, Any],
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
    require_evaluator_successor_schema(
        visible_check_result,
        record_type="visible-check-result",
    )
    if not isinstance(visible_check_result, Mapping) or set(visible_check_result) != {
        "schema_version",
        "copy_digest_after",
        "copy_digest_before",
        "invocations",
    }:
        raise EvaluatorError("complete observation visible result is not exact")
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
    candidate_architecture_rows = [
        *candidate_record["builtin_architectures"],
        candidate_record["candidate_witness"],
    ]
    candidate_architecture_ids = [
        row["public_id"] for row in candidate_architecture_rows
    ]
    request_architecture_ids = [
        row["architecture_id"] for row in request_record["architecture_cases"]
    ]
    adapter_architecture_ids = [
        row["architecture_id"] for row in adapter_result["architecture_results"]
    ]
    if (
        request_record["candidate_evidence_sha256"] != candidate_digest
        or candidate_record["candidate_id"] != request_record["candidate_id"]
        or adapter_result["candidate_id"] != request_record["candidate_id"]
        or adapter_result["operation_version"] != request_record["operation_version"]
        or candidate_architecture_ids != request_architecture_ids
        or adapter_architecture_ids != request_architecture_ids
    ):
        raise EvaluatorError("complete observation schema bindings drifted")
    try:
        expected_architecture_cases, _ = build_lifecycle_probe_inputs(
            architecture_rows=candidate_architecture_rows,
            seed=request_record["seed"],
        )
    except ValueError as exc:
        raise EvaluatorError(
            f"complete observation lifecycle authority drifted: {exc}"
        ) from exc
    if request_record["architecture_cases"] != expected_architecture_cases:
        raise EvaluatorError("complete observation lifecycle input binding drifted")
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

    expected_fixture_fields = _TOP_LEVEL_FIELDS["es-f1-fixture-manifest.v2"]
    if (
        not isinstance(fixture_manifest, Mapping)
        or set(fixture_manifest) != expected_fixture_fields
        or fixture_manifest.get("schema_version") != "es-f1-fixture-manifest.v2"
        or fixture_manifest.get("hard_clause_ids") != list(HARD_CLAUSE_IDS)
    ):
        raise EvaluatorError("complete observation fixture manifest is not exact")
    expected_registry_rows = fixture_manifest.get("registry_baseline")
    if not isinstance(expected_registry_rows, list):
        raise EvaluatorError("complete observation frozen registry is malformed")
    artifact_implementation_identities = _artifact_implementation_identities(
        fixture_manifest
    )
    h03 = derive_registry_observation(
        expected_registry_baseline=expected_registry_rows,
        registry_report=registry_report,
    )

    require_evaluator_successor_schema(
        artifact_report,
        record_type="artifact-fixture-verification",
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
    frozen_artifact_rows = fixture_manifest.get("artifact_eras")
    _validate_frozen_artifact_applicability(frozen_artifact_rows)
    assert isinstance(frozen_artifact_rows, list)
    expected_artifact_rows = _resolve_artifact_witness_placeholder(
        artifact_rows=frozen_artifact_rows,
        witness_id=candidate_record["candidate_witness"]["public_id"],
    )
    expected_eras = [row["era_id"] for row in expected_artifact_rows]
    if (
        not isinstance(artifact_rows, list)
        or [row.get("era_id") if isinstance(row, Mapping) else None for row in artifact_rows]
        != expected_eras
        or artifact_report.get("loaded_forbidden_modules") != []
        or artifact_report.get("outside_project_origin_rows") != []
        or artifact_report.get("cache_artifacts") != []
    ):
        raise EvaluatorError("complete observation artifact-era verification drifted")
    outcome_fields = {
        "architecture_id",
        "diagnostic",
        "implementation_identity",
        "module_returned",
        "strict_load",
    }
    artifact_matrix_satisfied = True
    for expected_row, observed_row in zip(
        expected_artifact_rows,
        artifact_rows,
        strict=True,
    ):
        if (
            not isinstance(observed_row, Mapping)
            or set(observed_row) != {"era_id", "architecture_results"}
            or not isinstance(observed_row["architecture_results"], list)
            or [
                outcome.get("architecture_id")
                if isinstance(outcome, Mapping)
                else None
                for outcome in observed_row["architecture_results"]
            ]
            != candidate_architecture_ids
        ):
            raise EvaluatorError("complete observation artifact matrix is not exact")
        for outcome in observed_row["architecture_results"]:
            if (
                not isinstance(outcome, Mapping)
                or set(outcome) != outcome_fields
                or type(outcome["module_returned"]) is not bool
                or type(outcome["strict_load"]) is not bool
                or (
                    outcome["diagnostic"] is not None
                    and not isinstance(outcome["diagnostic"], str)
                )
                or (
                    outcome["implementation_identity"] is not None
                    and not isinstance(outcome["implementation_identity"], str)
                )
            ):
                raise EvaluatorError(
                    "complete observation artifact matrix outcome is malformed"
                )
            architecture_id = outcome["architecture_id"]
            if architecture_id in expected_row["applicable_architecture_ids"]:
                expected_outcome = (
                    outcome["diagnostic"] is None
                    and outcome["implementation_identity"]
                    == artifact_implementation_identities[architecture_id]
                    and outcome["module_returned"] is True
                    and outcome["strict_load"] is True
                )
            else:
                expected_outcome = (
                    outcome["diagnostic"]
                    == "UNSUPPORTED_ARTIFACT_ARCHITECTURE"
                    and outcome["implementation_identity"] is None
                    and outcome["module_returned"] is False
                    and outcome["strict_load"] is False
                )
            artifact_matrix_satisfied = (
                artifact_matrix_satisfied and expected_outcome
            )
    h04 = observation(
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
        satisfied=artifact_matrix_satisfied,
        evidence={
            "expected_artifact_eras": fixture_manifest["artifact_eras"],
            "expected_implementation_identities": (
                artifact_implementation_identities
            ),
            "artifact_report": artifact_report,
        },
        details=(
            "exact public-load/rejection outcomes for the frozen ten-by-fifteen "
            "artifact applicability matrix"
        ),
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
    try:
        authenticated_workspace = Path(candidate_workspace)
        if not authenticated_workspace.is_dir():
            raise OSError("candidate workspace is not a directory")
        authenticated_workspace_digest = _workspace_digest(
            authenticated_workspace
        )
    except (OSError, TypeError, ValueError) as exc:
        raise EvaluatorError(
            "complete observation authenticated candidate workspace is unavailable"
        ) from exc
    if (
        authenticated_workspace_digest != visible_before
        or authenticated_workspace_digest != lifecycle_before
    ):
        raise EvaluatorError(
            "complete observation candidate workspace digest does not match "
            "visible and lifecycle evidence"
        )
    adapter_process_id = lifecycle_result.get("adapter_process_id")
    if type(adapter_process_id) is not int or adapter_process_id <= 0:
        raise EvaluatorError("complete observation adapter process is malformed")
    semantic_report = lifecycle_result.get("semantic_report")
    semantic_observations = lifecycle_result.get("semantic_observations")
    if not isinstance(semantic_report, Mapping) or not isinstance(
        semantic_observations, Mapping
    ):
        raise EvaluatorError("complete observation semantic evidence is malformed")
    semantic_rows = semantic_report.get("architecture_results")
    if (
        not isinstance(semantic_rows, list)
        or [
            row.get("architecture_id") if isinstance(row, Mapping) else None
            for row in semantic_rows
        ]
        != candidate_architecture_ids
        or not isinstance(semantic_observations, Mapping)
        or list(semantic_observations) != candidate_architecture_ids
    ):
        raise EvaluatorError("complete observation semantic matrix binding drifted")
    for semantic_row, declaration, request_case in zip(
        semantic_rows,
        candidate_architecture_rows,
        request_record["architecture_cases"],
        strict=True,
    ):
        architecture_id = declaration["public_id"]
        assert isinstance(semantic_row, Mapping)
        if (
            semantic_row.get("structural_fields")
            != declaration["structural_fields"]
            or semantic_row.get("config_digest")
            != request_case["config"]["sha256"]
            or semantic_row.get("input_digest")
            != request_case["input"]["sha256"]
            or semantic_row.get("seed") != request_record["seed"]
            or semantic_row.get("construction_route")
            != F1_PUBLIC_CONSTRUCTION_ROUTE
            or semantic_row.get("persisted_rebuild_route")
            != F1_PUBLIC_PERSISTED_REBUILD_ROUTE
        ):
            raise EvaluatorError("complete observation semantic declaration drifted")
        observed_architecture = semantic_observations[architecture_id]
        if not isinstance(observed_architecture, Mapping) or set(
            observed_architecture
        ) != {
            "checkpoint",
            "bundle",
        }:
            raise EvaluatorError("complete observation adapter semantics are not exact")
        if (
            observed_architecture["checkpoint"]
            != semantic_row.get("adapter_checkpoint_reload")
            or observed_architecture["bundle"]
            != semantic_row.get("adapter_bundle_reload")
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
    bypass_observation = derive_authenticated_task0_bypass_observation(
        candidate_workspace=candidate_workspace,
        proof_workspace=task0_proof_workspace,
        candidate_tree=candidate_tree,
        discovery_input=legacy_bypass_discovery_input,
        builtin_architecture_ids=candidate_architecture_ids[:-1],
        witness_architecture_id=candidate_architecture_ids[-1],
    )
    complete_lifecycle = deepcopy(derived_lifecycle)
    h05 = complete_lifecycle[0]
    h05["satisfied"] = h05["satisfied"] and bypass_observation["satisfied"]
    h05["evidence"].append(bypass_observation["evidence"])
    h05["details"] = (
        h05["details"]
        + "; closed Task-0 desired-state proofs and legacy-bypass oracle"
    )
    return [h01, h02, h03, h04, *complete_lifecycle]


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
            "ES_F1_IMAGE_SIZE": "64",
            "ES_F1_SEED": "20260802",
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
    require_evaluator_successor_schema(
        payload,
        record_type="preedit-lifecycle-probe",
    )
    if _workspace_digest(workspace) != before:
        raise EvaluatorError("pre-edit lifecycle probe mutated the evaluated copy")
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
        require_evaluator_successor_schema(
            report,
            record_type="artifact-fixture-build",
        )
        if set(report) != {"schema_version", "artifact_eras"}:
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
                    "applicable_architecture_ids": [
                        "ffno"
                        if source_row["era_id"]
                        in _F1_FFNO_HISTORICAL_ARTIFACT_ERAS
                        else "cnn"
                    ],
                    "bytes": len(payload),
                    "cas_relative_path": relative_cas,
                    "era_id": source_row["era_id"],
                    "kind": kind,
                    "load_contract": contracts[kind],
                    "rejected_architecture_ids": [
                        architecture_id
                        for architecture_id in F1_ARTIFACT_ARCHITECTURE_DOMAIN
                        if architecture_id
                        != (
                            "ffno"
                            if source_row["era_id"]
                            in _F1_FFNO_HISTORICAL_ARTIFACT_ERAS
                            else "cnn"
                        )
                    ],
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
    candidate_evidence_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Verify the exact ten-era by fifteen-architecture outcome matrix."""

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
    manifest_rows = resolve_artifact_applicability(
        fixture_manifest=fixture_manifest,
        candidate_evidence_path=candidate_evidence_path,
    )
    expected_implementation_identities = _artifact_implementation_identities(
        fixture_manifest
    )
    probe_rows: list[dict[str, Any]] = []
    expected_fields = {
        "bytes",
        "cas_relative_path",
        "era_id",
        "kind",
        "load_contract",
        "applicable_architecture_ids",
        "rejected_architecture_ids",
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
        architecture_domain = [
            *F1_BUILTIN_ARCHITECTURES,
            next(
                architecture_id
                for architecture_id in row["rejected_architecture_ids"]
                if architecture_id not in set(F1_BUILTIN_ARCHITECTURES)
            ),
        ]
        for architecture_id in architecture_domain:
            preflight = preflight_artifact_architecture(
                artifact_row=row,
                architecture_id=architecture_id,
            )
            probe_rows.append(
                {
                    "absolute_path": str(path),
                    "architecture_id": architecture_id,
                    "era_id": row["era_id"],
                    "expected_outcome": (
                        "LOAD" if preflight is None else "REJECTED"
                    ),
                    "kind": row["kind"],
                }
            )
    before = _workspace_digest(workspace)
    with tempfile.TemporaryDirectory(prefix="es-f1-artifact-verify-") as raw_temp:
        temporary = Path(raw_temp)
        rows_path = temporary / "rows.json"
        report_path = temporary / "report.json"
        fixture_input = {
            "schema_version": "es-f1-artifact-fixture-input.v2",
            "artifact_eras": probe_rows,
        }
        require_evaluator_successor_schema(
            fixture_input,
            record_type="artifact-fixture-input",
        )
        rows_path.write_bytes(canonical_json_bytes(fixture_input))
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
    require_evaluator_successor_schema(
        report,
        record_type="artifact-fixture-verification",
    )
    if set(report) != {
        "schema_version",
        "artifact_eras",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    }:
        raise EvaluatorError("artifact fixture verification report is not exact")
    report_rows = report.get("artifact_eras", [])
    if [
        row.get("era_id") if isinstance(row, Mapping) else None
        for row in report_rows
    ] != list(ARTIFACT_ERA_IDS):
        raise EvaluatorError("artifact fixture verification era set/order drifted")
    expected_architecture_domain = [
        *F1_BUILTIN_ARCHITECTURES,
        next(
            architecture_id
            for architecture_id in manifest_rows[0]["rejected_architecture_ids"]
            if architecture_id not in set(F1_BUILTIN_ARCHITECTURES)
        ),
    ]
    outcome_fields = {
        "architecture_id",
        "diagnostic",
        "implementation_identity",
        "module_returned",
        "strict_load",
    }
    if any(
        not isinstance(row, Mapping)
        or set(row) != {"era_id", "architecture_results"}
        or not isinstance(row["architecture_results"], list)
        or [
            outcome.get("architecture_id")
            if isinstance(outcome, Mapping)
            else None
            for outcome in row["architecture_results"]
        ]
        != expected_architecture_domain
        or any(
            not isinstance(outcome, Mapping)
            or set(outcome) != outcome_fields
            for outcome in row["architecture_results"]
        )
        for row in report_rows
    ):
        raise EvaluatorError("artifact fixture verification matrix is not exact")
    for manifest_row, report_row in zip(
        manifest_rows,
        report_rows,
        strict=True,
    ):
        for outcome in report_row["architecture_results"]:
            architecture_id = outcome["architecture_id"]
            preflight = preflight_artifact_architecture(
                artifact_row=manifest_row,
                architecture_id=architecture_id,
            )
            if preflight is not None:
                if outcome != {"architecture_id": architecture_id, **preflight}:
                    raise EvaluatorError(
                        "artifact fixture unsupported-architecture diagnostic drifted"
                    )
            elif (
                outcome["diagnostic"] is not None
                or outcome["implementation_identity"]
                != expected_implementation_identities[architecture_id]
                or outcome["module_returned"] is not True
                or outcome["strict_load"] is not True
            ):
                raise EvaluatorError("artifact fixture applicable load did not succeed")
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


def _validate_architecture_matrix(
    candidate_claims: Mapping[str, Any],
    frozen_registry: set[str],
) -> None:
    if frozen_registry != set(F1_BUILTIN_ARCHITECTURES):
        raise ValueError("candidate architecture matrix frozen registry is not exact")
    try:
        with tempfile.TemporaryDirectory(
            prefix="es-f1-candidate-evidence-validation-"
        ) as raw_temp:
            path = Path(raw_temp) / "es_f1_candidate_evidence.json"
            path.write_bytes(canonical_json_bytes(candidate_claims))
            loaded = load_candidate_extension_evidence(path)
    except (OSError, TypeError, ValueError, TaskPackageError) as exc:
        detail = exc.detail if isinstance(exc, TaskPackageError) else str(exc)
        raise ValueError(f"candidate architecture matrix is invalid: {detail}") from exc
    if loaded != candidate_claims:
        raise ValueError("candidate architecture matrix canonical loader disagreed")
    rows = [*loaded["builtin_architectures"], loaded["candidate_witness"]]
    try:
        build_lifecycle_probe_inputs(
            architecture_rows=rows,
            seed=0,
        )
    except ValueError as exc:
        raise ValueError(f"candidate architecture matrix is invalid: {exc}") from exc


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
    _validate_architecture_matrix(candidate_claims, frozen_registry)

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
                    "schema_version": "es-f1-hard-finding.v2",
                }
            )
    return {
        "schema_version": "es-f1-hard-evaluation.v2",
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
