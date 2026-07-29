(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule judgment_views/path_join_map_child_argument)
  (export orchestrate)

  (defpath ChildPath
    :kind relpath
    :under "artifacts/children"
    :must-exist false)

  (defworkflow child
    ((target ChildPath))
    -> Int
    (provider-result providers.worker
      :prompt prompts.worker
      :inputs ()
      :delivery :composed
      :returns Int))

  (defworkflow orchestrate
    ((child_names List[String]))
    -> List[Int]
    (list/map-effect ((child_name child_names)) :max 3
      (call child
        :target (path/join-under ChildPath child_name)))))
