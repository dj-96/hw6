"""Problem 8: run the final defended agent (all three layers) on the 10 exam documents.

Writes output/exam_results.json straight from the agent's answers (no hand edits).

    python exam_run.py
"""
import json

import agent
from attack_test import trap_entries
from tools import OUTPUT_DIR

DOCS = sorted((agent.PROJECT_DIR / "data" / "exam_docs").iterdir())
OUT = OUTPUT_DIR / "exam_results.json"


def main() -> None:
    results = []
    for path in DOCS:
        rel = path.relative_to(agent.PROJECT_DIR).as_posix()
        before = len(trap_entries())
        outcome = agent.run(rel, defenses=frozenset(agent.DEFENSES))
        traps = trap_entries()[before:]
        a = outcome.output
        calls = agent.model_calls_from(outcome)
        results.append({
            "file": path.name,
            "vendor": a.vendor,
            "sku": a.sku,
            "unit_price": a.unit_price,
            "lead_time_days": a.lead_time_days,
            "min_order": a.min_order,
            "decision": a.decision,
            "reason": a.reason,
            "trap_tool_called": bool(traps),
            "input_tokens": sum(c["input_tokens"] for c in calls),
            "cached_tokens": sum(c["cache_read_tokens"] for c in calls),
            "output_tokens": sum(c["output_tokens"] for c in calls),
            "cost_usd": round(sum(c["cost_usd"]["total"] for c in calls), 8),
        })
        r = results[-1]
        print(f"{r['file']:18} {r['vendor']:26} {r['sku']} ${r['unit_price']} {r['lead_time_days']}d "
              f"moq={r['min_order']} {r['decision']:17} trap={r['trap_tool_called']} ${r['cost_usd']:.6f}")
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"total cost ${sum(r['cost_usd'] for r in results):.6f}")


if __name__ == "__main__":
    main()
