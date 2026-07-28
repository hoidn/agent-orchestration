(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule composed_contract_delivery)
  (export composed-review)

  (defrecord ComposedReviewResult
    (approved Bool))

  (defprompt composed-review-prompt
    (:fills
      (subject :text))
    -> ComposedReviewResult
    "Review {subject}")

  (defworkflow composed-review
    ((subject String))
    -> ComposedReviewResult
    (provider-result providers.review
      :prompt (composed-review-prompt :subject subject)
      :delivery :composed))
)
