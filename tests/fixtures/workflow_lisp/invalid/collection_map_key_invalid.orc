(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord InvalidCollection
    (reports Map[Int, WorkReport])))
