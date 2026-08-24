(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule infer-output-contract)
  (export infer-output-contract)
  (defrecord OutputContractField
    (name String)
    (type String))
  (defrecord OutputContractDraft
    (fields List[OutputContractField]))
  (defworkflow infer-output-contract () -> OutputContractDraft
    (provider-result providers.inference
      :prompt prompts.inference
      :inputs ()
      :returns OutputContractDraft)))
