(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule implement_check_diagnose_repair)
  (import common :only (Change CheckReport Outcome))
  (export run)

  ;; The coder implements; dev-check runs the agent-visible checks once; on a
  ;; failing report the reviewer diagnoses and the coder repairs once.

  (defrecord Diagnosis (findings List[String]))

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nPreserve the evaluation inputs byte-for-byte: dev-check.json; every existing file named by its argv; pytest.ini, pyproject.toml, setup.cfg, tox.ini, conftest.py and tests/conftest.py, including other existing conftest.py files. Do not create any of these configuration or conftest files when absent. Add new tests in other files.\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.")

  (defprompt diagnose-prompt
    (:fills (intent :text) (repo :text) (account :text) (failing :value List[String]) (excerpt :text))
    -> Diagnosis
    "The development checks fail on the uncommitted changes in the git repository at {repo}. Read the code and diagnose why; change nothing.\nIntended change: {intent}\nThe author's account of the change: {account}\nFailing checks: {failing}\nCheck output excerpt:\n{excerpt}\n\nReport `findings`: each root cause, naming the file and the behaviour that goes wrong.")

  (defprompt repair-prompt
    (:fills (task :text) (repo :text) (findings :value List[String]))
    -> Change
    "Work in the git repository at {repo} and nowhere else. The development checks fail on your change for the task below. Fix the root causes the diagnosis names; replace code rather than adding a second mechanism beside the first.\n\nTask: {task}\n\nDiagnosis:\n{findings}\n\nPreserve the evaluation inputs byte-for-byte: dev-check.json; every existing file named by its argv; pytest.ini, pyproject.toml, setup.cfg, tox.ini, conftest.py and tests/conftest.py, including other existing conftest.py files. Do not create any of these configuration or conftest files when absent. Add new tests in other files.\n\nReport two things. `summary`: one sentence. `account`: the state of the whole change now, what you changed and why, and what you did not cover.")

  (defworkflow run
    ((task String)
     (intent String)
     (repo String)
     (context String)
     (model String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model "gpt-5.6-luna" :effort "high" :timeout-sec 14400))
           (report (command-result dev-check
                     :argv ("__PYTHON__" "__TRUSTED_CHECK__" "check" context)
                     :returns CheckReport)))
      (if report.passed
        (variant Outcome DONE :summary change.summary)
        (let* ((diagnosis (provider-result providers.reviewer
                            :prompt (diagnose-prompt :intent intent :repo repo :account change.account
                                      :failing report.failing :excerpt report.excerpt)
                            :model "gpt-5.6-luna" :effort "high" :timeout-sec 14400))
               (audit (command-result audit-diagnosis
                        :argv ("__PYTHON__" "__TRUSTED_CHECK__" "audit-diagnosis" context)
                        :returns Bool)))
          (if audit
            (let* ((repair (provider-result providers.coder
                              :prompt (repair-prompt :task task :repo repo :findings diagnosis.findings)
                              :model "gpt-5.6-luna" :effort "high" :timeout-sec 14400)))
              (variant Outcome DONE :summary repair.summary))
            (variant Outcome BLOCKED :reason "diagnosis snapshot changed")))))
))
