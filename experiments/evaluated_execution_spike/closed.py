"""The closed program: the elaborated program with every callee body attached and only calculus left.

Input: the typechecked program of `frontend.typecheck_program`. The elaborator and
the normal-form pass of the compiler run unchanged; their output (WCC) is
translated into plain JSON nodes (the node kinds are listed in `sites.py`).

Where the elaborator does not give a property of the design's section 4, this
module either supplies it and says so in a comment naming the property, or
raises `ClosedProgramGap` naming it:

- P1: callee bodies are elaborated here, once per call site, as the flat route
  does during lowering (`defunctionalize._lower_wcc_procedure_call`).
- P2: `WccOpaqueFrontendValue` (loop-state seeds and updates, lists, nonempty
  list heads, variant tags, inlined pure calls) is replaced here by catalog nodes
  or by elaborating the surface expression it holds with the elaborator's own
  body path. `repairs.py` holds the two repairs applied to the elaborator's input.
- P3: output contracts are derived here, with the function lowering uses; the
  command, adapter document and prompt (asset path, or template and fills) are
  resolved here from the build environment.
- P6/P7: provenance is kept under the key "@" and left out of the digest.
  Generated names are renamed `%<n>`, and specialized callees are named by
  their canonical identity, because the elaborator's names for both digest
  `repr(TypeRef)`, which holds file paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from orchestrator.workflow.pure_expr import validate_pure_expr_payload
from orchestrator.workflow_lisp.context_classification import _is_run_context_shape
from orchestrator.workflow_lisp.effects import EMPTY_EFFECT_SUMMARY
from orchestrator.workflow_lisp.expressions import (
    CompilerListNonemptyHeadExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    ListExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    NameExpr,
    ProviderBundlePathExpr,
    UnionVariantTagExpr,
)
from orchestrator.workflow_lisp.lowering.values import _procedure_signature_local_type_bindings
from orchestrator.workflow_lisp.normalized_type_descriptor import _module_export_info, compiler_normalized_type_descriptor
from orchestrator.workflow_lisp.type_env import DiscriminantTypeRef
from orchestrator.workflow_lisp.wcc import model as w
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import _elaborate_expr_to_body, elaborate_typed_workflow_body

from .closed_effects import translate_perform
from .frontend import TypedProgram
from .repairs import bind_done_values, elaboration_return_types
from .sites import ClosedProgram, assign_sites, canonical_digest, strip_provenance, validate

SCHEMA = "evaluated-execution-spike/closed-program/1"
ROUTE = w.WCC_M4_ROUTE_SCHEMA_VERSION
# The compiler-supplied `run` context (a `RunCtx`-shaped record) at a call that leaves it out: the run's
# identity, which the evaluator supplies, and the two roots the flat route binds (`_runtime_context_default_value`).
RUN_CONTEXT = {"k": "record", "fields": [["run-id", {"k": "context", "field": "run-id"}],
                                         ["state-root", {"k": "lit", "v": "state/run"}],
                                         ["artifact-root", {"k": "lit", "v": "artifacts/run"}]]}


class ClosedProgramGap(Exception):
    """A property of the design's section 4 that could not be obtained; `prop` names it (P1..P7)."""

    def __init__(self, prop: str, message: str) -> None:
        super().__init__(f"[{prop}] {message}")
        self.prop = prop


CLOSURE_OPTIONS = ("declared", "strict", "trusting")


def build_closed_program(
    typed: TypedProgram,
    *,
    no_repeat: frozenset[str] = frozenset(),
    closure: str = "declared",
    closures: Mapping[str, list[str]] | None = None,
) -> ClosedProgram:
    """`no_repeat` names command boundaries whose effect must not run again without a commit (section 8).

    `closure` is what a committed command's resolved input binds of what the command runs:
    - `declared`: the stable command's workspace paths (files, or directories as their sorted files with
      digests), the program resolved on PATH when it is a bare name, and the implementation closure the
      boundary declares in `closures` (files and directories); a symbolic link also by the path it resolves
      to. Anything else, modification times included, is outside the promise.
    - `strict`: as `declared`; a command boundary without a declared closure is refused here.
    - `trusting`: nothing (the present route).
    """

    if closure not in CLOSURE_OPTIONS:
        raise ValueError(f"closure option `{closure}` is not one of {CLOSURE_OPTIONS}")
    builder = _Builder(typed, no_repeat)
    builder.closure, builder.closures = closure, dict(closures or {})
    entry = typed.entry
    name = entry.definition.name
    d = _Def(name, name, typed.workflow_type_env(name))
    params = [[d.bind(param), d.desc(type_ref)] for param, type_ref in entry.signature.params]
    wcc = builder.elaborate_workflow(entry, d.type_env)
    body = builder.body(normalize_wcc_body_to_anf(wcc), d, dict(entry.signature.params))
    defaults = {d.ref(n): default.normalized_value for n, default in entry.signature.param_defaults.items()}
    tree = {
        "schema": SCHEMA,
        "closure": closure,
        "entry": name,
        "params": params,
        "defaults": defaults,
        "result": d.desc(entry.signature.return_type_ref),
        "body": body,
    }
    sites = assign_sites(tree)
    validate(tree)
    return ClosedProgram(tree=tree, sites=tuple(sites), digest=canonical_digest(strip_provenance(tree)))


@dataclass
class _Def:
    """One definition body being translated: its canonical name, elaborator owner and type environment."""

    canonical: str
    owner: str
    type_env: Any
    renames: dict[str, str] = field(default_factory=dict)
    loops: list[str] = field(default_factory=list)

    def bind(self, name: str) -> str:
        if not name.startswith("__"):
            return name
        # P7: generated names digest their owner, which for a specialized callee digests file paths.
        self.renames[name] = f"%{len(self.renames) + 1}"
        return self.renames[name]

    def ref(self, name: str) -> str:
        return self.renames.get(name, name)

    def desc(self, type_ref: Any) -> dict[str, Any]:
        if isinstance(type_ref, DiscriminantTypeRef):
            return {"kind": "enum", "name": type_ref.union_name + ".variant", "allowed": list(type_ref.variant_names)}
        return compiler_normalized_type_descriptor(type_ref, type_env=self.type_env)


def _provenance(node: Any) -> dict[str, Any]:
    metadata = getattr(node, "metadata", None)
    span = getattr(metadata, "source_span", None)
    start = getattr(span, "start", None)
    if start is None:
        return {}
    return {"@": {"span": f"{start.path}:{start.line}:{start.column}", "form": list(metadata.form_path)}}


def _type_id(type_ref: Any, d: _Def) -> str:
    """The canonical identity of a type: declaring module and name, and its arguments (section 6)."""

    item = getattr(type_ref, "item_type_ref", None)
    if item is not None:
        return f"{type(type_ref).__name__.removesuffix('TypeRef')}[{_type_id(item, d)}]"
    name = str(d.desc(type_ref).get("name", type_ref.name))
    start = getattr(getattr(getattr(type_ref, "definition", None), "span", None), "start", None)
    if "::" not in name and start is not None and not start.path.startswith("<"):
        # P6: a type records its declaring module only through the file path of its span.
        info = _module_export_info(start.path)
        name = f"{info[0]}::{name}" if info else name
    return name


class _Builder:
    def __init__(self, typed: TypedProgram, no_repeat: frozenset[str]) -> None:
        self.typed = typed
        self.no_repeat = no_repeat
        self.active: tuple[str, ...] = ()
        self.opaque_count = 0
        self.procedure_returns = elaboration_return_types(typed.procedures)
        self.workflow_returns = {n: wf.signature.return_type_ref for n, wf in typed.workflows.items()}

    # Bodies ---------------------------------------------------------------

    def body(self, node: Any, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        lets = []
        while isinstance(node, w.WccLet):
            value = self.binding(node.bound_value, d, env)
            lets.append((node, d.bind(node.bound_name), value))
            env = {**env, node.bound_name: node.bound_type_ref}
            node = node.body
        result = self.tail(node, d, env)
        for let, name, value in reversed(lets):
            result = {"k": "let", "name": name, "value": value, "body": result, **_provenance(let)}
        return result

    def tail(self, node: Any, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        handler = {
            w.WccHalt: self.halt, w.WccIf: self.branch, w.WccCase: self.case, w.WccJoin: self.join,
            w.WccJump: self.jump, w.WccRecJoin: self.loop, w.WccLoopContinue: self.cont, w.WccLoopDone: self.done,
        }.get(type(node))
        if handler is None:
            raise ClosedProgramGap("P2", f"body node {type(node).__name__} has no closed form")
        return {**handler(node, d, env), **_provenance(node)}

    def halt(self, node: w.WccHalt, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        return {"k": "halt", "value": self.value(node.result, d, env)}

    def done(self, node: w.WccLoopDone, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        return {"k": "done", "value": self.value(node.result, d, env)}

    def branch(self, node: w.WccIf, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        return {"k": "if", "cond": self.value(node.condition, d, env),
                "then": self.body(node.then_body, d, env), "else": self.body(node.else_body, d, env)}

    def case(self, node: w.WccCase, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        return {"k": "case", "subject": self.value(node.subject, d, env), "arms": [
            {"variant": arm.variant_name, "bind": d.bind(arm.binding_name),
             "body": self.body(arm.body, d, {**env, arm.binding_name: arm.binding_type_ref})}
            for arm in node.arms
        ]}

    def jump(self, node: w.WccJump, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        return {"k": "jump", "join": d.ref(node.join_name), "args": [self.value(a, d, env) for a in node.args]}

    def cont(self, node: w.WccLoopContinue, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        # The elaborator leaves `__wcc_current_loop__` on a `continue` under a join; the target
        # is the innermost loop by construction, so the closed program names it.
        return {"k": "continue", "loop": d.loops[-1], "args": [self.value(a, d, env) for a in node.state_args]}

    def join(self, node: w.WccJoin, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        name = d.bind(node.join_name)
        body = self.body(node.body, d, env)
        params = [d.bind(p.name) for p in node.params]
        cont = self.body(node.continuation, d, {**env, **{p.name: p.type_ref for p in node.params}})
        return {"k": "join", "name": name, "params": params, "body": body, "cont": cont}

    def loop(self, node: w.WccRecJoin, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        if len(node.params) != 1:
            raise ClosedProgramGap("P2", f"loop with {len(node.params)} state parameters")
        (param,) = node.params
        budget, init = self.value(node.budget, d, env), self.value(node.initial_state, d, env)
        name, pname = d.bind(node.loop_name), d.bind(param.name)
        inner = {**env, param.name: param.type_ref}
        d.loops.append(name)
        body = self.body(node.body, d, inner)
        d.loops.pop()
        exhausted = None if node.exhaustion is None else self.body(node.exhaustion, d, inner)
        return {"k": "loop", "name": name, "param": pname, "budget": budget, "init": init, "body": body,
                "exhausted": exhausted, "code": node.exhaustion_diagnostic_code}

    # Bound values ---------------------------------------------------------

    def binding(self, value: Any, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        if isinstance(value, w.WccPerform):
            if value.perform_kind == "workflow_call":
                return self.workflow_call(value, d, env)
            return {**self.perform(value, d, env), **_provenance(value)}
        if isinstance(value, w.WccCall):
            return {**self.call(value, d, env), **_provenance(value)}
        if isinstance(value, (w.WccProviderSupervision, w.WccProviderPeerGroup)):
            raise ClosedProgramGap("P3", f"{type(value).__name__} is a coordinator effect without a performer")
        return self.value(value, d, env)

    def call(self, call: w.WccCall, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        procs = self.typed.procedures
        procedure = procs.get(call.specialized_callee_name) or procs.get(call.callee_name)
        if procedure is None:
            raise ClosedProgramGap("P1", f"call target `{call.callee_name}` is not a typed procedure")
        if call.specialization_captures:
            raise ClosedProgramGap("P1", "specialization captures (bind-proc) are not attached")
        params = procedure.signature.params
        if len(call.args) != len(params):
            raise ClosedProgramGap("P1", f"`{call.callee_name}` takes {len(params)} arguments, the call has {len(call.args)}")
        callee = self.definition_id(procedure)
        name = procedure.definition.name
        callee_def = _Def(callee, name, self.typed.procedure_type_env(procedure))
        value_env = _procedure_signature_local_type_bindings(procedure)
        # P1: the flat route elaborates this body during lowering; here it is attached to the call.
        wcc = elaborate_typed_workflow_body(
            bind_done_values(procedure.typed_body),
            owner_name=name,
            type_env=callee_def.type_env,
            value_env=value_env,
            workflow_return_types=self.workflow_returns,
            procedure_return_types=self.procedure_returns,
            route_schema_version=ROUTE,
        )
        return self.attach(callee, callee_def, [p for p, _ in params], call.args, wcc, value_env, d, env)

    def workflow_call(self, perform: w.WccPerform, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        workflow = self.typed.workflows.get(perform.target_name)
        if workflow is None:
            raise ClosedProgramGap("P1", f"workflow `{perform.target_name}` is not in the typechecked program")
        name = workflow.definition.name
        callee_def = _Def(name, name, self.typed.workflow_type_env(name))
        by_name = {p: self.value(v, d, env) for p, v in perform.keyword_args}
        params = [p for p, _ in workflow.signature.params]
        wcc = self.elaborate_workflow(workflow, callee_def.type_env)
        defaults = workflow.signature.param_defaults
        for param, type_ref in workflow.signature.params:  # a parameter the call leaves out takes its default
            if param not in by_name and param in defaults:
                by_name[param] = {"k": "lit", "v": defaults[param].normalized_value}
            elif param not in by_name and _is_run_context_shape(type_ref):
                by_name[param] = RUN_CONTEXT
        missing = [p for p in params if p not in by_name]
        if missing:
            raise ClosedProgramGap("P1", f"workflow call of `{name}` binds no value to {missing}")
        args = [by_name[p] for p in params]
        return self.attach(name, callee_def, params, args, wcc, dict(workflow.signature.params), d, env)

    def elaborate_workflow(self, workflow: Any, type_env: Any) -> Any:
        return elaborate_typed_workflow_body(
            bind_done_values(workflow.typed_body),
            owner_name=workflow.definition.name,
            type_env=type_env,
            value_env=dict(workflow.signature.params),
            workflow_return_types=self.workflow_returns,
            procedure_return_types=self.procedure_returns,
            resolved_procedures_by_name=self.typed.procedures,
            procedure_type_envs=self.typed.procedure_type_envs,
            route_schema_version=ROUTE,
        )

    def attach(self, callee, callee_def, params, args, wcc, value_env, d, env) -> dict[str, Any]:
        if callee in self.active:
            raise ClosedProgramGap("P1", f"recursive call of `{callee}`")
        closed_args = [a if isinstance(a, dict) else self.value(a, d, env) for a in args]
        self.active = (*self.active, callee)
        try:
            bound = [callee_def.bind(p) for p in params]
            body = self.body(normalize_wcc_body_to_anf(wcc), callee_def, dict(value_env))
        finally:
            self.active = self.active[:-1]
        return {"k": "call", "callee": callee, "params": bound, "args": closed_args, "body": body}

    def definition_id(self, procedure: Any) -> str:
        """P6: a specialized procedure is named by its base and the canonical identity of its arguments."""

        spec = procedure.specialization
        if spec is None:
            return procedure.definition.name
        if spec.value_bindings or spec.workflow_ref_bindings:
            raise ClosedProgramGap("P6", f"specialization of `{spec.base_name}` binds values or workflows")
        d = _Def("", "", self.typed.procedure_type_env(procedure))
        args = [f"{k}={_type_id(t, d)}" for k, t in sorted(spec.type_bindings.items())]
        for key, ref in sorted(spec.proc_ref_bindings.items()):
            if getattr(ref, "bound_args", ()):
                raise ClosedProgramGap("P6", f"proc-ref `{key}` of `{spec.base_name}` has bound arguments")
            target = self.typed.procedures.get(ref.procedure_name)
            args.append(f"{key}={self.definition_id(target) if target else ref.procedure_name}")
        return f"{spec.base_name}[{', '.join(args)}]"

    def perform(self, perform: w.WccPerform, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        return translate_perform(self, perform, d, env)

    # Values ---------------------------------------------------------------

    def value(self, value: Any, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        kind = type(value)
        if kind is w.WccLiteralAtom:
            return {"k": "lit", "v": value.value}
        if kind is w.WccNameAtom:
            return {"k": "name", "n": d.ref(value.name)}
        if kind is w.WccFieldAccessAtom:
            return {"k": "field", "base": self.value(value.base, d, env), "path": list(value.fields)}
        if kind is w.WccRecordAtom:
            return {"k": "record", "fields": [[n, self.value(f, d, env)] for n, f in value.fields]}
        if kind is w.WccInject:
            return {"k": "inject", "variant": value.variant_name,
                    "fields": [[n, self.value(f, d, env)] for n, f in value.fields]}
        if kind is w.WccPureOp:
            return self.op(value, d, env)
        if kind is w.WccSelect:
            return {"k": "select", "cond": self.value(value.condition, d, env),
                    "then": self.arm(value.then_arm, d, env), "else": self.arm(value.else_arm, d, env)}
        if kind is w.WccOpaqueFrontendValue:
            return self.opaque(value, d, env)
        if kind is w.WccPhaseTargetAtom:
            # Its value is the phase context's target field (`execution_report_target`), or
            # `<ctx.artifact-root>/<phase>/<target>.md` for a generic `PhaseCtx`; but the atom keeps only the
            # target's name, and normal form lifts it out of the effect whose metadata holds the phase scope.
            raise ClosedProgramGap("P2", f"`phase-target {value.target_name}` has lost its `with-phase` scope")
        raise ClosedProgramGap("P2", f"value {kind.__name__} has no closed form")

    def arm(self, arm: w.WccSelectArm, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        prefix = []
        for let in arm.prefix:
            value = self.binding(let.bound_value, d, env)
            prefix.append({"name": d.bind(let.bound_name), "value": value})
            env = {**env, let.bound_name: let.bound_type_ref}
        return {"prefix": prefix, "value": self.value(arm.value, d, env)}

    def op(self, op: w.WccPureOp, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        """A pure operator as a payload of the catalog of `pure_expr.py`, with one binding per argument."""

        refs = [{"kind": "binding", "name": f"a{i}"} for i in range(len(op.args))]
        types = [a.metadata.type_ref for a in op.args]
        if op.operator == "record-update":
            expr = {"kind": "record_update", "record_type": d.desc(op.metadata.type_ref), "base": refs[0],
                    "fields": [{"name": n, "value": r} for n, r in zip(op.field_names, refs[1:])]}
        else:
            expr = {"kind": "op", "operator": op.operator, "args": refs}
        return {**self.payload(expr, op.metadata.type_ref, types, [self.value(a, d, env) for a in op.args], d),
                **_provenance(op)}

    def payload(self, expr, result, arg_types, args, d: _Def) -> dict[str, Any]:
        """`result` and `arg_types` are type references, or descriptors already derived."""

        desc = lambda t: t if isinstance(t, dict) else d.desc(t)  # noqa: E731
        payload = {
            "pure_expr_schema_version": 2,
            "result_type": desc(result),
            "bindings": {f"a{i}": {"type": desc(t)} for i, t in enumerate(arg_types)},
            "expr": expr,
        }
        validate_pure_expr_payload(payload)  # P5: the catalog types every operator when the program is built
        return {"k": "op", "payload": payload, "args": args}

    def opaque(self, value: w.WccOpaqueFrontendValue, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        """P2: the surface expressions the elaborator passes through, elaborated here."""

        expr = value.expr
        if isinstance(expr, UnionVariantTagExpr):
            return {"k": "lit", "v": expr.variant_name}
        if isinstance(expr, LoopStateSeedExpr):
            return {"k": "record", "fields": [[f.name, self.frontend(f.value_expr, d, env)] for f in expr.fields]}
        if isinstance(expr, ListExpr):
            return {"k": "list", "items": [self.frontend(item, d, env) for item in expr.items]}
        if isinstance(expr, LoopStateUpdateExpr):
            return {**self.loop_state_update(expr, value.metadata.type_ref, d, env), **_provenance(value)}
        if isinstance(expr, CompilerListNonemptyHeadExpr):  # the head of a list that `list/map-effect` knows nonempty
            item = d.desc(expr.element_type_ref)
            head = {"kind": "list_nonempty_head", "source": {"kind": "binding", "name": "a0"}, "element_type": item,
                    "compiler_owned": True, "invariant_diagnostic": "list_nonempty_invariant_broken"}
            source = [self.frontend(expr.source_expr, d, env)]
            return {**self.payload(head, item, [{"kind": "list", "item": item}], source, d), **_provenance(value)}
        if isinstance(expr, IfExpr):  # below target 2.26 the elaborator keeps a pure `if` opaque, parts included
            return {"k": "select", "cond": self.frontend(expr.condition_expr, d, env),
                    "then": {"prefix": [], "value": self.frontend(expr.then_expr, d, env)},
                    "else": {"prefix": [], "value": self.frontend(expr.else_expr, d, env)}}
        if isinstance(expr, LetStarExpr):  # an inlined pure call
            return self.frontend(expr, d, env)
        if isinstance(expr, GeneratedRelpathSeedExpr):  # a compiler-private path seed: its literal path (unverified)
            return {"k": "lit", "v": expr.literal_path}
        if isinstance(expr, ProviderBundlePathExpr) and isinstance(expr.source_expr, NameExpr):
            return {"k": "result_path", "n": d.ref(expr.source_expr.name)}
        raise ClosedProgramGap("P2", f"surface value {type(expr).__name__} has no closed form")

    def loop_state_update(self, expr: LoopStateUpdateExpr, carrier: Any, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        """`(loop-state :like base :f v ...)` is `record-update` of the catalog on the carrier record."""

        names = [name for name, _ in expr.overrides]
        refs = [{"kind": "binding", "name": f"a{i}"} for i in range(len(names) + 1)]
        update = {"kind": "record_update", "record_type": d.desc(carrier), "base": refs[0],
                  "fields": [{"name": n, "value": r} for n, r in zip(names, refs[1:])]}
        args = [self.frontend(expr.base_expr, d, env), *(self.frontend(e, d, env) for _, e in expr.overrides)]
        return self.payload(update, carrier, [carrier, *(carrier.field_types[n] for n in names)], args, d)

    def frontend(self, expr: Any, d: _Def, env: dict[str, Any]) -> dict[str, Any]:
        if isinstance(expr, NameExpr):
            return {"k": "name", "n": d.ref(expr.name)}
        self.opaque_count += 1
        scope = w.WccIdentityFactory(owner_name=d.owner, lexical_owner_chain=("spike-opaque", str(self.opaque_count)),
                                     route_schema_version=ROUTE)
        wcc = _elaborate_expr_to_body(
            expr, scope=scope, type_env=d.type_env, value_env=env, workflow_return_types=self.workflow_returns,
            procedure_return_types=self.procedure_returns, effect_summary=EMPTY_EFFECT_SUMMARY,
            procedure_edges_by_site={}, compile_time_bindings={},
        )
        body = self.body(normalize_wcc_body_to_anf(wcc), d, env)
        return body["value"] if body["k"] == "halt" else {"k": "block", "body": body}
