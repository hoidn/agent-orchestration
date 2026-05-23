(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule collection_structured_result)
  (export orchestrate)
  (defenum ReviewDecision
    APPROVE
    REVISE)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord CollectionResult
    (status String)
    (owner Optional[String])
    (attempt_ids List[Int])
    (reports Map[String, WorkReport])
    (review_states List[Optional[ReviewDecision]]))
  (defrecord WorkflowOutput
    (status String))
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> WorkflowOutput
    (let* ((result
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report_path)
               :returns CollectionResult)))
      (record WorkflowOutput
        :status result.status))))
