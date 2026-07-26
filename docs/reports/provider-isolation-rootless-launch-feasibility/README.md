# Provider Isolation Rootless Launch Feasibility

Status: `I0G_PASSED`

Assessment date: 2026-07-25

Governing design:
[`docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md`](../../superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md)

Governing plan:
[`docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md`](../../superpowers/plans/2026-07-23-provider-phase-information-isolation.md)

For the exact sealed identity recorded below, an ordinary-owner launch retained
the controller's supplementary groups, passed the joint host/inner namespace
binding and closed object/descriptor projection in both directions, and used
no privileged launcher. `I0G` passes and authorizes progression only to Task
2's production-backend `I0` gate.

This is not an `I0` backend-feasibility pass, production launcher, broker,
public run/resume integration, attestation implementation, public `G0` rerun,
or live-provider approval. Current orchestrator provider execution remains
unrestricted.

## Accepted identity

- Packaging source:
  `/home/ollie/.local/share/agent-orchestration/provider-environments/codex-cli-0.145.0-python-3.12`
- Prospective manifest:
  `/home/ollie/.provider-isolation-evidence/manifests/codex-cli-0.145.0-python-3.12.validated-v6.prospective.json`
- Run root:
  `/home/ollie/.provider-isolation-evidence/i0g-run-v6`
- Published rootfs:
  `/home/ollie/.provider-isolation-evidence/i0g-run-v6/provider_environment_snapshots/sha256:d51067aa4774b2a84b3c7a45fd53d8cfd857b50f2909e99532801dbcb9df7ac7/rootfs`
- Published manifest:
  `/home/ollie/.provider-isolation-evidence/i0g-run-v6/provider_environment_snapshots/sha256:d51067aa4774b2a84b3c7a45fd53d8cfd857b50f2909e99532801dbcb9df7ac7/manifest.json`
- Canonical environment/manifest digest:
  `sha256:d51067aa4774b2a84b3c7a45fd53d8cfd857b50f2909e99532801dbcb9df7ac7`
- Manifest rows: `1320`
- Snapshot symlinks: `0`
- Structural mountpoints:
  `candidate`, `dev`, `home`, `proc`, `run`, `tmp`, and `workspace`
- Materialized bootstrap digest:
  `sha256:7bcac522d36a244fd9a2eb7b2603515d228a29066ebe012a6daa37fbdf1b5d9a`
- Independently pinned shim source digest:
  `sha256:94b6d92bd566a45767544e06cb2daa7f778246fa6240024ac73aaba3d7ab14c1`
- Bootstrap import projection: `1286` entries,
  `sha256:2942c6fb45b13aaabecf2c25b2b32151bcf6fb65a9e8064cb0f5ed574502a52a`
- Provider entrypoint:
  `/opt/orchestrator-provider/bin/codex`, `310730800` bytes,
  `sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14`
- Provider version: `codex-cli 0.145.0`
- Provider help digest:
  `sha256:e0e9bf467f5eaa19c0d1f3d4db6f10844cdb080d30ddfdcbb384a16cb54171e5`

The prospective and published manifests were byte-identical. The published
manifest was mode `0400`; the prospective manifest was mode `0600`. Two
prelaunch strict reloads produced the same environment, bootstrap, shim, and
import-projection identities. A strict reload followed each of `diagnostic`,
`version`, and `help`, and the final bootstrap validation remained exact.

## Harness and accepted log

- Harness:
  `/home/ollie/Documents/agent-orchestration/tmp/run-provider-isolation-i0g-proof.py`
- Harness SHA-256:
  `dc50f1c3ad064123db2b3008bfdc54c8f6e9676ff4a7420b9e211efa2151b16d`
- Accepted log:
  `/home/ollie/.provider-isolation-evidence/i0g-v6-proof-attempt1.log`
- Accepted log SHA-256:
  `46ecda76a43a766417526efdf5a7c616c514307c06284ac2860d722e350c1a48`
- Accepted log size/mode/owner: `29836` bytes, `0600`, uid/gid `1000:1000`
- Log schema/status:
  `provider_isolation_rootless_i0g_proof.v1` / `passed`
- Binding status: `validated_current_harness_and_shim_binding`
- Credential names recorded: `I0G_NONCE` for the diagnostic only
- Credential values recorded or persisted: none

The harness source is evidence-only and is not the production backend. Its
accepted command shape was direct `/usr/bin/bwrap` with:

```text
--unshare-user --unshare-ipc --unshare-pid --unshare-net
--unshare-uts --unshare-cgroup
--disable-userns --assert-userns-disabled
--uid 0 --gid 0 --cap-drop ALL
--hostname orchestrator-provider-isolated
--die-with-parent --new-session --as-pid-1
--json-status-fd 8
--ro-bind-fd 4 /
--bind-fd 5 /candidate
--tmpfs /run
--bind-fd 6 /run/provider-scratch
--proc /proc --dev /dev
--tmpfs /tmp --tmpfs /home --dir /home/provider
--clearenv --chdir /
```

The three exact targets after the fixed shim were:

```text
/opt/orchestrator-provider/bin/python -I -S /candidate/probe.py
/opt/orchestrator-provider/bin/codex --version
/opt/orchestrator-provider/bin/codex --help
```

The diagnostic shim arguments declared only the credential name
`I0G_NONCE`; the value travelled through fd 3 after the validated boundary.
The version and help launches declared no credential names.

## Rootless host and namespace boundary

- Controller EUID/EGID: `1000:1000`
- Captured controller supplementary groups:
  `[4, 24, 27, 30, 46, 100, 114, 1000]`
- Supplementary-group multiset digest:
  `sha256:8b9431abfa379e8206e0571e931ee28f8c9e95cdd6c3253ddabfec565c3c6b2b`
- Expected primary/overflow counts: `1` / `7`
- Privileged launcher: `false`
- Per-run `sudo`, `pkexec`, privileged `setpriv`, set-id helper, or
  capability-bearing broker: none
- Bubblewrap:
  `/usr/bin/bwrap`, root-owned mode `0755`, `72160` bytes,
  `sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712`
- Bubblewrap set-ID bits/file capability: absent/absent
- Trusted root-owned mode-`0755` ancestors: `/`, `/usr`, `/usr/bin`

For each of the diagnostic, version, and help launches:

- Bubblewrap emitted one child PID through fd 8.
- The controller acquired a pidfd, opened the child's proc directory without
  following a caller-selected path, and bound its starttime.
- Both initial and immediately-pre-credential host observations saw UID/GID
  map rows `(0, 1000, 1)`, `setgroups: deny`, four UID and GID status columns
  equal to `1000`, and the exact captured supplementary-group multiset.
- The pinned PID/starttime was unchanged and live at both observations.
- The inner process saw UID/GID `0:0`, four all-zero UID/GID status columns,
  one normalized `(0, 0, 1)` map row, `setgroups: deny`, one primary group
  `0`, and seven kernel overflow groups `65534`.
- fd 7 carried exactly byte `0x52` and then EOF.
- The recorded release sequence was exactly:

```text
credential_bytes_before_release:0
bwrap_child_pid
child_pidfd_proc_start_pinned
inner_ready_exact_byte_and_eof
host_initial_validation
host_final_validation
first_fd3_write
```

- Provider exit and Bubblewrap-reported exit were both zero.
- stderr was empty.
- The launch was exactly reaped, its process group was absent, and its
  per-launch cgroup became naturally empty before removal.

The accepted child PIDs/starttimes were evidence observations only:
`559428/151011385`, `559473/151011631`, and `559526/151011868`.
They are not reusable authority.

## Closed object and descriptor projection

The only host-backed mount sources were already-open, admission-checked
descriptors:

| FD | Source role | Destination | Access |
| --- | --- | --- | --- |
| 4 | sealed rootfs | `/` | read-only |
| 5 | owner candidate | `/candidate` | read/write |
| 6 | invocation scratch | `/run/provider-scratch` | read/write |
| 7 | boundary-readiness pipe | setup only | write then close |
| 8 | Bubblewrap JSON status | setup only | write then close |

There were no pathname-backed bind sources and no projection of host `/`,
home, checkout, control root, evidence-root ancestor, or unrelated host
authority. `/proc`, `/dev`, `/home`, `/tmp`, and `/run` were fresh
invocation-private filesystems. The candidate and scratch roots were
controller-owned mode `0700`, descriptor-pinned, and revalidated after every
probe. The sealed snapshot was also revalidated after every probe. At final
provider execution the descriptor inventory was exactly `{0, 1, 2}`.

The candidate probe was mode `0600`, `4398` bytes, with digest
`sha256:ff1f4420869dbc3eecc503066ebea984e13d591edc1858299b2d2f87b81a2ca9`.
The diagnostic scratch contained only mode-`0600` `nonce-digest.txt`, whose
content was the nonce digest rather than the nonce. Version and help scratch
directories remained empty.

The deterministic negative fixture represented a foreign-owned mode-`0640`
candidate source whose group was one of the controller's supplementary
groups. The same `_admit_mount_source` seam rejected it before open:
`opener_call_count` was `0` and `content_read` was `false`. This proves the
rejection direction without reading an unrelated host secret.

## Inner diagnostic

The diagnostic recorded:

- Python `3.12.3`, cache tag `cpython-312`, executable and import paths wholly
  below `/opt/orchestrator-provider`;
- exact environment names `HOME`, `I0G_NONCE`, `LANG`, `LC_ALL`, `PATH`, and
  `TMPDIR`, with no Python bootstrap environment variables;
- nonce verification and scratch write verification;
- `NoNewPrivs: 1`;
- zero inheritable, permitted, effective, bounding, and ambient capabilities;
- `add_key`, `request_key`, and `keyctl` denied with `EPERM`;
- nested user-namespace creation denied with `ENOSPC`;
- PID/session/process-group `1/1/1` and only PID `1` visible in `/proc`;
- hostname `orchestrator-provider-isolated`;
- a network namespace distinct from the controller, loopback as the only
  interface, and no non-loopback IPv4 or IPv6 route; and
- no surviving setup descriptor.

All three launch cgroups were absent after completion. The final residue scan
was empty.

## Rejected immutable attempts

No rejected authority was deleted, rewritten, or relabeled as passing.

| Attempt | Harness identity | Immutable log | Result and disposition |
| --- | --- | --- | --- |
| v5 attempt 1 | `4fbe0ea5acd132977603fcfcdd22ddd442d895448149699853b3d0ed972b407f` | `/home/ollie/.provider-isolation-evidence/i0g-v5-proof-attempt1.log`; 17 bytes; `sha256:f46521728917c021817c822c284cb9c70b5c4fba0aa90d95519d3274a5169d34` | Failed before diagnostic output. The uninstrumented log could not localize the phase, so it was retained and not reused. |
| v5 attempt 2 | `a8bfc0c3524beb2dbbaa4e7f06ef44c282ea34c9ba0134040f4a735de9834f78` | `/home/ollie/.provider-isolation-evidence/i0g-v5-proof-attempt2.log`; 40 bytes; `sha256:467c985dfb34ec039d2fd0ccb7a701026cdbe2ecae93a702d284bf072a1bb334` | `diagnostic:outer_pidfd`. The active Conda Python lacked `os.pidfd_open`; the harness was corrected to use the already-reviewed shim syscall fallback. |
| v5 attempt 3 | `a17fb87b1b1ffd369bd6f4324468517f4282af46170532b0b3132f395c9c2373` | `/home/ollie/.provider-isolation-evidence/i0g-v5-proof-attempt3.log`; 38 bytes; `sha256:dafcfe29330a71e760aec5f7bfa92b526c4e131950faa95c84607feb4155a4c5` | `diagnostic:readiness`. Bubblewrap could not mount `/run` below a read-only rootfs that lacked that structural mountpoint. TDD added manifest-bound structural directories and produced fresh v6 evidence. |

The original v5 environment identity
`sha256:d14c4c19ca2b9c22e41c41794f13f6bd65c5b07cf4c50960344b902e9ddb4d6e`
and all v5 attempt directories remain historical rejected evidence. The v6
success does not mutate or promote them.

## Verification

Fresh verification included:

- `python -m py_compile` and `pyflakes` on the exact harness: passed.
- Harness whitespace check: no finding.
- Attempt-1 candidate, scratch, and log absence immediately before launch:
  passed.
- Structural-mountpoint TDD RED:
  `16 failed, 170 deselected`.
- Structural-mountpoint GREEN:
  `16 passed, 170 deselected`.
- Provider-prefix virtual-row regression RED/GREEN:
  `7 failed` then `7 passed`.
- Focused structural, shim-injection, and authority selector:
  `25 passed, 168 deselected`.
- Complete environment-plus-shim slice:
  `487 passed, 9 warnings`.
- Required Task 1B five-module provider gate:
  `618 passed, 9 warnings`.
- Exact serial rerun of the four provider-named broad failures:
  `4 passed`.
- Evidence-bundle assertion pass:
  `I0G_EVIDENCE_VALIDATED`.

The repository-wide command was:

```text
pytest -q -n 16 --dist=worksteal
```

It completed non-green with `8391 passed, 21 skipped, 12 failed, 42 warnings,
and 3 collection errors in 136.99 seconds`. Four failures named
provider-isolation modules; all four passed the exact serial rerun, and the
complete five-module provider gate passed. The other eight failures and three
collection errors were outside the Task 1B touched provider-isolation files.
This report does not relabel the repository-wide run as passing or erase those
facts.

The remaining failed test IDs were:

- `tests/test_resume_command.py::test_resume_list_map_effect_reuses_committed_call_before_accumulator_projection`
- `tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit`
- three `tests/test_workflow_semantic_ir.py` selectors;
- `tests/test_workflow_lisp_lowering.py::test_lowering_family_owner_modules_exist_across_full_target_map`; and
- two `tests/test_workflow_lisp_expressions.py` selectors.

The collection errors were in:

- `tests/test_at61_at62_wait_for_path_safety.py`
- `tests/test_cli_safety.py`
- `tests/test_secrets.py`

The complete broad output remains a current-worktree fact, not an `I0G`
success criterion substituted for the exact provider gate.

## Review boundary

The structural snapshot correction passed ordered specification and quality
reviews at combined diff identity
`sha256:daafe0947b8549fb30986b145c589259b76b85c1ce0c20fef1bd9110c5295e0d`.
The exact v6 pre-execution harness
`sha256:dc50f1c3ad064123db2b3008bfdc54c8f6e9676ff4a7420b9e211efa2151b16d`
also passed ordered specification/procedure and lifecycle/evidence reviews.

The ordered final holistic reviews both approved the same evidence candidate:

- specification/evidence review `/root/i0g_final_spec_review`: `APPROVED`,
  binding accepted log
  `sha256:46ecda76a43a766417526efdf5a7c616c514307c06284ac2860d722e350c1a48`,
  harness
  `sha256:dc50f1c3ad064123db2b3008bfdc54c8f6e9676ff4a7420b9e211efa2151b16d`,
  report
  `sha256:13ec1ad3ba5c3cc76f7aced02c64e2d6f38743dfffb1a5eb60f6969b9cabd0b6`,
  and tracked relevant diff
  `sha256:cfe37c3cb58643136f32aa0e552e795eb50e75818efd71759ab93c12cfb847d3`;
- quality/evidence/readiness review `/root/i0g_final_quality_review`:
  `APPROVED`, independently binding those same four identities and explicitly
  authorizing Task 1B closure plus Task 2 `I0` opening only.

This review-record amendment and the plan checkbox/status closure change no
runtime or evidence claim. `I0G_PASSED` is effective for the exact identity in
this report.

## Limitations

- This is one reviewed Linux x86-64 host/profile and one exact sealed
  environment/provider identity.
- Ordinary assembly, launch, and provider probes used no `sudo` and require no
  privileged runtime helper. A host that disables unprivileged user
  namespaces is `backend_unavailable`; v1 does not silently elevate. Enabling
  that host capability may still be an operator or administrator provisioning
  action outside the orchestrator runtime.
- The host already had the reviewed AppArmor user-namespace profile loaded.
  This evidence does not claim that arbitrary locked-down hosts require no
  initial administrative policy change.
- Separate repository clones remain useful experiment hygiene, but same-user
  clones do not provide confidentiality from an adversarial same-user provider
  process and are not an isolation substitute.
- The evidence harness is not a production launcher and must not be copied into
  public run/resume integration.
- Production `I0`, broker, lifecycle, state, attestation, public `G0`, and live
  smoke gates remain open.
