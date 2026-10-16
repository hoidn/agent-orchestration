"""Public run/resume coverage for target-2.28 union prompt inputs."""

from __future__ import annotations





_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule union_prompt_e2e)
  (export run)
  (defrecord Details (message String))
  (defunion Decision
    (SCALAR (value Int))
    (PAYLOAD (value Details))
    (EMPTY))
  (defprompt consume-decision
    (:fills (decision :value Decision))
    -> Bool
    "{decision}")
  (defworkflow run () -> Bool
    (let* ((decision
             (provider-result providers.produce
               :prompt prompts.produce
               :inputs ()
               :returns Decision))
           (consumed
             (provider-result providers.consume
               :prompt (consume-decision :decision decision)
               :delivery :composed))
           (finished
             (provider-result providers.finish
               :prompt prompts.finish
               :inputs (decision)
               :returns Bool)))
      finished)))
"""

_ACTIVE_DECISIONS = (
    {"variant": "SCALAR", "value": 7},
    {"variant": "PAYLOAD", "value": {"message": "active"}},
    {"variant": "EMPTY"},
)

_IMPORTED_HELPER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule union_prompt_e2e/helper)
  (export Decision make-decision)
  (defrecord Details (message String))
  (defunion Decision
    (SCALAR (value Int))
    (PAYLOAD (value Details))
    (EMPTY))
  (defproc private-produce () -> Decision
    :effects ((uses-provider providers.produce))
    :lowering private-workflow
    (provider-result providers.produce
      :prompt prompts.produce
      :inputs ()
      :returns Decision))
  (defworkflow make-decision () -> Decision
    (private-produce)))
"""

_IMPORTED_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule union_prompt_e2e/consumer)
  (import union_prompt_e2e/helper :only (Decision make-decision))
  (export run)
  (defprompt consume-decision
    (:fills (decision :value Decision))
    -> Bool
    "{decision}")
  (defworkflow run () -> Bool
    (let* ((decision (call make-decision))
           (consumed
             (provider-result providers.consume
               :prompt (consume-decision :decision decision)
               :delivery :composed))
           (finished
             (provider-result providers.finish
               :prompt prompts.finish
               :inputs (decision)
               :returns Bool)))
      finished)))
"""
