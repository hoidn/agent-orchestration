(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule inlined_procedure)
  (export run)

  ;; `label` is an effect-free procedure the compiler inlines into `run`; `bump` is a pure helper.

  (defrecord Note (text String))
  (defrecord Draft (topic String) (rounds Int))

  (defprompt write-note (:fills (topic :text)) -> Note
    "Write one sentence about {topic}.")

  (defun bump ((value Int)) -> Int
    (+ value 1))

  (defproc label ((topic String)) -> Draft
    (record Draft :topic topic :rounds 0))

  (defworkflow run ((topic String)) -> Note
    (let* ((draft (label topic))
           (rounds (bump draft.rounds)))
      (provider-result providers.writer :prompt (write-note :topic draft.topic)))))
