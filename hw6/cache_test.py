"""Problem 4: run all 12 practice documents with and without prompt caching.

Writes every model call (setup, document, every token count the API reports,
dollar cost from prices.json) to output/cache_test.json and prints a summary.

    python cache_test.py
"""
import json
from pathlib import Path

import agent
from tools import OUTPUT_DIR, now

DOCS = sorted((agent.PROJECT_DIR / "data" / "practice_docs").iterdir())
KEY = {row["file"]: row for row in json.loads((agent.PROJECT_DIR / "data" / "practice_key.json").read_text())}
OUT = OUTPUT_DIR / "cache_test.json"
FIELDS = ("vendor", "sku", "unit_price", "lead_time_days", "min_order", "decision")

# Without cache first, so its numbers can't benefit from anything the cached setup left behind.
SETUPS = [("without_cache", False), ("with_cache", True)]


def main() -> None:
    calls, docs = [], []
    for setup, cache in SETUPS:
        for path in DOCS:
            rel = path.relative_to(agent.PROJECT_DIR).as_posix()
            result = agent.run(rel, cache=cache, defenses=frozenset())
            out = result.output.model_dump()
            key = KEY[path.name]
            wrong = [f for f in FIELDS if out[f] != key[f]]
            per_call = agent.model_calls_from(result)
            for c in per_call:
                calls.append({"setup": setup, "document": path.name, **c})
            docs.append({
                "setup": setup,
                "document": path.name,
                "time": now(),
                "requests": len(per_call),
                "input_tokens": sum(c["input_tokens"] for c in per_call),
                "cache_read_tokens": sum(c["cache_read_tokens"] for c in per_call),
                "cache_write_tokens": sum(c["cache_write_tokens"] for c in per_call),
                "output_tokens": sum(c["output_tokens"] for c in per_call),
                "cost_usd": round(sum(c["cost_usd"]["total"] for c in per_call), 8),
                "decision": out["decision"],
                "matches_key": not wrong,
                "mismatched_fields": wrong,
            })
            d = docs[-1]
            print(f"{setup:14} {path.name:30} in={d['input_tokens']:>6} cached={d['cache_read_tokens']:>6} "
                  f"out={d['output_tokens']:>4} ${d['cost_usd']:.6f} {'OK' if not wrong else 'MISMATCH ' + str(wrong)}")

    summary = {}
    for setup, _ in SETUPS:
        rows = [d for d in docs if d["setup"] == setup]
        summary[setup] = {
            "documents": len(rows),
            "model_calls": sum(d["requests"] for d in rows),
            "input_tokens": sum(d["input_tokens"] for d in rows),
            "cache_read_tokens": sum(d["cache_read_tokens"] for d in rows),
            "cache_write_tokens": sum(d["cache_write_tokens"] for d in rows),
            "output_tokens": sum(d["output_tokens"] for d in rows),
            "total_cost_usd": round(sum(d["cost_usd"] for d in rows), 8),
            "cost_per_document_usd": round(sum(d["cost_usd"] for d in rows) / len(rows), 8),
            "matches_key": sum(d["matches_key"] for d in rows),
        }
    a, b = summary["without_cache"]["total_cost_usd"], summary["with_cache"]["total_cost_usd"]
    summary["percent_saved"] = round((a - b) / a * 100, 2)

    OUT.write_text(json.dumps({"summary": summary, "documents": docs, "calls": calls}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
