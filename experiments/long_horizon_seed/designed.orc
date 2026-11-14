(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule designed)
  (import common :only (Change CheckReport Outcome DocPath Spec Design Milestone Plan Verdict))
  (export run)
  ;; Candidate D. Guides, spec, design (reviewed once; revised if refused), plan; then rounds as in candidate A.
  (defprompt guides (:fills (task :text) (repo :text)) -> Change
    "Work in the git repository at {repo} and nowhere else. Prepare it for the task below; do not start the task. Where the repository has no AGENTS.md, set the project up: the directories the task needs (source, tests, docs; no task code yet); AGENTS.md (how to build, test and check the work, the layout, the conventions, and the documentation rules below, so that every later step follows them); docs/index.md (the catalogue: every document, one line each with a link and what it is for, grouped by kind); docs/log.md (append-only; each entry starts `## [date] step | title` and says what was done and decided); docs/notes/ (one page per lasting topic: a decision, a component, a pitfall). Documentation rules: read docs/index.md first; put lasting knowledge in a page under docs/notes/ and revise that page rather than adding a second; list every new document in docs/index.md; append one entry to docs/log.md per step. Where the repository already has guides or code, change none of it: read it, add only the missing parts of this structure, and record in docs/notes/ what a newcomer needs. Leave dev-check.json alone.\n\nTask: {task}\n\nReport `summary`: one sentence. `account`: the files you wrote.")
  (defprompt specify (:fills (task :text) (repo :text)) -> Spec
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Write docs/spec.md (another name under docs/ if the repository already has that file): the task below as numbered targets T1, T2, ..., each one observable behaviour with the command or inspection that shows it holds. Write no code.\n\nTask: {task}\n\nReport `doc`: the path you wrote. `targets`: the target ids.")
  (defprompt design (:fills (repo :text) (spec :path DocPath)) -> Design
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Write docs/design.md (another name under docs/ if the repository already has that file): the parts and what each is responsible for; the interfaces between them (names, inputs, outputs, errors); the flow of data and of control; each significant decision with the alternative rejected and why; the risks; and, for each target of {spec}, how it will be shown to hold. Write no code and no plan of work.\n\nReport `doc`: the path you wrote.")
  (defprompt critique (:fills (repo :text) (spec :path DocPath) (design :path DocPath)) -> Verdict
    "Review the design {design} in the git repository at {repo} against {spec}. Read both, and the code there is; change nothing. MET if the design is adequate to build from: every target is covered and has a way to be shown to hold, every interface is definite enough to code against, and no decision contradicts a target; give the evidence per target. NOT_MET otherwise; each reason names the target or the interface at fault and says what is missing or wrong.")
  (defprompt revise (:fills (repo :text) (spec :path DocPath) (design :path DocPath) (notes :value List[String])) -> Design
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. A reviewer refused the design {design} against {spec} for the reasons below. Revise that document: fix each reason that is right, keep what stands, and record under its decisions each reason you reject and why. Write no code and no plan of work.\n{notes}\n\nReport `doc`: the path of the revised design.")
  (defprompt plan (:fills (repo :text) (spec :path DocPath) (design :path DocPath)) -> Plan
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Read {spec} and {design}. Write docs/plan.md, replacing your own earlier plan (another name under docs/ if the repository already had that file): ordered milestones M1, M2, ..., each a small working increment that names the parts of the design it builds and the targets it meets, in an order that keeps the project's check passing after each. Do not restate the design. Write no code.\n\nReport `doc`: the path you wrote. `milestones`: each with `id`, `goal` and `targets`.")
  (defprompt work (:fills (repo :text) (plan :path DocPath) (design :path DocPath) (notes :value List[String])) -> Change
    "Work in the git repository at {repo} and nowhere else. Read AGENTS.md and follow it. Carry out {plan}, milestone by milestone, to the design in {design}; run the project's check as you go. Where the design proves wrong, correct {design} first and say so in `account`. Reasons the last round was refused, empty on the first; fix each one that is right:\n{notes}\n\nRecord what you did and learned as AGENTS.md says (notes, index, log). Report `summary`: one sentence. `account`: what you changed and why.")
  (defprompt review (:fills (repo :text) (scope :value Milestone) (spec :path DocPath) (report :value CheckReport)) -> Verdict
    "Review the git repository at {repo}. Read the code; change nothing. Under review:\n{scope}\nThe visible check just reported:\n{report}\nMET if the goal is reached and each of its targets, as {spec} states them, holds; give the evidence per target. NOT_MET otherwise; each reason names the target or the gap, the input or scenario that goes wrong, and the check output that shows it.")

  (defworkflow run ((task String) (intent String) (repo String)
                    (planner String) (coder String) (reviewer String) (effort String)) -> Outcome
    (let* ((ready (provider-result providers.planner :model planner :effort effort :timeout-sec 1200 :prompt (guides :task task :repo repo)))
           (spec (provider-result providers.planner :model planner :effort effort :timeout-sec 1200 :prompt (specify :task task :repo repo)))
           (draft (provider-result providers.planner :model planner :effort effort :timeout-sec 1200 :prompt (design :repo repo :spec spec.doc)))
           (opinion (provider-result providers.reviewer :model reviewer :effort effort :timeout-sec 1200
                      :prompt (critique :repo repo :spec spec.doc :design draft.doc)))
           (design (match opinion
                     ((MET ok) draft)
                     ((NOT_MET gap) (let* ((revised (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                                                      :prompt (revise :repo repo :spec spec.doc :design draft.doc :notes gap.reasons))))
                                      revised))))
           (plan (provider-result providers.planner :model planner :effort effort :timeout-sec 1200
                   :prompt (plan :repo repo :spec spec.doc :design design.doc)))
           (whole (record Milestone :id "all" :goal intent :targets spec.targets)))
      (loop/recur :max 4 :state (loop-state (notes List[String] (list)))
        :on-exhausted (variant Outcome BLOCKED :reason "round limit reached")
        (fn (state)
          (let* ((change (provider-result providers.coder :model coder :effort effort :timeout-sec 3600
                           :prompt (work :repo repo :plan plan.doc :design design.doc :notes state.notes)))
                 (report (command-result dev-check :returns CheckReport)))
            (if (not report.passed)
              (continue (loop-state :like state :notes (list/append report.failing report.excerpt)))
              (match (provider-result providers.reviewer :model reviewer :effort effort :timeout-sec 1200
                       :prompt (review :repo repo :scope whole :spec spec.doc :report report))
                ((MET met) (done (variant Outcome DONE :summary "accepted")))
                ((NOT_MET gap) (continue (loop-state :like state :notes gap.reasons)))))))))))
