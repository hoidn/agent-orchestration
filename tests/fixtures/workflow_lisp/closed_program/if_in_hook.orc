(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule cp/if_in_hook)
  (import std/improve :only (Decision Improvement improve))
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defrecord Candidate (score Int))
  (defrecord Note (n Int))
  (defproc review ((c Candidate)) -> Decision[Note Note]
    (let* ((b (fetch c.score)))
      (if (< b.n 4)
        (if (< b.n 1)
          (variant Decision[Note Note] REVISE :feedback (record Note :n 1))
          (variant Decision[Note Note] REVISE :feedback (record Note :n 2)))
        (variant Decision[Note Note] APPROVE :evidence (record Note :n b.n)))))
  (defproc revise ((c Candidate) (note Note)) -> Candidate
    (let* ((b (fetch (+ c.score note.n))))
      (record Candidate :score b.n)))
  (defworkflow run () -> Int
    (let* ((result (improve (record Candidate :score 0) (proc-ref review) (proc-ref revise) 5)))
      (match result
        ((APPROVED a) a.evidence.n)
        ((BLOCKED b) 0)
        ((EXHAUSTED e) e.value.score)))))
