"""2.29 scoped union-proof regressions for pure-projection output groups."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import PreparedProviderPolicy
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.executable_ir import NodeResultAddress
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.pure_expr import pure_expr_payload_digest
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow.validation import (
    WorkflowMappingBuildRequest,
    validate_workflow_mapping,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.workflow_bundle_helpers import bundle_context_dict
from tests.workflow_fixture_loader import WorkflowLoader


TWO_GROUP_LOOP_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defrecord Task (task_id String))
  (defrecord Progress (remaining List[Task]) (label String))
  (defrecord Summary (work List[Task]) (note String))
  (defunion Left
    (SAME (summary Summary))
    (OTHER (note String))
    (THIRD (third_note String)))
  (defunion Right
    (SAME (summary Summary))
    (OTHER (note String))
    (THIRD (third_note String)))
  (defrecord Result (left Left) (right Right))
  (defworkflow two-independent-union-groups
    ((tasks List[Task]) (finish Bool)) -> Result
    (loop/recur :max 1
      :state (record Progress :remaining tasks :label "state")
      :on-exhausted
        (record Result
          :left (variant Left SAME
            :summary (record Summary :work state.remaining :note state.label))
          :right (variant Right OTHER :note "right-exhausted"))
      (fn (state)
        (if finish
            (done (record Result
              :left (variant Left OTHER :note "left-done")
              :right (variant Right SAME
                :summary (record Summary :work state.remaining :note "right-done"))))
            (continue state))))))
"""


TWO_GROUP_PROVIDER_LOOP_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defrecord Task (task_id String))
  (defrecord Progress (remaining List[Task]) (label String))
  (defrecord Summary (work List[Task]) (note String))
  (defunion Left
    (SAME (summary Summary))
    (OTHER (note String))
    (THIRD (third_note String)))
  (defunion Right
    (SAME (summary Summary))
    (OTHER (note String))
    (THIRD (third_note String)))
  (defrecord Result (left Left) (right Right))
  (defworkflow two-independent-union-groups ((finish Bool)) -> Result
    (let* ((tasks
             (provider-result providers.seed
               :prompt prompts.seed
               :inputs ()
               :returns List[Task])))
      (loop/recur :max 2
        :state (record Progress :remaining tasks :label "state")
        :on-exhausted
          (record Result
            :left (variant Left SAME
              :summary (record Summary :work state.remaining :note state.label))
            :right (variant Right OTHER :note "right-exhausted"))
        (fn (state)
          (if finish
              (done (record Result
                :left (variant Left OTHER :note "left-done")
                :right (variant Right SAME
                  :summary (record Summary :work state.remaining :note "right-done"))))
              (continue state)))))))
"""


STRUCTURAL_LITERAL_FIELD_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defrecord Task (task_id String))
  (defrecord Report (__literal String) (remaining List[Task]))
  (defworkflow structural-literal-field ((tasks List[Task])) -> Report
    (record Report :__literal "literal" :remaining tasks)))
"""


STRUCTURAL_LITERAL_FIELD_COLLISION_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defrecord Nested (b String))
  (defrecord Collision (a__b String) (a Nested))
  (defworkflow structural-literal-field-collision () -> Collision
    (record Collision :a__b "flat" :a (record Nested :b "nested"))))
"""


IMPORTED_STRUCTURAL_RETURN_HELPER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defmodule structural_return/helper)
  (export Task Report build-report)
  (defrecord Task (task_id String))
  (defrecord Report (__literal String) (remaining List[Task]))
  (defproc build-report ((tasks List[Task])) -> Report
    :effects ()
    :lowering inline
    (record Report :__literal "literal" :remaining tasks)))
"""


IMPORTED_STRUCTURAL_RETURN_ENTRY_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defmodule structural_return/entry)
  (import structural_return/helper :only (Task Report build-report))
  (export run)
  (defworkflow run ((tasks List[Task])) -> Report
    (let* ((report (build-report tasks))) report)))
"""


def _projection_contract(
    *,
    group: str,
    discriminant: str,
    role: str,
    active_variants: list[str],
) -> dict[str, object]:
    return {
        "kind": "scalar",
        "type": "string",
        "projection": {
            "projection_class": "union_workflow_boundary",
            "return_kind": "union",
            "union_output_group": group,
            "discriminant_output": discriminant,
            "field_role": role,
            "active_variants": active_variants,
        },
    }


def _two_group_projection_workflow(
    *,
    cross_group_read: bool = False,
    left_allowed: tuple[str, ...] = ("SAME",),
) -> dict[str, object]:
    """Build the runtime representation emitted for two independent union groups.

    Both groups deliberately use SAME/OTHER/THIRD.  ``common_note`` is shared
    by only SAME and OTHER, so its activity proof must remain group-specific.
    """
    fields = {
        "left__variant": "SAME",
        "left__common_note": "left-common",
        "left__third_note": "left-third",
        "right__variant": "OTHER",
        "right__common_note": "right-common",
        "right__third_note": "right-third",
    }
    payload_fields = [
        {"name": name, "type": {"kind": "primitive", "name": "String"}}
        for name in fields
    ]
    payload = {
        "pure_expr_schema_version": 1,
        "result_type": {"kind": "record", "name": "TwoGroups", "fields": payload_fields},
        "bindings": {},
        "expr": {
            "kind": "record",
            "type": {"kind": "record", "name": "TwoGroups", "fields": payload_fields},
            "fields": [
                {
                    "name": name,
                    "value": {
                        "kind": "literal",
                        "type": {"kind": "primitive", "name": "String"},
                        "value": value,
                    },
                }
                for name, value in fields.items()
            ],
        },
    }
    output_contracts = {
        "left__variant": _projection_contract(
            group="left", discriminant="left__variant", role="discriminant",
            active_variants=["SAME", "OTHER", "THIRD"],
        ),
        "left__common_note": _projection_contract(
            group="left", discriminant="left__variant", role="variant",
            active_variants=["SAME", "OTHER"],
        ),
        "left__third_note": _projection_contract(
            group="left", discriminant="left__variant", role="variant",
            active_variants=["THIRD"],
        ),
        "right__variant": _projection_contract(
            group="right", discriminant="right__variant", role="discriminant",
            active_variants=["SAME", "OTHER", "THIRD"],
        ),
        "right__common_note": _projection_contract(
            group="right", discriminant="right__variant", role="variant",
            active_variants=["SAME", "OTHER"],
        ),
        "right__third_note": _projection_contract(
            group="right", discriminant="right__variant", role="variant",
            active_variants=["THIRD"],
        ),
    }
    for discriminant in ("left__variant", "right__variant"):
        output_contracts[discriminant]["type"] = "enum"
        output_contracts[discriminant]["allowed"] = ["SAME", "OTHER", "THIRD"]
    guarded_field = "right__common_note" if cross_group_read else "left__common_note"
    return {
        "version": "2.29",
        "name": "two-independent-union-groups",
        "steps": [
            {
                "name": "Project",
                "id": "project",
                "output_bundle": {
                    "path": "state/two_groups.json",
                    "fields": [
                        {"name": name, "json_pointer": f"/result/{name}", "type": "string"}
                        for name in fields
                    ],
                },
                "pure_projection": {
                    "payload": payload,
                    "binding_refs": {},
                    "payload_digest": pure_expr_payload_digest(payload),
                    "output_contracts": output_contracts,
                },
            },
            {
                "name": "UseLeftSame",
                "id": "use_left_same",
                "requires_variant": {
                    "ref": "root.steps.Project.artifacts.left__variant",
                    "allowed": list(left_allowed),
                },
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "selected_note",
                            "source": {"ref": f"root.steps.Project.artifacts.{guarded_field}"},
                            "contract": {"type": "string"},
                        }
                    ]
                },
            },
            {
                "name": "UseRightSame",
                "id": "use_right_same",
                "requires_variant": {
                    "ref": "root.steps.Project.artifacts.right__variant",
                    "allowed": ["SAME"],
                },
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "right_selected_note",
                            "source": {"ref": "root.steps.Project.artifacts.right__common_note"},
                            "contract": {"type": "string"},
                        }
                    ]
                },
            },
        ],
    }


def _rename_projection_artifact(value: object, *, old: str, new: str) -> object:
    """Rename one emitted artifact identity without changing payload values."""

    if isinstance(value, dict):
        return {
            (new if key == old else key): _rename_projection_artifact(
                nested,
                old=old,
                new=new,
            )
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [
            _rename_projection_artifact(item, old=old, new=new)
            for item in value
        ]
    if value == old:
        return new
    return value


def _load_executor(tmp_path: Path, workflow: dict[str, object]) -> WorkflowExecutor:
    workflow_path = tmp_path / "two_groups.compiler_output.json"
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    loader = WorkflowLoader(tmp_path)
    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping=workflow,
            workflow_path=workflow_path,
            frontend_kind="workflow_lisp",
        ),
        options=loader._validation_options(),
    )
    if result.errors:
        raise WorkflowValidationError(list(result.errors))
    assert result.bundle is not None
    loaded = result.bundle
    state_manager = StateManager(workspace=tmp_path, run_id="two-independent-groups")
    state_manager.initialize(workflow_path.name)
    return WorkflowExecutor(loaded, tmp_path, state_manager, retry_delay_ms=0)


def test_two_independent_union_groups_keep_same_tag_proofs_and_runtime_guards_separate(
    tmp_path: Path,
) -> None:
    executor = _load_executor(tmp_path, _two_group_projection_workflow())
    project = executor.executable_ir.nodes["root.project"].execution_config.pure_projection
    assert project is not None
    projection_groups = {
        contract["projection"]["union_output_group"]
        for contract in project["output_contracts"].values()
    }
    assert projection_groups == {"left", "right"}
    assert project["output_contracts"]["left__common_note"]["projection"]["active_variants"] == (
        "SAME",
        "OTHER",
    )

    state = executor.execute(on_error="continue")

    assert state["steps"]["Project"]["status"] == "completed"
    assert state["steps"]["UseLeftSame"]["artifacts"] == {"selected_note": "left-common"}
    right_guard = state["steps"]["UseRightSame"]
    assert right_guard["status"] == "failed"
    assert right_guard["error"]["type"] == "variant_unavailable"
    assert right_guard["error"]["context"]["selected_variant"] == "OTHER"
    assert right_guard["error"]["context"]["allowed"] == ["SAME"]


def test_two_independent_union_groups_reject_cross_group_proof_even_with_same_tag_name(
    tmp_path: Path,
) -> None:
    with pytest.raises(WorkflowValidationError, match="right__common_note"):
        _load_executor(tmp_path, _two_group_projection_workflow(cross_group_read=True))


def test_partial_shared_field_rejects_a_disjoint_tag_within_its_own_group(
    tmp_path: Path,
) -> None:
    with pytest.raises(WorkflowValidationError, match="left__common_note"):
        _load_executor(
            tmp_path,
            _two_group_projection_workflow(left_allowed=("THIRD",)),
        )


def test_discriminant_artifact_cannot_claim_another_groups_identity(
    tmp_path: Path,
) -> None:
    workflow = _two_group_projection_workflow()
    contracts = workflow["steps"][0]["pure_projection"]["output_contracts"]
    for name, contract in contracts.items():
        if name.startswith("left__"):
            contract["projection"].update(
                union_output_group="right",
                discriminant_output="right__variant",
            )

    with pytest.raises(WorkflowValidationError, match="inconsistent union discriminant metadata"):
        _load_executor(tmp_path, workflow)


def test_runtime_discriminant_contract_lookup_keeps_the_bound_producer_node(
    tmp_path: Path,
) -> None:
    """A projected tag's group comes from its node, never its display name."""

    executor = _load_executor(tmp_path, _two_group_projection_workflow())

    contract = executor._artifact_contract_for_node_id("root.project", "right__variant")

    assert contract is not None
    assert contract["projection"]["union_output_group"] == "right"
    assert contract["projection"]["discriminant_output"] == "right__variant"


def test_runtime_rejects_a_bound_variant_guard_on_a_projected_payload_field(
    tmp_path: Path,
) -> None:
    """A payload spelling a tag cannot impersonate its group's discriminant."""

    executor = _load_executor(tmp_path, _two_group_projection_workflow())

    failure = executor._resolve_selected_variant_guard(
        {
            "ref": NodeResultAddress(
                node_id="root.project",
                field="artifacts",
                member="left__common_note",
            ),
            "allowed": ["SAME"],
        },
        {"steps": {"Project": {"artifacts": {"left__common_note": "SAME"}}}},
    )

    assert failure is not None
    assert failure["error"]["type"] == "unsupported_variant_proof"


def test_runtime_legacy_guard_reads_a_custom_projected_discriminant(
    tmp_path: Path,
) -> None:
    """A 2.29 projected tag need not be named ``variant`` to guard its value."""

    workflow = copy.deepcopy(_two_group_projection_workflow())
    project = workflow["steps"][0]
    output_contracts = project["pure_projection"]["output_contracts"]
    for name in tuple(output_contracts):
        if name.startswith("right__"):
            del output_contracts[name]
    project["output_bundle"]["fields"] = [
        field
        for field in project["output_bundle"]["fields"]
        if not field["name"].startswith("right__")
    ]
    payload = project["pure_projection"]["payload"]
    payload["result_type"]["fields"] = [
        field
        for field in payload["result_type"]["fields"]
        if not field["name"].startswith("right__")
    ]
    payload["expr"]["type"]["fields"] = list(payload["result_type"]["fields"])
    payload["expr"]["fields"] = [
        field
        for field in payload["expr"]["fields"]
        if not field["name"].startswith("right__")
    ]
    workflow["steps"] = workflow["steps"][:2]
    workflow = _rename_projection_artifact(
        workflow,
        old="left__variant",
        new="left_tag",
    )
    workflow["steps"][0]["output_bundle"]["fields"][0]["json_pointer"] = "/result/left_tag"
    workflow["steps"][0]["pure_projection"]["payload_digest"] = pure_expr_payload_digest(
        workflow["steps"][0]["pure_projection"]["payload"]
    )
    use_left = workflow["steps"][1]
    use_left["requires_variant"] = {"step": "Project", "value": "SAME"}

    state = _load_executor(tmp_path, workflow).execute(on_error="stop")

    assert state["steps"]["UseLeftSame"]["status"] == "completed"
    assert state["steps"]["UseLeftSame"]["artifacts"] == {"selected_note": "left-common"}


def test_runtime_legacy_guard_uses_a_materialized_custom_discriminant(
    tmp_path: Path,
) -> None:
    """A conventional payload name cannot replace a declared materialized tag."""

    projection = {
        "projection_class": "union_workflow_boundary",
        "return_kind": "union",
        "union_output_group": "left",
        "discriminant_output": "left_tag",
        "field_role": "discriminant",
        "active_variants": ["A", "B"],
    }
    workflow = {
        "version": "2.29",
        "name": "materialized-custom-tag",
        "steps": [
            {
                "name": "Project",
                "id": "project",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "left_tag",
                            "source": {"literal": "B"},
                            "contract": {
                                "type": "enum",
                                "allowed": ["A", "B"],
                                "projection": projection,
                            },
                        },
                        {
                            "name": "variant",
                            "source": {"literal": "A"},
                            "contract": {"type": "string"},
                        },
                    ]
                },
            },
            {
                "name": "Use",
                "id": "use",
                "requires_variant": {"step": "Project", "value": "A"},
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "value",
                            "source": {"literal": "ok"},
                            "contract": {"type": "string"},
                        }
                    ]
                },
            },
        ],
    }

    state = _load_executor(tmp_path, workflow).execute(on_error="continue")

    assert state["steps"]["Use"]["status"] == "failed"
    assert state["steps"]["Use"]["error"]["context"]["selected_variant"] == "B"


@pytest.mark.parametrize("version", ["2.28", "2.29"])
def test_runtime_legacy_guard_does_not_infer_an_undeclared_tag_on_new_targets(
    tmp_path: Path, version: str,
) -> None:
    """Runtime defense; shared validation already rejects this undeclared proof."""

    workflow = {
        "version": version,
        "name": "ordinary-string-not-discriminant",
        "steps": [{
            "name": "Project",
            "materialize_artifacts": {"values": [{
                "name": "variant",
                "source": {"literal": "A"},
                "contract": {"type": "string"},
            }]},
        }],
    }
    executor = _load_executor(tmp_path, workflow)
    failure = executor._resolve_selected_variant_guard(
        {"step": "Project", "value": "A"},
        {"steps": {"Project": {"artifacts": {"variant": "A"}}}},
    )

    if version == "2.28":
        assert failure is None
    else:
        assert failure is not None
        assert failure["error"]["type"] == "variant_unavailable"
        assert failure["error"]["context"]["selected_variant"] is None


def test_runtime_scoped_guard_uses_the_bound_node_when_display_names_alias(
    tmp_path: Path,
) -> None:
    """A lexical same-name result cannot replace the guard producer's catalog."""

    executor = _load_executor(tmp_path, _two_group_projection_workflow())
    guard = {
        "ref": NodeResultAddress(
            node_id="root.project",
            field="artifacts",
            member="left__variant",
        ),
        "allowed": ["SAME"],
    }
    state = {"steps": {"Project": {"artifacts": {"left__variant": "OTHER"}}}}
    scope = {
        "self_node_results": {
            "root.project": {"artifacts": {"left__variant": "SAME"}},
        },
        "parent_steps": {"Project": {"artifacts": {"left__variant": "OTHER"}}},
    }

    assert executor._resolve_selected_variant_guard(guard, state, scope=scope) is None


def test_exhaustion_materializes_only_the_proven_inactive_list_union_field(
    tmp_path: Path,
) -> None:
    """A sparse inactive branch gets a typed list placeholder, not broad filler."""

    module_path = tmp_path / "two_independent_union_groups.orc"
    module_path.write_text(TWO_GROUP_LOOP_SOURCE, encoding="utf-8")
    bundle = next(
        iter(
            compile_stage3_module(
                module_path,
                validate_shared=True,
                workspace_root=tmp_path,
            ).validated_bundles.values()
        )
    )
    placeholder_steps = [
        step for step in bundle.surface.steps
        if step.name.endswith("__exhausted_placeholders")
    ]

    assert len(placeholder_steps) == 1
    assert placeholder_steps[0].materialize_artifacts == {
        "values": (
            {
                "name": "result__right__summary__work",
                "source": {"literal": ()},
                "contract": {
                    "type": "list",
                    "items": {
                        "type": "record",
                        "record_name": "Task",
                        "fields": ({"name": "task_id", "type": "string"},),
                    },
                    "kind": "collection",
                },
            },
        ),
    }


def test_structural_return_preserves_a_literal_double_underscore_field(
    tmp_path: Path,
) -> None:
    """Structural-return paths preserve user field spelling without name splitting."""

    module_path = tmp_path / "structural_literal_field.orc"
    module_path.write_text(STRUCTURAL_LITERAL_FIELD_SOURCE, encoding="utf-8")
    bundle = next(
        iter(
            compile_stage3_module(
                module_path,
                validate_shared=True,
                workspace_root=tmp_path,
            ).validated_bundles.values()
        )
    )
    public_inputs = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    state_manager = StateManager(workspace=tmp_path, run_id="structural-literal-field")
    state_manager.initialize(
        str(module_path),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(
            public_inputs,
            {"tasks": [{"task_id": "one"}]},
            tmp_path,
        ),
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return____literal": "literal",
        "return__remaining": [{"task_id": "one"}],
    }


def test_structural_return_rejects_a_literal_field_projection_collision(
    tmp_path: Path,
) -> None:
    """A legal field spelling cannot silently collide with a nested path."""

    module_path = tmp_path / "structural_literal_field_collision.orc"
    module_path.write_text(STRUCTURAL_LITERAL_FIELD_COLLISION_SOURCE, encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            module_path,
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "workflow_boundary_projection_collision"


def test_imported_structural_return_preserves_literal_double_underscore_field(
    tmp_path: Path,
) -> None:
    """An imported inline structural return retains the original field path."""

    module_dir = tmp_path / "structural_return"
    module_dir.mkdir()
    (module_dir / "helper.orc").write_text(
        IMPORTED_STRUCTURAL_RETURN_HELPER_SOURCE,
        encoding="utf-8",
    )
    module_path = module_dir / "entry.orc"
    module_path.write_text(IMPORTED_STRUCTURAL_RETURN_ENTRY_SOURCE, encoding="utf-8")
    bundle = next(
        iter(
            compile_stage3_module(
                module_path,
                validate_shared=True,
                workspace_root=tmp_path,
            ).validated_bundles.values()
        )
    )
    public_inputs = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    state_manager = StateManager(workspace=tmp_path, run_id="imported-structural-return")
    state_manager.initialize(
        str(module_path),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(
            public_inputs,
            {"tasks": [{"task_id": "one"}]},
            tmp_path,
        ),
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return____literal": "literal",
        "return__remaining": [{"task_id": "one"}],
    }


@pytest.mark.parametrize(
    ("finish", "expected_outputs"),
    [
        (
            True,
            {
                "return__left__variant": "OTHER",
                "return__left__note": "left-done",
                "return__right__variant": "SAME",
                "return__right__summary__work": [{"task_id": "one"}],
                "return__right__summary__note": "right-done",
            },
        ),
        (
            False,
            {
                "return__left__variant": "SAME",
                "return__left__summary__work": [{"task_id": "one"}],
                "return__left__summary__note": "state",
                "return__right__variant": "OTHER",
                "return__right__note": "right-exhausted",
            },
        ),
    ],
)
def test_stage3_loop_preserves_two_independent_union_groups_at_runtime(
    tmp_path: Path,
    *,
    finish: bool,
    expected_outputs: dict[str, object],
) -> None:
    module_path = tmp_path / "two_independent_union_groups.orc"
    module_path.write_text(TWO_GROUP_LOOP_SOURCE, encoding="utf-8")
    bundle = next(
        iter(
            compile_stage3_module(
                module_path,
                validate_shared=True,
                workspace_root=tmp_path,
            ).validated_bundles.values()
        )
    )
    public_inputs = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    state_manager = StateManager(
        workspace=tmp_path,
        run_id=f"two-independent-union-groups-{finish}",
    )
    state_manager.initialize(
        str(module_path),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(
            public_inputs,
            {"tasks": [{"task_id": "one"}], "finish": finish},
            tmp_path,
        ),
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == expected_outputs


def test_stage3_two_group_union_guards_resolve_after_a_committed_resume(
    tmp_path: Path,
) -> None:
    """A resumed exhaustion branch keeps each nested union group's proof."""

    module_path = tmp_path / "two_independent_union_groups_resume.orc"
    module_path.write_text(
        TWO_GROUP_PROVIDER_LOOP_SOURCE,
        encoding="utf-8",
    )
    prompt_path = tmp_path / "prompts" / "seed.md"
    prompt_path.parent.mkdir()
    prompt_path.write_text("seed\n", encoding="utf-8")
    bundle = next(
        iter(
            compile_stage3_module(
                module_path,
                validate_shared=True,
                workspace_root=tmp_path,
                provider_externs={"providers.seed": "seed"},
                prompt_externs={"prompts.seed": "prompts/seed.md"},
            ).validated_bundles.values()
        )
    )
    public_inputs = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    run_id = "two-independent-union-groups-resume"
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        str(module_path),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(
            public_inputs,
            {"finish": False},
            tmp_path,
        ),
    )

    class _PostCommitInterruption(BaseException):
        pass

    original_hook = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_repeat_until_commit

    def interrupt_first_iteration(self, step, progress):
        original_hook(self, step, progress)
        if progress.get("current_iteration") == 0:
            raise _PostCommitInterruption

    provider_calls: list[str] = []

    def prepare(_self, provider_name, *_args, **kwargs):
        provider_calls.append(provider_name)
        prompt = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            provider_name=provider_name,
            prompt=prompt,
            prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name,
                model=None,
                effort=None,
                timeout_sec=kwargs.get("timeout_sec"),
                input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}),
            input_mode="stdin",
        ), None

    def execute_provider(_self, invocation, **_kwargs):
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = tmp_path / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text('[{"task_id":"one"}]\n', encoding="utf-8")
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False,
            raw_stdout=None, normalized_stdout=None, provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute_provider,
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_repeat_until_commit",
        interrupt_first_iteration,
    ):
        with pytest.raises(_PostCommitInterruption):
            WorkflowExecutor(
                bundle, tmp_path, state_manager, retry_delay_ms=0,
            ).execute(on_error="stop")

    resumed_manager = StateManager(workspace=tmp_path, run_id=run_id)
    resumed_manager.load()
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute_provider,
    ):
        resumed = WorkflowExecutor(
            bundle, tmp_path, resumed_manager, retry_delay_ms=0,
        ).execute(resume=True)

    assert provider_calls == ["seed"]
    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {
        "return__left__variant": "SAME",
        "return__left__summary__work": [{"task_id": "one"}],
        "return__left__summary__note": "state",
        "return__right__variant": "OTHER",
        "return__right__note": "right-exhausted",
    }


def test_stage3_two_group_rich_loop_remains_unavailable_at_228(tmp_path: Path) -> None:
    module_path = tmp_path / "two_independent_union_groups_228.orc"
    module_path.write_text(
        TWO_GROUP_LOOP_SOURCE.replace('(:target-dsl "2.29")', '(:target-dsl "2.28")'),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError, match="loop_recur_state_type_invalid"):
        compile_stage3_module(
            module_path,
            validate_shared=True,
            workspace_root=tmp_path,
        )
