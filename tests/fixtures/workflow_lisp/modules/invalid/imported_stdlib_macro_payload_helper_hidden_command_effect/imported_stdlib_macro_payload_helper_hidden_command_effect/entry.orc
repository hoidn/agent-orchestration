(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_hidden_command_effect/entry)
  (import imported_stdlib_macro_payload_helper_hidden_command_effect/std_payload_helpers
    :only (CheckResult emit-run-drain-like))
  (export run-drain-like)
  (emit-run-drain-like run-drain-like))
