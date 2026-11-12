"""Content-free report projection for persisted prompt-attempt identity."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import os
from typing import Any, Callable

import pytest

from orchestrator.workflow.provider_attempts import ProviderAttemptScope


REPORT_SCHEMA = "workflow_prompt_context_report.v1"
V1_SCHEMA = "workflow_prompt_fragment_snapshot.functional.v1"
ROLE_ORDER = (
    "fragment_program",
    "resolved_bindings",
    "injected_dependencies",
    "runtime_contributions",
    "provider_policy",
)


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], Path, ProviderAttemptScope, dict[str, Any]]:
    retained = json.loads(
        (Path(__file__).parent / "fixtures" / "historical_prompt_identity.json")
        .read_text(encoding="utf-8")
        .replace("@WORKSPACE@", str(tmp_path))
    )
    state, record = retained["state"], retained["record"]
    scope = ProviderAttemptScope.from_dict(record["attempt"]["scope"])
    root = tmp_path / ".orchestrate" / "runs" / scope.run_id
    authority = next(iter(state["provider_attempt_allocations"].values()))[
        "prompt_fragment_identity_schema_version"
    ]
    _reset_scope(state, scope, authority=authority)
    record = _with_ordinal(record, scope, 1)
    _publish(state, root, scope, 1, record)
    return state, root, scope, deepcopy(record)


def _seal(record: dict[str, Any]) -> dict[str, Any]:
    from tests.test_prompt_identity import _record_seal

    return _record_seal(record)


def _reseal_identity(record: dict[str, Any]) -> dict[str, Any]:
    from tests.test_prompt_identity import (
        _record_seal,
        _reseal_identity,
    )

    _reseal_identity(record["prompt_attempt_identity"])
    return _record_seal(record)


def _legacy(record: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(record)
    projected["schema"] = V1_SCHEMA
    projected.pop("prompt_attempt_identity")
    return _seal(projected)


def _ordinary_failure(record: dict[str, Any]) -> dict[str, Any]:
    return _seal(
        {
            "schema": (
                "workflow_prompt_dependency_failure_evidence.functional.v1"
            ),
            "record_kind": "failure",
            "run": deepcopy(record["run"]),
            "compiler_contract": deepcopy(record["compiler_contract"]),
            "attempt": deepcopy(record["attempt"]),
            "failure": {
                "category": "missing_required_dependency",
                "operation": "resolve",
                "authored_row_id": None,
                "evaluated_relpath": None,
            },
            "provider_calls": {
                "preparation": False,
                "execution": False,
            },
        }
    )


def _with_ordinal(
    record: dict[str, Any],
    scope: ProviderAttemptScope,
    ordinal: int,
) -> dict[str, Any]:
    from orchestrator.workflow.prompt_dependency_evidence import _attempt

    projected = deepcopy(record)
    projected["attempt"] = _attempt(scope, ordinal)
    projected["run"]["run_id"] = scope.run_id
    projected["run"]["workflow_file"] = (
        scope.resume_scope.root_workflow_file
    )
    return _seal(projected)


def _allocation(
    state: dict[str, Any],
    scope: ProviderAttemptScope,
) -> dict[str, Any]:
    return state["provider_attempt_allocations"][scope.key]


def _reset_scope(
    state: dict[str, Any],
    scope: ProviderAttemptScope,
    *,
    authority: str | None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "scope": scope.to_dict(),
        "last_allocated_ordinal": 1,
    }
    if authority is not None:
        entry["prompt_fragment_identity_schema_version"] = authority
    state["provider_attempt_allocations"] = {scope.key: entry}
    return entry


def _append_allocation(
    state: dict[str, Any],
    scope: ProviderAttemptScope,
) -> int:
    entry = _allocation(state, scope)
    ordinal = entry["last_allocated_ordinal"] + 1
    entry["last_allocated_ordinal"] = ordinal
    return ordinal


def _publish(
    state: dict[str, Any],
    root: Path,
    scope: ProviderAttemptScope,
    ordinal: int,
    record: dict[str, Any],
    *,
    canonical: bool = True,
    tamper: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
        evidence_relative_path,
    )

    entry = _allocation(state, scope)
    authority = entry.get("prompt_fragment_identity_schema_version")
    projected = _with_ordinal(record, scope, ordinal)
    if tamper is not None:
        tamper(projected)
    if canonical:
        payload = canonical_record_bytes(
            projected,
            compiler_fragment_identity_schema_version=authority,
        )
    else:
        payload = json.dumps(
            projected,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    relative = evidence_relative_path(scope, ordinal)
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return destination


def _replace_first_publication(
    state: dict[str, Any],
    root: Path,
    scope: ProviderAttemptScope,
    record: dict[str, Any],
    *,
    canonical: bool = True,
) -> None:
    _publish(
        state,
        root,
        scope,
        1,
        record,
        canonical=canonical,
    )


def _project(state: dict[str, Any], root: Path) -> dict[str, Any]:
    from orchestrator.workflow.prompt_context_report import (
        project_prompt_context,
    )

    return project_prompt_context(state, root)


def _project_v2(state: dict[str, Any], root: Path) -> dict[str, Any]:
    from orchestrator.workflow.prompt_context_report import (
        project_prompt_context_v2,
    )

    return project_prompt_context_v2(state, root)


def _validate_v2(
    report: dict[str, Any],
    state: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    from orchestrator.workflow.prompt_context_report import (
        validate_prompt_context_report_v2_projection,
    )

    return validate_prompt_context_report_v2_projection(
        report,
        state=state,
        run_root=root,
    )


def _phased_v3(
    *,
    canonical_composed: bytes = b"Read these inputs.\n\nbase prompt",
    actual_deliveries: tuple = (),
    model: str = "gpt-5",
    identity_schema_version: str = "compiled_prompt_fragment_identity.v1",
    workflow_checksum: str | None = None,
) -> dict[str, Any]:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence_v3,
    )
    from tests.test_prompt_dependency_evidence import (
        _canonical_cut,
        _fragment_v1_record,
        _identity_v2,
    )

    cut = _canonical_cut(canonical_composed)
    record = build_fragment_success_evidence_v3(
        retained_v1=_fragment_v1_record(
            canonical_composed=canonical_composed,
        ),
        cut=cut,
        prompt_attempt_identity=_identity_v2(
            identity_schema_version=identity_schema_version,
            cut=cut,
            actual_deliveries=actual_deliveries,
            model=model,
        ),
        compiler_fragment_identity_schema_version=(
            identity_schema_version
        ),
    )
    if workflow_checksum is not None:
        record["run"]["workflow_checksum"] = workflow_checksum
        _seal(record)
    return record


def _phased_turns(
    *,
    canonical_composed: bytes = b"Read these inputs.\n\nbase prompt",
    submit_keys: tuple[str, ...] = ("ENTER",),
) -> tuple:
    from orchestrator.workflow.provider_phased_delivery.frames import (
        render_initial_materialization_turn,
        render_task_turn,
    )
    from tests.test_prompt_dependency_evidence import _canonical_cut

    cut = _canonical_cut(canonical_composed)
    return (
        render_task_turn(cut=cut),
        render_initial_materialization_turn(
            cut=cut,
            submit_keys=submit_keys,
        ),
    )


def test_internal_v2_projects_composed_identity_without_changing_public_v1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, _scope_value, functional_v2 = _fixture(
        tmp_path,
        monkeypatch,
    )
    public_before = _project(state, root)

    internal = _project_v2(state, root)
    identity = internal["attempts"][0]["identity"]

    assert public_before == _project(state, root)
    assert public_before["schema_version"] == REPORT_SCHEMA
    assert tuple(public_before["attempts"][0]["identity"]) == (
        "composition_sha256",
        "final_prompt_sha256",
        "role_sha256",
    )
    assert internal["schema_version"] == "workflow_prompt_context_report.v2"
    assert tuple(identity) == (
        "identity_version",
        "composition_sha256",
        "legacy_final_prompt_sha256",
        "canonical_composed",
        "actual_deliveries",
        "role_sha256",
    )
    source = functional_v2["prompt_attempt_identity"]
    assert identity == {
        "identity_version": "workflow_prompt_attempt_identity.v1",
        "composition_sha256": source["composition_sha256"],
        "legacy_final_prompt_sha256": source["final_prompt"]["sha256"],
        "canonical_composed": None,
        "actual_deliveries": None,
        "role_sha256": {
            role: source["roles"][role]["sha256"]
            for role in ROLE_ORDER
        },
    }
    assert "final_prompt_sha256" not in identity


def test_internal_v2_qualifies_functional_v3_with_exact_identity_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, _functional_v2 = _fixture(tmp_path, monkeypatch)
    _allocation(state, scope)[
        "prompt_fragment_identity_schema_version"
    ] = "compiled_prompt_fragment_identity.v1"
    functional_v3 = _phased_v3(
        actual_deliveries=_phased_turns(),
        workflow_checksum=state["workflow_checksum"],
    )
    _replace_first_publication(state, root, scope, functional_v3)

    row = _project_v2(state, root)["attempts"][0]
    identity = row["identity"]
    source = functional_v3["prompt_attempt_identity"]

    assert row["record_status"] == "snapshot"
    assert tuple(identity) == (
        "identity_version",
        "composition_sha256",
        "legacy_final_prompt_sha256",
        "canonical_composed",
        "actual_deliveries",
        "role_sha256",
    )
    assert identity["identity_version"] == (
        "workflow_prompt_attempt_identity.v2"
    )
    assert identity["legacy_final_prompt_sha256"] is None
    assert identity["canonical_composed"] == source["canonical_composed"]
    assert identity["actual_deliveries"] == source["actual_deliveries"]
    assert identity["composition_sha256"] == source["composition_sha256"]
    assert tuple(identity["role_sha256"]) == ROLE_ORDER
    assert "final_prompt_sha256" not in identity


def test_internal_v2_preserves_closed_status_and_nullability_for_all_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, functional_v2 = _fixture(tmp_path, monkeypatch)
    _allocation(state, scope)[
        "prompt_fragment_identity_schema_version"
    ] = "compiled_prompt_fragment_identity.v1"
    functional_v3 = _phased_v3(
        workflow_checksum=state["workflow_checksum"],
    )
    _replace_first_publication(state, root, scope, functional_v3)
    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, _legacy(functional_v2))
    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, _ordinary_failure(functional_v2))
    _append_allocation(state, scope)
    ordinal = _append_allocation(state, scope)
    _publish(
        state,
        root,
        scope,
        ordinal,
        functional_v3,
        canonical=False,
        tamper=lambda record: record["prompt_attempt_identity"].__setitem__(
            "composition_sha256",
            _sha(b"invalid"),
        ),
    )

    rows = _project_v2(state, root)["attempts"]

    assert [row["record_status"] for row in rows] == [
        "snapshot",
        "legacy_snapshot",
        "failure",
        "allocation_only",
        "invalid",
    ]
    assert [row["identity"] is not None for row in rows] == [
        True,
        False,
        False,
        False,
        False,
    ]
    assert [row["comparison"]["reason"] for row in rows] == [
        "no_predecessor",
        "legacy_snapshot_only",
        "current_record_missing",
        "current_record_missing",
        "current_record_invalid",
    ]


def test_internal_v2_comparison_is_version_strict_and_uses_latest_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, functional_v2 = _fixture(tmp_path, monkeypatch)
    authority = _allocation(state, scope)[
        "prompt_fragment_identity_schema_version"
    ]
    _replace_first_publication(state, root, scope, functional_v2)
    functional_v3 = _phased_v3(
        identity_schema_version=authority,
        workflow_checksum=state["workflow_checksum"],
    )
    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, functional_v3)
    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, functional_v3)

    rows = _project_v2(state, root)["attempts"]

    assert rows[1]["comparison"] == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": [],
        "reason": "identity_version_mismatch",
    }
    assert rows[2]["comparison"] == {
        "status": "available",
        "previous_attempt_ordinal": 2,
        "classifications": ["prompt_context_unchanged"],
        "reason": None,
    }


def test_internal_v2_classifies_actual_delivery_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, _functional_v2 = _fixture(tmp_path, monkeypatch)
    _allocation(state, scope)[
        "prompt_fragment_identity_schema_version"
    ] = "compiled_prompt_fragment_identity.v1"
    previous = _phased_v3(
        actual_deliveries=_phased_turns(submit_keys=("ENTER",)),
        workflow_checksum=state["workflow_checksum"],
    )
    current = _phased_v3(
        actual_deliveries=_phased_turns(submit_keys=("TAB",)),
        workflow_checksum=state["workflow_checksum"],
    )
    _replace_first_publication(state, root, scope, previous)
    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, current)

    comparison = _project_v2(state, root)["attempts"][-1]["comparison"]

    assert comparison == {
        "status": "available",
        "previous_attempt_ordinal": 1,
        "classifications": ["actual_delivery_drift"],
        "reason": None,
    }


def test_internal_v2_keeps_composition_mismatch_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, _functional_v2 = _fixture(tmp_path, monkeypatch)
    _allocation(state, scope)[
        "prompt_fragment_identity_schema_version"
    ] = "compiled_prompt_fragment_identity.v1"
    previous = _phased_v3(
        workflow_checksum=state["workflow_checksum"],
    )
    current = _phased_v3(
        canonical_composed=b"different composed bytes",
        workflow_checksum=state["workflow_checksum"],
    )
    _replace_first_publication(state, root, scope, previous)
    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, current)

    comparison = _project_v2(state, root)["attempts"][-1]["comparison"]

    assert comparison["status"] == "unavailable"
    assert comparison["reason"] == "prompt_identity_composition_mismatch"


@pytest.mark.parametrize(
    "tamper",
    (
        "top_level_extra",
        "attempt_extra",
        "record_status",
        "record_sha256",
        "identity_nullability",
        "identity_version",
        "legacy_final_prompt_sha256",
        "canonical_composed",
        "actual_deliveries",
        "role_sha256",
        "composition_sha256",
        "comparison",
    ),
)
def test_internal_v2_projection_validator_is_closed_and_source_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    state, root, scope, _functional_v2 = _fixture(tmp_path, monkeypatch)
    authority = _allocation(state, scope)[
        "prompt_fragment_identity_schema_version"
    ]
    functional_v3 = _phased_v3(
        actual_deliveries=_phased_turns(),
        identity_schema_version=authority,
        workflow_checksum=state["workflow_checksum"],
    )
    _replace_first_publication(state, root, scope, functional_v3)
    report = _project_v2(state, root)

    assert _validate_v2(report, state, root) == report

    candidate = deepcopy(report)
    row = candidate["attempts"][0]
    identity = row["identity"]
    if tamper == "top_level_extra":
        candidate["extra"] = None
    elif tamper == "attempt_extra":
        row["extra"] = None
    elif tamper == "record_status":
        row["record_status"] = "failure"
    elif tamper == "record_sha256":
        row["record_sha256"] = "sha256:" + "0" * 64
    elif tamper == "identity_nullability":
        row["identity"] = None
    elif tamper == "identity_version":
        identity["identity_version"] = "workflow_prompt_attempt_identity.v1"
    elif tamper == "legacy_final_prompt_sha256":
        identity["legacy_final_prompt_sha256"] = "sha256:" + "0" * 64
    elif tamper == "canonical_composed":
        identity["canonical_composed"]["sha256"] = "sha256:" + "0" * 64
    elif tamper == "actual_deliveries":
        identity["actual_deliveries"] = []
    elif tamper == "role_sha256":
        identity["role_sha256"]["provider_policy"] = "sha256:" + "0" * 64
    elif tamper == "composition_sha256":
        identity["composition_sha256"] = "sha256:" + "0" * 64
    else:
        row["comparison"]["reason"] = "current_record_invalid"

    with pytest.raises(ValueError, match="report-v2 projection"):
        _validate_v2(candidate, state, root)


def test_execution_and_resume_modules_do_not_import_prompt_context_reporting(
) -> None:
    repository_root = Path(__file__).parents[1]
    runtime_paths = sorted(
        path
        for path in (repository_root / "orchestrator").rglob("*.py")
        if (
            "executor" in path.stem
            or "resume" in path.stem
        )
    )

    assert runtime_paths
    for path in runtime_paths:
        assert "prompt_context_report" not in path.read_text(
            encoding="utf-8"
        ), path


def test_execution_and_resume_do_not_call_prompt_context_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.cli.commands.run import run_workflow
    from orchestrator.workflow import prompt_context_report
    from tests.test_workflow_evaluated_cli import _run_args
    from tests.test_workflow_evaluated_providers import _fixture as provider_fixture

    source, providers, prompts, _request = provider_fixture(tmp_path)
    args = _run_args({
        "source": source, "source_root": tmp_path,
        "providers": providers, "prompts": prompts,
    })
    args.emit_debug_yaml = False
    args.input = ["message=typed input"]
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])

    def forbidden(*_args, **_kwargs):
        raise AssertionError("runtime must not call report projection")

    for name in ("project_prompt_context", "project_prompt_context_v2"):
        monkeypatch.setattr(prompt_context_report, name, forbidden)
    monkeypatch.chdir(tmp_path)
    result = run_workflow(args, run_id="report-independent")
    assert result.exit_code == 0
    requests = (tmp_path / "requests.jsonl").read_bytes()
    assert len(requests.splitlines()) == 1
    assert resume_workflow("report-independent") == 0
    assert (tmp_path / "requests.jsonl").read_bytes() == requests
