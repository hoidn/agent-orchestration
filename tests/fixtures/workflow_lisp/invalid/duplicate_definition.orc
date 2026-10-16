(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord WorkReport
    (status String)))
