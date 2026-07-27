from __future__ import annotations

import copy
import hashlib
import itertools
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from orchestrator.experiments import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.experiments._evaluation_support import EvaluationError
from orchestrator.experiments import _pilot_review_execution as review_execution
from orchestrator.experiments._pilot_review import (
    publish_review_bindings,
    publish_unblinding_bindings,
    run_live_review_slot,
    validate_live_reviewer_apparatus,
)


FIXTURE_CLI = (
    Path(__file__).parent
    / "fixtures"
    / "lean_pilot"
    / "fake_reviewer_cli.py"
)
STAGED_REVIEW_ROOT = Path("controller-runtime/live-review")
STAGED_SCHEMA = STAGED_REVIEW_ROOT / "live-output.schema.json"
STAGED_RUBRIC = STAGED_REVIEW_ROOT / "rubric.md"
DIMENSIONS = (
    "TASK_COMPLETENESS",
    "BEHAVIORAL_CORRECTNESS",
    "MAINTAINABILITY",
    "SCOPE_CONTROL",
    "EVIDENCE_QUALITY",
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest(value: str) -> str:
    return _digest_bytes(value.encode())


def _schema() -> dict[str, Any]:
    citation = {
        "type": "array",
        "minItems": 1,
        "items": {"type": "string", "minLength": 1},
    }
    dimension = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dimension": {"type": "string", "enum": list(DIMENSIONS)},
            "assessment": {
                "type": "string",
                "enum": ["PASS", "CONCERN", "FAIL", "INDETERMINATE"],
            },
            "rationale": {"type": "string", "minLength": 1},
            "evidence_citations": citation,
        },
        "required": [
            "dimension",
            "assessment",
            "rationale",
            "evidence_citations",
        ],
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidates": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "opaque_label": {"type": "string", "minLength": 1},
                        "evidence_citations": citation,
                        "dimension_assessments": {
                            "type": "array",
                            "minItems": 5,
                            "maxItems": 5,
                            "items": dimension,
                        },
                        "sealed_treatment_guess": {
                            "type": "string",
                            "enum": [
                                "DIRECT",
                                "COORDINATOR",
                                "ORC",
                                "UNKNOWN",
                            ],
                        },
                    },
                    "required": [
                        "opaque_label",
                        "evidence_citations",
                        "dimension_assessments",
                        "sealed_treatment_guess",
                    ],
                },
            },
            "pairwise_results": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "candidate_a_label": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "candidate_b_label": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "outcome": {
                            "type": "string",
                            "enum": ["A", "B", "TIE", "INDETERMINATE"],
                        },
                        "rationale": {"type": "string", "minLength": 1},
                        "evidence_citations": citation,
                    },
                    "required": [
                        "candidate_a_label",
                        "candidate_b_label",
                        "outcome",
                        "rationale",
                        "evidence_citations",
                    ],
                },
            },
        },
        "required": ["candidates", "pairwise_results"],
    }


def _execution(
    cli: Path,
    environment: dict[str, str],
    *,
    timeout_milliseconds: int,
) -> dict[str, Any]:
    return {
        "provider_family": "codex-cli",
        "model": "gpt-5.5",
        "reasoning_effort": "high",
        "tool_policy": "read-only-package",
        "timeout_milliseconds": timeout_milliseconds,
        "cli": {
            "entry_path": cli.as_posix(),
            "entry_sha256": _digest_bytes(cli.read_bytes()),
            "version": "fake-codex-cli-v1",
        },
        "environment": {
            "identity": canonical_sha256(
                [[key, environment[key]] for key in sorted(environment)]
            ),
            "allowed_keys": sorted(environment),
            "credential_keys": [],
        },
        "invocation_payload_schema_digest": _digest(
            "calibration-two-candidate-schema"
        ),
    }


def _bundle_digest(
    apparatus: dict[str, Any],
    paths: list[str],
) -> str:
    manifest = {
        item["path"]: item for item in apparatus["asset_manifest"]
    }
    return canonical_sha256(
        [manifest[path] for path in sorted(paths, key=str.encode)]
    )


def _rebind_live_schema(
    *,
    lock: dict[str, Any],
    control: Path,
    schema: dict[str, Any],
) -> None:
    schema_path = control / "review/review-result.schema.json"
    config_path = control / "review/reviewer-command.json"
    schema_bytes = canonical_json_bytes(schema)
    schema_path.write_bytes(schema_bytes)
    config = json.loads(config_path.read_text())
    config["live_output_schema_digest"] = _digest_bytes(schema_bytes)
    config_path.write_bytes(canonical_json_bytes(config))
    manifest = {
        row["path"]: row for row in lock["apparatus"]["asset_manifest"]
    }
    manifest["review/review-result.schema.json"]["sha256"] = _digest_bytes(
        schema_bytes
    )
    manifest["review/reviewer-command.json"]["sha256"] = _digest_bytes(
        config_path.read_bytes()
    )
    lock["review"]["reviewer_command"]["bundle_digest"] = _bundle_digest(
        lock["apparatus"],
        lock["review"]["reviewer_command"]["asset_paths"],
    )


def _rebind_calibration_lock_bytes(
    *,
    lock: dict[str, Any],
    control: Path,
    data: bytes,
) -> None:
    calibration_path = control / "review/calibration-lock.json"
    calibration_path.write_bytes(data)
    manifest = {
        row["path"]: row for row in lock["apparatus"]["asset_manifest"]
    }
    manifest["review/calibration-lock.json"]["sha256"] = _digest_bytes(data)
    lock["review"]["reviewer_command"]["bundle_digest"] = _bundle_digest(
        lock["apparatus"],
        lock["review"]["reviewer_command"]["asset_paths"],
    )


def _refresh_profile(lock: dict[str, Any]) -> None:
    lock["task"]["profile_digest"] = canonical_sha256(
        {
            "profile_version": "lean-pilot-task-profile.v1",
            "task_id": lock["task"]["task_id"],
            "source_path": lock["task"]["source_path"],
            "brief_digest": lock["task"]["brief_digest"],
            "archive_digest": lock["archive"]["archive_digest"],
            "selected_final_files": lock["review"]["selected_final_files"],
            "permitted_check_evidence_names": lock["review"][
                "permitted_check_evidence_names"
            ],
            "visible_check": lock["apparatus"]["visible_check"],
            "product_projection_exclusions": lock["apparatus"][
                "product_projection_exclusions"
            ],
            "evaluator_bundle_digest": lock["review"]["evaluator"][
                "bundle_digest"
            ],
        }
    )


def _write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def _apparatus(
    tmp_path: Path,
    *,
    mode: str = "valid",
    forced_session_id: str | None = None,
    timeout_milliseconds: int = 30_000,
) -> tuple[dict[str, Any], Path, Path, set[str]]:
    control = tmp_path / "control"
    evidence = tmp_path / "evidence"
    control.mkdir()
    evidence.mkdir()
    cli = tmp_path / "fake-codex"
    cli.write_bytes(FIXTURE_CLI.read_bytes())
    cli.chmod(0o755)
    schema_bytes = canonical_json_bytes(_schema())
    rubric_bytes = b"rubric"
    environment = {
        "FAKE_EXPECT_RUBRIC_SHA256": _digest_bytes(rubric_bytes),
        "FAKE_EXPECT_SCHEMA_SHA256": _digest_bytes(schema_bytes),
        "FAKE_REVIEW_MODE": mode,
        "HOME": (tmp_path / "home").as_posix(),
        "PATH": os.environ["PATH"],
        "TMPDIR": (tmp_path / "tmp").as_posix(),
    }
    if forced_session_id is not None:
        environment["FAKE_REVIEW_SESSION_ID"] = forced_session_id
    (tmp_path / "home").mkdir()
    (tmp_path / "tmp").mkdir()
    environment_path = tmp_path / "reviewer-environment.json"
    environment_path.write_bytes(canonical_json_bytes(environment))
    execution = _execution(
        cli,
        environment,
        timeout_milliseconds=timeout_milliseconds,
    )
    calibration_lock = {
        "schema_version": "calibration-lock.v1",
        "calibration_id": "calibration-1",
        "round": 1,
        "revision": 0,
        "base_identity": {
            "repository_identity": "fixture-repository",
            "revision_identity": "fixture-revision",
            "archive_digest": _digest("calibration-archive"),
            "product_manifest_digest": _digest("calibration-product"),
        },
        "product_projection_exclusions": [],
        "task": {"path": "task.md", "digest": _digest("calibration-task")},
        "reference_patch": {
            "path": "reference.patch",
            "digest": _digest("reference-patch"),
        },
        "rubric": {
            "path": "reviewers/rubric.md",
            "digest": _digest("rubric"),
        },
        "selected_final_files": ["candidate.py"],
        "evaluator": {
            "module_digest": _digest("calibration-evaluator"),
            "class": "fixture",
        },
        "oracle": {"digest": _digest("calibration-oracle")},
        "environment_identity": _digest("calibration-environment"),
        "reviewer_execution": execution,
        "visible_check": {
            "argv": ["python", "-m", "pytest"],
            "timeout_milliseconds": 30_000,
            "class": "FIXTURE_VISIBLE",
        },
        "hidden_evaluator_class": "FIXTURE_HIDDEN",
        "expected_contrast": {
            "base_visible": "FAIL",
            "reference_visible": "PASS",
            "base_hidden": "FAIL",
            "reference_hidden": "PASS",
        },
        "reviewer_ids": ["reviewer-1", "reviewer-2"],
        "package_ids": ["calibration-1", "calibration-2", "calibration-3"],
        "mapping_seed": "fixture-mapping-seed",
    }
    calibration_lock_bytes = canonical_json_bytes(calibration_lock)
    calibration_lock_digest = canonical_sha256(calibration_lock)
    calibration_sessions = [
        f"calibration-session-{index}" for index in range(6)
    ]
    seal = {
        "status": "PASSED",
        "calibration_id": calibration_lock["calibration_id"],
        "round": calibration_lock["round"],
        "revision": calibration_lock["revision"],
        "calibration_lock_digest": calibration_lock_digest,
        "rubric_digest": _digest("rubric"),
        "validation": {"result": "PASSED"},
        "review_bindings": [
            {
                "reviewer_id": f"reviewer-{index // 3 + 1}",
                "package_id": calibration_lock["package_ids"][index % 3],
                "session_id": session_id,
            }
            for index, session_id in enumerate(calibration_sessions)
        ],
    }
    config = {
        "schema_version": "lean-pilot-live-review-command.v1",
        "reviewer_execution": execution,
        "calibration_lock_path": "review/calibration-lock.json",
        "live_output_schema_path": "review/review-result.schema.json",
        "live_output_schema_digest": _digest_bytes(schema_bytes),
    }
    payloads = {
        "tasks/A1.md": b"task",
        "config/provider.json": b"provider",
        "config/prompts.json": b"prompts",
        "config/commands.json": b"commands",
        "config/treatments/direct.json": b"direct",
        "config/treatments/coordinator.json": b"coordinator",
        "config/treatments/orc.json": b"orc",
        "sources/treatment_driver.py": b"driver",
        "sources/task_loop.orc": b"orc workflow",
        "review/rubric.md": rubric_bytes,
        "review/calibration-seal.json": canonical_json_bytes(seal),
        "evaluation/config.json": b"evaluator config",
        "evaluation/evaluator.py": b"evaluator",
        "review/reviewer-command.json": canonical_json_bytes(config),
        "review/review-result.schema.json": schema_bytes,
        "review/calibration-lock.json": calibration_lock_bytes,
    }
    for path, data in payloads.items():
        _write(control / path, data)
    manifest = [
        {"path": path, "sha256": _digest_bytes(data)}
        for path, data in payloads.items()
    ]
    treatment_paths = [
        "tasks/A1.md",
        "config/provider.json",
        "config/prompts.json",
        "config/commands.json",
        "config/treatments/direct.json",
        "config/treatments/coordinator.json",
        "config/treatments/orc.json",
        "sources/treatment_driver.py",
        "sources/task_loop.orc",
    ]
    apparatus = {
        "control_root": control.as_posix(),
        "asset_manifest": manifest,
        "treatment_asset_paths": treatment_paths,
        "task_path": "tasks/A1.md",
        "provider_config_path": "config/provider.json",
        "prompt_config_path": "config/prompts.json",
        "command_config_path": "config/commands.json",
        "environment": {
            "identity": _digest("treatment-environment"),
            "allowed_keys": ["HOME", "PATH", "TMPDIR"],
            "credential_keys": [],
        },
        "visible_check": {
            "argv": ["python", "-m", "pytest", "-q"],
            "timeout_milliseconds": 120_000,
        },
        "product_projection_exclusions": [".git"],
        "maximum_start_skew_milliseconds": 500,
        "quiescence_grace_milliseconds": 2_000,
    }
    reviewer_paths = [
        "review/reviewer-command.json",
        "review/review-result.schema.json",
        "review/calibration-lock.json",
    ]
    evaluator_paths = ["evaluation/config.json", "evaluation/evaluator.py"]
    lock = {
        "record_kind": "pilot_lock.v1",
        "pilot_id": "pilot-1",
        "task": {
            "task_id": "A1",
            "source_path": "docs/tasks/task.md",
            "profile_digest": _digest("pending"),
            "brief_digest": _digest_bytes(payloads["tasks/A1.md"]),
        },
        "archive": {
            "repository_identity": "example/repository",
            "repository_root": (tmp_path / "repository").as_posix(),
            "revision_identity": f"commit:{'0' * 40}",
            "source_subtree_path": "examples/task",
            "source_tree_identity": f"git-tree:{'1' * 40}",
            "archive_digest": _digest("archive"),
        },
        "provider_policy": {
            "family": "codex-cli",
            "model": "gpt-5.5",
            "reasoning_effort": "high",
            "tool_policy": "codex_unrestricted_workspace",
            "timeout_milliseconds": 1_800_000,
            "currency": "USD",
        },
        "review": {
            "reviewer_ids": ["reviewer-1", "reviewer-2"],
            "disagreement_policy": "INDETERMINATE_ON_DISAGREEMENT",
            "selected_final_files": ["torch_port/entrypoint.py"],
            "permitted_check_evidence_names": [
                "check-stderr.txt",
                "check-stdout.txt",
                "hidden-evaluator.json",
            ],
            "rubric_path": "review/rubric.md",
            "rubric_digest": _digest_bytes(payloads["review/rubric.md"]),
            "calibration_evidence_path": "review/calibration-seal.json",
            "calibration_evidence_digest": _digest_bytes(
                payloads["review/calibration-seal.json"]
            ),
            "evaluator": {
                "config_path": "evaluation/config.json",
                "asset_paths": evaluator_paths,
                "bundle_digest": _bundle_digest(apparatus, evaluator_paths),
            },
            "reviewer_command": {
                "config_path": "review/reviewer-command.json",
                "asset_paths": reviewer_paths,
                "bundle_digest": _bundle_digest(apparatus, reviewer_paths),
            },
        },
        "apparatus": apparatus,
        "randomization_seed": "fixed-seed",
        "evidence_root": evidence.as_posix(),
        "valid_block_count": 3,
        "max_live_attempt_count": 5,
        "smoke_id": "smoke-1",
        "live_attempt_ids": [
            "live-1",
            "live-2",
            "live-3",
            "live-4",
            "live-5",
        ],
        "claim_level": "exploratory_controlled_task",
        "treatments": [],
    }
    for treatment, command, source_paths, bounds in (
        (
            "DIRECT",
            "config/treatments/direct.json",
            ["config/treatments/direct.json", "sources/treatment_driver.py"],
            (1, 1),
        ),
        (
            "COORDINATOR",
            "config/treatments/coordinator.json",
            [
                "config/treatments/coordinator.json",
                "sources/treatment_driver.py",
            ],
            (3, 9),
        ),
        (
            "ORC",
            "config/treatments/orc.json",
            [
                "config/treatments/orc.json",
                "sources/treatment_driver.py",
                "sources/task_loop.orc",
            ],
            (3, 9),
        ),
    ):
        lock["treatments"].append(
            {
                "treatment_id": treatment,
                "source_asset_paths": source_paths,
                "source_digest": _bundle_digest(apparatus, source_paths),
                "command_digest": dict(
                    (row["path"], row["sha256"]) for row in manifest
                )[command],
                "command_config_path": command,
                "provider_call_bounds": {
                    "minimum": bounds[0],
                    "maximum": bounds[1],
                },
            }
        )
    _refresh_profile(lock)
    return lock, control, environment_path, set(calibration_sessions)


def _package(tmp_path: Path, block_id: str) -> Path:
    root = tmp_path / "packages" / block_id
    labels = [f"candidate-{index}" for index in range(3)]
    payloads = {"task.md": b"task"}
    for label in labels:
        payloads[f"candidates/{label}/diff.patch"] = label.encode()
    rows = []
    for path, data in payloads.items():
        _write(root / path, data)
        rows.append(
            {
                "path": path,
                "mode": 0o644,
                "size": len(data),
                "sha256": _digest_bytes(data),
            }
        )
    manifest = {
        "package_id": block_id,
        "task_path": "task.md",
        "candidate_labels": labels,
        "files": rows,
    }
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return root


def _label_map(lock: dict[str, Any], block_id: str, package: Path) -> dict[str, Any]:
    from orchestrator.experiments._reporting_reviews import (
        _locked_label_assignments,
    )

    assignments = _locked_label_assignments(lock, block_id)
    manifest_digest = _digest_bytes((package / "manifest.json").read_bytes())
    return {
        "packages": {
            block_id: {
                "labels": {
                    label: treatment
                    for treatment, label in assignments.items()
                },
                "manifest_digest": manifest_digest,
            }
        }
    }


def _run(
    lock: dict[str, Any],
    control: Path,
    environment: Path,
    package: Path,
    reviewer: str,
    used: set[str],
    prior: list[dict[str, Any]],
) -> dict[str, Any]:
    return run_live_review_slot(
        lock=lock,
        block_id=package.name,
        package_root=package,
        reviewer_id=reviewer,
        control_root=control,
        evidence_root=Path(lock["evidence_root"]),
        reviewer_environment_path=environment,
        used_session_ids=used,
        prior_block_records=prior,
    )


def test_live_reviewer_runs_two_exact_bounded_slots_and_publishes_results(
    tmp_path: Path,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")

    apparatus = validate_live_reviewer_apparatus(
        lock=lock,
        control_root=control,
        reviewer_environment_path=environment,
    )
    first = _run(lock, control, environment, package, "reviewer-1", used, [])
    used.add(first["session_id"])
    second = _run(
        lock,
        control,
        environment,
        package,
        "reviewer-2",
        used,
        [first],
    )

    assert apparatus["reviewer_ids"] == ("reviewer-1", "reviewer-2")
    assert [item["reviewer_id"] for item in (first, second)] == [
        "reviewer-1",
        "reviewer-2",
    ]
    assert all(len(item["candidates"]) == 3 for item in (first, second))
    assert all(len(item["pairwise_results"]) == 3 for item in (first, second))
    intent = json.loads(
        (
            Path(lock["evidence_root"])
            / "live-1"
            / "reviews"
            / "reviewer-1"
            / "launch-intent.json"
        ).read_text()
    )
    command = intent["command"]
    assert intent["pilot_lock_digest"] == canonical_sha256(lock)
    assert command[:5] == [
        apparatus["cli_entry"].as_posix(),
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
    ]
    assert "--strict-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--model") + 1] == "gpt-5.5"
    assert (
        command[command.index("--config") + 1]
        == 'model_reasoning_effort="high"'
    )
    assert command[-1] == "-"
    prompt = intent["prompt_contract"]
    assert prompt["output_contract"]["candidate_count"] == 3
    assert prompt["output_contract"]["pair_count"] == 3
    assert set(prompt["output_contract"]["dimensions"]) == set(DIMENSIONS)
    assert set(prompt["inspection_contract"]["package_files"]) == {
        row["path"]
        for row in json.loads(
            (package / "manifest.json").read_text(encoding="utf-8")
        )["files"]
    } | {"manifest.json"}
    citation_contract = prompt["inspection_contract"]["citation_contract"]
    assert set(citation_contract["citable_files"]) == {
        row["path"]
        for row in json.loads(
            (package / "manifest.json").read_text(encoding="utf-8")
        )["files"]
    }
    assert citation_contract["navigation_only_files"] == ["manifest.json"]
    assert citation_contract["allowed_forms"] == [
        "PATH",
        "PATH:LINE",
        "PATH:START-END",
    ]
    assert citation_contract["line_numbering"] == "ONE_BASED_INCLUSIVE"
    assert citation_contract["exact_path_precedence"] is True
    assert (
        prompt["inspection_contract"]["task_path"]
        == json.loads(
            (package / "manifest.json").read_text(encoding="utf-8")
        )["task_path"]
    )


@pytest.mark.parametrize("mutation", ["schema", "rubric"])
def test_live_reviewer_uses_verified_staged_bytes_after_source_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    schema_bytes = (control / "review/review-result.schema.json").read_bytes()
    rubric_bytes = (control / "review/rubric.md").read_bytes()
    original_validate = review_execution.validate_live_reviewer_apparatus

    def validate_then_mutate(**kwargs: object) -> dict[str, object]:
        apparatus = original_validate(**kwargs)
        relative = (
            "review/review-result.schema.json"
            if mutation == "schema"
            else "review/rubric.md"
        )
        (control / relative).write_bytes(b"post-validation mutation")
        return apparatus

    monkeypatch.setattr(
        review_execution,
        "validate_live_reviewer_apparatus",
        validate_then_mutate,
    )

    record = _run(
        lock,
        control,
        environment,
        package,
        "reviewer-1",
        used,
        [],
    )

    evidence = Path(lock["evidence_root"])
    intent = json.loads(
        (
            evidence
            / "live-1/reviews/reviewer-1/launch-intent.json"
        ).read_text(encoding="utf-8")
    )
    schema_path = Path(
        intent["command"][intent["command"].index("--output-schema") + 1]
    )
    rubric_path = Path(
        intent["prompt_contract"]["inspection_contract"]["rubric_path"]
    )
    assert record["reviewer_id"] == "reviewer-1"
    assert schema_path == evidence / STAGED_SCHEMA
    assert rubric_path == evidence / STAGED_RUBRIC
    assert schema_path.read_bytes() == schema_bytes
    assert rubric_path.read_bytes() == rubric_bytes


def test_live_reviewer_completes_partial_exact_staging_before_intent(
    tmp_path: Path,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    evidence = Path(lock["evidence_root"])
    staged_schema = evidence / STAGED_SCHEMA
    staged_schema.parent.mkdir(parents=True)
    staged_schema.write_bytes(
        (control / "review/review-result.schema.json").read_bytes()
    )
    staged_schema.chmod(0o644)

    record = _run(
        lock,
        control,
        environment,
        package,
        "reviewer-1",
        used,
        [],
    )

    assert record["reviewer_id"] == "reviewer-1"
    assert staged_schema.read_bytes() == (
        control / "review/review-result.schema.json"
    ).read_bytes()
    assert (evidence / STAGED_RUBRIC).read_bytes() == (
        control / "review/rubric.md"
    ).read_bytes()


@pytest.mark.parametrize("relative", [STAGED_SCHEMA, STAGED_RUBRIC])
def test_live_reviewer_rejects_tampered_staged_asset_before_intent(
    tmp_path: Path,
    relative: Path,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    evidence = Path(lock["evidence_root"])
    staged = evidence / relative
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"tampered staged bytes")

    with pytest.raises(
        EvaluationError,
        match="live_reviewer_staged_asset_invalid",
    ) as caught:
        _run(
            lock,
            control,
            environment,
            package,
            "reviewer-1",
            used,
            [],
        )

    assert caught.value.code == "live_reviewer_staged_asset_invalid"
    assert not (
        evidence / "live-1/reviews/reviewer-1/launch-intent.json"
    ).exists()


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("schema", "live_reviewer_schema_invalid"),
        ("cli", "live_reviewer_execution_invalid"),
        ("environment", "live_reviewer_environment_invalid"),
    ],
)
def test_live_reviewer_rejects_schema_cli_or_environment_drift_before_intent(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    if mutation == "schema":
        (control / "review/review-result.schema.json").write_text("{}")
    elif mutation == "cli":
        Path(
            json.loads(
                (control / "review/reviewer-command.json").read_text()
            )["reviewer_execution"]["cli"]["entry_path"]
        ).write_text("#!/bin/sh\nexit 0\n")
    else:
        value = json.loads(environment.read_text())
        value["HOME"] = "/different"
        environment.write_bytes(canonical_json_bytes(value))

    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert caught.value.code == code
    assert not (
        Path(lock["evidence_root"])
        / "live-1"
        / "reviews"
        / "reviewer-1"
        / "launch-intent.json"
    ).exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-required",
        "weakened-additional-properties",
        "altered-assessment-enum",
        "altered-guess-enum",
        "altered-outcome-enum",
        "missing-nested-type",
        "weakened-citation-cardinality",
        "weakened-citation-item",
        "weakened-rationale",
    ],
)
def test_live_reviewer_rejects_rebound_schema_contract_drift_before_intent(
    tmp_path: Path,
    mutation: str,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    schema = _schema()
    candidate = schema["properties"]["candidates"]["items"]
    assessment = candidate["properties"]["dimension_assessments"]["items"]
    pair = schema["properties"]["pairwise_results"]["items"]
    if mutation == "missing-required":
        assessment["required"].remove("rationale")
    elif mutation == "weakened-additional-properties":
        candidate["additionalProperties"] = True
    elif mutation == "altered-assessment-enum":
        assessment["properties"]["assessment"]["enum"] = ["PASS", "FAIL"]
    elif mutation == "altered-guess-enum":
        candidate["properties"]["sealed_treatment_guess"]["enum"].append(
            "UNBOUND"
        )
    elif mutation == "altered-outcome-enum":
        pair["properties"]["outcome"]["enum"].append("SKIP")
    elif mutation == "missing-nested-type":
        pair["properties"]["candidate_a_label"].pop("type")
    elif mutation == "weakened-citation-cardinality":
        pair["properties"]["evidence_citations"]["minItems"] = 0
    elif mutation == "weakened-citation-item":
        assessment["properties"]["evidence_citations"]["items"][
            "minLength"
        ] = 0
    else:
        pair["properties"]["rationale"]["minLength"] = 0
    _rebind_live_schema(lock=lock, control=control, schema=schema)

    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert caught.value.code == "live_reviewer_schema_invalid"
    assert not (
        Path(lock["evidence_root"])
        / "live-1"
        / "reviews"
        / "reviewer-1"
        / "launch-intent.json"
    ).exists()


def test_live_reviewer_rejects_coherently_rebound_calibration_shape_drift(
    tmp_path: Path,
) -> None:
    lock, control, environment, _used = _apparatus(tmp_path)
    calibration_path = control / "review/calibration-lock.json"
    calibration = json.loads(calibration_path.read_text())
    calibration["unexpected"] = True
    calibration_path.write_bytes(canonical_json_bytes(calibration))
    seal_path = control / "review/calibration-seal.json"
    seal = json.loads(seal_path.read_text())
    seal["calibration_lock_digest"] = canonical_sha256(calibration)
    seal_path.write_bytes(canonical_json_bytes(seal))
    manifest = {
        row["path"]: row for row in lock["apparatus"]["asset_manifest"]
    }
    manifest["review/calibration-lock.json"]["sha256"] = _digest_bytes(
        calibration_path.read_bytes()
    )
    manifest["review/calibration-seal.json"]["sha256"] = _digest_bytes(
        seal_path.read_bytes()
    )
    lock["review"]["calibration_evidence_digest"] = manifest[
        "review/calibration-seal.json"
    ]["sha256"]
    lock["review"]["reviewer_command"]["bundle_digest"] = _bundle_digest(
        lock["apparatus"],
        lock["review"]["reviewer_command"]["asset_paths"],
    )

    with pytest.raises(EvaluationError) as caught:
        validate_live_reviewer_apparatus(
            lock=lock,
            control_root=control,
            reviewer_environment_path=environment,
        )

    assert caught.value.code == "live_reviewer_execution_invalid"


def test_live_reviewer_accepts_canonical_calibration_lock_with_single_lf(
    tmp_path: Path,
) -> None:
    lock, control, environment, _used = _apparatus(tmp_path)
    calibration_path = control / "review/calibration-lock.json"
    canonical = calibration_path.read_bytes()
    _rebind_calibration_lock_bytes(
        lock=lock,
        control=control,
        data=canonical + b"\n",
    )

    apparatus = validate_live_reviewer_apparatus(
        lock=lock,
        control_root=control,
        reviewer_environment_path=environment,
    )

    assert apparatus["calibration_lock_path"] == calibration_path


@pytest.mark.parametrize(
    "calibration_bytes",
    [
        lambda canonical: canonical + b" ",
        lambda canonical: canonical + b"\t",
        lambda canonical: canonical + b"\r\n",
        lambda canonical: canonical + b"\n\n",
        lambda canonical: b" " + canonical,
    ],
)
def test_live_reviewer_rejects_other_calibration_lock_whitespace(
    tmp_path: Path,
    calibration_bytes: Any,
) -> None:
    lock, control, environment, _used = _apparatus(tmp_path)
    canonical = (control / "review/calibration-lock.json").read_bytes()
    _rebind_calibration_lock_bytes(
        lock=lock,
        control=control,
        data=calibration_bytes(canonical),
    )

    with pytest.raises(EvaluationError) as caught:
        validate_live_reviewer_apparatus(
            lock=lock,
            control_root=control,
            reviewer_environment_path=environment,
        )

    assert caught.value.code == "live_reviewer_execution_invalid"


def test_live_reviewer_rejects_passing_seal_with_wrong_reviewer_matrix(
    tmp_path: Path,
) -> None:
    lock, control, environment, _used = _apparatus(tmp_path)
    seal_path = control / "review/calibration-seal.json"
    seal = json.loads(seal_path.read_text())
    seal["review_bindings"][0]["reviewer_id"] = "foreign-reviewer"
    seal_path.write_bytes(canonical_json_bytes(seal))
    manifest = {
        row["path"]: row for row in lock["apparatus"]["asset_manifest"]
    }
    digest = _digest_bytes(seal_path.read_bytes())
    manifest["review/calibration-seal.json"]["sha256"] = digest
    lock["review"]["calibration_evidence_digest"] = digest

    with pytest.raises(EvaluationError) as caught:
        validate_live_reviewer_apparatus(
            lock=lock,
            control_root=control,
            reviewer_environment_path=environment,
        )

    assert caught.value.code == "live_reviewer_calibration_invalid"


def test_live_reviewer_rejects_undeclared_package_node_before_intent(
    tmp_path: Path,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    (package / "undeclared.txt").write_text("must not be reviewer-visible")

    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert caught.value.code == "live_reviewer_package_invalid"
    assert not (
        Path(lock["evidence_root"])
        / "live-1"
        / "reviews"
        / "reviewer-1"
        / "launch-intent.json"
    ).exists()


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("calibration-session", "review_session_reused"),
        ("prior-live-session", "review_session_reused"),
        ("duplicate-reviewer", "review_reviewer_reused"),
    ],
)
def test_live_reviewer_rejects_session_or_reviewer_reuse(
    tmp_path: Path,
    case: str,
    code: str,
) -> None:
    forced = (
        "calibration-session-0"
        if case == "calibration-session"
        else "already-used-live-session"
    )
    lock, control, environment, used = _apparatus(
        tmp_path,
        forced_session_id=forced,
    )
    package = _package(tmp_path, "live-1")
    prior: list[dict[str, Any]] = []
    if case == "prior-live-session":
        used.add(forced)
    elif case == "duplicate-reviewer":
        prior.append(
            {
                "reviewer_id": "reviewer-1",
                "session_id": "different-prior-session",
            }
        )

    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, prior)

    assert caught.value.code == code
    assert not (
        Path(lock["evidence_root"])
        / "live-1"
        / "reviews"
        / "reviewer-1"
        / "review-result.json"
    ).exists()


@pytest.mark.parametrize("mode", ["partial", "nonzero", "ambiguous"])
def test_started_reviewer_failure_consumes_slot_without_relaunch(
    tmp_path: Path,
    mode: str,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path, mode=mode)
    package = _package(tmp_path, "live-1")

    with pytest.raises(EvaluationError):
        _run(lock, control, environment, package, "reviewer-1", used, [])
    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert caught.value.code == "live_reviewer_slot_consumed"
    slot = (
        Path(lock["evidence_root"]) / "live-1" / "reviews" / "reviewer-1"
    )
    assert (slot / "launch-intent.json").is_file()
    assert not (slot / "review-result.json").exists()


def test_complete_transport_finalizes_provider_free_after_publication_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    real_run_process = review_execution._run_process
    real_publish = review_execution._publish
    launches = 0
    fail_once = True

    def counted_run_process(**kwargs: object) -> object:
        nonlocal launches
        launches += 1
        return real_run_process(**kwargs)

    def crash_before_review(
        root: Path,
        relative: str,
        value: bytes,
        *,
        code: str,
    ) -> None:
        nonlocal fail_once
        if relative.endswith("/review-result.json") and fail_once:
            fail_once = False
            raise EvaluationError("injected_post_transport_crash")
        real_publish(root, relative, value, code=code)

    monkeypatch.setattr(review_execution, "_run_process", counted_run_process)
    monkeypatch.setattr(review_execution, "_publish", crash_before_review)
    with pytest.raises(EvaluationError) as first:
        _run(lock, control, environment, package, "reviewer-1", used, [])
    assert first.value.code == "injected_post_transport_crash"
    slot = (
        Path(lock["evidence_root"]) / "live-1" / "reviews" / "reviewer-1"
    )
    assert (slot / "transport-completion.json").is_file()
    assert not (slot / "review-result.json").exists()

    recovered = _run(
        lock,
        control,
        environment,
        package,
        "reviewer-1",
        used,
        [],
    )

    assert launches == 1
    assert recovered["reviewer_id"] == "reviewer-1"
    assert (slot / "review-result.json").is_file()


def test_mismatched_retained_transport_fails_closed_without_relaunch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    real_run_process = review_execution._run_process
    real_publish = review_execution._publish
    launches = 0

    def counted_run_process(**kwargs: object) -> object:
        nonlocal launches
        launches += 1
        return real_run_process(**kwargs)

    def always_crash(
        root: Path,
        relative: str,
        value: bytes,
        *,
        code: str,
    ) -> None:
        if relative.endswith("/review-result.json"):
            raise EvaluationError("injected_post_transport_crash")
        real_publish(root, relative, value, code=code)

    monkeypatch.setattr(review_execution, "_run_process", counted_run_process)
    monkeypatch.setattr(review_execution, "_publish", always_crash)
    with pytest.raises(EvaluationError):
        _run(lock, control, environment, package, "reviewer-1", used, [])
    slot = (
        Path(lock["evidence_root"]) / "live-1" / "reviews" / "reviewer-1"
    )
    (slot / "stdout.jsonl").write_bytes(b"rewritten")

    with pytest.raises(EvaluationError) as recovered:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert recovered.value.code == "live_reviewer_transport_invalid"
    assert launches == 1
    assert not (slot / "review-result.json").exists()


@pytest.mark.parametrize(
    "mode",
    ["duplicate-first-dimension", "duplicate-last-dimension"],
)
def test_dimension_duplicate_and_semantic_omission_reject_at_strict_ingest(
    tmp_path: Path,
    mode: str,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path, mode=mode)
    package = _package(tmp_path, "live-1")

    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert caught.value.code == "review_record_invalid"
    slot = (
        Path(lock["evidence_root"]) / "live-1" / "reviews" / "reviewer-1"
    )
    assert (slot / "last-message.json").is_file()
    assert not (slot / "review-result.json").exists()


def test_launch_intent_collision_prevents_provider_start(tmp_path: Path) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    intent = (
        Path(lock["evidence_root"])
        / "live-1"
        / "reviews"
        / "reviewer-1"
        / "launch-intent.json"
    )
    _write(intent, b"occupied")

    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert caught.value.code == "live_reviewer_slot_consumed"
    assert intent.read_bytes() == b"occupied"


def test_other_slot_collision_rejects_before_intent_without_following_symlink(
    tmp_path: Path,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    slot = (
        Path(lock["evidence_root"]) / "live-1" / "reviews" / "reviewer-1"
    )
    slot.mkdir(parents=True)
    external = tmp_path / "external"
    external.write_text("unchanged")
    (slot / "last-message.json").symlink_to(external)

    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert caught.value.code == "live_reviewer_slot_invalid"
    assert external.read_text() == "unchanged"
    assert not (slot / "launch-intent.json").exists()


def test_timeout_is_interpreted_in_milliseconds_and_consumes_slot(
    tmp_path: Path,
) -> None:
    lock, control, environment, used = _apparatus(
        tmp_path,
        mode="hang",
        timeout_milliseconds=50,
    )
    package = _package(tmp_path, "live-1")

    with pytest.raises(EvaluationError) as caught:
        _run(lock, control, environment, package, "reviewer-1", used, [])

    assert caught.value.code == "live_reviewer_transport_invalid"
    with pytest.raises(EvaluationError) as repeated:
        _run(lock, control, environment, package, "reviewer-1", used, [])
    assert repeated.value.code == "live_reviewer_slot_consumed"


def test_review_and_unblinding_bindings_are_canonical_and_ordered(
    tmp_path: Path,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    packages = {
        block_id: _package(tmp_path, block_id)
        for block_id in ("live-2", "live-1")
    }
    reviews: list[dict[str, Any]] = []
    for block_id in ("live-1", "live-2"):
        block_prior: list[dict[str, Any]] = []
        for reviewer in ("reviewer-1", "reviewer-2"):
            review = _run(
                lock,
                control,
                environment,
                packages[block_id],
                reviewer,
                used,
                block_prior,
            )
            used.add(review["session_id"])
            block_prior.append(review)
            reviews.append(review)
        label_path = (
            Path(lock["evidence_root"]) / "label-maps" / f"{block_id}.json"
        )
        _write(
            label_path,
            canonical_json_bytes(
                _label_map(lock, block_id, packages[block_id])
            ),
        )

    review_path = publish_review_bindings(
        lock=lock,
        block_packages=packages,
        reviews=list(reversed(reviews)),
        evidence_root=Path(lock["evidence_root"]),
    )
    unblind_path = publish_unblinding_bindings(
        lock=lock,
        block_packages=packages,
        evidence_root=Path(lock["evidence_root"]),
        review_bindings_path=review_path,
    )

    review_rows = json.loads(review_path.read_text())
    assert [(row["block_id"], row["reviewer_id"]) for row in review_rows] == [
        ("live-1", "reviewer-1"),
        ("live-1", "reviewer-2"),
        ("live-2", "reviewer-1"),
        ("live-2", "reviewer-2"),
    ]
    unblind_rows = json.loads(unblind_path.read_text())
    assert [(row["block_id"], row["treatment_id"]) for row in unblind_rows] == [
        (block_id, treatment)
        for block_id in ("live-1", "live-2")
        for treatment in ("DIRECT", "COORDINATOR", "ORC")
    ]
    assert review_path.read_bytes() == canonical_json_bytes(review_rows)
    assert unblind_path.read_bytes() == canonical_json_bytes(unblind_rows)


def test_unblinding_does_not_read_label_maps_until_all_reviews_are_sealed(
    tmp_path: Path,
) -> None:
    lock, _control, _environment, _used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    label_path = (
        Path(lock["evidence_root"]) / "label-maps" / "live-1.json"
    )
    _write(label_path, b"this must not be parsed")
    incomplete = Path(lock["evidence_root"]) / "review-bindings.json"
    incomplete.write_bytes(canonical_json_bytes([]))

    with pytest.raises(EvaluationError) as caught:
        publish_unblinding_bindings(
            lock=lock,
            block_packages={"live-1": package},
            evidence_root=Path(lock["evidence_root"]),
            review_bindings_path=incomplete,
        )

    assert caught.value.code == "review_bindings_invalid"


def test_unblinding_rejects_symlinked_label_map_after_review_seal(
    tmp_path: Path,
) -> None:
    lock, control, environment, used = _apparatus(tmp_path)
    package = _package(tmp_path, "live-1")
    reviews: list[dict[str, Any]] = []
    for reviewer in ("reviewer-1", "reviewer-2"):
        review = _run(
            lock,
            control,
            environment,
            package,
            reviewer,
            used,
            reviews,
        )
        used.add(review["session_id"])
        reviews.append(review)
    evidence = Path(lock["evidence_root"])
    review_path = publish_review_bindings(
        lock=lock,
        block_packages={"live-1": package},
        reviews=reviews,
        evidence_root=evidence,
    )
    external = tmp_path / "external-label-map.json"
    external.write_bytes(
        canonical_json_bytes(_label_map(lock, "live-1", package))
    )
    label_path = evidence / "label-maps/live-1.json"
    label_path.parent.mkdir()
    label_path.symlink_to(external)

    with pytest.raises(EvaluationError) as caught:
        publish_unblinding_bindings(
            lock=lock,
            block_packages={"live-1": package},
            evidence_root=evidence,
            review_bindings_path=review_path,
        )

    assert caught.value.code == "unblinding_bindings_invalid"
    assert external.read_bytes() == canonical_json_bytes(
        _label_map(lock, "live-1", package)
    )


def test_zero_valid_blocks_publish_canonical_empty_binding_sets(
    tmp_path: Path,
) -> None:
    lock, _control, _environment, _used = _apparatus(tmp_path)
    evidence = Path(lock["evidence_root"])

    review_path = publish_review_bindings(
        lock=lock,
        block_packages={},
        reviews=[],
        evidence_root=evidence,
    )
    unblind_path = publish_unblinding_bindings(
        lock=lock,
        block_packages={},
        evidence_root=evidence,
        review_bindings_path=review_path,
    )

    assert review_path.read_bytes() == b"[]"
    assert unblind_path.read_bytes() == b"[]"


def test_binding_publication_rejects_foreign_block_even_with_no_reviews(
    tmp_path: Path,
) -> None:
    lock, _control, _environment, _used = _apparatus(tmp_path)

    with pytest.raises(EvaluationError) as caught:
        publish_review_bindings(
            lock=lock,
            block_packages={"foreign": _package(tmp_path, "foreign")},
            reviews=[],
            evidence_root=Path(lock["evidence_root"]),
        )

    assert caught.value.code == "review_bindings_invalid"


def test_tracked_live_command_binds_calibrated_execution_and_schema_bytes() -> None:
    root = Path(__file__).parents[2]
    config_path = (
        root
        / "experiments/orc_effectiveness/lean_pilot/reviewers"
        / "live-review-command.json"
    )
    schema_path = config_path.with_name("live-review-output.schema.json")
    calibration_path = (
        root
        / "experiments/orc_effectiveness/lean_pilot/calibration"
        / "calibration-lock.json"
    )
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))

    assert config_bytes in {
        canonical_json_bytes(config),
        canonical_json_bytes(config) + b"\n",
    }
    assert config["reviewer_execution"] == calibration["reviewer_execution"]
    assert config["live_output_schema_digest"] == _digest_bytes(
        schema_path.read_bytes()
    )
    assert config["live_output_schema_path"] == "review/review-result.schema.json"

    def keywords(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value).union(
                *(keywords(item) for item in value.values()),
            )
        if isinstance(value, list):
            return set().union(*(keywords(item) for item in value))
        return set()

    assert not {
        "contains",
        "minContains",
        "maxContains",
        "uniqueItems",
    }.intersection(keywords(json.loads(schema_path.read_text())))
