(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.17")
  (defmodule provider_peer_group_three)
  (export orchestrate)
  (defrecord TeamResult
    (plan String)
    (approved Bool)
    (notes String))
  (defworkflow orchestrate () -> TeamResult
    (with-live-provider-peers
      ((planner
         (provider-result providers.planner
           :prompt prompts.planner
           :inputs ()
           :timeout-sec 10
           :returns String))
       (reviewer
         (provider-result providers.reviewer
           :prompt prompts.reviewer
           :inputs ()
           :timeout-sec 10
           :returns Bool))
       (builder
         (provider-result providers.builder
           :prompt prompts.builder
           :inputs ()
           :timeout-sec 10
           :returns String)))
      (record TeamResult
        :plan planner
        :approved reviewer
        :notes builder))))
