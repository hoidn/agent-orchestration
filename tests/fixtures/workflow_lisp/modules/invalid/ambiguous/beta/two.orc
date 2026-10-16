(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule beta/two)
  (export Shared)
  (defrecord Shared
    (status String)))
