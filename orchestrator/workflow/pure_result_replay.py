"""Identity-neutral dependency indexing for deterministic pure-result replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .executable_ir import (
    ExecutableNodeKind,
    ExecutableWorkflow,
    ForEachNode,
    NodeResultAddress,
    PureProjectionStepConfig,
    RepeatUntilFrameNode,
    WorkflowInputAddress,
)
from .loaded_bundle import LoadedWorkflowBundle
from .references import (
    ReferenceResolutionError,
    SelfOutputReference,
    StructuredStepReference,
    SurfaceRefScopeCatalog,
    WorkflowInputReference,
    parse_surface_ref,
)
from .runtime_plan import (
    WorkflowRuntimePlan,
    validate_workflow_runtime_plan,
)


PURE_RESULT_REPLAY_DIAGNOSTIC = "pure_result_replay_unavailable"
DEPENDENCY_INDEX_INVALID = "dependency_index_invalid"
REACHABILITY_AMBIGUOUS = "reachability_ambiguous"
MULTIPLE_VISIT_REGION = "multiple_visit_region"

BindingPathPart = str | int
ReplayAddress = WorkflowInputAddress | NodeResultAddress


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
class PureReplayBinding:
    """One validator-owned binding path resolved to a typed address."""

    path: tuple[BindingPathPart, ...]
    address: ReplayAddress


@dataclass(frozen=True)
class PureReplayNode:
    """One replay-eligible pure projection and its exact dependencies."""

    node_id: str
    presentation_key: str
    bindings: tuple[PureReplayBinding, ...]
    output_addresses: tuple[NodeResultAddress, ...]
    pure_dependency_node_ids: tuple[str, ...]
    durable_dependency_node_ids: tuple[str, ...]


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
        for path, ref in _walk_binding_ref_documents(binding_refs):
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
        output_addresses[node_id] = tuple(
            NodeResultAddress(
                node_id=node_id,
                field="artifacts",
                member=member,
            )
            for member in sorted(output_contracts)
            if isinstance(member, str) and member
        )
        if len(output_addresses[node_id]) != len(output_contracts):
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "pure projection output contract names are invalid",
                context={"node_id": node_id},
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
            presentation_key=(
                projection.entries_by_node_id[node_id].presentation_key
            ),
            bindings=raw_bindings[node_id],
            output_addresses=output_addresses[node_id],
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


def _walk_binding_ref_documents(
    binding_refs: Mapping[str, Any],
) -> tuple[tuple[tuple[BindingPathPart, ...], str], ...]:
    resolved: list[tuple[tuple[BindingPathPart, ...], str]] = []

    def walk(value: Any, path: tuple[BindingPathPart, ...]) -> None:
        if isinstance(value, Mapping):
            if "ref" in value:
                if set(value) != {"ref"} or not isinstance(value["ref"], str):
                    raise PureResultReplayIndexError(
                        DEPENDENCY_INDEX_INVALID,
                        "binding ref document must contain only one string ref",
                        context={"binding_path": list(path)},
                    )
                resolved.append((path, value["ref"]))
                return
            if not value:
                raise PureResultReplayIndexError(
                    DEPENDENCY_INDEX_INVALID,
                    "binding ref document cannot be empty",
                    context={"binding_path": list(path)},
                )
            for key in sorted(value, key=str):
                if not isinstance(key, str) or not key:
                    raise PureResultReplayIndexError(
                        DEPENDENCY_INDEX_INVALID,
                        "binding ref document keys must be non-empty strings",
                        context={"binding_path": list(path)},
                    )
                walk(value[key], (*path, key))
            return
        if isinstance(value, (list, tuple)):
            if not value:
                raise PureResultReplayIndexError(
                    DEPENDENCY_INDEX_INVALID,
                    "binding ref sequence cannot be empty",
                    context={"binding_path": list(path)},
                )
            for index, item in enumerate(value):
                walk(item, (*path, index))
            return
        raise PureResultReplayIndexError(
            DEPENDENCY_INDEX_INVALID,
            "binding metadata contains a value outside the ref-document grammar",
            context={"binding_path": list(path)},
        )

    for binding_name in sorted(binding_refs):
        if not isinstance(binding_name, str) or not binding_name:
            raise PureResultReplayIndexError(
                DEPENDENCY_INDEX_INVALID,
                "binding names must be non-empty strings",
            )
        walk(binding_refs[binding_name], (binding_name,))
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
