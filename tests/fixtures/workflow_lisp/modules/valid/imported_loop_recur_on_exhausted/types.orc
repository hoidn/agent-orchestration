(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule types)
  (export WorkReport LoopSignal LoopState LoopResult)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defunion LoopSignal
    (RETRY
      (report WorkReport))
    (READY
      (report WorkReport)))
  (defrecord LoopState
    (report WorkReport))
  (defunion LoopResult
    (COMPLETED
      (status String)
      (report WorkReport))
    (EXHAUSTED
      (reason String)
      (report WorkReport))))
