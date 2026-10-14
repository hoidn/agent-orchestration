(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Review (ok Bool))
  (defworkflow run ((message String)) -> Review
    (let* ((first (provider-result providers.review :prompt prompts.base
                    :inputs (message) :model "chosen-model" :effort "low" :returns Review))
           (second (provider-result providers.review :prompt prompts.base
                    :inputs (message first) :model "chosen-model" :effort "low" :returns Review)))
      second)))
