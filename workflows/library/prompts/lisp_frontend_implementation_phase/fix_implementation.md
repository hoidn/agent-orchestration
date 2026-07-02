Fix the Lisp frontend implementation according to the review findings while
preserving the approved full-design plan scope and MVP-design constraints.

Update the execution report at the consumed canonical target path when possible,
or keep the currently published execution-report path valid if the target was
not used in the original implementation pass. Leave the check commands runnable.

Report a blocker instead of a fix only when a finding cannot be satisfied
because the approved binding surface is absent, contradictory, or would
require changing the approved contract.
