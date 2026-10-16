(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule review_revise_design_docs)
  (export review-revise-design-docs)
  (defrecord DesignDocReviewSubject (target_doc String))
  (defrecord ReviewResult (status String))
  (defprompt review-design-doc
    (:fills (target_doc :text))
    -> ReviewResult
    "Review {target_doc}")
  (defproc review-design-docs
    ((completed DesignDocReviewSubject))
    -> ReviewResult
    :effects ((uses-provider providers.design-docs.review))
    :lowering inline
    (provider-result providers.design-docs.review
      :prompt (review-design-doc :target_doc completed.target_doc)))
  (defproc fix-design-doc
    ((completed DesignDocReviewSubject)) -> DesignDocReviewSubject
    :effects () :lowering inline completed)
  (defmacro review-revise-loop (review fix value) value)
  (defworkflow build-review-runtime-owned ((value ReviewResult)) -> ReviewResult
    value)
  (defworkflow review-revise-design-docs
    ((completed DesignDocReviewSubject)) -> ReviewResult
    (let* ((reviewed (review-design-docs completed))
           (expanded (review-revise-loop
                       (proc-ref review-design-docs)
                       (proc-ref fix-design-doc)
                       reviewed)))
      (call build-review-runtime-owned :value expanded))))
