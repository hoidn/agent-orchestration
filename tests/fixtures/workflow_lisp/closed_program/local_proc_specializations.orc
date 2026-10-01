(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/local_proc_specializations)
  (export run)
  (defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int
    :effects ()
    :lowering inline
    (hook value))
  (defworkflow run ((choice Bool) (input Int)) -> Int
    (let* ((v 7))
      (if choice
        (let-proc (f ((x Int)) -> Int :captures (v) (+ x v))
          (apply-int (proc-ref f) input))
        (let-proc (f ((x Int)) -> Int :captures (v) (+ x v))
          (apply-int (proc-ref f) input))))))
