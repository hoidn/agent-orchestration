"""Price recorded sessions request by request under the kit's price rule (`price_rule.json`) and compare
with the CLI's own total; the variant rows show which part of the rule each archive needs.

A request is one assistant message id in the session file (its usage repeats once per content block). Its
prompt is input + cache read + cache write tokens; above the rule's threshold every rate is multiplied.
Each cache write is priced at its lifetime's rate (`usage.cache_creation`'s five-minute and one-hour split).

Usage: python -I price_check.py <trial dir>...   (each holding agent/claude-code.txt and agent/sessions/)
"""

import glob
import json
import sys
from pathlib import Path

RULE = Path(__file__).with_name("price_rule.json")


def load_rule(path=RULE):
    return json.loads(Path(path).read_text())


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


def _writes(usage):
    """(five-minute, one-hour) write tokens; written tokens the split does not name count as one-hour."""
    created = usage.get("cache_creation_input_tokens", 0)
    split = usage.get("cache_creation") or {}
    five, hour = split.get("ephemeral_5m_input_tokens", 0), split.get("ephemeral_1h_input_tokens", 0)
    return five, hour + max(created - five - hour, 0)


def price(usage, rule):
    rates, long_prompt = rule["per_million_usd"], rule["long_prompt"]
    read = usage.get("cache_read_input_tokens", 0)
    five, hour = _writes(usage)
    prompt = usage["input_tokens"] + read + usage.get("cache_creation_input_tokens", 0)
    factor = long_prompt["multiplier"] if prompt > long_prompt["above_prompt_tokens"] else 1
    return factor * (usage["input_tokens"] * rates["input"] + usage["output_tokens"] * rates["output"]
                     + read * rates["cache_read"] + five * rates["cache_write_5m"]
                     + hour * rates["cache_write_1h"]) / 1e6


def _variant(rule, write=None, above=None, multiplier=None):
    rates = {**rule["per_million_usd"], **({"cache_write_5m": write, "cache_write_1h": write} if write else {})}
    long_prompt = {**rule["long_prompt"], **({"above_prompt_tokens": above} if above else {}),
                   **({"multiplier": multiplier} if multiplier else {})}
    return {**rule, "per_million_usd": rates, "long_prompt": long_prompt}


def variants(rule):
    return {"rule (price_rule.json)": rule,
            "every write at 0.20 (the package table's cache_write, read per request)": _variant(rule, write=0.20),
            "rule with the threshold at 200k": _variant(rule, above=200_000),
            "rule without a long-prompt rate": _variant(rule, multiplier=1)}


def cli_total(trial):
    results = [json.loads(line) for line in open(f"{trial}/agent/claude-code.txt") if '"type":"result"' in line]
    return results[-1]["total_cost_usd"]


def main(trials):
    rule = load_rule()
    for trial in trials:
        rows = requests(trial)
        print(trial, f"requests={len(rows)}", f"cli={cli_total(trial):.9f}")
        for name, variant in variants(rule).items():
            print(f"  {sum(price(u, variant) for u in rows):.9f}  {name}")


if __name__ == "__main__":
    main(sys.argv[1:])
