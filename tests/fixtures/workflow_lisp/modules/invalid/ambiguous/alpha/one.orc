(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule alpha/one)
  (export Shared)
  (defrecord Shared
    (status String)))
