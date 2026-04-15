Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design` artifact before acting.

Draft an execution plan from the approved design.

The plan should:
- break the work into coherent tranches
- put prerequisites before dependent work
- include verification for each tranche
- call out migrations, compatibility boundaries, and explicit non-goals
- include discoverability or documentation update steps when the work changes behavioral specs, public or internal APIs, architectural conventions, development processes, test conventions, data or oracle contracts, creates important docs, or changes other durable project knowledge; when qualifying docs are created or materially changed, include a task for updating the relevant documentation index such as `docs/index.md` when present; avoid documentation churn for purely local implementation details
- when the design identifies generated artifacts, helper scripts, validators, or curated data, plan the concrete file targets, generation commands, validation checks, and tests needed to make the work executable

For the output contract's `plan_path`, read the path recorded in that file and write the plan document to that current-checkout-relative path. Leave the `plan_path` file containing only the path.
