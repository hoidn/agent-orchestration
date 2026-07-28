(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule phased_contract_delivery_public_e2e)
  (export phased-review)

  (defpath ReviewReportPath
    :kind relpath
    :under "."
    :must-exist false)

  (defrecord PhasedReviewResult
    (approved Bool))

  (defprompt phased-review-prompt
    (:fills
      (subject :text)
      (report :path :out ReviewReportPath))
    -> PhasedReviewResult
    "Review {subject} and materialize {report}")

  (defworkflow phased-review
    ((subject String)
     (report ReviewReportPath)
     (model String)
     (effort String))
    -> PhasedReviewResult
    (let* ((review
             (provider-result providers.review
               :prompt
                 (phased-review-prompt
                   :subject subject
                   :report report)
               :model model
               :effort effort
               :delivery :phased
               :materialization-attempts 2)))
      (record PhasedReviewResult
        :approved review.approved)))
)
