# E1 `run-ref` Final Review

Status: `PASS_E1`

Reviewed candidate:

- base tree: `3eeb2ffd591cdc50e5fad12ba394f115ed6a60a1`;
- exact staged binary-diff SHA-256:
  `85928186160c6b79c720b224afc5720676d50ba4282838e6e561c7906e4509f9`;
- committed candidate: `577715f176fcacf9c29127f8b519d58c3a5b6470`;
- committed tree: `ef7eacbdb747d09754d02aab328606893dad07e3`.

Ordered final verdicts:

1. `E1_FINAL_SPEC_APPROVED`, issued by the independent delegated
   specification reviewer `/root/e1_task9_dispatch_extract` against the exact
   staged tree and diff digest above.
2. `E1_FINAL_QUALITY_APPROVED`, issued afterward by the distinct independent
   delegated quality reviewer `/root/e1_task9_dispatch_quickcheck` against the
   unchanged candidate.

The reviewed candidate was committed byte-for-byte as `577715f1`; its tree is
the reviewed staged tree. Its fresh postcommit run-ref, routing, and
route-readiness control passed 864 tests. Unstaged owner P-series work was
excluded from the candidate and remained untouched after commit.

## Implementation lineage

| Task | Reviewed tip | Result |
| --- | --- | --- |
| 0A/0B — entry proof and reviewed plan | `04c13f99` | compiler hermeticity proved; ordered plan gate accepted |
| 1 — target-2.24 contracts | `c73cb00b` | normative syntax, state, versioning, and routing landed |
| 2 — source identity and materialization | `91ce4090` | exact pinned source, clone, setup, and tree evidence landed |
| 3 — structured compiler diagnostics | `949bd4df` | ordinary full compiler exposes one stable JSON diagnostic API |
| 4 — typed compiler and shared IR | `c01c4149` | `run-ref` crosses all compiler, IR, checkpoint, and persisted views |
| 5 — compiled-bundle capsule | `bf16b22a` | closed mode-1 capsule runs without compiler or controller-source reads |
| 6 — path-mode compilation and admission | `44d1aa2b` | mode 2 uses the full compiler and closed effect admission |
| 7 — durable child runtime | `2a0ae82e` | separate roots, attempt ledger, fresh rerun, reuse, and delta evidence landed |
| 8 — end-to-end feasibility proofs | `2a1f42f2` | both modes and feasibility proofs 2–4 passed; closure `79540e0a` |
| 9 — exact final candidate | `577715f1` | routing candidate, compatibility correction, final gates, and ordered reviews passed |

## Verification evidence

- New end-to-end module: 4 tests collected.
- Deterministic CLI plus real parent/child smoke: 2 passed.
- Final pre-review focused E1 and adjacent gate: 2,015 passed in 13.87
  seconds; complete log SHA-256
  `f14ba4e1edab922069395bc5d4ddfa5b014e02f1a0b3d05dd6f98f73421e4cb8`.
- Initial broad run: 11,087 passed and six failed. The failures exposed the
  lowering-core size ratchet and five additive compatibility rows missing the
  nullable `run_ref` compiler carrier. The run-ref lowering moved intact to
  its existing owner, and only the five compiler-carrier rows and their
  digests changed.
- Corrected broad non-security gate: 10,798 passed, 19 skipped, 5 warnings,
  and zero failures/errors in 144.21 seconds; complete log SHA-256
  `383a7ff687b2ce2c360b357a1184b666dca9741c5ac0cb98f60c275723e7d90f`.
- Fresh postcommit run-ref, routing, and route-readiness control: 864 passed
  in 30.40 seconds; complete log SHA-256
  `38ea61a994595350813c47112dc8622e2421e2b3ec022fc7c31f466661b816f8`.
- `git diff --check` and the exact staged-candidate check passed before
  review and commit.

The broad run preserved the repository's standing exclusions for security,
safety, secrets, provider isolation, and the provider-launch shim. Those
exclusions are not counted as passing E1 evidence.

## Exit decision

`PASS_E1`

Target 2.24 is normative and backward compatible. `run-ref` is a distinct
durable pinned-revision effect in both compiled-bundle and clone-path modes;
the first executes without compiler or mutable controller-source reads, and
the second uses the ordinary full compiler and structured rejection surface.
Both modes preserve exact transportable contracts, deterministic identity and
workspace evidence, separate run roots and writers, committed-result reuse,
and incomplete-attempt discard followed by a fresh run. Generated candidates
admit only through the accepted deterministic-effect-free profile; this gate
makes no sandbox or isolation claim.

This verdict completes E1 only. It makes the already selected E2 tranche
eligible for its separate target-2.25 reviewed component plan. It does not
implement E2, make E3 eligible, select C1-C3, or modify any P-series surface.
