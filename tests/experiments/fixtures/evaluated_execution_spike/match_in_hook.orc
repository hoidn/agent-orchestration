(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/match_in_hook)
  (import std/improve :only (Decision Improvement improve))
  (export run)
  (defrecord Box (n Int))
  (defunion Gate (OPEN (n Int)) (SHUT (n Int)))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defproc gate ((n Int)) -> Gate
    :effects ((uses-command gate))
    :lowering inline
    (command-result gate :argv ("python" "probe.py" "gate" n) :returns Gate))
  (defrecord Candidate (score Int))
  (defrecord Brief (goal Int))
  (defrecord Note (n Int))
  (defproc review ((c Candidate) (brief Brief)) -> Decision[Note Note]
    :effects ((uses-command gate))
    :lowering inline
    (match (gate c.score)
      ((OPEN o)
       (if (< o.n brief.goal)
         (variant Decision[Note Note] REVISE :feedback (record Note :n 1))
         (variant Decision[Note Note] APPROVE :evidence (record Note :n o.n))))
      ((SHUT s) (variant Decision[Note Note] BLOCKED :reason (record Note :n s.n)))))
  (defproc revise ((c Candidate) (brief Brief) (note Note)) -> Candidate
    :effects ((uses-command fetch))
    :lowering inline
    (let* ((b (fetch (+ c.score note.n))))
      (record Candidate :score b.n)))
  (defworkflow run () -> Int
    (let* ((result (improve (record Candidate :score 0) (record Brief :goal 3) (proc-ref review) (proc-ref revise) 5)))
      (match result
        ((APPROVED a) a.evidence.n)
        ((BLOCKED b) 0)
        ((EXHAUSTED e) e.value.score)))))
