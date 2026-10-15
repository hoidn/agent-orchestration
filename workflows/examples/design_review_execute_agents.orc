(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.38")
  (defmodule design_review_execute_agents)
  (export run DraftDocPath DesignDocPath Draft Design Feedback Execution
          draft-design review-design revise-design execute-design)

  ;; The design lives in markdown files, not in the result JSON. The planner
  ;; drafts and names artifacts/design/<slug>.md, a reviewer from another
  ;; model family reads the draft and reports findings, the planner writes
  ;; the final docs/design/<slug>.md, and the reviewer's model executes it.
  ;; The draft is never edited after the review reads it. Each result carries
  ;; only what the program needs: a typed path, the findings, and the
  ;; execution receipt; every later prompt receives the document whole
  ;; through its :doc fill.
  ;;
  ;; Opt-in variant: the designer and the reviewer each keep one native
  ;; conversation (Agent Sessions, target 2.38), so the revise turn sees the
  ;; draft turn's context and the execute turn sees the review turn's.
  ;; Invalidating `feedback`, or any step before a committed turn, is
  ;; refused (C8). The baseline design_review_execute.orc keeps four
  ;; independent calls. Compiles at 2.38; running it requires the pending
  ;; agent-session runtime.
  ;;
  ;;   python -m orchestrator compile workflows/examples/design_review_execute_agents.orc \
  ;;     --provider-externs-file workflows/examples/inputs/design_review_execute_agents/providers.json

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
    "You are designing one feature for this repository, a git worktree of agent-orchestration. Read AGENTS.md and docs/index.md first, then the documents and code the task names.\n\nWrite the design document as a new file artifacts/design/<slug>.md, with a short slug you choose from the task, structured by docs/templates/design_template.md with the sections that do not apply deleted. It must leave no decision to the implementer: the contracts it adds or changes and the documents that own them, the modules it touches and what goes into each, what it refuses and with which diagnostic codes, and what stays out of scope. Its implementation handoff lists the ordered steps an engineer executes without further design work, each naming the files it creates or changes. Its verification section lists the exact commands that prove the work through public entries: narrow pytest selectors first, then `pytest -q -n 16 --dist=worksteal -m \"not e2e\"`, then one smoke through the public CLI. Change no other file.\n\nTask:\n{task}\n\nReturn `doc`: the path you wrote, relative to the repository root, as the result rather than as a reply.")

  (defprompt review-design (:fills (task :text) (design :doc DraftDocPath)) -> Feedback
    "Review the injected design document against the repository. Read AGENTS.md, docs/index.md, the specs and designs the document cites, and every code path it names. Change nothing.\n\nTask:\n{task}\n\nJudge five things. (1) Each decision is consistent with the governing specs and designs it cites and with the code as it is. (2) The implementation handoff is executable as written: every file, function and entry it names exists or is created by an earlier step. (3) The verification section proves behaviour through public entries and stays valid when prompt text changes. (4) Scope stays bounded to the task. (5) Nothing relies on an unproven capability without naming it as a prerequisite.\n`blocking`: defects that would make execution fail, violate a contract, or leave the task's scope; each names the section or step and the scenario that goes wrong. `notes`: improvements that do not block; may be empty.")

  (defprompt revise-design
    (:fills (task :text) (design :doc DraftDocPath) (draft_path :path DraftDocPath)
            (blocking :value List[String]) (notes :value List[String]))
    -> Design
    "Revise the injected design document with the reviewer's feedback and write the final document as a new file docs/design/<slug>.md, with the same slug as the draft {draft_path}. Leave the draft unchanged. Address every blocking finding; adopt each note or answer it under a `Review responses` heading. A finding can be wrong: where you do not adopt one, say why there. Keep everything the reviewer did not question. Change no other file.\n\nTask:\n{task}\n\nBlocking findings:\n{blocking}\nNotes:\n{notes}\n\nReturn `doc`: the path you wrote, relative to the repository root, as the result rather than as a reply.")

  (defprompt execute-design (:fills (task :text) (design :doc DesignDocPath)) -> Execution
    "Execute the injected design document in the current repository. Read AGENTS.md first and follow it.\n\nTask:\n{task}\n\nRules. Follow the document's implementation handoff in order, then its verification section. Run every verification command and treat its output as the evidence; do not claim a check you did not run. Never disable, weaken or delete a test to make it pass. If a step cannot be done as planned, do the nearest thing that keeps the design's contracts and record it in `left_undone`. Keep modules under 500 lines. Commit incrementally with `git add <paths>` and `git commit -- <paths>`; commit messages describe the change and carry no assistant attribution or co-author trailer.\n\nReport `summary`: what now exists. `commits`: each commit hash with one line. `checks_run`: each command you ran with its result. `left_undone`: anything the design asked for that is not done, with the reason; may be empty.")

  (defworkflow run
    ((task String)
     (planner_model String :default "claude-fable-5-1")
     (reviewer_model String :default "gpt-6.1-sol"))
    -> Execution
    (let* ((designer (agent providers.claude :model planner_model :effort "high"))
           (reviewer (agent providers.codex :model reviewer_model :effort "high"))
           (draft (provider-result designer :timeout-sec 3600
                    :prompt (draft-design :task task)))
           (feedback (provider-result reviewer :timeout-sec 3600
                       :prompt (review-design :task task :design draft.doc)))
           (revised (provider-result designer :timeout-sec 3600
                      :prompt (revise-design :task task :design draft.doc :draft_path draft.doc
                                             :blocking feedback.blocking :notes feedback.notes))))
      (provider-result reviewer :timeout-sec 14400
        :prompt (execute-design :task task :design revised.doc))))
)
