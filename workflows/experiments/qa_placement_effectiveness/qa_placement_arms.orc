(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule qa_placement_effectiveness/qa_placement_arms)
  (import control/direct_task
    :as control
    :only (direct-task))
  (export direct design-qa product-qa rich)

  (defpath DesignTarget
    :kind relpath
    :under "artifacts/work/qa-placement"
    :must-exist false)

  (defpath ReviewTarget
    :kind relpath
    :under "artifacts/review/qa-placement"
    :must-exist false)

  (defenum ReviewDecision
    APPROVE
    REVISE
    BLOCKED)

  (defrecord ReviewResult
    (decision ReviewDecision))

  (defprompt design-prompt
    (:fills
      (task :text)
      (check_contract :text)
      (design_target :path :out DesignTarget))
    -> Bool
    "Develop the smallest load-bearing design for the repository task.\n\nTask:\n{task}\n\nRequired checks:\n{check_contract}\n\n{design_target}\n")

  (defprompt design-review-prompt
    (:fills
      (task :text)
      (check_contract :text)
      (design :path DesignTarget)
      (review_target :path :out ReviewTarget))
    -> ReviewResult
    "Independently review the design against the task and required checks. Decide APPROVE, REVISE, or BLOCKED.\n\nTask:\n{task}\n\nRequired checks:\n{check_contract}\n\nDesign path:\n{design}\n\n{review_target}\n")

  (defprompt design-revision-prompt
    (:fills
      (task :text)
      (check_contract :text)
      (design :path DesignTarget)
      (review :path ReviewTarget)
      (revision_target :path :out DesignTarget))
    -> Bool
    "Revise the design once, limited to the independent review findings.\n\nTask:\n{task}\n\nRequired checks:\n{check_contract}\n\nDesign path:\n{design}\n\nReview path:\n{review}\n\n{revision_target}\n")

  (defprompt implementation-prompt
    (:fills
      (task :text)
      (check_contract :text)
      (design :path DesignTarget))
    -> Bool
    "Implement the repository task using the reviewed design and satisfy the required checks.\n\nTask:\n{task}\n\nRequired checks:\n{check_contract}\n\nDesign path:\n{design}\n")

  (defprompt product-review-prompt
    (:fills
      (task :text)
      (check_contract :text)
      (review_target :path :out ReviewTarget))
    -> ReviewResult
    "Independently inspect the current workspace implementation against the task and required checks. Decide APPROVE, REVISE, or BLOCKED.\n\nTask:\n{task}\n\nRequired checks:\n{check_contract}\n\n{review_target}\n")

  (defprompt product-fix-prompt
    (:fills
      (task :text)
      (check_contract :text)
      (review :path ReviewTarget))
    -> Bool
    "Inspect the current workspace and apply at most one correction, limited to the independent product-review findings.\n\nTask:\n{task}\n\nRequired checks:\n{check_contract}\n\nReview path:\n{review}\n")

  (defworkflow produce-design
    ((task String)
     (check_contract String)
     (design_target DesignTarget)
     (model String)
     (effort String))
    -> Bool
    (provider-result providers.design
      :prompt
        (design-prompt
          :task task
          :check_contract check_contract
          :design_target design_target)
      :delivery :composed
      :model model
      :effort effort))

  (defworkflow review-design
    ((task String)
     (check_contract String)
     (design DesignTarget)
     (review_target ReviewTarget)
     (model String)
     (effort String))
    -> ReviewResult
    (provider-result providers.design-review
      :prompt
        (design-review-prompt
          :task task
          :check_contract check_contract
          :design design
          :review_target review_target)
      :delivery :composed
      :model model
      :effort effort))

  (defworkflow revise-design
    ((task String)
     (check_contract String)
     (design DesignTarget)
     (review ReviewTarget)
     (revision_target DesignTarget)
     (model String)
     (effort String))
    -> Bool
    (provider-result providers.design-revision
      :prompt
        (design-revision-prompt
          :task task
          :check_contract check_contract
          :design design
          :review review
          :revision_target revision_target)
      :delivery :composed
      :model model
      :effort effort))

  (defworkflow implement-with-design
    ((task String)
     (check_contract String)
     (design DesignTarget)
     (model String)
     (effort String))
    -> Bool
    (provider-result providers.implementation
      :prompt
        (implementation-prompt
          :task task
          :check_contract check_contract
          :design design)
      :delivery :composed
      :model model
      :effort effort))

  (defworkflow review-product
    ((task String)
     (check_contract String)
     (review_target ReviewTarget)
     (model String)
     (effort String))
    -> ReviewResult
    (provider-result providers.product-review
      :prompt
        (product-review-prompt
          :task task
          :check_contract check_contract
          :review_target review_target)
      :delivery :composed
      :model model
      :effort effort))

  (defworkflow fix-product
    ((task String)
     (check_contract String)
     (review ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (provider-result providers.product-fix
      :prompt
        (product-fix-prompt
          :task task
          :check_contract check_contract
          :review review)
      :delivery :composed
      :model model
      :effort effort))

  (defworkflow finish-product-fix
    ((task String)
     (check_contract String)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (call fix-product
      :task task
      :check_contract check_contract
      :review product_review_target
      :model model
      :effort effort))

  (defworkflow finish-nonapproved-product-review
    ((review ReviewResult)
     (task String)
     (check_contract String)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((is_revise
             (= review.decision ReviewDecision.REVISE)))
      (if is_revise
        (call finish-product-fix
          :task task
          :check_contract check_contract
          :product_review_target product_review_target
          :model model
          :effort effort)
        false)))

  (defworkflow finish-product-review
    ((review ReviewResult)
     (task String)
     (check_contract String)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((is_approve
             (= review.decision ReviewDecision.APPROVE)))
      (if is_approve
        true
        (call finish-nonapproved-product-review
          :review review
          :task task
          :check_contract check_contract
          :product_review_target product_review_target
          :model model
          :effort effort))))

  (defworkflow run-product-qa
    ((task String)
     (check_contract String)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((review
             (call review-product
               :task task
               :check_contract check_contract
               :review_target product_review_target
               :model model
               :effort effort)))
      (call finish-product-review
        :review review
        :task task
        :check_contract check_contract
        :product_review_target product_review_target
        :model model
        :effort effort)))

  (defworkflow implement-reviewed-design
    ((task String)
     (check_contract String)
     (design DesignTarget)
     (model String)
     (effort String))
    -> Bool
    (call implement-with-design
      :task task
      :check_contract check_contract
      :design design
      :model model
      :effort effort))

  (defworkflow revise-and-implement-design
    ((task String)
     (check_contract String)
     (design_target DesignTarget)
     (design_review_target ReviewTarget)
     (revision_target DesignTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((revised
             (call revise-design
               :task task
               :check_contract check_contract
               :design design_target
               :review design_review_target
               :revision_target revision_target
               :model model
               :effort effort)))
      (if revised
        (call implement-reviewed-design
          :task task
          :check_contract check_contract
          :design revision_target
          :model model
          :effort effort)
        false)))

  (defworkflow finish-nonapproved-design-review
    ((review ReviewResult)
     (task String)
     (check_contract String)
     (design_target DesignTarget)
     (design_review_target ReviewTarget)
     (revision_target DesignTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((is_revise
             (= review.decision ReviewDecision.REVISE)))
      (if is_revise
        (call revise-and-implement-design
          :task task
          :check_contract check_contract
          :design_target design_target
          :design_review_target design_review_target
          :revision_target revision_target
          :model model
          :effort effort)
        false)))

  (defworkflow finish-design-review
    ((review ReviewResult)
     (task String)
     (check_contract String)
     (design_target DesignTarget)
     (design_review_target ReviewTarget)
     (revision_target DesignTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((is_approve
             (= review.decision ReviewDecision.APPROVE)))
      (if is_approve
        (call implement-reviewed-design
          :task task
          :check_contract check_contract
          :design design_target
          :model model
          :effort effort)
        (call finish-nonapproved-design-review
          :review review
          :task task
          :check_contract check_contract
          :design_target design_target
          :design_review_target design_review_target
          :revision_target revision_target
          :model model
          :effort effort))))

  (defworkflow continue-design-qa
    ((task String)
     (check_contract String)
     (design_target DesignTarget)
     (design_review_target ReviewTarget)
     (revision_target DesignTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((review
             (call review-design
               :task task
               :check_contract check_contract
               :design design_target
               :review_target design_review_target
               :model model
               :effort effort)))
      (call finish-design-review
        :review review
        :task task
        :check_contract check_contract
        :design_target design_target
        :design_review_target design_review_target
        :revision_target revision_target
        :model model
        :effort effort)))

  (defworkflow implement-reviewed-design-and-product-qa
    ((task String)
     (check_contract String)
     (design DesignTarget)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((implemented
             (call implement-with-design
               :task task
               :check_contract check_contract
               :design design
               :model model
               :effort effort)))
      (if implemented
        (call run-product-qa
          :task task
          :check_contract check_contract
          :product_review_target product_review_target
          :model model
          :effort effort)
        false)))

  (defworkflow revise-implement-and-product-qa
    ((task String)
     (check_contract String)
     (design_target DesignTarget)
     (design_review_target ReviewTarget)
     (revision_target DesignTarget)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((revised
             (call revise-design
               :task task
               :check_contract check_contract
               :design design_target
               :review design_review_target
               :revision_target revision_target
               :model model
               :effort effort)))
      (if revised
        (call implement-reviewed-design-and-product-qa
          :task task
          :check_contract check_contract
          :design revision_target
          :product_review_target product_review_target
          :model model
          :effort effort)
        false)))

  (defworkflow finish-nonapproved-rich-design-review
    ((review ReviewResult)
     (task String)
     (check_contract String)
     (design_target DesignTarget)
     (design_review_target ReviewTarget)
     (revision_target DesignTarget)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((is_revise
             (= review.decision ReviewDecision.REVISE)))
      (if is_revise
        (call revise-implement-and-product-qa
          :task task
          :check_contract check_contract
          :design_target design_target
          :design_review_target design_review_target
          :revision_target revision_target
          :product_review_target product_review_target
          :model model
          :effort effort)
        false)))

  (defworkflow finish-rich-design-review
    ((review ReviewResult)
     (task String)
     (check_contract String)
     (design_target DesignTarget)
     (design_review_target ReviewTarget)
     (revision_target DesignTarget)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((is_approve
             (= review.decision ReviewDecision.APPROVE)))
      (if is_approve
        (call implement-reviewed-design-and-product-qa
          :task task
          :check_contract check_contract
          :design design_target
          :product_review_target product_review_target
          :model model
          :effort effort)
        (call finish-nonapproved-rich-design-review
          :review review
          :task task
          :check_contract check_contract
          :design_target design_target
          :design_review_target design_review_target
          :revision_target revision_target
          :product_review_target product_review_target
          :model model
          :effort effort))))

  (defworkflow continue-rich
    ((task String)
     (check_contract String)
     (design_target DesignTarget)
     (design_review_target ReviewTarget)
     (revision_target DesignTarget)
     (product_review_target ReviewTarget)
     (model String)
     (effort String))
    -> Bool
    (let* ((review
             (call review-design
               :task task
               :check_contract check_contract
               :design design_target
               :review_target design_review_target
               :model model
               :effort effort)))
      (call finish-rich-design-review
        :review review
        :task task
        :check_contract check_contract
        :design_target design_target
        :design_review_target design_review_target
        :revision_target revision_target
        :product_review_target product_review_target
        :model model
        :effort effort)))

  (defworkflow direct
    ((task String)
     (check_contract String)
     (model String)
     (effort String))
    -> Bool
    (let* ((implemented
             (call control.direct-task
               :task task
               :model model
               :effort effort)))
      (if implemented true false)))

  (defworkflow design-qa
    ((task String)
     (check_contract String)
     (model String)
     (effort String)
     (design_target DesignTarget
       :default "artifacts/work/qa-placement/design.md")
     (design_review_target ReviewTarget
       :default "artifacts/review/qa-placement/design-review.md")
     (revision_target DesignTarget
       :default "artifacts/work/qa-placement/design.md"))
    -> Bool
    (let* ((designed
             (call produce-design
               :task task
               :check_contract check_contract
               :design_target design_target
               :model model
               :effort effort)))
      (if designed
        (call continue-design-qa
          :task task
          :check_contract check_contract
          :design_target design_target
          :design_review_target design_review_target
          :revision_target revision_target
          :model model
          :effort effort)
        false)))

  (defworkflow product-qa
    ((task String)
     (check_contract String)
     (model String)
     (effort String)
     (product_review_target ReviewTarget
       :default "artifacts/review/qa-placement/product-review.md"))
    -> Bool
    (let* ((implemented
             (call control.direct-task
               :task task
               :model model
               :effort effort)))
      (if implemented
        (call run-product-qa
          :task task
          :check_contract check_contract
          :product_review_target product_review_target
          :model model
          :effort effort)
        false)))

  (defworkflow rich
    ((task String)
     (check_contract String)
     (model String)
     (effort String)
     (design_target DesignTarget
       :default "artifacts/work/qa-placement/design.md")
     (design_review_target ReviewTarget
       :default "artifacts/review/qa-placement/design-review.md")
     (revision_target DesignTarget
       :default "artifacts/work/qa-placement/design.md")
     (product_review_target ReviewTarget
       :default "artifacts/review/qa-placement/product-review.md"))
    -> Bool
    (let* ((designed
             (call produce-design
               :task task
               :check_contract check_contract
               :design_target design_target
               :model model
               :effort effort)))
      (if designed
        (call continue-rich
          :task task
          :check_contract check_contract
          :design_target design_target
          :design_review_target design_review_target
          :revision_target revision_target
          :product_review_target product_review_target
          :model model
          :effort effort)
        false)))
)
