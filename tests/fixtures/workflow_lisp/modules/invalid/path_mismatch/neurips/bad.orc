(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule other/place)
  (export Broken)
  (defrecord Broken
    (status String)))
