(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule missing_bundle)
  (export run)
  (defrecord Trial (ordinal Int))
  (defrecord Progress (round Int) (history List[Trial]))
  (defworkflow run () -> Progress
    (loop/recur :max 3
      :state (record Progress :round 0 :history (list))
      :on-exhausted state
      (fn (state)
        (if (= state.round 2)
          (done state)
          (let* ((trial
                   (command-result emit
                     :argv ("python"
                            "experiments/mlevolve_pair/probes/missing_bundle.py"
                            state.round)
                     :returns Trial)))
            (continue
              (record-update state
                :round (+ state.round 1)
                :history (list/append state.history trial)))))))))
