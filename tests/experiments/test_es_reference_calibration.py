from __future__ import annotations

import ast
import copy
from dataclasses import asdict
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[2]
A1_SCHEMA = (
    ROOT
    / "docs"
    / "plans"
    / "evidence"
    / "es-f1-large-scope-refreeze"
    / "a1-calibration-anchor.schema.json"
)
A1_ROOT = Path(
    "/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/"
    "pilot-2026-07-27/a1-v7"
)
POLICY_SHA256 = "sha256:" + "1" * 64
GIT_POLICY_SHA256 = "sha256:" + "2" * 64

REFERENCE_SCHEMA = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "f1_es"
    / "reference-product.schema.json"
)
REFERENCE_RECORD = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "f1_es"
    / "reference-product.json"
)
REFERENCE_DISPOSITION = REFERENCE_RECORD.with_name("reference-product-disposition.json")
TASK0_EVIDENCE = (
    ROOT / "docs" / "plans" / "evidence" / "es-f1-large-scope-refreeze"
)
PREEDIT_POLICY = TASK0_EVIDENCE / "preedit-policy-manifest.json"
PREEDIT_POLICY_SCHEMA = TASK0_EVIDENCE / "preedit-policy-manifest.schema.json"
SOURCE_CENSUS = TASK0_EVIDENCE / "source-census.json"
SOURCE_CENSUS_SCHEMA = TASK0_EVIDENCE / "source-census.schema.json"
SELECTOR_MANIFEST = TASK0_EVIDENCE / "preedit-selector-manifest.json"
SELECTOR_MANIFEST_SCHEMA = TASK0_EVIDENCE / "preedit-selector-manifest.schema.json"
TASK0_REVIEW_ADOPTION = TASK0_EVIDENCE / "task0-review-adoption.json"
TASK0_REVIEW_ADOPTION_SCHEMA = TASK0_EVIDENCE / "task0-review-adoption.schema.json"
A1_RECORD = TASK0_EVIDENCE / "a1-calibration-anchor.json"
TASK_SEED_MANIFEST = (
    ROOT / "experiments" / "orc_effectiveness" / "f1_es" / "task-seed-manifest.json"
)
TASK_SEED_SCHEMA = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "f1_es"
    / "task-seed-manifest.schema.json"
)
VISIBLE_TASK_CONTRACT = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "f1_es"
    / "task"
    / "visible-task-contract.json"
)
VISIBLE_TASK_CONTRACT_SCHEMA = VISIBLE_TASK_CONTRACT.with_suffix(".schema.json")
VISIBLE_CHECK_MANIFEST = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "f1_es"
    / "task"
    / "visible-check-manifest.json"
)
CANDIDATE_EVIDENCE_SCHEMA = (
    VISIBLE_TASK_CONTRACT.parent / "candidate-extension-evidence.schema.json"
)
LIFECYCLE_REQUEST_SCHEMA = (
    VISIBLE_TASK_CONTRACT.parent / "lifecycle-probe-request.schema.json"
)
LIFECYCLE_RESULT_SCHEMA = (
    VISIBLE_TASK_CONTRACT.parent / "lifecycle-probe-result.schema.json"
)
EVALUATOR_FIXTURE_MANIFEST = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "f1_es"
    / "evaluator"
    / "fixture-manifest.json"
)
GOVERNING_PLAN = ROOT / "docs" / "plans" / "2026-08-03-es-f1-large-scope-refreeze-execution-plan.md"
REFERENCE_CALIBRATION_TOOL = (
    ROOT / "scripts" / "experiments" / "es" / "reference_calibration.py"
)
F1_EVALUATOR_TOOL = ROOT / "scripts" / "experiments" / "es" / "f1_evaluator.py"
BOUNDARY_PROOF_RUNNER = ROOT / "scripts" / "experiments" / "es" / "boundary_proofs.py"
BOUNDARY_PROOF_RUNNER_SHA256 = (
    "sha256:d2a8d0a2c6c0e542bf8e2835f3b274527e638287e35239954e29b185a33e0b85"
)
REFERENCE_WITNESS_ID = "reference_witness"
REFERENCE_REF = "refs/heads/reference-product"
REFERENCE_CLASSIFICATIONS = (
    "benchmark_task_seed_asset",
    "documentation",
    "fixture",
    "production_python",
    "test",
    "vendored",
)
REFERENCE_CAS_MEMBER_IDS = (
    "canonical_patch",
    "candidate_evidence",
    "visible_check_result",
    "registry_signature_report",
    "artifact_fixture_verification",
    "lifecycle_result",
    "hard_evaluation",
    "bypass_discovery",
    "bypass_classification",
    "no_delivery_report",
)
REFERENCE_HARD_CLAUSE_EVIDENCE = (
    ("F1-H01-FOCUSED-SUITES", ("visible_check_result",)),
    (
        "F1-H02-SCHEMA-CONFORMANCE",
        ("candidate_evidence", "lifecycle_result"),
    ),
    ("F1-H03-BUILTIN-SIGNATURES", ("registry_signature_report",)),
    (
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
        ("artifact_fixture_verification",),
    ),
    (
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
        ("lifecycle_result", "bypass_classification"),
    ),
    ("F1-H06-STRUCTURAL-ROUNDTRIP", ("lifecycle_result",)),
    ("F1-H07-STRUCTURAL-IDENTITY-REJECTION", ("lifecycle_result",)),
    ("F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY", ("lifecycle_result",)),
    (
        "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
        ("lifecycle_result", "registry_signature_report"),
    ),
    ("F1-H10-OWNERSHIP-BOUNDARY", ("lifecycle_result",)),
)
REFERENCE_BINDING_IDS = (
    "preedit_policy",
    "source_census",
    "selector_manifest",
    "task0_review_adoption",
    "a1_anchor",
    "task_seed_manifest",
    "visible_task_contract",
    "evaluator_fixture_manifest",
    "governing_plan",
    "reference_calibration",
    "f1_evaluator",
    "boundary_proof_runner",
)
REFERENCE_CHAIN_SOURCE_LINES = {
    "ptycho_torch/extension_identity.py": tuple(
        '''from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


def _normalized_structural_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(fields, Mapping):
        raise TypeError("structural_fields must be a mapping")
    try:
        encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise TypeError("structural_fields must contain JSON values") from exc
    normalized = json.loads(encoded)
    if not isinstance(normalized, dict):
        raise TypeError("structural_fields must encode a JSON object")
    return normalized


@dataclass(frozen=True)
class ExtensionIdentity:
    public_id: str
    implementation_path: str
    structural_fields: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.public_id, str) or not self.public_id:
            raise ValueError("public_id must be a non-empty string")
        if not isinstance(self.implementation_path, str) or ":" not in self.implementation_path:
            raise ValueError("implementation_path must be a module:attribute string")
        object.__setattr__(
            self,
            "structural_fields",
            _normalized_structural_fields(self.structural_fields),
        )

    def to_config(self) -> dict[str, Any]:
        return {
            "public_id": self.public_id,
            "implementation_path": self.implementation_path,
            "structural_fields": _normalized_structural_fields(self.structural_fields),
        }

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ExtensionIdentity":
        if set(config) != {"public_id", "implementation_path", "structural_fields"}:
            raise ValueError("identity config has an unexpected field domain")
        return cls(
            public_id=config["public_id"],
            implementation_path=config["implementation_path"],
            structural_fields=config["structural_fields"],
        )


def extension_identity_sha256(identity: ExtensionIdentity) -> str:
    canonical = json.dumps(
        identity.to_config(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
'''.splitlines(keepends=True)
    ),
    "ptycho_torch/generators/extension_adapter.py": tuple(
        '''from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import torch

from ptycho_torch.extension_identity import ExtensionIdentity


class ExtensionRegistry:
    def __init__(self) -> None:
        self._constructors: dict[
            str, tuple[str, Callable[..., torch.nn.Module]]
        ] = {}

    def register(
        self,
        identity: ExtensionIdentity,
        constructor: Callable[..., torch.nn.Module],
    ) -> None:
        if identity.public_id in self._constructors:
            raise ValueError(f"extension already registered: {identity.public_id!r}")
        self._constructors[identity.public_id] = (
            identity.implementation_path,
            constructor,
        )

    def build(self, identity: ExtensionIdentity) -> torch.nn.Module:
        registered = self._constructors.get(identity.public_id)
        if registered is None:
            raise ValueError(f"unregistered extension public_id: {identity.public_id!r}")
        implementation_path, constructor = registered
        if implementation_path != identity.implementation_path:
            raise ValueError("requested implementation differs from registration")
        module = constructor(**dict(identity.structural_fields))
        if not isinstance(module, torch.nn.Module):
            raise TypeError("registered constructor did not build a torch module")
        return module


class ReferenceExtensionGenerator:
    def __init__(self, config: object) -> None:
        self.config = config

    def build_model(self, configs: object) -> object:
        return configs


def build_extension_from_config(
    registry: ExtensionRegistry,
    config: Mapping[str, Any],
) -> tuple[torch.nn.Module, ExtensionIdentity]:
    identity = ExtensionIdentity.from_config(config)
    return registry.build(identity), identity
'''.splitlines(keepends=True)
    ),
    "ptycho_torch/extension_persistence.py": tuple(
        '''from __future__ import annotations

from pathlib import Path
from typing import Any

import torch

from ptycho_torch.extension_identity import (
    ExtensionIdentity,
    extension_identity_sha256,
)
from ptycho_torch.generators.registry import resolve_generator


def _registered_constructor(model_spec: Any) -> torch.nn.Module:
    return resolve_generator(model_spec)


def save_extension_checkpoint(
    module: torch.nn.Module,
    identity: ExtensionIdentity,
    checkpoint: str | Path,
) -> None:
    torch.save(
        {
            "identity": identity.to_config(),
            "identity_sha256": extension_identity_sha256(identity),
            "state_dict": module.state_dict(),
        },
        checkpoint,
    )


def load_extension_checkpoint(
    config: Any,
    checkpoint: str | Path,
) -> tuple[torch.nn.Module, ExtensionIdentity]:
    payload: dict[str, Any] = torch.load(
        checkpoint, map_location="cpu", weights_only=True
    )
    if set(payload) != {"identity", "identity_sha256", "state_dict"}:
        raise ValueError("checkpoint has an unexpected field domain")
    identity = ExtensionIdentity.from_config(payload["identity"])
    module = _registered_constructor(config)
    if extension_identity_sha256(identity) != payload["identity_sha256"]:
        raise ValueError("checkpoint extension identity digest does not match")
    module.load_state_dict(payload["state_dict"], strict=True)
    return module, identity
'''.splitlines(keepends=True)
    ),
    "ptycho_torch/extension_inference.py": tuple(
        '''from __future__ import annotations

from pathlib import Path

import torch

from ptycho_torch.extension_identity import ExtensionIdentity
from ptycho_torch.extension_persistence import load_extension_checkpoint


def predict_extension_checkpoint(
    config: object,
    checkpoint: str | Path,
    value: torch.Tensor,
) -> tuple[torch.Tensor, ExtensionIdentity]:
    module, identity = load_extension_checkpoint(config, checkpoint)
    module.eval()
    with torch.no_grad():
        prediction = module(value)
    return prediction, identity
'''.splitlines(keepends=True)
    ),
}
REFERENCE_CHAIN_PATHS = tuple(REFERENCE_CHAIN_SOURCE_LINES)
REFERENCE_REGISTRY_PATH = "ptycho_torch/generators/registry.py"
REFERENCE_PADDING_PATH = "ptycho_torch/reference_training_workload.py"
REFERENCE_EXTENSION_CLUSTER_BY_PATH = {
    REFERENCE_CHAIN_PATHS[0]: "IDENTITY_CONFIG",
    REFERENCE_CHAIN_PATHS[1]: "CONSTRUCTION_ADAPTERS",
    REFERENCE_CHAIN_PATHS[2]: "PERSISTENCE_REBUILD",
    REFERENCE_CHAIN_PATHS[3]: "INFERENCE_WORKFLOWS",
    REFERENCE_REGISTRY_PATH: "CONSTRUCTION_ADAPTERS",
    REFERENCE_PADDING_PATH: "TRAINING_OPTIMIZER",
}
REFERENCE_BYPASS_CLUSTER_BY_PATH = {
    "archive/root_scripts/analysis/extract_reconstructions.py": "CONSUMER_BYPASS",
    "ptycho/config/metadata_adapter.py": "IDENTITY_CONFIG",
    "ptycho/metadata.py": "CONSUMER_BYPASS",
}
REFERENCE_NEW_RESPONSIBILITY_IDS_BY_PATH = {
    "ptycho/config/metadata_adapter.py": (
        "PROJECTION_DOWNSTREAM_CONSUMERS",
        "PUBLIC_CONFIGURATION",
    ),
    REFERENCE_CHAIN_PATHS[0]: (
        "PROJECTION_DOWNSTREAM_CONSUMERS",
        "PUBLIC_CONFIGURATION",
        "STRUCTURAL_BOUNDARY_PERSISTED_IDENTITY",
    ),
    REFERENCE_CHAIN_PATHS[1]: (
        "CONSTRUCTION_ARCHITECTURES",
        "LEGACY_BYPASS_RETIREMENT",
        "PROJECTION_DOWNSTREAM_CONSUMERS",
        "PUBLIC_CONFIGURATION",
    ),
    REFERENCE_CHAIN_PATHS[2]: (
        "CHECKPOINT_BUNDLE_PERSISTENCE",
        "LEGACY_BYPASS_RETIREMENT",
        "PROJECTION_DOWNSTREAM_CONSUMERS",
        "PUBLIC_CONFIGURATION",
        "STRUCTURAL_BOUNDARY_PERSISTED_IDENTITY",
    ),
    REFERENCE_CHAIN_PATHS[3]: (
        "FRESH_RELOAD_INFERENCE",
        "PROJECTION_DOWNSTREAM_CONSUMERS",
        "PUBLIC_CONFIGURATION",
    ),
    REFERENCE_PADDING_PATH: ("TRAINING_OPTIMIZER_LIFECYCLE",),
}
REFERENCE_CLUSTER_BY_PATH = {
    **REFERENCE_BYPASS_CLUSTER_BY_PATH,
    **REFERENCE_EXTENSION_CLUSTER_BY_PATH,
}
REFERENCE_EDGE_LIFECYCLE_CLAUSES = {
    "01_identity_config_to_construction_adapters": (
        "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",
        "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
    ),
    "02_construction_adapters_to_persistence_rebuild": (
        "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
    ),
    "03_persistence_rebuild_to_inference_workflows": (
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
    ),
}
REFERENCE_EDGE_STATIC_SPECS = {
    "01_identity_config_to_construction_adapters": {
        "producer_path": REFERENCE_CHAIN_PATHS[0],
        "consumer_path": REFERENCE_CHAIN_PATHS[1],
        "imported_binding": "ExtensionIdentity",
        "producer_owner": "ExtensionIdentity",
        "producer_name": "from_config",
        "resolved_symbol": "ExtensionIdentity.from_config",
    },
    "02_construction_adapters_to_persistence_rebuild": {
        "producer_path": REFERENCE_REGISTRY_PATH,
        "consumer_path": REFERENCE_CHAIN_PATHS[2],
        "imported_binding": "resolve_generator",
        "producer_owner": None,
        "producer_name": "resolve_generator",
        "resolved_symbol": "resolve_generator",
    },
    "03_persistence_rebuild_to_inference_workflows": {
        "producer_path": REFERENCE_CHAIN_PATHS[2],
        "consumer_path": REFERENCE_CHAIN_PATHS[3],
        "imported_binding": "load_extension_checkpoint",
        "producer_owner": None,
        "producer_name": "load_extension_checkpoint",
        "resolved_symbol": "load_extension_checkpoint",
    },
}
REFERENCE_EDGE_EVIDENCE_KIND = (
    "static_import_call_resolution_with_lifecycle_conformance"
)
REFERENCE_EDGE_EVIDENCE_SEMANTICS = (
    "STATIC_IMPORT_CALL_RESOLUTION_PLUS_LIFECYCLE_CONFORMANCE_"
    "NOT_FUNCTION_LEVEL_RUNTIME_TRACE"
)
REFERENCE_DOCUMENTATION_PATH = "benchmark/es_f1/reference-product-notes.md"
REFERENCE_TREATMENT_PROMPT = (
    ROOT
    / "workflows"
    / "experiments"
    / "qa_placement_effectiveness"
    / "qa_placement_arms.orc"
)
REFERENCE_PROMPT_EXTERNS = REFERENCE_TREATMENT_PROMPT.with_name("prompts.json")
REFERENCE_EVALUATOR_RUBRIC = (
    REFERENCE_TREATMENT_PROMPT.parent / "prompts" / "trial_rubric.md"
)
REFERENCE_LOGICAL_OUTER_ARGV = (
    "codex",
    "exec",
    "--dangerously-bypass-approvals-and-sandbox",
    "--skip-git-repo-check",
    "--model",
    "gpt-5.5",
    "--config",
    "reasoning_effort=high",
)
REFERENCE_LOGICAL_METERED_ARGV = (
    "/opt/codex",
    "exec",
    "--json",
    "--dangerously-bypass-approvals-and-sandbox",
    "--skip-git-repo-check",
    "--model",
    "gpt-5.5",
    "--config",
    "model_reasoning_effort=high",
    "--",
    "-",
)
REFERENCE_GIT_POLICY_SHA256 = (
    "sha256:58c757172ca0c7bb667f7b1291a09d9ec8e37866fe6cd04d903037a5a8bd5c85"
)
REFERENCE_PYTHON = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
REFERENCE_PYTHON_TARGET = Path(
    "/home/ollie/miniconda3/envs/ptycho311/bin/python3.11"
)
REFERENCE_PYTHON_VERSION = "Python 3.11.13"
REFERENCE_PYTHON_SHA256 = (
    "sha256:d575ac63749e61ede79bc20518113452b114506ceec0af0cf3993b0fcc486cb0"
)
REFERENCE_PYTEST_CARRIER = Path("/usr/bin/bwrap")
REFERENCE_PYTEST_CARRIER_VERSION = "bubblewrap 0.9.0"
REFERENCE_PYTEST_CARRIER_SHA256 = (
    "sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712"
)
REFERENCE_TOP_LEVEL_FIELDS = (
    "schema_version",
    "bindings",
    "lineage",
    "repository",
    "evidence_store",
    "patch",
    "metric",
    "structural_scope",
    "evaluator_evidence",
    "desired_state_proofs",
    "bypass_oracle",
    "no_delivery",
    "record_sha256",
)


def _calibration_module():
    return importlib.import_module("scripts.experiments.es.reference_calibration")


def _git_contract(calibration, **changes):
    values = {
        "executable": Path("/usr/bin/git"),
        "version": "2.43.0",
        "executable_sha256": (
            "sha256:"
            "2a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668"
        ),
        "diff_controls": (
            "--no-ext-diff",
            "--no-textconv",
            "--diff-algorithm=histogram",
            "--find-renames=100%",
            "--find-copies=100%",
            "--find-copies-harder",
        ),
        "policy_sha256": GIT_POLICY_SHA256,
    }
    values.update(changes)
    return calibration.GitContract(**values)


def _production_policy(calibration, path: str):
    return calibration.MetricPathPolicy(
        path=path,
        classification="production_python",
        responsibility_ids=("RESP",),
    )


def _write_tree(root: Path, rows: dict[str, bytes]) -> None:
    for relative, payload in rows.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _require_a1_evidence() -> None:
    if not A1_ROOT.is_dir():
        pytest.skip(f"retained A1 calibration evidence is unavailable: {A1_ROOT}")


def _build_anchor(calibration):
    _require_a1_evidence()
    return calibration.build_a1_anchor(
        evidence_root=A1_ROOT,
        preedit_policy_sha256=POLICY_SHA256,
        git_contract=_git_contract(calibration),
    )


def test_canonical_json_uses_ascii_sorted_compact_lf_domain() -> None:
    calibration = _calibration_module()

    assert calibration.canonical_json_bytes(
        {"z": "λ", "a": [1, True, None]}
    ) == b'{"a":[1,true,null],"z":"\\u03bb"}\n'

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.canonical_json_bytes({"value": float("nan")})
    assert caught.value.code == "record_noncanonical"


def test_record_sha256_omits_exactly_the_top_level_digest_field() -> None:
    calibration = _calibration_module()
    body = {
        "schema_version": "example.v1",
        "nested": {"record_sha256": "this nested field remains in the body"},
        "value": 7,
    }
    sealed = calibration.seal_record(body)

    assert calibration.canonical_record_body_bytes(sealed) == (
        calibration.canonical_json_bytes(body)
    )
    assert sealed["record_sha256"] == calibration.compute_record_sha256(sealed)
    assert calibration.validate_record_sha256(sealed) == sealed["record_sha256"]


@pytest.mark.parametrize(
    "mutation",
    ["body", "digest", "missing", "complete-record-hash"],
)
def test_record_sha256_rejects_projection_and_digest_tamper(mutation: str) -> None:
    calibration = _calibration_module()
    record = calibration.seal_record({"schema_version": "example.v1", "value": 7})
    if mutation == "body":
        record["value"] = 8
    elif mutation == "digest":
        record["record_sha256"] = "sha256:" + "0" * 64
    elif mutation == "missing":
        record.pop("record_sha256")
    else:
        record["record_sha256"] = "sha256:" + hashlib.sha256(
            calibration.canonical_json_bytes(record)
        ).hexdigest()

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.validate_record_sha256(record)
    assert caught.value.code == "record_sha256_invalid"


def test_closed_canonical_loader_rejects_extra_digest_field_and_duplicate_key(
    tmp_path: Path,
) -> None:
    calibration = _calibration_module()
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "value", "record_sha256"],
        "properties": {
            "schema_version": {"const": "example.v1"},
            "value": {"type": "integer"},
            "record_sha256": {"type": "string"},
        },
    }
    schema_path = tmp_path / "record.schema.json"
    schema_path.write_bytes(json.dumps(schema, indent=2).encode() + b"\n")

    extra = calibration.seal_record(
        {
            "schema_version": "example.v1",
            "value": 7,
            "other_record_sha256": "sha256:" + "0" * 64,
        }
    )
    record_path = tmp_path / "extra.json"
    record_path.write_bytes(calibration.canonical_json_bytes(extra))
    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.load_canonical_record(
            record_path,
            schema_path=schema_path,
            expected_record_sha256=extra["record_sha256"],
        )
    assert caught.value.code == "record_schema_invalid"

    duplicate = calibration.seal_record({"schema_version": "example.v1", "value": 7})
    raw = calibration.canonical_json_bytes(duplicate).replace(
        b'{"record_sha256":', b'{"value":7,"record_sha256":', 1
    )
    record_path.write_bytes(raw)
    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.load_canonical_record(
            record_path,
            schema_path=schema_path,
            expected_record_sha256=duplicate["record_sha256"],
        )
    assert caught.value.code == "record_noncanonical"


def test_git_contract_is_exact_and_rejects_tool_drift() -> None:
    calibration = _calibration_module()

    assert calibration.verify_git_contract(_git_contract(calibration)).version == "2.43.0"

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.verify_git_contract(
            _git_contract(calibration, executable_sha256="sha256:" + "0" * 64)
        )
    assert caught.value.code == "git_contract_invalid"


def test_numstat_parser_handles_normal_and_nul_rename_rows() -> None:
    calibration = _calibration_module()

    rows = calibration.parse_numstat_z(
        b"2\t1\tplain.py\0" b"0\t0\t\0old name.py\0new name.py\0"
    )

    assert rows == (
        calibration.NumstatRow(2, 1, "plain.py", "plain.py"),
        calibration.NumstatRow(0, 0, "old name.py", "new name.py"),
    )


def test_metric_counts_additions_and_separates_classifications(tmp_path: Path) -> None:
    calibration = _calibration_module()
    base = (tmp_path / "base").resolve()
    candidate = (tmp_path / "candidate").resolve()
    base.mkdir()
    candidate.mkdir()
    _write_tree(
        base,
        {
            "pkg/core.py": b"keep\nold\n",
            "pkg/deleted.py": b"gone forever\n",
            "pkg/rename_old.py": b"unique rename payload\n",
            "pkg/copy_source.py": b"unique copy payload " + b"x" * 1_024 + b"\n",
            "tests/test_core.py": b"old test\n",
            "docs/readme.md": b"unchanged docs\n",
        },
    )
    _write_tree(
        candidate,
        {
            "pkg/core.py": b"keep\nnew\nextra\n",
            "pkg/rename_new.py": b"unique rename payload\n",
            "pkg/copy_source.py": b"unique copy payload " + b"x" * 1_024 + b"\n",
            "pkg/copy_dest.py": b"unique copy payload " + b"x" * 1_024 + b"\n",
            "pkg/new.py": b"\n# comment\n",
            "tests/test_core.py": b"new test\nextra test\n",
            "docs/readme.md": b"unchanged docs\n",
        },
    )
    policies = tuple(
        sorted(
            (
                *(
                    _production_policy(calibration, path)
                    for path in (
                        "pkg/core.py",
                        "pkg/deleted.py",
                        "pkg/rename_new.py",
                        "pkg/copy_source.py",
                        "pkg/copy_dest.py",
                        "pkg/new.py",
                    )
                ),
                calibration.MetricPathPolicy("tests/test_core.py", "test", ()),
                calibration.MetricPathPolicy("docs/readme.md", "documentation", ()),
            ),
            key=lambda row: row.path,
        )
    )

    result = calibration.measure_implementation_delta(
        base_root=base,
        candidate_root=candidate,
        path_policies=policies,
        allowed_responsibility_ids=frozenset({"RESP"}),
        git_contract=_git_contract(calibration),
    )

    assert result.implementation_additions == 4
    assert result.implementation_deletions == 2
    assert result.base_physical_lines == 5
    assert result.candidate_postimage_physical_lines == 8
    assert result.totals_by_classification["test"].additions == 2
    assert result.totals_by_classification["test"].deletions == 1
    by_candidate = {row.candidate_path: row for row in result.rows}
    assert by_candidate["pkg/core.py"].change_kind == "modify"
    assert by_candidate["pkg/rename_new.py"].change_kind == "rename"
    assert by_candidate["pkg/copy_dest.py"].change_kind == "copy"
    assert by_candidate["pkg/new.py"].additions == 2
    deletion = next(row for row in result.rows if row.base_path == "pkg/deleted.py")
    assert deletion.change_kind == "delete"
    assert deletion.additions == 0
    assert deletion.deletions == 1


@pytest.mark.parametrize(
    "invalid_kind", ["binary", "non_utf8", "symlink", "generated", "unclassified"]
)
def test_metric_rejects_unsafe_or_unclassified_inputs(
    tmp_path: Path, invalid_kind: str
) -> None:
    calibration = _calibration_module()
    base = (tmp_path / invalid_kind / "base").resolve()
    candidate = (tmp_path / invalid_kind / "candidate").resolve()
    base.mkdir(parents=True)
    candidate.mkdir(parents=True)
    (base / "item.py").write_bytes(b"old\n")
    (candidate / "item.py").write_bytes(b"new\n")
    policies = (_production_policy(calibration, "item.py"),)
    if invalid_kind == "binary":
        (candidate / "item.py").write_bytes(b"new\0value\n")
    elif invalid_kind == "non_utf8":
        (candidate / "item.py").write_bytes(b"\xff\n")
    elif invalid_kind == "symlink":
        (candidate / "item.py").unlink()
        os.symlink(base / "item.py", candidate / "item.py")
    elif invalid_kind == "generated":
        policies = (
            calibration.MetricPathPolicy("item.py", "generated", ()),
        )
    elif invalid_kind == "unclassified":
        policies = ()

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.measure_implementation_delta(
            base_root=base,
            candidate_root=candidate,
            path_policies=policies,
            allowed_responsibility_ids=frozenset({"RESP"}),
            git_contract=_git_contract(calibration),
        )
    assert caught.value.code == "metric_input_invalid"


def test_metric_rejects_responsibility_and_git_contract_drift(tmp_path: Path) -> None:
    calibration = _calibration_module()
    base = (tmp_path / "base").resolve()
    candidate = (tmp_path / "candidate").resolve()
    base.mkdir()
    candidate.mkdir()
    (base / "item.py").write_bytes(b"old\n")
    (candidate / "item.py").write_bytes(b"new\n")

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.measure_implementation_delta(
            base_root=base,
            candidate_root=candidate,
            path_policies=(
                calibration.MetricPathPolicy(
                    "item.py", "production_python", ("UNKNOWN",)
                ),
            ),
            allowed_responsibility_ids=frozenset({"RESP"}),
            git_contract=_git_contract(calibration),
        )
    assert caught.value.code == "metric_input_invalid"

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.measure_implementation_delta(
            base_root=base,
            candidate_root=candidate,
            path_policies=(_production_policy(calibration, "item.py"),),
            allowed_responsibility_ids=frozenset({"RESP"}),
            git_contract=_git_contract(
                calibration,
                diff_controls=("--no-ext-diff",),
            ),
        )
    assert caught.value.code == "git_contract_invalid"


def test_a1_schema_is_closed_and_anchor_recomputes_667_2_690() -> None:
    calibration = _calibration_module()
    schema = json.loads(A1_SCHEMA.read_bytes())
    Draft202012Validator.check_schema(schema)
    anchor = _build_anchor(calibration)

    Draft202012Validator(schema).validate(anchor)
    assert [row["member_id"] for row in anchor["members"]] == [
        "pilot_lock",
        "summary",
        "block_record",
        "package_manifest",
        "direct_patch",
        "base_entrypoint",
        "base_types",
        "base_init",
        "direct_entrypoint",
        "direct_types",
        "direct_init",
        "review_1",
        "review_2",
    ]
    assert anchor["metric"]["implementation_additions"] == 667
    assert anchor["metric"]["implementation_deletions"] == 2
    assert anchor["metric"]["candidate_postimage_physical_lines"] == 690
    assert calibration.validate_record_sha256(anchor) == anchor["record_sha256"]

    opened = copy.deepcopy(anchor)
    opened["unexpected"] = None
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(opened)


def test_a1_loader_validates_schema_record_members_bindings_and_fresh_metric(
    tmp_path: Path,
) -> None:
    calibration = _calibration_module()
    anchor = _build_anchor(calibration)
    anchor_path = tmp_path / "a1-anchor.json"
    anchor_path.write_bytes(calibration.canonical_json_bytes(anchor))

    result = calibration.validate_a1_anchor(
        anchor_path,
        schema_path=A1_SCHEMA,
        expected_record_sha256=anchor["record_sha256"],
        expected_preedit_policy_sha256=POLICY_SHA256,
        git_contract=_git_contract(calibration),
    )

    assert result.record == anchor
    assert result.measurement.implementation_additions == 667
    assert result.measurement.implementation_deletions == 2
    assert result.measurement.candidate_postimage_physical_lines == 690


@pytest.mark.parametrize("mutation", ["stale-body", "digest", "metric", "extra", "policy"])
def test_a1_loader_rejects_record_and_policy_tamper(
    tmp_path: Path, mutation: str
) -> None:
    calibration = _calibration_module()
    anchor = _build_anchor(calibration)
    if mutation == "stale-body":
        anchor["selection"]["arm_id"] = "arm-tampered"
    elif mutation == "digest":
        anchor["record_sha256"] = "sha256:" + "0" * 64
    elif mutation == "metric":
        anchor["metric"]["implementation_additions"] = 666
        anchor = calibration.seal_record(anchor)
    elif mutation == "extra":
        anchor["unexpected_record_sha256"] = "sha256:" + "0" * 64
        anchor = calibration.seal_record(anchor)
    else:
        anchor["preedit_policy_sha256"] = "sha256:" + "3" * 64
        anchor = calibration.seal_record(anchor)
    anchor_path = tmp_path / f"{mutation}.json"
    anchor_path.write_bytes(calibration.canonical_json_bytes(anchor))

    with pytest.raises(calibration.CalibrationError):
        calibration.validate_a1_anchor(
            anchor_path,
            schema_path=A1_SCHEMA,
            expected_record_sha256=anchor["record_sha256"],
            expected_preedit_policy_sha256=POLICY_SHA256,
            git_contract=_git_contract(calibration),
        )


@pytest.mark.parametrize("mutation", ["missing", "symlink", "digest", "escape"])
def test_a1_member_validation_rejects_missing_alias_and_byte_drift(
    tmp_path: Path, mutation: str
) -> None:
    calibration = _calibration_module()
    anchor = _build_anchor(calibration)
    copied_root = (tmp_path / mutation / "a1-v7").resolve()
    for row in anchor["members"]:
        source = A1_ROOT / row["path"]
        target = copied_root / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    rows = copy.deepcopy(anchor["members"])
    target = copied_root / rows[5]["path"]
    if mutation == "missing":
        target.unlink()
    elif mutation == "symlink":
        target.unlink()
        os.symlink(copied_root / rows[6]["path"], target)
    elif mutation == "digest":
        target.write_bytes(target.read_bytes() + b"# drift\n")
    else:
        rows[5]["path"] = "../escape.py"

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.validate_a1_member_files(copied_root, rows)
    assert caught.value.code == "a1_member_invalid"


@pytest.mark.parametrize("mutation", ["pilot", "block", "summary", "review"])
def test_a1_internal_binding_validation_rejects_selection_drift(mutation: str) -> None:
    calibration = _calibration_module()
    anchor = _build_anchor(calibration)
    payloads = calibration.validate_a1_member_files(A1_ROOT, anchor["members"])
    changed = dict(payloads)
    if mutation == "pilot":
        value = json.loads(changed["pilot_lock"])
        value["task"]["task_id"] = "A2"
        changed["pilot_lock"] = json.dumps(value).encode()
    elif mutation == "block":
        value = json.loads(changed["block_record"])
        direct = next(
            row for row in value["treatment_executions"] if row["treatment_id"] == "DIRECT"
        )
        direct["lifecycle_outcome"] = "PROTOCOL_FAILURE"
        changed["block_record"] = json.dumps(value).encode()
    elif mutation == "summary":
        value = json.loads(changed["summary"])
        block = next(row for row in value["valid_blocks"] if row["block_id"] == anchor["selection"]["block_id"])
        outcome = next(
            row for row in block["method_outcomes"] if row["comparison"] == "DIRECT_VS_ORC"
        )
        outcome["method_outcome"] = "B_WIN"
        changed["summary"] = json.dumps(value).encode()
    else:
        value = json.loads(changed["review_1"])
        pair = next(
            row
            for row in value["pairwise_results"]
            if row["candidate_b_label"] == "candidate-3cca13b2595a"
        )
        pair["outcome"] = "A"
        changed["review_1"] = json.dumps(value).encode()

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.validate_a1_evidence_bindings(changed, anchor["selection"])
    assert caught.value.code == "a1_binding_invalid"


def _json_record(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _raw_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _binding_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _authority_binding(path: Path, schema_path: Path | None = None) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "path": _binding_path(path),
        "sha256": _raw_sha256(path),
    }
    record = _json_record(path) if path.suffix == ".json" else None
    if record is not None and "record_sha256" in record:
        binding["record_sha256"] = record["record_sha256"]
    if schema_path is not None:
        binding["schema_path"] = _binding_path(schema_path)
        binding["schema_sha256"] = _raw_sha256(schema_path)
    return binding


def _git_blob_id(payload: bytes) -> str:
    prefix = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(prefix + payload).hexdigest()


def _git_environment(**changes: str) -> dict[str, str]:
    environment = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
    }
    environment.update(changes)
    return environment


def _run_git(
    repository: Path,
    *args: str,
    input_bytes: bytes | None = None,
    extra_environment: dict[str, str] | None = None,
) -> bytes:
    environment = _git_environment(**(extra_environment or {}))
    completed = subprocess.run(
        ("/usr/bin/git", "-C", str(repository), *args),
        input=input_bytes,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    return completed.stdout


def _strict_text_tree_payloads(
    repository: Path,
    tree: str,
) -> dict[str, dict[str, Any]]:
    """Reopen the regular strict-text projection of one bound Git tree."""

    entries = _run_git(
        repository,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        tree,
    )
    payloads: dict[str, dict[str, Any]] = {}
    for raw_entry in entries.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        raw_mode, object_type, raw_object_id = metadata.split(b" ", 2)
        if raw_mode not in {b"100644", b"100755"}:
            continue
        assert object_type == b"blob"
        path = raw_path.decode("utf-8", errors="strict")
        payload = _run_git(
            repository,
            "cat-file",
            "blob",
            raw_object_id.decode("ascii"),
        )
        try:
            payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            continue
        if b"\0" in payload:
            continue
        assert path not in payloads
        payloads[path] = {
            "blob_id": raw_object_id.decode("ascii"),
            "mode": int(raw_mode, 8) & 0o777,
            "payload": payload,
        }
    return payloads


def _write_bytes(root: Path, relative: str, payload: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _serialize_implementation_delta(
    measurement,
) -> dict[str, Any]:
    record = json.loads(json.dumps(asdict(measurement)))
    for row in record["rows"]:
        path = row["candidate_path"] or row["base_path"]
        row["cluster_ids"] = (
            [REFERENCE_CLUSTER_BY_PATH[path]]
            if row["classification"] == "production_python"
            else []
        )
    zero = {
        "additions": 0,
        "deletions": 0,
        "base_physical_lines": 0,
        "candidate_postimage_physical_lines": 0,
    }
    record["totals_by_classification"] = {
        classification: record["totals_by_classification"].get(
            classification, copy.deepcopy(zero)
        )
        for classification in REFERENCE_CLASSIFICATIONS
    }
    return record


def _reference_module_source(
    path: str,
    cluster_id: str,
    count: int,
    *,
    padding_only: bool,
) -> bytes:
    if padding_only and path == REFERENCE_PADDING_PATH:
        return (
            '"""Deliberate AST-empty padding control."""\n'
            + "".join(
                f"# reference-padding-{cluster_id.lower()}-{ordinal:04d}\n"
                for ordinal in range(count - 1)
            )
        ).encode("utf-8")
    semantic_lines = list(REFERENCE_CHAIN_SOURCE_LINES.get(path, ()))
    if path == REFERENCE_PADDING_PATH:
        semantic_lines.append(
            '"""Reference-product training/optimizer workload assignments."""\n'
        )
    assert len(semantic_lines) <= count
    prefix = path.removesuffix(".py").rsplit("/", 1)[-1]
    semantic_lines.extend(
        f"{prefix}_assignment_{ordinal:04d} = {ordinal}\n"
        for ordinal in range(count - len(semantic_lines))
    )
    return "".join(semantic_lines).encode("utf-8")


def _reference_registry_source(base: bytes, additions: int) -> bytes:
    semantic_lines = [
        "\n",
        "from ptycho_torch.generators.extension_adapter import "
        "ReferenceExtensionGenerator\n",
        '_REGISTRY["reference_witness"] = ReferenceExtensionGenerator\n',
    ]
    assert len(semantic_lines) <= additions
    semantic_lines.extend(
        f"reference_registry_assignment_{ordinal:04d} = {ordinal}\n"
        for ordinal in range(additions - len(semantic_lines))
    )
    assert base.endswith(b"\n")
    candidate = base + "".join(semantic_lines).encode("utf-8")
    ast.parse(candidate.decode("utf-8", errors="strict"))
    return candidate


def _reference_bypass_payloads(
    repository: Path,
    task_seed_commit: str,
    *,
    restored_direct_match: bool,
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    removal_path = "archive/root_scripts/analysis/extract_reconstructions.py"
    adapter_path = "ptycho/config/metadata_adapter.py"
    metadata_path = "ptycho/metadata.py"
    removal_base = _run_git(
        repository,
        "show",
        f"{task_seed_commit}:{removal_path}",
    )
    metadata_base = _run_git(
        repository,
        "show",
        f"{task_seed_commit}:{metadata_path}",
    )
    legacy_import = b"from ptycho.config.config import TrainingConfig, ModelConfig\n"
    adapter_import = (
        b"from ptycho.config.config import TrainingConfig\n"
        b"from ptycho.config.metadata_adapter import "
        b"build_training_config_from_metadata\n"
    )
    legacy_body = (
        b'    physics_params = metadata.get("physics_parameters", {})\n'
        b'    training_params = metadata.get("training_parameters", {})\n'
        b"    \n"
        b"    model_config = ModelConfig(\n"
        b'        N=physics_params.get("N", 64),\n'
        b'        gridsize=physics_params.get("gridsize", 1),\n'
        b'        model_type=physics_params.get("model_type", "pinn")\n'
        b"    )\n"
        b"    \n"
        b"    return TrainingConfig(\n"
        b"        model=model_config,\n"
        b'        nphotons=physics_params.get("nphotons", 1e9),\n'
        b'        probe_trainable=physics_params.get("probe_trainable", False),\n'
        b"        intensity_scale_trainable="
        b'physics_params.get("intensity_scale_trainable", True),\n'
        b'        nll_weight=physics_params.get("nll_weight", 1.0),\n'
        b'        n_images=training_params.get("n_images", 1000),\n'
        b'        batch_size=training_params.get("batch_size", 32),\n'
        b'        nepochs=training_params.get("nepochs", 50)\n'
        b"    )"
    )
    delegated_body = (
        b"    return build_training_config_from_metadata(metadata)"
    )
    adapter_source = (
        b'"""Metadata-to-training configuration boundary."""\n'
        b"\n"
        b"from collections.abc import Mapping\n"
        b"from typing import Any\n"
        b"\n"
        b"from ptycho.config.config import ModelConfig, TrainingConfig\n"
        b"\n"
        b"\n"
        b"def build_training_config_from_metadata(\n"
        b"    metadata: Mapping[str, Any],\n"
        b") -> TrainingConfig:\n"
        b'    """Build metadata-backed configuration at the public boundary."""\n'
        b"\n"
        b'    physics_parameters = metadata.get("physics_parameters", {})\n'
        b'    training_parameters = metadata.get("training_parameters", {})\n'
        b"    model_config = ModelConfig(\n"
        b'        N=physics_parameters.get("N", 64),\n'
        b'        gridsize=physics_parameters.get("gridsize", 1),\n'
        b'        model_type=physics_parameters.get("model_type", "pinn"),\n'
        b"    )\n"
        b"    return TrainingConfig(\n"
        b"        model=model_config,\n"
        b'        nphotons=physics_parameters.get("nphotons", 1e9),\n'
        b'        probe_trainable=physics_parameters.get("probe_trainable", False),\n'
        b"        intensity_scale_trainable="
        b'physics_parameters.get("intensity_scale_trainable", True),\n'
        b'        nll_weight=physics_parameters.get("nll_weight", 1.0),\n'
        b'        n_images=training_parameters.get("n_images", 1000),\n'
        b'        batch_size=training_parameters.get("batch_size", 32),\n'
        b'        nepochs=training_parameters.get("nepochs", 50),\n'
        b"    )\n"
    )
    assert metadata_base.count(legacy_import) == 1
    assert metadata_base.count(legacy_body) == 1
    metadata_candidate = metadata_base.replace(
        legacy_import,
        adapter_import,
    ).replace(legacy_body, delegated_body)
    assert b"ModelConfig" not in metadata_candidate
    assert adapter_source.count(b"def build_training_config_from_metadata(") == 1
    ast.parse(metadata_candidate.decode("utf-8", errors="strict"))
    ast.parse(adapter_source.decode("utf-8", errors="strict"))
    return (
        {
            removal_path: removal_base,
            metadata_path: metadata_base,
        },
        {adapter_path: adapter_source, metadata_path: metadata_candidate},
    )


def _populate_reference_index(
    repository: Path,
    *,
    base_commit: str,
    index_path: Path,
    candidate_payloads: dict[str, bytes],
    removed_paths: tuple[str, ...],
) -> dict[str, str]:
    index_environment = {"GIT_INDEX_FILE": str(index_path)}
    _run_git(
        repository,
        "read-tree",
        base_commit,
        extra_environment=index_environment,
    )
    for path in removed_paths:
        _run_git(
            repository,
            "update-index",
            "--index-info",
            input_bytes=("0 " + "0" * 40 + f"\t{path}\n").encode("ascii"),
            extra_environment=index_environment,
        )
    for path, payload in candidate_payloads.items():
        oid = _run_git(
            repository,
            "hash-object",
            "-w",
            "--stdin",
            input_bytes=payload,
        )
        _run_git(
            repository,
            "update-index",
            "--add",
            "--cacheinfo",
            "100644",
            oid.decode("ascii").strip(),
            path,
            extra_environment=index_environment,
        )
    return index_environment


def _reference_index_tree(
    repository: Path,
    *,
    base_commit: str,
    index_path: Path,
    candidate_payloads: dict[str, bytes],
    removed_paths: tuple[str, ...],
) -> str:
    index_environment = _populate_reference_index(
        repository,
        base_commit=base_commit,
        index_path=index_path,
        candidate_payloads=candidate_payloads,
        removed_paths=removed_paths,
    )
    tree = _run_git(
        repository,
        "write-tree",
        extra_environment=index_environment,
    ).decode("ascii").strip()
    index_path.unlink()
    return tree


def _build_reference_repository(
    storage_root: Path,
    *,
    implementation_lines: int,
    padding_only: bool = False,
    restored_direct_match: bool = False,
) -> dict[str, Any]:
    calibration = _calibration_module()
    task_seed = _json_record(TASK_SEED_MANIFEST)
    source_census = _json_record(SOURCE_CENSUS)
    policy = _json_record(PREEDIT_POLICY)
    source_repository = Path(task_seed["repository"]["locator"])
    task_seed_commit = task_seed["recipe"]["commit"]
    build_id = (
        f"{implementation_lines}-{'padding' if padding_only else 'semantic'}"
        f"-{'restored' if restored_direct_match else 'delegated'}"
    )
    staging = storage_root / f".{build_id}.git"
    shutil.copytree(source_repository, staging, copy_function=os.link)

    bypass_base_payloads, bypass_candidate_payloads = _reference_bypass_payloads(
        staging,
        task_seed_commit,
        restored_direct_match=restored_direct_match,
    )
    restored_absence_path = (
        "archive/root_scripts/analysis/extract_reconstructions.py"
    )
    removed_paths = () if restored_direct_match else (restored_absence_path,)
    bypass_index_path = storage_root / f".{build_id}.bypass.index"
    bypass_index_environment = _populate_reference_index(
        staging,
        base_commit=task_seed_commit,
        index_path=bypass_index_path,
        candidate_payloads=bypass_candidate_payloads,
        removed_paths=removed_paths,
    )
    bypass_numstat = _run_git(
        staging,
        "diff",
        "--cached",
        "--numstat",
        "-z",
        *calibration.PINNED_GIT_DIFF_CONTROLS,
        task_seed_commit,
        "--",
        extra_environment=bypass_index_environment,
    )
    bypass_index_path.unlink()
    bypass_rows = calibration.parse_numstat_z(bypass_numstat)
    expected_bypass_paths = set(REFERENCE_BYPASS_CLUSTER_BY_PATH)
    if restored_direct_match:
        expected_bypass_paths.remove(restored_absence_path)
    assert {row.new_path for row in bypass_rows} == expected_bypass_paths
    bypass_implementation_additions = sum(row.additions for row in bypass_rows)
    extension_lines = implementation_lines - bypass_implementation_additions
    assert extension_lines > 0
    quotient, remainder = divmod(
        extension_lines,
        len(REFERENCE_EXTENSION_CLUSTER_BY_PATH),
    )
    base_payloads: dict[str, bytes] = copy.deepcopy(bypass_base_payloads)
    candidate_payloads: dict[str, bytes] = copy.deepcopy(
        bypass_candidate_payloads
    )
    for index, (path, cluster_id) in enumerate(
        sorted(REFERENCE_EXTENSION_CLUSTER_BY_PATH.items())
    ):
        additions = quotient + (1 if index < remainder else 0)
        if path == REFERENCE_REGISTRY_PATH:
            registry_base = _run_git(
                staging,
                "show",
                f"{task_seed_commit}:{REFERENCE_REGISTRY_PATH}",
            )
            base_payloads[path] = registry_base
            candidate = _reference_registry_source(registry_base, additions)
        else:
            candidate = _reference_module_source(
                path,
                cluster_id,
                additions,
                padding_only=padding_only,
            )
        candidate_payloads[path] = candidate
    reference_canary = (
        "es-f1-reference-canary.v1:"
        + hashlib.sha256(
            (
                task_seed_commit
                + "\0"
                + _raw_sha256(GOVERNING_PLAN)
            ).encode("ascii")
        ).hexdigest()
    )
    documentation_payload = (reference_canary + "\n").encode("ascii")
    candidate_payloads[REFERENCE_DOCUMENTATION_PATH] = documentation_payload

    reference_tree = _reference_index_tree(
        staging,
        base_commit=task_seed_commit,
        index_path=storage_root / f".{build_id}.index",
        candidate_payloads=candidate_payloads,
        removed_paths=removed_paths,
    )
    commit_environment = {
        "GIT_AUTHOR_NAME": "ES F1 reference calibration",
        "GIT_AUTHOR_EMAIL": "es-f1-reference@invalid",
        "GIT_AUTHOR_DATE": "2026-08-05T12:00:00-0700",
        "GIT_COMMITTER_NAME": "ES F1 reference calibration",
        "GIT_COMMITTER_EMAIL": "es-f1-reference@invalid",
        "GIT_COMMITTER_DATE": "2026-08-05T12:00:00-0700",
    }
    reference_commit = _run_git(
        staging,
        "commit-tree",
        reference_tree,
        "-p",
        task_seed_commit,
        input_bytes=(
            "ES F1 deterministic reference product\n\n"
            f"Implementation-Lines: {implementation_lines}\n"
            f"Padding-Control: {'yes' if padding_only else 'no'}\n"
            f"Restored-Direct-Match: {'yes' if restored_direct_match else 'no'}\n"
        ).encode("utf-8"),
        extra_environment=commit_environment,
    ).decode("ascii").strip()
    _run_git(staging, "update-ref", REFERENCE_REF, reference_commit)
    _run_git(staging, "update-ref", "-d", "refs/heads/task-seed")
    _run_git(staging, "symbolic-ref", "HEAD", REFERENCE_REF)

    relative_path = f"git-sha1/{reference_commit}"
    repository = storage_root / relative_path
    repository.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(repository)
    patch_argv = [
        "/usr/bin/git",
        "-C",
        str(repository),
        "diff",
        "--patch",
        "--binary",
        "--full-index",
        "--no-color",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        *calibration.PINNED_GIT_DIFF_CONTROLS,
        task_seed_commit,
        reference_commit,
        "--",
    ]
    canonical_patch = subprocess.run(
        patch_argv,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    ).stdout
    assert canonical_patch

    eligible_base_tree = _strict_text_tree_payloads(
        repository,
        task_seed_commit,
    )
    eligible_candidate_tree = _strict_text_tree_payloads(
        repository,
        reference_tree,
    )
    new_extension_paths = set(REFERENCE_EXTENSION_CLUSTER_BY_PATH) - {
        REFERENCE_REGISTRY_PATH
    }
    assert not new_extension_paths & set(eligible_base_tree)
    assert new_extension_paths <= set(eligible_candidate_tree)
    assert REFERENCE_REGISTRY_PATH in (
        set(eligible_base_tree) & set(eligible_candidate_tree)
    )
    assert eligible_base_tree[REFERENCE_REGISTRY_PATH] != (
        eligible_candidate_tree[REFERENCE_REGISTRY_PATH]
    )
    assert "ptycho/metadata.py" in (
        set(eligible_base_tree) & set(eligible_candidate_tree)
    )
    if restored_direct_match:
        assert eligible_candidate_tree[restored_absence_path] == (
            eligible_base_tree[restored_absence_path]
        )
    else:
        assert restored_absence_path in (
            set(eligible_base_tree) - set(eligible_candidate_tree)
        )
    assert REFERENCE_DOCUMENTATION_PATH not in eligible_base_tree
    assert REFERENCE_DOCUMENTATION_PATH in eligible_candidate_tree
    expected_changed_paths = {
        *REFERENCE_CLUSTER_BY_PATH,
        REFERENCE_DOCUMENTATION_PATH,
    }
    if restored_direct_match:
        expected_changed_paths.remove(restored_absence_path)
    changed_paths = {
        path
        for path in set(eligible_base_tree) | set(eligible_candidate_tree)
        if eligible_base_tree.get(path) != eligible_candidate_tree.get(path)
    }
    assert changed_paths == expected_changed_paths

    metric_base = storage_root / f".{build_id}.metric-base"
    metric_candidate = storage_root / f".{build_id}.metric-candidate"
    metric_base.mkdir()
    metric_candidate.mkdir()
    for path, leaf in eligible_base_tree.items():
        _write_bytes(metric_base, path, leaf["payload"])
        (metric_base / path).chmod(leaf["mode"])
    for path, leaf in eligible_candidate_tree.items():
        _write_bytes(metric_candidate, path, leaf["payload"])
        (metric_candidate / path).chmod(leaf["mode"])
    leaves = {row["path"]: row for row in source_census["leaf_rows"]}
    path_policies = []
    for path in sorted(set(eligible_base_tree) | set(eligible_candidate_tree)):
        path_changed = eligible_base_tree.get(path) != eligible_candidate_tree.get(
            path
        )
        if path in REFERENCE_CLUSTER_BY_PATH and path_changed:
            classification = "production_python"
            responsibility_ids = (
                REFERENCE_NEW_RESPONSIBILITY_IDS_BY_PATH[path]
                if path in REFERENCE_NEW_RESPONSIBILITY_IDS_BY_PATH
                else tuple(sorted(leaves[path]["responsibility_ids"]))
            )
        elif path == REFERENCE_DOCUMENTATION_PATH:
            classification = "documentation"
            responsibility_ids = ()
        else:
            assert path in eligible_base_tree and path in eligible_candidate_tree
            assert eligible_base_tree[path] == eligible_candidate_tree[path]
            classification = "benchmark_task_seed_asset"
            responsibility_ids = ()
        path_policies.append(
            calibration.MetricPathPolicy(
                path=path,
                classification=classification,
                responsibility_ids=responsibility_ids,
            )
        )
    measurement = calibration.measure_implementation_delta(
        base_root=metric_base,
        candidate_root=metric_candidate,
        path_policies=path_policies,
        allowed_responsibility_ids=frozenset(
            row["responsibility_id"] for row in policy["responsibilities"]
        ),
        git_contract=_git_contract(
            calibration,
            policy_sha256=REFERENCE_GIT_POLICY_SHA256,
        ),
    )
    shutil.rmtree(metric_base)
    shutil.rmtree(metric_candidate)
    metric = _serialize_implementation_delta(measurement)
    assert metric["implementation_additions"] == implementation_lines

    task_package = importlib.import_module("scripts.experiments.es.task_package")
    object_rows = _run_git(
        repository,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype)",
    ).splitlines()
    reachable = {
        line.split(b" ", 1)[0]
        for line in _run_git(repository, "rev-list", "--objects", "--all").splitlines()
    }
    all_ids = {line.split(b" ", 1)[0] for line in object_rows}
    assert all_ids == reachable
    return {
        "storage_root": storage_root,
        "relative_path": relative_path,
        "repository": repository,
        "reference_commit": reference_commit,
        "reference_tree": reference_tree,
        "object_count": len(object_rows),
        "repository_snapshot_sha256": task_package.directory_snapshot_digest(
            repository
        ),
        "canonical_patch": canonical_patch,
        "patch_argv": patch_argv,
        "metric": metric,
        "base_payloads": base_payloads,
        "candidate_payloads": candidate_payloads,
        "eligible_base_tree": eligible_base_tree,
        "eligible_candidate_tree": eligible_candidate_tree,
        "reference_canary": reference_canary,
        "reference_chain_paths": REFERENCE_CHAIN_PATHS,
        "padding_only": padding_only,
        "restored_direct_match": restored_direct_match,
    }


@pytest.fixture(scope="module")
def reference_repository_factory():
    task_seed = _json_record(TASK_SEED_MANIFEST)
    source_repository = Path(task_seed["repository"]["locator"])
    storage_root = Path(
        tempfile.mkdtemp(
            prefix=".es-f1-reference-products-test.",
            dir=source_repository.parents[2],
        )
    )
    cache: dict[tuple[int, bool, bool], dict[str, Any]] = {}

    def build(
        implementation_lines: int = 5_000,
        *,
        padding_only: bool = False,
        restored_direct_match: bool = False,
    ) -> dict[str, Any]:
        key = (implementation_lines, padding_only, restored_direct_match)
        if key not in cache:
            cache[key] = _build_reference_repository(
                storage_root,
                implementation_lines=implementation_lines,
                padding_only=padding_only,
                restored_direct_match=restored_direct_match,
            )
        return cache[key]

    try:
        yield build
    finally:
        shutil.rmtree(storage_root)


def _materialize_reference_workspace(
    repository: dict[str, Any],
    name: str,
) -> Path:
    workspace = repository["storage_root"] / "workspaces" / name
    workspace.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        (
            "/usr/bin/git",
            "clone",
            "--quiet",
            "--no-checkout",
            str(repository["repository"]),
            str(workspace),
        ),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )
    _run_git(workspace, "checkout", "--quiet", "--detach", repository["reference_commit"])
    _run_git(workspace, "remote", "remove", "origin")
    assert _run_git(workspace, "status", "--porcelain=v1") == b""
    return workspace


def _git_object_ids(repository: Path, ref: str) -> tuple[str, ...]:
    object_ids = {
        line.split(b" ", 1)[0].decode("ascii")
        for line in _run_git(
            repository,
            "rev-list",
            "--objects",
            ref,
        ).splitlines()
    }
    return tuple(sorted(object_ids))


def _git_typed_object_rows(
    repository: Path,
    object_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not object_ids:
        return []
    output = _run_git(
        repository,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    )
    rows = []
    for line in output.splitlines():
        object_id, object_type, raw_byte_count = line.decode("ascii").split(" ")
        rows.append(
            {
                "object_id": object_id,
                "object_type": object_type,
                "byte_count": int(raw_byte_count),
            }
        )
    assert tuple(row["object_id"] for row in rows) == object_ids
    return rows


def _git_lookup_rows(
    repository: Path,
    object_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows = []
    for object_id in object_ids:
        completed = subprocess.run(
            (
                "/usr/bin/git",
                "-C",
                str(repository),
                "cat-file",
                "-e",
                object_id,
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
        rows.append(
            {
                "object_id": object_id,
                "return_code": completed.returncode,
                "stdout": completed.stdout.decode("utf-8", errors="strict"),
                "stderr_sha256": (
                    "sha256:" + hashlib.sha256(completed.stderr).hexdigest()
                ),
            }
        )
    return rows


def _reference_packet_payloads(calibration) -> tuple[bytes, bytes]:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    include = (
        "task_spec",
        "validated_result",
        "workspace_delta",
        "check_results",
        "declared_artifacts",
        "failure_evidence",
    )
    task_spec = {
        "inputs": {
            "task": "task",
            "check_contract": "checks",
            "model": "gpt-5.5",
            "effort": "high",
        }
    }
    empty_delta = {
        "changed_files": [],
        "deleted_files": [],
        "untracked_files": [],
        "normalized_diff": {
            "entries": [],
            "catalog_digest": "sha256:" + "0" * 64,
            "truncated": False,
            "omitted_bytes": 0,
            "omitted_entries": 0,
        },
        "declared_artifacts": [],
    }
    common = {
        "opaque_label": "opaque-" + "1" * 64,
        "observation_include": include,
        "sealed_identity_values": (
            "DIRECT",
            "DESIGN_QA",
            "PRODUCT_QA",
            "RICH",
        ),
        "max_item_bytes": 65_536,
        "max_packet_bytes": 262_144,
    }
    completed = packets.build_trial_evaluation_packet(
        **common,
        observations={
            "task_spec": task_spec,
            "validated_result": True,
            "workspace_delta": empty_delta,
            "check_results": [],
            "declared_artifacts": [],
        },
    )
    failed = packets.build_trial_evaluation_packet(
        **common,
        observations={
            "task_spec": task_spec,
            "failure_evidence": {
                "code": "run_ref_child_launch_failed",
                "phase": "launch",
                "retryable": False,
                "secondary_causes": [],
            },
        },
    )
    assert packets.validate_trial_evaluation_packet(completed) == completed
    assert packets.validate_trial_evaluation_packet(failed) == failed
    return (
        calibration.canonical_json_bytes(completed),
        calibration.canonical_json_bytes(failed),
    )


def _reference_surface_payloads(
    calibration,
    task_seed_manifest,
) -> list[dict[str, Any]]:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    metering = importlib.import_module("scripts.experiments.es.metering")
    provider_boundary = importlib.import_module(
        "scripts.experiments.es.provider_boundary"
    )
    assert metering.normalize_codex_argv(REFERENCE_LOGICAL_METERED_ARGV) == (
        REFERENCE_LOGICAL_METERED_ARGV
    )
    logical_environment = provider_boundary.boundary_environment(
        shim_dir=Path("/run/orc-es-f1/provider-shim"),
        manifest=provider_boundary.ManifestPublication(
            Path("/run/orc-es-f1/provider-boundary.json"),
            "sha256:" + "3" * 64,
        ),
        inherited_path="/usr/local/bin:/usr/bin:/bin",
    )
    completed_packet, failed_packet = _reference_packet_payloads(calibration)
    rows = [
        {
            "surface_id": f"visible_task_asset:{asset.target_path}",
            "surface_class": "visible_task_asset",
            "logical_path": asset.target_path,
            "payload": _run_git(
                task_seed_manifest.locator,
                "show",
                f"{task_seed_manifest.commit}:{asset.target_path}",
            ),
        }
        for asset in task_seed_manifest.visible_assets
    ]
    rows.extend(
        (
            {
                "surface_id": "treatment_prompt_authority",
                "surface_class": "treatment_prompt",
                "logical_path": _binding_path(REFERENCE_TREATMENT_PROMPT),
                "payload": REFERENCE_TREATMENT_PROMPT.read_bytes(),
            },
            {
                "surface_id": "prompt_extern_authority",
                "surface_class": "prompt_externs",
                "logical_path": _binding_path(REFERENCE_PROMPT_EXTERNS),
                "payload": REFERENCE_PROMPT_EXTERNS.read_bytes(),
            },
            {
                "surface_id": "trial_evaluator_instruction",
                "surface_class": "evaluator_instruction",
                "logical_path": evaluation.TRIAL_EVALUATOR_INSTRUCTION_ID,
                "payload": evaluation.TRIAL_EVALUATOR_INSTRUCTION.encode("utf-8"),
            },
            {
                "surface_id": "trial_evaluator_rubric",
                "surface_class": "evaluator_rubric",
                "logical_path": _binding_path(REFERENCE_EVALUATOR_RUBRIC),
                "payload": REFERENCE_EVALUATOR_RUBRIC.read_bytes(),
            },
            {
                "surface_id": "logical_outer_argv",
                "surface_class": "provider_argv",
                "logical_path": "task3a://provider/outer-argv",
                "payload": calibration.canonical_json_bytes(
                    list(REFERENCE_LOGICAL_OUTER_ARGV)
                ),
            },
            {
                "surface_id": "logical_metered_argv",
                "surface_class": "provider_argv",
                "logical_path": "task3a://provider/metered-argv",
                "payload": calibration.canonical_json_bytes(
                    list(REFERENCE_LOGICAL_METERED_ARGV)
                ),
            },
            {
                "surface_id": "logical_provider_environment",
                "surface_class": "provider_environment",
                "logical_path": "task3a://provider/environment",
                "payload": calibration.canonical_json_bytes(logical_environment),
            },
            {
                "surface_id": "logical_completed_packet",
                "surface_class": "provider_packet",
                "logical_path": "task3a://provider/completed-packet",
                "payload": completed_packet,
            },
            {
                "surface_id": "logical_failed_packet",
                "surface_class": "provider_packet",
                "logical_path": "task3a://provider/failed-packet",
                "payload": failed_packet,
            },
        )
    )
    assert len({row["surface_id"] for row in rows}) == len(rows)
    return rows


def _build_reference_no_delivery_report(
    repository: dict[str, Any],
    task_seed: dict[str, Any],
) -> dict[str, Any]:
    cached = repository.get("no_delivery_report")
    if cached is not None:
        return copy.deepcopy(cached)
    calibration = _calibration_module()
    task_package = importlib.import_module("scripts.experiments.es.task_package")
    source = importlib.import_module("orchestrator.workflow.run_ref.source")
    task_seed_manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST)
    task_seed_result = task_package.verify_task_seed(
        task_seed_manifest.locator,
        task_seed_manifest,
    )
    assert task_seed_result.unreachable_object_count == 0

    task_seed_object_ids = _git_object_ids(
        task_seed_manifest.locator,
        "refs/heads/task-seed",
    )
    task_seed_object_rows = _git_typed_object_rows(
        task_seed_manifest.locator,
        task_seed_object_ids,
    )
    reference_object_ids = _git_object_ids(
        repository["repository"],
        REFERENCE_REF,
    )
    reference_only_ids = tuple(
        sorted(set(reference_object_ids) - set(task_seed_object_ids))
    )
    reference_only_objects = _git_typed_object_rows(
        repository["repository"],
        reference_only_ids,
    )
    assert reference_only_objects
    assert {row["object_type"] for row in reference_only_objects} <= {
        "blob",
        "commit",
        "tree",
    }

    fsck_argv = (
        "/usr/bin/git",
        "-C",
        str(task_seed_manifest.locator),
        "fsck",
        "--full",
        "--strict",
        "--no-reflogs",
        "--unreachable",
    )
    fsck = subprocess.run(
        fsck_argv,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )
    all_task_seed_rows = _run_git(
        task_seed_manifest.locator,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
    ).splitlines()
    all_task_seed_ids = {
        row.split(b" ", 1)[0].decode("ascii") for row in all_task_seed_rows
    }
    unreachable_ids = all_task_seed_ids - set(task_seed_object_ids)
    history_rows = []
    for raw in _run_git(
        task_seed_manifest.locator,
        "rev-list",
        "--parents",
        "--topo-order",
        "--all",
    ).splitlines():
        values = raw.decode("ascii").split(" ")
        history_rows.append({"commit": values[0], "parents": values[1:]})
    tree_rows = [
        {
            "commit": row["commit"],
            "tree": _run_git(
                task_seed_manifest.locator,
                "rev-parse",
                f"{row['commit']}^{{tree}}",
            ).decode("ascii").strip(),
        }
        for row in history_rows
    ]
    ref_rows = [
        {"refname": values[0], "object_id": values[1]}
        for values in (
            line.decode("ascii").split(" ")
            for line in _run_git(
                task_seed_manifest.locator,
                "for-each-ref",
                "--format=%(refname) %(objectname)",
            ).splitlines()
        )
    ]
    visible_asset_rows = [
        {
            "source_path": row.source_path,
            "target_path": row.target_path,
            "mode": row.mode,
            "object_type": row.object_type,
            "object_id": row.oid,
            "byte_count": row.byte_count,
            "sha256": row.digest,
        }
        for row in task_seed_manifest.visible_assets
    ]
    task_seed_closure = {
        "repository_locator": str(task_seed_manifest.locator),
        "head_ref": _run_git(
            task_seed_manifest.locator,
            "symbolic-ref",
            "HEAD",
        ).decode("ascii").strip(),
        "ref_rows": ref_rows,
        "history_rows": history_rows,
        "tree_rows": tree_rows,
        "reachable_object_count": len(task_seed_object_rows),
        "reachable_objects_sha256": (
            "sha256:"
            + hashlib.sha256(
                calibration.canonical_json_bytes(task_seed_object_rows)
            ).hexdigest()
        ),
        "unreachable_object_count": len(unreachable_ids),
        "fsck": {
            "argv": list(fsck_argv),
            "return_code": fsck.returncode,
            "stdout_sha256": (
                "sha256:" + hashlib.sha256(fsck.stdout).hexdigest()
            ),
            "stderr_sha256": (
                "sha256:" + hashlib.sha256(fsck.stderr).hexdigest()
            ),
        },
        "visible_asset_rows": visible_asset_rows,
    }
    task_seed_lookup_rows = _git_lookup_rows(
        task_seed_manifest.locator,
        reference_only_ids,
    )

    provider_root = (
        repository["storage_root"]
        / "no-delivery-provider"
        / repository["reference_commit"]
    )
    destination = provider_root / "workspace"
    run_ref_root = provider_root / "run-ref"
    assert not destination.exists() and not destination.is_symlink()
    source_request = source.SourceRequest(
        locator=str(task_seed_manifest.locator),
        commit=task_seed_manifest.commit,
    )
    canonical_request = source.canonical_source_request(source_request)
    materialized = source.materialize_source(
        source_request,
        run_ref_root=run_ref_root,
        workspace=destination,
    )
    symbolic_ref = subprocess.run(
        ("/usr/bin/git", "-C", str(destination), "symbolic-ref", "-q", "HEAD"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )
    provider_workspace = {
        "destination": str(destination),
        "destination_initial_state": "absent",
        "run_ref_root": str(run_ref_root),
        "source_request": canonical_request,
        "normalized_locator": materialized.normalized_locator,
        "resolved_commit": materialized.resolved_commit_sha,
        "verified_git_tree": materialized.verified_git_tree.value,
        "source_tree_manifest_sha256": materialized.source_tree_manifest.digest,
        "post_setup_tree_manifest_sha256": (
            materialized.post_setup_tree_manifest.digest
        ),
        "head_commit": _run_git(destination, "rev-parse", "HEAD")
        .decode("ascii")
        .strip(),
        "head_tree": _run_git(destination, "rev-parse", "HEAD^{tree}")
        .decode("ascii")
        .strip(),
        "symbolic_ref_return_code": symbolic_ref.returncode,
        "status_porcelain": _run_git(
            destination,
            "status",
            "--porcelain=v1",
        ).decode("utf-8", errors="strict"),
        "reference_object_lookup_rows": _git_lookup_rows(
            destination,
            reference_only_ids,
        ),
    }

    reference_blob_rows = []
    forbidden_payloads: list[tuple[str, bytes]] = []
    for row in reference_only_objects:
        if row["object_type"] != "blob":
            continue
        payload = _run_git(
            repository["repository"],
            "cat-file",
            "blob",
            row["object_id"],
        )
        assert payload
        reference_blob_rows.append(
            {
                "object_id": row["object_id"],
                "byte_count": len(payload),
                "content_sha256": (
                    "sha256:" + hashlib.sha256(payload).hexdigest()
                ),
            }
        )
        forbidden_payloads.append(
            (f"reference_source_blob:{row['object_id']}", payload)
        )
    canonical_patch_sha256 = (
        "sha256:" + hashlib.sha256(repository["canonical_patch"]).hexdigest()
    )
    measured_count_ascii = str(repository["metric"]["implementation_additions"])
    forbidden_domain = {
        "reference_locator": str(repository["repository"]),
        "reference_relative_path": repository["relative_path"],
        "reference_ref": REFERENCE_REF,
        "reference_commit": repository["reference_commit"],
        "reference_tree": repository["reference_tree"],
        "reference_object_ids": list(reference_only_ids),
        "reference_source_blobs": reference_blob_rows,
        "canonical_patch": {
            "member_id": "canonical_patch",
            "byte_count": len(repository["canonical_patch"]),
            "sha256": canonical_patch_sha256,
        },
        "reference_manifest": {
            "schema_version": "es_f1_reference_product.v1",
            "path": _binding_path(REFERENCE_RECORD),
        },
        "reference_canary": {
            "path": REFERENCE_DOCUMENTATION_PATH,
            "value": repository["reference_canary"],
        },
        "measured_count": {
            "metric_version": repository["metric"]["metric_version"],
            "value": repository["metric"]["implementation_additions"],
            "ascii": measured_count_ascii,
        },
    }
    for name in (
        "reference_locator",
        "reference_relative_path",
        "reference_ref",
        "reference_commit",
        "reference_tree",
    ):
        forbidden_payloads.append(
            (name, str(forbidden_domain[name]).encode("utf-8"))
        )
    forbidden_payloads.extend(
        (f"reference_object:{object_id}", object_id.encode("ascii"))
        for object_id in reference_only_ids
    )
    forbidden_payloads.extend(
        (
            ("canonical_patch", repository["canonical_patch"]),
            (
                "reference_manifest_schema",
                forbidden_domain["reference_manifest"]["schema_version"].encode(
                    "ascii"
                ),
            ),
            (
                "reference_manifest_path",
                forbidden_domain["reference_manifest"]["path"].encode("utf-8"),
            ),
            ("reference_canary", repository["reference_canary"].encode("ascii")),
            ("measured_count", measured_count_ascii.encode("ascii")),
        )
    )
    surface_rows = []
    all_matches = []
    for surface in _reference_surface_payloads(calibration, task_seed_manifest):
        payload = surface.pop("payload")
        matches = [
            forbidden_id
            for forbidden_id, forbidden_payload in forbidden_payloads
            if forbidden_payload in payload
        ]
        row = {
            **surface,
            "byte_count": len(payload),
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "matches": matches,
        }
        surface_rows.append(row)
        all_matches.extend(
            {"surface_id": row["surface_id"], "forbidden_id": forbidden_id}
            for forbidden_id in matches
        )

    controller_refs = [
        {"refname": values[0], "object_id": values[1]}
        for values in (
            line.decode("ascii").split(" ")
            for line in _run_git(
                repository["repository"],
                "for-each-ref",
                "--format=%(refname) %(objectname)",
            ).splitlines()
        )
    ]
    escape_candidates = (
        repository["repository"] / "objects" / "info" / "alternates",
        repository["repository"] / "info" / "grafts",
        repository["repository"] / "shallow",
        repository["repository"] / "refs" / "replace",
    )
    controller_resolution = {
        "repository_locator": str(repository["repository"]),
        "head_ref": _run_git(
            repository["repository"],
            "symbolic-ref",
            "HEAD",
        ).decode("ascii").strip(),
        "ref_rows": controller_refs,
        "resolved_commit": _run_git(
            repository["repository"],
            "rev-parse",
            REFERENCE_REF,
        ).decode("ascii").strip(),
        "resolved_tree": _run_git(
            repository["repository"],
            "rev-parse",
            f"{REFERENCE_REF}^{{tree}}",
        ).decode("ascii").strip(),
        "remote_rows": _run_git(
            repository["repository"],
            "remote",
            "-v",
        ).decode("utf-8").splitlines(),
        "escape_paths": [
            path.relative_to(repository["repository"]).as_posix()
            for path in escape_candidates
            if os.path.lexists(path)
        ],
        "reference_object_rows": copy.deepcopy(reference_only_objects),
    }
    report = {
        "schema_version": "es_f1_reference_no_delivery.v1",
        "bindings": {
            "task_seed_manifest_sha256": _raw_sha256(TASK_SEED_MANIFEST),
            "task_seed_repository_snapshot_sha256": task_seed[
                "repository"
            ]["repository_snapshot_sha256"],
            "reference_repository_snapshot_sha256": repository[
                "repository_snapshot_sha256"
            ],
            "reference_ref": REFERENCE_REF,
            "reference_commit": repository["reference_commit"],
            "reference_tree": repository["reference_tree"],
            "canonical_patch_member_id": "canonical_patch",
            "canonical_patch_sha256": canonical_patch_sha256,
        },
        "task_seed_closure": task_seed_closure,
        "reference_only_objects": reference_only_objects,
        "task_seed_lookup_rows": task_seed_lookup_rows,
        "surface_scan": {
            "scope": {
                "surface_set": "task3a_logical_prelaunch.v1",
                "final_prompt_manifest": "not_yet_materialized",
                "final_environment_lock": "not_yet_materialized",
                "task5_replay_required": True,
            },
            "forbidden_domain": forbidden_domain,
            "surface_rows": surface_rows,
            "matches": all_matches,
        },
        "provider_workspace": provider_workspace,
        "controller_resolution": controller_resolution,
    }
    repository["no_delivery_report"] = copy.deepcopy(report)
    return report


def _sealed_reference_record(
    calibration,
    record: dict[str, Any],
) -> dict[str, Any]:
    body = copy.deepcopy(record)
    body.pop("record_sha256", None)
    return calibration.seal_record(body)


def _load_reference_product(
    calibration,
    tmp_path: Path,
    record: dict[str, Any],
    *,
    name: str = "reference-product.json",
):
    path = tmp_path / name
    path.write_bytes(calibration.canonical_json_bytes(record))
    return calibration.load_reference_product(
        path,
        schema_path=REFERENCE_SCHEMA,
        expected_record_sha256=record["record_sha256"],
    )


def _desired_state_rows(
    boundary,
    contract,
    *,
    repository: Path,
    target_tree: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec, witness in zip(
        contract.desired_specs,
        contract.witnesses,
        strict=True,
    ):
        observation = copy.deepcopy(spec.expected_result)
        row: dict[str, Any] = {
            "proof_id": spec.proof_id,
            "ordinal": spec.ordinal,
            "selector_id": spec.selector_id,
            "witness_id": spec.witness_id,
            "consumer_id": spec.consumer_id,
            "proof_kind": spec.proof_kind,
            "witness_kind": witness.witness_kind,
            "target_tree": target_tree,
            "target_path": witness.consumer_path,
            "target_blob_id": (
                None
                if spec.proof_kind == "reference_absence"
                else _run_git(
                    repository,
                    "rev-parse",
                    f"{target_tree}:{witness.consumer_path}",
                ).decode("ascii").strip()
            ),
            "mechanically_observed": True,
            "observation": observation,
            "observation_sha256": (
                "sha256:"
                + hashlib.sha256(boundary.canonical_json_bytes(observation)).hexdigest()
            ),
            "passed": True,
        }
        if witness.witness_kind in {
            "pytest_runtime",
            "controller_pytest_runtime",
            "runtime_probe",
        }:
            row["source_event"] = copy.deepcopy(observation)
        rows.append(row)
    return rows


def _reference_bypass_reports(
    calibration,
    repository: dict[str, Any],
    desired_state_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    source_census_module = importlib.import_module(
        "scripts.experiments.es.source_census"
    )
    cached = repository.get("bypass_discovery_and_classification")
    if cached is None:
        discovery_input = _json_record(TASK0_EVIDENCE / "preedit-discovery-input.json")
        raw_inventory = _run_git(
            repository["repository"],
            "ls-tree",
            "-rz",
            "-r",
            "--full-tree",
            repository["reference_commit"],
        )
        inventory_rows = [row for row in raw_inventory.split(b"\0") if row]
        discovery_input["projection"] = {
            "repository": str(repository["repository"].resolve()),
            "commit": repository["reference_commit"],
            "tree": repository["reference_tree"],
            "inventory_sha256": "sha256:"
            + hashlib.sha256(raw_inventory).hexdigest(),
            "leaf_count": len(inventory_rows),
        }
        discovery_output = source_census_module.discover_source(
            discovery_input,
            discovery_input_sha256="sha256:"
            + hashlib.sha256(
                source_census_module.canonical_json_bytes(discovery_input)
            ).hexdigest(),
        )
        classification = evaluator.classify_task0_bypass_discovery(
            discovery_input=discovery_input,
            discovery_output=discovery_output,
            verified_construction_route=evaluator.F1_PUBLIC_CONSTRUCTION_ROUTE,
        )
        cached = {
            "discovery_input": discovery_input,
            "discovery_output": discovery_output,
            "classification": classification,
        }
        repository["bypass_discovery_and_classification"] = copy.deepcopy(cached)
    cached = copy.deepcopy(cached)
    source_census = _json_record(SOURCE_CENSUS)
    consumers = {
        row["consumer_id"]: row for row in source_census["consumer_rows"]
    }
    inventory = source_census["legacy_bypass_inventory"]
    legacy_report = {
        "bindings": copy.deepcopy(cached["classification"]["authority_bindings"]),
        "legacy_inventory_partition": {
            status + "_consumer_ids": [
                consumer_id
                for consumer_id in inventory
                if consumers[consumer_id]["coverage_status"] == status
            ]
            for status in ("required", "inherited", "open")
        },
        "novel_matches": copy.deepcopy(
            cached["classification"]["novel_direct_matches"]
        ),
        "schema_version": "es-f1-legacy-bypass-report.v1",
        "selected_required_results": copy.deepcopy(desired_state_rows),
    }
    derived_observation = evaluator._derive_task0_bypass_observation(legacy_report)
    discovery_report = {
        "schema_version": "es_f1_reference_bypass_discovery.v1",
        "candidate_tree": repository["reference_tree"],
        "discovery_input": cached["discovery_input"],
        "discovery_output": cached["discovery_output"],
    }
    classification_report = {
        "schema_version": "es_f1_reference_bypass_classification.v1",
        "candidate_tree": repository["reference_tree"],
        "authority_bindings": copy.deepcopy(
            cached["classification"]["authority_bindings"]
        ),
        "classification": cached["classification"],
        "legacy_report": legacy_report,
        "derived_observation": derived_observation,
    }
    bypass_oracle = {
        "report_member_ids": {
            "discovery": "bypass_discovery",
            "classification": "bypass_classification",
        },
        "candidate_tree": repository["reference_tree"],
        "discovery_candidate_set_sha256": cached["discovery_output"][
            "candidate_set_sha256"
        ],
        "authority_bindings": copy.deepcopy(
            cached["classification"]["authority_bindings"]
        ),
        "classification_sha256": "sha256:"
        + hashlib.sha256(
            calibration.canonical_json_bytes(cached["classification"])
        ).hexdigest(),
        "legacy_report_sha256": "sha256:"
        + hashlib.sha256(
            calibration.canonical_json_bytes(legacy_report)
        ).hexdigest(),
        "desired_state_results_sha256": "sha256:"
        + hashlib.sha256(
            calibration.canonical_json_bytes(desired_state_rows)
        ).hexdigest(),
        "derived_observation": derived_observation,
    }
    return discovery_report, classification_report, bypass_oracle


def _visible_check_result(
    visible_check_manifest: dict[str, Any],
    *,
    reference_tree: str,
) -> dict[str, Any]:
    runner = visible_check_manifest["runner"]
    invocations_by_id = {
        row["id"]: row for row in visible_check_manifest["invocations"]
    }
    copy_digest = "sha256:" + hashlib.sha256(
        f"reference-tree:{reference_tree}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "es-f1-visible-check-result.v2",
        "copy_digest_before": copy_digest,
        "copy_digest_after": copy_digest,
        "invocations": [
            {
                "argv": [
                    runner["python_executable"],
                    *runner["argv_prefix"],
                    *invocations_by_id[invocation_id]["selectors"],
                ],
                "exit_code": 0,
                "invocation_id": invocation_id,
                "stderr_sha256": "sha256:"
                + hashlib.sha256(
                    f"{reference_tree}:{invocation_id}:stderr".encode("utf-8")
                ).hexdigest(),
                "stdout_sha256": "sha256:"
                + hashlib.sha256(
                    f"{reference_tree}:{invocation_id}:stdout".encode("utf-8")
                ).hexdigest(),
            }
            for invocation_id in visible_check_manifest["invocation_order"]
        ],
    }


def _registry_signature_report(
    fixture_manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "es-f1-registry-signature-probe.v1",
        "registry_baseline": copy.deepcopy(fixture_manifest["registry_baseline"]),
        "loaded_forbidden_modules": [],
        "outside_project_origin_rows": [],
        "cache_artifacts": [],
    }


def _artifact_fixture_verification(
    fixture_manifest: dict[str, Any],
    architectures: list[str],
    *,
    witness_identity: str,
) -> dict[str, Any]:
    identities = {
        row["architecture"]: row["implementation_identity"]
        for row in fixture_manifest["registry_baseline"]
    }
    identities[REFERENCE_WITNESS_ID] = witness_identity
    artifact_eras: list[dict[str, Any]] = []
    for era in fixture_manifest["artifact_eras"]:
        applicable = {
            REFERENCE_WITNESS_ID if value == "$candidate_witness" else value
            for value in era["applicable_architecture_ids"]
        }
        rejected = {
            REFERENCE_WITNESS_ID if value == "$candidate_witness" else value
            for value in era["rejected_architecture_ids"]
        }
        assert applicable | rejected == set(architectures)
        assert not applicable & rejected
        artifact_eras.append(
            {
                "era_id": era["era_id"],
                "architecture_results": [
                    {
                        "architecture_id": architecture_id,
                        "diagnostic": (
                            None
                            if architecture_id in applicable
                            else "UNSUPPORTED_ARTIFACT_ARCHITECTURE"
                        ),
                        "implementation_identity": (
                            identities[architecture_id]
                            if architecture_id in applicable
                            else None
                        ),
                        "module_returned": architecture_id in applicable,
                        "strict_load": architecture_id in applicable,
                    }
                    for architecture_id in architectures
                ],
            }
        )
    return {
        "schema_version": "es-f1-artifact-fixture-verification.v2",
        "artifact_eras": artifact_eras,
        "loaded_forbidden_modules": [],
        "outside_project_origin_rows": [],
        "cache_artifacts": [],
    }


def _reference_architecture_declaration(
    architecture_id: str,
    *,
    witness: bool = False,
) -> dict[str, Any]:
    return {
        "construction_route": (
            "ptycho_torch.generators.registry.resolve_generator"
        ),
        "persisted_rebuild_route": (
            "ptycho_torch.application_factory.build_ptychopinn_application"
        ),
        "public_id": architecture_id,
        "structural_fields": [
            {
                "alternate_value": (
                    3 if witness else f"{architecture_id}-alternate"
                ),
                "baseline_value": 2 if witness else architecture_id,
                "name": "es_f1_depth" if witness else "architecture",
            }
        ],
    }


def _candidate_extension_evidence(
    visible_contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "architecture_decision_path": "README.md",
        "builtin_architectures": [
            _reference_architecture_declaration(architecture_id)
            for architecture_id in visible_contract["builtin_architectures"]
        ],
        "candidate_id": "reference_product",
        "candidate_witness": _reference_architecture_declaration(
            REFERENCE_WITNESS_ID,
            witness=True,
        ),
        "claims": [
            {
                "clause_id": row["id"],
                "evidence_paths": ["ptycho_torch/model.py"],
                "scope": "IMPLEMENTED",
            }
            for row in visible_contract["hard_contract"]
        ],
        "extension_author_guide_path": "docs/README.md",
        "fixed_outputs": {
            "candidate_test_path": (
                "tests/torch/test_es_f1_extension_boundary.py"
            ),
            "lifecycle_adapter_path": "scripts/es_f1_lifecycle_adapter.py",
        },
        "ownership": {
            "excludes": ["PHYSICS", "LOSS", "SCALING", "DATA_OWNERSHIP"],
            "owns": [
                "ARCHITECTURE_IDENTITY",
                "STRUCTURAL_CONFIGURATION",
                "CONSTRUCTION",
                "PERSISTENCE_MIGRATION",
            ],
        },
        "schema_version": "candidate_extension_evidence.v2",
    }


def _reference_semantic_lifecycle_report(
    evaluator,
    *,
    candidate_evidence: dict[str, Any],
    architecture_cases: list[dict[str, Any]],
    fixture_manifest: dict[str, Any],
    witness_identity: str,
    seed: int,
) -> dict[str, Any]:
    declarations = [
        *candidate_evidence["builtin_architectures"],
        candidate_evidence["candidate_witness"],
    ]
    implementation_identities = {
        row["architecture"]: row["implementation_identity"]
        for row in fixture_manifest["registry_baseline"]
    }
    implementation_identities[REFERENCE_WITNESS_ID] = witness_identity
    owner_contract = {
        "loss_function": "Poisson",
        "measurement_domain": "normalized_amplitude",
        "physics_forward_mode": "amplitude",
        "scale_contract_version": "legacy_v1",
        "torch_loss_mode": "poisson",
    }
    owners = {
        "compute_loss": "ptycho_torch.model.PtychoPINN_Lightning.compute_loss",
        "loss_forward": "ptycho_torch.model.PoissonLoss.forward",
        "model_forward": "ptycho_torch.model.PtychoPINN.forward",
        "physics_forward": "ptycho_torch.model.ForwardModel.forward",
        "scaling": "ptycho_torch.model.IntensityScalerModule.scale",
    }

    def digest(label: str) -> str:
        return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()

    def rejection(label: str) -> dict[str, Any]:
        return {
            "exception_detail_sha256": digest(label),
            "exception_type": "ValueError",
            "module_returned": False,
            "rejected": True,
        }

    rows: list[dict[str, Any]] = []
    next_pid = 1_000
    for ordinal, (declaration, case) in enumerate(
        zip(declarations, architecture_cases, strict=True),
        start=1,
    ):
        architecture_id = declaration["public_id"]
        assert case["architecture_id"] == architecture_id
        image_size = case["N"]
        implementation = implementation_identities[architecture_id]
        structural_values = {
            field["name"]: field["baseline_value"]
            for field in declaration["structural_fields"]
        }
        state_signature = digest(f"{architecture_id}:state")
        observable_digest = digest(f"{architecture_id}:observable")

        def reload(*, bundle: bool, route: str) -> dict[str, Any]:
            nonlocal next_pid
            next_pid += 1
            return {
                "artifact_bytes": 1_000 + ordinal,
                "artifact_sha256": digest(
                    f"{architecture_id}:{route}:artifact"
                ),
                "architecture_id": architecture_id,
                "boundary_contract": copy.deepcopy(owner_contract),
                "boundary_input_digest_after": digest(
                    f"{architecture_id}:boundary"
                ),
                "boundary_input_digest_before": digest(
                    f"{architecture_id}:boundary"
                ),
                "boundary_owners": copy.deepcopy(owners),
                "fresh_pid": next_pid,
                "implementation_identity": implementation,
                "inference_deterministic": True,
                "inference_dtype": "complex64",
                "inference_finite": True,
                "inference_max_abs_delta": 0.0,
                "inference_shape": [1, 1, image_size, image_size],
                "inference_tolerance": 0.0,
                "loaded_forbidden_modules": [],
                "observable_digest": observable_digest,
                "outside_project_origin_rows": [],
                "roles": (
                    ["autoencoder", "diffraction_to_obj"] if bundle else []
                ),
                "state_signature": state_signature,
                "structural_values": copy.deepcopy(structural_values),
            }

        sensitivities = {
            field["name"]: {
                "alternate_identity_digest": digest(
                    f"{architecture_id}:{field['name']}:alternate-identity"
                ),
                "alternate_observable_digest": digest(
                    f"{architecture_id}:{field['name']}:alternate-observable"
                ),
                "alternate_state_signature": digest(
                    f"{architecture_id}:{field['name']}:alternate-state"
                ),
                "baseline_identity_digest": digest(
                    f"{architecture_id}:{field['name']}:baseline-identity"
                ),
                "baseline_observable_digest": observable_digest,
                "baseline_state_signature": state_signature,
                "deterministic": True,
            }
            for field in declaration["structural_fields"]
        }
        rows.append(
            {
                "N": image_size,
                "architecture_id": architecture_id,
                "boundary_contract": copy.deepcopy(owner_contract),
                "boundary_input_digest_after": digest(
                    f"{architecture_id}:boundary"
                ),
                "boundary_input_digest_before": digest(
                    f"{architecture_id}:boundary"
                ),
                "bundle_implementation": implementation,
                "completed_stages": list(
                    _json_record(VISIBLE_TASK_CONTRACT)[
                        "required_lifecycle_stages"
                    ]
                ),
                "config_digest": case["config"]["sha256"],
                "construction_route": declaration["construction_route"],
                "registry_constructor_identity": implementation,
                "evaluator_bundle_reload": reload(
                    bundle=True,
                    route="evaluator-bundle",
                ),
                "evaluator_checkpoint_reload": reload(
                    bundle=False,
                    route="evaluator-checkpoint",
                ),
                "adapter_bundle_reload": reload(
                    bundle=True,
                    route="adapter-bundle",
                ),
                "adapter_checkpoint_reload": reload(
                    bundle=False,
                    route="adapter-checkpoint",
                ),
                "forward_deterministic": True,
                "forward_dtype": "complex64",
                "forward_finite": True,
                "forward_max_abs_delta": 0.0,
                "forward_shape": [1, 1, image_size, image_size],
                "forward_tolerance": 0.0,
                "gradients_finite": True,
                "identity_rejections": {
                    "extra": rejection(f"{architecture_id}:extra"),
                    "missing": {
                        field["name"]: rejection(
                            f"{architecture_id}:missing:{field['name']}"
                        )
                        for field in declaration["structural_fields"]
                    },
                    "unsupported_value": rejection(
                        f"{architecture_id}:unsupported"
                    ),
                },
                "identity_sensitivity": sensitivities,
                "inference_digest": observable_digest,
                "input_digest": case["input"]["sha256"],
                "loss_finite": True,
                "loss_scalar": True,
                "optimizer_state_after": digest(
                    f"{architecture_id}:optimizer-after"
                ),
                "optimizer_state_before": digest(
                    f"{architecture_id}:optimizer-before"
                ),
                "optimizer_step_bound": evaluator.F1_MAX_OPTIMIZER_STEP_ABS_DELTA,
                "optimizer_step_max_abs_delta": 0.25,
                "optimizer_transition_bounded": True,
                "persisted_boundary_owners": copy.deepcopy(owners),
                "persisted_implementation": implementation,
                "persisted_rebuild_implementation": implementation,
                "persisted_rebuild_route": declaration[
                    "persisted_rebuild_route"
                ],
                "persisted_state_signature": state_signature,
                "public_boundary_owners": copy.deepcopy(owners),
                "public_implementation": implementation,
                "public_state_signature": state_signature,
                "seed": seed,
                "structural_fields": copy.deepcopy(
                    declaration["structural_fields"]
                ),
                "structural_values": structural_values,
            }
        )
    return {
        "architecture_results": rows,
        "cache_artifacts": [],
        "construction_pid": 99,
        "loaded_forbidden_modules": [],
        "outside_project_origin_rows": [],
        "schema_version": "es-f1-semantic-lifecycle.v2",
        "unknown_architecture_rejection": rejection("unknown-architecture"),
    }


def _reference_lifecycle_evidence(
    calibration,
    *,
    candidate_evidence: dict[str, Any],
    fixture_manifest: dict[str, Any],
    reference_tree: str,
    witness_identity: str,
) -> dict[str, Any]:
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    seed = 20_260_802
    declarations = [
        *candidate_evidence["builtin_architectures"],
        candidate_evidence["candidate_witness"],
    ]
    architecture_cases, input_payloads = evaluator.build_lifecycle_probe_inputs(
        architecture_rows=declarations,
        seed=seed,
    )
    assert len(input_payloads) == 30
    candidate_bytes = calibration.canonical_json_bytes(candidate_evidence)
    request = {
        "architecture_cases": architecture_cases,
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": "sha256:"
        + hashlib.sha256(candidate_bytes).hexdigest(),
        "candidate_id": candidate_evidence["candidate_id"],
        "lifecycle_output_dir": ".es-f1/lifecycle",
        "operation_version": "ptychopinn_public_lifecycle.v2",
        "required_lifecycle_stages": list(
            _json_record(VISIBLE_TASK_CONTRACT)["required_lifecycle_stages"]
        ),
        "schema_version": "lifecycle_probe_request.v3",
        "seed": seed,
    }
    semantic_report = _reference_semantic_lifecycle_report(
        evaluator,
        candidate_evidence=candidate_evidence,
        architecture_cases=architecture_cases,
        fixture_manifest=fixture_manifest,
        witness_identity=witness_identity,
        seed=seed,
    )
    adapter_result = {
        "architecture_results": [
            {
                "architecture_id": row["architecture_id"],
                "bundle_path": (
                    f"artifacts/{ordinal:02d}-{row['architecture_id']}/wts.h5.zip"
                ),
                "checkpoint_path": (
                    f"artifacts/{ordinal:02d}-{row['architecture_id']}/model.ckpt"
                ),
            }
            for ordinal, row in enumerate(architecture_cases, start=1)
        ],
        "candidate_id": candidate_evidence["candidate_id"],
        "operation_version": request["operation_version"],
        "schema_version": "lifecycle_probe_result.v3",
    }
    semantic_observations = {
        row["architecture_id"]: {
            "checkpoint": copy.deepcopy(row["adapter_checkpoint_reload"]),
            "bundle": copy.deepcopy(row["adapter_bundle_reload"]),
        }
        for row in semantic_report["architecture_results"]
    }
    adapter_process_id = 200
    lifecycle_observations = evaluator.derive_lifecycle_observations(
        semantic_report=semantic_report,
        adapter_process_id=adapter_process_id,
    )
    copy_digest = "sha256:" + hashlib.sha256(
        f"reference-tree:{reference_tree}".encode("utf-8")
    ).hexdigest()
    lifecycle_result = {
        "adapter_result": adapter_result,
        "audit_digest": evaluator._digest({"events": []}),
        "copy_digest_after": copy_digest,
        "copy_digest_before": copy_digest,
        "adapter_process_id": adapter_process_id,
        "semantic_observations": semantic_observations,
        "semantic_report": semantic_report,
        "lifecycle_observations": lifecycle_observations,
    }
    return {
        "schema_version": "es_f1_reference_lifecycle_evidence.v1",
        "lifecycle_request": request,
        "lifecycle_result": lifecycle_result,
    }


def _repeatability_lifecycle_result() -> dict[str, Any]:
    calibration = _calibration_module()
    visible_contract = _json_record(VISIBLE_TASK_CONTRACT)
    fixture_manifest = _json_record(EVALUATOR_FIXTURE_MANIFEST)
    candidate_evidence = _candidate_extension_evidence(visible_contract)
    return _reference_lifecycle_evidence(
        calibration,
        candidate_evidence=candidate_evidence,
        fixture_manifest=fixture_manifest,
        reference_tree="1" * 40,
        witness_identity="reference_product.reference_witness.Implementation",
    )["lifecycle_result"]


def _rederive_repeatability_lifecycle_observations(
    result: dict[str, Any],
) -> None:
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    result["semantic_observations"] = {
        row["architecture_id"]: {
            "checkpoint": copy.deepcopy(row["adapter_checkpoint_reload"]),
            "bundle": copy.deepcopy(row["adapter_bundle_reload"]),
        }
        for row in result["semantic_report"]["architecture_results"]
    }
    result["lifecycle_observations"] = evaluator.derive_lifecycle_observations(
        semantic_report=result["semantic_report"],
        adapter_process_id=result["adapter_process_id"],
    )


def test_task3a_repeat_projection_ignores_only_serialization_containers_and_pids() -> None:
    calibration = _calibration_module()
    left = _repeatability_lifecycle_result()
    right = copy.deepcopy(left)
    right["adapter_process_id"] += 10_000
    right["audit_digest"] = "sha256:" + "9" * 64
    right["semantic_report"]["construction_pid"] += 10_000
    for ordinal, row in enumerate(
        right["semantic_report"]["architecture_results"], start=1
    ):
        for reload_name in (
            "evaluator_checkpoint_reload",
            "evaluator_bundle_reload",
            "adapter_checkpoint_reload",
            "adapter_bundle_reload",
        ):
            reload = row[reload_name]
            reload["fresh_pid"] += 10_000
            reload["artifact_bytes"] += ordinal
            reload["artifact_sha256"] = "sha256:" + f"{ordinal:064x}"
        for field_ordinal, sensitivity in enumerate(
            row["identity_sensitivity"].values(), start=1
        ):
            sensitivity["baseline_identity_digest"] = (
                "sha256:" + f"{ordinal * 100 + field_ordinal:064x}"
            )
            sensitivity["alternate_identity_digest"] = (
                "sha256:" + f"{ordinal * 100 + field_ordinal + 1_000_000:064x}"
            )
    _rederive_repeatability_lifecycle_observations(right)

    assert calibration.project_reference_lifecycle_repeat_facts(
        left
    ) == calibration.project_reference_lifecycle_repeat_facts(right)


def test_task3a_repeat_projection_preserves_semantic_state_drift() -> None:
    calibration = _calibration_module()
    left = _repeatability_lifecycle_result()
    right = copy.deepcopy(left)
    right["semantic_report"]["architecture_results"][0][
        "evaluator_checkpoint_reload"
    ]["state_signature"] = "sha256:" + "8" * 64
    _rederive_repeatability_lifecycle_observations(right)

    assert calibration.project_reference_lifecycle_repeat_facts(
        left
    ) != calibration.project_reference_lifecycle_repeat_facts(right)


def test_task3a_repeat_projection_preserves_bundle_observable_drift() -> None:
    calibration = _calibration_module()
    left = _repeatability_lifecycle_result()
    right = copy.deepcopy(left)
    replacement = "sha256:" + "7" * 64
    right["semantic_report"]["architecture_results"][0][
        "adapter_bundle_reload"
    ]["observable_digest"] = replacement
    _rederive_repeatability_lifecycle_observations(right)

    assert right["semantic_observations"]["cnn"]["bundle"][
        "observable_digest"
    ] == replacement
    assert calibration.project_reference_lifecycle_repeat_facts(
        left
    ) != calibration.project_reference_lifecycle_repeat_facts(right)


def test_task3a_repeat_projection_rejects_invalid_masked_artifact_facts() -> None:
    calibration = _calibration_module()
    result = _repeatability_lifecycle_result()
    result["semantic_report"]["architecture_results"][0][
        "evaluator_checkpoint_reload"
    ]["artifact_bytes"] = 0
    _rederive_repeatability_lifecycle_observations(result)

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.project_reference_lifecycle_repeat_facts(result)

    assert caught.value.code == "reference_evaluator_repeat_invalid"


def _witness_route_identities_from_lifecycle(
    lifecycle_evidence: dict[str, Any],
) -> list[dict[str, str]]:
    semantic_rows = lifecycle_evidence["lifecycle_result"]["semantic_report"][
        "architecture_results"
    ]
    witness_row = next(
        row
        for row in semantic_rows
        if row["architecture_id"] == REFERENCE_WITNESS_ID
    )
    checkpoint_identities = {
        witness_row["evaluator_checkpoint_reload"]["implementation_identity"],
        witness_row["adapter_checkpoint_reload"]["implementation_identity"],
    }
    bundle_identities = {
        witness_row["evaluator_bundle_reload"]["implementation_identity"],
        witness_row["adapter_bundle_reload"]["implementation_identity"],
    }
    persisted_identities = {
        witness_row["persisted_implementation"],
        witness_row["persisted_rebuild_implementation"],
        witness_row["bundle_implementation"],
    }
    assert len(checkpoint_identities) == 1
    assert len(bundle_identities) == 1
    assert len(persisted_identities) == 1
    identities_by_role = {
        "REGISTRY_CONSTRUCTOR": witness_row["registry_constructor_identity"],
        "PUBLIC_CONSTRUCTION": witness_row["public_implementation"],
        "CHECKPOINT_RELOAD": next(iter(checkpoint_identities)),
        "BUNDLE_RELOAD": next(iter(bundle_identities)),
        "PERSISTED_REBUILD": next(iter(persisted_identities)),
    }
    return [
        {
            "role": role,
            "architecture_id": REFERENCE_WITNESS_ID,
            "implementation_identity": identity,
        }
        for role, identity in identities_by_role.items()
    ]


def _reference_structural_scope(
    selector: dict[str, Any],
    repository: dict[str, Any],
) -> dict[str, Any]:
    metric = repository["metric"]
    target_tree = repository["reference_tree"]
    production_rows = [
        row for row in metric["rows"] if row["classification"] == "production_python"
    ]
    by_path = {
        row["candidate_path"]: row
        for row in production_rows
    }
    changed_clusters = list(
        dict.fromkeys(
            cluster_id
            for row in production_rows
            for cluster_id in row["cluster_ids"]
        )
    )
    edges: list[dict[str, Any]] = []
    frozen_edges = selector["feasibility_spike"]["integration_edges"]
    assert len(frozen_edges) == len(REFERENCE_EDGE_STATIC_SPECS) == 3
    for frozen in frozen_edges:
        static_spec = REFERENCE_EDGE_STATIC_SPECS[frozen["edge_id"]]
        producer_path = static_spec["producer_path"]
        consumer_path = static_spec["consumer_path"]
        producer = by_path[producer_path]
        consumer = by_path[consumer_path]
        producer_tree = ast.parse(
            repository["candidate_payloads"][producer_path].decode("utf-8")
        )
        consumer_tree = ast.parse(
            repository["candidate_payloads"][consumer_path].decode("utf-8")
        )
        imported_module = producer_path.removesuffix(".py").replace("/", ".")
        imported_binding = static_spec["imported_binding"]
        import_nodes = [
            node
            for node in consumer_tree.body
            if isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == imported_module
            and any(
                alias.name == imported_binding and alias.asname is None
                for alias in node.names
            )
        ]
        assert len(import_nodes) == 1
        import_node = import_nodes[0]
        producer_owner = static_spec["producer_owner"]
        if producer_owner is None:
            producer_nodes = [
                node
                for node in producer_tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == static_spec["producer_name"]
            ]
        else:
            owner_nodes = [
                node
                for node in producer_tree.body
                if isinstance(node, ast.ClassDef) and node.name == producer_owner
            ]
            assert len(owner_nodes) == 1
            producer_nodes = [
                node
                for node in owner_nodes[0].body
                if isinstance(node, ast.FunctionDef)
                and node.name == static_spec["producer_name"]
            ]
        assert len(producer_nodes) == 1
        producer_node = producer_nodes[0]
        consumer_nodes = [
            node
            for node in ast.walk(consumer_tree)
            if isinstance(node, ast.Call)
            and (
                (
                    producer_owner is None
                    and isinstance(node.func, ast.Name)
                    and node.func.id == imported_binding
                )
                or (
                    producer_owner is not None
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == static_spec["producer_name"]
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == imported_binding
                )
            )
        ]
        assert len(consumer_nodes) == 1
        consumer_node = consumer_nodes[0]
        symbol = static_spec["resolved_symbol"]
        edges.append(
            {
                "edge_id": frozen["edge_id"],
                "from_cluster": frozen["from_cluster"],
                "to_cluster": frozen["to_cluster"],
                "producer": {
                    "path": producer["candidate_path"],
                    "blob_id": producer["candidate_blob_id"],
                    "node_kind": "FunctionDef",
                    "symbol": symbol,
                    "span": {
                        "line_start": producer_node.lineno,
                        "column_start": producer_node.col_offset,
                        "line_end": producer_node.end_lineno,
                        "column_end": producer_node.end_col_offset,
                    },
                },
                "consumer": {
                    "path": consumer["candidate_path"],
                    "blob_id": consumer["candidate_blob_id"],
                    "node_kind": "Call",
                    "symbol": symbol,
                    "span": {
                        "line_start": consumer_node.lineno,
                        "column_start": consumer_node.col_offset,
                        "line_end": consumer_node.end_lineno,
                        "column_end": consumer_node.end_col_offset,
                    },
                },
                "evidence": {
                    "evidence_kind": REFERENCE_EDGE_EVIDENCE_KIND,
                    "evidence_semantics": REFERENCE_EDGE_EVIDENCE_SEMANTICS,
                    "target_tree": target_tree,
                    "imported_module": imported_module,
                    "imported_binding": imported_binding,
                    "import_span": {
                        "line_start": import_node.lineno,
                        "column_start": import_node.col_offset,
                        "line_end": import_node.end_lineno,
                        "column_end": import_node.end_col_offset,
                    },
                    "consumer_blob_id": consumer["candidate_blob_id"],
                    "resolved_producer_blob_id": producer["candidate_blob_id"],
                    "resolved_symbol": symbol,
                    "lifecycle_report_member_id": "lifecycle_result",
                    "lifecycle_clause_ids": list(
                        REFERENCE_EDGE_LIFECYCLE_CLAUSES[frozen["edge_id"]]
                    ),
                },
            }
        )
    return {
        "responsibility_ids": [
            row["responsibility_id"]
            for row in _json_record(PREEDIT_POLICY)["responsibilities"]
        ],
        "cluster_domain": list(selector["feasibility_spike"]["cluster_domain"]),
        "changed_cluster_ids": changed_clusters,
        "integration_edges": edges,
    }


def _cas_member(
    root: Path,
    member_id: str,
    payload: bytes,
) -> dict[str, Any]:
    digest = hashlib.sha256(payload).hexdigest()
    relative = f"{digest}/payload"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "member_id": member_id,
        "cas_relative_path": relative,
        "byte_count": len(payload),
        "sha256": f"sha256:{digest}",
    }


def _cas_member_row(record: dict[str, Any], member_id: str) -> dict[str, Any]:
    return next(
        row
        for row in record["evidence_store"]["members"]
        if row["member_id"] == member_id
    )


def _cas_member_path(record: dict[str, Any], member_id: str) -> Path:
    member = _cas_member_row(record, member_id)
    return Path(record["evidence_store"]["root"]) / member["cas_relative_path"]


def _cas_json_record(record: dict[str, Any], member_id: str) -> dict[str, Any]:
    return _json_record(_cas_member_path(record, member_id))


def _replace_cas_json_record(
    calibration,
    record: dict[str, Any],
    member_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    changed = copy.deepcopy(record)
    replacement = _cas_member(
        Path(changed["evidence_store"]["root"]),
        member_id,
        calibration.canonical_json_bytes(payload),
    )
    current = _cas_member_row(changed, member_id)
    current.clear()
    current.update(replacement)
    return _sealed_reference_record(calibration, changed)


def _rebuild_reference_cas(
    calibration,
    record: dict[str, Any],
    *,
    root: Path,
    json_overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    payloads = {
        member_id: _cas_member_path(record, member_id).read_bytes()
        for member_id in REFERENCE_CAS_MEMBER_IDS
        if member_id != "hard_evaluation"
    }
    payloads.update(
        {
            member_id: calibration.canonical_json_bytes(payload)
            for member_id, payload in json_overrides.items()
        }
    )
    member_sha256 = {
        member_id: "sha256:" + hashlib.sha256(payload).hexdigest()
        for member_id, payload in payloads.items()
    }
    candidate_evidence = json.loads(payloads["candidate_evidence"])
    visible_check_result = json.loads(payloads["visible_check_result"])
    registry_signature_report = json.loads(payloads["registry_signature_report"])
    artifact_fixture_verification = json.loads(
        payloads["artifact_fixture_verification"]
    )
    lifecycle_evidence = json.loads(payloads["lifecycle_result"])
    bypass_classification = json.loads(payloads["bypass_classification"])
    visible_manifest = _json_record(VISIBLE_CHECK_MANIFEST)
    fixture_manifest = _json_record(EVALUATOR_FIXTURE_MANIFEST)

    visible_invocations = visible_check_result["invocations"]
    visible_satisfied = (
        [row["invocation_id"] for row in visible_invocations]
        == visible_manifest["invocation_order"]
        and all(row["exit_code"] == 0 for row in visible_invocations)
    )

    lifecycle_request = lifecycle_evidence["lifecycle_request"]
    lifecycle_result = lifecycle_evidence["lifecycle_result"]
    candidate_architecture_ids = [
        row["public_id"]
        for row in [
            *candidate_evidence["builtin_architectures"],
            candidate_evidence["candidate_witness"],
        ]
    ]
    request_architecture_ids = [
        row["architecture_id"]
        for row in lifecycle_request["architecture_cases"]
    ]
    adapter_architecture_ids = [
        row["architecture_id"]
        for row in lifecycle_result["adapter_result"]["architecture_results"]
    ]
    claim_ids = [row["clause_id"] for row in candidate_evidence["claims"]]
    candidate_satisfied = (
        claim_ids == list(evaluator.HARD_CLAUSE_IDS)
        and all(
            row["scope"] != "NOT_CLAIMED"
            and bool(row["evidence_paths"])
            for row in candidate_evidence["claims"]
        )
        and lifecycle_request["candidate_evidence_sha256"]
        == member_sha256["candidate_evidence"]
        and candidate_architecture_ids
        == request_architecture_ids
        == adapter_architecture_ids
    )

    registry_satisfied = (
        registry_signature_report["registry_baseline"]
        == fixture_manifest["registry_baseline"]
    )
    witness_identity = _witness_route_identities_from_lifecycle(
        lifecycle_evidence
    )[0]["implementation_identity"]
    expected_artifact_report = _artifact_fixture_verification(
        fixture_manifest,
        candidate_architecture_ids,
        witness_identity=witness_identity,
    )
    artifact_satisfied = (
        artifact_fixture_verification == expected_artifact_report
    )

    # Frozen ordering is evaluated by H02 above.  Canonicalizing a comparison
    # copy lets the remaining lifecycle facts be derived from the same rows
    # even in the deliberate order-drift mutant; the actual resealed lifecycle
    # member remains the hard-evidence input below.
    semantic_report = lifecycle_result["semantic_report"]
    semantic_by_architecture = {
        row["architecture_id"]: row
        for row in semantic_report["architecture_results"]
    }
    semantic_comparison = copy.deepcopy(semantic_report)
    semantic_comparison["architecture_results"] = [
        copy.deepcopy(semantic_by_architecture[architecture_id])
        for architecture_id in candidate_architecture_ids
    ]
    lifecycle_observations = evaluator.derive_lifecycle_observations(
        semantic_report=semantic_comparison,
        adapter_process_id=lifecycle_result["adapter_process_id"],
    )
    lifecycle_satisfied = {
        row["clause_id"]: row["satisfied"]
        for row in lifecycle_observations
    }
    bypass_satisfied = (
        bypass_classification["derived_observation"]["satisfied"] is True
        and not bypass_classification["classification"][
            "restored_required_consumer_ids"
        ]
    )
    facts = {
        "F1-H01-FOCUSED-SUITES": visible_satisfied,
        "F1-H02-SCHEMA-CONFORMANCE": candidate_satisfied,
        "F1-H03-BUILTIN-SIGNATURES": registry_satisfied,
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY": artifact_satisfied,
        **lifecycle_satisfied,
    }
    facts["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"] = (
        facts["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"]
        and bypass_satisfied
    )
    details = {
        "F1-H01-FOCUSED-SUITES": (
            "exact candidate-visible invocation results on an immutable copy"
        ),
        "F1-H02-SCHEMA-CONFORMANCE": (
            "candidate claims and actual resealed lifecycle-member order bindings"
        ),
        "F1-H03-BUILTIN-SIGNATURES": (
            "exact frozen built-in registry signature comparison"
        ),
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY": (
            "exact frozen ten-by-fifteen artifact applicability matrix"
        ),
    }
    lifecycle_by_clause = {
        row["clause_id"]: copy.deepcopy(row) for row in lifecycle_observations
    }
    lifecycle_by_clause["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"][
        "satisfied"
    ] = facts["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"]
    lifecycle_by_clause["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"][
        "evidence"
    ].append(evaluator._digest(bypass_classification["derived_observation"]))
    lifecycle_by_clause["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"][
        "details"
    ] += "; closed Task-0 desired-state proofs and legacy-bypass oracle"
    derived_observations = [
        (
            lifecycle_by_clause[clause_id]
            if clause_id in lifecycle_by_clause
            else {
                "clause_id": clause_id,
                "satisfied": facts[clause_id],
                "evidence": [
                    evaluator._digest(
                        {
                            "clause_id": clause_id,
                            "satisfied": facts[clause_id],
                        }
                    )
                ],
                "details": details[clause_id],
            }
        )
        for clause_id in evaluator.HARD_CLAUSE_IDS
    ]
    observations = calibration._normalize_reference_publication_observations(
        derived_observations,
        cas_member_sha256_by_id=member_sha256,
    )
    dispositions = {
        clause_id: "PRODUCT_DEFECT"
        for clause_id, satisfied in facts.items()
        if not satisfied
    }
    payloads["hard_evaluation"] = calibration.canonical_json_bytes(
        evaluator.evaluate_observations(
            candidate_claims=candidate_evidence,
            evaluator_observations=observations,
            dispositions=dispositions,
            frozen_registry={
                row["architecture"]
                for row in fixture_manifest["registry_baseline"]
            },
        )
    )
    assert not root.exists()
    changed = copy.deepcopy(record)
    changed["evidence_store"]["root"] = str(root.resolve())
    changed["evidence_store"]["members"] = [
        _cas_member(root, member_id, payloads[member_id])
        for member_id in REFERENCE_CAS_MEMBER_IDS
    ]
    return _sealed_reference_record(calibration, changed)


def _write_reference_cas(
    root: Path,
    repository: dict[str, Any],
    *,
    evaluator_evidence: dict[str, Any],
    candidate_evidence: dict[str, Any],
    visible_check_result: dict[str, Any],
    registry_signature_report: dict[str, Any],
    artifact_fixture_verification: dict[str, Any],
    lifecycle_evidence: dict[str, Any],
    bypass_discovery: dict[str, Any],
    bypass_classification: dict[str, Any],
    no_delivery_report: dict[str, Any],
) -> list[dict[str, Any]]:
    calibration = _calibration_module()
    raw_reports: dict[str, bytes] = {
        "canonical_patch": repository["canonical_patch"],
        "candidate_evidence": calibration.canonical_json_bytes(
            candidate_evidence
        ),
        "visible_check_result": calibration.canonical_json_bytes(
            visible_check_result
        ),
        "registry_signature_report": calibration.canonical_json_bytes(
            registry_signature_report
        ),
        "artifact_fixture_verification": calibration.canonical_json_bytes(
            artifact_fixture_verification
        ),
        "lifecycle_result": calibration.canonical_json_bytes(
            lifecycle_evidence
        ),
        "bypass_discovery": calibration.canonical_json_bytes(
            bypass_discovery
        ),
        "bypass_classification": calibration.canonical_json_bytes(
            bypass_classification
        ),
        "no_delivery_report": calibration.canonical_json_bytes(
            no_delivery_report
        ),
    }
    assert set(raw_reports) == set(REFERENCE_CAS_MEMBER_IDS) - {
        "hard_evaluation"
    }
    member_sha256 = {
        member_id: "sha256:" + hashlib.sha256(payload).hexdigest()
        for member_id, payload in raw_reports.items()
    }
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    hard_clause_evidence = evaluator_evidence["hard_clause_evidence"]
    assert list(hard_clause_evidence) == list(evaluator.HARD_CLAUSE_IDS)
    bypass_satisfied = (
        bypass_classification["derived_observation"]["satisfied"] is True
        and not bypass_classification["classification"][
            "restored_required_consumer_ids"
        ]
    )
    derived_lifecycle = {
        row["clause_id"]: copy.deepcopy(row)
        for row in lifecycle_evidence["lifecycle_result"][
            "lifecycle_observations"
        ]
    }
    derived_lifecycle["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"][
        "satisfied"
    ] = (
        derived_lifecycle["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"][
            "satisfied"
        ]
        and bypass_satisfied
    )
    derived_lifecycle["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"][
        "evidence"
    ].append(evaluator._digest(bypass_classification["derived_observation"]))
    derived_lifecycle["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"][
        "details"
    ] += "; closed Task-0 desired-state proofs and legacy-bypass oracle"
    derived_observations = [
        (
            derived_lifecycle[clause_id]
            if clause_id in derived_lifecycle
            else {
                "clause_id": clause_id,
                "satisfied": True,
                "evidence": [
                    evaluator._digest(
                        {
                            "clause_id": clause_id,
                            "controller_fact": "reference-capture",
                        }
                    )
                ],
                "details": f"controller-owned reference evidence for {clause_id}",
            }
        )
        for clause_id in evaluator.HARD_CLAUSE_IDS
    ]
    observations = calibration._normalize_reference_publication_observations(
        derived_observations,
        cas_member_sha256_by_id=member_sha256,
    )
    hard_evaluation = evaluator.evaluate_observations(
        candidate_claims=candidate_evidence,
        evaluator_observations=observations,
        dispositions=(
            {}
            if bypass_satisfied
            else {"F1-H05-FULL-ARCHITECTURE-LIFECYCLE": "PRODUCT_DEFECT"}
        ),
        frozen_registry={
            row["architecture"]
            for row in registry_signature_report["registry_baseline"]
        },
    )
    payload_by_member_id = {
        **raw_reports,
        "hard_evaluation": calibration.canonical_json_bytes(hard_evaluation),
    }
    reports = {
        member_id: payload_by_member_id[member_id]
        for member_id in REFERENCE_CAS_MEMBER_IDS
    }
    assert tuple(reports) == REFERENCE_CAS_MEMBER_IDS
    return [
        _cas_member(root, member_id, reports[member_id])
        for member_id in REFERENCE_CAS_MEMBER_IDS
    ]


def _build_reference_record(
    tmp_path: Path,
    repository: dict[str, Any],
) -> dict[str, Any]:
    calibration = _calibration_module()
    boundary = importlib.import_module("scripts.experiments.es.boundary_proofs")
    source_census = _json_record(SOURCE_CENSUS)
    selector = _json_record(SELECTOR_MANIFEST)
    task_seed = _json_record(TASK_SEED_MANIFEST)
    visible_contract = _json_record(VISIBLE_TASK_CONTRACT)
    visible_check_manifest = _json_record(VISIBLE_CHECK_MANIFEST)
    fixture_manifest = _json_record(EVALUATOR_FIXTURE_MANIFEST)

    boundary.validate_authority_bindings(selector, source_census)
    contract = boundary.validate_contract(
        selector,
        consumer_rows=source_census["consumer_rows"],
        expected_runner_sha256=BOUNDARY_PROOF_RUNNER_SHA256,
    )
    assert len(source_census["consumer_rows"]) == 1_959
    assert len(contract.desired_specs) == 23

    metric = copy.deepcopy(repository["metric"])
    structural_scope = _reference_structural_scope(
        selector,
        repository,
    )
    architectures = [
        *visible_contract["builtin_architectures"],
        REFERENCE_WITNESS_ID,
    ]
    witness_identity = "reference_product.reference_witness.Implementation"
    assert _raw_sha256(VISIBLE_CHECK_MANIFEST) == visible_contract[
        "visible_checks"
    ]["sha256"]
    visible_check_result = _visible_check_result(
        visible_check_manifest,
        reference_tree=repository["reference_tree"],
    )
    registry_signature_report = _registry_signature_report(fixture_manifest)
    candidate_evidence = _candidate_extension_evidence(visible_contract)
    lifecycle_evidence = _reference_lifecycle_evidence(
        calibration,
        candidate_evidence=candidate_evidence,
        fixture_manifest=fixture_manifest,
        reference_tree=repository["reference_tree"],
        witness_identity=witness_identity,
    )
    artifact_fixture_verification = _artifact_fixture_verification(
        fixture_manifest,
        architectures,
        witness_identity=witness_identity,
    )

    evidence_root = repository["storage_root"] / "evidence" / tmp_path.name
    evidence_root.mkdir(parents=True)

    evaluator_evidence = {
        "report_member_ids": {
            "candidate_evidence": "candidate_evidence",
            "visible_check_result": "visible_check_result",
            "registry_signature_report": "registry_signature_report",
            "artifact_fixture_verification": "artifact_fixture_verification",
            "lifecycle_result": "lifecycle_result",
            "hard_evaluation": "hard_evaluation",
        },
        "witness_architecture_id": REFERENCE_WITNESS_ID,
        "witness_identity_roles": list(
            visible_contract["witness_identity_proof"]["identity_roles"]
        ),
        "witness_route_identities": (
            _witness_route_identities_from_lifecycle(lifecycle_evidence)
        ),
        "candidate_id": candidate_evidence["candidate_id"],
        "architecture_ids": [
            row["architecture_id"]
            for row in lifecycle_evidence["lifecycle_request"][
                "architecture_cases"
            ]
        ],
        "lifecycle_stage_ids": list(
            lifecycle_evidence["lifecycle_request"][
                "required_lifecycle_stages"
            ]
        ),
        "lifecycle_observations": copy.deepcopy(
            lifecycle_evidence["lifecycle_result"][
                "lifecycle_observations"
            ]
        ),
        "hard_clause_evidence": {
            clause_id: list(member_ids)
            for clause_id, member_ids in REFERENCE_HARD_CLAUSE_EVIDENCE
        },
        "artifact_applicability": copy.deepcopy(
            artifact_fixture_verification["artifact_eras"]
        ),
    }
    desired_state_rows = _desired_state_rows(
        boundary,
        contract,
        repository=repository["repository"],
        target_tree=repository["reference_tree"],
    )
    (
        bypass_discovery,
        bypass_classification,
        bypass_oracle,
    ) = _reference_bypass_reports(
        calibration,
        repository,
        desired_state_rows,
    )
    no_delivery_report = _build_reference_no_delivery_report(
        repository,
        task_seed,
    )
    no_delivery = {
        "report_member_id": "no_delivery_report",
        "task_seed_repository": task_seed["repository"]["locator"],
        "task_seed_tree": task_seed["recipe"]["tree"],
        "reference_object_ids": [
            row["object_id"]
            for row in no_delivery_report["reference_only_objects"]
        ],
        "task5_replay_required": True,
    }
    cas_members = _write_reference_cas(
        evidence_root,
        repository,
        evaluator_evidence=evaluator_evidence,
        candidate_evidence=candidate_evidence,
        visible_check_result=visible_check_result,
        registry_signature_report=registry_signature_report,
        artifact_fixture_verification=artifact_fixture_verification,
        lifecycle_evidence=lifecycle_evidence,
        bypass_discovery=bypass_discovery,
        bypass_classification=bypass_classification,
        no_delivery_report=no_delivery_report,
    )

    body = {
        "schema_version": "es_f1_reference_product.v1",
        "bindings": {
            "preedit_policy": _authority_binding(
                PREEDIT_POLICY, PREEDIT_POLICY_SCHEMA
            ),
            "source_census": _authority_binding(
                SOURCE_CENSUS, SOURCE_CENSUS_SCHEMA
            ),
            "selector_manifest": _authority_binding(
                SELECTOR_MANIFEST, SELECTOR_MANIFEST_SCHEMA
            ),
            "task0_review_adoption": _authority_binding(
                TASK0_REVIEW_ADOPTION, TASK0_REVIEW_ADOPTION_SCHEMA
            ),
            "a1_anchor": _authority_binding(A1_RECORD, A1_SCHEMA),
            "task_seed_manifest": _authority_binding(
                TASK_SEED_MANIFEST, TASK_SEED_SCHEMA
            ),
            "visible_task_contract": _authority_binding(
                VISIBLE_TASK_CONTRACT, VISIBLE_TASK_CONTRACT_SCHEMA
            ),
            "evaluator_fixture_manifest": _authority_binding(
                EVALUATOR_FIXTURE_MANIFEST
            ),
            "governing_plan": _authority_binding(GOVERNING_PLAN),
            "reference_calibration": _authority_binding(
                REFERENCE_CALIBRATION_TOOL
            ),
            "f1_evaluator": _authority_binding(F1_EVALUATOR_TOOL),
            "boundary_proof_runner": {
                **_authority_binding(BOUNDARY_PROOF_RUNNER),
                "sha256": BOUNDARY_PROOF_RUNNER_SHA256,
            },
        },
        "lineage": {
            "projection_commit": task_seed["parent_projection"]["commit"],
            "projection_tree": task_seed["parent_projection"]["tree"],
            "task_seed_commit": task_seed["recipe"]["commit"],
            "task_seed_tree": task_seed["recipe"]["tree"],
            "reference_commit": repository["reference_commit"],
            "reference_tree": repository["reference_tree"],
        },
        "repository": {
            "storage_root": str(repository["storage_root"]),
            "relative_path": repository["relative_path"],
            "locator": str(repository["repository"]),
            "head_ref": REFERENCE_REF,
            "object_format": "sha1",
            "commit_count": 3,
            "object_count": repository["object_count"],
            "unreachable_object_count": 0,
            "repository_snapshot_sha256": repository[
                "repository_snapshot_sha256"
            ],
        },
        "evidence_store": {
            "algorithm": "sha256",
            "root": str(evidence_root.resolve()),
            "members": cas_members,
        },
        "patch": {
            "member_id": "canonical_patch",
            "format": "git-diff-binary-full-index.v1",
            "base": task_seed["recipe"]["commit"],
            "target": repository["reference_commit"],
            "argv": repository["patch_argv"],
        },
        "metric": metric,
        "structural_scope": structural_scope,
        "evaluator_evidence": evaluator_evidence,
        "desired_state_proofs": {
            "schema_version": "es_f1_boundary_desired_state.v1",
            "runner_sha256": BOUNDARY_PROOF_RUNNER_SHA256,
            "target_tree": repository["reference_tree"],
            "execution": {
                "python": {
                    "path": str(REFERENCE_PYTHON),
                    "target": str(REFERENCE_PYTHON_TARGET),
                    "version": REFERENCE_PYTHON_VERSION,
                    "sha256": REFERENCE_PYTHON_SHA256,
                },
                "pytest_carrier": {
                    "path": str(REFERENCE_PYTEST_CARRIER),
                    "version": REFERENCE_PYTEST_CARRIER_VERSION,
                    "sha256": REFERENCE_PYTEST_CARRIER_SHA256,
                },
            },
            "result_rows": desired_state_rows,
        },
        "bypass_oracle": bypass_oracle,
        "no_delivery": no_delivery,
    }
    return calibration.seal_record(body)


_VALIDATE_A1_AUTHORITIES = (
    (
        "policy",
        "--policy",
        PREEDIT_POLICY,
        "--policy-schema",
        PREEDIT_POLICY_SCHEMA,
        "--expected-policy-sha256",
    ),
    (
        "source-census",
        "--source-census",
        SOURCE_CENSUS,
        "--source-census-schema",
        SOURCE_CENSUS_SCHEMA,
        "--expected-source-census-sha256",
    ),
    (
        "task0-review-adoption",
        "--task0-review-adoption",
        TASK0_REVIEW_ADOPTION,
        "--task0-review-adoption-schema",
        TASK0_REVIEW_ADOPTION_SCHEMA,
        "--expected-task0-review-adoption-sha256",
    ),
    (
        "a1-anchor",
        "--a1-anchor",
        A1_RECORD,
        "--a1-anchor-schema",
        A1_SCHEMA,
        "--expected-a1-anchor-sha256",
    ),
)
_VALIDATE_A1_REQUIRED_OPTIONS = tuple(
    option
    for _, record_option, _, schema_option, _, digest_option in (
        _VALIDATE_A1_AUTHORITIES
    )
    for option in (record_option, schema_option, digest_option)
)


def _published_validate_a1_argv() -> list[str]:
    argv = [
        sys.executable,
        "-m",
        "scripts.experiments.es.reference_calibration",
        "validate-a1",
    ]
    for (
        _,
        record_option,
        record_path,
        schema_option,
        schema_path,
        digest_option,
    ) in _VALIDATE_A1_AUTHORITIES:
        argv.extend(
            (
                record_option,
                str(record_path.resolve()),
                schema_option,
                str(schema_path.resolve()),
                digest_option,
                _json_record(record_path)["record_sha256"],
            )
        )
    assert tuple(argv[4::2]) == _VALIDATE_A1_REQUIRED_OPTIONS
    assert len(argv) == 4 + 2 * len(_VALIDATE_A1_REQUIRED_OPTIONS)
    return argv


def _run_reference_calibration_cli(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        check=False,
        cwd=ROOT,
        env={**os.environ, "PYTHONHASHSEED": "0"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.mark.parametrize(
    "surface_mutation",
    [
        *[
            ("missing", option)
            for option in _VALIDATE_A1_REQUIRED_OPTIONS
        ],
        ("unknown", "--output"),
    ],
    ids=[
        *[
            "missing-" + option.removeprefix("--")
            for option in _VALIDATE_A1_REQUIRED_OPTIONS
        ],
        "unknown-output",
    ],
)
def test_task3a_validate_a1_cli_requires_exact_closed_option_surface(
    tmp_path: Path,
    surface_mutation: tuple[str, str],
) -> None:
    argv = _published_validate_a1_argv()
    mutation, option = surface_mutation
    if mutation == "missing":
        option_index = argv.index(option)
        del argv[option_index : option_index + 2]
    else:
        output = tmp_path / "not-an-output-command.json"
        argv.extend((option, str(output)))

    completed = _run_reference_calibration_cli(argv)

    assert completed.returncode == 2
    assert completed.stdout == b""
    if mutation == "unknown":
        assert not output.exists()


def test_task3a_validate_a1_cli_accepts_exact_published_authority_chain_silently(
) -> None:
    _require_a1_evidence()
    anchor = _json_record(A1_RECORD)
    bound_paths = {
        *[
            path
            for _, _, record_path, _, schema_path, _ in (
                _VALIDATE_A1_AUTHORITIES
            )
            for path in (record_path, schema_path)
        ],
        *[
            A1_ROOT / row["path"]
            for row in anchor["members"]
        ],
    }
    before = {
        path.resolve(): path.read_bytes()
        for path in bound_paths
    }

    completed = _run_reference_calibration_cli(
        _published_validate_a1_argv()
    )
    help_completed = _run_reference_calibration_cli(
        [
            sys.executable,
            "-m",
            "scripts.experiments.es.reference_calibration",
            "validate-a1",
            "--help",
        ]
    )

    assert completed.returncode == 0
    assert completed.stdout == b""
    assert completed.stderr == b""
    assert {
        path: path.read_bytes()
        for path in before
    } == before
    assert anchor["metric"] == {
        "metric_version": "implementation_delta_physical_lines.v1",
        "git_contract_policy_sha256": _json_record(PREEDIT_POLICY)[
            "record_sha256"
        ],
        "base_member_ids": ["base_entrypoint", "base_types", "base_init"],
        "candidate_member_ids": [
            "direct_entrypoint",
            "direct_types",
            "direct_init",
        ],
        "patch_member_id": "direct_patch",
        "implementation_additions": 667,
        "implementation_deletions": 2,
        "candidate_postimage_physical_lines": 690,
    }
    assert help_completed.returncode == 0
    assert help_completed.stdout != b""


@pytest.mark.parametrize(
    "authority_id",
    [row[0] for row in _VALIDATE_A1_AUTHORITIES],
)
def test_task3a_validate_a1_cli_rejects_each_expected_self_digest_drift(
    authority_id: str,
) -> None:
    argv = _published_validate_a1_argv()
    digest_option = next(
        row[5]
        for row in _VALIDATE_A1_AUTHORITIES
        if row[0] == authority_id
    )
    argv[argv.index(digest_option) + 1] = "sha256:" + "0" * 64

    completed = _run_reference_calibration_cli(argv)

    assert completed.returncode == 2
    assert completed.stdout == b""


@pytest.mark.parametrize(
    "authority_id",
    [row[0] for row in _VALIDATE_A1_AUTHORITIES],
)
def test_task3a_validate_a1_cli_rejects_byte_identical_nonpublished_schema_path(
    tmp_path: Path,
    authority_id: str,
) -> None:
    argv = _published_validate_a1_argv()
    _, _, _, schema_option, schema_path, _ = next(
        row for row in _VALIDATE_A1_AUTHORITIES if row[0] == authority_id
    )
    copied_schema = tmp_path / authority_id / schema_path.name
    copied_schema.parent.mkdir(parents=True)
    copied_schema.write_bytes(schema_path.read_bytes())
    argv[argv.index(schema_option) + 1] = str(copied_schema.resolve())

    completed = _run_reference_calibration_cli(argv)

    assert copied_schema.read_bytes() == schema_path.read_bytes()
    assert completed.returncode == 2
    assert completed.stdout == b""


@pytest.mark.parametrize(
    ("authority_id", "binding_field"),
    [
        ("source-census", "preedit_policy_sha256"),
        ("a1-anchor", "preedit_policy_sha256"),
        ("task0-review-adoption", "preedit_policy_sha256"),
        ("task0-review-adoption", "source_census_sha256"),
        ("task0-review-adoption", "a1_anchor_sha256"),
    ],
    ids=(
        "census-to-policy",
        "a1-to-policy",
        "adoption-to-policy",
        "adoption-to-census",
        "adoption-to-a1",
    ),
)
def test_task3a_validate_a1_cli_rejects_internally_resealed_authority_join_drift(
    tmp_path: Path,
    authority_id: str,
    binding_field: str,
) -> None:
    calibration = _calibration_module()
    (
        _,
        record_option,
        record_path,
        _,
        _,
        digest_option,
    ) = next(
        row for row in _VALIDATE_A1_AUTHORITIES if row[0] == authority_id
    )
    changed = _json_record(record_path)
    if authority_id == "task0-review-adoption":
        changed["bindings"][binding_field] = "sha256:" + "0" * 64
    else:
        changed[binding_field] = "sha256:" + "0" * 64
    changed = calibration.seal_record(
        {key: value for key, value in changed.items() if key != "record_sha256"}
    )
    changed_path = tmp_path / authority_id / record_path.name
    changed_path.parent.mkdir(parents=True)
    changed_path.write_bytes(calibration.canonical_json_bytes(changed))
    argv = _published_validate_a1_argv()
    argv[argv.index(record_option) + 1] = str(changed_path.resolve())
    argv[argv.index(digest_option) + 1] = changed["record_sha256"]

    completed = _run_reference_calibration_cli(argv)

    assert completed.returncode == 2
    assert completed.stdout == b""


@pytest.fixture
def canonical_reference_record(
    tmp_path: Path,
    reference_repository_factory,
) -> dict[str, Any]:
    return _build_reference_record(tmp_path, reference_repository_factory())


def test_task3a_closed_reference_product_or_nonpromotable_disposition_exists() -> None:
    calibration = _calibration_module()

    assert REFERENCE_SCHEMA.is_file()
    schema = _json_record(REFERENCE_SCHEMA)
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(REFERENCE_TOP_LEVEL_FIELDS)
    assert set(schema["required"]) == set(REFERENCE_TOP_LEVEL_FIELDS)
    if REFERENCE_RECORD.is_file():
        record = _json_record(REFERENCE_RECORD)
        loaded = calibration.load_reference_product(
            REFERENCE_RECORD,
            schema_path=REFERENCE_SCHEMA,
            expected_record_sha256=record["record_sha256"],
        )

        assert isinstance(loaded, calibration.ReferenceProduct)
        assert loaded.record == record
        return

    assert REFERENCE_DISPOSITION.is_file()
    disposition = _json_record(REFERENCE_DISPOSITION)
    assert REFERENCE_DISPOSITION.read_bytes() == calibration.canonical_json_bytes(
        disposition
    )
    assert set(disposition) == {
        "schema_version",
        "package_status",
        "terminal_result",
        "scale_rejection",
        "successor_design",
        "task4_eligible",
        "reference_promotion_eligible",
        "reference_promotion_requires",
        "record_sha256",
    }
    assert calibration.validate_record_sha256(disposition) == disposition[
        "record_sha256"
    ]
    assert disposition["schema_version"] == "es_f1_reference_disposition.v1"
    assert (
        disposition["package_status"]
        == "SUPERSEDED_PRELAUNCH_SCOPE_TOO_SMALL"
    )
    assert disposition["terminal_result"] == "GREEN_TERMINAL_SCALE_REJECTION"
    assert disposition["scale_rejection"] == {
        "byte_count": 937062,
        "capture": "ES_F1_TASK3A_SCALE_REJECTION",
        "inclusive_band": {"maximum": 10000, "minimum": 5000},
        "observed_implementation_additions": 615,
        "path": (
            "/home/ollie/.local/state/orchestrator/es-reference-products/captures/"
            "task3a-24d907a-attempt-09/scale-rejection.json"
        ),
        "result": "REJECTED_OUT_OF_BAND",
        "sha256": (
            "sha256:79883e9e098463fc5f7a927ab7762cc8172408cc62763d68ee6cf538ad9a0692"
        ),
    }
    assert disposition["successor_design"] == {
        "commit": "69f242939732b6cebb3c698bd465172a02fbddcd",
        "path": "docs/superpowers/specs/2026-08-06-es-f1v2-config-ownership-task-design.md",
    }
    assert disposition["task4_eligible"] is False
    assert disposition["reference_promotion_eligible"] is False
    assert disposition["reference_promotion_requires"] == (
        "experiments/orc_effectiveness/f1_es/reference-product.json"
    )


def test_task3a_reference_record_has_exact_fields_and_self_digest(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    record = canonical_reference_record

    assert len(record) == len(REFERENCE_TOP_LEVEL_FIELDS)
    assert set(record) == set(REFERENCE_TOP_LEVEL_FIELDS)
    assert tuple(record["bindings"]) == REFERENCE_BINDING_IDS
    assert len(record["bindings"]) == len(REFERENCE_BINDING_IDS)
    assert calibration.validate_record_sha256(record) == record["record_sha256"]
    for binding in record["bindings"].values():
        assert not Path(binding["path"]).is_absolute()
        assert ".." not in Path(binding["path"]).parts
        if "schema_path" in binding:
            assert not Path(binding["schema_path"]).is_absolute()
            assert ".." not in Path(binding["schema_path"]).parts
    loaded = _load_reference_product(calibration, tmp_path, record)
    assert isinstance(loaded, calibration.ReferenceProduct)
    assert len(loaded.record) == len(REFERENCE_TOP_LEVEL_FIELDS)
    assert set(loaded.record) == set(REFERENCE_TOP_LEVEL_FIELDS)

    stale = copy.deepcopy(record)
    stale["metric"]["implementation_additions"] += 1
    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, stale, name="stale.json")


@pytest.mark.parametrize("mutation", ["missing", "extra", "renamed"])
def test_task3a_reference_rejects_nonclosed_binding_domain(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    bindings = changed["bindings"]
    if mutation == "missing":
        bindings.pop(REFERENCE_BINDING_IDS[-1])
    elif mutation == "extra":
        bindings["unexpected_authority"] = copy.deepcopy(
            bindings[REFERENCE_BINDING_IDS[0]]
        )
    else:
        renamed = bindings.pop(REFERENCE_BINDING_IDS[0])
        bindings["renamed_preedit_policy"] = renamed
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_reference_repository_patch_and_external_cas_are_reopenable(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    task_package = importlib.import_module("scripts.experiments.es.task_package")
    record = canonical_reference_record
    lineage = record["lineage"]
    repository = Path(record["repository"]["locator"])

    assert _run_git(repository, "rev-parse", "--is-bare-repository") == b"true\n"
    assert _run_git(repository, "remote") == b""
    assert _run_git(
        repository,
        "for-each-ref",
        "--format=%(refname) %(objectname)",
    ).decode("ascii").splitlines() == [
        f"{REFERENCE_REF} {lineage['reference_commit']}"
    ]
    assert _run_git(
        repository,
        "rev-list",
        "--parents",
        "--topo-order",
        "--all",
    ).decode("ascii").splitlines() == [
        f"{lineage['reference_commit']} {lineage['task_seed_commit']}",
        f"{lineage['task_seed_commit']} {lineage['projection_commit']}",
        lineage["projection_commit"],
    ]
    assert _run_git(
        repository,
        "rev-parse",
        f"{lineage['reference_commit']}^{{tree}}",
    ).decode("ascii").strip() == lineage["reference_tree"]
    assert task_package.directory_snapshot_digest(repository) == record["repository"][
        "repository_snapshot_sha256"
    ]

    store = record["evidence_store"]
    assert set(store) == {"algorithm", "root", "members"}
    assert store["algorithm"] == "sha256"
    assert [row["member_id"] for row in store["members"]] == list(
        REFERENCE_CAS_MEMBER_IDS
    )
    root = Path(store["root"])
    for member in store["members"]:
        assert set(member) == {
            "member_id",
            "cas_relative_path",
            "byte_count",
            "sha256",
        }
        digest = member["sha256"].removeprefix("sha256:")
        assert member["cas_relative_path"] == f"{digest}/payload"
        member_path = root / member["cas_relative_path"]
        assert member_path.is_file() and not member_path.is_symlink()
        payload = member_path.read_bytes()
        assert len(payload) == member["byte_count"]
        assert hashlib.sha256(payload).hexdigest() == digest

    patch_member = next(
        row
        for row in store["members"]
        if row["member_id"] == record["patch"]["member_id"]
    )
    assert record["patch"]["member_id"] == "canonical_patch"
    assert record["patch"]["base"] == lineage["task_seed_commit"]
    assert record["patch"]["target"] == lineage["reference_commit"]
    assert record["patch"]["format"] == "git-diff-binary-full-index.v1"
    assert record["patch"]["argv"] == [
        "/usr/bin/git",
        "-C",
        str(repository),
        "diff",
        "--patch",
        "--binary",
        "--full-index",
        "--no-color",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        *calibration.PINNED_GIT_DIFF_CONTROLS,
        record["patch"]["base"],
        record["patch"]["target"],
        "--",
    ]
    captured_patch = (root / patch_member["cas_relative_path"]).read_bytes()
    reproduced_patch = subprocess.run(
        record["patch"]["argv"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    ).stdout
    assert captured_patch == reproduced_patch

    loaded = _load_reference_product(calibration, tmp_path, record)
    assert loaded.record["repository"] == record["repository"]


@pytest.mark.parametrize("mutation", ["base", "target", "member_id"])
def test_task3a_reference_rejects_patch_lineage_or_member_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    patch = changed["patch"]
    lineage = changed["lineage"]
    if mutation == "base":
        patch["base"] = lineage["projection_commit"]
        patch["argv"][-3] = lineage["projection_commit"]
    elif mutation == "target":
        patch["target"] = lineage["task_seed_commit"]
        patch["argv"][-2] = lineage["task_seed_commit"]
    else:
        patch["member_id"] = "candidate_evidence"
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "duplicate", "reordered"],
)
def test_task3a_reference_rejects_nonclosed_cas_member_domain(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    members = changed["evidence_store"]["members"]
    if mutation == "missing":
        members.pop()
    elif mutation == "extra":
        extra = copy.deepcopy(members[-1])
        extra["member_id"] = "unexpected_evidence"
        members.append(extra)
    elif mutation == "duplicate":
        members[1] = copy.deepcopy(members[0])
    else:
        members[0], members[1] = members[1], members[0]
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize("relation", ["at-repository", "inside-repository"])
def test_task3a_reference_rejects_cas_root_at_or_inside_bare_repository(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    relation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    repository = Path(changed["repository"]["locator"])
    changed["evidence_store"]["root"] = str(
        repository if relation == "at-repository" else repository / "objects"
    )
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_reference_rejects_cas_member_through_symlinked_digest_directory(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    member = _cas_member_row(canonical_reference_record, "canonical_patch")
    member_path = _cas_member_path(canonical_reference_record, "canonical_patch")
    digest_directory = member_path.parent
    outside_directory = tmp_path / "outside-cas-digest"
    shutil.move(str(digest_directory), outside_directory)
    digest_directory.symlink_to(outside_directory, target_is_directory=True)

    payload = (outside_directory / "payload").read_bytes()
    assert len(payload) == member["byte_count"]
    assert "sha256:" + hashlib.sha256(payload).hexdigest() == member["sha256"]
    assert digest_directory.is_symlink()
    assert member_path.is_file() and not member_path.is_symlink()

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, canonical_reference_record)


@pytest.mark.parametrize(
    "binding_id",
    [
        "preedit_policy",
        "source_census",
        "selector_manifest",
        "task0_review_adoption",
        "a1_anchor",
        "task_seed_manifest",
        "visible_task_contract",
        "evaluator_fixture_manifest",
        "governing_plan",
    ],
)
def test_task3a_reference_loader_reopens_bound_authorities(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    binding_id: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    changed["bindings"][binding_id]["sha256"] = "sha256:" + "0" * 64
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize("mutation", ["absolute", "traversal"])
def test_task3a_reference_rejects_noncanonical_checked_in_authority_paths(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    binding = changed["bindings"]["source_census"]
    binding["path"] = (
        str(SOURCE_CENSUS.resolve())
        if mutation == "absolute"
        else "docs/plans/evidence/../source-census.json"
    )
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "binding_id",
    [
        "preedit_policy",
        "source_census",
        "selector_manifest",
        "task0_review_adoption",
        "a1_anchor",
        "task_seed_manifest",
        "visible_task_contract",
    ],
)
def test_task3a_reference_rejects_bound_record_digest_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    binding_id: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    changed["bindings"][binding_id]["record_sha256"] = "sha256:" + "0" * 64
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "binding_id",
    [
        "preedit_policy",
        "source_census",
        "selector_manifest",
        "task0_review_adoption",
        "a1_anchor",
        "task_seed_manifest",
        "visible_task_contract",
    ],
)
def test_task3a_reference_rejects_bound_schema_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    binding_id: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    changed["bindings"][binding_id]["schema_sha256"] = "sha256:" + "0" * 64
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_reference_rejects_resealed_task0_adoption_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    adoption = _json_record(TASK0_REVIEW_ADOPTION)
    adoption["reviews"].reverse()
    adoption = _sealed_reference_record(calibration, adoption)
    with tempfile.TemporaryDirectory(
        prefix="task3a-adoption-drift-",
        dir=ROOT / ".tmp",
    ) as drift_dir:
        adoption_path = Path(drift_dir) / "task0-review-adoption-drift.json"
        adoption_path.write_bytes(calibration.canonical_json_bytes(adoption))

        changed = copy.deepcopy(canonical_reference_record)
        changed["bindings"]["task0_review_adoption"] = _authority_binding(
            adoption_path,
            TASK0_REVIEW_ADOPTION_SCHEMA,
        )
        changed = _sealed_reference_record(calibration, changed)

        with pytest.raises(calibration.CalibrationError):
            _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "binding_id",
    ["reference_calibration", "f1_evaluator", "boundary_proof_runner"],
)
def test_task3a_reference_rejects_bound_tool_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    binding_id: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    changed["bindings"][binding_id]["sha256"] = "sha256:" + "0" * 64
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_metric_rows_bind_complete_production_assignments(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    record = canonical_reference_record
    rows = record["metric"]["rows"]
    responsibility_domain = set(record["structural_scope"]["responsibility_ids"])
    cluster_domain = set(record["structural_scope"]["cluster_domain"])
    production_rows = [
        row for row in rows if row["classification"] == "production_python"
    ]
    nonproduction_rows = [
        row for row in rows if row["classification"] != "production_python"
    ]

    assert rows
    assert set(record["metric"]) == {
        "metric_version",
        "git_contract_policy_sha256",
        "rows",
        "totals_by_classification",
        "implementation_additions",
        "implementation_deletions",
        "base_physical_lines",
        "candidate_postimage_physical_lines",
    }
    assert record["metric"]["git_contract_policy_sha256"] == (
        REFERENCE_GIT_POLICY_SHA256
    )
    assert tuple(record["metric"]["totals_by_classification"]) == (
        REFERENCE_CLASSIFICATIONS
    )
    assert len(production_rows) == len(REFERENCE_CLUSTER_BY_PATH)
    assert nonproduction_rows
    assert all(
        row["responsibility_ids"]
        and len(row["responsibility_ids"]) == len(set(row["responsibility_ids"]))
        and set(row["responsibility_ids"]) <= responsibility_domain
        and row["cluster_ids"]
        and len(row["cluster_ids"]) == len(set(row["cluster_ids"]))
        and set(row["cluster_ids"]) <= cluster_domain
        for row in production_rows
    )
    assert all(
        not row["responsibility_ids"] and not row["cluster_ids"]
        for row in nonproduction_rows
    )
    repository = Path(record["repository"]["locator"])
    reopened_base = _strict_text_tree_payloads(
        repository,
        record["lineage"]["task_seed_tree"],
    )
    reopened_candidate = _strict_text_tree_payloads(
        repository,
        record["lineage"]["reference_tree"],
    )
    expected_base_domain = {
        path: (leaf["blob_id"], leaf["mode"])
        for path, leaf in reopened_base.items()
    }
    expected_candidate_domain = {
        path: (leaf["blob_id"], leaf["mode"])
        for path, leaf in reopened_candidate.items()
    }
    actual_base_domain = {
        row["base_path"]: (row["base_blob_id"], row["base_mode"])
        for row in rows
        if row["base_path"] is not None
    }
    actual_candidate_domain = {
        row["candidate_path"]: (
            row["candidate_blob_id"],
            row["candidate_mode"],
        )
        for row in rows
        if row["candidate_path"] is not None
    }
    assert actual_base_domain == expected_base_domain
    assert actual_candidate_domain == expected_candidate_domain
    assert len(actual_base_domain) == sum(
        row["base_path"] is not None for row in rows
    )
    assert len(actual_candidate_domain) == sum(
        row["candidate_path"] is not None for row in rows
    )
    expected_unchanged = (
        set(reopened_base)
        & set(reopened_candidate)
        - set(REFERENCE_CLUSTER_BY_PATH)
    )
    unchanged_rows = {
        row["base_path"]
        for row in rows
        if row["change_kind"] == "unchanged"
    }
    assert unchanged_rows == expected_unchanged
    assert all(
        row["classification"] == "benchmark_task_seed_asset"
        for row in rows
        if row["base_path"] in expected_unchanged
    )
    expected_delta_fields = {
        "base_path",
        "candidate_path",
        "base_blob_id",
        "candidate_blob_id",
        "base_mode",
        "candidate_mode",
        "base_physical_lines",
        "candidate_physical_lines",
        "additions",
        "deletions",
        "change_kind",
        "classification",
        "responsibility_ids",
        "cluster_ids",
    }
    assert all(set(row) == expected_delta_fields for row in rows)
    loaded = _load_reference_product(calibration, tmp_path, record)
    assert loaded.record["metric"]["rows"] == rows


def test_task3a_reference_rejects_unexpected_changed_eligible_seed_path(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    row = next(
        row
        for row in changed["metric"]["rows"]
        if row["classification"] == "benchmark_task_seed_asset"
        and row["change_kind"] == "unchanged"
    )
    row["candidate_blob_id"] = "0" * 40
    row["candidate_physical_lines"] += 1
    row["additions"] = 1
    row["change_kind"] = "modify"
    totals = changed["metric"]["totals_by_classification"][
        "benchmark_task_seed_asset"
    ]
    totals["additions"] += 1
    totals["candidate_postimage_physical_lines"] += 1
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-responsibility",
        "duplicate-responsibility",
        "missing-cluster",
        "duplicate-cluster",
    ],
)
def test_task3a_reference_rejects_incomplete_or_duplicate_path_assignments(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    row = next(
        row
        for row in changed["metric"]["rows"]
        if row["classification"] == "production_python"
    )
    if mutation == "missing-responsibility":
        row["responsibility_ids"] = []
    elif mutation == "duplicate-responsibility":
        row["responsibility_ids"].append(row["responsibility_ids"][0])
    elif mutation == "missing-cluster":
        row["cluster_ids"] = []
    else:
        row["cluster_ids"].append(row["cluster_ids"][0])
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_structural_scope_has_four_changed_clusters_and_frozen_edges(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    selector = _json_record(SELECTOR_MANIFEST)
    record = canonical_reference_record
    scope = record["structural_scope"]

    expected_clusters = list(
        dict.fromkeys(
            cluster_id
            for row in record["metric"]["rows"]
            if row["classification"] == "production_python"
            for cluster_id in row["cluster_ids"]
        )
    )
    assert scope["changed_cluster_ids"] == expected_clusters
    assert len(expected_clusters) >= 4
    assert [
        (row["edge_id"], row["from_cluster"], row["to_cluster"])
        for row in scope["integration_edges"]
    ] == [
        (row["edge_id"], row["from_cluster"], row["to_cluster"])
        for row in selector["feasibility_spike"]["integration_edges"]
    ]
    edge_pairs = [
        (edge["producer"]["path"], edge["consumer"]["path"])
        for edge in scope["integration_edges"]
    ]
    assert edge_pairs == [
        (
            REFERENCE_EDGE_STATIC_SPECS[edge["edge_id"]]["producer_path"],
            REFERENCE_EDGE_STATIC_SPECS[edge["edge_id"]]["consumer_path"],
        )
        for edge in scope["integration_edges"]
    ]
    edge_paths = {path for pair in edge_pairs for path in pair}
    assert edge_paths == {REFERENCE_REGISTRY_PATH, *REFERENCE_CHAIN_PATHS}
    repository = Path(record["repository"]["locator"])
    target_tree = record["lineage"]["reference_tree"]
    for path in REFERENCE_CHAIN_PATHS:
        absent = subprocess.run(
            (
                "/usr/bin/git",
                "-C",
                str(repository),
                "cat-file",
                "-e",
                f"{record['lineage']['task_seed_tree']}:{path}",
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
        assert absent.returncode != 0
    registry_seed_blob = _run_git(
        repository,
        "rev-parse",
        f"{record['lineage']['task_seed_tree']}:{REFERENCE_REGISTRY_PATH}",
    )
    registry_reference_blob = _run_git(
        repository,
        "rev-parse",
        f"{target_tree}:{REFERENCE_REGISTRY_PATH}",
    )
    assert registry_seed_blob != registry_reference_blob
    production_rows = {
        row["candidate_path"]: row
        for row in record["metric"]["rows"]
        if row["classification"] == "production_python"
    }
    assert edge_paths <= set(production_rows)
    assert all(
        production_rows[path]["change_kind"] != "unchanged"
        for path in edge_paths
    )
    for edge in scope["integration_edges"]:
        static_spec = REFERENCE_EDGE_STATIC_SPECS[edge["edge_id"]]
        for role, endpoint in (
            ("producer", edge["producer"]),
            ("consumer", edge["consumer"]),
        ):
            actual = _run_git(
                repository,
                "rev-parse",
                f"{target_tree}:{endpoint['path']}",
            ).decode("ascii").strip()
            assert endpoint["blob_id"] == actual
            payload = _run_git(
                repository,
                "show",
                f"{target_tree}:{endpoint['path']}",
            )
            assert b"_es_reference_" not in payload
            parsed = ast.parse(payload.decode("utf-8"))
            matching_nodes = [
                node
                for node in ast.walk(parsed)
                if type(node).__name__ == endpoint["node_kind"]
                and (
                    (
                        getattr(node, "name", None)
                        == static_spec["producer_name"]
                    )
                    if role == "producer"
                    else (
                        isinstance(node, ast.Call)
                        and (
                            (
                                static_spec["producer_owner"] is None
                                and isinstance(node.func, ast.Name)
                                and node.func.id
                                == static_spec["imported_binding"]
                            )
                            or (
                                static_spec["producer_owner"] is not None
                                and isinstance(node.func, ast.Attribute)
                                and node.func.attr
                                == static_spec["producer_name"]
                                and isinstance(node.func.value, ast.Name)
                                and node.func.value.id
                                == static_spec["imported_binding"]
                            )
                        )
                    )
                )
            ]
            assert len(matching_nodes) == 1
            node = matching_nodes[0]
            assert endpoint["symbol"] == static_spec["resolved_symbol"]
            if role == "producer" and static_spec["producer_owner"] is not None:
                assert isinstance(node, ast.FunctionDef)
                assert [
                    decorator.id
                    for decorator in node.decorator_list
                    if isinstance(decorator, ast.Name)
                ] == ["classmethod"]
            assert endpoint["span"] == {
                "line_start": node.lineno,
                "column_start": node.col_offset,
                "line_end": node.end_lineno,
                "column_end": node.end_col_offset,
            }
        evidence = edge["evidence"]
        producer_module = edge["producer"]["path"].removesuffix(".py").replace(
            "/", "."
        )
        assert evidence["evidence_kind"] == REFERENCE_EDGE_EVIDENCE_KIND
        assert evidence["evidence_semantics"] == REFERENCE_EDGE_EVIDENCE_SEMANTICS
        assert evidence["imported_module"] == producer_module
        assert evidence["imported_binding"] == static_spec["imported_binding"]
        assert evidence["lifecycle_report_member_id"] == "lifecycle_result"
        assert evidence["lifecycle_clause_ids"] == list(
            REFERENCE_EDGE_LIFECYCLE_CLAUSES[edge["edge_id"]]
        )
        assert evidence["consumer_blob_id"] == edge["consumer"]["blob_id"]
        assert evidence["resolved_producer_blob_id"] == edge["producer"][
            "blob_id"
        ]
        assert evidence["resolved_symbol"] == edge["producer"]["symbol"]
        consumer_payload = _run_git(
            repository,
            "show",
            f"{target_tree}:{edge['consumer']['path']}",
        )
        consumer_tree = ast.parse(consumer_payload.decode("utf-8"))
        imports = [
            node
            for node in consumer_tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == producer_module
            and any(
                alias.name == evidence["imported_binding"]
                and alias.asname is None
                for alias in node.names
            )
        ]
        assert len(imports) == 1
        assert evidence["import_span"] == {
            "line_start": imports[0].lineno,
            "column_start": imports[0].col_offset,
            "line_end": imports[0].end_lineno,
            "column_end": imports[0].end_col_offset,
        }
    loaded = _load_reference_product(calibration, tmp_path, record)
    assert loaded.record["structural_scope"] == scope


def test_task3a_static_edge_resolver_covers_qualified_classmethod() -> None:
    calibration = _calibration_module()
    edge_id = "01_identity_config_to_construction_adapters"
    resolution = calibration._resolve_reference_static_edge(
        edge_id=edge_id,
        producer_payload="".join(
            REFERENCE_CHAIN_SOURCE_LINES[REFERENCE_CHAIN_PATHS[0]]
        ).encode("utf-8"),
        consumer_payload="".join(
            REFERENCE_CHAIN_SOURCE_LINES[REFERENCE_CHAIN_PATHS[1]]
        ).encode("utf-8"),
    )

    assert resolution["producer"]["node_kind"] == "FunctionDef"
    assert resolution["producer"]["symbol"] == (
        "ExtensionIdentity.from_config"
    )
    assert resolution["consumer"]["node_kind"] == "Call"
    assert resolution["consumer"]["symbol"] == (
        "ExtensionIdentity.from_config"
    )
    assert resolution["imported_module"] == "ptycho_torch.extension_identity"
    assert resolution["imported_binding"] == "ExtensionIdentity"


def test_task3a_static_edge_resolver_covers_registry_public_route() -> None:
    calibration = _calibration_module()
    task_seed = _json_record(TASK_SEED_MANIFEST)
    registry_base = _run_git(
        Path(task_seed["repository"]["locator"]),
        "show",
        f"{task_seed['recipe']['commit']}:{REFERENCE_REGISTRY_PATH}",
    )
    resolution = calibration._resolve_reference_static_edge(
        edge_id="02_construction_adapters_to_persistence_rebuild",
        producer_payload=_reference_registry_source(registry_base, 3),
        consumer_payload="".join(
            REFERENCE_CHAIN_SOURCE_LINES[REFERENCE_CHAIN_PATHS[2]]
        ).encode("utf-8"),
    )

    assert resolution["producer"]["symbol"] == "resolve_generator"
    assert resolution["consumer"]["symbol"] == "resolve_generator"
    assert resolution["imported_module"] == "ptycho_torch.generators.registry"
    assert resolution["imported_binding"] == "resolve_generator"


@pytest.mark.parametrize("mutation", ["missing", "unsatisfied"])
def test_task3a_structural_scope_requires_authenticated_lifecycle_clauses(
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    lifecycle = _cas_json_record(canonical_reference_record, "lifecycle_result")
    clause_satisfaction = {
        row["clause_id"]: row["satisfied"]
        for row in lifecycle["lifecycle_result"]["lifecycle_observations"]
    }
    if mutation == "missing":
        clause_satisfaction.pop("F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY")
    else:
        clause_satisfaction["F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY"] = False

    with pytest.raises(calibration.CalibrationError):
        calibration._validate_reference_structural_scope(
            canonical_reference_record,
            repository=Path(canonical_reference_record["repository"]["locator"]),
            authorities=calibration._load_reference_authorities(
                canonical_reference_record
            ),
            lifecycle_clause_satisfaction=clause_satisfaction,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-import",
        "missing-import",
        "aliased-import",
        "shadowed-import",
        "ambiguous-import",
        "missing-call",
        "ambiguous-call",
        "shadowed-call",
    ],
)
def test_task3a_static_edge_resolver_fails_closed(
    mutation: str,
) -> None:
    calibration = _calibration_module()
    producer = "".join(
        REFERENCE_CHAIN_SOURCE_LINES[REFERENCE_CHAIN_PATHS[0]]
    ).encode("utf-8")
    consumer = "".join(
        REFERENCE_CHAIN_SOURCE_LINES[REFERENCE_CHAIN_PATHS[1]]
    )
    import_line = (
        "from ptycho_torch.extension_identity import "
        "ExtensionIdentity\n"
    )
    call_line = (
        "    identity = ExtensionIdentity.from_config(config)\n"
    )
    if mutation == "wrong-import":
        consumer = consumer.replace(
            "ptycho_torch.extension_identity",
            "ptycho_torch.extension_persistence",
        )
    elif mutation == "missing-import":
        consumer = consumer.replace(import_line, "")
    elif mutation == "aliased-import":
        consumer = consumer.replace(
            import_line,
            import_line.rstrip()
            + " as ImportedExtensionIdentity\n",
        )
    elif mutation == "shadowed-import":
        consumer = consumer.replace(
            import_line,
            import_line + "ExtensionIdentity = object\n",
        )
    elif mutation == "ambiguous-import":
        consumer = consumer.replace(import_line, import_line * 2)
    elif mutation == "missing-call":
        consumer = consumer.replace(
            call_line,
            "    identity = config\n",
        )
    elif mutation == "ambiguous-call":
        consumer = consumer.replace(
            call_line,
            call_line
            + "    duplicate = ExtensionIdentity.from_config(config)\n",
        )
    else:
        consumer = consumer.replace(
            call_line,
            "    ExtensionIdentity = object\n" + call_line,
        )

    with pytest.raises(calibration.CalibrationError):
        calibration._resolve_reference_static_edge(
            edge_id="01_identity_config_to_construction_adapters",
            producer_payload=producer,
            consumer_payload=consumer.encode("utf-8"),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "three-clusters",
        "missing-edge",
        "edge-drift",
        "producer-span",
        "consumer-span",
        "import-span",
        "imported-binding",
        "resolution-drift",
        "wrong-report",
        "wrong-clause-set",
        "semantics-drift",
    ],
)
def test_task3a_reference_rejects_incomplete_structural_scope(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    scope = changed["structural_scope"]
    if mutation == "three-clusters":
        scope["changed_cluster_ids"] = scope["changed_cluster_ids"][:3]
    elif mutation == "missing-edge":
        scope["integration_edges"].pop()
    elif mutation == "edge-drift":
        scope["integration_edges"][0]["to_cluster"] = "PERSISTENCE_REBUILD"
    elif mutation == "producer-span":
        scope["integration_edges"][0]["producer"]["span"]["line_start"] += 1
    elif mutation == "consumer-span":
        scope["integration_edges"][0]["consumer"]["span"]["line_start"] += 1
    elif mutation == "import-span":
        scope["integration_edges"][0]["evidence"]["import_span"][
            "line_start"
        ] += 1
    elif mutation == "imported-binding":
        scope["integration_edges"][0]["evidence"][
            "imported_binding"
        ] = "AliasedExtensionIdentity"
    elif mutation == "resolution-drift":
        scope["integration_edges"][0]["evidence"][
            "resolved_producer_blob_id"
        ] = "0" * 40
    elif mutation == "wrong-report":
        scope["integration_edges"][0]["evidence"][
            "lifecycle_report_member_id"
        ] = "candidate_evidence"
    elif mutation == "wrong-clause-set":
        scope["integration_edges"][0]["evidence"][
            "lifecycle_clause_ids"
        ] = ["F1-H09-CONSTRUCTION-REBUILD-EQUALITY"]
    else:
        scope["integration_edges"][0]["evidence"][
            "evidence_semantics"
        ] = "FUNCTION_LEVEL_RUNTIME_TRACE"
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize("implementation_lines", [5_000, 10_000])
def test_task3a_reference_scale_band_is_inclusive(
    tmp_path: Path,
    implementation_lines: int,
    reference_repository_factory,
) -> None:
    calibration = _calibration_module()
    record = _build_reference_record(
        tmp_path,
        reference_repository_factory(implementation_lines),
    )

    loaded = _load_reference_product(calibration, tmp_path, record)
    assert (
        loaded.record["metric"]["implementation_additions"]
        == implementation_lines
    )


@pytest.mark.parametrize("implementation_lines", [4_999, 10_001])
def test_task3a_reference_scale_band_rejects_outside_values(
    tmp_path: Path,
    implementation_lines: int,
    reference_repository_factory,
) -> None:
    calibration = _calibration_module()
    record = _build_reference_record(
        tmp_path,
        reference_repository_factory(implementation_lines),
    )

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, record)


def test_task3a_reference_rejects_padding_only_python_delta(
    tmp_path: Path,
    reference_repository_factory,
) -> None:
    calibration = _calibration_module()
    repository = reference_repository_factory(padding_only=True)
    changed = _build_reference_record(
        tmp_path,
        repository,
    )
    padding_row = next(
        row
        for row in changed["metric"]["rows"]
        if row["candidate_path"] == REFERENCE_PADDING_PATH
    )
    assert padding_row["base_path"] is None
    padding_tree = ast.parse(
        repository["candidate_payloads"][REFERENCE_PADDING_PATH].decode("utf-8")
    )
    assert len(padding_tree.body) == 1
    assert isinstance(padding_tree.body[0], ast.Expr)
    assert isinstance(padding_tree.body[0].value, ast.Constant)
    assert isinstance(padding_tree.body[0].value.value, str)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_desired_state_results_are_exact_ordered_task0_join(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    boundary = importlib.import_module("scripts.experiments.es.boundary_proofs")
    selector = _json_record(SELECTOR_MANIFEST)
    source_census = _json_record(SOURCE_CENSUS)
    boundary.validate_authority_bindings(selector, source_census)
    contract = boundary.validate_contract(
        selector,
        consumer_rows=source_census["consumer_rows"],
        expected_runner_sha256=BOUNDARY_PROOF_RUNNER_SHA256,
    )
    proof_record = canonical_reference_record["desired_state_proofs"]
    rows = proof_record["result_rows"]
    reference_tree = canonical_reference_record["lineage"]["reference_tree"]

    assert proof_record["runner_sha256"] == BOUNDARY_PROOF_RUNNER_SHA256
    assert proof_record["target_tree"] == reference_tree
    assert proof_record["execution"] == {
        "python": {
            "path": str(REFERENCE_PYTHON),
            "target": str(REFERENCE_PYTHON_TARGET),
            "version": REFERENCE_PYTHON_VERSION,
            "sha256": REFERENCE_PYTHON_SHA256,
        },
        "pytest_carrier": {
            "path": str(REFERENCE_PYTEST_CARRIER),
            "version": REFERENCE_PYTEST_CARRIER_VERSION,
            "sha256": REFERENCE_PYTEST_CARRIER_SHA256,
        },
    }
    assert len(rows) == 23
    assert [
        (
            row["proof_id"],
            row["ordinal"],
            row["selector_id"],
            row["witness_id"],
            row["consumer_id"],
            row["proof_kind"],
            row["witness_kind"],
        )
        for row in rows
    ] == [
        (
            spec.proof_id,
            spec.ordinal,
            spec.selector_id,
            spec.witness_id,
            spec.consumer_id,
            spec.proof_kind,
            witness.witness_kind,
        )
        for spec, witness in zip(
            contract.desired_specs,
            contract.witnesses,
            strict=True,
        )
    ]
    assert [row["ordinal"] for row in rows] == list(range(1, 24))
    assert all(row["target_tree"] == reference_tree for row in rows)
    assert all(row["mechanically_observed"] and row["passed"] for row in rows)
    assert sum(row["proof_kind"] == "boundary_runtime" for row in rows) == 21
    assert sum(row["proof_kind"] == "reference_absence" for row in rows) == 1
    assert sum(row["proof_kind"] == "non_cdi_static" for row in rows) == 1
    assert sum(row["witness_kind"] == "pytest_runtime" for row in rows) == 19
    assert (
        sum(row["witness_kind"] == "controller_pytest_runtime" for row in rows)
        == 1
    )
    assert sum(row["witness_kind"] == "runtime_probe" for row in rows) == 1
    assert sum(row["witness_kind"] == "static_ast" for row in rows) == 2
    loaded = _load_reference_product(calibration, tmp_path, canonical_reference_record)
    assert loaded.record["desired_state_proofs"] == proof_record


def test_task3a_desired_state_execution_manifest_projects_only_failing_static_targets() -> None:
    calibration = _calibration_module()
    selector = _json_record(SELECTOR_MANIFEST)
    source_census = _json_record(SOURCE_CENSUS)
    original = copy.deepcopy(selector)

    execution = calibration.build_desired_state_execution_manifest(
        selector,
        source_census=source_census,
    )

    assert selector == original
    assert set(execution) == {
        "provider_visible_pytest_selectors",
        "controller_only_proof_selectors",
        "coverage_witnesses",
        "desired_state_proof_specs",
    }
    assert execution["provider_visible_pytest_selectors"] == selector[
        "provider_visible_pytest_selectors"
    ]
    assert execution["coverage_witnesses"] == selector["coverage_witnesses"]
    assert execution["desired_state_proof_specs"] == selector[
        "desired_state_proof_specs"
    ]
    projected_targets = {
        ("CO-ABS-01", "archive/root_scripts/analysis/extract_reconstructions.py"),
        ("CO-NCDI-01", "ptycho/metadata.py"),
    }
    assert {
        (row["selector_id"], row["target_path"])
        for row in selector["baseline_characterization"]["witness_results"]
        if row["passed"] is False
    } == projected_targets
    for selector_id, target in projected_targets:
        source_row = next(
            row
            for row in selector["controller_only_proof_selectors"]
            if row["selector_id"] == selector_id
        )
        execution_row = next(
            row
            for row in execution["controller_only_proof_selectors"]
            if row["selector_id"] == selector_id
        )
        assert [row["path"] for row in source_row["input_bindings"]].count(
            target
        ) == 1
        assert target not in {row["path"] for row in execution_row["input_bindings"]}
        assert len(execution_row["input_bindings"]) == (
            len(source_row["input_bindings"]) - 1
        )
    source_other = [
        row
        for row in selector["controller_only_proof_selectors"]
        if row["selector_id"] not in {selector_id for selector_id, _ in projected_targets}
    ]
    execution_other = [
        row
        for row in execution["controller_only_proof_selectors"]
        if row["selector_id"] not in {selector_id for selector_id, _ in projected_targets}
    ]
    assert execution_other == source_other


def _candidate_expanded_provider_nodes(
    selector: dict[str, Any],
    *,
    builtin_architecture_ids: tuple[str, ...],
    witness_architecture_id: str,
) -> list[str]:
    collected: list[str] = []
    for row in selector["provider_visible_pytest_selectors"]:
        nodes = row["pytest_node_ids"]
        suffixes_by_prefix: dict[str, list[str]] = {}
        for node in nodes:
            if "[" not in node or not node.endswith("]"):
                continue
            prefix, suffix = node.rsplit("[", 1)
            suffixes_by_prefix.setdefault(prefix, []).append(suffix[:-1])
        expanded_prefixes = {
            prefix
            for prefix, suffixes in suffixes_by_prefix.items()
            if tuple(suffixes) == builtin_architecture_ids
        }
        emitted: set[str] = set()
        for node in nodes:
            prefix = node.rsplit("[", 1)[0] if "[" in node and node.endswith("]") else ""
            if prefix not in expanded_prefixes:
                collected.append(node)
                continue
            if prefix not in emitted:
                collected.extend(
                    f"{prefix}[{architecture_id}]"
                    for architecture_id in sorted(
                        (*builtin_architecture_ids, witness_architecture_id)
                    )
                )
                emitted.add(prefix)
    return collected


def test_task3a_provider_node_projection_accepts_only_complete_candidate_siblings() -> None:
    calibration = _calibration_module()
    selector = _json_record(SELECTOR_MANIFEST)
    source_census = _json_record(SOURCE_CENSUS)
    builtins = tuple(_json_record(VISIBLE_TASK_CONTRACT)["builtin_architectures"])
    execution = calibration.build_desired_state_execution_manifest(
        selector,
        source_census=source_census,
    )
    original = copy.deepcopy(execution)
    collected = _candidate_expanded_provider_nodes(
        selector,
        builtin_architecture_ids=builtins,
        witness_architecture_id=REFERENCE_WITNESS_ID,
    )

    projected = calibration.project_desired_state_provider_nodes(
        execution,
        collected_node_ids=collected,
        builtin_architecture_ids=builtins,
        witness_architecture_id=REFERENCE_WITNESS_ID,
    )

    assert execution == original
    assert sum(
        len(row["pytest_node_ids"])
        for row in projected["provider_visible_pytest_selectors"]
    ) == 481
    pv02 = next(
        row
        for row in projected["provider_visible_pytest_selectors"]
        if row["selector_id"] == "PV-02"
    )
    assert len(pv02["pytest_node_ids"]) == 30
    assert [
        node for node in pv02["pytest_node_ids"] if node.endswith("[reference_witness]")
    ] == [
        "tests/torch/test_construction_consolidation.py::"
        "test_registry_and_model_spec_construction_have_one_state_signature"
        "[reference_witness]",
        "tests/torch/test_construction_consolidation.py::"
        "test_registry_wrappers_delegate_to_the_single_application_factory"
        "[reference_witness]",
    ]
    assert [
        node
        for row in projected["provider_visible_pytest_selectors"]
        for node in row["pytest_node_ids"]
    ] == collected
    assert {
        key: value
        for key, value in projected.items()
        if key != "provider_visible_pytest_selectors"
    } == {
        key: value
        for key, value in original.items()
        if key != "provider_visible_pytest_selectors"
    }
    source_by_id = {
        row["selector_id"]: row
        for row in original["provider_visible_pytest_selectors"]
    }
    projected_by_id = {
        row["selector_id"]: row
        for row in projected["provider_visible_pytest_selectors"]
    }
    for selector_id, source in source_by_id.items():
        target = projected_by_id[selector_id]
        assert {
            key: value for key, value in target.items() if key != "pytest_node_ids"
        } == {
            key: value for key, value in source.items() if key != "pytest_node_ids"
        }
        assert [
            node for node in target["pytest_node_ids"] if node in source["pytest_node_ids"]
        ] == source["pytest_node_ids"]


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_baseline_node",
        "duplicate_node",
        "reordered_baseline_nodes",
        "wrong_witness_suffix",
        "missing_witness_sibling",
        "addition_outside_complete_builtin_group",
        "no_additions",
        "witness_is_builtin",
    ),
)
def test_task3a_provider_node_projection_rejects_any_other_collection_delta(
    mutation: str,
) -> None:
    calibration = _calibration_module()
    selector = _json_record(SELECTOR_MANIFEST)
    source_census = _json_record(SOURCE_CENSUS)
    builtins = tuple(_json_record(VISIBLE_TASK_CONTRACT)["builtin_architectures"])
    execution = calibration.build_desired_state_execution_manifest(
        selector,
        source_census=source_census,
    )
    collected = _candidate_expanded_provider_nodes(
        selector,
        builtin_architecture_ids=builtins,
        witness_architecture_id=REFERENCE_WITNESS_ID,
    )
    witness = REFERENCE_WITNESS_ID
    if mutation == "missing_baseline_node":
        collected.remove(selector["provider_visible_pytest_selectors"][0]["pytest_node_ids"][0])
    elif mutation == "duplicate_node":
        collected.insert(1, collected[0])
    elif mutation == "reordered_baseline_nodes":
        collected[0], collected[1] = collected[1], collected[0]
    elif mutation == "wrong_witness_suffix":
        index = next(
            index for index, node in enumerate(collected) if node.endswith(f"[{witness}]")
        )
        collected[index] = collected[index].replace(witness, "other_witness")
    elif mutation == "missing_witness_sibling":
        index = next(
            index for index, node in enumerate(collected) if node.endswith(f"[{witness}]")
        )
        collected.pop(index)
    elif mutation == "addition_outside_complete_builtin_group":
        collected.append(
            "tests/torch/test_generator_registry.py::"
            f"test_registry_keys_match_contract[{witness}]"
        )
    elif mutation == "no_additions":
        collected = [
            node
            for row in selector["provider_visible_pytest_selectors"]
            for node in row["pytest_node_ids"]
        ]
    elif mutation == "witness_is_builtin":
        witness = builtins[0]
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(mutation)

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.project_desired_state_provider_nodes(
            execution,
            collected_node_ids=collected,
            builtin_architecture_ids=builtins,
            witness_architecture_id=witness,
        )

    assert caught.value.code == "reference_execution_projection_invalid"


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_from_owner",
        "bound_by_other_selector",
        "would_empty_owner",
        "unobserved_baseline",
        "no_failing_baseline",
    ),
)
def test_task3a_desired_state_execution_manifest_fails_closed_on_ambiguous_projection(
    mutation: str,
) -> None:
    calibration = _calibration_module()
    selector = _json_record(SELECTOR_MANIFEST)
    source_census = _json_record(SOURCE_CENSUS)
    absence_target = "archive/root_scripts/analysis/extract_reconstructions.py"
    absence_selector = next(
        row
        for row in selector["controller_only_proof_selectors"]
        if row["selector_id"] == "CO-ABS-01"
    )
    target_binding = next(
        row
        for row in absence_selector["input_bindings"]
        if row["path"] == absence_target
    )
    if mutation == "missing_from_owner":
        absence_selector["input_bindings"] = [
            row
            for row in absence_selector["input_bindings"]
            if row["path"] != absence_target
        ]
    elif mutation == "bound_by_other_selector":
        other = next(
            row
            for row in selector["controller_only_proof_selectors"]
            if row["selector_id"] != "CO-ABS-01"
        )
        other["input_bindings"].append(copy.deepcopy(target_binding))
    elif mutation == "would_empty_owner":
        absence_selector["input_bindings"] = [copy.deepcopy(target_binding)]
    elif mutation == "unobserved_baseline":
        failed = next(
            row
            for row in selector["baseline_characterization"]["witness_results"]
            if row["passed"] is False
        )
        failed["mechanically_observed"] = False
    elif mutation == "no_failing_baseline":
        expected_by_witness = {
            row["witness_id"]: row["expected_result"]
            for row in selector["desired_state_proof_specs"]
        }
        for row in selector["baseline_characterization"]["witness_results"]:
            if row["passed"] is False:
                row["observation"] = copy.deepcopy(
                    expected_by_witness[row["witness_id"]]
                )
                row["observation_sha256"] = "sha256:" + hashlib.sha256(
                    calibration.canonical_json_bytes(row["observation"])
                ).hexdigest()
                row["passed"] = True
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(mutation)
    selector = calibration.seal_record(selector)

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.build_desired_state_execution_manifest(
            selector,
            source_census=source_census,
        )

    assert caught.value.code == "reference_execution_projection_invalid"


@pytest.mark.parametrize("mutation", ("missing", "failed"))
def test_task3a_reference_rejects_missing_or_failed_co_ncdi_01_result(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    rows = changed["desired_state_proofs"]["result_rows"]
    index = next(
        index
        for index, row in enumerate(rows)
        if row["selector_id"] == "CO-NCDI-01"
    )
    assert rows[index]["proof_kind"] == "non_cdi_static"
    if mutation == "missing":
        rows.pop(index)
    else:
        rows[index]["passed"] = False
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(
            calibration,
            tmp_path,
            changed,
            name=f"reference-product-co-ncdi-01-{mutation}.json",
        )


def test_task3a_desired_state_orchestration_uses_full_bound_contract_without_live_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    canonical_reference_record: dict[str, Any],
    reference_repository_factory,
) -> None:
    calibration = _calibration_module()
    boundary = importlib.import_module("scripts.experiments.es.boundary_proofs")
    repository = reference_repository_factory()
    workspace = _materialize_reference_workspace(repository, tmp_path.name)
    selector = _json_record(SELECTOR_MANIFEST)
    source_census = _json_record(SOURCE_CENSUS)
    events: list[str] = []
    validation_calls: list[dict[str, Any]] = []
    collection_calls: list[dict[str, Any]] = []
    execution_calls: list[dict[str, Any]] = []
    builtins = tuple(_json_record(VISIBLE_TASK_CONTRACT)["builtin_architectures"])
    collected_provider_nodes = _candidate_expanded_provider_nodes(
        selector,
        builtin_architecture_ids=builtins,
        witness_architecture_id=REFERENCE_WITNESS_ID,
    )

    def recording_validation_stub(selector_manifest, source_census_record):
        events.append("validate_authority_bindings")
        validation_calls.append(
            {
                "selector_manifest": copy.deepcopy(selector_manifest),
                "source_census": copy.deepcopy(source_census_record),
            }
        )

    def recording_execution_stub(selector_manifest, **kwargs):
        events.append("execute_desired_state")
        execution_calls.append(
            {
                "selector_manifest": copy.deepcopy(selector_manifest),
                "kwargs": copy.deepcopy(kwargs),
                "workspace_head": _run_git(
                    Path(kwargs["workspace"]), "rev-parse", "HEAD"
                ).decode("ascii").strip(),
                "workspace_tree": _run_git(
                    Path(kwargs["workspace"]), "rev-parse", "HEAD^{tree}"
                ).decode("ascii").strip(),
                "workspace_status": _run_git(
                    Path(kwargs["workspace"]), "status", "--porcelain=v1"
                ),
            }
        )
        return copy.deepcopy(
            canonical_reference_record["desired_state_proofs"]["result_rows"]
        )

    def recording_collection_stub(contract, **kwargs):
        events.append("collect_provider_nodes")
        collection_calls.append(
            {
                "selector_ids": [row.selector_id for row in contract.provider_selectors],
                "kwargs": copy.deepcopy(kwargs),
            }
        )
        return {"node_ids": copy.deepcopy(collected_provider_nodes)}

    monkeypatch.setattr(
        boundary,
        "validate_authority_bindings",
        recording_validation_stub,
    )
    monkeypatch.setattr(
        boundary,
        "execute_desired_state",
        recording_execution_stub,
    )
    monkeypatch.setattr(
        boundary,
        "_run_pytest_observation",
        recording_collection_stub,
    )
    loaded = _load_reference_product(
        calibration,
        tmp_path,
        canonical_reference_record,
    )
    assert events == []
    assert validation_calls == []
    assert collection_calls == []
    assert execution_calls == []

    result = calibration.execute_reference_desired_state(
        loaded,
        workspace=workspace,
    )
    assert result == canonical_reference_record["desired_state_proofs"][
        "result_rows"
    ]
    assert events == [
        "validate_authority_bindings",
        "collect_provider_nodes",
        "execute_desired_state",
    ]
    assert validation_calls == [
        {
            "selector_manifest": selector,
            "source_census": source_census,
        }
    ]
    assert len(collection_calls) == 1
    collection_call = collection_calls[0]
    assert collection_call["selector_ids"] == [f"PV-{ordinal:02d}" for ordinal in range(1, 20)]
    assert collection_call["kwargs"]["collect_only"] is True
    assert Path(collection_call["kwargs"]["workspace"]) == workspace.resolve()
    assert len(execution_calls) == 1
    call = execution_calls[0]
    execution_selector = call["selector_manifest"]
    assert set(execution_selector) == {
        "provider_visible_pytest_selectors",
        "controller_only_proof_selectors",
        "coverage_witnesses",
        "desired_state_proof_specs",
    }
    assert [
        node
        for row in execution_selector["provider_visible_pytest_selectors"]
        for node in row["pytest_node_ids"]
    ] == collected_provider_nodes
    for source, target in zip(
        selector["provider_visible_pytest_selectors"],
        execution_selector["provider_visible_pytest_selectors"],
        strict=True,
    ):
        assert {
            key: value for key, value in target.items() if key != "pytest_node_ids"
        } == {
            key: value for key, value in source.items() if key != "pytest_node_ids"
        }
    assert execution_selector["coverage_witnesses"] == selector[
        "coverage_witnesses"
    ]
    assert execution_selector["desired_state_proof_specs"] == selector[
        "desired_state_proof_specs"
    ]
    expected_controllers = copy.deepcopy(
        selector["controller_only_proof_selectors"]
    )
    projected_targets = {
        ("CO-ABS-01", "archive/root_scripts/analysis/extract_reconstructions.py"),
        ("CO-NCDI-01", "ptycho/metadata.py"),
    }
    for selector_id, target in projected_targets:
        projected_selector = next(
            row for row in expected_controllers if row["selector_id"] == selector_id
        )
        removed = [
            row for row in projected_selector["input_bindings"] if row["path"] == target
        ]
        assert len(removed) == 1
        projected_selector["input_bindings"] = [
            row for row in projected_selector["input_bindings"] if row["path"] != target
        ]
    assert execution_selector["controller_only_proof_selectors"] == (
        expected_controllers
    )
    assert _json_record(SELECTOR_MANIFEST) == selector
    kwargs = call["kwargs"]
    assert kwargs["consumer_rows"] == source_census["consumer_rows"]
    assert len(kwargs["consumer_rows"]) == 1_959
    assert Path(kwargs["workspace"]) == workspace.resolve()
    assert call["workspace_head"] == canonical_reference_record["lineage"][
        "reference_commit"
    ]
    assert call["workspace_tree"] == canonical_reference_record["lineage"][
        "reference_tree"
    ]
    assert call["workspace_status"] == b""
    assert kwargs["expected_tree"] == call["workspace_tree"]
    assert kwargs["expected_runner_sha256"] == BOUNDARY_PROOF_RUNNER_SHA256
    execution = loaded.record["desired_state_proofs"]["execution"]
    assert execution == {
        "python": {
            "path": str(REFERENCE_PYTHON),
            "target": str(REFERENCE_PYTHON_TARGET),
            "version": REFERENCE_PYTHON_VERSION,
            "sha256": REFERENCE_PYTHON_SHA256,
        },
        "pytest_carrier": {
            "path": str(REFERENCE_PYTEST_CARRIER),
            "version": REFERENCE_PYTEST_CARRIER_VERSION,
            "sha256": REFERENCE_PYTEST_CARRIER_SHA256,
        },
    }
    assert boundary.PINNED_PYTHON == REFERENCE_PYTHON
    assert boundary.PINNED_PYTHON_TARGET == REFERENCE_PYTHON_TARGET
    assert boundary.PINNED_PYTHON_VERSION == REFERENCE_PYTHON_VERSION
    assert boundary.PINNED_PYTHON_SHA256 == REFERENCE_PYTHON_SHA256
    assert Path(kwargs["python"]) == Path(execution["python"]["path"])
    assert boundary.PINNED_PYTEST_CARRIER == REFERENCE_PYTEST_CARRIER
    assert boundary.PINNED_PYTEST_CARRIER_VERSION == (
        REFERENCE_PYTEST_CARRIER_VERSION
    )
    assert boundary.PINNED_PYTEST_CARRIER_SHA256 == (
        REFERENCE_PYTEST_CARRIER_SHA256
    )
    assert Path(kwargs["pytest_carrier"]) == Path(
        execution["pytest_carrier"]["path"]
    )
    assert kwargs["expected_pytest_carrier_sha256"] == (
        REFERENCE_PYTEST_CARRIER_SHA256
    )
    assert kwargs["expected_result_rows"] == result
    assert _json_record(PREEDIT_POLICY)["selector_policy"]["pytest_carrier"] == {
        "executable": str(REFERENCE_PYTEST_CARRIER),
        "version": REFERENCE_PYTEST_CARRIER_VERSION,
        "sha256": REFERENCE_PYTEST_CARRIER_SHA256,
        "tmp_isolation": "private_tmpfs",
    }


def _assert_reference_execution_rejected_before_boundary(
    calibration,
    monkeypatch: pytest.MonkeyPatch,
    reference,
    *,
    workspace: Path,
) -> None:
    boundary = importlib.import_module("scripts.experiments.es.boundary_proofs")
    events: list[str] = []

    def recording_validation_stub(*_args, **_kwargs):
        events.append("validate_authority_bindings")

    def recording_execution_stub(*_args, **_kwargs):
        events.append("execute_desired_state")
        return []

    monkeypatch.setattr(
        boundary,
        "validate_authority_bindings",
        recording_validation_stub,
    )
    monkeypatch.setattr(
        boundary,
        "execute_desired_state",
        recording_execution_stub,
    )
    rejected = False
    try:
        calibration.execute_reference_desired_state(reference, workspace=workspace)
    except calibration.CalibrationError:
        rejected = True

    assert events == []
    assert rejected is True


def test_task3a_reference_execution_rejects_resealed_post_load_authority_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    canonical_reference_record: dict[str, Any],
    reference_repository_factory,
) -> None:
    calibration = _calibration_module()
    repository = reference_repository_factory()
    workspace = _materialize_reference_workspace(
        repository,
        f"post-load-mutation-{tmp_path.name}",
    )
    loaded = _load_reference_product(
        calibration,
        tmp_path,
        canonical_reference_record,
    )
    changed_observation = {"path_absent": False}
    selector = loaded._selector_manifest
    selector["coverage_witnesses"][0]["expected_result"] = copy.deepcopy(
        changed_observation
    )
    selector["desired_state_proof_specs"][0]["expected_result"] = copy.deepcopy(
        changed_observation
    )
    resealed_selector = calibration.seal_record(
        {key: value for key, value in selector.items() if key != "record_sha256"}
    )
    selector.clear()
    selector.update(resealed_selector)
    result_row = loaded.record["desired_state_proofs"]["result_rows"][0]
    assert result_row["witness_kind"] == "static_ast"
    result_row["observation"] = copy.deepcopy(changed_observation)
    result_row["observation_sha256"] = (
        "sha256:"
        + hashlib.sha256(
            calibration.canonical_json_bytes(changed_observation)
        ).hexdigest()
    )
    resealed_record = _sealed_reference_record(calibration, loaded.record)
    loaded.record.clear()
    loaded.record.update(resealed_record)
    assert calibration.validate_record_sha256(loaded.record) == loaded.record[
        "record_sha256"
    ]

    _assert_reference_execution_rejected_before_boundary(
        calibration,
        monkeypatch,
        loaded,
        workspace=workspace,
    )


def test_task3a_reference_execution_reopens_external_evidence_after_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    canonical_reference_record: dict[str, Any],
    reference_repository_factory,
) -> None:
    calibration = _calibration_module()
    repository = reference_repository_factory()
    workspace = _materialize_reference_workspace(
        repository,
        f"external-drift-{tmp_path.name}",
    )
    loaded = _load_reference_product(
        calibration,
        tmp_path,
        canonical_reference_record,
    )
    evidence_path = _cas_member_path(
        canonical_reference_record,
        "candidate_evidence",
    )
    evidence_path.write_bytes(evidence_path.read_bytes() + b" ")

    _assert_reference_execution_rejected_before_boundary(
        calibration,
        monkeypatch,
        loaded,
        workspace=workspace,
    )


def test_task3a_reference_execution_rejects_directly_forged_reference_product(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    canonical_reference_record: dict[str, Any],
    reference_repository_factory,
) -> None:
    calibration = _calibration_module()
    repository = reference_repository_factory()
    workspace = _materialize_reference_workspace(
        repository,
        f"forged-reference-{tmp_path.name}",
    )
    forged = calibration.ReferenceProduct(
        record=copy.deepcopy(canonical_reference_record),
        _selector_manifest=_json_record(SELECTOR_MANIFEST),
        _source_census=_json_record(SOURCE_CENSUS),
    )

    _assert_reference_execution_rejected_before_boundary(
        calibration,
        monkeypatch,
        forged,
        workspace=workspace,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "baseline-substitution",
        "wrong-tree",
        "runner-drift",
    ],
)
def test_task3a_reference_rejects_invalid_desired_state_result_join(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    proofs = changed["desired_state_proofs"]
    rows = proofs["result_rows"]
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        extra = copy.deepcopy(rows[-1])
        extra["proof_id"] = "proof-extra"
        extra["ordinal"] = 24
        rows.append(extra)
    elif mutation == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    elif mutation == "baseline-substitution":
        proofs["result_rows"] = copy.deepcopy(
            _json_record(SELECTOR_MANIFEST)["baseline_characterization"][
                "witness_results"
            ]
        )
    elif mutation == "wrong-tree":
        rows[0]["target_tree"] = "0" * 40
    else:
        proofs["runner_sha256"] = "sha256:" + "0" * 64
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_evaluator_evidence_has_complete_lifecycle_and_hard_clause_order(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    visible = _json_record(VISIBLE_TASK_CONTRACT)
    visible_checks = _json_record(VISIBLE_CHECK_MANIFEST)
    fixture_manifest = _json_record(EVALUATOR_FIXTURE_MANIFEST)
    evidence = canonical_reference_record["evaluator_evidence"]
    architectures = [
        *visible["builtin_architectures"],
        REFERENCE_WITNESS_ID,
    ]
    stages = visible["required_lifecycle_stages"]
    hard_clause_ids = [row["id"] for row in visible["hard_contract"]]

    assert evidence["report_member_ids"] == {
        "candidate_evidence": "candidate_evidence",
        "visible_check_result": "visible_check_result",
        "registry_signature_report": "registry_signature_report",
        "artifact_fixture_verification": "artifact_fixture_verification",
        "lifecycle_result": "lifecycle_result",
        "hard_evaluation": "hard_evaluation",
    }
    assert len(architectures) == 15
    assert len(stages) == 12
    assert [clause_id.split("-", 2)[1] for clause_id in hard_clause_ids] == [
        f"H{ordinal:02d}" for ordinal in range(1, 11)
    ]
    assert evidence["architecture_ids"] == architectures
    assert evidence["lifecycle_stage_ids"] == stages
    assert evidence["hard_clause_evidence"] == {
        clause_id: list(member_ids)
        for clause_id, member_ids in REFERENCE_HARD_CLAUSE_EVIDENCE
    }
    assert list(evidence["hard_clause_evidence"]) == hard_clause_ids
    assert [row["role"] for row in evidence["witness_route_identities"]] == (
        evidence["witness_identity_roles"]
    )
    assert {
        row["architecture_id"] for row in evidence["witness_route_identities"]
    } == {REFERENCE_WITNESS_ID}
    candidate_report = _cas_json_record(
        canonical_reference_record,
        "candidate_evidence",
    )
    Draft202012Validator(_json_record(CANDIDATE_EVIDENCE_SCHEMA)).validate(
        candidate_report
    )
    assert set(candidate_report) == {
        "schema_version",
        "candidate_id",
        "builtin_architectures",
        "candidate_witness",
        "ownership",
        "architecture_decision_path",
        "extension_author_guide_path",
        "fixed_outputs",
        "claims",
    }
    assert [
        row["public_id"] for row in candidate_report["builtin_architectures"]
    ] == visible["builtin_architectures"]
    assert candidate_report["candidate_witness"]["public_id"] == (
        REFERENCE_WITNESS_ID
    )
    assert candidate_report["candidate_id"] == evidence["candidate_id"]
    task_package = importlib.import_module("scripts.experiments.es.task_package")
    candidate_path = tmp_path / "es_f1_candidate_evidence.json"
    candidate_path.write_bytes(calibration.canonical_json_bytes(candidate_report))
    assert task_package.load_candidate_extension_evidence(candidate_path) == (
        candidate_report
    )
    visible_result = _cas_json_record(
        canonical_reference_record, "visible_check_result"
    )
    assert evaluator.require_evaluator_successor_schema(
        visible_result,
        record_type="visible-check-result",
    ) is visible_result
    assert set(visible_result) == {
        "schema_version",
        "copy_digest_before",
        "copy_digest_after",
        "invocations",
    }
    assert visible_result["copy_digest_before"] == visible_result[
        "copy_digest_after"
    ]
    visible_by_id = {
        row["id"]: row for row in visible_checks["invocations"]
    }
    assert [row["invocation_id"] for row in visible_result["invocations"]] == (
        visible_checks["invocation_order"]
    )
    assert [row["argv"] for row in visible_result["invocations"]] == [
        [
            visible_checks["runner"]["python_executable"],
            *visible_checks["runner"]["argv_prefix"],
            *visible_by_id[invocation_id]["selectors"],
        ]
        for invocation_id in visible_checks["invocation_order"]
    ]
    assert all(
        row["exit_code"] == 0
        and row["stdout_sha256"].startswith("sha256:")
        and row["stderr_sha256"].startswith("sha256:")
        for row in visible_result["invocations"]
    )
    registry_report = _cas_json_record(
        canonical_reference_record, "registry_signature_report"
    )
    assert set(registry_report) == {
        "schema_version",
        "registry_baseline",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    }
    assert registry_report["registry_baseline"] == fixture_manifest[
        "registry_baseline"
    ]
    assert evaluator.derive_registry_observation(
        expected_registry_baseline=fixture_manifest["registry_baseline"],
        registry_report=registry_report,
    )["satisfied"] is True
    lifecycle_evidence = _cas_json_record(
        canonical_reference_record,
        "lifecycle_result",
    )
    assert set(lifecycle_evidence) == {
        "schema_version",
        "lifecycle_request",
        "lifecycle_result",
    }
    assert lifecycle_evidence["schema_version"] == (
        "es_f1_reference_lifecycle_evidence.v1"
    )
    request = lifecycle_evidence["lifecycle_request"]
    raw_result = lifecycle_evidence["lifecycle_result"]
    Draft202012Validator(_json_record(LIFECYCLE_REQUEST_SCHEMA)).validate(request)
    assert request["candidate_evidence_sha256"] == _cas_member_row(
        canonical_reference_record,
        "candidate_evidence",
    )["sha256"]
    assert [row["architecture_id"] for row in request["architecture_cases"]] == (
        architectures
    )
    assert request["required_lifecycle_stages"] == stages
    request_path = tmp_path / "lifecycle-request.json"
    request_path.write_bytes(calibration.canonical_json_bytes(request))
    assert task_package.load_lifecycle_probe_request(request_path) == request
    assert set(raw_result) == {
        "adapter_result",
        "audit_digest",
        "copy_digest_after",
        "copy_digest_before",
        "adapter_process_id",
        "semantic_observations",
        "semantic_report",
        "lifecycle_observations",
    }
    assert raw_result["copy_digest_before"] == raw_result["copy_digest_after"]
    adapter_result = raw_result["adapter_result"]
    Draft202012Validator(_json_record(LIFECYCLE_RESULT_SCHEMA)).validate(
        adapter_result
    )
    result_path = tmp_path / "lifecycle-result.json"
    result_path.write_bytes(calibration.canonical_json_bytes(adapter_result))
    assert task_package.load_lifecycle_probe_result(
        result_path,
        expected_architecture_ids=tuple(architectures),
        expected_candidate_id=candidate_report["candidate_id"],
    ) == adapter_result
    semantic_report = raw_result["semantic_report"]
    assert evaluator.require_evaluator_successor_schema(
        semantic_report,
        record_type="semantic-lifecycle",
    ) is semantic_report
    assert [
        row["architecture_id"]
        for row in semantic_report["architecture_results"]
    ] == architectures
    assert all(
        row["completed_stages"] == stages
        for row in semantic_report["architecture_results"]
    )
    assert all(
        row["config_digest"] == case["config"]["sha256"]
        and row["input_digest"] == case["input"]["sha256"]
        for row, case in zip(
            semantic_report["architecture_results"],
            request["architecture_cases"],
            strict=True,
        )
    )
    assert raw_result["semantic_observations"] == {
        row["architecture_id"]: {
            "checkpoint": row["adapter_checkpoint_reload"],
            "bundle": row["adapter_bundle_reload"],
        }
        for row in semantic_report["architecture_results"]
    }
    assert raw_result["audit_digest"] == evaluator._digest({"events": []})
    assert raw_result["audit_digest"] != evaluator._digest(
        raw_result["semantic_observations"]
    )
    derived_lifecycle = evaluator.derive_lifecycle_observations(
        semantic_report=semantic_report,
        adapter_process_id=raw_result["adapter_process_id"],
    )
    assert raw_result["lifecycle_observations"] == derived_lifecycle
    assert evidence["lifecycle_observations"] == derived_lifecycle
    assert [row["clause_id"] for row in derived_lifecycle] == hard_clause_ids[4:]
    assert all(row["satisfied"] for row in derived_lifecycle)
    derived_witness_routes = _witness_route_identities_from_lifecycle(
        lifecycle_evidence
    )
    assert evidence["witness_route_identities"] == derived_witness_routes
    witness_route_identities = {
        row["implementation_identity"] for row in derived_witness_routes
    }
    frozen_builtin_identities = {
        row["implementation_identity"]
        for row in registry_report["registry_baseline"]
    }
    assert len(frozen_builtin_identities) == 14
    assert len(witness_route_identities) == 1
    assert witness_route_identities.isdisjoint(frozen_builtin_identities)
    hard_evaluation = _cas_json_record(
        canonical_reference_record,
        "hard_evaluation",
    )
    assert set(hard_evaluation) == {
        "schema_version",
        "candidate_id",
        "candidate_claims_digest",
        "evaluator_observations",
        "hard_findings",
    }
    assert hard_evaluation["schema_version"] == "es-f1-hard-evaluation.v2"
    assert hard_evaluation["candidate_id"] == candidate_report["candidate_id"]
    assert hard_evaluation["candidate_claims_digest"] == _cas_member_row(
        canonical_reference_record,
        "candidate_evidence",
    )["sha256"]
    assert hard_evaluation["hard_findings"] == []
    hard_observations = hard_evaluation["evaluator_observations"]
    assert [row["clause_id"] for row in hard_observations] == hard_clause_ids
    assert all(
        set(row) == {"clause_id", "details", "evidence_digest", "satisfied"}
        and row["satisfied"] is True
        for row in hard_observations
    )
    for observation in hard_observations:
        member_ids = evidence["hard_clause_evidence"][
            observation["clause_id"]
        ]
        ordered_member_sha256 = [
            _cas_member_row(canonical_reference_record, member_id)["sha256"]
            for member_id in member_ids
        ]
        assert observation["evidence_digest"] == (
            "sha256:"
            + hashlib.sha256(
                calibration.canonical_json_bytes(ordered_member_sha256)
            ).hexdigest()
        )
    loaded = _load_reference_product(calibration, tmp_path, canonical_reference_record)
    assert loaded.record["evaluator_evidence"] == evidence


@pytest.mark.parametrize("mutation", ["malformed", "missing", "extra"])
def test_task3a_reference_rejects_invalid_lifecycle_audit_envelope(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    lifecycle = _cas_json_record(canonical_reference_record, "lifecycle_result")
    result = lifecycle["lifecycle_result"]
    if mutation == "malformed":
        result["audit_digest"] = "sha256:not-a-canonical-digest"
    elif mutation == "missing":
        result.pop("audit_digest")
    else:
        result["audit_ledger"] = {"events": []}
    changed = _replace_cas_json_record(
        calibration,
        canonical_reference_record,
        "lifecycle_result",
        lifecycle,
    )

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_reference_rejects_resealed_witness_builtin_identity_alias(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    changed = copy.deepcopy(canonical_reference_record)
    registry_report = _cas_json_record(
        canonical_reference_record,
        "registry_signature_report",
    )
    frozen_builtin_identities = {
        row["implementation_identity"]
        for row in registry_report["registry_baseline"]
    }
    assert len(frozen_builtin_identities) == 14
    builtin_alias = registry_report["registry_baseline"][0][
        "implementation_identity"
    ]

    lifecycle_evidence = _cas_json_record(
        canonical_reference_record,
        "lifecycle_result",
    )
    raw_result = lifecycle_evidence["lifecycle_result"]
    witness_row = next(
        row
        for row in raw_result["semantic_report"]["architecture_results"]
        if row["architecture_id"] == REFERENCE_WITNESS_ID
    )
    for field in (
        "registry_constructor_identity",
        "public_implementation",
        "persisted_implementation",
        "persisted_rebuild_implementation",
        "bundle_implementation",
    ):
        witness_row[field] = builtin_alias
    for field in (
        "evaluator_checkpoint_reload",
        "adapter_checkpoint_reload",
        "evaluator_bundle_reload",
        "adapter_bundle_reload",
    ):
        witness_row[field]["implementation_identity"] = builtin_alias
    raw_result["semantic_observations"] = {
        row["architecture_id"]: {
            "checkpoint": copy.deepcopy(row["adapter_checkpoint_reload"]),
            "bundle": copy.deepcopy(row["adapter_bundle_reload"]),
        }
        for row in raw_result["semantic_report"]["architecture_results"]
    }
    raw_result["lifecycle_observations"] = (
        evaluator.derive_lifecycle_observations(
            semantic_report=raw_result["semantic_report"],
            adapter_process_id=raw_result["adapter_process_id"],
        )
    )
    changed["evaluator_evidence"]["witness_route_identities"] = (
        _witness_route_identities_from_lifecycle(lifecycle_evidence)
    )
    changed["evaluator_evidence"]["lifecycle_observations"] = copy.deepcopy(
        raw_result["lifecycle_observations"]
    )

    artifact_report = _cas_json_record(
        canonical_reference_record,
        "artifact_fixture_verification",
    )
    for era in artifact_report["artifact_eras"]:
        for row in era["architecture_results"]:
            if (
                row["architecture_id"] == REFERENCE_WITNESS_ID
                and row["module_returned"]
            ):
                row["implementation_identity"] = builtin_alias
    changed["evaluator_evidence"]["artifact_applicability"] = copy.deepcopy(
        artifact_report["artifact_eras"]
    )

    alias_root = (
        Path(changed["repository"]["storage_root"])
        / "evidence"
        / f"{tmp_path.name}-witness-builtin-alias"
    )
    changed = _rebuild_reference_cas(
        calibration,
        changed,
        root=alias_root,
        json_overrides={
            "artifact_fixture_verification": artifact_report,
            "lifecycle_result": lifecycle_evidence,
        },
    )

    derived_routes = _witness_route_identities_from_lifecycle(
        _cas_json_record(changed, "lifecycle_result")
    )
    assert changed["evaluator_evidence"]["witness_route_identities"] == (
        derived_routes
    )
    assert {
        row["implementation_identity"] for row in derived_routes
    } == {builtin_alias}
    assert builtin_alias in frozen_builtin_identities
    hard_evaluation = _cas_json_record(changed, "hard_evaluation")
    assert [
        row["clause_id"]
        for row in hard_evaluation["evaluator_observations"]
        if not row["satisfied"]
    ] == ["F1-H09-CONSTRUCTION-REBUILD-EQUALITY"]
    assert [
        (row["clause_id"], row["disposition"])
        for row in hard_evaluation["hard_findings"]
    ] == [("F1-H09-CONSTRUCTION-REBUILD-EQUALITY", "PRODUCT_DEFECT")]

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-architecture",
        "architecture-order",
        "missing-stage",
        "lifecycle-observation-order",
    ],
)
def test_task3a_reference_rejects_incomplete_or_reordered_evaluator_evidence(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    evidence = changed["evaluator_evidence"]
    if mutation == "missing-architecture":
        evidence["architecture_ids"].pop()
    elif mutation == "architecture-order":
        evidence["architecture_ids"][0:2] = reversed(
            evidence["architecture_ids"][0:2]
        )
    elif mutation == "missing-stage":
        evidence["lifecycle_stage_ids"].pop()
    else:
        evidence["lifecycle_observations"][0:2] = reversed(
            evidence["lifecycle_observations"][0:2]
        )
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "reorder", "member-map", "evidence-digest"],
)
def test_task3a_reference_rejects_resealed_hard_evaluation_join_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    if mutation == "member-map":
        changed = copy.deepcopy(canonical_reference_record)
        changed["evaluator_evidence"]["hard_clause_evidence"][
            "F1-H01-FOCUSED-SUITES"
        ] = ["registry_signature_report"]
        changed = _sealed_reference_record(calibration, changed)
    else:
        payload = _cas_json_record(
            canonical_reference_record,
            "hard_evaluation",
        )
        observations = payload["evaluator_observations"]
        if mutation == "missing":
            observations.pop()
        elif mutation == "reorder":
            observations[0:2] = reversed(observations[0:2])
        else:
            observations[0]["evidence_digest"] = "sha256:" + "0" * 64
        changed = _replace_cas_json_record(
            calibration,
            canonical_reference_record,
            "hard_evaluation",
            payload,
        )

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def _publication_observation_inputs():
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    observations = [
        {
            "clause_id": clause_id,
            "satisfied": True,
            "evidence": [evaluator._digest({"derived_fact": clause_id})],
            "details": f"derived details for {clause_id}",
        }
        for clause_id in evaluator.HARD_CLAUSE_IDS
    ]
    member_sha256 = {
        member_id: evaluator._digest({"cas_member": member_id})
        for member_id in REFERENCE_CAS_MEMBER_IDS
        if member_id != "hard_evaluation"
    }
    return evaluator, observations, member_sha256


def test_task3a_publication_normalization_preserves_derived_facts_and_binds_cas() -> None:
    calibration = _calibration_module()
    evaluator, derived, member_sha256 = _publication_observation_inputs()
    original = copy.deepcopy(derived)

    published = calibration._normalize_reference_publication_observations(
        derived,
        cas_member_sha256_by_id=member_sha256,
    )

    assert derived == original
    assert [row["clause_id"] for row in published] == list(
        evaluator.HARD_CLAUSE_IDS
    )
    for source, normalized in zip(derived, published, strict=True):
        assert set(normalized) == {
            "clause_id",
            "satisfied",
            "evidence",
            "details",
        }
        assert normalized["clause_id"] == source["clause_id"]
        assert normalized["satisfied"] is source["satisfied"]
        assert normalized["details"] == source["details"]
        assert normalized["evidence"] == [
            member_sha256[member_id]
            for member_id in dict(REFERENCE_HARD_CLAUSE_EVIDENCE)[
                source["clause_id"]
            ]
        ]
        assert normalized["evidence"] != source["evidence"]


@pytest.mark.parametrize(
    "mutation",
    ["missing-member", "malformed-member-digest", "malformed-derived-evidence"],
)
def test_task3a_publication_normalization_rejects_wrong_digest_or_evidence(
    mutation: str,
) -> None:
    calibration = _calibration_module()
    _, derived, member_sha256 = _publication_observation_inputs()
    if mutation == "missing-member":
        member_sha256.pop("lifecycle_result")
    elif mutation == "malformed-member-digest":
        member_sha256["lifecycle_result"] = "sha256:not-a-digest"
    else:
        derived[0]["evidence"] = ["not-a-derived-fact-digest"]

    with pytest.raises(calibration.CalibrationError):
        calibration._normalize_reference_publication_observations(
            derived,
            cas_member_sha256_by_id=member_sha256,
        )


def test_task3a_artifact_applicability_is_exact_ten_by_fifteen_partition(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    visible = _json_record(VISIBLE_TASK_CONTRACT)
    fixture_manifest = _json_record(EVALUATOR_FIXTURE_MANIFEST)
    artifact_eras = canonical_reference_record["evaluator_evidence"][
        "artifact_applicability"
    ]
    architectures = [
        *visible["builtin_architectures"],
        REFERENCE_WITNESS_ID,
    ]
    expected_coordinates = [
        (era["era_id"], architecture_id)
        for era in fixture_manifest["artifact_eras"]
        for architecture_id in architectures
    ]
    cells = [
        (era["era_id"], row)
        for era in artifact_eras
        for row in era["architecture_results"]
    ]

    assert len(fixture_manifest["artifact_eras"]) == 10
    assert len(architectures) == 15
    assert len(artifact_eras) == 10
    assert len(cells) == 150
    assert [
        (era_id, row["architecture_id"])
        for era_id, row in cells
    ] == expected_coordinates
    assert sum(row["module_returned"] for _, row in cells) == 10
    assert (
        sum(
            row["diagnostic"] == "UNSUPPORTED_ARTIFACT_ARCHITECTURE"
            for _, row in cells
        )
        == 140
    )
    assert all(
        row["module_returned"] == row["strict_load"]
        and row["module_returned"] == (row["diagnostic"] is None)
        for _, row in cells
    )
    identity_by_architecture = {
        row["architecture"]: row["implementation_identity"]
        for row in fixture_manifest["registry_baseline"]
    }
    witness_identity = canonical_reference_record["evaluator_evidence"][
        "witness_route_identities"
    ][0]["implementation_identity"]
    assert witness_identity not in set(identity_by_architecture.values())
    identity_by_architecture[REFERENCE_WITNESS_ID] = witness_identity
    assert all(
        row["implementation_identity"]
        == (
            identity_by_architecture[row["architecture_id"]]
            if row["module_returned"]
            else None
        )
        for _, row in cells
    )
    artifact_report = _cas_json_record(
        canonical_reference_record,
        "artifact_fixture_verification",
    )
    assert evaluator.require_evaluator_successor_schema(
        artifact_report,
        record_type="artifact-fixture-verification",
    ) is artifact_report
    assert set(artifact_report) == {
        "schema_version",
        "artifact_eras",
        "loaded_forbidden_modules",
        "outside_project_origin_rows",
        "cache_artifacts",
    }
    assert artifact_report["artifact_eras"] == artifact_eras
    assert artifact_report["loaded_forbidden_modules"] == []
    assert artifact_report["outside_project_origin_rows"] == []
    assert artifact_report["cache_artifacts"] == []
    loaded = _load_reference_product(calibration, tmp_path, canonical_reference_record)
    assert (
        loaded.record["evaluator_evidence"]["artifact_applicability"]
        == artifact_eras
    )


@pytest.mark.parametrize("mutation", ["unsupported-positive", "missing-rejection"])
def test_task3a_reference_rejects_invalid_artifact_applicability_partition(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    artifact_eras = changed["evaluator_evidence"]["artifact_applicability"]
    rejected_era = next(
        era
        for era in artifact_eras
        if any(
            row["diagnostic"] == "UNSUPPORTED_ARTIFACT_ARCHITECTURE"
            for row in era["architecture_results"]
        )
    )
    rejected_index = next(
        index
        for index, row in enumerate(rejected_era["architecture_results"])
        if row["diagnostic"] == "UNSUPPORTED_ARTIFACT_ARCHITECTURE"
    )
    if mutation == "unsupported-positive":
        rejected = rejected_era["architecture_results"][rejected_index]
        rejected["diagnostic"] = None
        rejected["implementation_identity"] = "candidate.UnexpectedPositive"
        rejected["module_returned"] = True
        rejected["strict_load"] = True
    else:
        rejected_era["architecture_results"].pop(rejected_index)
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


def test_task3a_evaluator_bypass_and_no_delivery_are_backed_by_cas_reports(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    record = canonical_reference_record
    evaluator = record["evaluator_evidence"]
    bypass = record["bypass_oracle"]
    no_delivery = record["no_delivery"]

    assert "passed" not in evaluator
    assert "passed" not in bypass
    assert "passed" not in no_delivery
    candidate_report = _cas_json_record(record, "candidate_evidence")
    assert candidate_report["schema_version"] == "candidate_extension_evidence.v2"
    assert candidate_report["candidate_id"] == evaluator["candidate_id"]
    assert set(bypass) == {
        "report_member_ids",
        "candidate_tree",
        "discovery_candidate_set_sha256",
        "authority_bindings",
        "classification_sha256",
        "legacy_report_sha256",
        "desired_state_results_sha256",
        "derived_observation",
    }
    assert bypass["report_member_ids"] == {
        "discovery": "bypass_discovery",
        "classification": "bypass_classification",
    }
    discovery = _cas_json_record(record, "bypass_discovery")
    assert set(discovery) == {
        "schema_version",
        "candidate_tree",
        "discovery_input",
        "discovery_output",
    }
    assert discovery["schema_version"] == "es_f1_reference_bypass_discovery.v1"
    assert discovery["candidate_tree"] == record["lineage"]["reference_tree"]
    assert discovery["discovery_input"]["projection"] == {
        "repository": record["repository"]["locator"],
        "commit": record["lineage"]["reference_commit"],
        "tree": record["lineage"]["reference_tree"],
        "inventory_sha256": discovery["discovery_output"]["projection"][
            "inventory_sha256"
        ],
        "leaf_count": discovery["discovery_output"]["projection"]["leaf_count"],
    }
    assert discovery["discovery_output"]["projection"] == discovery[
        "discovery_input"
    ]["projection"]
    assert discovery["discovery_output"]["candidate_set_sha256"] == bypass[
        "discovery_candidate_set_sha256"
    ]
    source_census_module = importlib.import_module(
        "scripts.experiments.es.source_census"
    )
    assert discovery["discovery_output"]["candidate_set_sha256"] == (
        "sha256:"
        + hashlib.sha256(
            source_census_module.canonical_json_bytes(
                discovery["discovery_output"]["consumer_candidates"]
            )
        ).hexdigest()
    )

    classification_report = _cas_json_record(record, "bypass_classification")
    assert set(classification_report) == {
        "schema_version",
        "candidate_tree",
        "authority_bindings",
        "classification",
        "legacy_report",
        "derived_observation",
    }
    assert classification_report["schema_version"] == (
        "es_f1_reference_bypass_classification.v1"
    )
    assert classification_report["candidate_tree"] == bypass["candidate_tree"]
    classification = classification_report["classification"]
    assert classification_report["authority_bindings"] == bypass[
        "authority_bindings"
    ]
    assert classification["authority_bindings"] == bypass["authority_bindings"]
    assert classification["novel_direct_matches"] == []
    assert classification["restored_required_consumer_ids"] == []
    public_route_matches = [
        row
        for row in classification["allowed_boundary_matches"]
        if row["caller_path"] == "ptycho_torch/extension_persistence.py"
        and row["callee_or_dispatch_form"]
        == "ptycho_torch.generators.registry.resolve_generator"
    ]
    assert {row["anchor_id"] for row in public_route_matches} == {
        "GENERATOR_PACKAGE_IMPORT",
        "GENERATOR_REGISTRY_IMPORT",
    }
    assert bypass["classification_sha256"] == (
        "sha256:"
        + hashlib.sha256(calibration.canonical_json_bytes(classification)).hexdigest()
    )
    legacy_report = classification_report["legacy_report"]
    assert set(legacy_report) == {
        "bindings",
        "legacy_inventory_partition",
        "novel_matches",
        "schema_version",
        "selected_required_results",
    }
    assert legacy_report["selected_required_results"] == record[
        "desired_state_proofs"
    ]["result_rows"]
    assert legacy_report["novel_matches"] == classification[
        "novel_direct_matches"
    ]
    assert bypass["legacy_report_sha256"] == (
        "sha256:"
        + hashlib.sha256(calibration.canonical_json_bytes(legacy_report)).hexdigest()
    )
    assert bypass["desired_state_results_sha256"] == (
        "sha256:"
        + hashlib.sha256(
            calibration.canonical_json_bytes(
                record["desired_state_proofs"]["result_rows"]
            )
        ).hexdigest()
    )
    f1_evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    derived = f1_evaluator._derive_task0_bypass_observation(legacy_report)
    assert derived == {"satisfied": True, "evidence": bypass["legacy_report_sha256"]}
    assert classification_report["derived_observation"] == derived
    assert bypass["derived_observation"] == derived

    repository = Path(record["repository"]["locator"])
    target_tree = record["lineage"]["reference_tree"]
    absent = subprocess.run(
        (
            "/usr/bin/git",
            "-C",
            str(repository),
            "cat-file",
            "-e",
            f"{target_tree}:archive/root_scripts/analysis/extract_reconstructions.py",
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )
    assert absent.returncode != 0 and absent.stdout == b""
    metadata = _run_git(repository, "show", f"{target_tree}:ptycho/metadata.py")
    metadata_tree = ast.parse(metadata.decode("utf-8", errors="strict"))
    assert all(
        not isinstance(node, ast.Name) or node.id != "ModelConfig"
        for node in ast.walk(metadata_tree)
    )
    assert not any(
        isinstance(node, ast.Name) and node.id in {"getattr", "config_types"}
        for node in ast.walk(metadata_tree)
    )

    assert no_delivery["report_member_id"] == "no_delivery_report"
    no_delivery_report = _cas_json_record(record, "no_delivery_report")
    assert set(no_delivery_report) == {
        "schema_version",
        "bindings",
        "task_seed_closure",
        "reference_only_objects",
        "task_seed_lookup_rows",
        "surface_scan",
        "provider_workspace",
        "controller_resolution",
    }
    assert no_delivery_report["schema_version"] == (
        "es_f1_reference_no_delivery.v1"
    )
    assert set(no_delivery_report["bindings"]) == {
        "task_seed_manifest_sha256",
        "task_seed_repository_snapshot_sha256",
        "reference_repository_snapshot_sha256",
        "reference_ref",
        "reference_commit",
        "reference_tree",
        "canonical_patch_member_id",
        "canonical_patch_sha256",
    }
    assert no_delivery_report["bindings"]["reference_commit"] == record[
        "lineage"
    ]["reference_commit"]
    assert no_delivery_report["bindings"]["reference_tree"] == record[
        "lineage"
    ]["reference_tree"]
    closure = no_delivery_report["task_seed_closure"]
    assert set(closure) == {
        "repository_locator",
        "head_ref",
        "ref_rows",
        "history_rows",
        "tree_rows",
        "reachable_object_count",
        "reachable_objects_sha256",
        "unreachable_object_count",
        "fsck",
        "visible_asset_rows",
    }
    assert closure["head_ref"] == "refs/heads/task-seed"
    assert closure["ref_rows"] == [
        {
            "refname": "refs/heads/task-seed",
            "object_id": record["lineage"]["task_seed_commit"],
        }
    ]
    assert len(closure["history_rows"]) == 2
    assert [row["commit"] for row in closure["tree_rows"]] == [
        row["commit"] for row in closure["history_rows"]
    ]
    assert closure["reachable_object_count"] == 2_216
    assert closure["unreachable_object_count"] == 0
    assert closure["fsck"]["return_code"] == 0
    assert len(closure["visible_asset_rows"]) == 8
    reference_only = no_delivery_report["reference_only_objects"]
    reference_object_ids = [row["object_id"] for row in reference_only]
    assert reference_object_ids == sorted(reference_object_ids)
    assert len(reference_object_ids) == len(set(reference_object_ids))
    assert set(reference_object_ids) == set(no_delivery["reference_object_ids"])
    assert {row["object_type"] for row in reference_only} <= {
        "blob",
        "commit",
        "tree",
    }
    assert record["lineage"]["reference_commit"] in reference_object_ids
    assert record["lineage"]["reference_tree"] in reference_object_ids
    assert [
        row["object_id"] for row in no_delivery_report["task_seed_lookup_rows"]
    ] == reference_object_ids
    assert all(
        row["return_code"] != 0 and row["stdout"] == ""
        for row in no_delivery_report["task_seed_lookup_rows"]
    )
    scan = no_delivery_report["surface_scan"]
    assert set(scan) == {"scope", "forbidden_domain", "surface_rows", "matches"}
    assert scan["scope"] == {
        "surface_set": "task3a_logical_prelaunch.v1",
        "final_prompt_manifest": "not_yet_materialized",
        "final_environment_lock": "not_yet_materialized",
        "task5_replay_required": True,
    }
    assert scan["matches"] == []
    assert all(row["matches"] == [] for row in scan["surface_rows"])
    surface_classes = {row["surface_class"] for row in scan["surface_rows"]}
    assert surface_classes == {
        "visible_task_asset",
        "treatment_prompt",
        "prompt_externs",
        "evaluator_instruction",
        "evaluator_rubric",
        "provider_argv",
        "provider_environment",
        "provider_packet",
    }
    assert sum(
        row["surface_class"] == "visible_task_asset"
        for row in scan["surface_rows"]
    ) == 8
    forbidden = scan["forbidden_domain"]
    assert forbidden["reference_object_ids"] == reference_object_ids
    assert forbidden["reference_canary"]["path"] == REFERENCE_DOCUMENTATION_PATH
    canary = forbidden["reference_canary"]["value"]
    assert canary.startswith("es-f1-reference-canary.v1:")
    assert len(canary.removeprefix("es-f1-reference-canary.v1:")) == 64
    canary_blob_id = _git_blob_id((canary + "\n").encode("ascii"))
    assert any(
        row["object_id"] == canary_blob_id
        and row["content_sha256"]
        == "sha256:"
        + hashlib.sha256((canary + "\n").encode("ascii")).hexdigest()
        for row in forbidden["reference_source_blobs"]
    )
    assert forbidden["measured_count"]["value"] == 5_000
    assert forbidden["measured_count"]["ascii"] == "5000"
    provider = no_delivery_report["provider_workspace"]
    assert provider["destination_initial_state"] == "absent"
    assert provider["source_request"]["resolved_commit_sha"] == record[
        "lineage"
    ]["task_seed_commit"]
    assert provider["resolved_commit"] == record["lineage"]["task_seed_commit"]
    assert provider["head_commit"] == record["lineage"]["task_seed_commit"]
    assert provider["head_tree"] == record["lineage"]["task_seed_tree"]
    assert provider["source_tree_manifest_sha256"] == (
        provider["post_setup_tree_manifest_sha256"]
    )
    assert provider["symbolic_ref_return_code"] != 0
    assert provider["status_porcelain"] == ""
    assert [
        row["object_id"] for row in provider["reference_object_lookup_rows"]
    ] == reference_object_ids
    assert all(
        row["return_code"] != 0 and row["stdout"] == ""
        for row in provider["reference_object_lookup_rows"]
    )
    controller = no_delivery_report["controller_resolution"]
    assert controller["head_ref"] == REFERENCE_REF
    assert controller["ref_rows"] == [
        {
            "refname": REFERENCE_REF,
            "object_id": record["lineage"]["reference_commit"],
        }
    ]
    assert controller["resolved_commit"] == record["lineage"]["reference_commit"]
    assert controller["resolved_tree"] == record["lineage"]["reference_tree"]
    assert controller["remote_rows"] == []
    assert controller["escape_paths"] == []
    assert controller["reference_object_rows"] == reference_only
    documentation_row = next(
        row
        for row in record["metric"]["rows"]
        if row["candidate_path"] == REFERENCE_DOCUMENTATION_PATH
    )
    assert documentation_row["classification"] == "documentation"
    assert documentation_row["responsibility_ids"] == []
    assert documentation_row["cluster_ids"] == []
    assert record["metric"]["implementation_additions"] == 5_000

    loaded = _load_reference_product(calibration, tmp_path, record)
    assert loaded.record["bypass_oracle"] == bypass
    assert loaded.record["no_delivery"] == no_delivery


def test_task3a_reference_accepts_alternate_metadata_boundary_with_pinned_config(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    record = canonical_reference_record
    repository = Path(record["repository"]["locator"])
    task_seed_tree = record["lineage"]["task_seed_tree"]
    reference_tree = record["lineage"]["reference_tree"]
    config_path = "ptycho/config/config.py"

    assert _run_git(
        repository,
        "rev-parse",
        f"{reference_tree}:{config_path}",
    ) == _run_git(
        repository,
        "rev-parse",
        f"{task_seed_tree}:{config_path}",
    )
    config_row = next(
        row
        for row in record["metric"]["rows"]
        if row["base_path"] == config_path
    )
    assert config_row["change_kind"] == "unchanged"
    assert config_row["classification"] == "benchmark_task_seed_asset"

    metadata = _run_git(
        repository,
        "show",
        f"{reference_tree}:ptycho/metadata.py",
    )
    metadata_tree = ast.parse(metadata.decode("utf-8", errors="strict"))
    assert all(
        not isinstance(node, ast.Name) or node.id != "ModelConfig"
        for node in ast.walk(metadata_tree)
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "ptycho.config.metadata_adapter"
        and any(
            alias.name == "build_training_config_from_metadata"
            for alias in node.names
        )
        for node in metadata_tree.body
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_training_config_from_metadata"
        for node in ast.walk(metadata_tree)
    )
    classification = _cas_json_record(record, "bypass_classification")[
        "classification"
    ]
    assert classification["novel_direct_matches"] == []
    assert classification["restored_required_consumer_ids"] == []
    assert record["bypass_oracle"]["derived_observation"]["satisfied"] is True

    loaded = _load_reference_product(
        calibration,
        tmp_path,
        record,
        name="reference-product-alternate-metadata-boundary.json",
    )
    assert loaded.record == record


def test_task3a_reference_rejects_restored_direct_construction_match(
    tmp_path: Path,
    reference_repository_factory,
) -> None:
    calibration = _calibration_module()
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    repository = reference_repository_factory(restored_direct_match=True)
    record = _build_reference_record(tmp_path, repository)
    target_tree = record["lineage"]["reference_tree"]
    assert repository["restored_direct_match"] is True
    assert record["metric"]["implementation_additions"] == 5_000

    desired_rows = record["desired_state_proofs"]["result_rows"]
    assert len(desired_rows) == 23
    assert all(
        row["target_tree"] == target_tree and row["passed"] is True
        for row in desired_rows
    )
    absence_row = next(
        row
        for row in desired_rows
        if row["consumer_id"] == "consumer-3d5ba8fb56b5dd7fc5a44edf1a3a1982"
    )
    assert absence_row["proof_kind"] == "reference_absence"
    assert absence_row["observation"] == {"path_absent": True}

    discovery = _cas_json_record(record, "bypass_discovery")
    classification_report = _cas_json_record(record, "bypass_classification")
    classification = classification_report["classification"]
    assert discovery["candidate_tree"] == target_tree
    assert discovery["discovery_output"]["projection"]["tree"] == target_tree
    assert any(
        row["caller_path"]
        == "archive/root_scripts/analysis/extract_reconstructions.py"
        for row in discovery["discovery_output"]["consumer_candidates"]
    )
    assert classification_report["candidate_tree"] == target_tree
    assert classification["novel_direct_matches"] == []
    assert classification["restored_required_consumer_ids"] == [
        "consumer-3d5ba8fb56b5dd7fc5a44edf1a3a1982"
    ]
    assert classification_report["legacy_report"][
        "selected_required_results"
    ] == desired_rows
    assert classification_report["derived_observation"]["satisfied"] is True

    restored_path = "archive/root_scripts/analysis/extract_reconstructions.py"
    assert repository["eligible_candidate_tree"][restored_path] == (
        repository["eligible_base_tree"][restored_path]
    )

    hard = _cas_json_record(record, "hard_evaluation")
    h05 = next(
        row
        for row in hard["evaluator_observations"]
        if row["clause_id"] == "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"
    )
    assert h05["satisfied"] is False
    assert h05["evidence_digest"] == evaluator._digest(
        [
            _cas_member_row(record, member_id)["sha256"]
            for member_id in record["evaluator_evidence"][
                "hard_clause_evidence"
            ]["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"]
        ]
    )
    assert [row["clause_id"] for row in hard["hard_findings"]] == [
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"
    ]
    assert hard["hard_findings"][0]["disposition"] == "PRODUCT_DEFECT"
    no_delivery = _cas_json_record(record, "no_delivery_report")
    assert no_delivery["bindings"]["reference_tree"] == target_tree
    assert no_delivery["bindings"]["reference_commit"] == record["lineage"][
        "reference_commit"
    ]

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, record)


_NO_DELIVERY_MUTATIONS = (
    "report-extra-field",
    "report-missing-section",
    "binding-seed-digest",
    "binding-patch-digest",
    "closure-ref-missing",
    "closure-history-reordered",
    "closure-tree-drift",
    "closure-object-digest",
    "closure-unreachable",
    "closure-fsck-failure",
    "closure-visible-missing",
    "object-missing",
    "object-extra",
    "object-duplicate",
    "object-reordered",
    "object-type-drift",
    "object-size-drift",
    "lookup-missing",
    "lookup-success",
    "lookup-wrong-object",
    "scope-task5-replay-disabled",
    "surface-missing-visible-task-asset",
    "surface-missing-treatment-prompt",
    "surface-missing-prompt-externs",
    "surface-missing-evaluator-instruction",
    "surface-missing-evaluator-rubric",
    "surface-missing-provider-argv",
    "surface-missing-provider-environment",
    "surface-missing-provider-packet",
    "forbidden-domain-missing-locator",
    "forbidden-domain-missing-patch",
    "forbidden-domain-missing-source-blob",
    "forbidden-domain-missing-manifest",
    "forbidden-domain-missing-canary",
    "forbidden-domain-missing-count",
    "surface-detected-locator",
    "surface-detected-patch",
    "surface-detected-source-blob",
    "surface-detected-manifest",
    "surface-detected-canary",
    "surface-detected-count",
    "provider-destination-not-absent",
    "provider-source-locator-drift",
    "provider-commit-drift",
    "provider-tree-manifest-drift",
    "provider-attached-head",
    "provider-dirty-workspace",
    "provider-reference-lookup-success",
    "controller-extra-ref",
    "controller-commit-drift",
    "controller-remote",
    "controller-escape",
    "controller-object-missing",
    "controller-object-type-drift",
)


def _mutate_no_delivery_report(
    report: dict[str, Any],
    mutation: str,
) -> None:
    digest_zero = "sha256:" + "0" * 64
    if mutation == "report-extra-field":
        report["unexpected"] = None
    elif mutation == "report-missing-section":
        report.pop("controller_resolution")
    elif mutation == "binding-seed-digest":
        report["bindings"]["task_seed_manifest_sha256"] = digest_zero
    elif mutation == "binding-patch-digest":
        report["bindings"]["canonical_patch_sha256"] = digest_zero
    elif mutation == "closure-ref-missing":
        report["task_seed_closure"]["ref_rows"] = []
    elif mutation == "closure-history-reordered":
        report["task_seed_closure"]["history_rows"].reverse()
    elif mutation == "closure-tree-drift":
        report["task_seed_closure"]["tree_rows"][0]["tree"] = "f" * 40
    elif mutation == "closure-object-digest":
        report["task_seed_closure"]["reachable_objects_sha256"] = digest_zero
    elif mutation == "closure-unreachable":
        report["task_seed_closure"]["unreachable_object_count"] = 1
    elif mutation == "closure-fsck-failure":
        report["task_seed_closure"]["fsck"]["return_code"] = 1
    elif mutation == "closure-visible-missing":
        report["task_seed_closure"]["visible_asset_rows"].pop()
    elif mutation == "object-missing":
        report["reference_only_objects"].pop()
    elif mutation == "object-extra":
        report["reference_only_objects"].append(
            {
                "object_id": "f" * 40,
                "object_type": "blob",
                "byte_count": 1,
            }
        )
    elif mutation == "object-duplicate":
        report["reference_only_objects"].append(
            copy.deepcopy(report["reference_only_objects"][0])
        )
    elif mutation == "object-reordered":
        report["reference_only_objects"].reverse()
    elif mutation == "object-type-drift":
        report["reference_only_objects"][0]["object_type"] = "tag"
    elif mutation == "object-size-drift":
        report["reference_only_objects"][0]["byte_count"] += 1
    elif mutation == "lookup-missing":
        report["task_seed_lookup_rows"].pop()
    elif mutation == "lookup-success":
        report["task_seed_lookup_rows"][0]["return_code"] = 0
    elif mutation == "lookup-wrong-object":
        report["task_seed_lookup_rows"][0]["object_id"] = "f" * 40
    elif mutation == "scope-task5-replay-disabled":
        report["surface_scan"]["scope"]["task5_replay_required"] = False
    elif mutation.startswith("surface-missing-"):
        surface_class = mutation.removeprefix("surface-missing-").replace("-", "_")
        report["surface_scan"]["surface_rows"] = [
            row
            for row in report["surface_scan"]["surface_rows"]
            if row["surface_class"] != surface_class
        ]
    elif mutation.startswith("forbidden-domain-missing-"):
        kind = mutation.removeprefix("forbidden-domain-missing-")
        key_by_kind = {
            "locator": "reference_locator",
            "patch": "canonical_patch",
            "manifest": "reference_manifest",
            "canary": "reference_canary",
            "count": "measured_count",
        }
        if kind == "source-blob":
            report["surface_scan"]["forbidden_domain"][
                "reference_source_blobs"
            ].pop()
        else:
            report["surface_scan"]["forbidden_domain"].pop(key_by_kind[kind])
    elif mutation.startswith("surface-detected-"):
        kind = mutation.removeprefix("surface-detected-")
        forbidden_id_by_kind = {
            "locator": "reference_locator",
            "patch": "canonical_patch",
            "manifest": "reference_manifest_schema",
            "canary": "reference_canary",
            "count": "measured_count",
        }
        forbidden_id = forbidden_id_by_kind.get(kind)
        if kind == "source-blob":
            object_id = report["surface_scan"]["forbidden_domain"][
                "reference_source_blobs"
            ][0]["object_id"]
            forbidden_id = f"reference_source_blob:{object_id}"
        assert forbidden_id is not None
        surface = report["surface_scan"]["surface_rows"][0]
        surface["matches"].append(forbidden_id)
        report["surface_scan"]["matches"].append(
            {
                "surface_id": surface["surface_id"],
                "forbidden_id": forbidden_id,
            }
        )
    elif mutation == "provider-destination-not-absent":
        report["provider_workspace"]["destination_initial_state"] = "present"
    elif mutation == "provider-source-locator-drift":
        report["provider_workspace"]["normalized_locator"] = "file:///tmp/not-seed"
        report["provider_workspace"]["source_request"][
            "normalized_locator"
        ] = "file:///tmp/not-seed"
    elif mutation == "provider-commit-drift":
        report["provider_workspace"]["resolved_commit"] = "f" * 40
        report["provider_workspace"]["head_commit"] = "f" * 40
        report["provider_workspace"]["source_request"][
            "resolved_commit_sha"
        ] = "f" * 40
    elif mutation == "provider-tree-manifest-drift":
        report["provider_workspace"]["source_tree_manifest_sha256"] = digest_zero
    elif mutation == "provider-attached-head":
        report["provider_workspace"]["symbolic_ref_return_code"] = 0
    elif mutation == "provider-dirty-workspace":
        report["provider_workspace"]["status_porcelain"] = " M tracked.py\n"
    elif mutation == "provider-reference-lookup-success":
        report["provider_workspace"]["reference_object_lookup_rows"][0][
            "return_code"
        ] = 0
    elif mutation == "controller-extra-ref":
        report["controller_resolution"]["ref_rows"].append(
            {"refname": "refs/heads/extra", "object_id": "f" * 40}
        )
    elif mutation == "controller-commit-drift":
        report["controller_resolution"]["resolved_commit"] = "f" * 40
    elif mutation == "controller-remote":
        report["controller_resolution"]["remote_rows"] = [
            "origin file:///tmp/escape (fetch)"
        ]
    elif mutation == "controller-escape":
        report["controller_resolution"]["escape_paths"] = [
            "objects/info/alternates"
        ]
    elif mutation == "controller-object-missing":
        report["controller_resolution"]["reference_object_rows"].pop()
    elif mutation == "controller-object-type-drift":
        report["controller_resolution"]["reference_object_rows"][0][
            "object_type"
        ] = "tag"
    else:
        raise AssertionError(f"unhandled no-delivery mutation: {mutation}")


@pytest.mark.parametrize("mutation", _NO_DELIVERY_MUTATIONS)
def test_task3a_reference_no_delivery_rejects_internally_resealed_mutants(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    report = _cas_json_record(canonical_reference_record, "no_delivery_report")
    _mutate_no_delivery_report(report, mutation)
    changed = _replace_cas_json_record(
        calibration,
        canonical_reference_record,
        "no_delivery_report",
        report,
    )

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(
            calibration,
            tmp_path,
            changed,
            name=f"reference-product-{mutation}.json",
        )


def test_task3a_reference_no_delivery_rejects_live_provider_object_delivery(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
) -> None:
    calibration = _calibration_module()
    report = _cas_json_record(canonical_reference_record, "no_delivery_report")
    provider = report["provider_workspace"]
    copied_root = tmp_path / "provider-with-reference-object"
    copied_destination = copied_root / "workspace"
    copied_run_ref_root = copied_root / "run-ref"
    shutil.copytree(
        Path(provider["destination"]),
        copied_destination,
        symlinks=True,
    )
    shutil.copytree(
        Path(provider["run_ref_root"]),
        copied_run_ref_root,
        symlinks=True,
    )
    provider["destination"] = str(copied_destination.resolve())
    provider["run_ref_root"] = str(copied_run_ref_root.resolve())

    reference_blob = next(
        row
        for row in report["reference_only_objects"]
        if row["object_type"] == "blob"
    )
    blob_payload = _run_git(
        Path(canonical_reference_record["repository"]["locator"]),
        "cat-file",
        "blob",
        reference_blob["object_id"],
    )
    written_object_id = _run_git(
        copied_destination,
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=blob_payload,
    ).decode("ascii").strip()
    assert written_object_id == reference_blob["object_id"]
    reference_object_ids = tuple(
        row["object_id"] for row in report["reference_only_objects"]
    )
    provider["reference_object_lookup_rows"] = _git_lookup_rows(
        copied_destination,
        reference_object_ids,
    )
    assert any(
        row["object_id"] == written_object_id and row["return_code"] == 0
        for row in provider["reference_object_lookup_rows"]
    )
    changed = _replace_cas_json_record(
        calibration,
        canonical_reference_record,
        "no_delivery_report",
        report,
    )

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(
            calibration,
            tmp_path,
            changed,
            name="reference-product-live-provider-delivery.json",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "incomplete-discovery",
        "classification-drift",
        "novel-hard-failure",
        "desired-result-join-failure",
    ],
)
def test_task3a_reference_rejects_resealed_bypass_semantic_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    changed = copy.deepcopy(canonical_reference_record)
    discovery = _cas_json_record(changed, "bypass_discovery")
    classification_report = _cas_json_record(changed, "bypass_classification")
    classification = classification_report["classification"]
    legacy_report = classification_report["legacy_report"]

    if mutation == "incomplete-discovery":
        discovery["discovery_output"]["consumer_candidates"].pop()
        discovery["discovery_output"]["candidate_set_sha256"] = evaluator._digest(
            discovery["discovery_output"]["consumer_candidates"]
        )
        changed["bypass_oracle"]["discovery_candidate_set_sha256"] = discovery[
            "discovery_output"
        ]["candidate_set_sha256"]
    elif mutation == "classification-drift":
        classification["governed_matches"].pop()
    elif mutation == "novel-hard-failure":
        novel = copy.deepcopy(
            next(
                row
                for row in classification["governed_matches"]
                if row["anchor_id"]
                in {"GENERATOR_PACKAGE_IMPORT", "GENERATOR_REGISTRY_IMPORT"}
            )
        )
        novel.update(
            {
                "caller_path": "scripts/reference_novel_direct.py",
                "consumer_id": "consumer-" + "a" * 32,
                "match_id": "match-" + "b" * 32,
            }
        )
        classification["novel_direct_matches"] = [novel]
        legacy_report["novel_matches"] = [copy.deepcopy(novel)]
    else:
        result = legacy_report["selected_required_results"][0]
        assert result["proof_kind"] == "reference_absence"
        result["observation"] = {"path_absent": False}
        result["observation_sha256"] = evaluator._digest(result["observation"])
        result["target_blob_id"] = "0" * 40
        result["passed"] = False

    if mutation != "incomplete-discovery":
        changed["bypass_oracle"]["classification_sha256"] = evaluator._digest(
            classification
        )
    if mutation in {"novel-hard-failure", "desired-result-join-failure"}:
        derived = evaluator._derive_task0_bypass_observation(legacy_report)
        assert derived["satisfied"] is False
        classification_report["derived_observation"] = derived
        changed["bypass_oracle"]["derived_observation"] = derived
        changed["bypass_oracle"]["legacy_report_sha256"] = evaluator._digest(
            legacy_report
        )
        if mutation == "desired-result-join-failure":
            changed["bypass_oracle"]["desired_state_results_sha256"] = (
                evaluator._digest(legacy_report["selected_required_results"])
            )

    changed = _rebuild_reference_cas(
        calibration,
        changed,
        root=tmp_path / f"resealed-bypass-{mutation}",
        json_overrides={
            "bypass_discovery": discovery,
            "bypass_classification": classification_report,
        },
    )

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "member_id",
    [
        "candidate_evidence",
        "visible_check_result",
        "registry_signature_report",
        "artifact_fixture_verification",
        "lifecycle_result",
        "hard_evaluation",
        "bypass_discovery",
        "bypass_classification",
        "no_delivery_report",
    ],
)
def test_task3a_reference_rejects_raw_report_byte_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    member_id: str,
) -> None:
    calibration = _calibration_module()
    path = _cas_member_path(canonical_reference_record, member_id)
    path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, canonical_reference_record)


@pytest.mark.parametrize("mutation", ["evaluator", "bypass", "no-delivery"])
def test_task3a_reference_rejects_report_member_reference_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    changed = copy.deepcopy(canonical_reference_record)
    if mutation == "evaluator":
        changed["evaluator_evidence"]["report_member_ids"][
            "lifecycle_result"
        ] = "hard_evaluation"
    elif mutation == "bypass":
        changed["bypass_oracle"]["report_member_ids"][
            "discovery"
        ] = "bypass_classification"
    else:
        changed["no_delivery"]["report_member_id"] = "lifecycle_result"
    changed = _sealed_reference_record(calibration, changed)

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)


@pytest.mark.parametrize(
    "mutation",
    [
        "candidate",
        "visible",
        "registry",
        "lifecycle",
        "artifact",
        "bypass",
        "no-delivery",
    ],
)
def test_task3a_reference_rejects_resealed_cas_report_content_drift(
    tmp_path: Path,
    canonical_reference_record: dict[str, Any],
    mutation: str,
) -> None:
    calibration = _calibration_module()
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    changed = copy.deepcopy(canonical_reference_record)
    json_overrides: dict[str, dict[str, Any]] = {}
    if mutation == "candidate":
        candidate = _cas_json_record(changed, "candidate_evidence")
        unclaimed = next(
            row
            for row in candidate["claims"]
            if row["clause_id"] == "F1-H02-SCHEMA-CONFORMANCE"
        )
        unclaimed["scope"] = "NOT_CLAIMED"
        unclaimed["evidence_paths"] = []
        lifecycle = _cas_json_record(changed, "lifecycle_result")
        lifecycle["lifecycle_request"]["candidate_evidence_sha256"] = (
            "sha256:"
            + hashlib.sha256(
                calibration.canonical_json_bytes(candidate)
            ).hexdigest()
        )
        json_overrides.update(
            {
                "candidate_evidence": candidate,
                "lifecycle_result": lifecycle,
            }
        )
    elif mutation == "visible":
        visible = _cas_json_record(changed, "visible_check_result")
        visible["invocations"][0]["exit_code"] = 1
        json_overrides["visible_check_result"] = visible
    elif mutation == "registry":
        registry = _cas_json_record(changed, "registry_signature_report")
        registry["registry_baseline"][0:2] = reversed(
            registry["registry_baseline"][0:2]
        )
        json_overrides["registry_signature_report"] = registry
    elif mutation == "lifecycle":
        lifecycle = _cas_json_record(changed, "lifecycle_result")
        request = lifecycle["lifecycle_request"]
        result = lifecycle["lifecycle_result"]
        request["architecture_cases"][0:2] = reversed(
            request["architecture_cases"][0:2]
        )
        result["adapter_result"]["architecture_results"][0:2] = reversed(
            result["adapter_result"]["architecture_results"][0:2]
        )
        semantic_report = result["semantic_report"]
        semantic_report["architecture_results"][0:2] = reversed(
            semantic_report["architecture_results"][0:2]
        )
        result["semantic_observations"] = {
            row["architecture_id"]: {
                "checkpoint": copy.deepcopy(row["adapter_checkpoint_reload"]),
                "bundle": copy.deepcopy(row["adapter_bundle_reload"]),
            }
            for row in semantic_report["architecture_results"]
        }
        semantic_by_architecture = {
            row["architecture_id"]: row
            for row in semantic_report["architecture_results"]
        }
        semantic_comparison = copy.deepcopy(semantic_report)
        semantic_comparison["architecture_results"] = [
            copy.deepcopy(semantic_by_architecture[architecture_id])
            for architecture_id in canonical_reference_record[
                "evaluator_evidence"
            ]["architecture_ids"]
        ]
        lifecycle_observations = evaluator.derive_lifecycle_observations(
            semantic_report=semantic_comparison,
            adapter_process_id=result["adapter_process_id"],
        )
        for row in lifecycle_observations:
            row["evidence"] = [
                evaluator._digest(
                    {
                        "clause_id": row["clause_id"],
                        "semantic_report": semantic_report,
                    }
                )
            ]
        result["lifecycle_observations"] = lifecycle_observations
        changed["evaluator_evidence"]["architecture_ids"] = [
            row["architecture_id"] for row in request["architecture_cases"]
        ]
        changed["evaluator_evidence"]["lifecycle_observations"] = (
            copy.deepcopy(lifecycle_observations)
        )
        changed["evaluator_evidence"]["witness_route_identities"] = (
            _witness_route_identities_from_lifecycle(lifecycle)
        )
        json_overrides["lifecycle_result"] = lifecycle
    elif mutation == "artifact":
        artifact = _cas_json_record(changed, "artifact_fixture_verification")
        artifact["artifact_eras"][0]["architecture_results"].pop()
        changed["evaluator_evidence"]["artifact_applicability"] = (
            copy.deepcopy(artifact["artifact_eras"])
        )
        json_overrides["artifact_fixture_verification"] = artifact
    elif mutation == "bypass":
        bypass = _cas_json_record(changed, "bypass_classification")
        bypass["classification"]["governed_matches"].pop()
        changed["bypass_oracle"]["classification_sha256"] = evaluator._digest(
            bypass["classification"]
        )
        json_overrides["bypass_classification"] = bypass
    else:
        member_id = "no_delivery_report"
        payload = _cas_json_record(changed, member_id)
        payload["task_seed_lookup_rows"].pop()
        changed = _replace_cas_json_record(
            calibration,
            changed,
            member_id,
            payload,
        )
    if mutation != "no-delivery":
        changed = _rebuild_reference_cas(
            calibration,
            changed,
            root=tmp_path / f"resealed-content-drift-{mutation}",
            json_overrides=json_overrides,
        )

        expected_failed_clause = {
            "candidate": "F1-H02-SCHEMA-CONFORMANCE",
            "visible": "F1-H01-FOCUSED-SUITES",
            "registry": "F1-H03-BUILTIN-SIGNATURES",
            "lifecycle": "F1-H02-SCHEMA-CONFORMANCE",
            "artifact": "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
            "bypass": None,
        }[mutation]
        hard_evaluation = _cas_json_record(changed, "hard_evaluation")
        assert [
            row["clause_id"] for row in hard_evaluation["hard_findings"]
        ] == ([] if expected_failed_clause is None else [expected_failed_clause])
        assert all(
            row["disposition"] == "PRODUCT_DEFECT"
            for row in hard_evaluation["hard_findings"]
        )
        for observation in hard_evaluation["evaluator_observations"]:
            member_ids = changed["evaluator_evidence"][
                "hard_clause_evidence"
            ][observation["clause_id"]]
            assert observation["evidence_digest"] == evaluator._digest(
                [
                    _cas_member_row(changed, member_id)["sha256"]
                    for member_id in member_ids
                ]
            )

    with pytest.raises(calibration.CalibrationError):
        _load_reference_product(calibration, tmp_path, changed)
