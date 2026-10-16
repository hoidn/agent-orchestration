"""Current scoped union-proof regressions for pure-projection output groups."""

from __future__ import annotations

from pathlib import Path

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.expressions import LoopRecurExpr, RecordExpr, UnionVariantExpr


TWO_GROUP_LOOP_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
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
  (:target-dsl "2.35")
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
  (:target-dsl "2.35")
  (defrecord Task (task_id String))
  (defrecord Report (__literal String) (remaining List[Task]))
  (defworkflow structural-literal-field ((tasks List[Task])) -> Report
    (record Report :__literal "literal" :remaining tasks)))
"""


STRUCTURAL_LITERAL_FIELD_COLLISION_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defrecord Nested (b String))
  (defrecord Collision (a__b String) (a Nested))
  (defworkflow structural-literal-field-collision () -> Collision
    (record Collision :a__b "flat" :a (record Nested :b "nested"))))
"""


IMPORTED_STRUCTURAL_RETURN_HELPER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
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
  (:target-dsl "2.35")
  (defmodule structural_return/entry)
  (import structural_return/helper :only (Task Report build-report))
  (export run)
  (defworkflow run ((tasks List[Task])) -> Report
    (let* ((report (build-report tasks))) report)))
"""










































def test_stage3_two_group_rich_loop_keeps_independent_union_values(tmp_path: Path) -> None:
    module_path = tmp_path / "two_independent_union_groups.orc"
    module_path.write_text(TWO_GROUP_LOOP_SOURCE, encoding="utf-8")
    result = compile_stage3_module(
        module_path,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    [workflow] = result.typed_workflows
    assert {name: value.name for name, value in workflow.signature.return_type_ref.field_types.items()} == {
        "left": "Left",
        "right": "Right",
    }
    body = workflow.typed_body.expr
    assert isinstance(body, LoopRecurExpr)
    assert isinstance(body.on_exhausted_result_expr, RecordExpr)
    values = dict(body.on_exhausted_result_expr.fields)
    assert all(isinstance(value, UnionVariantExpr) for value in values.values())
    assert (values["left"].type_name, values["left"].variant_name) == ("Left", "SAME")
    assert (values["right"].type_name, values["right"].variant_name) == ("Right", "OTHER")
