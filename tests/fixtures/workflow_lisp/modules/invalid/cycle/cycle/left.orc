(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule cycle/left)
  (import cycle/right)
  (export Left)
  (defrecord Left
    (status String)))
