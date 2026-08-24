# Task 5 Report: Launch pinned OMP provider templates

Date: 2026-08-23
Branch: OMP-I1 (worktree `omp-i1-prerequisites`, base `2b5df2fd5c266239e4542fe97f878278e9f3c005`)
Commit: single commit `Launch pinned OMP provider templates`

## Scope

One pinned OMP launch adapter, inherited Landlock write confinement, runtime
visit handoff, exact registry templates, and package assets. No public
binary/lane/session-directory override. Task 6 DSL syntax and public overrides
were not implemented.

## Files

Created:

- `orchestrator/providers/omp_launch.py` (486 lines) — pinned launch adapter.
- `orchestrator/providers/omp_write_confinement.py` (447 lines) — dependency-free
  Landlock exec helper (`--abi 3`, mutation-only rights `0x7FF2`, `no_new_privs`,
  no-follow-admitted directory roots, role-labelled write allowlist, private
  target enforcement, `execve`).
- `orchestrator/providers/omp_templates.py` (68 lines) — five registry templates.
- `orchestrator/omp_assets/__init__.py` + `confs/neutral/config.yml` — launch-time
  neutral conf package (advisor disabled, memory off, `maxConcurrency 1`,
  `maxRecursionDepth 0`, 7 bundled disabled agents).
- `tests/test_provider_omp_launch.py` (17 tests incl. one `e2e`-marked real-binary
  smoke), `tests/test_provider_omp_templates.py` (5), `tests/test_omp_package_assets.py`
  (4), `tests/fixtures/omp/fake_omp.py` (deterministic fake child).

Modified: `registry.py`, `types.py`, `providers/executor.py`, `state.py`,
`workflow/executor.py`, `workflow/validation.py`, `pyproject.toml` (package-data
for `orchestrator.omp_assets`), and the provider-execution/integration/state/
validation/call-policy tests.

## Adapter (Step 5.2/5.4)

- Parser accepts only `run --lane <registry-name> --model <token>`
  [`--conf-root <abs>` (conf lane only, required there)]
  [`--provider-session-dir <abs>` (fresh only)]. Zero positional prompt args.
- Template commands end after the admitted model/conf values; `fresh_command`
  appends `--provider-session-dir ${PROVIDER_SESSION_DIR}`; the adapter converts
  that private argument to OMP `--session-dir` and ordinary calls to
  `--no-session`.
- Source opened no-follow with owner/mode/type checks, descriptor-copy sha256
  against the pin, private digest-named copy under
  `$XDG_CACHE_HOME/omp-i1/private/<sha>`, re-verified; only the private copy is
  probed/executed. Source path substitution is impossible by construction.
- Version probe: exact `omp/<version>\n` stdout, empty stderr, exit 0, `DEVNULL`
  stdin, `close_fds=True`.
- Positive environment: exhaustive 12-name set; `PI_CODING_AGENT_DIR ==
  $HOME/.omp/agent`; loopback `OMP_BROKER_URL` with paired 32-byte hex token;
  env canaries never pass through; planted parent fds not inherited.
- Ambient lanes: unconfined, workspace cwd, frame `confinement: null`.
- Profile lanes: child and probe run through the helper with immutable
  `$HOME/.omp` and only XDG data/state/cache, temp, optional live-session, and
  conf-only workspace write roots; deterministic `$HOME/omp-empty-<sha16>` empty
  cwd (container-root rejection cannot fire); `conf` alone receives
  `--add-dir`; `no-tools`/`conf-inference` receive `--no-tools` and the neutral
  conf; `omp_conf` admits `${inputs.omp_conf_root}`.
- One adapter launch frame appended immediately after child stdout (line-adjacent;
  whitespace-only lines rejected by the accumulator). Frame carries binary
  projection, child argv/cwd/env-names/exit, session id/visit-key/primary
  relpath+sha256, conf manifest, ABI-3 policy digest, and observed relpaths.
- Failures before the child frame return exit 2 with `omp_launch: <reason>` on
  stderr; nonzero child exits are relayed; unsettled streams fail without a frame.

## Helper (Step 5.3)

- Private parser: `--abi 3`, `--digest <sha256>`, fixed protected roles
  (omp-home, system-runtime), exactly one each of data/state/cache/temp write
  roles, optional session/conf-workspace roles, then `-- <private-omp-argv>`.
  Reopens and recomputes everything; unknown/duplicate/wrong-cardinality roles
  or a non-private target fail before restriction/exec.
- Requires Landlock ABI 3+; handles every ABI-3 mutation right via
  `MUTATION_FS_RIGHTS = 0x7FF2`; role rights: write 0x7FF2, protected/read 0.
  `landlock_abi()` masks `(1, 0x1FFF), (2, 0x7FFF), (4, 0xFFFF)` and reports
  ABI 3+ as 4, ABI 2 as 2 (fail-closed). The helper emits NOTHING on stdout
  (stderr-only rc-2 errors); sets `no_new_privs`; `execve`s the private OMP binary.
- The unfinished public provider-isolation subsystem is not activated or widened.

## Runtime handoff (Step 5.3)

- `workflow/validation.py` rejects authored `command_metadata_mode`;
  `${PROVIDER_SESSION_DIR}` is legal exactly once only in a fresh command;
  `${SESSION_ID}` only in resume_command; reserved carrier values win over
  authored/default/step params.
- `workflow/executor.py` resolves the active provider-session visit dir
  (step_id/visit_count) before preparation, creates the `.live` dir only for OMP
  templates, and passes only that trusted directory into `prepare_invocation`.
- `providers/executor.py::_derive_omp_transport_expectation` runs after
  preparation and freezes one `OmpTransportExpectation` from the actual prepared
  adapter argv, code-owned lane policy, concrete model, workspace, explicit
  persistence, and active visit: lane from `LANE_POLICY`; persistence fresh iff
  `ProviderSessionMode.FRESH`; visit_key = basename minus `.live`;
  `child_argv = tuple(command)`; profile lanes require
  HOME/XDG_DATA_HOME/XDG_STATE_HOME/XDG_CACHE_HOME/TMPDIR in the merged env,
  admit the conf root, compute `empty_omp_cwd` + `canonical_policy_digest`;
  ambient lanes carry null manifest/digest. Non-pinned OMP-metadata templates
  yield `(None, None)` (accumulator refusal at execution remains fail-closed
  enforcement).
- Expectation/conf require OMP metadata mode; the accumulator factory refuses
  OMP mode without an expectation and compares the adapter frame against it
  (child argv, session id, primary relpath+sha256, observed relpaths, conf
  manifest, confinement digest).
- Fresh observed inventory is child-generated; the provider executor re-derives
  it post-run from the real visit dir and re-validates once (swap only on
  success). Negative variant preserves the failure.
- Metadata persistence is credential-minimized (no assistant content, tool
  payloads, opaque events, or broker-token values). Empty compatibility spool
  removed on finalized OMP success/failure; transient OMP creates no spool;
  non-OMP retention unchanged. `close_fds=True`, no `pass_fds` everywhere;
  close-time rehash is supplemental observation only.
- Provider code never reaches into `StateManager`.

## Templates (Step 5.4)

All five: model default `openai-codex/gpt-5.6-sol`, STDIN input, fresh-only
session support, `resume_command=None`, `turn_boundary_resume=False`,
`call_policy_bindings={"model": ...}`, `command_metadata_mode=OMP_JSON_STDOUT`,
wrapper `[sys.executable, "-m", "orchestrator.providers.omp_launch"]`:

- `omp` — ambient, write approval.
- `omp_unrestricted_workspace` — ambient, `--yolo`.
- `omp_no_tools` — profile-isolated neutral conf, no workspace `--add-dir`,
  `--no-tools`, write approval.
- `omp_conf` — profile-isolated `${inputs.omp_conf_root}`, workspace `--add-dir`,
  write approval.
- `omp_conf_inference` — registry-available internal (prompt service only),
  neutral conf, no `--add-dir`, `--no-tools`. Prompt CLI admission, not the
  registry name, keeps inference off the public selector.

Templates never expose authored binary/lane/approval flags. Registry merges
`**omp_templates()` into builtins (14 builtins total); exact commands preserved
(verified).

## Landlock mask (Step 5.1 evidence, re-run)

Write/mutation rights only (`0x7FF2`), no READ_FILE/READ_DIR/EXECUTE handled
bits. Real-kernel probe (fake child, ABI 4): 12 allowed / 16 denied — every
profile create/write/truncate/replace/rename/restore attempt under `$HOME/.omp`
fails while each exact XDG data/state/cache, temp, optional live-session, and
conf-only workspace write root succeeds.

## Test evidence

Collect gate: `pytest --collect-only -q` on the three new test files — no
collection errors.

Real-binary smokes (all `-m e2e`, pinned acceptance build
`/home/ollie/.cache/omp-i1/root-a-evidence/dist-omp`, sha
`f1ffead4d40e6d3740cd2400522d967b270dad5d43a80de7e70c509d97f88211`,
v17.3.4; real auth home `/home/ollie`):

```
python -m pytest -q tests/test_provider_omp_launch.py -m e2e
3 passed, 16 deselected in 16.29s
```

1. `test_real_pinned_binary_smoke` — profile lane, real confined child: the
   version probe passes through the ABI-3 helper, the child launches with the
   exact positive environment, and its first mutation under `$HOME/.omp` is
   denied by the Landlock write allowlist (EACCES on the natives extraction);
   the adapter relays the nonzero exit. This is the separate real-kernel
   confined-launch probe; the unprivileged write → spawn → restore confinement
   probe (fake child, 12 allowed / 16 denied) runs in the fake suite.
2. `test_real_pinned_binary_ambient_transient_completes` — real pinned binary,
   ambient `omp` lane, `--no-session`: a real session completes (one real model
   call); the OMP JSON transport streams on stdout (real `session` header id →
   `agent_end` with `isTerminal:true`), the adapter appends one real frame
   (lane ambient, persistence none, confinement null, exit 0), and the frame
   session id equals the transport header id.
3. `test_real_pinned_binary_ambient_fresh_completes` — real pinned binary,
   ambient `omp` lane, `--provider-session-dir <live>` → OMP `--session-dir`:
   the child writes its journal into the exclusive live dir; the adapter scans
   it and frames the real session id, `visit_key` (basename minus `.live`),
   the primary journal relpath + 64-hex sha256, and the observed inventory
   containing the primary.

To make the real transport contract hold, the adapter's OMP child argv now
carries `--mode=json` (the binary's JSON-output switch — the namesake of the
`OMP_JSON_STDOUT` metadata mode) directly after the session flag; the fake-child
exact-argv assertions were updated to the same token list and remain green.

Ordered gate: all fake-child tests pass before the real-binary smokes run.

Focused gate (brief's exact command):

```
369 passed in 42.63s
```

(tests/test_provider_omp_launch.py incl. real-kernel confinement probe,
templates, package assets, call policy, provider execution, integration,
state manager, AT72 persistence, workflow shared validation.)

Fresh e2e (integration suite): positive re-derivation and negative
fabricated-inventory tests both green; transient OMP e2e green.

Collect gate: `pytest --collect-only -q` on the three new test files — no
collection errors.

## Concerns

- The real pinned binary shells out to `sqlite3` (absent on this host) during
  config load; the child emits a benign `sqlite3: not found` warning to stderr
  and falls back to its bundled storage, so real sessions still complete.
  Confined runs surface the denial at the earliest denied mutation (natives
  extraction under `$HOME/.omp`) rather than a DB write. The write-only ruling
  is unchanged.
- The real-binary smokes require the live environment (real auth home
  `/home/ollie`, network + stored provider credentials) and make one real model
  call each; they are `e2e`-marked and skipped by default, and are only run
  explicitly after the fake-child gates.
- `test_provider_omp_launch.py` is 830 lines (tests are exempt from the 500-line
  module cap in this task's plan; all new/modified production modules are
  ≤ 500 lines).

---

# Task 5 Review Fix Round (separate commit on `eee1f37a`)

Date: 2026-08-24
Commit: separate fix commit on top of `eee1f37a` (never amended)

## Sequence (as actually executed; RED-before-production not followed)

The fix round did **not** follow RED-before-production. The actual sequence:
production fixes for the 13 findings and 3 minors were written **first**; the
controller stopped the round at that point; the full bytes of the changed
production modules were snapshotted to `.tmp/omp-i1-fix-round/production/`;
production was then restored to `eee1f37a`; the grouped base REDs were
captured honestly against that restored tree (tests/new files kept); and
finally the fixes were reapplied from the snapshot and completed.

### Test-design ruling (not an order deviation)

The empty-cwd `(dev, ino)` identity in the policy digest is preserved (the
brief requires binding opened descriptor identities). The three profile tests
therefore freeze/derive their policy expectation **before** `run()` removes the
exclusive empty cwd and assert the adapter frame against the frozen value. The
adapter keeps its secure post-run rmdir cleanup of the exclusive empty cwd.
This is a test-design ruling, not the order deviation above.

## Recovered base RED evidence

Production was reverted to `eee1f37a` (tests/new files kept) and the affected
selectors replayed to capture the base (pre-fix) failures:

- adapter/helper selected suite: 11 failed (fd-grammar and primary-journal
  not selected) — all as designed; the pre-existing spool tests failed because
  the base code never writes the transport spool.
- `tests/test_provider_integration.py`: 3 failed.
- `tests/test_provider_execution.py`: 1 failed.
- `tests/test_workflow_omp_sessions.py`: 4 failed, 1 passed
  (`test_omp_fresh_success_removes_the_empty_transport_spool` green on both).
- `tests/test_provider_omp_launch.py`: 10 passed → after reapply and the
  harness fixes the suite progressed 10 → 23 → 24 → 25 → 29 → 33 passed.

## Fix-round changes (13 findings + 3 minors)

1. Helper rewrite: fd-based ABI-3 Landlock exec, `MUTATION_FS_RIGHTS 0x7FF2`
   (`0x77F2 | 0x800` MAKE_BLOCK), mutation/write rights only, `no_new_privs`,
   private target enforcement, exact-mask validation, direct ABI version query
   (`--abi 3` answered from the kernel's `LANDLOCK_CREATE_RULESET` path).
2. Code-owned wrapper-prefix freeze: OMP commands must start with
   `(sys.executable, "-m", "orchestrator.providers.omp_launch")`; the adapter
   frame records the post-wrapper `sys.argv[1:]` slice.
3. Empty-cwd exclusivity: executor prepare creates the exclusive empty cwd;
   the adapter opens it at run start and removes it in its run-end finally.
4. fd-bound roots + overlap rejection: every admitted root identity is bound
   via descriptor `(dev, ino)`; overlapping roots are rejected
   ("overlaps runtime root") before confinement.
5. Confinement digest freezes before execution; parent write confinement is
   inherited by the child via the helper's fd-exec.
6. Descriptor-relative no-follow session inventory; bounded primary-journal
   hash (sha256 over capped bytes).
7. Broker-token redaction in the adapter relay **and** the capture layer
   (`output_capture.py` / `step_executor.py`); relay redaction is total for
   child stderr; the real generated token is observable only via the fake
   child's `token_file` side channel (64-hex, differs from the caller token).
8. Full minimized projection persisted in the step debug (`messages`,
   `total_tokens`, `total_cost`, `final_provider`, `final_model`,
   `launch_frame`) and in the session metadata `parser_summary`.
9. `.live` directory exclusivity fails closed: a pre-existing OMP fresh live
   dir raises `RuntimeError` before any child launch.
10. Spool retention semantics: `retain_transport_spool =
    (self.debug or exit_code != 0) and not omp_fresh` — OMP JSON transport is
    memory-only, so the empty compatibility spool is removed on every
    finalized OMP fresh visit (success **and** failure); non-OMP metadata
    modes keep the exact pre-Task-5 retention rules (retained on failure).
11. Post-wrapper argv freeze covers the fresh command; `--provider-session-dir`
    is converted to the private OMP `--session-dir`.
12. `start_new_session=True` for the child process group and whole-group
    SIGKILL on timeout.
13. Workflow evidence tests cover the projection persistence, spool retention
    semantics, `.live` exclusivity, and the run-end cleanup contract.

Three new discoveries during the round (all addressed):

- **execveat/scripts kernel limitation**: `os.execve(fd, ...)` (execveat
  AT_EMPTY_PATH) cannot exec shebang scripts (the interpreter receives an
  empty script path → ENOENT); native ELF binaries work. Production pinned
  binary is an ELF, so the helper's fd-exec is correct; the test fake is
  executed through a compiled native C launcher
  (`tests/fixtures/omp/fake_launcher.c`) that transfers to `python3` plus the
  real fake script.
- **Machine umask 0o002**: default dirs are 0775/group-writable; the harness
  and helper-private copy dirs require explicit `chmod 0o700`.
- **Empty-cwd parent check**: requires owner + no group/other WRITE
  (`st_mode & 0o022 == 0`), not `0o077`; real homes (0750/0755) must launch.

## Final verification (committed fix HEAD `9f449840`)

- `python -m pytest tests/test_provider_omp_launch.py tests/test_provider_integration.py
  tests/test_provider_execution.py tests/test_workflow_omp_sessions.py`: **131 passed**.
- Real-binary smokes (`-m e2e`, real pinned binary, real model calls,
  `REAL_AUTH_HOME=/home/ollie`): **3 passed** — profile confined probe fails
  closed at the first denied mutation; ambient transient and ambient fresh
  complete with correct frames (null confinement, session id, visit key,
  primary journal relpath + sha256).
- Brief verification gate (`pytest --collect-only` + the brief's full
  selector list including templates/package-assets/call-policy/state-manager/
  at72/validation): **43 collected, 387 passed**.
- `py_compile` clean for all changed modules; line counts: helper 497,
  adapter 490, `omp_launch_fs.py` 188, provider executor 2994, workflow
  executor 14166, output_capture 308, step_executor 326 (all ≤ 500 where the
  cap applies).

# Task 5 Review Fix Round 2 (separate commit on `9f449840`)

## Sequence (RED-before-production followed)

All round-2 changes were RED-first: the failing test/assertion was written
and observed failing before the production change, then the production
change flipped it GREEN.

## Findings and dispositions (from `'/home/ollie/.omp/agent/sessions/-Documents-agent-orchestration/2026-08-20T18-42-51-430Z_01a0207b-ada6-7000-ac82-4001a26734bc/local/task5-re-review-findings.md'`)

1. **T5-SEC-001 (ambient same-fd exec without Landlock)** — FIXED. Ambient
   lanes route the probe AND the child through a new internal `--exec-only`
   helper mode (`omp_write_confinement.py` `_exec_only_main`): no Landlock,
   but the private target is opened no-follow via the digest-named private
   copy dir, rehashed on the same fd, and `os.execve`'d from the fd; a
   same-UID swap between verify and spawn fails closed. Ambient frames keep
   `confinement: null`; `close_fds=True`. RED:
   `test_ambient_exec_is_not_mutable_after_verify` (swap of the private copy
   between probe and child must fail; root cause of the initial test bug: the
   fixture hardcoded the private-copy basename `fake_launcher` while the
   resolver returns `fake_launcher_<tag>`; fixed to derive the basename).
2. **T5-SEC-003 (duplicate/overlapping opened roots)** — FIXED.
   `verify_root_identity_relations` (fs) rejects duplicate `(dev,ino)`
   identities and, via fd-walk `_fd_is_descendant`, rejects write↔
   protected/read nesting in both directions AND write↔write nesting in both
   directions. The lexical prefilter `_reject_overlaps` now also covers
   write↔write pairs. REDs: `test_helper_rejects_duplicate_opened_root_identity`,
   `test_helper_rejects_nested_write_state_under_data`,
   `test_helper_rejects_nested_write_data_under_state` (both relation
   directions per Main's directive; the brief's overlapping-write-root
   failure is not limited to protected/read roots).
3. **T5-SEC-005 (run-owned visit parent; session-dir identity binding)** —
   FIXED. Workflow verifies `session_dir.parent` (uid + `st_mode & 0o077 == 0`)
   before the exclusive `.live` mkdir (parent created `mode=0o700`;
   `state.py` `provider_session_paths` creates the session root privately).
   Provider executor reopens the fresh dir no-follow and captures
   `(dev,ino)` into the new optional `OmpTransportExpectation.session_dir_identity`;
   post-run, the parent reopens the dir, requires the same identity, and
   calls `revalidate_primary_journal`. RED:
   `test_omp_fresh_non_private_visit_parent_fails_closed`.
4. **T5-SEC-006 (hardlinked primary journal + post-run revalidation)** —
   FIXED. `primary_journal_identity` requires `st_nlink == 1`;
   `revalidate_primary_journal(session_dir, session_id, relpath, sha256)`
   re-derives the primary relpath + bounded sha256 against the framed values
   and fails on any drift; wired into `_finalize_session_result` via
   `_revalidate_fresh_session`. REDs:
   `test_primary_journal_identity_rejects_hardlinked_journal`,
   `test_parent_revalidates_primary_journal_against_frame`.
5. **NEW-T5-FIX-001 (uncaught `OmpConfError` on conf prepare)** — FIXED.
   `_derive_omp_transport_expectation` catches `OmpConfError` around
   `admit_conf_tree` (in addition to `OSError, TypeError, ValueError`) →
   `validation_error`. RED: `test_omp_profile_prepare_cleans_empty_cwd_on_failure`
   (malformed conf must fail preparation, not raise).
6. **NEW-T5-FIX-002 (per-invocation empty-cwd cleanup/nonce)** — FIXED. The
   executor creates the empty cwd with a per-invocation nonce
   (`empty_omp_cwd_path(..., nonce=secrets.token_hex(8))`), appends the
   internal `--empty-cwd <path>` adapter option to the executed argv (frozen
   into the expectation's `child_argv`), and removes the directory on EVERY
   post-create failure. The adapter's outer `finally` (conf_fd close +
   best-effort `rmdir`) spans all post-create setup/execution failures; the
   direct-seam fallback (no `--empty-cwd`) keeps the deterministic
   open-then-create path for tests; `--empty-cwd` is rejected on ambient
   lanes. RED: `test_omp_profile_prepare_uses_per_invocation_empty_cwd`
   (a stale crashed-run leftover must never poison a fresh prepare; the
   stale dir is left in place, the fresh prepare uses a new nonce path).
   Empty-cwd leftover REDs at the adapter level also pass
   (`test_adapter_cleans_empty_cwd_on_pre_child_failure`).
7. **F7 (bundled/user/global agents absent)** — FIXED. The fake OMP binary
   now lists `$PI_CODING_AGENT_DIR/agents` contents (not the parent dir),
   proving repeated launches see exactly the authored `custom.md` and no
   bundled/user/global agents leak. REDs:
   `test_ambient_transient_exact_argv_stream_env_and_frame`,
   `test_no_spool_and_repeated_agent_discovery`.
8. **F8 (single neutral-conf helper)** — FIXED. `omp_assets.neutral_config_path()`
   delegates to `omp_launch.neutral_conf_root()` (lazy import). Guard:
   `test_neutral_conf_path_helper_is_single_sourced` (passes before and
   after).

## Main's write↔write ruling (coalescing, NOT a carve-out)

Directive: no session⊂conf-workspace overlap exemption; every overlapping
write-root pair must fail. For fresh `conf`, the canonical live-session dir
(`<workspace>/.orchestrate/runs/<id>/provider_sessions/<key>.live`) sits
beneath the admitted `conf-workspace` write root, so the redundant separate
Landlock `session` rule is COALESCED away: `profile_root_sets` (the single
shared role-set function used by both the adapter and the parent digest
derivation) omits the `session` write root exactly when
`lane == "conf" and session_dir is within workspace` (lexical
`_path_is_within`; the actual overlap rejection remains identity-based on
opened no-follow fds). Fresh lanes without workspace authority (`no-tools`,
`conf-inference`) keep the explicit `session` role. The parent still binds
and post-run revalidates the live-dir `(dev,ino)` (session_dir_identity),
the visit key, the session id, and the primary journal relpath + bounded
sha256. New integration RED/GREEN:
`test_profile_conf_fresh_session_under_workspace_coalesces` — conf+fresh
launch with the session dir nested under the workspace succeeds, the journal
is written under the workspace root, and the frame carries the exact
session/primary/confinement values with no overlapping write-root pair.
Proof of coalescing: `profile_root_sets` returns write roots
`[data, state, cache, temp, conf-workspace]` (no `session`) for conf+fresh
and `[data, state, cache, temp, session]` for no-tools+fresh.

## Root no-follow walker (Main's blocking directive, joined F2)

`open_dir_no_follow` / `directory_identity` / `_open_root` open the absolute
path component-by-component from `/` via dirfds with
`O_NOFOLLOW|O_DIRECTORY|O_CLOEXEC` at every component; a symlink at ANY
position (final or intermediate) fails closed with a "cannot open" message;
no lexical canonicalization weakens the no-follow-opened root contract.
`SYSTEM_RUNTIME_ROOTS` are resolved once at import (usrmerge) as root-owned
fixed constants. `_open_root` and `verify_root_identity_relations` in the
helper `main()` translate `LaunchFsError` → `ConfinementError` (rc 2).
REDs: `test_helper_rejects_symlink_final_root`,
`test_helper_rejects_symlink_intermediate_root`,
`test_helper_rejects_duplicate_opened_root_identity`,
`test_helper_root_open_is_race_closed`, `test_digest_rejects_symlink_root`.

## Final verification (round-2 worktree HEAD, uncommitted at report time)

- `tests/test_provider_omp_launch.py`: **46 passed** (incl. nested-write REDs
  x2, root-fix REDs x4, overlap x3, duplicate, swap test, F7 x2, conf+fresh
  coalesce).
- Full affected gate (launch, execution, workflow sessions, assets,
  templates, session, transport, conf, pin): **545 passed**.
- Brief verification gate (launch, templates, assets, call-policy,
  execution, integration, state-manager, at72, shared-validation):
  **404 passed**.
- Real-binary e2e smokes (`-m e2e`, real pinned binary, real model calls):
  **3 passed** (profile confined probe fails closed at first denied
  mutation; ambient transient and ambient fresh complete with correct
  frames).
- `py_compile` clean for all changed modules; line counts at commit time:
  adapter 452, `omp_launch_fs.py` 500, helper 497 (all ≤ 500).
- `.tmp/` (worktree-local TMPDIR for the C launcher cache) preserved
  untracked.

## Round 3 (fix round 3/5, review findings RED-first)

### Findings and dispositions (binding source: `'/home/ollie/.omp/agent/sessions/-Documents-agent-orchestration/2026-08-20T18-42-51-430Z_01a0207b-ada6-7000-ac82-4001a26734bc/local/task5-round3-findings.md'`)

1. **T5-SEC-003 — mount-alias overlap escape.** A bind-mounted alias of a
   protected root (e.g. `$HOME/.omp/subdir` mounted elsewhere) at a lexically
   disjoint write root bypassed the opened-identity descendant checks, and
   `no_new_privs` does not remove existing mounts or CAP_SYS_ADMIN.
   **Disposition (fail-closed, keep legitimate separate mounts admissible):**
   `omp_launch_policy.verify_root_identity_relations` now parses
   `/proc/self/mountinfo` ONCE (longest mount-point prefix → mount id per
   opened root) and, for every write×guarded pair on the SAME superblock
   (`st_dev`), requires the same mount id — a different mount id raises
   `LaunchFsError` "is a bind-mounted alias view of the ... root's
   filesystem". Genuine separate superblocks (tmpfs, other partitions)
   short-circuit admissible via `st_dev` inequality (no mountinfo lookup).
   `os.statx` is unavailable on this kernel (verified at runtime), so the
   mount id comes from `/proc/self/mountinfo`, read after the roots were
   opened no-follow. Alias mounts created BEFORE helper start are caught;
   the mountinfo snapshot is taken at admission time.
2. **T5-SEC-005 — fresh `.live` identity checked only after child mutation.**
   The parent froze `(dev, ino)` but the adapter/helper got only pathnames.
   **Disposition:** code-owned internal env carriers
   (`_OMP_I1_EMPTY_CWD`, `_OMP_I1_SESSION_DIR`, `_OMP_I1_SESSION_DIR_IDENTITY`;
   `CARRIER_ENV_NAMES` in `omp_launch_policy`) carry the frozen identity to
   the adapter/helper. The adapter compares `open_session_dir_verified`
   BEFORE spawning the child (rc 2, "identity"); the helper compares the same
   retained session-root fd before `add_rule`/exec via
   `verify_session_identity`. No public CLI flag, no `pass_fds`; carriers are
   rejected if authored at the provider/workflow boundary (prepare fails with
   "authored internal OMP carrier") and stripped by the helper before the
   exact positive child exec env.
3. **T5-SEC-006 — parent/adapter fresh journal revalidation not atomic to
   one visit fd.** **Disposition:** `open_session_dir_verified` opens the
   visit dir once (no-follow, owner/mode + expected identity), and inventory
   (`session_inventory_fd`) and primary derivation
   (`primary_journal_identity_fd`) run descriptor-relatively on that same
   retained fd; the executor's `_revalidate_fresh_session` and
   `_omp_fresh_observed_accumulator` do the same. A path swap between checks
   cannot redirect attribution.
4. **Executor post-create cleanup leaks.** `prepare_invocation` leaked the
   per-invocation empty cwd when a later error (digest, identity capture,
   wrapper mismatch, expectation construction) escaped.
   **Disposition:** `_derive_omp_transport_expectation` returns
   `(expectation, error, empty_cwd)`; the caller owns cleanup on EVERY error
   path (single ownership flag), and `ProviderInvocation` construction is
   guarded so a construction failure also cleans.
5. **Direct-seam fallback adopted pre-planted empty dirs.** The adapter's
   deterministic-path open-then-create adopted any pre-existing empty dir.
   **Disposition:** the `--empty-cwd` flag was REMOVED from the exact
   grammar (parser rejects it: "unexpected option"); the parent-prepared cwd
   travels only via `_OMP_I1_EMPTY_CWD` and is open-only; the direct seam
   now exclusive-creates (`create_empty_omp_cwd`), so a pre-planted dir
   fails with "empty OMP cwd already exists".
6. **Stale report claim + exact-grammar/conf_fd coverage.**
   **Disposition:** removed the stale "helper emits `omp_write_confinement.v1`
   stdout" claim (the helper is stdout-silent; stderr-only rc-2 errors) and
   the stale `0x77F2` mask mentions (`0x7FF2` since round 2); added
   exact-grammar + carrier + cleanup + conf_fd coverage tests.

### Evidence fixes (round-3 finding 7)

- `test_ambient_exec_is_not_mutable_after_verify`: chmod 0o700 BEFORE
  writing the evil bytes, then chmod 0o500, and asserts the private copy
  actually contains the swapped bytes — the swap is real, not vacuous.
- `test_helper_root_open_is_race_closed`: the vacuous
  `assert b"orchestrator.omp_launch.v1" not in b""` was replaced with a real
  "cannot open" stderr assertion plus a non-vacuous frame check.

### Module split (500-line cap trigger)

`omp_launch_fs.py` reached 669 lines after round-3 hardening. The
admission/binding policy (carriers, mount topology, identity relations,
fresh-session identity compare) is a coherent layer with a one-way import
(policy → fs primitives, no cycle), so it moved to the NEW module
`orchestrator/providers/omp_launch_policy.py` (249 lines) — admitted solely
by the ≤500 production cap; `revalidate_primary_journal` inlines its identity
compare to avoid a policy↔fs cycle. Line counts at round-3 commit time:
adapter 479, `omp_launch_fs.py` 452, `omp_launch_policy.py` 249, helper 464
(all ≤ 500; executor 3200 is the pre-existing giant, exempt by the plan).

### RED-first evidence (on `e1365f8b` before re-application)

- `test_parser_rejects_internal_empty_cwd_flag`: base accepted `--empty-cwd`
  (rc 2 only for an unrelated missing path; "unexpected" never appeared).
- `test_ambient_fresh_rejects_mismatched_session_identity_before_child`:
  rc 0; the child ran with a mismatched identity carrier.
- `test_profile_helper_rejects_mismatched_session_identity`: rc 2 with
  "exec of the private target failed" — no identity comparison text.
- `test_adapter_direct_seam_rejects_preplanted_empty_cwd`: rc 0 — the
  pre-planted empty dir was adopted.
- `test_fresh_session_scan_is_atomic_to_one_visit_fd` /
  `test_verify_root_identity_*`: ImportError (`omp_launch_policy` absent).
- `test_omp_profile_prepare_cleans_empty_cwd_on_failure`: raw
  `ConfinementError` escaped (blocker file as `XDG_DATA_HOME`).
- `test_omp_profile_prepare_cleans_empty_cwd_on_identity_failure`:
  `omp-empty-*` leftover after the session-identity capture failure.
- `test_omp_profile_prepare_exact_grammar_and_env_carrier`: ImportError
  (`EMPTY_CWD_ENV` absent on base).

### Verification (round-3 worktree HEAD)

- Round-3 selectors: launch suite 8/8 RED-then-GREEN; execution suite 3/3
  RED-then-GREEN (after the pre-create 2-tuple returns were converted).
- Affected suites: `test_provider_omp_launch.py` 54/54,
  `test_provider_execution.py` 85/85.
- Brief verification gate (launch, templates, assets, call-policy,
  execution, integration, state-manager, at72, shared-validation):
  **414 passed**; collect-only 65 tests collected.
- Real-binary e2e smokes (`-m e2e`, real pinned binary, real model calls):
  **3 passed**.
- `py_compile` clean for all changed modules; `.tmp/` preserved untracked.
