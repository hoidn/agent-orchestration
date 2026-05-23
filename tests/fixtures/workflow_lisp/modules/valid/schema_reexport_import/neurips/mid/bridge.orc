(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/mid/bridge)
  (import neurips/shared/common :only (CommonFields))
  (export ExtendedFields)
  (defschema ExtendedFields
    (:include CommonFields)
    (execution_report String)))
