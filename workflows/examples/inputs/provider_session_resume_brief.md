# Provider-Session Resume Feature Brief

Design and implement first-class provider-session resume support in the workflow DSL and runtime.

Requirements:
- prefer a provider-agnostic design
- a Codex-first implementation is acceptable as the first pass
- if scalar `string` support is required for session handles, treat that as an explicit prerequisite
- make the runtime ownership of session metadata clear
- keep workflow `resume` distinct from provider-session `resume`

Review expectations:
- be willing to require internal refactoring or debt paydown before feature work if it is a real prerequisite
- do not accept a design or plan that hand-waves over runtime contracts, state ownership, or migration boundaries
