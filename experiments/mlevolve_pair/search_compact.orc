(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule mlevolve_pair/search_compact)
  (export run-search)

  (defrecord Candidate (a Int) (b Int))
  (defrecord Evaluation (valid Bool) (score Float) (error String))
  (defrecord Trial
    (action String) (branch String) (parents List[Candidate])
    (candidate Candidate) (evaluation Evaluation) (accepted Bool))
  (defrecord SearchState
    (a Candidate) (a_evaluation Evaluation)
    (b Candidate) (b_evaluation Evaluation)
    (best Candidate) (best_evaluation Evaluation)
    (history List[Trial]) (evaluations Int) (next_branch String)
    (pending_branch String) (pending_candidate Candidate)
    (stall_a Int) (stall_b Int) (fused Bool))
  (defrecord SearchResult
    (candidate Candidate) (evaluation Evaluation) (evaluations Int)
    (status String) (trace List[Trial]))

  (defun result ((state SearchState) (status String)) -> SearchResult
    (record SearchResult :candidate state.best :evaluation state.best_evaluation
      :evaluations state.evaluations :status status :trace state.history))

  (defproc branch-step
    ((state SearchState) (operation String) (branch String)) -> SearchState
    :effects ((uses-command propose-branch-candidate) (uses-command evaluate-branch-candidate))
    :lowering inline
    (let* ((current (if (= branch "A") state.a state.b))
           (other (if (= branch "A") state.b state.a))
           (base (if (= operation "repair") state.pending_candidate current))
           (parents (if (= operation "repair")
                      (list state.pending_candidate) (list current)))
           (candidate (command-result propose-branch-candidate
                         :adapter propose_candidate
                         :inputs ((operation operation) (branch branch)
                                  (candidate_a base.a) (candidate_b base.b)
                                  (other_a other.a) (other_b other.b)
                                  (history_size state.evaluations))
                         :returns Candidate))
           (evaluation (command-result evaluate-branch-candidate
                           :adapter evaluate_candidate
                           :inputs ((a candidate.a) (b candidate.b))
                           :returns Evaluation))
           (current-evaluation (if (= branch "A") state.a_evaluation state.b_evaluation))
           (accepted (and evaluation.valid (< evaluation.score current-evaluation.score)))
           (best-changed (and accepted (< evaluation.score state.best_evaluation.score)))
           (trial (record Trial :action operation :branch branch :parents parents
                    :candidate candidate :evaluation evaluation :accepted accepted))
           (next (record-update state
                   :best (if best-changed candidate state.best)
                   :best_evaluation (if best-changed evaluation state.best_evaluation)
                   :history (list/append state.history trial)
                   :evaluations (+ state.evaluations 1)
                   :next_branch (if (= branch "A") "B" "A")
                   :pending_branch (if (= operation "repair") "none"
                                     (if evaluation.valid "none" branch))
                   :pending_candidate (if (= operation "repair") state.pending_candidate candidate)
                   :fused state.fused)))
      (if (= branch "A")
        (record-update next
          :a (if accepted candidate state.a)
          :a_evaluation (if accepted evaluation state.a_evaluation)
          :stall_a (if accepted 0 (+ state.stall_a 1)))
        (record-update next
          :b (if accepted candidate state.b)
          :b_evaluation (if accepted evaluation state.b_evaluation)
          :stall_b (if accepted 0 (+ state.stall_b 1))))))

  (defworkflow run-search
    ((max_evaluations Int :default 12) (target_score Float :default 0.0))
    -> SearchResult
    (if (or (< max_evaluations 2) (> max_evaluations 16))
      (record SearchResult
        :candidate (record Candidate :a 1 :b 0)
        :evaluation (record Evaluation :valid false :score target_score :error "invalid_budget")
        :evaluations 0 :status "invalid_budget" :trace (list))
      (let* ((seed-a (record Candidate :a 1 :b 0))
             (seed-a-evaluation (command-result evaluate-seed-a
                                  :adapter evaluate_candidate
                                  :inputs ((a seed-a.a) (b seed-a.b)) :returns Evaluation))
             (seed-b (record Candidate :a 0 :b 1))
             (seed-b-evaluation (command-result evaluate-seed-b
                                  :adapter evaluate_candidate
                                  :inputs ((a seed-b.a) (b seed-b.b)) :returns Evaluation))
             (best-seed (if (< seed-b-evaluation.score seed-a-evaluation.score) seed-b seed-a))
             (best-evaluation (if (< seed-b-evaluation.score seed-a-evaluation.score)
                                seed-b-evaluation seed-a-evaluation))
             (seed-a-trial (record Trial :action "seed" :branch "A" :parents (list)
                                :candidate seed-a :evaluation seed-a-evaluation :accepted true))
             (seed-b-trial (record Trial :action "seed" :branch "B" :parents (list)
                                :candidate seed-b :evaluation seed-b-evaluation :accepted true))
             (initial (record SearchState
                         :a seed-a :a_evaluation seed-a-evaluation
                         :b seed-b :b_evaluation seed-b-evaluation
                         :best best-seed :best_evaluation best-evaluation
                         :history (list seed-a-trial seed-b-trial) :evaluations 2
                         :next_branch "A" :pending_branch "none" :pending_candidate seed-a
                         :stall_a 0 :stall_b 0 :fused false)))
        (loop/recur
          :max 16
          :state initial
          :on-exhausted (result state "loop_bound_exhausted")
          (fn (state)
            (if (<= state.best_evaluation.score target_score)
              (done (result state "solved"))
              (if (>= state.evaluations max_evaluations)
                (done (result state "budget_exhausted"))
                (if (!= state.pending_branch "none")
                  (let* ((next-state (branch-step state "repair" state.pending_branch)))
                    (continue next-state))
                  (if (and (>= state.stall_a 2) (>= state.stall_b 2)
                           (= state.fused false))
                    (let* ((candidate (command-result propose-fusion
                                       :adapter propose_candidate
                                       :inputs ((operation "fuse") (branch "both")
                                                (candidate_a state.a.a) (candidate_b state.a.b)
                                                (other_a state.b.a) (other_b state.b.b)
                                                (history_size state.evaluations))
                                       :returns Candidate))
                           (evaluation (command-result evaluate-fusion
                                         :adapter evaluate_candidate
                                         :inputs ((a candidate.a) (b candidate.b))
                                         :returns Evaluation))
                           (accepted (and evaluation.valid (< evaluation.score state.best_evaluation.score)))
                           (trial (record Trial :action "fuse" :branch "both"
                                    :parents (list state.a state.b) :candidate candidate
                                    :evaluation evaluation :accepted accepted)))
                      (continue (record-update state
                        :best (if accepted candidate state.best)
                        :best_evaluation (if accepted evaluation state.best_evaluation)
                        :history (list/append state.history trial)
                        :evaluations (+ state.evaluations 1)
                        :stall_a 0 :stall_b 0 :fused true)))
                    (let* ((next-state (branch-step state "improve" state.next_branch)))
                      (continue next-state))))))))))))
