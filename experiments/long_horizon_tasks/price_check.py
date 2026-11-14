"""Price recorded sessions request by request under candidate long-prompt rules and compare with the CLI's own total.

A request is one assistant message id in the session file (its usage repeats once per content block); its
prompt is input + cache read + cache write tokens. Rates are the frozen table's base rates for the model
(USD per million: input 0.10, output 0.50, cache read 0.01); a rule names the cache-write rate, the
threshold above which the long-prompt multiplier applies, and the multiplier.

Usage: python -I price_check.py <trial dir>...   (each holding agent/claude-code.txt and agent/sessions/)
"""

import glob
import json
import sys

BASE = {"input": 0.10, "output": 0.50, "cache_read": 0.01}
RULES = {  # name: (cache write per million, threshold on the prompt, multiplier on every rate above it)
    "table as frozen (write 0.20, 5x above 100k)": (0.20, 100_000, 5),
    "5-minute write 0.125, 5x above 100k": (0.125, 100_000, 5),
    "5-minute write 0.125, 5x above 200k": (0.125, 200_000, 5),
    "write 0.20, no long-prompt rate": (0.20, float("inf"), 1),
}


def requests(trial):
    usage = {}
    for path in glob.glob(f"{trial}/agent/sessions/projects/*/*.jsonl"):
        for line in open(path):
            event = json.loads(line)
            message = event.get("message")
            if event.get("type") == "assistant" and isinstance(message, dict) and message.get("usage") \
                    and message.get("model") != "<synthetic>":
                usage[message["id"]] = message["usage"]
    return list(usage.values())


def price(usage, write, threshold, multiplier):
    read, created = usage.get("cache_read_input_tokens", 0), usage.get("cache_creation_input_tokens", 0)
    factor = multiplier if usage["input_tokens"] + read + created > threshold else 1
    return factor * (usage["input_tokens"] * BASE["input"] + usage["output_tokens"] * BASE["output"]
                     + read * BASE["cache_read"] + created * write) / 1e6


def cli_total(trial):
    results = [json.loads(line) for line in open(f"{trial}/agent/claude-code.txt") if '"type":"result"' in line]
    return results[-1]["total_cost_usd"]


def main(trials):
    for trial in trials:
        rows = requests(trial)
        print(trial, f"requests={len(rows)}", f"cli={cli_total(trial):.9f}")
        for name, rule in RULES.items():
            print(f"  {sum(price(u, *rule) for u in rows):.9f}  {name}")


if __name__ == "__main__":
    main(sys.argv[1:])
