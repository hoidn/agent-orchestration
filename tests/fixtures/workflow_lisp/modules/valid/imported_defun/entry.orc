(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry)
  (import neurips/types :only (ChecksResult))
  (import neurips/helpers :as helpers :only (summarize))
  (export orchestrate)
  (defworkflow orchestrate
    ((input ChecksResult))
    -> ChecksResult
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" (helpers.summarize input))
      :returns ChecksResult)))
