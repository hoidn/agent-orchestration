(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule approval)
  (import std/host :only (HostReply))
  (export recover Evidence)

  (defpath Evidence :kind relpath :under "artifacts" :must-exist true)
  (defpath Guide :kind relpath :under "docs" :must-exist true)
  (defenum Cause BROKEN_RECORD MISSING_METADATA)
  (defenum Approval APPROVED DENIED)
  (defrecord Diagnosis (cause Cause) (summary String))
  (defrecord Verification (cause Cause) (summary String) (evidence Evidence))
  (defrecord Outcome (status String) (reason String) (cause Cause) (diagnosis String))

  (defprompt diagnose-question (:fills (problem :text)) -> Diagnosis
    "Diagnose this recovery input: {problem}")
  (defprompt approval-question
    (:fills (cause :value Cause) (summary :text) (guide :doc Guide)) -> Approval
    "A local verification command checked cause {cause}: {summary}")

  (defproc approval ((cause Cause) (summary String) (evidence Evidence) (guide Guide)) -> HostReply[Approval]
    (request-input (approval-question :cause cause :summary summary :guide guide)
      :timeout-sec 3600
      :show (evidence)))

  (defworkflow recover ((problem String) (report Evidence) (guide Guide)) -> Outcome
    (let* ((diagnosis (provider-result providers.diagnose
                       :model "local-stub" :effort "low"
                       :prompt (diagnose-question :problem problem)))
           (checked (command-result verify
                      :argv ("python" "action.py" "verify" diagnosis.cause diagnosis.summary report)
                      :returns Verification))
           (reply (approval checked.cause checked.summary checked.evidence guide)))
      (match reply
        ((ANSWERED answer)
          (if (= answer.value Approval.APPROVED)
            (command-result action
              :argv ("python" "action.py" "repair" checked.cause checked.summary)
              :returns Outcome)
            (command-result action
              :argv ("python" "action.py" "escalate" "denied" checked.cause checked.summary)
              :returns Outcome)))
        ((CANCELLED _)
          (command-result action
            :argv ("python" "action.py" "escalate" "cancelled" checked.cause checked.summary)
            :returns Outcome))
        ((EXPIRED _)
          (command-result action
            :argv ("python" "action.py" "escalate" "expired" checked.cause checked.summary)
            :returns Outcome)))))
)
