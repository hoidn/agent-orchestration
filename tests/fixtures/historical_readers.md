# Historical reader fixtures

`historical_judgment_contract.json` and `historical_prompt_identity.json` were
captured with the actual flat compiler/runtime at commit `23eb9c97`, using the
original `_fixture` from `test_workflow_judgment_result_contracts.py` and
`_actual_v2_schema_record_and_manager` from
`test_workflow_lisp_prompt_identity_runtime.py`, respectively.

They retain only the data consumed by current historical readers. No executable
backend or fixture compiler is included. `@WORKSPACE@` replaces the temporary
capture root; tests rebase it, update the surface digest or attempt scope seal,
and validate through the ordinary readers. The original sources remain in git
at that commit. These fixtures prove reading and rejection behavior, not that
the current package can create or execute a flat program.
