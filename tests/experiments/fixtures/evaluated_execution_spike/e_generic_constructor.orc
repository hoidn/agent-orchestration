(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/e_generic_constructor)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defunion Maybe :forall (T) (SOME (value T)) (NONE (n Int)))
  (defproc wrap :forall (T) ((x T)) :where ((T is-record)) -> Maybe[T]
    :effects ()
    :lowering inline
    (variant Maybe[T] SOME :value x))
  (defworkflow run () -> Int
    (let* ((b (fetch 7)))
      (match (wrap b) ((SOME s) s.value.n) ((NONE z) z.n)))))
