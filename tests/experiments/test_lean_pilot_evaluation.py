from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import orchestrator.experiments.evaluation as evaluation_module
from orchestrator.demo.evaluators import linear_classifier
from orchestrator.experiments._evaluation_ingest import _validate_citation
from orchestrator.experiments.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.experiments.evaluation import (
    EvaluationError,
    _diff_bytes,
    build_blind_packages,
    build_calibration_packages,
    ingest_review,
    validate_calibration,
)
from orchestrator.experiments.workspace import freeze_product


ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "examples" / "demo_task_linear_classifier_port"
REFERENCE_PATCH = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "lean_pilot"
    / "calibration"
    / "a0-reference.patch"
)
RUBRIC = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "lean_pilot"
    / "reviewers"
    / "rubric.md"
)


def test_evaluation_facade_and_private_modules_stay_bounded() -> None:
    facade = Path(evaluation_module.__file__)
    production_modules = [facade, *facade.parent.glob("_evaluation*.py")]

    assert evaluation_module._diff_bytes is _diff_bytes
    assert {
        "EvaluationError",
        "build_blind_packages",
        "build_calibration_packages",
        "validate_calibration",
        "ingest_review",
    }.issubset(vars(evaluation_module))
    assert {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in production_modules
    } == {
        path.name: line_count
        for path in production_modules
        if (line_count := len(path.read_text(encoding="utf-8").splitlines())) <= 500
    }


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _bundle_digest(
    manifest: list[dict[str, str]],
    paths: list[str],
) -> str:
    by_path = {entry["path"]: entry for entry in manifest}
    return canonical_sha256(
        [by_path[path] for path in sorted(paths, key=str.encode)]
    )


def _write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def _live_inputs(
    tmp_path: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    Path,
    dict[str, Path],
    Path,
    Path,
]:
    base_root = tmp_path / "base"
    _write(base_root / "task.md", "Implement the requested behavior.\n")
    _write(base_root / "result.txt", "base\n")
    _write(base_root / "not-selected.txt", "controller-only source detail\n")

    product_roots: dict[str, Path] = {}
    for index, (treatment_id, value) in enumerate((
        ("DIRECT", "implementation one\n"),
        ("COORDINATOR", "implementation two\n"),
        ("ORC", "implementation three\n"),
    ), start=1):
        root = tmp_path / f"product-{treatment_id.lower()}"
        shutil.copytree(base_root, root)
        _write(root / "result.txt", value, mode=0o640)
        _write(root / "not-selected.txt", f"candidate detail {index}\n")
        product_roots[treatment_id] = root

    controller_root = (tmp_path / "evidence").resolve()
    for block_id in ("smoke-001", "live-001"):
        for index in range(1, 4):
            _write(
                controller_root
                / block_id
                / f"arm-{index}"
                / "check-stdout.txt",
                "PASS\n",
            )

    apparatus_root = (tmp_path / "control").resolve()
    apparatus_assets = {
        "tasks/A1.md": "Implement the requested behavior.\n",
        "providers.json": "providers",
        "prompts.json": "prompts",
        "commands.json": "commands",
        "direct.json": "direct-command",
        "coordinator.json": "coordinator-command",
        "orc.json": "orc-command",
        "source.py": "shared-source",
        "review/rubric.md": "rubric",
        "review/calibration-seal.json": "calibration",
        "evaluation/config.json": "evaluator-config",
        "evaluation/evaluator.py": "evaluator",
        "review/reviewer-command.json": "reviewer-command",
        "review/review-result.schema.json": "review-schema",
    }
    for relative_path, contents in apparatus_assets.items():
        _write(apparatus_root / relative_path, contents)
    manifest = [
        {
            "path": relative_path,
            "sha256": _digest_bytes(contents.encode("utf-8")),
        }
        for relative_path, contents in apparatus_assets.items()
    ]
    output_root = tmp_path / "packages"
    command_digests = {
        treatment_id: _digest(f"{treatment_id.lower()}-command")
        for treatment_id in product_roots
    }
    task_digest = _digest_bytes((base_root / "task.md").read_bytes())
    provider_policy = {
        "family": "fixture",
        "model": "fixture-model",
        "reasoning_effort": "high",
        "tool_policy": "workspace-write-no-network",
        "timeout_milliseconds": 1000,
        "currency": "USD",
    }
    evaluator_paths = [
        "evaluation/config.json",
        "evaluation/evaluator.py",
    ]
    reviewer_command_paths = [
        "review/reviewer-command.json",
        "review/review-result.schema.json",
    ]
    treatment_asset_paths = [
        path
        for path in apparatus_assets
        if not path.startswith(("evaluation/", "review/"))
    ]
    repository_root = (tmp_path / "repository").resolve()
    repository_root.mkdir()
    lock = {
        "record_kind": "pilot_lock.v1",
        "pilot_id": "lean-pilot-001",
        "task": {
            "task_id": "A1",
            "source_path": "task.md",
            "profile_digest": _digest("pending-profile"),
            "brief_digest": task_digest,
        },
        "archive": {
            "repository_identity": "fixture/repository",
            "repository_root": repository_root.as_posix(),
            "revision_identity": f"commit:{'0' * 40}",
            "source_subtree_path": "fixture",
            "source_tree_identity": f"git-tree:{'1' * 40}",
            "archive_digest": freeze_product(base_root, ()).digest,
        },
        "provider_policy": provider_policy,
        "review": {
            "reviewer_ids": ["reviewer-1", "reviewer-2"],
            "disagreement_policy": "INDETERMINATE_ON_DISAGREEMENT",
            "selected_final_files": ["result.txt"],
            "permitted_check_evidence_names": ["check-stdout.txt"],
            "rubric_path": "review/rubric.md",
            "rubric_digest": _digest("rubric"),
            "calibration_evidence_path": "review/calibration-seal.json",
            "calibration_evidence_digest": _digest("calibration"),
            "evaluator": {
                "config_path": "evaluation/config.json",
                "asset_paths": evaluator_paths,
                "bundle_digest": _bundle_digest(manifest, evaluator_paths),
            },
            "reviewer_command": {
                "config_path": "review/reviewer-command.json",
                "asset_paths": reviewer_command_paths,
                "bundle_digest": _bundle_digest(
                    manifest,
                    reviewer_command_paths,
                ),
            },
        },
        "apparatus": {
            "control_root": apparatus_root.as_posix(),
            "asset_manifest": manifest,
            "treatment_asset_paths": treatment_asset_paths,
            "task_path": "tasks/A1.md",
            "provider_config_path": "providers.json",
            "prompt_config_path": "prompts.json",
            "command_config_path": "commands.json",
            "environment": {
                "identity": _digest("environment"),
                "allowed_keys": ["HOME", "PATH", "TMPDIR"],
                "credential_keys": [],
            },
            "visible_check": {
                "argv": ["python", "-m", "pytest", "-q"],
                "timeout_milliseconds": 1000,
            },
            "product_projection_exclusions": [],
            "maximum_start_skew_milliseconds": 500,
            "quiescence_grace_milliseconds": 500,
        },
        "randomization_seed": "fixed-seed",
        "evidence_root": controller_root.as_posix(),
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
                "treatment_id": treatment_id,
                "source_asset_paths": [
                    f"{treatment_id.lower()}.json",
                    "source.py",
                ],
                "source_digest": _bundle_digest(
                    manifest,
                    [f"{treatment_id.lower()}.json", "source.py"],
                ),
                "command_digest": command_digests[treatment_id],
                "command_config_path": f"{treatment_id.lower()}.json",
                "provider_call_bounds": {
                    "minimum": 1 if treatment_id == "DIRECT" else 3,
                    "maximum": 1 if treatment_id == "DIRECT" else 9,
                },
            }
            for treatment_id in product_roots
        ],
    }
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
    block = {
        "record_kind": "block_attempt.v1",
        "pilot_lock_digest": canonical_sha256(lock),
        "attempt_class": "LIVE",
        "sequence_index": 0,
        "block_id": "live-001",
        "status": "VALID",
        "treatment_executions": [
            {
                "opaque_arm_label": f"arm-{index}",
                "treatment_id": treatment_id,
                "command_digest": command_digests[treatment_id],
                "lifecycle_outcome": "COMPLETED",
                "product_frozen": True,
                "product_manifest_digest": freeze_product(
                    product_roots[treatment_id], ()
                ).digest,
                "provider_call_count": 1 if treatment_id == "DIRECT" else 3,
                "elapsed_milliseconds": 100,
                "evidence_references": [
                    f"live-001/arm-{index}/check-stdout.txt"
                ],
                "token_counts": "UNKNOWN",
                "cost": "UNKNOWN",
            }
            for index, treatment_id in enumerate(
                ("DIRECT", "COORDINATOR", "ORC"), start=1
            )
        ],
    }
    return (
        lock,
        block,
        base_root,
        product_roots,
        output_root,
        controller_root,
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _locked_selected_files(
    lock: dict[str, Any],
    product_roots: dict[str, Path],
) -> dict[str, tuple[str, ...]]:
    selected = tuple(lock["review"]["selected_final_files"])
    return {treatment_id: selected for treatment_id in product_roots}


def _locked_check_evidence(
    lock: dict[str, Any],
    block: dict[str, Any],
) -> dict[str, tuple[str, ...]]:
    names = tuple(lock["review"]["permitted_check_evidence_names"])
    return {
        execution["treatment_id"]: tuple(
            f"{block['block_id']}/{execution['opaque_arm_label']}/{name}"
            for name in names
        )
        for execution in block["treatment_executions"]
    }


def test_build_blind_packages_is_deterministic_and_contains_only_allowlisted_evidence(
    tmp_path: Path,
) -> None:
    (
        lock,
        block,
        base_root,
        product_roots,
        output_root,
        controller_root,
    ) = _live_inputs(tmp_path)
    selected = _locked_selected_files(lock, product_roots)
    checks = _locked_check_evidence(lock, block)

    packages = build_blind_packages(
        lock=lock,
        block=block,
        base_root=base_root,
        product_roots=product_roots,
        task_path=lock["apparatus"]["task_path"],
        selected_final_files=selected,
        permitted_check_evidence=checks,
        output_root=output_root,
        controller_root=controller_root,
    )

    assert set(packages) == {"live-001"}
    package_root = packages["live-001"]
    manifest = json.loads(
        (package_root / "manifest.json").read_text(encoding="utf-8")
    )
    labels = manifest["candidate_labels"]
    assert len(labels) == 3
    assert len(set(labels)) == 3
    assert manifest["package_id"] == "live-001"
    assert manifest["task_path"] == "task.md"
    assert set(manifest) == {
        "candidate_labels",
        "files",
        "package_id",
        "task_path",
    }

    payload_paths = {entry["path"] for entry in manifest["files"]}
    assert "task.md" in payload_paths
    for label in labels:
            assert f"candidates/{label}/diff.patch" in payload_paths
            assert f"candidates/{label}/files/result.txt" in payload_paths
            assert (
                f"candidates/{label}/checks/check-001-check-stdout.txt"
                in payload_paths
            )
    assert not any("not-selected" in path for path in payload_paths)
    diff_text = b"\n".join(
        (package_root / f"candidates/{label}/diff.patch").read_bytes()
        for label in labels
    )
    assert b"not-selected.txt" in diff_text

    for entry in manifest["files"]:
        path = package_root / entry["path"]
        identity = path.stat()
        assert entry == {
            "path": entry["path"],
            "mode": identity.st_mode & 0o777,
            "size": identity.st_size,
            "sha256": _digest_bytes(path.read_bytes()),
        }

    reviewer_bytes = b"\n".join(_snapshot(package_root).values()).lower()
    for forbidden in (
        b"direct",
        b"coordinator",
        b"orc",
        b"provider_call_count",
        b"elapsed_milliseconds",
        b"cost_microunits",
        b"prompt",
        b"transcript",
        b"label-map",
    ):
        assert forbidden not in reviewer_bytes

    mapping_path = controller_root / "label-maps" / "live-001.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    assert set(mapping["packages"]["live-001"]["labels"].values()) == {
        "DIRECT",
        "COORDINATOR",
        "ORC",
    }
    assert not (package_root / "label-map.json").exists()

    (
        lock_2,
        block_2,
        base_root_2,
        product_roots_2,
        output_root_2,
        controller_root_2,
    ) = _live_inputs(tmp_path / "repeat")
    repeated = build_blind_packages(
        lock=lock_2,
        block=block_2,
        base_root=base_root_2,
        product_roots=product_roots_2,
        task_path=lock_2["apparatus"]["task_path"],
        selected_final_files=_locked_selected_files(lock_2, product_roots_2),
        permitted_check_evidence=_locked_check_evidence(lock_2, block_2),
        output_root=output_root_2,
        controller_root=controller_root_2,
    )
    assert _snapshot(package_root) == _snapshot(repeated["live-001"])
    assert json.loads(
        mapping_path.read_text(encoding="utf-8")
    )["packages"] == json.loads(
        (controller_root_2 / "label-maps" / "live-001.json").read_text(
            encoding="utf-8"
        )
    )["packages"]


def test_build_blind_packages_retains_one_controller_map_per_block(
    tmp_path: Path,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    second_block = copy.deepcopy(block)
    second_block["sequence_index"] = 1
    second_block["block_id"] = "live-002"
    for execution in second_block["treatment_executions"]:
        arm = execution["opaque_arm_label"]
        evidence_path = f"live-002/{arm}/check-stdout.txt"
        _write(controller / evidence_path, "PASS\n")
        execution["evidence_references"] = [evidence_path]

    first_packages = build_blind_packages(
        lock=lock,
        block=block,
        base_root=base,
        product_roots=products,
        task_path=lock["apparatus"]["task_path"],
        selected_final_files=_locked_selected_files(lock, products),
        permitted_check_evidence=_locked_check_evidence(lock, block),
        output_root=output,
        controller_root=controller,
    )
    second_packages = build_blind_packages(
        lock=lock,
        block=second_block,
        base_root=base,
        product_roots=products,
        task_path=lock["apparatus"]["task_path"],
        selected_final_files=_locked_selected_files(lock, products),
        permitted_check_evidence=_locked_check_evidence(lock, second_block),
        output_root=tmp_path / "packages-2",
        controller_root=controller,
    )

    assert set(first_packages) == {"live-001"}
    assert set(second_packages) == {"live-002"}
    first_mapping = json.loads(
        (controller / "label-maps" / "live-001.json").read_text(
            encoding="utf-8"
        )
    )
    second_mapping = json.loads(
        (controller / "label-maps" / "live-002.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(first_mapping["packages"]) == {"live-001"}
    assert set(second_mapping["packages"]) == {"live-002"}


def test_build_blind_packages_rejects_existing_controller_map_without_mutation(
    tmp_path: Path,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    mapping_path = controller / "label-maps" / "live-001.json"
    original = b"existing-controller-map\n"
    mapping_path.parent.mkdir()
    mapping_path.write_bytes(original)

    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=_locked_selected_files(lock, products),
            permitted_check_evidence=_locked_check_evidence(lock, block),
            output_root=output,
            controller_root=controller,
        )

    assert caught.value.code == "evaluation_output_exists"
    assert mapping_path.read_bytes() == original


def test_build_blind_packages_rejects_controller_map_directory(
    tmp_path: Path,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    mapping_path = controller / "label-maps" / "live-001.json"
    mapping_path.mkdir(parents=True)

    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=_locked_selected_files(lock, products),
            permitted_check_evidence=_locked_check_evidence(lock, block),
            output_root=output,
            controller_root=controller,
        )

    assert caught.value.code == "evaluation_output_exists"
    assert mapping_path.is_dir()


def test_build_blind_packages_rejects_controller_map_symlink_without_following(
    tmp_path: Path,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    external = tmp_path / "external-controller-map.json"
    original = b"external-controller-state\n"
    external.write_bytes(original)
    mapping_path = controller / "label-maps" / "live-001.json"
    mapping_path.parent.mkdir()
    mapping_path.symlink_to(external)

    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=_locked_selected_files(lock, products),
            permitted_check_evidence=_locked_check_evidence(lock, block),
            output_root=output,
            controller_root=controller,
        )

    assert caught.value.code == "evaluation_output_exists"
    assert mapping_path.is_symlink()
    assert external.read_bytes() == original


@pytest.mark.parametrize(
    "mutation",
    ["selected_files", "check_evidence", "evidence_root"],
)
def test_build_blind_packages_rejects_caller_allowlist_or_evidence_root_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    selected = _locked_selected_files(lock, products)
    checks = _locked_check_evidence(lock, block)
    supplied_controller = controller
    if mutation == "selected_files":
        selected = {
            treatment_id: ("not-selected.txt",)
            for treatment_id in products
        }
    elif mutation == "check_evidence":
        _write(controller / "unlocked-check.txt", "PASS\n")
        checks = {
            treatment_id: ("unlocked-check.txt",)
            for treatment_id in products
        }
    else:
        supplied_controller = (tmp_path / "different-evidence").resolve()
        for paths in checks.values():
            for relative_path in paths:
                _write(supplied_controller / relative_path, "PASS\n")

    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=selected,
            permitted_check_evidence=checks,
            output_root=output,
            controller_root=supplied_controller,
        )

    assert caught.value.code == "evaluation_product_binding_invalid"


@pytest.mark.parametrize(
    "overlap_name",
    ["base", "product", "output", "evidence"],
)
def test_build_blind_packages_rejects_apparatus_root_overlap(
    tmp_path: Path,
    overlap_name: str,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    overlap_roots = {
        "base": base,
        "product": products["DIRECT"],
        "output": output,
        "evidence": controller,
    }
    if overlap_name == "output":
        output.mkdir()
    lock["apparatus"]["control_root"] = overlap_roots[
        overlap_name
    ].resolve().as_posix()
    block["pilot_lock_digest"] = canonical_sha256(lock)

    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=_locked_selected_files(lock, products),
            permitted_check_evidence=_locked_check_evidence(lock, block),
            output_root=output,
            controller_root=controller,
        )

    assert caught.value.code == "evaluation_root_overlap"


def test_build_blind_packages_rejects_lock_block_or_frozen_product_drift(
    tmp_path: Path,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    products["DIRECT"].joinpath("late.txt").write_text("drift\n", encoding="utf-8")

    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=_locked_selected_files(lock, products),
            permitted_check_evidence=_locked_check_evidence(lock, block),
            output_root=output,
            controller_root=controller,
        )

    assert caught.value.code == "evaluation_product_manifest_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("command_digest", "evaluation_command_digest_mismatch"),
        ("block_id", "evaluation_block_identity_mismatch"),
        ("base_tree", "evaluation_archive_digest_mismatch"),
    ],
)
def test_build_blind_packages_requires_exact_live_execution_lineage(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    if mutation == "command_digest":
        block["treatment_executions"][0]["command_digest"] = _digest(
            "different-command"
        )
    elif mutation == "block_id":
        block["block_id"] = "live-002"
    else:
        _write(base / "late-base-drift.txt", "not in the locked archive\n")

    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=_locked_selected_files(lock, products),
            permitted_check_evidence=_locked_check_evidence(lock, block),
            output_root=output,
            controller_root=controller,
        )

    assert caught.value.code == expected_code


def test_build_blind_packages_accepts_the_locked_valid_smoke_lineage(
    tmp_path: Path,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    block["attempt_class"] = "SMOKE"
    block["block_id"] = lock["smoke_id"]
    block["sequence_index"] = 0

    packages = build_blind_packages(
        lock=lock,
        block=block,
        base_root=base,
        product_roots=products,
        task_path=lock["apparatus"]["task_path"],
        selected_final_files=_locked_selected_files(lock, products),
        permitted_check_evidence=_locked_check_evidence(lock, block),
        output_root=output,
        controller_root=controller,
    )

    assert set(packages) == {lock["smoke_id"]}


def test_build_blind_packages_fails_closed_on_identity_in_full_diff(
    tmp_path: Path,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    _write(products["DIRECT"] / "not-selected.txt", "secret DIRECT\n")
    block["treatment_executions"][0]["product_manifest_digest"] = freeze_product(
        products["DIRECT"], ()
    ).digest
    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=_locked_selected_files(lock, products),
            permitted_check_evidence=_locked_check_evidence(lock, block),
            output_root=output,
            controller_root=controller,
        )
    assert caught.value.code == "evaluation_blinding_violation"


def test_build_blind_packages_does_not_treat_lowercase_domain_prose_as_identity(
    tmp_path: Path,
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    _write(
        products["DIRECT"] / "not-selected.txt",
        "Model the direct beam without clipping.\n",
    )
    block["treatment_executions"][0]["product_manifest_digest"] = freeze_product(
        products["DIRECT"], ()
    ).digest

    packages = build_blind_packages(
        lock=lock,
        block=block,
        base_root=base,
        product_roots=products,
        task_path=lock["apparatus"]["task_path"],
        selected_final_files=_locked_selected_files(lock, products),
        permitted_check_evidence=_locked_check_evidence(lock, block),
        output_root=output,
        controller_root=controller,
    )

    assert set(packages) == {"live-001"}


@pytest.mark.parametrize("unsafe_id", ["../escape", "/absolute", ".", "a/b"])
def test_build_blind_packages_rejects_unsafe_block_id(
    tmp_path: Path, unsafe_id: str
) -> None:
    lock, block, base, products, output, controller = _live_inputs(tmp_path)
    block["block_id"] = unsafe_id
    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base,
            product_roots=products,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=_locked_selected_files(lock, products),
            permitted_check_evidence=_locked_check_evidence(lock, block),
            output_root=output,
            controller_root=controller,
        )
    assert caught.value.code == "evaluation_id_invalid"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("selected_escape", "evaluation_path_invalid"),
        ("check_absolute", "evaluation_path_invalid"),
        ("selected_duplicate", "evaluation_product_binding_invalid"),
        ("check_duplicate", "evaluation_product_binding_invalid"),
        ("selected_nul", "evaluation_path_invalid"),
        ("overlap_output", "evaluation_root_overlap"),
        ("unknown_product", "evaluation_product_binding_invalid"),
    ],
)
def test_build_blind_packages_rejects_unsafe_or_incomplete_explicit_inputs(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    (
        lock,
        block,
        base_root,
        product_roots,
        output_root,
        controller_root,
    ) = _live_inputs(tmp_path)
    selected = _locked_selected_files(lock, product_roots)
    checks = _locked_check_evidence(lock, block)
    if mutation == "selected_escape":
        selected["DIRECT"] = ("../not-selected.txt",)
    elif mutation == "check_absolute":
        checks["DIRECT"] = (str((controller_root / "x").resolve()),)
    elif mutation == "selected_duplicate":
        selected["DIRECT"] = ("result.txt", "result.txt")
    elif mutation == "check_duplicate":
        locked_path = checks["DIRECT"][0]
        checks["DIRECT"] = (
            locked_path,
            locked_path,
        )
    elif mutation == "selected_nul":
        selected["DIRECT"] = ("result.txt\x00suffix",)
    elif mutation == "overlap_output":
        output_root = product_roots["DIRECT"] / "packages"
    else:
        product_roots["UNLOCKED"] = product_roots.pop("DIRECT")

    with pytest.raises(EvaluationError) as caught:
        build_blind_packages(
            lock=lock,
            block=block,
            base_root=base_root,
            product_roots=product_roots,
            task_path=lock["apparatus"]["task_path"],
            selected_final_files=selected,
            permitted_check_evidence=checks,
            output_root=output_root,
            controller_root=controller_root,
        )

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_fragments"),
    [
        ("added", (b"added.txt", b"--- metadata null", b"+added")),
        ("deleted", (b"removed.txt", b"+++ metadata null", b"-removed")),
        ("mode", (b"mode.txt", b'"mode":420', b'"mode":384')),
        ("type", (b"type-entry", b'"kind":"file"', b'"kind":"directory"')),
        (
            "symlink_target",
            (b"link-entry", b'"link_target":"target-a"', b'"link_target":"target-b"'),
        ),
    ],
)
def test_full_tree_diff_preserves_every_structural_change(
    tmp_path: Path,
    mutation: str,
    expected_fragments: tuple[bytes, ...],
) -> None:
    base = tmp_path / "base"
    _write(base / "removed.txt", "removed\n")
    _write(base / "mode.txt", "same\n")
    _write(base / "type-entry", "file before\n")
    _write(base / "target-a", "a\n")
    _write(base / "target-b", "b\n")
    os.symlink("target-a", base / "link-entry")
    product = tmp_path / "product"
    shutil.copytree(base, product, symlinks=True)
    if mutation == "added":
        _write(product / "added.txt", "added\n")
    elif mutation == "deleted":
        (product / "removed.txt").unlink()
    elif mutation == "mode":
        (product / "mode.txt").chmod(0o600)
    elif mutation == "type":
        (product / "type-entry").unlink()
        (product / "type-entry").mkdir()
    else:
        (product / "link-entry").unlink()
        os.symlink("target-b", product / "link-entry")

    diff = _diff_bytes(
        base_root=base,
        product_root=product,
        excluded_roots=(),
    )

    for fragment in expected_fragments:
        assert fragment in diff


def _calibration_lock(
    *,
    base_root: Path | None = None,
    environment: dict[str, str] | None = None,
    round_number: int = 1,
    revision: int = 0,
) -> dict[str, Any]:
    base_root = base_root or SEED
    environment = environment or {}
    projection_exclusions = ("rust/target", "src_py/__pycache__")
    lock: dict[str, Any] = {
        "schema_version": "calibration-lock.v1",
        "calibration_id": "a0-round",
        "round": round_number,
        "revision": revision,
        "product_projection_exclusions": list(projection_exclusions),
        "base_identity": _calibration_base_identity(
            base_root,
            projection_exclusions,
        ),
        "task": {
            "path": "docs/tasks/port_linear_classifier_to_rust.md",
            "digest": _digest_bytes(
                (
                    base_root
                    / "docs/tasks/port_linear_classifier_to_rust.md"
                ).read_bytes()
            ),
        },
        "reference_patch": {
            "path": "calibration/a0-reference.patch",
            "digest": _digest_bytes(REFERENCE_PATCH.read_bytes()),
        },
        "rubric": {
            "path": "reviewers/rubric.md",
            "digest": _digest_bytes(RUBRIC.read_bytes()),
        },
        "selected_final_files": [
            "rust/src/lib.rs",
            "rust/tests/smoke_linear_classifier.rs",
        ],
        "evaluator": {
            "module_digest": _digest_bytes(
                Path(linear_classifier.__file__).read_bytes()
            ),
            "class": "linear_classifier",
        },
        "oracle": {
            "digest": _digest_bytes(
                (base_root / "src_py/linear_classifier.py").read_bytes()
            ),
        },
        "environment_identity": canonical_sha256(
            [[key, environment[key]] for key in sorted(environment)]
        ),
        "reviewer_execution": _reviewer_execution(),
        "visible_check": {
            "argv": [
                "cargo",
                "test",
                "--quiet",
                "--manifest-path",
                "rust/Cargo.toml",
            ],
            "timeout_milliseconds": 300_000,
            "class": "A0_VISIBLE",
        },
        "hidden_evaluator_class": "A0_LINEAR_CLASSIFIER",
        "expected_contrast": {
            "base_visible": "FAIL",
            "reference_visible": "PASS",
            "base_hidden": "FAIL",
            "reference_hidden": "PASS",
        },
        "reviewer_ids": ["reviewer-1", "reviewer-2"],
        "package_ids": [
            "calibration-direction-1",
            "calibration-direction-2",
            "calibration-identity",
        ],
        "mapping_seed": "a0-fixed-mapping-seed",
    }
    if round_number == 2:
        predecessor = _calibration_lock(
            base_root=base_root,
            environment=environment,
        )
        lock["predecessor"] = {
            "lock_digest": canonical_sha256(predecessor),
            "status": "FAILED",
        }
    return lock


def _calibration_base_identity(
    base_root: Path,
    projection_exclusions: tuple[str, ...] = (
        "rust/target",
        "src_py/__pycache__",
    ),
) -> dict[str, str]:
    return {
        "repository_identity": "example:demo_task_linear_classifier_port",
        "revision_identity": "source-tree:2026-07-26-a0",
        "archive_digest": freeze_product(base_root, ()).digest,
        "product_manifest_digest": freeze_product(
            base_root,
            tuple(Path(value) for value in projection_exclusions),
        ).digest,
    }


def _reviewer_execution() -> dict[str, Any]:
    entry = Path("/bin/true").resolve(strict=True)
    return {
        "provider_family": "fixture-provider",
        "model": "fixture-model",
        "reasoning_effort": "high",
        "tool_policy": "read-only-package",
        "timeout_milliseconds": 120_000,
        "cli": {
            "entry_path": entry.as_posix(),
            "entry_sha256": _digest_bytes(entry.read_bytes()),
            "version": "fixture-true-v1",
        },
        "environment": {
            "identity": _digest("reviewer-environment"),
            "allowed_keys": ["HOME", "PATH", "TMPDIR"],
            "credential_keys": [],
        },
        "invocation_payload_schema_digest": _digest(
            "reviewer-invocation-payload-v1"
        ),
    }


def test_build_calibration_packages_proves_real_a0_reference_and_binds_controller_evidence(
    tmp_path: Path,
) -> None:
    base_root = tmp_path / "a0-base"
    shutil.copytree(SEED, base_root)
    output_root = tmp_path / "packages"
    controller_root = tmp_path / "controller"
    environment = dict(os.environ)

    calibration_lock = _calibration_lock(
        base_root=base_root,
        environment=environment,
    )
    packages = build_calibration_packages(
        calibration_lock=calibration_lock,
        base_identity=calibration_lock["base_identity"],
        predecessor_lock=None,
        predecessor_controller_mapping=None,
        predecessor_controller_root=None,
        predecessor_reviews=None,
        base_root=base_root,
        task_path="docs/tasks/port_linear_classifier_to_rust.md",
        reference_patch=REFERENCE_PATCH,
        rubric_path=RUBRIC,
        selected_final_files=(
            "rust/src/lib.rs",
            "rust/tests/smoke_linear_classifier.rs",
        ),
        visible_check_argv=(
            "cargo",
            "test",
            "--quiet",
            "--manifest-path",
            "rust/Cargo.toml",
        ),
        visible_check_timeout_milliseconds=300_000,
        visible_check_class="A0_VISIBLE",
        hidden_evaluator_class="A0_LINEAR_CLASSIFIER",
        evaluator_module=linear_classifier,
        oracle_path=base_root / "src_py" / "linear_classifier.py",
        environment=environment,
        reviewer_execution=_reviewer_execution(),
        output_root=output_root,
        controller_root=controller_root,
    )

    assert set(packages) == set(calibration_lock["package_ids"])
    mapping = json.loads(
        (controller_root / "controller-mapping.json").read_text(
            encoding="utf-8"
        )
    )
    assert mapping["evaluation"]["visible_check"]["argv"] == [
        "cargo",
        "test",
        "--quiet",
        "--manifest-path",
        "rust/Cargo.toml",
    ]
    assert mapping["evaluation"]["base"] == {
        "visible_check": "FAIL",
        "hidden_evaluator": "FAIL",
    }
    assert mapping["evaluation"]["reference"] == {
        "visible_check": "PASS",
        "hidden_evaluator": "PASS",
    }
    assert mapping["bindings"]["evaluator_module"]["sha256"] == _digest_bytes(
        Path(linear_classifier.__file__).read_bytes()
    )
    assert mapping["bindings"]["oracle_module"]["sha256"] == _digest_bytes(
        (base_root / "src_py" / "linear_classifier.py").read_bytes()
    )
    assert mapping["bindings"]["environment_identity"] == canonical_sha256(
        [[key, environment[key]] for key in sorted(environment)]
    )
    assert mapping["bindings"]["reference_patch"]["sha256"] == _digest_bytes(
        REFERENCE_PATCH.read_bytes()
    )
    assert mapping["reviewer_execution"] == calibration_lock[
        "reviewer_execution"
    ]
    assert mapping["bindings"]["reviewer_cli_entry"]["sha256"] == (
        calibration_lock["reviewer_execution"]["cli"]["entry_sha256"]
    )
    for binding in mapping["bindings"].values():
        if isinstance(binding, dict) and "evidence_path" in binding:
            bound = controller_root / binding["evidence_path"]
            assert bound.is_file()
            assert _digest_bytes(bound.read_bytes()) == binding["sha256"]

    first = mapping["packages"]["calibration-direction-1"]["labels"]
    second = mapping["packages"]["calibration-direction-2"]["labels"]
    identity = mapping["packages"]["calibration-identity"]["labels"]
    assert set(first) == set(second)
    assert all(first[label] != second[label] for label in first)
    assert set(first.values()) == {"BASE", "REFERENCE"}
    assert set(second.values()) == {"BASE", "REFERENCE"}
    assert set(identity.values()) == {"REFERENCE"}

    snapshots = {package_id: _snapshot(path) for package_id, path in packages.items()}
    first_manifest = json.loads(
        snapshots["calibration-direction-1"]["manifest.json"]
    )
    second_manifest = json.loads(
        snapshots["calibration-direction-2"]["manifest.json"]
    )
    first_labels = first_manifest["candidate_labels"]
    second_labels = second_manifest["candidate_labels"]
    assert first_labels == second_labels
    for label in first_labels:
        role_first = first[label]
        role_second = second[label]
        first_file = snapshots["calibration-direction-1"][
            f"candidates/{label}/files/rust/src/lib.rs"
        ]
        second_file = snapshots["calibration-direction-2"][
            f"candidates/{label}/files/rust/src/lib.rs"
        ]
        assert (first_file == second_file) is (role_first == role_second)

    identity_labels = json.loads(
        snapshots["calibration-identity"]["manifest.json"]
    )["candidate_labels"]
    assert (
        snapshots["calibration-identity"][
            f"candidates/{identity_labels[0]}/files/rust/src/lib.rs"
        ]
        == snapshots["calibration-identity"][
            f"candidates/{identity_labels[1]}/files/rust/src/lib.rs"
        ]
    )

    for package_root in packages.values():
        package_bytes = b"\n".join(_snapshot(package_root).values())
        assert canonical_json_bytes(mapping) not in package_bytes
        assert b"controller-mapping" not in package_bytes
        assert b"A1" not in package_bytes
        assert str(base_root).encode("utf-8") not in package_bytes
        assert str(controller_root).encode("utf-8") not in package_bytes
        assert str(output_root).encode("utf-8") not in package_bytes


def _calibration_mapping(
    lock: dict[str, Any] | None = None,
    *,
    controller_root: Path,
) -> dict[str, Any]:
    lock = lock or _calibration_lock()
    controller_root.mkdir(parents=True)

    def file_binding(relative: str, data: bytes) -> dict[str, Any]:
        path = controller_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o640)
        return {
            "evidence_path": relative,
            "mode": 0o640,
            "size": len(data),
            "sha256": _digest_bytes(data),
        }

    raw_base = canonical_json_bytes({"verdict": "FAIL"})
    raw_reference = canonical_json_bytes({"verdict": "PASS"})
    mapping = {
        "calibration_id": "a0-round",
        "calibration_lock_digest": canonical_sha256(lock),
        "bindings": {
            "evaluator_module": file_binding(
                "bindings/evaluator-module.py",
                Path(linear_classifier.__file__).read_bytes(),
            ),
            "oracle_module": file_binding(
                "bindings/oracle-module.py",
                (SEED / "src_py/linear_classifier.py").read_bytes(),
            ),
            "reference_patch": file_binding(
                "bindings/reference.patch",
                REFERENCE_PATCH.read_bytes(),
            ),
            "rubric": file_binding(
                "bindings/rubric.md",
                RUBRIC.read_bytes(),
            ),
            "reviewer_cli_entry": file_binding(
                "bindings/reviewer-cli-entry",
                Path(lock["reviewer_execution"]["cli"]["entry_path"]).read_bytes(),
            ),
            "environment_identity": lock["environment_identity"],
        },
        "evaluation": {
            "visible_check": copy.deepcopy(lock["visible_check"]),
            "hidden_evaluator_class": lock["hidden_evaluator_class"],
            "raw_evidence": {
                "base_hidden": file_binding(
                    "evaluation/raw-base-hidden.json",
                    raw_base,
                ),
                "reference_hidden": file_binding(
                    "evaluation/raw-reference-hidden.json",
                    raw_reference,
                ),
            },
            "base": {
                "visible_check": "FAIL",
                "hidden_evaluator": "FAIL",
            },
            "reference": {
                "visible_check": "PASS",
                "hidden_evaluator": "PASS",
            },
        },
        "packages": {
            "calibration-direction-1": {
                "manifest_digest": _digest("manifest-direction-1"),
                "candidate_labels": ["candidate-alpha", "candidate-beta"],
                "labels": {
                    "candidate-alpha": "REFERENCE",
                    "candidate-beta": "BASE",
                }
            },
            "calibration-direction-2": {
                "manifest_digest": _digest("manifest-direction-2"),
                "candidate_labels": ["candidate-alpha", "candidate-beta"],
                "labels": {
                    "candidate-alpha": "BASE",
                    "candidate-beta": "REFERENCE",
                }
            },
            "calibration-identity": {
                "manifest_digest": _digest("manifest-identity"),
                "candidate_labels": ["candidate-alpha", "candidate-beta"],
                "labels": {
                    "candidate-alpha": "REFERENCE",
                    "candidate-beta": "REFERENCE",
                }
            },
        },
        "review_bindings": {},
        "reviewer_execution": copy.deepcopy(lock["reviewer_execution"]),
    }
    for reviewer_id in ("reviewer-1", "reviewer-2"):
        for package_id in lock["package_ids"]:
            mapping["review_bindings"][
                f"{package_id}-{reviewer_id}"
            ] = {
                "package_id": package_id,
                "reviewer_id": reviewer_id,
                "rubric_digest": lock["rubric"]["digest"],
                "package_manifest_digest": mapping["packages"][package_id][
                    "manifest_digest"
                ],
            }
    (controller_root / "controller-mapping.json").write_bytes(
        canonical_json_bytes(mapping)
    )
    return mapping


def _calibration_reviews(
    lock: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    lock = lock or _calibration_lock()
    reviews: list[dict[str, Any]] = []
    winners = {
        "calibration-direction-1": "A",
        "calibration-direction-2": "B",
        "calibration-identity": "TIE",
    }
    for reviewer_index, reviewer_id in enumerate(("reviewer-1", "reviewer-2")):
        for package_index, package_id in enumerate(
            _calibration_lock()["package_ids"]
        ):
            reviews.append(
                {
                    "record_kind": "review_result.v1",
                    "review_id": f"{package_id}-{reviewer_id}",
                    "pilot_lock_digest": canonical_sha256(lock),
                    "reviewer_id": reviewer_id,
                    "session_id": (
                        f"session-{reviewer_index + 1}-{package_index + 1}"
                    ),
                    "review_class": "CALIBRATION",
                    "rubric_digest": lock["rubric"]["digest"],
                    "candidates": [
                        {
                            "opaque_label": "candidate-alpha",
                            "evidence_citations": [
                                "candidates/candidate-alpha/diff.patch"
                            ],
                            "dimension_assessments": _dimension_assessments(
                                "candidates/candidate-alpha/diff.patch"
                            ),
                            "sealed_treatment_guess": "UNKNOWN",
                        },
                        {
                            "opaque_label": "candidate-beta",
                            "evidence_citations": [
                                "candidates/candidate-beta/diff.patch"
                            ],
                            "dimension_assessments": _dimension_assessments(
                                "candidates/candidate-beta/diff.patch"
                            ),
                            "sealed_treatment_guess": "UNKNOWN",
                        },
                    ],
                    "pairwise_results": [
                        {
                            "candidate_a_label": "candidate-alpha",
                            "candidate_b_label": "candidate-beta",
                            "outcome": winners[package_id],
                            "rationale": "Evidence supports this outcome.",
                            "evidence_citations": [
                                "candidates/candidate-alpha/diff.patch",
                                "candidates/candidate-beta/diff.patch",
                            ],
                        }
                    ],
                }
            )
    return reviews


def _dimension_assessments(citation: str) -> list[dict[str, Any]]:
    return [
        {
            "dimension": dimension,
            "assessment": "PASS",
            "rationale": "The cited package evidence supports this assessment.",
            "evidence_citations": [citation],
        }
        for dimension in (
            "TASK_COMPLETENESS",
            "BEHAVIORAL_CORRECTNESS",
            "MAINTAINABILITY",
            "SCOPE_CONTROL",
            "EVIDENCE_QUALITY",
        )
    ]


def test_validate_calibration_accepts_exact_two_by_three_contract(
    tmp_path: Path,
) -> None:
    controller_root = tmp_path / "controller"
    validate_calibration(
        calibration_lock=_calibration_lock(),
        controller_mapping=_calibration_mapping(
            controller_root=controller_root,
        ),
        controller_root=controller_root,
        reviews=_calibration_reviews(),
        predecessor_lock=None,
        predecessor_controller_mapping=None,
        predecessor_controller_root=None,
        predecessor_reviews=None,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_bindings_object",
        "unknown_mapping_field",
        "missing_binding_file",
        "tampered_binding_file",
        "missing_package",
        "extra_review_binding",
    ],
)
def test_validate_calibration_seals_closed_mapping_and_bound_files(
    tmp_path: Path,
    mutation: str,
) -> None:
    lock = _calibration_lock()
    controller_root = tmp_path / "controller"
    mapping = _calibration_mapping(
        lock,
        controller_root=controller_root,
    )
    if mutation == "missing_bindings_object":
        mapping.pop("bindings")
    elif mutation == "unknown_mapping_field":
        mapping["unexpected"] = True
    elif mutation == "missing_binding_file":
        (controller_root / "bindings" / "rubric.md").unlink()
    elif mutation == "tampered_binding_file":
        (controller_root / "bindings" / "rubric.md").write_text(
            "tampered\n",
            encoding="utf-8",
        )
    elif mutation == "missing_package":
        mapping["packages"].pop(lock["package_ids"][0])
    else:
        mapping["review_bindings"]["extra-review"] = copy.deepcopy(
            next(iter(mapping["review_bindings"].values()))
        )
    if mutation not in {"missing_binding_file", "tampered_binding_file"}:
        (controller_root / "controller-mapping.json").write_bytes(
            canonical_json_bytes(mapping)
        )

    with pytest.raises(EvaluationError) as caught:
        validate_calibration(
            calibration_lock=lock,
            controller_mapping=mapping,
            controller_root=controller_root,
            reviews=_calibration_reviews(lock),
            predecessor_lock=None,
            predecessor_controller_mapping=None,
            predecessor_controller_root=None,
            predecessor_reviews=None,
        )

    assert caught.value.code == "calibration_mapping_mismatch"


def test_build_calibration_packages_rejects_prospective_lock_drift(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    shutil.copytree(SEED, base)
    environment = dict(os.environ)
    lock = _calibration_lock(base_root=base, environment=environment)
    lock["unexpected"] = True
    with pytest.raises(EvaluationError) as caught:
        build_calibration_packages(
            calibration_lock=lock,
            base_identity=lock["base_identity"],
            predecessor_lock=None,
            predecessor_controller_mapping=None,
            predecessor_controller_root=None,
            predecessor_reviews=None,
            base_root=base,
            task_path="docs/tasks/port_linear_classifier_to_rust.md",
            reference_patch=REFERENCE_PATCH,
            rubric_path=RUBRIC,
            selected_final_files=tuple(lock["selected_final_files"]),
            visible_check_argv=tuple(lock["visible_check"]["argv"]),
            visible_check_timeout_milliseconds=300_000,
            visible_check_class="A0_VISIBLE",
            hidden_evaluator_class="A0_LINEAR_CLASSIFIER",
            evaluator_module=linear_classifier,
            oracle_path=base / "src_py/linear_classifier.py",
            environment=environment,
            reviewer_execution=_reviewer_execution(),
            output_root=tmp_path / "packages",
            controller_root=tmp_path / "controller",
        )
    assert caught.value.code == "calibration_lock_invalid"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("caller_missing_field", "calibration_binding_invalid"),
        ("caller_identity_mismatch", "calibration_binding_invalid"),
        ("locked_missing_field", "calibration_lock_invalid"),
        ("actual_tree_drift", "calibration_binding_invalid"),
    ],
)
def test_build_calibration_packages_requires_closed_explicit_base_identity(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    base = tmp_path / "base"
    shutil.copytree(SEED, base)
    environment = dict(os.environ)
    lock = _calibration_lock(base_root=base, environment=environment)
    supplied = copy.deepcopy(lock["base_identity"])
    if mutation == "caller_missing_field":
        supplied.pop("revision_identity")
    elif mutation == "caller_identity_mismatch":
        supplied["repository_identity"] = "example:different-repository"
    elif mutation == "locked_missing_field":
        lock["base_identity"].pop("archive_digest")
        supplied = copy.deepcopy(lock["base_identity"])
    else:
        _write(base / "post-lock-drift.txt", "not in the frozen base\n")

    with pytest.raises(EvaluationError) as caught:
        build_calibration_packages(
            calibration_lock=lock,
            base_identity=supplied,
            predecessor_lock=None,
            predecessor_controller_mapping=None,
            predecessor_controller_root=None,
            predecessor_reviews=None,
            base_root=base,
            task_path="docs/tasks/port_linear_classifier_to_rust.md",
            reference_patch=REFERENCE_PATCH,
            rubric_path=RUBRIC,
            selected_final_files=tuple(lock["selected_final_files"]),
            visible_check_argv=tuple(lock["visible_check"]["argv"]),
            visible_check_timeout_milliseconds=300_000,
            visible_check_class="A0_VISIBLE",
            hidden_evaluator_class="A0_LINEAR_CLASSIFIER",
            evaluator_module=linear_classifier,
            oracle_path=base / "src_py/linear_classifier.py",
            environment=environment,
            reviewer_execution=_reviewer_execution(),
            output_root=tmp_path / "packages",
            controller_root=tmp_path / "controller",
        )

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("caller_model", "calibration_binding_invalid"),
        ("caller_cli_digest", "calibration_binding_invalid"),
        ("locked_cli_digest", "calibration_lock_invalid"),
        ("relative_cli_path", "calibration_lock_invalid"),
        ("zero_timeout", "calibration_lock_invalid"),
        ("ambient_key", "calibration_lock_invalid"),
        ("credential_not_allowed", "calibration_lock_invalid"),
    ],
)
def test_build_calibration_packages_rejects_unbound_reviewer_execution(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    base = tmp_path / "base"
    shutil.copytree(SEED, base)
    environment = dict(os.environ)
    lock = _calibration_lock(base_root=base, environment=environment)
    actual = copy.deepcopy(lock["reviewer_execution"])
    if mutation == "caller_model":
        actual["model"] = "unlocked-model"
    elif mutation == "caller_cli_digest":
        actual["cli"]["entry_sha256"] = _digest("wrong-caller-cli")
    elif mutation == "locked_cli_digest":
        lock["reviewer_execution"]["cli"]["entry_sha256"] = _digest(
            "wrong-cli"
        )
    elif mutation == "relative_cli_path":
        lock["reviewer_execution"]["cli"]["entry_path"] = "bin/reviewer"
        actual = copy.deepcopy(lock["reviewer_execution"])
    elif mutation == "zero_timeout":
        lock["reviewer_execution"]["timeout_milliseconds"] = 0
        actual = copy.deepcopy(lock["reviewer_execution"])
    elif mutation == "ambient_key":
        lock["reviewer_execution"]["environment"]["unexpected"] = True
        actual = copy.deepcopy(lock["reviewer_execution"])
    else:
        lock["reviewer_execution"]["environment"]["credential_keys"] = [
            "SECRET"
        ]
        actual = copy.deepcopy(lock["reviewer_execution"])

    with pytest.raises(EvaluationError) as caught:
        build_calibration_packages(
            calibration_lock=lock,
            base_identity=lock["base_identity"],
            predecessor_lock=None,
            predecessor_controller_mapping=None,
            predecessor_controller_root=None,
            predecessor_reviews=None,
            base_root=base,
            task_path="docs/tasks/port_linear_classifier_to_rust.md",
            reference_patch=REFERENCE_PATCH,
            rubric_path=RUBRIC,
            selected_final_files=tuple(lock["selected_final_files"]),
            visible_check_argv=tuple(lock["visible_check"]["argv"]),
            visible_check_timeout_milliseconds=300_000,
            visible_check_class="A0_VISIBLE",
            hidden_evaluator_class="A0_LINEAR_CLASSIFIER",
            evaluator_module=linear_classifier,
            oracle_path=base / "src_py/linear_classifier.py",
            environment=environment,
            reviewer_execution=actual,
            output_root=tmp_path / "packages",
            controller_root=tmp_path / "controller",
        )
    assert caught.value.code == expected_code


def _round_two_validation_inputs(
    tmp_path: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    Path,
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    Path,
    list[dict[str, Any]],
]:
    predecessor_lock = _calibration_lock()
    predecessor_controller_root = tmp_path / "predecessor-controller"
    predecessor_mapping = _calibration_mapping(
        predecessor_lock,
        controller_root=predecessor_controller_root,
    )
    predecessor_reviews = _calibration_reviews(predecessor_lock)
    predecessor_reviews[2]["pairwise_results"][0]["outcome"] = "A"
    current_lock = _calibration_lock(round_number=2, revision=1)
    current_controller_root = tmp_path / "current-controller"
    current_mapping = _calibration_mapping(
        current_lock,
        controller_root=current_controller_root,
    )
    current_reviews = _calibration_reviews(current_lock)
    return (
        predecessor_lock,
        predecessor_mapping,
        predecessor_controller_root,
        predecessor_reviews,
        current_lock,
        current_mapping,
        current_controller_root,
        current_reviews,
    )


def test_validate_round_two_accepts_genuine_substantive_failed_predecessor(
    tmp_path: Path,
) -> None:
    (
        predecessor_lock,
        predecessor_mapping,
        predecessor_root,
        predecessor_reviews,
        current_lock,
        current_mapping,
        current_root,
        current_reviews,
    ) = _round_two_validation_inputs(tmp_path)

    validate_calibration(
        calibration_lock=current_lock,
        controller_mapping=current_mapping,
        controller_root=current_root,
        reviews=current_reviews,
        predecessor_lock=predecessor_lock,
        predecessor_controller_mapping=predecessor_mapping,
        predecessor_controller_root=predecessor_root,
        predecessor_reviews=predecessor_reviews,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "absent",
        "digest_mismatch",
        "passing_predecessor",
        "malformed_mapping",
        "role_semantics",
        "non_substantive_failure",
    ],
)
def test_validate_round_two_rejects_unproved_predecessor(
    tmp_path: Path,
    mutation: str,
) -> None:
    (
        predecessor_lock,
        predecessor_mapping,
        predecessor_root,
        predecessor_reviews,
        current_lock,
        _current_mapping,
        _current_root,
        current_reviews,
    ) = _round_two_validation_inputs(tmp_path)
    if mutation == "absent":
        predecessor_lock = None
        predecessor_mapping = None
        predecessor_root = None
        predecessor_reviews = None
    elif mutation == "digest_mismatch":
        current_lock["predecessor"]["lock_digest"] = _digest("fabricated")
    elif mutation == "passing_predecessor":
        predecessor_reviews = _calibration_reviews(predecessor_lock)
    elif mutation == "malformed_mapping":
        predecessor_mapping["unexpected"] = True
        (predecessor_root / "controller-mapping.json").write_bytes(
            canonical_json_bytes(predecessor_mapping)
        )
    elif mutation == "role_semantics":
        predecessor_mapping["packages"]["calibration-direction-1"]["labels"] = {
            "candidate-alpha": "BASE",
            "candidate-beta": "REFERENCE",
        }
        (predecessor_root / "controller-mapping.json").write_bytes(
            canonical_json_bytes(predecessor_mapping)
        )
    else:
        predecessor_reviews[1]["session_id"] = predecessor_reviews[0]["session_id"]
    current_root = tmp_path / "current-controller-final"
    current_mapping = _calibration_mapping(
        current_lock,
        controller_root=current_root,
    )

    with pytest.raises(EvaluationError) as caught:
        validate_calibration(
            calibration_lock=current_lock,
            controller_mapping=current_mapping,
            controller_root=current_root,
            reviews=current_reviews,
            predecessor_lock=predecessor_lock,
            predecessor_controller_mapping=predecessor_mapping,
            predecessor_controller_root=predecessor_root,
            predecessor_reviews=predecessor_reviews,
        )

    assert caught.value.code == "calibration_predecessor_invalid"


def test_build_round_two_rejects_passing_predecessor_before_output(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    shutil.copytree(SEED, base)
    environment = dict(os.environ)
    predecessor_lock = _calibration_lock(
        base_root=base,
        environment=environment,
    )
    predecessor_root = tmp_path / "predecessor-controller"
    predecessor_mapping = _calibration_mapping(
        predecessor_lock,
        controller_root=predecessor_root,
    )
    current_lock = _calibration_lock(
        base_root=base,
        environment=environment,
        round_number=2,
        revision=1,
    )

    with pytest.raises(EvaluationError) as caught:
        build_calibration_packages(
            calibration_lock=current_lock,
            base_identity=current_lock["base_identity"],
            predecessor_lock=predecessor_lock,
            predecessor_controller_mapping=predecessor_mapping,
            predecessor_controller_root=predecessor_root,
            predecessor_reviews=_calibration_reviews(predecessor_lock),
            base_root=base,
            task_path="docs/tasks/port_linear_classifier_to_rust.md",
            reference_patch=REFERENCE_PATCH,
            rubric_path=RUBRIC,
            selected_final_files=tuple(current_lock["selected_final_files"]),
            visible_check_argv=tuple(current_lock["visible_check"]["argv"]),
            visible_check_timeout_milliseconds=300_000,
            visible_check_class="A0_VISIBLE",
            hidden_evaluator_class="A0_LINEAR_CLASSIFIER",
            evaluator_module=linear_classifier,
            oracle_path=base / "src_py/linear_classifier.py",
            environment=environment,
            reviewer_execution=_reviewer_execution(),
            output_root=tmp_path / "packages",
            controller_root=tmp_path / "controller",
        )

    assert caught.value.code == "calibration_predecessor_invalid"
    assert not (tmp_path / "packages").exists()


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("session_reuse", "calibration_reviewer_session_reused"),
        ("label_order", "calibration_label_order_inconsistent"),
        ("base_preferred", "calibration_reference_not_preferred"),
        ("identity_winner", "calibration_identity_not_tie"),
        ("third_reviewer", "calibration_reviewer_mismatch"),
        ("invalid_record", "calibration_review_invalid"),
        ("candidate_mismatch", "calibration_mapping_mismatch"),
        ("lock_digest", "calibration_mapping_mismatch"),
        ("manifest_binding", "calibration_mapping_mismatch"),
        ("pair_labels", "calibration_mapping_mismatch"),
        ("second_revision", "calibration_revision_limit_exceeded"),
        ("second_round_failed", "CALIBRATION_FAILED"),
    ],
)
def test_validate_calibration_fails_closed_with_stable_codes(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    lock = _calibration_lock()
    reviews = _calibration_reviews()
    mutate_manifest_binding = False
    predecessor_lock = None
    predecessor_controller_mapping = None
    predecessor_controller_root = None
    predecessor_reviews = None
    if mutation == "session_reuse":
        reviews[1]["session_id"] = reviews[0]["session_id"]
    elif mutation == "label_order":
        reviews[1]["pairwise_results"][0]["outcome"] = "A"
        reviews[4]["pairwise_results"][0]["outcome"] = "A"
    elif mutation == "base_preferred":
        reviews[0]["pairwise_results"][0]["outcome"] = "B"
        reviews[1]["pairwise_results"][0]["outcome"] = "A"
        reviews[3]["pairwise_results"][0]["outcome"] = "B"
        reviews[4]["pairwise_results"][0]["outcome"] = "A"
    elif mutation == "identity_winner":
        reviews[2]["pairwise_results"][0]["outcome"] = "A"
    elif mutation == "third_reviewer":
        extra = copy.deepcopy(reviews[0])
        extra["reviewer_id"] = "reviewer-3"
        extra["session_id"] = "session-third"
        reviews.append(extra)
    elif mutation == "invalid_record":
        reviews[0]["unexpected"] = True
    elif mutation == "candidate_mismatch":
        reviews[0]["candidates"][0]["opaque_label"] = "candidate-other"
    elif mutation == "lock_digest":
        reviews[0]["pilot_lock_digest"] = _digest("wrong-lock")
    elif mutation == "manifest_binding":
        mutate_manifest_binding = True
    elif mutation == "pair_labels":
        reviews[0]["pairwise_results"][0]["candidate_b_label"] = (
            "candidate-alpha"
        )
    elif mutation == "second_revision":
        lock["revision"] = 2
    else:
        predecessor_lock = _calibration_lock()
        predecessor_controller_root = tmp_path / "predecessor-controller"
        predecessor_controller_mapping = _calibration_mapping(
            predecessor_lock,
            controller_root=predecessor_controller_root,
        )
        predecessor_reviews = _calibration_reviews(predecessor_lock)
        predecessor_reviews[2]["pairwise_results"][0]["outcome"] = "A"
        lock = _calibration_lock(round_number=2, revision=1)
        reviews = _calibration_reviews(lock)
        reviews[0]["pairwise_results"][0]["outcome"] = "B"

    controller_root = tmp_path / "controller"
    mapping = _calibration_mapping(
        lock,
        controller_root=controller_root,
    )
    if mutate_manifest_binding:
        mapping["review_bindings"][reviews[0]["review_id"]][
            "package_manifest_digest"
        ] = _digest("wrong-manifest")
        (controller_root / "controller-mapping.json").write_bytes(
            canonical_json_bytes(mapping)
        )
    with pytest.raises(EvaluationError) as caught:
        validate_calibration(
            calibration_lock=lock,
            controller_mapping=mapping,
            controller_root=controller_root,
            reviews=reviews,
            predecessor_lock=predecessor_lock,
            predecessor_controller_mapping=predecessor_controller_mapping,
            predecessor_controller_root=predecessor_controller_root,
            predecessor_reviews=predecessor_reviews,
        )

    assert caught.value.code == expected_code


def _live_review(package_root: Path) -> dict[str, Any]:
    labels = json.loads(
        (package_root / "manifest.json").read_text(encoding="utf-8")
    )["candidate_labels"]
    citations = [
        f"candidates/{label}/diff.patch" for label in labels
    ]
    return {
        "record_kind": "review_result.v1",
        "review_id": "review-live-001",
        "pilot_lock_digest": _digest("pilot-lock"),
        "reviewer_id": "reviewer-live",
        "session_id": "session-live",
        "review_class": "LIVE",
        "rubric_digest": _digest("rubric"),
        "candidates": [
            {
                "opaque_label": label,
                "evidence_citations": [citation],
                "dimension_assessments": _dimension_assessments(citation),
                "sealed_treatment_guess": "UNKNOWN",
            }
            for label, citation in zip(labels, citations, strict=True)
        ],
        "pairwise_results": [
            {
                "candidate_a_label": labels[left_index],
                "candidate_b_label": labels[right_index],
                "outcome": "INDETERMINATE",
                "rationale": "The cited evidence is inconclusive.",
                "evidence_citations": [
                    citations[left_index],
                    citations[right_index],
                ],
            }
            for left_index in range(len(labels))
            for right_index in range(left_index + 1, len(labels))
        ],
    }


def _write_live_package(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    (
        lock,
        block,
        base_root,
        product_roots,
        output_root,
        controller_root,
    ) = _live_inputs(tmp_path)
    package_root = build_blind_packages(
        lock=lock,
        block=block,
        base_root=base_root,
        product_roots=product_roots,
        task_path=lock["apparatus"]["task_path"],
        selected_final_files=_locked_selected_files(lock, product_roots),
        permitted_check_evidence=_locked_check_evidence(lock, block),
        output_root=output_root,
        controller_root=controller_root,
    )["live-001"]
    return package_root, _live_review(package_root)


def test_ingest_review_accepts_unknown_guesses_and_exact_package_citations(
    tmp_path: Path,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))

    manifest_bytes = (package_root / "manifest.json").read_bytes()
    loaded = ingest_review(
        path,
        package_root=package_root,
        expected_bindings={
            "pilot_lock_digest": _digest("pilot-lock"),
            "rubric_digest": _digest("rubric"),
            "review_class": "LIVE",
            "candidate_labels": tuple(
                item["opaque_label"] for item in record["candidates"]
            ),
            "package_id": "live-001",
            "package_manifest_digest": _digest_bytes(manifest_bytes),
            "reviewer_id": record["reviewer_id"],
        },
        used_session_ids=set(),
        prior_records=(),
    )

    assert loaded == record
    assert all(
        item["sealed_treatment_guess"] == "UNKNOWN"
        for item in loaded["candidates"]
    )


@pytest.mark.parametrize("suffix", [":1", ":1-2"])
def test_ingest_review_accepts_manifest_citations_with_line_locations(
    tmp_path: Path,
    suffix: str,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    candidate = record["candidates"][0]
    candidate["evidence_citations"][0] += suffix
    candidate["dimension_assessments"][0]["evidence_citations"][0] += suffix
    record["pairwise_results"][0]["evidence_citations"][0] += suffix
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))

    manifest_bytes = (package_root / "manifest.json").read_bytes()
    loaded = ingest_review(
        path,
        package_root=package_root,
        expected_bindings={
            "pilot_lock_digest": _digest("pilot-lock"),
            "rubric_digest": _digest("rubric"),
            "review_class": "LIVE",
            "candidate_labels": tuple(
                item["opaque_label"] for item in record["candidates"]
            ),
            "package_id": "live-001",
            "package_manifest_digest": _digest_bytes(manifest_bytes),
            "reviewer_id": record["reviewer_id"],
        },
        used_session_ids=set(),
        prior_records=(),
    )

    assert loaded == record


@pytest.mark.parametrize(
    ("citation", "expected_code"),
    [
        ("../escape.txt:1", "review_citation_escape"),
        ("/absolute.txt:1", "review_citation_escape"),
        ("not-in-manifest.txt:1", "review_citation_not_in_package"),
        (None, "review_citation_location_invalid"),
        ("OUT_OF_RANGE", "review_citation_location_invalid"),
        ("ZERO", "review_citation_location_invalid"),
        ("LEADING_ZERO", "review_citation_location_invalid"),
        ("TRAILING_RANGE", "review_citation_location_invalid"),
        ("DOUBLE_LOCATION", "review_citation_location_invalid"),
        ("PREFIX_TRAVERSAL", "review_citation_escape"),
        ("PREFIX_BACKSLASH", "review_citation_escape"),
    ],
)
def test_ingest_review_rejects_invalid_line_location(
    tmp_path: Path,
    citation: str | None,
    expected_code: str,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    manifest_path = record["candidates"][0]["evidence_citations"][0]
    if citation is None:
        citation = f"{manifest_path}:2-1"
    elif citation == "OUT_OF_RANGE":
        citation = f"{manifest_path}:999999"
    elif citation == "ZERO":
        citation = f"{manifest_path}:0"
    elif citation == "LEADING_ZERO":
        citation = f"{manifest_path}:01"
    elif citation == "TRAILING_RANGE":
        citation = f"{manifest_path}:1-"
    elif citation == "DOUBLE_LOCATION":
        citation = f"{manifest_path}:1:2"
    elif citation == "PREFIX_TRAVERSAL":
        citation = f"{manifest_path}:/../escape"
    elif citation == "PREFIX_BACKSLASH":
        citation = f"{manifest_path}:\\..\\escape"
    record["candidates"][0]["evidence_citations"][0] = citation
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))

    manifest_bytes = (package_root / "manifest.json").read_bytes()
    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == expected_code


@pytest.mark.parametrize("citation", ["manifest.json", "manifest.json:1"])
def test_ingest_review_rejects_manifest_navigation_citation(
    tmp_path: Path,
    citation: str,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    record["candidates"][0]["evidence_citations"][0] = citation
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))
    manifest_bytes = (package_root / "manifest.json").read_bytes()

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == "review_citation_not_in_package"


def test_citation_exact_colon_path_takes_precedence_over_locator() -> None:
    _validate_citation(
        "artifact:1",
        permitted_payloads={
            "artifact": b"",
            "artifact:1": b"\xff",
        },
    )


def test_validate_citation_accepts_exact_path_for_empty_payload() -> None:
    _validate_citation(
        "empty.txt",
        permitted_payloads={"empty.txt": b""},
    )


@pytest.mark.parametrize("suffix", [":1", ":1-1", ":1-2"])
def test_validate_citation_rejects_line_location_for_empty_payload(
    suffix: str,
) -> None:
    with pytest.raises(EvaluationError) as caught:
        _validate_citation(
            f"empty.txt{suffix}",
            permitted_payloads={"empty.txt": b""},
        )

    assert caught.value.code == "review_citation_location_invalid"


def test_ingest_review_rejects_line_location_on_non_utf8_payload(
    tmp_path: Path,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    citation_path = record["candidates"][0]["evidence_citations"][0]
    payload_path = package_root / citation_path
    payload = b"\xff"
    payload_path.write_bytes(payload)
    manifest_path = package_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = next(
        item for item in manifest["files"] if item["path"] == citation_path
    )
    row["size"] = len(payload)
    row["sha256"] = _digest_bytes(payload)
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    record["candidates"][0]["evidence_citations"][0] = f"{citation_path}:1"
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == "review_citation_location_invalid"


def test_ingest_review_accepts_complete_pair_coverage_in_either_orientation(
    tmp_path: Path,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    pair = record["pairwise_results"][1]
    pair["candidate_a_label"], pair["candidate_b_label"] = (
        pair["candidate_b_label"],
        pair["candidate_a_label"],
    )
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))
    manifest_bytes = (package_root / "manifest.json").read_bytes()

    loaded = ingest_review(
        path,
        package_root=package_root,
        expected_bindings={
            "pilot_lock_digest": _digest("pilot-lock"),
            "rubric_digest": _digest("rubric"),
            "review_class": "LIVE",
            "candidate_labels": tuple(
                item["opaque_label"] for item in record["candidates"]
            ),
            "package_id": "live-001",
            "package_manifest_digest": _digest_bytes(manifest_bytes),
            "reviewer_id": record["reviewer_id"],
        },
        used_session_ids=set(),
        prior_records=(),
    )

    assert loaded == record


def test_ingest_review_rejects_manifest_candidate_label_binding_drift(
    tmp_path: Path,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    manifest_path = package_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["candidate_labels"] = [
        "candidate-wrong-alpha",
        "candidate-wrong-beta",
        "candidate-wrong-gamma",
    ]
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == "review_binding_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "review_package_invalid"),
        ("unsafe", "evaluation_path_invalid"),
        ("undeclared", "review_package_invalid"),
    ],
)
def test_ingest_review_rejects_missing_unsafe_or_undeclared_manifest_task_path(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    manifest_path = package_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "missing":
        del manifest["task_path"]
    elif mutation == "unsafe":
        manifest["task_path"] = "../task.md"
    else:
        manifest["task_path"] = "undeclared-task.md"
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "review_binding_mismatch"),
        ("duplicate", "review_binding_mismatch"),
        ("reversed-duplicate", "review_binding_mismatch"),
        ("extra", "review_record_invalid"),
    ],
)
def test_ingest_review_rejects_incomplete_or_duplicate_pair_coverage(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    if mutation == "missing":
        record["pairwise_results"].pop()
    elif mutation in {"duplicate", "reversed-duplicate"}:
        duplicate = copy.deepcopy(record["pairwise_results"][0])
        if mutation == "reversed-duplicate":
            duplicate["candidate_a_label"], duplicate["candidate_b_label"] = (
                duplicate["candidate_b_label"],
                duplicate["candidate_a_label"],
            )
        else:
            duplicate["outcome"] = "A"
        record["pairwise_results"][-1] = duplicate
    else:
        duplicate = copy.deepcopy(record["pairwise_results"][0])
        duplicate["outcome"] = "B"
        record["pairwise_results"].append(duplicate)
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))
    manifest_bytes = (package_root / "manifest.json").read_bytes()

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == expected_code


def test_ingest_review_rejects_smoke_as_a_review_class(
    tmp_path: Path,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    record["review_class"] = "SMOKE"
    path = tmp_path / "smoke-review.json"
    path.write_bytes(canonical_json_bytes(record))

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={},
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == "review_record_invalid"


def test_ingest_review_binds_expected_stable_reviewer_identity(
    tmp_path: Path,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))
    manifest_bytes = (package_root / "manifest.json").read_bytes()

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": "different-reviewer",
            },
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == "review_binding_mismatch"


def test_ingest_review_allows_stable_reviewer_across_blocks_on_fresh_session(
    tmp_path: Path,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))
    manifest_bytes = (package_root / "manifest.json").read_bytes()

    loaded = ingest_review(
        path,
        package_root=package_root,
        expected_bindings={
            "pilot_lock_digest": _digest("pilot-lock"),
            "rubric_digest": _digest("rubric"),
            "review_class": "LIVE",
            "candidate_labels": tuple(
                item["opaque_label"] for item in record["candidates"]
            ),
            "package_id": "live-001",
            "package_manifest_digest": _digest_bytes(manifest_bytes),
            "reviewer_id": record["reviewer_id"],
        },
        used_session_ids={"session-prior-block"},
        prior_records=(),
    )

    assert loaded == record


def test_ingest_review_rejects_duplicate_reviewer_within_one_block(
    tmp_path: Path,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))
    manifest_bytes = (package_root / "manifest.json").read_bytes()
    prior = copy.deepcopy(record)
    prior["review_id"] = "review-same-block-prior"
    prior["session_id"] = "session-same-block-prior"

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids={"session-prior-block"},
            prior_records=(prior,),
        )

    assert caught.value.code == "review_reviewer_reused"


@pytest.mark.parametrize("node_kind", ["directory", "symlink", "fifo"])
def test_ingest_review_rejects_undeclared_nonregular_nodes(
    tmp_path: Path,
    node_kind: str,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    extra = package_root / "undeclared-node"
    if node_kind == "directory":
        extra.mkdir()
    elif node_kind == "symlink":
        os.symlink("missing-target", extra)
    else:
        os.mkfifo(extra)
    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))
    manifest_bytes = (package_root / "manifest.json").read_bytes()

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids=set(),
            prior_records=(),
        )

    assert caught.value.code == "review_package_invalid"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("session_ledger", "review_session_reused"),
        ("prior_session", "review_session_reused"),
        ("citation_escape", "review_citation_escape"),
        ("nested_citation_escape", "review_citation_escape"),
        ("nested_citation_unmanifested", "review_citation_not_in_package"),
        ("citation_unmanifested", "review_package_invalid"),
        ("binding", "review_binding_mismatch"),
    ],
)
def test_ingest_review_rejects_reuse_escape_and_binding_mismatch(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    used_session_ids: set[str] = set()
    prior_records: list[dict[str, Any]] = []
    expected = {
        "pilot_lock_digest": _digest("pilot-lock"),
        "rubric_digest": _digest("rubric"),
        "review_class": "LIVE",
        "candidate_labels": tuple(
            item["opaque_label"] for item in record["candidates"]
        ),
        "package_id": "live-001",
        "package_manifest_digest": _digest_bytes(
            (package_root / "manifest.json").read_bytes()
        ),
        "reviewer_id": record["reviewer_id"],
    }
    if mutation == "session_ledger":
        used_session_ids.add(record["session_id"])
    elif mutation == "prior_session":
        prior_records.append(
            {
                "reviewer_id": "different-reviewer",
                "session_id": record["session_id"],
            }
        )
    elif mutation == "citation_escape":
        record["candidates"][0]["evidence_citations"] = ["../escape.txt"]
    elif mutation == "nested_citation_escape":
        record["candidates"][0]["dimension_assessments"][0][
            "evidence_citations"
        ] = ["../escape.txt"]
    elif mutation == "nested_citation_unmanifested":
        record["candidates"][0]["dimension_assessments"][0][
            "evidence_citations"
        ] = ["not-in-manifest.txt"]
    elif mutation == "citation_unmanifested":
        _write(package_root / "not-in-manifest.txt", "present but forbidden\n")
        record["candidates"][0]["evidence_citations"] = [
            "not-in-manifest.txt"
        ]
    elif mutation == "binding":
        expected["rubric_digest"] = _digest("different-rubric")

    path = tmp_path / "review.json"
    path.write_bytes(canonical_json_bytes(record))
    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            path,
            package_root=package_root,
            expected_bindings=expected,
            used_session_ids=used_session_ids,
            prior_records=prior_records,
        )

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    "mutation",
    ["unreferenced_payload", "duplicate_manifest_row", "extra_manifest_field"],
)
def test_ingest_review_rejects_any_package_manifest_or_payload_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    package_root, record = _write_live_package(tmp_path)
    manifest_path = package_root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if mutation == "unreferenced_payload":
        payload = package_root / manifest["files"][0]["path"]
        payload.write_bytes(payload.read_bytes() + b"tampered")
    elif mutation == "duplicate_manifest_row":
        manifest["files"].append(copy.deepcopy(manifest["files"][0]))
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    else:
        manifest["unexpected"] = True
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    review_path = tmp_path / "review.json"
    review_path.write_bytes(canonical_json_bytes(record))

    with pytest.raises(EvaluationError) as caught:
        ingest_review(
            review_path,
            package_root=package_root,
            expected_bindings={
                "pilot_lock_digest": _digest("pilot-lock"),
                "rubric_digest": _digest("rubric"),
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    item["opaque_label"] for item in record["candidates"]
                ),
                "package_id": "live-001",
                "package_manifest_digest": _digest_bytes(manifest_bytes),
                "reviewer_id": record["reviewer_id"],
            },
            used_session_ids=set(),
            prior_records=(),
        )
    assert caught.value.code == "review_package_invalid"


def test_frozen_rubric_and_reference_patch_are_present() -> None:
    assert RUBRIC.is_file()
    assert REFERENCE_PATCH.is_file()
