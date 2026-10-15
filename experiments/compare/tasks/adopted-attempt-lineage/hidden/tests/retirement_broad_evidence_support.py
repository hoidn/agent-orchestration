from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest

from orchestrator.retirement.broad_evidence import (
    build_initial_execution_ledger,
    build_pytest_temp_root_preflight,
    canonical_sha256,
    file_sha256,
    publish_immutable_review,
    validate_record,
)
from orchestrator.retirement.materialization import (
    MaterializationReceipt,
    materialize_transaction,
)


__all__ = [
    "PRODUCER_FAILURE_NODE_IDS",
    "bind_candidate_to_repository",
    "producer_candidate_and_ledger",
    "producer_raw_broad",
    "publish_producer_review_pair",
    "synthetic_pytest_temp_root_preflight",
    "write_producer_json",
]


PRODUCER_FAILURE_NODE_IDS = (
    "tests/synthetic_alpha.py::test_alpha",
    "tests/synthetic_beta.py::test_beta",
    "tests/synthetic_delta.py::test_delta",
    "tests/synthetic_epsilon.py::test_epsilon",
    "tests/synthetic_gamma.py::test_gamma",
    "tests/synthetic_zeta.py::test_zeta",
)


def write_producer_json(
    repository: Path, logical_path: str, value: object
) -> Path:
    path = repository / logical_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return path


def _git_output(repository: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _initialize_candidate_repository(repository: Path) -> None:
    _git_output(repository, "init", "-q")
    _git_output(repository, "config", "user.email", "fixture@example.invalid")
    _git_output(repository, "config", "user.name", "Fixture")
    _git_output(repository, "commit", "-q", "--allow-empty", "-m", "baseline")


def bind_candidate_to_repository(
    repository: Path, binding: dict[str, object]
) -> None:
    binding["head"] = _git_output(repository, "rev-parse", "HEAD").decode().strip()
    binding["head_tree"] = (
        _git_output(repository, "rev-parse", "HEAD^{tree}").decode().strip()
    )
    binding["index_sha256"] = (
        "sha256:"
        + hashlib.sha256((repository / ".git/index").read_bytes()).hexdigest()
    )


def _write_ledger_plan(path: Path) -> None:
    path.write_text(
        "\n".join(
            f"### Task {number}: Task {number}\n\n"
            + "\n".join(
                f"- [ ] **Step {step}: Work**" for step in range(1, 5)
            )
            for number in range(1, 18)
        )
        + "\n"
    )


def _prior_generation_binding(
    receipt: MaterializationReceipt,
) -> dict[str, object]:
    return {
        "request_path": receipt.request_path.as_posix(),
        "request_sha256": receipt.request_sha256,
        "snapshot_path": receipt.snapshot_path.as_posix(),
        "snapshot_sha256": receipt.snapshot_sha256,
        "generation": receipt.generation,
        "output_path": receipt.output_path.as_posix(),
    }


def _ledger_binding(receipt: MaterializationReceipt) -> dict[str, object]:
    return {
        "live_path": receipt.output_path.as_posix(),
        "byte_sha256": receipt.output_sha256,
        "schema_version": "workflow_retirement_execution_ledger.v1",
        "generation": receipt.generation,
        "request_path": receipt.request_path.as_posix(),
        "request_sha256": receipt.request_sha256,
        "snapshot_path": receipt.snapshot_path.as_posix(),
        "snapshot_sha256": receipt.snapshot_sha256,
    }


def _advance_ledger(
    record: dict[str, object], receipt: MaterializationReceipt
) -> dict[str, object]:
    advanced = deepcopy(record)
    task_number = advanced["current_task"]
    assert isinstance(task_number, int)
    tasks = advanced["tasks"]
    assert isinstance(tasks, list)
    task = tasks[task_number - 1]
    assert isinstance(task, dict)
    assert task["status"] == "in_progress"
    completed_step_count = task["completed_step_count"]
    assert isinstance(completed_step_count, int)
    step_number = completed_step_count + 1
    task["completed_step_count"] = step_number
    old_status = "in_progress"
    if step_number == task["total_step_count"]:
        task["status"] = "complete"
        new_status = "complete"
        if task_number == 17:
            advanced["current_task"] = None
        else:
            next_task = tasks[task_number]
            assert isinstance(next_task, dict)
            next_task["status"] = "in_progress"
            advanced["current_task"] = task_number + 1
    else:
        new_status = "in_progress"
    advanced["last_transition"] = {
        "prior_generation_binding": _prior_generation_binding(receipt),
        "task_number": task_number,
        "step_number": step_number,
        "old_status": old_status,
        "new_status": new_status,
        "prepared_at": "2026-01-01T00:00:00+00:00",
        "evidence_bindings": [],
        "future_bindings": [],
    }
    advanced["normalized_ledger_sha256"] = canonical_sha256(
        advanced, exclude={"normalized_ledger_sha256"}
    )
    return advanced


def producer_candidate_and_ledger(
    repository: Path, *, ledger_generation: int = 1
) -> tuple[dict[str, object], dict[str, object]]:
    _initialize_candidate_repository(repository)
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    record = build_initial_execution_ledger(
        plan_path=Path("plan.md"), plan_bytes=plan.read_bytes()
    )
    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=Path("evidence/execution-ledger.json"),
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
    )
    for _ in range(2, ledger_generation + 1):
        record = _advance_ledger(record, receipt)
        receipt = materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=receipt.output_path,
            generation=receipt.generation + 1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
            prior_request=receipt.request_path,
            prior_snapshot=receipt.snapshot_path,
        )
    _git_output(repository, "add", "--", plan.relative_to(repository).as_posix())
    _git_output(repository, "commit", "-q", "-m", "bind plan")
    source = repository / "source.py"
    source.write_text("candidate = True\n")
    row = {
        "path": "source.py",
        "sha256": file_sha256(source),
        "size": source.stat().st_size,
        "state": "added",
    }
    candidate: dict[str, object] = {
        "head": "0" * 40,
        "head_tree": "0" * 40,
        "index_sha256": "sha256:" + "0" * 64,
        "evidence_root_exclusion": "evidence",
        "candidate_paths": [row],
        "candidate_path_set_sha256": canonical_sha256([row]),
    }
    bind_candidate_to_repository(repository, candidate)
    return candidate, _ledger_binding(receipt)


def _capture_pytest_temp_root_preflight() -> dict[str, object]:
    variable = "PYTEST_DEBUG_TEMPROOT"
    was_present = variable in os.environ
    prior = os.environ.pop(variable, None)
    try:
        return build_pytest_temp_root_preflight(
            Path(sys.executable).with_name("pytest")
        )
    finally:
        if was_present:
            assert prior is not None
            os.environ[variable] = prior
        else:
            os.environ.pop(variable, None)


def synthetic_pytest_temp_root_preflight() -> dict[str, object]:
    import _pytest.tmpdir as tmpdir_module

    executable = Path(sys.executable).with_name("pytest").resolve(strict=True)
    module_path = Path(tmpdir_module.__file__).resolve(strict=True)
    system_temp_root = Path(tempfile.gettempdir()).resolve()
    session_parent = system_temp_root / "pytest-of-unknown"
    record: dict[str, object] = {
        "schema_version": "pytest_temp_root_preflight.v1",
        "pytest_executable_binding": {
            "path": str(executable),
            "sha256": file_sha256(executable),
        },
        "pytest_version": pytest.__version__,
        "tmpdir_module_binding": {
            "path": str(module_path),
            "sha256": file_sha256(module_path),
        },
        "environment_binding": {"PYTEST_DEBUG_TEMPROOT": None},
        "raw_get_user": None,
        "root_component_resolution": "missing_user_unknown",
        "root_component": "unknown",
        "system_temp_root": str(system_temp_root),
        "observed_session_parent": str(session_parent),
        "observed_basetemp": str(session_parent / "pytest-0"),
        "normalized_record_sha256": "",
        "claims_not_made": [
            "This synthetic preflight does not execute the broad test suite."
        ],
    }
    record["normalized_record_sha256"] = canonical_sha256(
        record, exclude={"normalized_record_sha256"}
    )
    assert validate_record(record) == []
    return record


def producer_raw_broad(
    repository: Path,
    *,
    failure_node_ids: tuple[str, ...] = PRODUCER_FAILURE_NODE_IDS,
    pytest_temp_root_preflight: Mapping[str, object] | None = None,
) -> dict[str, str]:
    pass_node_id = "tests/synthetic_pass.py::test_pass"
    nodes = sorted((*failure_node_ids, pass_node_id))
    raw = repository / "evidence/implementation-baseline"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "collect.log").write_text("\n".join(nodes) + "\n")
    (raw / "collect.exit").write_bytes(b"0\n")
    (raw / "collected-node-ids.txt").write_text("\n".join(nodes) + "\n")
    (raw / "pytest-rs.log").write_text(
        "".join(f"FAILED {node_id} - assertion\n" for node_id in failure_node_ids)
        + (
            f"================ {len(failure_node_ids)} failed, "
            "1 passed in 0.01s ================\n"
        )
    )
    (raw / "pytest.exit").write_bytes(b"1\n")
    (raw / "pytest.junit.xml").write_text(
        f'<testsuite tests="{len(nodes)}" '
        f'failures="{len(failure_node_ids)}" errors="0" skipped="0">'
        + "".join(
            f'<testcase file="{node_id.partition("::")[0]}" '
            f'name="{node_id.partition("::")[2]}"><failure>'
            f"{repository}/source.py failed for {node_id}"
            "</failure></testcase>"
            for node_id in failure_node_ids
        )
        + '<testcase file="tests/synthetic_pass.py" name="test_pass"/>'
        + "</testsuite>\n"
    )
    preflight = (
        dict(pytest_temp_root_preflight)
        if pytest_temp_root_preflight is not None
        else _capture_pytest_temp_root_preflight()
    )
    issues = validate_record(preflight)
    assert issues == []
    write_producer_json(
        repository,
        "evidence/implementation-baseline/pytest-temp-root-preflight.json",
        preflight,
    )
    return {
        "collection_log_path": "evidence/implementation-baseline/collect.log",
        "collection_exit_path": "evidence/implementation-baseline/collect.exit",
        "collected_node_ids_path": (
            "evidence/implementation-baseline/collected-node-ids.txt"
        ),
        "rs_log_path": "evidence/implementation-baseline/pytest-rs.log",
        "broad_exit_path": "evidence/implementation-baseline/pytest.exit",
        "junit_path": "evidence/implementation-baseline/pytest.junit.xml",
        "pytest_temp_root_preflight_path": (
            "evidence/implementation-baseline/pytest-temp-root-preflight.json"
        ),
    }


def publish_producer_review_pair(
    repository: Path,
    *,
    evidence_root: Path,
    subject_path: Path,
    subject_kind: str,
    specification_name: str,
    quality_name: str,
    specification_reviewed_at: str = "2026-01-01T00:00:00+00:00",
    quality_reviewed_at: str = "2026-01-01T00:00:00+00:00",
    prior_review_bindings: Mapping[str, dict[str, object] | None] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    bindings = []
    for review_kind, name, reviewed_at in (
        ("specification", specification_name, specification_reviewed_at),
        ("code_quality", quality_name, quality_reviewed_at),
    ):
        review_path = evidence_root / name
        review = {
            "schema_version": "review.v1",
            "review_kind": review_kind,
            "reviewer": {"identity": f"{review_kind}-reviewer"},
            "reviewed_at": reviewed_at,
            "subject": {
                "kind": subject_kind,
                "path": subject_path.as_posix(),
                "sha256": file_sha256(repository / subject_path),
            },
            "result": "approved",
            "issues": [],
            "claims_not_made": [
                "Synthetic approval for producer integration testing."
            ],
        }
        write_producer_json(repository, review_path.as_posix(), review)
        bindings.append(
            publish_immutable_review(
                repository_root=repository,
                evidence_root=evidence_root,
                subject_path=subject_path,
                review_path=review_path,
                prior_review_binding=(prior_review_bindings or {}).get(review_kind),
            )
        )
    return bindings[0], bindings[1]
