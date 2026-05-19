(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule other/place)
  (export Broken)
  (defrecord Broken
    (status String)))
