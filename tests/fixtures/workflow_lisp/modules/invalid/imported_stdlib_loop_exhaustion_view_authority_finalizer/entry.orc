(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry)
  (import std_drain_exhaustion
    :only (BlockerClass
           PhaseCtx
           PhaseStateBundle
           ResumeStateValue
           ChecksResult
           WorkReport
           StateExisting
           DrainLoopTerminal
           DrainTerminalResult
           emit-run-drain-like))
  (export run-drain-like)
  (emit-run-drain-like run-drain-like))
