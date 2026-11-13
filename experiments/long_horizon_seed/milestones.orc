(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule milestones)
  (import common :only (Change CheckReport Outcome DocPath Spec Milestone Plan Verdict))
  (export run)
  ;; Candidate B. Guides, spec; then rounds of: plan, build each milestone (work, check, review), check, acceptance.
  (defprompt guides (:fills (task :text) (repo :text)) -> Change
    "Work in the git repository at {repo} and nowhere else. Prepare it for the task below; do not start the task. Where the repository has no AGENTS.md, write one (how to build, test and check the work, and its conventions), docs/index.md (one line per document) and docs/memory.md (decisions and lessons; every later step appends to it). Where it already has guides or code, change none of it: read it and record in docs/memory.md what a newcomer needs. Leave dev-check.json alone.\n\nTask: {task}\n\nReport `summary`: one sentence. `account`: the files you wrote.")
  (defprompt specify (:fills (task :text) (repo :text)) -> Spec
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Write docs/spec.md (another name under docs/ if the repository already has that file): the task below as numbered targets T1, T2, ..., each one observable behaviour with the command or inspection that shows it holds. Write no code.\n\nTask: {task}\n\nReport `doc`: the path you wrote. `targets`: the target ids.")
  (defprompt plan (:fills (repo :text) (spec :path DocPath) (notes :value List[String])) -> Plan
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Write docs/plan.md, replacing your own earlier plan (another name under docs/ if the repository already had that file): the design in brief, then at most eight ordered milestones M1, M2, ..., each a small working increment that names the targets of {spec} it meets. Plan only what is not yet done. Reasons the last round was refused, empty on the first:\n{notes}\nWrite no code.\n\nReport `doc`: the path you wrote. `milestones`: each with `id`, `goal` and `targets`.")
  (defprompt work (:fills (repo :text) (milestone :value Milestone) (notes :value List[String])) -> Change
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Carry out this milestone of the plan and nothing beyond it; run the project's check as you go:\n{milestone}\nReasons your last attempt was refused, empty on the first; fix each one that is right:\n{notes}\n\nAppend what you learned to docs/memory.md. Report `summary`: one sentence. `account`: what you changed and why.")
  (defprompt review (:fills (repo :text) (scope :value Milestone) (spec :path DocPath) (report :value CheckReport)) -> Verdict
    "Review the git repository at {repo}. Read the code; change nothing. Under review:\n{scope}\nThe visible check just reported:\n{report}\nMET if the goal is reached and each of its targets, as {spec} states them, holds; give the evidence per target. NOT_MET otherwise; each reason names the target or the gap, the input or scenario that goes wrong, and the check output that shows it.")

  (defworkflow milestone ((m Milestone) (repo String) (spec DocPath) (coder String) (reviewer String) (effort String)) -> Verdict
    (loop/recur :max 2 :state (loop-state (notes List[String] (list)))
      :on-exhausted (variant Verdict NOT_MET :reasons state.notes)
      (fn (state)
        (let* ((change (provider-result providers.coder :model coder :effort effort :timeout-sec 3600
                         :prompt (work :repo repo :milestone m :notes state.notes)))
               (report (command-result dev-check :returns CheckReport)))
          (match (provider-result providers.reviewer :model reviewer :effort effort :timeout-sec 1200
                   :prompt (review :repo repo :scope m :spec spec :report report))
            ((MET met) (done (variant Verdict MET :evidence met.evidence)))
            ((NOT_MET gap) (continue (loop-state :like state :notes gap.reasons))))))))

  (defworkflow run ((task String) (intent String) (repo String)
                    (planner String) (coder String) (reviewer String) (effort String)) -> Outcome
    (let* ((ready (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                    :prompt (guides :task task :repo repo)))
           (spec (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                   :prompt (specify :task task :repo repo)))
           (whole (record Milestone :id "all" :goal intent :targets spec.targets)))
      (loop/recur :max 2 :state (loop-state (notes List[String] (list)))
        :on-exhausted (variant Outcome BLOCKED :reason "acceptance round limit reached")
        (fn (state)
          (let* ((plan (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                         :prompt (plan :repo repo :spec spec.doc :notes state.notes)))
                 (built (list/map-effect ((m plan.milestones)) :max 8
                          (call milestone :m m :repo repo :spec spec.doc :coder coder :reviewer reviewer :effort effort)))
                 (report (command-result dev-check :returns CheckReport)))
            (if (not report.passed)
              (continue (loop-state :like state :notes (list/append report.failing report.excerpt)))
              (match (provider-result providers.reviewer :model reviewer :effort effort :timeout-sec 1200
                       :prompt (review :repo repo :scope whole :spec spec.doc :report report))
                ((MET met) (done (variant Outcome DONE :summary "accepted")))
                ((NOT_MET gap) (continue (loop-state :like state :notes gap.reasons)))))))))))
