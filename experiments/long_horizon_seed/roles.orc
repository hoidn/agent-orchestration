(workflow-lisp (:language "0.1") (:target-dsl "2.40") (defmodule roles)
  (import common :only (Change CheckReport Outcome DocPath GuidePath Setup Spec Milestone Plan Verdict)) (export run)
  ;; Candidate C. Candidate B with conversations (Agent Sessions): one planner and one acceptance reviewer for the run,
  ;; one coder and one reviewer per milestone. Inputs: the task text and the intent only. At most eight milestones are
  ;; built: 6 + 8 * 8 calls at worst. Not yet: one refused twice is built upon; its reasons do not reach the planner.
  (defprompt guides (:fills (task :text)) -> Setup
    "Work in the current working directory and nowhere else. Prepare the project there for the task below; do not start the task. If there is no AGENTS.md, write it: how to build and test, the layout, the conventions, that the check this workflow runs after each piece of work is `python dev_check.py`, and the documentation rules below, so that every later step follows them. If there is code already, AGENTS.md describes its layout and conventions as they are, and you move or rewrite none of it; if there is none, create the directories the task needs (source, tests, docs; no task code yet). If AGENTS.md exists, keep what it says and add only what it lacks of the above. Then add what is missing of: docs/index.md (the catalogue: every document, one line each with a link and what it is for, grouped by kind); docs/log.md (append-only; each entry starts `## [date] step | title` and says what was done and decided); docs/notes/ (one page per lasting topic: a decision, a component, a pitfall; for existing code, what a newcomer needs). Documentation rules: read docs/index.md first; put lasting knowledge in a page under docs/notes/ and revise that page rather than adding a second; list every new document in docs/index.md; each step that changes a file appends one entry to docs/log.md (a review changes nothing and logs nothing). Never change dev_check.py or dev-check.json.\n\nTask: {task}\n\nReport `guide`: the path of that guide; every later step is given it and reads it first. `index`: the path of the catalogue. `log`: the path of the log.")
  (defprompt specify (:fills (guide :path GuidePath) (task :text)) -> Spec
    "Work in the current working directory and nowhere else. Read {guide} and follow it. Write docs/spec.md (another name under docs/ if the project already has that file): the task below as numbered targets T1, T2, ..., each one observable behaviour with the command or inspection that shows it holds; leave out nothing the task asks for. Write no code; never change dev_check.py or dev-check.json.\n\nTask: {task}\n\nReport `doc`: the path you wrote. `targets`: the target ids.")
  (defprompt plan (:fills (guide :path GuidePath) (log :path DocPath) (spec :path DocPath)
                          (notes :value List[String])) -> Plan
    "Work in the current working directory and nowhere else. Read {guide} and follow it. Write the plan to docs/plan.md, over the plan an earlier round of this work wrote there ({log} records it); use another name under docs/ only if the project had that file before this work began. The plan: the design in brief, then at most eight ordered milestones M1, M2, ..., each a small working increment that names the targets of {spec} it meets. Plan only what is not yet done. What earlier rounds left open (the reasons an acceptance was refused, then the check output of each round that failed since), empty on the first:\n{notes}\nWrite no code; never change dev_check.py or dev-check.json.\n\nReport `doc`: the path you wrote. `milestones`: each with `id`, `goal` and `targets`.")
  (defprompt work (:fills (guide :path GuidePath) (milestone :value Milestone) (spec :path DocPath)
                          (notes :value List[String])) -> Change
    "Work in the current working directory and nowhere else. Read {guide} and follow it. Carry out this milestone of the plan; {spec} states its targets:\n{milestone}\nDo not start a later milestone. Fix or restructure earlier code where this milestone needs it, and say so in `account`. Write tests for the behaviour you add. Run the check this workflow runs, `python dev_check.py`, as you go: whatever passed before your work must still pass; never change dev_check.py or dev-check.json. Leave the tree clean: no stray files, no commented-out code. Reasons your last attempt was refused, empty on the first; fix each one that is right:\n{notes}\n\nRecord what you did and learned as {guide} says (notes, index, log). Report `summary`: one sentence. `account`: what you changed and why.")
  (defprompt review (:fills (guide :path GuidePath) (task :text) (scope :value Milestone) (spec :path DocPath)
                            (report :value CheckReport)) -> Verdict
    "Review the project in the current working directory. Read {guide} and the code; change nothing. The task:\n{task}\nUnder review (the scope `all` is the whole task):\n{scope}\nThe check this workflow runs, `python dev_check.py`, just reported:\n{report}\nMET if all of this holds: the goal of the scope is reached; each of its targets holds as {spec} states it; no target that held before is broken; for the scope `all`, nothing the task asks for is left out, even where the spec is silent; the code is readable, tested and consistent with {guide}. Give the evidence per target. NOT_MET otherwise; each reason names the target or the gap, the input or scenario that goes wrong, and the check output that shows it.")
  (defworkflow milestone ((m Milestone) (guide GuidePath) (task String) (spec DocPath)) -> Verdict
    (let* ((coding (agent providers.coder :model "claude-haiku-5-5" :effort "medium"))
           (reviewing (agent providers.reviewer :model "claude-haiku-5-5" :effort "medium")))
      (loop/recur :max 2 :state (loop-state (notes List[String] (list)))
        :on-exhausted (variant Verdict NOT_MET :reasons state.notes) (fn (state)
          (let* ((change (provider-result coding :timeout-sec 3600
                           :prompt (work :guide guide :milestone m :spec spec :notes state.notes)))
                 (report (command-result dev-check :returns CheckReport))
                 (verdict (provider-result reviewing :timeout-sec 1200
                            :prompt (review :guide guide :task task :scope m :spec spec :report report))))
            (match verdict ((MET met) (done (variant Verdict MET :evidence met.evidence)))
              ((NOT_MET gap) (continue (loop-state :like state :notes gap.reasons)))))))))
  (defworkflow run ((task String) (intent String)) -> Outcome
    (let* ((planning (agent providers.planner :model "claude-haiku-5-5" :effort "medium"))
           (accepting (agent providers.reviewer :model "claude-haiku-5-5" :effort "medium"))
           (ready (provider-result planning :timeout-sec 1200 :prompt (guides :task task)))
           (spec (provider-result planning :timeout-sec 1200 :prompt (specify :guide ready.guide :task task)))
           (whole (record Milestone :id "all" :goal intent :targets spec.targets)))
      (loop/recur :max 2 :state (loop-state (notes List[String] (list)))
        :on-exhausted (variant Outcome BLOCKED :reason "acceptance round limit reached" :notes state.notes) (fn (state)
          (let* ((plan (provider-result planning :timeout-sec 1200
                         :prompt (plan :guide ready.guide :log ready.log :spec spec.doc :notes state.notes)))
                 (built (list/map-effect ((m (list/take plan.milestones 8))) :max 8
                          (let* ((each (call milestone :m m :guide ready.guide :task task :spec spec.doc))) each)))
                 (report (command-result dev-check :returns CheckReport)))
            (if (not report.passed) (continue (loop-state :like state :notes (list/append state.notes report.excerpt)))
              (let* ((acceptance
                       (provider-result accepting :timeout-sec 1200
                         :prompt (review :guide ready.guide :task task :scope whole :spec spec.doc :report report))))
                (match acceptance ((MET met) (done (variant Outcome DONE :summary "accepted")))
                  ((NOT_MET gap) (continue (loop-state :like state :notes gap.reasons))))))))))))
