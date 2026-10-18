(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule shadowing)
  (export run)

  ;; Nested `let*` forms rebind `x`; each provider call sees the innermost `x`.

  (defrecord Note (text String))

  (defprompt write-note (:fills (topic :text)) -> Note
    "Write one sentence about {topic}.")

  (defworkflow run ((topic String)) -> Note
    (let* ((x topic))
      (let* ((x (provider-result providers.writer :prompt (write-note :topic x))))
        (provider-result providers.writer :prompt (write-note :topic x.text))))))
