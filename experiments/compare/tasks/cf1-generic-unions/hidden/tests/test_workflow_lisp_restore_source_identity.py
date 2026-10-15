"""Checkpoint sources resolve by compiled identity, independently of node order."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.workflow.executor import WorkflowExecutor
from tests.test_workflow_lisp_lexical_checkpoint_restore import (
    FIXTURE,
    _compile_fixture,
    _force_materialize_view_resume_state,
    _prepare_failed_run,
    _restore_module,
)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("nested_scope", [False, True])
def test_restore_source_requires_exact_name_and_step_id(
    tmp_path: Path, reverse: bool, nested_scope: bool,
):
    bundle = _compile_fixture(tmp_path)
    point = next(point for point in bundle.runtime_plan.lexical_checkpoint_points
                 if point.details.get("restore", {}).get("proof_descriptors"))
    descriptor = point.details["restore"]["proof_descriptors"][0]
    original = next(node for node in bundle.ir.nodes.values()
                    if node.presentation_name == descriptor["source_step_name"])
    if nested_scope:
        scoped_id = "root.parent.CASE." + descriptor["source_step_id"]
        original = replace(original, node_id=scoped_id, step_id=scoped_id,
                           lexical_scope=tuple(scoped_id.split(".")))
    other = replace(original, node_id="root.other", step_id="root.other",
                    presentation_name="other." + original.presentation_name)
    nodes = [other, original]
    if reverse:
        nodes.reverse()
    executable = SimpleNamespace(nodes={node.node_id: node for node in nodes})
    resolve = _restore_module().resolve_restore_source_node

    assert resolve(executable_workflow=executable, descriptor=descriptor) is original
    assert resolve(executable_workflow=executable, descriptor={
        **descriptor, "source_step_id": "other",
    }) is None
    assert resolve(executable_workflow=executable, descriptor={
        **descriptor, "source_step_name": original.presentation_name.rsplit("__", 1)[-1],
    }) is None
    assert resolve(executable_workflow=executable, descriptor={}) is None
    duplicate = replace(original, node_id="root.duplicate", step_id="root.duplicate")
    executable.nodes[duplicate.node_id] = duplicate
    assert resolve(executable_workflow=executable, descriptor=descriptor) is None


def test_resume_preserves_ordinary_record_field_named_ref(tmp_path: Path) -> None:
    source = (FIXTURE.read_text().replace("(label String", "(ref String")
              .replace(":label", ":ref").replace(".label", ".ref")
              .replace("(loop_count Int)", "(loop_count Int) (loop_ref String)")
              .replace(":loop_count loop_result.count",
                       ":loop_count loop_result.count :loop_ref loop_result.ref"))
    bundle, manager, first = _prepare_failed_run(
        tmp_path, run_id="restore-record-ref-field", source=source,
    )
    assert first["status"] == "failed"
    _force_materialize_view_resume_state(manager, bundle)

    resumed = WorkflowExecutor(bundle, tmp_path, manager).execute(resume=True)

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"]["return__loop_ref"] == "tick"
    assert resumed["workflow_outputs"]["return__loop_count"] == 1
