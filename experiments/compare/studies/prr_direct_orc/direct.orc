(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule direct)
  (import common :only (Change Outcome))
  (export run)

  ;; One coder call implements the task (ported from
  ;; experiments/compare/control/direct_task.orc).

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nPreserve the evaluation inputs byte-for-byte: dev-check.json; every existing file named by its argv; pytest.ini, pyproject.toml, setup.cfg, tox.ini, conftest.py and tests/conftest.py, including other existing conftest.py files. Do not create any of these configuration or conftest files when absent. Add new tests in other files.\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.")

  (defworkflow run
    ((task String)
     (intent String)
     (repo String)
     (context String)
     (model String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model "gpt-5.6-luna"
                     :effort "high"
                     :timeout-sec 14400)))
      (variant Outcome DONE :summary change.summary)))
)
