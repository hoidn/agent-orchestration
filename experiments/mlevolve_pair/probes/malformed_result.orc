(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule malformed_result)
  (export run)
  (defrecord Trial (ordinal Int))
  (defworkflow run () -> Trial
    (command-result emit
      :argv ("python" "experiments/mlevolve_pair/probes/missing_bundle.py"
             "0" "malformed")
      :returns Trial)))
