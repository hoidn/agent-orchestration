"""Content-free report projection for persisted prompt-attempt identity."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from orchestrator.workflow.provider_attempts import ProviderAttemptScope


REPORT_SCHEMA = "workflow_prompt_context_report.v1"
V1_SCHEMA = "workflow_prompt_fragment_snapshot.functional.v1"
V2_SCHEMA = "workflow_prompt_fragment_snapshot.functional.v2"
PREPARATION_FAILURE_SCHEMA = (
    "workflow_prompt_fragment_preparation_failure.functional.v1"
)
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
    from tests.test_workflow_lisp_prompt_identity_runtime import (
        _actual_v2_schema_record_and_manager,
    )

    record, manager = _actual_v2_schema_record_and_manager(
        tmp_path,
        monkeypatch,
    )
    state = manager._read_state_from_disk().to_dict()
    allocation = next(iter(state["provider_attempt_allocations"].values()))
    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    return state, manager.run_root, scope, deepcopy(record)


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


def _preparation_failure(
    record: dict[str, Any],
    *,
    authority: str,
) -> dict[str, Any]:
    roles = record["prompt_attempt_identity"]["roles"]
    return _seal(
        {
            "schema": PREPARATION_FAILURE_SCHEMA,
            "record_kind": "failure",
            "run": deepcopy(record["run"]),
            "attempt": deepcopy(record["attempt"]),
            "fragment": {
                "identity_schema_version": authority,
                "compiled_prompt_fragment_identity": record[
                    "compiled_prompt_fragment_identity"
                ],
                "prompt_attempt_identity_version": (
                    "workflow_prompt_attempt_identity.v1"
                ),
                "binding_plan_sha256": roles["resolved_bindings"][
                    "payload"
                ]["binding_plan_sha256"],
            },
            "failure": {
                "category": "provider_policy_unresolved",
                "phase": "invocation_preparation",
            },
            "provider_calls": {
                "preparation": True,
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


def _with_changed_policy(record: dict[str, Any]) -> dict[str, Any]:
    from tests.test_prompt_identity import _reseal_role

    projected = deepcopy(record)
    policy = projected["prompt_attempt_identity"]["roles"][
        "provider_policy"
    ]
    policy["payload"]["model"] = "changed-model"
    _reseal_role(policy)
    return _reseal_identity(projected)


def _with_unmodelled_final_prompt(
    record: dict[str, Any],
) -> dict[str, Any]:
    projected = deepcopy(record)
    replacement = b"different-final-prompt"
    final = {
        "bytes": len(replacement),
        "sha256": _sha(replacement),
    }
    projected["final_prompt"] = deepcopy(final)
    projected["prompt_attempt_identity"]["final_prompt"] = deepcopy(final)
    return _reseal_identity(projected)


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
        "events": [{"ordinal": 1, "event": "allocated"}],
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
    entry["events"].append({"ordinal": ordinal, "event": "allocated"})
    return ordinal


def _publish(
    state: dict[str, Any],
    root: Path,
    scope: ProviderAttemptScope,
    ordinal: int,
    record: dict[str, Any],
    *,
    record_kind: str | None = None,
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
    entry["events"].append(
        {
            "ordinal": ordinal,
            "event": "evidence_published",
            "relative_path": str(relative),
            "file_sha256": _sha(payload),
            "record_kind": record_kind or projected["record_kind"],
        }
    )
    return destination


def _replace_first_publication(
    state: dict[str, Any],
    root: Path,
    scope: ProviderAttemptScope,
    record: dict[str, Any],
    *,
    canonical: bool = True,
) -> None:
    entry = _allocation(state, scope)
    entry["events"] = [{"ordinal": 1, "event": "allocated"}]
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


def test_prompt_context_closed_status_and_nullability_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    authority = _allocation(state, scope)[
        "prompt_fragment_identity_schema_version"
    ]
    _replace_first_publication(state, root, scope, v2)

    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, _legacy(v2))
    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, _ordinary_failure(v2))
    _append_allocation(state, scope)
    ordinal = _append_allocation(state, scope)
    invalid = deepcopy(v2)
    _publish(
        state,
        root,
        scope,
        ordinal,
        invalid,
        canonical=False,
        tamper=lambda record: record.__setitem__(
            "record_sha256",
            "sha256:" + "0" * 64,
        ),
    )
    ordinal = _append_allocation(state, scope)
    _publish(
        state,
        root,
        scope,
        ordinal,
        _preparation_failure(v2, authority=authority),
    )

    report = _project(state, root)
    rows = report["attempts"]

    assert tuple(report) == ("schema_version", "attempts")
    assert report["schema_version"] == REPORT_SCHEMA
    assert [row["record_status"] for row in rows] == [
        "snapshot",
        "legacy_snapshot",
        "failure",
        "allocation_only",
        "invalid",
        "failure",
    ]
    assert [row["comparison"]["reason"] for row in rows] == [
        "no_predecessor",
        "legacy_snapshot_only",
        "current_record_missing",
        "current_record_missing",
        "current_record_invalid",
        "provider_policy_unresolved",
    ]
    assert all(
        tuple(row)
        == (
            "runtime_step_id",
            "visit_key",
            "attempt_ordinal",
            "record_status",
            "record_sha256",
            "identity",
            "comparison",
        )
        for row in rows
    )
    assert rows[0]["record_sha256"] == v2["record_sha256"]
    assert rows[0]["identity"]["composition_sha256"] == (
        v2["prompt_attempt_identity"]["composition_sha256"]
    )
    assert tuple(rows[0]["identity"]["role_sha256"]) == ROLE_ORDER
    assert rows[0]["identity"]["final_prompt_sha256"] == (
        v2["prompt_attempt_identity"]["final_prompt"]["sha256"]
    )
    for row in rows[1:]:
        assert row["identity"] is None
    assert rows[1]["record_sha256"] is not None
    assert rows[2]["record_sha256"] is not None
    assert rows[3]["record_sha256"] is None
    assert rows[4]["record_sha256"] is None
    assert rows[5]["record_sha256"] is not None
    assert "sha256:" + "0" * 64 not in json.dumps(report)


@pytest.mark.parametrize(
    "retained_authority",
    (None, "compiled_prompt_fragment_identity.v1"),
)
def test_prompt_context_v2_requires_exact_persisted_scope_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    retained_authority: str | None,
) -> None:
    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    entry = _allocation(state, scope)
    if retained_authority is None:
        entry.pop("prompt_fragment_identity_schema_version")
    else:
        entry["prompt_fragment_identity_schema_version"] = (
            retained_authority
        )
    _replace_first_publication(
        state,
        root,
        scope,
        v2,
        canonical=False,
    )
    ordinal = _append_allocation(state, scope)
    _publish(state, root, scope, ordinal, _legacy(v2))

    rows = _project(state, root)["attempts"]

    assert [row["record_status"] for row in rows] == [
        "invalid",
        "legacy_snapshot",
    ]
    assert rows[0]["identity"] is None


def test_prompt_context_preparation_failure_requires_scope_authority_agreement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    _replace_first_publication(state, root, scope, v2)
    ordinal = _append_allocation(state, scope)
    _publish(
        state,
        root,
        scope,
        ordinal,
        _preparation_failure(
            v2,
            authority="compiled_prompt_fragment_identity.v1",
        ),
    )

    rows = _project(state, root)["attempts"]

    assert rows[-1]["record_status"] == "invalid"
    assert rows[-1]["comparison"]["reason"] == "current_record_invalid"


def test_prompt_context_available_comparison_and_fixed_role_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    _replace_first_publication(state, root, scope, v2)
    ordinal = _append_allocation(state, scope)
    _publish(
        state,
        root,
        scope,
        ordinal,
        _with_changed_policy(v2),
    )

    current = _project(state, root)["attempts"][-1]

    assert current["comparison"] == {
        "status": "available",
        "previous_attempt_ordinal": 1,
        "classifications": ["provider_policy_drift"],
        "reason": None,
    }
    assert tuple(current["identity"]["role_sha256"]) == ROLE_ORDER


@pytest.mark.parametrize(
    ("blocker", "expected_reason"),
    (
        ("legacy", "legacy_snapshot_only"),
        ("invalid", "previous_record_invalid"),
    ),
)
def test_prompt_context_newer_snapshot_blocks_older_v2_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocker: str,
    expected_reason: str,
) -> None:
    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    _replace_first_publication(state, root, scope, v2)
    ordinal = _append_allocation(state, scope)
    candidate = _legacy(v2) if blocker == "legacy" else deepcopy(v2)
    _publish(
        state,
        root,
        scope,
        ordinal,
        candidate,
        canonical=blocker == "legacy",
        tamper=(
            None
            if blocker == "legacy"
            else lambda record: record.__setitem__(
                "record_sha256",
                "sha256:" + "0" * 64,
            )
        ),
    )
    ordinal = _append_allocation(state, scope)
    _publish(
        state,
        root,
        scope,
        ordinal,
        _with_changed_policy(v2),
    )

    comparison = _project(state, root)["attempts"][-1]["comparison"]

    assert comparison == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": [],
        "reason": expected_reason,
    }


@pytest.mark.parametrize("middle", ("failure", "allocation_only"))
def test_prompt_context_skips_non_snapshot_predecessors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    middle: str,
) -> None:
    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    _replace_first_publication(state, root, scope, v2)
    ordinal = _append_allocation(state, scope)
    if middle == "failure":
        _publish(state, root, scope, ordinal, _ordinary_failure(v2))
    ordinal = _append_allocation(state, scope)
    _publish(
        state,
        root,
        scope,
        ordinal,
        _with_changed_policy(v2),
    )

    comparison = _project(state, root)["attempts"][-1]["comparison"]

    assert comparison["status"] == "available"
    assert comparison["previous_attempt_ordinal"] == 1


def test_prompt_context_composition_mismatch_is_closed_unavailability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    _replace_first_publication(state, root, scope, v2)
    ordinal = _append_allocation(state, scope)
    _publish(
        state,
        root,
        scope,
        ordinal,
        _with_unmodelled_final_prompt(v2),
    )

    comparison = _project(state, root)["attempts"][-1]["comparison"]

    assert comparison["status"] == "unavailable"
    assert comparison["reason"] == "prompt_identity_composition_mismatch"


def test_prompt_context_uses_allocator_domain_and_marks_missing_file_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        evidence_relative_path,
    )

    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    _replace_first_publication(state, root, scope, v2)
    ordinal = _append_allocation(state, scope)
    missing = evidence_relative_path(scope, ordinal)
    _allocation(state, scope)["events"].append(
        {
            "ordinal": ordinal,
            "event": "evidence_published",
            "relative_path": str(missing),
            "file_sha256": _sha(b"missing"),
            "record_kind": "prompt_snapshot",
        }
    )
    _append_allocation(state, scope)

    rows = _project(state, root)["attempts"]

    assert [row["attempt_ordinal"] for row in rows] == [1, 2, 3]
    assert [row["record_status"] for row in rows] == [
        "snapshot",
        "invalid",
        "allocation_only",
    ]
    assert rows[1]["record_sha256"] is None


def test_prompt_context_does_not_infer_qualification_from_names_or_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    scope_node = scope.to_dict()
    scope_node["runtime_step_id"] = "prompt-fragment-looking-name"
    scope_node["enclosing_step"]["step_id"] = (
        "prompt-fragment-looking-name"
    )
    scope = ProviderAttemptScope.from_dict(scope_node)
    _reset_scope(state, scope, authority=None)
    non_fragment = _legacy(v2)
    non_fragment["schema"] = (
        "workflow_prompt_dependency_evidence.functional.v1"
    )
    non_fragment["compiler_contract"]["origin_kind"] = (
        "workflow_lisp_provider_result_prompt_dependencies"
    )
    non_fragment.pop("compiled_prompt_fragment_identity")
    _seal(non_fragment)
    _publish(state, root, scope, 1, non_fragment)

    assert "prompt" in scope.runtime_step_id.lower()
    assert _project(state, root) == {
        "schema_version": REPORT_SCHEMA,
        "attempts": [],
    }


def test_prompt_context_order_is_runtime_bytes_then_visit_then_ordinal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, original, v2 = _fixture(tmp_path, monkeypatch)
    legacy = _legacy(v2)
    scopes = []
    for runtime_step_id, frames in (
        ("z-step", []),
        ("a-step", ["frame-b"]),
        ("a-step", ["frame-a"]),
    ):
        node = original.to_dict()
        node["runtime_step_id"] = runtime_step_id
        node["enclosing_step"]["step_id"] = runtime_step_id
        node["resume_scope"]["call_frame_ids"] = frames
        scopes.append(ProviderAttemptScope.from_dict(node))
    state["provider_attempt_allocations"] = {}
    for scope in scopes:
        state["provider_attempt_allocations"][scope.key] = {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 1,
            "events": [{"ordinal": 1, "event": "allocated"}],
        }
        _publish(state, root, scope, 1, legacy)

    rows = _project(state, root)["attempts"]

    assert [
        (row["runtime_step_id"], row["visit_key"])
        for row in rows
    ] == sorted(
        [
            (scope.runtime_step_id, scope.key[7:31])
            for scope in scopes
        ],
        key=lambda value: (value[0].encode("utf-8"), value[1]),
    )


def test_prompt_context_duplicate_publication_fails_before_row_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, root, scope, _v2 = _fixture(tmp_path, monkeypatch)
    entry = _allocation(state, scope)
    entry["events"].append(deepcopy(entry["events"][-1]))

    with pytest.raises(ValueError, match="publication|canonical"):
        _project(state, root)


@pytest.mark.parametrize("status", ("running", "failed", "completed"))
def test_prompt_context_projection_is_status_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    state, root, _scope_value, _v2 = _fixture(tmp_path, monkeypatch)
    expected = _project(state, root)
    state["status"] = status

    assert _project(state, root) == expected


def test_loaded_and_state_only_reports_share_exact_prompt_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.cli.commands.report import _state_only_snapshot
    from orchestrator.observability.report import build_status_snapshot
    from tests.test_workflow_lisp_prompt_identity_runtime import (
        _runtime_q3_fixture,
    )

    state, root, _scope_value, _v2 = _fixture(tmp_path, monkeypatch)
    loaded_root = tmp_path / "loaded"
    loaded_root.mkdir()
    bundle, _unused_manager = _runtime_q3_fixture(loaded_root)

    loaded = build_status_snapshot(bundle, state, root)
    state_only = _state_only_snapshot(state, root)

    assert loaded["prompt_context"] == state_only["prompt_context"]
    assert loaded["prompt_context"] == _project(state, root)


def test_prompt_context_markdown_is_content_free_and_keeps_closed_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.observability.report import render_status_markdown

    state, root, scope, v2 = _fixture(tmp_path, monkeypatch)
    sentinel_values = (
        "PROMPT-SENTINEL",
        "RESOLVED-VALUE-SENTINEL",
        "DEPENDENCY-BYTES-SENTINEL",
        "COMMAND-SENTINEL",
        "ENV-SENTINEL",
        "/absolute/workspace/sentinel",
    )
    ordinal = _append_allocation(state, scope)
    invalid = deepcopy(v2)
    invalid["unvalidated_material"] = list(sentinel_values)
    _publish(
        state,
        root,
        scope,
        ordinal,
        invalid,
        canonical=False,
    )
    snapshot = {
        "run": {},
        "progress": {},
        "steps": [],
        "prompt_context": _project(state, root),
    }

    markdown = render_status_markdown(snapshot)

    assert "## Prompt context" in markdown
    assert "snapshot" in markdown
    assert "fragment_program" in markdown
    for sentinel in sentinel_values:
        assert sentinel not in markdown


def test_execution_and_resume_do_not_call_prompt_context_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow import prompt_context_report
    from orchestrator.workflow.executor import WorkflowExecutor
    from tests.test_workflow_lisp_prompt_identity_runtime import (
        _prepared_invocation,
        _runtime_q3_fixture,
        _successful_execution,
    )

    bundle, manager = _runtime_q3_fixture(tmp_path)
    monkeypatch.setattr(
        prompt_context_report,
        "project_prompt_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runtime must not call report projection")
        ),
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        lambda _self, *_args, **kwargs: (
            _prepared_invocation(
                kwargs["prompt_content"],
                kwargs.get("env") or {},
            ),
            None,
        ),
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "execute",
        lambda _self, invocation, **_kwargs: _successful_execution(
            tmp_path,
            invocation,
        ),
    )
    executor = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    )

    assert executor.execute(on_error="stop")["status"] == "completed"
    assert executor.execute(resume=True, on_error="stop")["status"] == (
        "completed"
    )
