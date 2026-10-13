(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule repl_feature)
  (export run)

  ;; A variation of workflows/examples/plan_review_execute.orc with prompts
  ;; detailed enough to design and build one repository feature: Claude plans,
  ;; Codex reviews the plan, Claude revises it with that feedback, Codex
  ;; executes the revised plan in the current repository.
  ;;
  ;;   python -m orchestrator compile experiments/orc_repl_feature/repl_feature.orc \
  ;;     --provider-externs-file experiments/orc_repl_feature/providers.json

  (defrecord Plan
    (summary String)
    (decisions List[String])
    (steps List[String])
    (verification List[String]))
  (defrecord Feedback
    (blocking List[String])
    (notes List[String]))
  (defrecord Execution
    (summary String)
    (commits List[String])
    (checks_run List[String])
    (left_undone List[String]))

  (defprompt draft-plan (:fills (task :text)) -> Plan
    "You are designing one feature for this repository, which is a git worktree of agent-orchestration. Change no files.\n\nBefore planning, read AGENTS.md, docs/index.md, docs/templates/design_template.md, docs/design/workflow_language_design_principles.md, sections 1, 5, 8, 10 and 12 of docs/design/workflow_lisp_evaluated_execution.md, the `Evaluated execution (target 2.35)` section of specs/cli.md, the evaluated profile section of specs/state.md, and the code in orchestrator/workflow/evaluated/machine.py, values.py, views.py, runtime.py, authority.py, memo.py, in orchestrator/cli/commands/evaluated.py, run.py, resume.py, report.py, and in orchestrator/workflow_lisp/typecheck_dispatch.py and orchestrator/workflow_lisp/closed/build.py.\n\nTask:\n{task}\n\nProduce a plan an engineer can execute without further design work.\n`summary`: one sentence.\n`decisions`: every design decision the task leaves open, each stated as a decision with its reason: the command line and the forms the REPL accepts; where the lexical environment is captured for a completed run and for an interrupted or failed run; how an expression typed at the prompt is typechecked and evaluated against the captured bindings, naming the existing functions reused; what the REPL refuses and with which diagnostic code; how a value and its type are printed; what the first release leaves out. Prefer the existing typechecker, closed-program builder, memo reader and evaluator over any new evaluator; do not change the memo format, the closed-program schema or evaluator semantics.\n`steps`: ordered implementation steps, each naming the files it creates or changes and what goes into them. The first step writes the design document from docs/templates/design_template.md under docs/design/. Later steps implement, add behavioural tests through public entries, and update docs/index.md and docs/capability_status_matrix.md.\n`verification`: the exact commands that prove the work: narrow pytest selectors first, then `pytest -q -n 16 --dist=worksteal -m \"not e2e\"`, then one smoke of the REPL against a real evaluated run of workflows/examples/plan_review_execute.orc.")

  (defprompt review-plan
    (:fills (task :text) (summary :text) (decisions :value List[String]) (steps :value List[String]) (verification :value List[String]))
    -> Feedback
    "Review this implementation plan against the repository. Read AGENTS.md, docs/index.md, sections 1, 5, 8, 10 and 12 of docs/design/workflow_lisp_evaluated_execution.md, the `Evaluated execution (target 2.35)` section of specs/cli.md, and every code path the plan names. Change nothing.\n\nTask:\n{task}\n\nPlan summary: {summary}\nDecisions:\n{decisions}\nSteps:\n{steps}\nVerification:\n{verification}\n\nJudge six things. (1) Each decision is consistent with the evaluated-execution contract: values are evaluated, effects are memoized by identity, a reader launches nothing, and the memo format, closed-program schema and evaluator semantics are unchanged. (2) The REPL reuses the ordinary typechecker, closed-program builder and evaluator; there is no second expression evaluator or parser. (3) The REPL never holds the run writer lock while waiting for input and performs no effect of its own in this release. (4) The steps are executable as written: every file, function and entry they name exists or is created by an earlier step, and nothing relies on a test-only or fixture-only path. (5) The verification proves behaviour through public entries and would stay valid if prompt text changed. (6) Scope stays bounded to the task.\n`blocking`: defects that would make execution fail, violate a contract above, or leave the task's scope; each names the decision or step and the input or scenario that goes wrong. `notes`: improvements that do not block; may be empty.")

  (defprompt revise-plan
    (:fills (task :text) (summary :text) (decisions :value List[String]) (steps :value List[String]) (verification :value List[String]) (blocking :value List[String]) (notes :value List[String]))
    -> Plan
    "Revise this plan with the reviewer's feedback. Change no files. Address every blocking finding; adopt each note or answer it. A finding can be wrong: where you do not adopt one, add a decision beginning with `Reply:` that says why. Keep everything the reviewer did not question.\n\nTask:\n{task}\n\nPlan summary: {summary}\nDecisions:\n{decisions}\nSteps:\n{steps}\nVerification:\n{verification}\n\nBlocking findings:\n{blocking}\nNotes:\n{notes}\n\nReport the whole revised plan: `summary`, `decisions`, `steps`, `verification`, with the same meaning as before.")

  (defprompt execute-plan
    (:fills (task :text) (summary :text) (decisions :value List[String]) (steps :value List[String]) (verification :value List[String]))
    -> Execution
    "Execute this plan in the current repository, a git worktree on branch feature/orc-repl. Read AGENTS.md first and follow it.\n\nTask:\n{task}\n\nPlan summary: {summary}\nDecisions:\n{decisions}\nSteps:\n{steps}\nVerification:\n{verification}\n\nRules. Write the design document first, then implement, then test. Run every verification command and treat its output as the evidence; do not claim a check you did not run. Never disable, weaken or delete a test to make it pass. If a step cannot be done as planned, do the nearest thing that keeps the design's contracts and record it in `left_undone`. Keep modules under 500 lines. Commit incrementally with `git add <paths>` and `git commit -- <paths>`; commit messages describe the change and carry no assistant attribution or co-author trailer.\n\nReport `summary`: what now exists. `commits`: each commit hash with one line. `checks_run`: each command you ran with its result. `left_undone`: anything the plan asked for that is not done, with the reason; may be empty.")

  (defworkflow run ((task String)) -> Execution
    (let* ((draft (provider-result providers.claude :model "claude-fable-5-1" :effort "high" :timeout-sec 3600
                    :prompt (draft-plan :task task)))
           (feedback (provider-result providers.codex :model "gpt-6-sol" :effort "high" :timeout-sec 3600
                       :prompt (review-plan :task task :summary draft.summary :decisions draft.decisions
                                            :steps draft.steps :verification draft.verification)))
           (revised (provider-result providers.claude :model "claude-fable-5-1" :effort "high" :timeout-sec 3600
                      :prompt (revise-plan :task task :summary draft.summary :decisions draft.decisions
                                           :steps draft.steps :verification draft.verification
                                           :blocking feedback.blocking :notes feedback.notes))))
      (provider-result providers.codex :model "gpt-5.6-luna" :effort "xhigh" :timeout-sec 14400
        :prompt (execute-plan :task task :summary revised.summary :decisions revised.decisions
                              :steps revised.steps :verification revised.verification))))
)
