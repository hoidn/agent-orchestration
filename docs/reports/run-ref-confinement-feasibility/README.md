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
