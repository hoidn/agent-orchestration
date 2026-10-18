"""Probe P-1 and F-a of docs/design/workflow_lisp_source_site_inspection.md on real compiler products.

P-1: per-node WCC metadata is obtainable for every owner of one build. Callee bodies are retained on the
builder (`CallableRequest`/`WorkflowRequest.prepared_body`); the entry body is re-elaborated with the
arguments `_build_with_builder` passes, without a call preparator, and must match the compiled body.
F-a: every closed perform node's `@` start matches exactly one `WccPerform` start in its owner's WCC body and
one closed-program site row.
"""

import time

import pytest

from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.source_sites import (
    closed_perform_rows,
    owner_wcc_bodies,
    reelaborate_entry,
    wcc_value_nodes,
)
from orchestrator.workflow_lisp.wcc.model import WccPerform
from tests.test_workflow_lisp_source_sites import EXAMPLES as EXAMPLES_ROOT, compile_source

EXAMPLES = [("plan_review_execute", "plan_review_execute::run"),
    ("improve_experiment_proposal", "improve_experiment_proposal::run-experiment")]


def compile_in_process(stem: str, entry: str):
    """Compile one maintained example with its inputs directory's externs; returns the bundle result."""
    return compile_source(EXAMPLES_ROOT / f"{stem}.orc", entry, root=EXAMPLES_ROOT,
        externs=EXAMPLES_ROOT / "inputs" / stem)


def key(position) -> tuple[str, int, int]:
    return position.path, position.line, position.column


def metadata_sequence(body) -> list[tuple]:
    """Each node's metadata with the two binder fields that `WccNodeMetadata` equality leaves out."""
    return [(node.metadata, node.metadata.binding_label, node.metadata.binding_identity)
        for node in wcc_value_nodes(body)]


def authored_name(owner: str) -> str:
    """The definition a closed owner lowers: its canonical name without the specialization key."""
    return owner.partition("[")[0]


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


@pytest.mark.parametrize(("stem", "entry"), EXAMPLES)
def test_every_closed_perform_start_matches_one_wcc_perform_in_its_owner(stem, entry):
    result = compile_in_process(stem, entry)
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
    for owner, site, start in perform_rows:
        assert len([node for row_owner, node in starts.get(start, []) if row_owner == owner]) == 1


@pytest.mark.parametrize(("stem", "entry"), EXAMPLES)
def test_closed_perform_rows_are_exactly_the_unique_site_rows(stem, entry):
    result = compile_in_process(stem, entry)
    rows = [(owner, site) for owner, site, _ in closed_perform_rows(result.program)]
    assert (len(rows) == len(set(rows)), set(rows)) == (True, set(result.program.sites))


@pytest.mark.parametrize(("stem", "entry"), EXAMPLES)
def test_a_start_repeats_across_owners_only_for_specializations_of_one_definition(stem, entry):
    owners_by_start = {}
    for owner, _, start in closed_perform_rows(compile_in_process(stem, entry).program):
        owners_by_start.setdefault(start, set()).add(owner)
    repeated = [owners for owners in owners_by_start.values() if len(owners) > 1]
    assert all(len({authored_name(owner) for owner in owners}) == 1 for owners in repeated)


def test_retained_callee_bodies_equal_reelaborated_bodies_node_for_node(captured_owners):
    result = compile_in_process(*EXAMPLES[1])
    by_body = {id(body): row for row in captured_owners for body in [row[3]]}
    requests = list(result.builder.prepared_by_key.values())
    assert requests, "fixture must prepare callees"
    for request in requests:
        callable_def, source_program, kwargs, _ = by_body[id(request.prepared_body)]
        again = result.builder._command_wcc_body(callable_def, source_program, **kwargs)
        assert metadata_sequence(again) == metadata_sequence(request.prepared_body)


@pytest.mark.parametrize(("stem", "entry"), EXAMPLES)
def test_entry_reelaboration_equals_compiled_entry_body(stem, entry, captured_owners):
    result = compile_in_process(stem, entry)
    (compiled,) = [body for callable_def, _, _, body in captured_owners if callable_def is result.typed_program.entry]
    assert metadata_sequence(reelaborate_entry(result)) == metadata_sequence(compiled)


@pytest.mark.parametrize(("stem", "entry"), EXAMPLES)
def test_entry_reelaboration_leaves_artifact_bytes_unchanged(stem, entry):
    result = compile_in_process(stem, entry)
    before = build_closed_program(result.typed_program).artifact()
    reelaborate_entry(result)
    assert build_closed_program(result.typed_program).artifact() == before == result.program.artifact()


def _container_sizes(builder):
    return {name: len(value) for name, value in vars(builder).items() if isinstance(value, (dict, list, set))}


@pytest.mark.parametrize(("stem", "entry"), EXAMPLES)
def test_entry_reelaboration_leaves_builder_containers_unchanged(stem, entry):
    result = compile_in_process(stem, entry)
    before = _container_sizes(result.builder)
    reelaborate_entry(result)
    assert _container_sizes(result.builder) == before


@pytest.mark.parametrize(("stem", "entry"), EXAMPLES)
def test_reelaboration_cost_is_recorded(stem, entry, captured_owners, capsys):
    started = time.perf_counter()
    result = compile_in_process(stem, entry)
    compile_seconds = time.perf_counter() - started
    owners = {id(request.prepared_body): request.canonical for request in result.builder.prepared_by_key.values()}
    elapsed = {}
    for callable_def, source_program, kwargs, body in captured_owners:
        owner = result.program.tree["entry"] if callable_def is result.typed_program.entry else owners.get(id(body))
        if owner is not None:
            started = time.perf_counter()
            result.builder._command_wcc_body(callable_def, source_program, **kwargs)
            elapsed[owner] = time.perf_counter() - started
    with capsys.disabled():
        print(f"\n{stem}: compile {compile_seconds:.4f}s; re-elaboration per owner " + ", ".join(
            f"{name} {seconds:.4f}s" for name, seconds in elapsed.items()))
    assert (set(elapsed), sum(elapsed.values()) < 3 * compile_seconds) == (set(owner_wcc_bodies(result)), True)
