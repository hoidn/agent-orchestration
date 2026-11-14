"""compile_all.py TREE OUT.json [JOBS]: compile every .orc under TREE through the command line and record, per
file, the exit code and the output (OUT.json). A file that built has its program digest in its output.

TREE is an export of a revision (`git archive`), so every .orc under it is tracked, and its `orchestrator` package
is the compiler (TREE stands first on `PYTHONPATH`; the caller's `PYTHONPATH` follows). Each compile runs in a
scratch directory of its own under the temporary directory, because a compile writes `.orchestrate/build/` where
it runs: never point this at a working tree to compile in place. TREE and the scratch directory are replaced in
the recorded output, so two exports of one revision give byte-identical files. Prints the files and the builds.
"""
import concurrent.futures, json, os, pathlib, subprocess, sys, tempfile
tree = pathlib.Path(sys.argv[1]).resolve(); out = sys.argv[2]; jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 8
files = sorted(str(p.relative_to(tree)) for p in tree.rglob("*.orc"))
env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(tree), os.environ.get("PYTHONPATH")]))}
def one(rel):
    with tempfile.TemporaryDirectory() as cwd:
        r = subprocess.run([sys.executable, "-m", "orchestrator", "compile", str(tree / rel)], cwd=cwd, env=env, capture_output=True, text=True)
        fix = lambda s: s.replace(str(tree), "<TREE>").replace(os.path.realpath(cwd), "<CWD>").replace(cwd, "<CWD>")
        return rel, {"exit": r.returncode, "stdout": fix(r.stdout), "stderr": fix(r.stderr)}
with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
    rows = dict(pool.map(one, files))
json.dump(rows, open(out, "w"), indent=0, sort_keys=True)
print(len(rows), "files;", sum(row["exit"] == 0 for row in rows.values()), "built")
