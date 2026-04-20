# ADR: Adjudicated Provider Step

**Status:** Proposed

**Date:** 2026-04-20

**Owners:** Orchestrator maintainers

## Context

The workflow system currently treats one provider step as one provider invocation.
Recent EasySpin workflow work exposed a useful recurring pattern: run the same
logical step through one or more provider/model/prompt candidates, evaluate the
candidate outputs, keep a queryable score record, and promote the best candidate
as the step output consumed by the rest of the workflow.

Ad hoc PATH shims can route a provider command, but they do not provide
candidate workspace separation, output comparison, historical score data,
deterministic selection, or clean artifact lineage. Encoding this pattern
manually in YAML is possible for one-off experiments, but it spreads the same
mechanics across candidate setup, provider invocation, evaluation, score storage,
selection, and promotion. Those mechanics belong in the workflow runtime.

The desired pattern is:

- farm one logical provider step out to one or more candidate providers and/or
  prompt variants in separate copy-backed child workspaces
- evaluate each valid candidate output with a reusable evaluator prompt
- store one global score row per candidate in an easily queryable form
- promote the highest-scoring candidate output into the current execution
  frame's normal workflow artifact stream
- still attempt evaluation and score recording when only one candidate runs

## Decision Summary

Add a new DSL step execution form, `adjudicated_provider`, gated behind DSL
version `2.11`.

An adjudicated provider step behaves like a normal provider step in its current
execution frame for deterministic artifacts: it uses the same `consumes`, prompt
composition, output contracts, and `publishes` surfaces. It does not expose the
ordinary provider-step stdout capture surface in the first release; downstream
dataflow must use declared artifacts. Internally, the runtime creates one
immutable post-preflight baseline snapshot, executes one or more candidate
provider invocations from separate copy-backed workspaces, evaluates valid
candidate outputs from deterministic evidence packets, selects a candidate, and
promotes the selected candidate's declared outputs back to the canonical
workflow paths.

The first implementation targets artifact-producing provider steps such as
design, plan, review, manifest, and report generation. It does not promote
arbitrary source edits from competing implementation candidates.

## Goals

- Represent candidate generation, evaluation, scoring, selection, and promotion
  as one logical workflow step.
- Preserve downstream compatibility: later workflow steps in the same execution
  frame consume ordinary `expected_outputs`, `output_bundle`, and published
  artifacts.
- Run each candidate in a separate child workspace so candidates do not clobber
  one another's declared output paths through orchestrator-managed paths.
- Store one global numeric score per scored candidate, plus short evaluator
  rationale.
- Record provider, model, prompt source, prompt hash, candidate status,
  evaluator identity, score, selection status, and idempotency key in a normative
  JSONL score ledger.
- Provide a reusable library evaluator prompt for qualitative candidate
  evaluation.
- Make single-candidate execution use the same ledger and promotion machinery as
  multi-candidate execution while keeping evaluator failure non-blocking by
  default when the score cannot affect selection.

## Non-Goals

- Do not implement pass/fail evaluator semantics. Runtime contract validity
  determines whether a candidate output is promotable; evaluator score orders
  candidates only when every output-valid candidate that needs a score has one.
  An unscored output-valid candidate is never silently demoted below a scored
  candidate.
- Do not make prompt text decide routing or selection.
- Do not support provider sessions inside adjudicated candidates in the first
  release.
- Do not support arbitrary source-edit promotion, patch merging, or conflict
  resolution in the first release.
- Do not support stdout-derived dataflow for adjudicated steps in the first
  release. Candidate and evaluator stdout/stderr are runtime logs and
  non-scoring sidecars, not `steps.<Step>.output`, `steps.<Step>.lines`, or
  `steps.<Step>.json`.
- Do not implement general data-loss prevention, arbitrary secret discovery, or
  automatic redaction of score-critical evidence. The first release rejects
  evidence containing known workflow-declared secret values, but otherwise treats
  copied workspace files, prompts, packets, and declared outputs as sensitive
  unmasked run state.
- Do not introduce OS-level sandboxing or prove containment of arbitrary
  child-process side effects. The first release covers only orchestrator-managed
  path resolution, candidate baseline state, validation, evaluation evidence, and
  selected-output promotion.
- Do not introduce a generic parallel execution framework before the candidate
  selection contract is proven.
- Do not make the evaluator prompt workflow-specific. Workflows may provide a
  small rubric, but the normalized evaluator output contract is shared.

## Proposed DSL Surface

The authored step keeps normal provider-step prompt, deterministic
output-contract, and publication surfaces, but uses `adjudicated_provider`
instead of `provider`.

```yaml
- name: DraftBigDesign
  id: draft_big_design
  adjudicated_provider:
    candidates:
      - id: codex_high
        provider: codex
        provider_params:
          model: gpt-5.4
          effort: high

      - id: claude_opus
        provider: claude
        provider_params:
          model: claude-opus-4-7
          effort: high

    evaluator:
      provider: claude
      provider_params:
        model: claude-opus-4-7
      asset_file: prompts/adjudication/evaluate_candidate.md
      evidence_confidentiality: same_trust_boundary

    selection:
      tie_break: candidate_order
      require_score_for_single_candidate: false

    score_ledger_path: artifacts/evaluations/major-project/${run.id}/draft_big_design.candidate_scores.jsonl

  asset_file: prompts/major_project_stack/draft_big_design.md
  consumes:
    - artifact: tranche_brief
      policy: latest_successful
      freshness: any
  prompt_consumes: ["tranche_brief"]
  expected_outputs:
    - name: design_path
      path: ${inputs.state_root}/design_path.txt
      type: relpath
      under: docs/plans
      must_exist_target: true
  publishes:
    - artifact: design
      from: design_path
```

Candidate fields:

- `id`: stable candidate id, unique within the step.
- `provider`: provider template name.
- `provider_params`: optional provider parameters, with the same substitution
  semantics as ordinary provider steps in the candidate execution context.
- `asset_file` or `input_file`: optional candidate base-prompt override. The two
  fields are mutually exclusive. If absent, the candidate inherits the step's
  base `asset_file` or `input_file`.
- `prompt_variant_id`: optional stable label for score analysis. If absent, the
  runtime derives one from prompt source kind, prompt source path, and composed
  prompt hash.

Candidate prompt overrides replace only the base prompt source. The step-level
`asset_depends_on`, `depends_on`, `consumes`, `prompt_consumes`,
`inject_consumes`, output contract suffix, and output contract itself still
apply uniformly to every candidate.

Evaluator fields:

- `provider`: provider template name.
- `provider_params`: optional provider parameters.
- `asset_file` or `input_file`: evaluator prompt source.
- `rubric_asset_file` or `rubric_input_file`: optional task-specific rubric.
  The runtime reads the rubric and embeds complete rubric content in the
  evaluation packet when it fits the score-critical evidence limits; the
  evaluator is not expected to read the rubric path itself.
- `evidence_confidentiality`: required literal
  `same_trust_boundary` in the first release. This is an explicit author
  attestation that the evaluator provider, its configured account or local
  process, and any provider-side retention are allowed to receive the complete
  unmasked score-critical evidence packet for this step.
- `evidence_limits`: optional object controlling the maximum score-critical text
  evidence that may be embedded in an evaluator packet. `max_item_bytes` defaults
  to `262144` and `max_packet_bytes` defaults to `1048576`. Both values are byte
  counts after UTF-8 encoding; `max_packet_bytes` must be greater than or equal
  to `max_item_bytes`.

Selection fields:

- `tie_break`: only `candidate_order` in the first release.
- `require_score_for_single_candidate`: optional boolean, default `false`. When
  `false`, one output-valid candidate is promoted even if evaluation fails. When
  `true`, a single candidate must also produce a valid finite score.

No threshold, pass/fail status, or score band is part of the selection contract.
For multi-candidate runs, every output-valid candidate must produce a finite
score in `[0.0, 1.0]` before selection can proceed. The runtime then selects the
highest score, using declared candidate order as the tie-break.

## Execution Context And Path Authority

The runtime maintains one workflow state frame, two workspace authorities, and
one evaluator execution directory for an adjudicated step:

- **Current execution frame**: the lexical/runtime state scope in which the step
  is executing. For a root workflow step this is the top-level run state. For a
  reusable-call callee step this is the call-frame-local state persisted under
  `state.call_frames[call_frame_id].state`.
- **Parent WORKSPACE**: the checkout where the orchestrator was launched. This is
  the canonical filesystem workspace used for workspace-relative authored paths
  after frame-scoped substitutions, promotion destinations, and the
  workspace-visible score ledger mirror.
- **Candidate WORKSPACE**: the copy-backed workspace used as the current working
  directory for one candidate provider invocation and for that candidate's
  output-contract validation.
- **Evaluator CWD**: a runtime-owned scratch directory under the parent run root,
  used as the current working directory for evaluator provider invocations.
  Authored evaluator prompt and rubric paths are still resolved before invocation
  using the rules below; the evaluator CWD is not a workflow artifact authority.

The canonical `RUN_ROOT` remains under the parent WORKSPACE at
`.orchestrate/runs/${run.id}`. Candidate metadata, composed prompt files,
stdout/stderr logs, evaluation packets, score ledgers, promotion manifests, and
promotion staging directories are runtime-owned files under that parent run
root. `RUN_ROOT` is not rebound into the candidate copy.

Runtime-owned adjudication sidecars are also scoped by the current execution
frame. Path templates below use `<frame_scope>` for that durable scope key:
`root` for top-level workflow steps, or a path-safe encoding of the reusable
`call_frame_id` for callee steps. This prevents two invocations of the same
imported workflow step from sharing candidate workspaces, evaluation packets,
score ledgers, or promotion manifests.

State and lineage authority follows the same lexical/call-frame scope as an
ordinary provider step. Candidate and evaluator provider names resolve in the
active workflow's private provider namespace. Workflow inputs, context defaults,
`self`/`parent` step references, loop variables, `consumes` freshness, and
`publishes` all use the current execution frame. Inside a reusable call,
callee-private `artifact_versions` and `artifact_consumes` remain inside the
call-frame-local state, and only declared callee workflow outputs cross back to
the caller through the existing outer call-step export contract.

Workspace-relative authored surfaces are interpreted as follows:

- `consumes` preflight runs once in the current execution frame before the
  candidate baseline snapshot is created. Resolved consume values come from that
  frame's state and artifact lineage. For DSL versions that materialize relpath
  consume pointer files, that materialization happens in the parent WORKSPACE
  before the baseline snapshot so every candidate sees the same selected consume
  state.
- `input_file`, plain `depends_on`, `consume_bundle.path`, `expected_outputs.path`,
  `output_bundle.path`, and deterministic relpath targets are rebound to the
  candidate WORKSPACE for candidate prompt composition, dependency checks,
  provider execution, and candidate output-contract validation.
- `asset_file`, `asset_depends_on`, evaluator `asset_file`, and
  `rubric_asset_file` remain workflow-source-relative to the authored workflow
  file or imported workflow source tree. Candidate WORKSPACE rebinding does not
  change workflow-source-relative asset authority.
- If `consume_bundle` is declared, the runtime writes a candidate-local bundle
  from the already resolved current-frame consumes before composing that
  candidate's prompt. The bundle is not promoted unless it is also part of the
  selected candidate's declared output contract.
- Provider command `cwd` is the candidate WORKSPACE. The provider receives the
  same environment, secrets, and provider template parameter substitution model
  as an ordinary provider step. Orchestrator-managed workspace-relative path
  resolution is scoped to the candidate WORKSPACE; arbitrary filesystem effects
  by the child provider process are not.
- The output contract suffix is rendered after substitution in the candidate
  execution context. It shows concrete workspace-relative paths, not absolute
  candidate or parent paths. Promotion later maps those same relative paths from
  candidate WORKSPACE to parent WORKSPACE.
- Step-result variables, workflow inputs, context, loop variables, `${run.id}`,
  and `${run.timestamp_utc}` keep their normal current-frame values. The first
  release rejects `adjudicated_provider` output-contract paths,
  `consume_bundle.path`, candidate or step `input_file`, and step `depends_on`
  entries whose substituted value depends on `${run.root}` or names the parent
  run root in parent-WORKSPACE coordinates. Runtime-owned run files are not valid
  candidate-managed outputs.
- Candidate WORKSPACE is a logical path authority even when its physical
  directory is stored below the parent `RUN_ROOT`. A candidate-managed path is
  valid when its resolved path stays under the logical Candidate WORKSPACE root;
  it is not rejected merely because that workspace's physical path is nested
  under `.orchestrate/runs/${run.id}`. The candidate authority root is exactly
  `<candidate_root>/workspace`; sibling runtime-owned directories under
  `<candidate_root>` and all parent `RUN_ROOT` paths remain outside candidate
  authority.

All path checks use the existing security model: reject absolute paths, reject
`..`, follow symlinks, and ensure the resolved path remains under the applicable
authority root before each orchestrator-managed filesystem operation.

This feature does not add a new subprocess security boundary. Provider and
evaluator commands are ordinary child processes under the existing provider
model, so they can read or write any path allowed by the operating system and by
the provider tool itself. The built-in Codex provider template, for example, may
run with its own approvals and sandbox bypassed. The adjudicated-provider
contract therefore guarantees only runtime-managed separation:

- candidate prompt composition, dependency checks, consume-bundle materialization,
  output validation, evidence collection, and promotion source reads use the
  candidate WORKSPACE authority
- each candidate starts from the same runtime-created baseline snapshot for the
  paths included by the baseline policy below
- only the selected candidate's declared outputs are copied into parent
  workflow paths by the promotion transaction

It does not prove that an arbitrary provider or evaluator avoided undeclared
side effects in the parent checkout, sibling candidate workspaces, the run root,
or other OS-visible paths. Workflows that require containment for untrusted or
side-effectful provider tools must run the whole orchestrator inside an external
OS/user/container sandbox or a disposable checkout. Runtime logs, manifests, and
promotion preimage checks are audit and transaction tools for declared outputs,
not a general filesystem-conflict detector for undeclared child-process writes.

## Confidentiality And Retention Contract

Adjudication intentionally creates more durable run state than an ordinary
provider step: baseline snapshots, candidate workspaces, composed candidate
prompts, evaluation packets, scorer snapshots, score ledgers, evaluator logs, and
promotion manifests. These artifacts are sensitive run state, not public logs.
They may contain unmasked prompt text, consumed artifact content, workspace file
content, declared outputs, relpath target contents, evaluator rationales, and
failure messages.

The existing secret model still applies to ordinary logs, state, prompt audit,
stdout/stderr tails, and provider transport surfaces: known secret values are
masked on a best-effort basis there. That masking guarantee does not sanitize
copied workspace files, candidate workspaces, declared output files, composed
provider prompts, evaluation packets, scorer snapshots, or promotion staging
files. Those artifacts preserve exact bytes when exact bytes are part of the
candidate or scoring contract.

The baseline snapshot has three possible null paths:

- A declared-input-only candidate workspace would minimize retention, but it
  would not match ordinary provider behavior for repository-context tasks where
  the provider may read supporting files that were not named in `depends_on`.
- Author-supplied include or exclude lists would give finer control, but they
  add a second dataflow language before the candidate contract is proven and can
  make same-step candidates incomparable if authors accidentally hide different
  context.
- Honor-all-ignore-files behavior, such as treating `.gitignore` as a copy
  policy, is too broad for this repo's existing workflow model because ignored
  roots often include runtime artifact surfaces such as `state/`, `artifacts/`,
  `logs/`, and `tmp/` that provider steps intentionally consume or produce.

The first release therefore uses one fixed broad workspace copy policy with a
fixed local-secret denylist and an explicit manifest. The copy is intentionally
unmasked for included files. Authors who need a stricter inclusion boundary must
run the workflow from a minimized or disposable checkout, materialize only
non-sensitive summaries as declared inputs, or avoid `adjudicated_provider` for
that step until a later include-list feature exists.

Evaluator evidence has a similar null-path decision. Hash-only packets are not
scoreable, path-based evaluator reads are not replayable or authority-stable, and
masked score-critical evidence would no longer be the exact output being
compared. The first release therefore sends complete unmasked score-critical text
evidence to the evaluator only when the workflow author explicitly sets
`evaluator.evidence_confidentiality: same_trust_boundary`. Loader validation
rejects omitted or different values. This field is an author attestation that the
selected evaluator provider is inside the same confidentiality boundary as the
candidate provider and the workspace content for this step. The runtime cannot
infer that trust relationship from provider names.

Before writing an evaluation packet to disk or launching the evaluator, the
runtime scans the in-memory score-critical evidence for every non-empty value of
workflow-declared `secrets`. The first policy version is
`workflow_declared_secrets.v1`. If a known secret value is found, the runtime
does not persist the packet and does not send it to the evaluator. The candidate
records `score_status: "evaluation_failed"` with failure type
`secret_detected_in_score_evidence`, and normal selection rules apply:
multi-candidate selection and single-candidate steps requiring a score fail
closed, while an optional-score single-candidate step may still promote an
otherwise valid output with a null score. This scan is only a guard for declared
secret environment values; it cannot detect arbitrary credentials or
confidential data inside repository files, consumed artifacts, prompts, or
outputs.

Workflow authors are responsible for the remaining confidentiality decision. If
prompts, consumed artifacts, candidate outputs, or relpath targets can contain
secrets or regulated data, the author must either choose candidate and evaluator
providers approved for that data, move the adjudicated step to a disposable
checkout with only approved inputs, produce a bounded non-sensitive artifact for
adjudication and handle the sensitive payload in a later ordinary step, or keep
the step as a non-adjudicated provider step.

## Candidate Workspaces And Baseline Snapshot

Each candidate runs in a runtime-owned child workspace:

```text
.orchestrate/runs/<run_id>/candidates/<frame_scope>/<step_id>/<visit_count>/<candidate_id>/workspace/
```

After consume preflight and parent-side consume materialization, the runtime
creates one immutable baseline snapshot for the step visit:

```text
.orchestrate/runs/<run_id>/adjudication/<frame_scope>/<step_id>/<visit_count>/baseline/workspace/
```

The baseline is a deterministic filesystem copy of the supported parent
WORKSPACE surface at that point in the step. It is a semantic adapter for
candidate prompt and output-contract paths, not a byte-for-byte clone of
everything an ordinary provider subprocess could inspect.

Baseline copy policy `adjudicated_provider.baseline_copy.v1`:

- Include regular files, directories, and safe relative symlinks from the parent
  WORKSPACE except for the excluded roots below.
- Exclude all orchestrator runtime state under `.orchestrate/`, including prior
  run roots and the current run root.
- Exclude VCS metadata under `.git/`. Providers that need git metadata are
  outside the first release unless an earlier workflow step materializes the
  required git facts into regular workspace files.
- Exclude common dependency, virtual-environment, build, and cache roots:
  `.venv/`, `venv/`, `env/`, `.tox/`, `.nox/`, `node_modules/`, `dist/`,
  `build/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, and `.ruff_cache/`.
  These are high-entropy operational inputs, not deterministic adjudication
  evidence. A future DSL option may add explicit additional include or exclude
  rules, but the first release has only this fixed policy.
- Exclude fixed local-secret and credential file classes at any workspace depth:
  `.env`, `.env.*` except `.env.example`, `.env.sample`, and `.env.template`;
  `.netrc`; `.npmrc`; `.pypirc`; `.docker/config.json`; `.ssh/`; `.aws/`;
  `.azure/`; `.config/gcloud/`; `.gnupg/`; files ending in `.pem`, `.p12`,
  `.pfx`, `.key`, or `.kubeconfig`; files named `id_rsa`, `id_dsa`,
  `id_ecdsa`, `id_ed25519`, `credentials.json`, `token.json`, or
  `service-account.json`. These paths are recorded as excluded with reason
  `secret_denylist`. If a required orchestrator-managed path crosses this
  denylist, the candidate fails before provider launch rather than copying or
  redacting the file.
- Do not honor `.gitignore`, global Git excludes, tool-specific ignore files, or
  user-configured ignore files as baseline copy policy in the first release.
  Those files are authoring and VCS hints, while the adjudication baseline is a
  runtime dataflow adapter. Existing workflows commonly place intentional runtime
  surfaces under ignored roots such as `state/`, `artifacts/`, `logs/`, or `tmp/`.
- Preserve a symlink only when its link text is relative and its normalized target
  remains under the parent WORKSPACE and outside every excluded root. Absolute,
  broken, escaping, or excluded-target symlinks are not copied; the manifest
  records the path as excluded. Any required orchestrator-managed path that
  crosses such a symlink fails before provider launch.

The baseline manifest is runtime-owned state, not candidate input. It records:

- copy policy version, local-secret denylist version, workflow checksum, source
  parent workspace path, baseline root path, and resolved consume selections
- an ordered included-entry list with entry type, workspace-relative path, byte
  size, executable bit, SHA-256 content hash for regular files, and link text plus
  resolved target for preserved symlinks
- an ordered excluded-root list, secret-denylist exclusion list, and
  excluded-symlink list with reason codes
- a `baseline_digest` computed from the canonical manifest content

The runtime also records null-path comparison for every workspace-relative path
surface it resolves before candidate launch: candidate or step `input_file`,
plain `depends_on`, `consume_bundle.path`, materialized consume pointer files,
and declared output value-file paths. The comparison records whether the parent
path was included, excluded, or absent and whether the baseline path has the same
state and hash. A required path that would have existed for an ordinary provider
but is excluded by baseline policy fails with `candidate_status:
"prompt_failed"` and a baseline-excluded failure type. Optional paths that are
excluded are treated as absent and recorded. This is the only input-equivalence
check the runtime can prove; undeclared child-process reads remain outside the
contract.

The immutable baseline is also the authority for promotion destination
preimages. For declared output value-file destinations whose workspace-relative
paths are known before provider launch, the runtime records the baseline-time
parent preimage with the step visit. For relpath target destinations that are
known only after a candidate validates, the runtime derives the baseline-time
parent preimage from the baseline manifest and baseline workspace before
promotion. A destination baseline preimage is either `file` with SHA-256 hash and
mode metadata, `absent`, or `unavailable` when the destination would cross an
excluded, escaping, absolute, broken-symlink, directory-as-file, or otherwise
unresolvable path. `unavailable` is a promotion conflict in the first release.

Every candidate workspace, including every provider retry workspace, is copied
from this same immutable baseline, not from the live parent WORKSPACE. Parent
checkout changes after baseline creation therefore cannot change supported
candidate input state or make one candidate see different included source files
than another. Promotion compares every destination against its baseline-time
parent preimage, not merely against the parent state observed after candidate
execution. A parent destination that appears, disappears, changes content, changes
type, or changes symlink resolution after baseline creation fails promotion with
`error.type: "promotion_conflict"` before selected outputs are copied into the
parent WORKSPACE.

Later implementations may replace the baseline and child workspace copies with a
more efficient overlay, but the contract is the same: each candidate provider
starts in a separate copy-backed workspace with identical supported baseline
input state and may use normal workspace-relative paths inside that workspace.

The first release promotes only declared outputs from the selected candidate.
Candidate-local source edits that are not part of the declared output contract
remain in the candidate workspace for inspection but are not applied to the
parent checkout by the orchestrator.

## Output Validation And Promotion

Each candidate executes the logical provider step in its child workspace using
the same prompt composition and output contract suffix that an ordinary provider
step would receive, adjusted by the execution-context rules above. Runtime
validation of `expected_outputs` or `output_bundle` runs against the candidate
WORKSPACE.

Only candidates whose declared output contract validates are eligible for
evaluation. A provider failure, timeout, prompt preparation error, missing
output, path escape, or output-contract validation failure is recorded in
candidate metadata and in the score ledger, but it is not evaluated.

After evaluation, if selection succeeds, the runtime promotes the selected
candidate's declared outputs to the parent WORKSPACE.

Promotion inputs:

- For non-`relpath` `expected_outputs`, the promotion source is the candidate
  output value file at the declared path.
- For `relpath` `expected_outputs`, the promotion sources are the path-only value
  file and, when `must_exist_target: true`, the candidate WORKSPACE target file
  named by that relpath value.
- For `output_bundle`, the promotion source is the candidate bundle JSON file
  and, for any relpath bundle field with `must_exist_target: true`, the
  candidate WORKSPACE target file named by that extracted relpath value.

Promotion is a resume-safe transaction, not a blind copy:

1. Build a promotion manifest under
   `.orchestrate/runs/<run_id>/promotions/<frame_scope>/<step_id>/<visit_count>/manifest.json`.
   The manifest records selected candidate id, source paths, destination paths,
   source hashes, baseline destination preimages, current parent destination
   preimages, and an ordered file list. Each baseline destination preimage is one
   of `file` with a SHA-256 hash and backup path to be created during commit, or
   `absent` with no backup path. Existing directories at destination file paths,
   baseline preimage `unavailable`, or a current parent preimage that differs
   from the baseline preimage are promotion conflicts before staging or parent
   writes. Duplicate destination paths are rejected unless they refer to the exact
   same source hash and role. The manifest also records parent directories that
   must be created for promotion, with their baseline and current preimage state.
2. Copy every promotion source into a staging directory under the same promotion
   root. Re-run the deterministic output-contract validator against the staged
   tree before touching parent outputs.
3. Re-check destination preimages in the parent WORKSPACE immediately before
   commit against the baseline destination preimages recorded in the manifest. If
   any destination differs from its baseline-time preimage, fail the step with
   `error.type: "promotion_conflict"` and do not modify parent outputs. Existing
   destination files that are unchanged from their baseline preimage may be
   replaced; destinations that were absent at baseline must still be absent.
   Unrelated files are never touched.
4. Mark the manifest `committing`, then replace destinations using same-filesystem
   temp files and atomic renames per file. Create only the missing parent
   directories recorded in the manifest. For each overwritten destination whose
   live parent file still matches the baseline preimage, keep a backup copy under
   the promotion root until parent validation succeeds. For each destination
   whose baseline preimage was `absent`, the manifest entry is the rollback
   tombstone.
5. After all files are in place, validate the canonical parent-WORKSPACE output
   contract again. If validation fails, mark the manifest `rolling_back` and undo
   only files touched by this transaction: restore backup files for `file`
   baseline preimages whose current content still matches the staged source hash,
   delete `absent`-baseline destinations whose current content still matches the
   staged source hash, and treat already-absent `absent`-baseline destinations as
   rolled back. If a touched destination matches neither the staged source nor the
   recorded baseline preimage state, fail with `error.type:
   "promotion_rollback_conflict"` and leave the manifest for operator inspection.
   After file rollback, remove manifest-created parent directories in reverse
   order only when they are empty; never remove pre-existing directories or
   directories containing unrecorded files. A completed rollback marks the
   promotion failed and fails the step with `error.type:
   "promotion_validation_failed"`.
6. Mark the manifest `committed` only after canonical parent validation succeeds.
   Normal `publishes` and completed step state are written only after the
   committed marker exists.

Resume rules for promotion:

- If the manifest is `prepared`, resume repeats baseline preimage checks and
  commits.
- If the manifest is `committing`, resume compares each destination with the
  staged source hash and recorded baseline preimage state. Destinations already
  matching the staged source are treated as committed. Destinations with `file`
  baseline preimages that still match the recorded hash are replaced.
  Destinations with `absent` baseline preimages that are still absent are
  replaced. Any destination matching neither the staged source nor the recorded
  baseline preimage state fails with
  `promotion_conflict`.
- If the manifest is `rolling_back`, resume performs the rollback rules above
  before returning the promotion failure.
- If the manifest is `failed` after a completed rollback, resume returns the
  recorded promotion failure without publishing artifacts.
- If the manifest is `committed`, resume revalidates the canonical parent output
  contract and proceeds to publication if publication has not already completed.

This makes downstream workflow steps in the current execution frame unaware of
candidate execution. They see the selected outputs as if a normal provider step
in that frame produced them, and they cannot consume selected artifact lineage
until promotion and publication have both completed. Inside a reusable call,
that lineage remains callee-private unless exported through declared callee
workflow outputs.

## Evaluation Contract

The evaluator prompt is a library component. The first shared prompt should live
at:

```text
workflows/library/prompts/adjudication/evaluate_candidate.md
```

The runtime builds one deterministic evaluation packet per output-valid
candidate, stores it under the parent run root, and appends the packet content to
the evaluator prompt. This packet is the only candidate-specific evidence the
evaluator may use for scoring. It contains complete score-critical text evidence
only, including the exact rendered provider prompt delivered to the candidate.
The rendered prompt includes the base prompt, injected source/workspace
dependencies, consumed-artifact injection, and deterministic output-contract
suffix after runtime substitution. The packet may also carry hashes and
component metadata for auditability, but the evaluator-visible prompt evidence is
not a lossy replacement for the provider prompt. Packet contents are unmasked
sensitive run state; the runtime only builds and sends them under the
confidentiality rules above. Truncatable or advisory side channels such as
candidate stdout/stderr, transport logs, prompt previews, and non-injected
consume previews are stored as non-scoring sidecars under the parent run root and
are not appended to the evaluator prompt, not included in
`evaluation_packet_hash`, and not part of `score_run_key`. Paths in the packet
are metadata only for embedded score-critical items; non-scoring sidecar paths
are not included in the evaluator prompt. The evaluator contract is based on
embedded evidence, so evaluator providers are not required to have file-read
capability beyond receiving the composed prompt.

Before the first evaluator launch for a step visit, the runtime resolves the
evaluator provider configuration, evaluator prompt source, and optional rubric
source into a scorer snapshot under:

```text
.orchestrate/runs/<run_id>/adjudication/<frame_scope>/<step_id>/<visit_count>/scorer/
```

The snapshot stores the exact base evaluator prompt content before any candidate
packet is appended, optional rubric content, prompt/rubric source metadata,
resolved evaluator provider params, and their hashes. The runtime computes
`scorer_identity_hash` from a canonical object containing evaluator provider,
resolved evaluator model and params hash, evaluator prompt source kind/source and
content hash, rubric source kind/source and content hash or `null`, evaluator
JSON contract version, evaluation packet schema version, score-critical evidence
limits, `evidence_confidentiality`, and the secret-detection policy version. This
hash identifies the scoring function and evidence contract used to compare
candidates; it does not include candidate-specific evidence.

Scorer resolution failure is distinct from evaluator failure. If at least one
output-valid candidate exists but the runtime cannot resolve the evaluator
provider configuration, evaluator prompt source, optional rubric source, provider
params, or scorer snapshot metadata, no evaluator is launched and no evaluation
packet is built. The runtime persists normalized failure metadata under the
scorer directory with `scorer_resolution_failure_key`; this metadata is not a
scorer snapshot and cannot be used to compare scores. Output-valid candidates
that would otherwise need evaluation record `score_status:
"scorer_unavailable"` with null scorer identity fields, a non-null
`scorer_resolution_failure_key`, and a scorer-resolution `failure_type`.
Candidates whose output contract did not validate still record `score_status:
"not_evaluated"` because they were never eligible for scoring. A scorer
resolution failure blocks promotion whenever a score is required: all
multi-candidate comparisons and single-candidate steps with
`require_score_for_single_candidate: true` fail with `error.type:
"adjudication_scorer_unavailable"`. A single output-valid candidate with
`require_score_for_single_candidate: false` may still be selected by contract
validity and promoted, with `selected_score: null`.

Evaluator invocation context:

- The evaluator provider process runs with `cwd` set to a runtime-owned
  Evaluator CWD under
  `.orchestrate/runs/<run_id>/adjudication/<frame_scope>/<step_id>/<visit_count>/evaluators/<candidate_id>/workspace/`.
  The runtime supplies the composed evaluator prompt through the provider
  template's normal prompt-delivery mode; evaluator scoring must not depend on
  reading files from the parent WORKSPACE.
- The evaluator receives the reusable evaluator prompt plus one `Evaluator
  Packet` block. The packet embeds the exact rendered candidate provider prompt,
  including the output-contract suffix that the provider received. The evaluator
  does not receive `output_capture`, provider stdout/stderr, transport logs,
  non-scoring sidecars, or any bounded preview content.
- Evaluator stdout must be strict JSON. Stderr and transport logs are captured as
  runtime-owned evaluator logs under the parent run root.
- Evaluator `input_file` and `rubric_input_file`, when used, are substituted in
  the current execution frame and resolved parent-WORKSPACE-relative because they
  are evaluator prompt surfaces, not candidate prompt surfaces.

Evaluation packet schema version `adjudication.evaluation_packet.v1` includes:

- scorer identity hash, evaluator provider, evaluator params hash, evaluator
  model, evaluator prompt source metadata, evaluator prompt hash, and rubric
  source/hash metadata
- candidate id, provider, provider params hash, model, candidate index, and
  prompt variant id
- composed candidate prompt path, full composed prompt hash, and complete
  rendered candidate provider prompt content exactly as delivered to the
  provider, including the deterministic output-contract suffix after runtime
  substitution
- prompt component hashes for the base/task portion and deterministic
  output-contract suffix, when those components exist
- normalized declared output artifact names and the candidate's parsed output
  artifact values
- embedded contents for every declared output value file and every required
  relpath target file
- embedded bundle JSON and extracted field values for `output_bundle`
- resolved consumed artifact values from current-frame consume preflight and
  complete text content for consumed relpath targets that were injected into the
  candidate task prompt for this step
- optional rubric content, rubric source path, and rubric hash
- `evidence_confidentiality`, secret-detection policy version,
  `evidence_valid`, and `evidence_invalid_reasons` for packet evidence
- byte sizes, SHA-256 hashes, UTF-8/text detection status, and read errors for
  every embedded evidence item

The runtime computes packet evidence validity before launching the evaluator.
There is no advisory evidence class in the v1 scoring packet. Score-critical
evidence consists of the complete rendered candidate provider prompt content,
every declared output value file, every required `relpath` target file, the
`output_bundle` JSON file and required bundle `relpath` targets when
`output_bundle` is used, optional rubric content when a rubric source is
declared, and current-frame consume relpath target content that was injected into
the candidate prompt for this step.

Packet evidence is valid only when the runtime can embed the complete UTF-8 text
for every score-critical item, with no read error, truncation, binary omission,
size-limit overflow, or known workflow secret value. Hash-only or prefix-only
evidence is not scoreable in the first release. If any score-critical item is
incomplete or contains a known secret value from workflow-declared `secrets`, the
runtime does not persist the packet and does not ask the evaluator to score that
candidate. It records `score_status: "evaluation_failed"` with an
evidence-incomplete or `secret_detected_in_score_evidence` failure type.
Multi-candidate selection then fails closed under the partial-scoring rule. A
single-candidate step may still promote the output-valid candidate only when
`require_score_for_single_candidate` is `false`.

Score-critical content rules are deterministic:

- Score-critical text evidence is embedded completely. The resolved evidence
  limits are `evaluator.evidence_limits.max_item_bytes` and
  `evaluator.evidence_limits.max_packet_bytes`, defaulting to 256 KiB per item
  and 1 MiB total per packet. A larger score-critical item makes the packet
  evidence invalid rather than allowing selection from partial content. The
  resolved limits are part of `scorer_identity_hash`, `score_run_key`, and
  scorer-resolution failure keys because changing them changes which candidates
  are scoreable.
- Truncation is never valid inside an evaluator-visible packet. Content that
  would require truncation stays in non-scoring sidecars and is unavailable to
  the evaluator.
- Non-UTF-8 or binary score-critical evidence makes the packet evidence invalid.
- Detection of any non-empty workflow-declared secret value in score-critical
  evidence makes the packet evidence invalid and prevents packet persistence.
  This is a precise-value guard, not a general data-loss-prevention scanner.
- A required declared output that cannot be read for evidence makes evaluation
  fail for that candidate. For a single-candidate step with
  `require_score_for_single_candidate: false`, that evaluation failure is
  recorded but does not block promotion of an otherwise output-valid candidate.

The default limits are conservative transport and reviewability defaults, not
semantic score thresholds. The first release appends the packet to the evaluator
prompt and then uses the evaluator provider template's normal prompt-delivery
mode, so every byte of score-critical evidence competes with evaluator
instructions, rubric text, provider argv/stdin transport limits, provider context
limits, and durable run-log size. Workflows may raise or lower the limits per
step after choosing an evaluator provider template that can carry the resulting
prompt; for large packets, an explicit stdin-mode evaluator provider is the
expected authoring pattern because the runtime does not auto-convert argv
templates. The limits bound packet construction only; provider transport failure
after packet construction is still an evaluator failure.

This embedded-evidence adapter is intentionally stricter than asking evaluators
to read original files. The packet is immutable, path-authority checked, hashed,
and replayable from the parent run root; evaluator scoring does not depend on
provider filesystem permissions, candidate workspace lifetime, symlink behavior,
or later parent-workspace mutations. When complete score-critical evidence cannot
fit in the packet, the runtime fails evaluation instead of silently delegating a
lossy comparison to the evaluator. Authors who need to adjudicate large or
binary outputs have three first-release choices: raise the explicit evidence
limits and use a provider that can accept the resulting prompt, restructure the
workflow so the adjudicated step declares a bounded UTF-8 text artifact that
summarizes or references the large payload while a later non-adjudicated step
handles the payload, or wait for a later non-lossy evaluator transport.

The evaluator must write strict JSON:

```json
{
  "candidate_id": "codex_high",
  "score": 0.82,
  "summary": "Concrete, self-contained, and suitable for planning."
}
```

Runtime requirements:

- `candidate_id` must match the candidate being evaluated.
- `score` must be a finite number in `[0.0, 1.0]`.
- `summary` must be a non-empty string.

The runtime does not interpret score bands. Score is used only for ordering
after all candidates that need scores have valid scores.

## Selection Semantics

Selection operates over output-valid candidates:

- If no candidate validates its declared output contract, the adjudicated step
  fails with no promotion and `error.type:
  "adjudication_no_valid_candidates"`.
- If exactly one candidate validates its output contract and
  `require_score_for_single_candidate` is `false`, that candidate is selected
  regardless of scorer resolution or evaluator success. The runtime still
  attempts scorer resolution and evaluation and records a score when available.
  If scorer resolution fails, `selected_score` is `null`, the selected ledger row
  records `score_status: "scorer_unavailable"`, and `selection_reason` is
  `single_candidate_contract_valid`. If scorer resolution succeeds but evaluation
  fails, `selected_score` is `null`, the selected ledger row records
  `score_status: "evaluation_failed"`, and `selection_reason` is
  `single_candidate_contract_valid`.
- If exactly one candidate validates its output contract and
  `require_score_for_single_candidate` is `true`, the candidate must produce a
  valid finite score or the step fails. Scorer-resolution failure fails the step
  with `error.type: "adjudication_scorer_unavailable"`; evaluator or evidence
  failure after scorer resolution fails the step with
  `error.type: "adjudication_partial_scoring_failed"`.
- If two or more candidates validate their output contracts, every output-valid
  candidate must produce a valid finite score from the same resolved scorer. If
  scorer resolution fails, the step fails with no promotion and `error.type:
  "adjudication_scorer_unavailable"`. If any output-valid candidate is unscored
  after scorer resolution and evaluator retries, the step fails with no promotion
  and `error.type: "adjudication_partial_scoring_failed"`. This preserves the
  rule that evaluator failure cannot silently remove an otherwise promotable
  candidate from comparison.
- If all output-valid candidates in a multi-candidate comparison have valid
  finite scores, the highest score wins. Ties are resolved by declared candidate
  order.

## Step Failure And Outcome Mapping

Successful adjudicated provider steps are recorded like successful provider
steps: `status: "completed"`, `exit_code: 0`, and `outcome` set to
`{status: "completed", phase: "execution", class: "completed", retryable:
false}`. Skipped steps keep the existing `when` false contract.

All adjudication-specific terminal failures are step-visible. Candidate-level
provider failures, evaluator failures, and evidence failures remain in
`steps.<Step>.adjudication.candidates` and ledger rows, but the logical step
also records one primary `error.type`, `exit_code`, and normalized `outcome` for
routing and workflow-output refs.

| Terminal condition | `error.type` | `exit_code` | `outcome.phase` | `outcome.class` | `outcome.retryable` |
| --- | --- | ---: | --- | --- | --- |
| No candidate produced output-valid declared artifacts after candidate retries | `adjudication_no_valid_candidates` | 2 | `post_execution` | `adjudication_no_valid_candidates` | false |
| Scorer provider, prompt, rubric, params, or scorer snapshot cannot be resolved when a score is required | `adjudication_scorer_unavailable` | 2 | `execution` | `adjudication_scorer_unavailable` | false |
| A required score is missing after scorer resolution because evaluator execution failed, timed out, returned invalid JSON, evidence was incomplete, evidence exceeded limits, or known secret evidence was rejected | `adjudication_partial_scoring_failed` | 2 | `execution` | `adjudication_partial_scoring_failed` | false |
| Logical adjudicated step deadline expires | `timeout` | 124 | `execution` | `timeout` | true |
| Static or dynamic score-ledger path collision with adjudicated dataflow paths | `ledger_path_collision` | 2 | `pre_execution` for static collisions before candidate launch, otherwise `post_execution` | `ledger_path_collision` | false |
| Existing non-empty workspace-visible ledger mirror belongs to a different owner tuple or is invalid JSONL | `ledger_conflict` | 2 | `post_execution` | `ledger_conflict` | false |
| Terminal mirror materialization fails after selection or promotion state is known | `ledger_mirror_failed` | 2 | `post_execution` | `ledger_mirror_failed` | false |
| Promotion destination differs from the baseline preimage before commit | `promotion_conflict` | 2 | `post_execution` | `promotion_conflict` | false |
| Parent output validation fails after commit and rollback completes | `promotion_validation_failed` | 2 | `post_execution` | `promotion_validation_failed` | false |
| Parent output validation fails after commit and rollback cannot safely restore the baseline | `promotion_rollback_conflict` | 2 | `post_execution` | `promotion_rollback_conflict` | false |
| Persisted adjudication state cannot be reconciled with the workflow, baseline, scorer, packet, ledger, or promotion manifest on resume | `adjudication_resume_mismatch` | 2 | `pre_execution` | `adjudication_resume_mismatch` | false |

Existing executor mappings still cover non-adjudication failures: loader
validation exits before execution, `when` false records a skipped result, consume
preflight failures remain `contract_violation` with exit code `2`, ordinary
provider/evaluator subprocess attempts use their provider exit codes in
candidate/evaluator metadata, and path-safety failures for authored surfaces use
the existing contract-violation shape unless one of the adjudication-specific
terminal conditions above is reached.

## Score Ledger

Every adjudicated provider step writes a run-local score ledger. When the
workflow declares `score_ledger_path`, the runtime also materializes an atomic
workspace-visible mirror.

Run-local path:

```text
.orchestrate/runs/<run_id>/adjudication/<frame_scope>/<step_id>/<visit_count>/candidate_scores.jsonl
```

The ledger row shape is normative. One row is materialized for each candidate
after selection is known, including candidates that failed before evaluation.
Rows are keyed by `score_run_key`. `candidate_run_key` identifies candidate
generation and is stable for one run, execution frame id, step id, visit count,
candidate id, candidate config hash, and composed prompt hash. `score_run_key`
identifies the ledger row and is stable for `candidate_run_key` plus the scoring
state: `scorer_identity_hash` and the evaluation packet hash when a packet
exists, `scorer_identity_hash` and the packet/evaluator failure metadata when
scorer resolution succeeded but evaluation failed before a score was accepted,
the literal status `scorer_unavailable` and `scorer_resolution_failure_key` when
no scorer snapshot exists, or the literal status `not_evaluated` when a candidate
was not output-valid and no packet was built. This prevents scores produced by
different evaluator prompts, rubrics, provider params, evidence contracts, or
scorer-resolution outcomes from sharing an idempotency key.

For adjudicated steps inside reusable calls, `workflow_file`,
`workflow_checksum`, provider namespace fields, `step_id`, `step_name`, and
artifact values describe the active callee workflow and call-frame-local step,
not the outer caller step. `execution_frame_id` ties the row back to the root
frame or durable `call_frame_id`.

Required fields:

```json
{
  "row_schema": "adjudicated_provider.score.v1",
  "score_run_key": "sha256:...",
  "candidate_run_key": "sha256:...",
  "run_id": "20260420T...",
  "workflow_file": "workflows/examples/...",
  "workflow_checksum": "sha256:...",
  "dsl_version": "2.11",
  "state_schema_version": "2.1",
  "execution_frame_id": "root",
  "call_frame_id": null,
  "step_id": "root.draft_big_design",
  "step_name": "DraftBigDesign",
  "visit_count": 1,
  "candidate_id": "codex_high",
  "candidate_index": 0,
  "candidate_provider": "codex",
  "candidate_model": "gpt-5.4",
  "candidate_params_hash": "sha256:...",
  "candidate_config_hash": "sha256:...",
  "prompt_variant_id": "draft_big_design_current",
  "prompt_source_kind": "asset_file",
  "prompt_source": "workflows/library/prompts/major_project_stack/draft_big_design.md",
  "composed_prompt_hash": "sha256:...",
  "candidate_status": "output_valid",
  "provider_exit_code": 0,
  "attempt_count": 1,
  "score_status": "scored",
  "scorer_identity_hash": "sha256:...",
  "scorer_resolution_failure_key": null,
  "evaluator_provider": "claude",
  "evaluator_model": "claude-opus-4-7",
  "evaluator_params_hash": "sha256:...",
  "evaluator_config_hash": "sha256:...",
  "evaluator_prompt_source_kind": "asset_file",
  "evaluator_prompt_source": "workflows/library/prompts/adjudication/evaluate_candidate.md",
  "evaluator_prompt_hash": "sha256:...",
  "evidence_confidentiality": "same_trust_boundary",
  "secret_detection_policy": "workflow_declared_secrets.v1",
  "rubric_source_kind": null,
  "rubric_source": null,
  "rubric_hash": null,
  "evaluation_packet_hash": "sha256:...",
  "score": 0.82,
  "selected": true,
  "selection_reason": "highest_score",
  "promotion_status": "committed",
  "summary": "Concrete, self-contained, and suitable for planning.",
  "failure_type": null,
  "failure_message": null,
  "candidate_root": ".orchestrate/runs/.../candidates/root/root.draft_big_design/1/codex_high",
  "candidate_workspace": ".orchestrate/runs/.../candidates/root/root.draft_big_design/1/codex_high/workspace",
  "output_paths": {
    "design_path": "state/.../design_path.txt"
  },
  "promoted_paths": {
    "design_path": "state/.../design_path.txt"
  },
  "created_at": "2026-04-20T12:00:00Z"
}
```

Nullable fields:

- `call_frame_id` is `null` for top-level workflow steps and non-null for
  adjudicated provider steps executed inside reusable-call frames.
- `candidate_model` is `null` when no model can be derived from provider params.
- `provider_exit_code` is `null` when the provider process was not launched.
- `scorer_identity_hash`, `evaluator_provider`, `evaluator_model`,
  `evaluator_params_hash`, `evaluator_config_hash`,
  `evaluator_prompt_source_kind`, `evaluator_prompt_source`,
  `evaluator_prompt_hash`, `evidence_confidentiality`,
  `secret_detection_policy`, and rubric fields are non-null after the scorer
  snapshot is resolved. They are `null` when no scorer snapshot exists: no
  candidate was output-valid, the step failed before scorer resolution, or scorer
  resolution itself failed. A row with `score_status: "scored"` or
  `"evaluation_failed"` must have non-null scorer identity fields. A row with
  `score_status: "scorer_unavailable"` must have null scorer identity fields,
  null `evidence_confidentiality`, null `secret_detection_policy`, null
  `evaluation_packet_hash`, null `score`, null `summary`, and non-null
  `scorer_resolution_failure_key`, `failure_type`, and `failure_message`.
- `scorer_resolution_failure_key` is non-null only for `score_status:
  "scorer_unavailable"`. It is a canonical hash over the evaluator provider
  reference, substituted evaluator params that were available before failure,
  evaluator prompt and rubric source descriptors, scorer contract versions,
  score-critical evidence limits, evidence confidentiality policy,
  secret-detection policy version, and normalized scorer-resolution failure type.
- `evaluation_packet_hash` is `null` only when no evaluation packet was
  persisted, such as `score_status: "not_evaluated"` or
  `"scorer_unavailable"`, or `score_status: "evaluation_failed"` before packet
  persistence because score-critical evidence was incomplete or contained a known
  workflow secret value.
- `score` and `summary` are `null` when evaluation did not produce valid score
  JSON.
- `promoted_paths` is `{}` for non-selected candidates and for selected
  candidates before promotion has committed or after promotion fails.
- `failure_type` and `failure_message` are `null` when candidate generation,
  evaluation, and, for selected candidates, promotion complete without terminal
  failure.

`candidate_status` values:

- `output_valid`: provider succeeded and declared outputs validated.
- `prompt_failed`: prompt preparation, dependency resolution, or consume-bundle
  materialization failed before provider launch.
- `provider_failed`: provider returned non-zero after retries were exhausted.
- `timeout`: provider timed out after retries were exhausted.
- `contract_failed`: provider exited zero but declared outputs failed validation.

`score_status` values:

- `scored`: evaluator returned valid score JSON.
- `evaluation_failed`: evaluator failed, timed out, returned invalid JSON, or the
  runtime could not build complete score-critical evidence after a scorer
  snapshot was resolved, including because known secret evidence was detected and
  rejected before packet persistence.
- `scorer_unavailable`: output-valid candidate could not be evaluated because
  scorer resolution failed before a scorer snapshot or evaluation packet existed.
- `not_evaluated`: candidate output was not valid, so evaluation was not run.

`selection_reason` values:

- `highest_score`: selected by highest finite score.
- `candidate_order_tie_break`: selected among tied highest scores by declared
  candidate order.
- `single_candidate_contract_valid`: selected because exactly one candidate was
  output-valid and single-candidate score was optional.
- `none`: not selected.

`promotion_status` values:

- `not_selected`: the candidate was not selected, or no selection was possible.
- `pending`: the candidate was selected but promotion has not reached a terminal
  state.
- `committed`: promotion committed and canonical parent output validation passed.
- `failed`: promotion reached a terminal failure.

Ledger materialization rules:

- Candidate terminal metadata is written under the parent run root as soon as a
  candidate provider/evaluator reaches a terminal state.
- JSONL ledger rows are first materialized after selection is computed, or before
  step failure when no selection is possible, so every row has a stable
  `selected` value. At this phase the selected row has
  `promotion_status: "pending"` and `promoted_paths: {}`. This materialization
  writes only the run-local ledger; the workspace-visible mirror is not written
  while promotion is pending.
- After promotion commits or reaches a terminal failure, terminal candidate
  metadata and the promotion manifest state are used to regenerate the run-local
  ledger atomically before the step returns completed or failed. A completed step
  must expose `promotion_status: "committed"` and populated `promoted_paths` for
  the selected candidate. A failed promotion must expose
  `promotion_status: "failed"`, `promoted_paths: {}`, and the promotion failure
  type/message.
- Resume regenerates the run-local ledger from terminal candidate metadata,
  scorer snapshot metadata or scorer-resolution failure metadata, evaluation
  packet metadata when present, and promotion manifest state, then suppresses
  duplicate `score_run_key` rows.
  The ledger is therefore idempotent even if the process stops while writing
  JSONL or between promotion commit/failure and terminal ledger materialization.
- `score_ledger_path`, when present, is substituted in the current execution
  frame, path-checked under the parent WORKSPACE, and must resolve under
  `artifacts/`. Absolute paths, `..`, and symlink escapes are rejected. Inside a
  reusable call, the mirror file is still a workspace-visible file, but it does
  not become caller-visible artifact lineage unless the callee explicitly exports
  it through the normal workflow-output/call boundary.
- The workspace-visible ledger mirror is an observability mirror, not a promoted
  output, and it is never allowed to alias step-managed dataflow paths. The
  runtime rejects `score_ledger_path` with `error.type:
  "ledger_path_collision"` if its resolved parent-WORKSPACE path equals or
  resolves through the same final path as any declared `expected_outputs.path`,
  `output_bundle.path`, required relpath target discovered from any
  output-valid candidate, selected promotion destination, or canonical pointer
  path for any relpath artifact named by this step's `publishes`. Static
  collisions are checked before candidate launch; dynamic relpath-target and
  promotion-destination collisions are checked after candidate validation and
  before selection can enter promotion. A collision check follows symlinks under
  the same parent WORKSPACE authority used by deterministic output validation.
- The workspace-visible ledger mirror is a single step-visit mirror, not an
  aggregate append target. Its owner tuple is `row_schema`, `run_id`,
  `execution_frame_id`, `step_id`, and `visit_count`. Before replacing an
  existing non-empty mirror, the runtime reads every JSONL row at the resolved
  path. Replacement is allowed only when every existing row is valid
  `adjudicated_provider.score.v1` JSON and has the same owner tuple as the
  terminal run-local ledger being materialized. An absent or empty mirror may be
  replaced. Any invalid JSONL, missing ownership field, different schema,
  different run, different execution frame, different step, or different visit
  fails with `error.type: "ledger_conflict"`. This also rejects two adjudicated
  steps or two reusable-call invocations in the same run reusing one
  `score_ledger_path` unless they are resuming the exact same step visit.
- The workspace-visible ledger mirror is replaced atomically from the terminal
  run-local ledger only during step finalization: after no-selection failure is
  known, after promotion reaches terminal failure, or after promotion commits and
  canonical parent output validation succeeds. For a successful promotion, mirror
  materialization occurs before normal `publishes` and before the completed step
  state is written, so a mirror failure cannot leave published lineage claiming a
  completed adjudicated step. It is not append-across-runs, append-across-steps,
  or append-across-visits in the first release. Authors who want retained history
  should include `${run.id}` and a step-specific component in
  `score_ledger_path` and aggregate separate run ledgers later.
- If terminal mirror materialization fails after promotion has committed, the
  promotion remains committed and the run-local ledger remains authoritative, but
  the step fails with `error.type: "ledger_mirror_failed"` and normal `publishes`
  are withheld. Resume retries terminal run-local ledger regeneration, mirror
  materialization, and then publication. If a no-selection or promotion failure
  has already made the step fail, a mirror failure is recorded under that failure
  context without masking the primary adjudication or promotion error.

The ledger is intentionally flat. It does not store component scores. Run-local
ledgers and workspace-visible mirrors are sensitive observability artifacts
because `summary`, `failure_message`, provider/model identity, artifact names,
and promoted paths may reveal information about the score-critical evidence.
Authors should place `score_ledger_path` only where that sensitivity is
acceptable; the mirror is never a declassification boundary.

## State Model

The normal current-frame `artifacts` field contains only promoted selected
outputs. Candidate outputs are not published into normal artifact lineage.

Stdout capture state is deliberately absent for adjudicated provider steps:

- Loader validation rejects `output_capture` and `allow_parse_error` on a step
  that declares `adjudicated_provider`. The ordinary default
  `output_capture: text` behavior for provider steps is suppressed.
- Candidate provider stdout/stderr and evaluator stdout/stderr are stored only as
  runtime-owned logs and non-scoring sidecars. The selected candidate's stdout is
  not projected into the current-frame step result and is not passed to the
  evaluator.
- A completed adjudicated provider step result does not populate
  `steps.<Step>.output`, `steps.<Step>.lines`, `steps.<Step>.json`,
  `steps.<Step>.truncated`, or `steps.<Step>.debug.json_parse_error`.
- Downstream substitutions that reference those stdout-derived fields are
  undefined under the normal variable model. Workflows that need downstream
  values from an adjudicated step must write and publish deterministic artifacts.

The selected candidate and candidate metadata are recorded under the step result:

```json
{
  "schema_version": "2.1",
  "steps": {
    "DraftBigDesign": {
      "status": "completed",
      "name": "DraftBigDesign",
      "step_id": "root.draft_big_design",
      "visit_count": 1,
      "artifacts": {
        "design_path": "docs/plans/example-design.md"
      },
      "adjudication": {
        "schema": "adjudicated_provider.state.v1",
        "execution_frame_id": "root",
        "call_frame_id": null,
        "selected_candidate_id": "codex_high",
        "selected_score": 0.82,
        "selection_reason": "highest_score",
        "promotion_status": "committed",
        "scorer_identity_hash": "sha256:...",
        "evaluator_prompt_hash": "sha256:...",
        "evidence_confidentiality": "same_trust_boundary",
        "secret_detection_policy": "workflow_declared_secrets.v1",
        "score_ledger_path": "artifacts/evaluations/...jsonl",
        "run_score_ledger_path": ".orchestrate/runs/.../adjudication/root/root.draft_big_design/1/candidate_scores.jsonl",
        "scorer_snapshot_path": ".orchestrate/runs/.../adjudication/root/root.draft_big_design/1/scorer/metadata.json",
        "promotion_manifest_path": ".orchestrate/runs/.../promotions/root/root.draft_big_design/1/manifest.json",
        "candidates": {
          "codex_high": {
            "score_run_key": "sha256:...",
            "candidate_run_key": "sha256:...",
            "candidate_status": "output_valid",
            "score_status": "scored",
            "score": 0.82,
            "selected": true,
            "promotion_status": "committed",
            "candidate_root": ".orchestrate/runs/.../candidates/root/root.draft_big_design/1/codex_high"
          },
          "claude_opus": {
            "score_run_key": "sha256:...",
            "candidate_run_key": "sha256:...",
            "candidate_status": "output_valid",
            "score_status": "scored",
            "score": 0.75,
            "selected": false,
            "promotion_status": "not_selected",
            "candidate_root": ".orchestrate/runs/.../candidates/root/root.draft_big_design/1/claude_opus"
          }
        }
      }
    }
  }
}
```

State schema boundary:

- DSL version `2.11` gates authoring and validation for `adjudicated_provider`.
- State schema remains `2.1`. The new `steps.<Step>.adjudication` payload is an
  additive step-result extension keyed by existing `step_id`, `visit_count`, and
  execution frame. In a reusable-call callee it is stored inside that
  call-frame-local `steps` map, not the caller-global `steps` map. It does not
  change top-level artifact lineage, call-frame storage shape, or run identity.
- Resume of an in-progress DSL `2.11` run requires a runtime that understands
  `adjudicated_provider`. Older runtimes reject the workflow version before
  interpreting adjudication state.
- If a later implementation moves candidate lineage into shared top-level state
  or changes existing artifact ledger meaning, that later feature must bump the
  state schema. This first release does not.

## Retry, Timeout, And Resume Semantics

Candidate execution is resumable at candidate granularity.

Timeout and retry rules:

- Step-level `timeout_sec`, when set, is a wall-clock deadline for one logical
  adjudicated step visit. The deadline starts after `when` and consume preflight
  succeed and covers baseline creation, candidate workspace copies, candidate
  provider subprocesses, evaluator subprocesses, retry delays, selection, ledger
  materialization, promotion, and final parent validation.
- Candidate and evaluator subprocess invocations receive only the remaining
  logical deadline as their timeout budget. The full `timeout_sec` is never
  restarted per candidate, per evaluator, or per retry attempt.
- If the deadline expires while a candidate or evaluator subprocess is running,
  the runtime terminates that subprocess using the existing provider timeout
  behavior and records the attempt as exit code `124`. If the deadline expires
  between subprocesses or during runtime-owned work, the runtime starts no new
  candidate, evaluator, ledger mirror, or promotion operation and fails the step
  with `error.type: "timeout"`, `exit_code: 124`, and the normalized timeout
  outcome.
- Step-level `retries.max` and `retries.delay_ms` apply independently to each
  candidate provider subprocess and each evaluator subprocess only while logical
  deadline remains. They do not retry the whole adjudicated step visit and do not
  retry promotion conflicts, ledger conflicts, or parent output validation
  failures.
- Separate candidate-timeout and evaluator-timeout fields are not part of the
  first release. Preserving `timeout_sec` as the logical step cap is the least
  surprising inheritance from ordinary provider steps; authors who need different
  budgets must split the work into separate steps or wait for a later explicit
  timeout surface.
- Each candidate provider retry starts from a fresh copy of the step visit's
  immutable baseline snapshot. Partial files from a failed attempt are not reused
  for a later attempt.
- Evaluator retries reuse the same evaluation packet. Evaluator retries never
  rerun the candidate provider.
- The score ledger has one row per candidate per step visit, not one row per
  retry attempt. Attempt details may be recorded in candidate sidecar metadata;
  the normative row records `attempt_count` and final status.

Resume rules:

- Candidate ids must be stable.
- Baseline snapshot metadata is part of the current execution frame's step visit
  state. On resume, an existing baseline is reused for all unfinished candidates
  and retries. If the baseline is missing while any candidate workspace,
  evaluation packet, terminal candidate metadata, or ledger row for the step visit
  exists, resume fails with
  `error.type: "adjudication_resume_mismatch"` unless the operator explicitly
  forces the step to rerun. If no adjudication state exists yet, resume may
  create the baseline from the current execution frame's preflight state as a
  normal not-yet-started step.
- Candidate sidecar metadata includes `candidate_run_key`,
  `candidate_config_hash`, and `composed_prompt_hash`. On resume, if the
  workflow checksum matches but the candidate config hash for an unfinished
  candidate differs from persisted metadata, the step fails with
  `error.type: "adjudication_resume_mismatch"` unless the operator explicitly
  forces the step to rerun.
- Scorer snapshot metadata includes `scorer_identity_hash`,
  `evaluator_config_hash`, `evaluator_prompt_hash`, optional `rubric_hash`, and
  the resolved base evaluator prompt/rubric content, evidence confidentiality
  policy, and secret-detection policy version. Once the scorer snapshot exists,
  resume uses that persisted snapshot for all unfinished evaluations in the step
  visit. If current authored evaluator provider params, evaluator prompt content,
  rubric content, evaluator contract version, packet schema version, evidence
  limits, evidence confidentiality policy, or secret-detection policy version
  would produce a different `scorer_identity_hash`, resume fails with
  `error.type: "adjudication_resume_mismatch"` unless the operator explicitly
  forces the step visit to rerun. The first release does not support partial
  rescore in place; changing scorer identity requires rerunning the step visit
  before selection or promotion can continue.
- Scorer-resolution failure metadata includes `scorer_resolution_failure_key`,
  normalized failure type/message, evaluator provider reference, substituted
  params that were available before failure, evaluator prompt and rubric source
  descriptors, scorer contract versions, evidence limits,
  `evidence_confidentiality`, and secret-detection policy version. Once
  persisted, resume uses that terminal scorer-resolution failure for row
  generation and selection/failure handling. If the current authored evaluator
  configuration would produce a different `scorer_resolution_failure_key` or
  would now resolve successfully, resume fails with `error.type:
  "adjudication_resume_mismatch"` unless the operator explicitly forces the step
  visit to rerun.
- If any terminal `score_status: "scored"` or `"evaluation_failed"` metadata, or
  any evaluation packet, exists without a matching persisted scorer snapshot,
  resume fails with `error.type: "adjudication_resume_mismatch"` to avoid
  comparing scores from different scoring functions. Ledger rows with
  `score_status: "scorer_unavailable"` require matching scorer-resolution failure
  metadata instead. Ledger rows with `score_status: "not_evaluated"` may have
  neither scorer snapshot nor scorer-resolution failure metadata when no
  candidate was score-eligible.
- Completed candidate workspaces, evaluation packets, and terminal candidate
  metadata are reused on resume unless the step is explicitly forced to rerun.
- If the run stops after candidate generation but before evaluation, resume
  evaluates remaining output-valid candidates with the persisted scorer snapshot,
  creates the snapshot first if no scorer state exists yet, or uses persisted
  scorer-resolution failure metadata to apply the selection/failure rules without
  inventing a scorer identity.
- If the run stops after evaluation but before ledger materialization, resume
  regenerates the ledger rows from terminal candidate metadata, scorer snapshot
  metadata or scorer-resolution failure metadata, and evaluation packet metadata
  when present.
- If the run stops after ledger materialization but before promotion, resume
  reuses recorded scores only after scorer identity has been verified, or reuses
  `scorer_unavailable` rows only after scorer-resolution failure metadata has
  been verified, then completes selection/promotion.
- If the run stops during promotion, resume follows the promotion manifest rules
  in the promotion section.
- If the run stops after promotion commits or fails but before terminal ledger
  materialization, resume regenerates the run-local ledger and workspace-visible
  mirror from terminal candidate metadata, scorer snapshot metadata or
  scorer-resolution failure metadata, evaluation packet metadata when present,
  and the promotion manifest before publishing or returning the failure.
- Failed candidates are not retried on resume unless the step visit itself is
  rerun under normal retry/force semantics.

## Validation Rules

Loader/schema rules:

- `adjudicated_provider` requires DSL version `2.11`.
- A step may specify exactly one of `provider`, `adjudicated_provider`,
  `command`, `assert`, `set_scalar`, `increment_scalar`, `wait_for`, `call`,
  `for_each`, `repeat_until`, `if`, or `match`.
- `adjudicated_provider.candidates` must be a non-empty list.
- Candidate ids must match the step id token pattern and be unique within the
  step.
- Candidate providers and evaluator provider must reference known provider
  templates in the active workflow's private provider namespace: the root
  workflow namespace for root steps, or the imported callee namespace for steps
  executing inside a reusable call.
- The step must declare exactly one of `expected_outputs` or `output_bundle`.
- The step must declare exactly one base prompt source, `asset_file` or
  `input_file`, unless every candidate declares its own base prompt source.
- Candidate prompt overrides may use one of `asset_file` or `input_file`, not
  both. Candidate prompt overrides may not define their own `consumes`,
  `depends_on`, `publishes`, `expected_outputs`, `output_bundle`, or
  `output_file`.
- Evaluator prompt source must use one of `asset_file` or `input_file`, not both.
- Evaluator rubric source may use one of `rubric_asset_file` or
  `rubric_input_file`, not both.
- Evaluator `evidence_confidentiality` is required and must be the literal value
  `same_trust_boundary`. It is not substitutable and has no default.
- Evaluator `evidence_limits`, when present, may define `max_item_bytes` and
  `max_packet_bytes` only. Both must be literal positive integers; string
  substitution in these fields is rejected. `max_packet_bytes` must be greater
  than or equal to `max_item_bytes`.
- `provider_session` is invalid with `adjudicated_provider` in the first release.
- `output_file`, `output_capture`, and `allow_parse_error` are invalid with
  `adjudicated_provider` in the first release; candidate stdout/stderr are always
  runtime-owned candidate logs and are not projected into step-visible stdout
  state.
- Evaluator output is always strict JSON and cannot use the step's
  `output_capture`, `allow_parse_error`, `expected_outputs`, or `output_bundle`
  settings.
- `selection.tie_break`, when present, must be `candidate_order`.
- `selection.require_score_for_single_candidate`, when present, must be boolean.
- `score_ledger_path`, when present, must be a workspace-relative path under
  `artifacts/` and must not collide with statically known step-managed output
  value files, output-bundle files, or published relpath artifact pointer paths.
  Collisions involving candidate-produced relpath targets or selected promotion
  destinations are runtime validation errors because those paths are known only
  after candidate output validation.
- The first release rejects adjudicated candidate-managed path fields whose
  substituted value depends on `${run.root}` or names the parent run root in
  parent-WORKSPACE coordinates. Candidate-managed paths are subsequently checked
  against the logical Candidate WORKSPACE authority, so physical nesting of the
  candidate workspace below the parent run root is not itself a violation.

Runtime rules:

- Consume preflight runs once in the current execution frame before creating one
  immutable candidate baseline snapshot for the step visit.
- Baseline creation uses `adjudicated_provider.baseline_copy.v1`; required
  orchestrator-managed paths excluded by that policy, including the fixed
  local-secret denylist, fail before provider launch.
- Candidates run in separate child workspaces with candidate WORKSPACE authority
  for orchestrator-managed paths, without claiming OS-level subprocess
  sandboxing.
- Every candidate workspace and candidate retry workspace is copied from the same
  immutable baseline snapshot.
- Candidate output-contract validation runs in the candidate WORKSPACE.
- The scorer snapshot fixes evaluator identity before scoring and is part of
  resume/idempotency checks. Scorer-resolution failure before a snapshot exists
  is represented separately from evaluator failure after a snapshot exists.
- Evaluator providers receive only complete score-critical evidence packets,
  including the exact rendered provider prompt that the candidate received with
  its output-contract suffix; score correctness must not depend on evaluator
  filesystem reads, runtime logs, bounded previews, or non-scoring sidecars, and
  incomplete score-critical evidence fails evaluation rather than allowing lossy
  scoring.
- Evaluator packets are persisted and sent only under the explicit
  `same_trust_boundary` confidentiality attestation. If score-critical evidence
  contains a non-empty workflow-declared secret value, packet persistence and
  evaluator launch are skipped and the candidate records
  `score_status: "evaluation_failed"` with failure type
  `secret_detected_in_score_evidence`.
- Adjudicated provider step state never derives `output`, `lines`, or `json`
  fields from candidate or evaluator stdout.
- Only output-contract-valid candidates are evaluated.
- Selection follows the single-candidate and multi-candidate rules above.
- Promotion uses the manifest/staging transaction described above and rejects any
  destination whose live parent preimage differs from the immutable baseline-time
  parent preimage.
- Only selected candidate outputs are promoted and published.
- A configured workspace-visible score ledger mirror is collision-checked against
  step-managed dataflow paths and is written only during terminal step
  finalization, never while promotion is pending. Existing non-empty mirror rows
  must all belong to the same `row_schema`, `run_id`, `execution_frame_id`,
  `step_id`, and `visit_count` owner tuple as the step visit being finalized.

## Versioning

This feature should be gated as DSL `2.11`. Workflows using
`adjudicated_provider` under earlier versions fail validation. Existing
`provider` steps and provider templates keep their current behavior.

State schema remains `2.1` for the first release because adjudication state is an
additive step-result extension and run-root sidecar contract. No existing state
file requires migration.

## Example Use Cases

- Draft the same big-design document with Codex and Claude, evaluate both, and
  promote the better design.
- Run one design-drafting provider, promote its valid output, and still record a
  non-blocking quality score when the evaluator is available.
- Try two prompt variants for a plan draft while keeping the downstream workflow
  unaware of the experiment.

## Future Extensions

- `max_concurrency` for parallel candidate execution.
- Command evaluators for deterministic score extraction.
- Source-edit candidate promotion through selected patch application.
- Candidate workspace overlays instead of full copies.
- Provider-session support inside candidate workspaces.
- Aggregate score-report tooling over per-run JSONL ledgers.
- Optional aggregate append-only ledger mode with cross-run duplicate
  reconciliation.
