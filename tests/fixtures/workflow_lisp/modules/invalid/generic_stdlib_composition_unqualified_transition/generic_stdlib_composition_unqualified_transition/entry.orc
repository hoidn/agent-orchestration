(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule generic_stdlib_composition_unqualified_transition/entry)
  (import generic_stdlib_composition_unqualified_transition/helper :only (OutcomeRequest OutcomeResult SummaryPath SummaryValue emit-run-outcome))
  (export run-outcome)
  (emit-run-outcome run-outcome))
