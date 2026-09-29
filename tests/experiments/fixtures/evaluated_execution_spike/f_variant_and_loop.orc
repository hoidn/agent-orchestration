(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/f_variant_and_loop)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defunion Gate (OPEN (n Int)) (SHUT (n Int)))
  (defproc gate ((n Int)) -> Gate
    :effects ((uses-command gate))
    :lowering inline
    (command-result gate :argv ("python" "probe.py" "gate" n) :returns Gate))
  (defunion Outcome (QUICK (n Int)) (LOOPED (n Int)))
  (defworkflow run () -> Int
    (let* ((g (gate 1))
           (o (match g
                ((SHUT s) (variant Outcome QUICK :n s.n))
                ((OPEN p)
                 (loop/recur :max 3
                   :state (loop-state (n Int p.n))
                   :on-exhausted (variant Outcome LOOPED :n state.n)
                   (fn (state)
                     (let* ((b (fetch (+ state.n 1))))
                       (if (< b.n 3)
                         (continue (loop-state :like state :n b.n))
                         (done (variant Outcome LOOPED :n b.n))))))))))
      (match o ((QUICK q) q.n) ((LOOPED l) l.n)))))
