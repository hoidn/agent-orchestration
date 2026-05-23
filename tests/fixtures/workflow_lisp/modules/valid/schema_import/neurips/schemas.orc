(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/schemas)
  (export WorkReport ReportTargets ReviewTargets)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defschema ReportTargets
    (execution_report WorkReport))
  (defschema ReviewTargets
    (status String)
    (:include ReportTargets)))
