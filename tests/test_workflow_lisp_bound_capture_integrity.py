"""Owner-local freeze obligations in the existing preparation equality guard."""

from dataclasses import fields, is_dataclass, replace

import pytest

from orchestrator.workflow_lisp.closed.preparation_check import assert_same_prepared_body
from orchestrator.workflow_lisp.wcc import model as w
from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
from tests.test_workflow_lisp_closed_preparation_integrity import _shadow_program
from tests.test_workflow_lisp_closed_command_transport import _compile, _command


def _request(root):
    _, children, builder = _prepared_entry(_shadow_program(root))
    request, = children.values()
    incoming = request.procedure.typed_body.binding_environment["n"]
    local = request.prepared_body.metadata.binding_identity
    assert incoming != local
    return request, builder, incoming, local


@pytest.mark.parametrize("mode", ["missing", "retargeted", "unknown"])
def test_retention_obligation_cannot_be_removed_or_retargeted(tmp_path, mode):
    first, builder, incoming, local = _request(tmp_path)
    first = replace(first, retained_capture_bindings=frozenset({incoming}))
    replacements = {"missing": frozenset(), "retargeted": frozenset({local}),
        "unknown": frozenset({replace(incoming, path=("unknown",))})}
    second = replace(first, retained_capture_bindings=replacements[mode])
    with pytest.raises(ValueError, match="contradictory prepared.*retention"):
        assert_same_prepared_body(first, second, builder=builder)


def _rebind_wcc_identities(node, replacements):
    if isinstance(node, w.WccNodeMetadata):
        return replace(node, binding_identity=replacements.get(
            node.binding_identity, node.binding_identity))
    if isinstance(node, tuple):
        return tuple(_rebind_wcc_identities(item, replacements) for item in node)
    if is_dataclass(node) and type(node).__module__ == w.__name__:
        return replace(node, **{field.name: _rebind_wcc_identities(
            getattr(node, field.name), replacements) for field in fields(node) if field.init})
    return node


def test_fresh_alpha_equivalent_incoming_and_local_obligations_are_accepted(tmp_path):
    first, builder, incoming, local = _request(tmp_path)
    fresh_incoming = replace(incoming, path=("fresh", "incoming"), ordinal=10)
    fresh_local = replace(local, path=("fresh", "local"), ordinal=20)
    replacements = {incoming: fresh_incoming, local: fresh_local}
    first = replace(first, retained_capture_bindings=frozenset(replacements))
    typed = replace(first.procedure.typed_body,
        binding_environment={"n": fresh_incoming})
    second = replace(first, procedure=replace(first.procedure, typed_body=typed),
        prepared_body=_rebind_wcc_identities(first.prepared_body, replacements),
        retained_capture_bindings=frozenset(replacements.values()))
    assert first.retained_capture_bindings != second.retained_capture_bindings
    assert_same_prepared_body(first, second, builder=builder)


def test_discarded_preparation_does_not_leak_its_owner_retention(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed.build import Builder

    declarations = '(defproc helper ((n Int)) -> Int :effects ((uses-command echo)) '
    declarations += ':lowering inline ' + _command('"${inputs.n}"') + ')'
    program = _compile(tmp_path, '(helper 3)', declarations=declarations)
    builder = Builder(program)
    original = builder._prepare_command_owner
    observed = []
    discarded = object()

    def observe(callable_def, source, context, **kwargs):
        relevant = callable_def.definition.name.endswith("helper")
        if relevant:
            observed.append(context.capture_binding_identities)
        result = original(callable_def, source, context, **kwargs)
        if relevant and len(observed) == 1:
            context.capture_binding_identities |= {discarded}
        return result

    monkeypatch.setattr(builder, "_prepare_command_owner", observe)
    _prepared_entry(program, builder=builder)
    assert len(observed) == 2
    assert discarded not in observed[1]
