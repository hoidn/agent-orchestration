"""Closed, read-only Q4 judgment-view projection."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.runtime_observability import (
    record_compiled_frontend_provenance,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.prompt_identity import (
    ROLE_ORDER,
    canonical_sha256,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)


EMPTY_VIEWS = {
    "schema_version": "workflow_judgment_views.v1",
    "judgments": [],
    "matrices": [],
    "disagreements": [],
    "iteration_series": [],
}


def _project(
    state: dict[str, Any],
    run_root: Path,
    *,
    workspace_root: Path,
) -> dict[str, Any]:
    from orchestrator.workflow.judgment_views import (
        project_judgment_views,
    )

    return project_judgment_views(
        state,
        run_root,
        workspace_root=workspace_root,
    )


def _available_root_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    dict[str, Any],
    Path,
    ProviderAttemptScope,
    dict[str, Any],
    dict[str, Any],
]:
    from tests.test_workflow_lisp_prompt_calculus_runtime import (
        _compile_runtime_fragment,
        _provider_success,
        _runtime_fragment_manager,
    )

    generated_source, _discarded = _compile_runtime_fragment(
        tmp_path,
        lowering_route="wcc_m4",
        target_dsl="2.22",
        with_output_position=True,
    )
    source_path = tmp_path / "demo" / "prompt-runtime.orc"
    source_path.parent.mkdir(parents=True)
    generated_source.replace(source_path)
    providers = tmp_path / "providers.json"
    providers.write_text(
        json.dumps({"providers.review": "capturing-provider"}),
        encoding="utf-8",
    )
    build = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="run-review",
            provider_externs_path=providers,
            workspace_root=tmp_path,
            lowering_route="wcc_m4",
        )
    )
    bundle = build.validated_bundle
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="q4-judgment-view",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, base_execute = _provider_success(tmp_path, captured)

    def execute(provider: object, invocation: object, **kwargs: Any) -> object:
        report = tmp_path / "artifacts" / "work" / "review.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("reviewed\n", encoding="utf-8")
        return base_execute(provider, invocation, **kwargs)

    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    )
    monkeypatch.setattr(ProviderExecutor, "execute", execute)
    state = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")
    assert state["status"] == "completed"
    record_compiled_frontend_provenance(
        state,
        build.validated_bundle.provenance,
    )
    allocation = next(
        iter(state["provider_attempt_allocations"].values())
    )
    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    publication = next(
        event
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    )
    record = json.loads(
        (
            manager.run_root / publication["relative_path"]
        ).read_text(encoding="utf-8")
    )
    result = next(
        step
        for step in state["steps"].values()
        if step.get("step_id") == scope.runtime_step_id
    )
    return state, manager.run_root, scope, record, result


def _coordinate(
    state: dict[str, Any],
    scope: ProviderAttemptScope,
) -> dict[str, Any]:
    loop = scope.loop_iteration
    return {
        "root_workflow_identity": state["workflow_checksum"],
        "call_frame_path": list(scope.resume_scope.call_frame_ids),
        "runtime_step_id": scope.runtime_step_id,
        "enclosing_step_id": scope.enclosing_step.step_id,
        "enclosing_visit": scope.enclosing_step.visit_count,
        "loop": (
            None
            if loop is None
            else {
                "kind": loop.kind,
                "step_id": loop.loop_step_id,
                "iteration": loop.iteration,
            }
        ),
    }


def test_judgment_views_empty_projection_is_stable_without_allocations(
    tmp_path: Path,
) -> None:
    state = {
        "run_id": "empty",
        "workflow_file": "workflow.orc",
        "workflow_checksum": "sha256:" + "1" * 64,
        "provider_attempt_allocations": {},
        "steps": {},
        "call_frames": {},
    }

    assert _project(
        state,
        tmp_path / ".orchestrate" / "runs" / "empty",
        workspace_root=tmp_path,
    ) == EMPTY_VIEWS


def test_non_fragment_allocation_keeps_empty_projection_without_compiled_state(
    tmp_path: Path,
) -> None:
    scope = ProviderAttemptScope.from_dict(
        {
            "run_id": "old-run",
            "resume_scope": {
                "root_workflow_file": "workflow.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "root.provider",
            "enclosing_step": {
                "step_name": "provider",
                "step_id": "root.provider",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )
    state = {
        "run_id": "old-run",
        "workflow_file": "workflow.orc",
        "provider_attempt_allocations": {
            scope.key: {
                "scope": scope.to_dict(),
                "last_allocated_ordinal": 1,
                "events": [{"ordinal": 1, "event": "allocated"}],
            }
        },
    }

    assert _project(
        state,
        tmp_path / "missing-run-root",
        workspace_root=tmp_path,
    ) == EMPTY_VIEWS


def test_judgment_views_projects_one_available_root_scalar_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.judgment_views import (
        resolve_persisted_result_contract,
    )

    state, run_root, scope, record, result = _available_root_fixture(
        tmp_path,
        monkeypatch,
    )
    contract = resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=state,
        scope=scope,
    )
    identity = record["prompt_attempt_identity"]
    locator = result["debug"]["prompt_attempt_result_binding"]
    coordinate = _coordinate(state, scope)
    value = result["artifacts"]["__result__"]
    expected_judgment = {
        "schema_version": "workflow_judgment_inspection.v1",
        "status": "available",
        "coordinate": coordinate,
        "attempt_ordinal": locator["attempt_ordinal"],
        "result": {
            "declared_shape": "root_value",
            "contract_sha256": contract.contract_sha256,
            "value_sha256": canonical_sha256(value),
            "value": value,
            "comparison": {
                "kind": "canonical_value",
                "value": value,
            },
        },
        "provenance": {
            "evidence_record_sha256": record["record_sha256"],
            "identity_schema_version": (
                "workflow_prompt_attempt_identity.v1"
            ),
            "role_sha256": {
                role: identity["roles"][role]["sha256"]
                for role in ROLE_ORDER
            },
            "final_prompt_sha256": identity["final_prompt"]["sha256"],
            "composition_sha256": identity["composition_sha256"],
            "comparison": {
                "status": "unavailable",
                "previous_attempt_ordinal": None,
                "classifications": [],
                "reason": "no_predecessor",
            },
        },
    }

    projected = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )

    assert projected["judgments"] == [expected_judgment]
    assert projected["matrices"] == [
        {
            "schema_version": "workflow_judgment_matrix.v1",
            "group": {
                "root_workflow_identity": state["workflow_checksum"],
                "runtime_step_id": scope.runtime_step_id,
            },
            "members": [
                {
                    "coordinate": coordinate,
                    "status": "comparable",
                    "comparison": {
                        "kind": "canonical_value",
                        "value": value,
                    },
                    "result_value_sha256": canonical_sha256(value),
                    "evidence_record_sha256": record["record_sha256"],
                    "reason": None,
                }
            ],
        }
    ]
    assert projected["disagreements"] == [
        {
            "schema_version": "workflow_judgment_disagreement.v1",
            "group": {
                "root_workflow_identity": state["workflow_checksum"],
                "runtime_step_id": scope.runtime_step_id,
            },
            "status": "insufficient_members",
            "available_member_count": 1,
            "comparable_member_count": 1,
            "not_comparable_member_count": 0,
            "unavailable_member_count": 0,
            "distinct_comparison_key_count": 1,
        }
    ]
    assert projected["iteration_series"] == [
        {
            "schema_version": (
                "workflow_judgment_iteration_series.v1"
            ),
            "scope_sha256": scope.key,
            "coordinate": coordinate,
            "attempts": [
                {
                    "attempt_ordinal": 1,
                    "record_status": "snapshot",
                    "record_sha256": record["record_sha256"],
                    "comparison": {
                        "status": "unavailable",
                        "previous_attempt_ordinal": None,
                        "classifications": [],
                        "reason": "no_predecessor",
                    },
                    "committed_result_status": "bound",
                }
            ],
        }
    ]


def test_pre_q4_result_without_locator_is_unavailable_and_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, run_root, scope, record, result = _available_root_fixture(
        tmp_path,
        monkeypatch,
    )
    result["debug"].pop("prompt_attempt_result_binding")
    coordinate = _coordinate(state, scope)

    projected = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )

    assert projected["judgments"] == [
        {
            "schema_version": "workflow_judgment_inspection.v1",
            "status": "unavailable",
            "coordinate": coordinate,
            "reason": "judgment_result_binding_missing",
        }
    ]
    assert projected["matrices"] == [
        {
            "schema_version": "workflow_judgment_matrix.v1",
            "group": {
                "root_workflow_identity": state["workflow_checksum"],
                "runtime_step_id": scope.runtime_step_id,
            },
            "members": [
                {
                    "coordinate": coordinate,
                    "status": "unavailable",
                    "comparison": None,
                    "result_value_sha256": None,
                    "evidence_record_sha256": None,
                    "reason": "judgment_result_binding_missing",
                }
            ],
        }
    ]
    assert projected["disagreements"] == [
        {
            "schema_version": "workflow_judgment_disagreement.v1",
            "group": {
                "root_workflow_identity": state["workflow_checksum"],
                "runtime_step_id": scope.runtime_step_id,
            },
            "status": "insufficient_members",
            "available_member_count": 0,
            "comparable_member_count": 0,
            "not_comparable_member_count": 0,
            "unavailable_member_count": 1,
            "distinct_comparison_key_count": 0,
        }
    ]
    assert projected["iteration_series"] == [
        {
            "schema_version": (
                "workflow_judgment_iteration_series.v1"
            ),
            "scope_sha256": scope.key,
            "coordinate": coordinate,
            "attempts": [
                {
                    "attempt_ordinal": 1,
                    "record_status": "snapshot",
                    "record_sha256": record["record_sha256"],
                    "comparison": {
                        "status": "unavailable",
                        "previous_attempt_ordinal": None,
                        "classifications": [],
                        "reason": "no_predecessor",
                    },
                    "committed_result_status": "unknown_pre_q4",
                }
            ],
        }
    ]


def test_tampered_bound_evidence_makes_only_the_view_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, run_root, scope, _record, result = _available_root_fixture(
        tmp_path,
        monkeypatch,
    )
    locator = result["debug"]["prompt_attempt_result_binding"]
    evidence_path = run_root / locator["evidence_relative_path"]
    evidence_path.write_bytes(evidence_path.read_bytes() + b"\n")

    projected = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )

    assert state["status"] == "completed"
    assert projected["judgments"] == [
        {
            "schema_version": "workflow_judgment_inspection.v1",
            "status": "unavailable",
            "coordinate": _coordinate(state, scope),
            "reason": "judgment_result_evidence_invalid",
        }
    ]
    assert projected["matrices"][0]["members"][0]["status"] == (
        "unavailable"
    )
    assert projected["matrices"][0]["members"][0]["reason"] == (
        "judgment_result_evidence_invalid"
    )


def test_duplicate_publication_claim_is_one_ambiguous_unavailable_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, run_root, scope, _record, _result = _available_root_fixture(
        tmp_path,
        monkeypatch,
    )
    allocation = state["provider_attempt_allocations"][scope.key]
    publication = next(
        event
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    )
    allocation["events"].append(deepcopy(publication))

    projected = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )

    assert projected["judgments"] == [
        {
            "schema_version": "workflow_judgment_inspection.v1",
            "status": "unavailable",
            "coordinate": _coordinate(state, scope),
            "reason": "judgment_result_binding_ambiguous",
        }
    ]


@pytest.mark.parametrize(
    ("damage", "expected_reason"),
    (
        ("invalid", "judgment_result_binding_invalid"),
        ("scope", "judgment_result_scope_mismatch"),
        ("attempt", "judgment_result_attempt_mismatch"),
    ),
)
def test_locator_tamper_maps_to_one_closed_unavailable_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
    expected_reason: str,
) -> None:
    state, run_root, scope, _record, result = _available_root_fixture(
        tmp_path,
        monkeypatch,
    )
    locator = result["debug"]["prompt_attempt_result_binding"]
    if damage == "invalid":
        locator["attempt_ordinal"] = True
    elif damage == "scope":
        locator["scope_sha256"] = "sha256:" + "0" * 64
    else:
        locator["attempt_ordinal"] = 2

    projected = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )

    assert projected["judgments"] == [
        {
            "schema_version": "workflow_judgment_inspection.v1",
            "status": "unavailable",
            "coordinate": _coordinate(state, scope),
            "reason": expected_reason,
        }
    ]


def test_committed_result_value_tamper_is_closed_unavailability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, run_root, scope, _record, result = _available_root_fixture(
        tmp_path,
        monkeypatch,
    )
    result["artifacts"]["__result__"] = "not-a-bool"

    projected = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )

    assert projected["judgments"] == [
        {
            "schema_version": "workflow_judgment_inspection.v1",
            "status": "unavailable",
            "coordinate": _coordinate(state, scope),
            "reason": "judgment_result_value_mismatch",
        }
    ]


def test_persisted_visit_coordinate_tamper_is_closed_unavailability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, run_root, scope, _record, _result = _available_root_fixture(
        tmp_path,
        monkeypatch,
    )
    state["step_visits"][scope.enclosing_step.step_name] = 2

    projected = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )

    assert projected["judgments"] == [
        {
            "schema_version": "workflow_judgment_inspection.v1",
            "status": "unavailable",
            "coordinate": _coordinate(state, scope),
            "reason": "judgment_result_coordinate_invalid",
        }
    ]


def test_json_round_tripped_state_has_identical_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, run_root, _scope_value, _record, _result = (
        _available_root_fixture(tmp_path, monkeypatch)
    )

    loaded = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )
    state_only = _project(
        json.loads(json.dumps(state)),
        run_root,
        workspace_root=tmp_path,
    )

    assert state_only == loaded


def test_reversing_allocator_discovery_does_not_change_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, run_root, _scope_value, _record, _result = (
        _available_root_fixture(tmp_path, monkeypatch)
    )
    other_scope = ProviderAttemptScope.from_dict(
        {
            "run_id": state["run_id"],
            "resume_scope": {
                "root_workflow_file": state["workflow_file"],
                "call_frame_ids": [],
            },
            "runtime_step_id": "ineligible.unreached",
            "enclosing_step": {
                "step_name": "unreached",
                "step_id": "ineligible.unreached",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )
    state["provider_attempt_allocations"][other_scope.key] = {
        "scope": other_scope.to_dict(),
        "last_allocated_ordinal": 1,
        "events": [{"ordinal": 1, "event": "allocated"}],
        "prompt_fragment_identity_schema_version": (
            "compiled_prompt_fragment_identity.v2"
        ),
    }
    forward = _project(
        state,
        run_root,
        workspace_root=tmp_path,
    )
    state["provider_attempt_allocations"] = dict(
        reversed(
            tuple(state["provider_attempt_allocations"].items())
        )
    )

    assert _project(
        state,
        run_root,
        workspace_root=tmp_path,
    ) == forward


def test_execution_resume_and_parser_modules_do_not_consume_judgment_views(
) -> None:
    repository_root = Path(__file__).parents[1]
    runtime_paths = sorted(
        path
        for path in (repository_root / "orchestrator").rglob("*.py")
        if (
            "executor" in path.stem
            or "resume" in path.stem
            or "parser" in path.stem
            or path.name in {"reader.py", "syntax.py"}
        )
    )

    assert runtime_paths
    for path in runtime_paths:
        assert "project_judgment_views" not in path.read_text(
            encoding="utf-8"
        ), path

    for relative in (
        "orchestrator/cli/commands/report.py",
        "orchestrator/observability/report.py",
    ):
        source = (repository_root / relative).read_text(encoding="utf-8")
        assert "project_judgment_views" in source


def _synthetic_coordinate(visit: int) -> dict[str, Any]:
    return {
        "root_workflow_identity": "sha256:" + "a" * 64,
        "call_frame_path": [f"frame-{visit}"],
        "runtime_step_id": "root.judge",
        "enclosing_step_id": "root.judge",
        "enclosing_visit": visit,
        "loop": None,
    }


def _synthetic_available(
    *,
    visit: int,
    value: Any,
    comparable: bool = True,
) -> dict[str, Any]:
    comparison = (
        {"kind": "canonical_value", "value": value}
        if comparable
        else None
    )
    return {
        "schema_version": "workflow_judgment_inspection.v1",
        "status": "available",
        "coordinate": _synthetic_coordinate(visit),
        "attempt_ordinal": 1,
        "result": {
            "declared_shape": (
                "root_value" if comparable else "record_value"
            ),
            "contract_sha256": "sha256:" + "b" * 64,
            "value_sha256": canonical_sha256(value),
            "value": deepcopy(value),
            "comparison": comparison,
        },
        "provenance": {
            "evidence_record_sha256": (
                "sha256:" + f"{visit:x}" * 64
            )[:71],
            "identity_schema_version": (
                "workflow_prompt_attempt_identity.v1"
            ),
            "role_sha256": {
                role: "sha256:" + "c" * 64 for role in ROLE_ORDER
            },
            "final_prompt_sha256": "sha256:" + "d" * 64,
            "composition_sha256": "sha256:" + "e" * 64,
            "comparison": {
                "status": "unavailable",
                "previous_attempt_ordinal": None,
                "classifications": [],
                "reason": "no_predecessor",
            },
        },
    }


def _synthetic_unavailable(*, visit: int) -> dict[str, Any]:
    return {
        "schema_version": "workflow_judgment_inspection.v1",
        "status": "unavailable",
        "coordinate": _synthetic_coordinate(visit),
        "reason": "judgment_result_evidence_invalid",
    }


@pytest.mark.parametrize(
    ("judgments", "expected"),
    (
        (
            (
                _synthetic_available(visit=2, value=True),
                _synthetic_unavailable(visit=1),
            ),
            {
                "status": "insufficient_members",
                "available_member_count": 1,
                "comparable_member_count": 1,
                "not_comparable_member_count": 0,
                "unavailable_member_count": 1,
                "distinct_comparison_key_count": 1,
            },
        ),
        (
            (
                _synthetic_available(visit=2, value=True),
                _synthetic_available(visit=1, value=True),
            ),
            {
                "status": "agree",
                "available_member_count": 2,
                "comparable_member_count": 2,
                "not_comparable_member_count": 0,
                "unavailable_member_count": 0,
                "distinct_comparison_key_count": 1,
            },
        ),
        (
            (
                _synthetic_available(visit=2, value=False),
                _synthetic_available(visit=1, value=True),
            ),
            {
                "status": "disagree",
                "available_member_count": 2,
                "comparable_member_count": 2,
                "not_comparable_member_count": 0,
                "unavailable_member_count": 0,
                "distinct_comparison_key_count": 2,
            },
        ),
        (
            (
                _synthetic_available(visit=2, value={"score": 2}, comparable=False),
                _synthetic_available(visit=1, value=True),
            ),
            {
                "status": "not_comparable",
                "available_member_count": 2,
                "comparable_member_count": 1,
                "not_comparable_member_count": 1,
                "unavailable_member_count": 0,
                "distinct_comparison_key_count": 1,
            },
        ),
    ),
)
def test_group_views_classify_all_four_states_and_ignore_input_order(
    judgments: tuple[dict[str, Any], ...],
    expected: dict[str, Any],
) -> None:
    from orchestrator.workflow.judgment_views import (
        _project_group_views,
    )

    matrices, disagreements = _project_group_views(list(judgments))
    reverse_matrices, reverse_disagreements = _project_group_views(
        list(reversed(judgments))
    )

    assert (reverse_matrices, reverse_disagreements) == (
        matrices,
        disagreements,
    )
    assert len(matrices) == len(disagreements) == 1
    assert [
        member["coordinate"]["enclosing_visit"]
        for member in matrices[0]["members"]
    ] == [1, 2]
    assert disagreements[0] == {
        "schema_version": "workflow_judgment_disagreement.v1",
        "group": {
            "root_workflow_identity": "sha256:" + "a" * 64,
            "runtime_step_id": "root.judge",
        },
        **expected,
    }


def test_duplicate_structural_members_collapse_to_group_invalid_both_directions(
) -> None:
    from orchestrator.workflow.judgment_views import (
        _project_group_views,
    )

    rows = (
        _synthetic_available(visit=1, value=True),
        _synthetic_available(visit=1, value=False),
    )
    forward = _project_group_views(rows)
    reverse = _project_group_views(tuple(reversed(rows)))

    assert reverse == forward
    matrices, disagreements = forward
    assert matrices[0]["members"] == [
        {
            "coordinate": _synthetic_coordinate(1),
            "status": "unavailable",
            "comparison": None,
            "result_value_sha256": None,
            "evidence_record_sha256": None,
            "reason": "judgment_view_group_invalid",
        }
    ]
    assert disagreements[0]["status"] == "insufficient_members"
    assert disagreements[0]["unavailable_member_count"] == 1


@pytest.mark.parametrize(
    "comparison",
    (
        {
            "status": "available",
            "previous_attempt_ordinal": "1",
            "classifications": ["invented"],
            "reason": "invented",
        },
        {
            "status": "unavailable",
            "previous_attempt_ordinal": 1,
            "classifications": ["input_drift"],
            "reason": None,
        },
    ),
)
@pytest.mark.parametrize("location", ("provenance", "series"))
def test_closed_q3_comparison_rejects_invalid_status_dependent_fields(
    comparison: dict[str, Any],
    location: str,
) -> None:
    from orchestrator.workflow.judgment_views import (
        _project_group_views,
        validate_judgment_views_projection,
    )

    judgment = _synthetic_available(visit=1, value=True)
    matrices, disagreements = _project_group_views([judgment])
    series = {
        "schema_version": "workflow_judgment_iteration_series.v1",
        "scope_sha256": "sha256:" + "f" * 64,
        "coordinate": _synthetic_coordinate(1),
        "attempts": [
            {
                "attempt_ordinal": 1,
                "record_status": "snapshot",
                "record_sha256": "sha256:" + "0" * 64,
                "comparison": {
                    "status": "unavailable",
                    "previous_attempt_ordinal": None,
                    "classifications": [],
                    "reason": "no_predecessor",
                },
                "committed_result_status": "bound",
            }
        ],
    }
    if location == "provenance":
        judgment["provenance"]["comparison"] = comparison
    else:
        series["attempts"][0]["comparison"] = comparison
    candidate = {
        "schema_version": "workflow_judgment_views.v1",
        "judgments": [judgment],
        "matrices": matrices,
        "disagreements": disagreements,
        "iteration_series": [series],
    }

    with pytest.raises(ValueError, match="Q3 comparison"):
        validate_judgment_views_projection(candidate)


@pytest.mark.parametrize(
    ("declared_shape", "value", "comparison"),
    (
        (
            "root_value",
            True,
            {"kind": "canonical_value", "value": False},
        ),
        (
            "root_value",
            True,
            {"kind": "union_variant", "value": "PASS"},
        ),
        (
            "record_value",
            {"decision": "PASS"},
            {"kind": "canonical_value", "value": "PASS"},
        ),
        (
            "union_value",
            {"variant": "PASS", "value": {}},
            {"kind": "canonical_value", "value": "PASS"},
        ),
        (
            "union_value",
            {"variant": "PASS", "value": {}},
            {"kind": "union_variant", "value": "FAIL"},
        ),
        (
            "union_value",
            {"variant": "PASS", "value": {}},
            None,
        ),
    ),
)
def test_result_comparison_must_match_declared_shape_and_exact_value(
    declared_shape: str,
    value: Any,
    comparison: dict[str, Any] | None,
) -> None:
    from orchestrator.workflow.judgment_views import (
        _project_group_views,
        validate_judgment_views_projection,
    )

    judgment = _synthetic_available(visit=1, value=value)
    judgment["result"].update(
        {
            "declared_shape": declared_shape,
            "value_sha256": canonical_sha256(value),
            "comparison": comparison,
        }
    )
    matrices, disagreements = _project_group_views([judgment])
    candidate = {
        "schema_version": "workflow_judgment_views.v1",
        "judgments": [judgment],
        "matrices": matrices,
        "disagreements": disagreements,
        "iteration_series": [],
    }

    with pytest.raises(ValueError, match="comparison"):
        validate_judgment_views_projection(candidate)


@pytest.mark.parametrize(
    "statuses",
    (
        ("bound", "unknown_pre_q4"),
        ("unknown_pre_q4", "bound"),
        ("not_bound", "unknown_pre_q4"),
        ("unknown_pre_q4", "not_bound"),
    ),
)
def test_iteration_series_rejects_impossible_mixed_commit_statuses(
    statuses: tuple[str, str],
) -> None:
    from orchestrator.workflow.judgment_views import (
        validate_judgment_views_projection,
    )

    comparison = {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": [],
        "reason": "no_predecessor",
    }
    candidate = {
        "schema_version": "workflow_judgment_views.v1",
        "judgments": [],
        "matrices": [],
        "disagreements": [],
        "iteration_series": [
            {
                "schema_version": (
                    "workflow_judgment_iteration_series.v1"
                ),
                "scope_sha256": "sha256:" + "f" * 64,
                "coordinate": _synthetic_coordinate(1),
                "attempts": [
                    {
                        "attempt_ordinal": ordinal,
                        "record_status": "allocation_only",
                        "record_sha256": None,
                        "comparison": comparison,
                        "committed_result_status": status,
                    }
                    for ordinal, status in enumerate(statuses, start=1)
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="commit statuses"):
        validate_judgment_views_projection(candidate)


def test_record_union_and_list_values_rehydrate_without_name_heuristics(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.judgment_views import (
        ResolvedPersistedResultContract,
        _rehydrate_result_value,
        _result_comparison,
    )

    record = ResolvedPersistedResultContract(
        workflow_name="generic",
        persisted_step_id="root.record",
        contract_kind="output_bundle",
        declared_shape="record_value",
        contract={
            "path": "result.json",
            "fields": (
                {
                    "name": "outcome",
                    "json_pointer": "/outcome",
                    "type": "enum",
                    "allowed": ("PASS", "FAIL"),
                },
                {
                    "name": "score",
                    "json_pointer": "/metrics/score",
                    "type": "float",
                },
            ),
        },
        contract_sha256="sha256:" + "1" * 64,
    )
    record_value = _rehydrate_result_value(
        result={
            "artifacts": {"outcome": "PASS", "score": 0.75}
        },
        resolved=record,
        workspace=tmp_path,
    )
    assert record_value == {
        "outcome": "PASS",
        "metrics": {"score": 0.75},
    }
    assert _result_comparison(record, record_value) is None

    union = ResolvedPersistedResultContract(
        workflow_name="generic",
        persisted_step_id="root.union",
        contract_kind="variant_output",
        declared_shape="union_value",
        contract={
            "path": "result.json",
            "discriminant": {
                "name": "variant",
                "json_pointer": "/variant",
                "type": "enum",
                "allowed": ("PASS", "FAIL"),
            },
            "shared_fields": (),
            "variants": {
                "PASS": {
                    "fields": (
                        {
                            "name": "score",
                            "json_pointer": "/score",
                            "type": "float",
                        },
                    )
                },
                "FAIL": {"fields": ()},
            },
        },
        contract_sha256="sha256:" + "2" * 64,
    )
    union_value = _rehydrate_result_value(
        result={"artifacts": {"variant": "PASS", "score": 0.75}},
        resolved=union,
        workspace=tmp_path,
    )
    assert union_value == {
        "variant": "PASS",
        "value": {"score": 0.75},
    }
    assert _result_comparison(union, union_value) == {
        "kind": "union_variant",
        "value": "PASS",
    }

    list_root = ResolvedPersistedResultContract(
        workflow_name="generic",
        persisted_step_id="root.list",
        contract_kind="output_bundle",
        declared_shape="root_value",
        contract={
            "path": "result.json",
            "fields": (
                {
                    "name": "__result__",
                    "json_pointer": "",
                    "type": "list",
                    "items": {"type": "integer"},
                },
            ),
        },
        contract_sha256="sha256:" + "3" * 64,
    )
    list_value = _rehydrate_result_value(
        result={"artifacts": {"__result__": [1, 2]}},
        resolved=list_root,
        workspace=tmp_path,
    )
    assert list_value == [1, 2]
    assert _result_comparison(list_root, list_value) is None
