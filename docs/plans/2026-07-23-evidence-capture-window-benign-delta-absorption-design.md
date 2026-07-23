# Evidence-Capture Window And Benign Predecessor-Delta Absorption Design

**Status:** Proposed prospective controller extension. It applies to open and
future evidence-capture attempts only. It does not reinterpret or retrofit the
completed YAML-retirement Task 2 attempt or its repair evidence.

**Decision:** Keep an explicit repository-visible capture-window marker and
allow the commit controller to absorb an otherwise uncovered committed
predecessor delta only when a closed, content-bound lineage projection proves
that every uncovered commit/path occurrence is disjoint from the selected
window's declared evidence scope. Any scope intersection, missing coverage, or
ambiguous authority restarts the attempt.

## Context

The retirement commit controller binds a workspace baseline to a later
controlled commit. A valid retirement-control trailer accounts for paths
changed by an intervening controlled commit. A normal commit without that
trailer remains an uncovered predecessor delta and currently invalidates the
attempt even when its changed paths are unrelated to the evidence being
captured.

External commits during capture windows are now expected rather than
exceptional. Restarting a long capture for every unrelated documentation or
feature commit is disproportionate. Silently ignoring those commits would be
incorrect: the workspace-baseline validator must still explain why the current
semantic index differs from the captured one.

The existing generic
`derive_committed_predecessor_lineage(repository_root, baseline_head,
intended_predecessor_head)` projection is the authority for the first-parent
commit sequence, each commit's changed paths and control coordinates, and the
aggregate controlled and uncovered path sets. This design adds a narrow
controller decision over that projection. It does not change Git history,
rewrite the baseline, or declare the unrelated files semantically equivalent.

## Goals

1. Make an active evidence-capture window visible to every repository actor.
2. Bind each window to its exact task, opening time, workspace-baseline HEAD,
   and conservative evidence-path scope.
3. Record, rather than infer later, every accepted uncovered predecessor
   commit/path occurrence.
4. Continue the same capture when all still-uncovered occurrences are outside
   the selected evidence scope.
5. Restart when any still-uncovered occurrence intersects that scope.
6. Preserve the existing root, index, durable-authority, pathspec, trailer,
   commit-tree, and reconstruction checks.
7. Keep the mechanism generic and free of workflow, queue, family, repository,
   task-number, and owner branches.

## Non-Goals

- Retrofitting completed attempts or changing their evidence meaning.
- Treating a disjoint commit as reviewed, correct, or owned by the capture.
- Absorbing uncommitted worktree or index drift.
- Absorbing merges, non-first-parent ancestry, malformed trailers, missing
  objects, or a changed baseline.
- Automatically resolving overlapping edits.
- Authorizing an external commit, evidence mutation, workflow run, deletion,
  or owner attestation.
- Replacing an attempt-disposition record when the capture itself is
  invalidated.

## Capture-Window Marker

The single repository path is:

`state/evidence-capture-windows.json`

The path is live repository-local coordination state under the already ignored
`state/` root. It is not staged, force-added, or made a durable authority.
Durable absorption records snapshot and bind its exact bytes as described
below; fresh-clone reconstruction therefore does not depend on ignored local
state.

Its closed top-level schema is:

```json
{
  "schema_version": "evidence_capture_windows.v1",
  "windows": []
}
```

Its byte grammar is exactly the existing source-binding canonical encoder:

```python
json.dumps(
    value,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8") + b"\n"
```

Path-based validation rejects a semantically equal pretty-printed,
insertion-ordered, BOM-prefixed, non-UTF-8, or missing-final-newline file. Open
and close operations publish only those canonical bytes and reopen them before
returning. The live marker was normalized to this grammar when the incomplete
provisional row was dispositioned, before any absorption authority relied on
its binding.

Each `windows` row has exactly:

```json
{
  "window_id": "<nonempty stable identifier>",
  "task": "<nonempty human-readable task>",
  "opened_at": "<timezone-aware RFC 3339 timestamp>",
  "baseline_head": "<40 lowercase hex commit>",
  "evidence_paths": ["<repository-relative POSIX path>", "..."],
  "status": "open"
}
```

`status` is exactly `open` or `closed`. Rows are ordered by
`(opened_at, window_id)` and `window_id` is unique. `evidence_paths` is a
nonempty sorted unique set of normalized repository-relative paths. Empty
components, `.`/`..`, absolute paths, backslashes, NULs, and redundant
ancestor/descendant scope rows are rejected.

More than one open row is representable because the schema is a repository
coordination surface, not an implicit lock. Every controller operation selects
one exact `window_id`; it never chooses "the latest" row. A missing, duplicate,
closed, or ambiguous selected row fails closed.

### Lifecycle

An attempt opens a row immediately after its workspace baseline is captured or,
for a deliberately reusable baseline, immediately after that baseline is
selected and freshly validated for the new attempt. The row's `baseline_head`
must equal the selected baseline's `head`; a newly captured baseline also
requires `opened_at` to equal its `captured_at`.

The row remains `open` throughout capture, review, precommit validation, the
controlled commit, postcommit validation, and reconstruction. After those
checks pass, the live marker changes only that row's `status` to `closed`.
The next attempt appends a new open row rather than rewriting prior rows. If an
attempt is archived through an accepted disposition, the same status-only close
happens after disposition validation. Marker lifecycle changes remain ignored
local state and never expand a controlled commit's candidate path set.

The controller supplies generic open, close, and validate operations. Every
write uses the existing repository-relative no-follow, compare-before-publish
primitive. It never follows a symlink or overwrites a concurrently changed
marker.

The local commit-message hook is a coordination aid: while any row is open it
rejects a commit without a retirement-control trailer unless the actor
consciously supplies `ORC_CAPTURE_WINDOW_ACK=1`. The hook is not validation
authority. The production controller always reopens and validates the marker
and absorbs or rejects every resulting committed delta. A hook bypass,
override, absence, or failure cannot make a delta disappear.

## Scope Intersection

Git reports file or gitlink paths while a window may name a file or subtree.
An uncovered path intersects a scope row when either path is equal to the
other, is a descendant of the other, or is an ancestor of the other. This
symmetric lexical rule catches both a file under a scoped directory and a
commit that replaces a scoped parent directory.

All comparisons use normalized repository-relative POSIX paths. There is no
basename, glob, substring, realpath, or case-folded match.

The scope must conservatively contain every mutable source, test, fixture,
evidence, review, ledger, state, and generated artifact owned by or capable of
changing the active attempt's candidate or verdict. Omitting such a path is a
capture-definition error; absorption is not a substitute for a complete scope.
Separately committed prerequisite design/review documents may remain outside
the active scope only when their commits intentionally precede candidate
capture and the later implementation subject content-binds their exact
digests. Such an acknowledged prerequisite commit is still recorded as
uncovered predecessor lineage; this exception does not apply to its production
implementation or owning tests.

Completeness is mechanically checked in both consumers of the scope. Every
`implementation_verification_subject.v2.candidate_path_manifest` row and every
prospective `build_precommit_control.allowed_paths` entry must be equal to or a
descendant of at least one selected `window.evidence_paths` row. The symmetric
ancestor rule remains only for detecting predecessor intersection; a candidate
or allowed path cannot be an ancestor of its declared scope. Extra conservative
scope rows are permitted. A path outside the scope fails before subject review
or precommit validation and is never rescued by absorption.

## Recorded Absorption Authority

Every prospective controlled capture commit carries one always-present
`evidence_capture_window_boundary.v1` durable authority. Its closed record
has exactly:

```json
{
  "schema_version": "evidence_capture_window_boundary.v1",
  "window_marker_binding": {
    "path": "state/evidence-capture-windows.json",
    "size": 123,
    "sha256": "sha256:<64 lowercase hex>",
    "schema_version": "evidence_capture_windows.v1"
  },
  "window_marker_snapshot": {
    "schema_version": "evidence_capture_windows.v1",
    "windows": [
      {
        "window_id": "...",
        "task": "...",
        "opened_at": "...",
        "baseline_head": "<40 lowercase hex>",
        "evidence_paths": ["..."],
        "status": "open"
      }
    ]
  },
  "window": {
    "window_id": "...",
    "task": "...",
    "opened_at": "...",
    "baseline_head": "<40 lowercase hex>",
    "evidence_paths": ["..."],
    "status": "open"
  },
  "baseline_head": "<40 lowercase hex>",
  "intended_predecessor_head": "<40 lowercase hex>",
  "intended_predecessor_tree": "<40 lowercase hex>",
  "expected_commit_subject": "<one valid base commit subject>",
  "evidence_path_set_sha256": "sha256:<64 lowercase hex>",
  "normalized_boundary_sha256": "sha256:<64 lowercase hex>",
  "claims_not_made": [
    "This boundary record does not invoke or authorize a commit or mutate any worktree path, index entry, marker, or evidence artifact.",
    "This boundary record binds only the selected capture window and does not approve its implementation, evidence, reviews, or completion.",
    "This boundary record grants no workflow execution, deletion, owner-attestation, or predecessor-delta absorption authority."
  ]
}
```

`window_marker_snapshot` is the complete marker object and `window` equals its
exact selected row. The evidence-path
digest uses the same sorted UTF-8 path-plus-newline rule as the absorption
record. `normalized_boundary_sha256` is the SHA-256 of the canonical compact
JSON object excluding only that field. The persisted record is those canonical
bytes plus one LF. The claims array above is exact and ordered.

The builder rederives all fields except the caller-supplied window ID and commit
subject. The boundary authority is required even when there is no uncovered
predecessor delta. It lets postcommit validation and close prove which one of
several open rows the controlled boundary belongs to without making the ignored
marker itself durable.

For the active Task 3 attempt its deterministic path is:

`docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-commits/task-03/evidence-capture-window-boundary.json`

The following absorption authority is separate and conditional.

The new closed durable-authority schema is
`committed_predecessor_delta_absorption.v1`:

```json
{
  "schema_version": "committed_predecessor_delta_absorption.v1",
  "window_marker_binding": {
    "path": "state/evidence-capture-windows.json",
    "size": 123,
    "sha256": "sha256:<64 lowercase hex>",
    "schema_version": "evidence_capture_windows.v1"
  },
  "window_marker_snapshot": {
    "schema_version": "evidence_capture_windows.v1",
    "windows": [
      {
        "window_id": "...",
        "task": "...",
        "opened_at": "...",
        "baseline_head": "<40 lowercase hex>",
        "evidence_paths": ["..."],
        "status": "open"
      }
    ]
  },
  "window": {
    "window_id": "...",
    "task": "...",
    "opened_at": "...",
    "baseline_head": "<40 lowercase hex>",
    "evidence_paths": ["..."],
    "status": "open"
  },
  "lineage_projection": {},
  "absorbed_uncovered_occurrences": [
    {
      "commit": "<40 lowercase hex>",
      "path": "<repository-relative POSIX path>"
    }
  ],
  "absorbed_uncovered_paths": ["..."],
  "absorbed_uncovered_path_set_sha256": "sha256:<64 lowercase hex>",
  "disposition": "absorb_disjoint_uncovered_predecessor_delta",
  "normalized_absorption_sha256": "sha256:<64 lowercase hex>",
  "claims_not_made": [
    "This record does not authorize or mutate any commit, worktree path, index entry, or evidence artifact.",
    "This record does not claim semantic equivalence, correctness, review, or ownership of the absorbed predecessor paths.",
    "This record does not cover an occurrence that intersects the selected evidence scope or any uncommitted workspace drift."
  ]
}
```

The occurrence rows are necessary because an earlier accepted commit and a
later uncovered commit can change the same path. A path-only union cannot
distinguish those cases.

The record embeds the exact complete marker snapshot, the exact selected open
row from that snapshot, and the exact normalized lineage projection. The
marker binding's size and SHA-256 rederive from the canonical snapshot bytes
plus one trailing newline, exactly matching the live marker writer.
`absorbed_uncovered_occurrences` equals every untrailed `(commit, path)`
occurrence in that projection not already covered by a valid earlier
absorption authority. Rows follow first-parent commit order and then path order
within each commit; duplicate `(commit, path)` pairs are invalid.
`absorbed_uncovered_paths` is the sorted unique projection of those occurrence
paths. The path-set digest uses sorted UTF-8 paths, each followed by one
newline. `normalized_absorption_sha256` hashes the canonical object excluding
that field. The persisted record is those canonical compact JSON bytes plus one
LF. The three `claims_not_made` strings shown in the schema are exact and
ordered.

An absorption record is allowed only when the outstanding occurrence set is
nonempty. Supplying one for an empty set is stale/ambiguous authority and is
rejected.

For the active Task 3 attempt the one deterministic repository path is:

`docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-commits/task-03/committed-predecessor-delta-absorption.json`

The current lineage has outstanding uncovered occurrences, so this path has
exact cardinality one. This reviewed prospective contract is an additive
extension to the immutable Task 6 layout; the old plan bytes remain unchanged.
Task 3's fixed evidence manifest and subject validator must require both the
always-present boundary role/path/binding and this exact conditional
absorption role/path/binding. Its candidate manifest additionally admits the
generic controller implementation and owning-test paths named by the
implementation plan. Any alternate filename, second record of either kind,
or missing required record rejects the subject. A source/test path outside the
implementation plan's Authorized Paths rejects candidate construction and the
ordered specification review; the generic v2 validator does not infer a
plan-specific source allowlist. It instead requires the exact candidate binding
to project into the manifest and every projected path to be covered by the
selected window scope.

That requirement is represented by additive
`implementation_verification_subject.v2`, not by weakening the closed v1
shape. V2 retains every v1 field and adds exactly
`capture_window_authority_bindings`:

```json
{
  "boundary": {
    "path": ".../evidence-capture-window-boundary.json",
    "size": 123,
    "sha256": "sha256:<64 lowercase hex>",
    "schema_version": "evidence_capture_window_boundary.v1",
    "normalized_boundary_sha256": "sha256:<64 lowercase hex>"
  },
  "predecessor_delta_absorption": {
    "path": ".../committed-predecessor-delta-absorption.json",
    "size": 123,
    "sha256": "sha256:<64 lowercase hex>",
    "schema_version": "committed_predecessor_delta_absorption.v1",
    "normalized_absorption_sha256": "sha256:<64 lowercase hex>"
  }
}
```

The absorption value is exactly `null` when the rederived outstanding set is
empty and a complete binding when it is nonempty. The subject builder emits v1
byte-for-byte when no capture-window boundary input is supplied and emits v2
only from explicit boundary plus optional absorption paths. It does not infer
omitted capture intent from a live marker. V2 deep validation
always reopens the boundary and reopens the absorption only when its field is
non-null. It rederives their relationship to the same selected
window/baseline/predecessor, requires the boundary and any non-null absorption
binding in the candidate path manifest, requires exact null/non-null agreement
with the outstanding occurrence set, and requires every manifest row to be
covered by the selected window's scope. Review-subject validation accepts v1
or v2 for the generic
`implementation_candidate` kind while preserving every historical v1 byte and
verdict. V1 remains the pure no-boundary historical/compatibility path; review
publication may validate either schema and does not infer whether a caller
omitted a required boundary.

This additive generic discriminator supersedes the immutable Task 6 plan's
v1-only implementation-subject sentence for prospective capture-bearing Tasks
3–6 without editing that plan's bytes. The active Task 3 execution and every
later capture-bearing Task 4–6 execution must build a v2 subject.

## Persistent Coverage

A later controller boundary must not ask a new record to re-authorize an
already absorbed occurrence, and it must not lose coverage when the same path
is changed again.

For every valid retirement-controlled commit between the selected baseline and
the intended predecessor, the controller reconstructs the commit's
`precommit_control.v1` from durable history. It examines only absorption
authorities that were members of that reconstructed control's exact durable
authority set and validates them against:

- the exact marker snapshot and byte binding embedded in the authority;
- the selected window row embedded in the authority;
- the baseline and predecessor commits named by its lineage projection;
- the first-parent Git objects and raw commit messages;
- the exact outstanding untrailed occurrence set as of that predecessor; and
- the disjointness rule above.

Those occurrence rows form the cumulative covered set. An absorption authority
that is merely present in a tree, was not part of the control, is malformed, or
cannot be reconstructed contributes no coverage and causes validation to fail
closed when the current boundary depends on it.

A syntactically valid retirement trailer is not enough to classify its changed
occurrences as controlled. Its named control digest, transaction ID, parent,
tree, path set, durable-authority set, and complete reconstructed
`precommit_control.v1` must validate. A valid-looking trailer with forged,
missing, or unreconstructable coordinates fails the lineage operation; its
paths are never silently moved to either the controlled or absorbable
partition.

The current absorption authority, when required, covers exactly the remaining
outstanding occurrences. Missing, extra, duplicate, reordered, stale,
overlapping, or multiply matching current authorities are rejected.

## Controller Integration

`precommit_control.v1` remains byte- and schema-compatible. The new authority
records are members of its content-bound `durable_authority_bindings`; no
optional field is added to the control. Historical controls without a boundary
authority remain valid historical records but cannot close a prospective
window.

Before live workspace validation, the builder:

1. validates the selected workspace baseline and capture-window marker;
2. requires exactly one current boundary authority matching the selected open
   row, baseline, current predecessor, tree, scope, and commit subject;
3. derives the full predecessor lineage from `baseline.head` to current
   `HEAD`;
4. reconstructs earlier controlled boundaries and their accepted absorption
   occurrence coverage;
5. calculates the exact outstanding uncovered occurrence set;
6. requires no current absorption authority when it is empty;
7. otherwise requires exactly one explicitly selected current authority,
   rederives it, and rejects any scope intersection; and
8. passes the union of valid prior-control paths and all valid absorbed paths
   as `committed_paths` to the existing semantic-index reconstruction.

The last step explains the captured-index-to-current-HEAD difference; it does
not skip the existing byte, status, protected-path, allowed-addition, staged
delta, or index checks.

Before semantic-index reconstruction, the builder also requires every exact
`allowed_paths` entry to be covered by the selected boundary window's scope.
Postcommit validation and reconstruction repeat that check against the
committed allowed delta.

Precommit validation repeats the derivation from live bytes. Postcommit
validation repeats it against the controlled commit's parent, then applies the
existing controlled allowed-path delta. Fresh-clone reconstruction locates the
absorption authority only through the reconstructed durable-authority set and
reopens the authority blob from the controlled commit. It rederives the
embedded marker snapshot and binding without requiring the ignored live marker.
Live precommit and immediate postcommit modes additionally require the current
marker bytes to equal that snapshot. Local control-directory bytes are never
required.

The prospective builder accepts an explicit required `capture_window_boundary`
path and an optional `predecessor_delta_absorption` path. If outstanding
occurrences exist, absence of the latter fails. If none exist, its presence
fails. The CLI exposes the same explicit roles; it never scans arbitrary JSON
files for a convenient record.

Supplying `capture_window_boundary` puts `build_precommit_control` in explicit
capture mode. In that mode its durable-authority set must contain exactly one
`implementation_verification_subject.v2` plus its ordered approved
specification and quality reviews. Build and live precommit validation use the
existing full live review-pair validation, then deep-reopen the subject and
reviews and require the subject's boundary and nullable absorption bindings to
equal the explicitly supplied controller authorities.

Postcommit validation and fresh reconstruction use a distinct committed-blob
mode because the reviewed live index and dirty-worktree candidate no longer
exist. That mode reopens the exact subject and review blobs from the
reconstructed durable-authority set and validates their closed schemas,
content bindings, review identities, approved results, required
specification-before-quality order, subject pointers, and v2
boundary/absorption joins. It relies on the existing reconstructed
commit-parent, tree, allowed-delta, and control checks for candidate truth; it
does not run live candidate-state validation or depend on the current index,
worktree, ignored marker, or local control directory. Missing/multiple v2
subjects, v1-only authority, wrong or tampered committed reviews, or any join
mismatch rejects in the applicable live or committed-blob mode. Historical
calls without a boundary retain the old v1-compatible behavior. This execution
gate, rather than inference inside the pure v1 builder or review publisher,
prevents a capture-bearing commit from using v1.

## Mechanically Bound Closure

Changing an open row to `closed` is not a free status-edit API. The close
operation receives the selected window ID plus one exact closure mode:

- **controlled boundary:** current `HEAD`, the exact expected commit subject,
  and the reconstructed control coordinates; or
- **archived attempt:** the deterministic repository-local
  `evidence_capture_window_disposition.v1` record for the selected invalidated
  window.

For the controlled-boundary mode, the close command reconstructs the selected
commit without local control
bytes, recreates its control directory, runs the existing full postcommit
validator, requires `HEAD` and the expected subject/tree/path set to match, and
requires exactly one `evidence_capture_window_boundary.v1` member of that
control's durable-authority set to match the selected live row. It then
revalidates the still-open live marker. Only then may it publish the status-only
canonical marker update. A valid commit bound to another open row fails even
when both rows share a baseline and no absorption authority is required.

The archive mode is intentionally independent of the invalid attempt's commit
controller. A scope-intersecting predecessor cannot pass that controller, so
requiring the disposition itself to land in a controlled commit would be
circular.

`build_evidence_capture_window_disposition` writes this exact closed canonical
record:

```json
{
  "schema_version": "evidence_capture_window_disposition.v1",
  "window_marker_binding": {
    "path": "state/evidence-capture-windows.json",
    "size": 123,
    "sha256": "sha256:<64 lowercase hex>",
    "schema_version": "evidence_capture_windows.v1"
  },
  "window_marker_snapshot": {
    "schema_version": "evidence_capture_windows.v1",
    "windows": [
      {
        "window_id": "...",
        "task": "...",
        "opened_at": "...",
        "baseline_head": "<40 lowercase hex>",
        "evidence_paths": ["..."],
        "status": "open"
      }
    ]
  },
  "window": {
    "window_id": "...",
    "task": "...",
    "opened_at": "...",
    "baseline_head": "<40 lowercase hex>",
    "evidence_paths": ["..."],
    "status": "open"
  },
  "lineage_projection": {},
  "intersecting_uncovered_occurrences": [
    {
      "commit": "<40 lowercase hex>",
      "path": "<repository-relative POSIX path>"
    }
  ],
  "intersecting_uncovered_paths": ["..."],
  "intersecting_uncovered_path_set_sha256": "sha256:<64 lowercase hex>",
  "disposition": "archive_capture_attempt",
  "reason": "<nonempty operator-supplied reason>",
  "archived_at": "<timezone-aware RFC 3339 timestamp>",
  "normalized_disposition_sha256": "sha256:<64 lowercase hex>",
  "claims_not_made": [
    "This disposition does not invoke or authorize a commit or mutate any worktree path, index entry, or evidence artifact.",
    "This disposition grants no occurrence coverage, replacement baseline, retry, or successor-window authority.",
    "This disposition does not attest owner approval, workflow execution, deletion eligibility, or roadmap completion."
  ]
}
```

The complete marker snapshot/selected-row rules match the boundary schema.
Intersection rows are ordered by first-parent commit then path and are unique;
the path projection is sorted unique and uses the path-plus-newline digest.
`normalized_disposition_sha256` is the SHA-256 of the canonical compact JSON
object excluding only that field. The persisted record is those canonical
bytes plus one LF, and the claims array above is exact and ordered.

The record is written at
`state/evidence-capture-window-dispositions/<window-id-sha256>/<record-sha256>.json`.
The directory component is the lowercase hexadecimal SHA-256 of the UTF-8
window ID with no prefix or terminator. The filename component is the lowercase
hexadecimal `normalized_disposition_sha256` with its `sha256:` prefix removed.
The ignored repository-local record embeds and binds the same complete open marker
snapshot and selected row, the exact current predecessor lineage, the exact
scope-intersecting occurrence rows, disposition `archive_capture_attempt`, a
nonempty reason, timezone-aware `archived_at`, a canonical digest, and fixed
claims that it grants no commit, mutation, occurrence coverage, replacement
baseline, retry, workflow, deletion, or owner authority. It is publish-once and
content-addressed by the selected ID; a changed marker, HEAD, lineage,
intersection set, or existing different byte stream rejects.

Archive-mode close rederives that complete record from live Git and marker
bytes, requires at least one scope intersection, and only then closes the
selected row. The disposition remains machine-visible local archival state; it
does not make the intersecting occurrence acceptable to this or a successor
window. A successor requires a separately reviewed recovery that establishes a
new valid baseline or other explicit coverage. If the governing roadmap
forbids that transition, execution remains stopped. Unknown, missing, changed,
noncanonical, nonregular, symlinked, wrong-window, or nonintersecting
dispositions reject.

Disposition files are immutable generations, not a single occupied slot. If
HEAD or the marker changes between build and close, the stale generation
remains as history and close rejects it. A new build derives a different
content digest/path from the new lineage and may then close successfully.
Callers select one explicit disposition path; there is no "latest" inference.

The one provisional row created before this design existed is a bootstrap
exception, not a production close. Its scope omission was found before Task 3
evidence generation. The exact
`evidence_capture_window_bootstrap_disposition.v1` record at
`docs/plans/evidence/yaml-retirement/evidence-capture-window-benign-delta-absorption-design/provisional-window-disposition.json`
archives it and names its complete replacement. The reviewed design commit
content-binds that record. No later close accepts the bootstrap schema.

## Failure Semantics

The attempt restarts or is dispositioned when any of these is true:

- an outstanding uncovered occurrence intersects the selected scope;
- the baseline is not an ancestor of the predecessor;
- the lineage contains a merge or malformed control trailer;
- the marker is absent, unreadable, nonregular, changed, malformed, closed, or
  selects no unique row;
- a previous coverage authority cannot be reconstructed exactly;
- a valid-looking control trailer cannot reconstruct and validate exactly;
- current coverage is missing, extra, duplicated, stale, or ambiguous;
- the authority, marker, projection, occurrence set, path set, digest, or
  predecessor tree does not rederive byte-for-byte;
- a protected, dirty, staged, or uncommitted path fails an existing check; or
- a scope row or changed path cannot be normalized.

These are typed controller failures. None falls back to silent restart,
best-effort path matching, or a broader absorption.

## Public Surface

The generic production surface adds:

- `validate_evidence_capture_windows`;
- `open_evidence_capture_window`;
- `close_evidence_capture_window`;
- `build_evidence_capture_window_boundary`;
- `build_committed_predecessor_delta_absorption`;
- `build_evidence_capture_window_disposition`;
- corresponding `source_bindings` CLI commands; and
- the required prospective boundary input and optional explicit absorption
  input to `build_precommit_control`; and
- additive `implementation_verification_subject.v2` construction and
  validation for capture-bearing implementation reviews.

Only builders, explicit marker lifecycle operations, and issue-returning
validators are public. Internal persistent coverage reconstruction remains
private so callers cannot supply a claimed covered occurrence set.

## Verification

Tests must prove both directions:

- valid marker open/close lifecycle and concurrent-publish rejection;
- premature close, a boundary other than current `HEAD`, failed postcommit
  validation, or a missing/changed/nonintersecting/wrong-window disposition
  each rejects;
- with two open rows sharing a baseline and zero uncovered occurrences, the
  always-present boundary closes only its exact selected row;
- a scope-intersecting lineage can publish its exact local disposition and
  close the invalid window without treating the intersection as absorbed or
  authorizing a successor baseline;
- a commit racing between disposition build and close rejects the stale
  generation, permits a new content-addressed generation, and then closes only
  against that fresh record;
- valid disjoint uncovered commit absorption;
- an exact scope path, a descendant, and an ancestor each reject;
- an absent record with outstanding occurrences rejects;
- a record with no outstanding occurrences rejects;
- missing, extra, duplicate, or reordered occurrence rows reject;
- wrong marker bytes, window ID/status, baseline, predecessor, tree, commit,
  path, set digest, or normalized digest rejects;
- a second untrailed edit to a previously absorbed path still requires fresh
  coverage;
- valid coverage from a prior reconstructed control persists;
- a syntactically valid trailer with forged or unreconstructable coordinates
  rejects before controlled/absorbed partitioning;
- controlled-only predecessor paths retain existing behavior;
- controlled and absorbed occurrence partitions reconcile exactly;
- deletions and file/gitlink transitions reconstruct correctly;
- precommit, postcommit, and fresh-clone reconstruction all agree; and
- v1 implementation subjects remain byte-compatible while v2 requires exact
  boundary/conditional-absorption bindings in both its explicit field and
  candidate manifest;
- completed Task 2 controls and fixtures remain valid without regeneration or
  reinterpretation.

Focused source-binding tests run before the broad repository suite. No test or
production branch contains a workflow-family, queue, repository, batch, owner,
or pilot name.

## Rollout

1. Preserve the incomplete provisional row as closed, bind its bootstrap
   disposition, and keep its complete replacement row live for the active Task
   3 attempt.
2. Review and land this design and its implementation plan using the conscious
   hook override; those planning commits are prospective and disjoint from the
   active window's declared scope.
3. Implement and independently review the generic controller extension before
   generating the next capture-bearing evidence.
4. Materialize the current attempt's exact absorption authority from the live
   marker and current predecessor lineage, and materialize its always-present
   window-boundary authority.
5. Include the boundary and absorption authorities, but not the ignored marker,
   in the controlled Task 3 boundary; validate postcommit and reconstruct, then
   close the live marker.
6. For every later capture-bearing attempt, freshly validate the reusable
   workspace baseline, append a distinct open row, and repeat the lifecycle.

No completed Task 2 record, baseline, disposition, review, or commit is changed.
