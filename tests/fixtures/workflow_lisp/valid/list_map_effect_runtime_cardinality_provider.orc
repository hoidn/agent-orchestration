(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule list_map_effect_runtime_cardinality_provider)
  (export orchestrate)
  (defpath ReviewReport
    :kind relpath
    :under "artifacts/reviews"
    :must-exist true)
  (defpath SynthesisReport
    :kind relpath
    :under "artifacts/synthesis"
    :must-exist true)
  (defrecord PanelResult
    (reports List[ReviewReport])
    (synthesis SynthesisReport))
  (defworkflow orchestrate
    ((lens_ids List[Int]))
    -> PanelResult
    (let* ((reports
             (list/map-effect ((lens_id lens_ids)) :max 4
               (provider-result providers.review
                 :prompt prompts.review
                 :inputs (lens_id)
                 :returns ReviewReport)))
           (synthesis
             (provider-result providers.synthesize
               :prompt prompts.synthesize
               :inputs (reports)
               :returns SynthesisReport)))
      (record PanelResult
        :reports reports
        :synthesis synthesis))))
