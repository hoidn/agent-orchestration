(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/bind_proc_capture)
  (export run)
  (defproc add-leading ((leading Int) (value Int)) -> Int
    :effects ()
    :lowering inline
    (+ leading value))
  (defworkflow run () -> Int
    (let* ((b 1)
           (hook (bind-proc (proc-ref add-leading) :leading (+ b 1))))
      (let* ((b 7))
        (hook 5)))))
