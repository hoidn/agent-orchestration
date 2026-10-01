"""Independent source-free validation for a closed Workflow Lisp program."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
import json
import math
import re
from itertools import product
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from orchestrator.workflow.pure_expr import (
    PureExprEvaluationError,
    _coerce_value,
    _descriptors_match,
    canonical_json_for_pure_value,
    validate_pure_expr_payload,
)
from orchestrator.workflow.prompt_fragment_contract import (
    _RENDERERS_BY_KIND,
    _scan_placeholders,
)
from orchestrator.workflow.run_ref.config import (
    ReferenceBinding,
    decode_run_ref_static_config,
)
from orchestrator.workflow.run_ref.result_contract import (
    RUN_REF_RESULT_CONTRACT_SCHEMA,
)
from orchestrator.workflow.type_descriptor import (
    COMPILER_PRIMITIVE_TYPE_NAMES,
    compiled_boundary_rows,
    normalize_boundary_contract_definition,
    transport_schema_for_descriptor,
    validate_compiler_normalized_type_descriptor,
)
from orchestrator.workflow.view_renderer import (
    ViewRendererError,
    render_view,
    resolve_view_renderer,
)

from . import EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
from .names import (
    _parse_identity,
    _render_key_identity,
    canonical_callee_name_from_key,
    canonical_run_ref_signature,
    key_type_descriptor,
    run_ref_type_dependencies,
)


_TOP_FIELDS = {
    "schema",
    "representation",
    "target",
    "entry",
    "params",
    "defaults",
    "result",
    "body",
    "types",
    "configuration",
    "definitions",
    "sites",
}
_BODY_KEYS = {
    "let": {"k", "name", "value", "body", "label", "@"},
    "halt": {"k", "value", "@"},
    "done": {"k", "value", "@"},
    "if": {"k", "cond", "then", "else", "@"},
    "case": {"k", "subject", "arms", "@"},
    "join": {"k", "name", "params", "result", "body", "cont", "label", "@"},
    "jump": {"k", "join", "args", "@"},
    "loop": {
        "k", "name", "param", "state_type", "result", "budget", "init",
        "body", "exhausted", "code", "label", "@",
    },
    "continue": {"k", "loop", "args", "@"},
}
_VALUE_KEYS = {
    "lit": {"k", "v", "type", "@"},
    "name": {"k", "n", "@"},
    "field": {"k", "base", "path", "@"},
    "record": {"k", "type", "fields", "@"},
    "inject": {"k", "type", "variant", "fields", "@"},
    "op": {"k", "payload", "args", "@"},
    "select": {"k", "cond", "then", "else", "@"},
    "list": {"k", "items", "type", "@"},
    "list_map": {"k", "binder", "source", "body", "type", "@"},
    "path_join": {"k", "base", "child", "type", "@"},
    "block": {"k", "body", "@"},
    "context": {"k", "field", "@"},
    "result_path": {"k", "n", "type", "@"},
    "call": {"k", "callee", "args", "type", "boundary", "frame", "@"},
    "perform": {
        "k", "class", "result", "repeat", "site", "@", "boundary", "command",
        "closure", "contract", "argv", "document", "provider", "prompt", "inputs",
        "dependencies", "policy", "config", "arm_inputs", "question",
    },
}
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_GENERATED_RESULT_RE = re.compile(r"RunRefResult\$[0-9a-f]{16}\Z")
_RESULT_CONTRACT_METADATA_KEYS = frozenset(
    {
        "path",
        "guidance",
        "description",
        "format_hint",
        "example",
        "guidance_context",
        "guidance_by_variant",
        "result_guidance",
        "source_map_subject",
        "source_map_subjects_by_variant",
    }
)
_COMMAND_COMMON_FIELDS = frozenset(
    {
        "kind",
        "name",
        "stable_command",
        "must_not_repeat",
        "closure",
        "retirement_class",
        "retirement_label",
        "replacement_surface",
        "bridge_owner",
        "expiry_condition",
        "evidence_refs",
        "retirement_status",
    }
)
_COMMAND_CERTIFIED_FIELDS = frozenset(
    {
        "input_contract",
        "output_type_name",
        "effects",
        "path_safety",
        "source_map_behavior",
        "fixture_ids",
        "negative_fixture_ids",
        "behavior_class",
        "input_signature",
        "artifact_contracts",
        "state_writes",
        "error_codes",
        "owner_module",
        "replacement_path",
        "invocation_protocol",
        "transition_binding",
        "view_binding",
        "declared_promoted_fields",
    }
)
_PROMOTED_METADATA_FIELDS = frozenset(
    {
        "behavior_class",
        "input_signature",
        "artifact_contracts",
        "state_writes",
        "error_codes",
        "owner_module",
        "replacement_path",
        "invocation_protocol",
    }
)
_PROMPT_VALUE_PRIMITIVES = frozenset(
    {"String", "Int", "Float", "Bool", "Json", "Value"}
)


def _prompt_value_type_is_renderable(descriptor: Any) -> bool:
    """Mirror the source prompt owner's canonical-JSON type admission."""

    if not isinstance(descriptor, Mapping):
        return False
    kind = descriptor.get("kind")
    if kind == "primitive":
        return descriptor.get("name") in _PROMPT_VALUE_PRIMITIVES
    if kind in {"enum", "path", "record", "union"}:
        # The closed target is 2.35; whole-union prompt values were admitted at
        # 2.28 and the checked descriptor validator has already checked shape.
        return True
    if kind == "list":
        return _prompt_value_type_is_renderable(descriptor.get("item"))
    return False


def _value_coercion_descriptor(descriptor: Any) -> Any:
    """Use the catalog's JSON coercion for DSL Value, including nested slots."""

    if not isinstance(descriptor, Mapping):
        return descriptor
    kind = descriptor.get("kind")
    if kind == "primitive" and descriptor.get("name") == "Value":
        return {"kind": "primitive", "name": "Json"}
    projected = deepcopy(dict(descriptor))
    if kind in {"optional", "list"} and "item" in projected:
        projected["item"] = _value_coercion_descriptor(projected["item"])
    elif kind == "map":
        for field in ("key", "value"):
            if field in projected:
                projected[field] = _value_coercion_descriptor(projected[field])
    elif kind in {"record", "variant_case"}:
        for row in projected.get("fields", []):
            if isinstance(row, Mapping) and "type" in row:
                row["type"] = _value_coercion_descriptor(row["type"])
    elif kind == "union":
        for variant in projected.get("variants", []):
            if isinstance(variant, Mapping):
                for row in variant.get("fields", []):
                    if isinstance(row, Mapping) and "type" in row:
                        row["type"] = _value_coercion_descriptor(row["type"])
    return projected


def _coerce_checked_value(value: Any, descriptor: Mapping[str, Any], *, context: str) -> Any:
    """Coerce with strict catalog scalar tags while accepting JSON-valued Value."""

    return _coerce_value(
        value,
        _value_coercion_descriptor(descriptor),
        context=context,
    )
class CheckedFormError(ValueError):
    """A closed-program invariant failure with a stable rule and source span."""

    def __init__(
        self,
        rule: str,
        message: str,
        *,
        location: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rule = rule
        self.location = location


@dataclass(frozen=True)
class _BodyOutcome:
    kind: str
    value_type: Mapping[str, Any] | None = None
    target: str | None = None


@dataclass
class _SiteLabels:
    named_counts: dict[str, int] = dataclass_field(default_factory=dict)
    anonymous_count: int = 0


def validate(tree: dict[str, Any]) -> None:
    """Validate one complete closed program without a frontend type environment."""

    _Checker(tree).run()


class _Checker:
    def __init__(self, tree: Any) -> None:
        self.tree = tree
        self.definitions: dict[str, Any] = {}
        self.types: dict[str, Any] = {}
        self.root_configuration: dict[str, Any] = {}
        self.calls: dict[str, list[dict[str, Any]]] = {}
        self.semantic_calls: dict[str, tuple[dict[str, Any], ...]] = {}
        self.call_argument_origins: dict[int, list[int | None]] = {}
        self.performs: dict[str, list[dict[str, Any]]] = {}
        self.effectful: dict[str, bool] = {}
        self.call_edges: dict[str, list[str]] = {}
        self.frame_expectations: dict[int, str] = {}
        self.site_expectations: list[tuple[str, str]] = []
        self.run_ref_origins: dict[str, list[dict[str, Any]]] = {}
        self.run_ref_configs: dict[int, Any] = {}
        self.run_ref_signatures: dict[str, dict[str, Any]] = {}
        self.pending_boundaries: list[dict[str, Any]] = []
        self.definition_order: list[str] = []
        self._run_ref_visiting: set[str] = set()

    def fail(
        self,
        rule: str,
        message: str,
        node: Any = None,
    ) -> None:
        location = None
        if isinstance(node, Mapping):
            provenance = node.get("@")
            if isinstance(provenance, Mapping) and isinstance(provenance.get("span"), str):
                location = provenance["span"]
        raise CheckedFormError(rule, message, location=location)

    def run(self) -> None:
        self._validate_json(self.tree)
        if not isinstance(self.tree, dict):
            self.fail("program_shape", "closed program must be a JSON object")
        if set(self.tree) != _TOP_FIELDS:
            self.fail("program_shape", "closed program has missing or extra top-level fields")
        if self.tree.get("schema") != "workflow-lisp/closed-program/1":
            self.fail("program_schema", "unsupported closed-program schema")
        if self.tree.get("representation") != "table/1":
            self.fail("program_representation", "unsupported closed-program representation")
        if self.tree.get("target") != EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION:
            self.fail(
                "program_target",
                f"closed program target must be {EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}",
            )
        self.definitions = self._mapping(self.tree.get("definitions"), "definition_table")
        self.types = self._mapping(self.tree.get("types"), "type_table")
        self._validate_type_table()
        self.root_configuration = self._validate_configurations()
        self._validate_labels(self.tree["body"])
        for definition in self.definitions.values():
            if not isinstance(definition, Mapping):
                self.fail("definition_shape", "definition must be a mapping")
            self._validate_labels(definition.get("body"))
        self._validate_definition_keys()
        self.calls = {name: [] for name in self.definitions}
        self.performs = {name: [] for name in self.definitions}
        self.call_edges = {name: [] for name in self.definitions}
        self._scan_identity_edges()
        self.semantic_calls = {owner: tuple(calls) for owner, calls in self.calls.items()}
        self.call_argument_origins = self._scan_capture_argument_origins()
        self._check_call_graph()
        self._compute_effectful_definitions()
        self._check_identities_and_site_table()
        self._check_entry()
        self._check_definition_bodies()
        self._check_call_graph()
        self._compute_effectful_definitions()
        self._check_effect_configurations()
        self._validate_run_ref_origins()
        self._check_run_ref_signatures_and_digests()
        self._check_pending_boundaries()
        self._check_key_runtime_agreement()
        self._check_context_capture_routes()

    def _validate_labels(self, body: Any) -> None:
        """Validate label locations and visit AST children without reading data."""

        def label(row: Mapping[str, Any]) -> None:
            if "label" in row and (not isinstance(row["label"], str) or not row["label"]):
                self.fail("binding_label", "binding label must be a nonempty string", row)

        def value(node: Any) -> None:
            if not isinstance(node, Mapping):
                return
            kind = node.get("k")
            if kind == "select":
                value(node.get("cond"))
                for arm_name in ("then", "else"):
                    arm = node.get(arm_name)
                    if not isinstance(arm, Mapping):
                        continue
                    for row in arm.get("prefix", []) if isinstance(arm.get("prefix", []), list) else []:
                        if isinstance(row, Mapping):
                            label(row)
                            value(row.get("value"))
                    value(arm.get("value"))
                return
            if kind == "block":
                walk_body(node.get("body"))
                return
            for child in self._value_children(node, strict=False):
                value(child)
            if kind == "call":
                for argument in node.get("args", []) if isinstance(node.get("args", []), list) else []:
                    value(argument)
            elif kind == "perform":
                for child in self._effect_children(node):
                    value(child)

        def walk_body(node: Any) -> None:
            if not isinstance(node, Mapping):
                return
            kind = node.get("k")
            if kind == "let":
                label(node)
                value(node.get("value"))
                walk_body(node.get("body"))
            elif kind == "if":
                value(node.get("cond"))
                walk_body(node.get("then"))
                walk_body(node.get("else"))
            elif kind == "case":
                value(node.get("subject"))
                for arm in node.get("arms", []) if isinstance(node.get("arms", []), list) else []:
                    if isinstance(arm, Mapping):
                        walk_body(arm.get("body"))
            elif kind == "join":
                label(node)
                params = node.get("params")
                if not isinstance(params, list) or len(params) != 1:
                    self.fail("join_arity", "join must have exactly one result parameter", node)
                walk_body(node.get("body"))
                walk_body(node.get("cont"))
            elif kind == "loop":
                label(node)
                value(node.get("budget"))
                value(node.get("init"))
                walk_body(node.get("body"))
                if node.get("exhausted") is not None:
                    walk_body(node.get("exhausted"))
            elif kind in {"halt", "done"}:
                value(node.get("value"))
            elif kind in {"jump", "continue"}:
                for argument in node.get("args", []) if isinstance(node.get("args", []), list) else []:
                    value(argument)

        walk_body(body)

    def _node_shape(self, value: Mapping[str, Any], allowed: set[str], *, node: Any = None) -> None:
        if not isinstance(value, Mapping):
            self.fail("node_shape", "node must be an object")
        kind = value.get("k")
        required: dict[str, set[str]] = {
            "let": {"k", "name", "value", "body"},
            "halt": {"k", "value"}, "done": {"k", "value"},
            "if": {"k", "cond", "then", "else"},
            "case": {"k", "subject", "arms"},
            "join": {"k", "name", "params", "result", "body", "cont"},
            "jump": {"k", "join", "args"},
            "loop": {"k", "name", "param", "state_type", "result", "budget", "init", "body", "exhausted", "code"},
            "continue": {"k", "loop", "args"},
            "lit": {"k", "v", "type"}, "name": {"k", "n"},
            "field": {"k", "base", "path"},
            "record": {"k", "type", "fields"},
            "inject": {"k", "type", "variant", "fields"},
            "op": {"k", "payload", "args"},
            "select": {"k", "cond", "then", "else"},
            "list": {"k", "items", "type"},
            "list_map": {"k", "binder", "source", "body", "type"},
            "path_join": {"k", "base", "child", "type"},
            "block": {"k", "body"},
            "context": {"k", "field"},
            "result_path": {"k", "n", "type"},
            "call": {"k", "callee", "args", "type"},
            "perform": {"k", "class", "result", "repeat"},
        }
        req = required.get(kind)
        if kind == "loop" and "budget" not in value:
            self.fail("budget_missing", "loop is missing its execution budget", node if node is not None else value)
        if req is None or not req.issubset(value) or set(value) - allowed:
            self.fail("node_shape", f"{kind!r} node has missing or extra fields", node if node is not None else value)
        if "@" in value:
            provenance = value["@"]
            if not isinstance(provenance, Mapping) or set(provenance) != {"span", "form"}:
                self.fail("provenance", "node provenance must contain span and form", value)
            if not isinstance(provenance["span"], str) or not isinstance(provenance["form"], list):
                self.fail("provenance", "node provenance span/form have invalid types", value)

    def _binding_name(self, value: Any, node: Any = None) -> str:
        if not isinstance(value, str) or not value:
            self.fail("binding_name", "binding name must be a nonempty string", node)
        return value

    def _require_type(self, actual: Any, expected: Any, rule: str, node: Any = None) -> None:
        if not isinstance(actual, Mapping) or not isinstance(expected, Mapping):
            self.fail(rule, "type fact is missing or malformed", node)
        try:
            self._validate_descriptor(actual, node=node)
            self._validate_descriptor(expected, node=node)
            same = _descriptors_match(actual, expected)
        except (TypeError, ValueError, RecursionError) as exc:
            self.fail(rule, f"type comparison failed: {exc}", node)
        if not same:
            self.fail(rule, "observed type differs from required type", node)

    def _assignable(self, actual: Any, expected: Any) -> bool:
        if not isinstance(actual, Mapping) or not isinstance(expected, Mapping):
            return False
        try:
            self._validate_descriptor(actual)
            self._validate_descriptor(expected)
            return _descriptors_match(actual, expected)
        except (CheckedFormError, TypeError, ValueError, RecursionError):
            return False

    @staticmethod
    def _merge_body_outcomes(results: Sequence[Sequence[_BodyOutcome]]) -> tuple[_BodyOutcome, ...]:
        return tuple(outcome for result in results for outcome in result)

    def _halt_body_type(
        self,
        outcomes: Sequence[_BodyOutcome],
        expected: Mapping[str, Any] | None,
        *,
        rule: str,
        message: str,
        node: Any,
    ) -> Mapping[str, Any]:
        observed: Mapping[str, Any] | None = None
        for outcome in outcomes:
            if outcome.kind != "halt" or not isinstance(outcome.value_type, Mapping):
                self.fail(rule, message, node)
            if expected is not None:
                self._require_type(outcome.value_type, expected, rule, node)
            if observed is None:
                observed = outcome.value_type
            else:
                self._require_type(outcome.value_type, observed, rule, node)
        if observed is None:
            self.fail(rule, message, node)
        return observed

    def _value_children(self, node: Mapping[str, Any], *, strict: bool = True) -> list[Any]:
        kind = node.get("k")
        if kind == "field":
            return [node.get("base")]
        if kind in {"record", "inject"}:
            fields = node.get("fields", [])
            if isinstance(fields, Mapping):
                return list(fields.values())
            return [row[1] for row in fields if isinstance(row, (list, tuple)) and len(row) == 2]
        if kind == "op":
            return list(node.get("args", [])) if isinstance(node.get("args", []), list) else []
        if kind == "list":
            return list(node.get("items", [])) if isinstance(node.get("items", []), list) else []
        if kind == "list_map":
            return [node.get("source"), node.get("body")]
        if kind == "path_join":
            return [node.get("base"), node.get("child")]
        if kind in {"lit", "name", "context", "result_path", "select", "block", "call", "perform"}:
            return []
        if strict:
            self.fail("node_kind", f"unknown value node kind {kind!r}", node)
        return []

    def _effect_children(self, node: Mapping[str, Any]) -> list[Any]:
        effect_class = node.get("class")
        if effect_class == "command":
            if "document" in node:
                rows = node.get("document", [])
                return [row[1] for row in rows if isinstance(row, (list, tuple)) and len(row) == 2] if isinstance(rows, list) else []
            return list(node.get("argv", [])) if isinstance(node.get("argv"), list) else []
        if effect_class == "provider":
            children = []
            rows = node.get("inputs", [])
            if isinstance(rows, list):
                children.extend(row[2] for row in rows if isinstance(row, (list, tuple)) and len(row) == 3)
            dependencies = node.get("dependencies")
            if isinstance(dependencies, Mapping):
                for key in ("required", "optional"):
                    children.extend(dependencies.get(key, []) if isinstance(dependencies.get(key, []), list) else [])
            policy = node.get("policy")
            if isinstance(policy, Mapping):
                children.extend(policy.values())
            prompt = node.get("prompt")
            template = prompt.get("template") if isinstance(prompt, Mapping) else None
            fills = template.get("fills", []) if isinstance(template, Mapping) else []
            if isinstance(fills, list):
                children.extend(fill.get("value") for fill in fills if isinstance(fill, Mapping))
            return children
        if effect_class == "run_ref":
            rows = node.get("inputs", [])
            return [row[1] for row in rows if isinstance(row, (list, tuple)) and len(row) == 2] if isinstance(rows, list) else []
        return []

    def _scan_identity_edges(self) -> None:
        """Enumerate declared AST edges, excluding payloads and literal data."""

        entry = self.tree["entry"]
        self.calls = {name: [] for name in self.definitions}
        self.performs = {name: [] for name in self.definitions}
        self.call_edges = {name: [] for name in self.definitions}
        self.calls[entry] = []
        self.performs[entry] = []
        self.call_edges[entry] = []

        def scan_effect(node: Mapping[str, Any], owner: str) -> None:
            for child in self._effect_children(node):
                scan_value(child, owner)

        def scan_value(node: Any, owner: str) -> None:
            if not isinstance(node, Mapping):
                self.fail("node_kind", "value node must be an object")
            kind = node.get("k")
            allowed = _VALUE_KEYS.get(kind)
            if allowed is None:
                self.fail("node_kind", f"unknown value node kind {kind!r}", node)
            self._node_shape(node, allowed, node=node)
            if kind == "call":
                self.calls.setdefault(owner, []).append(node)
                callee = node.get("callee")
                if owner in self.call_edges:
                    self.call_edges[owner].append(callee)
                for argument in node["args"]:
                    scan_value(argument, owner)
            elif kind == "perform":
                self.performs.setdefault(owner, []).append(node)
                scan_effect(node, owner)
            elif kind == "select":
                scan_value(node["cond"], owner)
                for branch_name in ("then", "else"):
                    branch = node[branch_name]
                    if not isinstance(branch, Mapping) or set(branch) - {"prefix", "value", "@"} or not {"prefix", "value"}.issubset(branch):
                        self.fail("select_shape", "select branch has invalid fields", node)
                    prefixes = branch["prefix"]
                    if not isinstance(prefixes, list):
                        self.fail("select_prefix", "select prefix must be an array", node)
                    for row in prefixes:
                        if not isinstance(row, Mapping) or set(row) - {"name", "value", "label", "@"} or not {"name", "value"}.issubset(row):
                            self.fail("select_prefix", "select prefix row has invalid fields", node)
                        scan_value(row["value"], owner)
                    scan_value(branch["value"], owner)
            elif kind == "block":
                scan_body(node["body"], owner)
            else:
                for child in self._value_children(node):
                    scan_value(child, owner)

        def scan_body(node: Any, owner: str) -> None:
            if not isinstance(node, Mapping):
                self.fail("node_kind", "body node must be an object")
            kind = node.get("k")
            allowed = _BODY_KEYS.get(kind)
            if allowed is None:
                self.fail("node_kind", f"unknown body node kind {kind!r}", node)
            self._node_shape(node, allowed, node=node)
            if kind == "let":
                scan_value(node["value"], owner)
                scan_body(node["body"], owner)
            elif kind == "if":
                scan_value(node["cond"], owner)
                scan_body(node["then"], owner)
                scan_body(node["else"], owner)
            elif kind == "case":
                scan_value(node["subject"], owner)
                if not isinstance(node["arms"], list):
                    self.fail("case_shape", "case arms must be an array", node)
                for arm in node["arms"]:
                    if not isinstance(arm, Mapping) or set(arm) - {"variant", "bind", "body", "@"} or not {"variant", "bind", "body"}.issubset(arm):
                        self.fail("case_shape", "case arm has invalid fields", node)
                    scan_body(arm["body"], owner)
            elif kind == "join":
                scan_body(node["body"], owner)
                scan_body(node["cont"], owner)
            elif kind == "loop":
                scan_value(node["budget"], owner)
                scan_value(node["init"], owner)
                scan_body(node["body"], owner)
                if node["exhausted"] is not None:
                    scan_body(node["exhausted"], owner)
            elif kind in {"halt", "done"}:
                scan_value(node["value"], owner)
            elif kind in {"jump", "continue"}:
                if not isinstance(node["args"], list):
                    self.fail("node_shape", "control transfer arguments must be an array", node)
                for argument in node["args"]:
                    scan_value(argument, owner)

        for name, definition in self.definitions.items():
            if not isinstance(definition, Mapping) or not isinstance(definition.get("body"), Mapping):
                self.fail("definition_shape", "definition must contain a body", definition)
            scan_body(definition["body"], name)
        scan_body(self.tree["body"], entry)

    def _scan_capture_argument_origins(self) -> dict[int, list[int | None]]:
        """Track direct capture-parameter references through lexical scopes."""

        origins: dict[int, list[int | None]] = {}

        def effect(node: Any, env: Mapping[str, int | None], owner: str) -> None:
            if not isinstance(node, Mapping):
                return
            for child in self._effect_children(node):
                value(child, env, owner)

        def value(node: Any, env: Mapping[str, int | None], owner: str) -> None:
            if not isinstance(node, Mapping):
                return
            kind = node.get("k")
            if kind == "call":
                arguments = node.get("args", [])
                if isinstance(arguments, list):
                    origins[id(node)] = [
                        env.get(argument.get("n"))
                        if isinstance(argument, Mapping) and argument.get("k") == "name"
                        else None
                        for argument in arguments
                    ]
                    for argument in arguments:
                        value(argument, env, owner)
                return
            if kind == "perform":
                effect(node, env, owner)
                return
            if kind == "select":
                value(node.get("cond"), env, owner)
                for arm_name in ("then", "else"):
                    arm = node.get(arm_name)
                    if not isinstance(arm, Mapping):
                        continue
                    arm_env = dict(env)
                    prefix = arm.get("prefix", [])
                    if isinstance(prefix, list):
                        for row in prefix:
                            if not isinstance(row, Mapping):
                                continue
                            value(row.get("value"), arm_env, owner)
                            name = row.get("name")
                            if isinstance(name, str):
                                arm_env[name] = None
                    value(arm.get("value"), arm_env, owner)
                return
            if kind == "block":
                body(node.get("body"), dict(env), owner)
                return
            if kind == "list_map":
                value(node.get("source"), env, owner)
                body_env = dict(env)
                binder = node.get("binder")
                if isinstance(binder, str):
                    body_env[binder] = None
                value(node.get("body"), body_env, owner)
                return
            for child in self._value_children(node, strict=False):
                value(child, env, owner)

        def body(node: Any, env: Mapping[str, int | None], owner: str) -> None:
            if not isinstance(node, Mapping):
                return
            kind = node.get("k")
            if kind == "let":
                value(node.get("value"), env, owner)
                nested = dict(env)
                name = node.get("name")
                if isinstance(name, str):
                    nested[name] = None
                body(node.get("body"), nested, owner)
            elif kind == "if":
                value(node.get("cond"), env, owner)
                body(node.get("then"), dict(env), owner)
                body(node.get("else"), dict(env), owner)
            elif kind == "case":
                value(node.get("subject"), env, owner)
                arms = node.get("arms", [])
                if isinstance(arms, list):
                    for arm in arms:
                        if not isinstance(arm, Mapping):
                            continue
                        nested = dict(env)
                        binder = arm.get("bind")
                        if isinstance(binder, str):
                            nested[binder] = None
                        body(arm.get("body"), nested, owner)
            elif kind == "join":
                nested = dict(env)
                params = node.get("params", [])
                if isinstance(params, list):
                    for row in params:
                        if isinstance(row, list) and row and isinstance(row[0], str):
                            nested[row[0]] = None
                body(node.get("body"), dict(env), owner)
                body(node.get("cont"), nested, owner)
            elif kind == "loop":
                value(node.get("budget"), env, owner)
                value(node.get("init"), env, owner)
                nested = dict(env)
                binder = node.get("param")
                if isinstance(binder, str):
                    nested[binder] = None
                body(node.get("body"), nested, owner)
                if node.get("exhausted") is not None:
                    body(node["exhausted"], dict(nested), owner)
            elif kind in {"halt", "done"}:
                value(node.get("value"), env, owner)
            elif kind in {"jump", "continue"}:
                args = node.get("args", [])
                if isinstance(args, list):
                    for argument in args:
                        value(argument, env, owner)

        for owner, definition in self.definitions.items():
            params = definition.get("params", []) if isinstance(definition, Mapping) else []
            key = definition.get("key", []) if isinstance(definition, Mapping) else []
            captures = key[7] if isinstance(key, list) and len(key) == 9 and isinstance(key[7], list) else []
            env: dict[str, int | None] = {}
            if isinstance(params, list):
                for index, row in enumerate(params):
                    if isinstance(row, list) and len(row) == 2 and isinstance(row[0], str):
                        env[row[0]] = index if index < len(captures) else None
            body(definition.get("body") if isinstance(definition, Mapping) else None, env, owner)
        entry_env = {
            row[0]: None
            for row in self.tree.get("params", [])
            if isinstance(row, list) and len(row) == 2 and isinstance(row[0], str)
        }
        body(self.tree.get("body"), entry_env, self.tree.get("entry"))
        return origins

    def _check_call_graph(self) -> None:
        graph = {name: list(self.call_edges.get(name, [])) for name in self.definitions}
        for owner, calls in self.calls.items():
            for call in calls:
                callee = call.get("callee")
                if not isinstance(callee, str) or callee not in self.definitions:
                    self.fail("callee_unknown", f"call target {callee!r} has no definition", call)
                if owner in graph and callee not in graph[owner]:
                    graph[owner].append(callee)
        self.call_edges = {**graph, self.tree["entry"]: list(self.call_edges.get(self.tree["entry"], []))}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                self.fail("call_cycle", f"recursive call through {name!r}")
            if name in visited:
                return
            visiting.add(name)
            try:
                for callee in graph[name]:
                    visit(callee)
            finally:
                visiting.remove(name)
            visited.add(name)

        for name in graph:
            visit(name)

    def _check_effect_configurations(self) -> None:
        """Match effects to the already-resolved configuration of their owner."""

        scopes: list[tuple[str, Mapping[str, Any]]] = [(self.tree["entry"], self.root_configuration)]
        scopes.extend((name, self._scope_for(definition, node=definition)) for name, definition in self.definitions.items())
        for owner, scope in scopes:
            for node in self.performs.get(owner, []):
                effect_class = node.get("class")
                if effect_class == "run_ref":
                    continue
                if effect_class == "command":
                    boundary = node.get("boundary")
                    row = scope["commands"].get(boundary) if isinstance(scope["commands"], Mapping) else None
                    if not isinstance(row, Mapping):
                        self.fail("configuration_scope", f"command boundary {boundary!r} is missing from {owner!r} configuration", node)
                    if not isinstance(row.get("kind"), str) or row["kind"] not in {"external_tool", "certified_adapter"}:
                        self.fail("configuration_scope", "command effect selects an invalid binding kind", node)
                    stable = row.get("stable_command")
                    if not isinstance(stable, list) or not stable or any(not isinstance(token, str) or not token for token in stable):
                        self.fail("configuration_scope", "command configuration omits its canonical stable tokens", node)
                    if not self._same(node.get("command"), stable):
                        self.fail("configuration_scope", "command stable tokens differ from its configuration binding", node)
                    configured_closure = row.get("closure")
                    if not isinstance(configured_closure, list):
                        self.fail("configuration_scope", "command configuration omits its normalized closure", node)
                    if not self._same(node.get("closure"), configured_closure):
                        self.fail("configuration_scope", "command closure differs from its configuration binding", node)
                    must_not_repeat = row["must_not_repeat"]
                    if must_not_repeat and node.get("repeat") != "never":
                        self.fail("configuration_scope", "command repeat rule differs from its configuration binding", node)
                    if not must_not_repeat and node.get("repeat") != "rerun":
                        self.fail("configuration_scope", "command repeat rule differs from its configuration binding", node)
                    if "document" in node:
                        if row["kind"] != "certified_adapter":
                            self.fail("configuration_scope", "document invocation requires a certified adapter binding", node)
                        promoted = row["declared_promoted_fields"]
                        supports_promoted = (
                            _PROMOTED_METADATA_FIELDS.issubset(promoted)
                            and bool(row["behavior_class"])
                            and bool(row["input_signature"])
                            and bool(row["owner_module"])
                            and row["invocation_protocol"] == "json_object_positional_arg"
                        )
                        if not supports_promoted:
                            self.fail("configuration_scope", "certified binding does not declare promoted document metadata", node)
                        if not self._document_keys_match_signature(row["input_signature"], node["document"]):
                            self.fail("configuration_scope", "command document keys differ from the selected signature rows", node)
                    continue
                if effect_class == "provider":
                    providers = scope["providers"]
                    provider = node.get("provider")
                    if not isinstance(providers, Mapping):
                        self.fail("configuration_scope", "provider configuration must be an object", node)
                    if provider not in providers and not any(
                        isinstance(value, Mapping) and value.get("provider_id") == provider
                        for value in providers.values()
                    ):
                        self.fail("configuration_scope", f"provider {provider!r} is missing from {owner!r} configuration", node)
                    prompt = node.get("prompt")
                    if (
                        isinstance(prompt, Mapping)
                        and isinstance(prompt.get("source_kind"), str)
                        and prompt["source_kind"] in {"asset_file", "input_file"}
                    ):
                        prompts = scope["prompts"]
                        if not isinstance(prompts, Mapping):
                            self.fail("configuration_scope", "prompt configuration must be an object", node)
                        keyset = {"source_kind", "path"} | ({"asset_base"} if prompt.get("source_kind") == "asset_file" else set())
                        projected = {key: prompt.get(key) for key in keyset}
                        if not any(isinstance(row, Mapping) and self._same(row, projected) for row in prompts.values()):
                            self.fail("configuration_scope", "provider prompt source differs from resolved prompt configuration", node)
                    continue
                self.fail("effect_class", f"unsupported effect class {effect_class!r}", node)

    def _validate_run_ref_origins(self) -> None:
        """Build the unique generated-type -> lexical run_ref producer index."""

        origins: dict[str, list[dict[str, Any]]] = {}
        for owner, nodes in self.performs.items():
            for node in nodes:
                if node.get("class") != "run_ref":
                    continue
                config = self.run_ref_configs.get(id(node))
                if config is None:
                    self.fail("run_ref_config", "run-ref config was not decoded during typed validation", node)
                generated = config.generated_result_type
                envelope = config.result_descriptor["envelope"]
                if envelope.get("name") != generated or not self._same(node.get("result"), envelope):
                    self.fail("run_ref_result", "run-ref result node differs from its decoded generated envelope", node)
                registered = self.types.get(generated)
                if not isinstance(registered, Mapping) or not self._same(registered, envelope):
                    self.fail("nominal_definition", f"generated run-ref result {generated!r} differs from its type-table row", node)
                origins.setdefault(generated, []).append(
                    {"owner": owner, "node": node, "config": config, "site": node.get("site")}
                )
        for name, descriptor in self.types.items():
            if name.startswith("RunRefResult$"):
                if _GENERATED_RESULT_RE.fullmatch(name) is None:
                    self.fail("run_ref_result", f"reserved generated type name {name!r} is malformed")
                if name not in origins:
                    self.fail("run_ref_origin", f"generated run-ref type {name!r} has no lexical producer")
            try:
                dependencies = run_ref_type_dependencies(descriptor)
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("type_descriptor", f"type-table identity dependencies are invalid: {exc}")
            for generated in dependencies:
                if generated not in origins:
                    self.fail("run_ref_origin", f"generated run-ref type argument {generated!r} has no lexical producer")
        for name, rows in origins.items():
            if len(rows) != 1:
                self.fail("run_ref_origin", f"generated run-ref type {name!r} has multiple lexical producers", rows[1]["node"])
        self.run_ref_origins = origins

    def _check_run_ref_signatures_and_digests(self) -> None:
        """Derive every finite S and verify each producer's complete site digest."""

        def producer_dependencies(origin: Mapping[str, Any]) -> set[str]:
            config = origin["config"]
            dependencies: set[str] = set()
            for row in config.inputs:
                dependencies.update(run_ref_type_dependencies(row.type_descriptor))
            for field in config.result_descriptor["envelope"]["fields"]:
                dependencies.update(run_ref_type_dependencies(field["type"]))
            return dependencies

        completed: dict[str, dict[str, Any]] = {}
        visiting: list[str] = []

        def signature_for(name: str) -> dict[str, Any]:
            if name in completed:
                return completed[name]
            if name not in self.run_ref_origins:
                self.fail("run_ref_origin", f"generated run-ref dependency {name!r} has no producer")
            if name in visiting:
                self.fail("run_ref_cycle", f"run-ref signature dependency cycle contains {name!r}")
            visiting.append(name)
            origin = self.run_ref_origins[name][0]
            dependencies = producer_dependencies(origin)
            for dependency in sorted(dependencies):
                if dependency == name or dependency in visiting:
                    self.fail("run_ref_cycle", f"run-ref signature dependency cycle contains {dependency!r}", origin["node"])
                signature_for(dependency)
            config = origin["config"]
            rows = [(row.name, row.type_descriptor) for row in config.inputs]
            try:
                signature = canonical_run_ref_signature(
                    rows,
                    config.result_descriptor,
                    run_ref_signatures=completed,
                )
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("run_ref_signature", f"run-ref structural signature is invalid: {exc}", origin["node"])
            visiting.pop()
            completed[name] = signature
            return signature

        for name in sorted(self.run_ref_origins):
            signature_for(name)
        self.run_ref_signatures = completed

        # Every structural marker is an exact projection of one checked
        # producer. This membership check is also the final grammar check for S.
        encoded_signatures = {self._canonical(value) for value in completed.values()}
        for key in self._definition_keys.values():
            self._check_key_markers(key, encoded_signatures)

        for name, rows in self.run_ref_origins.items():
            origin = rows[0]
            owner = origin["owner"]
            node = origin["node"]
            config = origin["config"]
            site = origin["site"]
            # Site identity is scoped by the canonical definition name, the
            # same string stored in the first column of the site's table row.
            containing = owner
            signature = completed[name]
            digest_input = ["workflow-lisp/run-ref-site/1", containing, site, signature]
            digest = sha256(self._canonical(digest_input).encode("utf-8")).hexdigest()
            if config.site_digest != digest:
                self.fail("run_ref_digest", "run-ref full site digest does not match its owner, site, and S", node)
            if config.generated_result_type != f"RunRefResult${digest[:16]}":
                self.fail("run_ref_digest", "run-ref generated result name does not match its site digest", node)
            if config.result_descriptor["envelope"].get("name") != config.generated_result_type:
                self.fail("run_ref_result", "run-ref config envelope name differs from its generated identity", node)

    def _check_key_markers(self, value: Any, signatures: set[str]) -> None:
        if not isinstance(value, list) or len(value) != 9:
            self.fail("definition_key", "key marker walk requires a validated nine-component key")
        for _, descriptor in value[3]:
            self._check_key_type_markers(descriptor, signatures)
        for _, reference in value[4]:
            self._check_pref_markers(reference, signatures)
        for _, reference in value[5]:
            self._check_wref_markers(reference, signatures)
        for _, descriptor, closed_value in value[6]:
            self._check_key_type_markers(descriptor, signatures)
            self._check_closed_value_markers(closed_value, signatures)
        for capture in value[7]:
            self._check_key_type_markers(capture["type"], signatures)
        for descriptor in [*value[8]["params"], value[8]["result"]]:
            self._check_key_type_markers(descriptor, signatures)

    def _check_key_type_markers(self, value: Any, signatures: set[str]) -> None:
        if not isinstance(value, Mapping):
            return
        kind = value.get("kind")
        if kind == "run-ref-result":
            if set(value) != {"kind", "signature"} or not isinstance(value.get("signature"), Mapping) or self._canonical(value["signature"]) not in signatures:
                self.fail("definition_key", "run-ref key marker does not equal a derived producer signature")
            return
        if kind in {"procedure-reference", "workflow-reference"}:
            signature = value.get("signature")
            if isinstance(signature, Mapping) and set(signature) == {"params", "result"}:
                for descriptor in [*signature["params"], signature["result"]]:
                    self._check_key_type_markers(descriptor, signatures)
            return
        if kind in {"record", "union", "enum"}:
            self._check_key_identity_markers(value.get("name"), signatures)
        elif kind == "variant_case":
            self._check_key_identity_markers(value.get("union_name"), signatures)
        if kind in {"optional", "list"}:
            self._check_key_type_markers(value.get("item"), signatures)
        elif kind == "map":
            self._check_key_type_markers(value.get("key"), signatures)
            self._check_key_type_markers(value.get("value"), signatures)
        elif kind in {"record", "variant_case"}:
            for row in value.get("fields", []):
                if isinstance(row, Mapping):
                    self._check_key_type_markers(row.get("type"), signatures)
        elif kind == "union":
            for variant in value.get("variants", []):
                if isinstance(variant, Mapping):
                    for row in variant.get("fields", []):
                        if isinstance(row, Mapping):
                            self._check_key_type_markers(row.get("type"), signatures)

    def _check_key_identity_markers(self, value: Any, signatures: set[str]) -> None:
        if isinstance(value, str):
            if value.startswith("RunRefResult$"):
                self.fail("definition_key", "concrete run-ref generated names cannot be persisted in a key")
            try:
                parsed = _parse_identity(value)
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("definition_key", f"projected nominal identity is invalid: {exc}")
            if not isinstance(parsed, str):
                self.fail("definition_key", "applied nominal identities must use structured key identities")
        if isinstance(value, Mapping):
            if value.get("kind") == "run-ref-result":
                self._check_key_type_markers(value, signatures)
            elif set(value) == {"head", "args"} and isinstance(value["args"], list):
                for argument in value["args"]:
                    self._check_key_identity_markers(argument, signatures)
            elif set(value) == {"owner", "member"}:
                self._check_key_identity_markers(value["owner"], signatures)

    def _check_signature_markers(self, signature: Any, signatures: set[str]) -> None:
        if isinstance(signature, Mapping) and set(signature) == {"params", "result"} and isinstance(signature["params"], list):
            for descriptor in [*signature["params"], signature["result"]]:
                self._check_key_type_markers(descriptor, signatures)

    def _check_pref_markers(self, reference: Any, signatures: set[str]) -> None:
        self._check_key_markers(reference["target"], signatures)
        self._check_signature_markers(reference["residual"], signatures)
        for _, descriptor, binding in reference["bound"]:
            self._check_key_type_markers(descriptor, signatures)
            self._check_binding_markers(binding, signatures)

    def _check_wref_markers(self, reference: Any, signatures: set[str]) -> None:
        self._check_key_markers(reference["target"], signatures)

    def _check_binding_markers(self, binding: Any, signatures: set[str]) -> None:
        if not isinstance(binding, Mapping) or len(binding) != 1:
            return
        category, value = next(iter(binding.items()))
        if category == "value":
            self._check_closed_value_markers(value, signatures)
        elif category == "procedure":
            self._check_pref_markers(value, signatures)
        elif category == "workflow":
            self._check_wref_markers(value, signatures)

    def _check_closed_value_markers(self, value: Any, signatures: set[str]) -> None:
        if not isinstance(value, Mapping):
            return
        kind = value.get("k")
        if kind == "lit":
            self._check_key_type_markers(value.get("type"), signatures)
        elif kind == "field":
            self._check_closed_value_markers(value.get("base"), signatures)
        elif kind in {"record", "inject"}:
            self._check_key_type_markers(value.get("type"), signatures)
            for row in value.get("fields", []):
                if isinstance(row, list) and len(row) == 2:
                    self._check_closed_value_markers(row[1], signatures)
        elif kind == "op":
            self._check_payload_key_markers(value.get("payload"), signatures)
            for child in value.get("args", []):
                self._check_closed_value_markers(child, signatures)
        elif kind == "select":
            self._check_closed_value_markers(value.get("cond"), signatures)
            for branch in (value.get("then"), value.get("else")):
                if isinstance(branch, Mapping):
                    for row in branch.get("prefix", []):
                        if isinstance(row, Mapping):
                            self._check_closed_value_markers(row.get("value"), signatures)
                    self._check_closed_value_markers(branch.get("value"), signatures)
        elif kind == "list":
            self._check_key_type_markers(value.get("type"), signatures)
            for child in value.get("items", []):
                self._check_closed_value_markers(child, signatures)
        elif kind == "list_map":
            self._check_key_type_markers(value.get("type"), signatures)
            self._check_closed_value_markers(value.get("source"), signatures)
            self._check_closed_value_markers(value.get("body"), signatures)
        elif kind == "path_join":
            self._check_key_type_markers(value.get("type"), signatures)
            self._check_closed_value_markers(value.get("base"), signatures)
            self._check_closed_value_markers(value.get("child"), signatures)
        elif kind == "block":
            self._check_closed_body_markers(value.get("body"), signatures)

    def _check_closed_body_markers(self, body: Any, signatures: set[str]) -> None:
        if not isinstance(body, Mapping):
            return
        kind = body.get("k")
        if kind == "let":
            self._check_closed_value_markers(body.get("value"), signatures)
            self._check_closed_body_markers(body.get("body"), signatures)
        elif kind in {"halt", "done"}:
            self._check_closed_value_markers(body.get("value"), signatures)

    def _check_payload_key_markers(self, payload: Any, signatures: set[str]) -> None:
        if not isinstance(payload, Mapping) or payload.get("pure_expr_schema_version") != 2:
            self.fail("definition_key", "closed operator payload must use pure-expression schema version 2")
        projected = self._catalog_payload_from_key(payload, signatures)
        try:
            validate_pure_expr_payload(projected)
        except (PureExprEvaluationError, TypeError, ValueError, RecursionError) as exc:
            self.fail("definition_key", f"closed operator payload has invalid typed descriptors: {exc}")

    def _catalog_payload_from_key(self, payload: Any, signatures: set[str]) -> Any:
        """Prepare only catalog descriptor slots for neutral catalog validation."""

        if not isinstance(payload, Mapping):
            return payload
        result = deepcopy(dict(payload))

        def descriptor(value: Any) -> Any:
            self._validate_key_type(value)
            self._check_key_type_markers(value, signatures)
            return _value_coercion_descriptor(self._neutralize_key_type(value))

        bindings = result.get("bindings")
        if isinstance(bindings, Mapping):
            for row in bindings.values():
                if isinstance(row, Mapping) and "type" in row:
                    row["type"] = descriptor(row["type"])
        if "result_type" in result:
            result["result_type"] = descriptor(result["result_type"])

        def expression(node: Any) -> None:
            if not isinstance(node, Mapping):
                return
            kind = node.get("kind")
            if kind in {"literal", "record", "union"} and "type" in node:
                node["type"] = descriptor(node["type"])
            elif kind == "record_update" and "record_type" in node:
                node["record_type"] = descriptor(node["record_type"])
            elif kind == "let":
                for row in node.get("bindings", []):
                    if isinstance(row, Mapping) and "type" in row:
                        row["type"] = descriptor(row["type"])
            elif kind == "list" and "element_type" in node:
                node["element_type"] = descriptor(node["element_type"])
            elif kind == "list_map":
                binder = node.get("binder")
                if isinstance(binder, Mapping) and "type" in binder:
                    binder["type"] = descriptor(binder["type"])
                if "result_element_type" in node:
                    node["result_element_type"] = descriptor(node["result_element_type"])
            elif kind == "path_join_under" and "path_type" in node:
                node["path_type"] = descriptor(node["path_type"])
            elif kind == "list_nonempty_head" and "element_type" in node:
                node["element_type"] = descriptor(node["element_type"])

            if kind in {"field_access"}:
                expression(node.get("base"))
            elif kind == "if":
                for field in ("condition", "then", "else"):
                    expression(node.get(field))
            elif kind in {"record", "union"}:
                for row in node.get("fields", []):
                    if isinstance(row, Mapping):
                        expression(row.get("value"))
            elif kind == "record_update":
                expression(node.get("base"))
                for row in node.get("fields", []):
                    if isinstance(row, Mapping):
                        expression(row.get("value"))
            elif kind == "let":
                for row in node.get("bindings", []):
                    if isinstance(row, Mapping):
                        expression(row.get("value"))
                expression(node.get("body"))
            elif kind == "list":
                for child in node.get("items", []):
                    expression(child)
            elif kind == "list_map":
                expression(node.get("source"))
                expression(node.get("body"))
            elif kind in {"path_join_under", "list_nonempty_head"}:
                expression(node.get("child" if kind == "path_join_under" else "source"))
            elif kind == "op":
                for child in node.get("args", []):
                    expression(child)

        expression(result.get("expr"))
        return result

    def _check_key_runtime_agreement(self) -> None:
        """Compare capture/residual/runtime facts through the shared S projection."""

        for name, definition in self.definitions.items():
            key = self._definition_keys[name]
            captures = key[7]
            params = definition.get("params")
            if not isinstance(params, list) or len(params) != len(captures) + len(key[8]["params"]):
                self.fail("definition_key", "definition parameter list differs from its capture prefix and residual signature", definition)
            for index, capture in enumerate(captures):
                parameter = params[index]
                if not isinstance(parameter, list) or len(parameter) != 2:
                    self.fail("definition_key", "capture parameter row is malformed", definition)
                try:
                    projected = key_type_descriptor(parameter[1], run_ref_signatures=self.run_ref_signatures)
                except (TypeError, ValueError, RecursionError) as exc:
                    self.fail("definition_key", f"capture descriptor cannot be projected: {exc}", definition)
                if not self._same(projected, capture["type"]):
                    self.fail("definition_key", f"capture parameter {index} differs from its key prefix", definition)
            for offset, expected in enumerate(key[8]["params"], start=len(captures)):
                parameter = params[offset]
                if not isinstance(parameter, list) or len(parameter) != 2:
                    self.fail("definition_key", "residual parameter row is malformed", definition)
                try:
                    projected = key_type_descriptor(parameter[1], run_ref_signatures=self.run_ref_signatures)
                except (TypeError, ValueError, RecursionError) as exc:
                    self.fail("definition_key", f"residual descriptor cannot be projected: {exc}", definition)
                if not self._same(projected, expected):
                    self.fail("definition_key", f"residual parameter {offset - len(captures)} differs from its key signature", definition)
            try:
                projected_result = key_type_descriptor(definition.get("result"), run_ref_signatures=self.run_ref_signatures)
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("definition_key", f"result descriptor cannot be projected: {exc}", definition)
            if not self._same(projected_result, key[8]["result"]):
                self.fail("definition_key", "definition result differs from its key residual signature", definition)

        visited: set[int] = set()

        def check_key_values(key: list[Any]) -> None:
            if id(key) in visited:
                return
            visited.add(id(key))
            for _, descriptor, value in key[6]:
                inferred = self._infer_closed_value(value, {})
                self._require_key_type(inferred, descriptor, value)
            for _, reference in key[4]:
                check_pref(reference)
            for _, reference in key[5]:
                check_wref(reference)

        def check_pref(reference: Mapping[str, Any]) -> None:
            check_key_values(reference["target"])
            for _, descriptor, binding in reference["bound"]:
                if set(binding) == {"value"}:
                    inferred = self._infer_closed_value(binding["value"], {})
                    self._require_key_type(inferred, descriptor, binding["value"])
                elif set(binding) == {"procedure"}:
                    check_pref(binding["procedure"])
                elif set(binding) == {"workflow"}:
                    check_wref(binding["workflow"])

        def check_wref(reference: Mapping[str, Any]) -> None:
            check_key_values(reference["target"])

        for key in self._definition_keys.values():
            check_key_values(key)

    def _require_key_type(self, actual: Any, expected: Any, node: Any) -> None:
        if not self._same(actual, expected):
            self.fail("definition_key", "closed substitution expression differs from its declared key type", node)

    def _infer_closed_value(self, value: Any, env: Mapping[str, Any]) -> Any:
        if not isinstance(value, Mapping):
            self.fail("definition_key", "closed expression value must be an object")
        kind = value.get("k")
        if kind == "lit":
            descriptor = value["type"]
            try:
                _coerce_checked_value(value.get("v"), descriptor, context="closed literal")
            except (PureExprEvaluationError, TypeError, ValueError, RecursionError) as exc:
                self.fail("definition_key", f"closed literal does not match its declared type: {exc}", value)
            return descriptor
        if kind == "name":
            name = value.get("n")
            if not isinstance(name, str) or name not in env:
                self.fail("definition_key", f"closed expression has a free name {name!r}", value)
            return env[name]
        if kind == "field":
            descriptor = self._infer_closed_value(value["base"], env)
            path = value["path"]
            if not path or any(not isinstance(part, str) or not part for part in path):
                self.fail("definition_key", "closed field path must be a nonempty string path", value)
            for segment in path:
                descriptor = self._key_field_type(descriptor, segment, value)
            return descriptor
        if kind in {"record", "inject"}:
            descriptor = value["type"]
            if kind == "record":
                if descriptor.get("kind") != "record":
                    self.fail("definition_key", "closed record value has a non-record type", value)
                fields = descriptor["fields"]
            else:
                if descriptor.get("kind") != "union":
                    self.fail("definition_key", "closed injection value has a non-union type", value)
                variant = next((row for row in descriptor["variants"] if row["name"] == value["variant"]), None)
                if variant is None:
                    self.fail("definition_key", "closed injection names an unknown variant", value)
                fields = variant["fields"]
            actual_rows = self._field_rows(value["fields"], value)
            expected = {row["name"]: row["type"] for row in fields}
            if set(actual_rows) != set(expected):
                self.fail("definition_key", "closed aggregate fields differ from its key type", value)
            for name, child in actual_rows.items():
                self._require_key_type(self._infer_closed_value(child, env), expected[name], child)
            return descriptor
        if kind == "op":
            payload = value["payload"]
            try:
                signatures = {self._canonical(row) for row in self.run_ref_signatures.values()}
                catalog_payload = self._catalog_payload_from_key(payload, signatures)
                validate_pure_expr_payload(catalog_payload)
            except (PureExprEvaluationError, TypeError, ValueError, RecursionError) as exc:
                self.fail("definition_key", f"closed operator payload is invalid: {exc}", value)
            args = value["args"]
            bindings = payload["bindings"]
            expected_names = [f"a{index}" for index in range(len(args))]
            if list(bindings) != expected_names:
                self.fail("definition_key", "closed operator bindings do not match argument order", value)
            for index, child in enumerate(args):
                descriptor = self._infer_closed_value(child, env)
                expected = bindings[f"a{index}"]["type"]
                self._require_key_type(descriptor, expected, child)
            return payload["result_type"]
        if kind == "select":
            self._require_key_type(
                self._infer_closed_value(value["cond"], env),
                {"kind": "primitive", "name": "Bool"}, value["cond"],
            )
            results = []
            for branch in (value["then"], value["else"]):
                branch_env = dict(env)
                for row in branch["prefix"]:
                    name = row["name"]
                    if not isinstance(name, str) or not name:
                        self.fail("definition_key", "closed select prefix binder is invalid", row)
                    branch_env[name] = self._infer_closed_value(row["value"], branch_env)
                results.append(self._infer_closed_value(branch["value"], branch_env))
            self._require_key_type(results[1], results[0], value)
            return results[0]
        if kind == "list":
            descriptor = value["type"]
            if descriptor.get("kind") != "list":
                self.fail("definition_key", "closed list value has a non-list type", value)
            for child in value["items"]:
                self._require_key_type(self._infer_closed_value(child, env), descriptor["item"], child)
            return descriptor
        if kind == "list_map":
            source = self._infer_closed_value(value["source"], env)
            descriptor = value["type"]
            if source.get("kind") != "list" or descriptor.get("kind") != "list":
                self.fail("definition_key", "closed list-map source and result must be lists", value)
            binder = value["binder"]
            if not isinstance(binder, str) or not binder:
                self.fail("definition_key", "closed list-map binder is invalid", value)
            body_env = dict(env)
            body_env[binder] = source["item"]
            self._require_key_type(
                self._infer_closed_value(value["body"], body_env), descriptor["item"], value["body"]
            )
            return descriptor
        if kind == "path_join":
            descriptor = value["type"]
            base = self._infer_closed_value(value["base"], env)
            child = self._infer_closed_value(value["child"], env)
            if descriptor.get("kind") != "path" or base.get("kind") != "path" or base.get("under") != descriptor.get("under"):
                self.fail("definition_key", "closed path join does not preserve its path root", value)
            self._require_key_type(child, {"kind": "primitive", "name": "String"}, value["child"])
            if value["child"].get("k") != "lit" or not isinstance(value["child"].get("v"), str) or not value["child"]["v"] or "\\" in value["child"]["v"]:
                self.fail("definition_key", "closed path join child is not a literal relative component", value["child"])
            return descriptor
        if kind == "block":
            return self._infer_closed_body(value["body"], dict(env))
        self.fail("definition_key", f"unsupported closed value kind {kind!r}", value)

    def _infer_closed_body(self, body: Any, env: dict[str, Any]) -> Any:
        if not isinstance(body, Mapping):
            self.fail("definition_key", "closed block body must be an object")
        kind = body.get("k")
        if kind == "let":
            name = body["name"]
            if not isinstance(name, str) or not name:
                self.fail("definition_key", "closed block binder is invalid", body)
            env[name] = self._infer_closed_value(body["value"], env)
            return self._infer_closed_body(body["body"], env)
        if kind == "halt":
            return self._infer_closed_value(body["value"], env)
        self.fail("definition_key", f"closed block terminal {kind!r} is unsupported", body)

    def _key_field_type(self, descriptor: Mapping[str, Any], segment: str, node: Any) -> Any:
        kind = descriptor.get("kind")
        if kind in {"record", "variant_case"}:
            fields = descriptor["fields"]
        elif kind == "union" and segment == "variant":
            name = descriptor["name"]
            enum_name = f"{name}.variant" if isinstance(name, str) else {"owner": name, "member": "variant"}
            return {"kind": "enum", "name": enum_name, "allowed": [row["name"] for row in descriptor["variants"]]}
        elif kind == "union":
            candidates = [field["type"] for variant in descriptor["variants"] for field in variant["fields"] if field["name"] == segment]
            if len(candidates) != len(descriptor["variants"]) or any(not self._same(candidates[0], row) for row in candidates[1:]):
                self.fail("definition_key", "closed union field is absent or variant-dependent", node)
            return candidates[0]
        else:
            self.fail("definition_key", "closed field access descends through a scalar", node)
        field = next((row for row in fields if row["name"] == segment), None)
        if field is None:
            self.fail("definition_key", f"closed field {segment!r} is absent from its type", node)
        return field["type"]

    def _compute_effectful_definitions(self) -> None:
        self.effectful = {}
        visiting: set[str] = set()

        def effectful(name: str) -> bool:
            if name in self.effectful:
                return self.effectful[name]
            if name in visiting:
                self.fail("call_cycle", f"recursive call through {name!r}")
            visiting.add(name)
            direct = bool(self.performs.get(name, []))
            called = False
            for callee in self.call_edges.get(name, []):
                called = effectful(callee) or called
            visiting.remove(name)
            self.effectful[name] = direct or called
            return self.effectful[name]

        for name in self.definitions:
            effectful(name)

    def _check_identities_and_site_table(self) -> None:
        """Recompute every site and frame from typed-form AST edges and labels."""

        expected_frames: dict[int, str] = {}
        expected_performs: dict[int, tuple[str, str]] = {}

        def escape(label: str) -> str:
            return "".join(f"%{ord(char):02X}" if char in "%/=#[]" else char for char in label)

        def next_label(scope: _SiteLabels, binder: str, authored: Any = None) -> str:
            if authored is None and binder.startswith("%"):
                scope.anonymous_count += 1
                return f"#{scope.anonymous_count}"
            label = binder if authored is None else authored
            scope.named_counts[label] = scope.named_counts.get(label, 0) + 1
            escaped = escape(label)
            return escaped if scope.named_counts[label] == 1 else f"{escaped}#{scope.named_counts[label]}"

        def pure_value(node: Any) -> bool:
            if not isinstance(node, Mapping):
                self.fail("node_kind", "value must be an object")
            kind = node.get("k")
            if kind in {"perform", "call"}:
                self.fail("effect_in_value", "effectful value is outside a binding", node)
            if kind == "block":
                has = body_effect(node["body"])
                if has:
                    self.fail("effect_in_value", "effectful block is outside a binding", node)
                return False
            if kind == "select":
                pure_value(node["cond"])
                effect = False
                for branch_name in ("then", "else"):
                    branch = node[branch_name]
                    for row in branch["prefix"]:
                        if bound_effect(row["value"]):
                            effect = True
                    pure_value(branch["value"])
                if effect:
                    self.fail("effect_in_value", "effectful select is outside a binding", node)
                return False
            for child in self._value_children(node):
                pure_value(child)
            return False

        def bound_effect(node: Any) -> bool:
            if not isinstance(node, Mapping):
                self.fail("node_kind", "bound value must be an object")
            kind = node.get("k")
            if kind == "perform":
                for child in self._effect_children(node):
                    pure_value(child)
                return True
            if kind == "call":
                for argument in node["args"]:
                    pure_value(argument)
                return self.effectful[node["callee"]]
            return value_effect(node)

        def value_effect(node: Any) -> bool:
            if not isinstance(node, Mapping):
                self.fail("node_kind", "value must be an object")
            kind = node.get("k")
            if kind == "block":
                return body_effect(node["body"])
            if kind == "select":
                pure_value(node["cond"])
                has_effect = False
                for branch_name in ("then", "else"):
                    branch = node[branch_name]
                    for row in branch["prefix"]:
                        has_effect = bound_effect(row["value"]) or has_effect
                    pure_value(branch["value"])
                return has_effect
            for child in self._value_children(node):
                pure_value(child)
            return False

        def body_effect(node: Any) -> bool:
            kind = node["k"]
            if kind == "let":
                has = bound_effect(node["value"])
                rest = body_effect(node["body"])
                return has or rest
            if kind == "if":
                pure_value(node["cond"])
                left = body_effect(node["then"])
                right = body_effect(node["else"])
                return left or right
            if kind == "case":
                pure_value(node["subject"])
                any_effect = False
                for arm in node["arms"]:
                    any_effect = body_effect(arm["body"]) or any_effect
                return any_effect
            if kind == "join":
                body = body_effect(node["body"])
                cont = body_effect(node["cont"])
                return body or cont
            if kind == "loop":
                pure_value(node["budget"])
                pure_value(node["init"])
                body = body_effect(node["body"])
                exhausted = node["exhausted"] is not None and body_effect(node["exhausted"])
                return body or exhausted
            if kind in {"halt", "done"}:
                pure_value(node["value"])
                return False
            if kind in {"jump", "continue"}:
                for argument in node["args"]:
                    pure_value(argument)
                return False
            self.fail("node_kind", f"unknown body node kind {kind!r}", node)

        def walk_value(owner: str, node: Mapping[str, Any], prefix: tuple[str, ...]) -> None:
            kind = node["k"]
            if kind == "select":
                for branch_name in ("then", "else"):
                    branch = node[branch_name]
                    branch_prefix = (*prefix, branch_name)
                    scope = _SiteLabels()
                    for row in branch["prefix"]:
                        walk_bound(owner, row["name"], row.get("label"), row["value"], branch_prefix, scope)
                    walk_value(owner, branch["value"], branch_prefix)
            elif kind == "block":
                walk_body(owner, node["body"], (*prefix, "block"), _SiteLabels())

        def walk_bound(owner: str, binder: str, authored: Any, value: Mapping[str, Any], prefix: tuple[str, ...], scope: _SiteLabels) -> None:
            kind = value["k"]
            if kind == "perform":
                site = " / ".join((*prefix, next_label(scope, binder, authored)))
                expected_performs[id(value)] = (owner, site)
            elif kind == "call":
                callee = value["callee"]
                if self.effectful.get(callee, False):
                    label = next_label(scope, binder, authored)
                    expected_frames[id(value)] = " / ".join((*prefix, f"{label}={callee}"))
            elif value_effect(value):
                label = next_label(scope, binder, authored)
                walk_value(owner, value, (*prefix, label))

        def walk_body(owner: str, body: Mapping[str, Any], prefix: tuple[str, ...], scope: _SiteLabels) -> None:
            while body["k"] == "let":
                walk_bound(owner, body["name"], body.get("label"), body["value"], prefix, scope)
                body = body["body"]
            kind = body["k"]
            if kind == "if":
                walk_body(owner, body["then"], (*prefix, "then"), _SiteLabels())
                walk_body(owner, body["else"], (*prefix, "else"), _SiteLabels())
            elif kind == "case":
                for arm in body["arms"]:
                    walk_body(owner, arm["body"], (*prefix, arm["variant"]), _SiteLabels())
            elif kind == "join":
                if body_effect(body["body"]):
                    param_name = body["params"][0][0]
                    label = next_label(scope, param_name, body.get("label"))
                    walk_body(owner, body["body"], (*prefix, label, "body"), _SiteLabels())
                walk_body(owner, body["cont"], prefix, scope)
            elif kind == "loop":
                in_body = body_effect(body["body"])
                exhausted = body["exhausted"]
                in_exhausted = exhausted is not None and body_effect(exhausted)
                if in_body or in_exhausted:
                    label = next_label(scope, body["param"], body.get("label"))
                    segment = f"loop:{label}"
                    if in_body:
                        walk_body(owner, body["body"], (*prefix, f"{segment}[*]"), _SiteLabels())
                    if in_exhausted:
                        walk_body(owner, exhausted, (*prefix, segment, "exhausted"), _SiteLabels())

        # Effect detection is deliberately a full traversal before any label
        # ordinal is assigned, so short-circuiting cannot hide a call edge.
        for name, definition in self.definitions.items():
            body_effect(definition["body"])
        body_effect(self.tree["body"])

        walk_body(self.tree["entry"], self.tree["body"], (), _SiteLabels())
        for name in self._definition_order():
            walk_body(name, self.definitions[name]["body"], (), _SiteLabels())

        expected_rows: list[list[str]] = []
        by_owner: dict[str, set[str]] = {}
        persisted_by_owner: dict[str, set[str]] = {}
        for node in self.performs.get(self.tree["entry"], []):
            owner, site = expected_performs[id(node)]
            persisted = node.get("site")
            if isinstance(persisted, str):
                if persisted in persisted_by_owner.setdefault(owner, set()):
                    self.fail("site_duplicate", "perform site is duplicated within its definition", node)
                persisted_by_owner[owner].add(persisted)
            if site in by_owner.setdefault(owner, set()):
                self.fail("site_duplicate", "perform site is duplicated within its definition", node)
            by_owner[owner].add(site)
            if node.get("site") != site:
                rule = "site_missing" if "site" not in node else "site_mismatch"
                self.fail(rule, "perform site does not match its definition-local path", node)
            expected_rows.append([owner, site])
        for name in self._definition_order():
            for node in self.performs.get(name, []):
                owner, site = expected_performs[id(node)]
                persisted = node.get("site")
                if isinstance(persisted, str):
                    if persisted in persisted_by_owner.setdefault(owner, set()):
                        self.fail("site_duplicate", "perform site is duplicated within its definition", node)
                    persisted_by_owner[owner].add(persisted)
                if site in by_owner.setdefault(owner, set()):
                    self.fail("site_duplicate", "perform site is duplicated within its definition", node)
                by_owner[owner].add(site)
                if node.get("site") != site:
                    rule = "site_missing" if "site" not in node else "site_mismatch"
                    self.fail(rule, "perform site does not match its definition-local path", node)
                expected_rows.append([owner, site])
        for owner, calls in self.calls.items():
            for call in calls:
                expected = expected_frames.get(id(call))
                if expected is None:
                    if "frame" in call:
                        self.fail("frame_mismatch", "pure call cannot carry an effect frame", call)
                elif call.get("frame") != expected:
                    self.fail("frame_missing" if "frame" not in call else "frame_mismatch", "call frame does not match its definition-local path", call)
        sites = self.tree["sites"]
        if not isinstance(sites, list) or not self._same(sites, expected_rows):
            self.fail("site_table", "site table does not bijectively match perform nodes")
        self.site_expectations = [(row[0], row[1]) for row in expected_rows]

    def _definition_order(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def visit(owner: str) -> None:
            for call in self.calls.get(owner, []):
                callee = call.get("callee")
                if not isinstance(callee, str) or callee not in self.definitions or callee in seen:
                    continue
                seen.add(callee)
                ordered.append(callee)
                visit(callee)

        visit(self.tree["entry"])
        ordered.extend(sorted(set(self.definitions) - seen))
        return ordered

    def _validate_json(self, value: Any, *, depth: int = 0) -> None:
        if depth > 256:
            self.fail("program_shape", "closed program nesting exceeds the limit")
        if value is None or type(value) in {str, bool, int}:
            return
        if type(value) is float:
            if not math.isfinite(value):
                self.fail("nonfinite_json", "closed program contains a non-finite number")
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                if not isinstance(key, str):
                    self.fail("program_shape", "JSON object keys must be strings")
                self._validate_json(item, depth=depth + 1)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                self._validate_json(item, depth=depth + 1)
            return
        self.fail("program_shape", "closed program contains a non-JSON value")

    def _mapping(self, value: Any, rule: str) -> dict[str, Any]:
        if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
            self.fail(rule, f"{rule.replace('_', ' ')} must be a string-keyed object")
        return dict(value)

    def _canonical(self, value: Any) -> str:
        try:
            return canonical_json_for_pure_value(value)
        except (TypeError, ValueError, RecursionError) as exc:
            self.fail("nonfinite_json", f"value is not canonical JSON: {exc}")

    def _same(self, left: Any, right: Any) -> bool:
        return self._canonical(left) == self._canonical(right)

    def _validate_type_table(self) -> None:
        for name, descriptor in self.types.items():
            if not isinstance(name, str) or not name:
                self.fail("type_table", "type names must be non-empty strings")
            self._validate_descriptor(descriptor)
            descriptor_name = descriptor.get("name") if isinstance(descriptor, Mapping) else None
            if descriptor_name != name:
                self.fail("nominal_definition", f"type table row {name!r} has a different nominal name")

    def _validate_descriptor(self, descriptor: Any, *, node: Any = None) -> None:
        try:
            validate_compiler_normalized_type_descriptor(descriptor)
        except (TypeError, ValueError, RecursionError) as exc:
            self.fail("type_descriptor", f"invalid normalized descriptor: {exc}", node)
        kind = descriptor["kind"]
        if kind == "primitive" and descriptor["name"] not in COMPILER_PRIMITIVE_TYPE_NAMES:
            self.fail("type_mismatch", f"unknown compiler primitive {descriptor['name']!r}", node)
        if kind in {"record", "union", "enum", "path"}:
            name = descriptor["name"]
            self._validate_runtime_identity_arguments(name, node=node)
            registered = self.types.get(name)
            if registered is None or not self._same(descriptor, registered):
                self.fail("nominal_definition", f"nominal type {name!r} has no exact type-table definition", node)
        if kind == "variant_case":
            self._validate_runtime_identity_arguments(descriptor["union_name"], node=node)
            union = self.types.get(descriptor["union_name"])
            if not isinstance(union, Mapping) or union.get("kind") != "union":
                self.fail("nominal_definition", "variant case has no registered union definition", node)
            variant = next((row for row in union["variants"] if row["name"] == descriptor["variant"]), None)
            if variant is None or not self._same(descriptor["fields"], variant["fields"]):
                self.fail("nominal_definition", "variant case differs from its registered union variant", node)
        kind = descriptor["kind"]
        if kind in {"optional", "list"}:
            self._validate_descriptor(descriptor["item"], node=node)
        elif kind == "map":
            self._validate_descriptor(descriptor["key"], node=node)
            self._validate_descriptor(descriptor["value"], node=node)
        elif kind == "record":
            for field in descriptor["fields"]:
                self._validate_descriptor(field["type"], node=node)
        elif kind == "union":
            for variant in descriptor["variants"]:
                for field in variant["fields"]:
                    self._validate_descriptor(field["type"], node=node)
        elif kind == "variant_case":
            for field in descriptor["fields"]:
                self._validate_descriptor(field["type"], node=node)

    def _validate_runtime_identity_arguments(self, identity: str, *, node: Any = None) -> None:
        """Validate materialized nominal arguments hidden in runtime identities."""

        try:
            parsed = _parse_identity(identity)
        except (TypeError, ValueError, RecursionError) as exc:
            self.fail("type_descriptor", f"runtime nominal identity is invalid: {exc}", node)

        def render_runtime(value: Any) -> str:
            if isinstance(value, str):
                return value
            if not isinstance(value, Mapping):
                self.fail("type_descriptor", "runtime applied identity is malformed", node)
            if set(value) == {"head", "args"}:
                args = [render_runtime(argument) for argument in value["args"]]
                if value["head"] == "Map":
                    return f"Map[{args[0]},{args[1]}]"
                return f"{value['head']}[{' '.join(args)}]"
            if set(value) == {"owner", "member"} and value["member"] == "variant":
                return f"{render_runtime(value['owner'])}.variant"
            self.fail("type_descriptor", "runtime applied identity has invalid fields", node)

        def visit(value: Any, *, top: bool) -> None:
            if isinstance(value, str):
                if value.startswith("RunRefResult$"):
                    if _GENERATED_RESULT_RE.fullmatch(value) is None or value not in self.types:
                        self.fail("run_ref_origin", f"generated run-ref identity {value!r} is malformed or unregistered", node)
                elif not top and value not in COMPILER_PRIMITIVE_TYPE_NAMES and value not in self.types:
                    self.fail("nominal_definition", f"applied type argument {value!r} has no type-table definition", node)
                return
            if not isinstance(value, Mapping):
                self.fail("type_descriptor", "runtime applied identity is malformed", node)
            if set(value) == {"head", "args"} and isinstance(value.get("args"), list):
                if (
                    not top
                    and value["head"] not in {"List", "Optional", "Map"}
                    and render_runtime(value) not in self.types
                ):
                    self.fail(
                        "nominal_definition",
                        f"applied type argument {render_runtime(value)!r} has no type-table definition",
                        node,
                    )
                for argument in value["args"]:
                    visit(argument, top=False)
                return
            if set(value) == {"owner", "member"} and value.get("member") == "variant":
                visit(value["owner"], top=False)
                return
            self.fail("type_descriptor", "runtime applied identity has invalid fields", node)

        visit(parsed, top=True)

    def _validate_configurations(self) -> dict[str, Any]:
        config = self._mapping(self.tree.get("configuration"), "configuration_scope")
        expected = {"commands", "providers", "prompts", "imports"}
        if set(config) != expected:
            self.fail("configuration_scope", "root configuration has missing or extra maps")
        imports = self._mapping(config["imports"], "configuration_scope")
        for digest, row in imports.items():
            if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
                self.fail("configuration_scope", "import configuration key is not a canonical digest")
            if not isinstance(row, Mapping) or set(row) != {"commands", "providers", "prompts"}:
                self.fail("configuration_scope", "import configuration has invalid maps")
            for field in ("commands", "providers", "prompts"):
                if not isinstance(row[field], Mapping):
                    self.fail("configuration_scope", f"import configuration {field} must be an object")
            self._validate_resolved_extern_rows(row)
            actual = "sha256:" + sha256(self._canonical(row).encode("utf-8")).hexdigest()
            if actual != digest:
                self.fail("configuration_scope", "import configuration digest does not match its row")
        for field in ("commands", "providers", "prompts"):
            if not isinstance(config[field], Mapping):
                self.fail("configuration_scope", f"root configuration {field} must be an object")
        self._validate_resolved_extern_rows(config)
        return config

    def _validate_resolved_extern_rows(self, scope: Mapping[str, Any]) -> None:
        commands = scope.get("commands")
        providers = scope.get("providers")
        prompts = scope.get("prompts")
        if not isinstance(commands, Mapping) or not isinstance(providers, Mapping) or not isinstance(prompts, Mapping):
            self.fail("configuration_scope", "resolved command, provider and prompt rows must be objects")
        self._validate_command_configuration_rows(commands)
        for name, row in providers.items():
            if (
                not isinstance(name, str)
                or not name
                or not isinstance(row, Mapping)
                or set(row) != {"provider_id"}
                or not isinstance(row["provider_id"], str)
                or not row["provider_id"].strip()
            ):
                self.fail("configuration_scope", "resolved provider row must contain exactly one provider_id")
        for name, row in prompts.items():
            if not isinstance(name, str) or not name or not isinstance(row, Mapping):
                self.fail("configuration_scope", "resolved prompt row is malformed")
            source_kind = row.get("source_kind")
            expected = {"source_kind", "path"} | ({"asset_base"} if source_kind == "asset_file" else set())
            if (
                not isinstance(source_kind, str)
                or source_kind not in {"asset_file", "input_file"}
                or set(row) != expected
                or not isinstance(row.get("path"), str)
                or not row["path"].strip()
                or (source_kind == "asset_file" and (not isinstance(row.get("asset_base"), str) or not row["asset_base"]))
            ):
                self.fail("configuration_scope", "resolved prompt row does not match its exact source shape")

    def _validate_command_configuration_rows(self, commands: Mapping[str, Any]) -> None:
        for lookup_name, row in commands.items():
            if not isinstance(lookup_name, str) or not lookup_name.strip() or not isinstance(row, Mapping):
                self.fail("configuration_scope", "command configuration key or row is malformed")
            kind = row.get("kind")
            if not isinstance(kind, str) or kind not in {"external_tool", "certified_adapter"}:
                self.fail("configuration_scope", "command configuration kind is unsupported")
            expected = _COMMAND_COMMON_FIELDS | (
                _COMMAND_CERTIFIED_FIELDS if kind == "certified_adapter" else frozenset()
            )
            if set(row) != expected:
                self.fail("configuration_scope", "command configuration row has missing or extra fields")
            if not isinstance(row.get("name"), str):
                self.fail("configuration_scope", "command configuration name must be a string")
            stable = row.get("stable_command")
            if not isinstance(stable, list) or not stable or any(not isinstance(token, str) or not token for token in stable):
                self.fail("configuration_scope", "command stable tokens must be a nonempty string array")
            if type(row.get("must_not_repeat")) is not bool:
                self.fail("configuration_scope", "command repeat policy must be a boolean")
            closure = row.get("closure")
            if not isinstance(closure, list):
                self.fail("configuration_scope", "command closure must be a canonical array")
            closure_pairs: list[tuple[str, str]] = []
            for closure_row in closure:
                if not isinstance(closure_row, Mapping) or set(closure_row) != {"base", "path"}:
                    self.fail("configuration_scope", "command closure row must contain base and path")
                base, path = closure_row["base"], closure_row["path"]
                if not isinstance(base, str) or base not in {"workspace", "absolute", "package:orchestrator"} or not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
                    self.fail("configuration_scope", "command closure path is malformed")
                absolute = path.startswith("/")
                if (base == "absolute") != absolute:
                    self.fail("configuration_scope", "command closure base does not match path absoluteness")
                body = path[1:] if absolute else path
                segments = body.split("/") if body and path != "." else []
                if any(segment in {"", "."} for segment in segments):
                    self.fail("configuration_scope", "command closure path is not normalized")
                normalized = ("/" if absolute else "") + "/".join(segments)
                if not segments and not absolute:
                    normalized = "."
                if not segments and absolute:
                    normalized = "/"
                if path != normalized:
                    self.fail("configuration_scope", "command closure path is not canonical")
                closure_pairs.append((base, path))
            if closure_pairs != sorted(set(closure_pairs)):
                self.fail("configuration_scope", "command closure rows must be unique and canonically ordered")
            for field in (
                "retirement_class",
                "retirement_label",
                "replacement_surface",
                "bridge_owner",
                "expiry_condition",
                "retirement_status",
            ):
                if row[field] is not None and not isinstance(row[field], str):
                    self.fail("configuration_scope", f"command {field} must be a string or null")
            if not isinstance(row.get("evidence_refs"), list) or any(not isinstance(value, str) for value in row["evidence_refs"]):
                self.fail("configuration_scope", "command evidence_refs must be an array of strings")
            if kind != "certified_adapter":
                continue
            for field in ("input_contract", "path_safety"):
                if not isinstance(row[field], Mapping):
                    self.fail("configuration_scope", f"certified command {field} must be an object")
            for field in (
                "output_type_name",
                "source_map_behavior",
            ):
                if not isinstance(row[field], str):
                    self.fail("configuration_scope", f"certified command {field} must be a string")
            for field in (
                "effects",
                "fixture_ids",
                "negative_fixture_ids",
                "artifact_contracts",
                "state_writes",
                "error_codes",
            ):
                if not isinstance(row[field], list) or any(not isinstance(value, str) for value in row[field]):
                    self.fail("configuration_scope", f"certified command {field} must be an array of strings")
            for field in ("behavior_class", "owner_module", "replacement_path", "invocation_protocol"):
                if row[field] is not None and not isinstance(row[field], str):
                    self.fail("configuration_scope", f"certified command {field} must be a string or null")
            signature = row["input_signature"]
            if not isinstance(signature, list):
                self.fail("configuration_scope", "certified command input_signature must be an array")
            for signature_row in signature:
                if not isinstance(signature_row, Mapping) or set(signature_row) != {"name", "type_name", "required", "transport_key"}:
                    self.fail("configuration_scope", "certified command input signature row is malformed")
                if any(not isinstance(signature_row[field], str) for field in ("name", "type_name", "transport_key")) or type(signature_row["required"]) is not bool:
                    self.fail("configuration_scope", "certified command input signature row has invalid value types")
            for field, required in (
                ("transition_binding", {"transition_name", "resource_kind", "contract_role", "backend_selector"}),
                ("view_binding", {"view_name", "renderer_id", "renderer_version", "contract_role"}),
            ):
                nested = row[field]
                if nested is None:
                    continue
                if not isinstance(nested, Mapping) or set(nested) != required:
                    self.fail("configuration_scope", f"certified command {field} has invalid fields")
                text_fields = required - ({"renderer_version"} if field == "view_binding" else set())
                if any(not isinstance(nested[name], str) for name in text_fields):
                    self.fail("configuration_scope", f"certified command {field} has invalid value types")
                if field == "view_binding" and type(nested["renderer_version"]) is not int:
                    self.fail("configuration_scope", "certified command view renderer_version must be an integer")
            promoted = row["declared_promoted_fields"]
            if (
                not isinstance(promoted, list)
                or any(not isinstance(field, str) for field in promoted)
                or promoted != sorted(set(promoted))
            ):
                self.fail("configuration_scope", "certified command promoted fields are not canonical")

    def _document_keys_match_signature(self, signature: list[Any], document: list[Any]) -> bool:
        """Check the ordered projection of selected signature names, preserving duplicate rows."""

        if any(not isinstance(row, Mapping) for row in signature):
            return False
        if any(not isinstance(row, (list, tuple)) or len(row) != 2 or not isinstance(row[0], str) for row in document):
            return False
        actual_keys = [row[0] for row in document]
        required_names = {row["name"] for row in signature if row["required"]}
        last_index = {row["name"]: index for index, row in enumerate(signature)}
        states: set[tuple[int, tuple[tuple[str, bool], ...]]] = {(0, ())}
        for index, row in enumerate(signature):
            next_states: set[tuple[int, tuple[tuple[str, bool], ...]]] = set()
            for document_index, assignments_tuple in states:
                assignments = dict(assignments_tuple)
                name = row["name"]
                choices = (assignments[name],) if name in assignments else ((True,) if name in required_names else (False, True))
                for selected in choices:
                    next_document_index = document_index
                    if selected:
                        if document_index >= len(actual_keys) or actual_keys[document_index] != row["transport_key"]:
                            continue
                        next_document_index += 1
                    next_assignments = dict(assignments)
                    if name in next_assignments:
                        del next_assignments[name]
                    if last_index[name] > index:
                        next_assignments[name] = selected
                    next_states.add((next_document_index, tuple(sorted(next_assignments.items()))))
            states = next_states
            if not states:
                return False
        return any(document_index == len(actual_keys) for document_index, _ in states)

    def _scope_for(self, definition: Mapping[str, Any], *, node: Any = None) -> dict[str, Any]:
        selected = definition.get("configuration")
        if selected is None:
            return self.root_configuration
        if not isinstance(selected, str):
            self.fail("configuration_scope", "definition configuration selector must be a digest", node)
        row = self.root_configuration["imports"].get(selected)
        if not isinstance(row, Mapping):
            self.fail("configuration_scope", "definition selects a missing imported configuration", node)
        return dict(row)

    def _validate_definition_keys(self) -> None:
        keys: dict[str, list[Any]] = {}
        for name, definition in self.definitions.items():
            key = definition.get("key")
            self._validate_key_shape(key)
            try:
                derived = canonical_callee_name_from_key(key)
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("definition_key", f"definition key cannot name its definition: {exc}", definition)
            if derived != name:
                self.fail("definition_key", "definition name does not match its canonical key", definition)
            encoded = self._canonical(key)
            previous = keys.get(derived)
            if previous is not None and self._canonical(previous) != encoded:
                self.fail("definition_key", "one canonical name has conflicting definition keys", definition)
            keys[derived] = key
        self._definition_keys = keys

    def _validate_key_shape(self, key: Any, *, nested: bool = False) -> None:
        if not isinstance(key, list) or len(key) != 9:
            self.fail("definition_key", "definition key must have exactly nine components")
        module, kind, declaration, types, procedures, workflows, values, captures, residual = key
        if not isinstance(module, str) or not module or not isinstance(kind, str) or kind not in {"procedure", "workflow"}:
            self.fail("definition_key", "definition key has an invalid module or callable kind")
        self._validate_declaration_id([module, kind, declaration])
        for index, rows in ((3, types), (4, procedures), (5, workflows), (6, values)):
            if not isinstance(rows, list):
                self.fail("definition_key", f"definition key component {index} must be an array")
            previous_selector: tuple[int, Any] | None = None
            seen: set[str] = set()
            expected_width = 3 if index == 6 else 2
            for row in rows:
                if not isinstance(row, list) or len(row) != expected_width:
                    self.fail("definition_key", f"definition key component {index} has a malformed row")
                selector = row[0]
                order = self._formal_order(selector)
                encoded_selector = self._canonical(selector)
                if encoded_selector in seen or (previous_selector is not None and order <= previous_selector):
                    self.fail("definition_key", "definition key rows are duplicate or out of formal order")
                seen.add(encoded_selector)
                previous_selector = order
                if index == 3:
                    self._validate_key_type(row[1])
                elif index == 4:
                    self._validate_pref(row[1], enclosing_key=key, reference_path=[row[0]])
                elif index == 5:
                    self._validate_wref(row[1], enclosing_key=key)
                else:
                    self._validate_key_type(row[1])
                    self._validate_closed_value(row[2])
        if not isinstance(captures, list):
            self.fail("definition_key", "capture prefix must be an array")
        for capture in captures:
            if not isinstance(capture, Mapping) or set(capture) != {"type", "routes"}:
                self.fail("definition_key", "capture row must contain exactly type and routes")
            self._validate_key_type(capture["type"])
            routes = capture["routes"]
            if not isinstance(routes, list) or not routes:
                self.fail("definition_key", "capture routes must be a nonempty array")
            canonical_routes = [self._canonical(route) for route in routes]
            if canonical_routes != sorted(set(canonical_routes)):
                self.fail("definition_key", "capture routes must be unique and canonically ordered")
            for route in routes:
                self._validate_capture_route(route)
        if not isinstance(residual, Mapping) or set(residual) != {"params", "result"}:
            self.fail("definition_key", "residual signature must contain exactly params and result")
        if not isinstance(residual["params"], list):
            self.fail("definition_key", "residual signature params must be an array")
        for descriptor in [*residual["params"], residual["result"]]:
            self._validate_key_type(descriptor, runtime_only=True)

    def _formal_order(self, selector: Any) -> tuple[int, Any]:
        if isinstance(selector, str) and selector:
            return (1, selector)
        if (
            isinstance(selector, list)
            and len(selector) == 2
            and selector[0] == "local"
            and type(selector[1]) is int
            and selector[1] >= 0
        ):
            return (0, selector[1])
        self.fail("definition_key", "formal selector must be a name or nonnegative local index")

    def _validate_declaration_id(self, value: Any) -> None:
        if not isinstance(value, list) or len(value) != 3:
            self.fail("definition_key", "declaration identity must be a three-element array")
        module, kind, declaration = value
        if not isinstance(module, str) or not module or not isinstance(kind, str) or kind not in {"procedure", "workflow"}:
            self.fail("definition_key", "declaration identity has invalid module or kind")
        if isinstance(declaration, str) and declaration:
            return
        if (
            isinstance(declaration, Mapping)
            and set(declaration) == {"owner", "name", "ordinal"}
            and isinstance(declaration["name"], str)
            and declaration["name"]
            and type(declaration["ordinal"]) is int
            and declaration["ordinal"] >= 0
        ):
            owner = declaration["owner"]
            if (
                isinstance(owner, list)
                and len(owner) == 3
                and isinstance(owner[0], str)
                and owner[0]
                and owner[1] in {"procedure", "workflow"}
                and isinstance(owner[2], str)
                and owner[2]
            ):
                return
        self.fail("definition_key", "declaration identity has an invalid declaration")

    def _validate_key_type(self, descriptor: Any, *, runtime_only: bool = False) -> None:
        if not isinstance(descriptor, Mapping):
            self.fail("definition_key", "key type must be an object")
        kind = descriptor.get("kind")
        if kind == "procedure-reference" or kind == "workflow-reference":
            if runtime_only:
                self.fail("definition_key", "reference types cannot appear in runtime signatures")
            if set(descriptor) != {"kind", "signature"}:
                self.fail("definition_key", "reference type has invalid fields")
            self._validate_signature_shape(descriptor["signature"], runtime_only=False)
            return
        if kind == "run-ref-result":
            if set(descriptor) != {"kind", "signature"}:
                self.fail("definition_key", "run-ref marker has invalid fields")
            # S is checked against the inventory derived from actual run_ref
            # nodes after typed traversal. Parsing a second, weaker S grammar
            # here would allow nominal strings to stand in for type proof.
            if not isinstance(descriptor["signature"], Mapping):
                self.fail("definition_key", "run-ref marker signature must be an object")
            self._validate_json(descriptor["signature"])
            return
        try:
            normalized = self._neutralize_key_type(descriptor)
            validate_compiler_normalized_type_descriptor(normalized)
        except (TypeError, ValueError, RecursionError) as exc:
            self.fail("definition_key", f"invalid projected key type: {exc}")
        self._validate_key_primitive_names(normalized)

    def _validate_key_primitive_names(self, descriptor: Any) -> None:
        if not isinstance(descriptor, Mapping):
            return
        kind = descriptor.get("kind")
        if kind == "primitive":
            if descriptor.get("name") not in COMPILER_PRIMITIVE_TYPE_NAMES:
                self.fail("definition_key", f"unknown compiler primitive {descriptor.get('name')!r}")
        elif kind in {"optional", "list"}:
            self._validate_key_primitive_names(descriptor.get("item"))
        elif kind == "map":
            self._validate_key_primitive_names(descriptor.get("key"))
            self._validate_key_primitive_names(descriptor.get("value"))
        elif kind in {"record", "variant_case"}:
            for row in descriptor.get("fields", []):
                if isinstance(row, Mapping):
                    self._validate_key_primitive_names(row.get("type"))
        elif kind == "union":
            for variant in descriptor.get("variants", []):
                if isinstance(variant, Mapping):
                    for row in variant.get("fields", []):
                        if isinstance(row, Mapping):
                            self._validate_key_primitive_names(row.get("type"))

    def _neutralize_key_type(self, descriptor: Any) -> Any:
        """Validate projected grammar while deferring generated S equality."""

        if not isinstance(descriptor, Mapping):
            return descriptor
        kind = descriptor.get("kind")
        if kind == "run-ref-result":
            return {"kind": "primitive", "name": "String"}
        if kind in {"procedure-reference", "workflow-reference"}:
            return {"kind": "primitive", "name": "String"}
        result = deepcopy(dict(descriptor))
        if kind in {"record", "union", "enum"} and "name" in result:
            try:
                result["name"] = _render_key_identity(result["name"])
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("definition_key", f"invalid projected nominal identity: {exc}")
        elif kind == "variant_case" and "union_name" in result:
            try:
                result["union_name"] = _render_key_identity(result["union_name"])
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("definition_key", f"invalid projected union identity: {exc}")
        if kind in {"optional", "list"} and "item" in result:
            result["item"] = self._neutralize_key_type(result["item"])
        elif kind == "map":
            for field in ("key", "value"):
                if field in result:
                    result[field] = self._neutralize_key_type(result[field])
        elif kind in {"record", "variant_case"}:
            for row in result.get("fields", []):
                if isinstance(row, Mapping) and "type" in row:
                    row["type"] = self._neutralize_key_type(row["type"])
        elif kind == "union":
            for variant in result.get("variants", []):
                if isinstance(variant, Mapping):
                    for row in variant.get("fields", []):
                        if isinstance(row, Mapping) and "type" in row:
                            row["type"] = self._neutralize_key_type(row["type"])
        return result

    def _validate_signature_shape(self, signature: Any, *, runtime_only: bool) -> None:
        if not isinstance(signature, Mapping) or set(signature) != {"params", "result"}:
            self.fail("definition_key", "reference signature must contain params and result")
        if not isinstance(signature["params"], list):
            self.fail("definition_key", "reference signature params must be an array")
        for descriptor in [*signature["params"], signature["result"]]:
            self._validate_key_type(descriptor, runtime_only=runtime_only)

    def _validate_capture_route(self, route: Any) -> None:
        if not isinstance(route, list) or not route or not isinstance(route[0], str):
            self.fail("definition_key", "capture route must be a nonempty tagged array")
        tag = route[0]
        if tag == "parameter" and len(route) == 2 and isinstance(route[1], str) and route[1]:
            return
        if tag == "local" and len(route) == 2 and type(route[1]) is int and route[1] >= 0:
            return
        if tag == "reference" and len(route) == 3 and isinstance(route[1], list) and route[1]:
            if any(not self._is_formal_selector(item) for item in route[1]):
                self.fail("definition_key", "reference capture path contains an invalid formal")
            terminal = route[2]
            if isinstance(terminal, list) and len(terminal) == 2:
                if terminal[0] == "parameter" and isinstance(terminal[1], str) and terminal[1]:
                    return
                if terminal[0] == "local" and self._is_local_selector(terminal[1]):
                    return
        if tag == "context" and len(route) == 4:
            hops, native_formal, fields = route[1:]
            if not isinstance(hops, list) or not hops or not isinstance(native_formal, str) or not native_formal:
                self.fail("definition_key", "context route has invalid hops or native formal")
            for hop in hops:
                if not isinstance(hop, list) or len(hop) != 2:
                    self.fail("definition_key", "context route hop is malformed")
                self._validate_declaration_id(hop[0])
                if type(hop[1]) is not int or hop[1] < 0:
                    self.fail("definition_key", "context route occurrence must be nonnegative")
            if not isinstance(fields, list):
                self.fail("definition_key", "context route fields must be an array")
            seen: set[str] = set()
            encodings = []
            for pair in fields:
                if not isinstance(pair, list) or len(pair) != 2 or any(
                    not isinstance(path, list) or any(not isinstance(segment, str) or not segment for segment in path)
                    for path in pair
                ):
                    self.fail("definition_key", "context route field path pair is malformed")
                encoded = self._canonical(pair)
                if encoded in seen:
                    self.fail("definition_key", "context route field pairs are duplicated")
                seen.add(encoded)
                encodings.append(encoded)
            if encodings != sorted(encodings):
                self.fail("definition_key", "context route field pairs are not canonically ordered")
            return
        self.fail("definition_key", "capture route uses an unsupported shape")

    def _check_context_capture_routes(self) -> None:
        """Bind context routes to real calls and the checked terminal boundary."""

        for owner, definition in self.definitions.items():
            key = self._definition_keys[owner]
            captures = key[7]
            for capture_index, capture in enumerate(captures):
                for route in capture["routes"]:
                    if route[0] != "context":
                        continue
                    hops, native_formal, field_pairs = route[1:]
                    current_owner = owner
                    current_capture_index = capture_index
                    capture_type = capture["type"]
                    for hop_index, hop in enumerate(hops):
                        declaration_id, occurrence = hop
                        matching_calls: list[tuple[dict[str, Any], str]] = []
                        for call in self.semantic_calls.get(current_owner, ()):
                            callee = call.get("callee")
                            callee_key = self._definition_keys.get(callee) if isinstance(callee, str) else None
                            if isinstance(callee_key, list) and self._same(callee_key[:3], declaration_id):
                                matching_calls.append((call, callee))
                        if occurrence >= len(matching_calls):
                            self.fail("capture_route", "context route hop does not select an actual call", definition)
                        call, callee_name = matching_calls[occurrence]
                        args = call.get("args")
                        origins = self.call_argument_origins.get(id(call), [])
                        target_key = self._definition_keys[callee_name]
                        target_definition = self.definitions[callee_name]
                        if hop_index + 1 < len(hops):
                            suffix = ["context", hops[hop_index + 1 :], native_formal, field_pairs]
                            target_captures = target_key[7]
                            forwarded = [
                                index
                                for index, target_capture in enumerate(target_captures)
                                if self._same(target_capture["type"], capture_type)
                                and any(self._same(candidate, suffix) for candidate in target_capture["routes"])
                            ]
                            if len(forwarded) != 1:
                                self.fail("capture_route", "context route is missing its matching suffix capture", call)
                            target_capture_index = forwarded[0]
                            if (
                                not isinstance(args, list)
                                or target_capture_index >= len(args)
                                or target_capture_index >= len(origins)
                                or origins[target_capture_index] != current_capture_index
                            ):
                                self.fail("capture_route", "context route call does not forward its capture parameter", call)
                            current_owner = callee_name
                            current_capture_index = target_capture_index
                            continue

                        self._check_terminal_context_transfer(
                            call,
                            target_definition,
                            capture_type=capture_type,
                            capture_index=current_capture_index,
                            native_formal=native_formal,
                            field_pairs=field_pairs,
                        )

    def _check_terminal_context_transfer(
        self,
        call: Mapping[str, Any],
        definition: Mapping[str, Any],
        *,
        capture_type: Mapping[str, Any],
        capture_index: int,
        native_formal: str,
        field_pairs: list[Any],
    ) -> None:
        boundary = call.get("boundary")
        if not isinstance(boundary, Mapping):
            self.fail("capture_route", "terminal context transfer requires a checked call boundary", call)
        caller_params = boundary.get("params")
        native_params = definition.get("params")
        if not isinstance(caller_params, list) or not isinstance(native_params, list):
            self.fail("capture_route", "terminal context boundary has no parameter roots", call)
        native_indices = [
            index
            for index, row in enumerate(native_params)
            if isinstance(row, list) and len(row) == 2 and row[0] == native_formal
        ]
        if len(native_indices) != 1:
            self.fail("capture_route", "context route native formal is absent or ambiguous", call)
        native_index = native_indices[0]
        native_root = native_params[native_index]
        args = call.get("args")
        origins = self.call_argument_origins.get(id(call), [])
        if not isinstance(args, list) or not isinstance(native_root, list) or len(native_root) != 2:
            self.fail("capture_route", "terminal context call or native parameter roots are malformed", call)

        input_rows = boundary.get("inputs")
        if not isinstance(input_rows, Mapping):
            self.fail("capture_route", "terminal context boundary has no input projection", call)
        direct = boundary.get("direct")
        if not isinstance(direct, list):
            self.fail("capture_route", "terminal context boundary has no direct-pair table", call)
        candidates: list[list[list[str]]] = []
        for caller_index, caller_root in enumerate(caller_params):
            if (
                caller_index >= len(args)
                or caller_index >= len(origins)
                or origins[caller_index] != capture_index
                or not isinstance(caller_root, list)
                or len(caller_root) != 2
            ):
                continue
            try:
                projected_source = key_type_descriptor(caller_root[1], run_ref_signatures=self.run_ref_signatures)
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("capture_route", f"terminal context source type cannot be projected: {exc}", call)
            if not self._same(projected_source, capture_type):
                continue
            direct_targets = [
                pair[1]
                for pair in direct
                if isinstance(pair, list) and len(pair) == 2 and pair[0] == caller_index
            ]
            if direct_targets and direct_targets != [native_index]:
                continue
            try:
                caller_all = compiled_boundary_rows([(caller_root[0], caller_root[1])]) if direct_targets else [
                    row for row in input_rows["caller"]
                    if isinstance(row, Mapping) and isinstance(row.get("path"), list)
                    and row["path"] and row["path"][0] == caller_root[0]
                ]
                native_all = compiled_boundary_rows([(native_root[0], native_root[1])]) if direct_targets else [
                    row for row in input_rows["callee"]
                    if isinstance(row, Mapping) and isinstance(row.get("path"), list)
                    and row["path"] and row["path"][0] == native_root[0]
                ]
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("capture_route", f"terminal context projection cannot be derived: {exc}", call)
            caller_by_name = {row["name"]: row for row in caller_all}
            native_by_name = {row["name"]: row for row in native_all}
            if not caller_by_name or set(caller_by_name) != set(native_by_name):
                continue

            def relative_path(row: Mapping[str, Any], root_name: str) -> list[str]:
                path = row.get("path")
                if not isinstance(path, list) or not path or path[0] != root_name:
                    self.fail("capture_route", "terminal context projection path has the wrong root", call)
                return path[1:]

            derived_pairs: dict[str, list[list[list[str]]]] = {}
            for wire_name, caller_row in caller_by_name.items():
                native_row = native_by_name[wire_name]
                pair = [relative_path(caller_row, caller_root[0]), relative_path(native_row, native_root[0])]
                derived_pairs[self._canonical(pair)] = pair
            candidate_pairs = sorted(derived_pairs.values(), key=self._canonical)
            if self._same(candidate_pairs, field_pairs):
                candidates.append(candidate_pairs)
        if len(candidates) != 1:
            self.fail("capture_route", "terminal context fields do not identify one captured boundary transfer", call)

    def _validate_pref(
        self,
        reference: Any,
        *,
        enclosing_key: list[Any],
        reference_path: list[Any],
    ) -> None:
        if not isinstance(reference, Mapping) or set(reference) != {"target", "residual", "bound"}:
            self.fail("definition_key", "procedure reference has invalid fields")
        target = reference["target"]
        self._validate_key_shape(target, nested=True)
        if target[1] != "procedure":
            self.fail("definition_key", "procedure reference target is not a procedure key")
        self._validate_signature_shape(reference["residual"], runtime_only=True)
        target_residual = target[8]
        if not self._same(reference["residual"], target_residual):
            self.fail("definition_key", "procedure-reference residual differs from its target key")
        rows = reference["bound"]
        if not isinstance(rows, list):
            self.fail("definition_key", "procedure-reference bound rows must be an array")
        previous = None
        seen: set[str] = set()
        actual: dict[str, list[Any]] = {}
        for row in rows:
            if not isinstance(row, list) or len(row) != 3:
                self.fail("definition_key", "procedure-reference bound row is malformed")
            order = self._formal_order(row[0])
            encoded = self._canonical(row[0])
            if encoded in seen or (previous is not None and order <= previous):
                self.fail("definition_key", "procedure-reference bound rows are duplicate or out of order")
            previous = order
            seen.add(encoded)
            self._validate_key_type(row[1])
            self._validate_binding(
                row[2],
                enclosing_key=enclosing_key,
                reference_path=[*reference_path, row[0]],
            )
            actual[encoded] = row

        capture_map: dict[int, int] = {}
        expected: dict[str, tuple[Any, Any, Any]] = {}

        def add_expected(selector: Any, descriptor: Any, binding: Any) -> None:
            encoded = self._canonical(selector)
            if encoded in expected:
                self.fail("definition_key", "target facts bind one formal through multiple categories")
            expected[encoded] = (selector, descriptor, binding)

        for selector, nested in target[4]:
            add_expected(
                selector,
                {"kind": "procedure-reference", "signature": deepcopy(nested["residual"])},
                {"procedure": nested},
            )
        for selector, nested in target[5]:
            add_expected(
                selector,
                {"kind": "workflow-reference", "signature": deepcopy(nested["target"][8])},
                {"workflow": nested},
            )
        for selector, descriptor, value in target[6]:
            add_expected(selector, descriptor, {"value": value})

        for capture_index, capture in enumerate(target[7]):
            for route in capture["routes"]:
                terminal: list[Any] | None = None
                if route[0] in {"parameter", "local"}:
                    terminal = [route[0], route[1]]
                elif route[0] == "reference":
                    terminal = route[2]
                if terminal is not None:
                    if route[0] == "reference":
                        external_route = ["reference", [*reference_path, *route[1]], terminal]
                    else:
                        external_route = ["reference", reference_path, terminal]
                    matches = [
                        index
                        for index, outer_capture in enumerate(enclosing_key[7])
                        if any(self._same(candidate, external_route) for candidate in outer_capture["routes"])
                        and self._same(outer_capture["type"], capture["type"])
                    ]
                    if len(matches) != 1:
                        self.fail("definition_key", "reference capture route does not identify one enclosing capture")
                    previous_capture = capture_map.get(capture_index)
                    if previous_capture is not None and previous_capture != matches[0]:
                        self.fail("definition_key", "one target capture maps to competing enclosing captures")
                    capture_map[capture_index] = matches[0]
                if route[0] in {"parameter", "local"}:
                    selector = route[1] if route[0] == "parameter" else ["local", route[1]]
                    if capture_index not in capture_map:
                        self.fail("definition_key", "direct reference capture has no enclosing capture mapping")
                    add_expected(selector, capture["type"], {"capture": capture_map[capture_index]})

        if set(actual) != set(expected):
            self.fail("definition_key", "PRef.bound is not a bijection with target binding facts")
        for selector, descriptor, binding in expected.values():
            row = actual[self._canonical(selector)]
            if not self._same(row[1], descriptor):
                self.fail("definition_key", "PRef.bound type differs from its target binding fact")
            expected_binding = deepcopy(binding)
            if "procedure" in expected_binding:
                expected_binding["procedure"] = self._remap_reference_captures(
                    expected_binding["procedure"], capture_map
                )
            if not self._same(row[2], expected_binding):
                self.fail("definition_key", "PRef.bound binding differs from its target binding fact")

        target_name = canonical_callee_name_from_key(target)
        reachable = self.definitions.get(target_name)
        if isinstance(reachable, Mapping):
            if not self._same(reachable.get("key"), target):
                self.fail("definition_key", "reachable procedure-reference target has a different key")

    def _validate_wref(self, reference: Any, *, enclosing_key: list[Any]) -> None:
        if not isinstance(reference, Mapping) or set(reference) != {"target", "externs"}:
            self.fail("definition_key", "workflow reference has invalid fields")
        self._validate_key_shape(reference["target"], nested=True)
        if reference["target"][1] != "workflow":
            self.fail("definition_key", "workflow reference target is not a workflow key")
        externs = reference["externs"]
        if not isinstance(externs, Mapping) or set(externs) != {"providers", "prompts"}:
            self.fail("definition_key", "workflow extern table has invalid fields")
        for category in ("providers", "prompts"):
            rows = externs[category]
            if not isinstance(rows, list):
                self.fail("definition_key", f"workflow {category} externs must be an array")
            previous = None
            seen: set[str] = set()
            for row in rows:
                if not isinstance(row, list) or len(row) != 2:
                    self.fail("definition_key", "workflow extern row is malformed")
                if not isinstance(row[0], str) or not row[0]:
                    self.fail("definition_key", "workflow extern formal must be a nonempty name")
                order = self._formal_order(row[0])
                encoded = self._canonical(row[0])
                if encoded in seen or (previous is not None and order <= previous):
                    self.fail("definition_key", "workflow extern rows are duplicate or out of order")
                previous = order
                seen.add(encoded)
                self._validate_extern_row(category, row[1])

    def _validate_extern_row(self, category: str, row: Any) -> None:
        if not isinstance(row, Mapping):
            self.fail("definition_key", "resolved extern row must be an object")
        if category == "providers":
            if set(row) != {"provider_id"} or not isinstance(row["provider_id"], str) or not row["provider_id"].strip():
                self.fail("definition_key", "provider extern row is invalid")
            return
        source_kind = row.get("source_kind")
        expected = {"source_kind", "path", "asset_base"} if source_kind == "asset_file" else {"source_kind", "path"}
        if (
            set(row) != expected
            or not isinstance(source_kind, str)
            or source_kind not in {"asset_file", "input_file"}
            or not isinstance(row.get("path"), str)
            or not row["path"].strip()
            or (source_kind == "asset_file" and (not isinstance(row.get("asset_base"), str) or not row["asset_base"]))
        ):
            self.fail("definition_key", "prompt extern row is invalid")

    def _validate_binding(
        self,
        binding: Any,
        *,
        enclosing_key: list[Any],
        reference_path: list[Any] | None = None,
    ) -> None:
        if not isinstance(binding, Mapping) or len(binding) != 1:
            self.fail("definition_key", "reference binding must contain one category")
        category, value = next(iter(binding.items()))
        if category == "value":
            self._validate_closed_value(value)
        elif category == "capture":
            if type(value) is not int or value < 0 or value >= len(enclosing_key[7]):
                self.fail("definition_key", "capture binding index is outside the enclosing capture prefix")
        elif category == "procedure":
            self._validate_pref(
                value,
                enclosing_key=enclosing_key,
                reference_path=reference_path or [],
            )
        elif category == "workflow":
            self._validate_wref(value, enclosing_key=enclosing_key)
        else:
            self.fail("definition_key", "reference binding category is unsupported")

    def _remap_reference_captures(
        self,
        reference: Mapping[str, Any],
        capture_map: Mapping[int, int],
    ) -> dict[str, Any]:
        """Move nested reference bindings from a target-key scope to its caller."""

        result = deepcopy(dict(reference))
        for row in result["bound"]:
            binding = row[2]
            if set(binding) == {"capture"}:
                index = binding["capture"]
                if index not in capture_map:
                    self.fail("definition_key", "nested reference capture has no enclosing route")
                binding["capture"] = capture_map[index]
            elif set(binding) == {"procedure"}:
                binding["procedure"] = self._remap_reference_captures(
                    binding["procedure"], capture_map
                )
        return result

    def _is_local_selector(self, value: Any) -> bool:
        return isinstance(value, list) and len(value) == 2 and value[0] == "local" and type(value[1]) is int and value[1] >= 0

    def _is_formal_selector(self, value: Any) -> bool:
        return (isinstance(value, str) and bool(value)) or self._is_local_selector(value)

    def _validate_closed_value(self, value: Any) -> None:
        if not isinstance(value, Mapping) or value.get("k") not in {
            "lit", "name", "field", "record", "inject", "op", "select", "list", "list_map", "path_join", "block"
        }:
            self.fail("definition_key", "closed substitution value is not a closed value node")
        if "@" in value or "label" in value:
            self.fail("definition_key", "closed substitution values cannot retain provenance or labels")
        kind = value["k"]
        if kind == "lit":
            if set(value) != {"k", "v", "type"}:
                self.fail("definition_key", "closed literal has invalid fields")
            self._validate_key_type(value["type"])
        elif kind == "name":
            if set(value) != {"k", "n"} or not isinstance(value["n"], str):
                self.fail("definition_key", "closed name has invalid fields")
        elif kind == "field":
            if set(value) != {"k", "base", "path"} or not isinstance(value["path"], list):
                self.fail("definition_key", "closed field value is malformed")
            self._validate_closed_value(value["base"])
        elif kind in {"record", "inject"}:
            expected = {"k", "type", "fields"} if kind == "record" else {"k", "type", "variant", "fields"}
            if set(value) != expected:
                self.fail("definition_key", "closed aggregate value is malformed")
            self._validate_key_type(value["type"])
            rows = value["fields"]
            if not isinstance(rows, list):
                self.fail("definition_key", "closed aggregate fields must be an array")
            for row in rows:
                if not isinstance(row, list) or len(row) != 2:
                    self.fail("definition_key", "closed aggregate field is malformed")
                self._validate_closed_value(row[1])
        elif kind == "op":
            if set(value) != {"k", "payload", "args"} or not isinstance(value["args"], list):
                self.fail("definition_key", "closed operator value is malformed")
            for child in value["args"]:
                self._validate_closed_value(child)
        elif kind == "select":
            if set(value) != {"k", "cond", "then", "else"}:
                self.fail("definition_key", "closed select value is malformed")
            self._validate_closed_value(value["cond"])
            for branch in (value["then"], value["else"]):
                if not isinstance(branch, Mapping) or set(branch) != {"prefix", "value"}:
                    self.fail("definition_key", "closed select branch is malformed")
                self._validate_closed_value(branch["value"])
        elif kind == "list":
            if set(value) != {"k", "items", "type"} or not isinstance(value["items"], list):
                self.fail("definition_key", "closed list value is malformed")
            self._validate_key_type(value["type"])
            for child in value["items"]:
                self._validate_closed_value(child)
        elif kind == "list_map":
            if set(value) != {"k", "binder", "source", "body", "type"}:
                self.fail("definition_key", "closed list-map value is malformed")
            self._validate_closed_value(value["source"])
            self._validate_closed_value(value["body"])
            self._validate_key_type(value["type"])
        elif kind == "path_join":
            if set(value) != {"k", "base", "child", "type"}:
                self.fail("definition_key", "closed path-join value is malformed")
            self._validate_closed_value(value["base"])
            self._validate_closed_value(value["child"])
            self._validate_key_type(value["type"])
        elif kind == "block":
            if set(value) != {"k", "body"}:
                self.fail("definition_key", "closed block value is malformed")
            self._validate_closed_body(value["body"])

    def _validate_closed_body(self, body: Any) -> None:
        if not isinstance(body, Mapping):
            self.fail("definition_key", "closed substitution body must be a body node")
        kind = body.get("k")
        if kind == "let":
            if set(body) != {"k", "name", "value", "body"}:
                self.fail("definition_key", "closed substitution let is malformed")
            self._validate_closed_value(body["value"])
            self._validate_closed_body(body["body"])
        elif kind in {"halt", "done"}:
            if set(body) != {"k", "value"}:
                self.fail("definition_key", "closed substitution terminal is malformed")
            self._validate_closed_value(body["value"])
        elif kind in {"if", "case", "join", "jump", "loop", "continue"}:
            self.fail("definition_key", "closed substitution body contains unsupported control flow")
        else:
            self.fail("definition_key", "closed substitution body has an unknown node")

    def _check_entry(self) -> None:
        owner = self.tree["entry"]
        self.calls[owner] = []
        self.performs[owner] = []
        self.call_edges[owner] = []
        self._check_signature_rows(self.tree.get("params"), self.tree.get("defaults"), self.tree.get("result"))
        env, _ = self._parameter_environment(self.tree["params"], self.tree.get("defaults", {}), node=self.tree)
        observed = self._body(
            self.tree["body"],
            env,
            owner=self.tree["entry"],
            result=self.tree["result"],
            joins={},
            loops=(),
            scope=self._scope_for({}, node=self.tree),
        )
        self._halt_body_type(
            observed,
            self.tree["result"],
            rule="entry_result",
            message="entry body must halt with its declared result type",
            node=self.tree["body"],
        )

    def _check_signature_rows(self, params: Any, defaults: Any, result: Any) -> None:
        if not isinstance(params, list):
            self.fail("call_signature", "parameters must be an array")
        self._parameter_environment(params, defaults, node=self.tree)
        self._validate_descriptor(result)

    def _parameter_environment(
        self,
        params: Any,
        defaults: Any,
        *,
        node: Any = None,
    ) -> tuple[dict[str, Any], list[str]]:
        if not isinstance(params, list):
            self.fail("call_signature", "parameters must be an array", node)
        if not isinstance(defaults, Mapping):
            self.fail("call_signature", "defaults must be an object", node)
        env: dict[str, Any] = {}
        names: list[str] = []
        for row in params:
            if not isinstance(row, list) or len(row) != 2:
                self.fail("call_signature", "parameter row must be a name/descriptor pair", node)
            name, descriptor = row
            if not isinstance(name, str) or not name or name in env:
                self.fail("call_signature", "parameter names must be nonempty and unique", node)
            self._validate_descriptor(descriptor, node=node)
            env[name] = descriptor
            names.append(name)
        if not set(defaults).issubset(env):
            self.fail("call_signature", "defaults refer to an unknown parameter", node)
        for name, value in defaults.items():
            try:
                _coerce_checked_value(value, env[name], context=f"default {name}")
            except (PureExprEvaluationError, TypeError, ValueError, RecursionError) as exc:
                self.fail("call_signature", f"default for {name!r} does not match its parameter: {exc}", node)
        return env, names

    def _check_definition_bodies(self) -> None:
        for name, definition in self.definitions.items():
            params = definition.get("params")
            defaults = definition.get("defaults", {})
            result = definition.get("result")
            if not isinstance(definition.get("body"), Mapping):
                self.fail("definition_shape", "definition body must be a body node", definition)
            if "key" not in definition:
                self.fail("definition_key", "definition is missing its canonical key", definition)
            self._validate_descriptor(result, node=definition)
            env, _ = self._parameter_environment(params, defaults, node=definition)
            self.calls[name] = []
            self.performs[name] = []
            self.call_edges[name] = []
            observed = self._body(
                definition["body"],
                env,
                owner=name,
                result=result,
                joins={},
                loops=(),
                scope=self._scope_for(definition, node=definition),
            )
            self._halt_body_type(
                observed,
                result,
                rule="entry_result",
                message=f"definition {name!r} body must halt with its declared result type",
                node=definition["body"],
            )

    def _body(
        self,
        node: Any,
        env: dict[str, Any],
        *,
        owner: str,
        result: Any,
        joins: dict[str, tuple[list[Any], Any]],
        loops: tuple[dict[str, Any], ...],
        scope: Mapping[str, Any],
        provider_origins: frozenset[str] = frozenset(),
    ) -> tuple[_BodyOutcome, ...]:
        if not isinstance(node, Mapping):
            self.fail("node_kind", "body node must be an object")
        kind = node.get("k")
        fields = _BODY_KEYS.get(kind)
        if fields is None:
            self.fail("node_kind", f"unknown body node kind {kind!r}", node)
        self._node_shape(node, fields, node=node)
        self.calls.setdefault(owner, [])
        self.performs.setdefault(owner, [])
        if kind == "let":
            name = self._binding_name(node.get("name"), node)
            value_type, provider = self._bound(
                node.get("value"), env, owner=owner, loops=loops, scope=scope,
                provider_origins=provider_origins,
            )
            nested = dict(env)
            nested[name] = value_type
            nested_origins = (provider_origins - {name}) | ({name} if provider else set())
            return self._body(
                node.get("body"), nested, owner=owner, result=result,
                joins=joins, loops=loops, scope=scope,
                provider_origins=frozenset(nested_origins),
            )
        if kind in {"halt", "done"}:
            value_type = self._value(node.get("value"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            if kind == "halt":
                return (_BodyOutcome("halt", value_type),)
            if not loops:
                self.fail("continue_target", "done must occur inside a loop", node)
            loop = loops[-1]
            self._require_type(value_type, loop["result"], "type_mismatch", node)
            return (_BodyOutcome("done", value_type, loop["name"]),)
        if kind == "if":
            condition = self._value(node.get("cond"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            self._require_type(condition, {"kind": "primitive", "name": "Bool"}, "type_mismatch", node["cond"])
            left = self._body(node.get("then"), dict(env), owner=owner, result=result, joins=joins, loops=loops, scope=scope, provider_origins=provider_origins)
            right = self._body(node.get("else"), dict(env), owner=owner, result=result, joins=joins, loops=loops, scope=scope, provider_origins=provider_origins)
            return self._merge_body_outcomes((left, right))
        if kind == "case":
            subject_type = self._value(node.get("subject"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            if subject_type.get("kind") != "union":
                self.fail("type_mismatch", "case subject must have a union type", node["subject"])
            variants = {variant["name"]: variant for variant in subject_type["variants"]}
            arms = node.get("arms")
            if not isinstance(arms, list):
                self.fail("node_kind", "case arms must be an array", node)
            arm_names: list[str] = []
            results: list[tuple[_BodyOutcome, ...]] = []
            for arm in arms:
                if not isinstance(arm, Mapping) or set(arm) - {"variant", "bind", "body", "@"}:
                    self.fail("node_kind", "case arm is malformed", arm)
                variant = arm.get("variant")
                if not isinstance(variant, str) or variant not in variants or variant in arm_names:
                    self.fail("variant_case", "case arm names an invalid or duplicate variant", arm)
                arm_names.append(variant)
                binder = self._binding_name(arm.get("bind"), arm)
                variant_desc = {
                    "kind": "variant_case",
                    "union_name": subject_type["name"],
                    "variant": variant,
                    "fields": deepcopy(variants[variant]["fields"]),
                }
                self._validate_descriptor(variant_desc, node=arm)
                arm_env = dict(env)
                arm_env[binder] = variant_desc
                arm_origins = provider_origins - {binder}
                results.append(self._body(arm.get("body"), arm_env, owner=owner, result=result, joins=joins, loops=loops, scope=scope, provider_origins=arm_origins))
            if set(arm_names) != set(variants):
                self.fail("variant_case", "case arms must cover each union variant once", node)
            return self._merge_body_outcomes(results)
        if kind == "join":
            params = node.get("params")
            if not isinstance(params, list) or len(params) != 1:
                self.fail("join_arity", "join must have exactly one result parameter", node)
            target = node.get("name")
            if not isinstance(target, str) or not target:
                self.fail("join_target", "join target must have a name", node)
            param = params[0]
            if not isinstance(param, list) or len(param) != 2:
                self.fail("join_arity", "join parameter must be a name/descriptor pair", node)
            param_name = self._binding_name(param[0], node)
            param_type = param[1]
            self._validate_descriptor(param_type, node=node)
            join_result = node.get("result")
            self._validate_descriptor(join_result, node=node)
            self._require_type(param_type, join_result, "type_mismatch", node)
            inner_env = dict(env)
            inner_joins = dict(joins)
            if target in inner_joins:
                self.fail("join_target", "join target is shadowed", node)
            inner_joins[target] = ([param_type], join_result)
            cont_env = dict(env)
            cont_env[param_name] = param_type
            cont_origins = provider_origins - {param_name}
            body_result = self._body(node.get("body"), inner_env, owner=owner, result=join_result, joins=inner_joins, loops=loops, scope=scope, provider_origins=provider_origins)
            cont_result = self._body(node.get("cont"), cont_env, owner=owner, result=result, joins=joins, loops=loops, scope=scope, provider_origins=cont_origins)
            continue_into_continuation = False
            propagated: list[_BodyOutcome] = []
            for outcome in body_result:
                if outcome.kind == "halt":
                    self._require_type(outcome.value_type, join_result, "type_mismatch", node["body"])
                    continue_into_continuation = True
                elif outcome.kind == "jump" and outcome.target == target:
                    continue_into_continuation = True
                else:
                    propagated.append(outcome)
            if continue_into_continuation:
                propagated.extend(cont_result)
            return tuple(propagated)
        if kind == "jump":
            target = node.get("join")
            if target not in joins:
                self.fail("jump_target", "jump does not name an enclosing join", node)
            expected_args, _join_result = joins[target]
            args = node.get("args")
            if not isinstance(args, list) or len(args) != len(expected_args):
                self.fail("jump_arity", "jump argument count differs from join arity", node)
            for argument, expected in zip(args, expected_args, strict=True):
                observed = self._value(argument, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                self._require_type(observed, expected, "type_mismatch", argument)
            return (_BodyOutcome("jump", target=target),)
        if kind == "loop":
            loop_name = node.get("name")
            param_name = self._binding_name(node.get("param"), node)
            if not isinstance(loop_name, str) or not loop_name:
                self.fail("continue_target", "loop target must have a name", node)
            state_type = node.get("state_type")
            loop_result = node.get("result")
            self._validate_descriptor(state_type, node=node)
            self._validate_descriptor(loop_result, node=node)
            budget_type = self._value(node.get("budget"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            self._require_type(budget_type, {"kind": "primitive", "name": "Int"}, "type_mismatch", node["budget"])
            init_type = self._value(node.get("init"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            self._require_type(init_type, state_type, "type_mismatch", node["init"])
            loop_env = dict(env)
            loop_env[param_name] = state_type
            loop_origins = provider_origins - {param_name}
            current_loop = {"name": loop_name, "param": param_name, "state": state_type, "result": loop_result}
            body_result = self._body(
                node.get("body"), loop_env, owner=owner, result=loop_result,
                joins={}, loops=(*loops, current_loop), scope=scope,
                provider_origins=loop_origins,
            )
            for outcome in body_result:
                if outcome.kind == "done" and outcome.target == loop_name:
                    self._require_type(outcome.value_type, loop_result, "type_mismatch", node["body"])
                elif outcome.kind != "continue" or outcome.target != loop_name:
                    self.fail(
                        "loop_control",
                        "loop body must end with done or continue for its own loop",
                        node["body"],
                    )
            exhausted = node.get("exhausted")
            if exhausted is not None:
                exhausted_result = self._body(
                    exhausted, dict(loop_env), owner=owner, result=loop_result,
                    joins={}, loops=loops, scope=scope,
                    provider_origins=loop_origins,
                )
                self._halt_body_type(
                    exhausted_result,
                    loop_result,
                    rule="type_mismatch",
                    message="loop exhaustion must halt with its declared result type",
                    node=exhausted,
                )
            return (_BodyOutcome("halt", loop_result),)
        if kind == "continue":
            target = node.get("loop")
            if not loops or target != loops[-1]["name"]:
                self.fail("continue_target", "continue must name the innermost enclosing loop", node)
            args = node.get("args")
            if not isinstance(args, list) or len(args) != 1:
                self.fail("continue_arity", "continue requires exactly one state value", node)
            state_type = self._value(args[0], env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            self._require_type(state_type, loops[-1]["state"], "type_mismatch", args[0])
            return (_BodyOutcome("continue", target=target),)
        self.fail("node_kind", f"unknown body node kind {kind!r}", node)

    def _bound(
        self,
        node: Any,
        env: dict[str, Any],
        *,
        owner: str,
        loops: tuple[dict[str, Any], ...],
        scope: Mapping[str, Any],
        provider_origins: frozenset[str] = frozenset(),
    ) -> tuple[dict[str, Any], bool]:
        if not isinstance(node, Mapping):
            self.fail("node_kind", "bound value must be an object")
        kind = node.get("k")
        if kind == "perform":
            result = node.get("result")
            self._validate_descriptor(result, node=node)
            self.performs.setdefault(owner, []).append(node)
            self._check_effect_node(node, env, owner=owner, loops=loops, scope=scope, provider_origins=provider_origins)
            return result, node.get("class") == "provider"
        if kind == "call":
            return self._call(node, env, owner=owner, loops=loops, scope=scope, provider_origins=provider_origins), False
        return self._value(node, env, owner=owner, loops=loops, scope=scope, allow_effect=True, provider_origins=provider_origins), False

    def _value(
        self,
        node: Any,
        env: dict[str, Any],
        *,
        owner: str,
        loops: tuple[dict[str, Any], ...],
        scope: Mapping[str, Any],
        allow_effect: bool,
        provider_origins: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        if not isinstance(node, Mapping):
            self.fail("node_kind", "value node must be an object")
        kind = node.get("k")
        allowed = _VALUE_KEYS.get(kind)
        if allowed is None:
            self.fail("node_kind", f"unknown value node kind {kind!r}", node)
        self._node_shape(node, allowed, node=node)
        if kind == "lit":
            descriptor = node.get("type")
            self._validate_descriptor(descriptor, node=node)
            try:
                _coerce_checked_value(node.get("v"), descriptor, context="literal")
            except (PureExprEvaluationError, TypeError, ValueError, RecursionError) as exc:
                self.fail("type_mismatch", f"literal does not match its descriptor: {exc}", node)
            return descriptor
        if kind == "name":
            name = node.get("n")
            if not isinstance(name, str) or name not in env:
                self.fail("unbound_name", f"name {name!r} is not bound", node)
            return env[name]
        if kind == "field":
            descriptor = self._value(node.get("base"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            path = node.get("path")
            if not isinstance(path, list) or not path or any(not isinstance(part, str) or not part for part in path):
                self.fail("field_path", "field path must be a nonempty string array", node)
            for segment in path:
                descriptor = self._field_type(descriptor, segment, node)
            return descriptor
        if kind == "record":
            descriptor = node.get("type")
            self._validate_descriptor(descriptor, node=node)
            if descriptor.get("kind") != "record":
                self.fail("type_mismatch", "record value requires a record descriptor", node)
            rows = self._field_rows(node.get("fields"), node)
            expected = {field["name"]: field["type"] for field in descriptor["fields"]}
            if set(rows) != set(expected):
                self.fail("record_fields", "record value fields differ from its descriptor", node)
            for name, value in rows.items():
                actual = self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                self._require_type(actual, expected[name], "type_mismatch", value)
            return descriptor
        if kind == "inject":
            descriptor = node.get("type")
            self._validate_descriptor(descriptor, node=node)
            if descriptor.get("kind") != "union":
                self.fail("type_mismatch", "inject value requires a union descriptor", node)
            variant = node.get("variant")
            selected = next((row for row in descriptor["variants"] if row["name"] == variant), None)
            if selected is None:
                self.fail("variant_case", "inject names an unknown union variant", node)
            fields = self._field_rows(node.get("fields"), node)
            expected = {field["name"]: field["type"] for field in selected["fields"]}
            if set(fields) != set(expected):
                self.fail("record_fields", "injected fields differ from the selected variant", node)
            for name, value in fields.items():
                actual = self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                self._require_type(actual, expected[name], "type_mismatch", value)
            return descriptor
        if kind == "op":
            payload = node.get("payload")
            try:
                validate_pure_expr_payload(payload)
            except (PureExprEvaluationError, TypeError, ValueError, RecursionError) as exc:
                self.fail("payload_invalid", f"operator payload is invalid: {exc}", node)
            if payload.get("pure_expr_schema_version") != 2:
                self.fail("payload_invalid", "closed operator payload must use pure-expression schema version 2", node)
            args = node.get("args")
            if not isinstance(args, list):
                self.fail("payload_invalid", "operator arguments must be an array", node)
            bindings = payload.get("bindings", {})
            expected_names = [f"a{index}" for index in range(len(args))]
            if list(bindings) != expected_names:
                self.fail("payload_invalid", "operator bindings do not match argument order", node)
            for index, argument in enumerate(args):
                actual = self._value(argument, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                self._require_type(actual, bindings[f"a{index}"]["type"], "type_mismatch", argument)
            result = payload.get("result_type")
            self._validate_descriptor(result, node=node)
            return result
        if kind == "select":
            condition = self._value(node.get("cond"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            self._require_type(condition, {"kind": "primitive", "name": "Bool"}, "type_mismatch", node["cond"])
            branch_types: list[dict[str, Any]] = []
            for arm in (node.get("then"), node.get("else")):
                if not isinstance(arm, Mapping) or set(arm) - {"prefix", "value", "@"}:
                    self.fail("node_kind", "select arm is malformed", node)
                branch_env = dict(env)
                branch_origins = provider_origins
                prefix = arm.get("prefix")
                if not isinstance(prefix, list):
                    self.fail("node_kind", "select prefix must be an array", arm)
                for row in prefix:
                    if not isinstance(row, Mapping) or set(row) - {"name", "value", "label", "@"}:
                        self.fail("node_kind", "select prefix row is malformed", row)
                    name = self._binding_name(row.get("name"), row)
                    value_type, provider = self._bound(
                        row.get("value"), branch_env, owner=owner, loops=loops,
                        scope=scope, provider_origins=branch_origins,
                    )
                    branch_env[name] = value_type
                    branch_origins = (branch_origins - {name}) | ({name} if provider else set())
                branch_types.append(self._value(arm.get("value"), branch_env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=frozenset(branch_origins)))
            self._require_type(branch_types[1], branch_types[0], "type_mismatch", node)
            return branch_types[0]
        if kind == "list":
            descriptor = node.get("type")
            self._validate_descriptor(descriptor, node=node)
            if descriptor.get("kind") != "list":
                self.fail("type_mismatch", "list value requires a list descriptor", node)
            items = node.get("items")
            if not isinstance(items, list):
                self.fail("type_mismatch", "list items must be an array", node)
            for value in items:
                actual = self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                self._require_type(actual, descriptor["item"], "type_mismatch", value)
            return descriptor
        if kind == "list_map":
            descriptor = node.get("type")
            self._validate_descriptor(descriptor, node=node)
            source = self._value(node.get("source"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            if source.get("kind") != "list" or descriptor.get("kind") != "list":
                self.fail("type_mismatch", "list_map source and result must be lists", node)
            binder = self._binding_name(node.get("binder"), node)
            body_env = dict(env)
            body_env[binder] = source["item"]
            body_type = self._value(node.get("body"), body_env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins - {binder})
            self._require_type(body_type, descriptor["item"], "type_mismatch", node["body"])
            return descriptor
        if kind == "path_join":
            descriptor = node.get("type")
            self._validate_descriptor(descriptor, node=node)
            if descriptor.get("kind") != "path" or not descriptor.get("under"):
                self.fail("path_root", "path_join requires a path descriptor with a root", node)
            base = self._value(node.get("base"), env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            if base.get("kind") != "path" or base.get("under") != descriptor.get("under"):
                self.fail("path_root", "path_join base does not have the same path root", node)
            child = node.get("child")
            if not isinstance(child, Mapping) or child.get("k") != "lit":
                self.fail("path_child", "path_join child must be a literal", node)
            child_type = self._value(child, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            self._require_type(child_type, {"kind": "primitive", "name": "String"}, "type_mismatch", child)
            if not isinstance(child.get("v"), str) or not child["v"] or "\\" in child["v"]:
                self.fail("path_child", "path_join child must be a nonempty relative component", child)
            return descriptor
        if kind == "block":
            if not allow_effect:
                self._require_no_effect_value(node, env, owner=owner, loops=loops, scope=scope)
            outcomes = self._body(node.get("body"), dict(env), owner=owner, result=None, joins={}, loops=loops, scope=scope, provider_origins=provider_origins)
            return self._halt_body_type(
                outcomes,
                None,
                rule="block_control",
                message="block body must halt locally with a value",
                node=node,
            )
        if kind == "context":
            if node.get("field") != "run-id":
                self.fail("node_kind", "context supports only run-id", node)
            return {"kind": "primitive", "name": "String"}
        if kind == "result_path":
            name = node.get("n")
            if not isinstance(name, str) or name not in provider_origins:
                self.fail("provider_result_path", "result_path must name a provider effect binding", node)
            descriptor = node.get("type")
            self._validate_descriptor(descriptor, node=node)
            if descriptor.get("kind") != "path" or descriptor.get("under") != ".orchestrate/runs":
                self.fail("provider_result_path", "provider result path must be rooted under .orchestrate/runs", node)
            return descriptor
        if kind == "call":
            if not allow_effect:
                self.fail("effect_in_value", "call appears in a value-only position", node)
            return self._call(node, env, owner=owner, loops=loops, scope=scope, provider_origins=provider_origins)
        if kind == "perform":
            self.fail("effect_in_value", "perform appears in a value-only position", node)
        self.fail("node_kind", f"unknown value node kind {kind!r}", node)

    def _field_type(self, descriptor: Mapping[str, Any], segment: str, node: Any) -> dict[str, Any]:
        kind = descriptor.get("kind")
        if kind == "record":
            fields = descriptor["fields"]
        elif kind == "variant_case":
            fields = descriptor["fields"]
        elif kind == "union" and segment == "variant":
            return {"kind": "enum", "name": descriptor["name"] + ".variant", "allowed": [row["name"] for row in descriptor["variants"]]}
        elif kind == "union":
            candidate_fields = [
                field
                for variant in descriptor["variants"]
                for field in variant["fields"]
                if field["name"] == segment
            ]
            if len(candidate_fields) != len(descriptor["variants"]) or any(not self._same(candidate_fields[0]["type"], row["type"]) for row in candidate_fields[1:]):
                self.fail("field_path", f"union field {segment!r} is absent or has variant-dependent types", node)
            return candidate_fields[0]["type"]
        else:
            self.fail("field_path", f"type {kind!r} has no field {segment!r}", node)
        row = next((field for field in fields if field["name"] == segment), None)
        if row is None:
            self.fail("field_path", f"field {segment!r} does not exist", node)
        return row["type"]

    def _field_rows(self, value: Any, node: Any) -> dict[str, Any]:
        if not isinstance(value, list):
            self.fail("record_fields", "aggregate fields must be an ordered array", node)
        rows: dict[str, Any] = {}
        for row in value:
            if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str) or row[0] in rows:
                self.fail("record_fields", "aggregate field rows must have unique string names", node)
            rows[row[0]] = row[1]
        return rows

    def _require_no_effect_value(
        self,
        node: Any,
        env: Mapping[str, Any],
        *,
        owner: str,
        loops: tuple[dict[str, Any], ...],
        scope: Mapping[str, Any],
    ) -> None:
        if self._effect_in_value(node):
            self.fail("effect_in_value", "effectful control value appears outside a binding", node)

    def _checked_effect_result_contract(self, descriptor: Mapping[str, Any]) -> dict[str, Any]:
        """Derive the structural output contract from its checked result type."""

        def pointer(path: Sequence[str]) -> str:
            return "" if not path else "/" + "/".join(
                segment.replace("~", "~0").replace("/", "~1") for segment in path
            )

        def flatten(descriptor_: Mapping[str, Any], path: tuple[str, ...]) -> list[dict[str, Any]]:
            if descriptor_.get("kind") == "record":
                rows: list[dict[str, Any]] = []
                for field in descriptor_["fields"]:
                    rows.extend(flatten(field["type"], (*path, field["name"])))
                return rows
            return [
                {
                    "name": "__".join(path),
                    "json_pointer": pointer(path),
                    **transport_schema_for_descriptor(descriptor_, allow_nested_structures=True),
                }
            ]

        kind = descriptor.get("kind")
        if kind == "record":
            fields = flatten(descriptor, ())
            return {"kind": "output_bundle", "payload": {"fields": fields}}
        if kind == "union":
            variants = descriptor["variants"]
            per_variant = {
                variant["name"]: [
                    row
                    for field in variant["fields"]
                    for row in flatten(field["type"], (field["name"],))
                ]
                for variant in variants
            }
            first_rows = per_variant[variants[0]["name"]]
            shared: list[dict[str, Any]] = []
            for candidate in first_rows:
                if all(
                    any(self._same(candidate, row) for row in per_variant[variant["name"]])
                    for variant in variants[1:]
                ):
                    shared.append(candidate)
            shared_names = {row["name"] for row in shared}
            return {
                "kind": "variant_output",
                "payload": {
                    "discriminant": {
                        "name": "variant",
                        "json_pointer": "/variant",
                        "type": "enum",
                        "allowed": [variant["name"] for variant in variants],
                    },
                    "shared_fields": shared,
                    "variants": {
                        variant["name"]: {
                            "fields": [
                                row for row in per_variant[variant["name"]]
                                if row["name"] not in shared_names
                            ]
                        }
                        for variant in variants
                    },
                },
            }
        root = flatten(descriptor, ("__result__",))[0]
        root["json_pointer"] = ""
        return {"kind": "output_bundle", "payload": {"fields": [root]}}

    def _result_contract_view(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: self._result_contract_view(item)
                for key, item in value.items()
                if key not in _RESULT_CONTRACT_METADATA_KEYS
            }
        if isinstance(value, list):
            return [self._result_contract_view(item) for item in value]
        return value

    def _check_effect_result_contract(self, node: Mapping[str, Any]) -> None:
        contract = node.get("contract")
        result = node.get("result")
        if not isinstance(contract, Mapping) or not isinstance(result, Mapping):
            self.fail("effect_result", "effect result contract is missing its typed result", node)
        try:
            expected = self._checked_effect_result_contract(result)
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            self.fail("effect_result", f"effect result contract cannot be derived: {exc}", node)
        actual = {
            "kind": contract.get("kind"),
            "payload": self._result_contract_view(contract.get("payload")),
        }
        if "path" in contract.get("payload", {}):
            self.fail("effect_result", "effect result contract must omit its generated output path", node)
        if not self._same(actual, expected):
            self.fail("effect_result", "effect result descriptor differs from its command/provider contract", node)

    def _provider_input_renderer(
        self,
        renderer_id: Any,
        value: Mapping[str, Any],
        value_type: Mapping[str, Any],
        node: Mapping[str, Any],
    ) -> None:
        if not isinstance(renderer_id, str) or not renderer_id:
            self.fail("effect_shape", "provider input renderer id must be a nonempty string", node)
        try:
            renderer = resolve_view_renderer(renderer_id, 1)
        except ViewRendererError as exc:
            self.fail("effect_shape", f"provider input renderer is not registered: {exc}", node)
        if renderer.accepted_shape == "path_value":
            try:
                schema = transport_schema_for_descriptor(
                    value_type,
                    allow_nested_structures=True,
                )
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("effect_shape", f"provider input renderer has no matching value shape: {exc}", node)
            if schema.get("type") not in {"string", "enum", "relpath"}:
                self.fail("effect_shape", "path-line provider input requires a string or path value", node)
        elif renderer.accepted_shape != "any_pure_value":
            self.fail("effect_shape", "provider input renderer has an unsupported accepted shape", node)

        if value.get("k") == "lit":
            try:
                render_view(renderer_id, 1, value.get("v"))
            except (ViewRendererError, TypeError, ValueError, OverflowError) as exc:
                self.fail("effect_shape", f"provider input literal is not renderable: {exc}", node)

    def _check_provider_prompt_fills(
        self,
        prompt: Mapping[str, Any],
        *,
        node: Mapping[str, Any],
        env: dict[str, Any],
        owner: str,
        loops: tuple[dict[str, Any], ...],
        scope: Mapping[str, Any],
        provider_origins: frozenset[str],
    ) -> None:
        fills = prompt["fills"]
        try:
            placeholders = _scan_placeholders(prompt["template"])
        except (TypeError, ValueError, RecursionError) as exc:
            self.fail("effect_shape", f"provider prompt template is malformed: {exc}", node)

        names: set[str] = set()
        claimed: set[int] = set()
        for fill in fills:
            expected = {"name", "kind", "type", "value", "renderer_id", "output_role", "placeholder_ordinals"}
            if not isinstance(fill, Mapping) or set(fill) != expected:
                self.fail("effect_shape", "provider template fill has invalid fields", node)
            name = fill["name"]
            if not isinstance(name, str) or not _NAME_RE.fullmatch(name) or name in names:
                self.fail("effect_shape", "provider template slot names must be unique valid names", node)
            names.add(name)
            descriptor = fill["type"]
            self._validate_descriptor(descriptor, node=node)
            actual = self._value(
                fill["value"],
                env,
                owner=owner,
                loops=loops,
                scope=scope,
                allow_effect=False,
                provider_origins=provider_origins,
            )
            self._require_type(actual, descriptor, "type_mismatch", node)

            slot_kind = fill["kind"]
            if not isinstance(slot_kind, str):
                self.fail("effect_shape", "provider template slot kind is invalid", node)
            if slot_kind == "doc":
                type_matches = descriptor.get("kind") == "path" and descriptor.get("must_exist_target") is True
                expected_renderer = None
            elif slot_kind == "text":
                type_matches = descriptor.get("kind") == "primitive" and descriptor.get("name") == "String"
                expected_renderer = _RENDERERS_BY_KIND["text"]
            elif slot_kind == "path":
                type_matches = descriptor.get("kind") == "path"
                expected_renderer = _RENDERERS_BY_KIND["path"]
            elif slot_kind == "value":
                type_matches = _prompt_value_type_is_renderable(descriptor)
                expected_renderer = _RENDERERS_BY_KIND["value"]
            else:
                self.fail("effect_shape", f"unsupported provider template slot kind {slot_kind!r}", node)
            if not type_matches:
                self.fail("effect_shape", f"provider template {slot_kind} slot has an incompatible type", node)
            if fill["renderer_id"] != expected_renderer:
                self.fail("effect_shape", "provider template slot renderer does not match its kind and type", node)

            output_role = fill["output_role"]
            if output_role not in (None, "none", "required_string_file"):
                self.fail("effect_shape", "provider template output role is unsupported", node)
            if output_role == "required_string_file" and not (
                slot_kind == "path"
                and descriptor.get("kind") == "path"
                and descriptor.get("must_exist_target") is False
            ):
                self.fail("effect_shape", "required output slot must be a non-existing relpath", node)

            ordinals = fill["placeholder_ordinals"]
            if (
                not isinstance(ordinals, list)
                or any(type(index) is not int or index < 0 for index in ordinals)
                or ordinals != sorted(set(ordinals))
            ):
                self.fail("effect_shape", "provider template slot placeholder ordinals are invalid", node)
            if slot_kind == "doc":
                if ordinals:
                    self.fail("effect_shape", "document slots do not consume template placeholders", node)
                continue
            if not ordinals:
                self.fail("effect_shape", "rendered prompt slots require placeholder positions", node)
            for ordinal in ordinals:
                if ordinal >= len(placeholders) or placeholders[ordinal] != name or ordinal in claimed:
                    self.fail("effect_shape", "provider prompt placeholder rows are inconsistent", node)
                claimed.add(ordinal)

        if claimed != set(range(len(placeholders))):
            self.fail("effect_shape", "provider prompt placeholder coverage is incomplete", node)

    def _effect_in_value(self, node: Any) -> bool:
        """Find forbidden effects using value/body AST edges only."""

        if not isinstance(node, Mapping):
            return False
        kind = node.get("k")
        if kind in {"call", "perform"}:
            self.fail("effect_in_value", "call or perform appears in a value-only position", node)
        if kind == "block":
            return self._body_has_effect(node.get("body"))
        if kind == "select":
            if self._effect_in_value(node.get("cond")):
                return True
            found = False
            for branch_name in ("then", "else"):
                branch = node.get(branch_name)
                if not isinstance(branch, Mapping):
                    continue
                prefix = branch.get("prefix", [])
                if isinstance(prefix, list):
                    for row in prefix:
                        if isinstance(row, Mapping):
                            found = self._bound_has_effect(row.get("value")) or found
                found = self._effect_in_value(branch.get("value")) or found
            return found
        found = False
        for child in self._value_children(node, strict=False):
            found = self._effect_in_value(child) or found
        return found

    def _bound_has_effect(self, node: Any) -> bool:
        if not isinstance(node, Mapping):
            return False
        kind = node.get("k")
        if kind == "perform":
            return True
        if kind == "call":
            return bool(self.effectful.get(node.get("callee"), False))
        return self._effect_in_value(node)

    def _body_has_effect(self, node: Any) -> bool:
        if not isinstance(node, Mapping):
            return False
        kind = node.get("k")
        if kind == "let":
            has = self._bound_has_effect(node.get("value"))
            rest = self._body_has_effect(node.get("body"))
            return has or rest
        if kind == "if":
            return self._body_has_effect(node.get("then")) or self._body_has_effect(node.get("else"))
        if kind == "case":
            arms = node.get("arms", [])
            return any(self._body_has_effect(arm.get("body")) for arm in arms if isinstance(arm, Mapping)) if isinstance(arms, list) else False
        if kind == "join":
            body = self._body_has_effect(node.get("body"))
            cont = self._body_has_effect(node.get("cont"))
            return body or cont
        if kind == "loop":
            body = self._body_has_effect(node.get("body"))
            exhausted = node.get("exhausted")
            return body or (exhausted is not None and self._body_has_effect(exhausted))
        return False

    def _check_effect_node(
        self,
        node: Mapping[str, Any],
        env: dict[str, Any],
        *,
        owner: str,
        loops: tuple[dict[str, Any], ...],
        scope: Mapping[str, Any],
        provider_origins: frozenset[str],
    ) -> None:
        effect_class = node.get("class")
        if effect_class == "command":
            if set(node) - {"k", "class", "result", "repeat", "site", "@", "boundary", "command", "closure", "contract", "argv", "document"}:
                self.fail("effect_shape", "command effect has class-inappropriate fields", node)
            if not {"boundary", "command", "closure", "contract", "repeat"}.issubset(node):
                self.fail("effect_shape", "command effect is missing a required field", node)
            if not isinstance(node.get("repeat"), str) or node["repeat"] not in {"rerun", "never"}:
                self.fail("effect_repeat", "command repeat must be rerun or never", node)
            if not isinstance(node.get("command"), list) or not node["command"] or any(not isinstance(token, str) or not token for token in node["command"]):
                self.fail("effect_shape", "command stable tokens must be a nonempty string array", node)
            closure = node.get("closure")
            if not isinstance(closure, list):
                self.fail("command_closure", "command closure must be a canonical array", node)
            canonical_closure: list[str] = []
            for row in closure:
                if not isinstance(row, Mapping) or set(row) != {"base", "path"}:
                    self.fail("command_closure", "command closure row must contain base and path", node)
                if not isinstance(row["base"], str) or row["base"] not in {"workspace", "absolute", "package:orchestrator"} or not isinstance(row["path"], str) or not row["path"] or "\x00" in row["path"]:
                    self.fail("command_closure", "command closure row has an invalid base or path", node)
                canonical_closure.append(self._canonical(row))
            if canonical_closure != sorted(set(canonical_closure)):
                self.fail("command_closure", "command closure rows must be unique and canonically ordered", node)
            if not isinstance(node.get("boundary"), str) or not node["boundary"]:
                self.fail("effect_shape", "command boundary must be a nonempty string", node)
            if not isinstance(node.get("contract"), Mapping) or set(node["contract"]) != {"kind", "payload"} or not isinstance(node["contract"]["kind"], str) or not isinstance(node["contract"]["payload"], Mapping):
                self.fail("effect_contract", "command output contract is malformed", node)
            self._check_effect_result_contract(node)
            if "document" in node:
                if not isinstance(node.get("argv"), list) or node["argv"]:
                    self.fail("effect_shape", "document invocation must carry an empty argv array", node)
                rows = node["document"]
                if not isinstance(rows, list):
                    self.fail("effect_shape", "command document must be an array", node)
                for row in rows:
                    if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str):
                        self.fail("effect_shape", "command document row is malformed", node)
                    self._value(row[1], env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            elif isinstance(node.get("argv"), list):
                for value in node["argv"]:
                    self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
            else:
                self.fail("effect_shape", "raw command invocation requires argv and cannot carry document", node)
            return
        if effect_class == "provider":
            if set(node) - {"k", "class", "result", "repeat", "site", "@", "provider", "prompt", "inputs", "dependencies", "policy", "contract"}:
                self.fail("effect_shape", "provider effect has class-inappropriate fields", node)
            if not {"provider", "prompt", "inputs", "dependencies", "policy", "contract", "repeat"}.issubset(node):
                self.fail("effect_shape", "provider effect is missing a required field", node)
            if not isinstance(node.get("repeat"), str) or node["repeat"] != "rerun":
                self.fail("effect_repeat", "provider repeat must be rerun", node)
            if not isinstance(node.get("provider"), str) or not node["provider"].strip():
                self.fail("effect_shape", "provider id must be a nonempty string", node)
            if not isinstance(node.get("contract"), Mapping) or set(node["contract"]) != {"kind", "payload"} or not isinstance(node["contract"]["kind"], str) or not isinstance(node["contract"]["payload"], Mapping):
                self.fail("effect_contract", "provider output contract is malformed", node)
            self._check_effect_result_contract(node)
            rows = node.get("inputs", [])
            if not isinstance(rows, list):
                self.fail("effect_shape", "provider inputs must be an array", node)
            names: set[str] = set()
            for row in rows:
                if not isinstance(row, list) or len(row) != 3 or not isinstance(row[0], str) or not row[0] or row[0] in names:
                    self.fail("effect_shape", "provider input row is malformed or duplicated", node)
                names.add(row[0])
                actual = self._value(row[2], env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                self._provider_input_renderer(row[1], row[2], actual, node)
            dependencies = node.get("dependencies")
            if dependencies is not None:
                if not isinstance(dependencies, Mapping) or set(dependencies) != {"required", "optional", "position", "instruction"}:
                    self.fail("effect_shape", "provider dependency payload is malformed", node)
                if any(not isinstance(dependencies[key], list) for key in ("required", "optional")):
                    self.fail("effect_shape", "provider dependency rows must be arrays", node)
                position = dependencies["position"]
                if not isinstance(position, str) or position not in {"prepend", "append"}:
                    self.fail("effect_shape", "provider dependency position must be prepend or append", node)
                instruction = dependencies["instruction"]
                if instruction is not None:
                    if not isinstance(instruction, str):
                        self.fail("effect_shape", "provider dependency instruction must be text or null", node)
                    try:
                        instruction_bytes = instruction.encode("utf-8", errors="strict")
                    except UnicodeEncodeError as exc:
                        self.fail("effect_shape", f"provider dependency instruction is not valid UTF-8: {exc}", node)
                    if len(instruction_bytes) > 261630:
                        self.fail("effect_shape", "provider dependency instruction exceeds its UTF-8 byte limit", node)
                for value in [*dependencies["required"], *dependencies["optional"]]:
                    actual = self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                    if actual.get("kind") != "path":
                        self.fail("effect_shape", "provider dependencies require relpath values", value)
            policy = node.get("policy")
            if policy is not None:
                if not isinstance(policy, Mapping) or set(policy) - {"model", "effort", "delivery", "materialization_attempts", "timeout_sec"}:
                    self.fail("effect_shape", "provider policy payload is malformed", node)
                string_type = {"kind": "primitive", "name": "String"}
                int_type = {"kind": "primitive", "name": "Int"}
                for field_name in ("model", "effort"):
                    if field_name in policy:
                        value = policy[field_name]
                        actual = self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                        self._require_type(actual, string_type, "effect_shape", node)
                        if not isinstance(value, Mapping) or value.get("k") not in {"lit", "name", "field"}:
                            self.fail("effect_shape", f"provider policy {field_name} must be an inline String value", node)
                if "timeout_sec" in policy:
                    value = policy["timeout_sec"]
                    actual = self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                    self._require_type(actual, int_type, "effect_shape", node)
                    if (
                        not isinstance(value, Mapping)
                        or value.get("k") != "lit"
                        or type(value.get("v")) is not int
                        or value["v"] <= 0
                    ):
                        self.fail("effect_shape", "provider timeout must be a positive Int literal", node)
                if "delivery" in policy:
                    value = policy["delivery"]
                    actual = self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                    self._require_type(actual, string_type, "effect_shape", node)
                    if not isinstance(value, Mapping) or value.get("k") != "lit" or value.get("v") != "composed":
                        self.fail("effect_shape", "checked providers support only composed delivery", node)
                if "materialization_attempts" in policy:
                    self.fail("effect_shape", "materialization attempts are outside the composed provider surface", node)
            prompt = node.get("prompt")
            if not isinstance(prompt, Mapping):
                self.fail("effect_shape", "provider prompt must be an object", node)
            if isinstance(prompt.get("source_kind"), str) and prompt["source_kind"] in {"asset_file", "input_file"}:
                expected_prompt_keys = {"source_kind", "path"} | ({"asset_base"} if prompt["source_kind"] == "asset_file" else set())
                if set(prompt) != expected_prompt_keys or not isinstance(prompt.get("path"), str) or not prompt["path"].strip():
                    self.fail("effect_shape", "provider prompt source row is malformed", node)
                if prompt["source_kind"] == "asset_file" and (not isinstance(prompt.get("asset_base"), str) or not prompt["asset_base"]):
                    self.fail("effect_shape", "asset prompt requires a logical asset base", node)
            elif set(prompt) == {"template", "fills"}:
                if not isinstance(prompt["template"], str) or not isinstance(prompt["fills"], list):
                    self.fail("effect_shape", "provider prompt template is malformed", node)
                self._check_provider_prompt_fills(
                    prompt,
                    node=node,
                    env=env,
                    owner=owner,
                    loops=loops,
                    scope=scope,
                    provider_origins=provider_origins,
                )
            else:
                self.fail("effect_shape", "provider prompt must be an extern source or typed template", node)
            return
        if effect_class == "run_ref":
            if set(node) - {"k", "class", "result", "repeat", "site", "@", "config", "inputs"}:
                self.fail("effect_shape", "run-ref effect has class-inappropriate fields", node)
            if node.get("repeat") != "rerun":
                self.fail("effect_repeat", "run-ref repeat must be rerun", node)
            encoded = node.get("config")
            if not isinstance(encoded, str):
                self.fail("run_ref_config", "run-ref config must be base64 text", node)
            try:
                config = decode_run_ref_static_config(base64.b64decode(encoded, validate=True))
            except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                self.fail("run_ref_config", f"run-ref static config is invalid: {exc}", node)
            if config.target_dsl_version != EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION or config.program.__class__.__name__ != "PathProgram":
                self.fail("run_ref_config", "checked run-ref config must select target 2.35 path mode", node)
            self.run_ref_configs[id(node)] = config
            inputs = node.get("inputs")
            if not isinstance(inputs, list) or len(inputs) != len(config.inputs):
                self.fail("run_ref_config", "run-ref node inputs differ from its config", node)
            seen: set[str] = set()
            for row, config_input in zip(inputs, config.inputs, strict=True):
                if not isinstance(row, list) or len(row) != 2 or row[0] != config_input.name or row[0] in seen:
                    self.fail("run_ref_config", "run-ref node input order differs from its config", node)
                seen.add(row[0])
                actual = self._value(row[1], env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins)
                self._require_type(actual, config_input.type_descriptor, "type_mismatch", row[1])
                if config_input.binding.record != {"kind": "reference", "reference": f"inputs.{row[0]}"}:
                    self.fail("run_ref_config", "run-ref input must use its own inputs reference", node)
            if not self._same(node.get("result"), config.result_descriptor["envelope"]):
                self.fail("effect_result", "run-ref node result differs from its decoded config", node)
            return
        self.fail("effect_class", f"unsupported effect class {effect_class!r}", node)

    def _call(
        self,
        node: Mapping[str, Any],
        env: dict[str, Any],
        *,
        owner: str,
        loops: tuple[dict[str, Any], ...],
        scope: Mapping[str, Any],
        provider_origins: frozenset[str],
    ) -> dict[str, Any]:
        callee = node.get("callee")
        definition = self.definitions.get(callee) if isinstance(callee, str) else None
        if not isinstance(definition, Mapping):
            self.fail("callee_unknown", f"call target {callee!r} has no definition", node)
        args = node.get("args")
        if not isinstance(args, list):
            self.fail("call_signature", "call arguments must be an array", node)
        arg_types = [self._value(value, env, owner=owner, loops=loops, scope=scope, allow_effect=False, provider_origins=provider_origins) for value in args]
        call_type = node.get("type")
        self._validate_descriptor(call_type, node=node)
        params = definition.get("params")
        if not isinstance(params, list):
            self.fail("call_signature", "callee parameters must be an array", node)
        if "boundary" not in node:
            if len(args) != len(params):
                self.fail("call_signature", "ordinary call argument count differs from callee", node)
            for actual, row in zip(arg_types, params, strict=True):
                if not isinstance(row, list) or len(row) != 2:
                    self.fail("call_signature", "callee parameter row is malformed", definition)
                self._require_type(actual, row[1], "call_signature", node)
        else:
            self._check_call_boundary(node, arg_types, definition)
            # The annotated relation owns the caller/native result conversion;
            # each output endpoint is checked against its own nominal type.
        if "boundary" not in node:
            self._require_type(call_type, definition.get("result"), "call_signature", node)
        self.calls.setdefault(owner, []).append(node)
        self.call_edges.setdefault(owner, []).append(callee)
        return call_type

    def _check_call_boundary(
        self,
        node: Mapping[str, Any],
        arg_types: list[dict[str, Any]],
        definition: Mapping[str, Any],
    ) -> None:
        boundary = node.get("boundary")
        if not isinstance(boundary, Mapping) or set(boundary) != {"params", "direct", "inputs", "outputs"}:
            self.fail("call_boundary", "annotated call boundary has invalid fields", node)
        caller_params = boundary["params"]
        if not isinstance(caller_params, list) or len(caller_params) != len(arg_types):
            self.fail("call_boundary", "boundary caller params do not align with call arguments", node)
        caller_roots: list[tuple[str, Mapping[str, Any]]] = []
        names: set[str] = set()
        for row, actual in zip(caller_params, arg_types, strict=True):
            if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str) or row[0] in names:
                self.fail("call_boundary", "boundary caller parameter row is malformed", node)
            names.add(row[0])
            self._validate_descriptor(row[1], node=node)
            self._require_type(actual, row[1], "call_boundary", node)
            caller_roots.append((row[0], row[1]))
        native_params = definition.get("params")
        if not isinstance(native_params, list):
            self.fail("call_boundary", "callee parameter list is malformed", node)
        native_roots: list[tuple[str, Mapping[str, Any]]] = []
        for row in native_params:
            if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str):
                self.fail("call_boundary", "native parameter row is malformed", definition)
            native_roots.append((row[0], row[1]))
        direct = boundary["direct"]
        if not isinstance(direct, list):
            self.fail("call_boundary", "boundary direct pairs must be an array", node)
        caller_direct: list[int] = []
        native_direct: list[int] = []
        pairs: list[tuple[int, int]] = []
        for pair in direct:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or any(type(index) is not int or index < 0 for index in pair)
            ):
                self.fail("call_boundary", "direct indices must be nonnegative non-Boolean integers", node)
            arg_index, param_index = pair
            if arg_index >= len(caller_roots) or param_index >= len(native_roots):
                self.fail("call_boundary", "direct index is out of range", node)
            pairs.append((arg_index, param_index))
            caller_direct.append(arg_index)
            native_direct.append(param_index)
            self._require_type(caller_roots[arg_index][1], native_roots[param_index][1], "call_boundary", node)
        if pairs != sorted(pairs, key=lambda pair: pair[1]) or len(set(caller_direct)) != len(caller_direct) or len(set(native_direct)) != len(native_direct):
            self.fail("call_boundary", "direct pairs are duplicate or not ordered by native slot", node)
        capture_prefix = definition.get("key", [None] * 8)[7]
        if not isinstance(capture_prefix, list) or len(caller_roots) < len(capture_prefix):
            self.fail("call_boundary", "caller slots omit a persisted capture-prefix position", node)
        for capture_index, _capture in enumerate(capture_prefix):
            pair = next(((left, right) for left, right in pairs if right == capture_index), None)
            if pair is not None and pair != (capture_index, capture_index):
                self.fail("call_boundary", "a direct capture pair must preserve its capture-prefix index", node)
        caller_projected = [row for index, row in enumerate(caller_roots) if index not in caller_direct]
        native_projected = [row for index, row in enumerate(native_roots) if index not in native_direct]
        inputs = boundary["inputs"]
        outputs = boundary["outputs"]
        if not isinstance(inputs, Mapping) or set(inputs) != {"caller", "callee"} or not isinstance(outputs, Mapping) or set(outputs) != {"caller", "callee"}:
            self.fail("call_boundary", "boundary input/output partitions are malformed", node)
        try:
            caller_input_rows = compiled_boundary_rows(caller_projected)
            native_input_rows = compiled_boundary_rows(native_projected)
            caller_output_rows = compiled_boundary_rows(
                [("return", node["type"])],
                output=True,
                relax_inactive_union_paths=node["type"]["kind"] == "union",
            )
            native_output_rows = compiled_boundary_rows(
                [("return", definition["result"])],
                output=True,
                relax_inactive_union_paths=definition["result"]["kind"] == "union",
            )
        except (TypeError, ValueError, RecursionError) as exc:
            self.fail("call_boundary", f"boundary descriptors cannot derive wire rows: {exc}", node)
        for partition, expected in (
            (inputs, {"caller": caller_input_rows, "callee": native_input_rows}),
            (outputs, {"caller": caller_output_rows, "callee": native_output_rows}),
        ):
            for side in ("caller", "callee"):
                rows = partition[side]
                if not isinstance(rows, list) or not self._same(rows, expected[side]):
                    self.fail("call_boundary", f"boundary {side} projection rows differ from descriptors", node)
        self._require_projected_roots_covered(caller_projected, inputs["caller"], node)
        self._require_projected_roots_covered(native_projected, inputs["callee"], node)
        self._require_projected_roots_covered([("return", node["type"])], outputs["caller"], node)
        self._require_projected_roots_covered([("return", definition["result"])], outputs["callee"], node)
        self.pending_boundaries.append(
            {
                "node": node,
                "definition": definition,
                "capture_prefix": capture_prefix,
                "caller_roots": caller_roots,
                "native_roots": native_roots,
                "caller_projected": caller_projected,
                "native_projected": native_projected,
                "inputs": inputs,
                "outputs": outputs,
            }
        )

    def _check_pending_boundaries(self) -> None:
        """Check identity-sensitive boundary facts after all producer S values exist."""

        for pending in self.pending_boundaries:
            node = pending["node"]
            capture_prefix = pending["capture_prefix"]
            caller_roots = pending["caller_roots"]
            native_roots = pending["native_roots"]
            for capture_index, capture in enumerate(capture_prefix):
                try:
                    caller_projected = key_type_descriptor(
                        caller_roots[capture_index][1],
                        run_ref_signatures=self.run_ref_signatures,
                    )
                    native_projected = key_type_descriptor(
                        native_roots[capture_index][1],
                        run_ref_signatures=self.run_ref_signatures,
                    )
                except (TypeError, ValueError, RecursionError) as exc:
                    self.fail("call_boundary", f"capture descriptor cannot be projected: {exc}", node)
                if not self._same(caller_projected, capture["type"]) or not self._same(native_projected, capture["type"]):
                    self.fail("call_boundary", "callee capture prefix differs from its canonical key schema", node)

            definition = pending["definition"]
            endpoints = (
                (
                    pending["inputs"]["caller"],
                    pending["inputs"]["callee"],
                    pending["caller_projected"],
                    pending["native_projected"],
                ),
                (
                    pending["outputs"]["caller"],
                    pending["outputs"]["callee"],
                    [("return", node["type"])],
                    [("return", definition["result"])],
                ),
            )
            for caller_rows, native_rows, caller_roots_side, native_roots_side in endpoints:
                caller_facts = self._generated_boundary_facts(caller_roots_side, caller_rows, node)
                native_facts = self._generated_boundary_facts(native_roots_side, native_rows, node)
                self._check_generated_boundary_units(
                    caller_rows, native_rows, caller_facts, native_facts, node
                )
                if not self._boundary_rows_compatible(
                    caller_rows, native_rows, caller_facts, native_facts, node=node
                ):
                    self.fail("call_boundary", "caller and callee wire rows are incompatible", node)

    def _normalize_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "name": row["name"],
            "contract": normalize_boundary_contract_definition(row["contract"]),
        }

    def _require_projected_roots_covered(
        self,
        roots: list[tuple[str, Mapping[str, Any]]],
        rows: list[Mapping[str, Any]],
        node: Any,
    ) -> None:
        covered: set[str] = set()
        root_names = {name for name, _ in roots}
        for row in rows:
            path = row.get("path")
            if not isinstance(path, list) or not path or path[0] not in root_names:
                self.fail("call_boundary", "projection row has no valid root path", node)
            covered.add(path[0])
        if covered != root_names:
            self.fail("call_boundary", "projected roots do not have exhaustive wire rows", node)

    def _generated_boundary_facts(
        self,
        roots: list[tuple[str, Mapping[str, Any]]],
        rows: list[Mapping[str, Any]],
        node: Any,
    ) -> dict[str, Any]:
        """Derive protected units and terminal type facts from one endpoint."""

        by_name = {row["name"]: row for row in rows}
        units: list[dict[str, Any]] = []
        terminals: dict[str, list[tuple[tuple[tuple[str, str], ...], str, bool]]] = {}
        domains: dict[str, tuple[str, ...]] = {}

        def projected(descriptor: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
            try:
                key_type = key_type_descriptor(
                    dict(descriptor), run_ref_signatures=self.run_ref_signatures
                )
                dependencies = run_ref_type_dependencies(dict(descriptor))
            except (TypeError, ValueError, RecursionError) as exc:
                self.fail("call_boundary", f"generated boundary descriptor cannot be projected: {exc}", node)
            return key_type, dependencies

        def identity_has_generated(identity: Any) -> bool:
            if isinstance(identity, Mapping):
                if identity.get("kind") == "run-ref-result":
                    return True
                return any(identity_has_generated(value) for value in identity.values())
            if isinstance(identity, list):
                return any(identity_has_generated(value) for value in identity)
            return False

        def record_terminal(
            wire_name: str,
            descriptor: Mapping[str, Any],
            activation: tuple[tuple[str, str], ...],
        ) -> None:
            if wire_name not in by_name:
                self.fail("call_boundary", "derived endpoint path has no serialized wire row", node)
            key_type, dependencies = projected(descriptor)
            terminals.setdefault(wire_name, []).append(
                (activation, self._canonical(key_type), bool(dependencies))
            )

        def selector_domain(wire_name: str, variants: tuple[str, ...]) -> None:
            row = by_name.get(wire_name)
            if (
                row is None
                or not isinstance(row.get("contract"), Mapping)
                or row["contract"].get("type") != "enum"
                or row["contract"].get("allowed") != list(variants)
            ):
                self.fail("call_boundary", "union selector row does not carry its declared discriminator domain", node)
            previous = domains.get(wire_name)
            if previous is not None and previous != variants:
                self.fail("call_boundary", "one selector wire has conflicting discriminator domains", node)
            domains[wire_name] = variants

        def walk(
            descriptor: Mapping[str, Any],
            *,
            wire_root: str,
            path: tuple[str, ...],
            activation: tuple[tuple[str, str], ...],
            protected_ancestor: bool,
        ) -> None:
            kind = descriptor["kind"]
            key_type, dependencies = projected(descriptor)
            identity = None
            if kind in {"record", "union", "enum"}:
                identity = key_type.get("name")
            elif kind == "variant_case":
                identity = key_type.get("union_name")
            generated_identity = identity_has_generated(identity)
            generated_envelope = key_type.get("kind") == "run-ref-result"
            terminal_descriptor = kind not in {"record", "union"}
            is_unit = generated_envelope or generated_identity or (
                terminal_descriptor and bool(dependencies)
            )
            under_protected = protected_ancestor or is_unit
            if is_unit and not protected_ancestor:
                footprint = tuple(
                    sorted(
                        (
                            row["name"],
                            tuple(row["path"][len(path) :]),
                        )
                        for row in rows
                        if isinstance(row.get("path"), list)
                        and tuple(row["path"][: len(path)]) == path
                    )
                )
                if not footprint:
                    self.fail("call_boundary", "generated boundary unit has an empty wire footprint", node)
                units.append(
                    {
                        "activation": activation,
                        "footprint": footprint,
                        "descriptor": self._canonical(key_type),
                    }
                )

            if kind == "record":
                for field in descriptor["fields"]:
                    walk(
                        field["type"],
                        wire_root=f"{wire_root}__{field['name']}",
                        path=(*path, field["name"]),
                        activation=activation,
                        protected_ancestor=under_protected,
                    )
                return
            if kind == "union":
                variant_names = tuple(variant["name"] for variant in descriptor["variants"])
                selector = f"{wire_root}__variant"
                selector_domain(selector, variant_names)
                enum = {
                    "kind": "enum",
                    "name": f"{descriptor['name']}.variant",
                    "allowed": list(variant_names),
                }
                record_terminal(selector, enum, activation)
                for variant in descriptor["variants"]:
                    child_activation = (*activation, (selector, variant["name"]))
                    for field in variant["fields"]:
                        walk(
                            field["type"],
                            wire_root=f"{wire_root}__{field['name']}",
                            path=(*path, field["name"]),
                            activation=child_activation,
                            protected_ancestor=under_protected,
                        )
                return
            if terminal_descriptor:
                record_terminal(wire_root, descriptor, activation)

        for root_name, descriptor in roots:
            walk(
                descriptor,
                wire_root=root_name,
                path=(root_name,),
                activation=(),
                protected_ancestor=False,
            )
        return {"units": units, "terminals": terminals, "domains": domains}

    def _generated_boundary_assignments(
        self,
        selectors: set[str],
        domains: Mapping[str, tuple[str, ...]],
        activations: Sequence[tuple[tuple[str, str], ...]],
        node: Any,
    ) -> list[dict[str, str]]:
        """Enumerate only branch distinctions that affect these units or rows."""

        variants_by_selector: dict[str, set[str]] = {name: set() for name in selectors}
        for activation in activations:
            for selector, variant in activation:
                if selector not in selectors or selector not in domains or variant not in domains[selector]:
                    self.fail("call_boundary", "generated boundary activation has no matching discriminator row", node)
                variants_by_selector[selector].add(variant)
        options: list[list[str | None]] = []
        names = sorted(selectors)
        for selector in names:
            declared = domains[selector]
            selected = variants_by_selector[selector]
            choices: list[str | None] = [variant for variant in declared if variant in selected]
            if any(variant not in selected for variant in declared):
                choices.append(None)
            options.append(choices or [None])
        return [
            {name: variant for name, variant in zip(names, choice, strict=True) if variant is not None}
            for choice in (product(*options) if options else [()])
        ]

    @staticmethod
    def _generated_activation_is_active(
        activation: tuple[tuple[str, str], ...], assignment: Mapping[str, str]
    ) -> bool:
        return all(assignment.get(selector) == variant for selector, variant in activation)

    def _check_generated_boundary_units(
        self,
        caller_rows: list[Mapping[str, Any]],
        native_rows: list[Mapping[str, Any]],
        caller: Mapping[str, Any],
        native: Mapping[str, Any],
        node: Any,
    ) -> None:
        caller_by_name = {row["name"]: row for row in caller_rows}
        native_by_name = {row["name"]: row for row in native_rows}
        for selector in set(caller["domains"]) | set(native["domains"]):
            left, right = caller_by_name.get(selector), native_by_name.get(selector)
            if (
                left is None
                or right is None
                or not isinstance(left.get("contract"), Mapping)
                or not isinstance(right.get("contract"), Mapping)
                or left["contract"].get("type") != "enum"
                or right["contract"].get("type") != "enum"
                or left["contract"].get("allowed") != right["contract"].get("allowed")
            ):
                self.fail("call_boundary", "paired union selector rows have different variant domains", node)

        caller_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        native_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for facts, groups in ((caller, caller_groups), (native, native_groups)):
            for unit in facts["units"]:
                groups.setdefault(unit["footprint"], []).append(unit)
        common_domains = {**native["domains"], **caller["domains"]}
        for footprint in set(caller_groups) | set(native_groups):
            left_units = caller_groups.get(footprint, [])
            right_units = native_groups.get(footprint, [])
            activations = [unit["activation"] for unit in (*left_units, *right_units)]
            selectors = {selector for activation in activations for selector, _ in activation}
            assignments = self._generated_boundary_assignments(
                selectors, common_domains, activations, node
            )
            for assignment in assignments:
                left = sorted(
                    unit["descriptor"]
                    for unit in left_units
                    if self._generated_activation_is_active(unit["activation"], assignment)
                )
                right = sorted(
                    unit["descriptor"]
                    for unit in right_units
                    if self._generated_activation_is_active(unit["activation"], assignment)
                )
                if left != right:
                    self.fail("call_boundary", "generated boundary units differ for an active union assignment", node)

    def _boundary_rows_compatible(
        self,
        caller_rows: list[Mapping[str, Any]],
        native_rows: list[Mapping[str, Any]],
        caller: Mapping[str, Any],
        native: Mapping[str, Any],
        *,
        node: Any,
    ) -> bool:
        caller_by_name = {row["name"]: row for row in caller_rows}
        native_by_name = {row["name"]: row for row in native_rows}
        if set(caller_by_name) != set(native_by_name):
            return False
        domains = {**native["domains"], **caller["domains"]}
        for name, caller_row in caller_by_name.items():
            native_row = native_by_name[name]
            left_contract = normalize_boundary_contract_definition(caller_row["contract"])
            right_contract = normalize_boundary_contract_definition(native_row["contract"])
            if self._same(left_contract, right_contract):
                continue
            left_terminals = caller["terminals"].get(name, [])
            right_terminals = native["terminals"].get(name, [])
            if not left_terminals or not right_terminals:
                return False
            activations = [row[0] for row in (*left_terminals, *right_terminals)]
            selectors = {selector for activation in activations for selector, _ in activation}
            assignments = self._generated_boundary_assignments(
                selectors, domains, activations, node
            )
            for assignment in assignments:
                left_active = [
                    (descriptor, generated)
                    for activation, descriptor, generated in left_terminals
                    if self._generated_activation_is_active(activation, assignment)
                ]
                right_active = [
                    (descriptor, generated)
                    for activation, descriptor, generated in right_terminals
                    if self._generated_activation_is_active(activation, assignment)
                ]
                if not left_active and not right_active:
                    continue
                if (
                    not left_active
                    or not right_active
                    or any(not generated for _, generated in (*left_active, *right_active))
                    or sorted(descriptor for descriptor, _ in left_active)
                    != sorted(descriptor for descriptor, _ in right_active)
                ):
                    return False
        return True
