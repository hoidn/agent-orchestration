(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum Queue
    active
    in_progress)
  (defpath BacklogInProgressPath
    :kind relpath
    :under "docs/backlog/in_progress"
    :must-exist true)
  (defrecord ResourceTransitionResult
    (resource-id String)
    (from Queue)
    (to Queue)
    (new-path BacklogInProgressPath)
    (transition-id String))
  (defworkflow move-selected-item
    ((resource_id String)
     (destination BacklogInProgressPath))
    -> ResourceTransitionResult
    (command-result apply_resource_transition
      :adapter apply_resource_transition
      :inputs
        ((resource_id resource_id)
         (from Queue.active)
         (to Queue.in_progress)
         (new_path destination)
         (transition_id "transition-1"))
      :returns ResourceTransitionResult)))
