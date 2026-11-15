"""program_digests.py BASETEMP OUT.json: the run-reference program digests. For every `closed_program.json` a serial
run of the run-reference test modules left under BASETEMP (`inv.sh` with `RUNREF=DIR`), the SHA-256 of the program
with `compiler_runtime_identity_digest` (a hash of every package file), its `expected_` form and
`resolved_commit_sha` (a commit the test itself makes) removed, also inside a base64-encoded run-reference
`config`, so two package versions can be compared. A program that holds none of them has no run reference and is
left to the other two invariants. Output: {pytest folder of a test: sorted distinct digests}; prints the program
files, the test folders and the distinct programs. Use one BASETEMP path for both revisions compared and a serial
run: worker folders change the embedded paths.
"""
import base64, hashlib, json, pathlib, sys
FIELD = "compiler_runtime_identity_digest"
DROP = {FIELD, "expected_" + FIELD, "resolved_commit_sha"}
def decoded(text):
    try:
        value = json.loads(base64.b64decode(text, validate=True))
    except ValueError:  # a `config` that is not an encoded run reference stays as it is
        return None
    return value if isinstance(value, (dict, list)) else None
def strip(value):
    if isinstance(value, list):
        return [strip(v) for v in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for k, v in value.items():
        inner = decoded(v) if k == "config" and isinstance(v, str) else None
        if k not in DROP:
            out[k] = {"__decoded_config__": strip(inner)} if inner is not None else strip(v)
    return out
base = pathlib.Path(sys.argv[1]); rows = {}; files = 0
for path in sorted(base.rglob("closed_program.json")):
    try:
        tree = json.loads(path.read_text())
    except ValueError:  # some tests corrupt the file on purpose
        continue
    stripped = strip(tree)
    if stripped == tree:
        continue
    digest = hashlib.sha256(json.dumps(stripped, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    files += 1
    rows.setdefault(path.relative_to(base).parts[0], set()).add(digest)
json.dump({k: sorted(v) for k, v in rows.items()}, open(sys.argv[2], "w"), indent=0, sort_keys=True)
print(files, "program files with a run reference;", len(rows), "test folders;", len(set().union(*rows.values())), "distinct programs")
