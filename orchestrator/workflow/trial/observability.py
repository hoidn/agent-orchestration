"""Read-only status projection for one validated target-2.25 trial visit."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any, cast

from orchestrator.workflow.executable_ir import TrialStepConfig
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.run_ref.runtime import (
    resolve_run_ref_parent_input_values_for_config,
)

from .config import build_trial_runtime_request
from .contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
    derive_trial_cell_effect_scopes,
)
from .ledger import (
    TrialEventLedger,
    load_trial_event_ledger,
    replay_trial_evaluator_attempts,
    validate_trial_event_ledger_authority,
)
from .settlement import (
    PreparedTrialParentSettlement,
    _expected_prepared_payload,
    _normalized_terminal_envelope,
    _validate_verdict_artifact,
    validate_trial_parent_state_settlement,
)


TRIAL_OBSERVABILITY_SCHEMA_VERSION = "workflow_trial_observability.v1"
_FAILURE_LIMIT = 16
_FAILURE_CODE_LIMIT = 128
_FAILURE_PHASE_LIMIT = 64
_CELL_INACTIVE_KINDS = frozenset(
    {
        "cell_prepared",
        "cell_settled",
        "cell_e1_committed",
        "cell_failed",
        "cell_discarded",
    }
)


def _canonical_absolute_path(value: object, *, field: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{field} must be a path")
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=False) != path:
        raise ValueError(f"{field} must be canonical and absolute")
    return path


def _json_copy(value: object) -> Any:
    return json.loads(canonical_json_bytes(value))


def _cell_identity(payload: Mapping[str, Any]) -> tuple[str, int]:
    raw = payload.get("cell")
    if not isinstance(raw, Mapping):
        raise ValueError("trial observability cell authority is missing")
    arm_id = raw.get("arm_id")
    rep = raw.get("rep")
    if not isinstance(arm_id, str) or not arm_id or type(rep) is not int or rep < 1:
        raise ValueError("trial observability cell authority is invalid")
    return arm_id, rep


def _cell_progress(
    ledger: TrialEventLedger,
) -> tuple[int, int, set[tuple[str, int]]]:
    active: set[tuple[str, int]] = set()
    completed: set[tuple[str, int]] = set()
    failed: set[tuple[str, int]] = set()
    for row in ledger.rows[1:]:
        if not row.kind.startswith("cell_"):
            continue
        cell = _cell_identity(row.payload)
        if row.kind == "cell_allocated":
            active.add(cell)
        elif row.kind == "cell_allocation_started":
            active.discard(cell)
        elif row.kind in _CELL_INACTIVE_KINDS:
            active.discard(cell)
        if row.kind == "cell_e1_committed":
            completed.add(cell)
        elif row.kind == "cell_failed":
            failed.add(cell)
    return len(completed), len(failed), active


def _child_attempt_progress(
    ledger: TrialEventLedger,
    *,
    active_cells: set[tuple[str, int]],
) -> tuple[int, int]:
    paths_by_cell: dict[tuple[str, int], Path] = {}
    for row in ledger.rows[1:]:
        if row.kind != "cell_allocated":
            continue
        paths_by_cell[_cell_identity(row.payload)] = Path(
            row.payload["e1_ledger_path"]
        )
    attempts = 0
    active = 0
    for cell, path in paths_by_cell.items():
        child_ledger = load_attempt_ledger(path)
        attempts += sum(row.stage == "launched" for row in child_ledger.rows)
        latest = child_ledger.rows[-1]
        if (
            cell in active_cells
            and latest.stage == "launched"
            and latest.status == "in_progress"
        ):
            active += 1
    return attempts, active


def _current_phase(ledger: TrialEventLedger) -> str:
    kind = ledger.rows[-1].kind
    if kind == "trial_parent_committed":
        return "terminal"
    if kind == "trial_prepared":
        return "parent_commit"
    if kind == "verdict_published":
        return "parent_settlement"
    if kind == "verdict_settled":
        return "publication"
    if kind == "aggregation_frozen":
        return "verdict"
    if kind == "scores_frozen":
        return "aggregation"
    if kind in {
        "packets_frozen",
        "scorer_frozen",
        "evaluator_attempt_allocated",
        "evaluator_attempt_settled",
        "score_settled",
    }:
        return "evaluation"
    if kind == "checks_frozen":
        return "packets"
    if kind in {"evidence_frozen", "check_settled"}:
        return "checks"
    return "cells"


def _phase_digests(
    ledger: TrialEventLedger,
    *,
    request_digest: str,
) -> dict[str, str]:
    header = ledger.rows[0].payload
    projected = {
        "trial_request": request_digest,
        "cell_domain": header["cell_domain_digest"],
        "ledger_head": ledger.rows[-1].row_digest,
    }
    fields = {
        "evidence_frozen": ("evidence_set", "evidence_set_digest"),
        "checks_frozen": ("check_set", "check_set_digest"),
        "packets_frozen": ("packet_set", "packet_set_digest"),
        "scores_frozen": ("score_set", "score_set_digest"),
        "aggregation_frozen": ("aggregation_input", "aggregation_input_digest"),
        "verdict_settled": ("verdict", "verdict_digest"),
    }
    for row in ledger.rows[1:]:
        binding = fields.get(row.kind)
        if binding is not None:
            output_name, payload_name = binding
            value = row.payload.get(payload_name)
            if not isinstance(value, str):
                raise ValueError("trial observability digest authority is invalid")
            projected[output_name] = value
    return projected


def _bounded_failures(ledger: TrialEventLedger) -> list[dict[str, Any]]:
    grouped: Counter[tuple[str, str, bool]] = Counter()
    for row in ledger.rows[1:]:
        if row.kind != "cell_failed":
            continue
        raw = row.payload.get("failure")
        if not isinstance(raw, Mapping):
            raise ValueError("trial failure authority is invalid")
        code = raw.get("code")
        phase = raw.get("phase")
        retryable = raw.get("retryable")
        if (
            not isinstance(code, str)
            or not code
            or not isinstance(phase, str)
            or not phase
            or type(retryable) is not bool
        ):
            raise ValueError("trial failure authority is invalid")
        grouped[
            (
                code[:_FAILURE_CODE_LIMIT],
                phase[:_FAILURE_PHASE_LIMIT],
                retryable,
            )
        ] += 1
    return [
        {
            "code": code,
            "phase": phase,
            "retryable": retryable,
            "count": count,
        }
        for (code, phase, retryable), count in sorted(grouped.items())[
            :_FAILURE_LIMIT
        ]
    ]


def _common_projection(
    *,
    request: Any,
    ledger: TrialEventLedger,
    completed: int,
    failed: int,
    active_children: int,
    child_attempts: int,
    evaluator_attempts: int,
    active_evaluators: int,
) -> dict[str, Any]:
    budget = request.static_config.budget
    return {
        "schema_version": TRIAL_OBSERVABILITY_SCHEMA_VERSION,
        "status": "active",
        "phase": _current_phase(ledger),
        "cell_counts": {
            "frozen": len(request.cell_domain),
            "completed": completed,
            "failed": failed,
        },
        "active_counts": {
            "children": active_children,
            "evaluators": active_evaluators,
        },
        "concurrency": {
            "children": request.static_config.max_concurrency,
            "evaluators": budget["max_evaluator_concurrency"],
        },
        "budget": {
            "child_attempts": child_attempts,
            "evaluator_attempts": evaluator_attempts,
            "max_evaluator_attempts": budget["max_evaluator_attempts"],
        },
        "digests": _phase_digests(ledger, request_digest=request.digest),
        "failures": _bounded_failures(ledger),
    }


def _terminal_outcomes(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TypeError("trial terminal outcomes must be a list")
    projected: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise TypeError("trial terminal outcome must be a mapping")
        variant = raw.get("variant")
        arm_id = raw.get("arm_id")
        rep = raw.get("rep")
        if (
            variant not in {"Completed", "Failed"}
            or not isinstance(arm_id, str)
            or not arm_id
            or type(rep) is not int
            or rep < 1
        ):
            raise ValueError("trial terminal outcome identity is invalid")
        row: dict[str, Any] = {
            "variant": variant,
            "arm_id": arm_id,
            "rep": rep,
        }
        if variant == "Failed":
            failure = raw.get("failure")
            if not isinstance(failure, Mapping):
                raise ValueError("trial terminal failure is invalid")
            code = failure.get("code")
            phase = failure.get("phase")
            retryable = failure.get("retryable")
            if (
                not isinstance(code, str)
                or not code
                or not isinstance(phase, str)
                or not phase
                or type(retryable) is not bool
            ):
                raise ValueError("trial terminal failure is invalid")
            row["failure"] = {
                "code": code[:_FAILURE_CODE_LIMIT],
                "phase": phase[:_FAILURE_PHASE_LIMIT],
                "retryable": retryable,
            }
        projected.append(row)
    return projected


def _terminal_projection(
    *,
    common: dict[str, Any],
    request: Any,
    ledger: TrialEventLedger,
    result: Mapping[str, Any],
    state: Mapping[str, Any],
    parent_workspace: Path,
    step_name: str,
    ledger_path: Path,
) -> dict[str, Any] | None:
    prepared_rows = tuple(row for row in ledger.rows if row.kind == "trial_prepared")
    committed_rows = tuple(
        row for row in ledger.rows if row.kind == "trial_parent_committed"
    )
    if (
        len(prepared_rows) != 1
        or len(committed_rows) != 1
        or ledger.rows[-1].row_digest != committed_rows[0].row_digest
    ):
        return None
    envelope = result.get("trial")
    artifacts = result.get("artifacts")
    if not isinstance(envelope, Mapping) or not isinstance(artifacts, Mapping):
        return None
    publication_rows = tuple(
        row for row in ledger.rows if row.kind == "verdict_published"
    )
    verdict_rows = tuple(row for row in ledger.rows if row.kind == "verdict_settled")
    aggregation_rows = tuple(
        row for row in ledger.rows if row.kind == "aggregation_frozen"
    )
    if not (
        len(publication_rows)
        == len(verdict_rows)
        == len(aggregation_rows)
        == 1
    ):
        return None
    normalized_envelope = _normalized_terminal_envelope(
        request=request,
        parent_workspace=parent_workspace,
        result_envelope=envelope,
    )
    expected_prepared = _expected_prepared_payload(
        request=request,
        publication=publication_rows[0],
        envelope=normalized_envelope,
    )
    if (
        prepared_rows[0].payload != expected_prepared
        or expected_prepared["verdict_digest"]
        != verdict_rows[0].payload["verdict_digest"]
        or expected_prepared["authored_outcomes_digest"]
        != aggregation_rows[0].payload["final_outcomes_digest"]
        or expected_prepared["verdict_artifact_relpath"]
        != normalized_envelope["verdict_artifact"]
    ):
        return None
    _validate_verdict_artifact(
        workspace=parent_workspace,
        request=request,
        envelope=normalized_envelope,
        artifact_digest=expected_prepared["verdict_artifact_digest"],
    )
    prepared = PreparedTrialParentSettlement(ledger_path, prepared_rows[0])
    historical_state = dict(state)
    historical_state["current_step"] = None
    parent_settlement = validate_trial_parent_state_settlement(
        request=request,
        prepared=prepared,
        step_name=step_name,
        expected_artifacts=dict(artifacts),
        persisted_state=historical_state,
    )
    expected_commit = {
        "trial_prepared_row_digest": prepared.row.row_digest,
        "result_envelope_digest": prepared.row.payload["result_envelope_digest"],
        "parent_state_settlement_digest": parent_settlement.digest,
    }
    if committed_rows[0].payload != expected_commit:
        return None
    verdict = normalized_envelope.get("verdict")
    outcomes = normalized_envelope.get("outcomes")
    verdict_artifact = normalized_envelope.get("verdict_artifact")
    if not isinstance(verdict, Mapping) or not isinstance(verdict_artifact, str):
        return None
    evidence_rows = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    if len(evidence_rows) != 1:
        return None
    required_verdict_fields = {
        "aggregate_scores",
        "ranking",
        "selected_arm",
        "success_rule_disposition",
        "budget_accounting",
    }
    if not required_verdict_fields.issubset(verdict):
        return None
    terminal = dict(common)
    terminal.update(
        {
            "status": "completed",
            "phase": "terminal",
            "outcomes": _terminal_outcomes(outcomes),
            "aggregate_scores": _json_copy(verdict["aggregate_scores"]),
            "ranking": _json_copy(verdict["ranking"]),
            "selected_arm": _json_copy(verdict["selected_arm"]),
            "success_rule_disposition": verdict["success_rule_disposition"],
            "verdict": {
                "digest": canonical_sha256(dict(verdict)),
                "relpath": verdict_artifact,
            },
            "evidence_freeze_digest": evidence_rows[0].row_digest,
            "budget_accounting": _json_copy(verdict["budget_accounting"]),
        }
    )
    return terminal


def _ledger_path_for_request(
    *,
    request: Any,
    parent_run_root: Path,
    run_ref_root: Path,
) -> Path:
    scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
    )
    if not scopes:
        raise ValueError("trial observability scope authority is empty")
    return scopes[0].trial_root / "trial-events.jsonl"


def _project_trial_observability(
    *,
    step_config: TrialStepConfig,
    state: Mapping[str, Any],
    run_root: Path,
    parent_workspace: Path,
    step_name: str,
    step_id: str,
    is_current: bool,
    result: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if type(step_config) is not TrialStepConfig:
        raise TypeError("trial observability requires exact TrialStepConfig")
    if not isinstance(state, Mapping):
        raise TypeError("trial observability state must be a mapping")
    if type(is_current) is not bool:
        raise TypeError("trial observability current flag must be boolean")
    parent_run_root = Path(run_root).resolve(strict=False)
    state_run_root = _canonical_absolute_path(
        state.get("run_root"),
        field="trial state run_root",
    )
    if parent_run_root != state_run_root:
        raise ValueError("trial report run root disagrees with state authority")
    run_ref_root = _canonical_absolute_path(
        state.get("run_ref_root"),
        field="trial state run_ref_root",
    )
    workspace = _canonical_absolute_path(
        parent_workspace,
        field="trial parent workspace",
    )
    if not isinstance(step_name, str) or not step_name:
        raise ValueError("trial report step name is invalid")
    if not isinstance(step_id, str) or not step_id:
        raise ValueError("trial report step id is invalid")
    if is_current:
        current = state.get("current_step")
        if (
            not isinstance(current, Mapping)
            or current.get("name") != step_name
            or current.get("step_id") != step_id
            or current.get("type") != "trial"
            or current.get("status") not in {"running", "failed"}
        ):
            raise ValueError("current trial report identity is invalid")
        visit_count = current.get("visit_count")
    else:
        if (
            not isinstance(result, Mapping)
            or result.get("status") != "completed"
            or result.get("step_id") != step_id
            or not isinstance(result.get("trial"), Mapping)
        ):
            return None
        visit_count = result.get("visit_count")
    if type(visit_count) is not int or visit_count < 1:
        raise ValueError("trial report visit authority is invalid")
    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("trial report parent run identity is invalid")
    resolved_inputs = {
        arm.arm_id: resolve_run_ref_parent_input_values_for_config(
            arm.run_ref,
            state,
        )
        for arm in step_config.arms
    }
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=RunRefVisitKey(
            parent_run_id=run_id,
            execution_frame_id="root",
            call_frame_id=None,
            step_id=step_id,
            visit_count=visit_count,
        ),
        resolved_inputs_by_arm=resolved_inputs,
    )
    ledger_path = _ledger_path_for_request(
        request=request,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
    )
    ledger = load_trial_event_ledger(ledger_path)
    header = ledger.rows[0].payload
    bindings = header.get("sealed_opaque_label_map", {}).get("bindings")
    if not isinstance(bindings, list):
        raise ValueError("trial sealed label authority is invalid")
    labels_list: list[str] = []
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise ValueError("trial sealed label authority is invalid")
        label = binding.get("opaque_label")
        if not isinstance(label, str):
            raise ValueError("trial sealed label authority is invalid")
        labels_list.append(label)
    if any(type(cell) is not TrialCellKey for cell in request.cell_domain):
        raise ValueError("trial cell-domain authority is invalid")
    cell_domain = cast(tuple[TrialCellKey, ...], request.cell_domain)
    sealed = build_sealed_opaque_label_map(
        cell_domain,
        labels=tuple(labels_list),
    )
    validate_trial_event_ledger_authority(
        ledger_path,
        request=request,
        sealed_opaque_labels=sealed,
    )
    ledger = load_trial_event_ledger(ledger_path)
    completed, failed, active_cells = _cell_progress(ledger)
    child_attempts, active_children = _child_attempt_progress(
        ledger,
        active_cells=active_cells,
    )
    evaluator = replay_trial_evaluator_attempts(ledger_path)
    common = _common_projection(
        request=request,
        ledger=ledger,
        completed=completed,
        failed=failed,
        active_children=active_children,
        child_attempts=child_attempts,
        evaluator_attempts=evaluator.charged_attempt_count,
        active_evaluators=len(evaluator.active_allocations),
    )
    if is_current:
        return common
    assert result is not None
    return _terminal_projection(
        common=common,
        request=request,
        ledger=ledger,
        result=result,
        state=state,
        parent_workspace=workspace,
        step_name=step_name,
        ledger_path=ledger_path,
    )


def project_trial_observability(
    *,
    step_config: TrialStepConfig,
    state: Mapping[str, Any],
    run_root: Path,
    parent_workspace: Path,
    step_name: str,
    step_id: str,
    is_current: bool,
    result: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Project validated trial authority without writing, routing, or repair."""

    try:
        return _project_trial_observability(
            step_config=step_config,
            state=state,
            run_root=run_root,
            parent_workspace=parent_workspace,
            step_name=step_name,
            step_id=step_id,
            is_current=is_current,
            result=result,
        )
    except (OSError, TypeError, ValueError):
        return None


__all__ = [
    "TRIAL_OBSERVABILITY_SCHEMA_VERSION",
    "project_trial_observability",
]
