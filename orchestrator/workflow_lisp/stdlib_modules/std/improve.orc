(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule std/improve)
  (export Decision Improvement improve)
  ; Contract: docs/design/workflow_lisp_composition_first.md sections 3 and 4.
  ; Both hook results are bound with `let*` before use, because the frontend
  ; does not yet lower an effectful hook call written directly as a `match`
  ; scrutinee or a `loop-state :like` field (WCC elaboration and pure projection).
  (defunion Decision :forall (F B)
    (APPROVE (evidence F))
    (REVISE (feedback F))
    (BLOCKED (reason B)))
  (defunion Improvement :forall (S F B)
    (APPROVED (value S) (evidence F))
    (BLOCKED (value S) (reason B))
    (EXHAUSTED (value S)))
  (defproc improve
    :forall (S I F B)
    ((initial S)
     (inputs I)
     (review ProcRef[(S I) -> Decision[F B]])
     (revise ProcRef[(S I F) -> S])
     (limit Int))
    :where ((S is-record))
    -> Improvement[S F B]
    :effects ()
    :lowering inline
    (loop/recur :max limit
      :state (loop-state (current S initial))
      :on-exhausted (variant Improvement[S F B] EXHAUSTED :value state.current)
      (fn (state)
        (let* ((decision (review state.current inputs)))
          (match decision
            ((APPROVE a)
             (done (variant Improvement[S F B] APPROVED :value state.current :evidence a.evidence)))
            ((BLOCKED b)
             (done (variant Improvement[S F B] BLOCKED :value state.current :reason b.reason)))
            ((REVISE r)
             (let* ((next (revise state.current inputs r.feedback)))
               (continue (loop-state :like state :current next))))))))))
