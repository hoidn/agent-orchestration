(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule shared_procedure)
  (export run)

  ;; One non-generic procedure with a provider call, called from two workflows.
  ;; `unused` is never reached from `run`, so the build prepares no body for it.

  (defrecord Note (text String))

  (defprompt write-note (:fills (topic :text)) -> Note
    "Write one sentence about {topic}.")

  (defproc consult ((topic String)) -> Note
    (provider-result providers.writer :prompt (write-note :topic topic)))

  (defworkflow left ((topic String)) -> Note
    (consult topic))

  (defworkflow right ((topic String)) -> Note
    (consult "fixed topic"))

  (defworkflow run ((topic String)) -> Note
    (let* ((first (call left :topic topic))
           (second (call right :topic topic)))
      (if (= first.text "")
          second
          first)))

  (defworkflow unused ((topic String)) -> Note
    (provider-result providers.writer :prompt (write-note :topic topic))))
