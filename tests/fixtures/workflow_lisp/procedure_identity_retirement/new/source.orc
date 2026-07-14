; FICTIONAL TEST-ONLY PROCEDURE RETIREMENT SOURCE — NEVER COPY INTO PILOT EVIDENCE.
(module fictional.retirement
  (export retained-stack)
  (defproc internal-phase ((input String)) -> String
    (:lowering inline)
    (return input))
  (defworkflow retained-stack ((input String)) -> String
    (return (proc-call internal-phase input))))
