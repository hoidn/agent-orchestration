# OMP Pin Upgrade Runbook

Status: operator setup and upgrade procedure for the code-owned OMP-I1
executable pin. For ordinary profile launches, use [Run prerequisites](#run-prerequisites);
building and installing a new pin is a separate operation.

This runbook changes one coupled release unit: the Orchestrator code, the
`OmpBinaryPin`, the audited OMP source overlay, the packaged conf presets, and
the installed `~/.local/bin/omp`. Never update only the version or final digest.

## Current authority

The machine-readable authority is `orchestrator/providers/omp_pin.py`.
The current pin is:

- OMP tag `v17.3.4`, commit
  `ffd53ff92a6f575d499730475a73460dd7cc2eea`;
- Linux `x86_64`, AVX2, Landlock ABI 3 or newer;
- pinned Bun, Bazelisk/Bazel, Rust, C/C++ and linker identities recorded in
  `OMP_BINARY_PIN`;
- audited source overlay
  `orchestrator/providers/omp_source_overlay.patch`;
- final executable SHA-256
  `df4c4d98b8a28c51651de79bc925449b6dcc3c57d2653b17aba7e5755f76dddb`.

The design rationale and complete reproducible-build evidence are in
`docs/plans/2026-08-14-omp-integration-design-and-roadmap.md`. The executable
recipe is Task 1 of
`docs/plans/2026-08-21-omp-i1-implementation-plan.md`.

## Inspect the installed pin

Run from the Orchestrator repository root:

```sh
python -c 'from orchestrator.providers.omp_pin import OMP_BINARY_PIN, canonical_pin_json; print(canonical_pin_json(OMP_BINARY_PIN))'
command -v omp
omp --version
sha256sum "$(command -v omp)"
stat -c '%U %a %n' "$(command -v omp)"
```

Acceptance:

- `command -v omp` is exactly `$HOME/.local/bin/omp`;
- version is exactly `omp/17.3.4`;
- SHA-256 equals `OMP_BINARY_PIN.executable_sha256`;
- the path is a current-user- or root-owned regular non-symlink with mode
  `0555` and no group/other write bit.

The launcher repeats platform, AVX2, version, ownership, mode, and whole-file
digest checks before every run. An operator shell alias or alternate binary on
`PATH` is not an override.

## Run prerequisites

First [inspect the installed pin](#inspect-the-installed-pin); ordinary use
does not require rebuilding it. The profile-isolated lanes `omp_no_tools`,
`omp_conf`, and internal `omp_conf_inference` require nonempty caller roots.
In the terminal that will launch the orchestrator, preserve existing values
or supply the conventional defaults:

```sh
: "${HOME:?HOME must name your existing home directory}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export TMPDIR="${TMPDIR:-/tmp}"
mkdir -p "$XDG_DATA_HOME" "$XDG_STATE_HOME" "$XDG_CACHE_HOME" "$TMPDIR"
```

Keep the inspected `omp` on `PATH`. These are caller settings; the launcher
creates separate child HOME/XDG/temp roots for each attempt.

Start the credential broker in a separate private terminal, using your
configured credential home:

```sh
omp auth-broker serve --bind 127.0.0.1:47653
```

In the orchestrator terminal using the same credential home:

```sh
export OMP_AUTH_BROKER_URL=http://127.0.0.1:47653
export OMP_AUTH_BROKER_TOKEN="$(omp auth-broker token)"
```

The profile adapter requires this URL/token pair and does not start the
broker. The URL must be HTTP with loopback IP `127.0.0.1` or `[::1]` and an
explicit port; `localhost` is refused. Never print or paste the token. For
`omp_conf`, also supply the admitted repository conf root through the provider
binding. See [provider contracts](../specs/providers.md) for lane boundaries.

## Build a candidate

1. Freeze the proposed OMP source commit and tag. Record the source lockfiles,
   build launchers, resolved Bazel binary, selected toolchain labels and actual
   compiler/linker executable digests before accepting output.
2. Rebase and audit `orchestrator/providers/omp_source_overlay.patch`. Reject
   any unrelated source delta. Update its recorded digest only after review.
3. Use the exact canonical build root recorded by the candidate pin. For the
   current build host that is `/home/ollie/.cache/omp-i1/canonical`.
4. Build twice, sequentially. Before each build, delete and recreate the entire
   canonical checkout plus its HOME, XDG cache/config/data/state, and temp
   roots. Clone with `git clone --no-local`, detach at the proposed commit, and
   verify the declared lock hashes before applying the overlay.
5. Start the build from an empty environment. Admit only the positive names in
   `OmpBinaryPin.environment_variables`; use exact pinned tool paths. Proxy,
   registry, preload, dynamic-loader, compiler/linker, Cargo/Rust, Bazelisk,
   Bun compile, `OMP_NATIVE_BUILD_BACKEND`, `OMP_BAZEL_RC`, and `CROSS_TARGET`
   overrides must be absent.
6. For the current recipe, run only:

   ```sh
   git apply --check "$ORCHESTRATOR_ROOT/orchestrator/providers/omp_source_overlay.patch"
   git apply "$ORCHESTRATOR_ROOT/orchestrator/providers/omp_source_overlay.patch"
   bun install --frozen-lockfile
   bun run build:native -- -- -- --jobs=1 --spawn_strategy=local
   bun -e 'import { lstatSync, utimesSync } from "node:fs"; const p="packages/natives/native/pi_natives.linux-x64-modern.node"; const b=Buffer.from(await Bun.file(p).arrayBuffer()); if (b.includes(Buffer.from("processwrapper-sandbox/"))) throw new Error("sandbox path retained"); const s=lstatSync(p); if (!s.isFile() || s.isSymbolicLink()) throw new Error("native addon is not a regular file"); utimesSync(p, 0, 0); if (lstatSync(p,{bigint:true}).mtimeNs !== 0n) throw new Error("mtime normalization failed")'
   bun --cwd=packages/coding-agent run build
   ```

7. Capture the configured Bazel action closure through the exact pinned
   Bazelisk launcher. Verify the selected Rust/C/C++/link toolchain labels and
   executable digests. Re-hash every declared source/build input after the
   build; only the predeclared effective `MODULE.bazel.lock` rewrite is legal.
8. Preserve each `packages/coding-agent/dist/omp` outside the canonical root
   before wiping for the next build. Require both files to be regular,
   byte-identical, the same size, and to report the proposed version. Compare
   their embedded native addons byte-for-byte and require normalized mtime 0.

Stop on any mismatch. Do not normalize the final executable, bless one build,
or add a digest exception.

## Admit and install the candidate

Before installation:

1. Update all fields of `OMP_BINARY_PIN`, not just `version` and
   `executable_sha256`.
2. Update the design's source/build evidence and this runbook's current-pin
   block.
3. Update raw transport fixtures only when an audited protocol change requires
   it; never rewrite them merely to make a parser test pass.
4. Run the pin, transport, conf, launch, observation, scaffold, session,
   import, and resume selectors. Then run the real OMP-I1 gates below.

Retain the previous admitted executable under a digest-qualified operator path.
Install the new file by same-filesystem temporary name and atomic rename:

```sh
candidate=/absolute/path/to/verified/dist/omp
dest="$HOME/.local/bin/omp"
mkdir -p "$(dirname "$dest")"
tmp="$(mktemp "$(dirname "$dest")/.omp-install.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
install -m 0555 "$candidate" "$tmp"
test "$(sha256sum "$tmp" | cut -d' ' -f1)" = "$(python -c 'from orchestrator.providers.omp_pin import OMP_BINARY_PIN; print(OMP_BINARY_PIN.executable_sha256)')"
mv -T "$tmp" "$dest"
trap - EXIT
```

Immediately repeat the inspection commands. If `PATH`, version, digest,
ownership, or mode differs, restore the previous matching Orchestrator/binary
pair before running workflows.

## Verification

Narrow deterministic checks:

```sh
pytest --collect-only -q tests/test_omp_integration.py
pytest -q \
  tests/test_provider_omp_pin.py \
  tests/test_provider_omp_transport.py \
  tests/test_provider_omp_conf.py \
  tests/test_provider_omp_launch.py \
  tests/test_provider_omp_observation.py \
  tests/test_omp_package_assets.py \
  tests/test_prompt_scaffold.py \
  tests/test_prompt_session.py \
  tests/test_prompt_resume.py \
  tests/test_cli_prompt.py \
  tests/test_cli_prompt_import.py
```

Real acceptance requires the [run prerequisites](#run-prerequisites), including
a live loopback broker and real credential home. In the prepared terminal:

```sh
export OMP_E2E_AUTH_HOME="$HOME"
pytest -q -n 2 --dist=worksteal tests/test_omp_integration.py
```

Never paste, print, or persist the token. Exact advisor or hub observation may
fail closed on a transient provider failure. The OMP-I1 gate permits one fresh
rerun of only that failed case; a second failure blocks the upgrade. Do not
weaken the topology predicate.

`omp_conf` cannot enforce this instruction against model-facing tools. Treat
its provider output, live journals, snapshots, and run root as sensitive
credential-bearing surfaces.

After narrow and real gates, run the full repository suite:

```sh
pytest -q -n 16 --dist=worksteal
```

## Rollback

A rollback moves the Orchestrator code and installed OMP executable together:

1. stop new workflow launches;
2. restore the previous reviewed Orchestrator revision;
3. atomically restore the executable whose digest matches that revision's
   `OMP_BINARY_PIN`;
4. repeat the inspection commands and narrow pin/launch tests;
5. use `orchestrator resume <run_id>` only when that restored revision accepts
   the run's existing workflow checksum and state. Never force a session link,
   continuation chain, scaffold, or run state across pin drift.

Existing structured workflow results remain authority. OMP journals, launch
frames, snapshots, and continuations are evidence; they are not migration
inputs and must not be edited to manufacture compatibility.
