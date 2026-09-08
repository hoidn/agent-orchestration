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
          (:repo "file:///home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/73866149edbda624aef9fd09e299cf07ecb02c1b"
           :commit "73866149edbda624aef9fd09e299cf07ecb02c1b")
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
          (:repo "file:///home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/73866149edbda624aef9fd09e299cf07ecb02c1b"
           :commit "73866149edbda624aef9fd09e299cf07ecb02c1b")
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
          (:repo "file:///home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/73866149edbda624aef9fd09e299cf07ecb02c1b"
           :commit "73866149edbda624aef9fd09e299cf07ecb02c1b")
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
          (:repo "file:///home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/73866149edbda624aef9fd09e299cf07ecb02c1b"
           :commit "73866149edbda624aef9fd09e299cf07ecb02c1b")
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
              "tests/test_simulation_config.py"
              "tests/torch/test_config_bridge.py"
              "tests/torch/test_structural_config_ownership.py"
              "tests/scripts/test_training_backend_selector.py"
              "tests/scripts/test_inference_backend_selector.py"
              "tests/scripts/test_simulation_config_cli.py"
              "tests/torch/test_cli_shared.py"
              "tests/test_workflow_components.py"
              "tests/test_grid_lines_workflow.py"
              "tests/torch/test_workflows_components.py"
              "tests/torch/test_train_lightning_execution_contract.py"
              "tests/torch/test_cli_train_torch.py"
              "tests/studies/test_grid_study_dataset_builder.py"
              "tests/studies/test_tf_reference_cnn_runner.py"
              "tests/studies/test_openfwi_flatvel_a_run_config.py"
              "--deselect"
              "tests/torch/test_workflows_components.py::TestWorkflowsComponentsScaffold::test_run_cdi_example_calls_update_legacy_dict"
              "tests/test_es_f1_config_ownership.py")
            :authority "correctness"
            :required true
            :timeout-ms 14400000))
        :judgment
        (record
          :provider "scorer"
          :rubric-asset
          "prompts/trial_rubric.md"
          :evidence-confidentiality "same_trust_boundary"
          :evidence-limits
          (record :max-item-bytes 4194304 :max-packet-bytes 8388608))
        :observation
        (record
          :include
          (list "task_spec" "validated_result" "workspace_delta"
                "check_results" "declared_artifacts" "failure_evidence")
          :diff-cap-bytes 2097152
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
        :arm-timeout-ms 172800000
        :trial-timeout-ms 216000000
        :max-evaluator-attempts 4
        :max-evaluator-concurrency 4)))
)
