(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule cx/entry)
  (import cx/lib :only (Tagged keep))
  (import cx/a :only (Item make-a))
  (import cx/b :as b :only (make-b))
  (export run)
  (defrecord Out
    (n Int))
  (defproc run
    ((n Int))
    -> Out
    (let* ((from-a (keep (make-a n)))
           (from-b (keep (make-b n))))
      (record Out :n n))))
