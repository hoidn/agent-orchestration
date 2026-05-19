(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule duplicate/alias)
  (import alpha/common)
  (import beta/common)
  (export Placeholder)
  (defrecord Placeholder
    (status String)))
