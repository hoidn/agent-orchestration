"""Identity-neutral dependency indexing for deterministic pure-result replay."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, NoReturn

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_contract_value,
)

from .executable_ir import (
    ExecutableNodeKind,
    ExecutableWorkflow,
    ForEachNode,
    NodeResultAddress,
    PureProjectionStepConfig,
    RepeatUntilFrameNode,
    WorkflowInputAddress,
)
from .loaded_bundle import (
    LoadedWorkflowBundle,
    workflow_runtime_input_contracts,
)
from .pure_expr import (
    PureExprEvaluationError,
    _coerce_value,
    canonical_json_for_pure_value,
)
from .references import (
    ReferenceResolutionError,
    SelfOutputReference,
    StructuredStepReference,
    SurfaceRefScopeCatalog,
    WorkflowInputReference,
    parse_surface_ref,
)
from .resume_projection_integrity import ResumeScopePath
from .runtime_plan import (
    WorkflowRuntimePlan,
    validate_workflow_runtime_plan,
)


PURE_RESULT_REPLAY_DIAGNOSTIC = "pure_result_replay_unavailable"
DEPENDENCY_INDEX_INVALID = "dependency_index_invalid"
REACHABILITY_AMBIGUOUS = "reachability_ambiguous"
MULTIPLE_VISIT_REGION = "multiple_visit_region"
DERIVED_PURE_REPLAY_PROFILE = "derived_pure_replay.v1"
PROGRESS_WITNESS_INVALID = "progress_witness_invalid"
PROFILE_CONFLICT = "profile_conflict"
DURABLE_INPUT_MISSING = "durable_input_missing"
DURABLE_INPUT_INVALID = "durable_input_invalid"
BINDING_UNRESOLVED = "binding_unresolved"
EVALUATION_FAILED = "evaluation_failed"
OUTPUT_CONTRACT_INVALID = "output_contract_invalid"
DURABLE_ROUTED_SKIP = "durable_routed_skip"
_OVERLAY_VALUE_MISSING = object()
_DURABLE_VALUE_MISSING = object()

_INTRINSIC_DURABLE_RESULT_CONTRACTS = MappingProxyType(
    {
        ("exit_code", None): MappingProxyType(
            {"type": "integer"}
        ),
        ("outcome", "status"): MappingProxyType(
            {"type": "string"}
        ),
        ("outcome", "phase"): MappingProxyType(
            {"type": "string"}
        ),
        ("outcome", "class"): MappingProxyType(
            {"type": "string"}
        ),
        ("outcome", "retryable"): MappingProxyType(
            {"type": "bool"}
        ),
    }
)
_INTRINSIC_DURABLE_RESULT_TYPES = MappingProxyType(
    {
        ("exit_code", None): int,
        ("outcome", "status"): str,
        ("outcome", "phase"): str,
        ("outcome", "class"): str,
        ("outcome", "retryable"): bool,
    }
)

_PURE_COMPLETION_SHELL_KEYS = frozenset(
    {
        "name",
        "step_id",
        "visit_count",
        "status",
        "exit_code",
        "outcome",
        "result_storage",
    }
)
_PURE_RUNNING_CURSOR_KEYS = frozenset(
    {
        "name",
        "index",
        "type",
        "status",
        "started_at",
        "last_heartbeat_at",
        "step_id",
        "visit_count",
    }
)

BindingPathPart = str | int
ReplayAddress = WorkflowInputAddress | NodeResultAddress


def _typed_node_result_addresses(value: Any) -> tuple[NodeResultAddress, ...]:
    """Collect exact typed result addresses from one validated IR consumer."""

    addresses: list[NodeResultAddress] = []
    seen_addresses: set[NodeResultAddress] = set()
    seen_containers: set[int] = set()

    def visit(candidate: Any) -> None:
        if isinstance(candidate, NodeResultAddress):
            if candidate not in seen_addresses:
                seen_addresses.add(candidate)
                addresses.append(candidate)
            return
        if candidate is None or isinstance(
            candidate,
            (str, bytes, int, float, bool, Path),
        ):
            return
        if isinstance(candidate, Mapping):
            identity = id(candidate)
            if identity in seen_containers:
                return
            seen_containers.add(identity)
            for item in candidate.values():
                visit(item)
            return
        if isinstance(candidate, Sequence):
            identity = id(candidate)
            if identity in seen_containers:
                return
            seen_containers.add(identity)
            for item in candidate:
                visit(item)
            return
        if is_dataclass(candidate) and not isinstance(candidate, type):
            identity = id(candidate)
            if identity in seen_containers:
                return
            seen_containers.add(identity)
            for field_definition in fields(candidate):
                visit(getattr(candidate, field_definition.name))

    visit(value)
    return tuple(addresses)


class PureResultReplayIndexError(ValueError):
    """A replay dependency index could not be derived without guessing."""

    code = PURE_RESULT_REPLAY_DIAGNOSTIC

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.context = MappingProxyType(dict(context or {}))


@dataclass(frozen=True)
class PureReplayVisitWitness:
    """Exact identity of one single-visit pure projection execution."""

    presentation_key: str
    step_index: int
    step_id: str
    visit_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.presentation_key, str) or not self.presentation_key:
            raise ValueError("pure replay presentation key must be non-empty")
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise ValueError("pure replay step index must be a non-negative integer")
        if not isinstance(self.step_id, str) or not self.step_id:
            raise ValueError("pure replay step identity must be non-empty")
        if type(self.visit_count) is not int or self.visit_count != 1:
            raise ValueError("pure replay visit count must be exactly one")


def build_pure_completion_shell(
    witness: PureReplayVisitWitness,
) -> dict[str, Any]:
    """Build the only successful durable row admitted by the replay profile."""

    if not isinstance(witness, PureReplayVisitWitness):
        raise TypeError("PureReplayVisitWitness required")
    return {
        "name": witness.presentation_key,
        "step_id": witness.step_id,
        "visit_count": witness.visit_count,
        "status": "completed",
        "exit_code": 0,
        "outcome": {
            "status": "completed",
            "phase": "execution",
            "class": "completed",
            "retryable": False,
        },
        "result_storage": DERIVED_PURE_REPLAY_PROFILE,
    }


def validate_pure_completion_shell(
    row: Mapping[str, Any],
    *,
    witness: PureReplayVisitWitness,
) -> None:
    """Reject any successful replay row that is not the exact value-free shell."""

    if not isinstance(row, Mapping):
        raise ValueError("pure replay completion shell must be an object")
    if set(row) != _PURE_COMPLETION_SHELL_KEYS:
        raise ValueError("pure replay completion shell fields are invalid")
    if not _same_json_shape_and_value(
        row,
        build_pure_completion_shell(witness),
    ):
        raise ValueError("pure replay completion shell does not match its visit")


def _same_json_shape_and_value(left: Any, right: Any) -> bool:
    """Compare JSON-like values without Python's bool/int equivalence."""

    if type(left) is not type(right):
        return False
    if isinstance(left, Mapping):
        return (
            set(left) == set(right)
            and all(
                _same_json_shape_and_value(left[key], right[key])
                for key in left
            )
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_json_shape_and_value(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return bool(left == right)


def _progress_state_mapping(state: Any) -> Mapping[str, Any]:
    if isinstance(state, Mapping):
        return state
    to_dict = getattr(state, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise TypeError("pure replay progress state must be an object")


def _is_matching_running_cursor(
    cursor: Any,
    witness: PureReplayVisitWitness,
) -> bool:
    if not isinstance(cursor, Mapping) or set(cursor) != _PURE_RUNNING_CURSOR_KEYS:
        return False
    expected = {
        "name": witness.presentation_key,
        "index": witness.step_index,
        "type": "pure_projection",
        "status": "running",
        "step_id": witness.step_id,
        "visit_count": witness.visit_count,
    }
    if any(
        not _same_json_shape_and_value(cursor.get(field), value)
        for field, value in expected.items()
    ):
        return False
    return all(
        isinstance(cursor.get(field), str) and bool(cursor.get(field))
        for field in ("started_at", "last_heartbeat_at")
    )


def _cursor_targets_witness(
    cursor: Any,
    witness: PureReplayVisitWitness,
) -> bool:
    return isinstance(cursor, Mapping) and (
        cursor.get("name") == witness.presentation_key
        or cursor.get("step_id") == witness.step_id
    )


def _is_matching_failure_or_skip(
    row: Any,
    witness: PureReplayVisitWitness,
) -> bool:
    if not isinstance(row, Mapping) or row.get("status") not in {"failed", "skipped"}:
        return False
    return (
        row.get("name") == witness.presentation_key
        and row.get("step_id") == witness.step_id
        and type(row.get("visit_count")) is int
        and row.get("visit_count") == witness.visit_count
    )


def _is_matching_unvisited_routed_skip(
    row: Any,
    witness: PureReplayVisitWitness,
) -> bool:
    """Recognize the ordinary route-skip row written before visit start."""

    return (
        isinstance(row, Mapping)
        and row.get("status") == "skipped"
        and row.get("name") == witness.presentation_key
        and row.get("step_id") == witness.step_id
        and "visit_count" not in row
        and row.get("skipped") is True
        and type(row.get("exit_code")) is int
        and row.get("exit_code") == 0
        and _same_json_shape_and_value(
            row.get("outcome"),
            {
                "status": "skipped",
                "phase": "pre_execution",
                "class": "skipped",
                "retryable": False,
            },
        )
    )


def classify_pure_replay_progress(
    state: Any,
    *,
    witness: PureReplayVisitWitness,
) -> str:
    """Classify the closed visit/cursor/result witness state."""

    if not isinstance(witness, PureReplayVisitWitness):
        raise TypeError("PureReplayVisitWitness required")
    payload = _progress_state_mapping(state)
    visits = payload.get("step_visits", {})
    steps = payload.get("steps", {})
    cursor = payload.get("current_step")
    if not isinstance(visits, Mapping) or not isinstance(steps, Mapping):
        return PROGRESS_WITNESS_INVALID

    recorded_visit = visits.get(witness.presentation_key)
    row = steps.get(witness.presentation_key)
    cursor_is_relevant = _cursor_targets_witness(cursor, witness)
    if cursor is not None and not cursor_is_relevant:
        cursor = None
    if (
        recorded_visit is None
        and cursor is None
        and _is_matching_unvisited_routed_skip(row, witness)
    ):
        return DURABLE_ROUTED_SKIP
    if recorded_visit is None and cursor is None and row is None:
        return "unstarted"
    if (
        isinstance(recorded_visit, bool)
        or not isinstance(recorded_visit, int)
        or recorded_visit != witness.visit_count
    ):
        return PROGRESS_WITNESS_INVALID
    if cursor is not None and row is not None:
        return PROGRESS_WITNESS_INVALID
    if cursor is not None:
        return (
            "interrupted"
            if _is_matching_running_cursor(cursor, witness)
            else PROGRESS_WITNESS_INVALID
        )
    if row is None:
        return PROGRESS_WITNESS_INVALID
    try:
        validate_pure_completion_shell(row, witness=witness)
    except ValueError:
        if _is_matching_failure_or_skip(row, witness):
            return "durable_failure_skip"
        return PROGRESS_WITNESS_INVALID
    return "derived_complete"


@dataclass(frozen=True)
class PureReplayOverlayKey:
    """Exact process-local authority key for one reconstructed result."""

    scope_path: ResumeScopePath
    node_id: str
    visit_count: int
    output_addresses: tuple[NodeResultAddress, ...]


class PureReplayRuntime:
    """Audited replay-profile classification and transient result authority."""

    def __init__(
        self,
        *,
        bundle: LoadedWorkflowBundle,
        scope_path: ResumeScopePath,
    ) -> None:
        if not isinstance(scope_path, ResumeScopePath):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay requires a validated resume scope path",
            )
        self.bundle = bundle
        # Compiled ``root.steps`` refs are local to this loaded workflow.
        # ResumeScopePath carries any enclosing call-frame identity separately.
        self.index = derive_pure_result_replay_index(
            bundle,
            scope_kind="root",
        )
        self.scope_path = scope_path
        self._overlay: dict[
            PureReplayOverlayKey,
            dict[str, Any],
        ] = {}
        self._execution_index_by_node_id = {
            node_id: index
            for index, node_id in enumerate(
                tuple(bundle.ir.body_region)
                + tuple(bundle.ir.finalization_region)
            )
        }
        self._eligible_step_ids = frozenset(
            replay_node.step_id
            for replay_node in self.index.nodes.values()
        )
        self._node_id_by_step_id = {
            replay_node.step_id: node_id
            for node_id, replay_node in self.index.nodes.items()
        }
        if len(self._node_id_by_step_id) != len(self.index.nodes):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay step identities are not unique",
            )
        self._selector_to_node_id = _validated_projection_catalog(bundle)
        self._reference_catalog = SurfaceRefScopeCatalog(
            root_step_names=(
                tuple(self._selector_to_node_id)
                if self.index.scope_kind == "root"
                else ()
            ),
            self_step_names=(
                tuple(self._selector_to_node_id)
                if self.index.scope_kind == "self"
                else ()
            ),
        )
        self._eligible_restore_source_step_ids = (
            self._derive_restore_source_step_ids()
        )
        self._replay_in_progress: set[str] = set()

    def is_eligible(self, node_id: str) -> bool:
        return node_id in self.index.nodes

    def successful_checkpoint_is_suppressed(
        self,
        node_id: str,
        *,
        state: Mapping[str, Any],
    ) -> bool:
        """Suppress only the exact checkpoint of a derived-complete shell."""

        if node_id not in self.index.nodes:
            return False
        classification = classify_pure_replay_progress(
            state,
            witness=self.witness_from_state(node_id, state),
        )
        if classification == PROGRESS_WITNESS_INVALID:
            raise PureResultReplayIndexError(
                PROGRESS_WITNESS_INVALID,
                "pure replay checkpoint suppression requires valid progress",
                context={"node_id": node_id},
            )
        return classification == "derived_complete"

    def default_resume_checkpoint_excluded_node_ids(
        self,
        *,
        state: Mapping[str, Any],
        restart_node_id: str,
    ) -> frozenset[str]:
        """Exclude derived shells plus the exact interrupted restart point."""

        excluded: set[str] = set()
        for node_id in self.index.topological_node_ids:
            classification = classify_pure_replay_progress(
                state,
                witness=self.witness_from_state(node_id, state),
            )
            if classification == PROGRESS_WITNESS_INVALID:
                raise PureResultReplayIndexError(
                    PROGRESS_WITNESS_INVALID,
                    "pure replay default checkpoint filtering requires valid progress",
                    context={"node_id": node_id},
                )
            if classification == "derived_complete":
                excluded.add(node_id)
            elif classification == "interrupted":
                if node_id != restart_node_id:
                    raise PureResultReplayIndexError(
                        PROGRESS_WITNESS_INVALID,
                        "interrupted pure replay point is not the selected restart",
                        context={
                            "node_id": node_id,
                            "restart_node_id": restart_node_id,
                        },
                    )
                excluded.add(node_id)
        return frozenset(excluded)

    def node_id_for_step_id(self, step_id: Any) -> str | None:
        return (
            self._node_id_by_step_id.get(step_id)
            if isinstance(step_id, str)
            else None
        )

    def witness(
        self,
        node_id: str,
        *,
        visit_count: int = 1,
    ) -> PureReplayVisitWitness:
        replay_node = self.index.nodes.get(node_id)
        step_index = self._execution_index_by_node_id.get(node_id)
        if replay_node is None or not isinstance(step_index, int):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay witness requires an eligible executable node",
                context={"node_id": node_id},
            )
        return PureReplayVisitWitness(
            presentation_key=replay_node.presentation_key,
            step_index=step_index,
            step_id=replay_node.step_id,
            visit_count=visit_count,
        )

    def witness_from_state(
        self,
        node_id: str,
        state: Mapping[str, Any],
    ) -> PureReplayVisitWitness:
        replay_node = self.index.nodes.get(node_id)
        visits = state.get("step_visits")
        recorded_visit = (
            visits.get(replay_node.presentation_key)
            if replay_node is not None and isinstance(visits, Mapping)
            else None
        )
        if recorded_visit is not None and (
            type(recorded_visit) is not int
            or recorded_visit != 1
        ):
            raise PureResultReplayIndexError(
                PROGRESS_WITNESS_INVALID,
                "pure replay persisted visit must be exactly one",
                context={"node_id": node_id},
            )
        return self.witness(node_id, visit_count=1)

    def record_full_result(
        self,
        node_id: str,
        *,
        witness: PureReplayVisitWitness,
        result: Mapping[str, Any],
    ) -> None:
        replay_node = self.index.nodes.get(node_id)
        if replay_node is None or witness != self.witness(
            node_id,
            visit_count=witness.visit_count,
        ):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay result identity does not match its executable node",
                context={"node_id": node_id},
            )
        _validate_replay_result_output_members(
            replay_node,
            result=result,
        )
        if (
            result.get("status") != "completed"
            or type(result.get("exit_code")) is not int
            or result.get("exit_code") != 0
            or result.get("step_id") != witness.step_id
            or result.get("name") != witness.presentation_key
            or type(result.get("visit_count")) is not int
            or result.get("visit_count") != 1
        ):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay result is not the normalized completed visit",
                context={"node_id": node_id},
            )
        key = PureReplayOverlayKey(
            scope_path=self.scope_path,
            node_id=node_id,
            visit_count=witness.visit_count,
            output_addresses=replay_node.output_addresses,
        )
        self._overlay[key] = deepcopy(dict(result))

    def _result_row(
        self,
        node_id: str,
        *,
        visit_count: int,
    ) -> dict[str, Any] | None:
        replay_node = self.index.nodes.get(node_id)
        if replay_node is None:
            return None
        key = PureReplayOverlayKey(
            scope_path=self.scope_path,
            node_id=node_id,
            visit_count=visit_count,
            output_addresses=replay_node.output_addresses,
        )
        result = self._overlay.get(key)
        return deepcopy(result) if result is not None else None

    def value_for_state_address(
        self,
        address: NodeResultAddress,
        state: Mapping[str, Any],
    ) -> Any:
        """Resolve only one exact typed address from the scoped overlay."""

        if not isinstance(address, NodeResultAddress):
            raise TypeError("NodeResultAddress required")
        replay_node = self.index.nodes.get(address.node_id)
        if (
            replay_node is None
            or address not in replay_node.output_addresses
        ):
            return _OVERLAY_VALUE_MISSING
        visits = state.get("step_visits")
        visit_count = (
            visits.get(replay_node.presentation_key)
            if isinstance(visits, Mapping)
            else None
        )
        if type(visit_count) is not int or visit_count != 1:
            return _OVERLAY_VALUE_MISSING
        row = self._result_row(
            address.node_id,
            visit_count=visit_count,
        )
        if row is None:
            return _OVERLAY_VALUE_MISSING
        container = row.get(address.field)
        if not isinstance(container, Mapping) or address.member not in container:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay overlay does not contain its exact result address",
                context={
                    "node_id": address.node_id,
                    "field": address.field,
                    "member": address.member,
                },
            )
        return deepcopy(container[address.member])

    def resolve_state_address(
        self,
        address: NodeResultAddress,
        state: Mapping[str, Any],
    ) -> tuple[bool, Any]:
        value = self.value_for_state_address(address, state)
        return (
            (False, None)
            if value is _OVERLAY_VALUE_MISSING
            else (True, value)
        )

    def replay_address_for_ref(
        self,
        ref: Any,
    ) -> NodeResultAddress | None:
        """Resolve one closed surface ref to an eligible exact address."""

        if not isinstance(ref, str) or not ref:
            return None
        try:
            parsed = parse_surface_ref(ref, self._reference_catalog)
        except ReferenceResolutionError:
            return None
        if (
            not isinstance(parsed, StructuredStepReference)
            or parsed.scope != self.index.scope_kind
        ):
            return None
        node_id = self._selector_to_node_id.get(parsed.step_name)
        if node_id not in self.index.nodes:
            return None
        address = NodeResultAddress(
            node_id=node_id,
            field=parsed.field,
            member=parsed.member,
        )
        return (
            address
            if address in self.index.nodes[node_id].output_addresses
            else None
        )

    def required_node_ids_for_boundary(
        self,
        restart_node_id: str | None,
        *,
        state: Mapping[str, Any],
    ) -> tuple[str, ...]:
        """Derive the exact pure closure named by one selected boundary."""

        seed_addresses: list[NodeResultAddress] = []
        if restart_node_id is None:
            for contract in self.bundle.ir.outputs.values():
                source_address = getattr(contract, "source_address", None)
                if isinstance(source_address, NodeResultAddress):
                    seed_addresses.append(source_address)
            points: tuple[Any, ...] = ()
        else:
            restart_node = self.bundle.ir.nodes.get(restart_node_id)
            if restart_node is None:
                raise PureResultReplayIndexError(
                    DEPENDENCY_INDEX_INVALID,
                    "resume boundary names an unknown executable node",
                    context={"node_id": restart_node_id},
                )
            seed_addresses.extend(
                _typed_node_result_addresses(restart_node)
            )
            points = tuple(
                point
                for point in (
                    getattr(
                        self.bundle.runtime_plan,
                        "lexical_checkpoint_points",
                        (),
                    )
                    or ()
                )
                if getattr(point, "node_id", None) == restart_node_id
            )
        if len(points) > 1:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "resume boundary has ambiguous checkpoint metadata",
                context={"node_id": restart_node_id},
            )
        if points:
            details = getattr(points[0], "details", None)
            restore = (
                details.get("restore")
                if isinstance(details, Mapping)
                else None
            )
            descriptors = (
                restore.get("binding_descriptors")
                if isinstance(restore, Mapping)
                else ()
            )
            if not isinstance(descriptors, Sequence) or isinstance(
                descriptors,
                (str, bytes),
            ):
                raise PureResultReplayIndexError(
                    DEPENDENCY_INDEX_INVALID,
                    "resume boundary binding metadata is invalid",
                    context={"node_id": restart_node_id},
                )
            for descriptor in descriptors:
                if not isinstance(descriptor, Mapping):
                    raise PureResultReplayIndexError(
                        DEPENDENCY_INDEX_INVALID,
                        "resume boundary binding descriptor is invalid",
                        context={"node_id": restart_node_id},
                    )
                value_document = descriptor.get("value_document")
                if "value_document" not in descriptor:
                    continue
                for _, ref in _walk_value_document_refs(
                    {"boundary": value_document}
                ):
                    address = _resolve_replay_ref(
                        ref,
                        executable=self.bundle.ir,
                        selector_to_node_id=self._selector_to_node_id,
                        catalog=self._reference_catalog,
                        scope_kind=self.index.scope_kind,
                    )
                    if isinstance(address, NodeResultAddress):
                        seed_addresses.append(address)

        reached_node_ids = []
        for node_id in self.index.topological_node_ids:
            witness = self.witness_from_state(node_id, state)
            if (
                classify_pure_replay_progress(
                    state,
                    witness=witness,
                )
                == "derived_complete"
            ):
                reached_node_ids.append(node_id)
        return self.index.required_pure_node_ids(
            tuple(seed_addresses),
            reached_node_ids=tuple(reached_node_ids),
        )

    def replay_node(
        self,
        node_id: str,
        *,
        state: Mapping[str, Any],
        evaluate_node: Callable[
            [str, Mapping[str, Any]],
            Mapping[str, Any],
        ],
    ) -> None:
        """Reconstruct one exact completed shell and its pure closure."""

        replay_node = self.index.nodes.get(node_id)
        if replay_node is None:
            return

        witness = self.witness_from_state(node_id, state)
        classification = classify_pure_replay_progress(
            state,
            witness=witness,
        )
        cached_result = self._result_row(
            node_id,
            visit_count=witness.visit_count,
        )
        if cached_result is not None:
            visits = state.get("step_visits")
            steps = state.get("steps")
            # The active executor keeps its validated full result while the
            # state manager persists the value-free shell. Only that exact
            # process-local row may accompany a non-shell state view.
            active_result_matches_cache = (
                isinstance(visits, Mapping)
                and type(visits.get(witness.presentation_key)) is int
                and visits.get(witness.presentation_key)
                == witness.visit_count
                and isinstance(steps, Mapping)
                and _same_json_shape_and_value(
                    steps.get(witness.presentation_key),
                    cached_result,
                )
                and not _cursor_targets_witness(
                    state.get("current_step"),
                    witness,
                )
            )
            if (
                classification == "derived_complete"
                or active_result_matches_cache
            ):
                return
            raise PureResultReplayIndexError(
                PROGRESS_WITNESS_INVALID,
                "pure replay requires an exact completed persistence shell",
                context={"node_id": node_id},
            )
        if classification != "derived_complete":
            raise PureResultReplayIndexError(
                PROGRESS_WITNESS_INVALID,
                "pure replay requires an exact completed persistence shell",
                context={"node_id": node_id},
            )
        if node_id in self._replay_in_progress:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay evaluation re-entered its dependency closure",
                context={"node_id": node_id},
            )

        self._replay_in_progress.add(node_id)
        try:
            for dependency_node_id in replay_node.pure_dependency_node_ids:
                self.replay_node(
                    dependency_node_id,
                    state=state,
                    evaluate_node=evaluate_node,
                )
            self._validate_replay_leaves(
                replay_node,
                state=state,
            )
            result = evaluate_node(
                node_id,
                self.overlay_active_state(state),
            )
            if not isinstance(result, Mapping):
                self._raise_replay_result_failure(
                    node_id,
                    reason=EVALUATION_FAILED,
                    message="pure replay evaluator returned a non-object result",
                )
            if result.get("status") != "completed":
                error = result.get("error")
                error_type = (
                    error.get("type")
                    if isinstance(error, Mapping)
                    else None
                )
                reason = (
                    BINDING_UNRESOLVED
                    if error_type == "materialize_ref_unresolved"
                    else OUTPUT_CONTRACT_INVALID
                    if error_type
                    in {
                        "pure_projection_contract_invalid",
                        "invalid_reused_pure_projection_result",
                    }
                    else EVALUATION_FAILED
                )
                self._raise_replay_result_failure(
                    node_id,
                    reason=reason,
                    message="pure replay evaluation did not complete",
                    cause_type=error_type,
                )
            self.record_full_result(
                node_id,
                witness=witness,
                result=result,
            )
            if self._result_row(
                node_id,
                visit_count=witness.visit_count,
            ) is None:
                self._raise_replay_result_failure(
                    node_id,
                    reason=EVALUATION_FAILED,
                    message="pure replay result was not retained in the overlay",
                )
        finally:
            self._replay_in_progress.discard(node_id)

    def audit_boundary_leaves(
        self,
        restart_node_id: str | None,
        *,
        state: Mapping[str, Any],
    ) -> None:
        """Validate one boundary's durable replay leaves without evaluation."""

        for node_id in self.required_node_ids_for_boundary(
            restart_node_id,
            state=state,
        ):
            replay_node = self.index.nodes.get(node_id)
            if replay_node is None:
                raise PureResultReplayIndexError(
                    DEPENDENCY_INDEX_INVALID,
                    "pure replay boundary names an unknown eligible node",
                    context={"node_id": node_id},
                )
            witness = self.witness_from_state(node_id, state)
            if (
                classify_pure_replay_progress(
                    state,
                    witness=witness,
                )
                != "derived_complete"
            ):
                raise PureResultReplayIndexError(
                    PROGRESS_WITNESS_INVALID,
                    "pure replay requires an exact completed persistence shell",
                    context={"node_id": node_id},
                )
            self._validate_replay_leaves(
                replay_node,
                state=state,
            )

    def _validate_replay_leaves(
        self,
        replay_node: "PureReplayNode",
        *,
        state: Mapping[str, Any],
    ) -> None:
        bound_inputs = state.get("bound_inputs")
        steps = state.get("steps")
        if not isinstance(bound_inputs, Mapping):
            bound_inputs = {}
        if not isinstance(steps, Mapping):
            steps = {}
        input_contracts = workflow_runtime_input_contracts(self.bundle)
        for binding in replay_node.bindings:
            address = binding.address
            if isinstance(address, WorkflowInputAddress):
                if address.input_name not in bound_inputs:
                    self._raise_replay_result_failure(
                        replay_node.node_id,
                        reason=DURABLE_INPUT_MISSING,
                        message="pure replay workflow input is missing",
                    )
                input_contract = input_contracts.get(address.input_name)
                if not isinstance(input_contract, Mapping):
                    self._raise_replay_result_failure(
                        replay_node.node_id,
                        reason=DURABLE_INPUT_INVALID,
                        message=(
                            "pure replay workflow input contract is invalid"
                        ),
                    )
                try:
                    validate_contract_value(
                        bound_inputs[address.input_name],
                        dict(input_contract),
                        workspace=self.bundle.provenance.source_root,
                    )
                except OutputContractError:
                    self._raise_replay_result_failure(
                        replay_node.node_id,
                        reason=DURABLE_INPUT_INVALID,
                        message="pure replay workflow input is invalid",
                    )
                continue
            if (
                not isinstance(address, NodeResultAddress)
                or address.node_id
                not in replay_node.durable_dependency_node_ids
            ):
                continue
            presentation_key = (
                self.bundle.projection.presentation_key_by_node_id.get(
                    address.node_id
                )
            )
            row = (
                steps.get(presentation_key)
                if isinstance(presentation_key, str)
                else None
            )
            if row is None:
                self._raise_replay_result_failure(
                    replay_node.node_id,
                    reason=DURABLE_INPUT_MISSING,
                    message="pure replay durable dependency is missing",
                )
            if not isinstance(row, Mapping) or row.get("status") != "completed":
                self._raise_replay_result_failure(
                    replay_node.node_id,
                    reason=DURABLE_INPUT_INVALID,
                    message="pure replay durable dependency is invalid",
                )
            durable_value, contract = _durable_node_result_value(
                self.bundle,
                address,
                row,
            )
            if (
                durable_value is _DURABLE_VALUE_MISSING
                or contract is None
            ):
                self._raise_replay_result_failure(
                    replay_node.node_id,
                    reason=DURABLE_INPUT_INVALID,
                    message="pure replay durable result address is invalid",
                )
            intrinsic_type = _INTRINSIC_DURABLE_RESULT_TYPES.get(
                (address.field, address.member)
            )
            if (
                intrinsic_type is not None
                and type(durable_value) is not intrinsic_type
            ):
                self._raise_replay_result_failure(
                    replay_node.node_id,
                    reason=DURABLE_INPUT_INVALID,
                    message="pure replay durable result value is invalid",
                )
            try:
                validate_contract_value(
                    durable_value,
                    dict(contract),
                    workspace=self.bundle.provenance.source_root,
                )
            except OutputContractError:
                self._raise_replay_result_failure(
                    replay_node.node_id,
                    reason=DURABLE_INPUT_INVALID,
                    message="pure replay durable result value is invalid",
                )

    @staticmethod
    def _raise_replay_result_failure(
        node_id: str,
        *,
        reason: str,
        message: str,
        cause_type: str | None = None,
    ) -> None:
        context: dict[str, Any] = {"node_id": node_id}
        if isinstance(cause_type, str) and cause_type:
            context["cause"] = {"type": cause_type}
        raise PureResultReplayIndexError(
            reason,
            message,
            context=context,
        )

    def overlay_active_state(
        self,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        active = deepcopy(dict(state))
        steps = active.get("steps")
        visits = active.get("step_visits")
        if not isinstance(steps, dict) or not isinstance(visits, Mapping):
            return active
        for node_id, replay_node in self.index.nodes.items():
            visit_count = visits.get(replay_node.presentation_key)
            if isinstance(visit_count, bool) or not isinstance(
                visit_count,
                int,
            ):
                continue
            result = self._result_row(
                node_id,
                visit_count=visit_count,
            )
            if result is not None:
                steps[replay_node.presentation_key] = result
        return active

    def _derive_restore_source_step_ids(self) -> frozenset[str]:
        """Bind restore source spellings through validated point metadata."""

        presentation_to_node_id = {
            replay_node.presentation_key: node_id
            for node_id, replay_node in self.index.nodes.items()
        }
        source_step_ids: set[str] = set()
        for point in tuple(
            getattr(
                self.bundle.runtime_plan,
                "lexical_checkpoint_points",
                (),
            )
            or ()
        ):
            details = getattr(point, "details", None)
            restore = (
                details.get("restore")
                if isinstance(details, Mapping)
                else None
            )
            descriptors = (
                restore.get("binding_descriptors")
                if isinstance(restore, Mapping)
                else ()
            )
            if not isinstance(descriptors, Sequence) or isinstance(
                descriptors,
                (str, bytes),
            ):
                continue
            for descriptor in descriptors:
                if not isinstance(descriptor, Mapping):
                    continue
                source_step_name = descriptor.get("source_step_name")
                node_id = (
                    presentation_to_node_id.get(source_step_name)
                    if isinstance(source_step_name, str)
                    else None
                )
                if node_id is None:
                    continue
                source_step_id = descriptor.get("source_step_id")
                value_document = descriptor.get("value_document")
                if (
                    not isinstance(source_step_id, str)
                    or not source_step_id
                    or "value_document" not in descriptor
                ):
                    raise PureResultReplayIndexError(
                        DEPENDENCY_INDEX_INVALID,
                        "pure replay restore source metadata is incomplete",
                        context={"node_id": node_id},
                    )
                addresses = tuple(
                    _resolve_replay_ref(
                        ref,
                        executable=self.bundle.ir,
                        selector_to_node_id=self._selector_to_node_id,
                        catalog=self._reference_catalog,
                        scope_kind=self.index.scope_kind,
                    )
                    for _, ref in _walk_value_document_refs(
                        {"source": value_document}
                    )
                )
                if not addresses or any(
                    not isinstance(address, NodeResultAddress)
                    or address.node_id != node_id
                    for address in addresses
                ):
                    raise PureResultReplayIndexError(
                        DEPENDENCY_INDEX_INVALID,
                        "pure replay restore source identity is inconsistent",
                        context={"node_id": node_id},
                    )
                source_step_ids.add(source_step_id)
        return frozenset(source_step_ids)

    def source_step_is_derived(self, source_step_id: Any) -> bool:
        return (
            isinstance(source_step_id, str)
            and source_step_id
            in (
                self._eligible_step_ids
                | self._eligible_restore_source_step_ids
            )
        )

    def audit_persisted_surfaces(
        self,
        *,
        state: Mapping[str, Any],
        state_manager: Any,
        resolve_bundle_path: Callable[[str], Path | None],
    ) -> None:
        forbidden_checkpoint_node_ids: set[str] = set()
        for node_id, replay_node in self.index.nodes.items():
            witness = self.witness_from_state(node_id, state)
            classification = classify_pure_replay_progress(
                state,
                witness=witness,
            )
            if classification == PROGRESS_WITNESS_INVALID:
                self._raise_profile_conflict(
                    node_id,
                    "steps",
                )
            if classification not in {
                "durable_failure_skip",
                DURABLE_ROUTED_SKIP,
            }:
                forbidden_checkpoint_node_ids.add(node_id)
            self._audit_bundle_surface(
                node_id=node_id,
                resolve_bundle_path=resolve_bundle_path,
            )

        self._audit_private_lineage(state)
        self._audit_checkpoint_records(
            state_manager,
            forbidden_node_ids=frozenset(
                forbidden_checkpoint_node_ids
            ),
        )

    def _audit_bundle_surface(
        self,
        *,
        node_id: str,
        resolve_bundle_path: Callable[[str], Path | None],
    ) -> None:
        node = self.bundle.ir.nodes.get(node_id)
        common = getattr(getattr(node, "execution_config", None), "common", None)
        output_bundle = getattr(common, "output_bundle", None)
        if not isinstance(output_bundle, Mapping):
            return
        raw_path = output_bundle.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            self._raise_profile_conflict(node_id, "pure_bundle")
        path = resolve_bundle_path(node_id)
        if path is None:
            return
        if not isinstance(path, Path) or not path.is_absolute():
            self._raise_profile_conflict(node_id, "pure_bundle")
        if path.exists():
            self._raise_profile_conflict(node_id, "pure_bundle")

    def _audit_private_lineage(self, state: Mapping[str, Any]) -> None:
        versions = state.get("private_artifact_versions")
        if not isinstance(versions, Mapping):
            self._raise_profile_conflict(None, "private_artifact_versions")
        for entries in versions.values():
            if not isinstance(entries, Sequence) or isinstance(
                entries,
                (str, bytes),
            ):
                self._raise_profile_conflict(
                    None,
                    "private_artifact_versions",
                )
            for entry in entries:
                if not isinstance(entry, Mapping):
                    self._raise_profile_conflict(
                        None,
                        "private_artifact_versions",
                    )
                if (
                    self.source_step_is_derived(entry.get("producer"))
                    or self.source_step_is_derived(entry.get("step_id"))
                ):
                    self._raise_profile_conflict(
                        str(entry.get("producer") or ""),
                        "private_artifact_versions",
                    )

    def _audit_checkpoint_records(
        self,
        state_manager: Any,
        *,
        forbidden_node_ids: frozenset[str],
    ) -> None:
        from orchestrator.workflow_lisp.lexical_checkpoints import (
            resolve_checkpoint_record_family_path,
        )

        if not forbidden_node_ids.issubset(self.index.nodes):
            self._raise_profile_conflict(None, "checkpoint_record")
        expected_frame_id = (
            self.scope_path.call_frame_ids[-1]
            if self.scope_path.call_frame_ids
            else None
        )
        eligible_checkpoint_ids = {
            getattr(point, "checkpoint_id", None)
            for point in self.bundle.runtime_plan.lexical_checkpoint_points
            if getattr(point, "node_id", None) in forbidden_node_ids
        }
        for point in self.bundle.runtime_plan.lexical_checkpoint_points:
            checkpoint_id = getattr(point, "checkpoint_id", None)
            if not isinstance(checkpoint_id, str) or not checkpoint_id:
                self._raise_profile_conflict(None, "checkpoint_record")
            details = getattr(point, "details", None)
            storage = (
                details.get("storage")
                if isinstance(details, Mapping)
                else None
            )
            storage_scope = (
                storage.get("resume_scope")
                if isinstance(storage, Mapping)
                else None
            )
            family_root = resolve_checkpoint_record_family_path(
                state_manager=state_manager,
                workflow_name=self.bundle.runtime_plan.workflow_name,
                checkpoint_id=checkpoint_id,
                storage_scope=(
                    storage_scope
                    if isinstance(storage_scope, str)
                    else None
                ),
            )
            if not family_root.exists():
                continue
            for path in sorted(family_root.glob("*.json")):
                try:
                    record = json.loads(
                        path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    self._raise_profile_conflict(
                        None,
                        "checkpoint_record",
                    )
                if (
                    not isinstance(record, Mapping)
                    or record.get("checkpoint_id") != checkpoint_id
                ):
                    self._raise_profile_conflict(
                        None,
                        "checkpoint_record",
                    )
                frame_identity = record.get("frame_identity")
                record_frame_id = (
                    frame_identity.get("call_frame_id")
                    if isinstance(frame_identity, Mapping)
                    else None
                )
                if record_frame_id != expected_frame_id:
                    continue
                if checkpoint_id in eligible_checkpoint_ids:
                    self._raise_profile_conflict(
                        getattr(point, "node_id", None),
                        "checkpoint_record",
                    )
                restore = record.get("restore_payload")
                if restore is None:
                    continue
                bindings = (
                    restore.get("bindings")
                    if isinstance(restore, Mapping)
                    else None
                )
                if not isinstance(bindings, Sequence) or isinstance(
                    bindings,
                    (str, bytes),
                ):
                    self._raise_profile_conflict(
                        None,
                        "restore_payload",
                    )
                if any(
                    isinstance(binding, Mapping)
                    and self.source_step_is_derived(
                        binding.get("source_step_id")
                    )
                    for binding in bindings
                ):
                    self._raise_profile_conflict(
                        None,
                        "restore_payload",
                    )

    def _raise_profile_conflict(
        self,
        node_id: str | None,
        surface: str,
    ) -> None:
        raise PureResultReplayIndexError(
            PROFILE_CONFLICT,
            "replay-profile persistence surfaces conflict",
            context={
                "node_id": node_id,
                "surface": surface,
            },
        )


@dataclass(frozen=True)
class PureReplayBinding:
    """One validator-owned binding path resolved to a typed address."""

    path: tuple[BindingPathPart, ...]
    address: ReplayAddress


@dataclass(frozen=True)
class PureReplayNode:
    """One replay-eligible pure projection and its exact dependencies."""

    node_id: str
    step_id: str
    presentation_key: str
    bindings: tuple[PureReplayBinding, ...]
    output_addresses: tuple[NodeResultAddress, ...]
    output_contracts: Mapping[str, Mapping[str, Any]]
    pure_dependency_node_ids: tuple[str, ...]
    durable_dependency_node_ids: tuple[str, ...]


def _validate_replay_result_output_members(
    replay_node: PureReplayNode,
    *,
    result: Mapping[str, Any],
) -> None:
    """Require exactly the output members active for one normalized result."""

    artifacts = result.get("artifacts")
    if not isinstance(artifacts, Mapping) or any(
        not isinstance(member, str) or not member
        for member in artifacts
    ):
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "pure replay result artifacts must be a named object",
            context={"node_id": replay_node.node_id},
        )

    expected_members: set[str] = set()
    for member, contract in replay_node.output_contracts.items():
        projection = contract.get("projection")
        if (
            not isinstance(projection, Mapping)
            or projection.get("projection_class")
            != "union_workflow_boundary"
        ):
            expected_members.add(member)
            continue

        role = projection.get("field_role")
        discriminant_member = projection.get("discriminant_output")
        active_variants = projection.get("active_variants")
        if (
            role not in {"discriminant", "shared", "variant"}
            or not isinstance(discriminant_member, str)
            or not discriminant_member
            or discriminant_member not in replay_node.output_contracts
            or not isinstance(active_variants, (list, tuple))
            or not active_variants
            or any(
                not isinstance(variant, str) or not variant
                for variant in active_variants
            )
        ):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay union output projection metadata is invalid",
                context={
                    "node_id": replay_node.node_id,
                    "member": member,
                },
            )
        active_variant = artifacts.get(discriminant_member)
        if not isinstance(active_variant, str) or not active_variant:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay union result omits its discriminant",
                context={
                    "node_id": replay_node.node_id,
                    "member": discriminant_member,
                },
            )
        if role == "discriminant" and active_variant not in set(
            active_variants
        ):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay union result has an unknown discriminant",
                context={
                    "node_id": replay_node.node_id,
                    "member": discriminant_member,
                    "variant": active_variant,
                },
            )
        if role != "variant" or active_variant in set(active_variants):
            expected_members.add(member)

    actual_members = set(artifacts)
    if actual_members != expected_members:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "pure replay result output members do not match the active contract",
            context={
                "node_id": replay_node.node_id,
                "missing_members": sorted(expected_members - actual_members),
                "unexpected_members": sorted(actual_members - expected_members),
            },
        )


@dataclass(frozen=True)
class PureResultReplayIndex:
    """Immutable replay index derived from validated in-memory program facts."""

    scope_kind: str
    nodes: Mapping[str, PureReplayNode]
    topological_node_ids: tuple[str, ...]
    ineligible_pure_reasons: Mapping[str, str]
    _pure_node_ids: frozenset[str]

    def required_pure_node_ids(
        self,
        seed_addresses: Sequence[NodeResultAddress],
        *,
        reached_node_ids: Sequence[str],
    ) -> tuple[str, ...]:
        """Return the exact reached pure dependency closure for consumers."""

        reached = frozenset(reached_node_ids)
        required: set[str] = set()

        def include(node_id: str) -> None:
            if node_id in required:
                return
            if node_id in self.ineligible_pure_reasons:
                raise PureResultReplayIndexError(
                    self.ineligible_pure_reasons[node_id],
                    "replay consumer requires an ineligible pure projection",
                    context={"node_id": node_id},
                )
            replay_node = self.nodes.get(node_id)
            if replay_node is None:
                if node_id in self._pure_node_ids:
                    raise PureResultReplayIndexError(
                        DEPENDENCY_INDEX_INVALID,
                        "replay consumer requires an unindexed pure projection",
                        context={"node_id": node_id},
                    )
                return
            if node_id not in reached:
                raise PureResultReplayIndexError(
                    REACHABILITY_AMBIGUOUS,
                    "replay dependency is not in the validated reached prefix",
                    context={"node_id": node_id},
                )
            required.add(node_id)
            for dependency_node_id in replay_node.pure_dependency_node_ids:
                include(dependency_node_id)

        for address in seed_addresses:
            if not isinstance(address, NodeResultAddress):
                raise PureResultReplayIndexError(
                    DEPENDENCY_INDEX_INVALID,
                    "replay closure seeds must be typed node-result addresses",
                )
            replay_node = self.nodes.get(address.node_id)
            if replay_node is not None and address not in replay_node.output_addresses:
                raise PureResultReplayIndexError(
                    DEPENDENCY_INDEX_INVALID,
                    "replay closure seed is not a declared pure result address",
                    context={
                        "node_id": address.node_id,
                        "field": address.field,
                        "member": address.member,
                    },
                )
            include(address.node_id)

        return tuple(
            node_id
            for node_id in self.topological_node_ids
            if node_id in required
        )


def derive_pure_result_replay_index(
    bundle: LoadedWorkflowBundle,
    *,
    scope_kind: str = "root",
) -> PureResultReplayIndex:
    """Derive replay dependencies without mutating or serializing the program."""

    if scope_kind not in {"root", "self"}:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "replay scope kind must be root or self",
            context={"scope_kind": scope_kind},
        )
    if not isinstance(bundle, LoadedWorkflowBundle):
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "replay dependency derivation requires one loaded workflow bundle",
        )

    executable = bundle.ir
    runtime_plan = bundle.runtime_plan
    projection = bundle.projection
    selector_to_node_id = _validated_projection_catalog(bundle)
    program_node_ids = (
        tuple(runtime_plan.ordered_node_ids)
        + tuple(
            sorted(
                set(executable.nodes)
                - set(runtime_plan.ordered_node_ids)
            )
        )
    )

    iterative_node_ids = _iterative_node_ids(executable, runtime_plan)
    pure_node_ids = frozenset(
        node_id
        for node_id, node in executable.nodes.items()
        if node.kind is ExecutableNodeKind.PURE_PROJECTION
    )
    ineligible: dict[str, str] = {}
    eligible_node_ids: set[str] = set()
    for node_id in program_node_ids:
        if node_id not in pure_node_ids:
            continue
        node = executable.nodes[node_id]
        config = node.execution_config
        if not isinstance(config, PureProjectionStepConfig):
            ineligible[node_id] = DEPENDENCY_INDEX_INVALID
            continue
        if (
            node_id in iterative_node_ids
            or config.common.max_visits not in (None, 1)
        ):
            ineligible[node_id] = MULTIPLE_VISIT_REGION
            continue
        if (
            node_id not in executable.body_region
            or node_id in executable.finalization_region
            or config.common.publishes
        ):
            ineligible[node_id] = DEPENDENCY_INDEX_INVALID
            continue
        eligible_node_ids.add(node_id)

    catalog = SurfaceRefScopeCatalog(
        root_step_names=(
            tuple(selector_to_node_id) if scope_kind == "root" else ()
        ),
        self_step_names=(
            tuple(selector_to_node_id) if scope_kind == "self" else ()
        ),
    )
    raw_bindings: dict[str, tuple[PureReplayBinding, ...]] = {}
    output_addresses: dict[str, tuple[NodeResultAddress, ...]] = {}
    output_contracts_by_node: dict[
        str,
        Mapping[str, Mapping[str, Any]],
    ] = {}
    dependency_addresses: dict[str, tuple[NodeResultAddress, ...]] = {}

    for node_id in program_node_ids:
        if node_id not in eligible_node_ids:
            continue
        node = executable.nodes[node_id]
        config = node.execution_config
        assert isinstance(config, PureProjectionStepConfig)
        pure_projection = config.pure_projection
        binding_refs = pure_projection.get("binding_refs")
        payload = pure_projection.get("payload")
        output_contracts = pure_projection.get("output_contracts")
        if (
            not isinstance(binding_refs, Mapping)
            or not isinstance(payload, Mapping)
            or not isinstance(output_contracts, Mapping)
        ):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure projection replay metadata is incomplete",
                context={"node_id": node_id},
            )
        payload_bindings = payload.get("bindings")
        if (
            not isinstance(payload_bindings, Mapping)
            or set(payload_bindings) != set(binding_refs)
        ):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure projection binding catalog is inconsistent",
                context={"node_id": node_id},
            )

        resolved: list[PureReplayBinding] = []
        node_dependencies: list[NodeResultAddress] = []
        for path, ref in _walk_typed_binding_ref_documents(
            binding_refs,
            payload_bindings=payload_bindings,
        ):
            address = _resolve_replay_ref(
                ref,
                executable=executable,
                selector_to_node_id=selector_to_node_id,
                catalog=catalog,
                scope_kind=scope_kind,
            )
            resolved.append(PureReplayBinding(path=path, address=address))
            if isinstance(address, NodeResultAddress):
                node_dependencies.append(address)
        raw_bindings[node_id] = tuple(resolved)
        dependency_addresses[node_id] = tuple(node_dependencies)
        normalized_output_contracts: dict[str, Mapping[str, Any]] = {}
        for member, contract in output_contracts.items():
            if (
                not isinstance(member, str)
                or not member
                or not isinstance(contract, Mapping)
            ):
                raise PureResultReplayIndexError(
                    DEPENDENCY_INDEX_INVALID,
                    "pure projection output contracts are invalid",
                    context={"node_id": node_id},
                )
            normalized_output_contracts[member] = MappingProxyType(
                dict(contract)
            )
        output_contracts_by_node[node_id] = MappingProxyType(
            normalized_output_contracts
        )
        output_addresses[node_id] = tuple(
            NodeResultAddress(
                node_id=node_id,
                field="artifacts",
                member=member,
            )
            for member in sorted(normalized_output_contracts)
        )

    eligible_node_ids, ineligible = _propagate_pure_ineligibility(
        eligible_node_ids=eligible_node_ids,
        pure_node_ids=pure_node_ids,
        dependency_addresses=dependency_addresses,
        ineligible_reasons=ineligible,
        program_node_ids=program_node_ids,
    )

    pure_dependencies: dict[str, tuple[str, ...]] = {}
    durable_dependencies: dict[str, tuple[str, ...]] = {}
    for node_id in program_node_ids:
        if node_id not in eligible_node_ids:
            continue
        pure_dependencies[node_id] = _unique_in_program_order(
            (
                address.node_id
                for address in dependency_addresses[node_id]
                if address.node_id in eligible_node_ids
            ),
            runtime_plan=runtime_plan,
        )
        durable_dependencies[node_id] = _unique_in_program_order(
            (
                address.node_id
                for address in dependency_addresses[node_id]
                if address.node_id not in pure_node_ids
            ),
            runtime_plan=runtime_plan,
        )

    topological_node_ids = _topological_pure_order(
        eligible_node_ids,
        pure_dependencies,
        runtime_plan=runtime_plan,
    )
    nodes = {
        node_id: PureReplayNode(
            node_id=node_id,
            step_id=executable.nodes[node_id].step_id,
            presentation_key=(
                projection.entries_by_node_id[node_id].presentation_key
            ),
            bindings=raw_bindings[node_id],
            output_addresses=output_addresses[node_id],
            output_contracts=output_contracts_by_node[node_id],
            pure_dependency_node_ids=pure_dependencies[node_id],
            durable_dependency_node_ids=durable_dependencies[node_id],
        )
        for node_id in topological_node_ids
    }
    return PureResultReplayIndex(
        scope_kind=scope_kind,
        nodes=MappingProxyType(nodes),
        topological_node_ids=topological_node_ids,
        ineligible_pure_reasons=MappingProxyType(dict(ineligible)),
        _pure_node_ids=pure_node_ids,
    )


def _propagate_pure_ineligibility(
    *,
    eligible_node_ids: set[str],
    pure_node_ids: frozenset[str],
    dependency_addresses: Mapping[
        str,
        tuple[NodeResultAddress, ...],
    ],
    ineligible_reasons: Mapping[str, str],
    program_node_ids: Sequence[str],
) -> tuple[set[str], dict[str, str]]:
    """Propagate pure ineligibility in deterministic simultaneous rounds."""

    eligible = set(eligible_node_ids)
    reasons = dict(ineligible_reasons)
    ordered_node_ids = tuple(program_node_ids)
    if not eligible.issubset(ordered_node_ids):
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "eligible pure node is absent from program order",
        )

    while True:
        round_eligible = frozenset(eligible)
        rejected: list[tuple[str, str]] = []
        for node_id in ordered_node_ids:
            if node_id not in round_eligible:
                continue
            for address in dependency_addresses.get(node_id, ()):
                if (
                    address.node_id not in pure_node_ids
                    or address.node_id in round_eligible
                ):
                    continue
                rejected.append(
                    (
                        node_id,
                        reasons.get(
                            address.node_id,
                            DEPENDENCY_INDEX_INVALID,
                        ),
                    )
                )
                break
        if not rejected:
            return eligible, reasons
        for node_id, reason in rejected:
            eligible.remove(node_id)
            reasons[node_id] = reason


def _validated_projection_catalog(
    bundle: LoadedWorkflowBundle,
) -> dict[str, str]:
    executable = bundle.ir
    runtime_plan = bundle.runtime_plan
    projection = bundle.projection
    node_ids = set(executable.nodes)
    if (
        set(runtime_plan.nodes) != node_ids
        or set(projection.entries_by_node_id) != node_ids
        or set(projection.presentation_key_by_node_id) != node_ids
        or set(projection.node_id_by_step_id.values()) != node_ids
        or len(projection.node_id_by_step_id) != len(node_ids)
    ):
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "loaded workflow node and projection catalogs differ",
        )
    try:
        validate_workflow_runtime_plan(
            runtime_plan,
            executable,
            projection,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "loaded workflow runtime plan does not match its projection",
            context={"error": str(exc)},
        ) from exc

    expected_order = (
        tuple(executable.body_region)
        + tuple(executable.finalization_region)
    )
    if (
        runtime_plan.ordered_node_ids != expected_order
        or projection.ordered_execution_node_ids() != expected_order
    ):
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "loaded workflow execution order does not match its projection",
        )

    selector_to_node_id: dict[str, str] = {}
    for node_id in executable.nodes:
        executable_node = executable.nodes[node_id]
        plan_node = runtime_plan.nodes[node_id]
        entry = projection.entries_by_node_id[node_id]
        selector = entry.presentation_key
        if (
            entry.node_id != node_id
            or executable_node.node_id != node_id
            or plan_node.node_id != node_id
            or entry.step_id != executable_node.step_id
            or entry.step_id != plan_node.step_id
            or projection.node_id_by_step_id.get(entry.step_id) != node_id
            or projection.presentation_key_by_node_id.get(node_id) != selector
            or selector != executable_node.presentation_name
            or selector != plan_node.presentation_key
            or entry.region != executable_node.region
            or plan_node.region != executable_node.region.value
            or plan_node.kind != executable_node.kind.value
        ):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "loaded workflow projection identity disagrees",
                context={"node_id": node_id},
            )
        if not isinstance(selector, str) or not selector:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "projection presentation selector is missing",
                context={"node_id": node_id},
            )
        previous = selector_to_node_id.setdefault(selector, node_id)
        if previous != node_id:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "projection presentation selector is ambiguous",
                context={
                    "presentation_key": selector,
                    "node_ids": [previous, node_id],
                },
            )
    return selector_to_node_id


def _walk_value_document_refs(
    value_document: Any,
) -> tuple[tuple[tuple[BindingPathPart, ...], str], ...]:
    """Extract exact ref leaves while preserving ordinary JSON literals."""

    try:
        canonical_json_for_pure_value(value_document)
    except (PureExprEvaluationError, TypeError, ValueError) as exc:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "value document must contain canonical JSON values",
            context={"cause": type(exc).__name__},
        ) from exc

    resolved: list[tuple[tuple[BindingPathPart, ...], str]] = []

    def walk(value: Any, path: tuple[BindingPathPart, ...]) -> None:
        if isinstance(value, Mapping):
            if "ref" in value:
                if (
                    set(value) != {"ref"}
                    or not isinstance(value["ref"], str)
                    or not value["ref"]
                ):
                    raise PureResultReplayIndexError(
                        DEPENDENCY_INDEX_INVALID,
                        "value-document ref must contain only one non-empty string",
                        context={"binding_path": list(path)},
                    )
                resolved.append((path, value["ref"]))
                return
            for key in sorted(value, key=str):
                if not isinstance(key, str):
                    raise PureResultReplayIndexError(
                        DEPENDENCY_INDEX_INVALID,
                        "value-document keys must be strings",
                        context={"binding_path": list(path)},
                    )
                walk(value[key], (*path, key))
            return
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, (*path, index))
            return
        if value is None or type(value) in {bool, int, float, str}:
            return
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "value document contains a non-JSON value",
            context={"binding_path": list(path)},
        )

    walk(value_document, ())
    return tuple(resolved)


def _document_contains_ref_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return "ref" in value or any(
            _document_contains_ref_key(item)
            for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_document_contains_ref_key(item) for item in value)
    return False


def _typed_descriptor_contains_union(
    descriptor: Mapping[str, Any],
) -> bool:
    kind = descriptor.get("kind")
    if kind in {"union", "variant_case"}:
        return True
    if kind in {"optional", "list"}:
        item = descriptor.get("item")
        return isinstance(item, Mapping) and _typed_descriptor_contains_union(
            item
        )
    if kind == "map":
        return any(
            isinstance(item, Mapping)
            and _typed_descriptor_contains_union(item)
            for item in (descriptor.get("key"), descriptor.get("value"))
        )
    if kind == "record":
        fields_value = descriptor.get("fields")
        return (
            isinstance(fields_value, Sequence)
            and not isinstance(fields_value, (str, bytes))
            and any(
                isinstance(field, Mapping)
                and isinstance(field.get("type"), Mapping)
                and _typed_descriptor_contains_union(field["type"])
                for field in fields_value
            )
        )
    return False


def _raise_typed_binding_document_error(
    message: str,
    *,
    path: tuple[BindingPathPart, ...],
    cause: PureExprEvaluationError | None = None,
) -> NoReturn:
    context: dict[str, Any] = {"binding_path": list(path)}
    if cause is not None:
        context["cause"] = {
            "code": cause.code,
            "message": str(cause),
        }
    raise PureResultReplayIndexError(
        DEPENDENCY_INDEX_INVALID,
        message,
        context=context,
    ) from cause


def _validate_typed_literal(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    path: tuple[BindingPathPart, ...],
) -> None:
    try:
        _coerce_value(
            value,
            descriptor,
            context="pure replay binding literal",
        )
    except PureExprEvaluationError as exc:
        _raise_typed_binding_document_error(
            "pure replay binding literal does not match its declared type",
            path=path,
            cause=exc,
        )


def _descriptor_fields(
    descriptor: Mapping[str, Any],
    *,
    path: tuple[BindingPathPart, ...],
) -> dict[str, Mapping[str, Any]]:
    fields_value = descriptor.get("fields")
    if (
        not isinstance(fields_value, Sequence)
        or isinstance(fields_value, (str, bytes))
    ):
        _raise_typed_binding_document_error(
            "pure replay binding type has invalid field metadata",
            path=path,
        )
    fields_by_name: dict[str, Mapping[str, Any]] = {}
    for field in fields_value:
        if (
            not isinstance(field, Mapping)
            or not isinstance(field.get("name"), str)
            or not field["name"]
            or not isinstance(field.get("type"), Mapping)
            or field["name"] in fields_by_name
        ):
            _raise_typed_binding_document_error(
                "pure replay binding type has invalid field metadata",
                path=path,
            )
        fields_by_name[field["name"]] = field["type"]
    return fields_by_name


def _walk_typed_binding_value(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    path: tuple[BindingPathPart, ...],
    resolved: list[tuple[tuple[BindingPathPart, ...], str]],
) -> None:
    if isinstance(value, Mapping) and "ref" in value:
        if (
            set(value) != {"ref"}
            or not isinstance(value["ref"], str)
            or not value["ref"]
        ):
            _raise_typed_binding_document_error(
                "binding ref document must contain only one non-empty string ref",
                path=path,
            )
        resolved.append((path, value["ref"]))
        return

    kind = descriptor.get("kind")
    if kind == "primitive" and descriptor.get("name") == "Json":
        for nested_path, ref in _walk_value_document_refs(value):
            resolved.append(((*path, *nested_path), ref))
        return
    if (
        not _typed_descriptor_contains_union(descriptor)
        and not _document_contains_ref_key(value)
    ):
        _validate_typed_literal(value, descriptor, path=path)
        return

    if kind == "optional":
        item_descriptor = descriptor.get("item")
        if not isinstance(item_descriptor, Mapping):
            _raise_typed_binding_document_error(
                "pure replay optional binding metadata is invalid",
                path=path,
            )
        if value is None:
            _validate_typed_literal(value, descriptor, path=path)
            return
        _walk_typed_binding_value(
            value,
            item_descriptor,
            path=path,
            resolved=resolved,
        )
        return

    if kind == "list":
        item_descriptor = descriptor.get("item")
        if (
            not isinstance(item_descriptor, Mapping)
            or not isinstance(value, (list, tuple))
        ):
            _raise_typed_binding_document_error(
                "pure replay list binding metadata is invalid",
                path=path,
            )
        for index, item in enumerate(value):
            _walk_typed_binding_value(
                item,
                item_descriptor,
                path=(*path, index),
                resolved=resolved,
            )
        return

    if kind == "map":
        key_descriptor = descriptor.get("key")
        value_descriptor = descriptor.get("value")
        if (
            not isinstance(value, Mapping)
            or not isinstance(key_descriptor, Mapping)
            or not isinstance(value_descriptor, Mapping)
        ):
            _raise_typed_binding_document_error(
                "pure replay map binding metadata is invalid",
                path=path,
            )
        for key in sorted(value, key=str):
            _validate_typed_literal(
                key,
                key_descriptor,
                path=(*path, str(key)),
            )
            _walk_typed_binding_value(
                value[key],
                value_descriptor,
                path=(*path, str(key)),
                resolved=resolved,
            )
        return

    if kind == "record":
        if not isinstance(value, Mapping):
            _raise_typed_binding_document_error(
                "pure replay record binding must be an object",
                path=path,
            )
        fields_by_name = _descriptor_fields(descriptor, path=path)
        if set(value) != set(fields_by_name):
            _raise_typed_binding_document_error(
                "pure replay record binding fields do not match its type",
                path=path,
            )
        for field_name, field_descriptor in fields_by_name.items():
            _walk_typed_binding_value(
                value[field_name],
                field_descriptor,
                path=(*path, field_name),
                resolved=resolved,
            )
        return

    if kind in {"union", "variant_case"}:
        if not isinstance(value, Mapping):
            _raise_typed_binding_document_error(
                "pure replay union binding must be an object",
                path=path,
            )
        variant_value = value.get("variant", _DURABLE_VALUE_MISSING)
        variant_descriptor: Mapping[str, Any] | None = None
        if kind == "variant_case":
            variant_name = descriptor.get("variant")
            union_name = descriptor.get("union_name")
            if (
                not isinstance(variant_name, str)
                or not variant_name
                or not isinstance(union_name, str)
                or not union_name
                or variant_value is _DURABLE_VALUE_MISSING
            ):
                _raise_typed_binding_document_error(
                    "pure replay variant-case binding metadata is invalid",
                    path=path,
                )
            variant_descriptor = descriptor
            _walk_typed_binding_value(
                variant_value,
                {
                    "kind": "enum",
                    "name": union_name,
                    "allowed": [variant_name],
                },
                path=(*path, "variant"),
                resolved=resolved,
            )
        else:
            variants = descriptor.get("variants")
            if (
                not isinstance(variants, Sequence)
                or isinstance(variants, (str, bytes))
            ):
                _raise_typed_binding_document_error(
                    "pure replay union binding type is invalid",
                    path=path,
                )
            variant_name = variant_value
            if not isinstance(variant_name, str) or not variant_name:
                _raise_typed_binding_document_error(
                    "pure replay union binding must have a literal variant",
                    path=path,
                )
            variant_descriptor = next(
                (
                    variant
                    for variant in variants
                    if isinstance(variant, Mapping)
                    and variant.get("name") == variant_name
                ),
                None,
            )
        if not isinstance(variant_descriptor, Mapping):
            _raise_typed_binding_document_error(
                "pure replay union binding selects an unknown variant",
                path=path,
            )
        fields_by_name = _descriptor_fields(
            variant_descriptor,
            path=path,
        )
        missing = set(fields_by_name) - set(value)
        if missing:
            _raise_typed_binding_document_error(
                "pure replay union binding omits active fields",
                path=path,
            )
        field_descriptors: dict[str, list[Mapping[str, Any]]] = {
            field_name: [field_descriptor]
            for field_name, field_descriptor in fields_by_name.items()
        }
        if kind == "union":
            for variant in descriptor.get("variants", ()):
                if not isinstance(variant, Mapping):
                    continue
                for field_name, field_descriptor in _descriptor_fields(
                    variant,
                    path=path,
                ).items():
                    candidates = field_descriptors.setdefault(
                        field_name,
                        [],
                    )
                    if not any(
                        field_descriptor == candidate
                        for candidate in candidates
                    ):
                        candidates.append(field_descriptor)
        known_union_fields = set(field_descriptors)
        unknown = set(value) - known_union_fields - {"variant"}
        if unknown:
            _raise_typed_binding_document_error(
                "pure replay union binding has unknown fields",
                path=path,
            )
        for field_name, field_descriptor in fields_by_name.items():
            _walk_typed_binding_value(
                value[field_name],
                field_descriptor,
                path=(*path, field_name),
                resolved=resolved,
            )
        for inactive_name in known_union_fields - set(fields_by_name):
            inactive_value = value.get(inactive_name, _DURABLE_VALUE_MISSING)
            if (
                inactive_value is not _DURABLE_VALUE_MISSING
                and _document_contains_ref_key(inactive_value)
            ):
                _raise_typed_binding_document_error(
                    "pure replay inactive union binding fields cannot contain refs",
                    path=(*path, inactive_name),
                )
            if inactive_value is _DURABLE_VALUE_MISSING:
                continue
            for inactive_descriptor in field_descriptors[inactive_name]:
                _walk_typed_binding_value(
                    inactive_value,
                    inactive_descriptor,
                    path=(*path, inactive_name),
                    resolved=resolved,
                )
        return

    _raise_typed_binding_document_error(
        "pure replay binding ref appears outside a typed container",
        path=path,
    )


def _walk_typed_binding_ref_documents(
    binding_refs: Mapping[str, Any],
    *,
    payload_bindings: Mapping[str, Any],
) -> tuple[tuple[tuple[BindingPathPart, ...], str], ...]:
    resolved: list[tuple[tuple[BindingPathPart, ...], str]] = []
    for binding_name in sorted(binding_refs):
        if not isinstance(binding_name, str) or not binding_name:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "binding names must be non-empty strings",
            )
        binding_spec = payload_bindings.get(binding_name)
        descriptor = (
            binding_spec.get("type")
            if isinstance(binding_spec, Mapping)
            else None
        )
        if not isinstance(descriptor, Mapping):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay binding type metadata is missing",
                context={"binding_path": [binding_name]},
            )
        _walk_typed_binding_value(
            binding_refs[binding_name],
            descriptor,
            path=(binding_name,),
            resolved=resolved,
        )
    return tuple(resolved)


def _resolve_replay_ref(
    ref: str,
    *,
    executable: ExecutableWorkflow,
    selector_to_node_id: Mapping[str, str],
    catalog: SurfaceRefScopeCatalog,
    scope_kind: str,
) -> ReplayAddress:
    try:
        parsed = parse_surface_ref(ref, catalog)
    except ReferenceResolutionError as exc:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "pure replay binding ref is invalid",
            context={"ref": ref, "error": str(exc)},
        ) from exc

    if isinstance(parsed, WorkflowInputReference):
        if parsed.input_name not in executable.inputs:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay binding references an unknown workflow input",
                context={"ref": ref, "input_name": parsed.input_name},
            )
        return WorkflowInputAddress(parsed.input_name)
    if isinstance(parsed, SelfOutputReference):
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "self output refs are not replay dependency addresses",
            context={"ref": ref},
        )
    if not isinstance(parsed, StructuredStepReference):
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "pure replay binding ref has an unsupported parsed form",
            context={"ref": ref},
        )
    if parsed.scope != scope_kind:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "pure replay binding crosses the indexed frame scope",
            context={
                "ref": ref,
                "expected_scope": scope_kind,
                "actual_scope": parsed.scope,
            },
        )
    node_id = selector_to_node_id.get(parsed.step_name)
    if node_id is None:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "pure replay binding references an unknown presentation selector",
            context={"ref": ref, "step_name": parsed.step_name},
        )
    _validate_result_member(
        executable.nodes[node_id].execution_config,
        field=parsed.field,
        member=parsed.member,
        ref=ref,
    )
    return NodeResultAddress(
        node_id=node_id,
        field=parsed.field,
        member=parsed.member,
    )


def _validate_result_member(
    config: Any,
    *,
    field: str,
    member: str | None,
    ref: str,
) -> None:
    if field == "exit_code" and member is None:
        return
    if field == "outcome" and member in {
        "status",
        "phase",
        "class",
        "retryable",
    }:
        return
    if field != "artifacts" or not isinstance(member, str) or not member:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "pure replay binding field is not a supported result address",
            context={"ref": ref, "field": field, "member": member},
        )
    common = getattr(config, "common", None)
    output_bundle = getattr(common, "output_bundle", None)
    fields = (
        output_bundle.get("fields")
        if isinstance(output_bundle, Mapping)
        else None
    )
    members = {
        field_record.get("name")
        for field_record in fields
        if isinstance(field_record, Mapping)
        and isinstance(field_record.get("name"), str)
    } if isinstance(fields, (list, tuple)) else set()
    if member not in members:
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "pure replay binding references an unknown result member",
            context={"ref": ref, "member": member},
        )


def _compiled_node_result_contract(
    bundle: LoadedWorkflowBundle,
    address: NodeResultAddress,
) -> Mapping[str, Any] | None:
    """Return the exact compiled artifact-member contract for one address."""

    if address.field != "artifacts" or not isinstance(address.member, str):
        return None
    node = bundle.ir.nodes.get(address.node_id)
    common = getattr(
        getattr(node, "execution_config", None),
        "common",
        None,
    )
    output_bundle = getattr(common, "output_bundle", None)
    fields = (
        output_bundle.get("fields")
        if isinstance(output_bundle, Mapping)
        else None
    )
    if not isinstance(fields, (list, tuple)):
        return None
    matches = tuple(
        field
        for field in fields
        if isinstance(field, Mapping)
        and field.get("name") == address.member
    )
    if len(matches) != 1:
        return None
    return matches[0]


def _durable_node_result_value(
    bundle: LoadedWorkflowBundle,
    address: NodeResultAddress,
    row: Mapping[str, Any],
) -> tuple[Any, Mapping[str, Any] | None]:
    """Resolve one admitted durable result address and its exact contract."""

    intrinsic_contract = _INTRINSIC_DURABLE_RESULT_CONTRACTS.get(
        (address.field, address.member)
    )
    if intrinsic_contract is not None:
        if address.field == "exit_code":
            return (
                row.get("exit_code", _DURABLE_VALUE_MISSING),
                intrinsic_contract,
            )
        outcome = row.get("outcome")
        if not isinstance(outcome, Mapping):
            return _DURABLE_VALUE_MISSING, intrinsic_contract
        return (
            outcome.get(
                address.member,
                _DURABLE_VALUE_MISSING,
            ),
            intrinsic_contract,
        )

    contract = _compiled_node_result_contract(bundle, address)
    field_value = row.get(address.field)
    if (
        contract is None
        or not isinstance(field_value, Mapping)
        or address.member not in field_value
    ):
        return _DURABLE_VALUE_MISSING, contract
    return field_value[address.member], contract


def _iterative_node_ids(
    executable: ExecutableWorkflow,
    runtime_plan: WorkflowRuntimePlan,
) -> set[str]:
    iterative: set[str] = set()
    for node in executable.nodes.values():
        if isinstance(node, (ForEachNode, RepeatUntilFrameNode)):
            iterative.update(node.body_node_ids)
    for node in runtime_plan.nodes.values():
        iterative.update(node.nested_body_node_ids)
    return iterative


def _unique_in_program_order(
    node_ids: Any,
    *,
    runtime_plan: WorkflowRuntimePlan,
) -> tuple[str, ...]:
    requested = set(node_ids)
    order = {
        node_id: index
        for index, node_id in enumerate(runtime_plan.ordered_node_ids)
    }
    return tuple(
        sorted(
            requested,
            key=lambda node_id: (order.get(node_id, len(order)), node_id),
        )
    )


def _topological_pure_order(
    node_ids: set[str],
    dependencies: Mapping[str, tuple[str, ...]],
    *,
    runtime_plan: WorkflowRuntimePlan,
) -> tuple[str, ...]:
    order = {
        node_id: index
        for index, node_id in enumerate(runtime_plan.ordered_node_ids)
    }
    remaining = set(node_ids)
    emitted: list[str] = []
    while remaining:
        ready = sorted(
            (
                node_id
                for node_id in remaining
                if not (set(dependencies[node_id]) & remaining)
            ),
            key=lambda node_id: (order.get(node_id, len(order)), node_id),
        )
        if not ready:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure replay dependency graph contains a cycle",
                context={"node_ids": sorted(remaining)},
            )
        for node_id in ready:
            remaining.remove(node_id)
            emitted.append(node_id)
    return tuple(emitted)
