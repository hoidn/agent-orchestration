(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/prompt_dependency)
  (export run)
  (defrecord Box (n Int))
  (defpath Notes :kind relpath :under "artifacts/work" :must-exist true)
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defworkflow run ((notes Notes)) -> Box
    (let* ((first (provider-result providers.review
                    :prompt prompts.review
                    :inputs ()
                    :prompt-dependencies (:required (notes) :position append)
                    :returns Box))
           (second (fetch first.n)))
      second)))
