Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design` artifact before acting.

Draft an execution plan from the approved design.

The plan should:
- break the work into coherent tranches
- put prerequisites before dependent work
- include verification for each tranche
- call out migrations, compatibility boundaries, and explicit non-goals

For the output contract's `plan_path`, read the path recorded in that file and write the plan document to that current-checkout-relative path. Leave the `plan_path` file containing only the path.
