(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule branch_score)
  (export run)
  ;; The selection rule of docs/design/workflow_lisp_numeric_surface.md, section 4.
  (defun branch-score ((total Float) (visits Int) (all-visits Int) (weight Float)) -> Float
    (+ (/ total (int/to-float visits))
       (* weight
          (float/sqrt (/ (float/log (int/to-float all-visits))
                         (int/to-float visits))))))
  (defworkflow run ((total Float) (visits Int) (all-visits Int) (weight Float)) -> Float
    (branch-score total visits all-visits weight)))
