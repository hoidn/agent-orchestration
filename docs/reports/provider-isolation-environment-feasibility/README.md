# Provider Isolation Environment Feasibility

Status: `I0E_PASSED`

Assessment date: 2026-07-25

Governing plan:
[`docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md`](../../superpowers/plans/2026-07-23-provider-phase-information-isolation.md)

## Decision

The canonical content identity, corrected sealed snapshot, fixed bootstrap,
provider-runtime closure, and final sealed Bubblewrap execution pass. The
owner-run proof exercised the real packaged provider and completed every
required strict reload and quiescence check. Both final independent evidence
reviews approved promotion. `I0E` therefore passes and authorizes progression
to the next roadmap gate.

## Accepted identity

- Mutable packaging source:
  `/home/ollie/.local/share/agent-orchestration/provider-environments/codex-cli-0.145.0-python-3.12`
- Provider-visible build prefix: `/opt/orchestrator-provider`
- Prospective manifest:
  `/home/ollie/.provider-isolation-evidence/manifests/codex-cli-0.145.0-python-3.12.validated-v4.prospective.json`
- Fresh run root:
  `/home/ollie/.provider-isolation-evidence/i0e-run-v4`
- Environment/manifest digest:
  `sha256:f739b415b2dd73a656657d87f603acf67462ce8f1d19a086048f8897248e9c6c`
- Manifest rows: 1,317
- Snapshot symlinks: 0
- Strict materialized-bootstrap digest:
  `sha256:e6f2aec25645d01ed7337b3e8f9571b1741c8c7e4fee9e85f97ab07abfb8efdf`
- Prospective virtual-shim bootstrap digest:
  `sha256:6a485521cf32bf67f48775be54866d4c9e9ad539a6554b1c2de01d8f0dfe1a60`
- Independently pinned launch-shim source digest:
  `sha256:c99355dc578e53f7a97cc26dd01077a18e248ee32deb517ba4c0af8650ebe1e7`
- Standard-library projection: 1,286 rows,
  `sha256:2942c6fb45b13aaabecf2c25b2b32151bcf6fb65a9e8064cb0f5ed574502a52a`

The packaging source is symlink-free. Two formerly linked paths were
materialized as ordinary files before the accepted manifest was authored:

- `_sysconfigdata__linux_x86_64-linux-gnu.py` is a regular copy of the packaged
  `_sysconfigdata__x86_64-linux-gnu.py`.
- `/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2` is a regular copy of the
  packaged `/lib64/ld-linux-x86-64.so.2`, required by the reviewed glibc
  default-directory resolution.

Future package updates must keep those duplicate bytes synchronized or produce
a new environment identity and rerun `I0E`.

## Static admission evidence

The controller validated the real packaging source without executing the
provider or using `ldd`.

- Fixed CPython: `3.12.3`, invoked as
  `/opt/orchestrator-provider/bin/python -I -S`
- Python ELF closure: 7 manifest-backed rows
- `_ctypes`/libffi ELF closure: 5 manifest-backed rows
- `_ctypes`:
  `/opt/orchestrator-provider/lib/python3.12/lib-dynload/_ctypes.cpython-312-x86_64-linux-gnu.so`
- libffi: `/lib/x86_64-linux-gnu/libffi.so.8`
- Provider executable:
  `/opt/orchestrator-provider/bin/codex`
- Provider executable size: 310,730,800 bytes
- Provider executable digest:
  `sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14`
- Provider runtime closure: one statically linked executable row

The v4 snapshot passed two consecutive strict descriptor-based reloads after
the manifest-inode no-atime correction passed independent review. All 1,317
rootfs rows are symlink-free and retain the required fixed no-atime inode flag
and zero timestamps. The strict loader requires the published manifest inode
to carry the same flag and rechecks the flag and zero timestamps after reading.

## Host preflight

- Bubblewrap: `0.9.0`
- Kernel: Linux `6.17.0-35-generic`
- `kernel.apparmor_restrict_unprivileged_userns=1`
- Installed AppArmor profile:
  `/etc/apparmor.d/bwrap-userns-restrict`
- Installed profile SHA-256:
  `11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9`
- Exact gate:
  `/usr/bin/bwrap --unshare-user --uid 0 --gid 0 --ro-bind / / -- /bin/true`
- Gate result: exit 0
- Cgroup: delegated cgroup v2 with `cgroup.kill` and
  `cgroup.events: populated`

## Sealed runtime proof

Accepted proof:

- Log:
  `/home/ollie/.provider-isolation-evidence/i0e-v4-proof-attempt7.log`
- Log SHA-256:
  `52d40d6b1725d5bfe21fbcc2de04c5e88e9d4e92320a307584ee994ab0225150`
- Log size: 2,532 bytes
- Binding status: `validated_current_script_binding`
- Summary status: `passed`

The reviewed harness has one fixed 60-second launch deadline and one shared
five-second failure-cleanup deadline. It forks directly, confirms the
Bubblewrap `execve` handshake, moves the complete launch tree into one
delegated cgroup-v2 leaf, and requires `cgroup.kill` plus
`cgroup.events: populated 0` on failure. Normal completion requires the leaf
to be naturally empty before removal. It additionally uses pidfds, exact
reaping, and process-group absence as corroborating evidence.

The proof ran three launches from the same pinned sealed root descriptor:

1. Python identity, nonce, descriptor, credential, keyring/syscall, namespace,
   capability, NSS, and module-origin diagnostics;
2. real `codex --version`; and
3. real `codex --help`.

Each launch revalidates the fixed bootstrap first. Each completed probe is
followed by a fresh strict snapshot reload.

Observed results:

- Provider: `codex-cli 0.145.0`
- Provider help SHA-256:
  `e0e9bf467f5eaa19c0d1f3d4db6f10844cdb080d30ddfdcbb384a16cb54171e5`
- Python: `3.12.3`, cache tag `cpython-312`
- Provider identity: uid/gid `0:0`; PID/session/process group `1/1/1`
- Environment names:
  `HOME`, `I0E_NONCE`, `LANG`, `LC_ALL`, `PATH`, `TMPDIR`
- Supplementary groups and surviving fds at or above 3: empty
- `NoNewPrivs`: `1`; all five capability sets: zero
- Network: loopback only, with no non-loopback IPv4 or IPv6 routes
- Key syscalls: `add_key`, `request_key`, and `keyctl` denied with `EPERM`
- Nested user-namespace creation: failed with `ENOSPC`; Bubblewrap 0.9 uses
  `user.max_user_namespaces` exhaustion for `--disable-userns`, and
  `--assert-userns-disabled` also passed
- Post-probe strict reloads:
  `sealed diagnostic`, `provider version probe`, `provider help probe`
- Three unique launch cgroups became quiescent and were removed; a
  user-slice-wide residue scan found zero `i0e-proof-*` cgroups
- A fresh strict post-proof snapshot reload and materialized-bootstrap
  validation passed

## Verification

Fresh focused results:

- Collection: 499 tests
- Host-independent Task 1A gate: 495 passed, 4 deselected
- The four deselections are the live-shim checks that require an actually empty
  supplementary-group vector. This interactive controller cannot drop its
  groups without sudo; the sealed proof performs the exact checks after an
  owner-authorized `setpriv --clear-groups`.
- Independent specification review: approved
- Independent code-quality/no-atime review: approved after correction
- Independent proof-harness lifecycle review: approved
- Nested-userns denial correction specification review: approved
- Nested-userns denial correction quality review: approved
- Final proof-evidence specification review: approved
- Final proof-evidence quality/consistency review: approved
- Scoped `git diff --check`: passed
- Python compilation: passed

The required broad command,
`pytest -q -n 16 --dist=worksteal`, collected the current repository state and
finished with 7,983 passed, 21 skipped, 8 failed, and 3 collection errors.
Four failures are the same expected uncleared-group cases. Four unrelated
Workflow Lisp/output-contract failures reproduce under direct narrow
selection. The three collection errors are stale YAML tests importing the
intentionally removed `orchestrator.loader`. None intersects the Task 1A
implementation or its focused selectors; this report does not relabel those
repository-wide failures as passing.

## Rejected proof attempts

Every failed or cancelled proof log remains immutable and excluded. No failed
attempt contributes to the accepted runtime claim.

- Initial log: only the pre-sudo line was captured; no provider proof began.
  SHA-256:
  `f46b995b40c38f42274d3dac3480b12d3298b66e073f05b3aa430edb65ae6372`.
- Attempt 2: the non-TTY runner could not prompt for sudo. SHA-256:
  `b9db16995f6f3ae62c30902cf3d88aed66597e2537941da933632d36c96c411e`.
- Attempt 3: the graphical askpass prompt was cancelled before proof
  execution after renderer warnings. SHA-256:
  `51c4c22fff7d99bdf23f37da90e33ada245e89abb6aeb2988c89f25b4bb21993`.
- Attempt 4: the real-terminal prompt was cancelled before proof execution.
  SHA-256:
  `f46b995b40c38f42274d3dac3480b12d3298b66e073f05b3aa430edb65ae6372`.
- Attempt 5: the terminal cgroup was not delegated; the controller stopped
  before provider launch. SHA-256:
  `44321e9d5c17933957c8a2eabe3dfaa31835d4cfc55a2106a2c6cc73253d03af`.
- Attempt 6: the sealed diagnostic ran and cleaned up, but the harness
  misclassified Bubblewrap's valid `ENOSPC` nested-userns denial as a failure;
  version/help did not run. SHA-256:
  `92ea9b6358c7a82a5694e43805e5b3bec6b9c617b7bdee17bf9e81d2140e924a`.

## Rejected diagnostic identities

No rejected snapshot was repaired, promoted, or reused.

- `i0e-run-v1` / `sha256:fa67baac…` predates the finalized symlink-free and
  no-atime contract and remains diagnostic-only.
- `i0e-run-v2` used the accepted content identity, but an ordinary
  post-publication `cmp`/`sha256sum` verification changed its protected
  manifest atime. The strict loader rejected it with
  `provider_isolation_environment_invalid`. It remains untouched and is not
  evidence.
- An operator diagnostic directly invoked the mutable-source Codex binary with
  `--version` in the controller namespace. That invocation violated the
  evidence procedure, is excluded completely, and contributes no identity or
  execution claim here.
- `i0e-run-v3` was assembled fresh and its manifest retained zero timestamps
  across two strict reloads. Final review nevertheless rejected it because the
  implementation did not require the manifest inode itself to carry the fixed
  no-atime flag; a filesystem-level read fallback could therefore have changed
  its atime before rejection. It remains untouched and is not evidence.

## Limitations

- This is one reviewed Linux x86-64 glibc and CPython 3.12 bootstrap profile.
  Other interpreter versions or layouts require a new explicit profile.
- The static Codex binary does not have a separate Node runtime identity.
- `I0E` proves a sealed launch environment and offline provider
  `--version`/`--help` behavior. It does not yet implement the production
  backend lifecycle, phase-private result brokerage, public run/resume
  integration, or live-provider behavior; those remain later plan tasks.
