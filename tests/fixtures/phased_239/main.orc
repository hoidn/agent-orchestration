(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule main) (export run)
  (defpath Report :kind relpath :under "outputs" :must-exist false)
  (defrecord Review (approved Bool))
  (defprompt review (:fills (subject :text) (report :path :out Report))
    -> Review "Review {subject}; write {report}.")
  (defworkflow run ((subject String) (report Report)) -> Int
    (let* ((review (provider-result providers.review
                    :prompt (review :subject subject :report report)
                    :delivery :phased :materialization-attempts 2 :timeout-sec 60
                    :model "bound-model" :effort "low"))
           (after (command-result after
                    :argv ("python" "tests/fixtures/phased_239/after.py" review.approved)
                    :returns Int)))
      after)))
