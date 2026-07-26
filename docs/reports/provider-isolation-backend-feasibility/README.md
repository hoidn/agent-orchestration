# Provider Isolation Backend Feasibility

Status: `I0_PASSED`

Assessment date: 2026-07-26

Governing design:
[`docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md`](../../superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md)

Governing plan:
[`docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md`](../../superpowers/plans/2026-07-23-provider-phase-information-isolation.md)

The standalone production Bubblewrap backend has passed its runnable `I0`
directions on this host: a workflow-provider launch, a controller-attempt
certified check with no result channel, and timeout teardown. The complete
focused and affected gates pass, and both ordered independent reviews approved
the result without findings.

This is a standalone backend-feasibility result. It does not implement the
phase-private result broker, `ProviderExecutor` integration, public run/resume
state, attempt attestation, the public `G0` rerun, or a live Codex task. Those
remain Tasks 3–9.

## No-sudo launch contract

Production launches execute the fixed `/usr/bin/bwrap` directly as the
ordinary controller user. The implementation rejects per-run `sudo`, `pkexec`,
privileged `setpriv`, set-ID helpers, capability-bearing helpers, privilege
brokers, and launcher overrides. The accepted real launches ran at controller
EUID/GID `1000:1000` and did not use a privileged launcher.

A locked-down host may still need one administrator provisioning action to
install Bubblewrap or enable the host's AppArmor/user-namespace/cgroup
prerequisites. That is a host deployment prerequisite, not runtime launch
authority. After provisioning, launch is sudo-free; without the prerequisite,
the required backend fails closed as `provider_isolation_backend_unavailable`.

Repository clones at different same-user paths remain experiment hygiene.
They are not an information-isolation boundary.

## Accepted sealed environment

- Packaging source:
  `/home/ollie/.local/share/agent-orchestration/provider-environments/codex-cli-0.145.0-python-3.12`
- Run root:
  `/home/ollie/.provider-isolation-evidence/i0-task2-final-v1`
- Prospective manifest:
  `/home/ollie/.provider-isolation-evidence/i0-task2-final-v1-manifest.json`
- Published manifest:
  `/home/ollie/.provider-isolation-evidence/i0-task2-final-v1/provider_environment_snapshots/sha256:ca501a580da07051cb72b04961cdfa9d645b3baead794d0a17a1023bde419ffa/manifest.json`
- Published rootfs:
  `/home/ollie/.provider-isolation-evidence/i0-task2-final-v1/provider_environment_snapshots/sha256:ca501a580da07051cb72b04961cdfa9d645b3baead794d0a17a1023bde419ffa/rootfs`
- Canonical environment/manifest digest and both manifest file SHA-256 values:
  `sha256:ca501a580da07051cb72b04961cdfa9d645b3baead794d0a17a1023bde419ffa`
- Manifest composition:
  `1320` entries: `111` directories, `1209` regular files, `0` symlinks
- Prospective/published manifest modes:
  `0600` / `0400`
- Provider launch shim source and sealed-manifest digest:
  `sha256:7977b36e524a26073a207b982c0e2612cce910a1f27c12650a6f4a69f84eb2fe`
- Provider:
  `codex-cli 0.145.0`
- Provider executable:
  `/opt/orchestrator-provider/bin/codex`,
  `sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14`

The prospective and published manifests are byte-identical. The accepted live
tests loaded the snapshot by the exact canonical digest and revalidated it
before release.

## Supporting rootless prerequisite

The supporting `I0G` proof is:

- file:
  `/home/ollie/.provider-isolation-evidence/i0-task2-final-v1-i0g-proof.json`
- file SHA-256:
  `sha256:bac2ce3fb0d9f6b55383ba1e5de9837821ce0eb717ed08dc1a1958fb268c7051`
- schema/status:
  `provider_isolation_rootless_i0g_proof.v1` / `passed`
- launches:
  `3`
- final provider descriptors:
  `[0, 1, 2]`
- broad host-root and pathname-backed bind sources:
  absent
- privileged launcher and persisted credential plaintext:
  `false` / `false`
- launch-cgroup residue:
  empty

Its base harness is
`tmp/run-provider-isolation-i0g-proof.py`,
`sha256:dc50f1c3ad064123db2b3008bfdc54c8f6e9676ff4a7420b9e211efa2151b16d`.
The final overlay is
`tmp/run-provider-isolation-i0g-final-proof.py`,
`sha256:233b180bc54792f12dcfddb4a1bf0d3102377610c3dbd8cc376848577ccd85a8`.

Every `I0G` launch used `--unshare-net`. It proves only the narrower rootless
group/object-authority prerequisite. It does not prove the production
shared-network behavior below.

## Production backend identity

The private backend identity record is:

- file:
  `/home/ollie/.provider-isolation-evidence/i0-task2-final-v1-backend-identity.json`
- file SHA-256:
  `sha256:99878b9aacaeb2398a5e014adb058057d10cee042547837769c2562d88d4eafc`
- canonical backend identity:
  `sha256:afa92260d08d68bfebd99ad8342797be04add67a0934aa6b45fdfa4aab070028`
- contract/version:
  `bubblewrap.v1` / `bubblewrap 0.9.0`
- executable:
  `/usr/bin/bwrap`, root-owned mode `0755`, `72160` bytes,
  `sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712`
- startup closure:
  `6` path-bound entries
- loader cache:
  `/etc/ld.so.cache`,
  `sha256:f8fcb8f2a9f81e7cd26ea6e5ebddf739568e5ace535208aa0eee814f61089f36`
- startup configuration:
  `/etc/ld.so.preload` absent
- containment root identity:
  `sha256:5d7fb53582eb6c128a61a87729c30a7068ac61f82b0906e100b01a27a2bd0acf`
- containment capability checks:
  create/member/reload/kill/empty/remove all passed

The capability identity records
`test_only_host_root_projection=true`; that bootstrap probe establishes host
capability only. The minimal production projection is established by the real
launch tests, not inferred from that bootstrap probe.

## Production shared-network preflight

The accepted content-addressed capture is
`/home/ollie/.provider-isolation-evidence/i0-task2-final-v1-network-attempt3`.
All three files are controller-owned mode `0600` below a mode-`0700` real
directory.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `private-network-inventory.json` | 7102 | `sha256:6567082c6cc703df3c0841ba3e0917709198f43256c1838d41d42db2a6cd65f0` |
| `network-preflight.json` | 1157 | `sha256:2c160d2d756aab15498f3069b55fa3085f3960a1ab6f626abccdf8058244553d` |
| `evidence-summary.json` | 1996 | `sha256:8632a5a2ef2aec6bfb92c53d7baf960609faf46e565e016333572e6627a2c656` |

The accepted inventory contained `55` listeners:

| Class | Count |
| --- | ---: |
| TCP IPv4 / IPv6 | 28 / 12 |
| UDP IPv4 / IPv6 | 7 / 3 |
| Abstract stream / datagram / seqpacket | 3 / 1 / 1 |

The closed endpoint-set digest was
`sha256:d6422fba14aaca81f0656c7041f33d2cca634f09eb90e541cd1a65da4c61a6dc`.
All five versioned cloud-metadata probes returned
`status=not_reachable, match_code=timeout`. Runtime-known endpoints were empty.
The inventory decision was `accept_unlisted_reachability`, with the explicit
assumption
`all_unlisted_local_and_remote_reachability_is_a_deployment_trust_assumption`.
The exact capability revalidated twice in the capture.

The capture harness is
`tmp/capture-provider-isolation-i0-network-evidence.py`,
`sha256:1c6d8c11c79ee7512f8a5c65ac8d02b669f4985b6fc1742e9f83cf1e8303922d`.
It records the `shared_host_network` contract but does not claim to observe a
provider namespace. The real launch test separately proves that production
argv omits `--unshare-net`, provider and controller see the same network
namespace identity, registered loopback TCP and abstract-UNIX sentinels are
reachable, and the cloud-metadata probe is not reachable.

## Accepted real launch results

The accepted JUnit artifacts use the final fixture/test identity. All are mode
`0600`.

| Direction | Artifact | SHA-256 | Result |
| --- | --- | --- | --- |
| workflow provider, typed scratch | `i0-task2-final-v1-live-tests/workflow-provider-attempt7.xml` | `sha256:1be07cb55e4d19a2899462a22d294a5283384b35104d3693d3900da9d4b23fb2` | 1 passed in 14.53s |
| controller certified check, no result channel | `i0-task2-final-v1-live-tests/controller-attempt9.xml` | `sha256:927d94bad6bcc351b8287b11879b3c313fed3b8b612e196b8e5d87d7cd3d5cc3` | 1 passed in 14.61s |
| timeout, exact-slot kill and quiescence | `i0-task2-final-v1-live-tests/timeout-attempt7.xml` | `sha256:73c82c956ede1103f4fafeb41d5da953f31b5e4978f0f1e972b4cc3337af6748` | 1 passed in 20.11s |

All three used:

```text
ORCHESTRATOR_I0_ENVIRONMENT_RUN_ROOT=/home/ollie/.provider-isolation-evidence/i0-task2-final-v1
ORCHESTRATOR_I0_ENVIRONMENT_DIGEST=sha256:ca501a580da07051cb72b04961cdfa9d645b3baead794d0a17a1023bde419ffa
ORCHESTRATOR_I0_ENVIRONMENT_SOURCE=/home/ollie/.local/share/agent-orchestration/provider-environments/codex-cli-0.145.0-python-3.12
TMPDIR=/home/ollie/.i0p
```

The exact pytest nodes were:

```text
tests/test_provider_isolation_backend.py::test_real_rootless_projection_denies_external_and_publishes_only_scratch
tests/test_provider_isolation_backend.py::test_real_controller_attempt_certified_check_denies_g0_without_bundle
tests/test_provider_isolation_backend.py::test_real_timeout_kills_exact_slot_and_proves_quiescence
```

## Positive and denial matrix

| Surface | Observed result |
| --- | --- |
| Candidate product | read/write; provider-owned file persisted |
| Workflow active result | only invocation-private scratch path writable |
| Controller attempt result channel | `none`; no scratch mount and no output-bundle environment variable |
| External roots and sentinels | unreadable |
| Prior raw provider bundle | unreadable |
| Absolute and relative symlink escapes | unreadable |
| Pre-opened forbidden file/directory descriptors | absent from provider |
| Pre-opened pseudo-terminal descriptors | absent from provider |
| Final provider descriptor inventory | exactly `0,1,2` |
| Directory-fd `openat("..")` probes | parent could be opened only inside projection; all forbidden targets remained unreadable |
| PID view | provider is PID 1; only PID 1 visible |
| `/proc/1/fd` | exactly normalized stdio `0,1,2`; no setup or foreign descriptor |
| `pidfd_getfd` | attempted for the exact PID-1 stdio set; any success duplicates only already-observed provider-owned stdio |
| ptrace | no allowed attachment |
| `/proc/1/mem` | valid-address probe reads only a known provider-owned 33-byte marker; no foreign/setup-memory claim |
| `/proc/1/{cwd,root,environ,cmdline}` | exact candidate cwd, `/` root, exact fixed environment and target argv; no forbidden host-control path |
| TTY injection | exact `TIOCSTI`/`TIOCSCTTY` attempts on fd 0/1/2 and `/dev/tty`; none allowed |
| Network | intentionally shared host namespace; registered local sentinels reachable; cloud metadata not reachable |
| Namespace identity | one-row uid/gid maps, `setgroups: deny`, mapped inner uid/gid `0:0` |
| Process hardening | new session/PID 1, fixed hostname, `NoNewPrivs: 1`, all five capability sets zero |
| Keys/nested userns | key syscalls and nested user namespace denied |
| Containment | one exact cgroup-v2 slot, release after durable commit, kill/empty/remove on timeout and completion |

Self-owned stdio duplication and the provider's own valid memory marker are not
classified as external-authority leaks. The invariant is absence of
setup/foreign authority, not blanket denial of a process observing itself.

## Fail-closed matrix

Focused tests reject:

- missing fixed Bubblewrap, symlinked executable/ancestor, or unsafe
  owner/mode/set-ID/xattr/ancestor authority;
- unsafe startup-closure symlink, swap, or above-root escape while retaining
  safe recorded merged-usr, loader, and SONAME chains;
- same-version pathname replacement;
- same-inode, same-size, mode/mtime-preserved byte mutation;
- loader, transitive-library, loader-cache, and startup-configuration drift;
- unavailable user namespace or delegated cgroup;
- changed complete cgroup2 mount/delegation metadata or mount identity,
  prelaunch nonempty slot, missing/extra post-readiness membership, release
  replay, and unavailable allocation/probe/launch cleanup proof;
- invalid environment/candidate/runtime authority, alias, mount, and digest;
- malformed, changed, or overlapping network inventory authority;
- registered local-service exposure or cloud-metadata reachability;
- invalid workflow/controller request cross-combinations;
- timeout residue; and
- non-`fresh_only` policy session mode.

Regressions also cover a fast capability child that has been reaped while
diagnostic output remains and a provider child reaped immediately before a
later timeout: neither path signals or waits on the numeric PID again.

## Verification

| Gate | Fresh result |
| --- | --- |
| Seven Task 2 modules, collect-only | `602 tests collected in 0.90s` |
| Seven Task 2 modules, non-live | `599 passed, 3 skipped in 11.77s` |
| Policy/environment/environment-CLI owners | `322 passed in 5.43s` |
| Three configured real nodes | each accepted node passed; no skip |
| Broad `pytest -q -n 16 --dist=worksteal` | `8872 passed, 24 skipped, 7 failed, 3 collection errors in 133.57s` |
| Scoped compile and whitespace checks | passed |
| Delegated containment subtree residue | zero `provider-isolation-*` child directories |

The three non-live skips are exactly the explicitly configured real nodes; a
skip is not used as `I0` evidence.

The broad suite is not globally green. Five failures are in workflow
output-contract, semantic-IR, Workflow Lisp diagnostics, and
procedure-migration tests. Two additional failures are xdist-only
sealed-environment failures caused by concurrent changes to the shared
`/tmp` ancestor during identity admission; the exact two nodes passed together
immediately afterward (`2 passed in 0.81s`), and their complete focused owner
gates pass above. The three collection errors are stale imports of the
concurrently retired `orchestrator.loader` module in
`test_at61_at62_wait_for_path_safety.py`, `test_cli_safety.py`, and
`test_secrets.py`. This report preserves every result; it does not exclude,
waive, or relabel any failure.

## Preserved rejected and superseded attempts

No attempt was rewritten or relabeled.

- Network evidence attempt 1 failed before publication because the evidence
  harness supplied unavailable placeholder denied-authority roots.
- Network evidence attempt 2 passed mechanically but its summary used an
  unqualified `shared_host_network=true` field not directly observed by that
  capture. It is superseded by attempt 3's explicit contract/observation
  distinction.
- `workflow-provider-attempt1.xml`,
  `controller-attempt2.xml` through `controller-attempt4.xml`,
  `controller-attempt7.xml`, and
  `timeout-attempt3.xml` failed closed because unrelated host listener
  identities changed between reviewed capture and launch release.
- `workflow-provider-attempt6.xml`
  (`sha256:5086d057160ecd9f0c1105c12d004761106573d29980aed3fbe092ac4715cbf5`)
  and `timeout-attempt6.xml`
  (`sha256:81cc40c67d1f411fa14de11d98f948acb0e963fa8378cfd54478501fe6adad3f`)
  are preserved fresh fail-closed listener-churn attempts from the final
  evidence round.
- Earlier passing workflow/controller/timeout XML files, including attempts
  4/6/4 and 5/8/5, are superseded by later fixture/test identities and are not
  acceptance evidence.

Listener churn is a deployment availability fact, not authority to weaken
exact network revalidation.

Two broad invocations were rejected as verification attempts before the
accepted default-environment run:

- the first exhausted an already-full root-filesystem `/tmp` and produced
  `5711 passed`, `21 skipped`, `60 failed`, and `3026 errors`; and
- the second moved `TMPDIR` to the home filesystem, which changed the
  semantics of tests that intentionally bind canonical `/tmp` paths and
  produced `8739 passed`, `24 skipped`, `52 failed`, and `3 errors`.

Neither result is used as product evidence. The accepted broad invocation used
the ordinary `/tmp` contract after deleting only stale pytest-owned garbage.

## Independent reviews

Ordered reviews:

1. holistic specification review: **approved**, with no blocking, major, or
   minor findings, over the 23-file sorted manifest aggregate
   `sha256:24a86fb34108ea155cffa1bc917cec4e40dcea8e2875d167ac904cc34850e01c`;
2. holistic quality/evidence review: **approved**, with no blocking, major, or
   minor findings, over the specification-reviewed implementation plus its
   review record at aggregate
   `sha256:251c4f4d3fc79941ba3f61321a97d379caacdd70f14b9a9192f16571f1dd13be`.

## Claim limits

`I0` is one-host, one-backend, one-sealed-environment feasibility evidence.
It does not claim:

- brokered or typed-result validation and transfer;
- ordinary executor, public CLI, state, resume, or attestation integration;
- successful public `G0` or prospective `.orc` experiment execution;
- isolation from information deliberately written into the shared candidate;
- denial of network retrieval or causal noninterference while shared network
  remains the accepted v1 contract;
- resource-exhaustion protection or cgroup quotas;
- cross-platform support or shared provider sessions;
- resistance to another same-user host process mutating the writable candidate
  during invocation; or
- zero-administration deployment on a host whose kernel policy initially
  disables unprivileged Bubblewrap user namespaces.
