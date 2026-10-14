"""A workflow command run with the image executable pin: edits the clone, writes a result."""
import json, os, sys, hashlib
attempt = sys.argv[1]
with open("hello.txt", "a") as handle:
    handle.write("edited by confined command\n")
os.makedirs(f"/result/{attempt}", exist_ok=True)
value = {"interpreter": sys.executable, "cwd": os.getcwd(),
         "hello_sha256": hashlib.sha256(open("hello.txt", "rb").read()).hexdigest()}
json.dump(value, open(f"/result/{attempt}/result.json", "w"))
print(json.dumps(value))
