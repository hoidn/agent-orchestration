"""Compiled target-2.28 union prompt-input carriage coverage."""

from __future__ import annotations





_HELPER_SOURCE = """\
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.28\")
  (defmodule union_carriage/helper)
  (export Request Decision make-decision)
  (defrecord Nested (value Int))
  (defrecord Request (seed String))
  (defunion Decision
    (SCALAR (value Int))
    (RECORD (value Nested))
    (EMPTY))
  (defproc private-produce ((request Request)) -> Decision
    :effects ((uses-provider providers.produce))
    :lowering private-workflow
    (provider-result providers.produce
      :prompt prompts.produce
      :inputs (request)
      :returns Decision))
  (defworkflow make-decision ((request Request)) -> Decision
    (private-produce request)))
"""

_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.28\")
  (defmodule union_carriage/consumer)
  (import union_carriage/helper :only (Request Decision make-decision))
  (export consume)
  (defworkflow consume ((request Request)) -> Bool
    (let* ((decision (call make-decision :request request)))
      (provider-result providers.consume
        :prompt prompts.consume
        :inputs (decision)
        :returns Bool))))
"""

_OLD_TARGET_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.27\")
  (defmodule union_carriage/consumer)
  (import union_carriage/helper :only (Request Decision make-decision))
  (export consume)
  (defworkflow consume ((request Request)) -> Bool
    (let* ((decision (call make-decision :request request)))
      (match decision
        ((SCALAR scalar) true)
        ((RECORD record) true)
        ((EMPTY empty) true)))))
"""

_LIST_SOURCE = """\
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.28\")
  (defmodule union_carriage/list_consumer)
  (export consume-list)
  (defunion Decision
    (PAYLOAD (payload String))
    (EMPTY))
  (defworkflow consume-list () -> Bool
    (let* ((decisions
             (provider-result providers.produce
               :prompt prompts.produce
               :inputs ()
               :returns List[Decision])))
      (provider-result providers.consume
        :prompt prompts.consume
        :inputs (decisions)
        :returns Bool))))
"""
