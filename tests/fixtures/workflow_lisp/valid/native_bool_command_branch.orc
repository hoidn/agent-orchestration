(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule native_bool_command_branch)
  (export gate)
  (defworkflow gate
    ()
    -> Bool
    (let* ((ready
             (command-result probe_ready
               :argv ("python" "scripts/probe_ready.py")
               :returns Bool)))
      (if ready
          (command-result record_ready
            :argv ("python" "scripts/record_ready.py")
            :returns Bool)
          (command-result record_blocked
            :argv ("python" "scripts/record_blocked.py")
            :returns Bool)))))
