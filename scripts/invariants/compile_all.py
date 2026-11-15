"""compile_all.py TREE OUT.json [JOBS]: compile every .orc under TREE through the command line and record, per
file, the exit code and the output (OUT.json). A file that built has its program digest in its output.

TREE is an export of a revision (`git archive`), so every .orc under it is tracked, and its `orchestrator` package
is the compiler (TREE stands first on `PYTHONPATH`; the caller's `PYTHONPATH` follows). Each compile runs in a
scratch directory of its own under the temporary directory, because a compile writes `.orchestrate/build/` where
it runs: never point this at a working tree to compile in place. TREE and the scratch directory are replaced in
the recorded output, so two exports of one revision give byte-identical files.

A source that mentions `providers.<x>` (dotted names included) is compiled with a generated provider externs file
binding each such name to `claude_unrestricted_workspace`, and one that mentions `prompts.<x>` with a generated
prompt externs file binding each to a scratch `input_file`, so a program with a provider call reaches typecheck
instead of stopping at `provider_result_provider_invalid` or `provider_result_prompt_invalid`. Prints the files,
the builds, and how many of the builds name a provider.
"""
import concurrent.futures, json, os, pathlib, re, subprocess, sys, tempfile
tree = pathlib.Path(sys.argv[1]).resolve(); out = sys.argv[2]; jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 8
files = sorted(str(p.relative_to(tree)) for p in tree.rglob("*.orc"))
env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(tree), os.environ.get("PYTHONPATH")]))}
def one(rel):
    text = (tree / rel).read_text(errors="replace")
    names = sorted(set(re.findall(r"providers(?:\.[A-Za-z0-9_\-]+)+", text)))
    prompts = sorted(set(re.findall(r"prompts(?:\.[A-Za-z0-9_\-]+)+", text)))
    with tempfile.TemporaryDirectory() as cwd:
        flags = []
        if names:
            pathlib.Path(cwd, "providers.generated.json").write_text(json.dumps({n: "claude_unrestricted_workspace" for n in names}))
            flags += ["--provider-externs-file", "providers.generated.json"]
        if prompts:
            pathlib.Path(cwd, "prompt.md").write_text("Answer.")
            pathlib.Path(cwd, "prompts.generated.json").write_text(json.dumps({n: {"input_file": "prompt.md"} for n in prompts}))
            flags += ["--prompt-externs-file", "prompts.generated.json"]
        r = subprocess.run([sys.executable, "-m", "orchestrator", "compile", str(tree / rel), *flags], cwd=cwd, env=env, capture_output=True, text=True)
        fix = lambda s: s.replace(str(tree), "<TREE>").replace(os.path.realpath(cwd), "<CWD>").replace(cwd, "<CWD>")
        return rel, {"exit": r.returncode, "stdout": fix(r.stdout), "stderr": fix(r.stderr)}, bool(names)
with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
    results = list(pool.map(one, files))
json.dump({rel: row for rel, row, _ in results}, open(out, "w"), indent=0, sort_keys=True)
built = [named for _, row, named in results if row["exit"] == 0]
print(len(results), "files;", len(built), "built,", sum(built), "of them name a provider")
