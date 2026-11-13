(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule staged)
  (import common :only (Change CheckReport Outcome DocPath Spec Milestone Plan Verdict))
  (export run)

  ;; Candidate A. Guides, spec, plan; then rounds of: work through the plan, run
  ;; the visible check and, when it passes, ask for acceptance against the task.
  ;; A failed check or a refused acceptance is the next round's notes.
  (defprompt guides (:fills (task :text) (repo :text)) -> Change
    "Work in the git repository at {repo} and nowhere else. Prepare it for the task below; do not start the task. Where the repository has no AGENTS.md, set the project up: the directories the task needs (source, tests, docs; no task code yet); AGENTS.md (how to build, test and check the work, the layout, the conventions, and the documentation rules below, so that every later step follows them); docs/index.md (the catalogue: every document, one line each with a link and what it is for, grouped by kind); docs/log.md (append-only; each entry starts `## [date] step | title` and says what was done and decided); docs/notes/ (one page per lasting topic: a decision, a component, a pitfall). Documentation rules: read docs/index.md first; put lasting knowledge in a page under docs/notes/ and revise that page rather than adding a second; list every new document in docs/index.md; append one entry to docs/log.md per step. Where the repository already has guides or code, change none of it: read it, add only the missing parts of this structure, and record in docs/notes/ what a newcomer needs. Leave dev-check.json alone.\n\nTask: {task}\n\nReport `summary`: one sentence. `account`: the files you wrote.")
  (defprompt specify (:fills (task :text) (repo :text)) -> Spec
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Write docs/spec.md (another name under docs/ if the repository already has that file): the task below as numbered targets T1, T2, ..., each one observable behaviour with the command or inspection that shows it holds. Write no code.\n\nTask: {task}\n\nReport `doc`: the path you wrote. `targets`: the target ids.")
  (defprompt plan (:fills (repo :text) (spec :path DocPath)) -> Plan
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Write docs/plan.md, replacing your own earlier plan (another name under docs/ if the repository already had that file): the design in brief, then ordered milestones M1, M2, ..., each a small working increment that names the targets of {spec} it meets. Write no code.\n\nReport `doc`: the path you wrote. `milestones`: each with `id`, `goal` and `targets`.")
  (defprompt work (:fills (repo :text) (plan :path DocPath) (notes :value List[String])) -> Change
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Carry out {plan}, milestone by milestone; run the project's check as you go. Reasons the last round was refused, empty on the first; fix each one that is right:\n{notes}\n\nRecord what you did and learned as AGENTS.md says (notes, index, log). Report `summary`: one sentence. `account`: what you changed and why.")
  (defprompt review (:fills (repo :text) (scope :value Milestone) (spec :path DocPath) (report :value CheckReport)) -> Verdict
    "Review the git repository at {repo}. Read the code; change nothing. Under review:\n{scope}\nThe visible check just reported:\n{report}\nMET if the goal is reached and each of its targets, as {spec} states them, holds; give the evidence per target. NOT_MET otherwise; each reason names the target or the gap, the input or scenario that goes wrong, and the check output that shows it.")

  (defworkflow run ((task String) (intent String) (repo String)
                    (planner String) (coder String) (reviewer String) (effort String)) -> Outcome
    (let* ((ready (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                    :prompt (guides :task task :repo repo)))
           (spec (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                   :prompt (specify :task task :repo repo)))
           (plan (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                   :prompt (plan :repo repo :spec spec.doc)))
           (whole (record Milestone :id "all" :goal intent :targets spec.targets)))
      (loop/recur :max 4 :state (loop-state (notes List[String] (list)))
        :on-exhausted (variant Outcome BLOCKED :reason "round limit reached")
        (fn (state)
          (let* ((change (provider-result providers.coder :model coder :effort effort :timeout-sec 3600
                           :prompt (work :repo repo :plan plan.doc :notes state.notes)))
                 (report (command-result dev-check :returns CheckReport)))
            (if (not report.passed)
              (continue (loop-state :like state :notes (list/append report.failing report.excerpt)))
              (match (provider-result providers.reviewer :model reviewer :effort effort :timeout-sec 1200
                       :prompt (review :repo repo :scope whole :spec spec.doc :report report))
                ((MET met) (done (variant Outcome DONE :summary "accepted")))
                ((NOT_MET gap) (continue (loop-state :like state :notes gap.reasons)))))))))))
