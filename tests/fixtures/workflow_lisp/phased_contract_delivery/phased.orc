(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule phased_contract_delivery)
  (export phased-review)

  (defrecord PhasedReviewResult
    (approved Bool))

  (defprompt phased-review-prompt
    (:fills
      (subject :text))
    -> PhasedReviewResult
    "Review {subject}")

  (defworkflow phased-review
    ((subject String))
    -> PhasedReviewResult
    (provider-result providers.review
      :prompt (phased-review-prompt :subject subject)
      :delivery :phased))
)
