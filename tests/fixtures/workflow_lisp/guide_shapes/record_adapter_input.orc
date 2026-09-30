(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/record_adapter_input)
  (export run)
  (defrecord Box (n Int))
  (defworkflow run () -> Box
    (let* ((box (record Box :n 4)))
      (command-result fetch-record :adapter fetch_record :inputs ((box box)) :returns Box))))
