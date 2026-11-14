(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (let* ((one (provider-result providers.review :prompt prompts.one :inputs (message)
                  :model "m" :effort "low" :returns Result))
           (two (provider-result providers.review :prompt prompts.two :inputs (message)
                  :model "m" :effort "low" :returns Result)))
      two)))
