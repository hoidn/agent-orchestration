# Historical native prompt test witnesses

Scaffold files, manifests, output contracts, linked-session documents and the
original primary journals are frozen bytes captured from fake-provider tests
in the retirement evidence `full-tmp` tree. These are synthetic test witnesses;
they do not establish recovery of real historical sessions.

`tests/test_prompt_session.py::_historical_run` copies scaffold/journal bytes
and changes only explicit workspace, launch paths, cwd and no-tools conf inode
fields for the new temporary directory. Planted advisor/child artifacts update
the observed inventory and live/snapshot manifests through retained codecs.
Public scaffold files use 0644; private captured files use 0400. Fixture setup
never generates, compiles or executes the historical workflow source.

Exact capture source paths and SHA-256 digests are recorded outside the repo in
`native-history-capture-provenance.json` and `native-history-fixture-digests.json`
of the sibling `orc-consolidation-evidence-20261012` evidence directory.
