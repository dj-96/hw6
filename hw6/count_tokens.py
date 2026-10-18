"""Count the tokens in the shop handbook and estimate what it costs per call.

Uses tiktoken's o200k_base encoding (the tokenizer used by OpenAI's current
GPT models) as a local estimate. Problem 4 checks this against real API usage.
"""
import json
from pathlib import Path

import tiktoken

DATA = Path(__file__).parent / "data"
MODEL = "gpt-6-luna"

text = (DATA / "shop_handbook.md").read_text(encoding="utf-8")
prices = json.loads((DATA / "prices.json").read_text())[MODEL]

enc = tiktoken.get_encoding("o200k_base")
tokens = len(enc.encode(text))

per_tok = {k: v / 1_000_000 for k, v in prices.items()}
uncached_1 = tokens * per_tok["input_per_1m"]
write_1 = tokens * per_tok["cache_write_per_1m"]
read_1 = tokens * per_tok["cached_input_per_1m"]

print(f"characters: {len(text):,}")
print(f"words:      {len(text.split()):,}")
print(f"tokens:     {tokens:,} (o200k_base)")
print()
print(f"1 call, no cache:          ${uncached_1:.6f}")
print(f"1 call, cache write:       ${write_1:.6f}")
print(f"1 call, cache hit:         ${read_1:.6f}")
print(f"1000 calls, no cache:      ${uncached_1 * 1000:.4f}")
print(f"1000 calls, cached (1 write + 999 hits): ${write_1 + read_1 * 999:.4f}")
