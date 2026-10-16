(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule cycle/right)
  (import cycle/entry)
  (export Right)
  (defrecord Right
    (status String)))
