from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from orchestrator.experiments.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.experiments.workspace import (
    freeze_product,
    materialize_git_archive,
)
from orchestrator.experiments._runner_apparatus import opaque_label


ROOT = Path(__file__).resolve().parents[2]


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _bundle_digest(
    manifest: list[dict[str, str]],
    paths: list[str],
) -> str:
    by_path = {item["path"]: item for item in manifest}
    return canonical_sha256(
        [by_path[path] for path in sorted(paths, key=str.encode)]
    )


def _profile_digest(lock: dict[str, Any]) -> str:
    return canonical_sha256(
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


def _fake_evaluator_source() -> bytes:
    return b"""
from pathlib import Path

def evaluate_workspace(workspace):
    passed = (Path(workspace) / "result.txt").read_text() == "pass\\n"
    return {
        "failure_categories": [] if passed else ["hidden_acceptance_failed"],
        "soft_quality": {"findings": [], "score": 1 if passed else 0},
        "summary": {
            "hidden_tests_passed": passed,
            "score": 1 if passed else 0,
        },
        "verdict": "PASS" if passed else "FAIL",
    }
"""


def _fixture_reading_evaluator_source() -> bytes:
    return b"""
import json
from pathlib import Path

def evaluate_workspace(workspace):
    fixture = (
        Path(__file__).parent
        / "fixtures/nanobragg_entrypoint/cases.json"
    )
    locked_fixture = json.loads(
        fixture.read_text(encoding="utf-8")
    ) == {"expected": "locked"}
    passed = (
        locked_fixture
        and (Path(workspace) / "result.txt").read_text() == "pass\\n"
    )
    return {
        "failure_categories": [] if passed else ["hidden_acceptance_failed"],
        "soft_quality": {"findings": [], "score": 1 if passed else 0},
        "summary": {
            "hidden_tests_passed": passed,
            "score": 1 if passed else 0,
        },
        "verdict": "PASS" if passed else "FAIL",
    }
"""


def _always_failing_evaluator_source() -> bytes:
    return b"""
def evaluate_workspace(workspace):
    return {
        "failure_categories": ["mutated_module_executed"],
        "soft_quality": {"findings": [], "score": 0},
        "summary": {"hidden_tests_passed": False, "score": 0},
        "verdict": "FAIL",
    }
"""


def _spawning_evaluator_source() -> bytes:
    return (
        ROOT
        / "tests/experiments/fixtures/lean_pilot/spawning_evaluator.py"
    ).read_bytes()


def _evaluator_config(runtime_paths: list[str], *, timeout: int = 5_000) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": "lean-pilot-hidden-evaluator.v1",
            "module_path": (
                "orchestrator/demo/evaluators/nanobragg_entrypoint.py"
            ),
            "runtime_asset_paths": runtime_paths,
            "timeout_milliseconds": timeout,
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
    )


def _case(tmp_path: Path) -> dict[str, Any]:
    repo = (tmp_path / "repo").resolve()
    subtree = repo / "fixture"
    _write(subtree / "docs/tasks/task.md", b"Implement the behavior.\n")
    _write(subtree / "result.txt", b"base\n")
    _write(subtree / "ignored.txt", b"base ignored\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pilot@example.invalid")
    _git(repo, "config", "user.name", "Pilot Fixture")
    _git(repo, "add", "fixture")
    _git(repo, "commit", "-qm", "fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", f"{commit}:fixture")

    base = tmp_path / "base"
    base_manifest = materialize_git_archive(
        repo,
        f"{commit}:fixture",
        base,
    )
    work_root = (tmp_path / "work").resolve()
    block_id = "live-001"
    roles = ("DIRECT", "COORDINATOR", "ORC")
    labels = {
        role: opaque_label("fixed-seed", block_id, role) for role in roles
    }
    products: dict[str, Path] = {}
    for index, role in enumerate(roles, start=1):
        product = work_root / block_id / labels[role] / "workspace"
        shutil.copytree(base, product)
        _write(product / "result.txt", b"pass\n" if index == 1 else b"fail\n")
        _write(product / "ignored.txt", f"ignored {index}\n".encode())
        products[role] = product

    control_root = (tmp_path / "control").resolve()
    module_path = "orchestrator/demo/evaluators/nanobragg_entrypoint.py"
    fixture_path = (
        "orchestrator/demo/evaluators/fixtures/"
        "nanobragg_entrypoint/cases.json"
    )
    runtime_paths = [module_path, fixture_path]
    assets = {
        "task.md": b"Implement the behavior.\n",
        "providers.json": b"providers\n",
        "prompts.json": b"prompts\n",
        "commands.json": b"commands\n",
        "treatments/direct.json": b"direct\n",
        "treatments/coordinator.json": b"coordinator\n",
        "treatments/orc.json": b"orc\n",
        "treatment_driver.py": b"driver\n",
        "review/rubric.md": b"rubric\n",
        "review/calibration-seal.json": b"calibration\n",
        "evaluation/config.json": _evaluator_config(runtime_paths),
        module_path: _fake_evaluator_source(),
        fixture_path: b'{"cases":[]}\n',
        "review/reviewer-command.json": b"reviewer\n",
        "review/review-result.schema.json": b"schema\n",
    }
    for relative, data in assets.items():
        _write(control_root / relative, data)
    manifest = [
        {"path": relative, "sha256": _sha256(data)}
        for relative, data in assets.items()
    ]
    evaluator_paths = ["evaluation/config.json", *runtime_paths]
    reviewer_paths = [
        "review/reviewer-command.json",
        "review/review-result.schema.json",
    ]
    treatment_paths = [
        relative
        for relative in assets
        if not relative.startswith(("evaluation/", "review/", "orchestrator/"))
    ]
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    for role in roles:
        for name in ("check-stderr.txt", "check-stdout.txt"):
            _write(
                evidence_root / block_id / labels[role] / name,
                b"visible check\n",
            )

    task_digest = _sha256(
        (subtree / "docs/tasks/task.md").read_bytes()
    )
    command_digests = {
        role: _sha256(assets[f"treatments/{role.lower()}.json"])
        for role in roles
    }
    lock: dict[str, Any] = {
        "record_kind": "pilot_lock.v1",
        "pilot_id": "pilot-001",
        "task": {
            "task_id": "A1",
            "source_path": "docs/tasks/task.md",
            "profile_digest": _sha256(b"pending"),
            "brief_digest": task_digest,
        },
        "archive": {
            "repository_identity": "fixture/repository",
            "repository_root": repo.as_posix(),
            "revision_identity": f"commit:{commit}",
            "source_subtree_path": "fixture",
            "source_tree_identity": f"git-tree:{tree}",
            "archive_digest": base_manifest.digest,
        },
        "provider_policy": {
            "family": "fixture",
            "model": "fixture-model",
            "reasoning_effort": "high",
            "tool_policy": "fixture-policy",
            "timeout_milliseconds": 1_000,
            "currency": "USD",
        },
        "review": {
            "reviewer_ids": ["reviewer-1", "reviewer-2"],
            "disagreement_policy": "INDETERMINATE_ON_DISAGREEMENT",
            "selected_final_files": ["result.txt"],
            "permitted_check_evidence_names": [
                "check-stderr.txt",
                "check-stdout.txt",
                "hidden-evaluator.json",
            ],
            "rubric_path": "review/rubric.md",
            "rubric_digest": _sha256(assets["review/rubric.md"]),
            "calibration_evidence_path": "review/calibration-seal.json",
            "calibration_evidence_digest": _sha256(
                assets["review/calibration-seal.json"]
            ),
            "evaluator": {
                "config_path": "evaluation/config.json",
                "asset_paths": evaluator_paths,
                "bundle_digest": _bundle_digest(manifest, evaluator_paths),
            },
            "reviewer_command": {
                "config_path": "review/reviewer-command.json",
                "asset_paths": reviewer_paths,
                "bundle_digest": _bundle_digest(manifest, reviewer_paths),
            },
        },
        "apparatus": {
            "control_root": control_root.as_posix(),
            "asset_manifest": manifest,
            "treatment_asset_paths": treatment_paths,
            "task_path": "task.md",
            "provider_config_path": "providers.json",
            "prompt_config_path": "prompts.json",
            "command_config_path": "commands.json",
            "environment": {
                "identity": _sha256(b"environment"),
                "allowed_keys": ["HOME", "PATH", "TMPDIR"],
                "credential_keys": [],
            },
            "visible_check": {
                "argv": ["python", "-m", "pytest", "-q"],
                "timeout_milliseconds": 1_000,
            },
            "product_projection_exclusions": [],
            "maximum_start_skew_milliseconds": 500,
            "quiescence_grace_milliseconds": 500,
        },
        "randomization_seed": "fixed-seed",
        "evidence_root": evidence_root.as_posix(),
        "valid_block_count": 3,
        "max_live_attempt_count": 5,
        "smoke_id": "smoke-001",
        "live_attempt_ids": [
            "live-001",
            "live-002",
            "live-003",
            "live-004",
            "live-005",
        ],
        "claim_level": "exploratory_controlled_task",
        "treatments": [
            {
                "treatment_id": role,
                "source_asset_paths": [
                    f"treatments/{role.lower()}.json",
                    "treatment_driver.py",
                ],
                "source_digest": _bundle_digest(
                    manifest,
                    [
                        f"treatments/{role.lower()}.json",
                        "treatment_driver.py",
                    ],
                ),
                "command_digest": command_digests[role],
                "command_config_path": f"treatments/{role.lower()}.json",
                "provider_call_bounds": {
                    "minimum": 1 if role == "DIRECT" else 3,
                    "maximum": 1 if role == "DIRECT" else 9,
                },
            }
            for role in roles
        ],
    }
    lock["task"]["profile_digest"] = _profile_digest(lock)
    attempt = {
        "record_kind": "block_attempt.v1",
        "pilot_lock_digest": canonical_sha256(lock),
        "attempt_class": "LIVE",
        "sequence_index": 0,
        "block_id": block_id,
        "status": "VALID",
        "treatment_executions": [
            {
                "opaque_arm_label": labels[role],
                "treatment_id": role,
                "command_digest": command_digests[role],
                "lifecycle_outcome": "COMPLETED",
                "product_frozen": True,
                "product_manifest_digest": freeze_product(
                    products[role],
                    (),
                ).digest,
                "provider_call_count": 1 if role == "DIRECT" else 3,
                "elapsed_milliseconds": 100,
                "evidence_references": [
                    f"{block_id}/opaque-{index}/check-stdout.txt"
                ],
                "token_counts": "UNKNOWN",
                "cost": "UNKNOWN",
            }
            for index, role in enumerate(roles, start=1)
        ],
    }
    attempt_path = evidence_root / block_id / "block-attempt.json"
    _write(attempt_path, canonical_json_bytes(attempt))
    return {
        "lock": lock,
        "attempt": attempt,
        "work_root": work_root,
        "evaluation_root": (tmp_path / "evaluation" / block_id).resolve(),
        "package_root": (tmp_path / "packages" / block_id).resolve(),
        "products": products,
        "control_root": control_root,
        "evidence_root": evidence_root,
        "attempt_path": attempt_path,
        "module_path": module_path,
        "runtime_paths": runtime_paths,
        "labels": labels,
    }


def _refresh_control(case: dict[str, Any]) -> None:
    lock = case["lock"]
    control_root = case["control_root"]
    manifest = lock["apparatus"]["asset_manifest"]
    for entry in manifest:
        entry["sha256"] = _sha256(
            (control_root / entry["path"]).read_bytes()
        )
    evaluator_paths = lock["review"]["evaluator"]["asset_paths"]
    lock["review"]["evaluator"]["bundle_digest"] = _bundle_digest(
        manifest,
        evaluator_paths,
    )
    lock["task"]["profile_digest"] = _profile_digest(lock)
    attempt = case["attempt"]
    attempt["pilot_lock_digest"] = canonical_sha256(lock)
    _write(case["attempt_path"], canonical_json_bytes(attempt))


def _save_attempt(case: dict[str, Any]) -> None:
    _write(case["attempt_path"], canonical_json_bytes(case["attempt"]))


def _replace_evaluator(case: dict[str, Any], source: bytes) -> None:
    _write(case["control_root"] / case["module_path"], source)
    _refresh_control(case)


def _replace_config(
    case: dict[str, Any],
    *,
    timeout: int = 5_000,
    runtime_paths: list[str] | None = None,
) -> None:
    _write(
        case["control_root"] / "evaluation/config.json",
        _evaluator_config(
            case["runtime_paths"] if runtime_paths is None else runtime_paths,
            timeout=timeout,
        ),
    )
    _refresh_control(case)


def _prepare(case: dict[str, Any]) -> dict[str, object]:
    from orchestrator.experiments._pilot_evidence import prepare_block_package

    return prepare_block_package(
        lock=case["lock"],
        attempt=case["attempt"],
        work_root=case["work_root"],
        evaluation_root=case["evaluation_root"],
        package_root=case["package_root"],
    )


def test_tracked_evaluator_config_closes_the_runtime_fixture_set() -> None:
    path = (
        ROOT
        / "experiments/orc_effectiveness/lean_pilot/evaluation"
        / "nanobragg-entrypoint.json"
    )
    config = json.loads(path.read_text(encoding="utf-8"))
    fixture_root = (
        ROOT
        / "orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint"
    )
    expected = sorted(
        {
            item.relative_to(ROOT).as_posix()
            for item in fixture_root.rglob("*")
            if item.is_file() and item.name != "README.md"
        }
        | {"orchestrator/demo/evaluators/nanobragg_entrypoint.py"},
        key=str.encode,
    )

    assert config == {
        "module_path": "orchestrator/demo/evaluators/nanobragg_entrypoint.py",
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
        "runtime_asset_paths": expected,
        "schema_version": "lean-pilot-hidden-evaluator.v1",
        "timeout_milliseconds": 300_000,
    }


def test_prepare_block_package_evaluates_pass_and_fail_and_builds_package(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    result = _prepare(case)

    assert result["package_id"] == "live-001"
    assert result["package_root"] == case["package_root"] / "live-001"
    assert result["label_map_path"] == (
        case["evidence_root"] / "label-maps/live-001.json"
    )
    assert {
        role: binding["verdict"]
        for role, binding in result["evaluator_evidence"].items()
    } == {
        "DIRECT": "PASS",
        "COORDINATOR": "FAIL",
        "ORC": "FAIL",
    }
    assert (result["package_root"] / "manifest.json").is_file()
    assert result["package_manifest_digest"] == _sha256(
        (result["package_root"] / "manifest.json").read_bytes()
    )
    assert result["label_map_digest"] == _sha256(
        result["label_map_path"].read_bytes()
    )
    for binding in result["evaluator_evidence"].values():
        payload = json.loads(binding["path"].read_text(encoding="utf-8"))
        assert payload["verdict"] == binding["verdict"]
        assert binding["digest"] == _sha256(binding["path"].read_bytes())


def test_prepare_block_package_runs_the_materialized_real_evaluator(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    tracked_config = (
        ROOT
        / "experiments/orc_effectiveness/lean_pilot/evaluation"
        / "nanobragg-entrypoint.json"
    ).read_bytes()
    config = json.loads(tracked_config)
    _write(case["control_root"] / "evaluation/config.json", tracked_config)
    for relative in config["runtime_asset_paths"]:
        _write(
            case["control_root"] / relative,
            (ROOT / relative).read_bytes(),
        )
    manifest = [
        {
            "path": path.relative_to(case["control_root"]).as_posix(),
            "sha256": _sha256(path.read_bytes()),
        }
        for path in sorted(
            (
                item
                for item in case["control_root"].rglob("*")
                if item.is_file()
            ),
            key=lambda item: item.relative_to(case["control_root"])
            .as_posix()
            .encode(),
        )
    ]
    evaluator_paths = [
        "evaluation/config.json",
        *config["runtime_asset_paths"],
    ]
    case["lock"]["apparatus"]["asset_manifest"] = manifest
    case["lock"]["review"]["evaluator"] = {
        "config_path": "evaluation/config.json",
        "asset_paths": evaluator_paths,
        "bundle_digest": _bundle_digest(manifest, evaluator_paths),
    }
    case["lock"]["task"]["profile_digest"] = _profile_digest(case["lock"])
    case["attempt"]["pilot_lock_digest"] = canonical_sha256(case["lock"])
    _save_attempt(case)

    result = _prepare(case)

    assert {
        binding["verdict"]
        for binding in result["evaluator_evidence"].values()
    } == {"FAIL"}


@pytest.mark.parametrize(
    ("mutated_asset", "mutated_bytes"),
    [
        (
            "orchestrator/demo/evaluators/nanobragg_entrypoint.py",
            _always_failing_evaluator_source(),
        ),
        (
            "orchestrator/demo/evaluators/fixtures/"
            "nanobragg_entrypoint/cases.json",
            b'{"expected":"mutated"}',
        ),
    ],
    ids=("module", "fixture"),
)
def test_prepare_block_package_executes_only_post_verification_staged_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutated_asset: str,
    mutated_bytes: bytes,
) -> None:
    import orchestrator.experiments._pilot_evidence as evidence

    case = _case(tmp_path)
    locked_assets = {
        case["module_path"]: _fixture_reading_evaluator_source(),
        case["runtime_paths"][1]: b'{"expected":"locked"}',
    }
    for relative, data in locked_assets.items():
        _write(case["control_root"] / relative, data)
    _refresh_control(case)
    verify = evidence.apparatus.verified_assets

    def verify_then_mutate(lock: dict[str, object]) -> dict[str, bytes]:
        verified = verify(lock)
        _write(case["control_root"] / mutated_asset, mutated_bytes)
        return verified

    monkeypatch.setattr(
        evidence.apparatus,
        "verified_assets",
        verify_then_mutate,
    )

    result = _prepare(case)

    assert result["evaluator_evidence"]["DIRECT"]["verdict"] == "PASS"
    staged_root = (
        case["evaluation_root"] / ".controller/evaluator-apparatus"
    )
    for relative, data in locked_assets.items():
        assert staged_root.joinpath(*Path(relative).parts).read_bytes() == data
    assert (case["control_root"] / mutated_asset).read_bytes() == mutated_bytes


def test_prepare_block_package_rejects_source_manifest_drift(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    _write(case["products"]["DIRECT"] / "result.txt", b"changed after freeze\n")

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_product_manifest_mismatch"
    assert not case["evaluation_root"].exists()


def test_prepare_block_package_rejects_copied_product_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.experiments._pilot_evidence as evidence

    case = _case(tmp_path)
    original = evidence._copy_projected_product

    def corrupt_copy(
        source_root: Path,
        destination: Path,
        manifest: object,
    ) -> None:
        original(source_root, destination, manifest)
        _write(destination / "result.txt", b"copy drift\n")

    monkeypatch.setattr(evidence, "_copy_projected_product", corrupt_copy)
    with pytest.raises(evidence.PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_copy_manifest_mismatch"
    assert not (
        case["evidence_root"]
        / f"live-001/{case['labels']['DIRECT']}/hidden-evaluator.json"
    ).exists()


def test_prepare_block_package_rejects_projected_symlink(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    product = case["products"]["DIRECT"]
    (product / "linked").symlink_to("result.txt")
    case["attempt"]["treatment_executions"][0][
        "product_manifest_digest"
    ] = freeze_product(product, ()).digest
    _save_attempt(case)

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_product_unsafe"


def test_prepare_block_package_rejects_projected_nonregular_node(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    os.mkfifo(case["products"]["DIRECT"] / "pipe")

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_product_invalid"


def test_prepare_block_package_copies_only_locked_projection(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    case["lock"]["apparatus"]["product_projection_exclusions"] = ["scratch"]
    for execution in case["attempt"]["treatment_executions"]:
        role = execution["treatment_id"]
        product = case["products"][role]
        _write(product / "scratch/private.txt", role.encode())
        execution["product_manifest_digest"] = freeze_product(
            product,
            (Path("scratch"),),
        ).digest
    case["lock"]["task"]["profile_digest"] = _profile_digest(case["lock"])
    case["attempt"]["pilot_lock_digest"] = canonical_sha256(case["lock"])
    _save_attempt(case)

    result = _prepare(case)

    assert all(
        not (root / "scratch").exists()
        for root in result["evaluation_product_roots"].values()
    )


@pytest.mark.parametrize(
    ("source", "timeout", "expected_code"),
    [
        (
            b"""
import time
def evaluate_workspace(workspace):
    time.sleep(1)
    return {}
""",
            10,
            "pilot_evidence_evaluator_execution_failed",
        ),
        (
            b"""
def evaluate_workspace(workspace):
    raise RuntimeError("boom")
""",
            5_000,
            "pilot_evidence_evaluator_execution_failed",
        ),
        (
            b"""
print("unexpected output")
def evaluate_workspace(workspace):
    return {
        "failure_categories": [],
        "soft_quality": {},
        "summary": {"hidden_tests_passed": True},
        "verdict": "PASS",
    }
""",
            5_000,
            "pilot_evidence_evaluator_malformed",
        ),
    ],
    ids=("timeout", "nonzero", "malformed"),
)
def test_prepare_block_package_rejects_evaluator_apparatus_defects(
    tmp_path: Path,
    source: bytes,
    timeout: int,
    expected_code: str,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    _replace_evaluator(case, source)
    _replace_config(case, timeout=timeout)

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == expected_code


def test_prepare_block_package_quiesces_evaluator_descendants_after_success(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    _replace_evaluator(case, _spawning_evaluator_source())

    _prepare(case)

    runtime_parent = case["evaluation_root"] / ".controller"
    assert all(
        (runtime_parent / label / "tmp/descendant-started.txt").is_file()
        for label in case["labels"].values()
    )
    time.sleep(0.9)
    assert not any(
        (runtime_parent / label / "tmp/descendant-late-mutation.txt").exists()
        for label in case["labels"].values()
    )


def test_prepare_block_package_quiesces_evaluator_descendants_after_timeout(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    for execution in case["attempt"]["treatment_executions"]:
        role = execution["treatment_id"]
        _write(case["products"][role] / "result.txt", b"timeout\n")
        execution["product_manifest_digest"] = freeze_product(
            case["products"][role],
            (),
        ).digest
    _replace_evaluator(case, _spawning_evaluator_source())
    _replace_config(case, timeout=200)

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_evaluator_execution_failed"
    runtime = (
        case["evaluation_root"]
        / ".controller"
        / case["labels"]["DIRECT"]
        / "tmp"
    )
    assert (runtime / "descendant-started.txt").is_file()
    time.sleep(0.9)
    assert not (runtime / "descendant-late-mutation.txt").exists()


def test_prepare_block_package_rejects_unproven_evaluator_group_quiescence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.experiments import _pilot_evaluator_process as process
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    case["lock"]["apparatus"]["quiescence_grace_milliseconds"] = 1
    case["attempt"]["pilot_lock_digest"] = canonical_sha256(case["lock"])
    _save_attempt(case)
    monkeypatch.setattr(
        process,
        "_process_group_exists",
        lambda _process_group_id: True,
    )

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_evaluator_execution_failed"
    assert str(caught.value).endswith(": quiescence")


def test_prepare_block_package_rejects_evaluator_asset_closure_drift(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    _replace_config(case, runtime_paths=[case["module_path"]])

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_evaluator_invalid"


def test_prepare_block_package_never_replaces_evaluator_evidence(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    collision = (
        case["evidence_root"]
        / f"live-001/{case['labels']['DIRECT']}/hidden-evaluator.json"
    )
    _write(collision, b"retain me")

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_publication_failed"
    assert collision.read_bytes() == b"retain me"


def test_prepare_block_package_never_replaces_label_map(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    collision = case["evidence_root"] / "label-maps/live-001.json"
    _write(collision, b"retain me")

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_package_failed"
    assert collision.read_bytes() == b"retain me"


def test_prepare_block_package_allows_smoke_without_review(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    live_id = case["attempt"]["block_id"]
    smoke_id = case["lock"]["smoke_id"]
    (case["work_root"] / live_id).rename(case["work_root"] / smoke_id)
    (case["evidence_root"] / live_id).rename(
        case["evidence_root"] / smoke_id
    )
    for execution in case["attempt"]["treatment_executions"]:
        role = execution["treatment_id"]
        old_label = execution["opaque_arm_label"]
        new_label = opaque_label("fixed-seed", smoke_id, role)
        (case["work_root"] / smoke_id / old_label).rename(
            case["work_root"] / smoke_id / new_label
        )
        (case["evidence_root"] / smoke_id / old_label).rename(
            case["evidence_root"] / smoke_id / new_label
        )
        execution["opaque_arm_label"] = new_label
        execution["evidence_references"] = [
            f"{smoke_id}/{new_label}/check-stdout.txt"
        ]
    case["attempt"].update(
        {
            "attempt_class": "SMOKE",
            "block_id": smoke_id,
            "sequence_index": 0,
        }
    )
    case["attempt_path"] = (
        case["evidence_root"] / smoke_id / "block-attempt.json"
    )
    _save_attempt(case)
    case["evaluation_root"] = case["evaluation_root"].parent / smoke_id
    case["package_root"] = case["package_root"].parent / smoke_id

    result = _prepare(case)

    assert result["package_id"] == smoke_id
    assert not any(
        "review" in path.name
        for path in result["package_root"].rglob("*")
    )


def test_prepare_block_package_rejects_attempt_record_drift(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    case["attempt"]["treatment_executions"][0]["elapsed_milliseconds"] += 1

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_lineage_invalid"


def test_prepare_block_package_requires_canonical_committed_attempt_bytes(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    case["attempt_path"].write_text(
        json.dumps(case["attempt"], indent=2),
        encoding="utf-8",
    )

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_lineage_invalid"
    assert not case["evaluation_root"].exists()


@pytest.mark.parametrize("drift", ["sequence", "command", "opaque-label"])
def test_prepare_block_package_rejects_attempt_lineage_before_publication(
    tmp_path: Path,
    drift: str,
) -> None:
    from orchestrator.experiments._pilot_evidence import PilotEvidenceError

    case = _case(tmp_path)
    if drift == "sequence":
        case["attempt"]["sequence_index"] = 1
    elif drift == "command":
        case["attempt"]["treatment_executions"][0][
            "command_digest"
        ] = _sha256(b"foreign-command")
    else:
        source = case["products"]["DIRECT"]
        destination = source.parents[1] / "foreign-label" / "workspace"
        destination.parent.mkdir()
        source.rename(destination)
        case["attempt"]["treatment_executions"][0][
            "opaque_arm_label"
        ] = "foreign-label"
    _save_attempt(case)

    with pytest.raises(PilotEvidenceError) as caught:
        _prepare(case)

    assert caught.value.code == "pilot_evidence_lineage_invalid"
    assert not case["evaluation_root"].exists()
    assert not (
        case["evidence_root"]
        / f"live-001/{case['labels']['DIRECT']}/hidden-evaluator.json"
    ).exists()


def test_prepare_block_package_rejects_work_root_symlink_alias(
    tmp_path: Path,
) -> None:
    from orchestrator.experiments._pilot_evidence import (
        PilotEvidenceError,
        prepare_block_package,
    )

    case = _case(tmp_path)
    alias = tmp_path / "work-alias"
    alias.symlink_to(case["work_root"], target_is_directory=True)

    with pytest.raises(PilotEvidenceError) as caught:
        prepare_block_package(
            lock=case["lock"],
            attempt=case["attempt"],
            work_root=alias,
            evaluation_root=case["evaluation_root"],
            package_root=case["package_root"],
        )

    assert caught.value.code == "pilot_evidence_root_invalid"


@pytest.mark.parametrize("drifting_root", ["evaluation", "package"])
def test_prepare_block_package_rejects_overlapping_caller_roots(
    tmp_path: Path,
    drifting_root: str,
) -> None:
    from orchestrator.experiments._pilot_evidence import (
        PilotEvidenceError,
        prepare_block_package,
    )

    case = _case(tmp_path)
    evaluation_root = case["evaluation_root"]
    package_root = case["package_root"]
    if drifting_root == "evaluation":
        evaluation_root = case["evidence_root"] / "evaluation-copy"
    else:
        package_root = evaluation_root / "package"

    with pytest.raises(PilotEvidenceError) as caught:
        prepare_block_package(
            lock=case["lock"],
            attempt=case["attempt"],
            work_root=case["work_root"],
            evaluation_root=evaluation_root,
            package_root=package_root,
        )

    assert caught.value.code == "pilot_evidence_root_overlap"
