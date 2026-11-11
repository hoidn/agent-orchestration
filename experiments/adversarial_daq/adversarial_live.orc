(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule adversarial_live)
  (export run)

  (defpath Artifact :kind relpath :under "artifacts" :must-exist true)
  (defenum Position ADVANTAGE COUNTEREXAMPLE REVISE NEEDS_EXPERT)
  (defenum Status DEMO_SUPPORTED INCONCLUSIVE)
  (defrecord Submission (document Artifact) (manifest Artifact))
  (defrecord Evidence (valid Bool) (report Artifact) (digest String))
  (defrecord Vote
    (position Position)
    (claim String)
    (evidence_digest String)
    (fair Bool)
    (relevant Bool)
    (reproduced Bool)
    (blockers List[String])
    (reason String)
    (report Artifact))
  (defrecord Round
    (number Int)
    (proposal Submission)
    (challenge Submission)
    (evidence Evidence)
    (intact Bool)
    (skeptic Vote)
    (builder Vote))
  (defrecord SearchState (round Int) (history List[Round]))
  (defrecord Outcome (status Status) (reason String) (history List[Round]))

  ;; Judgments are explicit; valid transport alone never decides the thesis.
  (defun acceptable ((vote Vote) (evidence Evidence)) -> Bool
    (and evidence.valid vote.fair vote.relevant vote.reproduced
         (= vote.evidence_digest evidence.digest)
         (= (list/length vote.blockers) 0)
         (!= vote.claim "")))

  (defun agree ((a Vote) (b Vote) (evidence Evidence)) -> Bool
    (and (acceptable a evidence) (acceptable b evidence)
         (= a.position b.position) (= a.claim b.claim)))

  (defproc experiment
    ((brief String) (round Int) (history List[Round])) -> Round
    (let* ((proposal (provider-result providers.builder
                       :prompt prompts.builder
                       :inputs ("BUILD" brief round history)
                       :model "gpt-6.1-sol" :effort "high" :timeout-sec 1800 :returns Submission))
           (challenge (provider-result providers.skeptic
                        :prompt prompts.skeptic
                        :inputs ("CHALLENGE" brief round history proposal)
                        :model "gpt-6.1-sol" :effort "high" :timeout-sec 1800 :returns Submission))
           ;; A real command executes both implementations; no agent supplies its result.
           (evidence (command-result paired-trials
                       :argv ("python" "scripts/confined_trials.py" proposal.manifest challenge.manifest)
                       :returns Evidence))
           (skeptic (provider-result providers.skeptic
                      :prompt prompts.skeptic
                      :inputs ("REVIEW" brief round proposal challenge evidence)
                      :model "gpt-6.1-sol" :effort "high" :timeout-sec 900 :returns Vote))
           (builder (provider-result providers.builder
                      :prompt prompts.builder
                      :inputs ("ANSWER" brief round proposal challenge evidence skeptic)
                      :model "gpt-6.1-sol" :effort "high" :timeout-sec 900 :returns Vote))
           (intact (command-result verify-evidence
                     :argv ("python" "scripts/confined_trials.py" "verify" evidence.report evidence.digest)
                     :returns Bool)))
      ;; The pinned compiler requires explicit nested constructors at this boundary.
      (record Round :number round
        :proposal (record Submission :document proposal.document :manifest proposal.manifest)
        :challenge (record Submission :document challenge.document :manifest challenge.manifest)
        :evidence (record Evidence :valid evidence.valid :report evidence.report :digest evidence.digest)
        :intact intact
        :skeptic (record Vote :position skeptic.position :claim skeptic.claim
          :evidence_digest skeptic.evidence_digest :fair skeptic.fair :relevant skeptic.relevant
          :reproduced skeptic.reproduced :blockers skeptic.blockers :reason skeptic.reason :report skeptic.report)
        :builder (record Vote :position builder.position :claim builder.claim
          :evidence_digest builder.evidence_digest :fair builder.fair :relevant builder.relevant
          :reproduced builder.reproduced :blockers builder.blockers :reason builder.reason :report builder.report))))

  (defworkflow run
    ((brief String)
     (round_limit Int :default 4)) -> Outcome
    (if (or (< round_limit 1) (> round_limit 4))
      (record Outcome :status Status.INCONCLUSIVE
        :reason "round_limit must be between 1 and 4; no agents dispatched"
        :history (list))
      (loop/recur :max 4
        :state (record SearchState :round 1 :history (list))
        :on-exhausted (record Outcome :status Status.INCONCLUSIVE
                        :reason "hard search bound exhausted" :history state.history)
        (fn (state)
          (let* ((trial (experiment brief state.round state.history))
                 (history (list/append state.history trial))
                 (consensus (and trial.intact (agree trial.builder trial.skeptic trial.evidence))))
            (if (and consensus (= trial.skeptic.position Position.ADVANTAGE))
              (done (record Outcome :status Status.DEMO_SUPPORTED
                :reason trial.skeptic.claim :history history))
              (if (>= state.round round_limit)
                (done (record Outcome :status Status.INCONCLUSIVE
                  :reason "budget exhausted without a supported advantage; no impossibility claim"
                  :history history))
                (continue (record SearchState
                  :round (+ state.round 1) :history history)))))))))
)
