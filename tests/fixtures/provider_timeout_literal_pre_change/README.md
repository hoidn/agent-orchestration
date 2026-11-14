Captured with package 9bb55dda (main before a provider timeout could be a name), in a scratch workspace with a
scratch `HOME`: both steps have the literal `:timeout-sec 60`; step `one` committed, step `two` failed
(`SHIM_FAIL_CALL=2`); must never be regenerated.
