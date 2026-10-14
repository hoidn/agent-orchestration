# Run-Ref Confinement Feasibility Evidence

- **Status:** evidence ledger for [the run-ref confined child environments plan](../../plans/2026-10-14-run-ref-expression-environments-plan.md). Feasibility evidence, not release qualification.
- **Design authority:** [Workflow Lisp Run-Ref Confined Child Environments](../../design/workflow_lisp_run_ref_expression_environments.md).
- **Host:** reference workstation, Linux 7.0.0-38-generic x86_64. All commands run from the worktree root with `PYTHONPATH=<worktree>`.

## Task 0: baseline and readiness (2026-10-14)

Tested commit `0c156966bd25e598b44eafcdab0670236676d3b9` on branch `feat/run-ref-confined`, isolated worktree `.worktrees/run-ref-confined`. `git status --short` was empty (no dirty paths in the worktree). The main checkout carries other sessions' uncommitted hunks; they are not touched by this branch.

### Baseline tests

| Command | Exit | Result |
| --- | --- | --- |
| `pytest -q tests/test_workflow_lisp_closed_run_ref_placement.py tests/test_workflow_evaluated_run_ref.py tests/test_workflow_evaluated_run_ref_settlement.py tests/test_workflow_run_ref_config.py` | 0 | 260 passed in 284.46s; no pre-existing failures |
| `ORCHESTRATE_E2E=1 pytest -q tests/e2e/test_e2e_workflow_evaluated_run_ref.py tests/test_workflow_lisp_closed_run_ref_placement.py::test_closed_path_run_ref_placement_round_trip` | 0 | 19 passed in 47.70s (path-mode compatibility oracles, reused; no new fixtures) |

### Readiness probe

| Prerequisite | Command | Observation | Gate status |
| --- | --- | --- | --- |
| `bwrap` | `command -v bwrap; bwrap --version` | `/usr/bin/bwrap`, `bubblewrap 0.9.0` | ready (F2, F3, F4) |
| Container engines | `command -v podman skopeo umoci crane oras docker buildah regctl` | none installed | expected; the design forbids an engine |
| Unprivileged user namespaces | `cat /proc/sys/kernel/unprivileged_userns_clone /proc/sys/user/max_user_namespaces /proc/sys/kernel/apparmor_restrict_unprivileged_userns`; `bwrap --ro-bind / / --unshare-user --unshare-pid --unshare-net --dev /dev --proc /proc -- id` | `1`, `474829`, `1`; launch exit 0 (AppArmor restriction is on but permits bwrap) | ready |
| Network namespace | `bwrap ... --unshare-net ... -- bash -c 'cat /proc/net/dev; exec 3<>/dev/tcp/1.1.1.1/53'` | only `lo`; `connect: Network is unreachable` | ready (F3) |
| cgroup v2 delegation | `stat -fc %T /sys/fs/cgroup`; `cat .../user@1000.service/cgroup.{controllers,subtree_control}` | `cgroup2fs`; `cpu memory pids` delegated and enabled for `user@1000.service` | ready, with the caveat below |
| Controllers on the controller's own scope | `echo +memory > <self scope>/cgroup.subtree_control` | `Device or resource busy`: the controller's scope holds processes, so the cgroup v2 no-internal-process rule forbids enabling `memory`/`pids`/`cpu` for child slots. `CgroupV2ContainmentRoot.discover()` uses that scope, so its slots expose no `memory.max`/`pids.max`/`cpu.max` | assumption to resolve in F3 |
| Delegated scope with a leaf for the controller | `systemd-run --user --scope -p Delegate=yes -- sh -c 'mkdir $C/ctl; echo $$ > $C/ctl/cgroup.procs; echo "+memory +pids +cpu" > $C/cgroup.subtree_control; mkdir $C/slot; ls $C/slot'` | exit 0; slot exposes `cpu.max`, `memory.max`, `pids.max` | ready (F3 route) |
| Workspace quota | `bwrap --ro-bind / / --dev /dev --proc /proc --size 1048576 --tmpfs /mnt -- dd if=/dev/zero of=/mnt/f bs=65536 count=64` | write stops at 1048576 bytes | ready (tmpfs; charging to `memory.max` is checked in F3) |
| Image import tool | `python3 -c '<anonymous registry v2 token + HEAD manifest library/python:3.12-slim>'` | `200 sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 application/vnd.oci.image.index.v1+json`; no import tool installed, so import is Python stdlib code (pull + layer extraction) | ready (F3), no new dependency |
| Provider CLIs | `codex --version; claude --version` | `codex-cli 0.162.1` (static musl binary under `@openai/codex-linux-x64/vendor`), `2.1.300 (Claude Code)` (glibc ELF) | ready (F4) |
| Provider base-URL/API-key overrides | `codex exec --help`; `strings` on both binaries | codex: `-c/--config key=value`, `openai_base_url`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `CODEX_API_KEY`; claude: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_TELEMETRY` | ready (F4 in-sandbox leg) |
| API-key provider account | `env` filtered for `OPENAI_*`/`ANTHROPIC_*` | none set; only OAuth logins exist, which the design forbids passing through | **BLOCKED** for the F4 upstream leg (Ruling P2) |

No implementation claim is made by Task 0.
