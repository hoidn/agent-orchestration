(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defprompt ask (:fills (q :text)) -> Result "Answer {q}.")
  (defworkflow run ((message String)) -> Result
    (let* ((one (provider-result providers.review :model "m" :effort "low" :timeout-sec 60 :prompt (ask :q message)))
           (two (provider-result providers.review :model "m" :effort "low" :timeout-sec 60 :prompt (ask :q "two"))))
      two)))
