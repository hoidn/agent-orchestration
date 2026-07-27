from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from orchestrator.experiments import workspace
from orchestrator.experiments.contracts import (
    canonical_json_bytes,
    canonical_sha256,
    validate_record,
)
from orchestrator.experiments._pilot_prepare import (
    PilotPreparationError,
    prepare_pilot,
)
from orchestrator.experiments._pilot_prepare_validation import _shape


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _canonical_write(path: Path, value: object) -> bytes:
    data = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _bundle_digest(paths: list[str], by_path: dict[str, str]) -> str:
    return canonical_sha256(
        [
            {"path": path, "sha256": by_path[path]}
            for path in sorted(paths, key=lambda item: item.encode())
        ]
    )


def _fixture(tmp_path: Path) -> dict[str, Any]:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    _git(repo, "init", "-q")

    reviewer_cli = (tmp_path / "reviewer-cli").resolve()
    reviewer_cli.write_bytes(b"fixture reviewer\n")
    reviewer_execution = {
        "provider_family": "codex-cli",
        "model": "fixture-model",
        "reasoning_effort": "high",
        "tool_policy": "read-only-package",
        "timeout_milliseconds": 900_000,
        "cli": {
            "entry_path": reviewer_cli.as_posix(),
            "entry_sha256": _sha256(reviewer_cli.read_bytes()),
            "version": "fixture-cli 1",
        },
        "environment": {
            "identity": _sha256(b"reviewer environment"),
            "allowed_keys": ["CODEX_HOME", "HOME", "PATH", "TMPDIR"],
            "credential_keys": ["CODEX_HOME"],
        },
        "invocation_payload_schema_digest": _sha256(b"invocation schema"),
    }
    rubric = b"Judge the three candidates.\n"
    calibration_lock = {
        "schema_version": "calibration-lock.v1",
        "calibration_id": "fixture-calibration",
        "round": 1,
        "revision": 0,
        "package_ids": [
            "calibration-direction-1",
            "calibration-direction-2",
            "calibration-identity",
        ],
        "reviewer_ids": ["calibration-reviewer-01", "calibration-reviewer-02"],
        "rubric": {"path": "reviewers/rubric.md", "digest": _sha256(rubric)},
        "reviewer_execution": reviewer_execution,
    }
    calibration_seal = {
        "calibration_id": "fixture-calibration",
        "calibration_lock_digest": canonical_sha256(calibration_lock),
        "round": 1,
        "revision": 0,
        "rubric_digest": _sha256(rubric),
        "status": "PASSED",
        "validation": {
            "result": "PASSED",
            "validator": "orchestrator.experiments.evaluation.validate_calibration",
        },
        "review_bindings": [
            {
                "package_id": package_id,
                "reviewer_id": reviewer_id,
                "session_id": f"session-{package_id}-{reviewer_id}",
                "outcome": outcome,
            }
            for reviewer_id in calibration_lock["reviewer_ids"]
            for package_id, outcome in (
                ("calibration-direction-1", "A"),
                ("calibration-direction-2", "B"),
                ("calibration-identity", "TIE"),
            )
        ],
    }
    seal_path = (tmp_path / "calibration-seal.json").resolve()
    seal_bytes = _canonical_write(seal_path, calibration_seal)

    provider_policy = {
        "family": "codex-cli",
        "model": "fixture-model",
        "reasoning_effort": "high",
        "tool_policy": "codex_unrestricted_workspace",
        "timeout_milliseconds": 1_800_000,
        "currency": "USD",
    }
    policy_digest = canonical_sha256(provider_policy)
    environment = {
        "identity": _sha256(b"treatment environment"),
        "allowed_keys": [
            "CODEX_HOME",
            "HOME",
            "PATH",
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONPATH",
            "PYTHONUNBUFFERED",
            "TMPDIR",
        ],
        "credential_keys": ["CODEX_HOME"],
    }
    treatment_config = {
        "argv": [
            "python",
            "-B",
            "-P",
            "{apparatus_root}/treatment_driver.py",
        ],
        "environment": {
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "{treatment_runtime_root}",
            "PYTHONUNBUFFERED": "1",
        },
        "environment_identity": environment["identity"],
        "provider_policy_digest": policy_digest,
        "timeout_milliseconds": 18_000_000,
    }
    live_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
    }
    evaluator_paths = [
        "evaluation/config.json",
        "orchestrator/demo/evaluators/nanobragg_entrypoint.py",
        "orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/cases.json",
    ]
    evaluator_config = {
        "schema_version": "lean-pilot-hidden-evaluator.v1",
        "module_path": evaluator_paths[1],
        "runtime_asset_paths": evaluator_paths[1:],
        "timeout_milliseconds": 300_000,
        "output_contract": {
            "format": "canonical-json-object",
            "required_keys": [
                "failure_categories",
                "soft_quality",
                "summary",
                "verdict",
            ],
            "verdicts": ["PASS", "FAIL"],
        },
    }
    reviewer_config = {
        "schema_version": "lean-pilot-live-review-command.v1",
        "reviewer_execution": reviewer_execution,
        "calibration_lock_path": "review/calibration-lock.json",
        "live_output_schema_path": "review/review-result.schema.json",
        "live_output_schema_digest": canonical_sha256(live_schema),
    }

    task_bytes = b"Implement the fixture task.\n"
    source_values: dict[str, bytes] = {
        "scripts/treatment_driver.py": b"print('driver')\n",
        "workflows/task_loop.orc": b"(workflow task-loop)\n",
        "workflows/prompts/discover.md": b"Discover.\n",
        "control/providers.json": canonical_json_bytes(
            {"providers.repository-task.discover": "fixture-provider"}
        ),
        "control/prompts.json": canonical_json_bytes(
            {"prompts.repository-task.discover": {"asset_file": "prompts/discover.md"}}
        ),
        "control/commands.json": canonical_json_bytes(
            {
                "pilot_visible_check": {
                    "kind": "external_tool",
                    "stable_command": ["python"],
                }
            }
        ),
        "control/runtime-control.json": canonical_json_bytes(
            {
                "product_exclusions": [".orchestrate"],
                "visible_check": {
                    "argv": ["python", "-m", "pytest", "-q"],
                    "timeout_seconds": 300,
                },
            }
        ),
        "tasks/a1.md": task_bytes,
        "treatments/direct.json": canonical_json_bytes(treatment_config),
        "treatments/coordinator.json": canonical_json_bytes(treatment_config),
        "treatments/orc.json": canonical_json_bytes(treatment_config),
        "reviewers/rubric.md": rubric,
        "calibration/calibration-lock.json": canonical_json_bytes(calibration_lock),
        "evaluation/config.json": canonical_json_bytes(evaluator_config),
        "orchestrator/demo/evaluators/nanobragg_entrypoint.py": b"# evaluator\n",
        "orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/cases.json": b"{}",
        "reviewers/live-review-command.json": canonical_json_bytes(reviewer_config),
        "reviewers/live-review-output.schema.json": canonical_json_bytes(live_schema),
    }
    for source_path, data in source_values.items():
        destination = repo / source_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    benchmark = repo / "benchmark"
    benchmark.mkdir()
    (benchmark / "task.md").write_bytes(task_bytes)
    (benchmark / "source.py").write_text("VALUE = 1\n", encoding="utf-8")

    _git(repo, "add", "--all")
    _git(
        repo,
        "-c",
        "user.name=Lean Pilot Test",
        "-c",
        "user.email=lean-pilot@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "fixture",
    )
    commit = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", f"{commit}:benchmark")
    _git(repo, "checkout", "--detach", "-q", commit)
    archive_probe = tmp_path / "archive-probe"
    archive_digest = workspace.materialize_git_archive(
        repo, f"{commit}:benchmark", archive_probe
    ).digest

    destination_by_source = {
        "scripts/treatment_driver.py": "treatment_driver.py",
        "workflows/task_loop.orc": "task_loop.orc",
        "workflows/prompts/discover.md": "prompts/discover.md",
        "control/providers.json": "providers.json",
        "control/prompts.json": "prompts.json",
        "control/commands.json": "commands.json",
        "control/runtime-control.json": "runtime-control.json",
        "tasks/a1.md": "task.md",
        "treatments/direct.json": "treatments/direct.json",
        "treatments/coordinator.json": "treatments/coordinator.json",
        "treatments/orc.json": "treatments/orc.json",
        "reviewers/rubric.md": "review/rubric.md",
        "calibration/calibration-lock.json": "review/calibration-lock.json",
        "evaluation/config.json": "evaluation/config.json",
        "orchestrator/demo/evaluators/nanobragg_entrypoint.py": evaluator_paths[1],
        "orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/cases.json": evaluator_paths[2],
        "reviewers/live-review-command.json": "review/reviewer-command.json",
        "reviewers/live-review-output.schema.json": "review/review-result.schema.json",
    }
    sources = [
        {
            "source_kind": "repository",
            "source_path": source_path,
            "destination_path": destination,
            "sha256": _sha256(source_values[source_path]),
        }
        for source_path, destination in destination_by_source.items()
    ]
    sources.append(
        {
            "source_kind": "external_calibration_seal",
            "destination_path": "review/calibration-seal.json",
            "sha256": _sha256(seal_bytes),
        }
    )
    by_path = {row["destination_path"]: row["sha256"] for row in sources}
    treatment_assets = [
        "treatment_driver.py",
        "task_loop.orc",
        "prompts/discover.md",
        "providers.json",
        "prompts.json",
        "commands.json",
        "runtime-control.json",
        "task.md",
        "treatments/direct.json",
        "treatments/coordinator.json",
        "treatments/orc.json",
    ]
    treatments = [
        {
            "treatment_id": "DIRECT",
            "command_config_path": "treatments/direct.json",
            "source_asset_paths": [
                "treatment_driver.py",
                "treatments/direct.json",
            ],
            "provider_call_bounds": {"minimum": 1, "maximum": 1},
        },
        {
            "treatment_id": "COORDINATOR",
            "command_config_path": "treatments/coordinator.json",
            "source_asset_paths": [
                "treatment_driver.py",
                "treatments/coordinator.json",
            ],
            "provider_call_bounds": {"minimum": 3, "maximum": 9},
        },
        {
            "treatment_id": "ORC",
            "command_config_path": "treatments/orc.json",
            "source_asset_paths": [
                "task_loop.orc",
                "treatment_driver.py",
                "treatments/orc.json",
            ],
            "provider_call_bounds": {"minimum": 3, "maximum": 9},
        },
    ]
    reviewer_paths = [
        "review/calibration-lock.json",
        "review/reviewer-command.json",
        "review/review-result.schema.json",
    ]
    review = {
        "reviewer_ids": calibration_lock["reviewer_ids"],
        "disagreement_policy": "INDETERMINATE_ON_DISAGREEMENT",
        "selected_final_files": ["torch_port/entrypoint.py"],
        "permitted_check_evidence_names": [
            "check-stderr.txt",
            "check-stdout.txt",
            "hidden-evaluator.json",
        ],
        "rubric_path": "review/rubric.md",
        "calibration_evidence_path": "review/calibration-seal.json",
        "evaluator": {
            "config_path": "evaluation/config.json",
            "asset_paths": evaluator_paths,
        },
        "reviewer_command": {
            "config_path": "review/reviewer-command.json",
            "asset_paths": reviewer_paths,
        },
    }
    apparatus = {
        "treatment_asset_paths": treatment_assets,
        "task_path": "task.md",
        "provider_config_path": "providers.json",
        "prompt_config_path": "prompts.json",
        "command_config_path": "commands.json",
        "environment": environment,
        "visible_check": {
            "argv": ["python", "-m", "pytest", "-q"],
            "timeout_milliseconds": 300_000,
        },
        "product_projection_exclusions": [".orchestrate"],
        "maximum_start_skew_milliseconds": 2_000,
        "quiescence_grace_milliseconds": 10_000,
    }
    expected_source_digests = {
        row["treatment_id"]: _bundle_digest(
            row["source_asset_paths"], by_path
        )
        for row in treatments
    }
    evaluator_digest = _bundle_digest(evaluator_paths, by_path)
    reviewer_digest = _bundle_digest(reviewer_paths, by_path)
    profile_digest = canonical_sha256(
        {
            "profile_version": "lean-pilot-task-profile.v1",
            "task_id": "A1",
            "source_path": "task.md",
            "brief_digest": by_path["task.md"],
            "archive_digest": archive_digest,
            "selected_final_files": review["selected_final_files"],
            "permitted_check_evidence_names": review[
                "permitted_check_evidence_names"
            ],
            "visible_check": apparatus["visible_check"],
            "product_projection_exclusions": apparatus[
                "product_projection_exclusions"
            ],
            "evaluator_bundle_digest": evaluator_digest,
        }
    )
    source_map = {
        "schema_version": "lean-pilot-apparatus-source-map.v1",
        "pilot": {
            "pilot_id": "fixture-pilot",
            "task_id": "A1",
            "randomization_seed": _sha256(b"randomization"),
            "valid_block_count": 3,
            "max_live_attempt_count": 5,
            "smoke_id": "smoke-fixture",
            "live_attempt_ids": [f"live-{index}" for index in range(1, 6)],
            "claim_level": "exploratory_controlled_task",
        },
        "archive": {
            "repository_identity": "fixture-repository",
            "revision_identity": f"commit:{commit}",
            "source_subtree_path": "benchmark",
            "source_tree_identity": f"git-tree:{tree}",
            "archive_digest": archive_digest,
            "task_source_path": "task.md",
        },
        "provider_policy": provider_policy,
        "apparatus": apparatus,
        "review": review,
        "treatments": treatments,
        "sources": sources,
        "expected_derived_digests": {
            "treatment_sources": expected_source_digests,
            "evaluator_bundle": evaluator_digest,
            "reviewer_command_bundle": reviewer_digest,
            "task_profile": profile_digest,
        },
    }
    source_map_path = (tmp_path / "apparatus-source-map.json").resolve()
    _canonical_write(source_map_path, source_map)
    return {
        "repo": repo,
        "commit": commit,
        "source_map": source_map,
        "source_map_path": source_map_path,
        "seal": calibration_seal,
        "seal_path": seal_path,
        "control_root": (tmp_path / "control-root").resolve(),
        "evidence_root": (tmp_path / "evidence-root").resolve(),
        "lock_output": (tmp_path / "pilot-lock.json").resolve(),
        "source_values": source_values,
    }


def _prepare(case: dict[str, Any]) -> dict[str, Any]:
    return prepare_pilot(
        source_map_path=case["source_map_path"],
        repository_root=case["repo"],
        apparatus_revision=case["commit"],
        control_root=case["control_root"],
        evidence_root=case["evidence_root"],
        calibration_seal_path=case["seal_path"],
        lock_output_path=case["lock_output"],
    )


def _rewrite_map(case: dict[str, Any], value: dict[str, Any]) -> None:
    case["source_map"] = value
    _canonical_write(case["source_map_path"], value)


def test_tracked_source_map_is_closed_and_binds_literal_pilot_inputs() -> None:
    path = Path(
        "experiments/orc_effectiveness/lean_pilot/apparatus-source-map.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))

    _shape(value)

    assert value["pilot"] == {
        "claim_level": "exploratory_controlled_task",
        "live_attempt_ids": [
            "b-de346bae12e7fcaa",
            "b-4e8ad2b5a9394e11",
            "b-a2e6c6a472f9b866",
            "b-c559f809d4c111a3",
            "b-30d84c77dbc98d35",
        ],
        "max_live_attempt_count": 5,
        "pilot_id": "a1-lean-pilot-2026-07-27-r0",
        "randomization_seed": (
            "e7c416b9bb1bc2ee581c41a029db88d8bdbc74dd4badffd4d617c6dad7b164db"
        ),
        "smoke_id": "b-f8d04fa838232314",
        "task_id": "A1",
        "valid_block_count": 3,
    }
    assert len(value["apparatus"]["treatment_asset_paths"]) == 17
    assert len(value["sources"]) == 48
    external = [
        row
        for row in value["sources"]
        if row["source_kind"] == "external_calibration_seal"
    ]
    assert external == [
        {
            "destination_path": "review/calibration-seal.json",
            "sha256": (
                "sha256:"
                "ad2570d72a0608173232d53beee7990c0e2afaa198f549bae8769083cc8e7f8f"
            ),
            "source_kind": "external_calibration_seal",
        }
    ]
    for row in value["sources"]:
        if row["source_kind"] != "repository":
            continue
        assert _sha256(Path(row["source_path"]).read_bytes()) == row["sha256"]
    calibration = json.loads(
        Path(
            "experiments/orc_effectiveness/lean_pilot/calibration/"
            "calibration-lock.json"
        ).read_text(encoding="utf-8")
    )
    reviewer_command = json.loads(
        Path(
            "experiments/orc_effectiveness/lean_pilot/reviewers/"
            "live-review-command.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        reviewer_command["reviewer_execution"]
        == calibration["reviewer_execution"]
    )
    schema_bytes = Path(
        "experiments/orc_effectiveness/lean_pilot/reviewers/"
        "live-review-output.schema.json"
    ).read_bytes()
    assert reviewer_command["live_output_schema_digest"] == _sha256(schema_bytes)


def test_prepare_materializes_closed_tree_and_publishes_valid_lock(
    tmp_path: Path,
) -> None:
    case = _fixture(tmp_path)

    lock = _prepare(case)

    validate_record(lock)
    assert case["lock_output"].read_bytes() == canonical_json_bytes(lock)
    assert lock["archive"]["repository_root"] == case["repo"].as_posix()
    assert lock["apparatus"]["control_root"] == case["control_root"].as_posix()
    assert lock["evidence_root"] == case["evidence_root"].as_posix()
    actual_files = sorted(
        path.relative_to(case["control_root"]).as_posix()
        for path in case["control_root"].rglob("*")
        if path.is_file()
    )
    expected_files = sorted(
        row["destination_path"] for row in case["source_map"]["sources"]
    )
    assert actual_files == expected_files
    assert case["evidence_root"].is_dir()
    assert list(case["evidence_root"].iterdir()) == []
    assert (
        case["control_root"] / "task.md"
    ).read_bytes() == case["source_values"]["tasks/a1.md"]


def test_prepare_derives_treatment_runtime_from_explicit_repo_and_revision(
    tmp_path: Path,
) -> None:
    case = _fixture(tmp_path)

    lock = _prepare(case)

    assert lock["apparatus"]["treatment_runtime"] == {
        "import_root": case["repo"].as_posix(),
        "revision_identity": f"commit:{case['commit']}",
        "tree_identity": (
            "git-tree:"
            + _git(
                case["repo"],
                "rev-parse",
                f"{case['commit']}^{{tree}}",
            )
        ),
    }


@pytest.mark.parametrize("occupied", ["control_root", "evidence_root", "lock_output"])
def test_prepare_rejects_nonfresh_destinations(
    tmp_path: Path, occupied: str
) -> None:
    case = _fixture(tmp_path)
    path = case[occupied]
    if occupied == "lock_output":
        path.write_text("retain me", encoding="utf-8")
    else:
        path.mkdir()

    with pytest.raises(PilotPreparationError, match="must not exist"):
        _prepare(case)

    if occupied == "lock_output":
        assert path.read_text(encoding="utf-8") == "retain me"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["sources"][0].__setitem__(
                "destination_path", "../escape"
            ),
            "canonical relative POSIX",
        ),
        (
            lambda value: value["sources"].append(
                copy.deepcopy(value["sources"][0])
            ),
            "duplicate",
        ),
        (
            lambda value: value["sources"][0].__setitem__(
                "sha256", _sha256(b"wrong")
            ),
            "digest mismatch",
        ),
        (
            lambda value: value["sources"].append(
                {
                    "source_kind": "repository",
                    "source_path": "extra.txt",
                    "destination_path": "extra.txt",
                    "sha256": _sha256(b"extra"),
                }
            ),
            "classified",
        ),
        (
            lambda value: value["sources"].pop(),
            "classified",
        ),
    ],
)
def test_prepare_rejects_unsafe_duplicate_drifted_or_extra_source_rows(
    tmp_path: Path, mutation: Any, message: str
) -> None:
    case = _fixture(tmp_path)
    changed = copy.deepcopy(case["source_map"])
    mutation(changed)
    _rewrite_map(case, changed)

    with pytest.raises(PilotPreparationError, match=message):
        _prepare(case)

    assert not os.path.lexists(case["control_root"])
    assert not os.path.lexists(case["lock_output"])


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda digests: digests.__setitem__(
                "SHADOW", "sha256:" + "0" * 64
            ),
            "expected treatment digests has missing or extra fields",
        ),
        (
            lambda digests: digests.pop("ORC"),
            "expected treatment digests has missing or extra fields",
        ),
        (
            lambda digests: digests.__setitem__(
                "../DIRECT", digests.pop("DIRECT")
            ),
            "expected treatment digests has missing or extra fields",
        ),
        (
            lambda digests: digests.__setitem__("DIRECT", "not-a-digest"),
            "DIRECT treatment source digest is not a SHA-256 digest",
        ),
    ],
)
def test_prepare_rejects_open_or_malformed_treatment_source_digest_map(
    tmp_path: Path, mutation: Any, message: str
) -> None:
    case = _fixture(tmp_path)
    changed = copy.deepcopy(case["source_map"])
    mutation(changed["expected_derived_digests"]["treatment_sources"])
    _rewrite_map(case, changed)

    with pytest.raises(PilotPreparationError, match=message):
        _prepare(case)

    assert not os.path.lexists(case["control_root"])
    assert not os.path.lexists(case["evidence_root"])
    assert not os.path.lexists(case["lock_output"])


@pytest.mark.parametrize(
    ("field", "wrong", "message"),
    [
        ("source_tree_identity", "git-tree:" + "0" * 40, "tree"),
        ("archive_digest", "sha256:" + "0" * 64, "archive"),
        ("task_source_path", "missing-task.md", "task"),
    ],
)
def test_prepare_rejects_frozen_archive_or_task_drift(
    tmp_path: Path, field: str, wrong: str, message: str
) -> None:
    case = _fixture(tmp_path)
    changed = copy.deepcopy(case["source_map"])
    changed["archive"][field] = wrong
    _rewrite_map(case, changed)

    with pytest.raises(PilotPreparationError, match=message):
        _prepare(case)


def test_prepare_rejects_symlinked_calibration_seal_without_following_it(
    tmp_path: Path,
) -> None:
    case = _fixture(tmp_path)
    real = case["seal_path"]
    link = tmp_path / "seal-link.json"
    link.symlink_to(real)
    case["seal_path"] = link

    with pytest.raises(PilotPreparationError, match="regular file"):
        _prepare(case)


def test_prepare_rejects_calibration_seal_lock_or_execution_drift(
    tmp_path: Path,
) -> None:
    case = _fixture(tmp_path)
    changed_seal = copy.deepcopy(case["seal"])
    changed_seal["calibration_lock_digest"] = "sha256:" + "0" * 64
    seal_bytes = _canonical_write(case["seal_path"], changed_seal)
    changed_map = copy.deepcopy(case["source_map"])
    external = next(
        row
        for row in changed_map["sources"]
        if row["source_kind"] == "external_calibration_seal"
    )
    external["sha256"] = _sha256(seal_bytes)
    _rewrite_map(case, changed_map)

    with pytest.raises(PilotPreparationError, match="calibration lock"):
        _prepare(case)


@pytest.mark.parametrize(
    "field",
    [
        "evaluator_bundle",
        "reviewer_command_bundle",
        "task_profile",
    ],
)
def test_prepare_rejects_asserted_derived_digest_drift(
    tmp_path: Path, field: str
) -> None:
    case = _fixture(tmp_path)
    changed = copy.deepcopy(case["source_map"])
    changed["expected_derived_digests"][field] = "sha256:" + "0" * 64
    _rewrite_map(case, changed)

    with pytest.raises(PilotPreparationError, match="derived digest"):
        _prepare(case)


@pytest.mark.parametrize("state", ["tracked", "untracked", "ignored"])
def test_prepare_rejects_nonclean_treatment_runtime_repository(
    tmp_path: Path,
    state: str,
) -> None:
    case = _fixture(tmp_path)
    if state == "tracked":
        path = case["repo"] / "tasks/a1.md"
    else:
        path = case["repo"] / f"{state}.tmp"
    if state == "ignored":
        (case["repo"] / ".git/info/exclude").write_text(
            "ignored.tmp\n",
            encoding="utf-8",
        )
    path.write_bytes(b"nonclean live-tree bytes\n")

    with pytest.raises(PilotPreparationError, match="clean including ignored"):
        _prepare(case)

    assert not os.path.lexists(case["control_root"])
    assert not os.path.lexists(case["evidence_root"])
    assert not os.path.lexists(case["lock_output"])


def test_prepare_rejects_attached_or_indirect_treatment_runtime(
    tmp_path: Path,
) -> None:
    attached_root = tmp_path / "attached"
    attached_root.mkdir()
    attached = _fixture(attached_root)
    _git(attached["repo"], "checkout", "-q", "-")
    with pytest.raises(PilotPreparationError, match="HEAD must be detached"):
        _prepare(attached)

    indirect_root = tmp_path / "indirect"
    indirect_root.mkdir()
    indirect = _fixture(indirect_root)
    (indirect["repo"] / ".git/commondir").write_text(".\n", encoding="utf-8")
    with pytest.raises(PilotPreparationError, match="common-dir indirection"):
        _prepare(indirect)


@pytest.mark.parametrize("name", ["alternates", "http-alternates"])
def test_prepare_rejects_treatment_runtime_object_alternates(
    tmp_path: Path,
    name: str,
) -> None:
    case = _fixture(tmp_path)
    (case["repo"] / ".git/objects/info" / name).write_text(
        "/unlocked/object-store\n",
        encoding="utf-8",
    )

    with pytest.raises(PilotPreparationError, match=name):
        _prepare(case)

    assert not os.path.lexists(case["control_root"])
    assert not os.path.lexists(case["evidence_root"])
    assert not os.path.lexists(case["lock_output"])


def test_lock_publication_is_exclusive_under_a_late_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _fixture(tmp_path)
    from orchestrator.experiments import _pilot_prepare

    real_publish = _pilot_prepare._publish_exclusive

    def collide(path: Path, data: bytes) -> None:
        path.write_text("racer", encoding="utf-8")
        real_publish(path, data)

    monkeypatch.setattr(_pilot_prepare, "_publish_exclusive", collide)

    with pytest.raises(PilotPreparationError, match="already exists"):
        _prepare(case)

    assert case["lock_output"].read_text(encoding="utf-8") == "racer"
