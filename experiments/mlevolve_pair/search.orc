(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule mlevolve_pair/search)
  (export run-search)

  (defrecord Candidate (a Int) (b Int))
  (defrecord Evaluation (valid Bool) (score Float) (error String))
  (defrecord Trial
    (action String)
    (branch String)
    (parents List[Candidate])
    (candidate Candidate)
    (evaluation Evaluation)
    (accepted Bool))
  (defrecord SearchState
    (a Candidate)
    (a_evaluation Evaluation)
    (b Candidate)
    (b_evaluation Evaluation)
    (best Candidate)
    (best_evaluation Evaluation)
    (history List[Trial])
    (evaluations Int)
    (next_branch String)
    (pending_branch String)
    (pending_candidate Candidate)
    (stall_a Int)
    (stall_b Int)
    (fused Bool))
  (defrecord SearchResult
    (candidate Candidate)
    (evaluation Evaluation)
    (evaluations Int)
    (status String)
    (trace List[Trial]))

  (defun result ((state SearchState) (status String)) -> SearchResult
    (record SearchResult
      :candidate state.best
      :evaluation state.best_evaluation
      :evaluations state.evaluations
      :status status
      :trace state.history))

  (defworkflow run-search
    ((max_evaluations Int :default 12)
     (target_score Float :default 0.0))
    -> SearchResult
    (if (or (< max_evaluations 2) (> max_evaluations 16))
      (record SearchResult
        :candidate (record Candidate :a 1 :b 0)
        :evaluation (record Evaluation
                      :valid false :score target_score :error "invalid_budget")
        :evaluations 0 :status "invalid_budget" :trace (list))
      (let* ((seed-a (record Candidate :a 1 :b 0))
             (seed-a-evaluation
               (command-result evaluate-seed-a
                 :adapter evaluate_candidate
                 :inputs ((a seed-a.a) (b seed-a.b))
                 :returns Evaluation))
             (seed-b (record Candidate :a 0 :b 1))
             (seed-b-evaluation
               (command-result evaluate-seed-b
                 :adapter evaluate_candidate
                 :inputs ((a seed-b.a) (b seed-b.b))
                 :returns Evaluation))
             (seed-b-is-best (and seed-b-evaluation.valid
                               (or (not seed-a-evaluation.valid)
                                   (< seed-b-evaluation.score seed-a-evaluation.score))))
             (best-seed (if seed-b-is-best seed-b seed-a))
             (best-evaluation (if seed-b-is-best seed-b-evaluation seed-a-evaluation))
             (seed-a-trial (record Trial
                              :action "seed" :branch "A" :parents (list)
                              :candidate seed-a :evaluation seed-a-evaluation
                              :accepted true))
             (seed-b-trial (record Trial
                              :action "seed" :branch "B" :parents (list)
                              :candidate seed-b :evaluation seed-b-evaluation
                              :accepted true))
             (initial (record SearchState
                        :a seed-a :a_evaluation seed-a-evaluation
                        :b seed-b :b_evaluation seed-b-evaluation
                        :best best-seed :best_evaluation best-evaluation
                        :history (list seed-a-trial seed-b-trial)
                        :evaluations 2 :next_branch "A"
                        :pending_branch "none" :pending_candidate seed-a
                        :stall_a 0 :stall_b 0 :fused false)))
        (loop/recur
          :max 16
          :state initial
          :on-exhausted (result state "loop_bound_exhausted")
          (fn (state)
            (if (and state.best_evaluation.valid
                     (<= state.best_evaluation.score target_score))
              (done (result state "solved"))
              (if (>= state.evaluations max_evaluations)
                (done (result state "budget_exhausted"))
(if (!= state.pending_branch "none")
      (if (= state.pending_branch "A")
        (let* ((candidate (command-result propose-repair-a
                           :adapter propose_candidate
                           :inputs ((operation "repair") (branch "A")
                                    (candidate_a state.pending_candidate.a)
                                    (candidate_b state.pending_candidate.b)
                                    (other_a state.b.a) (other_b state.b.b)
                                    (history_size state.evaluations))
                           :returns Candidate))
               (evaluation (command-result evaluate-repair-a
                             :adapter evaluate_candidate
                             :inputs ((a candidate.a) (b candidate.b))
                             :returns Evaluation))
               (accepted (and evaluation.valid
                              (< evaluation.score state.a_evaluation.score)))
               (trial (record Trial :action "repair" :branch "A"
                        :parents (list state.pending_candidate)
                        :candidate candidate :evaluation evaluation
                        :accepted accepted)))
          (if accepted
            (continue (record-update state :a candidate :a_evaluation evaluation
              :best (if (< evaluation.score state.best_evaluation.score) candidate state.best)
              :best_evaluation (if (< evaluation.score state.best_evaluation.score) evaluation state.best_evaluation)
              :history (list/append state.history trial)
              :evaluations (+ state.evaluations 1) :pending_branch "none"
              :stall_a 0 :next_branch "B"))
            (continue (record-update state
              :history (list/append state.history trial)
              :evaluations (+ state.evaluations 1) :pending_branch "none"
              :stall_a (+ state.stall_a 1) :next_branch "B"))))
        (let* ((candidate (command-result propose-repair-b
                           :adapter propose_candidate
                           :inputs ((operation "repair") (branch "B")
                                    (candidate_a state.pending_candidate.a)
                                    (candidate_b state.pending_candidate.b)
                                    (other_a state.a.a) (other_b state.a.b)
                                    (history_size state.evaluations))
                           :returns Candidate))
               (evaluation (command-result evaluate-repair-b
                             :adapter evaluate_candidate
                             :inputs ((a candidate.a) (b candidate.b))
                             :returns Evaluation))
               (accepted (and evaluation.valid
                              (< evaluation.score state.b_evaluation.score)))
               (trial (record Trial :action "repair" :branch "B"
                        :parents (list state.pending_candidate)
                        :candidate candidate :evaluation evaluation
                        :accepted accepted)))
          (if accepted
            (continue (record-update state :b candidate :b_evaluation evaluation
              :best (if (< evaluation.score state.best_evaluation.score) candidate state.best)
              :best_evaluation (if (< evaluation.score state.best_evaluation.score) evaluation state.best_evaluation)
              :history (list/append state.history trial)
              :evaluations (+ state.evaluations 1) :pending_branch "none"
              :stall_b 0 :next_branch "A"))
            (continue (record-update state
              :history (list/append state.history trial)
              :evaluations (+ state.evaluations 1) :pending_branch "none"
              :stall_b (+ state.stall_b 1) :next_branch "A")))))
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
               (accepted (and evaluation.valid
                              (< evaluation.score state.best_evaluation.score)))
               (trial (record Trial :action "fuse" :branch "both"
                        :parents (list state.a state.b) :candidate candidate
                        :evaluation evaluation :accepted accepted)))
          (continue (record-update state
            :best (if accepted candidate state.best)
            :best_evaluation (if accepted evaluation state.best_evaluation)
            :history (list/append state.history trial)
            :evaluations (+ state.evaluations 1)
            :stall_a 0 :stall_b 0 :fused true)))
        (if (= state.next_branch "A")
          (let* ((candidate (command-result propose-improve-a
                             :adapter propose_candidate
                             :inputs ((operation "improve") (branch "A")
                                      (candidate_a state.a.a) (candidate_b state.a.b)
                                      (other_a state.b.a) (other_b state.b.b)
                                      (history_size state.evaluations))
                             :returns Candidate))
                 (evaluation (command-result evaluate-improve-a
                               :adapter evaluate_candidate
                               :inputs ((a candidate.a) (b candidate.b))
                               :returns Evaluation))
                 (accepted (and evaluation.valid
                                (< evaluation.score state.a_evaluation.score)))
                 (trial (record Trial :action "improve" :branch "A"
                          :parents (list state.a) :candidate candidate
                          :evaluation evaluation :accepted accepted)))
            (if accepted
              (continue (record-update state :a candidate :a_evaluation evaluation
                :best (if (< evaluation.score state.best_evaluation.score) candidate state.best)
                :best_evaluation (if (< evaluation.score state.best_evaluation.score) evaluation state.best_evaluation)
                :history (list/append state.history trial)
                :evaluations (+ state.evaluations 1) :stall_a 0
                :pending_branch "none" :pending_candidate candidate :next_branch "B"))
              (continue (record-update state
                :history (list/append state.history trial)
                :evaluations (+ state.evaluations 1)
                :stall_a (+ state.stall_a 1)
                :pending_branch (if evaluation.valid "none" "A")
                :pending_candidate candidate :next_branch "B"))))
          (let* ((candidate (command-result propose-improve-b
                             :adapter propose_candidate
                             :inputs ((operation "improve") (branch "B")
                                      (candidate_a state.b.a) (candidate_b state.b.b)
                                      (other_a state.a.a) (other_b state.a.b)
                                      (history_size state.evaluations))
                             :returns Candidate))
                 (evaluation (command-result evaluate-improve-b
                               :adapter evaluate_candidate
                               :inputs ((a candidate.a) (b candidate.b))
                               :returns Evaluation))
                 (accepted (and evaluation.valid
                                (< evaluation.score state.b_evaluation.score)))
                 (trial (record Trial :action "improve" :branch "B"
                          :parents (list state.b) :candidate candidate
                          :evaluation evaluation :accepted accepted)))
            (if accepted
              (continue (record-update state :b candidate :b_evaluation evaluation
                :best (if (< evaluation.score state.best_evaluation.score) candidate state.best)
                :best_evaluation (if (< evaluation.score state.best_evaluation.score) evaluation state.best_evaluation)
                :history (list/append state.history trial)
                :evaluations (+ state.evaluations 1) :stall_b 0
                :pending_branch "none" :pending_candidate candidate :next_branch "A"))
              (continue (record-update state
                :history (list/append state.history trial)
                :evaluations (+ state.evaluations 1)
                :stall_b (+ state.stall_b 1)
                :pending_branch (if evaluation.valid "none" "B")
                :pending_candidate candidate :next_branch "A")))))))))))))))
