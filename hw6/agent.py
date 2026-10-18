"""Campus Customs vendor desk agent.

Usage:
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html            # all defenses
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html --defenses none
    python agent.py --doc ... --defenses code,prompt                           # any subset

Reads one vendor document, extracts the key facts, applies the handbook's
purchasing checks, and logs the answer, tool calls, and cost to output/.
"""
import argparse
import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelSettings, Tool, UsageLimits
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from models import VendorDecision
from rules import decide
from sanitize import sanitize_document
from tools import (OUTPUT_DIR, PROJECT_DIR, TRAP_LOG, append_json, approve_payment, ensure_log, now, read_document,
                   read_document_safe, resolve, send_email)

MODEL_NAME = "gpt-6-luna"  # the only model used in this homework
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

PROMPT_PATH = PROJECT_DIR / "prompts" / "prompt.md"
HANDBOOK_PATH = PROJECT_DIR / "data" / "shop_handbook.md"
PRICES_PATH = PROJECT_DIR / "data" / "prices.json"
USAGE_LOG = OUTPUT_DIR / "usage_log.json"
AUDIT_LOG = OUTPUT_DIR / "audit_trail.json"

RESULT_PREVIEW = 300  # chars of each tool result kept in the audit trail

# The project .env (if any) wins; the class folder's .env holds PORTKEY_API_KEY.
for folder in (PROJECT_DIR, *PROJECT_DIR.parents):
    if (folder / ".env").is_file():
        load_dotenv(folder / ".env")


def build_model() -> OpenAIResponsesModel:
    """gpt-6-luna via OpenAI directly (OPENAI_API_KEY) or via Portkey (PORTKEY_API_KEY).

    LLM_GATEWAY=openai (default) or portkey picks the route. Same model either way.
    """
    gateway = os.getenv("LLM_GATEWAY", "openai").strip().lower()
    if gateway == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to a .env file.")
        client = AsyncOpenAI(api_key=api_key, max_retries=1)
    elif gateway == "portkey":
        api_key = os.getenv("PORTKEY_API_KEY")
        if not api_key:
            raise RuntimeError("PORTKEY_API_KEY is not set. Add it to a .env file.")
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=PORTKEY_BASE_URL,
            default_headers={"x-portkey-api-key": api_key},
            max_retries=1,
        )
    else:
        raise RuntimeError("LLM_GATEWAY must be 'openai' or 'portkey'.")
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


# The three defense layers (Problem 6). Any subset can be switched on.
#   code:   sanitize the document before the model sees it (sanitize.py)
#   design: the model never gets send_email/approve_payment, and Python makes the
#           decision from grounded facts (rules.py)
#   prompt: the security rules block in prompts/prompt.md
DEFENSES = ("code", "design", "prompt")
SECURITY_BLOCK = re.compile(r"\n*<!-- SECURITY RULES START.*?<!-- SECURITY RULES END -->\n*", re.S)


def build_instructions(prompt_defense: bool = True) -> str:
    """Our instructions followed by the full handbook (sent on every call)."""
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    if not prompt_defense:
        prompt = SECURITY_BLOCK.sub("\n", prompt).rstrip() + "\n"
    handbook = HANDBOOK_PATH.read_text(encoding="utf-8")
    return f"{prompt}\n\n---\n\n# HANDBOOK\n\n{handbook}"


@lru_cache(maxsize=None)
def get_agent(defenses: frozenset = frozenset(DEFENSES)) -> Agent:
    reader = Tool(read_document_safe if "code" in defenses else read_document, name="read_document")
    if "design" in defenses:
        # Least privilege: the extraction agent can only read. send_email and
        # approve_payment stay in tools.py for the shop's human-sign-off workflow,
        # but a model reading vendor documents never sees them.
        tools = [reader]
    else:
        tools = [reader, send_email, approve_payment]
    return Agent(
        build_model(),
        output_type=VendorDecision,
        instructions=build_instructions("prompt" in defenses),
        tools=tools,
        model_settings=ModelSettings(max_tokens=4_000, timeout=90),
    )


def parse_defenses(spec: str) -> frozenset:
    spec = spec.strip().lower()
    if spec in ("all", ""):
        return frozenset(DEFENSES)
    if spec == "none":
        return frozenset()
    chosen = frozenset(s.strip() for s in spec.split(","))
    if unknown := chosen - set(DEFENSES):
        raise ValueError(f"unknown defense(s) {sorted(unknown)}; choose from {DEFENSES}, 'all', or 'none'")
    return chosen


@dataclass
class RunOutcome:
    result: object  # the PydanticAI run result
    output: VendorDecision  # the final answer (after the design layer, if on)
    model_output: VendorDecision  # what the model itself returned
    defenses: frozenset
    removed_hidden_text: list = field(default_factory=list)
    design_notes: list = field(default_factory=list)

# Prompt caching. The instructions + handbook are an identical ~11k-token prefix
# on every call, so OpenAI can serve them from cache at 1/10 the input price.
# - cache on:  implicit caching (OpenAI picks the breakpoint) plus a fixed
#              prompt_cache_key so all our calls route to the same cache.
# - cache off: "explicit" mode with no CachePoint breakpoints, so OpenAI has
#              nothing it is allowed to cache or reuse.
CACHE_ON = OpenAIResponsesModelSettings(
    openai_prompt_cache_key="campus-customs-vendor-desk",
    openai_prompt_cache_options={"mode": "implicit"},
)
CACHE_OFF = OpenAIResponsesModelSettings(openai_prompt_cache_options={"mode": "explicit"})


def cost_usd(usage) -> dict:
    """Dollar cost from the token counts the API reports, using prices.json.

    OpenAI counts cached tokens inside input_tokens, so the uncached part is
    input - cache_read - cache_write.
    """
    p = json.loads(PRICES_PATH.read_text())[MODEL_NAME]
    uncached = usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens
    parts = {
        "uncached_input": uncached * p["input_per_1m"] / 1e6,
        "cached_input": usage.cache_read_tokens * p["cached_input_per_1m"] / 1e6,
        "cache_write": usage.cache_write_tokens * p["cache_write_per_1m"] / 1e6,
        "output": usage.output_tokens * p["output_per_1m"] / 1e6,
    }
    return {"total": round(sum(parts.values()), 8), **{k: round(v, 8) for k, v in parts.items()}}


def tool_calls_from(messages) -> list[dict]:
    """Pair each tool call with its (shortened) result for the audit trail."""
    calls, results = [], {}
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ToolCallPart) and isinstance(msg, ModelResponse):
                calls.append(part)
            elif isinstance(part, ToolReturnPart):
                results[part.tool_call_id] = str(part.content)
    out = []
    for c in calls:
        if c.tool_name.startswith("final_result"):
            continue  # the structured output itself, not a real tool
        result = results.get(c.tool_call_id, "")
        out.append({
            "tool": c.tool_name,
            "args": c.args_as_dict(),
            "result": result[:RESULT_PREVIEW] + ("..." if len(result) > RESULT_PREVIEW else ""),
        })
    return out


def model_calls_from(result) -> list[dict]:
    """One record per model request, with every token count the API reported."""
    result = getattr(result, "result", result)  # accept a RunOutcome too
    calls = []
    for i, msg in enumerate(m for m in result.all_messages() if isinstance(m, ModelResponse)):
        u = msg.usage
        calls.append({
            "call": i + 1,
            "input_tokens": u.input_tokens,
            "cache_read_tokens": u.cache_read_tokens,
            "cache_write_tokens": u.cache_write_tokens,
            "output_tokens": u.output_tokens,
            "total_tokens": u.total_tokens,
            "details": dict(u.details),  # e.g. reasoning_tokens
            "cost_usd": cost_usd(u),
        })
    return calls


def run(doc: str, cache: bool = True, defenses: frozenset = frozenset(DEFENSES)) -> RunOutcome:
    """Run the agent on one document, append the logs, and return the outcome."""
    for log in (TRAP_LOG, USAGE_LOG, AUDIT_LOG):
        ensure_log(log)
    defenses = frozenset(defenses)

    # What the code layer strips is logged for a human, never shown to the model.
    path = resolve(doc)
    removed = []
    if "code" in defenses and path.is_file():
        _, removed = sanitize_document(path)

    started = now()
    result = get_agent(defenses).run_sync(
        f"Vendor document path: {doc}",
        usage_limits=UsageLimits(request_limit=8, tool_calls_limit=6),
        model_settings=CACHE_ON if cache else CACHE_OFF,
    )
    usage = result.usage
    model_output = result.output
    final, notes = model_output, []
    if "design" in defenses:
        # Python makes the decision from facts grounded in the same text the model read.
        seen = read_document_safe(doc) if "code" in defenses else read_document(doc)
        final, notes = decide(model_output, seen)

    append_json(USAGE_LOG, {
        "document": doc,
        "time": started,
        "model": MODEL_NAME,
        "cache": cache,
        "defenses": sorted(defenses),
        "requests": usage.requests,
        "input_tokens": usage.input_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "cost_usd": cost_usd(usage),
    })
    append_json(AUDIT_LOG, {
        "document": doc,
        "time": started,
        "defenses": sorted(defenses),
        "removed_hidden_text": removed,
        "tool_calls": tool_calls_from(result.all_messages()),
        "model_answer": model_output.model_dump(),
        "design_notes": notes,
        "final_answer": final.model_dump(),
    })
    return RunOutcome(result, final, model_output, defenses, removed, notes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs vendor desk agent")
    parser.add_argument("--doc", required=True, help="Path to one vendor document (.html, .pdf, or .eml)")
    parser.add_argument("--no-cache", action="store_true", help="Turn off prompt caching for this run")
    parser.add_argument("--defenses", default="all",
                        help="Defense layers: 'all' (default), 'none', or a comma list of code,design,prompt")
    args = parser.parse_args()

    outcome = run(args.doc, cache=not args.no_cache, defenses=parse_defenses(args.defenses))
    print(json.dumps(outcome.output.model_dump(), indent=2))
    if outcome.removed_hidden_text:
        print(f"\ncode layer removed {len(outcome.removed_hidden_text)} hidden snippet(s) (see output/audit_trail.json)")
    for note in outcome.design_notes:
        print(f"design layer: {note}")
    last = json.loads(USAGE_LOG.read_text())[-1]
    print(f"\ntokens: {last['input_tokens']:,} in ({last['cache_read_tokens']:,} cached) / "
          f"{last['output_tokens']:,} out over {last['requests']} requests | cost ${last['cost_usd']['total']:.6f}")


if __name__ == "__main__":
    main()
