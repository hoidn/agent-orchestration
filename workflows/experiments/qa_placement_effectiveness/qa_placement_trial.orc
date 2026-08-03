(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule qa_placement_effectiveness/qa_placement_trial)
  (import qa_placement_effectiveness/qa_placement_arms
    :as arms
    :only (direct design-qa product-qa rich))
  (export compare)

  (defworkflow direct-treatment
    ((task String)
     (check_contract String)
     (model String)
     (effort String))
    -> Bool
    (call arms.direct
      :task task
      :check_contract check_contract
      :model model
      :effort effort))

  (defworkflow design-qa-treatment
    ((task String)
     (check_contract String)
     (model String)
     (effort String))
    -> Bool
    (call arms.design-qa
      :task task
      :check_contract check_contract
      :model model
      :effort effort))

  (defworkflow product-qa-treatment
    ((task String)
     (check_contract String)
     (model String)
     (effort String))
    -> Bool
    (call arms.product-qa
      :task task
      :check_contract check_contract
      :model model
      :effort effort))

  (defworkflow rich-treatment
    ((task String)
     (check_contract String)
     (model String)
     (effort String))
    -> Bool
    (call arms.rich
      :task task
      :check_contract check_contract
      :model model
      :effort effort))

  (defworkflow compare
    ((task String)
     (check_contract String)
     (model String)
     (effort String))
    -> Value
    (trial
      :arms
      ((:id "DIRECT"
        :run-ref
        (run-ref
          :source
          (:repo "file:///home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/93e0eb08e092fed177316517328b7effc2893399"
           :commit "93e0eb08e092fed177316517328b7effc2893399")
          :program (:bundle direct-treatment)
          :inputs
          (:task task
           :check_contract check_contract
           :model model
           :effort effort)
          :policy (:setup ())))
       (:id "DESIGN_QA"
        :run-ref
        (run-ref
          :source
          (:repo "file:///home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/93e0eb08e092fed177316517328b7effc2893399"
           :commit "93e0eb08e092fed177316517328b7effc2893399")
          :program (:bundle design-qa-treatment)
          :inputs
          (:task task
           :check_contract check_contract
           :model model
           :effort effort)
          :policy (:setup ())))
       (:id "PRODUCT_QA"
        :run-ref
        (run-ref
          :source
          (:repo "file:///home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/93e0eb08e092fed177316517328b7effc2893399"
           :commit "93e0eb08e092fed177316517328b7effc2893399")
          :program (:bundle product-qa-treatment)
          :inputs
          (:task task
           :check_contract check_contract
           :model model
           :effort effort)
          :policy (:setup ())))
       (:id "RICH"
        :run-ref
        (run-ref
          :source
          (:repo "file:///home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/93e0eb08e092fed177316517328b7effc2893399"
           :commit "93e0eb08e092fed177316517328b7effc2893399")
          :program (:bundle rich-treatment)
          :inputs
          (:task task
           :check_contract check_contract
           :model model
           :effort effort)
          :policy (:setup ()))))
      :reps 1
      :max-concurrency 4
      :evaluation
      (record
        :checks
        (list
          (record
            :id "visible-f1-contract"
            :command
            (list
              "env"
              "PYTHONPATH="
              "PYTHONDONTWRITEBYTECODE=1"
              "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"
              "/home/ollie/miniconda3/envs/ptycho311/bin/python3.11"
              "-m" "pytest" "-q" "-p" "no:cacheprovider"
              "tests/torch/test_generator_registry.py"
              "tests/torch/test_construction_consolidation.py"
              "tests/torch/test_generator_adapter.py"
              "tests/torch/test_config_bridge.py"
              "tests/torch/test_model_spec.py"
              "tests/torch/test_model_spec_v2.py"
              "tests/torch/test_lightning_checkpoint.py"
              "tests/torch/test_artifact_schema.py"
              "tests/torch/test_artifact_schema_v2.py"
              "tests/torch/test_workflows_components.py"
              "tests/torch/test_es_f1_extension_boundary.py")
            :authority "correctness"
            :required true
            :timeout-ms 1200000))
        :judgment
        (record
          :provider "scorer"
          :rubric-asset
          "prompts/trial_rubric.md"
          :evidence-confidentiality "same_trust_boundary"
          :evidence-limits
          (record :max-item-bytes 65536 :max-packet-bytes 262144))
        :observation
        (record
          :include
          (list "task_spec" "validated_result" "workspace_delta"
                "check_results" "declared_artifacts" "failure_evidence")
          :diff-cap-bytes 262144
          :reveal-provider-identity false)
        :aggregation
        (record
          :mode "independent_rubric"
          :rep-combine "median"
          :tie "authored_order")
        :success-rule
        (record
          :superior
          (record :min-abs-improvement 0.10 :max-cost-ratio 4.0)
          :non-inferior
          (record :min-cost-reduction 0.20)
          :count-failures-as-outcomes true))
      :budget
      (record
        :arm-timeout-ms 43200000
        :trial-timeout-ms 43200000
        :max-evaluator-attempts 4
        :max-evaluator-concurrency 4)))
)
