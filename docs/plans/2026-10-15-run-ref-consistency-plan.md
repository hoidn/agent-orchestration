# Run-ref confinement documentation consistency pass

## Scope

Reconcile the run-ref confinement delivery integrated in `fa17d214` with current
documentation. The reader must be able to discover and use the accepted command,
recovery and export surface, distinguish the private provider implementation from
public provider admission, and understand that existing native login needs no API
key. This pass changes documentation only; it does not qualify providers, change
policy, or complete implementation Tasks 10–13.

## Authority and evidence

- Normative owners: `specs/dsl.md`, `specs/security.md`, `specs/state.md`,
  `specs/io.md`, `specs/providers.md`, `specs/cli.md`, `specs/observability.md`
  and `specs/versioning.md`.
- Durable design: `docs/design/workflow_lisp_run_ref_expression_environments.md`
  and the applicable amendments in
  `docs/design/workflow_lisp_evaluated_execution.md`.
- Delivery and qualification owner:
  `docs/plans/2026-10-14-run-ref-expression-environments-plan.md` and the
  committed feasibility report. Historical results remain unchanged.
- Discoverability: `docs/index.md`, `docs/capability_status_matrix.md`,
  `docs/design/README.md`, the Workflow Lisp drafting guide, and relevant linked
  catalogs or readiness entries.
- Implementation and existing command-only integration tests establish the
  executable syntax and prerequisites. The previous merge's broad and sandbox
  results remain evidence for unchanged runtime code, not documentation coverage.

## Execution

1. Trace these entry points and their relevant dependents; inventory stale
   admission/status claims, API-key prerequisites, missing usage guidance and
   references whose source symbols or anchors have moved.
2. Revise the owning documentation and dependent routes narrowly. Separate
   current command admission from the provider target contract and pending real
   qualification. Preserve genuine confinement gates, Agent exclusions and
   explicitly historical evidence.
3. Have a distinct reviewer check contract agreement and coverage. Correct all
   known contradictions within this scope; report unrelated documentation gaps.
4. Validate local links/anchors, documented commands against CLI/tests, any
   touched machine-readable routing, and the complete task diff. Reuse runtime
   test evidence unless an example or behavioral claim requires a focused check.
5. Integrate only this pass's changes while preserving unrelated local work and
   record the final checks and coverage limits.

## Maintenance cost

Command support and provider qualification remain separate availability claims;
future provider delivery must update the status routes without weakening the
durable profile contract. Prefer one owning explanation and links to it over
copies of the same rules.

## Result

Completed the scoped pass across 19 maintained documents and this plan. Current
contracts and discovery routes distinguish public command-only admission,
accepted private provider implementation, and pending real/provider qualification.
The drafting guide now covers local OCI provisioning and the public command
lifecycle. Contract details and references were checked against their current
implementation owners; historical results and compatibility anchors were kept.

Independent documentation review found no remaining blocking contradictions in
the traced scope. The trace covered the hub, capability matrix, design catalog,
owning specs/designs, active implementation plan, drafting/library guides,
acceptance index and test guidance. There is no run-ref entry in the readiness
registry requiring an eligibility change. This was not a repository-wide audit.

Validation checked local targets and heading/explicit-HTML anchors in all 20
pages. The literal guide's OCI import, compile, run, parent completed-resume and
report succeeded in the real sandbox using the existing local image fixture;
the reported scalar matched the producer and no provider was invoked. Four
existing native-binding/checkpoint checks and the existing seccomp byte-equality
check passed. Runtime code, workflow files and machine-readable routing were
unchanged, so the prior broad runtime evidence was reused rather than rerun.

The complete provider example, real native authentication/TLS qualification and
implementation Tasks 11–13 remain pending. No new account or API key is required
for the selected native-login route.
