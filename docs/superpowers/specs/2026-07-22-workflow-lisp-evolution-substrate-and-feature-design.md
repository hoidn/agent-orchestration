# Workflow Lisp Evolution Substrate And Feature Design

## Metadata

- **Status:** draft
- **Kind:** architecture decision
- **Owner:** Workflow Lisp frontend/runtime
- **Reviewers:** pending
- **Created:** 2026-07-22
- **Last material update:** 2026-07-22
- **Related docs / issues / plans:**
  [Workflow Language Design Principles](../../design/workflow_language_design_principles.md),
  [Workflow Lisp Frontend Specification](../../design/workflow_lisp_frontend_specification.md),
  [Workflow Lisp Parametric Type System](../../design/workflow_lisp_parametric_type_system.md),
  [Runtime Closures Boundary](../../design/workflow_lisp_runtime_closures_boundary.md),
  [Semantic Workflow IR](../../design/workflow_lisp_semantic_workflow_ir.md),
  [MLEvolve Workflow Lisp System Architecture](../../design/mlevolve_workflow_lisp_system_architecture.md),
  [Security Specification](../../../specs/security.md), and
  [State Specification](../../../specs/state.md)
- **Implementation target:** no implementation is authorized by this draft. The
  first admissible implementation target is the pure-expression proving
  experiment in [Dependencies And Sequencing](#dependencies-and-sequencing),
  followed by separately reviewed substrate and feature plans.

Purpose: define the boundary between reusable variant-execution substrate and
an evolutionary Workflow Lisp feature capable of post-hoc, expression-granular
self-evaluation and mutation.

Authority: this document is a target architecture. Normative runtime behavior
remains in `specs/`; current authoring behavior remains in the accepted Workflow
Lisp frontend documents. This design does not supersede those sources.

Copy safety: all `.orc` and API fragments in this document are conceptual and
are **not copy-safe**. They name proposed contracts, not implemented syntax.

Current fallback: generate ordinary source variants outside the running
workflow, compile every variant through the current compiler, launch each as a
new immutable run, and keep experiment/search state in an external controller.
The MLEvolve draft sketches possible workflow-level search organization, but it
does not currently supply an executable fallback or the expression-level
substrate designed here.

## Summary

Workflow Lisp should support evolutionary experimentation by adding a small,
general capability for **compiler-certified immutable variants**, not by adding
runtime `eval`, unrestricted code values, or a monolithic `evolve` language
primitive. A running workflow may observe results and propose changes, but it
must never replace its own executing code. Proposed changes are admitted,
compiled, and executed as new child runs at a generation boundary.

The design has three layers:

1. a general substrate that describes typed operation boundaries, identifies
   source subjects, certifies rewrites, and trials immutable variants;
2. a thin evolution-admission layer that defines which loci and genes a search
   may change and which type, proof, effect, and capability ceilings apply; and
3. an evolutionary library/workflow that owns mutation, crossover, population
   management, attribution, fitness, selection, and promotion proposals.

Provider calls, procedures, workflows, and prompts should converge on common
typed contract metadata so tooling can inspect and trial them uniformly. They
remain nominally different execution kinds: common signatures do not erase
durability, nondeterminism, effect, checkpoint, prompt, or provider semantics.
This is **typed contract parity**, not semantic substitutability.

## Context And Authority

The current language already has useful foundations:

- typed workflow and procedure inputs and returns;
- pure `defun` expressions over a closed operator surface;
- compiler-generated `pure_projection` execution for eligible pure regions;
- structured provider and command results;
- compile-time `ProcRef` values and specialization;
- source maps, Semantic IR, Executable IR, effect summaries, and durable
  workflow identity; and
- source-checksum protection that prevents changed workflow source from
  silently resuming against incompatible state.

Those foundations make **compile-time generation followed by ordinary
execution** possible today. They do not make syntax trees runtime values, expose
stable expression identities as a public contract, certify provider-proposed
rewrites, launch an isolated child bundle through a typed trial API, or provide
an OS sandbox for arbitrary generated code.

This design accepts the following existing decisions:

- pure expressions remain closed and effect-free;
- `ProcRef` remains compile-time-only;
- provider-produced code is untrusted data, never an executable closure;
- runtime closures stay deferred behind their separate sealed-family design;
- runtime plans and reports are not semantic authority merely because they are
  convenient views;
- workflow source identity remains a resume compatibility guard; and
- a candidate workspace is output isolation, not an operating-system security
  sandbox.

This design narrows the intended scope of the draft MLEvolve architecture. That
document sketches a possible file/branch-level search control plane and typed
search state; no current implementation proves those surfaces. It does not
define the general compiler contract for expression subjects, typed rewrites,
content-addressed variants, or exact prompt-program identity. Those belong to
the substrate here and could later be reused by MLEvolve or another search
strategy.

## Problem

There are two different problems that are easy to conflate.

The first is a language/runtime problem: safely refer to a part of a program,
propose a replacement, prove that the replacement still fits its lexical and
effect context, give the resulting program an immutable identity, and run it
without corrupting the parent run or its checkpoints.

The second is an optimization feature: decide what to mutate, generate
alternatives, evaluate them, assign credit, manage populations, select parents,
and decide whether any result deserves promotion.

Putting both into one `evolve` primitive would make one search algorithm part of
the language core, couple compiler changes to experimental policy, and tempt the
runtime to execute provider-produced code directly. Keeping everything outside
the language, however, leaves every experiment to coordinate source selection,
compiler-produced artifacts, stale-preimage checks, lineage, trial identity,
and resume logic. A reusable external SDK could coordinate those concerns once;
the relevant platform question is whether compiler certification and trial
identity deserve a shared public substrate, not whether the controller must be
written in `.orc`.

The design-level question is therefore not whether genetic algorithms are
possible. They are already possible with external scripts and ordinary source
generation. The question is which small capabilities the language/runtime can
provide that make many forms of controlled program experimentation safer,
more inspectable, and less ad hoc.

## Goals And Non-Goals

### Goals

- Permit recursive traversal and adjudication of expression/subtree subjects
  while applying all consequences between immutable runs.
- Preserve the current compile/type/proof/effect pipeline plus explicit new
  admission checks as the sole authority for registered executable variants.
- Give each base bundle, manifest, subject, rewrite, variant, genome, candidate,
  trial request/attempt, observation, and promotion proposal an explicit,
  auditable identity.
- Make the substrate useful without an evolutionary algorithm—for example for
  compiler-certified repair, refactoring experiments, A/B trials, and staged
  upgrades.
- Treat code, prompt programs, provider policy, and context policy as separable
  typed genes with distinct validation and identity rules.
- Permit common inspection and trial tooling across providers, procedures,
  workflows, and prompts without erasing their execution kinds or effects.
- Make whole-candidate evidence the fitness authority while retaining local
  observations as advisory attribution.
- Resume a search controller without pretending that a changed candidate can
  resume as its parent.
- Fail closed when compiler admission, sandbox policy, exact identity, sealed
  promotion evaluation, or budget enforcement is unavailable.

### Non-Goals

- Runtime `eval`, quote/unquote, arbitrary AST values, dynamic linking, or
  unrestricted `Code<T>` values.
- An executing workflow changing its own current control flow or checkpoints.
- Runtime procedure values or general runtime closures.
- Adding recursive pure helper calls. “Recursive adjudication” in this design
  means walking nested program structure recursively; current rejection of
  recursive `defun` call cycles is unchanged.
- Making a provider call, procedure, workflow, and prompt interchangeable just
  because their input and output types happen to match.
- Allowing the genome to mutate its own compiler, admission policy, sandbox,
  evaluator, search/validation cases, promotion holdout, budget policy, or
  promotion authority.
- Claiming that local expression scores identify causality in an interacting
  program.
- Automatically overwriting canonical source with a winning candidate.
- Choosing one optimizer. Genetic algorithms, beam search, Bayesian search,
  hill climbing, provider-guided repair, and exhaustive enumeration should all
  be possible consumers.
- Making arbitrary effectful-code trials safe before a real isolation boundary
  exists.

## Decision

Adopt a layered, compiler-certified variant architecture.

The compiler/runtime core will expose neutral operations to describe source
subjects, certify a rewrite into a content-addressed variant, and execute that
variant as a new trial. A small admission profile will add search-specific
locus and genome constraints. Evolutionary policy will remain a library or
workflow feature built on those operations.

The following alternatives are rejected:

| Alternative | Decision | Reason |
| --- | --- | --- |
| Core `evolve` form owning mutation, trials, scoring, and selection | Reject | Hard-codes experimental policy, enlarges the trusted core, and makes non-evolution uses awkward. |
| Runtime homoiconicity with `quote`, `eval`, or general `Code<T>` | Reject | Breaks static identity, resume compatibility, effect visibility, source ownership, and provider-code trust boundaries. |
| External scripts only | Keep as current fallback, not target | Feasible, but repeats compiler-context reconstruction, lineage, identity, and child-run mechanics in every tool. |
| Provider emits source that the current run executes directly | Reject | Provider output cannot mint executable authority. |
| Mid-run hot replacement at a checkpoint | Reject | Changes the meaning of existing checkpoints and makes replay and audit conditional on hidden history. |
| Immutable batchwise variants plus ordinary compilation | Adopt | Preserves current language invariants and makes failure/replay boundaries explicit. |

This choice makes spontaneous mid-run adaptation and arbitrary metaprogramming
deliberately harder. It also means even small variants pay compilation and
child-run overhead. Those costs are accepted because identity and trust are
more important than minimizing mutation latency.

## Design Details

### 1. Terminology

| Term | Meaning |
| --- | --- |
| **operation** | A nominal provider, procedure, workflow, prompt-program, or other certified boundary with typed contract metadata. |
| **subject** | A compiler-described source object eligible for inspection, such as a pure expression, prompt program, procedure, or workflow. |
| **locus** | A subject plus the policy and contextual proof that make it eligible for a particular search. |
| **gene** | One independently replaceable dimension of a genome, such as code, prompt content, model policy, or context policy. |
| **rewrite proposal** | Untrusted data describing an intended change to one or more subjects. It is not executable authority. |
| **variant** | A compiler-certified, immutable program bundle produced from an exact parent bundle and rewrite set. |
| **execution instance** | A trusted-registry record binding one variant, public workflow entrypoint, concrete runtime bindings, frozen-kernel identity, and allowed trial envelope. |
| **candidate** | One immutable genome realization under an admission contract, including its code variant and all non-code gene assignments. |
| **lineage event** | Provenance linking a candidate occurrence to parents, operator/version, proposals, generation, and realized randomness; not part of content identity. |
| **trial contract** | The complete recorded candidate, input, environment, provider, evaluator, workspace, observation, budget, and seed-policy identity. |
| **trial request / attempt** | A durable logical request and one physical child-run attempt allocated for that request. |
| **observation** | Typed or redacted evidence recorded at an expression, boundary, or run scope. |
| **assessment** | An evaluator result derived from trial evidence under a frozen evaluator contract. |
| **fitness** | Experiment-defined aggregate over whole-candidate assessments. |
| **generation** | A batch boundary after which observations may affect the next candidate set. |
| **promotion proposal** | A reviewed artifact proposing that a certified variant replace a named canonical source preimage. |

### 2. Three-Layer Ownership Boundary

| Layer | Owns | Must not own |
| --- | --- | --- |
| **1. General variant substrate** | Operation contracts, subject manifests, neutral rewrite-certification policies, immutable variant and execution-instance registries, child-trial launch, evidence envelopes, source maps, diagnostics | Genomes, mutation algorithms, populations, fitness functions, selection, crossover, “winner” semantics |
| **2. Evolution admission** | Allowed loci and genes, genome/candidate registration, lineage schema, frozen-kernel identity, experiment budget envelope, references to neutral rewrite/execution policies | How proposals are generated, how candidates are ranked, automatic source promotion |
| **3. Evolution feature** | Mutation and crossover, prompt mutation, population/search policy, local attribution, evaluator calls, fitness aggregation, selection, reports, promotion proposals | Minting executable variants, bypassing compiler checks, weakening sandbox policy, changing frozen evaluators inside a generation |

The main dataflow is:

```text
immutable base bundle
    -> compiler subject manifest
    -> experiment chooses admitted loci
    -> parent trial produces observations
    -> search emits untrusted rewrite proposals
    -> compiler certifies a new immutable bundle
    -> trusted admission validates all genes and registers an execution instance
    -> runtime launches bounded child trials
    -> frozen evaluators assess whole-candidate evidence
    -> search selects the next generation
    -> optional reviewed promotion proposal
```

No arrow points back into an executing bundle. A child is always a new bundle
and run identity.

### 3. General Variant Substrate

The substrate uses domain-neutral names. Its contracts must make sense for an
IDE refactoring experiment or staged rollout without mentioning genomes or
fitness.

#### 3.1 Common operation metadata

The compiler catalog projects each **concrete, monomorphic operation** to common
metadata. This is a compile-time/host schema, not a runtime `.orc` record or a
new kind of callable value:

```text
OperationContract = {
  operation_contract_id: Digest,
  kind: OperationKind,
  nominal_name: QualifiedName,
  call_occurrence_id: Optional[CallOccurrenceId],
  specialization_id: Optional[SpecializationId],
  parameters: Vector[ParameterContract],
  result: ResultContract,
  resolved_transitive_effects: EffectSummary,
  admission_capabilities: CapabilitySummary,
  implementation_identity: Digest,
  durability: DurabilityClass,
  source_owner: SourceOwner
}
```

`ParameterContract` preserves declared order, names, and types. A procedure
contract is emitted only after generic specialization and transitive-effect
resolution. A `PROVIDER_CALL` contract belongs to a compiler-generated
`provider-result` call occurrence with concrete request and result contracts;
it is distinct from the provider profile/extern, which is not a typed
`ProviderRef`. A `PROMPT_PROGRAM` contract, when that future surface exists,
maps typed parameters to `ComposedPrompt`. The enclosing provider-call contract,
not the prompt program, owns the expected provider response type.

`OperationKind` is closed and nominal. Initial relevant members are
`PROCEDURE`, `WORKFLOW`, `PROVIDER_CALL`, and `PROMPT_PROGRAM`. Matching
parameter and result contracts do not make two kinds substitutable.

Examples of preserved distinctions:

- a workflow owns durable public invocation and resume identity;
- a procedure owns reusable internal behavior and its lowered effect graph;
- a provider-call occurrence is nondeterministic external interaction governed
  by separate provider-profile and prompt-program identities;
- a prompt program constructs `ComposedPrompt` but does not itself produce the
  provider response or perform a provider effect; and
- a pure expression has no direct effects and is not an operation boundary
  merely because it has a function-shaped type.

The common projection supports inspection, policy, observability, harness
generation, and future signature-aware tooling. It does not create a universal
invocation form. The catalog is erased or sealed into concrete launch metadata
before runtime; no `ProcRef`, workflow ref, provider ref, prompt ref, type value,
or effect value enters ordinary `.orc` state.

#### 3.2 Subject manifest

The compiler produces an internal manifest for an exact bundle and compiler
contract:

```text
SubjectManifestId = H(
  bundle_id,
  compiler_contract_id,
  manifest_schema_id,
  subject_enumeration_policy_id
)

CompilerSubjectDescriptor = {
  manifest_id: SubjectManifestId,
  subject_id: SubjectId,
  kind: SubjectKind,
  owner: QualifiedName,
  source_span: SourceSpan,
  source_origin_kind: SourceOriginKind,
  authored_preimage_id: Optional[AuthoredPreimageId],
  rewriteability: Rewriteability,
  expansion_owner: Optional[QualifiedName],
  expected_type: TypeRef,
  lexical_context: LexicalContext,
  proof_context: ProofContext,
  direct_effects: EffectSummary,
  downstream_influence: InfluenceSummary,
  admission_capabilities: CapabilitySummary,
  structural_digest: Digest,
  parent_subject: Optional[SubjectId]
}
```

Types, lexical/proof contexts, effects, capabilities, and influence graphs
remain compiler-owned. The runtime/controller receives only a bounded
`SubjectManifestView`: manifest and subject IDs, kind, display span, origin,
rewriteability, structural digest, parent relation, opaque context/admission
digests, and an optional compiler-rendered mutation-hint artifact. `.orc` cannot
construct, pattern-match on, or persist `TypeRef`, `ProofContext`,
`EffectSummary`, or `CapabilitySummary` as language values.

`SubjectId` is meaningful only within its exact `SubjectManifestId`. Source
coordinates alone are never identity. Nested subject relations permit tree
inspection without exposing mutable compiler ASTs.

The first admitted subject is an explicitly selected, directly authored,
pre-expansion `PURE_EXPRESSION` with one unique writable preimage. Imported,
macro-generated, expanded, shared, or ambiguously mapped subjects may be
inspectable but have `rewriteability = NOT_REWRITABLE`. Procedure, workflow,
provider-call, and prompt-program subjects may be described before they are
mutable.

`downstream_influence` conservatively records whether a pure value can reach an
effectful control predicate, prompt/context data, provider policy, path data,
publication, or budget. A zero-effect expression is not thereby operationally
safe: changing its value can change which later effects occur.

#### 3.3 Rewrite proposal

A proposal is declarative, bounded data:

```text
RewriteProposal = {
  proposal_id: ProposalId,
  parent_bundle_id: BundleId,
  subject_manifest_id: SubjectManifestId,
  replacements: NonEmptyVector[SubjectReplacement],
  proposer_identity: ProposerId,
  proposal_nonce: Digest,
  rationale_artifact: Optional[ArtifactRef]
}

SubjectReplacement = {
  subject_id: SubjectId,
  expected_preimage_digest: Digest,
  replacement_encoding: UntrustedSourceFragment
}
```

The service derives every expected type and contextual constraint from the
manifest; proposer claims are never type authority. It parses an
`UntrustedSourceFragment` in the subject's grammar and context. A provider may
emit a proposal but cannot emit a `VariantHandle`.

The replacement set is atomic. Subject IDs must be unique and sorted into the
compiler's canonical order. Any ancestor/descendant overlap, duplicate subject,
manifest mismatch, or stale preimage rejects the whole proposal before
rewriting. Partial application is forbidden.

The initial encoding should be the narrowest deterministic source-fragment or
typed syntax-patch format that preserves source maps. This design does not
require general user-visible AST serialization.

#### 3.4 Certification

Conceptually, as a compiler/host API rather than current `.orc` syntax:

```text
RewriteCertificationPolicy = {
  rewrite_policy_id: RewriteCertificationPolicyId,
  subject_manifest_id: SubjectManifestId,
  admitted_subjects: Vector[SubjectId],
  structural_constraints: Vector[Constraint],
  direct_effect_ceiling: EffectSummary,
  admission_capability_ceiling: CapabilitySummary,
  downstream_influence_ceiling: InfluenceSummary,
  replacement_set_policy: ReplacementSetPolicy
}

describe(bundle, enumeration_policy) -> SubjectManifestView

certify(
  base: BundleId,
  proposal: RewriteProposal,
  policy: RewriteCertificationPolicyId
) -> CertificationResult

CertificationResult =
  CERTIFIED(VariantHandle, CertificationEvidence)
  | REJECTED(NonEmptyVector[CertificationDiagnostic])
```

`RewriteCertificationPolicy` is neutral: repair, refactoring, A/B, and
evolution clients can all use it without inventing a genome, population,
fitness, search bound, or promotion policy. The evolution-admission layer
references one such policy and adds its own concerns.

Certification reconstructs the whole affected module/bundle and runs ordinary
reader, expansion, name resolution, type, proof, effect, lowering, IR
validation, source-map, and identity checks. It then applies the new
admission-capability and downstream-influence policy. The repository does not
currently have the general ordered capability model sketched here. The pure
first slice uses the trivial empty direct-capability set plus conservative
`UNKNOWN_OR_UNBOUNDED` treatment for child-process, network, and undeclared
filesystem authority. A local type match is necessary but not sufficient.

For a pure expression replacement the central judgment is:

```text
Gamma ; Proofs |- replacement : ExpectedT ! Effects

Effects = EMPTY
admission_capabilities = EMPTY
```

The compiler then revalidates the enclosing `defun`, procedure/workflow, module,
imports, and bundle. The certification evidence records all compiler contract
versions. The service rehashes the base bundle, manifest, neutral rewrite
policy, compiler contracts, and result before registration. Evolution's frozen
kernel is validated later by candidate/execution-instance admission. There is no
API that converts proposal data directly into an executable value.

#### 3.5 Immutable variant registry and handle

The authoritative record lives in a trusted content-addressed registry:

```text
RegisteredVariant = {
  variant_id: VariantId,
  parent_bundle_id: BundleId,
  bundle_id: BundleId,
  source_digest: Digest,
  dependency_lock_digest: Digest,
  compiler_contract_id: Digest,
  operation_contract_digest: Digest,
  effect_admission_digest: Digest,
  certification_evidence: ArtifactRef,
  trial_entrypoints: Vector[TrialEntrypointRecord],
  retention_state: RegistryRetentionState
}

VariantId = H(resulting bundle content and all execution-relevant contracts)
```

Proposal nonce, proposer, rationale, and lineage do not affect `VariantId`.
Distinct proposals producing byte- and contract-identical bundles resolve to
the same content identity while retaining separate provenance records.

The controller stores only an opaque, monomorphic `VariantHandle` containing a
registry locator and expected `VariantId`. A plain serialized handle may be
forgeable; authority comes from trusted registry resolution, content rehashing,
retention/revocation checks, and exact-ID comparison at certification, launch,
evaluation, and promotion—not from a language-level claim that a record is
sealed. A later signed/MAC handle is an optimization or cross-trust-boundary
extension, not the initial authority model.

`.orc` can persist the handle as data and pass it only to trusted registration
services. It cannot inspect it as code, invoke it as a closure, splice it, or
dynamically link its bundle into the controller. A variant alone is not yet
authorized for a trial.

The general substrate separately registers a complete execution instance:

```text
ExecutionAdmissionPolicy = {
  execution_policy_id: ExecutionAdmissionPolicyId,
  allowed_entrypoint_contracts: Vector[Digest],
  allowed_runtime_binding_contracts: Vector[Digest],
  allowed_environment_contracts: Vector[Digest],
  kernel_contract_id: Digest,
  evaluator_contract_ids: Vector[Digest],
  workspace_contract_id: TrialWorkspaceContractId,
  budget_ceiling: TrialBudget,
  observation_contract_ids: Vector[Digest]
}

ExecutionInstanceSpec = {
  variant: VariantHandle,
  entrypoint_id: TrialEntrypointId,
  prompt_program_instance_ids: Vector[Digest],
  provider_policy_instance_ids: Vector[Digest],
  context_policy_instance_ids: Vector[Digest],
  environment_contract_id: Digest,
  execution_policy_id: ExecutionAdmissionPolicyId,
  kernel_contract_id: Digest,
  evaluator_contract_ids: Vector[Digest],
  workspace_contract_id: TrialWorkspaceContractId,
  budget_ceiling: TrialBudget,
  observation_contract_ids: Vector[Digest]
}

RegisteredExecutionInstance = {
  execution_instance_id: ExecutionInstanceId,
  variant_id: VariantId,
  entrypoint_id: TrialEntrypointId,
  runtime_binding_snapshot: ArtifactRef,
  environment_contract_id: Digest,
  execution_policy_id: ExecutionAdmissionPolicyId,
  kernel_contract_id: Digest,
  evaluator_contract_ids: Vector[Digest],
  workspace_contract_id: TrialWorkspaceContractId,
  budget_ceiling: TrialBudget,
  observation_contract_ids: Vector[Digest],
  admission_evidence: ArtifactRef,
  retention_state: RegistryRetentionState
}

ExecutionInstanceId = H(
  variant_id,
  entrypoint_id,
  runtime_binding_snapshot,
  environment_contract_id,
  execution_policy_id,
  kernel_contract_id,
  evaluator_contract_ids,
  workspace_contract_id,
  budget_ceiling,
  observation_contract_ids
)

register_execution_instance(
  spec: ExecutionInstanceSpec
) -> ExecutionInstanceAdmissionResult
```

The trusted service resolves and rehashes the variant and every runtime binding,
validates the exact selected entrypoint, environment, kernel, evaluator,
workspace, budget ceiling, and observation envelope against the neutral
execution policy, stores those selected values rather than copying policy-wide
allowlists, and constructs the content identity. Selection may narrow an
allowlist or budget ceiling but cannot widen it. Repair, refactoring, A/B, and
evolution clients can register an instance without any genome/search concepts.
The resulting opaque `ExecutionInstanceHandle` is the only executable authority
accepted by the general trial effect.

#### 3.6 Trial contract and crash-durable launch

The first tranche adds one explicit runtime-native effect:

```text
trial-certified-workflow(
  execution: ExecutionInstanceHandle,
  request: TrialRequestId,
  spec: MonomorphicTrialSpec
) -> MonomorphicTrialOutcome
```

The instance's `TrialEntrypointId` names one public workflow entrypoint already
registered for the exact variant bundle. It is not a `WorkflowRef`, `ProcRef`,
or generic callable. Procedures, provider calls, prompt programs, and
expressions can be trialled only through a statically compiled public harness
included in bundle identity. Launch creates an isolated child run; it never
loads candidate code into the controller process.

Generic notation in this document describes host schemas. The compiler/library
must project concrete monomorphic `.orc` records for each trial family; this
design does not assume user-defined generic record constructors at runtime.

```text
TrialContract = {
  trial_contract_id: TrialContractId,
  execution_instance_id: ExecutionInstanceId,
  input_digest: Digest,
  environment_contract_id: Digest,
  provider_contract_ids: Vector[Digest],
  workspace_contract_id: TrialWorkspaceContractId,
  observation_contract_ids: Vector[Digest],
  evaluator_contract_ids: Vector[Digest],
  budget: TrialBudget,
  seed_policy: SeedPolicy
}

TrialWorkspaceContract = {
  immutable_base_snapshot: ArtifactRef,
  read_only_inputs: Vector[ArtifactRef],
  exclusive_run_root_policy: RootPolicy,
  declared_output_roots: Vector[PathContract],
  symlink_policy: SymlinkPolicy,
  network_policy: NetworkPolicy,
  process_policy: ProcessPolicy,
  collision_policy: CollisionPolicy,
  cleanup_and_retention: RetentionPolicy
}

TrialEvidence = {
  trial_contract_id: TrialContractId,
  trial_request_id: TrialRequestId,
  trial_attempt_id: TrialAttemptId,
  child_run_id: RunId,
  realized_seed: Optional[Seed],
  exact_identity: TrialIdentity,
  outcome: MonomorphicTrialOutcome,
  observations: ObservationBundleRef,
  artifacts: ArtifactLedgerRef,
  resource_usage: ResourceUsage,
  violations: Vector[PolicyViolation]
}
```

`TrialContractId` is the content hash of the complete planned contract and may
be shared by deliberate repeats. `TrialRequestId` names one requested
measurement under that contract. `TrialAttemptId` names one physical attempt to
satisfy the request. Request and attempt IDs are allocation identities, not
inputs to execution-instance or trial-contract content identity.

Before allocating an attempt, the launcher resolves and rehashes the registered
execution instance and frozen-kernel bindings. The requested evaluator,
workspace, observation, and provider contracts must equal the registered values;
the requested budget may only narrow the registered ceiling. A controller
cannot widen authority by constructing a looser `MonomorphicTrialSpec`.

The controller allocates and commits `TrialRequestId` before asking for launch.
The launcher allocates `TrialAttemptId`, creates the child run record, and
durably links the attempt to `child_run_id` before the child may perform effects.
Launch is idempotent by request/attempt identity. On a crash or uncertain reply,
resume reconciles the durable mapping and child status; it does not allocate a
replacement attempt until policy has classified the prior attempt terminal and
non-reusable. A deliberate stochastic repeat receives a new request/attempt and
records its realized seed. An exact terminal evidence record may be replayed
only under the declared replay policy.

Trial evidence is authoritative only for its complete identity envelope. A
report may render it but is not a substitute for it.

### 4. Evolution-Admission Layer

The admission layer translates neutral subjects and variants into a bounded
search space.

```text
CompilerEvolutionLocus = {
  rewrite_policy_id: RewriteCertificationPolicyId,
  subject_manifest_id: SubjectManifestId,
  subject_id: SubjectId,
  allowed_gene_kind: GeneKind,
  max_replacement_size: Int,
  owning_experiment: ExperimentId
}

GenomeSchema = {
  code_genes: Vector[CompilerEvolutionLocus],
  prompt_genes: Vector[PromptLocus],
  provider_policy_genes: Vector[ProviderPolicyLocus],
  context_policy_genes: Vector[ContextPolicyLocus]
}

EvolutionAdmissionContract = {
  admission_contract_id: Digest,
  base_bundle_id: BundleId,
  subject_manifest_id: SubjectManifestId,
  genome_schema_id: GenomeSchemaId,
  rewrite_policy_id: RewriteCertificationPolicyId,
  execution_policy_id: ExecutionAdmissionPolicyId,
  trial_entrypoint_id: TrialEntrypointId,
  frozen_kernel_id: Digest,
  environment_contract_id: Digest,
  evaluator_contract_ids: Vector[Digest],
  observation_contract_ids: Vector[Digest],
  search_bounds: SearchBounds,
  trial_budget_ceiling: TrialBudget,
  trial_workspace_contract_id: TrialWorkspaceContractId,
  promotion_policy_id: Digest
}

SearchBounds = {
  max_subject_depth: Int,
  max_subjects: Int,
  max_proposals: Int,
  max_certifications: Int,
  max_trials: Int,
  max_generations: Int
}

GeneAssignment =
  CODE(CodeGeneInstance)
  | PROMPT(PromptGeneInstance)
  | PROVIDER_POLICY(ProviderPolicyGeneInstance)
  | CONTEXT_POLICY(ContextPolicyGeneInstance)

GenomeInstance = {
  genome_content_id: GenomeContentId,
  schema_id: GenomeSchemaId,
  assignments: CanonicallyOrdered[GeneAssignment]
}

CandidateProposal = {
  admission_contract_id: Digest,
  genome: GenomeInstance,
  code_variant: VariantHandle
}

RegisteredCandidate = {
  candidate_id: CandidateId,
  admission_contract_id: Digest,
  genome: GenomeInstance,
  variant_id: VariantId,
  execution_instance_id: ExecutionInstanceId,
  admission_evidence: ArtifactRef,
  retention_state: RegistryRetentionState
}

admit_candidate(CandidateProposal) -> CandidateAdmissionResult

CandidateLineageEvent = {
  lineage_event_id: LineageEventId,
  child_candidate_id: CandidateId,
  parent_candidate_ids: Vector[CandidateId],
  operator_id_and_version: Digest,
  proposal_ids: Vector[ProposalId],
  generation: Int,
  realized_rng_inputs: Vector[Digest]
}
```

The neutral rewrite policy, not the evolution locus, retains types, proofs,
effects, capabilities, structural limits, and influence constraints. The
compiler-internal evolution locus adds only gene/search-specific bounds. The
controller receives an opaque `EvolutionLocusId` and bounded descriptive view,
not those compiler objects as runtime type values.

`GenomeContentId` hashes the ordered realized gene assignments.
`CandidateId` hashes the admission contract, genome content, and resulting
`ExecutionInstanceId`, so prompt, provider-policy, context-policy, environment,
or other bound execution changes distinguish candidates even when the code
bundle is unchanged. Lineage and proposal nonce do not change content identity;
duplicate realizations share a `CandidateId` but retain distinct
`CandidateLineageEvent` records and population occurrences.

Every `CodeGeneInstance` names the exact registered `VariantId` and realized
replacement set. `CandidateProposal.code_variant` must resolve to that same
`VariantId`; otherwise admission fails. Thus code content cannot fall outside
`CandidateId` merely because the controller carries a registry handle
separately.

`CandidateProposal` is untrusted data. A trusted evolution-admission service
recomputes genome and candidate identities; validates every code, prompt,
provider-policy, and context-policy assignment against the genome schema,
neutral rewrite policy, and frozen kernel; verifies exact kernel, environment,
and workspace contracts, selected evaluator/observation subsets, and a budget
ceiling no wider than the referenced neutral execution policy; verifies that
the admission contract's single
`trial_entrypoint_id` is allowed; constructs and registers the complete
`ExecutionInstanceSpec` with the exact selected envelope; records the selected
entrypoint and envelope in admission evidence; and only then stores
`RegisteredCandidate`. A missing, ambiguous, or unauthorized entrypoint rejects
admission. The controller receives opaque `CandidateHandle` and
`ExecutionInstanceHandle` values. An evolution-specific trial wrapper resolves
the candidate-to-execution mapping before delegating to the general
`trial-certified-workflow` effect, so a controller cannot score one candidate by
substituting another execution instance.

The same admission transaction validates and commits the corresponding
`CandidateLineageEvent`; controller-supplied parent/operator/proposal/RNG fields
are provenance inputs, not trusted merely because they form a record.

Code and prompts are separate genes even if one operator proposes both. This
permits ablation, interaction analysis, independent constraints, and exact
reproduction without pretending that ablation proves simple causal credit.

The first **type-safe rewrite profile** is deliberately narrow:

- one or more directly authored pure-expression loci;
- no new effects or capabilities;
- no imports, new bindings, recursion, dynamic dispatch, or runtime references;
- bounded source/IR size;
- fixed surrounding signatures; and
- fixed compiler, search evaluator, promotion holdout, provider allowlist, and
  promotion policy.

It is not automatically operationally safe. The proving harness must be wholly
deterministic and effect-free, or limited to named deterministic fixture effects.
A locus whose value can reach effectful control flow, prompt/context data, path
data, provider policy, publication, or budget inherits the controls of those
sinks and is out of the first profile.

Effectful loci require later admission profiles. A profile may be stricter than
what the language can compile. “Compiles” does not imply “safe to explore.”

### 5. Evolution Feature

The actual feature is a replaceable search controller. It may be a typed `.orc`
workflow/library over monomorphic substrate projections or an external program
using the same public SDK/CLI. These two controllers must be capable of the same
search behavior; `.orc` is justified only if its typed durable orchestration,
artifact lineage, and resume behavior outweigh its constraints. The feature
owns:

- initial population construction;
- mutation and crossover operators;
- proposal generation by deterministic code or admitted providers;
- scheduling and resource allocation;
- repeated trials and uncertainty estimates;
- local observation interpretation;
- evaluator invocation;
- candidate-level fitness aggregation;
- diversity and novelty policy;
- parent/survivor selection;
- stop conditions; and
- `PromotionProposal` production.

It must not become the only consumer of the substrate and it must not be the
only way to express search. A “genetic algorithm” package can sit beside a beam
search or compiler-repair package.

The controller checkpoints population, lineage, pending work, completed trial
requests/attempts, aggregate assessments, and budgets. It does not checkpoint
an executing candidate and later resume it under a different bundle.

### 6. Prompt Programs And Prompt Evolution

Prompt mutation is part of the feature, but typed prompt programs are a future
slice, not a contract already projected from current prompt externs. The target
compiler/host schemas are:

```text
PromptProgramContract = {
  prompt_contract_id: PromptContractId,
  prompt_subject_id: PromptSubjectId,
  parameters: Vector[ParameterContract],
  result_kind: COMPOSED_PROMPT,
  semantic_program_id: Digest,
  composer_contract_id: Digest
}

ProviderCallContract = {
  operation_contract_id: Digest,
  provider_profile_id: Digest,
  declared_model_id: String,
  attested_provider_revision: Optional[Digest],
  call_policy_id: Digest,
  prompt_program_contract_id: PromptContractId,
  expected_response_contract: ResultContract,
  declared_provider_capabilities: CapabilitySummary
}

PromptAttemptIdentity = {
  semantic_program_id: Digest,
  dependency_snapshot_ref: ProtectedArtifactRef,
  dependency_snapshot_digest: Digest,
  context_policy_id: Digest,
  exact_invocation_bytes_digest: Digest,
  transport_binding_digest: Digest,
  provider_call_contract_id: Digest,
  session_identity: Optional[Digest]
}
```

The layers are distinct:

1. semantic prompt-program identity;
2. an immutable, access-controlled dependency/content snapshot sufficient to
   reproduce composition when policy permits;
3. exact per-attempt invocation-byte identity, including run-local transport
   bindings; and
4. declared provider/model identity, separately from any externally attested
   provider revision.

A digest without a governed content snapshot supports equality detection, not
full reproduction. Snapshot storage may be encrypted and access-controlled;
retention and deletion must match the data's sensitivity. Opaque remote model
weights or service changes cannot be proven stable from a model-name string.
Declared-identity drift blocks comparison, but undetectable provider drift
requires contemporaneous randomized arms, repeated trials, and appropriately
narrow claims. Stateful provider sessions are excluded from the first prompt
profile.

`PromptSubjectId` and `PromptContractId` are compiler/catalog identities, not
runtime prompt closures, dynamically selected callables, or provider-minted
references.

A prompt gene may change:

- literal or templated instruction content;
- typed examples or rubric data;
- bounded prompt-composition structure; and
- declared context-selection policy, when that is an admitted separate gene.

It may not silently change the evaluator prompt or any evaluation dataset.
Evaluator evolution is possible only as an outer experiment: freeze one
evaluator generation while comparing subject candidates, validate proposed
evaluators against independent anchors, then explicitly adopt a new evaluator
contract for a later experiment.

Prompt mutation is effectful whenever the consuming provider can use tools,
filesystem, processes, network, secrets, or live peers. Before OS-enforced
isolation exists, prompt evolution is limited to a proven text-only/no-tool
provider, deterministic mock, or recorded replay. Current unrestricted
workspace provider profiles are explicitly ineligible, even if their provider
name and model are frozen.

Multi-turn prompt topology and live provider interaction remain separate
language designs. Their existence would add new possible prompt-gene kinds; it
does not change the immutable-variant boundary.

### 7. Observation And Adjudication

Observation can occur at three scopes:

| Scope | Purpose | Authority |
| --- | --- | --- |
| Expression/subtree | Attribute intermediate values, branch outcomes, invariants, or cost to a locus | Advisory |
| Operation boundary | Observe typed request/response, effects, latency, artifacts, and failures | Evidence for the exact trial |
| Whole candidate | Evaluate end-to-end outcome over one or more trials | Authoritative input to fitness |

Expression observation should be a compiler-instrumented trace overlay, not a
durable checkpoint for every expression. The overlay maps events to
`(SubjectManifestId, SubjectId, visit identity)` and respects the existing
source map.
Payloads default to type, shape, digest, redaction class, timing, and declared
metrics; raw values require explicit policy because prompts, outputs, and state
may contain secrets.

“Recursive” adjudication is finite tree processing, not runtime call-stack
recursion. `describe` emits a finite manifest bounded by
`max_subject_depth` and `max_subjects`. The controller uses bounded
`loop/recur` over opaque `SubjectId` work items, or delegates traversal to a
certified deterministic service. Each experiment also fixes `max_proposals`,
`max_certifications`, `max_trials`, and total resource budgets. No runtime
closure, AST value, recursive `defun`, or recursive procedure call is required.

The bounded worklist proceeds as follows:

1. traverse the subject tree and collect observations for nested loci;
2. ask the compiler/evaluator services to assess each opaque locus under its
   compiler-owned context and the enclosing trial;
3. propose zero or more child rewrites;
4. certify complete child bundles;
5. trial the children; and
6. assign selection fitness from whole-candidate evidence.

Local assessments may guide mutation priority or provide a surrogate score.
They must not certify causality or override a worse whole-candidate result.
Interactions, dead code, compensation between expressions, stochastic provider
behavior, and evaluator noise all make local credit ambiguous.

### 8. Identity, Reproduction, And Resume

The design distinguishes three claims:

- **replay:** reuse recorded evidence for the exact same trial identity without
  re-performing effects;
- **repeat:** allocate a new request/attempt for the same execution instance and
  trial contract, producing a possibly different stochastic result;
- **regenerate:** reconstruct a variant/execution instance from recorded inputs;
  an evolution client may additionally reconstruct a candidate from lineage and
  must reproduce the same registered identities before treating it as the same
  content.

At minimum, `TrialIdentity` includes:

- execution-instance, variant, bundle, and registered-entrypoint identities;
- source, import, dependency-lock, compiler, lowering, and runtime contract
  digests;
- exact typed input digest;
- semantic prompt, immutable dependency snapshot, exact invocation bytes,
  transport binding, declared provider/model, optional attested provider
  revision, context, call-policy, and sampling digests;
- environment, dataset, tool, and isolation-policy digests;
- observation and evaluator contract digests; and
- budget, random-seed policy, and realized seed when applicable.

When the evolution wrapper launched the request, its trusted mapping adds
candidate, genome-content, and lineage-occurrence identities to the evidence
association. General repair, refactoring, or A/B trials need no candidate field.

An “exact” identity claim is exact for recorded local inputs and declared or
attested external contracts. It does not prove that an opaque remote provider
served identical hidden weights or infrastructure. Reports must distinguish
declared equality, attested equality, and empirically contemporaneous
comparison.

A subject ID from one parent is not assumed to name the “same expression” in a
child. Certification emits a lineage map for unchanged or explicitly replaced
subjects. Ambiguous structural correspondence is reported, not guessed.

The search controller may resume its queue and aggregate state. A child trial
may resume only under its own exact bundle and compatibility contract. Existing
parent checkpoints are never imported merely because most expressions are
unchanged. Any future cross-variant checkpoint reuse requires the separately
specified, tested, atomic upgrade mechanism required by the state contract.

### 9. Frozen Trust Kernel

Every experiment names a frozen kernel outside the mutable genome:

- reader, expander, type/proof/effect checker, lowering, and IR validators;
- subject-manifest and certification algorithms;
- dependency and bundle construction policy;
- sandbox and capability policy;
- secret/redaction policy;
- search/training evaluation inputs and leakage checks;
- validation inputs plus their declared adaptive-use budget;
- a sealed promotion holdout unavailable to mutation, survivor selection, and
  ordinary analysis until the candidate set and promotion analysis are frozen;
- evaluator implementation, prompt, rubric, and aggregation contract;
- resource budgets and termination policy; and
- source-promotion authority.

This is not a claim that the kernel is infallible. It is the stable reference
needed to make a generation comparable and to prevent a candidate from winning
by changing the judge. Kernel evolution happens in a separately evaluated
outer loop with an explicit contract transition.

Any dataset consulted during mutation or survivor selection is search/training
data. Any dataset repeatedly consulted under adaptive search is at most an
adaptively used validation set. Once a putative holdout is exposed to the
controller or operator before selection and analysis freeze, it is reclassified
and a new promotion holdout is required.

The platform rehashes frozen-kernel and bundle artifacts before certification,
launch, evaluation, and promotion. Candidate, proposer, and evaluator processes
must lack write authority to canonical source, registry records, evaluators,
search/validation data, and promotion holdouts. A provider is outside the
candidate genome but still part of the threat model; freezing its identifier
does not constrain its filesystem or tool authority.

### 10. Promotion

Search never writes canonical source automatically in the initial design. It
emits:

```text
PromotionProposal = {
  experiment_id: ExperimentId,
  expected_canonical_preimage: BundleId,
  candidate: CandidateHandle,
  gene_change_set: ArtifactRef,
  code_source_patch: Optional[ArtifactRef],
  evidence_bundle: ArtifactRef,
  promotion_holdout_contract_id: Digest,
  evaluator_contract_ids: Vector[Digest],
  risk_summary: ArtifactRef,
  required_review_policy: ReviewPolicyId
}
```

Promotion is a separate reviewed transaction. It rejects a stale canonical
preimage, resolves and rehashes the registered variant and every non-code gene,
runs the sealed promotion holdout only after the candidate/analysis freeze,
reruns required validation against the repository's current state, and records
the resulting new canonical identities. Prompt, provider-policy, and context
genes cannot disappear merely because only code has a source patch. Rollback is
ordinary versioned configuration/source rollback, not mutation of historical
trial records.

## Candidate Value Hypotheses And Examples

These examples show where the design might add leverage; they are not evidence
that it does. All proposed `.orc` forms are target-only pseudocode. A public
variant SDK/CLI with an external controller is a first-class alternative, not a
weaker imitation.

### Example A: Evolving A Pure Integer Scoring Expression

The current pure-expression surface can express this fixed-point integer score:

```lisp
(defun rank-score
  ((quality Int) (novelty Int) (cost Int)) -> Int
  (- (+ (* quality 7) (* novelty 3))
     (* cost 2)))
```

The proving experiment replaces only the directly authored result expression
and invokes it through an entirely deterministic, effect-free public harness.
It does not use the score to gate providers, commands, paths, publication, or
budgets.

Three honest implementations are possible.

Target `.orc` controller over the shared substrate:

```lisp
;; Target-only pseudocode; not current Workflow Lisp.
(defworkflow tune-rank-score
  ((experiment ExperimentContract)) -> ExperimentResult
  (evo/search-certified-variants
    experiment
    :locus experiment.rank-score-locus
    :optimizer 'GENETIC
    :population 20
    :generations 8))
```

External controller over the same future public substrate:

```python
client = VariantClient(experiment_contract)
locus = client.describe().require_locus("rank-score/result")
result = GeneticSearch(
    certifier=client.certify,
    trialer=client.trial,
    locus=locus,
    population=20,
    generations=8,
).run()
client.propose_promotion(result.best_candidate)
```

Current fallback without that joined substrate:

```python
base = read_source("ranking.orc")
marker = locate_explicit_authored_marker(base, "rank-score/result")
for fragment in mutate(read_marked_fragment(base, marker)):
    child = splice_and_check_preimage(base, marker, fragment)
    build = invoke_full_orchestrator_compile(child)  # compiler owns context
    if build.ok:
        runs = launch_new_runs(build.bundle, deterministic_search_suite)
        join_build_run_evidence_lineage_and_cost(build, runs, fragment)
write_reviewable_patch(select_population().best)
```

The current fallback delegates lexical/type reconstruction to the compiler; it
does not reimplement the compiler. What it lacks is a stable public locus and
rewrite API plus a joined registry, crash-durable trial namespace, lineage
envelope, and promotion precondition. A reusable external SDK could solve those
once. Therefore this example supports the **shared substrate hypothesis**, not
the claim that the controller must be `.orc`.

This is promising when evaluation is objective, deterministic, representative,
and expensive enough for provenance and fault recovery to matter. It is not
compelling for a one-line constant that a developer can tune once by inspection.

### Example B: Joint Code And Prompt Evolution With Separate Identities

Target-only conceptual behavior:

```lisp
;; Target-only pseudocode; current prompt externs are not typed prompt programs.
(prompt-program choose-next-action-prompt
  ((state SearchState)) -> ComposedPrompt
  ...)

;; The consuming provider-call contract, not the prompt program, owns
;; `ActionDecision` as its result type.
(provider-result analyst
  :prompt choose-next-action-prompt
  :inputs state
  :result ActionDecision)

(defun accept-decision
  ((decision ActionDecision) (remaining Int)) -> Bool
  (and (> remaining 0)
       (not (= decision.kind 'BLOCKED))))
```

A future experiment can keep prompt and code assignments distinct:

```lisp
;; Target-only pseudocode.
(evo/search
  :genes (genome
           (prompt-gene 'choose-next-action-prompt)
           (pure-expression-gene 'accept-decision :result-expression))
  :arms '(PROMPT_ONLY CODE_ONLY JOINT)
  :search-evaluator action-search-evaluator
  :promotion-holdout sealed-action-promotion-suite
  :provider text-only-provider-profile-v3)
```

The candidate envelope records:

```text
candidate 17
  code gene:          exact authored preimage -> exact replacement
  prompt gene:        semantic program + protected dependency snapshot
  invocation:         exact bytes + transport-binding digest
  provider identity:  declared identity + optional attested revision
  evaluator:          frozen search/validation contracts
  promotion holdout:  sealed until candidate and analysis freeze
  arms:               prompt-only + code-only + joint
  fitness:            aggregate over search/validation outcomes
```

A source-only controller can record the same distinctions, and the shared SDK
should make it equally able to do so. The value hypothesis is that the standard
candidate/trial envelope prevents accidental gene loss and evaluator drift.
Ablation estimates arm-level and interaction effects; it does not causally
assign an interacting gain to one gene. The provider must be text-only/no-tool,
sandboxed, mocked, or replayed; a frozen unrestricted provider profile is not
safe.

### Example C: One Substrate, Several Non-Evolution Uses

The generality test is whether the core remains useful without a population:

```text
compiler repair       describe -> propose one fix -> certify -> regression trial
IDE refactoring       describe -> rewrite -> certify -> declared-oracle trial
staged workflow A/B   certify two bundles -> trial under one environment contract
evolutionary search   describe -> many proposals -> many trials -> select
```

Today each tool can shell out to compile and run and can reuse an external
library. The platform case exists only if shared compiler-owned locus semantics,
registry identity, trial reconciliation, and evidence envelopes measurably
reduce duplication or failure. That must be demonstrated by at least one
non-evolution client; it is not established by this document.

### Negative Example: Mutating A Provider Boundary Or Tool-Using Prompt

This looks attractive but is not initially admissible:

```lisp
(provider-result analyst
  :prompt choose-next-action-prompt
  :inputs request
  :result ActionDecision)
```

Changing the provider, model, prompt, topology, read set, retry policy, or result
use can alter cost, data disclosure, nondeterminism, and external behavior. Even
changing only prompt text can redirect a tool-using provider. A type-compatible
replacement and frozen profile name are not enough.

Before such mutation is enabled, the locus and consuming provider need a real
sandbox, capability ceilings, budget enforcement, exact prompt identity,
provider allowlists, secret policy, and a trusted immutable kernel. Until then,
experiments may use deterministic mocks, recorded replay, a proven text-only
provider, or pure logic in a deterministic harness. They must reject arbitrary
provider-step rewrites and current unrestricted workspace provider profiles.

## Contracts And Interfaces

The proposed public contracts are summarized below. Names remain provisional;
their responsibilities are not.

| Contract | Producer | Consumer | Authority rule |
| --- | --- | --- | --- |
| `OperationContract` | compiler/catalog | inspection, policy, harness generation | Compile-time metadata; kind and effects remain nominal and explicit. |
| `SubjectManifestView` | compiler | refactoring/search tools | Opaque view valid only for exact manifest/bundle/compiler identity. |
| `RewriteProposal` | deterministic tool or provider | certification service | Untrusted data; never executable authority. |
| `RewriteCertificationPolicy` | compiler/policy author | certification service, any variant client | Neutral subject/structure/effect/capability/influence bounds; no genome or search policy. |
| `CertificationEvidence` | compiler/variant service | runtime, reviewers | Must cover the ordinary full compile pipeline. |
| `RegisteredVariant` / `VariantHandle` | trusted registry / controller | execution-instance admission | Registry resolution and rehashing, not record unforgeability, confer authority. |
| `RegisteredExecutionInstance` / `ExecutionInstanceHandle` | trusted neutral admission registry / controller | general trial launcher | Binds variant, entrypoint, runtime bindings, frozen kernel, evaluator/workspace/observation contracts, and budget ceiling. |
| `GenomeInstance` / `CandidateHandle` | trusted evolution-admission registry / controller | evolution trial wrapper, population, promotion | Every gene and its execution instance are registry-validated; lineage is separate provenance. |
| `TrialContract` | controller | trial launcher | Exact execution instance, inputs, environment, provider, evaluator, observation, workspace, and budget. |
| `TrialRequestId` / `TrialAttemptId` | controller / launcher | launcher, resume reconciler | Durable allocation and run linkage precede effects. |
| `TrialEvidence` | runtime | evaluator/controller | Typed ledger for exact trial identity; reports are views. |
| `EvolutionAdmissionContract` | experiment author/reviewer | candidate-admission service and controller | References neutral rewrite/execution policies, bounds mutable genes/search, and freezes the kernel. |
| `PromotionProposal` | controller | human/policy review transaction | Cannot overwrite a stale or unreviewed canonical preimage. |

### Compatibility impact

The design adds contracts; it does not change existing `.orc` meaning. Ordinary
workflows that opt out do not create manifests beyond compiler-internal data, do
not record expression traces, and do not pay trial-controller costs.

Future typed provider and prompt contracts must be additive. Existing provider
forms may project into conservative contracts, but a surface lacking exact
input/output, prompt-content, effect, or capability identity is ineligible for
evolution rather than silently approximated.

### Diagnostic classes

Failures must remain distinguishable:

```text
SUBJECT_NOT_FOUND
SUBJECT_MANIFEST_MISMATCH
SUBJECT_NOT_REWRITABLE
STALE_SUBJECT_PREIMAGE
OVERLAPPING_REPLACEMENTS
REWRITE_PARSE_FAILED
REWRITE_TYPE_FAILED
REWRITE_PROOF_FAILED
EFFECT_CEILING_EXCEEDED
CAPABILITY_CEILING_EXCEEDED
BUNDLE_VALIDATION_FAILED
VARIANT_IDENTITY_MISMATCH
VARIANT_HANDLE_INVALID_OR_REVOKED
EXECUTION_INSTANCE_ADMISSION_FAILED
EXECUTION_INSTANCE_INVALID_OR_REVOKED
CANDIDATE_ENTRYPOINT_AMBIGUOUS
CANDIDATE_ENTRYPOINT_UNAUTHORIZED
CANDIDATE_GENE_ADMISSION_FAILED
CANDIDATE_EXECUTION_MAPPING_MISMATCH
FROZEN_KERNEL_DRIFT
TRIAL_ISOLATION_UNAVAILABLE
TRIAL_WORKSPACE_COLLISION
TRIAL_BUDGET_EXCEEDED
TRIAL_ENTRYPOINT_MISMATCH
TRIAL_LAUNCH_UNCERTAIN
TRIAL_ATTEMPT_DUPLICATE
TRIAL_EVIDENCE_INCOMPLETE
SEARCH_BOUND_EXCEEDED
PROMPT_IDENTITY_INCOMPLETE
EVALUATOR_CONTRACT_MISMATCH
PROMOTION_HOLDOUT_EXPOSED
OBSERVATION_POLICY_VIOLATION
PROMOTION_PREIMAGE_STALE
```

Candidate rejection and trial failure are data for the controller; corruption
of the certifier, identity system, frozen kernel, or isolation guarantee is a
run-level blocker.

## Dependencies And Sequencing

This is an umbrella boundary architecture, not one implementation plan. Work
must be decomposed so each slice has independent acceptance evidence.

### Current feasibility map

| Capability | Current position | Design consequence |
| --- | --- | --- |
| Typed workflows/procedures and native returns | Implemented for supported surface | Reuse; do not redesign. |
| Closed integer-capable pure expressions and generated `pure_projection` | Implemented | One directly authored expression in an effect-free deterministic harness is the first proving surface. |
| Compile-time `ProcRef` / specialization | Implemented | Reuse for static hooks; do not turn into runtime closures. |
| Semantic/Executable IR and source maps | Implemented/partial by surface | Extend as compiler-owned evidence, not public mutable AST. |
| Structured provider/command result boundaries | Implemented/partial by route | Useful trial evidence; insufficient for provider mutation alone. |
| Runtime closures or executable provider-produced code | Future/forbidden | Not a prerequisite and not part of this design. |
| Stable public expression subject manifests | Not implemented | Required substrate work. |
| Neutral rewrite policy and contextual certification service | Not implemented | Required substrate work; must not require evolution concepts. |
| Authored-source rewriteability and downstream-influence analysis | Not implemented as this contract | Required before a subject is admitted merely because its expression is pure. |
| Content-addressed variant registry and opaque runtime handles | Not implemented | Required substrate work; registry resolution/rehash is authority. |
| Neutral registered execution-instance authority | Not implemented | Required before any general trial; binds exact runtime configuration and trial ceilings without genome concepts. |
| Runtime-native certified child-workflow trial effect | Not implemented | Required; static public workflow entrypoint only in the first slice. |
| Crash-durable trial request/attempt allocation and reconciliation | Not implemented as this contract | Required before no-duplicate resume claims. |
| Generic contract notation used in this document | Host-design notation only | Implementations must emit monomorphic `.orc` projections; user-defined generic record constructors are not assumed. |
| General ordered capability model | Not implemented | Pure slice uses empty direct capabilities and treats unknown child-process/network/filesystem authority as unbounded. |
| OS sandbox for arbitrary generated code | Not implemented by candidate workspace | Required before effectful/untrusted trials. |
| Typed prompt programs and exact content/invocation identity | Not implemented; partial digest concepts exist | Required before prompt evolution claims. |
| Self-bundle identity available to `.orc` | Not implemented as an authored value | The compiler/controller injects a concrete experiment contract; no magic `current-bundle` value is assumed. |
| Expression trace overlay | Not implemented | Optional for first black-box experiment; required for local attribution. |
| Public variant SDK/CLI | Not implemented | Must accompany or precede controller comparisons so external and `.orc` features use identical substrate. |
| Trusted genome/candidate admission registry | Not implemented | Required before evolutionary trials; validates every gene and creates a neutral execution instance. |
| Evolutionary search controller | Possible externally with ad hoc mechanics; target library absent | Feature work after or alongside narrow substrate proof. |

### Required sequence

1. **Proving experiment:** use an external controller and the current compiler
   to mutate one explicitly marked, directly authored integer result expression
   through an effect-free deterministic harness. Measure the custom work for
   locus recovery, compiler-artifact coordination, identity, trials, lineage,
   and crash recovery. Do not add public syntax.
2. **Subject/certification slice:** specify and implement pure-expression
   manifests, rewriteability/influence metadata, stale/overlap protection,
   neutral rewrite policies, contextual certification, trusted variant registry
   identity, and negative tests. Demonstrate one non-evolution consumer.
3. **Trial and SDK slice:** specify the monomorphic certified-workflow trial
   effect, neutral execution-instance policy/registry, registry
   resolution/rehash, durable request/attempt allocation, new-run
   linkage/reconciliation, exact trial identity, typed evidence, workspace
   contracts, budgets, and the public SDK/CLI. This slice must not claim
   security sandboxing it does not provide.
4. **Evolution-admission and library slice:** add trusted genome/candidate
   admission over the neutral policies, then implement one bounded optimizer
   using only substrate contracts in both an external controller and, if
   feasible, `.orc`.
   Separately compare substrate versus no substrate, `.orc` versus external
   control over the same substrate, and optimizer quality versus random/simple
   baselines.
5. **Prompt slice:** add typed prompt-program identity, protected dependency
   snapshots, exact invocation bytes, and transport/provider envelopes before
   allowing prompt genes; limit execution
   to text-only/no-tool, mock, replay, or genuinely sandboxed providers.
6. **Effectful slice:** only after a separate security design and real sandbox
   evidence, consider provider/procedure/workflow loci with effect and capability
   ceilings.

Steps 2 and the controller data-model portion of step 4 can proceed in parallel
after the proving experiment fixes the minimum contract. Prompt identity work is
independently useful but prompt-evolution acceptance waits for it. Arbitrary
effectful mutation waits for isolation and capability enforcement.

## Invariants And Failure Modes

### Invariants

- The executing bundle is immutable.
- Every candidate's code variant is compiled through the ordinary full compiler
  pipeline.
- A registered variant is not launch authority. Only a trusted, fully admitted
  execution instance can authorize a trial, and every registry handle and bound
  artifact is resolved and content-rehashed.
- Provider output is proposal data, never code authority.
- Whole-candidate evidence, not local expression commentary, determines
  authoritative fitness.
- Operation kinds and their effects remain visible after common contract
  projection.
- A candidate cannot widen its admitted effects, capabilities, read/write
  roots, provider allowlist, or budget.
- Evaluators, search/validation suites, and sealed promotion holdouts are
  outside the evaluated genome; promotion holdouts do not feed selection.
- Candidate state and artifacts cannot become parent/controller authority
  without typed validation and an explicit commit.
- Reports, prompt prose, stdout, and visualization artifacts are views.
- Resume never crosses bundle identity by default.
- Promotion is separate from search and checks an exact canonical preimage.

### Expected failure behavior

| Failure | Required behavior |
| --- | --- |
| Provider proposes malformed syntax | Certification rejects that candidate with structured diagnostics. |
| Replacement has the right result type but adds an effect | Certification rejects `EFFECT_CEILING_EXCEEDED`. |
| Parent changed after proposal creation | Reject stale subject/bundle preimage; do not relocate heuristically. |
| Candidate fails a trial | Preserve typed failure evidence; continue other bounded work if controller policy permits. |
| Trial crashes after effects | Apply ordinary exact-bundle retry/resume rules; do not replay under a sibling candidate. |
| Controller loses a launch reply | Reconcile the durable request/attempt/run mapping; do not start a duplicate uncertain attempt. |
| Variant handle or content is missing, revoked, or changed | Reject execution-instance/candidate admission or promotion and report the identity violation. |
| Candidate gene or execution binding violates its schema/policy | Trusted admission rejects it; the controller cannot create executable authority. |
| Execution-instance handle or bound artifact is missing, revoked, or changed | Reject before launch/evaluation and report the identity violation. |
| Prompt bytes or composer identity are missing | Candidate is ineligible for prompt-comparison claims. |
| Local score improves but end-to-end score regresses | Whole-candidate fitness wins; retain local score only as attribution evidence. |
| Evaluator is unavailable or changes identity | Block comparison/promotion; do not substitute a new evaluator silently. |
| Sandbox floor cannot be met | Block the affected trial before executing untrusted/effectful code. |
| Budget exhausts | Return an explicit exhausted outcome and retain partial evidence. |
| Promotion target has changed | Reject the proposal and require recertification/retrial as policy dictates. |

## Security, Operations, And Performance

Generated source, prompt content, context-selection policy, and provider policy
are untrusted inputs. Compiler certification proves language conformance; it
does not prove semantic safety or contain operating-system access.

A pure replacement is only type/effect-safe locally. Its value can still change
downstream control flow, prompts, paths, provider behavior, publication, or
budget. The first experiment therefore uses an entirely deterministic harness;
any locus that influences an effectful sink inherits that sink's isolation,
authority, and budget requirements.

Arbitrary effectful candidates require real enforcement of:

- filesystem and symlink boundaries;
- read-only datasets and declared output roots;
- network policy;
- child-process termination and resource limits;
- provider/model allowlists and cost ceilings;
- credential isolation;
- secret and trace redaction; and
- artifact retention and deletion.

The current candidate-workspace model is not sufficient evidence for those
claims. Until a sandbox exists, effectful experimentation is limited to trusted
fixed boundaries, deterministic mocks, recorded replays, static plan analysis,
or non-executing certification.

Mutation and evaluator providers are also processes with authority; they are
not made safe by being outside the genome. Until OS enforcement exists, they
must be deterministic/local, proven no-tool/text-only, recorded replay, or
explicitly trusted fixed processes unable to write canonical source, registry,
kernel, evaluator, or dataset artifacts. Current unrestricted workspace
profiles do not meet that condition.

Performance costs include recompilation, bundle storage, source-map and trace
metadata, repeated child startup, evaluator calls, and trials needed to handle
stochastic variance. Implementations should cache certification by the complete
identity envelope and deduplicate exact trials only when replay semantics allow
it. They must not cache across omitted prompt, provider, environment, compiler,
or evaluator identities.

Expression tracing is opt-in and sampled/bounded. Ordinary workflows incur no
per-expression checkpointing or trace cost.

## Evidence And Implementation Boundaries

An implementation follows this design only if:

- a variant is compiled by the same compiler/validation path used for ordinary
  Workflow Lisp bundles and authorized through the trusted registry;
- neutral rewrite and execution policies can serve a non-evolution client
  without genome, search, or promotion fields;
- changing a fragment cannot bypass type, proof, effect, neutral
  admission-policy, IR, source-map, registry, or identity validation;
- every evolutionary gene is trusted-service validated into a registered
  candidate and neutral execution instance before it can be trialled;
- trial launch resolves and rehashes the complete execution instance and uses a
  real new-run boundary over its exact certified bundle and bindings;
- controller resume and child-run resume are visibly distinct;
- protected prompt content snapshot, semantic composition, exact invocation
  bytes, transport bindings, and provider identity are separated in
  prompt-evolution evidence;
- an evolution controller can be replaced without changing the certifier or
  trial contracts; and
- at least one non-evolution consumer uses the variant substrate.

The following do **not** constitute implementation evidence:

- a test helper that edits a source string and calls a private compiler
  function;
- a fixture-only fake handle that ordinary runtime paths cannot validate;
- a report that says a candidate compiled without retained certification
  evidence;
- a candidate directory presented as a security sandbox;
- provider prose parsed as fitness or promotion authority;
- a demo that changes prompt paths but cannot identify exact composed bytes;
- or an evolutionary script that works only because it has unrestricted
  repository and process access.

## Compatibility And Migration

The architecture is additive and opt-in. Existing `.orc` files keep their
meaning, compiler pipeline, checkpoint identity, and resume behavior.

No migration is required until a public subject/certification surface is
accepted. At that point:

- manifests and variant schemas must be versioned;
- compiler-contract changes invalidate or explicitly upgrade old proposals;
- old trial evidence remains historical evidence under its recorded contracts;
- old provider/prompt surfaces without complete identity remain executable but
  are not eligible for strong evolutionary comparison claims; and
- no source is automatically rewritten or promoted.

Common operation metadata should be introduced as projections over existing
procedure/workflow/provider structures. It must not force existing code into a
single runtime calling convention. If projection cannot faithfully express a
boundary's effects or durability, that boundary remains ineligible rather than
being assigned a misleading contract.

## Verification Strategy

### Substrate verification

- Round-trip exact manifest IDs and nested directly-authored subject views with
  source maps; generated/imported/ambiguous subjects remain non-rewriteable.
- Reject stale bundle/manifest/subject/structural preimages, duplicates, and
  overlapping ancestor/descendant replacements atomically.
- Property-test that accepted pure replacements retain expected type and zero
  direct-effect/capability summaries, and separately test downstream-influence
  admission.
- Recompile the complete affected bundle, not only the fragment.
- Prove that forged, stale, revoked, or tampered variant, execution-instance,
  and candidate handles fail at the correct registry/admission/launch boundary.
- Prove that content-identical results share `VariantId` regardless of proposal
  provenance, while prompt/provider/context changes produce distinct
  `CandidateId` values even if code bundle identity is unchanged.
- Reject every mismatched or out-of-schema code/prompt/provider/context gene
  before candidate registration; reject any launch request that widens the
  registered execution instance's evaluator, workspace, observation, provider,
  environment, or budget envelope.
- Verify that exact narrowed entrypoint/evaluator/workspace/observation/budget
  selections are stored and affect `ExecutionInstanceId`; reject missing,
  ambiguous, or unauthorized evolution entrypoints.
- Prove that two distinct source, dependency, compiler, prompt, provider,
  environment, or evaluator identities do not collapse to one trial identity.
- Crash after child-run creation, after child completion, and before controller
  acknowledgement; reconcile the durable request/attempt/run link without
  duplicating an uncertain trial.
- Exercise a non-evolution repair/refactor client through the same public
  certifier, execution-instance registry, and trial path without constructing a
  genome, candidate, search bound, fitness function, or promotion policy.

### Feature verification

- Compare no substrate against the public certifier/trial SDK on audit
  completeness, injected-failure recovery, maintenance effort, and overhead.
- Run the identical optimizer externally and in `.orc` over the same substrate;
  compare behavior, resume evidence, implementation effort, and overhead.
- Separately compare optimizer quality with random search, exhaustive search on
  a finite toy space, and a simple review/revise baseline.
- Use search and adaptively budgeted validation cases during selection. Use a
  sealed promotion holdout only after the candidate set and analysis freeze.
- Use contemporaneous randomized arms and repeated trials when a provider is
  stochastic or its hidden service revision cannot be attested.
- Run ablations for code-only, prompt-only, and joint mutation before claiming
  an arm-level or interaction effect; do not infer simple causal credit.
- Verify deterministic population/controller resume from an interrupted work
  queue without cross-candidate checkpoint reuse.
- Verify invalid candidates, trial failures, and evaluator failures are typed
  outcomes rather than report parsing.
- Verify local attribution can disagree with candidate fitness and cannot
  override it.
- Do not assert literal prompt wording; assert typed contracts, exact identity,
  dataflow, lineage, and observable behavior.

### Effectiveness evidence

There are three independent effectiveness questions:

1. does the shared substrate beat ad hoc compile/run coordination;
2. does an `.orc` controller add value over an external controller using the
   same substrate; and
3. does a chosen optimizer beat simpler search strategies?

No answer is assumed. Charge provider calls, compilation, trials, evaluator
calls, storage, and operator attention. For each benchmark report:

- best search/validation score versus random search and human-authored baseline;
- sealed promotion-holdout result after candidate/analysis freeze;
- area under best-so-far curve versus trial/cost budget;
- invalid-proposal and failed-trial rate;
- score variance and confidence interval;
- fraction of gains surviving independent rerun;
- diversity/duplication statistics;
- wall time, provider cost, and stored evidence volume; and
- manual effort needed to configure loci, evaluators, and promotion review;
- missing/mismatched evidence caught under injected failures;
- controller crash-recovery correctness; and
- external-versus-`.orc` maintenance and runtime overhead.

No claim should generalize from one toy arithmetic expression to effectful
workflow evolution.

## Declarative Acceptance / Integration Scenarios

### Scenario 1: Pure Expression Child Variant

Initial state:

- one ordinary `.orc` bundle containing a pure `defun` used by a fixture
  workflow whose entire transitive behavior is deterministic and effect-free;
- a directly-authored marked result-expression locus with one unique preimage;
- a finite search suite, an adaptively budgeted validation suite, and a sealed
  promotion holdout;
- fixed compiler, runtime, environment, evaluator, and single public harness
  `trial_entrypoint_id` contracts; and
- no provider, command, filesystem, network, process, path/publication, or
  budget effect reachable from the locus or harness.

Public entrypoint: the evolution controller requests a subject manifest,
submits two proposals, receives one rejected and one certified variant, and
submits the valid genome to trusted candidate admission. The service registers
the candidate and neutral execution instance; the evolution wrapper launches
that exact instance through the public trial boundary.

Expected result:

- the effectful proposal is rejected with an effect-ceiling diagnostic;
- the pure type-correct proposal produces a new immutable bundle, registered
  candidate/execution instance, and child run;
- candidate admission records the fixed harness entrypoint and exact narrowed
  execution envelope; a missing or unauthorized entrypoint is rejected before
  execution-instance registration;
- trial evidence identifies execution instance, source, compiler, input,
  environment, observation, and evaluator contracts, while the trusted wrapper
  preserves the candidate association;
- the parent source and run checkpoints are unchanged;
- a forced crash after child completion but before acknowledgement reconciles
  the durable request/attempt/run mapping without duplicate launch;
  and
- a promotion proposal contains a reviewable patch but does not modify
  canonical source.

Forbidden behavior:

- executing proposal data directly;
- choosing a different allowed entrypoint ad hoc during candidate admission or
  launch;
- importing a parent checkpoint into the child;
- deciding success by parsing a markdown report; or
- feeding promotion-holdout results back into mutation or selection; or
- attributing a whole-candidate improvement to the local expression without
  whole-candidate evidence.

This scenario uses the real compiler, variant registry, candidate/execution
admission services, runtime child-run path, and typed evidence ledger. The
evaluator may be a deterministic fixture, but the registry handles, admission,
and run path may not be mocked.

### Scenario 2: Prompt And Code Ablation

Initial state:

- one typed prompt program and one pure acceptance expression;
- semantic prompt identity, protected dependency snapshot, exact invocation
  bytes, and transport-binding identity;
- a fixed text-only/no-tool provider/model/call policy with no session reuse;
- fixed search/validation evaluator contracts and a sealed promotion holdout;
  and
- three experiment arms: prompt-only, code-only, and joint.

Public entrypoint: the controller generates, certifies, and trials candidates in
all three arms under equal budgets.

Expected result:

- each trial records prompt and code gene identities separately;
- detectable declared provider/evaluator drift blocks comparison rather than
  silently opening a new arm, while opaque drift is mitigated with randomized
  contemporaneous arms and appropriately qualified claims;
- results report arm-level uncertainty and whole-candidate fitness;
- reproduction reconstructs the same candidate, bundle, dependency snapshot,
  and invocation-byte digests; and
- a joint winner is reported as an arm/interaction result rather than assigned
  causally to the prompt gene.

Forbidden behavior:

- evaluator prompt inside the mutable genome;
- path-only prompt identity;
- a tool-enabled or unrestricted workspace provider;
- treating matching response type as provider semantic interchangeability; or
- promotion from training score alone.

### Scenario 3: Effectful Locus Fails Closed

Initial state:

- a proposed rewrite changes a provider profile and expands the prompt read set;
- no accepted effectful admission profile or OS sandbox is configured.

Public entrypoint: the proposal is submitted to certification/trial admission.

Expected result: admission rejects the proposal before provider or command
execution, reports the capability/read-set expansion and missing isolation
policy, and leaves controller and canonical state unchanged.

This negative scenario proves that type-compatible provider mutation is not
mistaken for safe interoperability.

### Scenario 4: External And `.orc` Controller Equivalence

Initial state: the same finite pure-expression experiment, optimizer version,
candidate seeds, budgets, certifier, SDK, trial registry, and deterministic
search/validation suites are available to one external controller and one
target `.orc` controller.

Public entrypoint: both controllers drain their worklists, including the same
injected invalid proposal and the same crash-after-launch fault.

Expected result: both produce the same content-addressed candidates, terminal
trial set, fitness aggregates, and selected population. Any difference is
explained by a versioned controller-policy input. The comparison reports
implementation effort, recovery evidence, and runtime overhead.

Forbidden behavior: the `.orc` controller receives private compiler shortcuts,
or the external controller is denied the public certification/trial contracts.

This scenario decides whether `.orc` orchestration adds value; it does not gate
the more general substrate on `.orc` winning.

## Open Questions

The following choices remain intentionally open for the proving experiment or
the named downstream design slice:

- the minimal deterministic `UntrustedSourceFragment` encoding and whether an
  authored-source marker/annotation is needed;
- the manifest enumeration policy and conservative downstream-influence
  analysis needed for the first locus;
- trusted registry deployment, retention/revocation, and whether cross-process
  or cross-host use later requires signed/MAC handles;
- the atomic neutral execution-instance and evolution-candidate admission
  transactions, including registry lifetime and policy-version transitions;
- the concrete monomorphic `.orc` projection of candidate, trial, and evidence
  contracts;
- the public SDK/CLI transport and atomic request/attempt/run allocation
  mechanism;
- the later capability lattice, including ordering and
  `UNKNOWN_OR_UNBOUNDED` authority;
- protected prompt-snapshot encryption, access, retention, and deletion;
- normalized semantic prompt comparison versus exact transport-specific bytes;
- how much incremental compilation is useful without weakening whole-bundle
  certification; and
- which benchmark can distinguish substrate value, `.orc` controller value,
  and optimizer value at realistic cost.

These are not permission for an implementation plan to improvise. The relevant
slice must resolve its item in a reviewed design or proving-experiment decision
record before implementation.

## Success Criteria

The substrate design may advance from draft when reviewers agree that:

- general subject/certification/trial contracts contain no search-policy terms;
- evolution admission is a thin policy profile, not a second compiler;
- the feature can be replaced by another optimizer without substrate changes;
- typed contract parity preserves nominal operation kinds and effects;
- pure expression mutation requires neither runtime closures nor `eval`;
- prompt identity distinguishes semantic program, protected content snapshot,
  exact invocation bytes, transport binding, and declared/attested provider
  identity without overclaiming hidden remote reproducibility;
- resume and promotion preserve immutable bundle identity; and
- security claims do not confuse output workspaces with sandboxing.

An initial implementation is successful only when:

- Scenario 1 passes through real public integration paths;
- a non-evolution client uses the same substrate;
- negative admission and forged-handle tests pass;
- controller resume is demonstrated with fresh execution evidence;
- substrate value, `.orc` controller value, and optimizer value are evaluated
  as separate comparisons;
- capability status and authoring docs distinguish implemented from designed
  surfaces; and
- no ordinary workflow pays tracing or evolutionary-controller overhead when
  the feature is disabled.

Prompt evolution requires Scenario 2. Effectful-locus support requires Scenario
3 plus positive sandbox and capability-enforcement scenarios from a separate
security design.

## Stop / Revise Criteria

Reconsider or narrow the design if any of the following occurs:

- the pure-expression proving experiment shows that ordinary source generation,
  compilation, and run launch already provide reliable identity and lineage
  with negligible duplicated machinery;
- stable subject identity requires exposing mutable compiler ASTs or guessing
  correspondence across bundles;
- certification cannot reuse the ordinary compiler path;
- trusted registry handles cannot remain inert identifiers limited to the
  certified-workflow trial effect;
- useful trials require mid-run code replacement rather than generation
  boundaries;
- common operation metadata hides kind-specific effects or durability;
- evaluator leakage or drift cannot be detected independently of candidate
  performance;
- evolutionary search does not outperform random/simple search after full cost
  accounting on representative tasks;
- the public SDK makes an `.orc` controller strictly more complex without
  better typed recovery, auditability, or integration value;
- local expression instrumentation dominates trial cost or creates unacceptable
  data exposure; or
- effectful evolution cannot be isolated without granting the candidate access
  to the controller, evaluator, credentials, or canonical source.

If the only compelling use remains one optimizer over one workflow, keep that
optimizer external or in a future MLEvolve feature package and do not
generalize the language core.

## Documentation And Specification Impact

No normative specification changes follow from accepting this draft alone.
Each implemented slice must update the relevant sources at the same time:

- `specs/dsl.md` for any public authored forms or reference types;
- `specs/state.md` and `specs/versioning.md` for bundle/trial identity and
  resume compatibility;
- `specs/security.md` for actual isolation and capability enforcement;
- `specs/providers.md` and `specs/dependencies.md` for typed prompt/provider
  identity;
- observability/source-map designs for expression trace contracts;
- the frontend and IR designs for subject manifests and certification; and
- `docs/capability_status_matrix.md` when an accepted design establishes a
  `Designed`/`Future` surface and whenever fresh evidence later changes it to
  partial or implemented.

Until then, current authors must use ordinary static `.orc`, compile-time
`ProcRef`, external variant generation, and new immutable runs.

## Implementation Handoff

After this design is reviewed, planning should begin only with the proving
experiment. That plan should inventory the exact custom machinery needed by one
pure-expression experiment and use the results to shrink or validate the
proposed substrate contracts. Subject/certification, child-trial identity,
evolution policy, prompt identity, and effectful sandboxing should remain
separate implementation plans with their own integration gates.
