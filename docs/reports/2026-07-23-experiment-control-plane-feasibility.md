# Experiment Control-Plane Feasibility Report

## Decision

- **Core gate:** `G0_BLOCKED`
- **Historical retrieval classification:** `OBSERVATIONAL_ONLY`
- **Experiment consequence:** stop
  [`.orc` Versus One-Shot Experiment Program Implementation Plan](../superpowers/plans/2026-07-23-orc-vs-one-shot-experiment.md)
  before Task 2
- **Required prerequisite design:**
  [Provider-Phase Information Isolation Design](../superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md)
- **Required prerequisite plan:**
  [Provider-Phase Information Isolation Implementation Plan](../superpowers/plans/2026-07-23-provider-phase-information-isolation.md)
- **Review state:** formal specification and quality re-reviews approved 2026-07-23

The current public CLI can compile and run a Workflow Lisp source whose
workflow, prompts, and extern manifests live outside the candidate product. It
can use an external `--state-dir`, execute two provider phases, carry a
declared typed relpath between them, write an ordinary product file, and
validate certified command results. It produced and stored the prior scalar,
but the lowered phase-two provider step did not render that scalar into its
prompt.

It cannot enforce the required provider information boundary. The ordinary
provider child ran with ambient OS authority and read every known forbidden
sentinel, the external controller state, candidate runtime build/checkpoint
files, and the prior phase's undeclared raw result bundle. Because one core
negative assertion is enough to block G0, no experiment apparatus or scored
trial work is admissible.

No runtime semantics were changed during this spike.

## Scope And Runtime Identity

- **Primary pinned runtime commit:**
  `7437409d4619843d1c660a1a5e1905e4afd1020d`
  (`docs(experiments): plan orc effectiveness study`)
- **Primary failing run:** 2026-07-23 12:35 PDT
- **Fresh confirmation checkout:**
  `b9eae74e0ed0d9376b1910202c83df52f739a7cf`
- **Delta between those commits:** one documentation-only file,
  `docs/plans/2026-07-23-yaml-retirement-proportionality-ruling.md`; no runtime
  or test implementation changed
- **Working-tree note:** the shared checkout contained unrelated dirty
  documentation, workflow, state, and test paths. No `orchestrator/` provider,
  CLI, state, Workflow Lisp, or runtime implementation file was modified by
  this spike or listed dirty when the primary run started.
- **Python:** 3.13.9
- **pytest:** 8.4.1
- **Host:** Linux

The deterministic fixture shadowed the built-in `codex` executable on `PATH`
with a probe provider. It therefore exercised the public CLI, Workflow Lisp
build, provider extern resolution, built-in provider argv/cwd/environment path,
ordinary provider subprocess execution, typed result bundles, checkpoints,
and state persistence without spending a model call or relying on model
cooperation.

## Gate Results

| G0 obligation | Result | Evidence |
| --- | --- | --- |
| External `.orc`, prompt assets, and extern manifests | PASS | CLI returned 0 with all control assets under the external control root |
| Provider `cwd` is the candidate root | PASS | both invocation records report the exact candidate path |
| Declared task prompt dependency | PASS | both phases record only `task/task.md` and contain the task token |
| Prior typed record parsed and stored | PASS | state contains `allowed_value: typed-prior-value` and `allowed_path: task/task.md` |
| Declared prior relpath reaches phase two | PASS | lowered dependency and invocation record contain `task/task.md` |
| Declared prior scalar reaches phase-two provider | **FAIL** | `prior.allowed_value` is absent from the lowered final provider step; the fixture recorded no direct scalar observation, so declared scalar consumption was not demonstrated |
| Ordinary candidate product write | PASS | `product-marker.txt` has the expected bytes |
| No `.orc` or extern manifest in product | PASS | product manifest contains only task inputs and the marker |
| `.orchestrate` excluded from product/reviewer projection | PASS | pre/post product manifests explicitly omit it |
| Inactive prompt, evaluator, peer, parent, and controller reads denied | **FAIL** | both phases read all five sentinels successfully |
| Later phase cannot read prior raw bundle/runtime state | **FAIL** | phase two read the prior raw result, build outputs, checkpoint records, and external state |
| Certified command-result transport behavior | PASS | all six typed pass/fail and adapter-contract cases passed after TDD implementation |
| Product-executing check child denied ambient filesystem authority | NOT PROVED | the diagnostic adapter launched its child ambiently; a provider-authored check could act as a confused deputy |
| Provider API transport separable from history retrieval | NOT PROVED | current provider/profile surface has no enforceable per-capability separation |

The first executed failed core assertion was:

```text
AssertionError: provider unexpectedly read inactive_prompt
assert True is False
```

The assertion required
`phase_two["known_sentinel_probes"]["inactive_prompt"]["read_succeeded"] is
False`; the observed value was `True`. The loop stops at that first assertion,
but the invocation evidence records the same successful read for all other
known sentinels and the prior-runtime probes.

A later evidence review found a second independent core failure that the test
had not asserted before stopping. The authored source declared
`prior.allowed_value` in phase two's `:inputs`, and phase-one state stored
`"typed-prior-value"`, but the persisted/lowered phase-two provider step
contains only the `allowed_path` dependency. Neither its prompt projection nor
the provider invocation record demonstrates scalar consumption. This is a
fixture coverage defect and a runtime/consumer-rendering gap, not a pass. The
prerequisite acceptance test must explicitly render and observe the scalar
before G0 can close.

This observation contradicts the current author-facing statement in
`docs/lisp_workflow_drafting_guide.md` that `provider-result :inputs` records
are rendered at the prompt seam. The governing
`docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
still classifies broader Track C consumer rendering as partial/future. The
prerequisite therefore owns narrow Track C1 carriage plus the required C6
implicit-default renderer-selection slice and status correction; filesystem
isolation alone cannot close this failure.

## Exact Public CLI Invocation

The fresh confirmation generated and executed:

```bash
cd /tmp/agent-orchestration-g0-20260723-red-v2/test_orc_control_plane_stays_o0/candidate
/home/ollie/miniconda3/bin/python3.13 -m orchestrator run \
  /tmp/agent-orchestration-g0-20260723-red-v2/test_orc_control_plane_stays_o0/control/external_control_plane/task_loop.orc \
  --source-root /tmp/agent-orchestration-g0-20260723-red-v2/test_orc_control_plane_stays_o0/control \
  --entry-workflow external_control_plane/task_loop::run \
  --provider-externs-file /tmp/agent-orchestration-g0-20260723-red-v2/test_orc_control_plane_stays_o0/control/providers.json \
  --prompt-externs-file /tmp/agent-orchestration-g0-20260723-red-v2/test_orc_control_plane_stays_o0/control/prompts.json \
  --command-boundaries-file /tmp/agent-orchestration-g0-20260723-red-v2/test_orc_control_plane_stays_o0/control/commands.json \
  --input-file /tmp/agent-orchestration-g0-20260723-red-v2/test_orc_control_plane_stays_o0/candidate/task-inputs.json \
  --state-dir /tmp/agent-orchestration-g0-20260723-red-v2/test_orc_control_plane_stays_o0/controller-state \
  --max-retries 0 \
  --retry-delay 0
```

The CLI returned 0 and persisted completed run
`20260723T194527Z-8hjehk`. G0 is blocked by what the provider could read, not
by an inability to compile or run the external workflow.

## Fixture And Control-Asset Digests

The final diagnostic source digests are:

| Asset | SHA-256 |
| --- | --- |
| `test_external_control_plane.py` | `e2acac649ee9637bb5e4b97af0b5207874657935780c3aed5bd0578907bf1db9` |
| `provider.py` | `0ea5921f5c1aba69a87f89899d35f4de7b38913fd086488935a98a02c3d0a534` |
| `check_adapter.py` | `50379918e65a00ecfd360a775d36bd1397dfb82c4bd3018602c29268a8db1ca1` |
| generated `task_loop.orc` | `52f7afd84d5b664d4a3195c017549e687a17c429f22cd46eb095a0ef0b6cc6cd` |
| generated `providers.json` | `8d24d2f8b3032394b563630e6a76cef5aea0748590757d6f03e1b4bddf958cfd` |
| generated `prompts.json` | `117f5fa93cd905c714c5cdda0beb9a5ffd68035a8711d8e3e19eeba5aa15e8f1` |
| generated `commands.json` | `ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356` |
| generated phase-one prompt | `399be989e14bc32d1e6a07ad992d03863f006f92178e07145f69b0f2edf80eef` |
| generated phase-two prompt | `8f05ce0b6a015a28d0ca13cf4604d621d4ba3dfaa28ac21e7e5a163dec7ce42d` |

## Product Pre/Post Manifests

The manifests enumerate candidate-owned files and intentionally exclude
`.orchestrate`.

### Pre-run

| Path | Size | SHA-256 |
| --- | ---: | --- |
| `task/task.md` | 45 | `c34108958474b3d568d882755874b98a62e2cffd6bd295ff35cbfad9eb1403f0` |
| `task-inputs.json` | 29 | `bc72e7258696e29dab2b24908e40445a839aa5cb8210aef342355a71fe8b5810` |

### Post-run

| Path | Size | SHA-256 |
| --- | ---: | --- |
| `product-marker.txt` | 23 | `f6cbe8fa5fdbd32c59960afe4f1b7a1e04b985b19953ae94191347c89a04a1ef` |
| `task/task.md` | 45 | `c34108958474b3d568d882755874b98a62e2cffd6bd295ff35cbfad9eb1403f0` |
| `task-inputs.json` | 29 | `bc72e7258696e29dab2b24908e40445a839aa5cb8210aef342355a71fe8b5810` |

The only product change was the expected marker. This proves product
projection cleanliness, but it does not make the physically nested runtime
projection unreadable to the provider.

## Observed Runtime Layout

`--state-dir` relocated the main `StateManager` run root, but not every
runtime-owned projection:

| Authority | Observed location | Provider read result |
| --- | --- | --- |
| Main run state, monitor metadata, prompt-dependency snapshots | external `controller-state/<run-id>/...` | readable |
| Frontend build bundle | `candidate/.orchestrate/build/<build-id>/...` | readable |
| Workflow Lisp checkpoint index/records | `candidate/.orchestrate/runs/<run-id>/workflow_lisp/checkpoints/...` | readable |
| Provider result bundles | `candidate/.orchestrate/workflow_lisp/entry/<run-id>/...` | readable |
| Prior phase raw bundle | same candidate runtime projection | readable by phase two |
| Current phase raw bundle | same candidate runtime projection | writable as intended |

Phase two successfully read 18 enumerated candidate runtime files, including:

```text
candidate/.orchestrate/workflow_lisp/entry/<run-id>/
  external_control_plane_task_loop_run/
  __write_root__external_control_plane_task_loop_run__prior__result_bundle.json
```

It also read the external `state.json`, monitor metadata, state lock/attempt
markers, checkpoint shadow report, prompt-dependency attempt records, and the
controller sentinel. The concrete layout confirms that `--state-dir` is not a
general runtime-projection relocation switch.

## TDD And Verification Record

### Collection

Initial isolation-only collection:

```bash
pytest --collect-only -q tests/experiments/test_external_control_plane.py
```

Result: 2 tests collected in 0.04s.

Final diagnostic collection after the command cases were added:

```text
7 tests collected in 0.04s
```

### Core G0 RED

Primary pinned run:

```bash
pytest -q \
  tests/experiments/test_external_control_plane.py::test_orc_control_plane_stays_outside_candidate_product \
  --basetemp=/tmp/agent-orchestration-g0-20260723-red
```

Result: `1 failed in 0.50s`, first failure `provider unexpectedly read
inactive_prompt`.

Fresh confirmation with persisted pre/post manifests:

```bash
pytest -q \
  tests/experiments/test_external_control_plane.py::test_orc_control_plane_stays_outside_candidate_product \
  --basetemp=/tmp/agent-orchestration-g0-20260723-red-v2
```

Result: `1 failed in 0.51s` at the same assertion.

The assertion was not weakened and no runtime fix was attempted inside the
experiment plan.

### Certified command-result RED/GREEN

RED, with the declaration-only adapter stub:

```bash
pytest -q tests/experiments/test_external_control_plane.py \
  -k command_result \
  --basetemp=/tmp/agent-orchestration-g0-20260723-command-red
```

Result: `2 failed, 3 passed, 2 deselected in 2.00s`. The primary expected
failure was the missing adapter behavior. One changed-manifest negative
assertion initially expected an `error` envelope that the established command
execution path does not use.

The minimum adapter then:

- accepts the compiler-appended exact JSON request;
- verifies a frozen argv-manifest SHA-256 before child launch;
- launches argv without a shell;
- maps child exit 0/nonzero to typed `PASS`/`FAIL`;
- keeps adapter exit 0 after a child result;
- atomically writes `checks_result.v1` through
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; and
- exits 2 on adapter contract errors.

The inaccurate test-only assertion was corrected to the runtime's actual
`exit_code: 2` and `outcome.class: command_failed` surface. Final GREEN:

```bash
pytest -q tests/experiments/test_external_control_plane.py \
  -k command_result \
  --basetemp=/tmp/agent-orchestration-g0-20260723-command-green-final
```

Result: `5 passed, 2 deselected in 2.37s`.

Covered cases:

1. child exit 0 -> typed `PASS`;
2. child exit 7 -> typed `FAIL`, adapter/workflow success;
3. missing bound bundle -> `missing_bundle_file`;
4. wrong schema version -> `invalid_enum_value`;
5. changed frozen manifest digest -> adapter exit 2, no child marker; and
6. valid-looking stdout with no bundle -> `missing_bundle_file`.

This proves only the certified command boundary's typed pass/fail and
result-contract semantics. It does not prove filesystem isolation for a child
that executes provider-authored product code and cannot be used unchanged for
planned visible checks: that child needs the reviewed no-result isolation
launcher and denial attestation.

### Historical classification

```bash
pytest -q \
  tests/experiments/test_external_control_plane.py::test_historical_retrieval_policy_is_truthfully_classified
```

Result: `1 passed in 0.03s`, validating the recorded
`OBSERVATIONAL_ONLY` enum value.

The substantive classification comes from supported-surface inspection:

- provider subprocess/API transport remains available;
- built-in Codex profiles use
  `--dangerously-bypass-approvals-and-sandbox`;
- the provider template and executor have no independent policy/attestation
  fields for remote Git, browser, source search, or repository fetch; and
- `specs/security.md` delegates stricter process access to an external OS/user
  sandbox.

No active remote endpoint was invoked, and no denial was inferred from a
missing tool call. Therefore the historical replay is observational only. This
classification is not the reason core G0 is blocked.

## Root Cause

The current runtime validates paths that the orchestrator itself resolves, but
ordinary provider commands are unrestricted child processes. Candidate `cwd`,
external control-plane CLI arguments, prompt dependency declarations,
`--state-dir`, and product projection filters operate at different layers;
none removes ambient OS filesystem authority from the child.

The built-in provider command path further disables the provider tool's own
sandbox/approval layer. Consequently, an absolute path known to the provider
is readable whenever the invoking user can read it. The spike deliberately
passed forbidden paths to an adversarial probe and observed that authority.

A truthful fix requires a reusable provider launch boundary with a
phase-specific filesystem projection and output broker. It is not a local
experiment fixture change.

## Required Next Work

The separate design and plan require:

- an explicit `provider_phase_isolation.v1` policy;
- consumer-side rendering that carries every declared typed phase input into
  the active provider prompt without exposing the raw producing bundle;
- a fail-closed Linux Bubblewrap backend with pinned executable and complete
  host loader/library/cache startup-closure identity;
- a frozen provider executable environment and isolated home/temp roots;
- candidate read/write access with candidate `.orchestrate` masked;
- no control/controller/evaluator/peer/parent mounts;
- an invocation-private active result-bundle broker;
- an atomic durable handoff from a validated typed bundle into authoritative
  workflow step/call-frame state and applicable artifact lineage before attempt
  closure, with any lexical checkpoint remaining a derived recoverable cache;
- isolated state schema `2.2` so older runtimes reject ordinary same-lineage
  resume rather than silently drop the boundary; an older force restart is a
  distinct unrestricted run and cannot satisfy the original attestation;
- exact policy/environment/backend state and resume identity;
- per-attempt isolation attestation;
- fresh-only provider sessions in the first profile;
- one closed launcher request union: workflow providers require a typed result
  channel plus root-owned lifecycle scope/ordinal, while controller attempts
  require `result_channel: "none"` plus a caller-owned external
  lifecycle/attestation sink and no workflow ordinal; product-executing
  certified-check children use only the latter and its separate service
  recovery path, while the prerequisite rejects ambient in-workflow command
  steps until the experiment adds a pinned built-in adapter seam;
- descriptor-safe disposable-product admission before such a child launches;
- a separate evaluator-containment design/gate before any scored evaluator
  imports or executes provider-authored product code;
- a separate reviewer/consumer provider-containment gate before scored
  soft-reviewer or F2 sessions can observe controller/peer/unblinding
  authorities; and
- a separate, computed history-retrieval capability classification.

The prerequisite must be implemented and independently reviewed outside the
experiment plan. G0 must then be rerun through the public CLI before Task 2 or
any scored trial work starts.

## External Content-Addressed Evidence

The raw failing fixtures and generated run trees are intentionally not retained
as a permanently failing repository test module. Their durable
project-external location is:

```text
/home/ollie/.local/share/agent-orchestration/evidence/
  sha256-1847661aa2baa7ca372b12fcf97de7f9b5b18d05c2a2ad023d6d8b5691aa8027/
```

Deterministic archive identity:

```text
sha256:1847661aa2baa7ca372b12fcf97de7f9b5b18d05c2a2ad023d6d8b5691aa8027
```

It was computed over:

```bash
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
  -cf - -C <evidence-directory> . | sha256sum
```

The directory contains 713 regular files and 24 symbolic links (about 11 MiB),
including:

- final diagnostic sources;
- the primary first RED run;
- the fresh RED run with pre/post manifests;
- command-boundary RED;
- the first GREEN attempt that exposed the inaccurate test assertion;
- the corrected GREEN run; and
- the final fresh GREEN run.

All 24 symlinks contain absolute targets below the mutable historical `/tmp`
fixture roots. Most are pytest `*current` convenience links; two are
`control/bin/codex` links to the corresponding temporary `control/provider.py`.
The deterministic tar digest authenticates each link's text, not the bytes at
its target. They are historical metadata only: recovery must inventory them
with `lstat`/`readlink`, must never resolve or execute them, and must recover
behavior from regular files inside the content-addressed tree. Any needed probe
launcher must be recreated as a reviewed relative/in-tree fixture.

A byte-identical working replica remains under
`/tmp/agent-orchestration-g0-evidence/` on the originating machine, but the
implementation handoff depends on the durable locator above. Before moving to
another host, copy the complete content-addressed directory without
modification and verify the deterministic archive digest. Do not commit the raw
failed run trees to the repository.

## Limitations

- The deterministic provider fixture is not a live model. It proves the
  production public runtime currently supplies no OS denial around the
  provider process; it does not characterize every behavior of a provider CLI.
- The frozen evidence tree's 24 absolute `/tmp` symlinks are not executable
  handoff artifacts. Their target bytes are outside the archive identity, so
  downstream work must use only audited regular in-tree sources.
- Known-sentinel probes are falsifiers, not a complete non-interference proof.
  A later passing implementation also needs mount-plan audit, symlink-escape
  cases, fail-closed backend tests, process-tree quiescence, and runtime
  attestation.
- The candidate is intentionally writable and shared across phases. Even a
  passing prerequisite can prove only that controller-owned/raw-runtime
  authorities are absent at launch; it cannot prevent a colluding earlier
  phase from deliberately relaying allowed data through a product file.
- The product manifest is a correct projection filter, not a security boundary.
- Historical retrieval was classified from the implemented capability surface
  and was not tested by contacting remote repositories or browser services.
- The initial fixture declared a prior scalar input but did not assert that it
  reached phase two. Frozen lowering evidence shows it did not; the report
  records that as a separate failure and the future E2E must observe the
  rendered scalar directly.
- The check adapter is diagnostic evidence only for the existing typed command
  result contract, not product-code filesystem isolation or production
  experiment apparatus. Its ambient child-launch behavior must be replaced by
  the no-result isolated launcher before planned visible checks execute
  provider-authored code.
- No broad pytest suite was run after the core G0 failure. The governing plan
  says to stop at the recorded diagnostic rather than run later gates.
- A fresh host feasibility probe after this report found Bubblewrap 0.9.0 at
  fixed path `/usr/bin/bwrap`; its file/ancestor ownership, modes, xattrs, and
  binary digest passed the initial file-level checks, but the proposed
  backend's complete dynamic loader/library/cache startup-closure identity is
  not yet implemented evidence. At `2026-07-23T21:32:15Z`, the exact command
  `/usr/bin/bwrap --unshare-user --uid 0 --gid 0 -- /bin/true` failed with
  `bwrap: setting up uid map: Permission denied` (exit 1).
  `kernel.unprivileged_userns_clone=1` and
  `user.max_user_namespaces=514239`, while
  `kernel.apparmor_restrict_unprivileged_userns=1`. This is not passing I0
  evidence: because the sealed-rootfs executable proof also requires a real
  namespace, the current host is expected to stop first at `I0E_BLOCKED` (and
  would also be `I0_BLOCKED`) until a reviewed AppArmor/system configuration,
  privileged reviewed rootfs probe, or independently designed backend enables
  the required real namespace execution.

These limitations narrow the claims; none changes the `G0_BLOCKED` decision.
