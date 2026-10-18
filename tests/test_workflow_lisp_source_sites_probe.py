"""Probe P-1 and F-a of docs/design/workflow_lisp_source_site_inspection.md on real compiler products.

P-1: per-node WCC metadata is obtainable for every owner of one build. Callee bodies are retained on the
builder (`CallableRequest`/`WorkflowRequest.prepared_body`); the entry body is re-elaborated with the
arguments `_build_with_builder` passes, without a call preparator, and must match the compiled body.
F-a: every closed perform node's `@` start matches exactly one `WccPerform` start in its owner's WCC body and
one closed-program site row.
"""

import time
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping

import pytest

from orchestrator.contracts.closed_program.node_walk import _ast_nodes
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle
from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.wcc.model import WccNodeMetadata, WccPerform

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = ["workflows/examples/plan_review_execute.orc", "workflows/examples/improve_experiment_proposal.orc"]
ENTRIES = {"plan_review_execute": "plan_review_execute::run",
    "improve_experiment_proposal": "improve_experiment_proposal::run-experiment"}
# Same exclusions as Builder._wcc_workflow_calls: provenance and frontend carriers hold no WCC nodes.
_SKIPPED_FIELDS = {"metadata", "body_metadata", "type_ref", "source_span", "form_path", "expansion_stack",
    "bound_proc_source", "source_binding"}


def compile_in_process(source: str):
    """Compile one maintained example with its inputs directory's externs; returns the bundle result."""
    stem = Path(source).stem
    inputs = REPO / "workflows/examples/inputs" / stem
    optional = {"prompt_externs_path": inputs / "prompts.json", "command_boundaries_path": inputs / "commands.json"}
    return prepare_closed_program_bundle(FrontendBuildRequest(
        source_path=REPO / source, source_roots=(REPO / "workflows/examples",), entry_workflow=ENTRIES[stem],
        provider_externs_path=inputs / "providers.json", workspace_root=REPO,
        **{name: path for name, path in optional.items() if path.exists()},
    ), source_read_trace=SourceReadTrace())


def wcc_value_nodes(body: Any) -> list[Any]:
    """Every WCC node reachable from `body` (each object once) that carries `WccNodeMetadata`."""
    nodes, seen, pending = [], set(), [body]
    while pending:
        node = pending.pop()
        if node is None or isinstance(node, (str, bytes, int, float, bool, Path)) or id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, Mapping):
            pending.extend(reversed(list(node.values())))
        elif isinstance(node, (tuple, list)):
            pending.extend(reversed(node))
        elif is_dataclass(node) and not isinstance(node, type):
            if isinstance(getattr(node, "metadata", None), WccNodeMetadata):
                nodes.append(node)
            pending.extend(reversed([getattr(node, f.name) for f in fields(node) if f.name not in _SKIPPED_FIELDS]))
    return nodes


def reelaborate_entry(result):
    """The entry's normalized WCC body, elaborated as `_build_with_builder` does but with no call preparator."""
    typed, entry = result.typed_program, result.typed_program.entry
    return result.builder._command_wcc_body(entry, typed,
        type_env=typed.workflow_type_env(entry.definition.name), value_env=dict(entry.signature.params))


def owner_wcc_bodies(result) -> dict[str, Any]:
    """Closed owner canonical name -> normalized WCC body: callees retained by the builder, entry re-elaborated."""
    bodies = {request.canonical: request.prepared_body for request in result.builder.completed_preparations.values()}
    bodies[result.program.tree["entry"]] = reelaborate_entry(result)
    return bodies


def closed_perform_rows(program) -> list[tuple[str, str, str]]:
    """(owner, site label path, `@` span) for every perform node of every closed owner body."""
    tree = program.tree
    owners = [(tree["entry"], tree["body"]), *((name, row["body"]) for name, row in tree["definitions"].items())]
    return [(owner, node["site"], node["@"]["span"])
        for owner, body in owners for node in _ast_nodes(body) if node.get("k") == "perform"]


def parse_span(span: str) -> tuple[str, int, int]:
    path, line, column = span.rsplit(":", 2)
    return path, int(line), int(column)


def key(position) -> tuple[str, int, int]:
    return position.path, position.line, position.column


def metadata_sequence(body) -> list[WccNodeMetadata]:
    return [node.metadata for node in wcc_value_nodes(body)]


@pytest.fixture
def captured_owners(monkeypatch):
    """Record every `_prepare_command_owner` call of the next compile: (callable_def, source, kwargs, body)."""
    calls, actual = [], Builder._prepare_command_owner

    def capture(self, callable_def, source_program, d, **kwargs):
        body, prepared = actual(self, callable_def, source_program, d, **kwargs)
        calls.append((callable_def, source_program, {**kwargs, "value_env": dict(kwargs["value_env"])}, body))
        return body, prepared

    monkeypatch.setattr(Builder, "_prepare_command_owner", capture)
    return calls


@pytest.mark.parametrize("source", EXAMPLES)
def test_every_closed_perform_start_matches_one_wcc_perform_and_one_site_row(source):
    result = compile_in_process(source)
    bodies = owner_wcc_bodies(result)
    starts = {}
    for owner, body in bodies.items():
        for node in wcc_value_nodes(body):
            if isinstance(node, WccPerform):
                starts.setdefault(key(node.metadata.source_span.start), []).append((owner, node))
    perform_rows = closed_perform_rows(result.program)
    assert perform_rows, "fixture must contain perform nodes"
    # A specialized definition repeats one authored start under several owners (design §3.2 executable_sites),
    # so the start is unique within its owner, not across owners.
    for owner, site, span in perform_rows:
        assert len([node for row_owner, node in starts.get(parse_span(span), []) if row_owner == owner]) == 1
        assert (owner, site) in result.program.sites


def test_retained_callee_bodies_equal_reelaborated_bodies_node_for_node(captured_owners):
    result = compile_in_process("workflows/examples/improve_experiment_proposal.orc")
    by_body = {id(body): row for row in captured_owners for body in [row[3]]}
    requests = list(result.builder.completed_preparations.values())
    assert requests, "fixture must prepare callees"
    for request in requests:
        callable_def, source_program, kwargs, _ = by_body[id(request.prepared_body)]
        again = result.builder._command_wcc_body(callable_def, source_program, **kwargs)
        assert metadata_sequence(again) == metadata_sequence(request.prepared_body)


@pytest.mark.parametrize("source", EXAMPLES)
def test_entry_reelaboration_equals_compiled_entry_body(source, captured_owners):
    result = compile_in_process(source)
    (compiled,) = [body for callable_def, _, _, body in captured_owners if callable_def is result.typed_program.entry]
    assert metadata_sequence(reelaborate_entry(result)) == metadata_sequence(compiled)


@pytest.mark.parametrize("source", EXAMPLES)
def test_entry_reelaboration_leaves_artifact_bytes_unchanged(source):
    result = compile_in_process(source)
    before = build_closed_program(result.typed_program).artifact()
    reelaborate_entry(result)
    assert build_closed_program(result.typed_program).artifact() == before == result.program.artifact()


def _container_sizes(builder):
    return {name: len(value) for name, value in vars(builder).items() if isinstance(value, (dict, list, set))}


@pytest.mark.parametrize("source", EXAMPLES)
def test_entry_reelaboration_leaves_builder_containers_unchanged(source):
    result = compile_in_process(source)
    before = _container_sizes(result.builder)
    reelaborate_entry(result)
    assert _container_sizes(result.builder) == before


@pytest.mark.parametrize("source", EXAMPLES)
def test_reelaboration_cost_is_recorded(source, captured_owners, capsys):
    started = time.perf_counter()
    result = compile_in_process(source)
    compile_seconds = time.perf_counter() - started
    owners = {id(request.prepared_body): request.canonical
        for request in result.builder.completed_preparations.values()}
    elapsed = {}
    for callable_def, source_program, kwargs, body in captured_owners:
        owner = result.program.tree["entry"] if callable_def is result.typed_program.entry else owners.get(id(body))
        if owner is not None:
            started = time.perf_counter()
            result.builder._command_wcc_body(callable_def, source_program, **kwargs)
            elapsed[owner] = time.perf_counter() - started
    with capsys.disabled():
        print(f"\n{source}: compile {compile_seconds:.4f}s; re-elaboration per owner " + ", ".join(
            f"{name} {seconds:.4f}s" for name, seconds in elapsed.items()))
    assert sum(elapsed.values()) < 3 * compile_seconds
