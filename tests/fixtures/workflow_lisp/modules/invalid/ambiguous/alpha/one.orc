(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule alpha/one)
  (export Shared)
  (defrecord Shared
    (status String)))
