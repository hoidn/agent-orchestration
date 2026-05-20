Fix the Lisp frontend implementation according to the review findings while
preserving the approved plan scope.

Update the execution report at the consumed canonical target path when possible,
or keep the currently published execution-report path valid if the target was
not used in the original implementation pass. Leave the check commands runnable.
