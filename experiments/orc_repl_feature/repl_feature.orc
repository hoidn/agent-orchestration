(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule repl_feature)
  (export run DraftDocPath DesignDocPath Draft Design Feedback Execution
          draft-design review-design revise-design execute-design)

  ;; The variation of workflows/examples/design_review_execute.orc that
  ;; designed and built `orchestrator repl`: the same four-step shape, with
  ;; prompts that name the documents, code and contracts this feature
  ;; touches. The design is a markdown file: the planner drafts
  ;; artifacts/design/<slug>.md, the reviewer reads it, the planner writes the
  ;; final docs/design/<slug>.md, and the reviewer's model executes it. The
  ;; draft is never edited after the review reads it, so `resume` can retry
  ;; any step. The runs recorded in README.md used an earlier shape of this
  ;; file that flattened the plan into JSON lists.
  ;;
  ;;   python -m orchestrator compile experiments/orc_repl_feature/repl_feature.orc \
  ;;     --provider-externs-file experiments/orc_repl_feature/providers.json

  (defpath DraftDocPath :kind relpath :under "artifacts/design" :must-exist true)
  (defpath DesignDocPath :kind relpath :under "docs/design" :must-exist true)

  (defrecord Draft (doc DraftDocPath))
  (defrecord Design (doc DesignDocPath))
  (defrecord Feedback
    (blocking List[String])
    (notes List[String]))
  (defrecord Execution
    (summary String)
    (commits List[String])
    (checks_run List[String])
    (left_undone List[String]))

  (defprompt draft-design (:fills (task :text)) -> Draft
    "You are designing one feature for this repository, a git worktree of agent-orchestration. Before designing, read AGENTS.md, docs/index.md, docs/templates/design_template.md, docs/design/workflow_language_design_principles.md, sections 1, 5, 8, 10 and 12 of docs/design/workflow_lisp_evaluated_execution.md, the `Evaluated execution (target 2.35)` section of specs/cli.md, the evaluated profile section of specs/state.md, and the code in orchestrator/workflow/evaluated/machine.py, values.py, views.py, runtime.py, authority.py, memo.py, in orchestrator/cli/commands/evaluated.py, run.py, resume.py, report.py, and in orchestrator/workflow_lisp/typecheck_dispatch.py and orchestrator/workflow_lisp/closed/build.py.\n\nWrite the design document as a new file artifacts/design/<slug>.md, with a short slug you choose from the task, structured by docs/templates/design_template.md with the sections that do not apply deleted. It must leave no decision to the implementer: the command line and the forms the REPL accepts; where the lexical environment is captured for a completed run and for an interrupted or failed run; how an expression typed at the prompt is typechecked and evaluated against the captured bindings, naming the existing functions reused; what the REPL refuses and with which diagnostic codes; how a value and its type are printed; what the first release leaves out. Prefer the existing typechecker, closed-program builder, memo reader and evaluator over any new evaluator; do not change the memo format, the closed-program schema or evaluator semantics. Its implementation handoff lists the ordered steps an engineer executes without further design work, each naming the files it creates or changes; the first step writes the final design document under docs/design/, later steps implement, add behavioural tests through public entries, and update docs/index.md and docs/capability_status_matrix.md. Its verification section lists the exact commands that prove the work: narrow pytest selectors first, then `pytest -q -n 16 --dist=worksteal -m \"not e2e\"`, then one smoke of the REPL against a real evaluated run of workflows/examples/plan_review_execute.orc. Change no other file.\n\nTask:\n{task}\n\nReturn `doc`: the path you wrote, relative to the repository root, as the result rather than as a reply.")

  (defprompt review-design (:fills (task :text) (design :doc DraftDocPath)) -> Feedback
    "Review the injected design document against the repository. Read AGENTS.md, docs/index.md, sections 1, 5, 8, 10 and 12 of docs/design/workflow_lisp_evaluated_execution.md, the `Evaluated execution (target 2.35)` section of specs/cli.md, and every code path the document names. Change nothing.\n\nTask:\n{task}\n\nJudge six things. (1) Each decision is consistent with the evaluated-execution contract: values are evaluated, effects are memoized by identity, a reader launches nothing, and the memo format, closed-program schema and evaluator semantics are unchanged. (2) The REPL reuses the ordinary typechecker, closed-program builder and evaluator; there is no second expression evaluator or parser. (3) The REPL never holds the run writer lock while waiting for input and performs no effect of its own in this release. (4) The implementation handoff is executable as written: every file, function and entry it names exists or is created by an earlier step, and nothing relies on a test-only or fixture-only path. (5) The verification section proves behaviour through public entries and would stay valid if prompt text changed. (6) Scope stays bounded to the task.\n`blocking`: defects that would make execution fail, violate a contract above, or leave the task's scope; each names the section or step and the input or scenario that goes wrong. `notes`: improvements that do not block; may be empty.")

  (defprompt revise-design
    (:fills (task :text) (design :doc DraftDocPath) (draft_path :path DraftDocPath)
            (blocking :value List[String]) (notes :value List[String]))
    -> Design
    "Revise the injected design document with the reviewer's feedback and write the final document as a new file docs/design/<slug>.md, with the same slug as the draft {draft_path}. Leave the draft unchanged. Address every blocking finding; adopt each note or answer it under a `Review responses` heading. A finding can be wrong: where you do not adopt one, say why there. Keep everything the reviewer did not question. Change no other file.\n\nTask:\n{task}\n\nBlocking findings:\n{blocking}\nNotes:\n{notes}\n\nReturn `doc`: the path you wrote, relative to the repository root, as the result rather than as a reply.")

  (defprompt execute-design (:fills (task :text) (design :doc DesignDocPath)) -> Execution
    "Execute the injected design document in the current repository, a git worktree on its feature branch. Read AGENTS.md first and follow it.\n\nTask:\n{task}\n\nRules. Follow the document's implementation handoff in order, then its verification section. Run every verification command and treat its output as the evidence; do not claim a check you did not run. Never disable, weaken or delete a test to make it pass. If a step cannot be done as planned, do the nearest thing that keeps the design's contracts and record it in `left_undone`. Keep modules under 500 lines. Commit incrementally with `git add <paths>` and `git commit -- <paths>`; commit messages describe the change and carry no assistant attribution or co-author trailer.\n\nReport `summary`: what now exists. `commits`: each commit hash with one line. `checks_run`: each command you ran with its result. `left_undone`: anything the design asked for that is not done, with the reason; may be empty.")

  (defworkflow run
    ((task String)
     (planner_model String :default "claude-fable-5-1")
     (reviewer_model String :default "gpt-6.1-sol"))
    -> Execution
    (let* ((draft (provider-result providers.claude :model planner_model :effort "high" :timeout-sec 3600
                    :prompt (draft-design :task task)))
           (feedback (provider-result providers.codex :model reviewer_model :effort "high" :timeout-sec 3600
                       :prompt (review-design :task task :design draft.doc)))
           (revised (provider-result providers.claude :model planner_model :effort "high" :timeout-sec 3600
                      :prompt (revise-design :task task :design draft.doc :draft_path draft.doc
                                             :blocking feedback.blocking :notes feedback.notes))))
      (provider-result providers.codex :model reviewer_model :effort "high" :timeout-sec 14400
        :prompt (execute-design :task task :design revised.doc))))
)
