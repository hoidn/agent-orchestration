"""Build one checked closed-program table from an admitted typed program."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from pathlib import Path
from typing import Any

from orchestrator.workflow_lisp.context_classification import (
    _is_item_context_shape,
    _is_phase_context_shape,
    _is_run_context_shape,
)
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    compiler_defect_boundary,
    records_defect_provenance,
)
from orchestrator.workflow_lisp.lowering.values import _procedure_signature_local_type_bindings
from orchestrator.workflow_lisp.type_env import (
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
)
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.model import (
    WCC_M4_ROUTE_SCHEMA_VERSION,
    WccBody,
    WccCall,
    WccCase,
    WccHalt,
    WccIf,
    WccJoin,
    WccJump,
    WccLet,
    WccLoopContinue,
    WccLoopDone,
    WccFieldAccessAtom,
    WccInject,
    WccPerform,
    WccNameAtom,
    WccPureOp,
    WccRecJoin,
    WccRecordAtom,
    WccSelect,
    WccProviderSupervision,
    WccProviderPeerGroup,
)

from . import EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
from .context import phase_context_value, run_context_value
from .effects import require_command_closures, translate_perform
from .names import (
    Renamer,
    _loop_carrier_metadata,
    _run_ref_signatures,
    canonical_callee_name,
    canonical_callee_name_from_key,
    canonical_definition_key,
    canonical_type_identity,
    canonical_type_descriptor,
)
from .program import (
    REPRESENTATION,
    SCHEMA,
    ClosedProgram,
    _canonical_json,
    canonical_configuration,
    logical_asset_base_for_module,
    program_digest,
)
from .sites import assign_sites
from .check import validate


class ClosedProgramGap(Exception):
    """A located admitted form that has no closed translation in this release."""

    def __init__(self, form: str, message: str, *, span=None, form_path=()) -> None:
        self.form = form
        self.message = message
        self.span = span
        self.form_path = tuple(form_path)
        super().__init__(f"{form} has no closed form: {message}")


@dataclass
class CaptureSlot:
    type_ref: TypeRef
    routes: list[Any]
    value: Any = None
    source_name: str | None = None
    identity: Any = None
    type_program: Any | None = None
    run_ref_producers: tuple["RunRefProducer", ...] = ()


@dataclass(frozen=True)
class ComputedCaptureValue:
    source_name: str


@dataclass(frozen=True)
class ComputedCaptureRequest:
    source_identity: int
    formal: tuple[str, ...]
    expression: Any
    type_ref: TypeRef
    source_aliases: Mapping[str, str]
    insertion_alias: str
    source_name: str


@dataclass
class CallableRequest:
    key: list[Any]
    canonical: str
    captures: list[CaptureSlot]
    procedure_refs: Mapping[str, Any]
    procedure_ref_keys: Mapping[str, Any]
    workflow_refs: Mapping[str, Any]
    workflow_ref_keys: Mapping[str, Any]
    procedure: Any | None = None
    argument_run_ref_producers: Mapping[str, tuple["RunRefProducer", ...]] | None = None


@dataclass(eq=False)
class RunRefProducer:
    """One concrete run-ref effect occurrence retained until final naming."""

    perform: WccPerform
    owner: str
    type_ref: TypeRef
    typed: Any
    node: dict[str, Any]
    signature: dict[str, Any]
    producer_context: tuple["RunRefProducer", ...]
    site: str | None = None
    site_digest: str | None = None
    generated_name: str | None = None


def _capture_owner_groups(
    rows: tuple[Any, ...],
    *,
    owner_kind: str,
    argument_index: int | None = None,
) -> tuple[tuple[Any, tuple[Any, ...]], ...]:
    groups: list[tuple[Any, list[Any]]] = []
    for capture in rows:
        if capture.owner_kind != owner_kind:
            continue
        if owner_kind == "argument" and capture.argument_index != argument_index:
            continue
        owner = capture.source_binding
        if owner is None:
            continue
        group = next((item for item in groups if item[0] is owner), None)
        if group is None:
            group = (owner, [])
            groups.append(group)
        group[1].append(capture)
    return tuple((owner, tuple(group)) for owner, group in groups)


@dataclass
class WorkflowRequest:
    key: list[Any]
    canonical: str
    captures: list[CaptureSlot]


def gap_diagnostic(gap: ClosedProgramGap) -> LispFrontendDiagnostic:
    if gap.span is None:
        raise ValueError("closed-program gap must carry a source span")
    return LispFrontendDiagnostic(
        code="closed_program_gap",
        message=f"`{gap.form}` has no closed form in this release: {gap.message}",
        span=gap.span,
        form_path=gap.form_path,
        notes=(f"form={gap.form}",),
        phase="lowering",
    )


def _strip_provenance(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _strip_provenance(child) for key, child in value.items() if key != "@"}
    if isinstance(value, list):
        return [_strip_provenance(child) for child in value]
    if isinstance(value, tuple):
        return [_strip_provenance(child) for child in value]
    return value


@dataclass
class Definition:
    """Facts owned by one source definition while its body is translated."""

    canonical: str
    owner: str
    source_program: Any
    type_env: Any
    externs: Mapping[str, Any]
    renamer: Renamer
    names: dict[str, str]
    loops: list[tuple[str, str]]
    configuration_selector: str | None = None
    callable_definition: Any | None = None
    callable_key: list[Any] | None = None
    captures: list[CaptureSlot] | None = None
    capture_names: list[str] | None = None
    procedure_refs: Mapping[str, Any] | None = None
    procedure_ref_keys: Mapping[str, Any] | None = None
    workflow_refs: Mapping[str, Any] | None = None
    workflow_ref_keys: Mapping[str, Any] | None = None
    computed_capture_sources: Mapping[tuple[int, Any], str] | None = None
    computed_capture_requests_by_alias: Mapping[str, tuple[ComputedCaptureRequest, ...]] | None = None
    reference_capture_aliases: Mapping[tuple[int, str], str] | None = None
    context_call_occurrences: Mapping[int, tuple[list[Any], int]] | None = None
    binding_aliases: Mapping[object, str] | None = None
    capture_binding_identities: frozenset[object] = frozenset()
    run_ref_names: Mapping[str, tuple[RunRefProducer, ...]] | None = None

    def with_names(
        self,
        names: dict[str, str],
        *,
        binding_aliases: Mapping[object, str] | None = None,
        run_ref_names: Mapping[str, tuple[RunRefProducer, ...]] | None = None,
    ) -> Definition:
        aliases = (self.binding_aliases or {}) if binding_aliases is None else binding_aliases
        producers = (self.run_ref_names or {}) if run_ref_names is None else run_ref_names
        return replace(
            self,
            names=names,
            binding_aliases=dict(aliases),
            run_ref_names=dict(producers),
        )

    def resolved_binding_name(
        self,
        name: str,
        binding_identity: object | None = None,
    ) -> str:
        if binding_identity is None:
            return name
        alias = (self.binding_aliases or {}).get(binding_identity)
        if alias is not None:
            return alias
        if binding_identity in self.capture_binding_identities:
            raise ValueError("retained capture reference has no frozen lexical owner")
        return name

    def ref(self, name: str, binding_identity: object | None = None) -> str:
        return self.renamer.ref(
            self.resolved_binding_name(name, binding_identity),
            env=self.names,
        )


@records_defect_provenance("closed-program")
def _located_value(node: Any, builder: "Builder", d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
    from .values import translate_value

    return translate_value(builder, node, d, env)


@records_defect_provenance("closed-program")
def _located_body(node: WccBody, builder: "Builder", d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
    return builder._body_impl(node, d, env)


@records_defect_provenance("closed-program")
def _located_binding(node: Any, builder: "Builder", d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
    return builder._binding_impl(node, d, env)


class Builder:
    """Translate WCC through the retained owner and canonical-name contracts."""

    def __init__(self, typed: Any) -> None:
        self.typed = typed
        self.route_schema_version = WCC_M4_ROUTE_SCHEMA_VERSION
        self.definitions: dict[str, dict[str, Any]] = {}
        self.definition_keys: dict[str, list[Any]] = {}
        self.active: list[str] = []
        self.nominal_types: dict[str, dict[str, Any]] = {}
        self.opaque_ordinal = 0
        self.workflow_return_types: dict[str, TypeRef] = {}
        self.procedure_return_types: dict[str, TypeRef] = {}
        self.workflow_owners: dict[str, tuple[Any, Any]] = {}
        self.procedure_owners: dict[str, tuple[Any, Any]] = {}
        self.configuration_rows: dict[tuple[int, str], dict[str, Any]] = {}
        self.configuration_imports: dict[str, dict[str, Any]] = {}
        self.run_ref_producers: list[RunRefProducer] = []
        self.run_ref_producers_by_effect: dict[int, RunRefProducer] = {}
        self.emitted_descriptors: list[
            tuple[dict[str, Any], TypeRef, Any, tuple[RunRefProducer, ...], RunRefProducer | None]
        ] = []
        self.generated_result_contract_requests: list[
            tuple[dict[str, Any], WccPerform, Definition, tuple[RunRefProducer, ...]]
        ] = []
        self.boundary_requests: list[dict[str, Any]] = []
        self.compiler_runtime_identity: str | None = None
        self._workflow_wcc_cache: dict[tuple[int, str], Any] = {}
        self._index_owners()

    def _programs(self) -> tuple[Any, ...]:
        ordered = []
        pending = [self.typed]
        seen: set[int] = set()
        while pending:
            program = pending.pop(0)
            if id(program) in seen:
                continue
            seen.add(id(program))
            ordered.append(program)
            pending.extend(getattr(program, "imported_programs", {}).values())
        return tuple(ordered)

    @staticmethod
    def _source_module_for(program: Any, owner: str, callable_def: Any | None = None) -> str:
        """Resolve a callable's source module from retained declaration facts."""

        owned = set(getattr(program, "source_file_digests", {}) or ())
        if not owned:
            return program.entry_module
        candidates = [owner]
        if callable_def is not None:
            specialization = getattr(callable_def, "specialization", None)
            candidates.extend(
                [
                    getattr(specialization, "base_name", None),
                    getattr(getattr(callable_def, "definition", None), "name", None),
                ]
            )
        local_dids = getattr(program, "local_definition_dids", {})
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            did = local_dids.get(candidate)
            if isinstance(did, (tuple, list)) and did and did[0] in owned:
                return did[0]
            if "::" in candidate:
                module = candidate.split("::", 1)[0]
                if (
                    module in owned
                    or module in getattr(program, "module_workflow_signatures", {})
                    or module in getattr(program, "module_externs", {})
                ):
                    return module
        if callable_def is None:
            for table_name in ("workflows", "procedures"):
                for selected in getattr(program, table_name, {}).values():
                    if getattr(getattr(selected, "definition", None), "name", None) == owner:
                        module = Builder._source_module_for(program, owner, selected)
                        if module in owned:
                            return module
            for name, did in local_dids.items():
                if name == owner and isinstance(did, (tuple, list)) and did and did[0] in owned:
                    return did[0]
        return program.entry_module if program.entry_module in owned else next(iter(sorted(owned)))

    def _module_for_owner(self, program: Any, owner: str, callable_def: Any | None = None) -> str:
        return self._source_module_for(program, owner, callable_def)

    def _index_owners(self) -> None:
        for program in self._programs():
            # TypedProgram maps can be flattened views containing imported
            # definitions.  Only source modules listed in this snapshot's
            # source digest table own its bodies and configuration.
            owned_modules = set(getattr(program, "source_file_digests", {}) or ())
            if not owned_modules:
                owned_modules = {program.entry_module}

            for name, workflow in program.workflows.items():
                source_name = getattr(getattr(workflow, "definition", None), "name", name)
                if self._module_for_owner(program, name, workflow) not in owned_modules:
                    continue
                self.workflow_owners.setdefault(name, (workflow, program))
                self.workflow_return_types[source_name] = workflow.signature.return_type_ref
            for name, procedure in program.procedures.items():
                specialization = getattr(procedure, "specialization", None)
                source_name = (
                    getattr(specialization, "base_name", None)
                    or getattr(getattr(procedure, "definition", None), "name", name)
                )
                if self._module_for_owner(program, name, procedure) not in owned_modules:
                    continue
                self.procedure_owners.setdefault(name, (procedure, program))
                if not getattr(procedure.definition, "type_params", ()):
                    self.procedure_return_types[name] = procedure.signature.return_type_ref

    def _workflow_return_types_for(self, source_program: Any, owner: str) -> dict[str, TypeRef]:
        """Return the owner's retained call view, including imported aliases."""

        result = dict(self.workflow_return_types)
        module = self._module_for_owner(source_program, owner)
        signatures = getattr(source_program, "module_workflow_signatures", {}).get(module, {})
        for name, signature in signatures.items():
            result[name] = signature.return_type_ref
        return result

    def _resolve_workflow_target(
        self,
        source_program: Any,
        owner: str,
        target_name: str,
    ) -> tuple[Any, Any, Any] | None:
        module = self._module_for_owner(source_program, owner)
        signatures = getattr(source_program, "module_workflow_signatures", {}).get(module, {})
        caller_signature = signatures.get(target_name)
        imported = getattr(source_program, "imported_programs", {}).get(target_name)
        if caller_signature is not None and imported is not None:
            workflow = getattr(imported, "entry", None)
            if workflow is None:
                workflow = imported.workflows.get(caller_signature.name)
            if workflow is not None:
                return caller_signature, workflow, imported
        target = self.workflow_owners.get(target_name)
        if target is None:
            target = self.workflow_owners.get(f"{module}::{target_name}")
        if target is None:
            return None
        workflow, target_program = target
        if caller_signature is None or caller_signature.name == workflow.signature.name:
            caller_signature = workflow.signature
        return caller_signature, workflow, target_program

    def _workflow_wcc_body(self, workflow: Any, source_program: Any) -> WccBody:
        owner = workflow.definition.name
        cache_key = (id(source_program), owner)
        cached = self._workflow_wcc_cache.get(cache_key)
        if cached is not None:
            return cached
        type_env = source_program.workflow_type_env(owner)
        wcc = elaborate_typed_workflow_body(
            workflow.typed_body,
            owner_name=owner,
            type_env=type_env,
            value_env=dict(workflow.signature.params),
            workflow_return_types=self._workflow_return_types_for(source_program, owner),
            procedure_return_types=self.procedure_return_types,
            resolved_procedures_by_name=source_program.procedures,
            procedure_type_envs=source_program.procedure_type_envs,
            route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
            closed_program=True,
        )
        normalized = normalize_wcc_body_to_anf(wcc)
        self._workflow_wcc_cache[cache_key] = normalized
        return normalized

    @staticmethod
    def _wcc_workflow_calls(body: WccBody) -> list[WccPerform]:
        rows: list[WccPerform] = []
        pending = [body]
        seen: set[int] = set()

        def walk(node: Any) -> None:
            if node is None or id(node) in seen:
                return
            if isinstance(node, WccPerform):
                if node.perform_kind == "workflow_call":
                    rows.append(node)
                return
            if isinstance(node, (str, bytes, int, float, bool, Path)):
                return
            if isinstance(node, Mapping):
                seen.add(id(node))
                for value in node.values():
                    walk(value)
                return
            if isinstance(node, (tuple, list)):
                seen.add(id(node))
                for value in node:
                    walk(value)
                return
            if is_dataclass(node) and not isinstance(node, type):
                seen.add(id(node))
                for field in fields(node):
                    if field.name in {"metadata", "type_ref", "source_span", "form_path", "expansion_stack", "bound_proc_source", "source_binding"}:
                        continue
                    walk(getattr(node, field.name))

        while pending:
            walk(pending.pop())
        return rows

    @staticmethod
    def _context_requirement_matches(left: Any, right: Any) -> bool:
        return (
            getattr(left, "context_kind", None) == getattr(right, "context_kind", None)
            and getattr(left, "phase_name", None) == getattr(right, "phase_name", None)
        )

    def _context_group_matches(self, workflow: Any, source_program: Any, requirement: Any) -> bool:
        facts = getattr(source_program, "_compiled_bundle_boundaries", {}).get(workflow.definition.name)
        if not isinstance(facts, (tuple, list)) or len(facts) < 3:
            return False
        projection = facts[2]
        for group in getattr(projection, "private_runtime_context_bindings", ()):
            if (
                group.context_family == getattr(requirement, "context_kind", None)
                and group.derived_phase_identity == getattr(requirement, "phase_name", None)
                and group.source_param_name == getattr(requirement, "param_name", None)
            ):
                return True
        return False

    def _context_field_pairs(
        self,
        caller_type: TypeRef,
        native_type: TypeRef,
        formal: str,
        native_program: Any,
    ) -> list[list[list[str]]]:
        from orchestrator.workflow.type_descriptor import compiled_boundary_rows

        caller_descriptor = canonical_type_descriptor(caller_type, typed=self.typed)
        native_descriptor = canonical_type_descriptor(native_type, typed=native_program)
        caller_rows = compiled_boundary_rows([(formal, caller_descriptor)])
        native_rows = compiled_boundary_rows([(formal, native_descriptor)])
        caller_by_name = {row["name"]: row for row in caller_rows}
        native_by_name = {row["name"]: row for row in native_rows}
        if not caller_by_name or set(caller_by_name) != set(native_by_name):
            raise ValueError(f"context {formal!r} has no exact complete wire relation")
        pairs = []
        for name in sorted(caller_by_name):
            caller_row = caller_by_name[name]
            native_row = native_by_name[name]
            if caller_row["contract"] != native_row["contract"]:
                raise ValueError(f"context {formal!r} has conflicting wire contracts")
            pairs.append([caller_row["path"][1:], native_row["path"][1:]])
        return sorted(pairs, key=_canonical_json)

    def _context_routes(
        self,
        workflow: Any,
        source_program: Any,
        requirement: Any,
        caller_type: TypeRef,
        *,
        prefix: tuple[list[Any], ...] = (),
        active: frozenset[tuple[int, str]] = frozenset(),
    ) -> list[Any]:
        identity = (id(source_program), workflow.definition.name)
        if identity in active:
            return []
        active = active | {identity}
        body = self._workflow_wcc_body(workflow, source_program)
        occurrence_by_did: dict[str, int] = {}
        routes = []
        for perform in self._wcc_workflow_calls(body):
            target = self._resolve_workflow_target(
                source_program,
                workflow.definition.name,
                perform.target_name,
            )
            if target is None:
                continue
            caller_view, native, native_program = target
            key, _canonical = self._callable_key(native, native_program)
            declaration_id = key[:3]
            did_key = _canonical_json(declaration_id)
            occurrence = occurrence_by_did.get(did_key, 0)
            occurrence_by_did[did_key] = occurrence + 1
            hop = [declaration_id, occurrence]
            explicit = dict(perform.keyword_args)
            native_requirement = next(
                (
                    candidate
                    for candidate in native.signature.hidden_context_requirements.values()
                    if self._context_requirement_matches(candidate, requirement)
                ),
                None,
            )
            if native_requirement is not None:
                formal = native_requirement.param_name
                if formal in explicit:
                    continue
                native_type = dict(native.signature.params).get(formal)
                if native_type is None:
                    raise ValueError(f"hidden context recipient {formal!r} has no native parameter type")
                field_pairs = self._context_field_pairs(
                    caller_type,
                    native_type,
                    formal,
                    native_program,
                )
                routes.append(
                    ["context", [*prefix, hop], formal, field_pairs]
                )
                continue
            if not self._context_group_matches(native, native_program, requirement):
                continue
            child_routes = self._context_routes(
                native,
                native_program,
                requirement,
                caller_type,
                prefix=(*prefix, hop),
                active=active,
            )
            routes.extend(child_routes)
        unique = {_canonical_json(route): route for route in routes}
        return [unique[key] for key in sorted(unique)]

    def _workflow_request(
        self,
        workflow: Any,
        source_program: Any,
        captures: list[CaptureSlot],
    ) -> WorkflowRequest:
        self._require_selected_callable(workflow)
        key = canonical_definition_key(
            workflow,
            typed=self.typed,
            binding_facts={"procedure_references": {}, "workflow_references": {}},
            capture_parameters=[
                {"type": row.type_ref, "routes": row.routes} for row in captures
            ],
            residual_signature=None,
        )
        return WorkflowRequest(
            key=key,
            canonical=canonical_callee_name(workflow, key=key),
            captures=captures,
        )

    def _workflow_call_occurrences(
        self,
        body: WccBody,
        source_program: Any,
        owner: str,
    ) -> dict[int, tuple[list[Any], int]]:
        counts: dict[str, int] = {}
        result = {}
        for perform in self._wcc_workflow_calls(body):
            target = self._resolve_workflow_target(source_program, owner, perform.target_name)
            if target is None:
                continue
            _caller_signature, workflow, target_program = target
            key, _canonical = self._callable_key(workflow, target_program)
            did = key[:3]
            encoded = _canonical_json(did)
            occurrence = counts.get(encoded, 0)
            counts[encoded] = occurrence + 1
            result[id(perform)] = (did, occurrence)
        return result

    def _command_bindings(self, source_program: Any, module_name: str) -> tuple[dict[str, Any], dict[str, str]]:
        config = source_program.configuration_bindings
        supplied = config.get("command_boundaries", {}) if isinstance(config, Mapping) else {}
        if not isinstance(supplied, Mapping):
            supplied = {}
        bindings = dict(supplied)
        used_by_module = config.get("used_command_boundaries", {}) if isinstance(config, Mapping) else {}
        available = used_by_module.get(module_name, {}) if isinstance(used_by_module, Mapping) else {}
        used_names = self._command_names_for_module(source_program, module_name)
        for name in used_names - set(bindings):
            binding = source_program.command_boundaries.get(name)
            if binding is None and isinstance(available, Mapping):
                binding = available.get(name)
            if binding is None:
                raise ValueError(f"used compiler-injected command boundary {name!r} has no retained binding")
            bindings[name] = binding
        origins = dict(source_program.command_boundary_origins)
        used_origins = config.get("used_command_boundary_origins", {}) if isinstance(config, Mapping) else {}
        module_origins = used_origins.get(module_name, {}) if isinstance(used_origins, Mapping) else {}
        if isinstance(module_origins, Mapping):
            origins.update(module_origins)
        origins = {name: origins.get(name, "workspace") for name in bindings}
        return bindings, origins

    def _command_names_for_module(self, source_program: Any, module_name: str) -> set[str]:
        from ..expression_traversal import walk_expr
        from ..expressions import CommandResultExpr

        names: set[str] = set()
        for definitions in (source_program.workflows.values(), source_program.procedures.values()):
            for definition in definitions:
                owner_name = definition.definition.name
                if self._module_for_owner(source_program, owner_name, definition) != module_name:
                    continue
                typed_body = definition.typed_body
                expression = getattr(typed_body, "expr", typed_body)
                for node in walk_expr(expression):
                    if isinstance(node, CommandResultExpr):
                        names.add(node.adapter_name or node.step_name)
        return names

    def configuration_for(self, source_program: Any, owner: str) -> dict[str, Any]:
        owned_modules = getattr(source_program, "source_file_digests", {}) or {}
        module = (
            owner
            if owner in owned_modules
            else self._module_for_owner(source_program, owner)
        )
        cache_key = (id(source_program), module)
        cached = self.configuration_rows.get(cache_key)
        if cached is not None:
            return cached
        bindings, origins = self._command_bindings(source_program, module)
        externs = source_program.module_externs.get(module, {})
        if not externs and module == source_program.entry_module:
            externs = source_program.externs
        row = canonical_configuration(
            bindings,
            origins=origins,
            externs=externs,
            asset_base=logical_asset_base_for_module(module),
        )
        self.configuration_rows[cache_key] = row
        return row

    def command_binding_for(self, source_program: Any, owner: str, boundary: str) -> Any:
        bindings, _ = self._command_bindings(source_program, self._module_for_owner(source_program, owner))
        return bindings.get(boundary)

    def _preflight_closures(self) -> None:
        seen: set[tuple[int, str]] = set()
        for program in self._programs():
            modules = set(getattr(program, "source_file_digests", {}) or ())
            if not modules:
                modules = {program.entry_module}
            for module in sorted(modules):
                key = (id(program), module)
                if key in seen:
                    continue
                seen.add(key)
                bindings, _ = self._command_bindings(program, module)
                require_command_closures(bindings, manifest_path=None)

    def desc(
        self,
        type_ref: TypeRef,
        d: Definition,
        *,
        typed: Any | None = None,
        run_ref_producer: RunRefProducer | None = None,
        run_ref_producers: tuple[RunRefProducer, ...] = (),
    ) -> dict[str, Any]:
        type_program = typed or d.source_program
        producer_context = tuple(
            dict.fromkeys(
                [
                    *(producer for rows in (d.run_ref_names or {}).values() for producer in rows),
                    *([run_ref_producer] if run_ref_producer is not None else []),
                    *run_ref_producers,
                ]
            )
        )
        descriptor = canonical_type_descriptor(type_ref, typed=type_program)
        self.emitted_descriptors.append(
            (descriptor, type_ref, type_program, producer_context, run_ref_producer)
        )
        self._register_types(descriptor)
        return descriptor

    def retain_generated_result_contract(
        self,
        node: dict[str, Any],
        perform: WccPerform,
        d: Definition,
    ) -> None:
        if not self._contains_run_ref(perform.metadata.type_ref):
            return
        producer_context = tuple(
            dict.fromkeys(
                producer
                for rows in (d.run_ref_names or {}).values()
                for producer in rows
            )
        )
        self.generated_result_contract_requests.append((node, perform, d, producer_context))

    def register_run_ref(
        self,
        perform: WccPerform,
        d: Definition,
        node: dict[str, Any],
    ) -> RunRefProducer:
        from .names import _run_ref_signatures

        type_ref = perform.metadata.type_ref
        if not isinstance(getattr(type_ref, "run_ref_origin", None), tuple):
            raise ValueError("run-ref perform has no retained generated type origin")
        projection = _run_ref_signatures(d.source_program)
        signature = projection.signature(type_ref)
        producer_context = tuple(
            dict.fromkeys(
                producer
                for rows in (d.run_ref_names or {}).values()
                for producer in rows
            )
        )
        producer = RunRefProducer(
            perform=perform,
            owner=d.canonical,
            type_ref=type_ref,
            typed=d.source_program,
            node=node,
            signature=signature,
            producer_context=producer_context,
        )
        self.run_ref_producers.append(producer)
        self.run_ref_producers_by_effect[id(node)] = producer
        return producer

    def _run_ref_context_for_value(
        self,
        value: Any,
        d: Definition,
        *,
        seen: set[int] | None = None,
    ) -> tuple[RunRefProducer, ...]:
        from orchestrator.workflow_lisp.wcc.model import (
            WccFieldAccessAtom,
            WccInject,
            WccNameAtom,
            WccOpaqueFrontendValue,
            WccPureOp,
            WccRecordAtom,
            WccSelect,
            WccCall,
        )

        seen = set() if seen is None else seen
        if id(value) in seen:
            return ()
        seen.add(id(value))
        if isinstance(value, WccNameAtom):
            resolved_name = d.resolved_binding_name(
                value.name,
                value.metadata.binding_identity,
            )
            return (d.run_ref_names or {}).get(resolved_name, ())
        if isinstance(value, WccFieldAccessAtom):
            return self._run_ref_context_for_value(value.base, d, seen=seen)
        if isinstance(value, WccOpaqueFrontendValue):
            from ..expression_traversal import free_expr_names

            rows = [
                producer
                for name in free_expr_names(value.expr)
                for producer in (d.run_ref_names or {}).get(name, ())
            ]
            return tuple(dict.fromkeys(rows))
        if isinstance(value, WccCall):
            target_name = value.specialized_callee_name or value.callee_name
            target = self.procedure_owners.get(target_name) or self.procedure_owners.get(value.callee_name)
            if target is None:
                return ()
            procedure, _source_program = target
            result_origins = {
                ref.run_ref_origin[0]
                for ref in self._run_ref_type_refs(value.metadata.type_ref)
            }
            if not result_origins:
                return ()
            rows = []
            for (_formal, parameter_type), argument in zip(
                procedure.signature.params,
                value.args,
                strict=True,
            ):
                parameter_origins = {
                    ref.run_ref_origin[0]
                    for ref in self._run_ref_type_refs(parameter_type)
                }
                if not (result_origins & parameter_origins):
                    continue
                argument_rows = self._run_ref_context_for_value(argument, d, seen=seen)
                rows.extend(
                    producer
                    for producer in argument_rows
                    if producer.type_ref.run_ref_origin[0] in result_origins
                )
            return tuple(dict.fromkeys(rows))
        children = ()
        if isinstance(value, (WccRecordAtom, WccInject)):
            children = tuple(child for _name, child in value.fields)
        elif isinstance(value, WccPureOp):
            children = value.args
        elif isinstance(value, WccSelect):
            children = (
                value.condition,
                *(item for arm in (value.then_arm, value.else_arm) for item in (*arm.prefix, arm.value)),
            )
        rows = [
            producer
            for child in children
            for producer in self._run_ref_context_for_value(child, d, seen=seen)
        ]
        return tuple(dict.fromkeys(rows))

    @staticmethod
    def _run_ref_type_refs(type_ref: Any) -> tuple[Any, ...]:
        from orchestrator.workflow_lisp.type_env import (
            DiscriminantTypeRef,
            ListTypeRef,
            MapTypeRef,
            OptionalTypeRef,
            RecordTypeRef,
            UnionTypeRef,
            VariantCaseTypeRef,
        )

        refs = []
        seen: set[int] = set()

        def visit(ref: Any) -> None:
            if id(ref) in seen:
                return
            seen.add(id(ref))
            if isinstance(ref, RecordTypeRef):
                if isinstance(getattr(ref, "run_ref_origin", None), tuple):
                    refs.append(ref)
                else:
                    for field_type in ref.field_types.values():
                        visit(field_type)
            elif isinstance(ref, (ListTypeRef, OptionalTypeRef)):
                visit(ref.item_type_ref)
            elif isinstance(ref, MapTypeRef):
                visit(ref.key_type_ref)
                visit(ref.value_type_ref)
            elif isinstance(ref, UnionTypeRef):
                for arg in ref.type_args:
                    visit(arg)
                for fields in ref.variant_field_types.values():
                    for field_type in fields.values():
                        visit(field_type)
            elif isinstance(ref, VariantCaseTypeRef):
                for arg in ref.union_type_args:
                    visit(arg)
                for field_type in (ref.field_types or {}).values():
                    visit(field_type)
            elif isinstance(ref, DiscriminantTypeRef):
                return

        visit(type_ref)
        return tuple(refs)

    def _producer_for_type_ref(
        self,
        type_ref: Any,
        producer_context: tuple[RunRefProducer, ...],
        producer_hint: RunRefProducer | None = None,
    ) -> RunRefProducer:
        candidates = list(producer_context)
        if producer_hint is not None and all(producer_hint is not row for row in candidates):
            candidates.append(producer_hint)
        exact = [row for row in candidates if row.type_ref is type_ref]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise ValueError("generated run-ref TypeRef has competing retained producers")
        origin = getattr(type_ref, "run_ref_origin", None)
        if isinstance(origin, tuple) and len(origin) == 2:
            same_origin = [
                row
                for row in candidates
                if isinstance(getattr(row.type_ref, "run_ref_origin", None), tuple)
                and row.type_ref.run_ref_origin[0] == origin[0]
            ]
            if len(same_origin) == 1:
                return same_origin[0]
            if len(same_origin) > 1:
                raise ValueError("generated run-ref origin has competing lexical producers")
        from .names import CanonicalNameError

        raise CanonicalNameError(getattr(type_ref, "name", type(type_ref).__name__))

    def _canonical_descriptor(
        self,
        type_ref: TypeRef,
        typed: Any,
        producer_context: tuple[RunRefProducer, ...],
        producer_hint: RunRefProducer | None = None,
    ) -> dict[str, Any]:
        builder = self

        class ConcreteRunRefNames:
            def __init__(self) -> None:
                from .names import _run_ref_signatures

                self.key_projection = _run_ref_signatures(typed)

            def alias_for(self, ref: Any) -> str:
                producer = builder._producer_for_type_ref(
                    ref,
                    producer_context,
                    producer_hint,
                )
                if producer.generated_name is None:
                    raise ValueError("run-ref producer name was not finalized")
                return producer.generated_name

            def key_type(self, ref: Any) -> dict[str, Any]:
                return self.key_projection.key_type(ref)

        return canonical_type_descriptor(
            type_ref,
            typed=typed,
            _run_ref_projection=ConcreteRunRefNames(),
        )

    def finalize_run_refs(self, tree: dict[str, Any]) -> None:
        if not self.run_ref_producers:
            return
        from base64 import b64encode
        from hashlib import sha256

        from orchestrator.workflow.run_ref.config import (
            ReferenceBinding,
            RunRefInput,
            build_run_ref_static_config,
            encode_run_ref_static_config,
        )
        from orchestrator.workflow.run_ref.contracts import canonical_sha256
        from orchestrator.workflow.run_ref.result_contract import RUN_REF_RESULT_CONTRACT_SCHEMA

        for producer in self.run_ref_producers:
            site = producer.node.get("site")
            if not isinstance(site, str) or not site:
                raise ValueError("run-ref perform has no assigned local site")
            producer.site = site
            digest_input = [
                "workflow-lisp/run-ref-site/1",
                producer.owner,
                site,
                producer.signature,
            ]
            producer.site_digest = sha256(_canonical_json(digest_input).encode("utf-8")).hexdigest()
            producer.generated_name = f"RunRefResult${producer.site_digest[:16]}"

        for descriptor, type_ref, typed, context, hint in self.emitted_descriptors:
            if not self._contains_run_ref(type_ref):
                continue
            rebuilt = self._canonical_descriptor(type_ref, typed, context, hint)
            descriptor.clear()
            descriptor.update(rebuilt)

        self.nominal_types.clear()
        for descriptor, _type_ref, _typed, _context, _hint in self.emitted_descriptors:
            self._register_types(descriptor)

        from .effects import _result_contract

        for node, perform, d, producer_context in self.generated_result_contract_requests:
            contract, source_subjects = _result_contract(
                self,
                perform,
                d,
                descriptor_projector=lambda nested_type: self._canonical_descriptor(
                    nested_type,
                    d.source_program,
                    producer_context,
                ),
            )
            node["contract"] = contract
            provenance = node.get("@")
            if isinstance(provenance, dict):
                if source_subjects:
                    provenance["source_map_subject"] = source_subjects
                else:
                    provenance.pop("source_map_subject", None)

        for request in self.boundary_requests:
            node = request["node"]
            caller_params = request["caller_params"]
            native_params = request["native_params"]
            caller_result = request["caller_result"]
            native_result = request["native_result"]
            direct_count = request["direct_count"]
            if request["initial"]:
                node["boundary"] = self._boundary_relation(
                    caller_params,
                    native_params,
                    caller_result,
                    native_result,
                    direct_capture_count=direct_count,
                )
                continue
            proof = request.get("proof")
            if proof is None:
                continue
            generated = any(self._contains_run_ref(ref) for ref in proof["caller_types"])
            generated = generated or self._contains_run_ref(proof["caller_result_ref"])
            concrete_difference = (
                len(caller_params) != len(native_params)
                or any(left[1] != right[1] for left, right in zip(caller_params, native_params))
                or caller_result != native_result
            )
            if generated and concrete_difference and self._ordinary_generated_signature_boundary(
                caller_types=proof["caller_types"],
                caller_type_scopes=proof["caller_type_scopes"],
                caller_result_ref=proof["caller_result_ref"],
                caller_scope=proof["caller_scope"],
                caller_params=caller_params,
                capture_routes=proof["capture_routes"],
                native_params=native_params,
                native_result=native_result,
                key=proof["key"],
            ):
                node["boundary"] = self._boundary_relation(
                    caller_params,
                    native_params,
                    caller_result,
                    native_result,
                    direct_capture_count=direct_count,
                )

        for producer in self.run_ref_producers:
            payload = producer.perform.operation_payload
            origin = producer.type_ref.run_ref_origin
            input_types = origin[1]
            if len(input_types) != len(producer.node["inputs"]):
                raise ValueError("run-ref typed input rows differ from WCC values")
            input_rows = []
            for (name, input_type), (node_name, _value) in zip(
                input_types,
                producer.node["inputs"],
                strict=True,
            ):
                if node_name != name:
                    raise ValueError("run-ref input names differ from retained ordered TypeRefs")
                input_descriptor = self._canonical_descriptor(
                    input_type,
                    producer.typed,
                    producer.producer_context,
                    None,
                )
                input_rows.append(
                    RunRefInput(
                        name=name,
                        type_descriptor=input_descriptor,
                        binding=ReferenceBinding(f"inputs.{name}"),
                        allow_nested_structures=True,
                    )
                )
                self._register_types(input_descriptor)
            envelope = producer.node["result"]
            result_descriptor = {
                "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
                "envelope": envelope,
            }
            result_digest = canonical_sha256(result_descriptor)
            if self.compiler_runtime_identity is None:
                from orchestrator.workflow.run_ref.contracts import compute_compiler_runtime_identity

                self.compiler_runtime_identity = compute_compiler_runtime_identity().digest
            config = build_run_ref_static_config(
                compiler_runtime_identity_digest=self.compiler_runtime_identity,
                site_digest=producer.site_digest,
                source=payload.source,
                program=payload.program,
                inputs=tuple(input_rows),
                result_descriptor=result_descriptor,
                result_digest=result_digest,
                target_dsl_version=EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
            )
            producer.node["config"] = b64encode(encode_run_ref_static_config(config)).decode("ascii")
            self._register_types(envelope)

    @staticmethod
    def _contains_run_ref(type_ref: Any) -> bool:
        return bool(Builder._run_ref_type_refs(type_ref))

    def _register_types(self, descriptor: dict[str, Any]) -> None:
        kind = descriptor.get("kind")
        if kind in {"record", "union", "enum", "path"}:
            name = descriptor.get("name")
            if isinstance(name, str):
                previous = self.nominal_types.get(name)
                if previous is not None and _canonical_json(previous) != _canonical_json(descriptor):
                    raise ValueError(f"canonical type {name!r} has conflicting definitions")
                self.nominal_types[name] = descriptor
        if kind in {"optional", "list"}:
            self._register_types(descriptor["item"])
        elif kind == "map":
            self._register_types(descriptor["key"])
            self._register_types(descriptor["value"])
        elif kind in {"record", "variant_case"}:
            for field in descriptor.get("fields", ()):
                self._register_types(field["type"])
        elif kind == "union":
            for variant in descriptor.get("variants", ()):
                for field in variant.get("fields", ()):
                    self._register_types(field["type"])

    @staticmethod
    def provenance(source: Any) -> dict[str, Any]:
        metadata = getattr(source, "metadata", source)
        span = getattr(metadata, "source_span", getattr(metadata, "span", None))
        form_path = getattr(metadata, "form_path", ())
        start = getattr(span, "start", None)
        if start is None:
            return {}
        return {"@": {"span": f"{start.path}:{start.line}:{start.column}", "form": list(form_path)}}

    def gap(self, form: str, message: str, node: Any | None = None) -> ClosedProgramGap:
        metadata = getattr(node, "metadata", node)
        return ClosedProgramGap(
            form,
            message,
            span=getattr(metadata, "source_span", getattr(metadata, "span", None)),
            form_path=getattr(metadata, "form_path", ()),
        )

    def _selected_callable_gap(self, callable_def: Any) -> ClosedProgramGap | None:
        """Return a located gap that must be reported before key construction.

        Some admitted result types are generated from effects that this release
        does not translate. Inspect only the retained body of the callable
        selected for emission, and leave local procedure bodies for the point
        where a call selects them.
        """

        from ..expression_traversal import iter_child_exprs
        from ..expressions import LetProcExpr, ProviderResultExpr, TrialExpr

        typed_body = getattr(callable_def, "typed_body", None)
        expression = getattr(typed_body, "expr", typed_body)
        if expression is None:
            return None
        pending = [expression]
        while pending:
            node = pending.pop()
            if isinstance(node, TrialExpr):
                return self.gap("trial", "trial execution is outside the closed surface", node)
            if isinstance(node, ProviderResultExpr):
                if node.session_artifact is not None:
                    return self.gap(
                        "provider-result",
                        "provider session artifacts are outside the closed provider surface",
                        node,
                    )
                if node.context_expr is not None or node.capture_context is not None:
                    return self.gap(
                        "provider-result",
                        "provider context capture is outside the closed provider surface",
                        node,
                    )
                if node.materialization_attempts is not None:
                    return self.gap(
                        "provider-result",
                        "provider materialization attempts are outside the closed provider surface",
                        node,
                    )
            if isinstance(node, LetProcExpr):
                pending.append(node.body)
                continue
            pending.extend(reversed(iter_child_exprs(node)))
        return None

    def _require_selected_callable(self, callable_def: Any) -> None:
        gap = self._selected_callable_gap(callable_def)
        if gap is not None:
            raise gap

    def _renamer(self, node: Any, params: Any = ()) -> Renamer:
        reserved = {label for label in _authored_labels(node) if label is not None}
        for param in params:
            label = getattr(param, "binding_label", None)
            if label is not None:
                reserved.add(label)
        return Renamer(reserved_names=tuple(sorted(reserved)))

    def definition_context(
        self,
        *,
        canonical: str,
        owner: str,
        source_program: Any,
        type_env: Any,
        node: Any,
        params: Any = (),
        callable_def: Any | None = None,
        configuration_selector: str | None = None,
    ) -> Definition:
        module = self._module_for_owner(source_program, owner, callable_def)
        externs = source_program.module_externs.get(module, {})
        return Definition(
            canonical=canonical,
            owner=owner,
            source_program=source_program,
            type_env=type_env,
            externs=externs,
            renamer=self._renamer(node, params),
            names={},
            loops=[],
            callable_definition=callable_def,
            configuration_selector=configuration_selector,
        )

    def bind(self, d: Definition, name: str, *, label: str | None) -> tuple[Definition, str]:
        local = dict(d.names)
        wire_name = d.renamer.bind(name, authored_label=label, env=local)
        return d.with_names(local), wire_name

    def _freeze_bound_capture(
        self,
        d: Definition,
        identity: object | None,
        wire_name: str,
        run_ref_producers: tuple[RunRefProducer, ...] = (),
    ) -> tuple[Definition, list[dict[str, Any]]]:
        if identity is None or identity not in d.capture_binding_identities:
            return d, []
        names = dict(d.names)
        binding_aliases = dict(d.binding_aliases or {})
        internal_name = f"\0lexical-capture:{len(binding_aliases) + 1}"
        alias_wire = d.renamer.bind(
            internal_name,
            authored_label=None,
            env=names,
        )
        binding_aliases[identity] = internal_name
        run_ref_names = dict(d.run_ref_names or {})
        if run_ref_producers:
            run_ref_names[internal_name] = run_ref_producers
        return (
            d.with_names(
                names,
                binding_aliases=binding_aliases,
                run_ref_names=run_ref_names,
            ),
            [{"k": "let", "name": alias_wire, "value": {"k": "name", "n": wire_name}}],
        )

    def _freeze_parameter_captures(
        self,
        d: Definition,
        typed_body: Any,
        params: Any,
    ) -> tuple[Definition, list[dict[str, Any]]]:
        """Pin retained incoming binders before same-spelling body lets shadow them."""

        if not d.capture_binding_identities:
            return d, []
        retained = getattr(typed_body, "binding_environment", {}) or {}
        current = d
        prefix: list[dict[str, Any]] = []
        for param in params:
            identity = retained.get(param.name)
            if identity not in current.capture_binding_identities:
                continue
            source_wire = current.names.get(param.name)
            if source_wire is None:
                # Erased private inputs are supplied by the entry-context
                # wrapper, so their lexical owner is installed there instead.
                continue
            current, rows = self._freeze_bound_capture(
                current,
                identity,
                source_wire,
                (current.run_ref_names or {}).get(param.name, ()),
            )
            prefix.extend(rows)
        return current, prefix

    def value(self, value: Any, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        return _located_value(value, self, d, env)

    def body(self, node: WccBody, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        return _located_body(node, self, d, env)

    def _body_impl(self, node: WccBody, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        lets = []
        names = dict(d.names)
        run_ref_names = dict(d.run_ref_names or {})
        binding_aliases = dict(d.binding_aliases or {})
        types = dict(env)
        while isinstance(node, WccLet):
            current = d.with_names(
                names,
                binding_aliases=binding_aliases,
                run_ref_names=run_ref_names,
            )
            value = self.binding(node.bound_value, current, types)
            nested_names = dict(names)
            wire_name = d.renamer.bind(
                node.bound_name,
                authored_label=node.metadata.binding_label,
                env=nested_names,
            )
            row = {"k": "let", "name": wire_name, "value": value}
            if node.metadata.binding_label is not None:
                row["label"] = node.metadata.binding_label
            row.update(self.provenance(node.metadata))
            lets.append(row)
            names = nested_names
            types[node.bound_name] = node.bound_type_ref
            producer = self.run_ref_producers_by_effect.get(id(value))
            if producer is None and isinstance(node.bound_value, WccNameAtom):
                resolved_name = current.resolved_binding_name(
                    node.bound_value.name,
                    node.bound_value.metadata.binding_identity,
                )
                producers = run_ref_names.get(resolved_name, ())
            elif producer is not None:
                producers = (producer,)
            else:
                producers = self._run_ref_context_for_value(node.bound_value, current)
            if producers:
                run_ref_names[node.bound_name] = producers
            identity = node.metadata.binding_identity
            if identity is not None and identity in d.capture_binding_identities:
                current = d.with_names(
                    names,
                    binding_aliases=binding_aliases,
                    run_ref_names=run_ref_names,
                )
                current, alias_prefix = self._freeze_bound_capture(
                    current,
                    identity,
                    wire_name,
                    producers,
                )
                names = dict(current.names)
                binding_aliases = dict(current.binding_aliases or {})
                run_ref_names = dict(current.run_ref_names or {})
                lets.extend(alias_prefix)
            for request in (d.computed_capture_requests_by_alias or {}).get(node.bound_name, ()):
                rewritten = dict(names)
                for source_name, alias_name in request.source_aliases.items():
                    if alias_name not in names:
                        raise ValueError(
                            f"computed capture source {source_name!r} is not bound at its creation region"
                        )
                    rewritten[source_name] = names[alias_name]
                from .values import frontend_value

                expression_value = frontend_value(
                    self,
                    request.expression,
                    d.with_names(
                        rewritten,
                        binding_aliases=binding_aliases,
                        run_ref_names=run_ref_names,
                    ),
                    types,
                )
                source_names = dict(names)
                wire_name = d.renamer.bind(
                    request.source_name,
                    authored_label=None,
                    env=source_names,
                )
                computed_row = {"k": "let", "name": wire_name, "value": expression_value}
                computed_row.update(self.provenance(request.expression))
                lets.append(computed_row)
                names = source_names
                types[request.source_name] = request.type_ref
            node = node.body
        tail = self.tail(
            node,
            d.with_names(
                names,
                binding_aliases=binding_aliases,
                run_ref_names=run_ref_names,
            ),
            types,
        )
        for row in reversed(lets):
            row["body"] = tail
            tail = row
        return tail

    def tail(self, node: Any, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        if isinstance(node, WccHalt):
            result = {"k": "halt", "value": self.value(node.result, d, env)}
        elif isinstance(node, WccLoopDone):
            result = {"k": "done", "value": self.value(node.result, d, env)}
        elif isinstance(node, WccIf):
            result = {
                "k": "if",
                "cond": self.value(node.condition, d, env),
                "then": self.body(node.then_body, d.with_names(dict(d.names)), dict(env)),
                "else": self.body(node.else_body, d.with_names(dict(d.names)), dict(env)),
            }
        elif isinstance(node, WccCase):
            arms = []
            subject = self.value(node.subject, d, env)
            for arm in node.arms:
                local, binder = self.bind(d, arm.binding_name, label=arm.binding_label)
                arm_env = dict(env)
                arm_env[arm.binding_name] = arm.binding_type_ref
                arm_local, alias_prefix = self._freeze_bound_capture(
                    local,
                    arm.binding_identity,
                    binder,
                    self._run_ref_context_for_value(node.subject, d),
                )
                arm_body = self.body(arm.body, arm_local, arm_env)
                arm_body = _prepend_lets(arm_body, alias_prefix)
                arms.append(
                    {
                        "variant": arm.variant_name,
                        "bind": binder,
                        "body": arm_body,
                    }
                )
            result = {"k": "case", "subject": subject, "arms": arms}
        elif isinstance(node, WccJoin):
            result = self._join(node, d, env)
        elif isinstance(node, WccJump):
            if node.join_name not in d.names:
                raise ValueError(f"WCC jump names an unbound join {node.join_name!r}")
            result = {
                "k": "jump",
                "join": d.ref(node.join_name),
                "args": [self.value(arg, d, env) for arg in node.args],
            }
        elif isinstance(node, WccLoopContinue):
            if not d.loops or node.target_name != d.loops[-1][0]:
                raise ValueError("WCC continue does not name its innermost loop")
            result = {
                "k": "continue",
                "loop": d.loops[-1][1],
                "args": [self.value(arg, d, env) for arg in node.state_args],
            }
        elif isinstance(node, WccRecJoin):
            result = self._loop(node, d, env)
        else:
            raise ValueError(f"WCC body {type(node).__name__} has no closed translation")
        return {**result, **self.provenance(node)}

    def _join(self, node: WccJoin, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        if len(node.params) != 1:
            raise ValueError("closed join requires exactly one result parameter")
        target_local, target = self.bind(d, node.join_name, label=None)
        param = node.params[0]
        cont_local, param_wire = self.bind(target_local, param.name, label=node.metadata.binding_label)
        body = self.body(node.body, target_local, dict(env))
        continuation_env = dict(env)
        continuation_env[param.name] = param.type_ref
        continuation_local, alias_prefix = self._freeze_bound_capture(
            cont_local,
            node.metadata.binding_identity,
            param_wire,
            self._run_ref_context_for_value(node.body, d),
        )
        continuation = self.body(node.continuation, continuation_local, continuation_env)
        continuation = _prepend_lets(continuation, alias_prefix)
        result = {
            "k": "join",
            "name": target,
            "params": [[param_wire, self.desc(param.type_ref, d)]],
            "result": self.desc(param.type_ref, d),
            "body": body,
            "cont": continuation,
        }
        if node.metadata.binding_label is not None:
            result["label"] = node.metadata.binding_label
        return result

    def _loop(self, node: WccRecJoin, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        if len(node.params) != 1 or node.initial_state is None:
            raise ValueError("closed loop requires one state parameter and an initial state")
        budget = self.value(node.budget, d, env)
        initial = self.value(node.initial_state, d, env)
        loop_local, loop_wire = self.bind(d, node.loop_name, label=None)
        param = node.params[0]
        body_local, param_wire = self.bind(loop_local, param.name, label=node.metadata.binding_label)
        loop_env = dict(env)
        loop_env[param.name] = param.type_ref
        post_param_local = body_local
        body_local, alias_prefix = self._freeze_bound_capture(
            body_local,
            node.metadata.binding_identity,
            param_wire,
            self._run_ref_context_for_value(node.initial_state, d),
        )
        d.loops.append((node.loop_name, loop_wire))
        try:
            body = self.body(node.body, body_local, loop_env)
            body = _prepend_lets(body, alias_prefix)
        finally:
            d.loops.pop()
        exhausted = None
        if node.exhaustion is not None:
            exhausted_local, exhausted_prefix = self._freeze_bound_capture(
                post_param_local.with_names(dict(post_param_local.names)),
                node.metadata.binding_identity,
                param_wire,
                self._run_ref_context_for_value(node.initial_state, d),
            )
            exhausted = self.body(node.exhaustion, exhausted_local, dict(loop_env))
            exhausted = _prepend_lets(exhausted, exhausted_prefix)
        result_type = self.desc(node.metadata.type_ref, d)
        state_type = self.desc(param.type_ref, d)
        result = {
            "k": "loop",
            "name": loop_wire,
            "param": param_wire,
            "state_type": state_type,
            "result": result_type,
            "budget": budget,
            "init": initial,
            "body": body,
            "exhausted": exhausted,
            "code": node.exhaustion_diagnostic_code,
        }
        if node.metadata.binding_label is not None:
            result["label"] = node.metadata.binding_label
        return result

    def binding(self, value: Any, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        return _located_binding(value, self, d, env)

    def _binding_impl(self, value: Any, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        if isinstance(value, WccPerform):
            if value.perform_kind == "workflow_call":
                return self.workflow_call(value, d, env)
            return translate_perform(self, value, d, env)
        if isinstance(value, WccCall):
            return self.call(value, d, env)
        if isinstance(value, WccProviderSupervision):
            raise self.gap(
                "with-live-providers",
                "provider supervision has no closed form in this release",
                value,
            )
        if isinstance(value, WccProviderPeerGroup):
            raise self.gap(
                "with-live-provider-peers",
                "provider peer groups have no closed form in this release",
                value,
            )
        return self.value(value, d, env)

    def _procedure(self, name: str) -> tuple[Any, Any] | None:
        return self.procedure_owners.get(name)

    def _selected_ref_procedure(self, resolved: Any, source_program: Any) -> Any | None:
        selected = source_program.procedures.get(getattr(resolved, "call_target_name", ""))
        if selected is not None:
            return selected
        return self.procedure_owners.get(getattr(resolved, "call_target_name", ""), (None, None))[0]

    @staticmethod
    def _local_definition_row(callable_def: Any, source_program: Any) -> Any | None:
        keys = getattr(source_program, "local_definition_keys", {})
        names = [getattr(getattr(callable_def, "definition", None), "name", None)]
        specialization = getattr(callable_def, "specialization", None)
        names.extend(
            [getattr(specialization, "specialized_name", None), getattr(specialization, "base_name", None)]
        )
        for name in names:
            if name is not None and name in keys:
                return keys[name]
        return None

    def _local_capture(self, resolved: Any, source_program: Any, formal: str) -> tuple[int, str] | None:
        selected = self._selected_ref_procedure(resolved, source_program)
        row = self._local_definition_row(selected, source_program) if selected is not None else None
        if row is None:
            for name in (getattr(resolved, "call_target_name", None), getattr(resolved, "procedure_name", None)):
                row = getattr(source_program, "local_definition_keys", {}).get(name)
                if row is not None:
                    break
        if row is None or len(row) < 4:
            return None
        for index, capture in enumerate(row[3]):
            if capture[0] == formal:
                return index, capture[0]
        return None

    def _local_capture_name(self, resolved: Any, source_program: Any, index: int) -> str:
        selected = self._selected_ref_procedure(resolved, source_program)
        row = self._local_definition_row(selected, source_program) if selected is not None else None
        if row is None:
            for name in (getattr(resolved, "call_target_name", None), getattr(resolved, "procedure_name", None)):
                row = getattr(source_program, "local_definition_keys", {}).get(name)
                if row is not None:
                    break
        if row is None or len(row) < 4 or index < 0 or index >= len(row[3]):
            raise ValueError(f"retained local capture index {index} has no source owner")
        return row[3][index][0]

    def _closed_bound_value(
        self,
        expr: Any,
        type_ref: TypeRef,
        d: Definition,
        *,
        typed: Any | None = None,
    ) -> dict[str, Any] | None:
        from ..expressions import LiteralExpr

        if isinstance(expr, LiteralExpr):
            return {
                "k": "lit",
                "v": expr.value,
                "type": canonical_type_descriptor(type_ref, typed=typed or d.source_program),
            }
        return None

    def _add_capture(
        self,
        captures: list[CaptureSlot],
        *,
        typed: Any,
        type_ref: TypeRef,
        route: Any,
        value: Any,
        source_name: str | None,
        identity: Any,
        run_ref_producers: tuple[RunRefProducer, ...] = (),
    ) -> int:
        descriptor = canonical_type_descriptor(type_ref, typed=typed)
        for index, capture in enumerate(captures):
            if (
                capture.identity == identity
                and canonical_type_descriptor(
                    capture.type_ref,
                    typed=capture.type_program or typed,
                ) == descriptor
            ):
                if route not in capture.routes:
                    capture.routes.append(route)
                if capture.run_ref_producers != run_ref_producers:
                    raise ValueError("one retained capture route has competing run-ref producers")
                return index
        captures.append(
            CaptureSlot(
                type_ref=type_ref,
                routes=[route],
                value=value,
                source_name=source_name,
                identity=identity,
                type_program=typed,
                run_ref_producers=run_ref_producers,
            )
        )
        return len(captures) - 1

    def _reference_facts(
        self,
        resolved: Any,
        *,
        path: list[str],
        aliases: Mapping[str, Any],
        captures: list[CaptureSlot],
        d: Definition,
        source_program: Any,
    ) -> dict[str, Any]:
        from ..expression_traversal import free_expr_names
        from ..expressions import NameExpr

        selected = self._selected_ref_procedure(resolved, source_program)
        selected_refs = dict(getattr(getattr(selected, "specialization", None), "proc_ref_bindings", {}) or {})
        bound_args = {argument.name: argument for argument in resolved.bound_args}
        facts: dict[str, Any] = {}
        for formal, _ in resolved.signature_params:
            argument = bound_args.get(formal)
            if argument is None:
                continue
            if isinstance(argument.type_ref, ProcRefTypeRef):
                nested = selected_refs.get(formal)
                if nested is None and hasattr(argument.value_expr, "bound_args"):
                    nested = argument.value_expr
                if nested is None:
                    raise ValueError(f"retained nested procedure reference {formal!r} is unavailable")
                facts[formal] = {"procedure": self._reference_facts(
                    nested,
                    path=[*path, formal],
                    aliases=aliases,
                    captures=captures,
                    d=d,
                    source_program=source_program,
                )}
                continue
            closed = self._closed_bound_value(
                argument.value_expr,
                argument.type_ref,
                d,
                typed=source_program,
            )
            if closed is not None:
                facts[formal] = {"value": closed}
                continue
            local_capture = self._local_capture(resolved, source_program, formal)
            if local_capture is not None:
                local_index, capture_name = local_capture
                route = ["reference", list(path), ["local", local_index]]
                forwarded = [
                    index
                    for index, outer in enumerate(d.captures or ())
                    if route in outer.routes
                ]
                if len(forwarded) > 1:
                    raise ValueError(f"local capture route {route!r} has competing enclosing values")
                if forwarded:
                    outer_index = forwarded[0]
                    source_name = (d.capture_names or ())[outer_index]
                    actual = {"k": "name", "n": d.ref(source_name)}
                    actual_identity = ("forwarded-local", id(d.captures[outer_index]), local_index)
                else:
                    binding_identity = getattr(argument, "source_binding_identity", None)
                    bound_alias = (d.binding_aliases or {}).get(binding_identity)
                    if bound_alias is not None:
                        source_name = bound_alias
                        actual = {"k": "name", "n": d.ref(bound_alias)}
                        actual_identity = ("local-binding", binding_identity)
                    else:
                        if (
                            binding_identity is not None
                            and binding_identity in d.capture_binding_identities
                        ):
                            raise ValueError(
                                f"retained local capture binder {binding_identity!r} has no lexical WCC owner"
                            )
                        from ..expressions import NameExpr

                        bound_source = (
                            argument.value_expr.name
                            if isinstance(argument.value_expr, NameExpr)
                            else capture_name
                        )
                        alias = aliases.get(bound_source)
                        if alias is not None and isinstance(alias[1], WccNameAtom):
                            source_name = alias[1].name
                        else:
                            source_name = bound_source
                        actual = {"k": "name", "n": d.ref(source_name)}
                        actual_identity = ("local", id(resolved), local_index, source_name)
                index = self._add_capture(
                    captures,
                    typed=source_program,
                    type_ref=argument.type_ref,
                    route=route,
                    value=actual,
                    source_name=source_name,
                    identity=actual_identity,
                    run_ref_producers=tuple((d.run_ref_names or {}).get(source_name, ())),
                )
                facts[formal] = {"capture": index}
                continue
            bound_alias = (d.reference_capture_aliases or {}).get(
                (id(argument.value_expr), formal)
            )
            if bound_alias is not None:
                route = ["reference", list(path), ["parameter", formal]]
                actual = {"k": "name", "n": d.ref(bound_alias)}
                index = self._add_capture(
                    captures,
                    typed=source_program,
                    type_ref=argument.type_ref,
                    route=route,
                    value=actual,
                    source_name=bound_alias,
                    identity=("bind-proc-expression", id(argument.value_expr), formal),
                    run_ref_producers=tuple((d.run_ref_names or {}).get(bound_alias, ())),
                )
                facts[formal] = {"capture": index}
                continue
            if isinstance(argument.value_expr, NameExpr):
                actual = aliases.get(argument.value_expr.name)
                alias_identity = None
                if isinstance(actual, tuple) and len(actual) == 2:
                    argument_index, actual = actual
                    alias_identity = ("argument", argument_index, id(actual))
                if actual is None:
                    # A retained lexical name can be used directly when the
                    # frontend did not need an alias let for this boundary.
                    actual = {"k": "name", "n": d.ref(argument.value_expr.name)}
                    alias_identity = None
                source_name = (
                    actual.name if isinstance(actual, WccNameAtom)
                    else argument.value_expr.name
                )
                route = ["reference", list(path), ["parameter", formal]]
                index = self._add_capture(
                    captures,
                    typed=source_program,
                    type_ref=argument.type_ref,
                    route=route,
                    value=actual,
                    source_name=source_name,
                    identity=alias_identity,
                    run_ref_producers=self._run_ref_context_for_value(actual, d)
                    or tuple((d.run_ref_names or {}).get(source_name, ())),
                )
                facts[formal] = {"capture": index}
                continue
            names = free_expr_names(argument.value_expr)
            if names:
                source_name = (d.computed_capture_sources or {}).get(
                    (id(argument.value_expr), formal)
                )
                if source_name is None:
                    raise ValueError(
                        f"computed bound procedure argument {formal!r} has no retained creation binding"
                    )
                route = ["reference", list(path), ["parameter", formal]]
                actual = ComputedCaptureValue(source_name)
                index = self._add_capture(
                    captures,
                    typed=source_program,
                    type_ref=argument.type_ref,
                    route=route,
                    value=actual,
                    source_name=source_name,
                    identity=("bind-proc-expression", id(argument.value_expr), formal),
                    run_ref_producers=tuple((d.run_ref_names or {}).get(source_name, ())),
                )
                facts[formal] = {"capture": index}
                continue
            from ..conditionals import _contains_effect

            if not _contains_effect(argument.value_expr):
                from .values import frontend_value

                closed = _strip_provenance(
                    frontend_value(self, argument.value_expr, d, env={})
                )
                facts[formal] = {"value": closed}
                continue
            raise ValueError(
                f"bound procedure argument {formal!r} is neither a checked closed value nor a retained lexical capture"
            )
        return {"bound": facts}

    def _workflow_reference_facts(self, resolved: Any, source_program: Any) -> dict[str, Any]:
        """Project only the exact extern rows retained by this WRef plan."""
        plan = resolved.extern_rebinding_plan
        if plan.is_empty:
            return {"externs": {"providers": {}, "prompts": {}}}
        target = self.workflow_owners.get(resolved.workflow_name)
        if target is None:
            raise ValueError(
                f"resolved workflow reference target {resolved.workflow_name!r} has no retained typed owner"
            )
        workflow, target_program = target
        module = self._module_for_owner(target_program, resolved.workflow_name, workflow)
        from .program import canonical_extern_configuration

        projected = canonical_extern_configuration(
            getattr(target_program, "module_externs", {}).get(module, {}),
            asset_base=logical_asset_base_for_module(module),
        )
        rows: dict[str, dict[str, Any]] = {"providers": {}, "prompts": {}}
        for category in ("providers", "prompts"):
            planned = getattr(plan, f"{category[:-1]}_bindings")
            for formal, sources in planned.items():
                if len(sources) != 1:
                    raise ValueError(
                        f"workflow reference extern {category[:-1]} {formal!r} has no exact single retained binding"
                    )
                source = sources[0]
                row = projected[category].get(source)
                if row is None:
                    raise ValueError(
                        f"workflow reference extern {category[:-1]} {formal!r} has no retained owner row"
                    )
                rows[category][formal] = row
        return {"externs": rows}

    def _call_request(self, procedure: Any, source_program: Any, call: WccCall, d: Definition) -> CallableRequest:
        from ..expression_traversal import free_expr_names, walk_expr
        from ..expressions import BindProcExpr, LetStarExpr, LiteralExpr, NameExpr

        self._require_selected_callable(procedure)
        specialization = getattr(procedure, "specialization", None)
        base_name = getattr(specialization, "base_name", None)
        base_owner = self.procedure_owners.get(base_name) if base_name is not None else None
        base = base_owner[0] if base_owner is not None else procedure
        proc_refs = dict(getattr(specialization, "proc_ref_bindings", {}) or {})
        workflow_refs = dict(getattr(specialization, "workflow_ref_bindings", {}) or {})
        capture_aliases: dict[int, dict[str, Any]] = {}
        for capture in call.specialization_captures:
            if capture.owner_kind == "argument" and capture.argument_index is not None:
                capture_aliases.setdefault(capture.argument_index, {})[capture.source_name] = (
                    capture.argument_index,
                    capture.value,
                )

        captures: list[CaptureSlot] = []
        ref_facts: dict[str, Any] = {}
        for argument_index, (formal, _) in enumerate(base.signature.params):
            resolved = proc_refs.get(formal)
            if resolved is None:
                continue
            ref_facts[formal] = self._reference_facts(
                resolved,
                path=[formal],
                aliases=capture_aliases.get(argument_index, {}),
                captures=captures,
                d=d,
                source_program=source_program,
            )
        procedure_view = procedure
        closed_values: dict[str, Any] = {}
        runtime_formals: set[str] = set()
        if specialization is not None:
            callee_owners: list[tuple[BindProcExpr, tuple[Any, ...]]] = []
            if isinstance(call.bound_proc_source, BindProcExpr):
                callee_owners.append((call.bound_proc_source, ()))
            for owner, owner_rows in _capture_owner_groups(
                call.specialization_captures,
                owner_kind="callee",
            ):
                existing = next(
                    (index for index, (candidate, _rows) in enumerate(callee_owners) if candidate is owner),
                    None,
                )
                if existing is None:
                    callee_owners.append((owner, owner_rows))
                else:
                    callee_owners[existing] = (owner, owner_rows)
            for bind_source, owner_rows in callee_owners:
                aliases_by_name: dict[str, list[WccNameAtom]] = {}
                for capture in owner_rows:
                    if isinstance(capture.value, WccNameAtom):
                        aliases_by_name.setdefault(capture.source_name, []).append(capture.value)
                for binding in bind_source.bindings:
                    formal = binding.name
                    expression = binding.value_expr
                    if formal not in specialization.value_bindings:
                        continue
                    type_ref = specialization.bound_param_types.get(formal)
                    if type_ref is None:
                        raise ValueError(f"retained bind-proc value {formal!r} has no type fact")
                    if isinstance(type_ref, ProcRefTypeRef):
                        continue
                    if isinstance(expression, LiteralExpr):
                        closed_values[formal] = self._closed_bound_value(
                            expression, type_ref, d, typed=source_program
                        )
                        continue
                    free_names = free_expr_names(expression)
                    route = ["parameter", formal]
                    identity = ("bind-proc", id(bind_source), formal)
                    if isinstance(expression, NameExpr):
                        aliases = aliases_by_name.get(expression.name, ())
                        if len(aliases) > 1:
                            raise ValueError(f"bind-proc capture {expression.name!r} has ambiguous WCC aliases")
                        actual: Any = aliases[0] if aliases else {"k": "name", "n": d.ref(expression.name)}
                        source_name = actual.name if isinstance(actual, WccNameAtom) else expression.name
                    elif free_names:
                        source_name = (d.computed_capture_sources or {}).get(
                            (id(bind_source), (formal,))
                        )
                        if source_name is None:
                            raise ValueError(f"computed bind-proc capture {formal!r} has no lexical creation binding")
                        actual = ComputedCaptureValue(source_name)
                    else:
                        from .values import frontend_value

                        actual = _strip_provenance(
                            frontend_value(self, expression, d, env={})
                        )
                        closed_values[formal] = {"type": type_ref, "value": actual}
                        continue
                    self._add_capture(
                        captures,
                        typed=source_program,
                        type_ref=type_ref,
                        route=route,
                        value=actual,
                        source_name=source_name,
                        identity=identity,
                        run_ref_producers=self._run_ref_context_for_value(actual, d),
                    )
                    runtime_formals.add(formal)
            if runtime_formals:
                retained_values = {
                    name: value
                    for name, value in specialization.value_bindings.items()
                    if name not in runtime_formals
                }
                procedure_view = replace(
                    procedure,
                    specialization=replace(specialization, value_bindings=retained_values),
                )
        workflow_facts = {
            formal: self._workflow_reference_facts(resolved, source_program)
            for formal, resolved in workflow_refs.items()
        }
        # Workflow reference routes use their retained selected facts. They do
        # not contribute ordinary procedure-call capture rows here.
        binding_facts = {
            "procedure_references": ref_facts,
            "workflow_references": workflow_facts,
            "closed_values": closed_values,
        }
        key = canonical_definition_key(
            procedure_view,
            typed=source_program,
            binding_facts=binding_facts,
            capture_parameters=[{"type": row.type_ref, "routes": row.routes} for row in captures],
            residual_signature=None,
        )
        argument_run_ref_producers: dict[str, tuple[RunRefProducer, ...]] = {}
        parameters = tuple(getattr(procedure_view.signature, "params", ()))
        if len(parameters) != len(call.args):
            if any(self._run_ref_context_for_value(argument, d) for argument in call.args):
                raise ValueError("run-ref call arguments have no aligned retained parameter owner")
        else:
            argument_run_ref_producers = {
                formal: self._run_ref_context_for_value(argument, d)
                for (formal, _type_ref), argument in zip(parameters, call.args, strict=True)
            }
        return CallableRequest(
            key=key,
            canonical=canonical_callee_name(procedure_view, key=key),
            captures=captures,
            procedure_refs=proc_refs,
            procedure_ref_keys={str(row[0]): row[1] for row in key[4]},
            workflow_refs=workflow_refs,
            workflow_ref_keys={str(row[0]): row[1] for row in key[5]},
            procedure=procedure_view,
            argument_run_ref_producers=argument_run_ref_producers,
        )

    @staticmethod
    def _capture_source(index: int) -> str:
        # NUL cannot occur in source identifiers, so this is an unambiguous
        # internal lexical key. It is never serialized or inferred later.
        return f"\0capture:{index}"

    def call(self, call: WccCall, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        if d.procedure_refs is not None and call.callee_name in d.procedure_refs:
            return self._reference_call(call, d, env, call.callee_name)
        target_name = call.specialized_callee_name or call.callee_name
        target = self.procedure_owners.get(target_name)
        if target is None:
            target = self.procedure_owners.get(call.callee_name)
        if target is None:
            raise ValueError(f"WCC procedure call {target_name!r} has no retained typed owner")
        procedure, source_program = target
        request = self._call_request(procedure, source_program, call, d)
        key, canonical = request.key, request.canonical
        args = [
            {"k": "name", "n": d.ref(row.value.source_name)}
            if isinstance(row.value, ComputedCaptureValue)
            else dict(row.value)
            if isinstance(row.value, Mapping)
            else self.value(row.value, d, env)
            for row in request.captures
        ]
        args.extend(self.value(argument, d, env) for argument in call.args)
        if canonical in self.active:
            raise self.gap("call", f"recursive call of {canonical!r}", call)
        if canonical not in self.definitions:
            self._build_procedure(request.procedure or procedure, source_program, key, canonical, request=request)
        definition = self.definitions[canonical]
        key = definition["key"]
        native_params = definition["params"]
        caller_types = [capture.type_ref for capture in request.captures]
        caller_type_scopes = [capture.type_program or d.source_program for capture in request.captures]
        caller_types.extend(argument.metadata.type_ref for argument in call.args)
        caller_type_scopes.extend(d.source_program for _argument in call.args)
        caller_result = self.desc(call.metadata.type_ref, d)
        caller_params = [
            [
                native_params[index][0] if index < len(native_params) else f"arg{index}",
                self.desc(
                    capture.type_ref,
                    d,
                    typed=capture.type_program or d.source_program,
                    run_ref_producers=capture.run_ref_producers,
                ),
            ]
            for index, capture in enumerate(request.captures)
        ]
        caller_params.extend(
            [
                native_params[index][0] if index < len(native_params) else f"arg{index}",
                self.desc(argument.metadata.type_ref, d),
            ]
            for index, argument in enumerate(call.args, start=len(request.captures))
        )
        native_result = definition["result"]
        concrete_difference = (
            len(caller_params) != len(native_params)
            or any(left[1] != right[1] for left, right in zip(caller_params, native_params))
            or caller_result != native_result
        )
        boundary = None
        if concrete_difference:
            if not self._ordinary_generated_signature_boundary(
                caller_types=caller_types,
                caller_type_scopes=caller_type_scopes,
                caller_result_ref=call.metadata.type_ref,
                caller_scope=d.source_program,
                caller_params=caller_params,
                capture_routes=[capture.routes for capture in request.captures],
                native_params=native_params,
                native_result=native_result,
                key=key,
            ):
                raise ValueError(
                    f"procedure call {canonical!r} changes its complete native signature without a generated-only boundary"
                )
            boundary = self._boundary_relation(
                caller_params,
                native_params,
                caller_result,
                native_result,
                direct_capture_count=len(request.captures),
            )
        result = {
            "k": "call",
            "callee": canonical,
            "type": caller_result,
            "args": args,
            **self.provenance(call.metadata),
        }
        if boundary is not None:
            result["boundary"] = boundary
        self._remember_boundary(
            result,
            caller_params,
            native_params,
            caller_result,
            native_result,
            direct_count=len(request.captures),
            proof={
                "caller_types": caller_types,
                "caller_type_scopes": caller_type_scopes,
                "caller_result_ref": call.metadata.type_ref,
                "caller_scope": d.source_program,
                "capture_routes": [capture.routes for capture in request.captures],
                "key": key,
            },
        )
        return result

    def _callable_key(self, callable_def: Any, source_program: Any) -> tuple[list[Any], str]:
        self._require_selected_callable(callable_def)
        key = canonical_definition_key(
            callable_def,
            typed=source_program,
            binding_facts={"procedure_references": {}, "workflow_references": {}},
            capture_parameters=(),
            residual_signature=None,
        )
        return key, canonical_callee_name(callable_def, key=key)

    def _capture_type_from_reference(
        self,
        resolved: Any,
        route: Any,
        source_program: Any,
    ) -> TypeRef:
        if not isinstance(route, (tuple, list)) or not route:
            raise ValueError("retained capture route is malformed")
        current = resolved
        if route[0] == "reference":
            for formal in route[1]:
                selected = self._selected_ref_procedure(current, source_program)
                nested = dict(getattr(getattr(selected, "specialization", None), "proc_ref_bindings", {}) or {}).get(formal)
                if nested is None:
                    raise ValueError(f"retained nested reference route {formal!r} is unavailable")
                current = nested
            route = route[2]
        if route[0] == "parameter":
            formal = route[1]
            argument = next((row for row in current.bound_args if row.name == formal), None)
            if argument is not None:
                return argument.type_ref
            return dict(current.signature_params)[formal]
        if route[0] == "local":
            capture_name = self._local_capture_name(current, source_program, route[1])
            argument = next((row for row in current.bound_args if row.name == capture_name), None)
            if argument is not None:
                return argument.type_ref
            return dict(current.signature_params)[capture_name]
        raise ValueError(f"capture route {route!r} has no Task 4 parameter type owner")

    @staticmethod
    def _lift_route(route: Any, formal: str) -> Any:
        if route[0] in {"parameter", "local"}:
            return ["reference", [formal], list(route)]
        if route[0] == "reference":
            return ["reference", [formal, *list(route[1])], list(route[2])]
        raise ValueError("retained capture route cannot be forwarded through this reference")

    def _reference_call(
        self,
        call: WccCall,
        d: Definition,
        env: Mapping[str, TypeRef],
        formal: str,
    ) -> dict[str, Any]:
        resolved = d.procedure_refs[formal]
        pref = (d.procedure_ref_keys or {}).get(formal)
        if not isinstance(pref, Mapping) or not isinstance(pref.get("target"), list):
            raise ValueError(f"canonical procedure-reference target for {formal!r} is unavailable")
        key = pref["target"]
        target = self._procedure(getattr(resolved, "call_target_name", resolved.procedure_name))
        if target is None:
            target = self._procedure(resolved.procedure_name)
        if target is None:
            raise ValueError(f"resolved procedure target {resolved.procedure_name!r} has no retained owner")
        procedure, source_program = target
        self._require_selected_callable(procedure)
        captures: list[CaptureSlot] = []
        capture_args: list[dict[str, Any]] = []
        for row in key[7]:
            routes = row["routes"]
            lifted_routes = [self._lift_route(route, formal) for route in routes]
            matches = [
                index
                for index, outer in enumerate(d.captures or ())
                if any(route in outer.routes for route in lifted_routes)
            ]
            if len(set(matches)) != 1:
                raise ValueError(
                    f"retained reference {formal!r} capture does not map to one enclosing value"
                )
            outer_index = matches[0]
            outer_capture = d.captures[outer_index]
            type_ref = self._capture_type_from_reference(resolved, routes[0], source_program)
            captures.append(
                CaptureSlot(
                    type_ref=type_ref,
                    routes=list(routes),
                    type_program=source_program,
                    run_ref_producers=outer_capture.run_ref_producers,
                )
            )
            source_name = (d.capture_names or [])[outer_index]
            capture_args.append({"k": "name", "n": d.ref(source_name)})

        # The PRef key already contains the names-owned target projection. Drop
        # only runtime substitutions from the ephemeral body view so its bound
        # names become the explicit capture parameters below.
        captured_formals = {
            route[1]
            for row in key[7]
            for route in row["routes"]
            if route[0] == "parameter"
        }
        specialization = getattr(procedure, "specialization", None)
        if specialization is not None and captured_formals:
            filtered = {
                name: value
                for name, value in specialization.value_bindings.items()
                if name not in captured_formals
            }
            procedure = replace(procedure, specialization=replace(specialization, value_bindings=filtered))
        request = CallableRequest(
            key=key,
            canonical=canonical_callee_name_from_key(key),
            captures=captures,
            procedure_refs=dict(getattr(specialization, "proc_ref_bindings", {}) or {}),
            procedure_ref_keys={str(row[0]): row[1] for row in key[4]},
            workflow_refs=dict(getattr(specialization, "workflow_ref_bindings", {}) or {}),
            workflow_ref_keys={str(row[0]): row[1] for row in key[5]},
            argument_run_ref_producers={
                formal: self._run_ref_context_for_value(argument, d)
                for (formal, _type_ref), argument in zip(
                    tuple(getattr(procedure.signature, "params", ())),
                    call.args,
                    strict=True,
                )
            },
        )
        canonical = request.canonical
        if canonical in self.active:
            raise self.gap("call", f"recursive call of {canonical!r}", call)
        if canonical not in self.definitions:
            self._build_procedure(procedure, source_program, key, canonical, request=request)
        definition = self.definitions[canonical]
        key = definition["key"]
        native_params = definition["params"]
        args = [*capture_args, *[self.value(argument, d, env) for argument in call.args]]
        caller_types = [capture.type_ref for capture in captures]
        caller_type_scopes = [capture.type_program or source_program for capture in captures]
        caller_types.extend(argument.metadata.type_ref for argument in call.args)
        caller_type_scopes.extend(d.source_program for _argument in call.args)
        caller_result = self.desc(call.metadata.type_ref, d)
        caller_params = [
            [
                native_params[index][0] if index < len(native_params) else f"arg{index}",
                self.desc(
                    capture.type_ref,
                    d,
                    typed=capture.type_program or source_program,
                    run_ref_producers=capture.run_ref_producers,
                ),
            ]
            for index, capture in enumerate(captures)
        ]
        caller_params.extend(
            [
                native_params[index][0] if index < len(native_params) else f"arg{index}",
                self.desc(argument.metadata.type_ref, d),
            ]
            for index, argument in enumerate(call.args, start=len(captures))
        )
        native_result = definition["result"]
        concrete_difference = (
            len(caller_params) != len(native_params)
            or any(left[1] != right[1] for left, right in zip(caller_params, native_params))
            or caller_result != native_result
        )
        boundary = None
        if concrete_difference:
            if not self._ordinary_generated_signature_boundary(
                caller_types=caller_types,
                caller_type_scopes=caller_type_scopes,
                caller_result_ref=call.metadata.type_ref,
                caller_scope=d.source_program,
                caller_params=caller_params,
                capture_routes=[capture.routes for capture in captures],
                native_params=native_params,
                native_result=native_result,
                key=key,
            ):
                raise ValueError(
                    f"procedure-reference call {canonical!r} changes its complete native signature without a generated-only boundary"
                )
            boundary = self._boundary_relation(
                caller_params,
                native_params,
                caller_result,
                native_result,
                direct_capture_count=len(captures),
            )
        result = {
            "k": "call",
            "callee": canonical,
            "type": caller_result,
            "args": args,
            **self.provenance(call.metadata),
        }
        if boundary is not None:
            result["boundary"] = boundary
        self._remember_boundary(
            result,
            caller_params,
            native_params,
            caller_result,
            native_result,
            direct_count=len(captures),
            proof={
                "caller_types": caller_types,
                "caller_type_scopes": caller_type_scopes,
                "caller_result_ref": call.metadata.type_ref,
                "caller_scope": d.source_program,
                "capture_routes": [capture.routes for capture in captures],
                "key": key,
            },
        )
        return result

    def workflow_call(self, perform: WccPerform, d: Definition, env: Mapping[str, TypeRef]) -> dict[str, Any]:
        target_name = perform.target_name
        caller_module = self._module_for_owner(d.source_program, d.owner, d.callable_definition)
        caller_rows = getattr(d.source_program, "module_workflow_signatures", {}).get(caller_module, {})
        resolved = self._resolve_workflow_target(d.source_program, d.owner, target_name)
        if resolved is None:
            raise ValueError(f"WCC workflow call {target_name!r} has no retained typed owner")
        caller_signature, workflow, source_program = resolved
        imported = getattr(d.source_program, "imported_programs", {}).get(target_name)
        admitted_import = (
            imported is source_program
            and caller_rows.get(target_name) is caller_signature
            and (
                getattr(imported, "entry", None) is workflow
                or workflow in getattr(imported, "workflows", {}).values()
            )
        )
        key, canonical = self._callable_key(workflow, source_program)
        supplied = {name: self.value(value, d, env) for name, value in perform.keyword_args}
        occurrence = (d.context_call_occurrences or {}).get(id(perform))
        forwarded_context: dict[str, tuple[int, CaptureSlot]] = {}
        target_captures_by_outer: dict[int, CaptureSlot] = {}
        if occurrence is not None:
            declaration_id, call_occurrence = occurrence
            for outer_index, outer_capture in enumerate(d.captures or ()):
                for route in outer_capture.routes:
                    if route[0] != "context" or not route[1]:
                        continue
                    if route[1][0] != [declaration_id, call_occurrence]:
                        continue
                    if len(route[1]) == 1:
                        previous = forwarded_context.get(route[2])
                        if previous is not None and previous[0] != outer_index:
                            raise ValueError(f"context formal {route[2]!r} has competing captures")
                        forwarded_context[route[2]] = (outer_index, outer_capture)
                        continue
                    suffix = ["context", route[1][1:], route[2], route[3]]
                    slot = target_captures_by_outer.get(outer_index)
                    if slot is None:
                        slot = CaptureSlot(
                            type_ref=outer_capture.type_ref,
                            routes=[],
                            source_name=outer_capture.source_name,
                            identity=("forwarded-context", outer_index, outer_capture.identity),
                            type_program=outer_capture.type_program,
                            run_ref_producers=outer_capture.run_ref_producers,
                        )
                        target_captures_by_outer[outer_index] = slot
                    if suffix not in slot.routes:
                        slot.routes.append(suffix)
        target_request = None
        if target_captures_by_outer:
            target_request = self._workflow_request(
                workflow,
                source_program,
                [target_captures_by_outer[index] for index in sorted(target_captures_by_outer)],
            )
            key, canonical = target_request.key, target_request.canonical
        for name, type_ref in caller_signature.params:
            if name in supplied:
                continue
            if name in forwarded_context:
                outer_index, _capture = forwarded_context[name]
                source_name = (d.capture_names or [])[outer_index]
                supplied[name] = {"k": "name", "n": d.ref(source_name)}
                continue
            default = caller_signature.param_defaults.get(name)
            if default is not None:
                supplied[name] = {
                    "k": "lit",
                    "v": default.normalized_value,
                    "type": self.desc(type_ref, d),
                }
                continue
            requirement = caller_signature.hidden_context_requirements.get(name)
            if requirement is None:
                continue
            if requirement.context_kind == "RunCtx" or _is_run_context_shape(type_ref):
                try:
                    supplied[name] = _caller_run_context(d, env)
                except ValueError:
                    supplied[name] = run_context_value(self.desc(type_ref, d))
            elif requirement.context_kind == "PhaseCtx" and requirement.phase_name:
                try:
                    run_value = _caller_run_context(d, env, required_formal=name)
                except ValueError:
                    run_type = type_ref.field_types.get("run") if isinstance(type_ref, RecordTypeRef) else None
                    if run_type is None:
                        raise
                    run_value = run_context_value(self.desc(run_type, d))
                supplied[name] = phase_context_value(
                    run_value,
                    requirement.phase_name,
                    self.desc(type_ref, d),
                )
        missing = [name for name, _ in caller_signature.params if name not in supplied]
        if missing:
            raise ValueError(f"workflow call {canonical!r} is missing checked arguments {missing!r}")

        caller_context_captures: list[CaptureSlot] = []
        if target_request is None:
            native_formals = {name for name, _ in workflow.signature.params}
            for formal, type_ref in caller_signature.params:
                if formal in native_formals:
                    continue
                requirement = caller_signature.hidden_context_requirements.get(formal)
                if requirement is None or caller_signature.param_defaults.get(formal) is not None:
                    continue
                if not self._context_group_matches(workflow, source_program, requirement):
                    continue
                routes = self._context_routes(
                    workflow,
                    source_program,
                    requirement,
                    type_ref,
                )
                if not routes:
                    raise ValueError(f"private context {formal!r} has no retained omitted recipient route")
                caller_context_captures.append(
                    CaptureSlot(
                        type_ref=type_ref,
                        routes=routes,
                        value=supplied[formal],
                        source_name=formal,
                        identity=("caller-context", id(d.source_program), formal, requirement.phase_name),
                        type_program=d.source_program,
                    )
                )
            if caller_context_captures:
                target_request = self._workflow_request(workflow, source_program, caller_context_captures)
                key, canonical = target_request.key, target_request.canonical

        if canonical in self.active:
            raise self.gap("call", f"recursive call of {canonical!r}", perform)
        if canonical not in self.definitions:
            self._build_workflow(
                workflow,
                source_program,
                key,
                canonical,
                request=target_request,
            )
        definition = self.definitions[canonical]
        key = definition["key"]
        captures = target_request.captures if target_request is not None else []
        captured_formals = {capture.source_name for capture in captures}
        forwarded_context_slots = {
            name: capture for name, (_index, capture) in forwarded_context.items()
        }
        caller_params = [
            [
                capture.source_name or self._capture_source(index),
                self.desc(
                    capture.type_ref,
                    d,
                    typed=capture.type_program,
                    run_ref_producers=capture.run_ref_producers,
                ),
            ]
            for index, capture in enumerate(captures)
        ]
        caller_params.extend(
            [
                name,
                self.desc(
                    forwarded_context_slots[name].type_ref if name in forwarded_context_slots else type_ref,
                    d,
                    typed=forwarded_context_slots[name].type_program if name in forwarded_context_slots else None,
                ),
            ]
            for name, type_ref in caller_signature.params
            if name not in captured_formals
        )
        native_params = definition["params"]
        caller_result = self.desc(perform.metadata.type_ref, d)
        native_result = definition["result"]
        has_concrete_difference = (
            len(caller_params) != len(native_params)
            or any(left[1] != right[1] for left, right in zip(caller_params, native_params))
            or caller_result != native_result
        )
        context_boundary = bool(forwarded_context or caller_context_captures)
        caller_types = [capture.type_ref for capture in captures]
        caller_type_scopes = [capture.type_program or d.source_program for capture in captures]
        for name, type_ref in caller_signature.params:
            if name in captured_formals:
                continue
            forwarded = forwarded_context_slots.get(name)
            caller_types.append(forwarded.type_ref if forwarded is not None else type_ref)
            caller_type_scopes.append(
                (forwarded.type_program or d.source_program) if forwarded is not None else d.source_program
            )
        ordinary_generated_boundary = False
        if has_concrete_difference and not admitted_import and not context_boundary:
            ordinary_generated_boundary = self._ordinary_generated_signature_boundary(
                caller_types=caller_types,
                caller_type_scopes=caller_type_scopes,
                caller_result_ref=perform.metadata.type_ref,
                caller_scope=d.source_program,
                caller_params=caller_params,
                capture_routes=[capture.routes for capture in captures],
                native_params=native_params,
                native_result=native_result,
                key=key,
            )
        boundary = None
        if admitted_import or context_boundary or ordinary_generated_boundary:
            boundary = self._boundary_relation(
                caller_params,
                native_params,
                caller_result,
                native_result,
                direct_capture_count=len(captures),
            )
        elif has_concrete_difference:
            raise ValueError(
                f"workflow call {canonical!r} changes its complete native signature without an admitted boundary"
            )
        result = {
            "k": "call",
            "callee": canonical,
            "type": caller_result,
            "args": [
                capture.value
                if target_request is not None and capture.value is not None
                else {"k": "name", "n": d.ref((d.capture_names or [])[outer_index])}
                for outer_index, capture in sorted(target_captures_by_outer.items())
            ]
            + [capture.value for capture in caller_context_captures]
            + [
                supplied[name]
                for name, _ in caller_signature.params
                if name not in captured_formals
            ],
            **self.provenance(perform.metadata),
        }
        if boundary is not None:
            result["boundary"] = boundary
        self._remember_boundary(
            result,
            caller_params,
            native_params,
            caller_result,
            native_result,
            direct_count=len(captures),
            proof={
                "caller_types": caller_types,
                "caller_type_scopes": caller_type_scopes,
                "caller_result_ref": perform.metadata.type_ref,
                "caller_scope": d.source_program,
                "capture_routes": [capture.routes for capture in captures],
                "key": key,
            },
        )
        return result

    @staticmethod
    def _ordinary_generated_signature_boundary(
        *,
        caller_types: list[TypeRef],
        caller_type_scopes: list[Any],
        caller_result_ref: TypeRef,
        caller_scope: Any,
        caller_params: list[list[Any]],
        capture_routes: list[list[Any]],
        native_params: list[list[Any]],
        native_result: dict[str, Any],
        key: list[Any],
    ) -> bool:
        """Authorize only a whole ordered D-equal view with concrete changes."""

        if not isinstance(key, list) or len(key) != 9 or not isinstance(key[7], list) or not isinstance(key[8], Mapping):
            raise ValueError("canonical callable key has no complete signature projection")
        key_params = key[8].get("params")
        if not isinstance(key_params, list) or not isinstance(key[8].get("result"), Mapping):
            raise ValueError("canonical callable residual signature is malformed")
        if len(caller_types) != len(caller_type_scopes) or len(caller_types) != len(caller_params):
            raise ValueError("caller signature TypeRefs, scopes, and descriptors are not aligned")
        if len(caller_params) != len(native_params) or len(capture_routes) != len(key[7]):
            return False
        if len(caller_types) != len(key[7]) + len(key_params):
            return False
        for key_capture, routes in zip(key[7], capture_routes, strict=True):
            if not isinstance(key_capture, Mapping) or not isinstance(key_capture.get("routes"), list):
                raise ValueError("canonical callable capture route is malformed")
            if _canonical_json(sorted(routes, key=_canonical_json)) != _canonical_json(key_capture["routes"]):
                return False

        projections: dict[int, Any] = {}
        caller_d = []
        for type_ref, scope in zip(caller_types, caller_type_scopes, strict=True):
            projection = projections.setdefault(id(scope), _run_ref_signatures(scope))
            caller_d.append(projection.key_type(type_ref))
        expected_d = [capture["type"] for capture in key[7]] + key_params
        caller_result_d = _run_ref_signatures(caller_scope).key_type(caller_result_ref)
        if caller_d != expected_d or caller_result_d != key[8]["result"]:
            return False

        # D retains every nominal and structural fact except generated identities.
        # Equality above plus a changed concrete endpoint is the complete proof;
        # concrete input changes include the leading capture prefix.
        return any(
            caller_row[1] != native_row[1]
            for caller_row, native_row in zip(caller_params, native_params, strict=True)
        ) or canonical_type_descriptor(caller_result_ref, typed=caller_scope) != native_result

    @staticmethod
    def _boundary_relation(
        caller_params: list[list[Any]],
        native_params: list[list[Any]],
        caller_result: dict[str, Any],
        native_result: dict[str, Any],
        *,
        direct_capture_count: int,
    ) -> dict[str, Any]:
        from orchestrator.workflow.type_descriptor import compiled_boundary_rows

        direct = [
            [index, index]
            for index in range(min(direct_capture_count, len(caller_params), len(native_params)))
            if caller_params[index][1] == native_params[index][1]
        ]
        caller_direct = {left for left, _right in direct}
        native_direct = {right for _left, right in direct}
        return {
            "params": caller_params,
            "direct": direct,
            "inputs": {
                "caller": compiled_boundary_rows(
                    [row for index, row in enumerate(caller_params) if index not in caller_direct]
                ),
                "callee": compiled_boundary_rows(
                    [row for index, row in enumerate(native_params) if index not in native_direct]
                ),
            },
            "outputs": {
                "caller": compiled_boundary_rows(
                    [("return", caller_result)],
                    output=True,
                    relax_inactive_union_paths=caller_result["kind"] == "union",
                ),
                "callee": compiled_boundary_rows(
                    [("return", native_result)],
                    output=True,
                    relax_inactive_union_paths=native_result["kind"] == "union",
                ),
            },
        }

    def _remember_boundary(
        self,
        node: dict[str, Any],
        caller_params: list[list[Any]],
        native_params: list[list[Any]],
        caller_result: dict[str, Any],
        native_result: dict[str, Any],
        *,
        direct_count: int,
        proof: Mapping[str, Any] | None,
    ) -> None:
        generated = bool(
            proof
            and (
                any(self._contains_run_ref(ref) for ref in proof["caller_types"])
                or self._contains_run_ref(proof["caller_result_ref"])
            )
        )
        if node.get("boundary") is None and not generated:
            return
        self.boundary_requests.append(
            {
                "node": node,
                "caller_params": caller_params,
                "native_params": native_params,
                "caller_result": caller_result,
                "native_result": native_result,
                "direct_count": direct_count,
                "initial": node.get("boundary") is not None,
                "proof": proof,
            }
        )

    def _signature_rows(
        self,
        callable_def: Any,
        d: Definition,
        params: Any,
        *,
        erased_formals: set[str] | frozenset[str] = frozenset(),
    ) -> tuple[list[list[Any]], dict[str, TypeRef], dict[str, str]]:
        rows = []
        type_env = {}
        labels = {param.name: getattr(param, "binding_label", None) for param in params}
        names = dict(d.names)
        for name, type_ref in callable_def.signature.params:
            if name in erased_formals:
                continue
            wire = d.renamer.bind(name, authored_label=labels.get(name), env=names)
            rows.append([wire, self.desc(type_ref, d)])
            type_env[name] = type_ref
        return rows, type_env, names

    def _build_procedure(
        self,
        procedure: Any,
        source_program: Any,
        key: list[Any],
        canonical: str,
        *,
        request: CallableRequest | None = None,
    ) -> None:
        self.active.append(canonical)
        try:
            type_env = source_program.procedure_type_env(procedure)
            context = self.definition_context(
                canonical=canonical,
                owner=procedure.definition.name,
                source_program=source_program,
                type_env=type_env,
                node=procedure.typed_body,
                params=procedure.definition.params,
                callable_def=procedure,
            )
            capture_slots = list(request.captures) if request is not None else []
            capture_rows = []
            capture_names = []
            local_capture_names: dict[int, str] = {}
            for index, capture in enumerate(capture_slots):
                source_name = self._capture_source(index)
                local, wire = self.bind(context, source_name, label=None)
                context = local
                capture_names.append(source_name)
                capture_rows.append(
                    [
                        wire,
                        self.desc(
                            capture.type_ref,
                            context,
                            typed=capture.type_program or source_program,
                            run_ref_producers=capture.run_ref_producers,
                        ),
                    ]
                )
                for route in capture.routes:
                    if route[0] == "parameter":
                        context.names[route[1]] = wire
                    elif route[0] == "local":
                        local_row = self._local_definition_row(procedure, source_program)
                        if local_row is None or route[1] < 0 or route[1] >= len(local_row[3]):
                            raise ValueError(f"local capture route {route!r} has no retained declaration owner")
                        local_name = local_row[3][route[1]][0]
                        context.names[local_name] = wire
                        local_capture_names[index] = local_name
            run_ref_names = dict(context.run_ref_names or {})
            if request is not None:
                run_ref_names.update(request.argument_run_ref_producers or {})
            for index, capture in enumerate(capture_slots):
                if not capture.run_ref_producers:
                    continue
                run_ref_names[capture_names[index]] = capture.run_ref_producers
                if capture.source_name is not None:
                    run_ref_names[capture.source_name] = capture.run_ref_producers
                for route in capture.routes:
                    if route[0] == "parameter":
                        run_ref_names[route[1]] = capture.run_ref_producers
                    elif route[0] == "local" and index in local_capture_names:
                        run_ref_names[local_capture_names[index]] = capture.run_ref_producers
            context = context.with_names(context.names, run_ref_names=run_ref_names)
            context.callable_definition = procedure
            context.callable_key = key
            context.captures = capture_slots
            context.capture_names = capture_names
            context.procedure_refs = request.procedure_refs if request is not None else dict(getattr(procedure.specialization, "proc_ref_bindings", {}) or {})
            context.procedure_ref_keys = request.procedure_ref_keys if request is not None else {}
            context.workflow_refs = request.workflow_refs if request is not None else dict(getattr(procedure.specialization, "workflow_ref_bindings", {}) or {})
            context.workflow_ref_keys = request.workflow_ref_keys if request is not None else {}
            param_rows, value_env, context.names = self._signature_rows(
                procedure,
                context,
                procedure.definition.params,
                erased_formals=(
                    {
                        row[0]
                        for row in [*key[4], *key[5], *key[6]]
                        if isinstance(row[0], str)
                    }
                    | {
                        route[1]
                        for capture in capture_slots
                        for route in capture.routes
                        if route[0] == "parameter"
                    }
                ),
            )
            param_rows = [*capture_rows, *param_rows]
            for source_name, capture in zip(capture_names, capture_slots, strict=True):
                value_env[source_name] = capture.type_ref
            for index, local_name in local_capture_names.items():
                value_env[local_name] = capture_slots[index].type_ref
            captured_formals = {
                route[1]
                for capture in capture_slots
                for route in capture.routes
                if route[0] == "parameter"
            }
            captured_formals.update(local_capture_names.values())
            specialization = getattr(procedure, "specialization", None)
            compile_time_bindings: dict[str, Any] = {}
            if specialization is not None:
                compile_time_bindings.update(dict(specialization.workflow_ref_bindings))
                compile_time_bindings.update(dict(specialization.proc_ref_bindings))
                compile_time_bindings.update(
                    {
                        name: value
                        for name, value in specialization.value_bindings.items()
                        if name not in captured_formals
                    }
                )
            wcc = elaborate_typed_workflow_body(
                procedure.typed_body,
                owner_name=procedure.definition.name,
                type_env=type_env,
                value_env=_procedure_signature_local_type_bindings(procedure),
                workflow_return_types=self._workflow_return_types_for(source_program, procedure.definition.name),
                procedure_return_types=self.procedure_return_types,
                resolved_procedures_by_name=source_program.procedures,
                procedure_type_envs=source_program.procedure_type_envs,
                route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
                closed_program=True,
                compile_time_bindings=compile_time_bindings,
            )
            normalized = normalize_wcc_body_to_anf(wcc)
            self._prepare_computed_capture_requests(normalized, context, source_program)
            context, capture_prefix = self._freeze_parameter_captures(
                context,
                procedure.typed_body,
                procedure.definition.params,
            )
            body = self.body(normalized, context, value_env)
            body = _prepend_lets(body, capture_prefix)
            row = {
                "key": key,
                "params": param_rows,
                "result": self.desc(procedure.signature.return_type_ref, context),
                "body": body,
            }
            selector = self._configuration_selector(source_program, procedure.definition.name)
            if selector is not None:
                row["configuration"] = selector
            self._insert_definition(canonical, key, row)
        finally:
            self.active.pop()

    def _build_workflow(
        self,
        workflow: Any,
        source_program: Any,
        key: list[Any],
        canonical: str,
        *,
        request: WorkflowRequest | None = None,
    ) -> None:
        self.active.append(canonical)
        try:
            name = workflow.definition.name
            type_env = source_program.workflow_type_env(name)
            context = self.definition_context(
                canonical=canonical,
                owner=name,
                source_program=source_program,
                type_env=type_env,
                node=workflow.typed_body,
                params=workflow.definition.params,
                callable_def=workflow,
            )
            captures = list(request.captures) if request is not None else []
            capture_rows = []
            capture_names = []
            for index, capture in enumerate(captures):
                internal_name = self._capture_source(index)
                local, wire = self.bind(context, internal_name, label=None)
                context = local
                capture_names.append(internal_name)
                capture_rows.append(
                    [
                        wire,
                        self.desc(
                            capture.type_ref,
                            context,
                            typed=capture.type_program or self.typed,
                            run_ref_producers=capture.run_ref_producers,
                        ),
                    ]
                )
                if capture.source_name is not None:
                    context.names[capture.source_name] = wire
            param_rows, value_env, context.names = self._signature_rows(
                workflow,
                context,
                workflow.definition.params,
            )
            param_rows = [*capture_rows, *param_rows]
            for capture in captures:
                if capture.source_name is not None:
                    value_env[capture.source_name] = capture.type_ref
            run_ref_names = dict(context.run_ref_names or {})
            for index, capture in enumerate(captures):
                if not capture.run_ref_producers:
                    continue
                run_ref_names[capture_names[index]] = capture.run_ref_producers
                if capture.source_name is not None:
                    run_ref_names[capture.source_name] = capture.run_ref_producers
                for route in capture.routes:
                    if route[0] == "parameter":
                        run_ref_names[route[1]] = capture.run_ref_producers
            context = context.with_names(context.names, run_ref_names=run_ref_names)
            context.callable_definition = workflow
            context.callable_key = key
            context.captures = captures
            context.capture_names = capture_names
            wcc = elaborate_typed_workflow_body(
                workflow.typed_body,
                owner_name=name,
                type_env=type_env,
                value_env=dict(workflow.signature.params),
                workflow_return_types=self._workflow_return_types_for(source_program, name),
                procedure_return_types=self.procedure_return_types,
                resolved_procedures_by_name=source_program.procedures,
                procedure_type_envs=source_program.procedure_type_envs,
                route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
                closed_program=True,
            )
            normalized = normalize_wcc_body_to_anf(wcc)
            context.context_call_occurrences = self._workflow_call_occurrences(
                normalized,
                source_program,
                name,
            )
            self._prepare_computed_capture_requests(normalized, context, source_program)
            context, capture_prefix = self._freeze_parameter_captures(
                context,
                workflow.typed_body,
                workflow.definition.params,
            )
            body = self.body(normalized, context, value_env)
            body = _prepend_lets(body, capture_prefix)
            row = {
                "key": key,
                "params": param_rows,
                "result": self.desc(workflow.signature.return_type_ref, context),
                "body": body,
            }
            selector = self._configuration_selector(source_program, name)
            if selector is not None:
                row["configuration"] = selector
            self._insert_definition(canonical, key, row)
        finally:
            self.active.pop()

    def _insert_definition(self, canonical: str, key: list[Any], row: dict[str, Any]) -> None:
        previous = self.definitions.get(canonical)
        if previous is not None and _canonical_json(previous) != _canonical_json(row):
            raise ValueError(f"canonical definition {canonical!r} has contradictory bodies")
        previous_key = self.definition_keys.get(canonical)
        if previous_key is not None and _canonical_json(previous_key) != _canonical_json(key):
            raise ValueError(f"canonical definition {canonical!r} has contradictory keys")
        self.definitions[canonical] = row
        self.definition_keys[canonical] = key

    def _prepare_computed_capture_requests(
        self,
        body: WccBody,
        d: Definition,
        source_program: Any,
    ) -> None:
        from ..expression_traversal import free_expr_names, walk_expr
        from ..expressions import BindProcExpr, LetStarExpr, LiteralExpr, NameExpr
        from ..wcc.model import WccNameAtom, WccOpaqueFrontendValue

        by_alias: dict[str, list[ComputedCaptureRequest]] = {
            alias: list(rows)
            for alias, rows in (d.computed_capture_requests_by_alias or {}).items()
        }
        sources: dict[tuple[int, Any], str] = dict(d.computed_capture_sources or {})
        reference_aliases: dict[tuple[int, str], str] = dict(d.reference_capture_aliases or {})
        requests: dict[tuple[int, tuple[str, ...]], ComputedCaptureRequest] = {
            (row.source_identity, row.formal): row
            for rows in by_alias.values()
            for row in rows
        }
        capture_binding_identities: set[object] = set(d.capture_binding_identities)

        def retain_static_capture_rows(expression: Any) -> None:
            for node in walk_expr(expression):
                if not isinstance(node, LetStarExpr):
                    continue
                capture_binding_identities.update(
                    identity
                    for row in node.binding_capture_sources
                    if row is not None
                    for identity in (row[0],)
                )

        def retain_reference_identities(resolved: Any, seen: set[int]) -> None:
            if id(resolved) in seen:
                return
            seen.add(id(resolved))
            for argument in getattr(resolved, "bound_args", ()):
                identity = getattr(argument, "source_binding_identity", None)
                if identity is not None:
                    capture_binding_identities.add(identity)
                value = getattr(argument, "value_expr", None)
                if hasattr(value, "bound_args"):
                    retain_reference_identities(value, seen)

        def retain_call_identities(call: WccCall) -> None:
            selected_owner = self.procedure_owners.get(call.specialized_callee_name)
            selected = selected_owner[0] if selected_owner is not None else None
            specialization = getattr(selected, "specialization", None)
            for resolved in (getattr(specialization, "proc_ref_bindings", {}) or {}).values():
                retain_reference_identities(resolved, set())

        def register_request(
            source_identity: int,
            formal_path: tuple[str, ...],
            expression: Any,
            type_ref: Any,
            aliases: Mapping[str, str],
            *,
            expression_lookup: tuple[int, str] | None = None,
        ) -> None:
            if isinstance(expression, (LiteralExpr, NameExpr)) or type_ref is None:
                return
            names = free_expr_names(expression)
            if not names:
                return
            selected_aliases = {
                name: alias for name, alias in aliases.items() if name in names
            }
            if set(selected_aliases) != names:
                raise ValueError(
                    f"computed bind-proc value {formal_path!r} lost a typed lexical source alias"
                )
            key = (source_identity, formal_path)
            previous = requests.get(key)
            if previous is not None:
                if dict(previous.source_aliases) != selected_aliases:
                    raise ValueError("one bind-proc creation has inconsistent WCC alias owners")
                if expression_lookup is not None:
                    previous_source = sources.get(expression_lookup)
                    if previous_source is not None and previous_source != previous.source_name:
                        raise ValueError(
                            "one checked bound argument has competing creation regions"
                        )
                    sources[expression_lookup] = previous.source_name
                return
            source_name = f"\0computed-capture:{len(requests) + 1}"
            request = ComputedCaptureRequest(
                source_identity=source_identity,
                formal=formal_path,
                expression=expression,
                type_ref=type_ref,
                source_aliases=selected_aliases,
                insertion_alias=tuple(selected_aliases.values())[-1],
                source_name=source_name,
            )
            requests[key] = request
            sources[key] = source_name
            if expression_lookup is not None:
                previous_source = sources.get(expression_lookup)
                if previous_source is not None and previous_source != source_name:
                    raise ValueError(
                        "one checked bound argument has competing creation regions"
                    )
                sources[expression_lookup] = source_name
            by_alias.setdefault(request.insertion_alias, []).append(request)

        def aliases_for(rows: tuple[Any, ...], expression: Any) -> dict[str, str]:
            names = free_expr_names(expression)
            aliases: dict[str, str] = {}
            for capture in rows:
                if (
                    capture.source_name in names
                    and isinstance(capture.value, WccNameAtom)
                ):
                    if capture.source_name in aliases:
                        raise ValueError(
                            f"computed capture source {capture.source_name!r} has competing lexical aliases"
                        )
                    aliases[capture.source_name] = capture.value.name
            return aliases

        def visit_reference_owner(
            resolved: Any,
            owner: BindProcExpr,
            rows: tuple[Any, ...],
            seen: set[tuple[int, int, tuple[str, ...]]],
            owner_path: tuple[str, ...] = (),
        ) -> None:
            marker = (id(resolved), id(owner), owner_path)
            if marker in seen:
                return
            seen.add(marker)
            selected = self._selected_ref_procedure(resolved, source_program)
            selected_refs = dict(
                getattr(getattr(selected, "specialization", None), "proc_ref_bindings", {}) or {}
            )
            bound_args = {argument.name: argument for argument in resolved.bound_args}
            origin = rows[0].source_binding
            for binding in owner.bindings:
                argument = bound_args.get(binding.name)
                if argument is None:
                    continue
                if isinstance(argument.type_ref, ProcRefTypeRef):
                    nested = selected_refs.get(binding.name)
                    if nested is None and hasattr(argument.value_expr, "bound_args"):
                        nested = argument.value_expr
                    if nested is not None and isinstance(binding.value_expr, BindProcExpr):
                        visit_reference_owner(
                            nested,
                            binding.value_expr,
                            rows,
                            seen,
                            (*owner_path, binding.name),
                        )
                    continue
                if self._local_capture(resolved, source_program, binding.name) is not None:
                    continue
                if isinstance(binding.value_expr, NameExpr):
                    lexical_alias = aliases_for(rows, binding.value_expr).get(
                        binding.value_expr.name
                    )
                    if lexical_alias is not None:
                        key = (id(argument.value_expr), binding.name)
                        previous = reference_aliases.get(key)
                        if previous is not None and previous != lexical_alias:
                            raise ValueError(
                                "one checked bound reference argument has competing lexical owners"
                            )
                        reference_aliases[key] = lexical_alias
                        continue
                if isinstance(argument.value_expr, NameExpr):
                    lexical_aliases = aliases_for(rows, argument.value_expr)
                    alias = lexical_aliases.get(argument.value_expr.name)
                    if alias is not None:
                        key = (id(argument.value_expr), binding.name)
                        previous = reference_aliases.get(key)
                        if previous is not None and previous != alias:
                            raise ValueError(
                                "one checked bound reference argument has competing lexical owners"
                            )
                        reference_aliases[key] = alias
                    continue
                register_request(
                    id(origin),
                    (*owner_path, binding.name),
                    argument.value_expr,
                    argument.type_ref,
                    aliases_for(rows, argument.value_expr),
                    expression_lookup=(id(argument.value_expr), binding.name),
                )

        def consider(call: WccCall) -> None:
            retain_call_identities(call)
            selected_owner = self.procedure_owners.get(call.specialized_callee_name)
            selected = selected_owner[0] if selected_owner is not None else None
            specialization = getattr(selected, "specialization", None)
            if specialization is None:
                return

            for owner, rows in _capture_owner_groups(
                call.specialization_captures,
                owner_kind="callee",
            ):
                type_rows = getattr(specialization, "bound_param_types", {}) or {}
                for binding in owner.bindings:
                    if isinstance(type_rows.get(binding.name), ProcRefTypeRef):
                        continue
                    register_request(
                        id(owner),
                        (binding.name,),
                        binding.value_expr,
                        type_rows.get(binding.name),
                        aliases_for(rows, binding.value_expr),
                    )

            base_name = getattr(specialization, "base_name", None)
            base_owner = self.procedure_owners.get(base_name) if base_name else None
            base = base_owner[0] if base_owner is not None else selected
            proc_refs = getattr(specialization, "proc_ref_bindings", {}) or {}
            if base is None:
                return
            for argument_index, (formal, _type_ref) in enumerate(base.signature.params):
                resolved = proc_refs.get(formal)
                if resolved is None:
                    continue
                for owner, rows in _capture_owner_groups(
                    call.specialization_captures,
                    owner_kind="argument",
                    argument_index=argument_index,
                ):
                    visit_reference_owner(resolved, owner, rows, set())

        def visit_value(value: Any) -> None:
            if isinstance(value, WccNameAtom):
                identity = value.metadata.binding_identity
                if identity is not None:
                    capture_binding_identities.add(identity)
            elif isinstance(value, WccOpaqueFrontendValue):
                retain_static_capture_rows(value.expr)
            elif isinstance(value, WccCall):
                consider(value)
                for argument in value.args:
                    visit_value(argument)
            elif isinstance(value, WccPerform):
                for argument in (*value.positional_args, *(item for _name, item in value.keyword_args)):
                    visit_value(argument)
            elif isinstance(value, WccSelect):
                visit_value(value.condition)
                for arm in (value.then_arm, value.else_arm):
                    for prefix in arm.prefix:
                        visit_value(prefix.bound_value)
                    visit_value(arm.value)
            elif isinstance(value, WccPureOp):
                for argument in value.args:
                    visit_value(argument)
            elif isinstance(value, WccRecordAtom):
                for _name, child in value.fields:
                    visit_value(child)
            elif isinstance(value, WccInject):
                for _name, child in value.fields:
                    visit_value(child)
            elif isinstance(value, WccFieldAccessAtom):
                visit_value(value.base)

        def visit_binding(binding: Any) -> None:
            visit_value(binding)

        def visit(node: Any) -> None:
            if isinstance(node, WccLet):
                visit_binding(node.bound_value)
                visit(node.body)
            elif isinstance(node, WccIf):
                visit_value(node.condition)
                visit(node.then_body)
                visit(node.else_body)
            elif isinstance(node, WccCase):
                visit_value(node.subject)
                for arm in node.arms:
                    visit(arm.body)
            elif isinstance(node, WccJoin):
                visit(node.body)
                visit(node.continuation)
            elif isinstance(node, WccRecJoin):
                visit_value(node.budget)
                if node.initial_state is not None:
                    visit_value(node.initial_state)
                visit(node.body)
                if node.exhaustion is not None:
                    visit(node.exhaustion)
            elif isinstance(node, (WccJump, WccLoopContinue)):
                for value in node.args if isinstance(node, WccJump) else node.state_args:
                    visit_value(value)
            elif isinstance(node, WccLoopDone):
                visit_value(node.result)
                if node.state is not None:
                    visit_value(node.state)
            elif isinstance(node, WccHalt):
                visit_value(node.result)

        visit(body)
        d.capture_binding_identities = frozenset(capture_binding_identities)
        d.computed_capture_sources = sources
        d.reference_capture_aliases = reference_aliases
        d.computed_capture_requests_by_alias = {
            alias: tuple(rows) for alias, rows in by_alias.items()
        }

    def _configuration_selector(self, source_program: Any, owner: str) -> str | None:
        row = self.configuration_for(source_program, owner)
        root = self.configuration_rows.get((id(self.typed), self.typed.entry_module))
        if root is not None and _canonical_json(row) == _canonical_json(root):
            return None
        from .program import canonical_digest

        digest = canonical_digest(row)
        self.configuration_imports[digest] = row
        return digest


def _authored_labels(root: Any):
    pending = [root]
    seen: set[int] = set()
    skip = {"metadata", "span", "form_path", "expansion_stack", "type_ref", "definition", "effect_summary", "source_span", "scope_id", "node_id"}
    while pending:
        node = pending.pop()
        if node is None or isinstance(node, (str, bytes, int, float, bool, Path)):
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        label = getattr(node, "binding_label", None)
        if label is not None:
            yield label
        labels = getattr(node, "binding_labels", ())
        yield from (label for label in labels if label is not None)
        if isinstance(node, Mapping):
            pending.extend(node.values())
        elif isinstance(node, (tuple, list)):
            pending.extend(node)
        elif is_dataclass(node) and not isinstance(node, type):
            pending.extend(getattr(node, field.name) for field in fields(node) if field.name not in skip)


def _prepend_lets(body: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(rows):
        row["body"] = body
        body = row
    return body


def _caller_run_context(
    d: Definition,
    env: Mapping[str, TypeRef],
    *,
    required_formal: str | None = None,
) -> dict[str, Any]:
    from ..phase import derived_private_child_context_eligibility

    callable_def = d.callable_definition
    signature = getattr(callable_def, "signature", None)
    params = tuple(getattr(signature, "params", ()))
    types = dict(params)

    def path_value(name: str, path: tuple[str, ...]) -> dict[str, Any]:
        value: dict[str, Any] = {"k": "name", "n": d.ref(name)}
        if path:
            value = {"k": "field", "base": value, "path": list(path)}
        return value

    # Derived child PhaseCtx values are authorized only by the frontend's
    # retained ItemCtx + payload eligibility proof. Local values that happen
    # to share a context type cannot substitute for that declared source.
    if required_formal is not None and signature is not None:
        eligibility = derived_private_child_context_eligibility(
            signature,
            param_name=required_formal,
        )
        carried = tuple(eligibility.carried_input_sources.values())
        expected_fields = {"run-id", "state-root", "artifact-root"}
        source_names = {row[0] for row in carried if len(row) == 3}
        source_paths = {tuple(row[1:-1]) for row in carried if len(row) == 3}
        target_fields = {row[-1] for row in carried if len(row) == 3}
        if (
            eligibility.allowed
            and len(carried) == 3
            and len(source_names) == 1
            and source_paths == {("run",)}
            and target_fields == expected_fields
        ):
            source_name = next(iter(source_names))
            if types.get(source_name) is not None and source_name in env:
                return path_value(source_name, ("run",))

    # Prefer declared caller formals in signature order. A same-shaped local
    # value must not hijack a call's hidden context default.
    for wanted in (_is_run_context_shape, _is_phase_context_shape):
        for name, type_ref in params:
            if name not in env or not wanted(type_ref):
                continue
            if wanted is _is_run_context_shape:
                return path_value(name, ())
            if isinstance(type_ref, RecordTypeRef) and "run" in type_ref.field_types:
                return path_value(name, ("run",))

    # Generated/internal callers may have no top-level signature. Keep their
    # retained environment usable, but only accept an actual RunCtx or
    # PhaseCtx; ItemCtx is accepted above through the explicit eligibility.
    if not params:
        for name, type_ref in env.items():
            if _is_run_context_shape(type_ref):
                return path_value(name, ())
        for name, type_ref in env.items():
            if _is_phase_context_shape(type_ref) and isinstance(type_ref, RecordTypeRef) and "run" in type_ref.field_types:
                return path_value(name, ("run",))
    raise ValueError("hidden phase context has no authorized caller RunCtx or PhaseCtx value")


def _entry_context_values(builder: Builder, workflow: Any, d: Definition, body: dict[str, Any]) -> dict[str, Any]:
    hidden = workflow.signature.hidden_context_requirements
    for param_name, type_ref in reversed(workflow.signature.params):
        requirement = hidden.get(param_name)
        if requirement is None:
            continue
        wire_name = d.names.get(param_name)
        if wire_name is None:
            local, wire_name = builder.bind(d, param_name, label=None)
            d.names = local.names
        descriptor = builder.desc(type_ref, d)
        if requirement.context_kind == "RunCtx" or _is_run_context_shape(type_ref):
            value = run_context_value(descriptor)
        elif requirement.context_kind == "PhaseCtx" and requirement.phase_name:
            run_type = type_ref.field_types.get("run") if isinstance(type_ref, RecordTypeRef) else None
            run_value = run_context_value(builder.desc(run_type, d)) if run_type is not None else None
            if run_value is None:
                raise ValueError("hidden phase context has no retained RunCtx field")
            value = phase_context_value(run_value, requirement.phase_name, descriptor)
        else:
            raise ValueError(f"entry hidden context {requirement.context_kind!r} has no Task 4 default")
        body = {"k": "let", "name": wire_name, "value": value, "body": body}
    return body


def build_closed_program(typed: Any) -> ClosedProgram:
    """Build, site, validate, and digest the complete source-free program table."""

    entry_span = getattr(getattr(typed.entry, "definition", None), "span", None)
    path = Path(entry_span.start.path) if entry_span is not None else Path(typed.entry_dir)
    with compiler_defect_boundary(path):
        try:
            # Construction and preflight belong to the same boundary as
            # translation: retained-state defects must be located uniformly.
            builder = Builder(typed)
            builder._preflight_closures()
            return _build_with_builder(typed, builder)
        except ClosedProgramGap as gap:
            raise LispFrontendCompileError((gap_diagnostic(gap),)) from gap


def _build_with_builder(typed: Any, builder: Builder) -> ClosedProgram:
    # `_build` remains the single assembly implementation for internal tests.
    if typed.entry is None:
        raise ValueError("closed-program entry workflow is missing")
    entry = typed.entry
    entry_key, entry_name = builder._callable_key(entry, typed)
    entry_type_env = typed.workflow_type_env(entry.definition.name)
    d = builder.definition_context(
        canonical=entry_name,
        owner=entry.definition.name,
        source_program=typed,
        type_env=entry_type_env,
        node=entry.typed_body,
        params=entry.definition.params,
        callable_def=entry,
    )
    root_configuration = builder.configuration_for(typed, typed.entry_module)
    native_params = {param.name: param for param in entry.definition.params}
    params = []
    defaults = {}
    hidden = set(entry.signature.hidden_context_requirements)
    value_env = dict(entry.signature.params)
    for name, type_ref in entry.signature.params:
        param = native_params.get(name)
        local, wire = builder.bind(d, name, label=getattr(param, "binding_label", None))
        d.names = local.names
        if name not in hidden:
            params.append([wire, builder.desc(type_ref, d)])
            default = entry.signature.param_defaults.get(name)
            if default is not None:
                defaults[wire] = default.normalized_value
    wcc = elaborate_typed_workflow_body(
        entry.typed_body,
        owner_name=entry.definition.name,
        type_env=entry_type_env,
        value_env=value_env,
        workflow_return_types=builder._workflow_return_types_for(typed, entry.definition.name),
        procedure_return_types=builder.procedure_return_types,
        resolved_procedures_by_name=typed.procedures,
        procedure_type_envs=typed.procedure_type_envs,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
        closed_program=True,
    )
    normalized = normalize_wcc_body_to_anf(wcc)
    builder._prepare_computed_capture_requests(normalized, d, typed)
    d, capture_prefix = builder._freeze_parameter_captures(
        d,
        entry.typed_body,
        entry.definition.params,
    )
    body = builder.body(normalized, d, value_env)
    body = _prepend_lets(body, capture_prefix)
    body = _entry_context_values(builder, entry, d, body)
    tree = {
        "schema": SCHEMA,
        "representation": REPRESENTATION,
        "target": EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
        "entry": entry_name,
        "params": params,
        "defaults": defaults,
        "result": builder.desc(entry.signature.return_type_ref, d),
        "body": body,
        "types": builder.nominal_types,
        "configuration": {**root_configuration, "imports": builder.configuration_imports},
        "definitions": builder.definitions,
        "sites": [],
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    builder.finalize_run_refs(tree)
    validate(tree)
    return ClosedProgram(
        tree=tree,
        sites=tuple(tuple(row) for row in tree["sites"]),
        digest=program_digest(tree),
    )
