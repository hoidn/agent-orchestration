(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule neurips/entry)
  (import neurips/macros :only (WorkReport ChecksResult emit-command-workflow))
  (export generated)
  (emit-command-workflow generated))
