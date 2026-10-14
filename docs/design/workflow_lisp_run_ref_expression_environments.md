# Workflow Lisp Run-Ref Confined Child Environments

- **Status:** proposed, unselected, unimplemented, and not copy-safe.
- **Kind:** architecture and authored-language extension.
- **Owner:** orchestration language/runtime maintainers; security acceptance also requires an independent isolation review.
- **Created / last material update:** 2026-10-14 / 2026-10-14.
- Revised 2026-10-14 after independent design review: Bubblewrap sibling profile, named-workflow locus, §8.1-aligned recovery.
- **Implementation target:** a future target, unassigned. No existing target is widened by this document.
- **Related plan:** [implementation and qualification plan](../plans/2026-10-14-run-ref-expression-environments-plan.md).

## Summary

Extend `run-ref` with a third program locus, `:program (:workflow <static-workflow-name>)`, whose child is a named workflow of the parent module graph, compiled by the ordinary closed-program pipeline as a private child entry. Each invocation materializes a pinned project revision, runs the child through the ordinary evaluated runtime inside a confined environment, and returns a typed outcome: the existing `value`, `workspace_delta`, and `accounting` envelope on completion, or a typed failure the parent can match on. Generating candidates, testing them, and selecting a result remain ordinary ORC composition.

The confinement substrate is the **existing rootless Bubblewrap backend**, extended as a sibling profile `run_ref_confinement.v1`: the rootfs is imported from a digest-pinned image into a sealed snapshot, the network namespace is unshared, cgroup v2 limits bound the child's processes, and every command and tool-enabled provider process of the child runs inside that boundary. An inference gateway grants bounded access to the selected remote model without exposing host credentials or host tools. This is a proposed, separately versioned security profile, not a claim that current `run-ref`, provider defaults, or the existing provider-isolation profile already supply this behavior. The approach removes workflow-owned clone/setup scripts and avoids a second evaluator, coordinator or container engine, and it makes ambient dependencies and arbitrary network access harder by construction: dependencies must be in the image and networking is explicit.

## Context And Authority

[The documentation index](../index.md) and [capability matrix](../capability_status_matrix.md) distinguish current support from historical E1 behavior. The governing contracts are:

| Authority | Constraint preserved or proposed amendment |
| --- | --- |
| [Program-search boundaries §§1–8](workflow_lisp_program_search_boundaries.md) | Immutable executing code, full compilation, registered children, honest OS isolation, typed operation kinds, neutral substrate, separated evidence. Confinement qualification (F3) is the positive isolation evidence required by §6. |
| [Runtime-closures boundary §§1–5](workflow_lisp_runtime_closures_boundary.md) | No runtime callable, source-string evaluation, provider-produced code identity, or implicit capability capture. A named static workflow introduces none of these. |
| [Evaluated execution §§4.2.1, 8.1, 8.4, 9.3.1, 9.4](workflow_lisp_evaluated_execution.md) | Native definition/configuration ownership, checked artifacts, memo authority and §8.1 rerun rules, `resume_request`/`result_root`, K4/K7/K8, the R2/R3 request contract. Every amendment is named in the identity section below. |
| [Agent sessions, persistence](workflow_lisp_agent_sessions.md) | The first-turn at-least-once rule for tool-enabled provider attempts and its scoped K4 exception govern confined provider recovery; PQ-1a owns the one shared qualification. |
| [Trial runs, E1](workflow_lisp_trial_runs.md) | Pinned materialization and typed result/delta/accounting remain useful substrate. Its shelf rule for inline subexpression children (synthetic entrypoints, 450–800 h) governs the `:body` deferral. Historical bundle/trial execution does not confer current admission. |
| [Security](../../specs/security.md) | Candidate copies are not sandboxes. `provider_phase_isolation.v1` has a specific rootfs/FD/launch contract; the sibling profile reuses its substrate and never claims to satisfy it. Setuid brokers are excluded for v1. |
| [State](../../specs/state.md), [IO](../../specs/io.md), [versioning](../../specs/versioning.md), [CLI](../../specs/cli.md), [DSL](../../specs/dsl.md) | Own final persisted schemas, result transport, target admission, public resume behavior and run-ref syntax after acceptance. |
| [Checked-program evaluation proposal](workflow_lisp_checked_program_evaluation.md) | A separate unselected dynamic-source proposal. This design neither depends on it nor admits generated ORC text as a child. |

Source inspection establishes the following, not a runtime qualification:

- `workflow_lisp/expressions.py` accepts a literal source and bundle/path locus; `closed/effects.py::_translate_run_ref` admits only path mode. `(:workflow ...)` is a new discriminator for both.
- `run_ref/closed_path.py::_require_closed_effects` requires empty direct/transitive effects and an empty site table. `evaluated_child.py::_terminal_value` requires a sole terminal memo entry and pure re-evaluation. Removing that guard would leave an invalid terminal proof.
- `run_ref/source.py` verifies the pinned revision and uses `git clone --no-local`; its setup runner executes on the host. That setup path must not provision this profile.
- `evaluated/run_ref.py` already exposes prepare/project/settle/reconcile around `run_ref/runtime.py` and its ledger. This remains the coordinator boundary. `run_ref/launch_authority.py` currently validates launch by reading the parent's protected authority through a retained FD. The current child state lives inside the clone. Neither that FD nor that state location can be exposed to candidate tools.
- `closed/build.py` closes definitions by demand and retains source/configuration owners. Compiling a non-exported workflow as a private entry needs no new extraction API; F1 proves it with the ordinary entry builder.
- `evaluated/interpreters.py:62` pins bare interpreters with `shutil.which`, which `authority.py` imports, and `effect_execution.py` substitutes those host paths. `evaluated/commands.py` also validates origins and constructs host IO paths. Confined dispatch needs image-owned executable identity and guest path translation.
- `run_ref/runtime.py` catalogs path leaves but returns child-relative paths; `WorkspaceDelta` contains metadata/diffs, not an exported file package. Automatic usable parent paths are new behavior.
- `providers/isolation_bubblewrap.py` builds the launch argv with user/ipc/pid/uts/cgroup unshare, FD-bound rootfs and candidate binds, `--clearenv` and a result scratch; it has no `--unshare-net`. `isolation_backend.py` holds the closed `_BACKENDS` registry (`:1567`), `CgroupV2ContainmentRoot`/`Slot` (`:2312`, `:2551`, membership and teardown only, no `memory.max`/`pids.max`/`cpu.max` writes) and `DurableLaunchReleaseGate` (`:2942`). `isolation_network_preflight.py` and `isolation_bundle_broker.py` are separate authorities not integrated with `ProviderExecutor`. `providers/executor.py:439` composes the provider environment from a copy of `os.environ` plus the supplied overlay; evaluated providers set only `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. `providers/registry.py:47–131` defines fixed host argv templates with no base-URL or configuration injection.

## Problem, Goals, And Non-Goals

The current child form cannot express a normal agent-edit/test workflow in a cloned workspace. Authors move clone preparation into shell commands or manual harnesses, and then must invent workspace identity, dependencies, cleanup, and result ownership. A directory change alone cannot safely admit a tool-enabled coding agent. The required flow is: take a pinned revision and candidate count; create independent pinned workspaces without workflow-owned provisioning scripts; run a named workflow containing ordinary provider calls, commands, calls, branches, and finite loops; obtain a typed candidate outcome and durable exported files; choose the best result in the parent; resume without replaying committed child work.

Non-goals are an optimizer/search engine, population/fitness primitives, automatic promotion, mutable workspace handles, a container-engine framework, source-string evaluation, runtime closures, dynamic imports, arbitrary setup hooks, package installation during a run, remote worker scheduling, and unrestricted networking. Generated project code may be executed by commands inside the confined environment; generated ORC is not admitted as executing workflow code by this feature.

## Decisions And Alternatives

**D1, substrate.** The existing rootless Bubblewrap backend (`bubblewrap.v1`; launch in `isolation_bubblewrap.py`; cgroup v2 containment slots; result broker) is the substrate of a new sibling profile `run_ref_confinement.v1`. Reason: it is installed on the reference host, reviewed, FD-bound at the root authority (`specs/security.md:38`) and rootless without setuid helpers, which security excludes for v1. It makes harder: image distribution has no engine, so the runtime imports images itself; supplementary-group dropping stays at what the existing profile proves; every new control is implemented and qualified in this repository. The `:image` operand stays a digest-pinned OCI image, but the runtime **imports** it into a content-addressed sealed rootfs snapshot through the existing snapshot assembly rules (closed canonical manifest, descriptor-relative, fixed-zero-atime); no container engine runs it. Stop condition: if F3 shows the profile cannot enforce network, limits or quota, the decision returns to design review with measurements; Podman is the recorded fallback.

What the existing profile cannot do today, and what the sibling profile adds: `--unshare-net` (absent from today's argv; `:none` and `:model-only` both require it); cgroup v2 `memory.max`, `pids.max` and `cpu.max` written on the existing containment slot; a rootfs taken from the imported image instead of the host provider closure; workflow commands admitted (today rejected); a workspace quota mechanism (a tmpfs-backed workspace whose pages are charged to the slot's `memory.max` and which outlives the attempt process so the host can read the quiescent tree, or admission refuses `:workspace-mib` as unenforceable); and public run/resume integration, which is still pending for the provider profile ([capability matrix](../capability_status_matrix.md), provider-phase isolation row).

**D2, locus.** The child program is a static named workflow, `:program (:workflow <name>)`, compiled by the ordinary closed-program pipeline as a private child entry with its own site table, owner configuration and effect summary. A `defworkflow` has explicit parameters, so `:inputs` bind to its signature exactly as mode 1 did and no free-variable, capture or shadowing machinery exists. `:body` (a compiler-extracted inline expression) is deferred under the trial-runs shelf: synthetic child entrypoints are its 450–800 h line item, and `:body` returns only when the shelf trigger, recurring documented authoring friction from wrapper workflows in real experiments, is documented. The retired `:bundle` capsule route stays retired; `(:workflow ...)` is a new discriminator and old `:bundle` artifacts are never reinterpreted. It makes harder: subexpression granularity costs a named wrapper workflow. One private child entry and one confinement profile owner are irreducible additions; no user-visible capsule, scope, broker, receipt, or workspace-management language is introduced.

| Alternative | Why it is not selected |
| --- | --- |
| Rootless Podman/OCI engine | Real advantages: image distribution and storage, supplementary-group dropping via `newgidmap`. Disadvantages: a large new trusted base (conmon, crun, pasta, storage, `containers.conf`, authfile); setuid `newuidmap`/`newgidmap`, which `specs/security.md` excludes for v1; path-based bind sources versus the FD-bound root authority; not installed on the reference host. Recorded fallback if F3 fails. |
| Only allow effects in path-mode children | Useful separately, but forces the caller's orchestration body into the candidate repository and mixes project revision with controller logic. |
| `:body` inline expression now | Deferred, not rejected: the shelf trigger above has not been documented; a named workflow gives the same granularity at about five lines. |
| A separate `with-workspace`/workspace handle primitive | Would expose mutable lifetime/ownership and let ordinary calls cross an environment boundary without a registered child run. |
| Put the whole evaluator inside a writable candidate container | Candidate tools could alter journal/compiler artifacts or interfere with the authority process. |
| New evaluator, worker service, or serialized code capsule API | Unnecessary. The existing closed program, child evaluator, memo, and coordinator own execution. |

## Authored Contract

`:program` accepts exactly one of `(:path ...)`, `(:workflow <name>)`; `:bundle` remains refused. For a workflow child:

```lisp
(run-ref
  :source (:repo "file:///srv/project.git" :commit revision)
  :program (:workflow candidate-body)
  :inputs (:task task :variant variant)
  :policy (:environment :confined
           :image "registry.example/project@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
           :network :model-only
           :limits (:wall-seconds 900 :memory-mib 4096 :cpus 2 :pids 256 :workspace-mib 2048 :output-mib 64)))
```

Image and limits are static literals. `:network` is exactly `:none` or `:model-only`; it never means general internet access. `:network :none` with any provider effect in the child's transitive summary refuses at compile time. All limits are positive bounded integers, checked against installation maxima; `:cpus` is an integer quota; `:output-mib` bounds exports only. The image must have a repository name and SHA-256 digest, without a mutable tag as authority; the imported snapshot digest and platform are recorded at admission. A digest alone does not promise bitwise deterministic computation or model responses.

**D4, source operands.** `:repo` stays a compile-time literal canonical locator exactly as today. Only `:commit` becomes a pure `String` expression, evaluated once in the parent in authored order before child allocation, validated as a 40-hex SHA, and included in the effect input digest. A changed revision is ordinary resume input drift; a repeated loop visit can select another validated revision. Reason: the locator is deployment configuration; the revision is search state. It makes harder: choosing among repositories at run time needs separate sites. Path-mode literals do not change.

`:inputs` is explicit keyword/value data transport. Its expressions run once in the parent in authored order and bind by name to the child workflow's signature with its ordinary exact-arity and type checks. `ProcRef`, provider roles as values, Context/session values, resources and other authority-bearing values cannot cross. Typed path inputs are copied and validated, not host mounts. `:returns` is not accepted; the result type is derived from the child signature.

**D6, child failure as typed data.** For this profile the form's type is a compiler-owned per-site union: `(COMPLETED (result <envelope>))`, where the envelope keeps the three existing fields `value`, `workspace_delta` and `accounting` (validated by `orchestrator/workflow/run_ref/result_contract.py`), and `(FAILED (code String) (detail String) (accounting <same>))` for child runtime failure, wall-time/budget exhaustion and environment refusal after release. The parent matches on it; one failed candidate does not abort the search. Structural, compile and admission failures before release still abort the parent effect under ordinary EE rules. Reason: a search must survive a lost candidate without authoring a second failure union per site. It makes harder: callers must match; a bare `.value` access no longer typechecks. Exact spelling is fixed with the contract amendments.

### Complete candidate-generation and selection module

This is complete illustrative future syntax. Every form except `run-ref :program (:workflow ...)` and its `:policy` compiles today at target 2.36 (verified: a variant in which `one-candidate` reaches `candidate-body` through `call` and matches a stand-in union compiled with the public `compile` command, exit 0, two sites). `NEXT_RUN_REF_TARGET` denotes the unassigned target and must not be replaced with a current target. Deployment supplies the ordinary provider binding manifest, here `{"providers.coder":"codex_unrestricted_workspace","providers.judge":"codex_unrestricted_workspace"}`; those profiles' bypass flags disable only the CLI's inner sandbox, and the outer profile is the boundary. The shown digest is illustrative; the repository is a literal locator and the revision is a typed run input. There is no shell provisioning command.

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "NEXT_RUN_REF_TARGET")
  (defmodule isolated_candidates)
  (export run)

  (defpath CandidateFile :kind relpath :under "artifacts" :must-exist true)
  (defrecord Candidate (file CandidateFile) (summary String))
  (defrecord Assessment (valid Bool) (score Float) (reason String))
  (defrecord CandidateResult
    (candidate Candidate) (assessment Assessment) (variant Int))
  (defunion CandidateOutcome
    (PRODUCED (result CandidateResult))
    (LOST (code String) (detail String)))
  (defrecord SearchState (best CandidateOutcome) (next Int))
  (defunion Selection
    (SELECTED (result CandidateResult))
    (INVALID (reason String)))

  (defprompt implement
    (:fills (task :text) (variant :value Int)) -> Candidate
    "Implement the project task in artifacts/candidate.py using the repository and the tools available here. Task: {task}. Candidate number: {variant}. Return the candidate file and a short summary.")

  (defprompt assess
    (:fills (task :text) (candidate :doc CandidateFile)) -> Assessment
    "Evaluate the injected candidate for this task: {task}. Use the project's tests and tools in this workspace. Return validity, a finite score where lower is better, and the reason for the score.")

  (defworkflow candidate-body ((task String) (variant Int)) -> CandidateResult
    (let* ((candidate
             (provider-result providers.coder
               :prompt (implement :task task :variant variant)))
           (assessment
             (provider-result providers.judge
               :prompt (assess :task task :candidate candidate.file))))
      (record CandidateResult :candidate candidate
        :assessment assessment :variant variant)))

  (defworkflow one-candidate
    ((revision String) (task String) (variant Int)) -> CandidateOutcome
    (let* ((child
             (run-ref
               :source (:repo "file:///srv/project.git" :commit revision)
               :program (:workflow candidate-body)
               :inputs (:task task :variant variant)
               :policy (:environment :confined
                        :image "registry.example/project@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                        :network :model-only
                        :limits (:wall-seconds 900 :memory-mib 4096 :cpus 2
                                 :pids 256 :workspace-mib 2048 :output-mib 64)))))
      (match child
        ((COMPLETED c)
          (variant CandidateOutcome PRODUCED :result c.result.value))
        ((FAILED f)
          (variant CandidateOutcome LOST :code f.code :detail f.detail)))))

  (defworkflow run
    ((revision String) (task String) (candidates Int :default 3)) -> Selection
    (if (or (< candidates 1) (> candidates 16))
      (variant Selection INVALID :reason "candidates must be between 1 and 16")
      (loop/recur
        :max 17
        :state (record SearchState
                 :best (variant CandidateOutcome LOST
                         :code "none" :detail "no candidate produced")
                 :next 0)
        :on-exhausted (variant Selection INVALID :reason "iteration limit")
        (fn (state)
          (if (>= state.next candidates)
            (done
              (match state.best
                ((PRODUCED p)
                  (if p.result.assessment.valid
                    (variant Selection SELECTED :result p.result)
                    (variant Selection INVALID :reason "no valid candidate")))
                ((LOST l) (variant Selection INVALID :reason l.detail))))
            (let* ((outcome
                     (call one-candidate :revision revision
                       :task task :variant state.next))
                   (best-beatable
                     (match state.best
                       ((LOST l) true)
                       ((PRODUCED b) (not b.result.assessment.valid))))
                   (best-score
                     (match state.best
                       ((LOST l) 0.0)
                       ((PRODUCED b) b.result.assessment.score)))
                   (better
                     (match outcome
                       ((LOST l) false)
                       ((PRODUCED p)
                         (and p.result.assessment.valid
                           (or best-beatable
                             (< p.result.assessment.score best-score))))))
                   (best (if better outcome state.best)))
              (continue
                (record SearchState :best best :next (+ state.next 1))))))))))
```

Each candidate gets a fresh clone; the two providers within that child share that clone, while each provider's HOME, process namespace and output scratch are invocation-private. The loop is serial and needs no parallel-map qualification. Ties keep the earlier result. A lost or invalid candidate leaves `best` unchanged, and `done` returns `INVALID` unless the best assessment is valid; the runtime never invents a successful candidate. The file returned to the parent is the exported `CandidateFile`, not a path into a live clone.

The judge is an ordinary provider with the candidate's trust level, not a sealed benchmark oracle. A research workflow still has to enforce the separate whole-candidate evidence and holdout rules in the program-search boundary. A deterministic checker can replace `assess` with an ordinary certified `command-result` installed in the immutable image, but candidate code loaded in the same process/UID can tamper with execution or forge the result channel. Such scores remain child-produced evidence unless a separately reviewed evaluator boundary protects its control, inputs and result channel from the candidate. That boundary is outside this proposal.

## Compiler And Configuration Ownership

The parent compiler resolves the named workflow in the parent's module graph, then builds it as a private child entry through the ordinary closed-program pipeline: reachable static functions, procedures, workflow calls, specialized hooks, types and prompt definitions keep their canonical owning modules; the entry has its own site table, source maps and inferred effect summary; it contains no runtime procedure value, no text to parse at invocation, and no live library lookup. The child need not be exported.

The full dependency closure, owner configuration, source snapshots, logical asset bases and compiler/runtime compatibility identity become an immutable child artifact contribution to the parent's checked program. Provider/command bindings are selected from these protected owning configurations; the clone cannot override manifests, provider registry, prompts or executable configuration. Project files remain workspace data, even if they happen to have `.orc` names. Child compilation uses the same frontend type/effect checks and closed read-back validation as an ordinary entry; do not copy closed nodes while keeping old site ids or reuse retired mode-1 data as permission.

The parent has one `run_ref` effect; the child summary is checked against environment-supported effects without erasing operation kinds. Workflow mode admits the selected target's ordinary pure forms, commands, portable tool-enabled provider calls and static calls, and refuses nested `run-ref`, dynamic evaluation, trial, human input, sessions/context capture, resource transitions and parallel effect execution inside the child. These refusals are transitive by effect kind through calls, procedures and hooks via the closed effect summary. Serial calls/loops provide the motivating flow; further classes require their own authority/recovery qualification.

## Runtime, Environment, And Provisioning

```text
parent evaluator / run_ref prepare-settle-reconcile
  -> verified pinned source + immutable child artifact + explicit input snapshot
  -> trusted child evaluator (host), private control root and memo
     -> pure evaluation and static calls
     -> confinement profile: sealed imported rootfs, containment slot, release gate
        -> bwrap command/provider process, --unshare-net, cgroup v2 limits:
           /workspace (this candidate, rw), /result (this attempt, rw),
           /tmp and HOME (private, bounded), model-only: unix-socket relay
  -> quiesce slot -> validate terminal and files -> export -> parent commit
```

The trusted child evaluator is an ordinary host runtime process under its existing child writer lock. It receives the checked child artifact and a runtime-owned, non-serializable execution environment binding: authority carried by runtime construction, not an ORC value. Direct child resume reconstructs it only from checked recorded authority and successful environment revalidation. A fallback to normal host command/provider execution is forbidden.

The image contains project dependencies and provider executables, not a competing ORC compiler. The host child evaluator never imports Python from the clone, sources its setup files, runs its hooks, or interprets its `.orc` files. Its private control root is outside the clone, with immutable program/config snapshots and its own run header/memo. Candidate `.orchestrate` is masked, as the existing launch already does; it is never child authority. Provisioning is runtime work: resolve the exact revision into the verified source store; import the exact image into the sealed snapshot store; allocate an independent detached clone; validate the baseline; copy explicit typed path inputs; allocate protected child state; then admit process execution. No `:setup` exists for workflow mode and this path must not call the existing host `_run_setup`. Image entrypoint scripts are not executed; the runtime selects the executable and sanitized argv/environment. Installation-time image preparation is outside an individual workflow run.

Host Git fetch/clone for this profile runs with a sanitized environment: no credential helpers, no SSH agent, no global/system Git configuration and no proxy environment; it reuses the existing source-materialization refusals. The materializer must leave no alternates, shared mutable object files, worktree links, executable hooks, host-bearing remotes or parent repository links reachable from the mounted clone; `--no-local` alone is not the complete security proof. Submodules and LFS stay rejected under current policy. A self-contained sanitized `.git` is a separate read-only mount for local diff tools; candidate commits are not part of this profile. The parent checkout and the mirror are never mounted. Host delta collection uses the existing tree-manifest/difflib path, never repository-controlled Git hooks, filters, external diff or configuration.

The provider and command adapters share one confinement launch boundary. Existing request rendering, ordinary memo attempts, command repeat policy, provider result validation and result-bundle transfer remain their owners. Namespace translation maps only the verified candidate root and the current attempt's result scratch. Host absolute paths, run-root FDs, ancestor directories, sockets other than the relay, and host interpreter pins never cross. R2/R3 take a guest spelling for confined attempts: `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` and the prompt's `- path:` line both name `/result/<attempt-relative>`, so prompt identity for confined attempts differs from host attempts by design at the new target. After process quiescence the result broker copies validated bytes into the protected attempt. Forms that would export a private runtime result path, in particular `provider-bundle-path`, refuse at compile time inside confined children with `run_ref_child_transport_unsupported`; the child's `result_root` records the external control root.

Confinement also applies when the trusted host reads candidate-controlled files. Before every host-side `:doc` fill, dependency/closure/input check, result import or delta scan, the previous leaf's containment slot must be quiescent; a provider that leaves a background tool behind has not completed. Keep the candidate root descriptor and read through the existing secure workspace-IO owner, validating beneath-root/no-follow traversal, regular file kind, bounded bytes and unchanged root identity. A returned typed path is untrusted input to that reader. If current secure IO cannot enforce these constraints across all readers, extending that shared owner is a blocking prerequisite. Confined child headers use versioned **image executable pins**: snapshot digest/platform, guest executable path and immutable executable/config closure. Host `shutil.which`, host package-origin checks and host absolute interpreter substitution do not authorize them. Resume validates the pins and rejects drift before dispatch. Ordinary host runs retain their current pin schema. Each provider timeout is clamped at dispatch to the remaining child wall budget.

## Isolation, Credentials, And Resource Contract

`run_ref_confinement.v1` is a sibling security profile requiring a versioned amendment in `specs/security.md`. It does not select, rename or weaken `provider_phase_isolation.v1`, and it is **not registered in `_BACKENDS`**, so it can never satisfy a `provider_phase_isolation.v1` request. The concurrent open provider-isolation integration (capability matrix, provider-phase isolation row: executor ownership/routing, lifecycle, run/resume, attestation) is a coordination constraint on executor routing: both profiles route through one executor seam, and neither may be integrated by special-casing the other.

Required positive evidence covers unprivileged host launch through the existing fixed `bwrap` authority; private user/PID/mount/IPC/UTS/cgroup/network namespaces; all capabilities dropped; no privilege gain; sealed read-only imported rootfs; bounded temporary mounts; no inherited host descriptors; a positive mount allowlist; `memory.max`/`pids.max`/`cpu.max` enforced on the slot; workspace quota enforced; and slot quiescence before result import. Host `/`, home, parent/peer workspaces, cloud credentials, SSH agents, engine sockets and orchestration state are absent. Reuse `DurableLaunchReleaseGate` for the durable release fact, `CgroupV2ContainmentRoot`/`Slot` for containment and quiescence, the result broker for transfer and `isolation_network_preflight.py` for the denied-endpoint inventory.

Tool-enabled provider processes run inside the same confinement as commands. Their child shells, filesystem tools, plugins and subprocesses cannot leave it. Provider CLI flags that bypass internal approvals do not establish outer isolation. A normal authenticated host SDK process is not a permitted alternative. For `:none`, commands and providers get no network. For `:model-only`, the network namespace is still unshared and only a bound unix socket enters the sandbox; it relays to a host-owned inference gateway that accepts only the admitted provider/model API operations with request/response byte limits, an attempt-bound capability, expiry and token/cost/request ceilings from installation policy. It chooses a fixed configured upstream; no arbitrary URL, CONNECT proxy, redirect authority, host tool call, filesystem API or credential read is provided. The capability is revoked when the attempt stops and is excluded from durable artifacts.

**D7, inference gateway prerequisites**, each unbuilt today: a per-attempt environment/config overlay outside R8/R10 (evaluated providers set only `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, and the executor copies `os.environ`); profile-specific provider template variants (`registry.py` templates are fixed host argv with no base-URL/config injection); telemetry and non-model traffic disabled; a unix-socket relay bound into the sandbox, because `--unshare-net` leaves only a bound socket and neither CLI speaks HTTP over a unix socket; a gateway implementing the streaming Responses/Messages APIs the CLIs use; API-key accounts only, because OAuth file passthrough (`~/.codex/auth.json`, `~/.claude/.credentials.json`) is forbidden, which may change billing and model availability. Reason: these are the concrete gaps between today's executor and a confined provider; naming them prevents a mounted-home shortcut. It makes harder: providers arrive later than commands. **Increment A: confined commands and `:network :none`; providers refuse with `run_ref_provider_transport_unavailable`** until F4 passes, so the profile can be admitted before transport is qualified.

Resource enforcement includes CPU, memory, process count, cumulative child wall time, workspace/scratch bytes, exported bytes/file count/depth, and bounded stdout/stderr. Post-run `du` is insufficient. Resume charges elapsed/resource/provider budgets to the existing child, not a fresh allowance. An oversized artifact, fork bomb, lingering daemon, output flood, decompression bomb or failed quiescence cannot proceed to export. **D8:** protected evidence snapshots are charged against a separate installation-policy evidence allowance, checked at each effect commit before the next dispatch, never against the author's `:output-mib`, which covers exports only; reason: evidence size is a runtime property authors cannot predict. It makes harder: two allowances to explain. Limits and effective kernel settings are retained in admission evidence.

## Results, Paths, And Lifetime

Preserve the envelope's three fields. Pure scalar/record/union/list/map values cross through the existing canonical descriptor checks. `.workspace_delta` remains a normalized bounded baseline-to-final description, not authority to read arbitrary clone files. `.accounting` includes the existing child accounting and actual provider usage; unavailable usage is explicit, not zero. For this profile the `RepositoryRevisionId` setup component is the literal `none` and `setup_ms` is `0`; the image digest belongs to environment admission, not the revision id.

**Chosen path rule: export copies while preserving the original declared root.** Every recursively returned path leaf is an explicit artifact declaration, as in current run-ref. This profile admits output path descriptors only when they have a nonempty workspace-relative `:under` root outside reserved control/Git roots and `:must-exist true`; a descriptor with `:must-exist false` refuses at compile time with `run_ref_child_transport_unsupported`. Each returned path must exist, stay below that declared root, and identify a regular file or bounded directory tree without symlinks, special files, unsafe hardlinks or nested mounts.

For a child path `artifacts/candidate.py` of nominal `CandidateFile :under "artifacts"`, the runtime copies into:

```text
artifacts/.run-ref-exports/<parent-run>/<activation>/<attempt>/candidate.py
```

The suffix is the original path relative to its own descriptor's `under`, and the destination is below that same `under`. Identical child paths share one copied object; conflicting descriptors/roots or destinations refuse. The compiler rejects a descriptor whose refinements cannot survive this mapping; the boundary validator independently checks the original child value and the rebased parent value against the same complete descriptor. This is not generic string prefix replacement or a nominal cast. The host performs export after the slot is quiescent, using retained roots, no-follow traversal, exact byte/count limits and atomic no-overwrite publication. Parent destinations are reserved per run/activation/attempt, cannot overwrite existing user files, and are recorded in the same settlement proof as child original paths, result field locations, sizes and digests. A corrupted or missing export refuses; it is not regenerated by rerunning a child. Exports live for the parent run's lifetime and are removed with run deletion/invalidation; the example README recommends ignoring `.run-ref-exports` in VCS. Input paths follow the converse rule: copy explicitly declared bytes into a child-owned location still satisfying each input descriptor, reject unsafe links and revalidate before launch.

After terminal validation, export and successful parent settlement, the existing run-ref coordinator initiates deletion of the settled workspace, recording cleanup intent/completion in the ledger under the parent writer lock; it first revalidates the exact owned root and quiescence and never deletes a pending/live workspace. Protected child artifact/header/memo, environment admission, baseline/final manifests, delta, accounting, export manifest and committed exported bytes are kept for the parent run's retention lifetime and suffice for settled reuse without the clone. Cleanup failure retains the workspace and records a pending obligation. **Completed-resume cleanup amendment** to `specs/cli.md` ("a completed run resumes to its recorded terminal with exit 0 and no write"): a completed run with a recorded pending cleanup obligation retries it on resume and records the outcome; otherwise no write. No new GC command or retention framework is introduced.

## Lifecycle, Cancellation, And Recovery

Keep one `run_ref` effect class, one visit identity derived from the parent's semantic site/activation, one `run-ref-attempts.jsonl` owner, and the existing prepare → parent memo commit → settle protocol. Workflow mode uses `run_ref_static_config.v2` with its checked child contribution, operand schema and `run_ref_confinement.v1` policy. The resolved revision is an ordinary reached effect input. Version the private request/proof and discriminate recovery by validated profile; old ledger rows keep their meaning. Allocation durably binds resolved revision, child artifact/config, inputs, environment, child run id, workspace/control roots and cumulative budget before releasing candidate processes. Each child effect launch gets an attempt-bound containment identity and a durable release fact through `DurableLaunchReleaseGate`; the inventory distinguishes allocated-but-not-released from possibly released before adopting, cancelling or retrying.

**D3, pending-effect recovery.** Confined children follow EE §8.1 and the agent-sessions amendment rather than a new stop code. A `started`/`failed` child attempt with no commit reruns on resume unless its boundary declares `must_not_repeat`, after the existing C4 implementation-file drift checks; tool-enabled provider attempts follow the agent-sessions first-turn at-least-once rule, qualified once under PQ-1a. Reason: the runtime already owns an at-least-once contract with drift checks; a second rule for the same attempts would fork recovery semantics. It makes harder: an interrupted tool-enabled attempt may repeat its tool work in the same clone; the clone is not transactional.

| Interruption point | Recovery for `run_ref_confinement.v1` |
| --- | --- |
| Before any child effect is released | No live process or release fact: discard and retry provisioning under today's K4 (fresh allocation). |
| After release, no child effect committed | Reconcile containment identity and quiesce the slot under the writer lock. Today's K4 applies: the child may be discarded and reallocated, or resumed; `invalidate` remains available. |
| After release, at least one child effect committed, child incomplete | Retain the same child run and workspace. Quiesce orphan work, then resume the child's ordinary memo: committed effects are reused, the pending attempt follows §8.1 (rerun unless `must_not_repeat`), budgets are cumulative. |
| Child terminal durable, export absent or partial | Revalidate the same terminal, reserve/reuse the same export destinations and finish atomic publication from the quiescent workspace. Never dispatch a child effect to rebuild it. |
| Child terminal and export prepared, parent has no commit | Revalidate retained terminal/export evidence and prepare the same value for the parent commit. |
| Parent committed, not settled | Validate the inline proof and finish existing settlement without launching a child. |
| Parent settled, clone removed | Reuse protected child/proof/export authority; no clone or provider launch is required. |
| Cleanup obligation pending after completion | Retry the recorded cleanup on resume and record the outcome (completed-resume cleanup amendment). |

**K4 amendment scope:** a confined child with at least one committed effect is never discarded; a confined child with zero committed effects keeps today's K4. **K8:** no-supersession applies from the first committed child effect, not before; `invalidate` stays available while no child effect has committed. Starting an explicitly new top-level run is distinct from recovering this run and claims no rollback. Missing authority, containment identity ambiguity, tampered memo, inconsistent release facts or lost control state fail closed with the retained evidence intact.

The terminal proof replaces the pure-child sole-terminal test only for this profile. Capture protected header, checked artifact and complete memo prefix once under retained roots; require a completed terminal, valid committed-effect proofs and no unfinished/unsettled effect. Replay pure control with the ordinary evaluator and those committed values, matching every reached commit in order by site/activation/input authority from retained attempt snapshots, without dispatch, reconciliation or reading mutable clone dependencies. Check canonical equality of replayed halt, terminal value and the child's direct typed result, and bind that evidence to the parent settlement before path export transforms the value. Before clone cleanup, preserve the exact result bytes, bound input values, rendered prompt/dependency snapshots, command closure/input witnesses and configuration assets the shared read-only validators require, charged to the evidence allowance (D8). Missing snapshots block settlement/cleanup rather than being reconstructed from current source.

Cancellation and wall-time exhaustion first stop the registered child and every slot member, revoke the model capability, prove quiescence, and then record the outcome: `FAILED` to the parent when the child cannot continue, or a pending child under the table above. If the controller dies, recovery inventories its recorded containment identities; a stray member never justifies allocating a replacement child.

## Semantic Identity, Source Maps, And EE Amendments

Parent program identity covers the child workflow's canonical definition, its signature, canonical dependency/configuration closure and image/policy literals. Runtime input identity additionally binds the resolved revision, explicit inputs and path content snapshots. Child admission binds verified Git tree, materialization policy, imported snapshot digest/platform, executable/config closure and profile version. Source paths/line numbers remain diagnostic provenance, not identity. Each loop/call activation has a distinct K7 visit, even for identical inputs; the child's sites are its own and never alias the parent's.

**D5, named EE amendments.**

| Amendment | Scope |
| --- | --- |
| K4 | As D3: committed child effect present, never discarded; none, today's K4. |
| §8.4 `resume_request`, child-recipe variant | A confined child has no `workflow_file`/`source_roots`; it records the parent-bound child artifact identity instead, and the fresh-build comparison is replaced for the child by validation of the stored checked artifact. Parent public resume keeps the ordinary fresh build/comparison. |
| X4 / `result_root` | `provider-bundle-path` refuses at compile time inside confined children (`run_ref_child_transport_unsupported`); the child's `result_root` records the external control root. |
| R2/R3 guest spelling | `/result/<attempt-relative>` in the provider/command environment and in the prompt's `- path:` line for confined attempts; prompt identity differs from host attempts by design at the new target. |
| Internal run-reference target (EE line "remains 2.35") | Confined children compile at the new target; path children keep 2.35. |
| K8 | No-supersession from the first committed child effect. |

## Diagnostics And Contract Changes

Reuse existing compiler/type, source-materialization, input-drift, memo-consistency, result and signature diagnostics where their meaning is unchanged. New codes name the boundary:

| Code | Refusal point / meaning |
| --- | --- |
| `run_ref_child_target_unavailable` | Compile: unselected/older target or unsupported representation. |
| `run_ref_child_transport_unsupported` | Compile/admission: authority value as input, `provider-bundle-path`, or a result path descriptor that cannot be exported (`:must-exist false`, reserved root). |
| `run_ref_environment_effect_unsupported` | Compile/admission: forbidden nested effect (transitive), `:network :none` with a provider effect, configuration, package origin or runtime-path access. |
| `run_ref_environment_unavailable` | Pre-release: `bwrap`, cgroup delegation, quota, network unshare or image import prerequisite unavailable. |
| `run_ref_environment_changed` | Resume preflight: snapshot/platform, profile, executable or fixed config differs. |
| `run_ref_environment_escape_rejected` | Admission/export: mount, path, descriptor, network or process authority exceeds the grant. |
| `run_ref_provider_transport_unavailable` | Before provider dispatch: gateway/relay integration not qualified (Increment A). |
| `run_ref_budget_exhausted` | Enforced resource/elapsed/output/evidence allowance reached; prior effects retained; surfaces to the parent as `FAILED` after release. |
| `run_ref_export_invalid` | Quiescent export or reuse: invalid/missing/oversized artifact or failed typed rebase. |

Diagnostics identify the site, child/attempt and failing obligation without exposing credentials or host paths to candidate output. A compile failure precedes any child allocation; runtime admission failure precedes candidate process release. Provider stderr is bounded evidence, not the typed result.

## Evidence, Dependencies, And Implementation Boundaries

These are required feasibility proofs, not claims of existing support:

| Gate / owner | Required witness | Stop condition |
| --- | --- | --- |
| F1 child entry closure / compiler | A non-exported named workflow with imported owner config, static calls and explicit inputs compiles as a private child entry with independent sites and source maps; ordinary compile and checked read-back agree. | Needs copied unchecked IR, reopening live imports or another evaluator. |
| F2 authority separation / runtime | The same ordinary child evaluator runs commands/providers through one environment seam; guest IO/image pins work while control roots remain outside all mounts/descriptors. | Any host effect fallback, host interpreter substitution, writable authority or candidate-origin host import. |
| F3 confinement / security | Real rootless `bwrap` launch of the sibling profile proving `--unshare-net`, cgroup limits, imported-image rootfs, admitted commands, workspace quota and escape negatives. | Configuration inspection or exit codes are the only evidence; a limit or quota is unenforceable (Podman fallback, back to design review with measurements). |
| F4 provider transport / provider owner | Real coding-agent tools edit a candidate inside the profile and return a typed result through the gateway relay; host credentials/control/peer canaries remain inaccessible. | Only text-only calls succeed, an account home/token must be mounted, or provider tools execute on host. |
| F5 recovery / memo and run-ref owners | Public external kills before release, before and after the first child commit, at child terminal, after export and around parent commit; same child id after the first commit, preserved committed prefix, §8.1 rerun of the pending attempt. | K4 discards a child with a committed effect, or a commit is invented from a result file. |
| F6 typed exports and retained terminal proof / path owner | Nested path types retain exact nominal refinements; no-overwrite bounded export; clone deletion followed by read-only settled resume from retained evidence. | Result type changes silently, replay needs mutable clone files, or export trusts child-supplied paths. |

Existing provider-isolation helpers are reused only after their exact authority assumptions are checked; the sibling profile never fabricates the provider profile's attestation. The host's available tools do not establish a working confined environment. No confined execution, provider integration or malicious-workspace check was run to produce this design; only the compile check named above was run.

## Compatibility, Migration, And Deletion

Assign the language target and wire versions only after the acceptance decisions. Keep existing path source/manifest-null/pure-child validation and old-run read-back unchanged. New operands, child artifacts, environment headers, image pins, external control roots, typed exports and the K4 refinement are versioned together; mixed/unknown records refuse. Never rewrite old run evidence to claim confinement or adopt an old child into the new profile.

Migrate the maintained best-of-N workflow/example from preprepared workspace paths and shell clone/setup to the revision input and this workflow locus. Remove the displaced maintained shell provisioning commands/helpers once consumer inventory proves they are unused. Historical experiment harnesses remain historical evidence. Do not migrate unrelated demos or remove the independently useful path mode. There is one child compilation route and one runtime lifecycle. Do not retain a workflow-to-old-bundle adapter, a second coordinator, a configurable unsafe fallback, or duplicate path parsers/brokers after integration. There is no feature flag that runs the same child on the host. Rollback means declining the new target/profile while retaining read-only diagnostics for its recorded artifacts.

## Verification And Declarative Acceptance Scenarios

1. **Normal tool-enabled flow.** Given a real pinned image containing the qualified provider CLI and project dependencies, a local pinned fixture repository, and the complete module above with three candidates, invoke public compile/run. The parent returns a typed selection, three distinct child registrations/workspaces, ordinary provider attempts, a bounded delta/accounting for each, and a selected exported file under its declared `artifacts` root. No provisioning command is present in the authored workflow. A deterministic local inference service may provide reproducible CI responses, but a separately recorded real remote-model run is required for transport qualification.
2. **Independent environments.** Each child writes the same candidate filename. Every child starts from the same baseline, sees no peer/parent/control canaries, and its file contents cannot affect the next child. Execute a tool that attempts parent/home/socket/metadata-network access, forks descendants, fills the workspace and emits excess output. Enforcement, not prompt obedience, prevents access and bounds the work; the parent observes `FAILED` for the exhausted candidate and continues. A candidate that forges a schema-valid score still yields only labelled child-produced evidence.
3. **Recovery across the commit gaps.** Publicly kill the controller before the first child commit, after a committed child provider, after child terminal/export preparation, and after parent commit but before settlement. Before the first commit, resume may reallocate under today's K4; afterwards it preserves child id and committed call counts, and the pending attempt reruns under §8.1 unless its boundary declares `must_not_repeat`. No whole-child replay is accepted as equivalent.
4. **Typed export and retention.** Return records/unions/maps containing aliases of the same `CandidateFile`. Verify exact transformed values, duplicate identity handling, field lineage and no-overwrite writes. The coordinator deletes the settled clone; public completed resume returns the same value without dispatch. Inject a cleanup failure and verify the next resume only retries the recorded cleanup. Tampered export, traversal, symlink, special file, reserved root, `:must-exist false` and incompatible refinement each refuse. An agent-written candidate symlink to a host canary also refuses at the next prompt `:doc` read, before any host bytes reach the provider.
5. **Authority and compatibility.** Change image/provider configuration/child definition/declared input before resume; refuse before dispatch. Blank-line/source relocation preserves identity. Read old path-child runs under their unchanged semantics. Forge a new-profile header/request or inject a parent FD into the launch; reject before process release. Request the sibling profile through `provider_phase_isolation.v1`; refuse as an unsupported backend.

Use narrow compiler/run-ref/provider/path tests first; collect newly added/renamed modules. Run at least one public orchestrator smoke and the end-to-end real confinement/provider scenarios because this crosses DSL/runtime/process boundaries. Broader pytest uses `pytest -q -n 16 --dist=worksteal` in tmux. Preserve classified pre-existing failures; neither mocks nor prose checks replace the positive isolation and crash evidence. Tests assert behavior, lineage, authority and typed outcomes, never literal prompt wording. Success requires these witnesses through the default public route, retained compatibility evidence, independent design/security/code review, and the maintained no-shell provisioning example. Stop/revise if there is no safe provider gateway, no enforceable workspace/resource limit, no compatible image-owned executable model, or no way to recover without repeating committed work. Increment A is a legitimate partial delivery and must be labelled as such.

## Documentation Impact And Implementation Handoff

After selection, update `specs/dsl.md` (run-ref syntax), EE lifecycle/K4/K7/K8 and §8.4/§9.4 amendments, security's sibling profile, state/IO/versioning/CLI contracts, capability matrix, design routing, drafting guide and the maintained best-of-N recipe. Keep the program-search and runtime-closure boundaries intact.

| Owner surface | Scoped change |
| --- | --- |
| `workflow_lisp/expressions.py`, WCC payload/conversion, `specs/dsl.md` | `(:workflow ...)` discriminator, `:commit` expression operand, `:policy` schema, result union typing. |
| `workflow_lisp/closed/build.py`, `closed/effects.py`, `closed/names.py`, `closed/artifact.py`; `contracts/closed_program` validators; run-ref config/result/wire | Private child entry compilation, dependency/config ownership, identity, source maps, transitive effect refusals; checked child contribution, versioned profile/config/request/proof, exact read-back. |
| `workflow/run_ref/source.py`, `workspace.py`, `delta.py` | Sanitized Git environment, safe materialization/input copies, no host setup, quiescent manifests and export metadata. |
| `workflow/run_ref/runtime.py`, `ledger.py`, `launch_authority.py`, `child.py`, `evaluated_child.py`, `evaluated/run_ref.py` | One lifecycle, external protected child root, terminal proof, §8.1 recovery, cancellation, cleanup obligation and settlement. |
| `workflow/evaluated/authority.py`, `interpreters.py`, `effect_execution.py`, `commands.py`, `providers.py`, child publisher/runner | Environment-bound execution seam, image pins, guest/result paths, timeout clamp, no host fallback. |
| `orchestrator/workflow/run_ref/confinement.py` (new) | Image import to sealed rootfs, admission, limits/quota, launch through the existing backend substrate without `_BACKENDS` registration. |
| `orchestrator/providers/inference_gateway.py` (new), `providers/executor.py`, `providers/registry.py` | Narrow model-only gateway and relay; per-attempt overlay; profile-specific template variants. |
| `tests/test_workflow_evaluated_run_ref*.py`, compiler/provider/path owner tests and real confinement fixtures | Public success, escape negatives, commit gaps, typed exports and legacy compatibility. |

The safe first work is Increment A through ordinary compiler/runtime interfaces: F1 and F2, then F3 with real rootless launch and explicit failure outcomes. The plan should gate provider transport (F4), recovery (F5) and typed export (F6) on those proofs before claiming the complete feature. General networking, nested children, parallel-map qualification, `:body`, dynamic generated ORC and search-library design remain separate. If any proof needs a different authority topology, return the decision to design review before implementation proceeds.
