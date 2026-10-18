"""Read-only source-site manifest over one in-memory checked build.

Contract: docs/design/workflow_lisp_source_site_inspection.md §3. Input is the `ClosedProgramBuildResult` of
`prepare_closed_program_bundle` with its retained `typed_program`, `stage3` and `builder`. Authored sites come
from each definition's typed body in the files the caller names; per-node types and binders come from the
owner's normalized WCC body; executable rows come from the closed program. Nothing is written, nothing is
inferred from text, and a fact the build does not hold is reported as "unavailable" with an exclusion reason.

Owner WCC bodies (probe P-1, tests/test_workflow_lisp_source_sites_probe.py): callee bodies are the builder's
retained `prepared_body`, one request per canonical key in `Builder.prepared_by_key` (the builder asserts that
a repeated key prepared the same body); the entry body is re-elaborated once as `_build_with_builder`
elaborates it, without a call preparator, which leaves the builder and the artifact unchanged.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

from orchestrator.contracts.closed_program.node_walk import _ast_nodes

from .closed.names import canonical_type_identity
from .expression_traversal import walk_expr
from .expressions import (
    AgentExpr,
    CallExpr,
    CondExpr,
    IfExpr,
    LetStarExpr,
    ListMapEffectExpr,
    ListMapExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    RunProviderPhaseExpr,
    RunRefExpr,
)
from .loops import LoopControlTypeRef
from .procedures import TypedProcedureDef, procedure_effect_inspection
from .prompts import PromptApplicationExpr
from .syntax import ExpansionFrame
from .type_env import render_type_ref
from .wcc.model import (
    WccCall,
    WccCase,
    WccCaseArm,
    WccIf,
    WccLet,
    WccListMap,
    WccNodeMetadata,
    WccParallelMap,
    WccPerform,
    WccRecJoin,
    WccSelect,
)

# Provenance and frontend carriers hold no WCC nodes; `Builder._wcc_workflow_calls` skips the same fields.
SKIPPED_WCC_FIELDS = frozenset({"metadata", "body_metadata", "type_ref", "source_span", "form_path",
    "expansion_stack", "bound_proc_source", "source_binding"})
# Fields of a binder node that its binder scopes over (a let binds in its body, not in its bound value).
_SCOPED_FIELDS = frozenset({"body", "workspace_body"})

_KINDS = {ProviderResultExpr: "provider-call", RunProviderPhaseExpr: "provider-phased-call",
    AgentExpr: "agent-turn", ProcedureCallExpr: "procedure-call", CallExpr: "workflow-call", RunRefExpr: "run-ref",
    LetStarExpr: "let*", IfExpr: "if", CondExpr: "cond", MatchExpr: "match", LoopRecurExpr: "loop",
    ListMapExpr: "list-map", ListMapEffectExpr: "list-map"}
# The WCC node that carries an authored site's value at the site's start; `let*` is anchored separately.
_VALUE_NODES = {"provider-call": (WccPerform,), "provider-phased-call": (WccPerform,), "agent-turn": (WccPerform,),
    "procedure-call": (WccCall,), "workflow-call": (WccPerform,), "run-ref": (WccPerform,),
    "if": (WccIf, WccSelect), "cond": (WccIf, WccSelect), "match": (WccCase,), "loop": (WccRecJoin,),
    "list-map": (WccListMap, WccParallelMap)}
_PROVIDER_FORMS = (ProviderResultExpr, AgentExpr, RunProviderPhaseExpr)

Position = tuple[str, int, int]


def wcc_value_nodes(body: Any) -> list[Any]:
    """Every WCC node reachable from `body` (each object once, pre-order) that carries `WccNodeMetadata`."""
    return [node for node, _ in _scoped_nodes(body)]


def _scoped_nodes(body: Any) -> Iterator[tuple[Any, tuple]]:
    """`wcc_value_nodes` paired with the binders in scope at each node, outermost first.

    A binder is `(name, identity, type_ref)` of an enclosing `WccLet`, `WccCaseArm`, `WccListMap` or
    `WccParallelMap`; it scopes over the node's `body`/`workspace_body` fields only.
    """
    seen, pending = set(), [(body, ())]
    while pending:
        node, chain = pending.pop()
        if node is None or isinstance(node, (str, bytes, int, float, bool, Path)) or id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, Mapping):
            pending.extend((value, chain) for value in reversed(list(node.values())))
        elif isinstance(node, (tuple, list)):
            pending.extend((value, chain) for value in reversed(node))
        elif is_dataclass(node) and not isinstance(node, type):
            if isinstance(getattr(node, "metadata", None), WccNodeMetadata):
                yield node, chain
            binder = _binder(node)
            inner = chain if binder is None else (*chain, binder)
            pending.extend((getattr(node, f.name), inner if f.name in _SCOPED_FIELDS else chain)
                for f in reversed(fields(node)) if f.name not in SKIPPED_WCC_FIELDS)


def _binder(node: Any) -> tuple[str, object, Any] | None:
    if isinstance(node, WccLet):
        return node.bound_name, node.metadata.binding_identity, node.bound_type_ref
    if isinstance(node, WccCaseArm):
        return node.binding_name, node.binding_identity, node.binding_type_ref
    if isinstance(node, (WccListMap, WccParallelMap)):
        return node.binder_name, node.binding_identity, node.binder_type_ref
    return None


def reelaborate_entry(result) -> Any:
    """The entry's normalized WCC body, elaborated as `_build_with_builder` does but with no call preparator."""
    typed, entry = result.typed_program, result.typed_program.entry
    return result.builder._command_wcc_body(entry, typed,
        type_env=typed.workflow_type_env(entry.definition.name), value_env=dict(entry.signature.params))


def _prepared_owners(result) -> list[tuple[str, Any, Any]]:
    """(closed owner canonical name, typed callable it lowers, normalized WCC body) for every closed owner."""
    tree = result.program.tree
    rows = [(request.canonical, getattr(request, "procedure", None) or request.workflow, request.prepared_body)
        for request in result.builder.prepared_by_key.values()]
    rows.append((tree["entry"], result.typed_program.entry, reelaborate_entry(result)))
    owners, expected = [row[0] for row in rows], {tree["entry"], *tree["definitions"]}
    if len(owners) != len(set(owners)) or set(owners) != expected:
        raise ValueError(f"prepared owners {sorted(owners)} do not match the closed owners {sorted(expected)}")
    return rows


def owner_wcc_bodies(result) -> dict[str, Any]:
    """Closed owner canonical name -> normalized WCC body: callees retained by the builder, entry re-elaborated."""
    return {owner: body for owner, _, body in _prepared_owners(result)}


def _parse_position(span: str) -> Position:
    path, line, column = span.rsplit(":", 2)
    return path, int(line), int(column)


def closed_perform_rows(program) -> list[tuple[str, str, Position]]:
    """(owner, site label path, `@` start) for every perform node of every closed owner body."""
    return [(owner, node["site"], _parse_position(node["@"]["span"]))
        for owner, node in _closed_nodes(program) if node.get("k") == "perform"]


def _closed_nodes(program) -> list[tuple[str, dict]]:
    tree = program.tree
    owners = [(tree["entry"], tree["body"]), *((name, row["body"]) for name, row in tree["definitions"].items())]
    return [(owner, node) for owner, body in owners for node in _ast_nodes(body)]


def _key(position) -> Position:
    return position.path, position.line, position.column


def _within(position: Position, span) -> bool:
    path, line, column = position
    return path == span.start.path and (span.start.line, span.start.column) <= (line, column) < (
        span.end.line, span.end.column)


class _Build:
    """Facts of one build shared by every site record: lowerings, closed rows, digests and paths."""

    def __init__(self, result, root: Path, files: Sequence[Path]) -> None:
        self.result, self.typed, self.root = result, result.typed_program, root.resolve()
        named = {str((self.root / file).resolve()) for file in files}
        sources = {str(path): module for module, path in self.typed._io_source_paths.items()}
        if missing := named - sources.keys():
            raise ValueError(f"named files are not sources of this build: {sorted(missing)}")
        self.named = named
        self.digests = {path: f"sha256:{self.typed.source_file_digests[sources[path]]}" for path in named}
        self.lowerings: dict[str, list] = defaultdict(list)
        for owner, callable_def, body in _prepared_owners(result):
            index = defaultdict(list)
            for node, chain in _scoped_nodes(body):
                index[_key(node.metadata.source_span.start)].append((node, chain))
            self.lowerings[_base_name(callable_def)].append((owner, callable_def, index))
        self.rows = closed_perform_rows(result.program)
        self.closed = defaultdict(list)
        for owner, node in _closed_nodes(result.program):
            if node.get("k") in {"perform", "call"} and "@" in node:
                self.closed[owner].append(node)

    def relative(self, path: str) -> str:
        return Path(path).relative_to(self.root).as_posix()

    def type_row(self, type_ref) -> tuple[str, str]:
        return canonical_type_identity(type_ref, typed=self.typed), render_type_ref(type_ref)


def build_manifest(result, *, root: Path, files: Sequence[Path]) -> dict:
    """Source-site manifest of `result` for the authored definitions of `files` (paths relative to `root`).

    Returns a JSON-serializable mapping `{build_key, program_digest, target, entry, file_digests, sites}`;
    `sites` maps `<owner canonical name>@<path relative to root>:<line>:<column>` to one record per eligible
    expression kind (§3.2), sorted by site id. Raises ValueError when a named file is not a source of the build
    or the builder's prepared owners do not match the closed program's owners.
    """
    build = _Build(result, root, files)
    sites: dict[str, dict] = {}
    for owner, kind, typed_def, authored in _indexed_definitions(build):
        authored_binders = _authored_binders(typed_def.typed_body.expr)
        for node in walk_expr(typed_def.typed_body.expr):
            record = _site_record(build, (owner, kind, typed_def, authored, authored_binders), node)
            if record is not None:  # pre-order: an outer form keeps a start an inner form reuses
                sites.setdefault(record["site_id"], record)
    return {"build_key": result.build_key, "program_digest": result.program.digest, "target": build.typed.target,
        "entry": result.program.tree["entry"],
        "file_digests": {build.relative(path): digest for path, digest in sorted(build.digests.items())},
        "sites": dict(sorted(sites.items()))}


def _indexed_definitions(build: _Build) -> Iterator[tuple[str, str, Any, bool]]:
    """(owner canonical name, kind, typed definition, authored) per base definition in the named files.

    A specialization is grouped under the definition it specializes, which represents the group when it is
    in the typed program. A group whose representative is a specialization or a generated local procedure
    reports its sites as `generated-definition`.
    """
    groups: dict[str, list] = defaultdict(list)
    for typed_def in [*build.typed.workflows.values(), *build.typed.procedures.values()]:
        if typed_def.definition.span.start.path in build.named:
            groups[_base_name(typed_def)].append(typed_def)
    for base, group in groups.items():
        typed_def = next((member for member in group if member.signature.name == base), group[0])
        kind = "procedure" if isinstance(typed_def, TypedProcedureDef) else "workflow"
        name = typed_def.signature.name
        # ponytail: compiler-generated callables are named `%...`; use a builder flag if one is added.
        authored = typed_def.specialization is None and not name.rpartition("::")[2].startswith("%")
        yield f"{kind}:{name}", kind, typed_def, authored


def _base_name(callable_def: Any) -> str:
    """The definition a callable lowers: its specialization's base, else itself."""
    return getattr(callable_def.specialization, "base_name", None) or callable_def.signature.name


def _authored_binders(expr: Any) -> frozenset:
    """Binding identities the author wrote in this body: not introduced by any expansion or normalization."""
    identities = set()
    for node in walk_expr(expr):
        if getattr(node, "expansion_stack", ()):
            continue
        identities.update(getattr(node, "binding_identities", ()))
        identities.add(getattr(node, "binding_identity", None))
        if isinstance(node, MatchExpr):
            identities.update(arm.binding_identity for arm in node.arms if not arm.expansion_stack)
    identities.discard(None)
    return frozenset(identities)


def _site_record(build: _Build, owner_row: tuple, node: Any) -> dict | None:
    owner, kind, typed_def, authored, authored_binders = owner_row
    site_kind = _KINDS.get(type(node))
    frames = node.expansion_stack if site_kind else ()
    # ponytail: helper- and procedure-inlined nodes are left to the authored-call pass (plan Task 3).
    if site_kind is None or any(not isinstance(frame, ExpansionFrame) for frame in frames):
        return None
    lowerings = build.lowerings.get(_base_name(typed_def), [])
    facts = _facts(build, lowerings, site_kind, node, authored_binders)
    start, end = node.span.start, node.span.end
    return {
        "site_id": f"{owner}@{build.relative(start.path)}:{start.line}:{start.column}",
        "span": {"start": _position(build, start), "end": _position(build, end)},
        "file_digest": build.digests[start.path],
        "owner": {"kind": kind, "name": owner, "form_path": list(node.form_path)},
        "kind": site_kind,
        "result_type": facts["result_type"],
        "bindings": facts["bindings"],
        "dependencies": _dependencies(build, lowerings, node, owner),
        # WCC effect nodes carry the owner body's summary (`wcc/elaborate.py` threads `typed_body.effect_summary`
        # to every node), not the expression's; no retained carrier holds per-expression inferred effects.
        "effects": {"inferred": "unavailable", "restriction": _restriction(build, typed_def)},
        "executable_sites": sorted([row_owner, label] for row_owner, label, position in build.rows
            if position == _key(start)),
        "authored_calls": [{"callee_kind": call.callee_kind, "callee_name": call.callee_name}
            for call in build.result.stage3.authored_direct_calls or ()
            if _within(_key(call.authored_callee_span.start), node.span)],
        "eligibility": _eligibility(authored, bool(frames), facts),
    }


def _position(build: _Build, position) -> dict:
    return {"path": build.relative(position.path), "line": position.line, "column": position.column,
        "offset": position.offset}


def _eligibility(authored: bool, macro: bool, facts: dict) -> str:
    if not authored:
        return "generated-definition"
    if macro:
        return "macro-generated"
    if facts.get("loop_control"):
        return "loop-control"
    return "facts-unavailable" if facts["result_type"] == "unavailable" else "eligible"


_UNAVAILABLE = {"result_type": "unavailable", "bindings": []}


def _facts(build: _Build, lowerings: list, site_kind: str, node: Any, authored_binders: frozenset) -> dict:
    """Result type and bindings of the node's WCC counterpart, equal in every lowering.

    Unavailable when the definition has no lowering, a lowering has no single counterpart at the anchor, or
    lowerings disagree (a generic definition specialized to different types).
    """
    if site_kind == "let*":
        anchor, classes = _key(node.bindings[0][1].span.start) if node.bindings else None, (WccLet,)
    else:
        anchor, classes = _key(node.span.start), _VALUE_NODES[site_kind]
    found = set()
    for _, callable_def, index in lowerings:
        matches = [(wcc, chain) for wcc, chain in index.get(anchor, ()) if isinstance(wcc, classes)
            and (site_kind != "let*" or wcc.metadata.binding_identity in node.binding_identities[:1])]
        if len(matches) != 1:
            return _UNAVAILABLE
        found.add(_lowering_facts(build, callable_def, *matches[0], authored_binders))
    if len(found) != 1:
        return _UNAVAILABLE
    type_row, bindings = found.pop()
    if type_row is None:
        return {**_UNAVAILABLE, "loop_control": True}
    canonical, rendered = type_row
    return {"result_type": {"canonical": canonical, "rendered": rendered},
        "bindings": [{"name": name, "identity": _identity(identity), "type": type_name}
            for name, identity, type_name in bindings]}


def _lowering_facts(build: _Build, callable_def: Any, wcc: Any, chain: tuple, authored_binders: frozenset):
    """(type row, or None for loop control, and binding rows) for one lowering.

    Hashable, so lowerings of one definition can be compared.
    """
    environment = callable_def.typed_body.binding_environment
    params = [(name, environment.get(name), type_ref) for name, type_ref in callable_def.signature.params]
    rows: dict[str, tuple] = {}
    for name, identity, type_ref in (*params, *(row for row in chain if row[1] in authored_binders)):
        rows.pop(name, None)  # the innermost binder of a repeated name wins and moves last
        rows[name] = (identity, canonical_type_identity(type_ref, typed=build.typed))
    bindings = tuple((name, identity, type_name) for name, (identity, type_name) in rows.items())
    type_ref = wcc.metadata.type_ref
    type_row = None if isinstance(type_ref, LoopControlTypeRef) else build.type_row(type_ref)
    return type_row, bindings


def _identity(identity: object) -> Any:
    """A `BindingIdentity` as plain JSON values, or "unavailable"."""
    return "unavailable" if identity is None else json.loads(json.dumps(asdict(identity)))


def _restriction(build: _Build, typed_def: Any) -> str:
    if not isinstance(typed_def, TypedProcedureDef):
        return "omitted"
    return procedure_effect_inspection(typed_def, build.typed.procedures)[0].removeprefix("restriction: ")


def _dependencies(build: _Build, lowerings: list, node: Any, owner: str) -> dict:
    """Prompt and provider bindings named in the site's subtree; commands and callees of its closed nodes."""
    prompts, providers, commands, callees = set(), set(), set(), set()
    for child in (child for child in walk_expr(node) if isinstance(child, _PROVIDER_FORMS)):
        if isinstance(child.provider, NameExpr):
            providers.add(child.provider.name)
        prompt = getattr(child, "prompt", None)  # an agent turn names no prompt
        if isinstance(prompt, NameExpr):
            prompts.add(prompt.name)
        elif isinstance(prompt, PromptApplicationExpr):
            prompts.add(prompt.prompt.qualified_name)
    for closed_owner, _, _ in lowerings:
        for closed in build.closed[closed_owner]:
            if not _within(_parse_position(closed["@"]["span"]), node.span):
                continue
            if closed["k"] == "call":
                callees.add(closed["callee"])
            elif "boundary" in closed:
                commands.add(closed["boundary"])
    own_module = owner.partition(":")[2].partition("::")[0]
    modules = {callee.partition(":")[2].partition("::")[0] for callee in callees} - {own_module}
    return {"prompts": sorted(prompts), "providers": sorted(providers), "commands": sorted(commands),
        "modules": sorted(modules), "callees": sorted(callees)}
