(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule staged)
  (import common :only (Change CheckReport Outcome DocPath Spec Plan Verdict))
  (export run)

  ;; Candidate A. Guides, spec, plan; then rounds of: work through the plan, run
  ;; the visible check and, when it passes, ask for acceptance against the task.
  ;; A failed check or a refused acceptance is the next round's notes.
  (defprompt guides (:fills (task :text) (repo :text)) -> Change
    "Work in the git repository at {repo} and nowhere else. Prepare it for the task below; do not start the task. Where the repository has no AGENTS.md, write one (how to build, test and check the work, and its conventions), docs/index.md (one line per document) and docs/memory.md (decisions and lessons; every later step appends to it). Where it already has guides or code, change none of it: read it and record in docs/memory.md what a newcomer needs. Leave dev-check.json alone.\n\nTask: {task}\n\nReport `summary`: one sentence. `account`: the files you wrote.")
  (defprompt specify (:fills (task :text) (repo :text)) -> Spec
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Write docs/spec.md (another name under docs/ if the repository already has that file): the task below as numbered targets T1, T2, ..., each one observable behaviour with the command or inspection that shows it holds. Write no code.\n\nTask: {task}\n\nReport `doc`: the path you wrote. `targets`: the target ids.")
  (defprompt plan (:fills (repo :text) (spec :path DocPath)) -> Plan
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Write docs/plan.md, replacing your own earlier plan (another name under docs/ if the repository already had that file): the design in brief, then ordered milestones M1, M2, ..., each a small working increment that names the targets of {spec} it meets. Write no code.\n\nReport `doc`: the path you wrote. `milestones`: each with `id`, `goal` and `targets`.")
  (defprompt work (:fills (repo :text) (plan :path DocPath) (notes :value List[String])) -> Change
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Carry out {plan}, milestone by milestone; run the project's check as you go. Reasons the last round was refused, empty on the first; fix each one that is right:\n{notes}\n\nAppend what you learned to docs/memory.md. Report `summary`: one sentence. `account`: what you changed and why.")
  (defprompt review (:fills (repo :text) (scope :text) (spec :path DocPath) (report :value CheckReport)) -> Verdict
    "Review the git repository at {repo}. Read the code; change nothing. Under review: {scope}\nThe visible check just reported:\n{report}\nMET if every target of {spec} within that scope holds; give the evidence per target. NOT_MET otherwise; each reason names the target or the gap, the input or scenario that goes wrong, and the check output that shows it.")

  (defworkflow run ((task String) (intent String) (repo String)
                    (planner String) (coder String) (reviewer String) (effort String)) -> Outcome
    (let* ((ready (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                    :prompt (guides :task task :repo repo)))
           (spec (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                   :prompt (specify :task task :repo repo)))
           (plan (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                   :prompt (plan :repo repo :spec spec.doc))))
      (loop/recur :max 4 :state (loop-state (notes List[String] (list)))
        :on-exhausted (variant Outcome BLOCKED :reason "round limit reached")
        (fn (state)
          (let* ((change (provider-result providers.coder :model coder :effort effort :timeout-sec 3600
                           :prompt (work :repo repo :plan plan.doc :notes state.notes)))
                 (report (command-result dev-check :returns CheckReport)))
            (if (not report.passed)
              (continue (loop-state :like state :notes (list/append report.failing report.excerpt)))
              (match (provider-result providers.reviewer :model reviewer :effort effort :timeout-sec 1200
                       :prompt (review :repo repo :scope intent :spec spec.doc :report report))
                ((MET met) (done (variant Outcome DONE :summary "accepted")))
                ((NOT_MET gap) (continue (loop-state :like state :notes gap.reasons)))))))))))
