# Rubric

Intended change: programs whose `loop/recur` result is a union with a path-typed
field outside the exhausted variant must compile and behave at targets 2.29
through 2.32 exactly as at 2.28, without weakening validation and without
changing behaviour at 2.28 and earlier.

The bug as reported: at target 2.29+ such a program is rejected at compile time with
`repeat_until.on_exhausted.outputs.result__report may only override scalar repeat_until outputs`.

Rate each patch on four criteria, each 0, 1 or 2
(0 = does not hold, 1 = holds with a real concern, 2 = holds):

1. **Cause.** The root cause is fixed, not the symptom silenced.
2. **Contracts.** No existing validation or guarantee is weakened, and nothing
   changes outside the intended scope (other targets, other steps, other value kinds).
3. **Generality.** The change holds beyond the reported case.
4. **Fit.** It sits in the layer that owns the behaviour and reuses existing
   mechanisms instead of adding parallel ones.

Then one overall answer: would you merge this patch as is? yes / no.
