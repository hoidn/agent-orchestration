(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule control/direct_task)
  (export direct-task)

  (defprompt direct-task-prompt
    (:fills
      (task :text))
    -> Bool
    "{task}")

  (defworkflow direct-task
    ((task String)
     (model String)
     (effort String))
    -> Bool
    (provider-result providers.direct
      :prompt (direct-task-prompt :task task)
      :model model
      :effort effort
      :delivery :composed))
)
