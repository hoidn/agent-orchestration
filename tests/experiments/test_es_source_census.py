from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest
from jsonschema import Draft202012Validator


GIT = Path("/usr/bin/git")
TASK0_PYTHON = "/home/ollie/miniconda3/envs/ptycho311/bin/python"
TASK0_PYTHON_TARGET = "/home/ollie/miniconda3/envs/ptycho311/bin/python3.11"
TASK0_PYTEST_CARRIER = {
    "executable": "/usr/bin/bwrap",
    "sha256": "sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712",
    "version": "bubblewrap 0.9.0",
    "tmp_isolation": "private_tmpfs",
}
TASK0_PROVIDER_MODULES = (
    "tests/torch/test_generator_registry.py",
    "tests/torch/test_construction_consolidation.py",
    "tests/torch/test_generator_adapter.py",
    "tests/torch/test_config_bridge.py",
    "tests/torch/test_model_spec.py",
    "tests/torch/test_model_spec_v2.py",
    "tests/torch/test_lightning_checkpoint.py",
    "tests/torch/test_artifact_schema.py",
    "tests/torch/test_artifact_schema_v2.py",
    "tests/torch/test_workflows_components.py",
    "tests/torch/test_fno_generators.py",
    "tests/torch/test_fno_lightning_integration.py",
    "tests/torch/test_neuralop_uno_generator.py",
    "tests/torch/test_model_output_modes.py",
    "tests/torch/test_model_manager.py",
    "tests/torch/test_model_training.py",
    "tests/torch/test_train_lightning_execution_contract.py",
    "tests/torch/test_object_big_generator_contract.py",
    "tests/torch/test_structural_config_ownership.py",
)
TASK0_AGGREGATE_PYTEST_ARGV = (
    TASK0_PYTHON,
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    *TASK0_PROVIDER_MODULES,
)


def _module():
    return importlib.import_module("scripts.experiments.es.source_census")


def _git_sha256() -> str:
    return "sha256:" + hashlib.sha256(GIT.read_bytes()).hexdigest()


def _git_version() -> str:
    return subprocess.check_output([str(GIT), "--version"], text=True).strip()


def _run_git(git_dir: Path, *args: str, data: bytes | None = None) -> bytes:
    env = {
        "HOME": str(git_dir.parent),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
    }
    return subprocess.run(
        [str(GIT), f"--git-dir={git_dir}", *args],
        check=True,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    ).stdout


def _provider_selector_path(ordinal: int) -> str:
    return "selector.py" if ordinal == 1 else f"selector_{ordinal:02d}.py"


def _provider_selector_node(ordinal: int) -> str:
    suffix = "" if ordinal == 1 else f"_{ordinal:02d}"
    return f"{_provider_selector_path(ordinal)}::test_placeholder{suffix}"


def _bare_projection(
    tmp_path: Path,
    *,
    provider_selector_count: int = 1,
    runtime_consumer_count: int = 2,
) -> dict[str, Any]:
    repository = tmp_path / "projection.git"
    subprocess.run(
        [str(GIT), "init", "--bare", "-q", str(repository)], check=True
    )
    if runtime_consumer_count < 2:
        raise ValueError("fixture needs the import and at least one call consumer")
    runtime_statements = [b"rg(config)"] * (runtime_consumer_count - 2)
    runtime_statements.append(b"return rg(config)")
    payloads = {
        "linked.py": b"../model.py",
        "model.py": (
            b"from ptycho_torch.generators.registry import resolve_generator as rg\n"
            b"\n"
            b"def build(config):\n"
            b"    " + b"; ".join(runtime_statements) + b"\n"
        ),
        "notes.txt": b"run_grid_lines_torch",
    }
    for ordinal in range(1, provider_selector_count + 1):
        suffix = "" if ordinal == 1 else f"_{ordinal:02d}"
        payloads[_provider_selector_path(ordinal)] = (
            f"def test_placeholder{suffix}():\n    pass\n".encode()
        )
    rows: list[bytes] = []
    for path, payload in sorted(payloads.items()):
        oid = _run_git(repository, "hash-object", "-w", "--stdin", data=payload)
        mode = b"120000" if path == "linked.py" else b"100644"
        rows.append(mode + b" blob " + oid.strip() + b"\t" + path.encode() + b"\n")
    tree = _run_git(repository, "mktree", data=b"".join(rows)).decode().strip()
    commit_env = {
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": "1700000000 +0000",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_DATE": "1700000000 +0000",
        "HOME": str(tmp_path),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    commit = subprocess.run(
        [str(GIT), f"--git-dir={repository}", "commit-tree", tree],
        check=True,
        input=b"fixture projection\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=commit_env,
    ).stdout.decode().strip()
    _run_git(repository, "update-ref", "refs/heads/projection", commit.encode())
    inventory = _run_git(repository, "ls-tree", "-rz", "-r", commit)
    return {
        "repository": repository,
        "commit": commit,
        "tree": tree,
        "inventory_sha256": "sha256:" + hashlib.sha256(inventory).hexdigest(),
        "leaf_count": len(payloads),
    }


def _discovery_input(projection: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "es_f1_preedit_discovery_input.v1",
        "authority_status": "non_authoritative_discovery_input",
        "git": {
            "executable": str(GIT),
            "version": _git_version(),
            "sha256": _git_sha256(),
            "object_controls": [
                "rev-parse --verify <commit>^{commit}",
                "rev-parse --verify <commit>^{tree}",
                "ls-tree -rz -r --full-tree <commit>",
                "cat-file --batch",
            ],
        },
        "projection": {
            "repository": str(projection["repository"]),
            "commit": projection["commit"],
            "tree": projection["tree"],
            "inventory_sha256": projection["inventory_sha256"],
            "leaf_count": projection["leaf_count"],
        },
        "detectors": [
            {
                "detector_id": "python-boundary",
                "version": "1",
                "language": "python_ast",
                "path_globs": ["*.py"],
                "anchors": [
                    {
                        "anchor_id": "import-registry",
                        "form": "import",
                        "pattern": "ptycho_torch.generators.registry.resolve_generator",
                        "responsibility_ids": ["CONSTRUCTION"],
                    },
                    {
                        "anchor_id": "call-registry",
                        "form": "call",
                        "pattern": "ptycho_torch.generators.registry.resolve_generator",
                        "responsibility_ids": ["CONSTRUCTION"],
                    },
                ],
            },
            {
                "detector_id": "text-boundary",
                "version": "1",
                "language": "text_regex",
                "path_globs": ["*.txt"],
                "anchors": [
                    {
                        "anchor_id": "run-grid-lines",
                        "form": "regex",
                        "pattern": "run_grid_lines_torch",
                        "responsibility_ids": ["RUNTIME"],
                    }
                ],
            },
        ],
        "responsibilities": [
            {
                "responsibility_id": "CONSTRUCTION",
                "anchors": ["import-registry", "call-registry"],
            },
            {"responsibility_id": "RUNTIME", "anchors": ["run-grid-lines"]},
        ],
        "provider_visible_pytest_selectors": [
            {
                "selector_id": "focused-01",
                "ordinal": 1,
                "pytest_module_path": "selector.py",
            }
        ],
    }


def _policy(discovery_input: dict[str, Any], discovery: dict[str, Any]) -> dict[str, Any]:
    module = _module()
    consumer_policies = []
    witness_specs = []
    desired_specs = []
    provider_selectors = discovery_input["provider_visible_pytest_selectors"]
    runtime_consumer_ordinal = 0
    sampled_controller_classes: set[tuple[str, str]] = set()
    for ordinal, candidate in enumerate(discovery["consumer_candidates"], 1):
        witness_id = f"witness-{ordinal:04d}"
        disposition = (
            "compatibility_adapter"
            if candidate["detector_id"] == "text-boundary"
            else "route_through_boundary"
        )
        proof_kind = (
            "non_cdi_static"
            if disposition == "compatibility_adapter"
            else "boundary_runtime"
        )
        witness_kind = "static_ast" if proof_kind == "non_cdi_static" else "pytest_runtime"
        consumer_class = (disposition, witness_kind)
        if witness_kind == "pytest_runtime":
            runtime_consumer_ordinal += 1
            provider_index = min(runtime_consumer_ordinal, len(provider_selectors)) - 1
            selector_id = provider_selectors[provider_index]["selector_id"]
            coverage_status = (
                "required"
                if runtime_consumer_ordinal <= len(provider_selectors)
                else "inherited"
            )
        else:
            selector_id = "static-01"
            coverage_status = (
                "inherited"
                if consumer_class in sampled_controller_classes
                else "required"
            )
            sampled_controller_classes.add(consumer_class)
        consumer_policies.append(
            {
                "consumer_id": candidate["consumer_id"],
                "match_id": candidate["match_id"],
                "proposed_disposition": disposition,
                "required_proof_kind": proof_kind,
                "selector_id": selector_id,
                "witness_kind": witness_kind,
                "coverage_status": coverage_status,
                "coverage_witness_ids": (
                    [witness_id] if coverage_status == "required" else []
                ),
            }
        )
        if coverage_status != "required":
            continue
        spec: dict[str, Any] = {"anchor_id": candidate["anchor_id"]}
        if witness_kind == "pytest_runtime":
            spec.update(
                {
                    "event_kind": (
                        "import_alias_opcode"
                        if candidate["anchor_id"] == "import-registry"
                        else "opcode_exact_span"
                    ),
                    "phase": "call",
                    "attribution": {
                        "attribution_kind": "pytest_node",
                        "pytest_node_pattern": r"selector\.py::test_placeholder",
                    },
                    "expected_event": {"consumer_span_hit": True, "status": "passed"},
                }
            )
        else:
            spec.update(
                {
                    "query": {
                        "query_kind": "forbidden_syntax_absent",
                        "forbidden_names": ["ModelSpec"],
                        "forbidden_attributes": ["load_torch_bundle"],
                        "forbidden_string_literals": ["cnn"],
                    },
                    "expected_event": {"matches": []},
                }
            )
        witness_specs.append(
            {
                "witness_id": witness_id,
                "witness_kind": witness_kind,
                "selector_id": selector_id,
                "consumer_id": candidate["consumer_id"],
                "required_proof_kind": proof_kind,
                "spec": spec,
            }
        )
        desired_specs.append(
            {
                "proof_spec_id": f"proof-{ordinal:04d}",
                "witness_id": witness_id,
                "proof_kind": proof_kind,
                "expected_result": spec["expected_event"],
            }
        )
    no_consumption_digest = module.no_consumption_observation_sha256([], [])
    body: dict[str, Any] = {
        "schema_version": "es_f1_preedit_policy.v1",
        "discovery": {
            "input_sha256": module.raw_sha256(module.canonical_json_bytes(discovery_input)),
            "output_sha256": module.raw_sha256(module.canonical_json_bytes(discovery)),
            "candidate_set_sha256": discovery["candidate_set_sha256"],
        },
        "git": discovery_input["git"],
        "projection": discovery_input["projection"],
        "schema_bindings": module.current_schema_bindings(),
        "lineage": module.current_lineage_bindings(),
        "detectors": discovery_input["detectors"],
        "responsibilities": discovery_input["responsibilities"],
        "consumer_policies": consumer_policies,
        "selector_policy": {
            "sampling_rule": (
                "first_observable_per_provider_and_disposition_witness_class_"
                "in_discovery_order.v1"
            ),
            "pytest_carrier": copy.deepcopy(TASK0_PYTEST_CARRIER),
            "provider_visible_pytest_selectors": discovery_input[
                "provider_visible_pytest_selectors"
            ],
            "controller_only_proof_selectors": [
                {
                    "selector_id": "static-01",
                    "ordinal": 1,
                    "proof_kind": "non_cdi_static",
                    "execution_kind": "static_ast",
                    "runner_path": "scripts/experiments/es/boundary_proofs.py",
                    "runner_sha256": "sha256:" + "1" * 64,
                    "argv": ["python", "-m", "scripts.experiments.es.boundary_proofs"],
                    "input_bindings": [
                        {"path": "policy.json", "sha256": "sha256:" + "2" * 64}
                    ],
                    "coverage_witness_ids": [
                        row["witness_id"]
                        for row in witness_specs
                        if row["selector_id"] == "static-01"
                    ],
                }
            ],
            "coverage_witness_specs": witness_specs,
            "desired_state_proof_specs": desired_specs,
        },
        "audit_groups": [
            {
                "group_id": "fixture-responsibility",
                "paths": ["model.py", "notes.txt"],
                "expected_physical_line_count": 5,
            }
        ],
        "legacy_bypass_consumer_ids": [],
        "no_consumption": {
            "captured_at": "2026-08-03T00:00:00Z",
            "external_roots": [],
            "repository_paths": [],
            "observation_sha256": no_consumption_digest,
        },
        "a1": {
            "evidence_root": "/fixture/a1-v7",
            "members": [
                {
                    "member_id": f"member-{ordinal:02d}",
                    "path": f"member-{ordinal:02d}.json",
                    "byte_count": ordinal,
                    "sha256": "sha256:" + f"{ordinal:064x}",
                }
                for ordinal in range(1, 14)
            ],
            "metric": {
                "metric_version": "implementation_delta_physical_lines.v1",
                "git_executable": str(GIT),
                "git_version": _git_version(),
                "git_sha256": _git_sha256(),
                "diff_controls": [
                    "--no-ext-diff",
                    "--no-textconv",
                    "--diff-algorithm=histogram",
                    "--find-renames=100%",
                    "--find-copies=100%",
                    "--find-copies-harder",
                ],
                "implementation_additions": 667,
                "implementation_deletions": 2,
                "candidate_postimage_physical_lines": 690,
            },
        },
        "witness_observability_reviews": {
            "plan": {
                "path": "docs/plans/2026-08-04-es-f1-witness-observability-correction-plan.md",
                "sha256": "sha256:" + "a" * 64,
            },
            "plan_specification_review": {
                "path": "artifacts/review/es-f1-witness-observability-plan-spec-review.json",
                "sha256": "sha256:" + "b" * 64,
                "verdict": "ES_F1_WITNESS_PLAN_SPEC_APPROVED",
            },
            "plan_quality_review": {
                "path": "artifacts/review/es-f1-witness-observability-plan-quality-review.json",
                "sha256": "sha256:" + "c" * 64,
                "verdict": "ES_F1_WITNESS_PLAN_QUALITY_APPROVED",
            },
            "implementation_review": {
                "path": "artifacts/review/es-f1-witness-observability-implementation-review.json",
                "sha256": "sha256:" + "d" * 64,
                "verdict": "ES_F1_WITNESS_IMPLEMENTATION_APPROVED",
                "candidate_set_sha256": "sha256:" + "e" * 64,
            },
        },
    }
    body["record_sha256"] = module.compute_record_sha256(body)
    return body


def _producer() -> dict[str, str]:
    module = _module()
    return {
        "path": "scripts/experiments/es/source_census.py",
        "sha256": module.raw_sha256(Path(module.__file__).read_bytes()),
    }


def _runtime_source_event_fixture(
    *,
    spec: dict[str, Any],
    attribution: dict[str, Any],
    consumer: dict[str, Any],
) -> dict[str, Any]:
    span = copy.deepcopy(
        consumer.get(
            "span",
            {
                "line_start": 1,
                "column_start": 0,
                "line_end": 1,
                "column_end": 8,
            },
        )
    )
    event: dict[str, Any] = {
        "event_kind": spec["event_kind"],
        "phase": spec["phase"],
        "attribution": copy.deepcopy(attribution),
        "consumer_path": consumer["caller_path"],
        "caller_object_id": consumer["caller_object_id"],
        "span": span,
        "hit_count": 1,
    }
    if spec["event_kind"] == "opcode_exact_span":
        event["opcode_exact_span"] = {
            "code_qualname": "boundary",
            "code_firstlineno": span["line_start"],
            "instruction_offset": 8,
            "opname": "CALL",
            "argrepr_sha256": "sha256:" + "8" * 64,
        }
    elif spec["event_kind"] == "import_alias_opcode":
        event["import_alias_opcode"] = {
            "code_qualname": "<module>",
            "code_firstlineno": span["line_start"],
            "statement_span": copy.deepcopy(span),
            "alias_ordinal": 0,
            "module": "pkg",
            "name": None,
            "asname": None,
            "level": 0,
            "instruction_offset": 2,
            "opname": "IMPORT_NAME",
            "argval": "pkg",
        }
    else:
        event["callable_entry"] = {
            "code_qualname": "boundary",
            "code_name": "boundary",
            "code_firstlineno": span["line_start"],
            "definition_span": copy.deepcopy(span),
        }
    return event


def _baseline_validation_fixture(
    module: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    tree = "a" * 40
    runner_sha256 = "sha256:" + "b" * 64
    consumer_id = "consumer-" + "c" * 32
    witness_id = "witness-0001"
    node_id = "selector.py::test_placeholder"
    expected_event = {"consumer_span_hit": True, "status": "passed"}
    policy = {
        "selector_policy": {
            "pytest_carrier": copy.deepcopy(TASK0_PYTEST_CARRIER),
            "provider_visible_pytest_selectors": [
                {
                    "selector_id": "focused-01",
                    "ordinal": 1,
                    "pytest_module_path": "selector.py",
                }
            ],
            "controller_only_proof_selectors": [
                {
                    "selector_id": "static-01",
                    "runner_path": "scripts/experiments/es/boundary_proofs.py",
                    "runner_sha256": runner_sha256,
                }
            ],
            "coverage_witness_specs": [
                {
                    "witness_id": witness_id,
                    "selector_id": "focused-01",
                    "consumer_id": consumer_id,
                    "required_proof_kind": "boundary_runtime",
                    "witness_kind": "pytest_runtime",
                    "spec": {"expected_event": expected_event},
                }
            ],
        }
    }
    census = {
        "projection": {"tree": tree},
        "consumer_rows": [
            {
                "consumer_id": consumer_id,
                "caller_path": "model.py",
                "caller_object_id": "d" * 40,
                "required_proof_kind": "boundary_runtime",
            }
        ],
    }
    baseline = {
        "schema_version": "es_f1_boundary_baseline.v1",
        "runner_sha256": runner_sha256,
        "pre_tree": tree,
        "post_tree": tree,
        "aggregate_pytest_argv": list(TASK0_AGGREGATE_PYTEST_ARGV),
        "collected_node_ids": [node_id],
        "collected_node_sha256": module.sequence_sha256([node_id]),
        "collection_total": 1,
        "outcomes": {"passed": 1, "failed": 0, "errors": 0, "skipped": 0},
        "origin_isolation": {
            "report_sha256": "sha256:" + "e" * 64,
            "python_executable": TASK0_PYTHON_TARGET,
            "pytest_carrier": copy.deepcopy(TASK0_PYTEST_CARRIER),
            "plugin_autoload_disabled": True,
            "removed_editable_hooks": [],
            "forbidden_roots": [],
            "forbidden_module_prefixes": [],
            "project_owned_module_prefixes": ["selector"],
            "loaded_forbidden_modules": [],
            "forbidden_origin_rows": [],
            "outside_project_origin_rows": [],
            "projected_origin_rows": [],
            "module_origin_rows": [],
            "cache_artifacts": [],
        },
        "selector_results": [
            {
                "selector_id": "focused-01",
                "pytest_node_ids": [node_id],
                "coverage_witness_ids": [witness_id],
            }
        ],
        "controller_selector_results": [],
        "witness_results": [
            {
                "witness_id": witness_id,
                "selector_id": "focused-01",
                "consumer_id": consumer_id,
                "proof_kind": "boundary_runtime",
                "witness_kind": "pytest_runtime",
                "target_tree": tree,
                "target_path": "model.py",
                "target_blob_id": "d" * 40,
                "mechanically_observed": True,
                "observation": expected_event,
                "observation_sha256": module.raw_sha256(
                    module.canonical_json_bytes(expected_event)
                ),
                "passed": True,
            }
        ],
    }
    return baseline, policy, census


def test_baseline_characterization_rejects_python_identity_substitution() -> None:
    module = _module()
    baseline, policy, census = _baseline_validation_fixture(module)
    baseline["origin_isolation"]["python_executable"] = "/opt/alternate/bin/python3"

    with pytest.raises(module.SourceCensusError, match="baseline_origin_isolation_failed"):
        module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
            baseline,
            policy=policy,
            census=census,
        )


def test_baseline_characterization_rejects_aggregate_argv_substitution() -> None:
    module = _module()
    baseline, policy, census = _baseline_validation_fixture(module)
    baseline["aggregate_pytest_argv"] = [
        "/usr/bin/env",
        "pytest",
        *baseline["aggregate_pytest_argv"][1:],
    ]

    with pytest.raises(module.SourceCensusError, match="baseline_argv_mismatch"):
        module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
            baseline,
            policy=policy,
            census=census,
        )


def test_discover_reads_only_bound_bare_objects_and_is_deterministic(tmp_path: Path) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    discovery_input = _discovery_input(projection)

    first = module.discover_source(discovery_input)
    second = module.discover_source(copy.deepcopy(discovery_input))

    assert module.canonical_json_bytes(first) == module.canonical_json_bytes(second)
    assert first["authority_status"] == "NON_AUTHORITATIVE_DISCOVERY"
    assert "record_sha256" not in first
    assert [row["path"] for row in first["leaf_rows"]] == [
        "linked.py",
        "model.py",
        "notes.txt",
        "selector.py",
    ]
    assert {row["anchor_id"] for row in first["consumer_candidates"]} == {
        "import-registry",
        "call-registry",
        "run-grid-lines",
    }
    notes = next(row for row in first["leaf_rows"] if row["path"] == "notes.txt")
    assert notes["text"] == {
        "is_strict_utf8": True,
        "physical_line_count": 1,
        "lf_octet_count": 0,
    }
    linked = next(row for row in first["leaf_rows"] if row["path"] == "linked.py")
    assert linked["text"] == {
        "is_strict_utf8": False,
        "physical_line_count": None,
        "lf_octet_count": None,
    }
    assert linked["nonmatch_reason"] == "symlink_leaf"


def test_frozen_discovery_covers_plan_mandated_omission_consumers() -> None:
    """Every omission named by the refreeze plan must be policy-addressable."""

    module = _module()
    discovery_input_path = Path(
        "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-discovery-input.json"
    )
    discovery_input = json.loads(discovery_input_path.read_text(encoding="utf-8"))

    discovery = module.discover_source(
        discovery_input,
        discovery_input_sha256=module.raw_sha256(discovery_input_path.read_bytes()),
    )
    candidates_by_path: dict[str, list[dict[str, Any]]] = {}
    for candidate in discovery["consumer_candidates"]:
        candidates_by_path.setdefault(candidate["caller_path"], []).append(candidate)

    assert {
        "ptycho_torch/api/mlflow_utils.py": "MLFLOW_REGISTRATION_OMISSION",
        "ptycho_torch/notebooks/analysis.py": "NOTEBOOK_RELOAD_OMISSION",
    } == {
        path: rows[0]["anchor_id"]
        for path, rows in candidates_by_path.items()
        if path
        in {
            "ptycho_torch/api/mlflow_utils.py",
            "ptycho_torch/notebooks/analysis.py",
        }
    }
    audit_groups = module.frozen_audit_groups(discovery["leaf_rows"])
    assert [row["expected_physical_line_count"] for row in audit_groups] == [
        6776,
        6833,
        11800,
        16052,
        5645,
        21697,
        29886,
        47515,
        50318,
    ]
    tampered_leaves = copy.deepcopy(discovery["leaf_rows"])
    generator = next(
        row
        for row in tampered_leaves
        if row["path"] == "ptycho_torch/generators/cnn.py"
    )
    generator["text"]["physical_line_count"] += 1
    with pytest.raises(module.SourceCensusError, match="audit_group_invalid"):
        module.frozen_audit_groups(tampered_leaves)


@pytest.mark.parametrize("field", ["tree", "inventory_sha256", "leaf_count"])
def test_discover_rejects_each_projection_binding_tamper(
    tmp_path: Path, field: str
) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    discovery_input = _discovery_input(projection)
    discovery_input["projection"][field] = (
        99 if field == "leaf_count" else "sha256:" + "0" * 64
        if field == "inventory_sha256"
        else "0" * 40
    )

    with pytest.raises(module.SourceCensusError):
        module.discover_source(discovery_input)


def test_discover_rejects_non_bare_or_ambient_repository(tmp_path: Path) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    checkout = tmp_path / "checkout"
    subprocess.run([str(GIT), "init", "-q", str(checkout)], check=True)
    discovery_input = _discovery_input(projection)
    discovery_input["projection"]["repository"] = str(checkout)

    with pytest.raises(module.SourceCensusError, match="projection_repository_not_bare"):
        module.discover_source(discovery_input)


def test_discover_ignores_replace_refs_and_rehashes_blob_payloads(tmp_path: Path) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    discovery_input = _discovery_input(projection)
    expected = module.discover_source(discovery_input)
    inventory = _run_git(
        projection["repository"], "ls-tree", "-rz", "-r", projection["commit"]
    )
    model_row = next(
        row for row in inventory.split(b"\0") if row.endswith(b"\tmodel.py")
    )
    original_oid = model_row.split(b" ", 2)[2].split(b"\t", 1)[0].decode()
    replacement_oid = _run_git(
        projection["repository"],
        "hash-object",
        "-w",
        "--stdin",
        data=b"x = 1\n",
    ).decode().strip()
    _run_git(
        projection["repository"],
        "replace",
        original_oid,
        replacement_oid,
    )

    assert module.discover_source(discovery_input) == expected


def test_direct_script_cli_rejects_an_alternate_projection_without_import_failure(
    tmp_path: Path,
) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    discovery_input = _discovery_input(projection)
    input_path = tmp_path / "discovery-input.json"
    schema_path = tmp_path / "schema.json"
    output_path = tmp_path / "discovery-output.json"
    input_raw = json.dumps(discovery_input, indent=2).encode() + b"\n"
    input_path.write_bytes(input_raw)
    schema_path.write_text(
        json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema"}) + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            os.fspath(Path(module.__file__).resolve()),
            "discover",
            "--discovery-input",
            os.fspath(input_path),
            "--discovery-input-schema",
            os.fspath(schema_path),
            "--expected-discovery-input-sha256",
            "sha256:" + hashlib.sha256(input_raw).hexdigest(),
            "--projection-repository",
            os.fspath(projection["repository"]),
            "--projection-commit",
            projection["commit"],
            "--expected-tree",
            projection["tree"],
            "--expected-inventory-sha256",
            projection["inventory_sha256"],
            "--expected-leaf-count",
            str(projection["leaf_count"]),
            "--output",
            os.fspath(output_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 2
    assert "schema_authority_invalid" in completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr
    assert not output_path.exists()

    with pytest.raises(module.SourceCensusError, match="projection_authority_mismatch"):
        module._validate_frozen_projection_authority(  # pyright: ignore[reportPrivateUsage]
            discovery_input["projection"]
        )


def test_direct_script_help_has_repository_import_context() -> None:
    module = _module()
    completed = subprocess.run(
        [sys.executable, os.fspath(Path(module.__file__).resolve()), "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "build-census" in completed.stdout


def test_build_census_recomputes_discovery_and_joins_policy(tmp_path: Path) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    discovery_input = _discovery_input(projection)
    discovery = module.discover_source(discovery_input)
    policy = _policy(discovery_input, discovery)

    census = module.build_source_census(
        discovery_input=discovery_input,
        discovery_output=discovery,
        policy=policy,
        producer=_producer(),
    )

    assert census["preedit_policy_sha256"] == policy["record_sha256"]
    assert len(census["leaf_rows"]) == 4
    assert len(census["consumer_rows"]) == 3
    assert all("proposed_disposition" in row for row in census["consumer_rows"])
    assert module.validate_record_sha256(census) is None


def test_build_census_treats_discovery_producer_as_historical_metadata(
    tmp_path: Path,
) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    discovery_input = _discovery_input(projection)
    discovery = module.discover_source(discovery_input)
    discovery["producer"]["sha256"] = module.raw_sha256(b"historical producer")
    policy = _policy(discovery_input, discovery)

    census = module.build_source_census(
        discovery_input=discovery_input,
        discovery_output=discovery,
        policy=policy,
        producer=_producer(),
    )

    assert census["producer"] == _producer()


def test_build_census_still_rejects_projection_derived_discovery_drift(
    tmp_path: Path,
) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    discovery_input = _discovery_input(projection)
    discovery = module.discover_source(discovery_input)
    discovery["leaf_rows"][0]["byte_count"] += 1
    policy = _policy(discovery_input, discovery)

    with pytest.raises(module.SourceCensusError, match="discovery_recompute_mismatch"):
        module.build_source_census(
            discovery_input=discovery_input,
            discovery_output=discovery,
            policy=policy,
            producer=_producer(),
        )


def test_build_census_rejects_missing_or_revised_policy_consumer(tmp_path: Path) -> None:
    module = _module()
    projection = _bare_projection(tmp_path)
    discovery_input = _discovery_input(projection)
    discovery = module.discover_source(discovery_input)
    policy = _policy(discovery_input, discovery)
    policy["consumer_policies"].pop()
    policy["record_sha256"] = module.compute_record_sha256(policy)

    with pytest.raises(module.SourceCensusError, match="consumer_policy_mismatch"):
        module.build_source_census(
            discovery_input=discovery_input,
            discovery_output=discovery,
            policy=policy,
            producer=_producer(),
        )

    policy = _policy(discovery_input, discovery)
    policy["legacy_bypass_consumer_ids"] = [
        policy["consumer_policies"][0]["consumer_id"]
    ]
    policy["record_sha256"] = module.compute_record_sha256(policy)
    with pytest.raises(module.SourceCensusError, match="legacy_bypass_inventory_invalid"):
        module.build_source_census(
            discovery_input=discovery_input,
            discovery_output=discovery,
            policy=policy,
            producer=_producer(),
        )


def test_build_selector_manifest_requires_observed_witness_and_exact_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    boundary = importlib.import_module("scripts.experiments.es.boundary_proofs")
    projection = _bare_projection(
        tmp_path,
        provider_selector_count=19,
        runtime_consumer_count=20,
    )
    discovery_input = _discovery_input(projection)
    discovery_input["provider_visible_pytest_selectors"] = [
        {
            "selector_id": f"focused-{ordinal:02d}",
            "ordinal": ordinal,
            "pytest_module_path": _provider_selector_path(ordinal),
        }
        for ordinal in range(1, 20)
    ]
    discovery = module.discover_source(discovery_input)
    policy = _policy(discovery_input, discovery)
    runtime_witnesses = [
        row
        for row in policy["selector_policy"]["coverage_witness_specs"]
        if row["witness_kind"] == "pytest_runtime"
    ]
    inherited_runtime_consumers = [
        row
        for row in policy["consumer_policies"]
        if row["witness_kind"] == "pytest_runtime"
        and row["coverage_status"] == "inherited"
    ]
    assert len(runtime_witnesses) == 19
    assert len(inherited_runtime_consumers) == 1
    controller_consumer = inherited_runtime_consumers[0]
    controller_candidate = next(
        row
        for row in discovery["consumer_candidates"]
        if row["consumer_id"] == controller_consumer["consumer_id"]
    )
    controller_witness_id = "witness-controller-pytest"
    controller_consumer.update(
        {
            "selector_id": "CO-PYTEST-01",
            "witness_kind": "controller_pytest_runtime",
            "coverage_status": "required",
            "coverage_witness_ids": [controller_witness_id],
        }
    )
    controller_witness = {
        "witness_id": controller_witness_id,
        "selector_id": "CO-PYTEST-01",
        "witness_kind": "controller_pytest_runtime",
        "consumer_id": controller_consumer["consumer_id"],
        "required_proof_kind": "boundary_runtime",
        "spec": {
            "anchor_id": controller_candidate["anchor_id"],
            "event_kind": "opcode_exact_span",
            "phase": "collection",
            "attribution": {
                "attribution_kind": "selector_module",
                "pytest_module_path": "tests/private/test_driver.py",
            },
            "expected_event": {"consumer_span_hit": True, "status": "passed"},
        },
    }
    policy["selector_policy"]["coverage_witness_specs"].append(
        controller_witness
    )
    policy["selector_policy"]["desired_state_proof_specs"].append(
        {
            "proof_spec_id": "proof-controller-pytest",
            "witness_id": controller_witness_id,
            "proof_kind": "boundary_runtime",
            "expected_result": copy.deepcopy(
                controller_witness["spec"]["expected_event"]
            ),
        }
    )
    policy["selector_policy"]["controller_only_proof_selectors"].append(
        {
            "selector_id": "CO-PYTEST-01",
            "ordinal": 2,
            "proof_kind": "boundary_runtime",
            "execution_kind": "pytest_aggregate",
            "runner_path": "scripts/experiments/es/boundary_proofs.py",
            "runner_sha256": "sha256:" + "1" * 64,
            "argv": [
                TASK0_PYTHON,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/private/test_driver.py",
            ],
            "input_bindings": [
                {
                    "path": "tests/private/test_driver.py",
                    "sha256": "sha256:" + "3" * 64,
                }
            ],
            "coverage_witness_ids": [controller_witness["witness_id"]],
        }
    )
    for ordinal, witness in enumerate(runtime_witnesses, 1):
        witness["selector_id"] = f"focused-{ordinal:02d}"
        witness["spec"]["attribution"]["pytest_node_pattern"] = (
            rf"{re.escape(_provider_selector_path(ordinal))}::"
            rf"test_placeholder{'' if ordinal == 1 else f'_{ordinal:02d}'}"
        )
    runner_sha256 = module.raw_sha256(Path(boundary.__file__).read_bytes())
    for selector in policy["selector_policy"]["controller_only_proof_selectors"]:
        selector["runner_sha256"] = runner_sha256
    policy["record_sha256"] = module.compute_record_sha256(policy)
    census = module.build_source_census(
        discovery_input=discovery_input,
        discovery_output=discovery,
        policy=policy,
        producer=_producer(),
    )
    node_ids = [_provider_selector_node(ordinal) for ordinal in range(1, 20)]
    node_id = node_ids[0]
    controller_node = "tests/private/test_driver.py::test_boundary"
    witness_results = []
    for row in policy["selector_policy"]["coverage_witness_specs"]:
        consumer = next(
            item for item in census["consumer_rows"]
            if item["consumer_id"] == row["consumer_id"]
        )
        observation = copy.deepcopy(row["spec"]["expected_event"])
        result = {
            "witness_id": row["witness_id"],
            "selector_id": row["selector_id"],
            "consumer_id": row["consumer_id"],
            "proof_kind": row["required_proof_kind"],
            "witness_kind": row["witness_kind"],
            "target_tree": projection["tree"],
            "target_path": consumer["caller_path"],
            "target_blob_id": consumer["caller_object_id"],
            "mechanically_observed": True,
            "observation": observation,
            "observation_sha256": module.raw_sha256(
                module.canonical_json_bytes(observation)
            ),
            "passed": True,
        }
        if row["witness_kind"] == "pytest_runtime":
            selector_ordinal = int(str(row["selector_id"]).removeprefix("focused-"))
            result["source_event"] = _runtime_source_event_fixture(
                spec=row["spec"],
                attribution={
                    "attribution_kind": "pytest_node",
                    "pytest_node_id": node_ids[selector_ordinal - 1],
                },
                consumer=consumer,
            )
        elif row["witness_kind"] == "controller_pytest_runtime":
            result["source_event"] = _runtime_source_event_fixture(
                spec=row["spec"],
                attribution={
                    "attribution_kind": "selector_module",
                    "pytest_module_path": "tests/private/test_driver.py",
                },
                consumer=consumer,
            )
        witness_results.append(result)
    baseline = {
        "schema_version": "es_f1_boundary_baseline.v1",
        "runner_sha256": runner_sha256,
        "pre_tree": projection["tree"],
        "post_tree": projection["tree"],
        "aggregate_pytest_argv": list(TASK0_AGGREGATE_PYTEST_ARGV),
        "collected_node_ids": node_ids,
        "collected_node_sha256": module.sequence_sha256(node_ids),
        "collection_total": 19,
        "outcomes": {"passed": 19, "failed": 0, "errors": 0, "skipped": 0},
        "origin_isolation": {
            "report_sha256": "sha256:" + "5" * 64,
            "python_executable": TASK0_PYTHON_TARGET,
            "pytest_carrier": copy.deepcopy(TASK0_PYTEST_CARRIER),
            "plugin_autoload_disabled": True,
            "removed_editable_hooks": [],
            "forbidden_roots": [],
            "forbidden_module_prefixes": [],
            "project_owned_module_prefixes": ["selector"],
            "loaded_forbidden_modules": [],
            "forbidden_origin_rows": [],
            "outside_project_origin_rows": [],
            "projected_origin_rows": [],
            "module_origin_rows": [],
            "cache_artifacts": [],
        },
        "selector_results": [
            {
                "selector_id": f"focused-{ordinal:02d}",
                "pytest_node_ids": [node_ids[ordinal - 1]],
                "coverage_witness_ids": (
                    [
                        row["witness_id"]
                        for row in runtime_witnesses
                        if row["selector_id"] == f"focused-{ordinal:02d}"
                    ]
                ),
            }
            for ordinal in range(1, 20)
        ],
        "controller_selector_results": [
            {
                "selector_id": "CO-PYTEST-01",
                "execution_kind": "pytest_aggregate",
                "argv": copy.deepcopy(
                    policy["selector_policy"]["controller_only_proof_selectors"][1][
                        "argv"
                    ]
                ),
                "collected_node_ids": [controller_node],
                "collected_node_sha256": module.sequence_sha256([controller_node]),
                "collection_total": 1,
                "outcomes": {
                    "passed": 1,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                },
                "origin_isolation": {
                    "report_sha256": "sha256:" + "6" * 64,
                    "python_executable": TASK0_PYTHON_TARGET,
                    "pytest_carrier": copy.deepcopy(TASK0_PYTEST_CARRIER),
                    "plugin_autoload_disabled": True,
                    "removed_editable_hooks": [],
                    "forbidden_roots": [],
                    "forbidden_module_prefixes": [],
                    "project_owned_module_prefixes": ["selector"],
                    "loaded_forbidden_modules": [],
                    "forbidden_origin_rows": [],
                    "outside_project_origin_rows": [],
                    "projected_origin_rows": [],
                    "module_origin_rows": [],
                    "cache_artifacts": [],
                },
                "trace_sha256": module.raw_sha256(
                    module.canonical_json_bytes(
                        [
                            {
                                "witness_id": controller_witness["witness_id"],
                                "source_event": next(
                                    row["source_event"]
                                    for row in witness_results
                                    if row["witness_id"]
                                    == controller_witness["witness_id"]
                                ),
                            }
                        ]
                    )
                ),
                "coverage_witness_ids": [controller_witness["witness_id"]],
                "coverage_witness_node_outcomes": [],
            }
        ],
        "witness_results": witness_results,
    }
    cluster_domain = [
        "IDENTITY_CONFIG",
        "CONSTRUCTION_ADAPTERS",
        "TRAINING_OPTIMIZER",
        "PERSISTENCE_REBUILD",
        "INFERENCE_WORKFLOWS",
        "CONSUMER_BYPASS",
    ]
    capture = {
        "schema_version": "es_f1_feasibility_capture_manifest.v1",
        "lifecycle": "retained_pending_ordered_reviews",
        "deterministic_sha256": "sha256:" + "8" * 64,
    }
    capture["record_sha256"] = module.compute_record_sha256(capture)
    feasibility = {
        "schema_version": "es_f1_structural_multi_context_feasibility.v1",
        "capture_manifest_path": (
            "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "feasibility-capture-manifest.json"
        ),
        "capture_manifest_sha256": capture["record_sha256"],
        "capture_deterministic_sha256": capture["deterministic_sha256"],
        "capture_lifecycle": "retained_pending_ordered_reviews",
        "source_tree_before": projection["tree"],
        "source_tree_after": "f" * 40,
        "cluster_domain": cluster_domain,
        "unmet_clusters": [
            {
                "cluster_id": cluster_id,
                "baseline_ledger_id": f"baseline-{ordinal}",
                "remove_one_ledger_id": f"remove-one-{ordinal}",
                "primary_production_paths": [f"pkg/{ordinal}.py"],
                "changed_production_paths": [f"pkg/{ordinal}.py"],
                "responsibility_ids": ["CONSTRUCTION"],
            }
            for ordinal, cluster_id in enumerate(cluster_domain[:4], 1)
        ],
        "integration_edges": [
            {
                "edge_id": f"edge-{ordinal}",
                "from_cluster": cluster_domain[ordinal - 1],
                "to_cluster": cluster_domain[ordinal],
                "producer_blob_oid": f"{ordinal:x}" * 40,
                "consumer_blob_oid": f"{ordinal + 3:x}" * 40,
                "ledger_id": "green-1",
                "pytest_node_id": "tests/test_vertical.py::test_edge",
            }
            for ordinal in range(1, 4)
        ],
        "delta": {
            "implementation_additions": 12,
            "implementation_deletions": 1,
            "physical_line_count": 12,
            "changed_production_paths": [f"pkg/{ordinal}.py" for ordinal in range(1, 5)],
        },
        "non_collapse": {
            "distinct_production_blob_count": 4,
            "distinct_cluster_path_sets": 4,
        },
    }
    feasibility_holder = {"value": feasibility}

    class _FakeFeasibilityProofs:
        @staticmethod
        def validate_feasibility_capture_manifest_record(
            value: dict[str, Any], *, reobserve_roots: bool
        ) -> dict[str, Any]:
            assert reobserve_roots is True
            assert value is capture
            return value

        @staticmethod
        def derive_feasibility_facts(value: dict[str, Any]) -> dict[str, Any]:
            assert value is capture
            return copy.deepcopy(feasibility_holder["value"])

    monkeypatch.setattr(
        module, "_feasibility_proofs_module", lambda: _FakeFeasibilityProofs
    )

    projection_blobs = {
        _provider_selector_path(ordinal): module.projection_blob(
            census, _provider_selector_path(ordinal)
        )
        for ordinal in range(1, 20)
    }
    manifest = module.build_selector_manifest(
        policy=policy,
        census=census,
        baseline_characterization=baseline,
        feasibility_capture_manifest=capture,
        projection_blobs=projection_blobs,
    )
    selector_schema = json.loads(
        Path(
            "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "preedit-selector-manifest.schema.json"
        ).read_text(encoding="utf-8")
    )
    feasibility_schema = {
        "$schema": selector_schema["$schema"],
        "$ref": "#/$defs/feasibility_spike",
        "$defs": selector_schema["$defs"],
    }
    assert not list(
        Draft202012Validator(feasibility_schema).iter_errors(
            manifest["feasibility_spike"]
        )
    )
    assert manifest["provider_visible_pytest_selectors"][0]["pytest_node_ids"] == [
        node_id
    ]
    assert [row["proof_id"] for row in manifest["desired_state_proof_specs"]] == [
        row["proof_spec_id"]
        for row in policy["selector_policy"]["desired_state_proof_specs"]
    ]
    assert all(
        {
            "caller_object_id",
            "column_start",
            "column_end",
        }
        <= set(row)
        for row in manifest["coverage_witnesses"]
    )
    boundary.validate_contract(
        manifest,
        consumer_rows=census["consumer_rows"],
        expected_runner_sha256=runner_sha256,
    )

    bad = copy.deepcopy(baseline)
    bad["witness_results"][0]["mechanically_observed"] = False
    with pytest.raises(module.SourceCensusError, match="coverage_witness_unobserved"):
        module.build_selector_manifest(
            policy=policy,
            census=census,
            baseline_characterization=bad,
            feasibility_capture_manifest=capture,
            projection_blobs=projection_blobs,
        )

    bad_truth = copy.deepcopy(baseline)
    bad_truth["witness_results"][0]["passed"] = False
    with pytest.raises(module.SourceCensusError, match="coverage_witness_truth_mismatch"):
        module.build_selector_manifest(
            policy=policy,
            census=census,
            baseline_characterization=bad_truth,
            feasibility_capture_manifest=capture,
            projection_blobs=projection_blobs,
        )

    bad_feasibility = copy.deepcopy(feasibility)
    bad_feasibility["unmet_clusters"].pop()
    feasibility_holder["value"] = bad_feasibility
    with pytest.raises(module.SourceCensusError, match="feasibility"):
        module.build_selector_manifest(
            policy=policy,
            census=census,
            baseline_characterization=baseline,
            feasibility_capture_manifest=capture,
            projection_blobs=projection_blobs,
        )


_TASK0_REVIEW_FINDINGS = (
    "anti_padding_accepted",
    "non_synthetic_baseline_and_remove_one_failures_accepted",
    "three_authenticated_ast_trace_cross_blob_edges_accepted",
    "four_independently_unmet_clusters_accepted",
    "non_collapse_requirement_accepted",
    "strict_reference_size_gate_5000_10000_deferred_to_task_3a",
    "operational_criterion_not_a_universal_provider_context_theorem",
)


def _task0_review_view_bytes(
    *,
    verdict: str,
    reviewer: str,
    reviewed_at: str,
    bindings: Mapping[str, str],
    decoy_verdict: str | None = None,
) -> bytes:
    lines = [
        "# Task-0 review fixture",
        "",
        f"verdict: {verdict}",
        f"reviewer: {reviewer}",
        f"reviewed_at: {reviewed_at}",
        *(f"{key}: {bindings[key]}" for key in bindings),
        *_TASK0_REVIEW_FINDINGS,
    ]
    if decoy_verdict is not None:
        lines.append(f"Prose mentions {decoy_verdict} without adopting it.")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def test_validate_review_adoption_requires_order_distinct_reviewers_bindings_and_view_bytes(
    tmp_path: Path,
) -> None:
    module = _module()
    specification_view = (
        tmp_path
        / "artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md"
    )
    quality_view = (
        tmp_path
        / "artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md"
    )
    specification_view.parent.mkdir(parents=True)
    common_bindings = {
        "plan_sha256": "sha256:" + "1" * 64,
        "preedit_policy_sha256": "sha256:" + "2" * 64,
        "source_census_sha256": "sha256:" + "3" * 64,
        "selector_manifest_sha256": "sha256:" + "4" * 64,
        "a1_anchor_sha256": "sha256:" + "5" * 64,
    }
    specification_view.write_bytes(
        _task0_review_view_bytes(
            verdict="ES_F1_SCOPE_AMENDMENT_PLAN_SPEC_APPROVED",
            reviewer="reviewer-a",
            reviewed_at="2026-08-03T01:00:00Z",
            bindings=common_bindings,
        )
    )
    quality_view.write_bytes(
        _task0_review_view_bytes(
            verdict="ES_F1_SCOPE_AMENDMENT_PLAN_QUALITY_APPROVED",
            reviewer="reviewer-b",
            reviewed_at="2026-08-03T02:00:00Z",
            bindings=common_bindings,
        )
    )
    specification_view_sha256 = module.raw_sha256(specification_view.read_bytes())
    quality_view_sha256 = module.raw_sha256(quality_view.read_bytes())
    tombstone = {
        "purged_at": "2026-08-03T03:00:00Z",
        "reviews": [
            {
                "review_kind": "specification",
                "path": "artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md",
                "sha256": specification_view_sha256,
            },
            {
                "review_kind": "quality",
                "path": "artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md",
                "sha256": quality_view_sha256,
            },
        ],
    }
    tombstone["record_sha256"] = module.compute_record_sha256(tombstone)
    top_level_bindings = {
        **common_bindings,
        "post_purge_tombstone_sha256": tombstone["record_sha256"],
    }
    adoption: dict[str, Any] = {
        "schema_version": "es_f1_task0_review_adoption.v1",
        "evidence_status": "approved",
        "bindings": top_level_bindings,
        "reviews": [
            {
                "review_kind": "specification",
                "reviewer": "reviewer-a",
                "verdict": "ES_F1_SCOPE_AMENDMENT_PLAN_SPEC_APPROVED",
                "reviewed_at": "2026-08-03T01:00:00Z",
                "review_view_path": "artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md",
                "review_view_sha256": specification_view_sha256,
                "bindings": common_bindings,
            },
            {
                "review_kind": "quality",
                "reviewer": "reviewer-b",
                "verdict": "ES_F1_SCOPE_AMENDMENT_PLAN_QUALITY_APPROVED",
                "reviewed_at": "2026-08-03T02:00:00Z",
                "review_view_path": "artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md",
                "review_view_sha256": quality_view_sha256,
                "bindings": common_bindings,
            },
        ],
    }
    adoption["record_sha256"] = module.compute_record_sha256(adoption)
    adoption_schema = json.loads(
        Path(
            "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "task0-review-adoption.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert not list(Draft202012Validator(adoption_schema).iter_errors(adoption))
    module.validate_review_adoption(
        adoption,
        expected_bindings=common_bindings,
        expected_post_purge_tombstone_sha256=top_level_bindings[
            "post_purge_tombstone_sha256"
        ],
        post_purge_tombstone=tombstone,
        review_view_root=tmp_path,
    )

    real_artifacts = tmp_path / "real-artifacts"
    artifacts = tmp_path / "artifacts"
    artifacts.rename(real_artifacts)
    artifacts.symlink_to(real_artifacts, target_is_directory=True)
    with pytest.raises(module.SourceCensusError, match="review_adoption_view_invalid"):
        module.validate_review_adoption(
            adoption,
            expected_bindings=common_bindings,
            expected_post_purge_tombstone_sha256=top_level_bindings[
                "post_purge_tombstone_sha256"
            ],
            post_purge_tombstone=tombstone,
            review_view_root=tmp_path,
        )
    artifacts.unlink()
    real_artifacts.rename(artifacts)

    for mutation in ("reorder", "duplicate", "stale"):
        bad = copy.deepcopy(adoption)
        if mutation == "reorder":
            bad["reviews"].reverse()
        elif mutation == "duplicate":
            bad["reviews"][1]["reviewer"] = "reviewer-a"
        else:
            bad["bindings"]["plan_sha256"] = "sha256:" + "0" * 64
        bad["record_sha256"] = module.compute_record_sha256(bad)
        with pytest.raises(module.SourceCensusError):
            module.validate_review_adoption(
                bad,
                expected_bindings=common_bindings,
                expected_post_purge_tombstone_sha256=top_level_bindings[
                    "post_purge_tombstone_sha256"
                ],
                post_purge_tombstone=tombstone,
                review_view_root=tmp_path,
            )

    quality_view.write_text("# Stale replacement\n", encoding="utf-8")
    with pytest.raises(module.SourceCensusError, match="review_adoption_view_invalid"):
        module.validate_review_adoption(
            adoption,
            expected_bindings=common_bindings,
            expected_post_purge_tombstone_sha256=top_level_bindings[
                "post_purge_tombstone_sha256"
            ],
            post_purge_tombstone=tombstone,
            review_view_root=tmp_path,
        )

    missing_tombstone_binding = copy.deepcopy(adoption)
    missing_tombstone_binding["bindings"].pop("post_purge_tombstone_sha256")
    missing_tombstone_binding["record_sha256"] = module.compute_record_sha256(
        missing_tombstone_binding
    )
    with pytest.raises(module.SourceCensusError, match="review_adoption_binding_mismatch"):
        module.validate_review_adoption(
            missing_tombstone_binding,
            expected_bindings=common_bindings,
            expected_post_purge_tombstone_sha256=top_level_bindings[
                "post_purge_tombstone_sha256"
            ],
            post_purge_tombstone=tombstone,
            review_view_root=tmp_path,
        )

    quality_view.write_bytes(
        _task0_review_view_bytes(
            verdict="ES_F1_SCOPE_AMENDMENT_PLAN_QUALITY_APPROVED",
            reviewer="reviewer-b",
            reviewed_at="2026-08-03T02:00:00Z",
            bindings=common_bindings,
        )
    )
    purge_first = copy.deepcopy(tombstone)
    purge_first["purged_at"] = "2026-08-03T00:30:00Z"
    purge_first["record_sha256"] = module.compute_record_sha256(purge_first)
    purge_first_adoption = copy.deepcopy(adoption)
    purge_first_adoption["bindings"]["post_purge_tombstone_sha256"] = purge_first[
        "record_sha256"
    ]
    purge_first_adoption["record_sha256"] = module.compute_record_sha256(
        purge_first_adoption
    )
    with pytest.raises(module.SourceCensusError, match="review_adoption_order_invalid"):
        module.validate_review_adoption(
            purge_first_adoption,
            expected_bindings=common_bindings,
            expected_post_purge_tombstone_sha256=purge_first["record_sha256"],
            post_purge_tombstone=purge_first,
            review_view_root=tmp_path,
        )

    rejected_raw = _task0_review_view_bytes(
        verdict="REJECTED",
        reviewer="reviewer-a",
        reviewed_at="2026-08-03T01:00:00Z",
        bindings=common_bindings,
        decoy_verdict="ES_F1_SCOPE_AMENDMENT_PLAN_SPEC_APPROVED",
    )
    specification_view.write_bytes(rejected_raw)
    rejected_digest = module.raw_sha256(rejected_raw)
    rejected_tombstone = copy.deepcopy(tombstone)
    rejected_tombstone["reviews"][0]["sha256"] = rejected_digest
    rejected_tombstone["record_sha256"] = module.compute_record_sha256(
        rejected_tombstone
    )
    rejected_adoption = copy.deepcopy(adoption)
    rejected_adoption["reviews"][0]["review_view_sha256"] = rejected_digest
    rejected_adoption["bindings"]["post_purge_tombstone_sha256"] = (
        rejected_tombstone["record_sha256"]
    )
    rejected_adoption["record_sha256"] = module.compute_record_sha256(
        rejected_adoption
    )
    with pytest.raises(module.SourceCensusError, match="review_adoption_view_invalid"):
        module.validate_review_adoption(
            rejected_adoption,
            expected_bindings=common_bindings,
            expected_post_purge_tombstone_sha256=rejected_tombstone[
                "record_sha256"
            ],
            post_purge_tombstone=rejected_tombstone,
            review_view_root=tmp_path,
        )


def test_post_purge_tombstone_binds_capture_reviews_and_fresh_absence(
    tmp_path: Path,
) -> None:
    module = _module()
    review_root = tmp_path / "review-root"
    specification_view = (
        review_root
        / "artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md"
    )
    quality_view = (
        review_root
        / "artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md"
    )
    specification_view.parent.mkdir(parents=True)
    specification_view.write_text("# Specification\n", encoding="utf-8")
    quality_view.write_text("# Quality\n", encoding="utf-8")
    roots = [
        {
            "root_id": f"root-{ordinal:032x}",
            "canonical_path": str((tmp_path / f"absent-{ordinal}").resolve()),
        }
        for ordinal in range(1, 8)
    ]
    capture: dict[str, Any] = {
        "disposable_roots": [
            {
                **row,
                "root_kind": "source_tree",
                "variant_id": f"variant-{ordinal}",
                "pre_purge_lstat": "directory",
                "tree_oid": f"{ordinal:x}" * 40,
            }
            for ordinal, row in enumerate(roots[:6], 1)
        ]
        + [
            {
                **roots[6],
                "root_kind": "git_object_store",
                "pre_purge_lstat": "directory",
                "snapshot_sha256": "sha256:" + "7" * 64,
            }
        ],
    }
    capture["record_sha256"] = module.compute_record_sha256(capture)
    tombstone: dict[str, Any] = {
        "schema_version": "es_f1_feasibility_post_purge_tombstone.v1",
        "evidence_status": "purged_after_ordered_reviews",
        "purged_at": "2026-08-04T01:00:00Z",
        "capture_manifest": {
            "path": (
                "docs/plans/evidence/es-f1-large-scope-refreeze/"
                "feasibility-capture-manifest.json"
            ),
            "sha256": capture["record_sha256"],
        },
        "reviews": [
            {
                "review_kind": "specification",
                "path": (
                    "artifacts/review/"
                    "es-f1-large-scope-amendment-plan-specification-review.md"
                ),
                "sha256": module.raw_sha256(specification_view.read_bytes()),
            },
            {
                "review_kind": "quality",
                "path": (
                    "artifacts/review/"
                    "es-f1-large-scope-amendment-plan-quality-review.md"
                ),
                "sha256": module.raw_sha256(quality_view.read_bytes()),
            },
        ],
        "absent_roots": [{**row, "lstat": "absent"} for row in roots],
    }
    tombstone["record_sha256"] = module.compute_record_sha256(tombstone)
    schema = json.loads(
        Path(
            "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "feasibility-post-purge-tombstone.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert not list(Draft202012Validator(schema).iter_errors(tombstone))
    module.validate_post_purge_tombstone(
        tombstone,
        capture_manifest=capture,
        review_view_root=review_root,
    )

    real_artifacts = review_root / "real-artifacts"
    artifacts = review_root / "artifacts"
    artifacts.rename(real_artifacts)
    artifacts.symlink_to(real_artifacts, target_is_directory=True)
    with pytest.raises(module.SourceCensusError, match="post_purge_review_invalid"):
        module.validate_post_purge_tombstone(
            tombstone,
            capture_manifest=capture,
            review_view_root=review_root,
        )
    artifacts.unlink()
    real_artifacts.rename(artifacts)

    present = Path(roots[0]["canonical_path"])
    present.mkdir()
    with pytest.raises(module.SourceCensusError, match="post_purge_root_present"):
        module.validate_post_purge_tombstone(
            tombstone,
            capture_manifest=capture,
            review_view_root=review_root,
        )
    present.rmdir()

    stale = copy.deepcopy(tombstone)
    stale["reviews"][1]["sha256"] = "sha256:" + "0" * 64
    stale["record_sha256"] = module.compute_record_sha256(stale)
    with pytest.raises(module.SourceCensusError, match="post_purge_review_invalid"):
        module.validate_post_purge_tombstone(
            stale,
            capture_manifest=capture,
            review_view_root=review_root,
        )


def test_cli_parser_exposes_the_non_authoritative_policy_completion_phase() -> None:
    module = _module()
    parser = module.build_argument_parser()
    choices = parser._subparsers._group_actions[0].choices  # pyright: ignore[reportPrivateUsage]
    assert set(choices) == {
        "discover",
        "complete-policy-candidate",
        "publish-policy",
        "build-census",
        "build-selector",
        "validate",
    }
    completion_options = {
        option
        for action in choices["complete-policy-candidate"]._actions  # pyright: ignore[reportPrivateUsage]
        for option in action.option_strings
    }
    assert completion_options == {
        "-h",
        "--help",
        "--discovery-input",
        "--expected-discovery-input-sha256",
        "--discovery-output",
        "--expected-discovery-output-sha256",
        "--observation-candidates",
        "--expected-observation-candidates-sha256",
        "--reviewed-dispositions",
        "--expected-reviewed-dispositions-sha256",
        "--producer-sha256",
        "--proof-runner-sha256",
        "--no-consumption-captured-at",
        "--a1-evidence-root",
        "--output",
    }
    publication_options = {
        option
        for action in choices["publish-policy"]._actions  # pyright: ignore[reportPrivateUsage]
        for option in action.option_strings
    }
    assert publication_options == {
        "-h",
        "--help",
        "--candidate",
        "--expected-candidate-sha256",
        "--plan",
        "--expected-plan-sha256",
        "--plan-spec-review",
        "--expected-plan-spec-review-sha256",
        "--plan-quality-review",
        "--expected-plan-quality-review-sha256",
        "--implementation-review",
        "--expected-implementation-review-sha256",
        "--policy-schema",
        "--output",
    }
    validate_options = {
        option
        for action in choices["validate"]._actions  # pyright: ignore[reportPrivateUsage]
        for option in action.option_strings
    }
    assert {
        "--feasibility-capture-manifest",
        "--feasibility-capture-manifest-schema",
        "--expected-feasibility-capture-manifest-sha256",
        "--post-purge-tombstone",
        "--post-purge-tombstone-schema",
        "--expected-post-purge-tombstone-sha256",
    } <= validate_options
    build_selector_options = {
        option
        for action in choices["build-selector"]._actions  # pyright: ignore[reportPrivateUsage]
        for option in action.option_strings
    }
    assert {
        "--feasibility-capture-manifest",
        "--feasibility-capture-manifest-schema",
        "--expected-feasibility-capture-manifest-sha256",
    } <= build_selector_options
    assert "--feasibility-spike" not in build_selector_options


def test_schema_bindings_include_capture_and_post_purge_lifecycle_contracts() -> None:
    module = _module()
    bindings = module.current_schema_bindings()
    by_role = {row["role"]: row["path"] for row in bindings}
    assert by_role["feasibility_capture"] == (
        "docs/plans/evidence/es-f1-large-scope-refreeze/"
        "feasibility-capture-manifest.schema.json"
    )
    assert by_role["post_purge_tombstone"] == (
        "docs/plans/evidence/es-f1-large-scope-refreeze/"
        "feasibility-post-purge-tombstone.schema.json"
    )
    for role in ("feasibility_capture", "post_purge_tombstone"):
        schema = json.loads(Path(by_role[role]).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    selector_schema_text = Path(
        by_role["selector_manifest"]
    ).read_text(encoding="utf-8")
    for forbidden_claim_field in (
        "good_faith_reference_band_expectation",
        "temporary_implementation_retained",
        "removal_control_passed",
    ):
        assert forbidden_claim_field not in selector_schema_text
    assert "capture_manifest_sha256" in selector_schema_text
    assert "capture_deterministic_sha256" in selector_schema_text
    assert "non_collapse" in selector_schema_text


def test_raw_sha256_is_prefixed_and_sequence_digest_is_order_sensitive() -> None:
    module = _module()
    assert module.raw_sha256(b"x") == "sha256:" + hashlib.sha256(b"x").hexdigest()
    assert module.sequence_sha256(["a", "b"]) != module.sequence_sha256(["b", "a"])


def test_no_consumption_scope_rejects_repeated_or_substituted_paths() -> None:
    module = _module()
    external_paths = [
        "/home/ollie/.local/state/orchestrator/es-f1-full/runs",
        "/home/ollie/.local/state/orchestrator/es-f1-full/run-refs",
        "/home/ollie/.local/share/agent-orchestration/es-f1-full/evidence",
    ]
    repository_paths = [
        "experiments/orc_effectiveness/f1_es/decision-lock.json",
        "experiments/orc_effectiveness/f1_es/controller-package.json",
        "experiments/orc_effectiveness/f1_es/prelaunch-owner-adoption.json",
        "experiments/orc_effectiveness/f1_es/launch-manifest.json",
    ]

    def observation(external: list[str], repository: list[str]) -> dict[str, Any]:
        external_rows = [
            {"path": path, "status": "ABSENT", "immediate_entries": []}
            for path in external
        ]
        repository_rows = [
            {"path": path, "status": "ABSENT"} for path in repository
        ]
        return {
            "captured_at": "2026-08-04T00:00:00Z",
            "external_roots": external_rows,
            "repository_paths": repository_rows,
            "observation_sha256": module.no_consumption_observation_sha256(
                external_rows, repository_rows
            ),
        }

    module._validate_no_consumption(  # pyright: ignore[reportPrivateUsage]
        observation(external_paths, repository_paths), reobserve=False
    )
    bogus = observation(
        ["/definitely-not-the-f1-root"] * 3,
        ["definitely/not/the/f1/control.json"] * 4,
    )
    with pytest.raises(module.SourceCensusError, match="no_consumption_scope_invalid"):
        module._validate_no_consumption(bogus, reobserve=False)  # pyright: ignore[reportPrivateUsage]

    for schema_name in (
        "preedit-policy-manifest.schema.json",
        "source-census.schema.json",
    ):
        schema = json.loads(
            Path(
                "docs/plans/evidence/es-f1-large-scope-refreeze", schema_name
            ).read_text(encoding="utf-8")
        )
        no_consumption_schema = {
            "$schema": schema["$schema"],
            "$ref": "#/$defs/no_consumption",
            "$defs": schema["$defs"],
        }
        assert list(Draft202012Validator(no_consumption_schema).iter_errors(bogus))


def test_official_policy_schema_accepts_structured_desired_results() -> None:
    schema = json.loads(
        Path(
            "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "preedit-policy-manifest.schema.json"
        ).read_text(encoding="utf-8")
    )
    desired_schema = {
        "$schema": schema["$schema"],
        "$ref": "#/$defs/desired_proof_spec",
        "$defs": schema["$defs"],
    }
    row = {
        "proof_spec_id": "proof-1",
        "witness_id": "witness-1",
        "proof_kind": "boundary_runtime",
        "expected_result": {"consumer_span_hit": True, "status": "passed"},
    }
    assert not list(Draft202012Validator(desired_schema).iter_errors(row))


def test_task7_policy_schema_requires_closed_witness_observability_reviews() -> None:
    schema = json.loads(
        Path(
            "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "preedit-policy-manifest.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert "witness_observability_reviews" in schema["required"]
    review_schema = {
        "$schema": schema["$schema"],
        "$ref": "#/$defs/witness_observability_reviews",
        "$defs": schema["$defs"],
    }
    reviews = {
        "plan": {
            "path": "docs/plans/2026-08-04-es-f1-witness-observability-correction-plan.md",
            "sha256": "sha256:" + "1" * 64,
        },
        "plan_specification_review": {
            "path": "artifacts/review/es-f1-witness-observability-plan-spec-review.json",
            "sha256": "sha256:" + "2" * 64,
            "verdict": "ES_F1_WITNESS_PLAN_SPEC_APPROVED",
        },
        "plan_quality_review": {
            "path": "artifacts/review/es-f1-witness-observability-plan-quality-review.json",
            "sha256": "sha256:" + "3" * 64,
            "verdict": "ES_F1_WITNESS_PLAN_QUALITY_APPROVED",
        },
        "implementation_review": {
            "path": "artifacts/review/es-f1-witness-observability-implementation-review.json",
            "sha256": "sha256:" + "4" * 64,
            "verdict": "ES_F1_WITNESS_IMPLEMENTATION_APPROVED",
            "candidate_set_sha256": "sha256:" + "5" * 64,
        },
    }
    validator = Draft202012Validator(review_schema)
    assert not list(validator.iter_errors(reviews))
    extra = copy.deepcopy(reviews)
    extra["implementation_review"]["extra"] = True
    assert list(validator.iter_errors(extra))


# Task 1A contract RED: these fragments freeze the reviewed witness-observability
# shapes before either unaccepted v1 schema is amended.
_TASK1_POLICY_SCHEMA_PATH = Path(
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "preedit-policy-manifest.schema.json"
)
_TASK1_SELECTOR_SCHEMA_PATH = Path(
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "preedit-selector-manifest.schema.json"
)
_TASK1_CENSUS_SCHEMA_PATH = Path(
    "docs/plans/evidence/es-f1-large-scope-refreeze/source-census.schema.json"
)


def _task1_schema_validator(path: Path, definition: str) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    return Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$ref": f"#/$defs/{definition}",
            "$defs": schema["$defs"],
        }
    )


def _task1_controller_selector(execution_kind: str) -> dict[str, Any]:
    if execution_kind == "pytest_aggregate":
        proof_kind = "boundary_runtime"
        argv = list(TASK0_AGGREGATE_PYTEST_ARGV)
        bindings = [
            {"path": path, "sha256": "sha256:" + f"{ordinal:064x}"}
            for ordinal, path in enumerate(TASK0_PROVIDER_MODULES, 1)
        ]
        selector_id = "CO-PYTEST-01"
    elif execution_kind == "isolated_probe":
        proof_kind = "boundary_runtime"
        argv = ["isolated-probe", "--selector-id", "CO-PROBE-01"]
        bindings = [
            {"path": "pkg/probe.py", "sha256": "sha256:" + "2" * 64}
        ]
        selector_id = "CO-PROBE-01"
    else:
        proof_kind = "non_cdi_static"
        argv = ["static-ast", "--selector-id", "CO-STATIC-01"]
        bindings = [
            {"path": "pkg/static.py", "sha256": "sha256:" + "3" * 64}
        ]
        selector_id = "CO-STATIC-01"
    return {
        "selector_id": selector_id,
        "ordinal": 1,
        "proof_kind": proof_kind,
        "execution_kind": execution_kind,
        "runner_path": "scripts/experiments/es/boundary_proofs.py",
        "runner_sha256": "sha256:" + "1" * 64,
        "argv": argv,
        "input_bindings": bindings,
        "coverage_witness_ids": ["witness-1"],
    }


def _task1_pytest_spec(*, controller: bool) -> dict[str, Any]:
    return {
        "witness_id": "witness-controller" if controller else "witness-provider",
        "witness_kind": (
            "controller_pytest_runtime" if controller else "pytest_runtime"
        ),
        "selector_id": "CO-PYTEST-01" if controller else "provider-01",
        "consumer_id": "consumer-1",
        "required_proof_kind": "boundary_runtime",
        "spec": {
            "anchor_id": "call-boundary",
            "event_kind": "opcode_exact_span",
            "phase": "call",
            "attribution": {
                "attribution_kind": "pytest_node",
                "pytest_node_pattern": r"tests/torch/test_model\.py::test_boundary",
            },
            "expected_event": {"status": "passed"},
        },
    }


def _task1_source_event_binding() -> dict[str, Any]:
    return {
        "event_kind": "opcode_exact_span",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": "tests/torch/test_model.py::test_boundary",
        },
    }


def _task1_source_event() -> dict[str, Any]:
    return {
        **_task1_source_event_binding(),
        "consumer_path": "pkg/model.py",
        "caller_object_id": "a" * 40,
        "span": {
            "line_start": 4,
            "column_start": 11,
            "line_end": 4,
            "column_end": 24,
        },
        "hit_count": 1,
        "opcode_exact_span": {
            "code_qualname": "build",
            "code_firstlineno": 3,
            "instruction_offset": 8,
            "opname": "CALL",
            "argrepr_sha256": "sha256:" + "4" * 64,
        },
    }


def _task1_rich_runtime_witness() -> dict[str, Any]:
    return {
        "witness_id": "witness-provider",
        "selector_id": "provider-01",
        "consumer_id": "consumer-1",
        "proof_kind": "boundary_runtime",
        "witness_kind": "pytest_runtime",
        "runner_sha256": "sha256:" + "1" * 64,
        "consumer_path": "pkg/model.py",
        "caller_object_id": "a" * 40,
        "start_line": 4,
        "column_start": 11,
        "end_line": 4,
        "column_end": 24,
        "match_id": "match-1",
        "source_event_binding": _task1_source_event_binding(),
        "expected_event": {"status": "passed"},
    }


def _task1_witness_result() -> dict[str, Any]:
    observation = {"status": "passed"}
    return {
        "witness_id": "witness-provider",
        "selector_id": "provider-01",
        "consumer_id": "consumer-1",
        "proof_kind": "boundary_runtime",
        "witness_kind": "pytest_runtime",
        "target_tree": "b" * 40,
        "target_path": "pkg/model.py",
        "target_blob_id": "a" * 40,
        "mechanically_observed": True,
        "source_event": _task1_source_event(),
        "observation": observation,
        "observation_sha256": "sha256:" + "5" * 64,
        "passed": True,
    }


def _task1_origin_isolation() -> dict[str, Any]:
    return {
        "report_sha256": "sha256:" + "6" * 64,
        "python_executable": TASK0_PYTHON_TARGET,
        "pytest_carrier": copy.deepcopy(TASK0_PYTEST_CARRIER),
        "plugin_autoload_disabled": True,
        "removed_editable_hooks": [],
        "forbidden_roots": [],
        "forbidden_module_prefixes": [],
        "project_owned_module_prefixes": ["pkg"],
        "loaded_forbidden_modules": [],
        "forbidden_origin_rows": [],
        "outside_project_origin_rows": [],
        "projected_origin_rows": [],
        "module_origin_rows": [],
        "cache_artifacts": [],
    }


_RUNTIME_OWNED_MODULE_ORIGIN_ROWS = [
    ["es_boundary_probe_plugin", "<runtime-owned:es-boundary-probe-plugin>"],
    [
        "es_exact_source_event_observer",
        "<runtime-owned:es-exact-source-event-observer>",
    ],
    [
        "<normalized-runtime-owned:autograph-generated-module:0001>",
        "<normalized-runtime-owned:autograph-generated-origin:0001>",
    ],
    [
        "<normalized-runtime-owned:autograph-generated-module:0002>",
        "<normalized-runtime-owned:autograph-generated-origin:0002>",
    ],
    [
        "_remote_module_non_scriptable",
        "<normalized-runtime-owned:torch-remote-module-non-scriptable-origin>",
    ],
]


def _validate_task1_origin_runtime_contract(
    isolation: dict[str, Any], *, label: str
) -> dict[str, Any]:
    module = _module()
    boundary = importlib.import_module("scripts.experiments.es.boundary_proofs")
    return module._validated_origin_isolation(  # pyright: ignore[reportPrivateUsage]
        isolation,
        boundary=boundary,
        expected_pytest_carrier=copy.deepcopy(TASK0_PYTEST_CARRIER),
        label=label,
    )


def _task1_runtime_owned_origin_isolation() -> dict[str, Any]:
    isolation = _task1_origin_isolation()
    isolation["module_origin_rows"] = copy.deepcopy(
        _RUNTIME_OWNED_MODULE_ORIGIN_ROWS
    )
    return isolation


def test_task1_origin_schema_accepts_exact_runtime_owned_module_sentinels() -> None:
    isolation = _task1_runtime_owned_origin_isolation()
    validator = _task1_schema_validator(
        _TASK1_SELECTOR_SCHEMA_PATH, "origin_isolation"
    )

    assert not list(validator.iter_errors(isolation))


@pytest.mark.parametrize(
    "label",
    ("origin isolation", "controller origin isolation CO-PYTEST-01"),
)
def test_task1_origin_runtime_accepts_exact_runtime_owned_module_sentinels(
    label: str,
) -> None:
    isolation = _task1_runtime_owned_origin_isolation()

    assert _validate_task1_origin_runtime_contract(
        isolation, label=label
    )["module_origin_rows"] == _RUNTIME_OWNED_MODULE_ORIGIN_ROWS


@pytest.mark.parametrize(
    "label",
    ("origin isolation", "controller origin isolation CO-PYTEST-01"),
)
def test_task1_origin_contract_retains_absolute_module_origins(label: str) -> None:
    isolation = _task1_origin_isolation()
    isolation["module_origin_rows"] = [
        ["project.module", "/workspace/project/module.py"]
    ]
    validator = _task1_schema_validator(
        _TASK1_SELECTOR_SCHEMA_PATH, "origin_isolation"
    )

    assert not list(validator.iter_errors(isolation))
    assert _validate_task1_origin_runtime_contract(
        isolation, label=label
    )["module_origin_rows"] == isolation["module_origin_rows"]


@pytest.mark.parametrize(
    ("origin_key", "row"),
    (
        (
            "module_origin_rows",
            ["unknown_runtime_module", "<runtime-owned:unknown>"],
        ),
        (
            "module_origin_rows",
            [
                "es_boundary_probe_plugin",
                "<runtime-owned:es-boundary-probe-pluginn>",
            ],
        ),
        (
            "module_origin_rows",
            [
                "es_boundary_probe_plugin",
                "<runtime-owned:es-exact-source-event-observer>",
            ],
        ),
        (
            "module_origin_rows",
            ["wrong_module", "<runtime-owned:es-boundary-probe-plugin>"],
        ),
        (
            "module_origin_rows",
            [
                "<normalized-runtime-owned:autograph-generated-module:0001>",
                "<normalized-runtime-owned:autograph-generated-origin:0002>",
            ],
        ),
        (
            "module_origin_rows",
            [
                "<normalized-runtime-owned:autograph-generated-module:0001>",
                "<normalized-runtime-owned:autograph-generated-originn:0001>",
            ],
        ),
        (
            "module_origin_rows",
            [
                "<normalized-runtime-owned:autograph-generated-module:0018>",
                "<normalized-runtime-owned:autograph-generated-origin:0018>",
            ],
        ),
        (
            "module_origin_rows",
            [
                "wrong_module",
                "<normalized-runtime-owned:torch-remote-module-non-scriptable-origin>",
            ],
        ),
        (
            "projected_origin_rows",
            ["es_boundary_probe_plugin", "<runtime-owned:es-boundary-probe-plugin>"],
        ),
        (
            "forbidden_origin_rows",
            ["es_boundary_probe_plugin", "<runtime-owned:es-boundary-probe-plugin>"],
        ),
        (
            "outside_project_origin_rows",
            ["es_boundary_probe_plugin", "<runtime-owned:es-boundary-probe-plugin>"],
        ),
        (
            "projected_origin_rows",
            [
                "<normalized-runtime-owned:autograph-generated-module:0001>",
                "<normalized-runtime-owned:autograph-generated-origin:0001>",
            ],
        ),
        (
            "forbidden_origin_rows",
            [
                "_remote_module_non_scriptable",
                "<normalized-runtime-owned:torch-remote-module-non-scriptable-origin>",
            ],
        ),
    ),
)
def test_task1_origin_contract_rejects_unbound_or_misplaced_runtime_sentinel(
    origin_key: str,
    row: list[str],
) -> None:
    isolation = _task1_origin_isolation()
    isolation[origin_key] = [row]
    validator = _task1_schema_validator(
        _TASK1_SELECTOR_SCHEMA_PATH, "origin_isolation"
    )

    assert list(validator.iter_errors(isolation))
    with pytest.raises(
        _module().SourceCensusError, match="baseline_origin_isolation_failed"
    ):
        _validate_task1_origin_runtime_contract(isolation, label="origin isolation")


def test_task1_schema_contract_repeats_closed_pytest_carrier_identity() -> None:
    policy_validator = _task1_schema_validator(
        _TASK1_POLICY_SCHEMA_PATH, "selector_policy"
    )
    selector_validator = _task1_schema_validator(
        _TASK1_SELECTOR_SCHEMA_PATH, "origin_isolation"
    )
    controller_validator = _task1_schema_validator(
        _TASK1_SELECTOR_SCHEMA_PATH, "controller_selector_result"
    )
    module = _module()
    selector_policy, _, _ = _task1c_selector_join_fixture(module)
    selector_policy["provider_visible_pytest_selectors"] = [
        {
            "selector_id": f"provider-{ordinal:02d}",
            "ordinal": ordinal,
            "pytest_module_path": f"tests/public/test_boundary_{ordinal:02d}.py",
        }
        for ordinal in range(1, 20)
    ]
    selector_policy["pytest_carrier"] = copy.deepcopy(TASK0_PYTEST_CARRIER)
    origin = _task1_origin_isolation()
    origin["pytest_carrier"] = copy.deepcopy(TASK0_PYTEST_CARRIER)
    controller = {
        "selector_id": "CO-PYTEST-01",
        "execution_kind": "pytest_aggregate",
        "argv": ["pytest"],
        "collected_node_ids": ["tests/private/test_driver.py::test_boundary"],
        "collected_node_sha256": "sha256:" + "1" * 64,
        "collection_total": 1,
        "outcomes": {"errors": 0, "failed": 0, "passed": 1, "skipped": 0},
        "origin_isolation": origin,
        "trace_sha256": "sha256:" + "2" * 64,
        "coverage_witness_ids": ["witness-controller"],
        "coverage_witness_node_outcomes": [
            {
                "witness_id": "witness-controller",
                "pytest_node_id": "tests/private/test_driver.py::test_boundary",
                "outcome": "passed",
            }
        ],
    }

    assert not list(policy_validator.iter_errors(selector_policy))
    assert not list(selector_validator.iter_errors(origin))
    assert not list(controller_validator.iter_errors(controller))

    for record, validator, key in (
        (selector_policy, policy_validator, "pytest_carrier"),
        (origin, selector_validator, "pytest_carrier"),
        (controller, controller_validator, "coverage_witness_node_outcomes"),
    ):
        missing = copy.deepcopy(record)
        missing.pop(key)
        assert list(validator.iter_errors(missing))

    tampered = copy.deepcopy(selector_policy)
    tampered["pytest_carrier"]["tmp_isolation"] = "shared"
    assert list(policy_validator.iter_errors(tampered))


def test_task1_schema_contract_controller_execution_kinds_are_closed() -> None:
    validator = _task1_schema_validator(
        _TASK1_POLICY_SCHEMA_PATH, "controller_selector"
    )
    for execution_kind in ("pytest_aggregate", "isolated_probe", "static_ast"):
        assert not list(
            validator.iter_errors(_task1_controller_selector(execution_kind))
        )

    missing_kind = _task1_controller_selector("static_ast")
    missing_kind.pop("execution_kind")
    assert list(validator.iter_errors(missing_kind))

    wrong_static_proof = _task1_controller_selector("static_ast")
    wrong_static_proof["proof_kind"] = "boundary_runtime"
    assert list(validator.iter_errors(wrong_static_proof))

    wrong_probe_proof = _task1_controller_selector("isolated_probe")
    wrong_probe_proof["proof_kind"] = "non_cdi_static"
    assert list(validator.iter_errors(wrong_probe_proof))


def test_task1_schema_contract_controller_pytest_runtime_is_distinct() -> None:
    validator = _task1_schema_validator(_TASK1_POLICY_SCHEMA_PATH, "witness_spec")
    provider = _task1_pytest_spec(controller=False)
    controller = _task1_pytest_spec(controller=True)
    assert not list(validator.iter_errors(provider))
    assert not list(validator.iter_errors(controller))

    lane_crossed = copy.deepcopy(controller)
    lane_crossed["witness_kind"] = "pytest_runtime"
    assert list(validator.iter_errors(lane_crossed))

    old_shape = copy.deepcopy(provider)
    old_shape["spec"] = {
        "anchor_id": "call-boundary",
        "pytest_node_pattern": r"tests/torch/test_model\.py::test_boundary",
        "expected_event": {"consumer_span_hit": True, "status": "passed"},
    }
    assert list(validator.iter_errors(old_shape))


def test_task1_schema_contract_runtime_probe_action_union_is_closed() -> None:
    validator = _task1_schema_validator(_TASK1_POLICY_SCHEMA_PATH, "runtime_probe")
    import_action = {
        "action": "import_module",
        "module": "pkg.model",
        "expected_outcome": {"status": "returned"},
    }
    call_action = {
        "action": "call",
        "module": "pkg.model",
        "callable": "Factory.build",
        "args": [1, True, None, {"count": 2}],
        "kwargs": {"enabled": False},
        "return_value": "ignore",
        "expected_outcome": {
            "status": "raised",
            "exception_type": "builtins.ValueError",
        },
    }
    assert not list(validator.iter_errors(import_action))
    assert not list(validator.iter_errors(call_action))

    old_shape = {
        "module": "pkg.model",
        "callable": "Factory.build",
        "args": [],
        "kwargs": {},
    }
    assert list(validator.iter_errors(old_shape))

    wrong_return = copy.deepcopy(call_action)
    wrong_return["return_value"] = "serialize"
    assert list(validator.iter_errors(wrong_return))

    float_argument = copy.deepcopy(call_action)
    float_argument["args"] = [1.5]
    assert list(validator.iter_errors(float_argument))


def test_task1_schema_contract_source_event_records_are_required() -> None:
    witness_validator = _task1_schema_validator(
        _TASK1_SELECTOR_SCHEMA_PATH, "coverage_witness"
    )
    result_validator = _task1_schema_validator(
        _TASK1_SELECTOR_SCHEMA_PATH, "witness_result"
    )
    witness = _task1_rich_runtime_witness()
    result = _task1_witness_result()
    assert not list(witness_validator.iter_errors(witness))
    assert not list(result_validator.iter_errors(result))

    missing_binding = copy.deepcopy(witness)
    missing_binding.pop("source_event_binding")
    assert list(witness_validator.iter_errors(missing_binding))

    missing_event = copy.deepcopy(result)
    missing_event.pop("source_event")
    assert list(result_validator.iter_errors(missing_event))

    controller_witness = copy.deepcopy(witness)
    controller_witness["witness_id"] = "witness-controller"
    controller_witness["witness_kind"] = "controller_pytest_runtime"
    controller_witness["selector_id"] = "CO-PYTEST-01"
    assert not list(witness_validator.iter_errors(controller_witness))

    for runtime_witness in (witness, controller_witness):
        for legacy_fields in (
            {"pytest_node_id": "tests/torch/test_model.py::test_boundary"},
            {"event_id": "pytest_node_consumer_span.v1"},
            {
                "pytest_node_id": "tests/torch/test_model.py::test_boundary",
                "event_id": "pytest_node_consumer_span.v1",
            },
        ):
            hybrid = copy.deepcopy(runtime_witness)
            hybrid.update(legacy_fields)
            assert list(witness_validator.iter_errors(hybrid)), (
                runtime_witness["witness_kind"],
                sorted(legacy_fields),
            )


def test_task1_schema_contract_baseline_separates_controller_results() -> None:
    validator = _task1_schema_validator(_TASK1_SELECTOR_SCHEMA_PATH, "baseline")
    provider_nodes = [
        f"{path}::test_placeholder_{ordinal:02d}"
        for ordinal, path in enumerate(TASK0_PROVIDER_MODULES, 1)
    ]
    baseline = {
        "schema_version": "es_f1_boundary_baseline.v1",
        "runner_sha256": "sha256:" + "1" * 64,
        "pre_tree": "b" * 40,
        "post_tree": "b" * 40,
        "aggregate_pytest_argv": list(TASK0_AGGREGATE_PYTEST_ARGV),
        "collected_node_ids": provider_nodes,
        "collected_node_sha256": "sha256:" + "2" * 64,
        "collection_total": 19,
        "outcomes": {"errors": 0, "failed": 0, "passed": 19, "skipped": 0},
        "origin_isolation": _task1_origin_isolation(),
        "selector_results": [
            {
                "selector_id": f"provider-{ordinal:02d}",
                "pytest_node_ids": [provider_nodes[ordinal - 1]],
                "coverage_witness_ids": [f"witness-{ordinal:02d}"],
            }
            for ordinal in range(1, 20)
        ],
        "controller_selector_results": [
            {
                "selector_id": "CO-PYTEST-01",
                "execution_kind": "pytest_aggregate",
                "argv": [*TASK0_AGGREGATE_PYTEST_ARGV, "tests/private/test_driver.py"],
                "collected_node_ids": ["tests/private/test_driver.py::test_boundary"],
                "collected_node_sha256": "sha256:" + "3" * 64,
                "collection_total": 1,
                "outcomes": {
                    "errors": 0,
                    "failed": 0,
                    "passed": 1,
                    "skipped": 0,
                },
                "origin_isolation": _task1_origin_isolation(),
                "trace_sha256": "sha256:" + "4" * 64,
                "coverage_witness_ids": ["witness-controller"],
                "coverage_witness_node_outcomes": [
                    {
                        "witness_id": "witness-controller",
                        "pytest_node_id": (
                            "tests/private/test_driver.py::test_boundary"
                        ),
                        "outcome": "passed",
                    }
                ],
            }
        ],
        "witness_results": [_task1_witness_result()],
    }
    assert not list(validator.iter_errors(baseline))

    missing_controller_results = copy.deepcopy(baseline)
    missing_controller_results.pop("controller_selector_results")
    assert list(validator.iter_errors(missing_controller_results))

    too_few_provider_results = copy.deepcopy(baseline)
    too_few_provider_results["selector_results"].pop()
    assert list(validator.iter_errors(too_few_provider_results))


def test_task1_source_census_uses_provider_visible_selector_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    assert hasattr(module, "provider_visible_selector_projection")
    original = module.provider_visible_selector_projection
    controller_canaries = (
        "CONTROLLER_CANARY_SELECTOR_7f3e",
        "tests/private/CONTROLLER_CANARY_DRIVER_7f3e.py",
        "tests/private/CONTROLLER_CANARY_DRIVER_7f3e.py::test_private",
        "CONTROLLER_CANARY_ARGV_7f3e",
        "CONTROLLER_CANARY_DIGEST_7f3e",
    )
    observed: list[dict[str, object]] = []

    def observe_projection(**kwargs: object) -> dict[str, object]:
        policy = copy.deepcopy(kwargs["policy"])
        baseline = copy.deepcopy(kwargs["baseline_characterization"])
        policy["selector_policy"]["controller_only_proof_selectors"] = [
            {
                "selector_id": controller_canaries[0],
                "runner_path": controller_canaries[1],
                "runner_sha256": controller_canaries[4],
                "argv": [controller_canaries[3]],
            }
        ]
        baseline["controller_selector_results"] = [
            {
                "selector_id": controller_canaries[0],
                "pytest_node_ids": [controller_canaries[2]],
                "argv": [controller_canaries[3]],
                "trace_sha256": controller_canaries[4],
            }
        ]
        projection = original(
            policy=policy,
            census=kwargs["census"],
            baseline_characterization=baseline,
            selector_results=kwargs["selector_results"],
            projection_blobs=kwargs["projection_blobs"],
        )
        observed.append(copy.deepcopy(projection))
        return projection

    monkeypatch.setattr(module, "provider_visible_selector_projection", observe_projection)

    test_build_selector_manifest_requires_observed_witness_and_exact_node(
        tmp_path,
        monkeypatch,
    )

    assert observed
    for projection in observed:
        assert set(projection) == {
            "aggregate_pytest_argv",
            "provider_visible_pytest_selectors",
        }
        assert projection["aggregate_pytest_argv"] == list(
            TASK0_AGGREGATE_PYTEST_ARGV
        )
        provider_rows = projection["provider_visible_pytest_selectors"]
        assert len(provider_rows) == 19
        assert [row["selector_id"] for row in provider_rows] == [
            f"focused-{ordinal:02d}" for ordinal in range(1, 20)
        ]
        assert [row["pytest_module_path"] for row in provider_rows] == [
            _provider_selector_path(ordinal) for ordinal in range(1, 20)
        ]
        canonical = module.canonical_json_bytes(projection)
        assert all(canary.encode() not in canonical for canary in controller_canaries)


def _task1c_selector_join_fixture(
    module: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    provider = {
        "selector_id": "provider-01",
        "ordinal": 1,
        "pytest_module_path": "tests/public/test_boundary.py",
    }
    controllers = [
        {
            "selector_id": "CO-PYTEST-01",
            "ordinal": 1,
            "proof_kind": "boundary_runtime",
            "execution_kind": "pytest_aggregate",
            "runner_path": "scripts/experiments/es/boundary_proofs.py",
            "runner_sha256": "sha256:" + "1" * 64,
            "argv": [*TASK0_AGGREGATE_PYTEST_ARGV, "tests/private/test_driver.py"],
            "input_bindings": [
                {
                    "path": "tests/private/test_driver.py",
                    "sha256": "sha256:" + "2" * 64,
                }
            ],
            "coverage_witness_ids": ["witness-controller-pytest"],
        },
        {
            "selector_id": "CO-PROBE-01",
            "ordinal": 2,
            "proof_kind": "boundary_runtime",
            "execution_kind": "isolated_probe",
            "runner_path": "scripts/experiments/es/boundary_proofs.py",
            "runner_sha256": "sha256:" + "1" * 64,
            "argv": ["isolated-probe", "--selector-id", "CO-PROBE-01"],
            "input_bindings": [
                {"path": "pkg/probe.py", "sha256": "sha256:" + "3" * 64}
            ],
            "coverage_witness_ids": ["witness-probe"],
        },
        {
            "selector_id": "CO-STATIC-01",
            "ordinal": 3,
            "proof_kind": "non_cdi_static",
            "execution_kind": "static_ast",
            "runner_path": "scripts/experiments/es/boundary_proofs.py",
            "runner_sha256": "sha256:" + "1" * 64,
            "argv": ["static-ast", "--selector-id", "CO-STATIC-01"],
            "input_bindings": [
                {"path": "pkg/static.py", "sha256": "sha256:" + "4" * 64}
            ],
            "coverage_witness_ids": ["witness-static"],
        },
    ]
    probe = {
        "action": "call",
        "module": "pkg.model",
        "callable": "Factory.build",
        "args": [],
        "kwargs": {},
        "return_value": "ignore",
        "expected_outcome": {"status": "returned"},
    }
    witnesses = [
        {
            "witness_id": "witness-provider",
            "witness_kind": "pytest_runtime",
            "selector_id": "provider-01",
            "consumer_id": "consumer-provider",
            "required_proof_kind": "boundary_runtime",
            "spec": {
                "anchor_id": "anchor-provider",
                "event_kind": "opcode_exact_span",
                "phase": "call",
                "attribution": {
                    "attribution_kind": "pytest_node",
                    "pytest_node_pattern": (
                        r"tests/public/test_boundary\.py::test_boundary"
                    ),
                },
                "expected_event": {"status": "passed"},
            },
        },
        {
            "witness_id": "witness-controller-pytest",
            "witness_kind": "controller_pytest_runtime",
            "selector_id": "CO-PYTEST-01",
            "consumer_id": "consumer-controller-pytest",
            "required_proof_kind": "boundary_runtime",
            "spec": {
                "anchor_id": "anchor-controller-pytest",
                "event_kind": "callable_entry",
                "phase": "collection",
                "attribution": {
                    "attribution_kind": "selector_module",
                    "pytest_module_path": "tests/private/test_driver.py",
                },
                "expected_event": {"status": "passed"},
            },
        },
        {
            "witness_id": "witness-probe",
            "witness_kind": "runtime_probe",
            "selector_id": "CO-PROBE-01",
            "consumer_id": "consumer-probe",
            "required_proof_kind": "boundary_runtime",
            "spec": {
                "anchor_id": "anchor-probe",
                "event_kind": "import_alias_opcode",
                "phase": "residual",
                "attribution": {
                    "attribution_kind": "residual_action",
                    "action_sha256": module.raw_sha256(
                        module.canonical_json_bytes(probe)
                    ),
                },
                "probe": probe,
                "expected_event": {"status": "returned"},
            },
        },
        {
            "witness_id": "witness-static",
            "witness_kind": "static_ast",
            "selector_id": "CO-STATIC-01",
            "consumer_id": "consumer-static",
            "required_proof_kind": "non_cdi_static",
            "spec": {
                "anchor_id": "anchor-static",
                "query": {
                    "query_kind": "forbidden_syntax_absent",
                    "forbidden_names": ["ModelSpec"],
                    "forbidden_attributes": ["load_torch_bundle"],
                    "forbidden_string_literals": ["cnn"],
                },
                "expected_event": {"matches": []},
            },
        },
    ]
    consumers = {
        row["consumer_id"]: {
            "consumer_id": row["consumer_id"],
            "anchor_id": row["spec"]["anchor_id"],
            "required_proof_kind": row["required_proof_kind"],
            "proposed_disposition": {
                "boundary_runtime": "route_through_boundary",
                "non_cdi_static": "compatibility_adapter",
                "reference_absence": "remove",
            }[row["required_proof_kind"]],
            "selector_id": row["selector_id"],
            "witness_kind": row["witness_kind"],
            "coverage_status": "required",
            "coverage_witness_ids": [row["witness_id"]],
        }
        for row in witnesses
    }
    selector_policy = {
        "sampling_rule": (
            "first_observable_per_provider_and_disposition_witness_class_"
            "in_discovery_order.v1"
        ),
        "pytest_carrier": copy.deepcopy(TASK0_PYTEST_CARRIER),
        "provider_visible_pytest_selectors": [provider],
        "controller_only_proof_selectors": controllers,
        "coverage_witness_specs": witnesses,
        "desired_state_proof_specs": [
            {
                "proof_spec_id": f"proof-{ordinal}",
                "witness_id": row["witness_id"],
                "proof_kind": row["required_proof_kind"],
                "expected_result": copy.deepcopy(row["spec"]["expected_event"]),
            }
            for ordinal, row in enumerate(witnesses, 1)
        ],
    }
    discovery_input = {"provider_visible_pytest_selectors": [provider]}
    return selector_policy, discovery_input, consumers


def _task1i_consumer_policy(
    *, coverage_status: str, coverage_witness_ids: list[str]
) -> dict[str, Any]:
    return {
        "consumer_id": "consumer-provider",
        "match_id": "match-provider",
        "proposed_disposition": "route_through_boundary",
        "required_proof_kind": "boundary_runtime",
        "selector_id": "provider-01",
        "witness_kind": "pytest_runtime",
        "coverage_status": coverage_status,
        "coverage_witness_ids": coverage_witness_ids,
    }


@pytest.mark.parametrize(
    ("coverage_status", "coverage_witness_ids"),
    [
        ("required", ["witness-provider"]),
        ("inherited", []),
        ("open", []),
    ],
)
def test_task1i_policy_consumer_schema_accepts_closed_coverage_status_shapes(
    coverage_status: str,
    coverage_witness_ids: list[str],
) -> None:
    module = _module()
    validator = _task1_schema_validator(_TASK1_POLICY_SCHEMA_PATH, "consumer_policy")
    row = _task1i_consumer_policy(
        coverage_status=coverage_status,
        coverage_witness_ids=coverage_witness_ids,
    )

    assert not list(validator.iter_errors(row))


@pytest.mark.parametrize(
    ("coverage_status", "coverage_witness_ids"),
    [
        ("required", []),
        ("required", ["witness-provider", "witness-extra"]),
        ("inherited", ["witness-provider"]),
        ("open", ["witness-provider"]),
    ],
)
def test_task1i_policy_consumer_schema_rejects_coverage_status_cardinality_mismatch(
    coverage_status: str,
    coverage_witness_ids: list[str],
) -> None:
    validator = _task1_schema_validator(_TASK1_POLICY_SCHEMA_PATH, "consumer_policy")
    row = _task1i_consumer_policy(
        coverage_status=coverage_status,
        coverage_witness_ids=coverage_witness_ids,
    )

    assert list(validator.iter_errors(row))


def test_task1i_selector_policy_schema_freezes_observable_sampling_rule() -> None:
    schema = json.loads(_TASK1_POLICY_SCHEMA_PATH.read_text(encoding="utf-8"))
    selector_policy = schema["$defs"]["selector_policy"]

    assert "sampling_rule" in selector_policy["required"]
    assert selector_policy["properties"]["sampling_rule"] == {
        "const": (
            "first_observable_per_provider_and_disposition_witness_class_"
            "in_discovery_order.v1"
        )
    }


@pytest.mark.parametrize(
    ("coverage_witness_ids", "is_valid"),
    [([], True), (["witness-1"], True), (["witness-1", "witness-2"], False)],
)
def test_task1i_controller_selector_schema_allows_zero_or_one_witness_backpointer(
    coverage_witness_ids: list[str],
    is_valid: bool,
) -> None:
    validator = _task1_schema_validator(
        _TASK1_POLICY_SCHEMA_PATH, "controller_selector"
    )
    row = _task1_controller_selector("isolated_probe")
    row["coverage_witness_ids"] = coverage_witness_ids

    assert (not list(validator.iter_errors(row))) is is_valid


def _task1i_census_consumer_row(
    *, coverage_status: str, coverage_witness_ids: list[str]
) -> dict[str, Any]:
    return {
        "consumer_id": "consumer-provider",
        "match_id": "match-provider",
        "caller_path": "pkg/model.py",
        "caller_object_id": "a" * 40,
        "span": {
            "line_start": 4,
            "column_start": 11,
            "line_end": 4,
            "column_end": 24,
        },
        "detector_id": "python-boundary",
        "detector_version": "1",
        "anchor_id": "call-boundary",
        "callee_or_dispatch_form": "resolve_generator",
        "responsibility_ids": ["CONSTRUCTION"],
        "proposed_disposition": "route_through_boundary",
        "required_proof_kind": "boundary_runtime",
        "selector_id": "provider-01",
        "witness_kind": "pytest_runtime",
        "coverage_status": coverage_status,
        "coverage_witness_ids": coverage_witness_ids,
    }


@pytest.mark.parametrize(
    ("coverage_status", "coverage_witness_ids"),
    [
        ("required", ["witness-provider"]),
        ("inherited", []),
        ("open", []),
    ],
)
def test_task1i_source_census_consumer_schema_retains_class_assignment_and_status(
    coverage_status: str,
    coverage_witness_ids: list[str],
) -> None:
    validator = _task1_schema_validator(_TASK1_CENSUS_SCHEMA_PATH, "consumer_row")
    row = _task1i_census_consumer_row(
        coverage_status=coverage_status,
        coverage_witness_ids=coverage_witness_ids,
    )

    assert not list(validator.iter_errors(row))


def test_task1c_selector_policy_parser_requires_exact_pytest_carrier() -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    selector_policy["pytest_carrier"] = copy.deepcopy(TASK0_PYTEST_CARRIER)

    module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
        selector_policy,
        discovery_input=discovery_input,
        consumers=consumers,
    )

    for tamper in ("missing", "digest", "extra"):
        bad = copy.deepcopy(selector_policy)
        if tamper == "missing":
            bad.pop("pytest_carrier")
        elif tamper == "digest":
            bad["pytest_carrier"]["sha256"] = "sha256:" + "0" * 64
        else:
            bad["pytest_carrier"]["extra"] = True
        with pytest.raises(module.SourceCensusError):
            module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
                bad,
                discovery_input=discovery_input,
                consumers=consumers,
            )


@pytest.mark.parametrize("coverage_status", ["inherited", "open"])
def test_task1i_selector_policy_accepts_unselected_or_unobserved_consumer_without_witness(
    coverage_status: str,
) -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    inherited = copy.deepcopy(consumers["consumer-provider"])
    inherited.update(
        {
            "consumer_id": f"consumer-{coverage_status}",
            "anchor_id": f"anchor-{coverage_status}",
            "coverage_status": coverage_status,
            "coverage_witness_ids": [],
        }
    )
    consumers[inherited["consumer_id"]] = inherited

    module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
        selector_policy,
        discovery_input=discovery_input,
        consumers=consumers,
    )


@pytest.mark.parametrize("coverage_status", ["inherited", "open"])
def test_task1i_selector_policy_rejects_witness_on_nonrequired_consumer(
    coverage_status: str,
) -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    consumers["consumer-provider"]["coverage_status"] = coverage_status

    with pytest.raises(
        module.SourceCensusError, match="consumer_coverage_status_invalid"
    ):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


def test_task1i_selector_policy_rejects_class_without_observable_required_sample() -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    consumers["consumer-static"].update(
        {"coverage_status": "open", "coverage_witness_ids": []}
    )
    static_selector = selector_policy["controller_only_proof_selectors"][2]
    static_selector["coverage_witness_ids"] = []
    selector_policy["coverage_witness_specs"] = [
        row
        for row in selector_policy["coverage_witness_specs"]
        if row["witness_id"] != "witness-static"
    ]
    selector_policy["desired_state_proof_specs"] = [
        row
        for row in selector_policy["desired_state_proof_specs"]
        if row["witness_id"] != "witness-static"
    ]

    with pytest.raises(module.SourceCensusError, match="coverage_required_sample_missing"):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


def test_task1i_selector_policy_rejects_provider_without_observable_required_sample() -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    consumers["consumer-provider"].update(
        {"coverage_status": "open", "coverage_witness_ids": []}
    )
    selector_policy["coverage_witness_specs"] = [
        row
        for row in selector_policy["coverage_witness_specs"]
        if row["witness_id"] != "witness-provider"
    ]
    selector_policy["desired_state_proof_specs"] = [
        row
        for row in selector_policy["desired_state_proof_specs"]
        if row["witness_id"] != "witness-provider"
    ]

    with pytest.raises(module.SourceCensusError, match="coverage_required_sample_missing"):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


def test_task1i_selector_policy_accepts_empty_controller_backpointer_for_open_consumer() -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    controller = copy.deepcopy(
        selector_policy["controller_only_proof_selectors"][1]
    )
    controller.update(
        {
            "selector_id": "CO-PROBE-02",
            "ordinal": 4,
            "argv": ["isolated-probe", "--selector-id", "CO-PROBE-02"],
            "coverage_witness_ids": [],
        }
    )
    selector_policy["controller_only_proof_selectors"].append(controller)
    consumers["consumer-open-probe"] = {
        **copy.deepcopy(consumers["consumer-probe"]),
        "consumer_id": "consumer-open-probe",
        "anchor_id": "anchor-open-probe",
        "selector_id": "CO-PROBE-02",
        "coverage_status": "open",
        "coverage_witness_ids": [],
    }

    module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
        selector_policy,
        discovery_input=discovery_input,
        consumers=consumers,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selector_id", "CO-PROBE-01"),
        ("witness_kind", "runtime_probe"),
        ("required_proof_kind", "non_cdi_static"),
    ],
)
def test_task1i_selector_policy_rejects_consumer_class_assignment_or_lane_tamper(
    field: str,
    value: str,
) -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    consumers["consumer-provider"][field] = value

    with pytest.raises(
        module.SourceCensusError, match="consumer_class_assignment_invalid"
    ):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


@pytest.mark.parametrize(
    ("controller_index", "execution_kind"),
    [(0, "static_ast"), (2, "isolated_probe")],
)
def test_task1c_controller_execution_kind_matches_proof_kind(
    controller_index: int,
    execution_kind: str,
) -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    selector_policy["controller_only_proof_selectors"][controller_index][
        "execution_kind"
    ] = execution_kind
    with pytest.raises(module.SourceCensusError, match="selector_execution_kind_invalid"):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


@pytest.mark.parametrize(
    ("witness_index", "selector_id"),
    [
        (0, "CO-PYTEST-01"),
        (1, "CO-PROBE-01"),
        (2, "CO-PYTEST-01"),
        (3, "CO-PYTEST-01"),
    ],
)
def test_task1c_witness_kind_is_confined_to_its_execution_lane(
    witness_index: int,
    selector_id: str,
) -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    selector_policy["coverage_witness_specs"][witness_index]["selector_id"] = selector_id
    with pytest.raises(module.SourceCensusError, match="coverage_witness_lane_invalid"):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


def test_task1c_witness_payload_requires_exact_source_event_attribution() -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
        selector_policy,
        discovery_input=discovery_input,
        consumers=consumers,
    )

    old_shape = copy.deepcopy(selector_policy)
    old_shape["coverage_witness_specs"][0]["spec"] = {
        "anchor_id": "anchor-provider",
        "pytest_node_pattern": r"tests/public/test_boundary\.py::test_boundary",
        "expected_event": {"status": "passed"},
    }
    with pytest.raises(module.SourceCensusError, match="coverage_witness_spec_incomplete"):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            old_shape,
            discovery_input=discovery_input,
            consumers=consumers,
        )

    wrong_attribution = copy.deepcopy(selector_policy)
    wrong_attribution["coverage_witness_specs"][0]["spec"]["attribution"] = {
        "attribution_kind": "selector_module",
        "pytest_module_path": "tests/public/test_boundary.py",
    }
    with pytest.raises(module.SourceCensusError, match="coverage_witness_attribution_invalid"):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            wrong_attribution,
            discovery_input=discovery_input,
            consumers=consumers,
        )

    wrong_action_digest = copy.deepcopy(selector_policy)
    wrong_action_digest["coverage_witness_specs"][2]["spec"]["attribution"][
        "action_sha256"
    ] = "sha256:" + "9" * 64
    with pytest.raises(module.SourceCensusError, match="coverage_witness_attribution_invalid"):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            wrong_action_digest,
            discovery_input=discovery_input,
            consumers=consumers,
        )


def test_task1c_controller_witness_backpointers_are_exact() -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(module)
    selector_policy["controller_only_proof_selectors"][0][
        "coverage_witness_ids"
    ] = ["witness-probe"]
    with pytest.raises(module.SourceCensusError, match="coverage_witness_join_invalid"):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


def _task1d_source_event_binding(
    *, phase: str, attribution: dict[str, Any]
) -> dict[str, Any]:
    return {
        "event_kind": "opcode_exact_span",
        "phase": phase,
        "attribution": copy.deepcopy(attribution),
    }


def _task1d_source_event(
    *,
    binding: dict[str, Any],
    consumer_path: str,
    caller_object_id: str,
) -> dict[str, Any]:
    return {
        **copy.deepcopy(binding),
        "consumer_path": consumer_path,
        "caller_object_id": caller_object_id,
        "span": {
            "line_start": 1,
            "column_start": 0,
            "line_end": 1,
            "column_end": 8,
        },
        "hit_count": 1,
        "opcode_exact_span": {
            "code_qualname": "boundary",
            "code_firstlineno": 1,
            "instruction_offset": 8,
            "opname": "CALL",
            "argrepr_sha256": "sha256:" + "8" * 64,
        },
    }


def _task1d_baseline_fixture(
    module: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    baseline, policy, census = _baseline_validation_fixture(module)
    runner_sha256 = baseline["runner_sha256"]
    provider_node = baseline["collected_node_ids"][0]
    provider_binding = _task1d_source_event_binding(
        phase="call",
        attribution={
            "attribution_kind": "pytest_node",
            "pytest_node_id": provider_node,
        },
    )
    policy["selector_policy"]["coverage_witness_specs"][0]["spec"] = {
        "event_kind": "opcode_exact_span",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_pattern": r"selector\.py::test_placeholder",
        },
        "expected_event": {"status": "passed"},
    }
    provider_result = baseline["witness_results"][0]
    provider_result["observation"] = {"status": "passed"}
    provider_result["observation_sha256"] = module.raw_sha256(
        module.canonical_json_bytes(provider_result["observation"])
    )
    provider_result["source_event"] = _task1d_source_event(
        binding=provider_binding,
        consumer_path=provider_result["target_path"],
        caller_object_id=provider_result["target_blob_id"],
    )

    controller_node = "tests/private/test_driver.py::test_boundary"
    controller_binding = _task1d_source_event_binding(
        phase="collection",
        attribution={
            "attribution_kind": "selector_module",
            "pytest_module_path": "tests/private/test_driver.py",
        },
    )
    probe = {
        "action": "call",
        "module": "pkg.probe",
        "callable": "run",
        "args": [],
        "kwargs": {},
        "return_value": "ignore",
        "expected_outcome": {"status": "returned"},
    }
    action_sha256 = module.raw_sha256(module.canonical_json_bytes(probe))
    probe_binding = _task1d_source_event_binding(
        phase="residual",
        attribution={
            "attribution_kind": "residual_action",
            "action_sha256": action_sha256,
        },
    )
    policy["selector_policy"]["controller_only_proof_selectors"] = [
        {
            "selector_id": "CO-PYTEST-01",
            "ordinal": 1,
            "proof_kind": "boundary_runtime",
            "execution_kind": "pytest_aggregate",
            "runner_path": "scripts/experiments/es/boundary_proofs.py",
            "runner_sha256": runner_sha256,
            "argv": [
                TASK0_PYTHON,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/private/test_driver.py",
            ],
            "input_bindings": [
                {
                    "path": "tests/private/test_driver.py",
                    "sha256": "sha256:" + "3" * 64,
                }
            ],
            "coverage_witness_ids": ["witness-controller"],
        },
        {
            "selector_id": "CO-PROBE-01",
            "ordinal": 2,
            "proof_kind": "boundary_runtime",
            "execution_kind": "isolated_probe",
            "runner_path": "scripts/experiments/es/boundary_proofs.py",
            "runner_sha256": runner_sha256,
            "argv": ["isolated-probe", "--selector-id", "CO-PROBE-01"],
            "input_bindings": [
                {"path": "pkg/probe.py", "sha256": "sha256:" + "4" * 64}
            ],
            "coverage_witness_ids": ["witness-probe"],
        },
        {
            "selector_id": "CO-STATIC-01",
            "ordinal": 3,
            "proof_kind": "non_cdi_static",
            "execution_kind": "static_ast",
            "runner_path": "scripts/experiments/es/boundary_proofs.py",
            "runner_sha256": runner_sha256,
            "argv": ["static-ast", "--selector-id", "CO-STATIC-01"],
            "input_bindings": [
                {"path": "pkg/static.py", "sha256": "sha256:" + "5" * 64}
            ],
            "coverage_witness_ids": ["witness-static"],
        },
    ]
    policy["selector_policy"]["coverage_witness_specs"].extend(
        [
            {
                "witness_id": "witness-controller",
                "selector_id": "CO-PYTEST-01",
                "consumer_id": "consumer-controller",
                "required_proof_kind": "boundary_runtime",
                "witness_kind": "controller_pytest_runtime",
                "spec": {
                    "event_kind": "opcode_exact_span",
                    "phase": "collection",
                    "attribution": {
                        "attribution_kind": "selector_module",
                        "pytest_module_path": "tests/private/test_driver.py",
                    },
                    "expected_event": {"status": "passed"},
                },
            },
            {
                "witness_id": "witness-probe",
                "selector_id": "CO-PROBE-01",
                "consumer_id": "consumer-probe",
                "required_proof_kind": "boundary_runtime",
                "witness_kind": "runtime_probe",
                "spec": {
                    "event_kind": "opcode_exact_span",
                    "phase": "residual",
                    "attribution": {
                        "attribution_kind": "residual_action",
                        "action_sha256": action_sha256,
                    },
                    "probe": probe,
                    "expected_event": {"status": "returned"},
                },
            },
            {
                "witness_id": "witness-static",
                "selector_id": "CO-STATIC-01",
                "consumer_id": "consumer-static",
                "required_proof_kind": "non_cdi_static",
                "witness_kind": "static_ast",
                "spec": {
                    "query": {
                        "query_kind": "forbidden_syntax_absent",
                        "forbidden_names": ["ModelSpec"],
                        "forbidden_attributes": [],
                        "forbidden_string_literals": [],
                    },
                    "expected_event": {"matches": []},
                },
            },
        ]
    )

    controller_consumers = [
        ("consumer-controller", "pkg/controller.py", "c" * 40, "boundary_runtime"),
        ("consumer-probe", "pkg/probe.py", "d" * 40, "boundary_runtime"),
        ("consumer-static", "pkg/static.py", "e" * 40, "non_cdi_static"),
    ]
    for consumer_id, path, blob, proof_kind in controller_consumers:
        census["consumer_rows"].append(
            {
                "consumer_id": consumer_id,
                "caller_path": path,
                "caller_object_id": blob,
                "required_proof_kind": proof_kind,
            }
        )

    def result(
        *,
        witness_id: str,
        selector_id: str,
        consumer_id: str,
        witness_kind: str,
        path: str,
        blob: str,
        observation: dict[str, Any],
        source_event: dict[str, Any] | None,
        proof_kind: str = "boundary_runtime",
    ) -> dict[str, Any]:
        row = {
            "witness_id": witness_id,
            "selector_id": selector_id,
            "consumer_id": consumer_id,
            "proof_kind": proof_kind,
            "witness_kind": witness_kind,
            "target_tree": baseline["pre_tree"],
            "target_path": path,
            "target_blob_id": blob,
            "mechanically_observed": True,
            "observation": observation,
            "observation_sha256": module.raw_sha256(
                module.canonical_json_bytes(observation)
            ),
            "passed": True,
        }
        if source_event is not None:
            row["source_event"] = source_event
        return row

    baseline["witness_results"].extend(
        [
            result(
                witness_id="witness-controller",
                selector_id="CO-PYTEST-01",
                consumer_id="consumer-controller",
                witness_kind="controller_pytest_runtime",
                path="pkg/controller.py",
                blob="c" * 40,
                observation={"status": "passed"},
                source_event=_task1d_source_event(
                    binding=controller_binding,
                    consumer_path="pkg/controller.py",
                    caller_object_id="c" * 40,
                ),
            ),
            result(
                witness_id="witness-probe",
                selector_id="CO-PROBE-01",
                consumer_id="consumer-probe",
                witness_kind="runtime_probe",
                path="pkg/probe.py",
                blob="d" * 40,
                observation={"status": "returned"},
                source_event=_task1d_source_event(
                    binding=probe_binding,
                    consumer_path="pkg/probe.py",
                    caller_object_id="d" * 40,
                ),
            ),
            result(
                witness_id="witness-static",
                selector_id="CO-STATIC-01",
                consumer_id="consumer-static",
                witness_kind="static_ast",
                path="pkg/static.py",
                blob="e" * 40,
                observation={"matches": []},
                source_event=None,
                proof_kind="non_cdi_static",
            ),
        ]
    )
    controller_source_event = next(
        row["source_event"]
        for row in baseline["witness_results"]
        if row["witness_id"] == "witness-controller"
    )
    baseline["controller_selector_results"] = [
        {
            "selector_id": "CO-PYTEST-01",
            "execution_kind": "pytest_aggregate",
            "argv": copy.deepcopy(
                policy["selector_policy"]["controller_only_proof_selectors"][0][
                    "argv"
                ]
            ),
            "collected_node_ids": [controller_node],
            "collected_node_sha256": module.sequence_sha256([controller_node]),
            "collection_total": 1,
            "outcomes": {"errors": 0, "failed": 0, "passed": 1, "skipped": 0},
            "origin_isolation": copy.deepcopy(baseline["origin_isolation"]),
            "trace_sha256": module.raw_sha256(
                module.canonical_json_bytes(
                    [
                        {
                            "witness_id": "witness-controller",
                            "source_event": controller_source_event,
                        }
                    ]
                )
            ),
            "coverage_witness_ids": ["witness-controller"],
            "coverage_witness_node_outcomes": [],
        }
    ]
    return baseline, policy, census


def _task1d_node_attributed_controller_fixture(
    module: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    baseline, policy, census = _task1d_baseline_fixture(module)
    result = baseline["controller_selector_results"][0]
    selected_node = result["collected_node_ids"][0]
    unrelated_node = "tests/private/test_driver.py::test_unrelated_failure"
    result["collected_node_ids"] = [selected_node, unrelated_node]
    result["collected_node_sha256"] = module.sequence_sha256(
        result["collected_node_ids"]
    )
    result["collection_total"] = 2
    result["outcomes"] = {"errors": 0, "failed": 1, "passed": 1, "skipped": 0}
    node_outcome = {
        "witness_id": "witness-controller",
        "pytest_node_id": selected_node,
        "outcome": "passed",
    }
    result["coverage_witness_node_outcomes"] = [node_outcome]

    compact = next(
        row
        for row in policy["selector_policy"]["coverage_witness_specs"]
        if row["witness_id"] == "witness-controller"
    )
    compact["spec"]["phase"] = "call"
    compact["spec"]["attribution"] = {
        "attribution_kind": "pytest_node",
        "pytest_node_pattern": r"tests/private/test_driver\.py::test_boundary",
    }
    witness = next(
        row
        for row in baseline["witness_results"]
        if row["witness_id"] == "witness-controller"
    )
    witness["source_event"]["phase"] = "call"
    witness["source_event"]["attribution"] = {
        "attribution_kind": "pytest_node",
        "pytest_node_id": selected_node,
    }
    result["trace_sha256"] = module.raw_sha256(
        module.canonical_json_bytes(
            [
                {
                    "witness_id": "witness-controller",
                    "source_event": witness["source_event"],
                    "node_outcome": node_outcome,
                }
            ]
        )
    )
    return baseline, policy, census


def test_task1d_controller_discloses_unrelated_nonpass_and_binds_selected_node() -> None:
    module = _module()
    baseline, policy, census = _task1d_node_attributed_controller_fixture(module)

    module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
        baseline,
        policy=policy,
        census=census,
    )

    for tamper in ("missing", "witness", "node", "outcome", "carrier"):
        bad = copy.deepcopy(baseline)
        controller = bad["controller_selector_results"][0]
        if tamper == "missing":
            controller.pop("coverage_witness_node_outcomes")
        elif tamper == "witness":
            controller["coverage_witness_node_outcomes"][0]["witness_id"] = (
                "witness-other"
            )
        elif tamper == "node":
            controller["coverage_witness_node_outcomes"][0]["pytest_node_id"] = (
                "tests/private/test_driver.py::test_unrelated_failure"
            )
        elif tamper == "outcome":
            controller["coverage_witness_node_outcomes"][0]["outcome"] = "failed"
        else:
            controller["origin_isolation"]["pytest_carrier"]["sha256"] = (
                "sha256:" + "0" * 64
            )
        with pytest.raises(module.SourceCensusError):
            module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
                bad,
                policy=policy,
                census=census,
            )

    errored = copy.deepcopy(baseline)
    errored["controller_selector_results"][0]["outcomes"] = {
        "errors": 1,
        "failed": 0,
        "passed": 1,
        "skipped": 0,
    }
    with pytest.raises(module.SourceCensusError, match="baseline_pytest_failed"):
        module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
            errored,
            policy=policy,
            census=census,
        )


def test_task1d_baseline_keeps_provider_results_separate_from_controller_results() -> None:
    module = _module()
    baseline, policy, census = _task1d_baseline_fixture(module)
    provider_argv = copy.deepcopy(baseline["aggregate_pytest_argv"])
    provider_results = copy.deepcopy(baseline["selector_results"])

    validated, _, _ = module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
        baseline,
        policy=policy,
        census=census,
    )
    assert validated["aggregate_pytest_argv"] == provider_argv
    assert validated["selector_results"] == provider_results
    assert validated["controller_selector_results"] == baseline[
        "controller_selector_results"
    ]

    for tamper in ("missing", "extra", "backpointer", "cross_lane"):
        bad = copy.deepcopy(baseline)
        if tamper == "missing":
            bad.pop("controller_selector_results")
        elif tamper == "extra":
            bad["controller_selector_results"].append(
                copy.deepcopy(bad["controller_selector_results"][0])
            )
        elif tamper == "backpointer":
            bad["controller_selector_results"][0]["coverage_witness_ids"] = [
                "witness-provider"
            ]
        else:
            bad["witness_results"][0]["selector_id"] = "CO-PYTEST-01"
        with pytest.raises(module.SourceCensusError):
            module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
                bad,
                policy=policy,
                census=census,
            )


def test_task1d_runtime_source_event_join_is_exact_and_static_rejects_source_event() -> None:
    module = _module()
    baseline, policy, census = _task1d_baseline_fixture(module)
    module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
        baseline,
        policy=policy,
        census=census,
    )

    for tamper in ("missing", "action_digest", "static_extra"):
        bad = copy.deepcopy(baseline)
        if tamper == "missing":
            bad["witness_results"][0].pop("source_event")
        elif tamper == "action_digest":
            probe_result = next(
                row
                for row in bad["witness_results"]
                if row["witness_id"] == "witness-probe"
            )
            probe_result["source_event"]["attribution"]["action_sha256"] = (
                "sha256:" + "9" * 64
            )
        else:
            static_result = next(
                row
                for row in bad["witness_results"]
                if row["witness_id"] == "witness-static"
            )
            static_result["source_event"] = _task1d_source_event(
                binding=_task1d_source_event_binding(
                    phase="call",
                    attribution={
                        "attribution_kind": "pytest_node",
                        "pytest_node_id": "tests/private/test_driver.py::test_boundary",
                    },
                ),
                consumer_path="pkg/static.py",
                caller_object_id="e" * 40,
            )
        with pytest.raises(module.SourceCensusError):
            module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
                bad,
                policy=policy,
                census=census,
            )


def test_task3_controller_trace_digest_binds_labelled_source_event_rows() -> None:
    module = _module()
    baseline, policy, census = _task1d_baseline_fixture(module)
    module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
        baseline,
        policy=policy,
        census=census,
    )
    baseline["controller_selector_results"][0]["trace_sha256"] = (
        "sha256:" + "0" * 64
    )

    with pytest.raises(module.SourceCensusError) as caught:
        module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
            baseline,
            policy=policy,
            census=census,
        )

    assert caught.value.code == "baseline_controller_trace_digest_mismatch"


def test_task1g_controller_result_may_reuse_provider_node_in_separate_lane() -> None:
    module = _module()
    baseline, policy, census = _task1d_baseline_fixture(module)
    provider_node = baseline["collected_node_ids"][0]
    controller_result = baseline["controller_selector_results"][0]
    controller_result["collected_node_ids"] = [provider_node]
    controller_result["collected_node_sha256"] = module.sequence_sha256(
        [provider_node]
    )
    controller_result["collection_total"] = 1
    controller_result["outcomes"] = {
        "errors": 0,
        "failed": 0,
        "passed": 1,
        "skipped": 0,
    }

    validated, _, _ = module._validate_baseline_characterization(  # pyright: ignore[reportPrivateUsage]
        baseline,
        policy=policy,
        census=census,
    )

    provider_selector_ids = {
        row["selector_id"] for row in validated["selector_results"]
    }
    controller_selector_ids = {
        row["selector_id"] for row in validated["controller_selector_results"]
    }
    assert provider_selector_ids.isdisjoint(controller_selector_ids)
    assert validated["controller_selector_results"][0]["collected_node_ids"] == [
        provider_node
    ]


def test_task1h_provider_selector_module_attribution_joins_same_selector() -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(
        module
    )
    provider = selector_policy["provider_visible_pytest_selectors"][0]
    provider_spec = selector_policy["coverage_witness_specs"][0]["spec"]
    provider_spec["phase"] = "collection"
    provider_spec["attribution"] = {
        "attribution_kind": "selector_module",
        "pytest_module_path": provider["pytest_module_path"],
    }
    module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
        selector_policy,
        discovery_input=discovery_input,
        consumers=consumers,
    )

    provider_spec["attribution"]["pytest_module_path"] = (
        "tests/public/test_not_selected.py"
    )
    with pytest.raises(
        module.SourceCensusError, match="coverage_witness_attribution_invalid"
    ):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


def test_task1h_controller_selector_module_attribution_joins_same_selector() -> None:
    module = _module()
    selector_policy, discovery_input, consumers = _task1c_selector_join_fixture(
        module
    )
    module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
        selector_policy,
        discovery_input=discovery_input,
        consumers=consumers,
    )

    controller_spec = selector_policy["coverage_witness_specs"][1]["spec"]
    controller_spec["attribution"]["pytest_module_path"] = (
        "tests/private/test_not_selected.py"
    )
    with pytest.raises(
        module.SourceCensusError, match="coverage_witness_attribution_invalid"
    ):
        module._validate_selector_policy(  # pyright: ignore[reportPrivateUsage]
            selector_policy,
            discovery_input=discovery_input,
            consumers=consumers,
        )


def _task5_source_event(
    module: Any,
    candidate: Mapping[str, Any],
    *,
    event_kind: str,
    phase: str,
    attribution: Mapping[str, Any],
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_kind": event_kind,
        "phase": phase,
        "attribution": copy.deepcopy(dict(attribution)),
        "consumer_path": candidate["caller_path"],
        "caller_object_id": candidate["caller_object_id"],
        "span": copy.deepcopy(candidate["span"]),
        "hit_count": 1,
    }
    if event_kind == "opcode_exact_span":
        event[event_kind] = {
            "code_qualname": "fixture_boundary",
            "code_firstlineno": candidate["span"]["line_start"],
            "instruction_offset": 8,
            "opname": "CALL",
            "argrepr_sha256": "sha256:" + "8" * 64,
        }
    elif event_kind == "import_alias_opcode":
        event[event_kind] = {
            "code_qualname": "<module>",
            "code_firstlineno": candidate["span"]["line_start"],
            "statement_span": copy.deepcopy(candidate["span"]),
            "alias_ordinal": 0,
            "module": "fixture",
            "name": "boundary",
            "asname": None,
            "level": 0,
            "instruction_offset": 2,
            "opname": "IMPORT_NAME",
            "argval": "fixture",
        }
    else:
        event[event_kind] = {
            "code_qualname": "fixture_boundary",
            "code_name": "fixture_boundary",
            "code_firstlineno": candidate["span"]["line_start"],
            "definition_span": copy.deepcopy(candidate["span"]),
        }
    return event


def _task5_policy_completion_inputs(
    tmp_path: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    module = _module()
    projection = _bare_projection(
        tmp_path,
        provider_selector_count=2,
        runtime_consumer_count=7,
    )
    discovery_input = _discovery_input(projection)
    discovery_input["provider_visible_pytest_selectors"].append(
        {
            "selector_id": "focused-02",
            "ordinal": 2,
            "pytest_module_path": "selector_02.py",
        }
    )
    discovery_input_sha256 = module.raw_sha256(
        module.canonical_json_bytes(discovery_input)
    )
    discovery_output = module.discover_source(
        discovery_input,
        discovery_input_sha256=discovery_input_sha256,
    )
    candidates = discovery_output["consumer_candidates"]
    assert len(candidates) == 8
    assignments = [
        ("route_through_boundary", "boundary_runtime", "focused-01", "pytest_runtime", True),
        ("route_through_boundary", "boundary_runtime", "focused-01", "pytest_runtime", True),
        ("route_through_boundary", "boundary_runtime", "focused-02", "pytest_runtime", True),
        (
            "route_through_boundary",
            "boundary_runtime",
            "CO-PYTEST-01",
            "controller_pytest_runtime",
            True,
        ),
        ("route_through_boundary", "boundary_runtime", "CO-PROBE-01", "runtime_probe", True),
        ("route_through_boundary", "boundary_runtime", "CO-PROBE-01", "runtime_probe", False),
        ("compatibility_adapter", "non_cdi_static", "CO-NCDI-01", "static_ast", True),
        ("remove", "reference_absence", "CO-ABS-01", "static_ast", True),
    ]
    decisions: list[dict[str, Any]] = []
    observed_rows: list[dict[str, Any]] = []
    for index, (candidate, assignment) in enumerate(
        zip(candidates, assignments, strict=True)
    ):
        disposition, proof_kind, selector_id, witness_kind, observable = assignment
        decision = {
            **copy.deepcopy(candidate),
            "authority_status": "NEUTRAL_RECOMMENDATION_ONLY",
            "baseline_expected_to_pass": False if disposition == "remove" else None,
            "coverage_witness_ids": [
                "W-" + candidate["consumer_id"].removeprefix("consumer-").upper()
            ],
            "proposed_disposition": disposition,
            "required_proof_kind": proof_kind,
            "selector_id": selector_id,
            "spec_strategy": "non_executable_review_hint",
            "witness_kind": witness_kind,
        }
        decisions.append(decision)
        choices: list[dict[str, Any]] = []
        if observable:
            if witness_kind in {"pytest_runtime", "controller_pytest_runtime"}:
                if witness_kind == "controller_pytest_runtime":
                    phase = "collection"
                    attribution = {
                        "attribution_kind": "selector_module",
                        "pytest_module_path": "selector.py",
                    }
                else:
                    phase = "call"
                    provider_ordinal = 1 if selector_id == "focused-01" else 2
                    attribution = {
                        "attribution_kind": "pytest_node",
                        "pytest_node_id": _provider_selector_node(provider_ordinal),
                    }
                event_kind = "opcode_exact_span"
                expected_event = _task5_source_event(
                    module,
                    candidate,
                    event_kind=event_kind,
                    phase=phase,
                    attribution=attribution,
                )
                spec = {
                    "event_kind": event_kind,
                    "phase": phase,
                    "attribution": attribution,
                    "expected_event": expected_event,
                }
            elif witness_kind == "runtime_probe":
                probe = {
                    "action": "import_module",
                    "module": "model",
                    "expected_outcome": {"status": "returned"},
                }
                attribution = {
                    "attribution_kind": "residual_action",
                    "action_sha256": module.raw_sha256(
                        module.canonical_json_bytes(probe)
                    ),
                }
                expected_event = _task5_source_event(
                    module,
                    candidate,
                    event_kind="opcode_exact_span",
                    phase="residual",
                    attribution=attribution,
                )
                spec = {
                    "event_kind": "opcode_exact_span",
                    "phase": "residual",
                    "attribution": attribution,
                    "probe": probe,
                    "expected_event": expected_event,
                }
            elif disposition == "compatibility_adapter":
                spec = {
                    "query": {
                        "query_kind": "forbidden_syntax_absent",
                        "forbidden_names": ["run_grid_lines_torch"],
                        "forbidden_attributes": [],
                        "forbidden_string_literals": [],
                    },
                    "expected_event": {"matches": []},
                }
            else:
                spec = {
                    "query": {"query_kind": "path_absent"},
                    "expected_event": {"path_absent": True},
                }
            choices.append(
                {
                    "selector_id": selector_id,
                    "proof_kind": proof_kind,
                    "witness_kind": witness_kind,
                    "spec": spec,
                }
            )
        observed_rows.append(
            {
                **copy.deepcopy(candidate),
                "proposed_disposition": disposition,
                "required_proof_kind": proof_kind,
                "selector_id": selector_id,
                "witness_kind": witness_kind,
                "observation_status": "observable" if observable else "open",
                "reason_code": (
                    "fixture_exact_event_replayed"
                    if observable
                    else "fixture_event_unobserved"
                ),
                "executable_choices": choices,
            }
        )
    discovery_output_sha256 = module.raw_sha256(
        module.canonical_json_bytes(discovery_output)
    )
    reviewed_dispositions: dict[str, Any] = {
        "schema_version": "es_f1_policy_path_decisions_candidate.v1",
        "authority_status": "NON_AUTHORITATIVE_NEUTRAL_RECOMMENDATION",
        "source_discovery": {
            "path": ".tmp/es-f1-source-census-discovery-1.json",
            "raw_sha256": discovery_output_sha256,
            "discovery_input_sha256": discovery_input_sha256,
            "candidate_set_sha256": discovery_output["candidate_set_sha256"],
            "consumer_candidate_count": len(candidates),
            "caller_path_count": len(
                {candidate["caller_path"] for candidate in candidates}
            ),
            "leaf_count": len(discovery_output["leaf_rows"]),
            "projection_repository": str(projection["repository"]),
            "projection_commit": projection["commit"],
            "projection_tree": projection["tree"],
        },
        "mapping_contract": {
            "consumer_order_preserved_from_discovery": True,
            "default_disposition": None,
            "disposition_to_proof": {
                "compatibility_adapter": "non_cdi_static",
                "remove": "reference_absence",
                "route_through_boundary": "boundary_runtime",
            },
            "every_discovered_consumer_explicitly_enumerated": True,
            "every_discovered_path_explicitly_enumerated": True,
            "path_set_equality_verified": True,
            "proof_results_claimed": False,
            "selector_node_feasibility_claimed": False,
        },
        "detector_findings": [
            {
                "classification": "fixture_closed_shape",
                "consumer_ids": [candidates[0]["consumer_id"]],
                "count": 1,
                "detail": "Fixture finding exercises the reviewed record shape.",
                "finding_id": "FIXTURE_FINDING",
                "paths": [candidates[0]["caller_path"]],
            }
        ],
        "ambiguous_cases": [],
        "controller_selector_recommendations": [
            {
                "note": "Fixture controller recommendation.",
                "proof_kind": "boundary_runtime",
                "selector_id": "CO-PROBE-01",
                "witness_kind": "runtime_probe",
            },
            {
                "note": "Fixture static recommendation.",
                "proof_kind": "non_cdi_static",
                "selector_id": "CO-NCDI-01",
                "witness_kind": "static_ast",
            },
            {
                "note": "Fixture absence recommendation.",
                "proof_kind": "reference_absence",
                "selector_id": "CO-ABS-01",
                "witness_kind": "static_ast",
            },
        ],
        "path_decisions": [],
        "consumer_decisions": decisions,
        "counts": {
            "consumers_by_disposition": {
                disposition: sum(
                    row["proposed_disposition"] == disposition for row in decisions
                )
                for disposition in (
                    "compatibility_adapter",
                    "remove",
                    "route_through_boundary",
                )
            },
            "paths_by_disposition": {},
        },
    }
    leaves_by_path = {
        row["path"]: row for row in discovery_output["leaf_rows"]
    }
    for caller_path in dict.fromkeys(row["caller_path"] for row in decisions):
        path_rows = [row for row in decisions if row["caller_path"] == caller_path]
        leaf = leaves_by_path[caller_path]
        reviewed_dispositions["path_decisions"].append(
            {
                "anchor_ids": sorted(
                    {row["anchor_id"] for row in path_rows}, key=str.encode
                ),
                "authority_status": "NEUTRAL_RECOMMENDATION_ONLY",
                "caller_object_id": path_rows[0]["caller_object_id"],
                "caller_path": caller_path,
                "candidate_count": len(path_rows),
                "consumer_ids": [row["consumer_id"] for row in path_rows],
                "rationale_code": "fixture_reviewed_classification",
                "recommended_disposition": path_rows[0]["proposed_disposition"],
                "recommended_selector_ids": list(
                    dict.fromkeys(row["selector_id"] for row in path_rows)
                ),
                "recommended_witness_kinds": list(
                    dict.fromkeys(row["witness_kind"] for row in path_rows)
                ),
                "required_proof_kind": path_rows[0]["required_proof_kind"],
                "source_audit": {
                    "ast_parsed": caller_path.endswith(".py"),
                    "blob_id_verified": True,
                    "byte_count": leaf["byte_count"],
                    "matched_source_lines_sha256": module.raw_sha256(
                        module.canonical_json_bytes(
                            [row["consumer_id"] for row in path_rows]
                        )
                    ),
                    "physical_line_count": leaf["text"]["physical_line_count"],
                    "source": "pinned_bare_projection_blob",
                },
            }
        )
    reviewed_dispositions["counts"]["paths_by_disposition"] = {
        disposition: sum(
            row["recommended_disposition"] == disposition
            for row in reviewed_dispositions["path_decisions"]
        )
        for disposition in (
            "compatibility_adapter",
            "remove",
            "route_through_boundary",
        )
    }
    reviewed_dispositions["candidate_sha256"] = module.raw_sha256(
        module.canonical_json_bytes(reviewed_dispositions)
    )
    reviewed_dispositions_sha256 = module.raw_sha256(
        module.canonical_json_bytes(reviewed_dispositions)
    )
    selector_leaf = next(
        row for row in discovery_output["leaf_rows"] if row["path"] == "selector.py"
    )
    selector_payload = _run_git(
        Path(projection["repository"]),
        "cat-file",
        "blob",
        selector_leaf["object_id"],
    )
    proof_runner_sha256 = module.raw_sha256(
        Path("scripts/experiments/es/boundary_proofs.py").read_bytes()
    )
    controller_selector_candidate = {
        "selector_id": "CO-PYTEST-01",
        "ordinal": 1,
        "proof_kind": "boundary_runtime",
        "execution_kind": "pytest_aggregate",
        "runner_path": "scripts/experiments/es/boundary_proofs.py",
        "runner_sha256": proof_runner_sha256,
        "argv": [
            TASK0_PYTHON,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "selector.py",
        ],
        "input_bindings": [
            {
                "path": "selector.py",
                "sha256": module.raw_sha256(selector_payload),
            }
        ],
        "projection_bindings": [
            {
                "path": "selector.py",
                "projection_blob_id": selector_leaf["object_id"],
            }
        ],
    }
    observation_candidates = {
        "schema_version": "es_f1_witness_observation_candidates.v1",
        "authority_status": "NON_AUTHORITATIVE",
        "input_bindings": {
            "discovery_input_sha256": discovery_input_sha256,
            "discovery_output_sha256": discovery_output_sha256,
            "draft_dispositions_sha256": reviewed_dispositions_sha256,
            "projection_tree": projection["tree"],
            "runner_sha256": proof_runner_sha256,
            "pytest_carrier": copy.deepcopy(TASK0_PYTEST_CARRIER),
            "controller_module_order_sha256": "sha256:" + "7" * 64,
            "controller_pytest_selector_candidate": controller_selector_candidate,
        },
        "counts": {
            "ambiguous": 0,
            "observable": 7,
            "open": 1,
            "total": len(candidates),
        },
        "candidate_rows": observed_rows,
    }
    return (
        discovery_input,
        discovery_output,
        observation_candidates,
        reviewed_dispositions,
    )


def _complete_task5_candidate(
    module: Any,
    discovery_input: Mapping[str, Any],
    discovery_output: Mapping[str, Any],
    observation_candidates: Mapping[str, Any],
    reviewed_dispositions: Mapping[str, Any],
    *,
    no_consumption_captured_at: str = "2026-08-04T12:00:00-07:00",
    a1_evidence_root: str = (
        "/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/"
        "pilot-2026-07-27/a1-v7"
    ),
) -> dict[str, Any]:
    return module.complete_policy_candidate(
        discovery_input,
        discovery_output=discovery_output,
        observation_candidates=observation_candidates,
        reviewed_dispositions=reviewed_dispositions,
        expected_discovery_input_sha256=module.raw_sha256(
            module.canonical_json_bytes(discovery_input)
        ),
        expected_discovery_output_sha256=module.raw_sha256(
            module.canonical_json_bytes(discovery_output)
        ),
        expected_observation_candidates_sha256=module.raw_sha256(
            module.canonical_json_bytes(observation_candidates)
        ),
        expected_reviewed_dispositions_sha256=module.raw_sha256(
            module.canonical_json_bytes(reviewed_dispositions)
        ),
        producer_sha256=module.raw_sha256(Path(module.__file__).read_bytes()),
        proof_runner_sha256=module.raw_sha256(
            Path("scripts/experiments/es/boundary_proofs.py").read_bytes()
        ),
        no_consumption_captured_at=no_consumption_captured_at,
        a1_evidence_root=a1_evidence_root,
    )


def test_task5_complete_policy_candidate_applies_exact_sampling_union(
    tmp_path: Path,
) -> None:
    module = _module()
    inputs = _task5_policy_completion_inputs(tmp_path)

    result = _complete_task5_candidate(module, *inputs)

    assert set(result) == {
        "schema_version",
        "authority_status",
        "input_bindings",
        "counts",
        "policy_body",
    }
    assert result["schema_version"] == "es_f1_complete_policy_candidate.v1"
    assert result["authority_status"] == "NON_AUTHORITATIVE"
    assert result["counts"] == {
        "total": 8,
        "observable": 7,
        "required": 6,
        "inherited": 1,
        "open": 1,
    }
    body = result["policy_body"]
    assert body["selector_policy"]["pytest_carrier"] == TASK0_PYTEST_CARRIER
    assert set(body) == {
        "schema_version",
        "discovery",
        "git",
        "projection",
        "schema_bindings",
        "lineage",
        "detectors",
        "responsibilities",
        "consumer_policies",
        "selector_policy",
        "audit_groups",
        "legacy_bypass_consumer_ids",
        "no_consumption",
        "a1",
    }
    assert body["schema_version"] == "es_f1_preedit_policy.v1"
    assert [row["coverage_status"] for row in body["consumer_policies"]] == [
        "required",
        "inherited",
        "required",
        "required",
        "required",
        "open",
        "required",
        "required",
    ]
    required_ids = {
        row["consumer_id"]
        for row in body["consumer_policies"]
        if row["coverage_status"] == "required"
    }
    witnesses = body["selector_policy"]["coverage_witness_specs"]
    desired = body["selector_policy"]["desired_state_proof_specs"]
    assert {row["consumer_id"] for row in witnesses} == required_ids
    assert {row["witness_id"] for row in witnesses} == {
        row["witness_id"] for row in desired
    }
    assert all("anchor_id" in row["spec"] for row in witnesses)
    provider_ids = {
        row["selector_id"]
        for row in body["selector_policy"]["provider_visible_pytest_selectors"]
    }
    assert {
        selector_id: sum(row["selector_id"] == selector_id for row in witnesses)
        for selector_id in provider_ids
    } == {"focused-01": 1, "focused-02": 1}
    assert all(
        len(row["coverage_witness_ids"]) <= 1
        for row in body["selector_policy"]["controller_only_proof_selectors"]
    )
    payload = module.canonical_json_bytes(result)
    assert b"spec_strategy" not in payload
    assert b"record_sha256" not in payload
    assert b'"owner_adoption"' not in payload
    assert b"witness_observability_reviews" not in payload
    provider_projection = module.canonical_json_bytes(
        body["selector_policy"]["provider_visible_pytest_selectors"]
    )
    assert b"CO-PYTEST-01" not in provider_projection
    assert result == _complete_task5_candidate(
        module, *(copy.deepcopy(row) for row in inputs)
    )


def test_task5_complete_policy_candidate_adopts_exact_controller_lane_promotion(
    tmp_path: Path,
) -> None:
    module = _module()
    inputs = list(_task5_policy_completion_inputs(tmp_path))
    observation = inputs[2]
    dispositions = inputs[3]
    decision = dispositions["consumer_decisions"][3]
    decision.update(
        {
            "selector_id": "CO-BR-01",
            "witness_kind": "runtime_probe",
            "spec_strategy": "requires_explicit_action",
        }
    )
    path_row = next(
        row
        for row in dispositions["path_decisions"]
        if decision["consumer_id"] in row["consumer_ids"]
    )
    path_decisions = [
        row
        for row in dispositions["consumer_decisions"]
        if row["caller_path"] == decision["caller_path"]
    ]
    path_row["recommended_selector_ids"] = list(
        dict.fromkeys(row["selector_id"] for row in path_decisions)
    )
    path_row["recommended_witness_kinds"] = list(
        dict.fromkeys(row["witness_kind"] for row in path_decisions)
    )
    body = copy.deepcopy(dispositions)
    body.pop("candidate_sha256")
    dispositions["candidate_sha256"] = module.raw_sha256(
        module.canonical_json_bytes(body)
    )
    dispositions_sha256 = module.raw_sha256(
        module.canonical_json_bytes(dispositions)
    )
    observation["input_bindings"][
        "draft_dispositions_sha256"
    ] = dispositions_sha256
    observation["candidate_rows"][3].update(
        {"selector_id": "CO-BR-01", "witness_kind": "runtime_probe"}
    )

    result = _complete_task5_candidate(module, *inputs)

    policy = result["policy_body"]["consumer_policies"][3]
    assert policy["selector_id"] == "CO-PYTEST-01"
    assert policy["witness_kind"] == "controller_pytest_runtime"
    witness = next(
        row
        for row in result["policy_body"]["selector_policy"]["coverage_witness_specs"]
        if row["consumer_id"] == policy["consumer_id"]
    )
    assert witness["selector_id"] == "CO-PYTEST-01"
    assert witness["witness_kind"] == "controller_pytest_runtime"


@pytest.mark.parametrize("missing", ["provider", "class"])
def test_task5_complete_policy_candidate_blocks_missing_required_sample(
    tmp_path: Path,
    missing: str,
) -> None:
    module = _module()
    inputs = list(_task5_policy_completion_inputs(tmp_path))
    observation = inputs[2]
    index = 2 if missing == "provider" else 4
    row = observation["candidate_rows"][index]
    row.update(
        {
            "observation_status": "open",
            "reason_code": "fixture_event_unobserved",
            "executable_choices": [],
        }
    )
    observation["counts"].update({"observable": 6, "open": 2})

    with pytest.raises(module.SourceCensusError, match="coverage_required_sample_missing"):
        _complete_task5_candidate(module, *inputs)


@pytest.mark.parametrize(
    "tamper",
    [
        "source_event",
        "choice_shape",
        "decision_join",
        "candidate_domain",
        "controller_projection",
        "carrier",
    ],
)
def test_task5_complete_policy_candidate_rejects_tampered_inputs(
    tmp_path: Path,
    tamper: str,
) -> None:
    module = _module()
    inputs = list(_task5_policy_completion_inputs(tmp_path))
    discovery, observation, decisions = inputs[1], inputs[2], inputs[3]
    if tamper == "source_event":
        observation["candidate_rows"][0]["executable_choices"][0]["spec"][
            "expected_event"
        ]["caller_object_id"] = "0" * 40
    elif tamper == "choice_shape":
        observation["candidate_rows"][0]["executable_choices"][0]["spec"][
            "spec_strategy"
        ] = "forbidden_placeholder"
    elif tamper == "decision_join":
        decisions["consumer_decisions"][0]["selector_id"] = "focused-02"
        body = copy.deepcopy(decisions)
        body.pop("candidate_sha256")
        decisions["candidate_sha256"] = module.raw_sha256(
            module.canonical_json_bytes(body)
        )
    elif tamper == "candidate_domain":
        discovery["consumer_candidates"].pop()
        discovery["candidate_set_sha256"] = module.raw_sha256(
            module.canonical_json_bytes(discovery["consumer_candidates"])
        )
    elif tamper == "controller_projection":
        observation["input_bindings"]["controller_pytest_selector_candidate"][
            "projection_bindings"
        ][0]["projection_blob_id"] = "0" * 40
    else:
        observation["input_bindings"]["pytest_carrier"]["sha256"] = (
            "sha256:" + "0" * 64
        )

    with pytest.raises(module.SourceCensusError):
        _complete_task5_candidate(module, *inputs)


@pytest.mark.parametrize("location", ["top", "path_decision"])
def test_task5_complete_policy_candidate_rejects_extra_disposition_fields(
    tmp_path: Path,
    location: str,
) -> None:
    module = _module()
    inputs = list(_task5_policy_completion_inputs(tmp_path))
    dispositions = inputs[3]
    if location == "top":
        dispositions["extra"] = True
    else:
        dispositions["path_decisions"][0]["extra"] = True
    body = copy.deepcopy(dispositions)
    body.pop("candidate_sha256")
    dispositions["candidate_sha256"] = module.raw_sha256(
        module.canonical_json_bytes(body)
    )

    with pytest.raises(module.SourceCensusError, match="source_census_shape_invalid"):
        _complete_task5_candidate(module, *inputs)


@pytest.mark.parametrize(
    ("captured_at", "a1_root", "error"),
    [
        (
            "2026-08-04T12:00:00",
            "/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/"
            "pilot-2026-07-27/a1-v7",
            "no_consumption_timestamp_invalid",
        ),
        (
            "2026-08-04T12:00:00-07:00",
            "/tmp/not-the-frozen-a1-root",
            "a1_policy_invalid",
        ),
    ],
)
def test_task5_complete_policy_candidate_requires_explicit_capture_and_a1_authority(
    tmp_path: Path,
    captured_at: str,
    a1_root: str,
    error: str,
) -> None:
    module = _module()
    with pytest.raises(module.SourceCensusError, match=error):
        _complete_task5_candidate(
            module,
            *_task5_policy_completion_inputs(tmp_path),
            no_consumption_captured_at=captured_at,
            a1_evidence_root=a1_root,
        )


def test_task5_complete_policy_candidate_cli_is_digest_bound_and_deterministic(
    tmp_path: Path,
) -> None:
    module = _module()
    names = (
        "discovery-input",
        "discovery-output",
        "observation-candidates",
        "reviewed-dispositions",
    )
    values = _task5_policy_completion_inputs(tmp_path)
    assert module.__file__ is not None
    paths: dict[str, Path] = {}
    digests: dict[str, str] = {}
    for name, value in zip(names, values, strict=True):
        path = tmp_path / f"{name}.json"
        payload = module.canonical_json_bytes(value)
        path.write_bytes(payload)
        paths[name] = path
        digests[name] = module.raw_sha256(payload)

    def argv(output: Path) -> list[str]:
        return [
            "complete-policy-candidate",
            "--discovery-input",
            str(paths["discovery-input"]),
            "--expected-discovery-input-sha256",
            digests["discovery-input"],
            "--discovery-output",
            str(paths["discovery-output"]),
            "--expected-discovery-output-sha256",
            digests["discovery-output"],
            "--observation-candidates",
            str(paths["observation-candidates"]),
            "--expected-observation-candidates-sha256",
            digests["observation-candidates"],
            "--reviewed-dispositions",
            str(paths["reviewed-dispositions"]),
            "--expected-reviewed-dispositions-sha256",
            digests["reviewed-dispositions"],
            "--producer-sha256",
            module.raw_sha256(Path(str(module.__file__)).read_bytes()),
            "--proof-runner-sha256",
            module.raw_sha256(
                Path("scripts/experiments/es/boundary_proofs.py").read_bytes()
            ),
            "--no-consumption-captured-at",
            "2026-08-04T12:00:00-07:00",
            "--a1-evidence-root",
            (
                "/home/ollie/.local/share/agent-orchestration/"
                "lean-pilot-evidence/pilot-2026-07-27/a1-v7"
            ),
            "--output",
            str(output),
        ]

    first = tmp_path / "complete-1.json"
    second = tmp_path / "complete-2.json"
    assert module.main(argv(first)) == 0
    assert module.main(argv(second)) == 0
    assert first.read_bytes() == second.read_bytes()
    stale = argv(tmp_path / "stale.json")
    stale[stale.index("--expected-observation-candidates-sha256") + 1] = (
        "sha256:" + "0" * 64
    )
    assert module.main(stale) == 2
    assert not (tmp_path / "stale.json").exists()


def _witness_review_record(
    module: Any,
    *,
    review_kind: str,
    verdict: str,
    reviewed_at: str,
    candidate_files: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": "es_f1_witness_observability_review.v1",
        "review_kind": review_kind,
        "verdict": verdict,
        "reviewer": f"fixture:{review_kind}",
        "reviewed_at": reviewed_at,
        "candidate_files": candidate_files,
        "candidate_set_sha256": module.raw_sha256(
            module.canonical_json_bytes(candidate_files)
        ),
        "findings": [],
    }


def _task7_review_inputs(module: Any) -> tuple[dict[str, Any], ...]:
    historical_candidates = [
        {
            "path": "docs/plans/2026-08-04-es-f1-witness-observability-correction-plan.md",
            "sha256": "sha256:" + "1" * 64,
        },
        {
            "path": "docs/plans/2026-08-03-es-f1-large-scope-refreeze-execution-plan.md",
            "sha256": "sha256:" + "2" * 64,
        },
    ]
    implementation_candidates = [
        {
            "path": path,
            "sha256": module.raw_sha256(Path(path).read_bytes()),
        }
        for path in (
            "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.schema.json",
            "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-selector-manifest.schema.json",
            "docs/plans/evidence/es-f1-large-scope-refreeze/source-census.schema.json",
            "scripts/experiments/es/source_census.py",
            "scripts/experiments/es/boundary_proofs.py",
            "scripts/experiments/es/projection.py",
            "tests/experiments/test_es_source_census.py",
            "tests/experiments/test_es_boundary_proofs.py",
            "tests/experiments/test_es_f1_projection.py",
        )
    ]
    return (
        _witness_review_record(
            module,
            review_kind="plan_specification",
            verdict="ES_F1_WITNESS_PLAN_SPEC_APPROVED",
            reviewed_at="2026-08-04T09:00:00-07:00",
            candidate_files=historical_candidates,
        ),
        _witness_review_record(
            module,
            review_kind="plan_quality",
            verdict="ES_F1_WITNESS_PLAN_QUALITY_APPROVED",
            reviewed_at="2026-08-04T09:01:00-07:00",
            candidate_files=historical_candidates,
        ),
        _witness_review_record(
            module,
            review_kind="implementation",
            verdict="ES_F1_WITNESS_IMPLEMENTATION_APPROVED",
            reviewed_at="2026-08-04T13:00:00-07:00",
            candidate_files=implementation_candidates,
        ),
    )


def _task7_fixture_schema(path: Path, policy_body: Mapping[str, Any]) -> None:
    properties = {key: {} for key in policy_body}
    properties.update(
        {
            "witness_observability_reviews": {"type": "object"},
            "record_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        }
    )
    path.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": list(properties),
                "properties": properties,
            }
        ),
        encoding="utf-8",
    )


def test_task7_publish_policy_promotes_only_reviewed_complete_candidate(
    tmp_path: Path,
) -> None:
    module = _module()
    candidate = _complete_task5_candidate(
        module, *_task5_policy_completion_inputs(tmp_path)
    )
    reviews = _task7_review_inputs(module)
    schema_path = tmp_path / "policy.schema.json"
    _task7_fixture_schema(schema_path, candidate["policy_body"])

    policy = module.publish_policy_candidate(
        candidate,
        expected_candidate_sha256=module.raw_sha256(
            module.canonical_json_bytes(candidate)
        ),
        current_plan_sha256="sha256:" + "a" * 64,
        plan_specification_review=reviews[0],
        expected_plan_specification_review_sha256=module.raw_sha256(
            module.canonical_json_bytes(reviews[0])
        ),
        plan_quality_review=reviews[1],
        expected_plan_quality_review_sha256=module.raw_sha256(
            module.canonical_json_bytes(reviews[1])
        ),
        implementation_review=reviews[2],
        expected_implementation_review_sha256=module.raw_sha256(
            module.canonical_json_bytes(reviews[2])
        ),
        policy_schema=schema_path,
    )

    assert set(policy) == set(candidate["policy_body"]) | {
        "witness_observability_reviews",
        "record_sha256",
    }
    module.validate_record_sha256(policy)
    assert policy["witness_observability_reviews"]["plan"]["sha256"] == (
        "sha256:" + "a" * 64
    )
    assert policy["witness_observability_reviews"]["implementation_review"][
        "candidate_set_sha256"
    ] == reviews[2]["candidate_set_sha256"]


@pytest.mark.parametrize(
    ("tamper", "error"),
    [
        ("implementation_candidate", "witness_review_candidate_invalid"),
        ("no_consumption", "no_consumption_fact_mismatch"),
        ("schema", "schema_validation_failed"),
    ],
)
def test_task7_publish_policy_rejects_review_state_and_schema_drift(
    tmp_path: Path,
    tamper: str,
    error: str,
) -> None:
    module = _module()
    candidate = _complete_task5_candidate(
        module, *_task5_policy_completion_inputs(tmp_path)
    )
    reviews = list(_task7_review_inputs(module))
    schema_path = tmp_path / "policy.schema.json"
    _task7_fixture_schema(schema_path, candidate["policy_body"])
    if tamper == "implementation_candidate":
        reviews[2]["candidate_files"][0]["sha256"] = "sha256:" + "0" * 64
        reviews[2]["candidate_set_sha256"] = module.raw_sha256(
            module.canonical_json_bytes(reviews[2]["candidate_files"])
        )
    elif tamper == "no_consumption":
        row = candidate["policy_body"]["no_consumption"]["external_roots"][0]
        row["status"] = (
            "PRESENT_EMPTY_DIRECTORY" if row["status"] == "ABSENT" else "ABSENT"
        )
        observation = candidate["policy_body"]["no_consumption"]
        observation["observation_sha256"] = module.no_consumption_observation_sha256(
            observation["external_roots"], observation["repository_paths"]
        )
    else:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["required"].append("impossible_required_field")
        schema["properties"]["impossible_required_field"] = {"const": True}
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
    review_digests = [
        module.raw_sha256(module.canonical_json_bytes(review)) for review in reviews
    ]

    with pytest.raises(module.SourceCensusError, match=error):
        module.publish_policy_candidate(
            candidate,
            expected_candidate_sha256=module.raw_sha256(
                module.canonical_json_bytes(candidate)
            ),
            current_plan_sha256="sha256:" + "a" * 64,
            plan_specification_review=reviews[0],
            expected_plan_specification_review_sha256=review_digests[0],
            plan_quality_review=reviews[1],
            expected_plan_quality_review_sha256=review_digests[1],
            implementation_review=reviews[2],
            expected_implementation_review_sha256=review_digests[2],
            policy_schema=schema_path,
        )


def test_task7_exclusive_policy_publication_rejects_even_identical_existing_bytes(
    tmp_path: Path,
) -> None:
    module = _module()
    output = tmp_path / "policy.json"
    value = {"schema_version": "fixture"}
    module._publish_json_exclusive(output, value)  # pyright: ignore[reportPrivateUsage]
    assert output.read_bytes() == module.canonical_json_bytes(value)

    with pytest.raises(module.SourceCensusError, match="output_collision"):
        module._publish_json_exclusive(  # pyright: ignore[reportPrivateUsage]
            output, value
        )


@pytest.mark.parametrize("digest_target", ["candidate", "review"])
def test_task7_publish_policy_rejects_explicit_raw_digest_tamper(
    tmp_path: Path,
    digest_target: str,
) -> None:
    module = _module()
    candidate = _complete_task5_candidate(
        module, *_task5_policy_completion_inputs(tmp_path)
    )
    reviews = _task7_review_inputs(module)
    schema_path = tmp_path / "policy.schema.json"
    _task7_fixture_schema(schema_path, candidate["policy_body"])
    candidate_sha256 = module.raw_sha256(module.canonical_json_bytes(candidate))
    review_digests = [
        module.raw_sha256(module.canonical_json_bytes(review)) for review in reviews
    ]
    if digest_target == "candidate":
        candidate_sha256 = "sha256:" + "0" * 64
    else:
        review_digests[1] = "sha256:" + "0" * 64

    with pytest.raises(
        module.SourceCensusError,
        match=(
            "policy_candidate_digest_mismatch"
            if digest_target == "candidate"
            else "witness_review_digest_mismatch"
        ),
    ):
        module.publish_policy_candidate(
            candidate,
            expected_candidate_sha256=candidate_sha256,
            current_plan_sha256="sha256:" + "a" * 64,
            plan_specification_review=reviews[0],
            expected_plan_specification_review_sha256=review_digests[0],
            plan_quality_review=reviews[1],
            expected_plan_quality_review_sha256=review_digests[1],
            implementation_review=reviews[2],
            expected_implementation_review_sha256=review_digests[2],
            policy_schema=schema_path,
        )
