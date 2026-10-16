(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule cycle/entry)
  (import cycle/left)
  (export Root)
  (defrecord Root
    (status String)))
