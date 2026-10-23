# Durable Host Input And Python Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The coordinator owns integration and final verification; use a reviewer distinct from each author.

**Goal:** Deliver typed, durable human decisions through native Lisp `request-input` and Python `ask`, with one evaluated runtime, public settlement API, CLI, observational surfaces, and deterministic recovery evidence.

**Architecture:** Add target 2.40's `request_input` effect to the existing checked program, effect memo and replay protocol. Implement the bounded Python frontend by tracing declarations into immutable ordinary `.orc` and passing supplied manifests unchanged to the existing compiler/run path. This makes arbitrary Python control flow and multiple simultaneous host requests unavailable; adding either later requires its own contract rather than another execution engine.

**Tech Stack:** Existing Python 3.11 package, Workflow Lisp frontend/WCC, checked closed programs, append-only JSONL memo, descriptor-relative `WorkspaceFiles`, existing run locks, pytest and pytest-xdist. No new dependency or provider expenditure.

---

## Role, authority and selection

This is the selected implementation plan and decision/evidence ledger. It is
not current runnable guidance until its implementation and verification steps
are complete. The behavioral owners are
[durable host input](../design/workflow_lisp_durable_host_input.md) and
[Python authoring](../design/workflow_python_frontend.md), read with
[evaluated execution](../design/workflow_lisp_evaluated_execution.md),
[state](../../specs/state.md), [CLI](../../specs/cli.md),
[IO](../../specs/io.md), [security](../../specs/security.md) and
[documentation conventions](../documentation_conventions.md).
Start routing at [docs/index.md](../index.md); check the
[capability matrix](../capability_status_matrix.md) before claiming support.

Work only in `/home/ollie/Documents/agent-orchestration/.worktrees/durable-host-input`
on `feat/durable-host-input`. The root worktree has independent user work.
Run commands from this worktree root. Do not modify historical `HumanReply`
records or turn historical input settlement into an evaluated execution path.

Execute Tasks 1–6 serially. Task 1 produces the actual compiler fixture used
by Task 2; Task 3 consumes Task 2's public API; Task 4 emits Task 1's source and
uses Tasks 2–3 for native Python execution; Task 5 verifies their composition.
Each implementation task includes its own checks rather than deferring them
to integration. Give each implementer the accepted designs, this plan, exact
file ownership and prior verification evidence. Follow-ups must state role
and artifact type. Independent read-only review may overlap other read-only
work; never overlap writers to shared compiler/runtime/CLI files.

The compiler, runtime and Python tasks are cross-cutting changes across
established interfaces, so use **Sol 6.1 high** for Tasks 1, 2 and 4 under the
repository escalation rule. Use **Luna 6 xhigh** for the bounded host adapters
in Task 3 and test preparation in Task 5; escalate a persistent or cross-cutting
issue to Sol. Use **Sol 6.1 high** for documentation revision and code/plan
review; design decisions return to **Astra 6 xhigh**. The coordinator assigns
review after each task and inspects the final diff personally.

## File and ownership map

Paths below are a change census, not permission for incidental refactoring.
Keep each existing owner; add only the focused files specified here.

| Task / boundary | Files and responsibility |
| --- | --- |
| 1: source types and operands | `orchestrator/workflow_lisp/expressions.py`, `typecheck_effects.py`, `expression_traversal.py`, `procedure_specialization.py`, `wcc/elaborate.py`, `wcc/model.py`: complete request operands, prompt applications, return contract and traversal. `effects.py` already owns `HostInputEffect`; reuse it. |
| 1: target and standard type | `orchestrator/contracts/closed_program/targets.py`, `orchestrator/workflow/run_ref/config.py`; create `orchestrator/workflow_lisp/stdlib_modules/std/host.orc` exporting ordinary generic `HostReply`. `syntax.py`, `type_env.py`, `resource_stdlib.py`, `stdlib_contracts.py` only where their existing registration/type resolution requires it; never replace historical `HumanReply`. |
| 1: closed emission/checking | `orchestrator/workflow_lisp/closed/effects.py`, `closed/build.py`, `closed/preparation_check.py`, `closed/command_templates.py`; `orchestrator/contracts/closed_program/check.py`, `node_walk.py`, `sites.py`: independently checked request shape, configuration operands, effect reachability and site identity. Adjust `typecheck_run_ref.py`/`parallel_map.py` only at the existing rejection owners. |
| 2: request protocol | Create `orchestrator/workflow/evaluated/host_input.py` for frozen payload, request/reply validation, preparation/recovery/expiration and settlement; create public `orchestrator/host_input.py` exporting `pending`, `answer`, `cancel` from this owner. |
| 2: evaluated lifecycle | `orchestrator/workflow/evaluated/{runtime,effect_inputs,memo_reducer,memo,replay,resume_prefix,attempts,views}.py`; reuse `prompts.py`, `values.py`, `authority.py` and `WorkspaceFiles`. Reuse/extract read-only preflight from `orchestrator/cli/commands/evaluated.py` and adapt `resume.py` only if needed to share that exact owner. Amend interfaces only for actual affected callers. |
| 3: public hosts/readers | `orchestrator/cli/main.py`, `cli/commands/human_input.py`, `orchestrator/state.py`, `workflow/evaluated/views.py`, `observability/report.py`, `dashboard/{models,projection,cursor,preview,server}.py` as needed by the existing read routes. No dashboard mutation endpoint. |
| 3: monitoring | `orchestrator/monitor/{models,classifier,ledger,messages}.py`; retain existing config/emailer and previous event-key behavior. |
| 4: Python frontend | Create `orchestrator/py/{__init__,types,trace,emit,build}.py`: public exports; finite authoring descriptors; symbolic declaration/branch tracing; deterministic `.orc`/source-map emission; atomic retained bundle publication and compiler delegation with supplied manifests. Create `orchestrator/cli/commands/python.py`; extend `cli/main.py`. Existing `cli/commands/run.py`/`compile.py` change only for a necessary shared-call adaptation. |
| 1–5: focused tests | Create `tests/test_workflow_lisp_host_input.py`, `tests/workflow_evaluated_host_input_helpers.py`, `tests/test_workflow_evaluated_host_input.py`, `tests/test_workflow_evaluated_host_input_recovery.py`, `tests/test_workflow_evaluated_host_input_hosts.py`, `tests/test_workflow_py_frontend.py`, `tests/test_workflow_py_build.py`, `tests/test_workflow_py_cli.py`, `tests/test_workflow_host_input_e2e.py`. Extend existing targeted tests named in each task. |
| 5: executable examples | Create `workflows/examples/durable_host_input/{approval.orc,approval.py,README.md,providers.json,commands.json,stub_provider.py,action.py}`. Both frontends use the same recording external stand-ins and actual public lifecycle. |
| 6: contracts/guides | `specs/{dsl,state,cli,io,observability,security,versioning}.md`; `docs/design/{workflow_lisp_evaluated_execution,workflow_lisp_frontend_specification}.md`; `docs/{index,capability_status_matrix,lisp_workflow_drafting_guide,lisp_library_reference,runtime_execution_lifecycle,workflow_monitoring}.md`, `docs/design/README.md`, `workflows/README.md`, `tests/README.md`; create `docs/python_workflow_drafting_guide.md`. |

## Verification protocol

Use @superpowers:test-driven-development and
@superpowers:verification-before-completion for implementation. Write the
smallest meaningful behavioral test before each new nontrivial branch/parser,
run its narrow selector and observe the expected failure, implement, then
rerun it. Do not assert question wording, prompt prose or exact emitted source
formatting. Test typed contracts, checked structures, lineage, branch execution
and artifacts. Preserve existing historical fixtures and retirement tests.

Collect every new/renamed test module with `python -m pytest --collect-only -q`
before executing its module. A single focused selector may run directly.
Run multi-module/broad/slow checks in tmux using @tmux and
`python -m pytest -q -n 16 --dist=worksteal`; capture actual exit status and
log path. Check existing evidence before repeating unchanged checks. Never
start a real provider, judge or email transport: scripted providers and a
recording emailer are the only external substitutes.

## Task 1: Typed Lisp request and independently checked target 2.40

**Role/artifact:** Implementation / compiler and standard-library code/tests.
**Dependencies:** Accepted design review; no runtime implementation required.
**Test files:** New `tests/test_workflow_lisp_host_input.py`; extend
`tests/test_workflow_lisp_effect_ceilings.py`,
`tests/test_workflow_lisp_phased_239.py` and
`tests/test_workflow_lisp_target_evaluated_execution.py` where relevant.

- [x] Add the smallest real compile fixture importing `std/host`, declaring
  `Approval`, and returning `HostReply[Approval]` from a procedure containing
  `(request-input question :returns Approval :timeout-sec 60)`. Compile through
  `compile_typed_program` and `build_closed_program`, then restore with
  `ClosedProgram.from_artifact` after deleting source. Assert class
  `request_input`, full answer/reply descriptors, normal site and immutable
  artifact digest. Run the new selector and observe the missing target/effect.
- [x] Add positive String, enum and closed-union answer cases, including
  constrained nested payloads and ordinary `match` refinement of
  `ANSWERED.value/by`, `CANCELLED.by` and payload-free `EXPIRED`. Reject a
  forged or wrong nominal reply descriptor, nontransportable/open/unbound
  answer types, wrong field accesses and missing/duplicate/unknown keywords.
- [x] Extend the retained expression rather than inventing another source
  effect. Carry `:returns`, optional positive integer timeout expression and
  ordered `:show` path operands through all expression/WCC transformations,
  specialization and closed emission. Keep old-target diagnostics and the
  original historical `HumanReply` type/reader semantics unchanged.
- [x] Add the ordinary `std/host` generic union. Keep a single nominal identity
  across imports, compiled capsules and later Python emission. Register 2.40
  through both target inventories, preserving defining-module target checks.
  Correct the three exact phased-provider 2.39 comparisons in
  `typecheck_effects.py`, `closed/effects.py` and
  `contracts/closed_program/check.py` so admitted 2.39 features also work at
  2.40 while old defining targets remain refused.
- [x] Admit a String question or fully applied `defprompt` in this position;
  reuse typed fill/doc handling and check prompt answer agreement. Exercise
  prompt text/value/doc fills and shown file-path projections. Reject plain
  String/object show operands, mismatched prompt return type,
  missing fills and invalid timeout types; dynamic timeout positivity is also
  validated at the runtime boundary. No provider output-file suffix is added.
- [x] Preserve inferred subject-free `host-input` in direct/imported/proc-ref
  calls; omitted effects infer, an explicit empty ceiling refuses. Reject
  reachable requests under `par-map`, pure functions and any child `run-ref`
  before child creation/dispatch. Cover direct, imported and specialized
  transitive helpers. Ordinary `defproc`/same-memo workflow calls remain valid.
- [x] Independently enforce complete descriptor/operand/target/class shape,
  configuration checks and transitive parallel/child restrictions in the
  source-free closed checker. Mutate artifact JSON to prove frontend bypass
  cannot admit a malformed request. Include checks that non-request effects
  still emit/check unchanged and a new request cannot fall through to provider
  dispatch while Task 2 has not wired execution.
- [x] Collect and run the narrow module, then in tmux run:

  ```bash
  python -m pytest --collect-only -q tests/test_workflow_lisp_host_input.py
  python -m pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_host_input.py tests/test_workflow_lisp_human_input.py tests/test_workflow_lisp_effect_ceilings.py tests/test_workflow_lisp_phased_239.py tests/test_workflow_lisp_target_evaluated_execution.py tests/test_workflow_lisp_source_floor.py tests/test_workflow_lisp_closed_program_check.py tests/test_workflow_lisp_wcc_closed_boundary.py
  ```

  Expected: valid 2.40 fixtures compile/round-trip; prohibited routes refuse
  before execution; existing historical and target contracts stay green.
- [x] Obtain independent review, apply accepted corrections, record evidence,
  and commit this task's owned files only with
  `feat: compile typed durable host requests at target 2.40`.

## Task 2: Authoritative memo lifecycle and public host API

**Role/artifact:** Implementation / runtime protocol, host API and focused tests.
**Dependencies:** Task 1 checked request fixture and immutable contract shape.
**Test files:** New `tests/workflow_evaluated_host_input_helpers.py`,
`tests/test_workflow_evaluated_host_input.py`,
`tests/test_workflow_evaluated_host_input_recovery.py`; extend
`tests/test_workflow_evaluated_memo.py` and invalidation tests only for shared
reducer invariants.

- [x] Add a real run fixture that reaches an ask after one committed command.
  Run its first failing test: execution must produce one `started` containing
  the frozen payload and one `suspended`, no terminal/continuation, and release
  its lock with exit 0. Two ordinary resumes must retain request ID, ordinal,
  deadline, memo bytes and earlier command count.
- [x] Add strict reducer cases before implementing the additive class. A
  request start must carry the complete versioned payload; suspension must
  match its identity/attempt/request ID exactly; only one pending request is
  legal; commit must preserve the matching input fields and contain the typed
  reply plus variant-appropriate `host_reply`. Reject unknown/missing fields,
  malformed contract/digest/request identity, inconsistent provenance,
  suspended non-request classes, duplicate suspension and terminal with a
  pending request. No coordinator `proof` or `settled` is permitted here.
- [x] Bind memo request/reply contracts back to `RunAuthority.program` in one
  shared checked validator used by pending, reports, dashboard, replay and
  mutation. The reducer's site-class table is not full nominal type authority;
  a forged memo cannot validate itself by supplying its own descriptor.
- [x] Implement request identity from canonical schema/run/header/program/
  dynamic effect/attempt identity. Freeze the complete prompt, full answer and
  reply contracts, ordered shown evidence, dependencies, creation time and
  absolute deadline in `started`, before attempt/view publication. Keep
  semantic input parts separate from frozen timestamps/show hashes. Validate
  exact positive integer durations and finite absolute deadlines before a
  start; never renew a deadline during recovery.
- [x] Integrate request preparation, replay and suspension into the existing
  runtime before generic retry/external-provider fallback. Use shared prompt
  rendering, complete typed value validation and ordinary dependency tracking.
  Recover a complete start without suspension at the same attempt and append
  one suspension. Deliberate suspension must bypass failed-effect/terminal
  handling. Expire only from resume, after prefix preflight and under the
  writer lock; at `now >= deadline`, commit typed `EXPIRED` with runtime-only
  provenance and continue. Read APIs never expire or reconcile.
- [x] Implement the exact public API:

  ```python
  pending(run_root)
  answer(run_root, request_id, value, *, by, attestation=None,
         accept_changed_evidence=False, workspace=None)
  cancel(run_root, request_id, *, by, attestation=None,
         accept_changed_evidence=False, workspace=None)
  ```

  Both mutations acquire the existing `memo_writer_lock`, reload checked
  authority/memo and validate the reached active request before repair/write.
  Validate nonempty NUL-free principal, optional opaque attestation, finite
  JSON answer and the complete constructed wrapper. The API accepts `A`,
  never a caller-supplied `HostReply`. A writer conflict is `memo_busy`.
  For new settlement reuse the side-effect-free ordinary rebuild/program/
  inputs/reached-prefix preflight before repair/write. `workspace` defaults
  to cwd and must satisfy the recorded result-root relationship; do not infer
  it from the run directory. Test custom state roots and moved-workspace
  relationships. Duplicate committed replies need no source rebuild.
  Test source/program, manifest, runtime Doc and earlier producer divergence
  during new answer/cancel: memo, any torn tail and views remain unchanged.
- [x] Test invalid values, missing/extra union fields, forged wrappers,
  constraints, empty principals, cross-run/stale IDs and
  `host_input_not_suspended`. Every refusal preserves memo, tail and views.
  Identical duplicate settlement returns its original value without writes
  or rereading current evidence, even after deadline/terminal; differing
  variant/value/principal/attestation/override is `request_already_settled`.
  Retrying an earlier noninvalidated committed request also succeeds while
  a later request is pending; lookup cannot consult only the current request.
  Invalidated requests are stale rather than idempotent successes.
- [x] Implement safe show-file snapshot comparison on answer and cancel.
  Changed/missing/unreadable evidence refuses by default. Initial snapshots
  require regular files and reject directories; the source type is the existing
  `relpath`, not a new static file/directory distinction. Explicit override
  records original and observed digests/classification without modifying the
  frozen request; traversal/forbidden symlinks are never waived. Recheck the
  observed snapshot at publication where supported by the existing reader.
  Replay uses recorded show-only snapshots, while changed question/doc inputs
  or earlier producer evidence still cause ordinary divergence. Tests must
  prove override succeeds through a subsequent resume and does not weaken
  those independent semantic checks.
- [x] Serialize deadline and invalidation decisions under the same run lock.
  Check the deadline immediately before host commit: a late answer/cancel
  refuses without expiring; a committed pre-deadline answer is never replaced.
  Existing suffix invalidation retires affected pending starts/suspensions;
  preserve their ordinal history and existing coordinator/session guards.
  Invalidating an answered request and resuming creates a new request ID.
- [x] Publish request prompt/JSON and reply JSON as rebuildable attempt views;
  do not materialize a redundant `result.json`, whose conventional locator
  remains in the normal memo row for existing tooling.
  memo inline reply and its canonical digest remain authority. Missing or
  corrupted views cannot supply a reply. Add fault tests for start/suspension/
  commit/view publication gaps and torn tails now; Task 5 adds process-kill
  coverage. Retain descriptors and dependencies on replay so ordinary union
  match cannot inspect inactive fields.
- [x] Collect new modules, run the narrow request/reducer selectors, then in
  tmux run:

  ```bash
  python -m pytest --collect-only -q tests/test_workflow_evaluated_host_input.py tests/test_workflow_evaluated_host_input_recovery.py
  python -m pytest -q -n 16 --dist=worksteal tests/test_workflow_evaluated_host_input.py tests/test_workflow_evaluated_host_input_recovery.py tests/test_workflow_evaluated_memo.py tests/test_workflow_evaluated_memo_writes.py tests/test_workflow_evaluated_memo_fd.py tests/test_workflow_evaluated_resume.py tests/test_workflow_evaluated_resume_replay.py tests/test_workflow_evaluated_invalidate.py tests/test_workflow_evaluated_invalidate_windows.py tests/test_workflow_evaluated_view_publication_faults.py
  ```

  Expected: all lifecycle transitions, read-only refusals and historical
  command/provider/coordinator recovery remain valid.
- [x] Obtain independent review, apply corrections, record evidence, and
  commit owned files with `feat: persist and settle evaluated host requests`.

## Task 3: CLI, state/report/dashboard and suspension notifications

**Role/artifact:** Implementation / bounded host adapters and observation tests.
**Dependencies:** Task 2 public API and request projection contract.
**Test files:** New `tests/test_workflow_evaluated_host_input_hosts.py`; extend
`tests/test_cli_human_input.py`, `tests/test_monitor_ledger.py`,
`tests/test_workflow_evaluated_monitor.py` and reader/dashboard tests as needed.

- [x] Add CLI tests for `input get RUN_ID`, `input answer RUN_ID
  REQUEST_ID --value JSON --by PRINCIPAL`, and `input cancel RUN_ID
  REQUEST_ID --by PRINCIPAL`, including `--state-dir`, attestation and
  evidence override. The CLI only delegates; mutation never resumes work.
  Decode strict JSON with duplicate-key/nonfinite refusal before mutation.
  Preserve `input get` evaluated routing and historical read compatibility;
  old-profile answer/cancel and old `--text` must not become a second current
  typed interface. Keep existing retirement tests meaningful.
- [x] Extend evaluated `RunState` status validation and the shared projection
  with `suspended` before generic lock-released interruption. Expose exact
  pending request, deadline/deadline-elapsed observation and settled
  attribution from checked memo. A successful external reply leaves the run
  interrupted until ordinary resume. Current terminal semantics are unchanged.
  A durable suspension is suspended even while its publishing writer still
  holds the lock, so no post-unlock view write is needed.
- [x] Wire report/dashboard readers through the same projection. Test missing,
  stale and malformed view files with byte snapshots proving all read routes
  remain read-only; malformed authority refuses without legacy fallback.
  Expose request information using existing safe render/link/preview patterns;
  add no answer/cancel web endpoint or new storage registry.
- [x] Add `MonitorEventKind.SUSPENDED`, classification and the existing email
  renderer's request ID/deadline/command instructions. Do not include evidence
  bodies or attestations in email. Extend the existing ledger's suspension key
  with request ID only, retaining older entries and unchanged event keys for
  other kinds. Test two requests in one run notify separately, repeated scans
  deduplicate, released pending writers are not crashed/stalled, and settlement
  never occurs from monitor/read operations. Use only a recording emailer.
- [x] Collect changed/new tests, run a narrow host case, then in tmux run:

  ```bash
  python -m pytest --collect-only -q tests/test_workflow_evaluated_host_input_hosts.py tests/test_cli_human_input.py tests/test_monitor_ledger.py
  python -m pytest -q -n 16 --dist=worksteal tests/test_workflow_evaluated_host_input_hosts.py tests/test_cli_human_input.py tests/test_workflow_evaluated_readers.py tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_dashboard.py tests/test_workflow_evaluated_monitor.py tests/test_monitor_classifier.py tests/test_monitor_ledger.py tests/test_monitor_messages_emailer.py tests/test_workflow_evaluated_watchdog_probe.py tests/test_workflow_evaluated_watchdog_watcher.py
  ```

  Expected: public request commands and observation work; legacy readers,
  monitor events and watchdog behaviors retain their contracts.
- [x] Obtain independent review, apply corrections, record evidence, and
  commit owned files with `feat: expose pending input through existing hosts`.

## Task 4: Native bounded Python authoring and public py commands

**Role/artifact:** Implementation / Python frontend, build publication and CLI.
**Dependencies:** Tasks 1–3; compiler/runtime semantics are reused, not extended
by a Python executor. First prove the small composition before expanding API.
**Test files:** New `tests/test_workflow_py_frontend.py`,
`tests/test_workflow_py_build.py`, `tests/test_workflow_py_cli.py`.

- [x] Start with an executable feasibility test: native `@workflow` calls a
  later-declared `@proc` returning `HostReply[Approval]`; a provider diagnosis
  feeds `ask`, and lazy `match` branches contain repair/escalation commands.
  Trace to real `.orc`, compile with `build_closed_program_bundle` and run via
  the actual evaluated route using a scripted provider. Assert closed effect
  classes/types and no provider/command execution during declaration/build.
  If this requires semantics beyond the two accepted designs, return the
  architectural decision to Design before expanding the emitter.
- [x] Implement finite authoring types in `types.py`: annotated `@record`,
  string-valued Enum, per-class `@variant` plus named `A | B`/`typing.Union`
  aliases, ordinary primitive/list annotations, `RelPath` subclasses, and a
  descriptor reexport for the same imported
  `std/host::HostReply[A]`. Reject unsupported generic/inherited/arbitrary
  types clearly. Record/variant constructors and enum constants emit ordinary
  values; no second host union or Python value codec becomes authoritative.
  Reject ambiguous variant membership. Map Enum member names to distinct
  string wire values explicitly, including match branches; reject aliases by
  inspecting `__members__`, not only ordinary Enum iteration.
- [x] Implement declarations and deterministic symbolic tracing in `trace.py`.
  Decorators retain bodies without execution until explicit build. Discover
  reachable procedures, trace each once, emit calls instead of inlining
  decorated procedure bodies, and detect recursion without Python recursion.
  Support field projections, constructors, left-to-right effect bindings,
  `ask`, lazy exhaustive `match`, and lazy `when`. Branch callbacks use isolated
  buffers. Reject eager branches and symbolic truth, iteration, length,
  formatting/string conversion with useful Python declaration/line locations.
  Also reject symbolic equality/ordering/arithmetic rather than accidentally
  accepting object-identity booleans. Support `@workflow(returns=T)` and
  `@proc(returns=T, effects=...)`, omitted inferred effects, explicit empty
  ceilings and `host_input`/`uses_provider(name)`/`uses_command(name)` effect
  descriptors. Conflicting decorator and return annotation contracts refuse.
- [x] Implement all advertised prompt/binding builders:
  `Prompt(text=... | file=..., fills=..., returns=...)`, `Text`, `Doc[T]`,
  `Value[T]`, `PathOf[T]` and `Out[T]`; `Provider(name)` and
  `Command(name, returns=T)` refer only to supplied manifest externs. Provider
  calls take an applied prompt whose return type owns the result; Command
  calls supply the full authored argv. Only command manifests declare stable
  argv and mandatory explicit closure. Emit ordinary `.orc` and pass supplied
  manifests unchanged; no source default extern bindings or generated
  manifests are introduced. Per-call `model`, `effort` and `timeout_sec` emit
  the existing ordinary provider options. `Prompt(file=...)` snapshots UTF-8
  template bytes at build; runtime `Doc` retains normal replay checks. Never
  interpolate symbolic values with Python formatting or auto-read path-like
  strings. Test full fill application and wrong/missing fill errors.
- [x] Implement deterministic emission and source mapping in `emit.py`.
  Stable declaration/operation order selects names and labels; Python object
  IDs, clocks and unordered traversal do not. Preserve nested branch/procedure
  attribution using generated spans plus original Python line/definition;
  do not invent exact columns. Assert checked structures and behavior, not
  full source text. Keep unsupported loops/agents/run-ref/parallel/direct-IR
  APIs absent, rather than exporting nonworking placeholders.
- [x] Implement build publication in `build.py` beneath
  `.orchestrate/generated/<module>/<digest>/`, covering emitted source,
  canonical source-map bytes, emitter version and authoring template bytes in
  deterministic identity. Use workspace-relative original source filenames;
  line/comment edits update bundle identity without stale-map collisions.
  Supplied manifest paths retain ordinary build/replay mutation semantics.
  Write/fsync a temporary sibling and atomically install a complete
  bundle. Verify exact bytes on existing-digest reuse; refuse corruption,
  symlinks and generation-root escapes without overwriting evidence. Hand
  `FrontendBuildRequest` to the existing closed-program builder. Compiler
  rejection may retain diagnostic source but must create no run or dispatch.
- [x] Implement `py check`, `py build`, `py run` for `file.py
  --entry-workflow NAME` in the
  thin CLI adapter; reuse existing runtime input/state/provider configuration.
  Without a selector require exactly one exported workflow. Implement
  `build(workflow, *, workspace=None, provider_externs_file=None,
  prompt_externs_file=None, command_boundaries_file=None, source_roots=())`.
  Build reports source/supplied manifests/entry and build/program digests. Run records
  the generated `.orc`/manifest recipe through the ordinary run entrypoint.
  There is no `py resume`: ordinary resume must not import Python, retrace,
  run decorators or select a newly generated bundle.
- [x] Test repeated-build determinism, module/helper declaration order,
  symbolic errors, type/branch failures, exact bundle reuse/corruption refusal,
  safe failure during atomic publication and source-mapped diagnostics.
  Explicitly test procedure effect ceilings/subjects, named union membership,
  distinct Enum member/wire names and aliases, symbolic equality/order/math
  refusals, and source-map bundle identity after comment/line-only edits.
  Suspend a native run, edit/delete its original Python and `Prompt(file=...)`
  template, settle and resume successfully. Tampering with retained generated
  input must fail normal rebuild/program checks; changing a runtime Doc must
  still fail semantic replay. No assertion may rely on provider prompt prose.
- [x] Collect all new modules, run the narrow feasibility selector, then in
  tmux run:

  ```bash
  python -m pytest --collect-only -q tests/test_workflow_py_frontend.py tests/test_workflow_py_build.py tests/test_workflow_py_cli.py
  python -m pytest -q -n 16 --dist=worksteal tests/test_workflow_py_frontend.py tests/test_workflow_py_build.py tests/test_workflow_py_cli.py tests/test_workflow_lisp_host_input.py tests/test_workflow_evaluated_host_input.py tests/test_workflow_lisp_closed_program_compile_cli.py tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_resume.py
  ```

  Expected: native Python uses the real compiler/runtime/host protocol and
  remains independent of original Python sources during resume.
- [x] Obtain independent review, apply corrections, record evidence, and
  commit owned files with `feat: author durable workflows through native Python`.

## Task 5: Public parity smoke, adversarial lineage and crash recovery

**Role/artifact:** Implementation / integration tests and runnable examples.
**Dependencies:** Tasks 1–4; retain their valid evidence and add only missing
cross-layer/adversarial coverage. No synthetic provider-quality comparison.
**Test files:** New `tests/test_workflow_host_input_e2e.py`; extend the new
recovery/host/Python test modules and fixture helper from prior tasks.

- [ ] Complete matching maintained Lisp and Python diagnose/approve/recover
  examples, all provider/command declarations and manifests, a recording
  provider stub, a verification command before approval and an action command.
  The request uses the verification command's typed cause/evidence output.
  Provider stubs return by logical request
  identity, not call count, so retry/replay evidence is interpretable. Stub
  commands produce a typed Outcome and record repair/escalation invocation.
  Include typed shown evidence and prompt docs in dedicated variants.
- [ ] Parametrize the public CLI integration across Lisp/native Python and
  APPROVED, DENIED, CANCELLED, EXPIRED. Run, inspect pending through API/CLI,
  settle through the other door, resume, then resume again. Assert repair only
  for ANSWERED(APPROVED); all other branches escalate with typed outcomes.
  Diagnosis runs once, command counts are exact, and no action runs before
  settlement. Compare semantic outcomes/contracts, not nominal program digest.
- [ ] Exercise two visits of one loop site and two procedure activations in
  Lisp; assert distinct request IDs and correct request-to-activation mapping.
  Repeated pending resume keeps identity. Cover same-memo workflow calls,
  transitive imported/proc-ref effect rejection under parallel and child
  run-ref before any child launch, and parallel work adjacent to a serial ask
  where the existing parallel contract admits it.
- [ ] Use existing recovery gate patterns from
  `tests/workflow_evaluated_recovery_helpers.py` and
  `tests/test_workflow_evaluated_resume_kills.py`; add only request-specific
  gates. Kill a subprocess after durable start/before attempt creation,
  before/after suspension, during torn reply append, after full reply commit
  and before/after view publication. Resume/duplicate submission must recover
  the same attempt and produce exactly one authoritative settlement; missing
  request/reply/result views never change the answer. Use markers and bounded
  timeouts, never timing-only sleeps as ordering evidence.
- [ ] Test concurrency with real separate-process writer locks and a
  controlled clock: answer-before-deadline wins; late answer leaves request
  pending; resume at the exact deadline expires; a waiting/late mutation cannot
  backdate a reply or replace expiration. A read observes deadline elapsed
  without changing memo. Assert every conflict/invalid reply preserves bytes,
  including a preexisting torn tail.
- [ ] Cover changed/missing/unreadable show evidence, explicit accepted drift,
  post-commit show-only changes, independent doc/producer divergence, unsafe
  path substitution and forged memo provenance. Cover invalidation of an
  earlier commit retiring a later pending request and invalidation/reissue of
  an answered request. Old IDs never settle the new attempt. Preserve existing
  coordinator/session invalidation refusals.
- [ ] Exercise all read/notification surfaces against missing/stale views,
  two sequential requests and settled/expired outcomes. Verify generated and
  original Python source attribution without making source maps runtime
  authority. No test sends real email or calls a paid provider.
- [ ] Collect new/renamed modules and run the public integration smoke in tmux:

  ```bash
  python -m pytest --collect-only -q tests/test_workflow_host_input_e2e.py tests/test_workflow_evaluated_host_input_recovery.py
  python -m pytest -q -n 16 --dist=worksteal tests/test_workflow_host_input_e2e.py tests/test_workflow_evaluated_host_input_recovery.py tests/test_workflow_evaluated_host_input_hosts.py tests/test_workflow_py_cli.py tests/test_workflow_evaluated_invalidate_smoke.py
  ```

  Expected: both public frontends complete all four outcomes and crash/race
  fixtures without duplicate dispatch or weakened replay. Record the exact
  smoke selector, exit status, branch counts and log; this is the required
  orchestrator end-to-end smoke, not a compiler-only substitute.
- [ ] Obtain independent review, record evidence, and commit owned files with
  `test: prove durable approval parity and crash recovery`.

## Task 6: Contracts, current guidance and integrated closeout

**Role/artifact:** Revision / contracts, guides and plan evidence; coordinator
owns final diff and verification. New architecture decisions return to Design.
**Dependencies:** Working Tasks 1–5, their reviews and fresh smoke evidence.

- [ ] Reconcile normative DSL/state/CLI/IO/security/observability/versioning
  contracts with the exact implemented target 2.40 behavior: class/row fields,
  typed answer restrictions, suspension/exit behavior, API attribution,
  deadlines, host mutation/idempotency, safe evidence override and invalidation.
  Correct evaluated-execution's previous suspended refusal and frontend rules
  without rewriting historical HumanReply sections as current behavior.
- [ ] Update capability/design/index routing for 2.40 and bounded Python
  authoring. State implementation and deterministic verification separately
  from live-provider qualification; do not change unrelated open gates. Keep
  target ranges accurate at the maintained entry points and preserve
  independently admitted older targets/import semantics.
  Include minimal current-scope corrections in `specs/index.md`, root
  `README.md`, `docs/architecture_overview.md`, `prompts/README.md`, and the
  maintained value/continuation and REPL designs where they state the current
  maximum target or sole authoring frontend. Preserve historical ranges.
- [ ] Add the Python drafting guide and the Lisp/library host-input recipes;
  include complete executable approval examples, manifest/provider
  prerequisites, JSON settlement commands, report/monitor usage and explicit
  resume. Document trusted build-time Python, lazy branches, supported names,
  generated-bundle retention, Prompt(file=...) versus runtime Doc semantics and
  unsupported Python surfaces. Update lifecycle, monitoring, workflow catalog
  and tests routing. Keep chronology/results in this plan, not maintained
  contracts or guides.
- [ ] Check links and examples against files and the actual CLI. Ensure no
  placeholder APIs, duplicate nominal HostReply, retired execution path,
  `invalidate --from` spelling, provider polling or dashboard mutation appears
  in current guidance. Record any documentation test constraints honestly;
  add no tests asserting prompt/document wording.
- [ ] Run final broad affected-suite verification in tmux after narrow checks
  and the public smoke have passed:

  ```bash
  python -m pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp*.py tests/test_workflow_evaluated*.py tests/test_workflow_py*.py tests/test_workflow_host_input_e2e.py tests/test_cli_human_input.py tests/test_monitor*.py tests/test_dashboard*.py tests/test_state*.py
  ```

  Capture command, environment, exit status and log path. If the branch has
  changed since a relevant green selector, rerun that selector first. Broader
  unrelated tests are required only if a failure/change reveals another
  affected boundary; do not silently reduce this affected-suite obligation.
- [ ] Use @superpowers:requesting-code-review for final independent review of
  the integrated compiler, runtime, Python and crash evidence. The coordinator
  inspects `git diff --check`, full change summary and actual verification
  output. Apply accepted findings to the existing author, rerun affected
  checks, then commit docs with `docs: describe durable host input and Python authoring`.
- [ ] Mark completed steps and record remaining limitations/evidence below.
  Summarize delivered behavior, tests and material constraints to the owner.
  Do not merge/publish or claim paid live qualification merely because local
  deterministic checks passed.

## Decision ledger

| Date | Decision | Reason / boundary |
| --- | --- | --- |
| 2026-10-22 | Select native Lisp and native Python ask in the same delivery. | Explicit owner clarification; external host Python settlement alone does not satisfy native authoring. |
| 2026-10-22 | Extend evaluated memo; emit Python to ordinary retained `.orc`. | One runtime/type/effect/recovery authority; no retired executor or Python continuation store. |
| 2026-10-22 | One outstanding serial request; reject transitive par-map and child run-ref. | No parent/child suspension coordinator or multiple-pending policy is selected; same-memo procedures/calls and serial loops are supported. |
| 2026-10-22 | Full frozen payload in started; show bytes are presentation evidence. | Recover start-to-suspension crash gaps and retain accepted drift across resume without bypassing semantic docs/producers. |
| 2026-10-22 | Sol 6.1 high for compiler/runtime/Python; Luna 6 xhigh for bounded hosts/tests. | Existing interfaces span multiple owners; user policy permits escalation for cross-cutting implementation. |
| 2026-10-22 | No provider or live notification spend. | Deterministic external stand-ins suffice for functionality/recovery; no quality comparison or spend is authorized. |
| 2026-10-22 | Python enum matches emit existing typed equality/if; union matches emit Lisp match. | Lisp match currently admits unions only; exhaustive enum callbacks need no new core construct. |
| 2026-10-22 | Python path constructors take a child relative to the declared root. | Reuse public path/join-under and its validation; do not expose private path seeds or add implicit full-path conversion. |
| 2026-10-22 | Evidence override does not waive a workflow input's must-exist contract. | Exact shared preflight remains authoritative. Missing presentation-only evidence is overrideable only when it has no independent input, Doc or producer obligation. Tests distinguish these cases rather than weakening ordinary input validation. |
| 2026-10-22 | Preserve the watchdog health-result enum for suspended evaluated runs. | Map intentional waits to existing RUNNING_OK/NONE with no repair; report/dashboard/monitor retain the explicit suspended state. No historical watchdog workflow is re-admitted or extended. |
| 2026-10-22 | Reconstruct configured capsule signatures only in modules that reference those workflow bindings. | Real HostReply enum/union capsule fixtures exposed reconstruction in unrelated stdlib/type/utility environments. Design review selected an extra existing expression-elaboration pass with a recording workflow resolver, only for explicit-import builds. This preserves lexical binding semantics at additional compile-time cost; no separate syntax scanner, native-signature fallback or lazy catalog is introduced. All supplied snapshots retain admission, conflict and closure checks. Known nominal return hints still require complete boundary-contract equality; erased imports retain their existing matching policy. |
| 2026-10-22 | Repair typed enum let normalization in its shared compiler owner. | Native Value fills require ordinary let bindings; a handwritten Lisp reproducer confirms that inline-procedure normalization wrongly resolves a known enum constant as a WorkflowRef. Exclude resolved enum types at that call site and retain existing reference handling, rather than emitting a synthetic conditional workaround. |
| 2026-10-22 | Present existing preflight/compiler refusals through the host CLI's controlled error path. | Native runtime Doc mutation exposed an uncaught domain refusal. Catch the specific existing domain exceptions and retain their diagnostic codes; do not change preflight, the public API's replay behavior or memo mutation ordering. |
| 2026-10-22 | Keep Python source and name hygiene explicit and finite. | Independent executable review exposed parameter capture by generated bindings and conflation of distinct same-named types. Reserve author names for generated bindings/prompts and refuse conflicting type owners. Normalize lexical source paths before checking workspace-relative attribution, so `..` cannot bypass the selected source boundary. This is not an import sandbox. |

## Evidence and current status

- Baseline before implementation: `python -m pytest -q
  tests/test_workflow_evaluated_memo.py tests/test_workflow_evaluated_resume.py`
  completed **109 passed in 75.92s**, exit 0; log
  `/tmp/host-input-baseline.log`. An earlier command named a nonexistent
  closed-program test file and exited 4; it was corrected before implementation
  and is not counted as test evidence.
- Both designs and the revised implementation plan received independent
  approval. All first-review plan findings are applied.
- Task 1 completed in `e93240f2` after independent spec and quality approvals.
  Final affected compiler regression: **977 passed in 13.58s**, exit 0,
  `/tmp/host-input-task1-final-regression.log`; host module: **71 passed**,
  `/tmp/host-input-task1-capsules-final.log`, with all 71 collected. Root inspected
  the final diff, logs and clean `git diff --check`. Review corrections cover
  exact generic identity, erased-import compatibility, lexical capsule consumers
  and checked atomic nested-union boundaries. Six source-free enum/union capsule
  cases pass, with forged root/nested discriminants rejected.
- The lexical `let*`/`WorkflowRef` fixture exposes a preexisting WCC `KeyError`
  even without a supplied capsule (`/tmp/host-input-let-baseline.log`). Its
  changed frontend/catalog boundary is verified against that baseline; no
  unrelated WCC repair or executable support claim is included.
- Task 2 completed in `d6c2932b` after independent spec and quality approval.
  The runtime regression passed **334 tests in 44.28s**, exit 0,
  `/tmp/host-input-task2-final2-regression.log`. Review added public error-code,
  active-writer status and exact reached-dependency checks. An expanded view
  regression found six compatibility failures from an unconditional null
  field; all six pass after emitting pending metadata only during suspension
  (`/tmp/host-input-task2-review-view-compat.log`). Focused correction checks
  passed 14, 9 and 5 cases respectively in the `review-narrow`, `review-final`
  and `dependencies-green` logs under `/tmp/host-input-task2-`. Unchanged
  successful checks were reused. The final two adversarial dependency cases
  verify both public pending and shared view refusal without writes. Root
  inspected the complete change, fresh outputs and clean diff before commit.
- Task 3 completed in `c0c34056` after independent spec and quality approval.
  The required adapter regression passed **205 tests in 69.72s**, exit 0,
  `/tmp/task3-host-input-final-tests.log`. The watchdog compatibility follow-up
  passed **24 tests in 244.55s**, `/tmp/task3-watchdog-final.log`; it retains
  `RUNNING_OK/NONE` and no repair for intentional host waits. Review corrections
  for invalidated pending-row presentation, deeply nested JSON refusal and
  frozen evidence hashes passed **111 tests in 19.40s**, exit 0,
  `/tmp/task3-revision-pytest.log` (111 collected). Root inspected the code,
  actual logs and clean diff before commit. Suspension emails contain only
  metadata/commands: rendered questions can contain runtime Doc bodies.
- Task 4 completed in `e4f90d02` after independent spec and quality approval.
  The required gate plus shared compiler/reference regressions passed **553
  tests in 43.31s**, exit 0, `/tmp/host-py-gate.log`. Final Python hygiene
  corrections passed **79 tests in 13.85s**, `/tmp/host-py-final.log` (79
  collected). The subsequent source containment correction passed **26 tests
  in 12.36s**, `/tmp/host-py-path.log` (26 collected); unaffected evidence was
  retained. Review reproduced and corrected generated-name capture, conflated
  same-named types and lexical `..` source escape. Root inspected the package,
  CLI/shared-owner diffs, fresh logs and clean diff before committing. Native
  feasibility includes actual provider/command stand-ins, HostReply through a
  forward procedure, settlement and repeated resume with exact dispatch counts.
- Task 5 public paired examples and real-process crash/race checks are active;
  the initial Python feasibility check does not replace that full campaign.
- No provider-quality result or live-provider qualification is claimed.
