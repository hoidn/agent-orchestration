# Run-Ref Confinement Feasibility Evidence

- **Status:** evidence ledger for [the run-ref confined child environments plan](../../plans/2026-10-14-run-ref-expression-environments-plan.md). Feasibility evidence, not release qualification.
- **Design authority:** [Workflow Lisp Run-Ref Confined Child Environments](../../design/workflow_lisp_run_ref_expression_environments.md).
- **Host:** reference workstation, Linux 7.0.0-38-generic x86_64. All commands run from the worktree root with `PYTHONPATH=<worktree>`.

The Task 0/1 account prerequisite and F4/P2 results below are historical.
The [native-authentication follow-up](#task-10-native-authentication-follow-up-2026-10-15)
records the current selected investigation without replacing those results or
qualifying F4.

## Task 0: baseline and readiness (2026-10-14)

Tested commit `0c156966bd25e598b44eafcdab0670236676d3b9` on branch `feat/run-ref-confined`, isolated worktree `.worktrees/run-ref-confined`. `git status --short` was empty (no dirty paths in the worktree). The main checkout carries other sessions' uncommitted hunks; they are not touched by this branch.

### Baseline tests

| Command | Exit | Result |
| --- | --- | --- |
| `pytest -q tests/test_workflow_lisp_closed_run_ref_placement.py tests/test_workflow_evaluated_run_ref.py tests/test_workflow_evaluated_run_ref_settlement.py tests/test_workflow_run_ref_config.py` | 0 | 260 passed in 284.46s; no pre-existing failures |
| `ORCHESTRATE_E2E=1 pytest -q tests/e2e/test_e2e_workflow_evaluated_run_ref.py tests/test_workflow_lisp_closed_run_ref_placement.py::test_closed_path_run_ref_placement_round_trip` | 0 | 19 passed in 47.70s (path-mode compatibility oracles, reused; no new fixtures) |

### Readiness probe

Each row names a probe in the command block below; outputs are quoted verbatim. `X` is the codex native binary `/home/ollie/.nvm/versions/node/v20.19.4/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex`; `C` in probe 5 is the delegated scope's cgroup directory, derived inside the scope from `/proc/self/cgroup`.

| Prerequisite | Probe | Observation | Gate status |
| --- | --- | --- | --- |
| `bwrap` | 1 | `/usr/bin/bwrap`, `bubblewrap 0.9.0` | ready (F2, F3, F4) |
| Container engines | 1 | none of podman, skopeo, umoci, crane, oras, docker, buildah, regctl installed | expected; the design forbids an engine |
| Unprivileged user namespaces | 2 | `1`, `474829`, `1`; launch exit 0 (the AppArmor restriction is on but permits bwrap). This probe binds host `/` read-only and is **not** confinement evidence | ready |
| Network namespace | 3 | only `lo`; `Network is unreachable` | ready (F3) |
| cgroup v2 delegation | 4 | `cgroup2fs`; `cpu memory pids` delegated and enabled for `user@1000.service` | ready, with the caveat below |
| Controllers on the controller's own scope | 4 | `Device or resource busy`: the controller's scope holds processes, so the cgroup v2 no-internal-process rule forbids enabling `memory`/`pids`/`cpu` for child slots. `CgroupV2ContainmentRoot.discover()` uses that scope, so its slots expose no `memory.max`/`pids.max`/`cpu.max` | assumption to resolve in F3 |
| Delegated scope with a leaf for the controller | 5 | exit 0; slot exposes `cpu.max`, `memory.max`, `pids.max` | ready (F3 route) |
| Workspace quota | 6 | write stops at 1048576 bytes with `No space left on device` | ready (tmpfs; charging to `memory.max` is checked in F3) |
| Image source | 7 | anonymous registry v2 token and manifest HEAD succeed. No import tool is installed; the stdlib importer (pull + layer extraction) is an F3 deliverable. Depends on Docker Hub network access and its anonymous pull rate limits | registry reachable; stdlib importer is an F3 deliverable |
| Provider CLIs | 8 | `codex-cli 0.162.1` (`X` is a static musl binary), `2.1.300 (Claude Code)` (glibc ELF) | ready (F4) |
| Provider base-URL/API-key overrides | 8 | codex: `-c, --config <key=value>`; strings `CODEX_API_KEY OPENAI_API_KEY openai_base_url OPENAI_BASE_URL`; claude strings `ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC DISABLE_TELEMETRY` | ready (F4 in-sandbox leg) |
| API-key provider account | 8 | `0` variables matching `^(OPENAI\|ANTHROPIC)_`; only OAuth logins exist, which the design forbids passing through | **BLOCKED** for the F4 upstream leg (Ruling P2) |

The main checkout (not this worktree) carried other sessions' uncommitted hunks at baseline time in `specs/{cli,state,providers,versioning}.md`, `docs/design/workflow_lisp_evaluated_execution.md`, `orchestrator/workflow/evaluated/providers.py`, `tests/test_workflow_evaluated_consumers.py`, `tests/workflow_evaluated_consumer_sources.py` and `workflows/README.md`; this branch does not touch them.

Probe commands and verbatim output:

```text
# 1
$ command -v bwrap; bwrap --version; command -v podman skopeo umoci crane oras docker buildah regctl
/usr/bin/bwrap
bubblewrap 0.9.0
# 2
$ cat /proc/sys/kernel/unprivileged_userns_clone /proc/sys/user/max_user_namespaces /proc/sys/kernel/apparmor_restrict_unprivileged_userns
1
474829
1
$ bwrap --ro-bind / / --unshare-user --unshare-pid --unshare-net --dev /dev --proc /proc -- sh -c id; echo exit=$?
uid=1000(ollie) gid=1000(ollie) groups=1000(ollie),65534(nogroup)
exit=0
# 3
$ bwrap --ro-bind / / --unshare-user --unshare-net --dev /dev --proc /proc -- bash -c 'tail -n +3 /proc/net/dev | cut -d: -f1; exec 3<>/dev/tcp/1.1.1.1/53 && echo CONNECTED || echo REFUSED'
    lo
bash: connect: Network is unreachable
bash: line 1: /dev/tcp/1.1.1.1/53: Network is unreachable
REFUSED
# 4
$ stat -fc %T /sys/fs/cgroup
cgroup2fs
$ cat /sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/cgroup.controllers /sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/cgroup.subtree_control
cpu memory pids
cpu memory pids
$ S=/sys/fs/cgroup$(sed -n 's/^0:://p' /proc/self/cgroup); echo "+memory" > "$S/cgroup.subtree_control"; echo "exit=$?"
/bin/bash: line 7: echo: write error: Device or resource busy
exit=1
# 5
$ systemd-run --user --scope -p Delegate=yes --quiet -- sh -c 'C=/sys/fs/cgroup$(sed -n "s/^0:://p" /proc/self/cgroup); echo "C=$C"; mkdir "$C/ctl" && echo $$ > "$C/ctl/cgroup.procs" && echo "+memory +pids +cpu" > "$C/cgroup.subtree_control" && cat "$C/cgroup.subtree_control" && mkdir "$C/slot" && ls "$C/slot" | grep -E "^(memory|pids|cpu)\.max$"; rmdir "$C/slot"'; echo "exit=$?"
C=/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/run-rb16620cecfe849b7a17bab4ab5e8551b.scope
cpu memory pids
cpu.max
memory.max
pids.max
exit=0
# 6
$ bwrap --ro-bind / / --dev /dev --proc /proc --size 1048576 --tmpfs /mnt -- sh -c 'dd if=/dev/zero of=/mnt/f bs=65536 count=64; stat -c %s /mnt/f'
dd: error writing '/mnt/f': No space left on device
17+0 records in
16+0 records out
1048576 bytes (1.0 MB, 1.0 MiB) copied, 0.000576231 s, 1.8 GB/s
1048576
# 7
$ timeout 20 python3 -c "
import json, urllib.request
token = json.load(urllib.request.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull', timeout=10))['token']
request = urllib.request.Request('https://registry-1.docker.io/v2/library/python/manifests/3.12-slim', method='HEAD', headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.index.v1+json'})
response = urllib.request.urlopen(request, timeout=10)
print(response.status, response.headers['Docker-Content-Digest'], response.headers['Content-Type'])
"
200 sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 application/vnd.oci.image.index.v1+json
# 8
$ codex --version; claude --version
codex-cli 0.162.1
2.1.300 (Claude Code)
$ "$X" exec --help | grep -- '-c, --config'
  -c, --config <key=value>
$ strings -n 10 "$X" | grep -oE 'OPENAI_BASE_URL|CODEX_API_KEY|OPENAI_API_KEY|openai_base_url' | sort -u | tr '\n' ' '
CODEX_API_KEY OPENAI_API_KEY openai_base_url OPENAI_BASE_URL
$ strings -n 12 /home/ollie/.local/share/claude/versions/2.1.300 | grep -oE 'ANTHROPIC_(BASE_URL|API_KEY|AUTH_TOKEN)|CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC|DISABLE_TELEMETRY' | sort -u | tr '\n' ' '
ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC DISABLE_TELEMETRY
$ env | grep -cE '^(OPENAI|ANTHROPIC)_'
0
```

No implementation claim is made by Task 0.

## Task 1: feasibility F1-F4 (2026-10-14)

Spike code (throwaway, Ruling P5 importer, holder/spawner launcher, F3/F4 drivers) was committed in `fdfa8b0d` (`experiments: add run-ref confinement feasibility spike`) and removed in the retained-slice commit; restore it with `git checkout fdfa8b0d -- experiments/run_ref_confinement_spike`. Task 1 adds no production code. Retained tests test only seams that exist today.

| Gate | Status | Evidence |
| --- | --- | --- |
| F1 child entry closure | **PASS** (programmatic seam, Ruling P1) | `tests/test_workflow_lisp_run_ref_workflow_program.py`, 6 tests |
| F2 authority separation | **PASS** for the separation facts; relocation of `validate_evaluated_child_terminal` is Task 5 | `tests/test_workflow_run_ref_confinement.py` (4 tests) and the F3 escape probe |
| F3 Bubblewrap sibling profile | **PASS** (network, limits, quota, rootfs, commands, escapes, cleanup enforced), with design deltas D-a to D-e below that must return to Design | `tests/e2e/test_e2e_run_ref_confined.py` (5 tests) and the F3 driver output |
| F4 transport probe | in-sandbox leg **PASS**; upstream leg **BLOCKED** (no API-key account; OAuth passthrough forbidden, Ruling P2) | F4 driver output |

### F1: private child entry through the ordinary closed-program builder

Seam: `dataclasses.replace(typed, entry=typed.workflows["controller::candidate-body"])` built with a fresh `Builder` by `closed/build.py::build_closed_program`. The child is a non-exported workflow whose body uses an imported helper module (`helper::bump` defun, `helper::fetch` defproc with a command), declared inputs `(seed Int) (task String)`, a provider binding (`providers.review`) and nested `let*`/`if`/`loop/recur`.

| Property | Result |
| --- | --- |
| Values | evaluating the read-back child artifact with inputs `seed=0, task="t"` returns `3`; effects in order `provider("t")`, `command(1)`, `command(2)`, `command(3)` |
| Own entry, signature, sites, summary | entry `workflow:controller::candidate-body`, params `[seed, task]`, site classes `command`, `provider`; transitive summary `{UsesCommandEffect(fetch), UsesProviderEffect(providers.review)}` |
| Canonical owners and owner bindings | definition owner `helper` for `fetch`; configuration `providers.review -> probe-provider`, command `fetch` stable command `["python", "probe.py"]` |
| No parent runtime binding | a child that names `limit`, bound only by `let*` in the parent `run`, fails compilation with `name_unknown`; evaluating the child with an extra parent input fails with `closed_input_names` |
| Identity | digest equal after `ClosedProgram.from_artifact` round trip and after a rebuild in a different root whose parent `run` body differs |

TDD: the seam exists, so the tests passed on first run. RED was shown by mutation (`child = typed`, i.e. building the parent entry instead of the child): `4 failed, 2 passed`; restored: `6 passed`.

### F2: authority outside the clone

- `orchestrator run child.orc --state-dir <control>` (cwd = clone) writes `run.json`, `closed_program.json`, `memo.jsonl` only under `<control>/<run_id>/`; the clone gets no `.orchestrate/runs`. RED finding: the clone still receives the compile cache `.orchestrate/build/<key>/closed_program.json` plus `workspace.guard`/`workspace.lock`. A confined child must take its program from the parent's checked artifact and never compile in the clone (Task 5).
- `run_ref/evaluated_child.py::_captured_child_authority(<control>/<run_id>)` reads the triplet from the external root; the memo terminal value is `42` for input `41`.
- A control root containing only a forged `result.json` raises `OSError` in `_captured_child_authority`: a result file alone is not authority.
- In the real sandbox (F3 escape probe) the guest cannot see the external control root, the launch gate directory, the parent repository or the worktree; its only mounts are `["/", "/dev", "/dev/full", "/dev/null", "/dev/pts", "/dev/random", "/dev/tty", "/dev/urandom", "/dev/zero", "/proc", "/result", "/run", "/run/runref", "/tmp", "/workspace"]`. `/run/runref` is the spawner's guest-visible control directory (FIFOs and leaf scripts), not authority.

### F3: real rootless profile from a digest-pinned imported image

Image (installation-time step, Ruling P5): `python3 experiments/run_ref_confinement_spike/image_import.py ~/.cache/run-ref-spike-images library/python 3.12-slim` resolved the linux/amd64 manifest and imported `docker.io/library/python@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe` (config `sha256:df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316`) in 4.6 s: anonymous registry v2 pull, per-blob SHA-256 verification, gzip layer extraction with whiteouts, devices dropped, profile mount points `/workspace` and `/result` added, read-only seal, canonical tree digest `sha256:973cd37339e7ef7627c497292983fa6b110ef784f121f41d8a52edc6385fadae` (125 MiB). Admission re-hashes the tree (0.28 s) and refused a mismatching record with `run_ref_environment_changed: sealed rootfs digest mismatch`.

Driver: `timeout 300 python3 experiments/run_ref_confinement_spike/f3_driver.py ~/.cache/run-ref-spike-images/records/sha256-2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe.json` (exit 0; re-execs itself under `systemd-run --user --scope -p Delegate=yes`). Slot limits written: `{"memory.max": "268435456", "memory.swap.max": "0", "pids.max": "64", "cpu.max": "100000 100000"}`. Holder argv: `bwrap --unshare-user --unshare-ipc --unshare-pid --unshare-net --unshare-uts --unshare-cgroup --disable-userns --die-with-parent --new-session --cap-drop ALL --clearenv --setenv PATH /usr/local/bin:/usr/bin:/bin --setenv HOME /tmp --ro-bind /home/ollie/.cache/run-ref-spike-images/rootfs/sha256-2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe / --dev /dev --proc /proc --size 16777216 --tmpfs /workspace --size 8388608 --tmpfs /tmp --tmpfs /run --ro-bind /tmp/runref-f3-uio_7tw_/ipc /run/runref --bind /tmp/runref-f3-uio_7tw_/result /result --info-fd 5 -- <spawner>`.

| Check | Measurement |
| --- | --- |
| Workflow command with image executable pin | argv[0] `/usr/local/bin/python3.12` (sha256 `0e6475dfda68a9b2...` from the sealed tree manifest; host `shutil.which("python3")` is `/home/ollie/miniconda3/bin/python3` and absent in the guest); exit 0, cwd `/workspace`, clone edit visible to the host after quiescence, result read from `/result/attempt-1/result.json` |
| `--unshare-net` | interfaces `["lo"]`; TCP 1.1.1.1:53 `ENETUNREACH`; DNS `EAI_AGAIN (-3)`; host abstract unix socket `ECONNREFUSED` |
| `memory.max` 256 MiB, swap 0 | allocation loop killed at 240 MiB, exit 137, `oom_kill` +1, `memory.peak` 256.0 MiB |
| `pids.max` 64 | `fork failed after 59 Resource temporarily unavailable`; `pids.events max` 1; leftovers killed by `cgroup.kill` |
| `cpu.max` 1 CPU | four busy loops for 2 s: 2.08 CPU-s in 2.06 s wall, `nr_throttled` 21 |
| Workspace quota (tmpfs 16 MiB) | `dd` of 32 MiB stops at 16646144 bytes (`No space left on device`); slot `shmem` +15.88 MiB and still charged after the writer exits (tmpfs pages are charged to the slot and outlive the leaf) |
| Workspace larger than memory | slot 48 MiB with a 128 MiB tmpfs: the writer is OOM-killed (`oom_kill` +1), not refused with ENOSPC; the holder survives |
| Descendant cleanup | `setsid sleep 300 &` left behind: lingering descendants detected and killed through `cgroup.kill`, no `sleep 300` left in the slot |
| Wall time | `sleep 100` with a 1 s budget: killed at 1.012 s |
| Teardown | holder stop leaves the slot unpopulated; slot and scope removed |
| Credentials and privileges | `CapEff`/`CapBnd` `0000000000000000`, `NoNewPrivs` 1, uid 1000, environment `["HOME", "LC_CTYPE", "PATH"]` (`LC_CTYPE` is Python's C-locale coercion), open fds `[0, 1, 2, 3]` (3 is the probe's own `listdir`), nested user namespaces `ENOSPC` |

Escape negatives (all inside the guest; nothing on the host was read by the guest):

| Target | Result |
| --- | --- |
| path `parent_repo` | exists = false |
| path `sibling_clone` | exists = false |
| path `worktree` | exists = false |
| path `authority_control_root` | exists = false |
| path `launch_gate_dir` | exists = false |
| path `host_python` | exists = false |
| path `codex_auth` | exists = false |
| path `claude_dir` | exists = false |
| path `ssh_dir` | exists = false |
| path `user_bus` | exists = false |
| path `docker_sock` | exists = false |
| path `sibling_holder_view` | exists = false |
| write rootfs | DENIED EROFS |
| hardlink rootfs into workspace | DENIED EXDEV |
| hardlink result into workspace | DENIED EXDEV |
| alternates target | DENIED ENOENT |
| host abstract socket | DENIED ECONNREFUSED |
| guest symlink `/workspace/leak -> /etc/hostname`, naive host read through `/proc/<holder>/root/workspace/leak` | **follows into the host filesystem** (returned the host's `/etc/hostname`): naive host reads are an escape |
| same, host no-follow reader (`O_NOFOLLOW` beneath a root fd) | `refused:ELOOP` |
| guest hardlink inside the workspace | no-follow reader `refused:hardlink` (`st_nlink` 2; both names refused) |
| guest-written `.git/hooks/post-checkout` | stays data (`-rwxr-xr-x`); the host never runs Git on the workspace |

The `parent_repo`/`alternates_target` rows used a clone made with `git clone --shared`, so `.git/objects/info/alternates` names the parent's object directory; the guest cannot reach it. A sibling attempt (separate holder and slot) is invisible: its host view path does not exist in the guest and the guest PID namespace shows only `[1, 2, 9, 11]`.

#### Authority assumptions of the existing backend

| Owner | Assumption | Holds for `run_ref_confinement.v1`? |
| --- | --- | --- |
| `CgroupV2ContainmentRoot.discover()` | the delegated root is the controller's own cgroup (`/proc/self/cgroup`), euid-owned, not group/other-writable | **No for limits.** The controller's processes live in that cgroup, so `+memory` in its `cgroup.subtree_control` fails with `EBUSY` (cgroup v2 no-internal-process rule; measured in the tmux scope in Task 0 and here in the transient delegated scope while the driver still lived in it, before it moved to `<scope>/ctl`). Slots under it can never carry `memory.max`/`pids.max`/`cpu.max`. The profile needs a delegated scope whose root holds no processes (controller moved to a `ctl` leaf, controllers enabled on the scope, slots as siblings of `ctl`) |
| `CgroupV2ContainmentRoot.create_slot`/`load_slot` | slots are flat children named `provider-isolation-<32 hex>`; no limit writes | Partly. Membership, `populated`, `cgroup.kill`, `wait_empty` and identity checks are reusable as is. The profile also needs limit writes on the slot and per-leaf sub-cgroups (`<slot>/holder`, `<slot>/<leaf>`) for per-leaf quiescence, which the flat naming rule does not admit |
| `CgroupV2ContainmentSlot.wait_empty` | bounded to 60 s | Holds |
| `DurableLaunchReleaseGate` | private 0700 euid-owned parent opened `O_NOFOLLOW` with device/inode revalidation; one intent -> commit -> single-use non-durable permit per launch, bound to one containment identity | Holds when the gate lives in the external control root and one gate is created per launch (holder and each leaf). Exercised: `["launch_intent", "launch_committed"]`, consumed, replay refused with `ProviderIsolationStateError`. A crash between commit and consume leaves "committed, not consumed": recovery must kill the slot and treat the launch as possibly started |
| `isolation_bubblewrap.execute_bubblewrap_invocation` | one bwrap process per invocation, candidate bound rw from host disk, credential frame delivered into the sandbox | **No.** A persistent quota-bounded workspace cannot be a host bind, and credentials must never enter this profile; the launch shape differs (D-b) |

#### Design deltas (return to Design before Tasks 5-6)

- **D-a, containment root.** Run the controller (or a dedicated launcher) in a delegated `systemd-run --user --scope -p Delegate=yes` scope with a `ctl` leaf; `discover()` as written cannot host limited slots.
- **D-b, leaf launch shape.** Host AppArmor (`apparmor_restrict_unprivileged_userns=1`, profile `bwrap-userns-restrict`) grants user-namespace capabilities only to `bwrap`. Joining a holder's namespaces from the host fails (`nsenter ... reassociate to namespace 'ns/cgroup' failed: Operation not permitted`; `unshare -U -r id`: `write failed /proc/self/uid_map: Operation not permitted`), and `bwrap --bind-fd`/`--bind` of `/proc/<holder>/root/workspace` fails (`No such file or directory` / `Permission denied`). A tmpfs workspace that persists across leaves therefore needs one holder sandbox per child attempt that forks every leaf through an in-sandbox spawner (here image `/bin/sh`), each leaf gated until the host moved it into its own leaf cgroup. The spawner is guest code: the host trusts only cgroup membership/quiescence and bounded post-quiescence reads; exit status and output are untrusted guest data. This replaces "one bwrap process per command/provider".
- **D-c, host reads.** Every host read of candidate files through `/proc/<holder>/root` must be beneath-root no-follow with `st_nlink == 1`; a naive read followed a guest symlink into the host filesystem.
- **D-d, quota admission.** `:workspace-mib` (plus scratch) must be strictly below `:memory-mib` with headroom, or the writer is OOM-killed instead of receiving ENOSPC. tmpfs pages stay charged to the slot after the leaf exits and are released when the holder stops.
- **D-e, rootfs mount points.** A sealed read-only rootfs needs the profile mount points (`/workspace`, `/result`) created at import (done here) and other bind targets under a tmpfs (`/run`, `/opt`).

### F4: provider CLI -> in-sandbox relay -> gateway stub (unix socket)

Driver: `timeout 300 python3 experiments/run_ref_confinement_spike/f4_driver.py <image record> <codex native binary> <claude binary>` (exit 0). The host gateway stub listens on a unix socket in a 0700 control directory, bound into the holder at `/run/gateway.sock`; `relay.py` (guest code, image Python) forwards `127.0.0.1:8080` to it. The stub admits only `POST /v1/responses` and `POST /v1/messages` with a per-attempt random capability (`secrets.token_hex(16)`, never logged), and answers admitted model calls with `502 upstream_blocked` because no API-key account exists. The provider executables were bound read-only from the host (`/opt/provider/codex`, the static musl `codex-cli 0.162.1`; `/opt/provider/claude`, `2.1.300`) instead of being image content; a qualified profile must ship them in the image (Task 10).

| Check | Result |
| --- | --- |
| codex `exec` with `-c model_provider=gw` (`base_url=http://127.0.0.1:8080/v1`, `env_key=RUNREF_GATEWAY_TOKEN`, `wire_api=responses`, retries 0) | gateway saw `[["POST", "/v1/responses"]]`, capability valid, model `gpt-5`; CLI exited 1 on `unexpected status 502 Bad Gateway: upstream_blocked` |
| claude `-p` with `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY=<capability>`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `DISABLE_TELEMETRY=1` | gateway saw 7 x `POST /v1/messages` (retries with backoff), capability valid, no other route; killed by the 60 s wall budget, which shows the provider timeout must be clamped to the remaining child budget |
| non-model route `GET /admin/keys`, `GET /v1/models` | `403` route_not_admitted |
| wrong capability | `401` |
| direct network from the guest (`api.openai.com:443`) | `gaierror -3` (no DNS, only `lo`) |
| credential files in the guest (`~/.codex/auth.json`, `~/.claude/.credentials.json`, `/tmp/codex-home/auth.json`, `/root/.codex/auth.json`) | none present |
| guest environment | `HOME`, `LC_CTYPE`, `PATH`, `PWD`, `RUNREF_GATEWAY_TOKEN` (the scoped attempt capability only) |
| upstream leg | **BLOCKED**: no `OPENAI_*`/`ANTHROPIC_*` API key on this host; OAuth passthrough is forbidden |

### Retained tests

| Module | Nodes | Run |
| --- | --- | --- |
| `tests/test_workflow_lisp_run_ref_workflow_program.py` | 6 | `pytest -q` -> `6 passed`; mutation RED `4 failed, 2 passed` |
| `tests/test_workflow_run_ref_confinement.py` | 4 | first run RED `1 failed, 3 passed` (compile cache in the clone, recorded above), then `4 passed` |
| `tests/e2e/test_e2e_run_ref_confined.py` | 5 (`@pytest.mark.e2e`, `skip_if_no_e2e`, `skip_if_no_cli("bwrap")`, `skip_if_no_cli("systemd-run")`) | `ORCHESTRATE_E2E=1 pytest -q` -> `5 passed`; without the variable `5 skipped`; mutation RED (no `--unshare-all`, `pids.max max`, `memory.max max`, no `--size`, no `ctl` leaf) -> all 5 fail. Fix round 1: the network probe is `python3` `connect_ex(("1.1.1.1", 53))` (host `/usr` bound) instead of a dash `/dev/tcp` redirect, which failed regardless of the namespace; GREEN gives `{"interfaces": ["lo"], "connect": "ENETUNREACH"}`, and mutation RED with `--share-net` gives `{"connect": 0, "interfaces": ["lo", "enp7s0"]}` (connected) |

`pytest --collect-only -q` over the three modules collects 15 tests. Real launches ran in the foreground with `timeout` (each under 10 s), not in tmux. Image store left at `~/.cache/run-ref-spike-images` (125 MiB) for review reproduction.

Full driver output (F3, then F4, capability redacted):

```json
{
 "admission": {
  "image": "docker.io/library/python@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe",
  "tree_digest": "sha256:973cd37339e7ef7627c497292983fa6b110ef784f121f41d8a52edc6385fadae",
  "admit_seconds": 0.28,
  "tampered_record": "run_ref_environment_changed: sealed rootfs digest mismatch"
 },
 "executable_pin": {
  "guest_path": "/usr/local/bin/python3.12",
  "sha256": "0e6475dfda68a9b2d93501449fc47593ca169010e8f4881577b97463fd0c1263",
  "tree_digest": "sha256:973cd37339e7ef7627c497292983fa6b110ef784f121f41d8a52edc6385fadae",
  "host_which_python3": "/home/ollie/miniconda3/bin/python3"
 },
 "containment_root_discover": {
  "path": "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/run-r80f66e5762f2478c944ca337168d8203.scope",
  "enable_memory_for_slots": "EBUSY",
  "has_memory_max": true
 },
 "slot_limits": {
  "memory.max": "268435456",
  "memory.swap.max": "0",
  "pids.max": "64",
  "cpu.max": "100000 100000"
 },
 "release_gate": {
  "events": [
   "launch_intent",
   "launch_committed"
  ],
  "release_consumed": true,
  "replay": "ProviderIsolationStateError"
 },
 "holder_argv": [
  "bwrap",
  "--unshare-user",
  "--unshare-ipc",
  "--unshare-pid",
  "--unshare-net",
  "--unshare-uts",
  "--unshare-cgroup",
  "--disable-userns",
  "--die-with-parent",
  "--new-session",
  "--cap-drop",
  "ALL",
  "--clearenv",
  "--setenv",
  "PATH",
  "/usr/local/bin:/usr/bin:/bin",
  "--setenv",
  "HOME",
  "/tmp",
  "--ro-bind",
  "/home/ollie/.cache/run-ref-spike-images/rootfs/sha256-2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe",
  "/",
  "--dev",
  "/dev",
  "--proc",
  "/proc",
  "--size",
  "16777216",
  "--tmpfs",
  "/workspace",
  "--size",
  "8388608",
  "--tmpfs",
  "/tmp",
  "--tmpfs",
  "/run",
  "--ro-bind",
  "/tmp/runref-f3-uio_7tw_/ipc",
  "/run/runref",
  "--bind",
  "/tmp/runref-f3-uio_7tw_/result",
  "/result",
  "--info-fd",
  "5",
  "--",
  "<spawner>"
 ],
 "seed": {
  "returncode": 0,
  "stdout": "",
  "stderr": "",
  "timed_out": false,
  "lingering_descendants_killed": false,
  "seconds": 0.01
 },
 "workflow_command": {
  "returncode": 0,
  "stdout": "{\"interpreter\": \"/usr/local/bin/python3.12\", \"cwd\": \"/workspace\", \"hello_sha256\": \"acce00233441a330cca3a3d30503c5b9fd84d6d8b57750055217cafe9e0d9b97\"}\n",
  "stderr": "",
  "timed_out": false,
  "lingering_descendants_killed": false,
  "seconds": 0.062,
  "host_result": {
   "interpreter": "/usr/local/bin/python3.12",
   "cwd": "/workspace",
   "hello_sha256": "acce00233441a330cca3a3d30503c5b9fd84d6d8b57750055217cafe9e0d9b97"
  },
  "host_view_hello": "hi\nedited by confined command\n"
 },
 "escape": {
  "returncode": 0,
  "stdout": {
   "exists:parent_repo": false,
   "exists:sibling_clone": false,
   "exists:worktree": false,
   "exists:authority_control_root": false,
   "exists:launch_gate_dir": false,
   "exists:host_python": false,
   "exists:codex_auth": false,
   "exists:claude_dir": false,
   "exists:ssh_dir": false,
   "exists:user_bus": false,
   "exists:docker_sock": false,
   "exists:sibling_holder_view": false,
   "tcp_1.1.1.1:53": [
    "DENIED",
    "ENETUNREACH"
   ],
   "dns_example.com": [
    "DENIED",
    "-3"
   ],
   "interfaces": [
    "lo"
   ],
   "host_abstract_socket": [
    "DENIED",
    "ECONNREFUSED"
   ],
   "write_rootfs": [
    "DENIED",
    "EROFS"
   ],
   "hardlink_rootfs_into_workspace": [
    "DENIED",
    "EXDEV"
   ],
   "hardlink_result_into_workspace": [
    "DENIED",
    "EXDEV"
   ],
   "unshare_user": [
    "DENIED",
    "ENOSPC"
   ],
   "alternates_target": [
    "DENIED",
    "ENOENT"
   ],
   "CapEff": "0000000000000000",
   "CapBnd": "0000000000000000",
   "NoNewPrivs": "1",
   "uid": 1000,
   "open_fds": [
    0,
    1,
    2,
    3
   ],
   "environ": [
    "HOME",
    "LC_CTYPE",
    "PATH"
   ],
   "mounts": [
    "/",
    "/dev",
    "/dev/full",
    "/dev/null",
    "/dev/pts",
    "/dev/random",
    "/dev/tty",
    "/dev/urandom",
    "/dev/zero",
    "/proc",
    "/result",
    "/run",
    "/run/runref",
    "/tmp",
    "/workspace"
   ],
   "visible_pids": [
    1,
    2,
    9,
    11
   ]
  },
  "stderr": "",
  "timed_out": false,
  "lingering_descendants_killed": false,
  "seconds": 0.082
 },
 "host_reads": {
  "naive_symlink_follow_reads_host_etc_hostname": true,
  "nofollow:leak": "refused:ELOOP",
  "nofollow:hello-hardlink": "refused:hardlink",
  "nofollow:hello.txt": "refused:hardlink",
  "hook_is_data": "-rwxr-xr-x"
 },
 "workspace_quota": {
  "returncode": 0,
  "stdout": "15+0 records out\n16646144 bytes (17 MB, 16 MiB) copied, 0.0076615 s, 2.2 GB/s\n16646144\n",
  "stderr": "",
  "timed_out": false,
  "lingering_descendants_killed": false,
  "seconds": 0.021,
  "slot_shmem_delta_mib_after_leaf_exit": 15.88
 },
 "memory_max": {
  "returncode": 137,
  "stdout": null,
  "stderr": "Killed\n",
  "timed_out": false,
  "lingering_descendants_killed": false,
  "seconds": 0.143,
  "stdout_tail": [
   "240"
  ],
  "oom_kill_delta": 1,
  "memory_peak_mib": 256.0
 },
 "pids_max": {
  "returncode": 0,
  "stdout": "fork failed after 59 Resource temporarily unavailable\n",
  "stderr": "",
  "timed_out": false,
  "lingering_descendants_killed": true,
  "seconds": 0.548,
  "pids_events": {
   "max": "1"
  }
 },
 "cpu_max": {
  "returncode": 0,
  "stdout": "",
  "stderr": "",
  "timed_out": false,
  "lingering_descendants_killed": false,
  "seconds": 2.047,
  "cpu_seconds": 2.08,
  "wall_seconds": 2.06,
  "nr_throttled": "21"
 },
 "descendants": {
  "returncode": 0,
  "stdout": "started\n",
  "stderr": "",
  "timed_out": false,
  "lingering_descendants_killed": true,
  "seconds": 0.526,
  "sleep_300_left": []
 },
 "wall_timeout": {
  "returncode": null,
  "stdout": "",
  "stderr": "",
  "timed_out": true,
  "lingering_descendants_killed": false,
  "seconds": 1.012
 },
 "teardown": {
  "memory_current_mib_live": 4.5,
  "memory_current_mib_after_holder_stop": 3.5,
  "slot_populated_after_stop": false
 },
 "workspace_over_memory": {
  "returncode": 0,
  "stdout": "",
  "stderr": "Killed\n",
  "timed_out": false,
  "lingering_descendants_killed": false,
  "seconds": 0.031,
  "oom_kill_delta": 1,
  "holder_alive": true
 }
}
```

```json
{
 "image": "docker.io/library/python@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe",
 "codex": {
  "returncode": 1,
  "stdout": "",
  "stderr": "WARNING: proceeding, even though we could not create PATH aliases: Refusing to create helper binaries under temporary dir \"/tmp\" (codex_home: AbsolutePathBuf(\"/tmp/codex-home\"))\nReading additional input from stdin...\nOpenAI Codex v0.162.1\n--------\nworkdir: /workspace\nmodel: gpt-5\nprovider: gw\napproval: never\nsandbox: danger-full-access\nreasoning effort: none\nreasoning summaries: none\nsession id: 01a13c72-1bb6-7b62-aaa5-6daafccae640\n--------\nuser\nreply with OK\nwarning: Model metadata for `gpt-5` not found. Defaulting to fallback metadata; this can degrade performance and cause issues.\nERROR: unexpected status 502 Bad Gateway: upstream_blocked: no API-key account, url: http://127.0.0.1:8080/v1/responses\nERROR: unexpected status 502 Bad Gateway: upstream_blocked: no API-key account, url: http://127.0.0.1:8080/v1/responses\n",
  "timed_out": false,
  "lingering_descendants_killed": true,
  "seconds": 0.922,
  "gateway_rows": [
   {
    "route": [
     "POST",
     "/v1/responses"
    ],
    "token_ok": true,
    "user_agent": "codex_exec/0.162.1 (Debian 13.0.0; x86_64) unknown (codex_ex",
    "body_bytes": 39249,
    "model": "gpt-5",
    "status": 502
   }
  ]
 },
 "claude": {
  "returncode": null,
  "stdout": "",
  "stderr": "",
  "timed_out": true,
  "lingering_descendants_killed": false,
  "seconds": 60.023,
  "gateway_rows": [
   {
    "route": [
     "POST",
     "/v1/messages"
    ],
    "token_ok": true,
    "user_agent": "claude-cli/2.1.300 (external, sdk-cli)",
    "body_bytes": 112603,
    "model": "claude-sonnet-4-5",
    "status": 502
   },
   {
    "route": [
     "POST",
     "/v1/messages"
    ],
    "token_ok": true,
    "user_agent": "claude-cli/2.1.300 (external, sdk-cli)",
    "body_bytes": 112603,
    "model": "claude-sonnet-4-5",
    "status": 502
   },
   {
    "route": [
     "POST",
     "/v1/messages"
    ],
    "token_ok": true,
    "user_agent": "claude-cli/2.1.300 (external, sdk-cli)",
    "body_bytes": 112603,
    "model": "claude-sonnet-4-5",
    "status": 502
   },
   {
    "route": [
     "POST",
     "/v1/messages"
    ],
    "token_ok": true,
    "user_agent": "claude-cli/2.1.300 (external, sdk-cli)",
    "body_bytes": 112603,
    "model": "claude-sonnet-4-5",
    "status": 502
   },
   {
    "route": [
     "POST",
     "/v1/messages"
    ],
    "token_ok": true,
    "user_agent": "claude-cli/2.1.300 (external, sdk-cli)",
    "body_bytes": 112603,
    "model": "claude-sonnet-4-5",
    "status": 502
   },
   {
    "route": [
     "POST",
     "/v1/messages"
    ],
    "token_ok": true,
    "user_agent": "claude-cli/2.1.300 (external, sdk-cli)",
    "body_bytes": 112603,
    "model": "claude-sonnet-4-5",
    "status": 502
   },
   {
    "route": [
     "POST",
     "/v1/messages"
    ],
    "token_ok": true,
    "user_agent": "claude-cli/2.1.300 (external, sdk-cli)",
    "body_bytes": 112603,
    "model": "claude-sonnet-4-5",
    "status": 502
   }
  ]
 },
 "policy_probe": {
  "returncode": 0,
  "stdout": "{\"admin_route\": 403, \"models_list\": 403, \"wrong_token\": 401, \"model_route\": 502, \"direct\": \"gaierror:-3\", \"credential_files\": [], \"env_names\": [\"HOME\", \"LC_CTYPE\", \"PATH\", \"PWD\", \"RUNREF_GATEWAY_TOKEN\"]}\n",
  "stderr": "",
  "timed_out": false,
  "lingering_descendants_killed": true,
  "seconds": 1.013,
  "gateway_rows": [
   {
    "route": [
     "GET",
     "/admin/keys"
    ],
    "token_ok": true,
    "user_agent": "Python-urllib/3.12",
    "body_bytes": 0,
    "status": 403
   },
   {
    "route": [
     "GET",
     "/v1/models"
    ],
    "token_ok": true,
    "user_agent": "Python-urllib/3.12",
    "body_bytes": 0,
    "status": 403
   },
   {
    "route": [
     "POST",
     "/v1/responses"
    ],
    "token_ok": false,
    "user_agent": "Python-urllib/3.12",
    "body_bytes": 2,
    "status": 401
   },
   {
    "route": [
     "POST",
     "/v1/responses"
    ],
    "token_ok": true,
    "user_agent": "Python-urllib/3.12",
    "body_bytes": 2,
    "model": null,
    "status": 502
   }
  ]
 }
}
```

## Task 5a: F3b-channel holder topology and channel confinement (2026-10-14)

Gate: F3b-channel in the design's evidence table (D-a, D-b, D-g, R4, R5, R6, R7, R10, N8). It is checked with a throwaway holder, `tests/e2e/run_ref_holder.py`, a test-local helper rebuilt from `fdfa8b0d`'s `profile.py` in the D-a shape. No holder code is in `orchestrator/`. **Verdict: PASS.** There are two design-text deltas below (pid 1's bwrap eventfd; how the `setsid` daemon case should be read). Neither changes the topology, so the Podman fallback is not needed.

### Harness shape

- **Scope per launch (D-a).** `systemd-run --user --scope --quiet --unit run-ref-<token[:16]>.scope -p MemoryMax=<bytes> -p MemorySwapMax=0 -p TasksMax=<n> -p CPUQuota=100% -p OOMPolicy=continue -p Delegate=yes -- python3 -I -c <launcher> <token> <launch fd> <kept fds> bwrap ...`. The token is 128 random bits.
- **Launcher.** It writes its own pid on a launch socketpair and blocks for one line. EOF exits 97 and any line other than the exact token exits 98, so `bwrap` never starts in either case. After the token it points fds 0-2 at `/dev/null`, keeps only the control socket (3), the gate socket (4), the `--info-fd` pipe (5) and the sealed rootfs directory (6, `--ro-bind-fd 6 /`), closes everything else and execs `bwrap`.
- **Host steps before release.** The host checks the reported pid against the spawned pid and resolves the scope from `/proc/<pid>/cgroup`, requiring the leaf name to equal the unit. It then reads back `systemctl --user show -p MemoryMax,MemorySwapMax,TasksMax,CPUQuotaPerSecUSec,OOMPolicy,Delegate,ControlGroup` and the scope's `memory.max`, `memory.swap.max`, `pids.max` and `cpu.max`; any mismatch refuses before release. Next it creates `<scope>/holder`, moves the launcher into it, checks that the scope root's `cgroup.procs` is empty and that `holder` holds only the launcher, enables `+memory +pids` for the slots and sends the token. The harness never writes a limit itself.
- **Holder argv.** `bwrap --unshare-user --unshare-ipc --unshare-pid --unshare-net --unshare-uts --unshare-cgroup --disable-userns --die-with-parent --new-session --cap-drop ALL --clearenv --setenv PATH /usr/local/bin:/usr/bin:/bin --setenv HOME /tmp --ro-bind-fd 6 / --dev /dev --size 8388608 --tmpfs /dev/shm --remount-ro /dev --proc /proc --size 33554432 --tmpfs /workspace --size 16777216 --tmpfs /tmp --size 16777216 --tmpfs /result --tmpfs /run --ro-bind <host leaf dir> /run/runref --remount-ro /run --info-fd 5 -- /bin/sh -c <spawner>`. The test sizes are smaller than the design's 256/64/128 MiB constants.
- **Spawner.** It runs as image `/bin/sh` and reports `ready`. For each request line it runs `( exec 3>&-; read go <&4; exec 4<&-; cd /workspace; exec setsid /bin/sh /run/runref/<leaf>/leaf.sh <stdin >/result/<leaf>/stdout 2>/result/<leaf>/stderr ) &`, then `echo "ack $!"`, `wait $!` and `echo "status $?"`.
- **Per-leaf host protocol.** These steps match the design's host protocol:
  1. Require quiescence: the holder slot equals the set recorded at `ready` and every leaf slot is empty.
  2. Empty `/tmp`, `/dev/shm` and `/result` through root descriptors that were opened once from `/proc/<holder>/root/...` after `ready`. Then `mkdir` `/result/<leaf>` exclusively.
  3. Write `leaf.sh`, create `<scope>/leaf-<name>` and send the request.
  4. Require the `ack` within 2 s and wait for exactly one member beyond the holder set; two or more refuse with `escape_rejected`. Move that member into the leaf slot, check membership, then send `go` on the gate.
  5. Wait for the status line, an empty leaf slot or the wall deadline. A missing status 2 s after the leaf slot empties, or EOF on the control socket, is holder death: `cgroup.kill` the whole scope. A leaf slot still populated after its status line counts as `lingering`.
  6. `cgroup.kill` the leaf slot and wait for it to empty, then check quiescence again before any read.
  7. Read `/result/<leaf>/stdout` and `stderr` beneath the retained root descriptor, opened `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` with an `fstat` `S_ISREG` check and a bounded read (1 MiB). A missing, symlinked or non-regular entry refuses with `escape_rejected` and kills the scope.
- **Teardown.** `stop()` is idempotent and runs in the fixture's teardown, so it also runs when a test fails. The teardown stops every holder even if one `stop()` raises, and then asserts that no scope is still populated. It kills the scope through `cgroup.kill` and reaps the launcher; systemd then garbage-collects the empty scope. It calls `systemctl --user reset-failed` for units that systemd stopped itself. After every run in this section, `systemctl --user list-units 'run-ref-*' --all` was empty.

### Commands

- `ORCHESTRATE_E2E=1 PYTHONPATH=<worktree> pytest -q tests/e2e/test_e2e_run_ref_confined.py` -> `11 passed in 7.82s` (5 Task 1 tests and 6 new ones; fix round 1 added the FIFO result witness).
- Without `ORCHESTRATE_E2E`: `11 skipped in 0.06s`. With `XDG_RUNTIME_DIR=/nonexistent DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent`: all skipped, reason `user systemd manager unreachable` (`systemctl --user show -p Version` fails). The Task 1 tests share this skip.
- A missing image record skips the holder tests. With `RUN_REF_REQUIRE_IMAGE=1` it fails them instead (`Failed: Task 1 image record ... absent`).
- `pytest --collect-only -q tests/e2e/test_e2e_run_ref_confined.py` -> `11 tests collected`.

### Witnesses

| Witness | Test | Status | Observable (verbatim from the evidence run) |
| --- | --- | --- | --- |
| D-a scope shape, read-back, launcher in `holder`, scope root empty | `test_holder_channels_descriptors_and_scope_shape` | **PASS** | Unit: `{"OOMPolicy": "continue", "Delegate": "yes", "CPUQuotaPerSecUSec": "1s", "MemoryMax": "268435456", "MemorySwapMax": "0", "TasksMax": "64", "ControlGroup": ".../app.slice/run-ref-78d41f18a835592b.scope"}`. Cgroup files: `{"memory.max": "268435456", "memory.swap.max": "0", "pids.max": "64", "cpu.max": "100000 100000"}`. Scope root procs `[]`. Holder set `[launcher 1741417, 1741421, 1741422]`, unchanged after four leaves. |
| Exact release token | `test_launcher_without_the_exact_release_token_never_starts_bwrap` | **PASS** | EOF: `{"child_pid": null, "launcher_exit": 97, "scope_populated": false}`. Wrong line: `{"child_pid": null, "launcher_exit": 98, "scope_populated": false}`. `--info-fd` reached EOF without `child-pid`, so `bwrap` never ran. |
| Memory enforced by `MemoryMax` | `test_unit_property_limits_are_enforced_and_oom_keeps_the_scope` | **PASS** | 128 MiB scope, leaf allocates 512 MiB: status `137`, `memory.events` `oom 1, oom_kill 1`, `memory.peak` `134217728`. |
| `OOMPolicy=continue` keeps the scope | same | **PASS** | After the OOM kill: `is-active` `active`, holder quiescent, later leaves run. The manager's `DefaultOOMPolicy=stop`, so the property is required (mutation M8). |
| Pids enforced by `TasksMax` | same | **PASS** | `TasksMax=32`: `28 Resource temporarily unavailable`, `pids.events max 1`. |
| CPU enforced by `CPUQuota` | same | **PASS** | 100%, four busy loops for 2 s: `cpu_seconds 2.087` in `2.073` s wall, `nr_throttled +20`. |
| Sockets unreachable from a leaf | channels test | **PASS** | Spawner fds `{"3": "socket:[188313993]", "4": "socket:[188313995]"}`, equal to the inodes of the host-created guest ends. From the leaf, both give `open` `ENXIO` and `pidfd_getfd` `EPERM`. Probe check: `pidfd_getfd` on the leaf's own child returned `obtained`. |
| FIFO and pipe positive controls | `test_fifo_and_pipe_placed_like_the_channels_reopen_from_a_leaf` | **PASS** | The same launcher also passes a pipe read end and an `O_RDWR` FIFO to the spawner (fds 7, 8). From the leaf: `{"pipe": "opened", "fifo": "opened", "socket": "ENXIO"}`; `pidfd_getfd` stays `EPERM` for all. |
| In-namespace descriptors (pid 1, spawner) | channels test | **PASS, design-text delta** | The leaf enumerates `/proc/[0-9]*`: the only processes it can see are `[1, spawner, itself]`, and the test asserts this. pid 1: `{"0": "/dev/null", "1": "/dev/null", "2": "/dev/null", "8": "anon_inode:[eventfd]"}`. Spawner: `/dev/null` x3 and the two sockets. `--info-fd` (5) and `--ro-bind-fd` (6) are not inherited by the spawner. The extra entry is bwrap's own pid-1 `event_fd` (it reports the child's exit to the monitor). From a leaf it gives `open` `EACCES` and `pidfd_getfd` `EPERM`, so it is unreachable. The test pins the set to exactly `{"anon_inode:[eventfd]"}` beyond `/dev/null` and the channels, and requires every entry to be unreachable. The N8 sentence "pid 1 holds only `/dev/null`, the sockets and guest objects" should name this eventfd. |
| `setsid` leaf: `kill 0` spares the spawner; leaf pid = ack (P4) | channels test | **PASS** | Probe leaf: `ack 3`, `leaf_nspid 3`, `pid 3`, `sid 3`, `pgid 3`, spawner pgid `1`. `kill 0` leaf: `ack 5`, stdout `5`, status `143` (killed its own group). The next leaf was acknowledged and the holder set was unchanged. |
| Stopped spawner -> failed attempt, empty scope | `test_stopped_or_signalled_spawner_and_setsid_daemon_fail_the_attempt_with_an_empty_scope` | **PASS** | `kill -STOP $PPID`: `holder_death`, `no status line within the deadline` after 2.06 s; scope killed, `scope_populated false`. |
| Signalled spawner | same | **PASS** | `kill -KILL $PPID`: `holder_death`, `control socket EOF` after 0.014 s; `bwrap` exited 137; scope empty. |
| `setsid` daemon | same | **PASS (interpretation recorded)** | `setsid sleep 300 &`: status `0`, then outcome `lingering` (failed attempt: the leaf slot was still populated after its status line). It was killed in the leaf slot: no process whose cmdline is exactly `sleep\0300\0` remains anywhere in the scope, and the holder set is unchanged and quiescent. The scope empties at stop, which the fixture teardown asserts. The daemon is a failed attempt and not a holder death. |
| Non-regular result entry refused without blocking (fix round 1) | `test_host_refuses_a_fifo_result_file_promptly_as_escape_rejected` | **PASS** | The leaf runs `rm /result/fifo/stdout && mkfifo /result/fifo/stdout`. Host: `escape_rejected`, `result read refused: /result/fifo/stdout is not a regular file`, 0.065 s, scope empty. A 10 s `SIGALRM` guard raises `HostReadBlocked`, a `BaseException` and not an `OSError`, so a blocking open crashes the test instead of hanging or being classed as a guest refusal. |
| `/dev`, `/run` read-only; `/dev/shm` sized | channels test (scratch leaves) | **PASS** | `{"/dev/x": "EROFS", "/run/x": "EROFS", "/run/runref/x": "EROFS"}`; `/dev/shm` fill stopped at `8388608` bytes with `ENOSPC`. |
| Earlier leaf's `/result` entry gone | same | **PASS** | `scratch-a` wrote `/result/scratch-b/forged`, `/result/scratch-a/extra`, `/tmp/left` and `/dev/shm/left`. `scratch-b` then saw `{"/result": ["scratch-b"], "/result/scratch-b": ["stderr", "stdout"], "/tmp": [], "/dev/shm": []}`. |
| Host creates files in `/workspace` through `/proc/<holder>/root` | same | **PASS** | `openat(<workspace root fd>, "from-host", O_CREAT|O_EXCL|O_NOFOLLOW)`; the next leaf read `written through /proc/<holder>/root`. |
| Holder-slot membership equals the recorded set outside request windows | all holder tests | **PASS** | Checked before and after every leaf; any change refuses with `escape_rejected`. |

### Mutation RED (one control removed per run, files restored afterwards)

| Mutation | Test | Result |
| --- | --- | --- |
| M1 no `setsid` (`exec /bin/sh leaf.sh`) | channels | RED: the `kill 0` leaf killed the spawner (`holder_death`, `control socket EOF`) |
| M2 forking `setsid -f` | channels | RED: `wait` returned at once (`status 0`); the real leaf was `lingering` with empty stdout |
| M3 launcher keeps inherited stdio | channels | RED: pid 1 and spawner held `pipe:[188250582]` (systemd-run's stderr), `open` `opened` from the leaf |
| M4 no `--remount-ro /dev` | channels | RED: `/dev/x` created (the second scratch leaf saw `EEXIST`) |
| M4b no `--remount-ro /run` | channels | RED: `/run/x` created |
| M5 `/dev/shm` without `--size` | channels | RED: the fill leaf was OOM-killed (`137`) instead of getting `ENOSPC` |
| M6 no scratch wipe | channels | RED: `FileExistsError: 'scratch-b'` (exclusive create of the pre-created result directory) |
| M7 launcher continues on EOF | release | RED in part: EOF fell through to the compare and exited `98`, not `97`; the token compare alone still refuses |
| M7b launcher accepts any line | release | RED: wrong line started `bwrap` (`child-pid 1737322`, scope populated) |
| M8 `OOMPolicy=stop` | limits | RED: systemd stopped the scope on the OOM kill (scope directory gone) |
| M9 `CPUQuota=400%` | limits | RED: `8.006` CPU-s in `2.076` s wall |
| M10 `TasksMax=1000` | limits | RED: 100 forks succeeded (no fork failure line) |
| M11 `MemoryMax=1024M` | limits | RED: the 512 MiB allocation completed (status 0) |
| M12 missing status treated as exit | spawner | RED: the stopped spawner became `exited`, scope still populated |
| M13 blocking host read (no `O_NONBLOCK`, no `S_ISREG`) | FIFO result | RED (test error): the host open blocked until the 10 s alarm, which raised `HostReadBlocked: host result read blocked` |
| M13b `O_NONBLOCK` without `S_ISREG` | FIFO result | RED: the FIFO read returned empty bytes and the leaf counted as `exited` |
| M14 pinned tree digest differs | any holder test | RED: `sealed rootfs does not match the pinned tree digest` |
| M15 lingering daemon left alive (leaf-slot kills and the post-leaf quiescence check removed) | spawner | RED: `daemon_left_in_scope ['1852146']`, `daemon_holder_quiescent False` (the exact matcher finds the live `sleep 300`) |

"FIFO instead of socketpair" is not a cheap mutation of the protocol. The FIFO/pipe positive-control test is the evidence that a FIFO or pipe channel would be reopenable.

### Durations

Each figure is the median of 5 launches: launch to `ready` (systemd-run round trip, read-back, move, release) 59 ms (max 73); leaf round trip 53 ms; stop 38 ms. Rootfs rehash 0.27 s per module. Full module 7.0-7.4 s; the slowest tests are the limits test (2.5 s: CPU loop) and the spawner-death test (2.4 s: the 2 s status deadline). All runs were foreground with `timeout`.

### Image on a fresh host

The tests use the Task 1 sealed rootfs through its record `~/.cache/run-ref-spike-images/records/sha256-2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe.json`. They rehash the tree against the constant `TREE_DIGEST` pinned in `tests/e2e/run_ref_holder.py` (`sha256:973cd373...`), not against the record, so a cache whose record and rootfs were both tampered with still fails. Without the record the tests skip and name the path; with `RUN_REF_REQUIRE_IMAGE=1` they fail instead. To obtain it:

```bash
d=$(mktemp -d) && git show fdfa8b0d:experiments/run_ref_confinement_spike/image_import.py > "$d/image_import.py"
python3 -I "$d/image_import.py" ~/.cache/run-ref-spike-images library/python sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe
```

This is an anonymous Docker Hub pull, with each blob verified and the store sealed read-only (125 MiB). Re-run on 2026-10-14 into a scratch store, it took 5.0 s and printed the recorded `tree_digest` `sha256:973cd37339e7ef7627c497292983fa6b110ef784f121f41d8a52edc6385fadae`. To remove it: `chmod -R u+w ~/.cache/run-ref-spike-images && rm -rf ~/.cache/run-ref-spike-images`. The cache is the only state left outside pytest tmp directories.

### Findings for Tasks 5b and 6

- bwrap 0.9.0 closes `--info-fd` and `--ro-bind-fd` descriptors before the command, so the D-a launcher can pass the rootfs by descriptor without leaking it to the spawner.
- With `--new-session`, the spawner is in process group 1 (pid 1's group). Without `setsid` a leaf's `kill 0` reaches the spawner (M1), so `setsid` is a required image pin, as R5 says.
- A guest can make the host's exclusive `mkdir /result/<leaf>` fail by pre-creating the directory; the wipe is what prevents this (M6). The runtime should treat a failed exclusive create as `escape_rejected`, not as a host error.
- `/dev` is not wiped between leaves, but it is read-only, so a leaf cannot leave state there.
- The result broker must open guest result entries with `O_NONBLOCK|O_NOFOLLOW`, check `S_ISREG` with `fstat` and bound the read. A plain `O_RDONLY` open of a guest FIFO blocks the host forever (M13).

## Task 5b: F3b-keyring witness and F3b gate re-record (2026-10-14)

Design row F3b-2 was added after the Task 5a gate ran (commit `6841bea7`). The throwaway holder in `tests/e2e/run_ref_holder.py` now has the F3b-2 launcher and argv, and the whole module was rerun with it. Fix round 1 (ruling P24) split the e2e tests by gate, so each module stays under 500 lines:

- `tests/e2e/test_e2e_run_ref_confined.py`: Task 1 F3 and F3b-channel.
- `tests/e2e/test_e2e_run_ref_keyring.py`: F3b-keyring.
- `tests/e2e/run_ref_fixtures.py`: the shared fixtures `sealed_rootfs` and `launch`, the user-manager skip, and the image pin.

| Gate | Run | Status | Evidence |
| --- | --- | --- | --- |
| F3b-channel (Task 5a) | launcher without keyring join, filter or `/proc/keys` masks | **PASS** (record of what that run measured; unchanged) | section "Task 5a" above |
| F3b-channel + F3b-keyring (Task 5b) | F3b-2 launcher and argv; channel witnesses rerun | **PASS**: the keyring witnesses pass and every channel witness passes again | both modules `13 passed in 12.48s` (fix round 1); table below |

### Changes to the holder

- **Launcher failure.** If the launcher fails after release (for example, the keyring join raises), `launch()` raises with the launcher's exit code and stderr, e.g. `launcher exited 1 before bwrap: ... PermissionError: [Errno 1] fresh session keyring unavailable`. Before fix round 1 it returned as if the release had been refused.
- **Launcher.** After the release token, the launcher loads `orchestrator/providers/provider_launch_shim.py` by file path (it runs under `python3 -I`) and calls `_join_fresh_session_keyring()`. Only then does it exec `bwrap`. It keeps three more descriptors, all of which `bwrap` consumes: fd 7 and fd 8 are empty memfds for the masks, fd 9 is the filter program.
- **bwrap argv additions** (after `--proc /proc`): `--perms 0000 --ro-bind-data 7 /proc/keys --perms 0000 --ro-bind-data 8 /proc/key-users --seccomp 9`.
- **Ruling P19 deviation.** P19 says `--ro-bind-data <fd>` followed by `--chmod 0000`, but bwrap 0.9.0 refuses that with `bwrap: Can't chmod 0 /proc/keys: Read-only file system`. The `--perms 0000` modifier before `--ro-bind-data` does what P19 intends: `---------- 0 1000 1000 0 /proc/keys`, and a read gives `Permission denied`. There is still no host-path bind source. Cost: one argv change in Task 6.
- **Filter bytes.** `_install_key_syscall_filter` (shim :913) builds its instruction list inline and installs it, so the bytes cannot be taken from it without modifying the shim; the builder is Task 6. `run_ref_holder.key_syscall_filter()` rebuilds the same list from the shim's own constants and `_SockFilter`. `test_harness_key_filter_has_the_shim_filter_semantics` then runs one probe in three fresh host interpreters: one after `shim._install_key_syscall_filter()`, one after `prctl(PR_SET_SECCOMP)` of the harness bytes, and one unfiltered. The shim and harness results must equal `EXPECTED_FILTER` and the unfiltered result must differ:
  - `add_key`, `request_key` and `keyctl`, native and x32 (`0x40000000|nr`): `EPERM`;
  - `getpid`: `ok`;
  - i386 `int 0x80` from an executable page: `SIGSYS` (foreign architecture killed).

### Witnesses (verbatim from the evidence run)

The test process first joins its own anonymous session keyring (`_join_fresh_session_keyring`) and adds a `user` canary key to it, so no host keyring is touched. Values were re-recorded in fix round 1 from a run in the fixture's order (join, canary, probes): test session `430183544`, canary `360029808`.

| Witness | Test | Status | Observable |
| --- | --- | --- | --- |
| Harness filter = shim filter semantics | `test_harness_key_filter_has_the_shim_filter_semantics` | **PASS** | Shim-installed and harness-installed both give `{"add_key:native": "EPERM", "add_key:x32": "EPERM", "request_key:native": "EPERM", "request_key:x32": "EPERM", "keyctl:native": "EPERM", "keyctl:x32": "EPERM", "getpid": "ok", "i386_int80": "SIGSYS"}`. Unfiltered (inheriting the test session keyring): `add_key`/`keyctl` native `ok`, `request_key` `ENOKEY`, x32 `ENOSYS` (no x32 ABI), i386 `exit 0`. |
| Leaf key syscalls refused, `/proc/keys` unreadable | `test_holder_keyring_is_fresh_and_key_syscalls_are_refused` | **PASS** | Leaf: the same eight `EPERM`/`ok`/`SIGSYS` values, plus `"/proc/keys": "EACCES", "/proc/key-users": "EACCES"`. |
| Key quota unchanged | same | **PASS** | The leaf loops `add_key` 50 times: `add_key_ok 0`, which is the main observable. The host's `/proc/key-users` `qnkeys` for uid 1000 was `12` before and `12` after. The test asserts only that the delta is below 50, because other same-uid processes may create keys during a parallel run. |
| Control launch, identical except for `--seccomp` (diagnostic, not the profile) | same | **PASS** | The leaf session keyring `638619947` is not `430183544`, and `KEYCTL_READ` of it returns `0` bytes (it is read before the probe's own `add_key`). Canary `KEYCTL_READ` `EACCES`, `KEYCTL_LINK` `EACCES`. Asserted: in the control, `add_key`/`keyctl` native are `ok`, so the filter is what refuses them in the profile. |
| Positive control: no join and no filter (diagnostic, kept permanently; was mutation K1) | same | **PASS** | The leaf session keyring `430183544` equals the test session, and the canary `KEYCTL_READ` returns `14` bytes (`canary-payload`), so the probe sees the canary whenever it is reachable. `KEYCTL_READ` of the session returns 8 bytes here: the canary plus the key the unfiltered host probe added to the inherited test session. |
| Channel witnesses rerun with the new launcher | `test_holder_channels_descriptors_and_scope_shape`, `test_fifo_and_pipe_placed_like_the_channels_reopen_from_a_leaf` and the rest of the module | **PASS** | The in-namespace descriptor set is unchanged (`/dev/null`, the two sockets, pid 1's eventfd), so `bwrap` consumed fds 7, 8 and 9. The FIFO and pipe controls still reopen and the sockets are `ENXIO`. |

### Mutation RED

| Mutation | Test | Result |
| --- | --- | --- |
| K1 launcher skips the keyring join | keyring | RED: control leaf session `547294256` == test session; `KEYCTL_READ` of it `4` bytes (the canary); canary `KEYCTL_READ` `14` bytes and `KEYCTL_LINK` `0`. Without the join, a leaf reads the controller's keys. |
| K2 profile without `--seccomp` | keyring | RED: `add_key:native ok`; quota `(50, 50)`, i.e. 50 keys charged to the host user |
| K3 `/proc/keys` unmasked | keyring | RED: `"/proc/keys": "read 639 bytes"` (the host user's key list) |
| K4 mask mode `0644` | keyring | RED: `"/proc/keys": "read 0 bytes"` (mode 0000 is what refuses the read) |
| K5 harness filter without x32 entries | filter semantics | RED: harness `add_key:x32 ENOSYS` instead of `EPERM` |
| K6 mask descriptor left unconsumed (`/proc/keys` mask argument removed) | channels | RED: spawner holds `/memfd:runref-holder (deleted)`, reopened (`opened`) from the leaf |

TDD note: the harness change and the tests were written together, so RED was observed by these mutations rather than by a first failing run.

### Commands and durations

- `ORCHESTRATE_E2E=1 PYTHONPATH=<worktree> pytest -q tests/e2e/test_e2e_run_ref_confined.py tests/e2e/test_e2e_run_ref_keyring.py` -> `13 passed in 12.48s` (fix round 1; before the split, `13 passed in 13.82s` from one module).
- Without `ORCHESTRATE_E2E`: `13 skipped`.
- `pytest --collect-only -q` over both modules -> `13 tests collected` (11 + 2).
- Afterwards, `systemctl --user list-units 'run-ref-*' --all` showed 0 units and no `run-ref-*` cgroup remained.
- Launch to `ready` is now a median of 138 ms (max 152), up from 59 ms. This is not attributed: the launcher now loads the shim by path, and the host was busy with parallel work (the rootfs rehash was also slower, 0.47 s against 0.27 s). The leaf round trip is 75 ms.
- The filter-semantics test takes 2.5 s (three fresh interpreters).
- The keyring test takes 1.0 s.

## Task 5ck: F3b-checkpoint on the throwaway holder (2026-10-14)

Gate: F3b-checkpoint, which is limited to the copier (N3). It uses the approved copier in `orchestrator/workflow/run_ref/checkpoint.py` (Task 5c, `9617b72e..53f27781`) between a clone on host disk and the holder's tmpfs `/workspace`. The tmpfs is reached through the root descriptor the harness opens from `/proc/<holder>/root/workspace` at ready. Tests: `tests/e2e/test_e2e_run_ref_checkpoint.py` (221 lines, ruling P24). It uses the shared fixtures and needed no harness or orchestrator change. **Verdict: PASS.** Holder death after a commit and wall charging are Task 6 witnesses; resume repair is Task 7.

The clone contains:
- `src/main.py` and `notes.txt`;
- `tool` with mode `0o4755` (setuid);
- the symlinks `entry -> src/main.py` and `host-link -> /etc/hostname`;
- `.git/config`.

The harness runs the copier in the pytest process; placing it in a `host` slot of the scope is Task 6.

| Witness | Test | Status | Observable (verbatim from the evidence run) |
| --- | --- | --- | --- |
| Seeding reproduces the clone in a fresh holder | `test_host_seeding_reproduces_the_clone_with_symlinks_preserved_and_setuid_masked` | **PASS** | `publish_initial_header` gives `committed`/`none`/0. `seed_workspace` (45 bytes, 0.001 s): the tmpfs manifest equals the clone manifest with modes masked to `0o777`, and the copy result's digest is the tmpfs manifest's. The clone keeps `0o4755`. Guest view: `{"entry": ["lrwxrwxrwx", "src/main.py"], "host-link": ["lrwxrwxrwx", "/etc/hostname"], "notes.txt": ["-rw-r--r--", null], "src": ["drwxr-xr-x", null], "src/main.py": ["-rw-r--r--", null], "tool": ["-rwxr-xr-x", null]}`, so symlinks stay strings, setuid is masked and `.git` is absent. |
| Checkpoint after a leaf: clone equals the tmpfs under `committed` | `test_checkpoint_after_a_leaf_makes_the_clone_equal_to_the_tmpfs_under_a_committed_header` | **PASS** | The leaf edits `src/main.py`, adds `new-leaf-1/deep/data.bin` and a relative symlink, removes `notes.txt`, creates a `0o4755` file, a hard link and a FIFO. `checkpoint_workspace` (1.33 s, including the global `os.sync()`) gives `{"state": "committed", "effect_identity": "effect-1", "ordinal": 1, "manifest_digest": "sha256:ab4e9e22...", "skipped_special": 1}`, where the digest equals the clone's fresh manifest. The masked clone and tmpfs manifests are equal. On the clone: the setuid file is `0o755`, `notes.txt` and the FIFO are absent, the hard link is flattened (`st_nlink` 1), `.git/config` is untouched. `preflight_checkpoint` accepts the header. |
| Crash mid-copy leaves `intent`; preflight repairs to `committed` | `test_a_checkpoint_killed_mid_copy_leaves_intent_that_preflight_repairs_by_refreezing` | **PASS** | A second leaf edits. A subprocess inheriting the tmpfs root descriptor runs `checkpoint_workspace` and SIGKILLs itself at the first file `fchmod` (temporary written, not renamed), as the 5c recovery tests do. Result: exit `-9`, header `{"state": "intent", "effect_identity": "effect-2", "ordinal": 2, "manifest_digest": null}`, one copier temporary (`.rr-<16 hex>.tmp`). The clone is partial: in the test's walk order `src/main.py` is still the base and `new-leaf-2/deep/data.bin` is missing. `preflight_checkpoint` (0.015 s) publishes `committed`/`effect-2`/2 with the re-frozen clone's digest and removes the temporary, and a second preflight accepts it. |

### Mutation RED

A scratch pytest plugin patched names in the test module at setup; no file was edited.

| Mutation | Result |
| --- | --- |
| C1 naive seeding (`shutil.copytree`, following symlinks) | RED: `tmpfs_equals_masked_clone False`; the guest sees `.git`, `.git/config`, and `entry`/`host-link` as regular files |
| C2 no checkpoint (the header is left as published) | RED: `FileNotFoundError: 'guest-setuid'` on the clone |
| C3 preflight without repair | RED: the clone's copier temporary makes `workspace_manifest` refuse (`run_ref_environment_escape_rejected: entry uses the copier's temporary name`) |
| C4 no injected kill | RED: exit `0`, header `committed`, no temporary, the clone carries the leaf-2 edits |

### Commands, durations, teardown

- `ORCHESTRATE_E2E=1 PYTHONPATH=<worktree> pytest -q` over the three holder modules (`test_e2e_run_ref_confined.py`, `test_e2e_run_ref_keyring.py`, `test_e2e_run_ref_checkpoint.py`): six consecutive runs, each `16 passed` (16.9 to 19.1 s).
- Without `ORCHESTRATE_E2E`: `16 skipped`. `--collect-only` -> `16 tests collected`. `pyright` 0 errors.
- Afterwards no `run-ref-*` units or cgroups remained.
- The intermittent teardown error did not recur in these six runs, or in five runs of the two older modules after fix round 3 (`18802b53`, ENOENT/ENODEV treated as vanished).

## Task 6: integrated confined command execution (2026-10-15)

Tested code: `c48d8fcc06e4177fc633a7f3155a8f71548eb876`, including the
integration corrections in `89f5c43b` and `d95e6857`. Independent conformance
review followed by code/security review: **PASS**, with no open findings.
This qualifies live command execution and completed-result reuse; controller
crash recovery (F5), exports/cleanup (F6) and live provider transport remain
separate acceptance requirements.

The public CLI fixture imports an OCI layout built from the Task 1 Debian
Python rootfs, whose pinned tree digest is
`sha256:973cd37339e7ef7627c497292983fa6b110ef784f121f41d8a52edc6385fadae`.
`tests/e2e/run_ref_image_fixture.py` records the construction and import path.
The command witness runs two leaves, checks their committed memo values and
checkpoint, and performs a completed public resume. The same suite covers
holder loss, budget exhaustion and provider refusal. Its per-test run roots
were temporary; their run IDs are not retained in this summary.

Commands ran from the feature worktree with `PYTHONPATH` pointing there:

| Check | Result |
| --- | --- |
| `ORCHESTRATE_E2E=1 pytest -q tests/e2e/test_e2e_run_ref_confined_child.py tests/e2e/test_e2e_run_ref_holder_runtime.py tests/e2e/test_e2e_run_ref_holder_failures.py` | **29 passed**, 39.16 s, exit 0 |
| `pytest -q tests/test_workflow_run_ref_quiescence.py` | **3 passed**, 2.17 s; the same regressions were first observed failing |
| `pytest --collect-only -q tests/test_workflow_run_ref_quiescence.py` | **3 collected** |
| `pytest -q -n 16 --dist=worksteal -m 'not e2e'` | **18 failed, 15856 passed, 6 skipped, 1 xfailed**, 1018.02 s, exit 1 |
| Isolated rerun of the two failures absent from the recorded base list | **1 passed, 1 xfailed**, 37.98 s, exit 0 |

The broad campaign is **not all green**. Sixteen failing node IDs also occur
in the preserved 85-failure baseline at `0c156966`: four nanoBragg harness
cases, ten use-site-scope cases, the Neovim diagnostic-progress case and the
evaluated growth-selector case. The other two are
`test_cancellation_escalates_after_a_failed_term_delivery` (process already
gone during fallback cleanup after a scheduling deadline; isolated PASS) and
`test_a_late_refusal_of_a_fresh_run_retries_with_the_fresh_run_id` (watchdog
timeout under load; isolated known F50 xfail). Their relevant source and tests
are unchanged from base. No related regression remained unresolved; no test
was weakened. Baseline failures absent from this campaign are not claimed
as fixes.

The corrections close the sessionless host-command route, charge admission
and ongoing host work to the budget, verify resolved inputs from retained
snapshots, and prevent clone repair or settlement after failed quiescence.
The final broad run used frozen sources. Local detailed evidence is retained
in the SDD `task-6c-broad-classification.md` and `task-6c-quiescence-review.md`,
and `/tmp/runref-t6c-quiescence-e2e.log`; this committed section preserves the
acceptance summary independently of those local logs.

## Task 7: durable command recovery accepted (2026-10-15)

Runtime `ade011fb8abaaccabe963eef52ea5ee5bd111a99` plus
`92b55aff25cf10b788b3c4a01282b5f22b315624`; final fixture-only correction
`57bbe06f666b2d04e6a5275a21ddd3beaff29323`. Independent conformance and
code/security review PASS, including the final fixture correction; the
coordinator inspected the diff, logs, retained identities and classifications.
Task 7 is accepted for its available command/recovery scope. Provider-commit
and post-export kill windows remain with Tasks 10/8/12; this is not full F5,
Increment A or release qualification.

The common ledger now supports v2 reservation, BOOTTIME visit accounting,
exact scope recovery and four durable FAILED boundaries while retaining v1
bytes and behavior. Durable terminals precede K4, committed effects are not
redispatched, and K4 carries remaining budget without inheriting release.
K8 preserves retry history when invalidation retires a pending projection.
Impossible checkpoint identity refuses before repair or K4; a coherent
checkpoint's manifest drift remains an environment-change refusal.

All commands ran from the feature root with its explicit `PYTHONPATH`:

| Check | Result |
| --- | --- |
| Affected lifecycle, recovery, memo, parallel and legacy owner modules, `pytest -q -n 16 --dist=worksteal` | 454 passed, 43.31 s, exit 0; frozen bytes subsequently committed in `ade011fb` |
| Final P30/terminal focal selector, `pytest -q tests/test_workflow_run_ref_confined_recovery.py -k 'zero_commit_k4 or retained_checkpoint or pure_completed or failed_repair'` | 8 passed, 72 deselected, 7.13 s, exit 0, on `92b55aff` |
| Collection of changed recovery/integration/e2e recovery modules | 120 collected, exit 0 |
| `ORCHESTRATE_E2E=1 RUN_REF_REQUIRE_IMAGE=1 pytest -q tests/e2e/test_e2e_run_ref_confined_recovery.py tests/e2e/test_e2e_run_ref_confined_child.py --basetemp=/tmp/run-ref-task7-real-final-92b55aff` | 16 passed, 106.41 s, exit 0, on `92b55aff` |
| `pytest -q -n 16 --dist=worksteal -m 'not e2e'` | **20 failed, 15897 passed, 6 skipped, 1 xfailed**, 950.16 s, exit 1, frozen runtime `92b55aff` |
| Focused unchanged timing cases and baseline watcher parity | 3 passed, 1 xfailed, 94.80 s, exit 0 |
| Caller fixture correction: three supersession variants; complete caller/ledger modules with `-n 16 --dist=worksteal` | 3 passed, 4.10 s; 62 passed, 8.35 s; both exit 0 |
| Independent retained-FAILED corruption probe | 5 passed, 12.46 s: prefix, boundary, accounting, closure and memo-suffix corruption refuse without repair or dispatch |

The broad campaign remains **RED**. Sixteen exact failures recur from the
preserved `0c156966` baseline: four nanoBragg harness cases, ten use-site-scope
cases, growth selectors, and watcher/report parity. Three other failures are
unrelated timing cases: prebind cancellation exceeded its two-second fixture
window; the late-refusal watcher timed out before its third call (isolated
known F50 xfail); running discovery exceeded its 40-second switching window.
Their provider/watchdog source and tests are unchanged from base. The three
cases plus baseline watcher parity were rerun unchanged with the result above.
Absent baseline failures are not claimed fixed.

The remaining failure exposed invalid test setup:
`test_direct_child_refuses_superseded_live_permission[new_ordinal]` reused a
discarded attempt's workspace for the new ordinal. Workspace uniqueness already
existed in the ledger reader; Task 7 validates it before append. The test-only
correction uses the canonical ordinal-2 workspace, preserving the original
request-invalid, no-compilation and no-write assertions. Its fresh RED was
observed before correction. No production behavior or test timeout was weakened,
and no related failure remains unresolved. Broad and real suites were not
repeated for this fixture-only correction; both complete affected owners passed.

The final real campaign used image
`example.invalid/run-ref-holder-fixture@sha256:9cd7c527bd9141fd944a4876d2facd11c8a541211d2cfb08698f93e924d8fba8`,
sealed tree `sha256:973cd37339e7ef7627c497292983fa6b110ef784f121f41d8a52edc6385fadae`,
from the retained e2e fixture/import path. Twelve external controller-SIGKILL
windows retain child IDs, clone identity, dispatch/holder counters and logs in
local `t7-e2e-92b55aff-evidence/` under this plan's SDD; the parent IDs are retained
here independently of temporary pytest directories:

| Window | Parent run ID |
| --- | --- |
| after_release | `20261015T101704Z-laqagk` |
| before_release | `20261015T101658Z-tqr9p3` |
| before_settlement | `20261015T101812Z-2dlsdy` |
| checkpoint_commit_gap | `20261015T101722Z-9tpmt4` |
| checkpoint_intent | `20261015T101716Z-upgno2` |
| child_terminal | `20261015T101736Z-5fhtz9` |
| failed_row | `20261015T101741Z-60uzef` |
| failed_terminal | `20261015T101750Z-hjvfuv` |
| first_commit | `20261015T101710Z-g6bsme` |
| parent_commit | `20261015T101806Z-uec87p` |
| pending | `20261015T101800Z-4418x5` |
| rerun_before_checkpoint | `20261015T101728Z-goieom` |

Detailed local artifacts are `task-7-report.md`, `task-7-code-review.md`,
`task-7-broad-classification.md`, `t7-final-campaign.sh`, `t7-final.head`,
`t7-e2e-final.{log,exit}`, `t7-broad-final.{log,exit}` and
`t7-classify.{log,exit}`. This committed section preserves their acceptance
summary. Clock/boot tests are injected controls, not physical host suspend,
reboot or power-loss experiments. No autonomous watchdog is selected; an open
interval charges downtime/suspension and refuses across boots.

## Task 8: exports, retained proof and cleanup accepted (2026-10-15)

Implementation `e85fcbf950539bf1d8ea5dc1f8eeaf3c0a851744` has independent
conformance and subsequent code/security PASS. The coordinator inspected the
diff and fresh outputs and verified all 18 runtime and 10 test hashes after
commit. The frozen runtime manifest is
`948342c2e667af8619f91b7a99d4e2df8201e10ea1b590a8b601c8bed8dbbfe6`;
the test manifest is
`42c95389cc18788dc46381b2803ccb4b059c696522acd784f8934d8d83908390`.

Typed nested paths now export through bounded copies and durable staged-object
identity before no-overwrite publication. Terminal proof retains canonical
trees, image inventory, inputs and results without requiring a disposable clone,
materialized baseline or live image store. Cleanup follows durable parent
settlement, preserves foreign replacements and exposes retryable obligations
without changing the completed workflow result. A completed resume returns 2
while cleanup remains pending and 0 after successful cleanup; report is read-only.

| Final check | Result |
| --- | --- |
| Collection of selected changed modules | 296 collected, exit 0 |
| Nineteen affected modules, `pytest -q -n 16 --dist=worksteal` | 634 passed, 71.95 s, exit 0 |
| Real child/recovery/export modules, serial `ORCHESTRATE_E2E=1 RUN_REF_REQUIRE_IMAGE=1` | 18 passed, 118.92 s, exit 0 |

Review reproduced and closed inconsistent delta capture and checkpoint
recreation during cleanup. Retained delta validation checks its catalog and
structural consistency; exact diff text is validated against live files before
capture and bound thereafter, not regenerated from deleted file bytes. Export
root selection now checks path ancestors rather than every pair; deterministic
1024/2048-path tests preserve overlap and ordering behavior.

The final F6 runs are `20261015T113509Z-vvykr7` (retained proof) and
`20261015T113517Z-qi4yjp` (cleanup pending/retry). They use image
`example.invalid/run-ref-holder-fixture@sha256:3c331d46f0667e83b9e7cf6198835c4d5814c26d83a5455cc94facdbcc9690bf`
and tree `sha256:7fcf53d85fd9edcd41863c396e045b04a461a0d1de26f9a71102340466154070`,
including the 294 MB native executable and its absolute/subtree closure. The
663934-byte image inventory supports replay after baseline/image withdrawal.
The parent consumes the exported path after clone/checkpoint removal.

Local `.tmp/task8/` retains exact commands, logs, exits, per-file pins and the
explicit `real-final-runs` basetemp; `real-final-evidence/authority-index.json`
binds 17 unique parent roots and 19 child recipes. The SDD `task-8-report.md`
and `task-8-code-review.md` retain the detailed evidence and review. Earlier
temporary F6 paths were rotated by pytest; these final runs replace that lost
temporary evidence. Integrated exception tests cover export preparation/rename
recovery without redispatch. External public SIGKILL at those export windows and
before parent settlement remains Task 12 work. No provider admission, global
suite PASS or Increment A acceptance is claimed by this Task 8 result.

## Task 9: Increment A accepted for commands (2026-10-15)

Test commit `0771999243b0ae279252a59b1e989a1ad7e8cd69` has independent
conformance and subsequent quality/security PASS. Runtime remains Task 8
`e85fcbf9`, manifest `948342c2e667af8619f91b7a99d4e2df8201e10ea1b590a8b601c8bed8dbbfe6`.
The coordinator inspected the diff, logs and retained run and checked all three
test-file hashes against both evidence and commit.

The public `python -m orchestrator` compile/run/resume/report recipe uses
absolute inputs and manifests. Run `20261015T114931Z-vqdha4` was externally
SIGKILLed after its first durable child command commit. Resume retained child
`run-ref-2e77c09bb1b6847120a986997e4df141c8e4f413`, attempt ordinal 1, and
executed only the second command. The parent consumed the typed export after
clone/checkpoint cleanup. Two completed resumes and a repeated report preserve
authority, value and export without dispatch, allocation or writes. The
unsupported provider case refuses before run-state creation or Holder launch.

The real module passed **13 tests in 24.96 s**, exit 0, serial in tmux with
`ORCHESTRATE_E2E=1 RUN_REF_REQUIRE_IMAGE=1`; the unit owner passed **66 tests in
7.91 s**, exit 0; collection found **82 tests**. A prior fixture filename error
failed compilation and was corrected without changing runtime. Local
`.tmp/task9/evidence-2/` and `retained-runs-2/` retain argv, logs, IDs, artifacts,
image and binary pins; SDD reports are `task-9-report.md` and
`task-9-code-review.md`. Source OCI is Python `2b4f19dae3a7…`; the run admits
the derived fixture reference `9cd7c527bd91…`, tree `973cd37339e7…`, whose full
pins are recorded in the Task 7 section and the retained evidence.

Increment A is the first shippable increment for commands with `:network :none`.
This does not complete provider transport, the maintained best-of-N migration,
the final global campaign or production admission. No global rerun was needed
for these test-only changes; the existing broad RED classification remains.

## Task 10: native authentication follow-up (2026-10-15)

This is a current feasibility investigation, not F4 or production qualification.
The revised [D7 contract](../../design/workflow_lisp_run_ref_expression_environments.md#isolation-credentials-and-resource-contract)
and [Task 10](../../plans/2026-10-14-run-ref-expression-environments-plan.md#task-10-provider-transport)
select Codex managed ChatGPT login through a private persistent native auth owner.
The user authorized reuse of the existing native login and normal refresh; no API
key is required for this selected route. Claude and other transports remain
unqualified. Historical F4/P2 keeps its original in-sandbox PASS,
`502 upstream_blocked` upstream result and host-binary deviation; no earlier
API-key-only experiment is relabelled as a native-login success.

| Evidence | Observed result and limit |
| --- | --- |
| Native-owner fixture, 2026-10-15 | Bounded independent PASS review; 19 historical category rows retained. Native auth RPC and routing were exercised with synthetic credentials in an isolated namespace, not a real account. |
| Image-CLI / real-Holder synthetic bridge, 2026-10-15 | Bounded independent PASS review; 62 category rows, `DONE_WITH_CONCERNS`. An image-owned Codex CLI made two synthetic SSE requests, edited and tested the candidate, delivered typed JSON and left a committed checkpoint. This uses the experimental socket seam under `network=none`, not production `model-only` admission or the public ORC provider lifecycle. |
| Native-login qualification decision and remote-control correction, 2026-10-15 | Independent documentary PASS. The pinned config schema accepted 20 corrected overrides; the former `allow_remote_control` ConfigToml override was rejected. The replacement is the pinned internal environment marker `CODEX_INTERNAL_APP_SERVER_REMOTE_CONTROL_DISABLED=1`, with no `--remote-control`. Schema/source checks are not operational startup or account evidence. |
| Operational prerequisites and cancellation correction | Independent bounded PASS. The original 78-row synthetic campaign remains intact; the R1 correction has 80 rows in eleven suites, exit 0, and 14 fresh independent cancellation controls pass. A timing race in the old-code RED replay fixture is recorded; two direct old-code replays reproduce the late POST. No synthetic TLS seam is presented as a real handshake. |
| First existing-login attempt | **UNQUALIFIED**: the one-attempt, two-request/90-second entry reached its absolute deadline before confirming the native account binding. No inference gateway or Holder was created. The supervisor verified its worker group empty; Holder/carrier cleanup fields are not applicable. Wrapper exit 0 is not experiment success. F4 and integrated Task 10 remain pending. |
| Separate zero-inference stage diagnostic | Independent code/security PASS preceded one new startup/preflight, with the same pins, environment and 90-second limit. The initialize request was flushed, but no matching response was observed before expiry; no account RPC or inference occurred. The worker group was empty and Holder/carrier were not applicable. This locates the protocol boundary without establishing why it stalled or explaining the first attempt. |

The original owner output (19 rows), subsequent synthetic output (62 rows),
source manifests, dates and categories remain unchanged in the local SDD evidence
for this plan. The historical `keyring:absent` category meant absence of mounted
user-runtime paths and credential-service sockets with a file-backed fixture;
it did not demonstrate kernel-keyring isolation. The complete synthetic fixture
also superseded refresh/owner-generation inferences affected by its original
incomplete identity. Those causal limits are preserved rather than treated as
native concurrency guarantees. The synthetic `token-budget` category did not
prove upstream token enforcement; slow-body rejection measured inactivity,
not a total deadline. The original F4 host-binary mount remains a deviation;
the later synthetic bridge used a new image-owned executable and did not
retroactively qualify that earlier run.

The selected native pin is Codex `0.162.1`, source
`092d3acd6bec3e3a14bdc7e7a2810ab628ab759d`, executable SHA-256
`628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1`.
Before using a real login, the new probe must prove total `CLOCK_BOOTTIME`
deadline/cancellation across blocking phases, exact model/config tool schemas,
secret-free synthetic artifacts (excluding only the exact synthetic credential
store object), and native-startup auxiliary isolation. Startup checks include
a static pinned catalog, all three OTEL exporters disabled, the
`environments.toml` existence guard before startup/grant, and a positive/negative
remote-control canary with persisted enabled preference. The source/schema
re-reading alone did not establish those checks; the subsequent operational
campaign and independent review now provide their bounded synthetic evidence.

The initial real-login experiment is bounded to one attempt, at most two serial
inference requests and 90 seconds total from before owner startup, with no
HTTP/stream/CLI retry. These are probe limits only: production must use checked
per-attempt policy and the child's existing durable remaining wall allowance,
without resetting it or adding a Task 7 watchdog. Request/response byte and wall
controls do not prove a remote generation-token or economic cap. A policy that
requires an unsupported hard token/cost ceiling refuses before auth/inference;
incomplete usage and unsupported cost remain `UNKNOWN`. A local disconnect does
not prove immediate remote cancellation. A later live result, including refusal,
must be recorded separately; it cannot by itself complete Task 10 or advance
Task 13 admission.

The first live result is preserved separately in local SDD
`task-10-native-auth-live-report.md` (SHA-256
`3499a05d9475e9d17a2e3803ec0dc5a4cae26af008ae3d431c1dabbcad2d6c56`)
and `task-10-native-auth-live/`, including exact invocation, original categories,
exit and evidence hashes. Its private owner directory exists, but the exact
startup/RPC phase before binding is unknown. It does not demonstrate invalid
credentials or missing entitlement. Native startup/discovery/refresh traffic
and changes to its store are unconfirmed; our code did not inspect that store.
The supervisor observed a 0.067191 ms deadline delay and 45.915125 ms cleanup
after the cut, without a real-time guarantee. No full inference retry or limit expansion has
been performed; the separate stage diagnostic is recorded below. Command
Increment A is accepted above.
The original Holder/carrier cleanup booleans default to true when Holder metadata
is absent; they do not prove a launched Holder was emptied. This interpretation
is preserved separately in SDD `task-10-native-auth-live-observation-addendum.md`.

The separate diagnostic has 34 synthetic result rows and an independent
conformance/code/security PASS before the coordinator's single actual activation.
Its actual output has ten bounded categorical rows (946 bytes), no stderr,
and wrapper exit 0. Preparation and spawn completed; initialize was flushed
at elapsed 368,932,133 ns with no response observed before the 90-second cutoff.
Final group-empty projection occurred at 90,061,534,605 ns; that includes reporting
and is not a measurement of exact cleanup latency. No initialized notification
or account-read followed. Cause, native startup traffic and store effects remain
unknown; no credential/configuration/log/DB files were inspected. Source-level
startup diagnosis and the bounded offline comparison below do not identify
the real cause; there is no automatic reactivation. Local SDD
`task-10-native-auth-stage-live-report.md`, SHA-256
`dbda33a8f9bed0fb49a5401b8575c1b41a00dcba30f75ee92d414e9552b80417`,
and its adjacent evidence directory retain the exact invocation and result.

## Task 10: internal request authority (2026-10-15)

Commit `9cd25356` adds the two parent-ledger facts for conservative request
reservations and the visit/policy-bound public account digest. Capacity and
binding survive K4 and lost acknowledgements; uncertain incarnations cannot
reuse a permit. Existing serial and internal parallel acknowledgement validation,
wall accounting, retention quota and terminal-first replay remain authoritative.
Command-only and v1 behavior is preserved. This internal preparation does not
admit providers or qualify the native transport.

Independent conformance followed by code/security review passed after correcting
the explicit authentication-mode digest field and strict nested JSON parsing.
Final verification: **502 affected tests in 39.56 s**, **26 focal tests**, and
**145 collected**. The real command module passed **13 tests in 24.26 s** before
the two provider-helper-only corrections; reuse is justified by their unchanged
command path. Parent `20261015T121303Z-lubwa9`, child
`run-ref-503ca38a78cb3233c72b8ff733889bf11893a01a`, and retained artifacts are in
local `.tmp/task10-ledger/`. The coordinator read the diff and evidence and
verified all seven committed file hashes against manifest
`5cdd614db94abffce73d345ba70416a788db3aad13b7d9bcca9d3946368af075`.

Policy validation here establishes retained structure and canonical bytes;
future admission must establish semantic validity, provenance, absence of
secrets and installed pins before the first reservation. The private gateway,
native owner containment, independent cancellation observer, real provider
qualification and public integration remain pending. No global suite was
rerun for this slice; the earlier broad RED classification remains.


The subsequent pinned-source disposition selected one offline control and one
held-bundle comparison in isolated namespaces with fictitious business auth.
The control received initialize at 605.808698 ms and finished at 1.121769382 s;
the held-bundle owner exited at 20.354260842 s, before the 90-second deadline,
without an initialize response. Both groups were observed empty; Holder/carrier
were N/A. Two bundle requests and no unexpected endpoint were observed in the
perturbation. This condition did not reproduce the 90-second symptom; it does
not exclude cloud generally or identify the actual cause. No actual auth or
inference was repeated. Local SDD `task-10-native-initialize-pair-report.md`
has SHA-256 `666ec70360478a783e0e17bf9397b2ae0764238f0b505f31ff6c8c8fac829bad`.
Its observation addendum distinguishes observed worker exits 0/3 from the outer
runner exit, which was inferred rather than captured and remains UNKNOWN.

## Task 10: private transport core (2026-10-15)

Commit `32e9fda6` adds the private fixed-route transport core, native RPC client,
semantic policy checks and exact pinned data resources, with no public caller
or process creation. It consumes the common ledger authority, discards the
preflight bearer and acquires fresh credentials for each request. Assets are
verified from an installed wheel outside the source tree. Public provider and
model-only refusals remain in place.

Independent conformance then code/security review passed after correcting
native writes after observed revocation and the environment guard after delayed
binding acknowledgement. HTTP/SSE truncation regressions also passed. Final
verification: **66 collected**, **66 narrow tests in 10.24 s**, **329 affected
tests in 11.85 s**, and five independent review regressions. Root read the full
change and verified all seven committed file hashes against source manifest
`2755b06181e16155437e66481d4e0efcae3fb76c6fee493e0c33494d881bb83f`.
Local SDD `task-10-transport-core-review.md` has SHA-256
`63af9e64fe9707cde05bdcbd0f80b29409cb0327a4091f4d39268ff91946685c`;
`/tmp/runref-transport-core-validation/` retains original RED/GREEN campaigns.

These checks use synthetic pipes/HTTP and the common ledger; they do not prove
real authentication or upstream TLS behavior. Public smoke was not repeated
for the module without callers. Host-slot containment, independent cancellation
observation during blocked durable acknowledgements, private IPC, scope cleanup
and their real command smoke are the next internal integration slice. Actual
provider qualification, public integration and Tasks 11–13 remain pending.
