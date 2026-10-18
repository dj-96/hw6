# Handbook Size and Cost Estimate (Problem 2)

## Token count

| Measure | Value |
|---|---|
| Characters | 28,903 |
| Words | 6,127 |
| **Tokens** | **10,058** |

**How I got it:** I ran `count_tokens.py`, which loads `data/shop_handbook.md` and counts its tokens with
`tiktoken`, OpenAI's tokenizer library, using the `o200k_base` encoding (the one current GPT models use).
That is a local estimate of what gpt-6-luna will see. As a sanity check, the usual rule of thumb is about
4 characters per token: 28,903 / 4 ≈ 7,200 tokens. The real count is higher because the handbook is full of
numbers, SKUs, `$` signs, and table pipes `|`, which split into many small tokens.

The actual prompt on each call will be a bit larger than 10,058 because it also includes our instructions
and the vendor document. Problem 4 checks this estimate against the real `usage` numbers from the API.

## gpt-6-luna prices (from `data/prices.json`)

| Token type | $ per 1M tokens | $ per token |
|---|---|---|
| Input (uncached) | $0.10 | $0.0000001 |
| Cache write | $0.125 | $0.000000125 |
| Cached input (cache hit) | $0.01 | $0.00000001 |
| Output | $0.50 | $0.0000005 |

## Cost of the handbook alone

Output tokens are not included here, only the handbook as input.

### One call

| Scenario | Math | Cost |
|---|---|---|
| No caching | 10,058 × $0.10 / 1,000,000 | **$0.0010058** (~0.10¢) |
| Cache write (first call) | 10,058 × $0.125 / 1,000,000 | **$0.0012573** (~0.13¢) |
| Cache hit (later calls) | 10,058 × $0.01 / 1,000,000 | **$0.0001006** (~0.01¢) |

### 1,000 calls

| Scenario | Math | Cost |
|---|---|---|
| No caching | 1,000 × $0.0010058 | **$1.0058** |
| With caching | 1 write + 999 hits = $0.0012573 + 999 × $0.0001006 = $0.0012573 + $0.1004794 | **$0.1017** |

**Savings with caching:** $1.0058 − $0.1017 = **$0.9041 per 1,000 calls, about 90% less.**

A cache hit costs 1/10 of a normal input token, and the one-time write premium (25% more than normal input)
is paid back on the very next call.

### Assumptions

- The handbook sits at the **start** of the prompt and is byte-for-byte identical on every call, so the
  provider can reuse the cached prefix.
- The cache stays warm for all 1,000 calls (calls come close together). If the cache expires between calls,
  each expiry costs another write ($0.0012573), so the real cached total would land between $0.10 and $1.01.
- These are estimates from a local tokenizer; Problem 4 will compare them to real runs.
