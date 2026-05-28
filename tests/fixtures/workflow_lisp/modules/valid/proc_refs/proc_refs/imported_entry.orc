(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule proc_refs/imported_entry)
  (import proc_refs/imported_helper :as helper :only (echo-helper))
  (export Output forward entry)
  (defrecord Output
    (value String))
  (defproc forward
    ((runner ProcRef[String -> String])
     (input String))
    -> Output
    :effects ((uses-command run_checks))
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" input)
      :returns Output))
  (defworkflow entry
    ((input String))
    -> Output
    (forward
      (proc-ref helper.echo-helper)
      input)))
