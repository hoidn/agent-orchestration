(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.22")
  (defmodule judgment_views/prompt_binding_map_child)
  (export orchestrate)

  (defprompt render-item
    (:fills
      (item :value Int))
    -> Int
    "Return the declared result for {item}.")

  (defworkflow child
    ((item Int))
    -> Int
    (provider-result providers.worker
      :prompt (render-item :item item)))

  (defworkflow orchestrate
    ((items List[Int]))
    -> List[Int]
    (list/map-effect ((item items)) :max 3
      (call child :item item))))
