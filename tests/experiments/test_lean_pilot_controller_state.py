from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from orchestrator.experiments._pilot_controller_state import (
    PilotControllerStateError,
    prepare_or_load_block_package,
)
from orchestrator.experiments.contracts import canonical_json_bytes


def _sha(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _case(
    tmp_path: Path,
    *,
    attempt_class: str = "LIVE",
) -> dict[str, Any]:
    block_id = "smoke-1" if attempt_class == "SMOKE" else "live-1"
    evidence = (tmp_path / "evidence").resolve()
    work = (tmp_path / "work").resolve()
    evaluation = (tmp_path / "evaluation" / block_id).resolve()
    packages = (tmp_path / "packages" / block_id).resolve()
    evidence.mkdir()
    work.mkdir()
    (evidence / block_id).mkdir()
    attempt = {
        "block_id": block_id,
        "attempt_class": attempt_class,
        "status": "VALID",
        "treatment_executions": [
            {
                "treatment_id": treatment,
                "opaque_arm_label": label,
            }
            for treatment, label in (
                ("DIRECT", "opaque-1"),
                ("COORDINATOR", "opaque-2"),
                ("ORC", "opaque-3"),
            )
        ],
    }
    lock = {
        "evidence_root": evidence.as_posix(),
        "treatments": [
            {"treatment_id": treatment}
            for treatment in ("DIRECT", "COORDINATOR", "ORC")
        ],
    }
    return {
        "lock": lock,
        "attempt": attempt,
        "work": work,
        "evaluation": evaluation,
        "packages": packages,
        "evidence": evidence,
    }


def _successful_prepare(case: dict[str, Any]) -> dict[str, object]:
    block_id = case["attempt"]["block_id"]
    package = case["packages"] / block_id
    package.mkdir(parents=True)
    task = b"implement the bounded task\n"
    task_path = package / "task.md"
    task_path.write_bytes(task)
    task_mode = stat.S_IMODE(task_path.stat().st_mode)
    manifest = canonical_json_bytes(
        {
            "package_id": block_id,
            "task_path": "task.md",
            "candidate_labels": [
                "candidate-1",
                "candidate-2",
                "candidate-3",
            ],
            "files": [
                {
                    "path": "task.md",
                    "mode": task_mode,
                    "size": len(task),
                    "sha256": _sha(task),
                }
            ],
        }
    )
    (package / "manifest.json").write_bytes(manifest)
    label_map = case["evidence"] / "label-maps" / f"{block_id}.json"
    label_map.parent.mkdir()
    label_bytes = canonical_json_bytes({"packages": {}})
    label_map.write_bytes(label_bytes)
    evaluator_evidence: dict[str, dict[str, object]] = {}
    for execution in case["attempt"]["treatment_executions"]:
        role = execution["treatment_id"]
        label = execution["opaque_arm_label"]
        path = (
            case["evidence"]
            / block_id
            / label
            / "hidden-evaluator.json"
        )
        path.parent.mkdir()
        data = canonical_json_bytes({"verdict": "PASS"})
        path.write_bytes(data)
        evaluator_evidence[role] = {
            "path": path,
            "digest": _sha(data),
            "verdict": "PASS",
        }
    return {
        "package_id": block_id,
        "package_root": package,
        "package_manifest_digest": _sha(manifest),
        "label_map_path": label_map,
        "label_map_digest": _sha(label_bytes),
        "evaluator_evidence": evaluator_evidence,
    }


def _invoke(
    case: dict[str, Any],
    prepare: Any,
) -> dict[str, object]:
    return prepare_or_load_block_package(
        lock=case["lock"],
        attempt=case["attempt"],
        work_root=case["work"],
        evaluation_root=case["evaluation"],
        package_root=case["packages"],
        evidence_root=case["evidence"],
        prepare=prepare,
    )


def _prepare_with_package_mutation(
    case: dict[str, Any],
    mutation: str,
) -> dict[str, object]:
    result = _successful_prepare(case)
    package = Path(result["package_root"])
    task_path = package / "task.md"
    if mutation == "changed":
        task_path.write_bytes(b"changed\n")
    elif mutation == "missing":
        task_path.unlink()
    elif mutation == "undeclared":
        (package / "undeclared.txt").write_text("extra", encoding="utf-8")
    elif mutation == "nonregular":
        task_path.unlink()
        os.mkfifo(task_path)
    else:
        raise AssertionError(f"unsupported mutation: {mutation}")
    return result


def test_incomplete_post_valid_preparation_requires_a_new_lock(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    calls = 0

    def failing(**_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise RuntimeError("evaluator defect")

    with pytest.raises(RuntimeError, match="evaluator defect"):
        _invoke(case, failing)
    assert (
        case["evidence"]
        / "live-1"
        / "package-preparation-intent.json"
    ).is_file()

    with pytest.raises(
        PilotControllerStateError,
        match="post_valid_preparation_requires_new_lock",
    ):
        _invoke(case, lambda **_kwargs: pytest.fail("must not retry"))
    assert calls == 1


@pytest.mark.parametrize("attempt_class", ["SMOKE", "LIVE"])
@pytest.mark.parametrize(
    "mutation",
    ["changed", "missing", "undeclared", "nonregular"],
)
def test_fresh_preparation_rejects_invalid_package_closure_before_completion(
    tmp_path: Path,
    attempt_class: str,
    mutation: str,
) -> None:
    case = _case(tmp_path, attempt_class=attempt_class)

    with pytest.raises(
        PilotControllerStateError,
        match="package_preparation_completion_invalid",
    ):
        _invoke(
            case,
            lambda **_kwargs: _prepare_with_package_mutation(case, mutation),
        )

    block_root = case["evidence"] / case["attempt"]["block_id"]
    assert (block_root / "package-preparation-intent.json").is_file()
    assert not (block_root / "package-preparation-completion.json").exists()


def test_completed_preparation_reloads_without_reexecution(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    calls = 0

    def prepare(**_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _successful_prepare(case)

    first = _invoke(case, prepare)
    second = _invoke(
        case,
        lambda **_kwargs: pytest.fail("completed preparation must not rerun"),
    )

    assert calls == 1
    assert second["package_root"] == first["package_root"]
    assert second["package_manifest_digest"] == first[
        "package_manifest_digest"
    ]

    (Path(second["package_root"]) / "manifest.json").write_bytes(b"tampered")
    with pytest.raises(
        PilotControllerStateError,
        match="package_preparation_completion_invalid",
    ):
        _invoke(case, lambda **_kwargs: pytest.fail("tamper must not rerun"))


@pytest.mark.parametrize("attempt_class", ["SMOKE", "LIVE"])
def test_completed_preparation_rejects_changed_declared_package_payload(
    tmp_path: Path,
    attempt_class: str,
) -> None:
    case = _case(tmp_path, attempt_class=attempt_class)
    first = _invoke(case, lambda **_kwargs: _successful_prepare(case))

    (Path(first["package_root"]) / "task.md").write_bytes(b"changed\n")

    with pytest.raises(
        PilotControllerStateError,
        match="package_preparation_completion_invalid",
    ):
        _invoke(case, lambda **_kwargs: pytest.fail("must not rerun"))


@pytest.mark.parametrize("attempt_class", ["SMOKE", "LIVE"])
def test_completed_preparation_rejects_missing_declared_package_payload(
    tmp_path: Path,
    attempt_class: str,
) -> None:
    case = _case(tmp_path, attempt_class=attempt_class)
    first = _invoke(case, lambda **_kwargs: _successful_prepare(case))

    (Path(first["package_root"]) / "task.md").unlink()

    with pytest.raises(
        PilotControllerStateError,
        match="package_preparation_completion_invalid",
    ):
        _invoke(case, lambda **_kwargs: pytest.fail("must not rerun"))


@pytest.mark.parametrize("attempt_class", ["SMOKE", "LIVE"])
def test_completed_preparation_rejects_extra_package_node(
    tmp_path: Path,
    attempt_class: str,
) -> None:
    case = _case(tmp_path, attempt_class=attempt_class)
    first = _invoke(case, lambda **_kwargs: _successful_prepare(case))

    (Path(first["package_root"]) / "undeclared.txt").write_text(
        "extra",
        encoding="utf-8",
    )

    with pytest.raises(
        PilotControllerStateError,
        match="package_preparation_completion_invalid",
    ):
        _invoke(case, lambda **_kwargs: pytest.fail("must not rerun"))


@pytest.mark.parametrize("attempt_class", ["SMOKE", "LIVE"])
def test_completed_preparation_rejects_nonregular_package_node(
    tmp_path: Path,
    attempt_class: str,
) -> None:
    case = _case(tmp_path, attempt_class=attempt_class)
    first = _invoke(case, lambda **_kwargs: _successful_prepare(case))
    task_path = Path(first["package_root"]) / "task.md"
    task_path.unlink()
    os.mkfifo(task_path)

    with pytest.raises(
        PilotControllerStateError,
        match="package_preparation_completion_invalid",
    ):
        _invoke(case, lambda **_kwargs: pytest.fail("must not rerun"))


@pytest.mark.parametrize("attempt_class", ["SMOKE", "LIVE"])
def test_completed_preparation_rejects_symlinked_package_node(
    tmp_path: Path,
    attempt_class: str,
) -> None:
    case = _case(tmp_path, attempt_class=attempt_class)
    first = _invoke(case, lambda **_kwargs: _successful_prepare(case))
    task_path = Path(first["package_root"]) / "task.md"
    task_path.unlink()
    task_path.symlink_to(Path(first["package_root"]) / "manifest.json")

    with pytest.raises(
        PilotControllerStateError,
        match="package_preparation_completion_invalid",
    ):
        _invoke(case, lambda **_kwargs: pytest.fail("must not rerun"))


@pytest.mark.parametrize("attempt_class", ["SMOKE", "LIVE"])
def test_completed_preparation_rejects_declared_package_mode_drift(
    tmp_path: Path,
    attempt_class: str,
) -> None:
    case = _case(tmp_path, attempt_class=attempt_class)
    first = _invoke(case, lambda **_kwargs: _successful_prepare(case))
    task_path = Path(first["package_root"]) / "task.md"
    task_path.chmod(stat.S_IMODE(task_path.stat().st_mode) ^ stat.S_IXUSR)

    with pytest.raises(
        PilotControllerStateError,
        match="package_preparation_completion_invalid",
    ):
        _invoke(case, lambda **_kwargs: pytest.fail("must not rerun"))
