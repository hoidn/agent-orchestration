(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_hidden_command_effect/std_payload_helpers)
  (export CheckResult emit-run-drain-like)
  (defrecord CheckResult
    (status String))
  (defmacro emit-run-drain-like (name)
    (defworkflow name
      ()
      -> CheckResult
      (command-result run_checks
        :argv ("python" "scripts/run_checks.py")
        :returns CheckResult))))
