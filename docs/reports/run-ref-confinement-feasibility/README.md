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
