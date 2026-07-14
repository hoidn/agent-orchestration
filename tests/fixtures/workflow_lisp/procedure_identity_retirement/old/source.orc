; FICTIONAL TEST-ONLY PROCEDURE RETIREMENT SOURCE — NEVER COPY INTO PILOT EVIDENCE.
(module fictional.retirement
  (export retained-stack)
  (defworkflow internal-phase ((input String)) -> String
    (return input))
  (defworkflow retained-stack ((input String)) -> String
    (return (call internal-phase input))))
