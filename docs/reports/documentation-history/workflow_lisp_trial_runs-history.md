# Workflow Lisp Trial Runs: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_trial_runs.md](../../design/workflow_lisp_trial_runs.md).

## E1 — Workspace-Pinned Child Runs

One new execution form (conceptual syntax):

```lisp
(run-ref
  :source (:repo <locator> :commit <sha>)      ; exact revision, resolved
  :program (:bundle <workflow-name>)           ; mode 1: from caller's bundle
  ;; or   (:path "experiments/candidate.orc" :entry <workflow-name>) ; mode 2
  :inputs (:task task)                         ; explicit typed data only
  :policy <trial-policy-ref>)
```

### Semantics

1. **Materialize** the repository at the exact commit into a run-owned
   directory outside the parent workspace. One content-addressed local mirror
   per `(locator, sha)`; per-arm workspaces materialize from that verified
   snapshot without further network access (local object sharing /
   reflink-or-copy is implementation guidance, not contract).
2. **Resolve the program** from the declared locus:
   - **Mode 1 (bundle):** the child program is a named workflow already in
     the caller's compiled bundle. The clone supplies files and working
     directory only. This is the default experiment mode: arms are authored
     and certified together with the controller.
   - **Mode 2 (clone path):** the child program is `.orc` source at a
     clone-relative path at that pinned commit, compiled from scratch by the
     ordinary full pipeline. This is the self-evolution mode: a candidate
     cannot execute until its source is committed, so git itself is the
     admission ledger — provider-proposed text becomes executable only by
     being materialized as a commit, passing the full compiler, and satisfying
     the execution-environment boundary below. Compilation is necessary but
     never sufficient authority to run a generated candidate.
3. **Execute as an ordinary child run.** The child is launched as a standard
   top-level orchestrator run (subprocess) with WORKSPACE = the arm
   directory and clone-local run state (`.orchestrate/` inside the arm
   workspace). No nested state managers and no new execution semantics are
   introduced. Parent state has one writer: the parent coordinator records the
   trial ledger entry and child-run reference; child state is written only by
   the ordinary child-run writer under its own root. Each root holds the
   landed fail-fast run-lifetime writer lock; a second writer is rejected
   rather than coordinated after the fact. A failed child compiler process is
   surfaced as structured diagnostics in the arm outcome. This operational
   failure boundary is not an OS-security boundary.
4. **Return typed evidence.** Declared child outputs (typed, validated at the
   child's own boundary) plus the normalized `WorkspaceDelta` (below) plus
   run accounting.

There is **no quoting, no code value, no closure conversion, and no runtime
evaluation of expression text**. "Subexpression granularity" is achieved by
authoring a small named wrapper workflow around the expression (mode 1 in the
controller's own source; mode 2 in the trial ref). An inline-expression sugar
(compiler-extracted child entrypoints with checked captures) is a possible
later ergonomic layer; it is explicitly out of scope here and shelved with an
evidence trigger (see Deliberately Not Selected).

### Typing and effect classification

`run-ref` is a new step-level execution form, mutually exclusive with every
other execution form, and a durable effect boundary: it participates in
checkpoints, at-least-once discard/rerun, and committed-result reuse like a
provider step. It is not a `call` variant — `call` is inline, same-run,
same-workspace; `run-ref` is a subprocess child run with its own state root
and workspace.

Result typing differs by program locus:

- **Mode 1 (bundle):** the named workflow's v2.1 signature is present in the
  caller's compiled bundle, so the child result type is statically known and
  checked at caller compile time. `run-ref` types as a record of that result
  plus `WorkspaceDelta` plus run accounting.
- **Mode 2 (clone path):** the child program is compiled at runtime by the
  child process; the caller cannot know its signature statically. The child
  result therefore defaults to the exact opaque transportable `Value` type
  (target 2.19). An optional `:returns <Type>` refinement is a caller claim,
  verified at runtime against the child's own compiled signature and failing
  closed on mismatch (`trial_program_signature_mismatch`). No structural
  inference across the boundary; the child compiler's output is the sole
  signature authority.

`trial` (E2) evaluates to the authored-order list of arm outcomes plus a
verdict artifact reference, with the arm element type expressed in the
language's existing tagged-union discipline:

```text
ArmOutcome = Completed { arm_id, rep, value, evidence: TrialEvidence }
           | Failed    { arm_id, rep, failure: TrialFailure, evidence: PartialTrialEvidence }
```

`value` is typed per the arm's `run-ref` mode above; failures are values and
never imply sibling cancellation.

### Repository identity

A trial source is not "URL + branch". The recorded source identity is:

```text
RepositoryRevisionId = hash(
  normalized locator,
  resolved commit SHA,
  materializer version,
  submodule policy,        ; v1: fail closed if .gitmodules present
  LFS policy,              ; v1: fail closed if LFS attributes present
  setup identity           ; see below
)
```

- v1 refuses submodules and LFS rather than normalizing them
  (`trial_source_submodules_unsupported`, `trial_source_lfs_unsupported`);
  lifting either is a later amendment with its own identity rules.
- **Setup steps** (dependency installation etc.) are the largest real-world
  confound for numerical target repos. v1: a trial declares an explicit
  ordered setup command list; its literal argv + declared env form the setup
  identity; setup runs once per arm workspace before the child run; setup
  output is evidence, not part of the delta. Network nondeterminism of setup
  is acknowledged and recorded, not solved, in v1.
- The materialized workspace begins from the verified committed tree, so
  unrelated untracked files from the source checkout do not enter trial
  identity. Environment, credentials, network access, global configuration,
  and host-visible paths are not isolated by cloning. The clone is an exact
  workspace/output boundary and a disposable directory, never a sandbox.

### Workspace delta

```text
WorkspaceDelta = {
  base: RepositoryRevisionId,
  changed_files, deleted_files, untracked_files,   ; from git status vs base
  normalized_diff,                                  ; bounded, deterministic
  declared_artifacts                                ; child-declared outputs
}
```

Candidate-generated commits inside the arm are optional artifacts, never
trial identity.

### Failure and resume semantics

Trial execution uses the landed ML at-least-once and single-writer run
contract, not the retired provider-interruption quarantine. An interrupted or
crashed incomplete arm is a failed attempt: retain whatever non-authoritative
incident evidence is already available, discard the arm workspace, allocate a
fresh ordinal, re-materialize, and re-run through ordinary control flow. A
committed completed arm result is validated and reused on parent resume.

This does **not** change the lean pilot's separate, load-bearing rule: pilot
attempts are never resumed, recovered, deleted, or rerun under the same ID,
and interrupted pilot blocks remain outcomes. The trial platform may
reproduce the pilot protocol only in new platform-owned runs after admission;
it may not reinterpret a pilot evidence root as a platform run.

### Refusal families (structural only)

The v1 refusal registry is closed; current codes and envelopes are normative
in the [DSL spec](../../../specs/dsl.md). The original design required each
envelope to carry `code`, `rejected_value`, and optional stable secondary
causes. Human prose is a view and is never routing authority.

| Boundary | Stable refusal codes |
| --- | --- |
| Source/materialization | `trial_source_unresolvable`, `trial_source_submodules_unsupported`, `trial_source_lfs_unsupported`, `trial_source_revision_digest_mismatch`, `trial_materialization_digest_mismatch`, `trial_workspace_preexisting`, `trial_setup_failed` |
| Program/signature/environment | `trial_program_missing`, `trial_program_compile_rejected` (with the child compiler's stable diagnostics), `trial_program_signature_mismatch`, `trial_candidate_environment_not_admissible` |
| Evaluation value | `trial_evaluation_contract_not_pure`, `trial_evaluation_contract_invalid`, `trial_evaluation_provider_unresolved`, `trial_evaluation_rubric_unresolved` |
| Budget/concurrency | `trial_reps_invalid`, `trial_concurrency_invalid`, `trial_budget_invalid` |
| Packet/blinding | `trial_packet_policy_invalid`, `trial_packet_limit_invalid`, `trial_blinding_policy_invalid`, `trial_packet_citation_invalid` |

`trial_candidate_environment_not_admissible` names the rejected effect/policy
facts and the missing admissible environment; it does not introduce an
isolation mechanism. Runtime arm failures after admission are routed as
`ArmOutcome.Failed`, with the originating stable refusal or runtime failure
code retained as evidence rather than collapsed into a generic error.

## E2 — Trial Form: Concurrent Arms Into Existing Adjudication

One new step-level form (conceptual):

```lisp
(trial
  :arms ((:id a :run-ref <...>) (:id b :run-ref <...>) ...)
  :reps <n>                       ; per arm; candidate id = (arm, rep)
  :max-concurrency <k>
  :evaluation <frozen evaluation contract ref>
  :budget <provider budget ref>)
```

### Reuse map (`adjudicated_provider`, originating at target 2.11)

| Layer | Disposition |
| --- | --- |
| Concurrent candidate fan-out, per-candidate private workspace | **Generalized:** candidate := `run-ref` child run instead of one provider invocation; workspace := pinned clone instead of parent-baseline copy. "Private" means separate run-owned files, not sandboxed host authority. |
| Evaluator provider + strict-JSON scoring + evidence-packet discipline (`specs/providers.md` evaluator contract) | **Reused** behind the blinding boundary below; packets gain a `WorkspaceDelta` member |
| Score ledgers (stable candidate/score run keys, owner tuples), resume reconciliation | **Reused** with trial-scoped key extension `(arm, rep)` |
| `evidence_confidentiality: same_trust_boundary` attestation | **Reused** unchanged |
| Promotion transaction | **Not reused for source.** The target-2.11 contract already restricts promotion to declared artifacts, "not arbitrary source-edit patch promotion" (`specs/versioning.md`). A trial's terminal output is a verdict artifact + optional proposal patch; canonical source changes only through review |
| Candidate prompt-composition overrides | **Not applicable** (arms are whole runs) |

Semantics adopted from the external memo, binding here:

- failures are values (`ArmOutcome = Completed | Failed`), never implicit
  sibling cancellation; collect-all is the default failure policy;
- authored arm order, not completion order, determines evaluator input order;
- per-arm ledgers: cost, tokens, elapsed time, provider identity, failures;
- evaluation begins only from a frozen set of admitted arm evidence;
- explicit cancellation/timeout policy per arm and per trial;
- a mandatory concurrency cap at trial and provider levels.

### Persistence and replay contract

Trial persistence is subordinate to the accepted M2 pure-result replay
design. Durable state records only facts needed to validate or continue
effects and public boundaries: trial identity, frozen evaluation identity,
arm attempt/result identity, child-run reference, terminal outcome, and
evidence/artifact lineage. Pure projections derived from those validated
facts use M2's value-free completion shells and transient replay overlay; the
trial design does not persist a second derived-value cache.

No effect-identity memo key, memo-first execution path, or cross-run result
cache is selected here. Those are explicitly outside accepted M2 component
(a). Any future memo key requires separate M2(b)/M3b selection and must consume
the landed Q3 role-separated identity rather than invent a trial-local
identity. Ordinary committed-result reuse remains valid within a run after the
existing root/callee, checkpoint, input, and result validations pass. Before
E1/E2 implementation planning freezes an exact state shape, a fixture must
prove that clean and crash/resume executions fit this boundary without
persisting derived pure values or re-spending a committed effect.

### Evaluation contract

The `trial` form's `:evaluation` operand is an ordinary structural record
value, not a new definition form and not a mandatory `TrialEvaluation` nominal
taxonomy. Authors may construct a structurally typed record directly or begin
with implemented transportable `Value` (target 2.19+) and narrow at the trial
boundary. The compiler checks only the fields the mechanism requires; authors
may define a local nominal wrapper if its name carries a useful project
contract, but the platform never requires one. Conceptual shape:

```lisp
(proc coding-trial-eval ()
  (record
    ;; authority levels 1-3: deterministic checks, run in the arm
    ;; workspace after its child run terminates
    :checks (list
      (record :id "hidden-tests"
              :command (list "python" "-m" "pytest" "-q" "tests/hidden")
              :authority "correctness" :required true)
      (record :id "perf-floor"
              :command (list "python" "bench/check_regression.py")
              :authority "invariant" :required false))
    ;; level 6; the evaluator contract originating at target 2.11 is reused:
    ;; provider alias and
    ;; rubric relpath are strings resolved and validated at the consuming
    ;; trial form, like asset_file and the target-2.11 evaluator provider
    :judgment (record
      :provider "scorer"
      :rubric-asset "rubrics/port_quality.md"
      :evidence-confidentiality "same_trust_boundary"
      :evidence-limits (record :max-item-bytes 65536
                               :max-packet-bytes 262144))
    ;; blinding boundary instantiation: include-list plus metric-relevant
    ;; reveals only
    :observation (record
      :include (list "task_spec" "workspace_delta" "check_results"
                     "declared_artifacts" "failure_evidence")
      :diff-cap-bytes 262144
      :reveal-provider-identity false)
    :aggregation (record
      :mode "independent_rubric"
      :rep-combine "median"
      :tie "candidate_order")
    :success-rule (record
      :superior (record :min-abs-improvement 0.10
                        :max-cost-ratio 1.5)
      :non-inferior (record :min-cost-reduction 0.20)
      :count-failures-as-outcomes true)))
```

The `:evaluation` operand must discharge the compiler's closed structural
constraint as a compile-time pure expression: the compiler embeds the resolved
record value in the IR, and a runtime-computed contract is rejected as
`trial_evaluation_contract_not_pure` (the referee may not be data-dependent).
The `trial` form performs deep structural validation — provider alias
resolution, rubric asset resolution, `max_packet_bytes >= max_item_bytes`,
and closed authority/aggregation value constraints — reusing the evaluator
contract that originated at target 2.11 without a dedicated definition form.

Evaluation is deliberately declarative data interpreted by trial machinery,
never an authored procedure invoked with arm evidence: blinding exclusions
and the authority hierarchy are enforceable only when the runtime owns packet
construction, deterministic check execution, schema/blinding/budget
validation, output-contract rendering, and level ordering; a behavioral referee could encode
data-dependent scoring no reviewer would spot; and the evaluator ledger,
packet-limit, and resume-reconciliation machinery is reusable only when
driven from config. Authored behavior appears exactly at the leaves — check
commands and the judgment provider call — executed under runtime
supervision with results captured as data.

- Checks are commands executed in the arm workspace after its child run
  terminates; their results enter both the packet and the authority
  hierarchy above any judgment score.
- The judgment member maps onto the existing evaluator contract that
  originated at target 2.11
  unchanged (provider, rubric source, `same_trust_boundary`, evidence
  limits).
- The observation member authors only the include-list and metric-relevant
  reveals;
  the blinding exclusions below are fixed by this design and are not
  authorable surface.
- One contract judges all arms: per-arm evaluation overrides are
  deliberately unsupported (asymmetric evaluation is a confound and an
  unblinding vector).
- The adaptive/validation/holdout partition is deliberately absent: the
  contract must not know which split a run serves (invariant 5); partition
  membership is controller-owned.
- Freezing is mechanical, not procedural: the contract compiles into the
  bundle and its digest is part of trial identity in the ledger. A
  post-hoc rubric or threshold edit produces a different trial, not an
  updated one.

### Blinding boundary

The adjudicator must be unable to identify treatments.

- Arm IDs entering evaluation are opaque; the treatment map is sealed in the
  trial ledger and joined only after scoring.
- Packets **exclude**: treatment labels, arm source text and filenames,
  candidate lineage/proposer identity, provider/model identity (unless the
  metric explicitly requires it), run logs and `.orchestrate` sidecars,
  completion order, prior adaptive scores.
- Packets **include**: task specification, validated result, `WorkspaceDelta`
  (normalized diff + artifacts), deterministic check results permitted by the
  protocol, and explicit failure evidence where failure is itself an outcome.
- The hardened blinded-review citation contract applies: evaluator citations
  must resolve inside the blinded packet only.

The known tension — lineage wants every artifact origin-stamped, blinding
wants the evaluator ignorant — is resolved exactly there: full lineage in the
sealed trial ledger, normalized packets to the evaluator, unsealed join after
verdict.

### Evaluation authority hierarchy (frozen per experiment, in this order)

1. trial validity (materialization, setup, policy attestation);
2. deterministic correctness checks (visible + hidden tests);
3. task-specific invariants;
4. operational completion;
5. cost and elapsed time;
6. blinded LLM/human judgment for soft dimensions;
7. candidate complexity.

LLM adjudication is never the sole correctness authority in proving
experiments. For >2 arms, no order-dependent single-elimination brackets:
independent scoring against a frozen rubric is the default (it composes with
reps and yields distributions); balanced randomized pairwise comparison with
order reversal is the alternative. The aggregation rule and tie handling are
frozen before evaluation.

### Comparison contract and preregistration

Arms must be matched on: task input, repository revision, provider/model
eligibility, tool permissions, context availability, and budget policy —
except where the treatment definition explicitly varies call count, in which
case results report both absolute quality and quality under a matched-budget
frontier. Default preregistered success rule (tunable per experiment
manifest, frozen before the run): materially better means ≥10 percentage
points absolute success improvement with an uncertainty interval excluding
zero at ≤1.5× provider cost, **or** statistically non-inferior success at
≥20% lower cost. Timeouts, malformed candidates, and failed runs count as
outcomes. Holdout floor: ≥30 independent cases, subject to a power
calculation. Task corpora are partitioned before adaptive work: adaptive set
/ validation set / sealed holdout, with the holdout opened once after
candidate generation, evaluator, and decision rule are frozen. The trial
ledger records which partition every run served.

## E3 — Evolution Methodology (No New Language Surface)

The first search controller lives **outside** Workflow Lisp (a small external
program consuming the trial platform's public surfaces), mirroring the lean
pilot's external-controller architecture. A `.orc`-native controller is a
later, separate experiment on the same public contracts.

The loop, entirely on existing rails: propose (provider writes a patch) →
commit to a trial ref (git = admission ledger + variant registry,
content-addressed and diffable) → compile gate (ordinary full compiler as the
free static fitness filter; rejections feed back as structured diagnostics at
zero provider cost) → trial via E2 (base vs mutants, reps, blinded scoring) →
verdict artifact → **promotion proposal** (patch + evidence manifest +
holdout result). The owner merges; nothing merges itself. Verdicts are
evidence, never authority.

Binding methodology:

- **Gene bounds as diff policy.** Admitted mutation surfaces are enforced as
  diff-span checks in the controller against declared loci — v1 admits:
  prompt text inside selected declarations (slots and result contracts
  preserved); literal thresholds/closed pure expressions of unchanged type;
  bounded compiler-legal topology edits from a fixed template vocabulary
  (add/remove a review or repair phase, bounded retry counts); provider
  policy selection from a frozen allowlist. Prompt, topology, provider, and
  context remain **separate genes** even when one proposal changes several —
  so a "prompt improvement" cannot silently acquire more compute or
  authority, and ablations stay possible. No `SubjectManifest`/rewrite
  certification substrate is built for this; a diff-span policy check plus
  the full compiler is sufficient for these bounds.
- **Mandatory baselines.** Every adaptive-search claim is tested against:
  fixed hand-authored workflow; random/enumerative candidate search under
  equal budget (distinguishes optimization from merely trying more
  candidates); prompt-only and topology-only ablations before any joint
  search claim.
- **Frozen kernel.** Candidates and the controller cannot modify: compiler
  and lowering pipeline, admission/diff policy, evaluator and rubric, corpus
  partition, materializer, setup commands/environment, admissible execution
  environment, budget accounting, or promotion rules. The controller never
  imports candidate code into its own process.

## Program-Search Boundary Compliance

Per `workflow_lisp_program_search_boundaries.md` ("satisfy or amend first,
explicitly"):

| Invariant | Disposition |
| --- | --- |
| 1 — Immutable generation boundaries | Satisfied by construction: running bundles never modified; every candidate passes the ordinary full compiler (mode 2 compiles from scratch; mode 1 was certified with the controller); execution is a new registered child run; promotion is a reviewable patch. Generation boundary = commit boundary. |
| 2 — Provider output is untrusted data | Satisfied structurally: mode 2 executes only committed source; a proposal becomes behavior only via commit + full compile + the admissible-environment gate + child run. No candidate text is ever evaluated from memory. |
| 3 — Neutral substrate vs feature | Satisfied: `run-ref`/`trial` know arms, reps, budgets, evidence, ledgers — no genome/population/fitness/selection vocabulary. All optimizer concepts live in the external controller (E3). |
| 4 — Whole-candidate evidence is fitness authority | Satisfied: arms are whole child runs; scoring binds to whole-arm evidence; any finer-grained signal is diagnostic only. |
| 5 — Evidence separation | Satisfied procedurally: adaptive/validation/sealed-holdout partition frozen before adaptive work; partition membership recorded per run in the trial ledger; holdout opened once. |
| 6 — Honest security boundary | Satisfied by exclusion: a clone is only an output boundary. Generated candidates run only in deterministic effect-free harnesses, or use text-only/no-tool, mock/replay, or genuinely sandboxed provider calls. |
| 7 — Typed-operation parity without kind erasure | Satisfied: `run-ref` is a distinct durable child-run boundary with data-only arguments (locator, sha, name/path, typed inputs). No `Code<T>`, no runtime closures, no expression shipping. |
| 8 — Prompt identity is role-separated | Satisfied by inheritance: arms are ordinary runs carrying the landed Q3 identity discipline unchanged. |

## Generated-Candidate Execution Environment

This design satisfies invariant 6 without amendment and without selecting
security work. A generated candidate may execute only in one of these
environments:

1. a deterministic effect-free harness;
2. provider calls that are text-only/no-tool;
3. mock or replay provider calls; or
4. a genuinely sandboxed environment whose positive isolation evidence is
   supplied by a separately accepted capability.

The compiler derives the candidate's effect summary and the trial admission
path validates it against the declared environment. An unknown effect,
tool-using provider call outside item 4, or missing positive sandbox evidence
fails closed as `trial_candidate_environment_not_admissible`. Gene bounds,
commits, full compilation, process separation, and cloned workspaces do not
substitute for this check. Owner-authored ordinary workflows outside program
search remain governed by their existing runtime contracts; this design does
not broaden or narrow them.

## Language Substrate Dependencies

The entry-proof and admission statements in this section record the original
pre-implementation assessment. E1/E2 implementation plans and the current
specs now own those contracts; these statements are not current blockers.

Named dependencies on existing tracks; this design builds none of them.

- **Compiler invocation strategy:** child compiles run inside child-run
  subprocesses so compiler failure is reported at the child-run boundary.
  This is operational fault containment, not a trust boundary. In-process
  batch compilation is a later optimization
  gated on MR-4 (compiler session state) / L3 (reentrancy), which the Q/L
  roadmap already owns.
- **Diagnostics as machine API:** E3's repair loop consumes compile
  rejections as data. Requires a stable diagnostic-code contract and a
  structured (JSON) batch validation surface. Cheap, independently useful;
  land at E1 admission.
- **Hermeticity entry proof:** trial identity requires compilation to be a
  function of the complete source/dependency set plus compiler identity, not
  an ambient path-keyed cache or undeclared environment read. This is not
  assumed from current direction. Before E1 planning, a minimal fixture must
  characterize the ordinary full compile path, prove content-addressed cache
  behavior for equal paths with changed bytes, and either bind every remaining
  input into identity or stop with the missing dependency named.
- **Incremental compilation: measurement gate, not machinery.** Trials are
  provider-bound by orders of magnitude; compile cost is negligible until E3
  population regimes. The trial ledger records compile share of generation
  wall time; the admission trigger for a content-addressed, module-granular
  compile cache (the natural continuation of the landed content-keyed
  projection cache) is measured compile share exceeding ~10% of generation
  wall time. Fine-grained (per-declaration) incrementality is not admissible:
  invariant 1 ("no reduced candidate mode") demands cache hits be provably
  equivalent to cold compiles, which content-keyed memoization of a hermetic
  pipeline gives by construction and dependency-tracked engines do not.

## Tranche Sequence And Gates

This table records the entry and exit criteria as reviewed on 2026-07-31. E0,
E1, and E2 have since completed; the remaining E3 row is not implementation
authorization or evidence that E3 has been selected.

| Tranche | Content | Entry gate | Exit gate |
| --- | --- | --- | --- |
| E0 | Control library workflow + conformance tests | ML kill-mid-provider crash/resume E2E green; lean-pilot owner-decision handoff; this design and component plan approved; E0 explicitly selected | one-call + accounting-parity conformance green |
| E1 | `run-ref`: materialization, identity, child runs, delta evidence, structural refusals | E0 exit; feasibility proofs 2–4; an assigned post-2.23 target | a pinned-revision child run executes both program modes with reproducible identity and evidence; inadmissible generated environments reject; crash → discard → rerun proven |
| E2 | `trial`: arms×reps, ledgers, blinding boundary, adjudication adapter, preregistration manifest | E1 exit; feasibility proofs 5–6 | a blinded three-treatment trial (DIRECT/COORDINATOR/ORC) reproduces the lean pilot's protocol on new platform-owned runs, evaluator unable to identify treatments (verified by a labeling probe) |
| E3 | External controller: gene-bounded proposals, baselines/ablations, promotion proposals | E2 exit + first fixed-study results reviewed | prompt-only search beats random search on validation under equal budget, or the program narrows/stops |
