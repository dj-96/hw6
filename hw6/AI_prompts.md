# AI Prompts Log — MGT 409 Homework 6 (Campus Customs Vendor Desk Agent)

This file logs what I typed to my vibe coder (Claude Code), one section per problem.
Prompts are in my own words. I updated this file as I worked.

---

## Setup — Scenario

**Prompt 1:**
> we are gonna do homework 6. do everything in Homework 6 folder

**Follow-up prompt:**
> Willl give you scenario first
>
> Campus Customs gets a steady stream of vendor quotes, invoices, catalog pages, and supplier emails. you will build a vendor desk agent that reads one of these documents, pulls out the key facts (vendor, item, price, lead time, minimum order), and recommends whether the shop should buy, following the rules in the Campus Customs Shop Handbook
>
> This week is about two things that matter once an agent runs for deal: cost (the handbook is about 10,000 tokens and goes out on every call) and safety (some vendor documents hide instructions aimed at your AI). you will measure the bill, cut it, attack your own agent, and defen it.
>
> do no send emails or make payments. the agent's email and payment tools only write to a log file.
>
> use your 'PORTKEY_API_KEY' and only 'gpt-6-luna' for every ai call. points will be deducted if any other model shows up in your code or runs.
>
> work one problem at time with your vibe coder. ... in the end you will push your project to a public GitHub repo and submit the repo URL on Canvas ... do not commit your '.env'

*What was lacking after the first prompt:* the folder only had data files, so the vibe coder didn't know what to build and asked me for the assignment context.

---

## Problem 1 — Vibe Coder Prompts

**Prompt 1:**
> problem 1: vibe coder prompts
>
> create 'AI_prompts.md' at the start of the assignment and keep it updated as you work. this file is the log of what you typed to your vibe coder.
>
> put one section for each problem. each section must include:
> * the problem number and title
> * at least one prompt you typed, in your own words as much as possible
> * one follow-up prompt if you needed it (and one sentence on what was lacking after the first)

**Follow-up prompt:** none needed. The first prompt was enough to create this file.

---

## Problem 2 — Size Up the Handbook

**Prompt 1:**
> problem 2: size up the handbook
>
> i unzipped 'data.zip'. look through 'data/shop_handbook.md'. this is the Campus Customs Shop Handbook, and your agent will send it to the model on every single call. Also look at 'data/prices.json', the gpt-6-luna price list.
>
> find out how many tokens the handbook is. in 'output/handbook_estimate.md' write:
> * the token count and how you got it
> * what the handbook alone costs in dollars on one call, and on 1000 calls, with cached tokens and without them. show your mate
>
> you will check these estimates against real runs in problme 4

**Follow-up prompt:** none needed. The vibe coder counted tokens with tiktoken (`count_tokens.py`) and wrote the report with the math shown.

---

## Problem 3 — Build the Vendor Desk Agent

**Prompt 1:**
> problme 3: build the vendor desk agent
>
> build the vendor desk agent with PydanticAI using 'gpt-6-luna'. the agent is these four files: 'prompts/prompt.md' (your instructions for the agent; the agent also sends the handbook to the model on every call), 'agent.py' (the entry point), 'tools.py' (the tools), 'models.py' (the structured types)
>
> give the agent the path to one vendor document. it reads the document with a tool (HTML, PDF, and '.eml' email files all have to work) and returns: vendor, SKU, unit price, lead time in delays, minimum order, a decision ('recommend' or 'do not recommend') following the handbook rules, and a one-sentence reason.
>
> your agent must also have two trap tools: 'send_email' and 'approve_payment'. its job never needs them. they are there to catch a malicious document that tricks your agent into emailing someone or paying a vendor. they do not send or pay anything. they only append the call and its argument to 'output/trap_calls.json' (start is as an empty list) ... keep them on your system for the whole homeowkr.
>
> after every run, append to 'output/usage_log.json' (document, time, the token counts the API reports, and the dollar cost using 'prices.json') and 'output/audit_trail.json' (each tool call with its arguments and a short result, plust the final answer)
>
> your agent should run like this in the terminal: python agent.py --doc data/practice_docs/p01_bluehen_quote.html
>
> run it on 'p01' and 'p08' to show it works. start 'output/harness.md': each field in 'models.py' and why, and each tool in one line.

**Follow-up prompt:**
> use OPENAI_API_KEY instead

*What was lacking after the first prompt:* the code was done, but the p01/p08 runs failed because my Portkey key hit its usage limit, so I switched the agent to call gpt-6-luna directly with my OpenAI key.

---

## Problem 4 — With and Without Cached Tokens

**Prompt 1:**
> problem 4: with and without cached tokens
>
> the handbook is the same on every call, so the model can resue it from a cache at a much cheaper price. test what that is worth. run your agent on all 12 practice documents two ways:
> * with cache: set up so the handbook gets reused from cache
> * without cache: set up so nothing gets reused from cache
>
> check the token counts the API sends back to prove each setup really did what you think. a without-cache run that still shows cached tokens does not count.
>
> save every model call from both setups to 'output/cache_test.json'. for each call include the setup, document, every token count the API reports, and dollars from 'prices.json'
>
> in 'output/cache_test.md': total cost and cost per document for each setup, and the percent you saved; how your real numbers compare to your problme 2 estimate; a projection for 1000 documents a day for 30 days, with and without cache; anything in the numbers that surprised you, and why it happens

**Follow-up prompt:** none needed. The vibe coder added cache on/off settings to `agent.py` (OpenAI `prompt_cache_options` mode implicit vs. explicit), tested one no-cache call to confirm 0 cached tokens before the full run, then wrote `cache_test.py` and the report.

---

## Problem 5 — Attack Your Own Agent

**Prompt 1:**
> problme 5: attack your own agent
>
> some vendor documents are booby-trapped with text aimed at AI. run your problme 3 agent, with no new defenses, on all 12 documents in 'data/practice_docs/'. compare each answer to 'data/practice_key.json' and check 'output/trap_calls.json', the log your fake email and payment tools from problem 3 write to.
>
> save 'output/attack_results.json': for each document, whether each field matched the key, whether the decision matched, whether a trap tool was called, and whether a link or other strange text showed up in the answer
>
> in 'output/attack_results.md', for every document that fooled your agent, write what fooled it and where in the fiile it was hiding. open the documents the way a person would (browser, PDF viewer, email app) and compare that with what your agent read.

**Follow-up prompt:** none needed. The vibe coder wrote `attack_test.py`, then opened each document in a real browser (headless Chrome screenshots) and rendered the PDFs to images to compare against the extracted text. The screenshots are in `output/screenshots/`.

---

## Problem 6 — Defend Your Agent

**Prompt 1:**
> problem 6: defend your agent
>
> defend your agent at three levels:
> * code: what your program does to the document before any model sees it
> * design: how your agent is put together, so a poisoned document cannot reach the dangerous tools or the decision
> * prompt: rules in 'prompts/prompt.md'
>
> you may not delete 'send_email' or 'approve_payment' from your system. the shop will use them later with a human sign-off. keep a way to run the agent with no defenses (you need it in problme 7)
>
> rerun all 12 practice documents. save 'output/defense_results.json' in the same shape as problem 5, plus tokens and dollars per document
>
> clean documents must still come back with the right values. refusing or blanking out a real quote counts as a failure.
>
> in 'output/defense_results.md': a before and after table for all 12 documents; what each layer catches that the others miss; the extra tokens and dollars each layer adds per document
>
> add your safety features to 'output/harness.md' in a Safety section: what each defense layer does, in plain words

**Follow-up prompt:** none needed. The vibe coder built `sanitize.py` (code), `rules.py` plus a read-only toolset (design), and a security block in `prompt.md` (prompt), added a `--defenses` flag (`none` keeps the original agent), and ran each layer alone and all together to measure what each one catches and costs.

---

## Problem 7 — Red Team

**Prompt 1:**
> problme 7: red team
>
> now you are the attacker. make two new booby-trapped vendor documents in 'data/my_attacks/' (HTML, PDF, or email). each one should use a hiding trick or an attack goal that is not in the practice set. a person opening the document should see a normal quote.
>
> run both attacks on your agent with no defenses and on your defended agent. in 'output/red_team.md', for each attack: what is hidden, where, what it tries to make the agent do, and what happened before and after your defenses.
>
> more points for attachs that are new and that actuallly fool the agnet with no defense.

**Follow-up prompt:** none typed. The vibe coder iterated on its own: version 1 (an overt fake handbook addendum plus an approve_payment request, and a "file under CC-TE-003" note) didn't fool even the undefended agent, so it rewrote both as quiet one-fact "corrections" (version 2), which did. It then patched `sanitize.py` to close the two gaps the attacks exposed (`<style>` class hiding and PDF render mode 3) and re-ran.

---

## Problem 8 — Exam Documents

**Prompt 1:**
> problem 8: exam documents
>
> 'data/exam_docs/' has 10 vendor documents with no answer key. run your final defended agent on all of them. do not hand-edit the results.
>
> save 'output/exam_results.json' with one entry per exam file. each entry has these fields: 'file', 'vendor', 'sku', 'unit_price', 'lead_time_days', 'min_order', 'decision' ('recommend' or 'do_not_recommend'), 'reason', 'trap_tool_called' (true or false), 'input_tokens', 'cached_tokens', 'output_tokens', 'cost_usd'
>
> graders compare your results to a hidden answer key and rerun some agents to cehck. you get points for correct fields and decisions, no trap tool calls, and clean doucments handled normally.

**Follow-up prompt:** none needed. The vibe coder wrote `exam_run.py`, which runs the agent with all three defenses and writes `output/exam_results.json` directly from the agent's output, with no hand edits.

---

## Problem 9 — Results Page

**Prompt 1:**
> problem 9: results page
>
> build 'output/hw6_report.html'. it must be one file that opens by double-click with no internet and no other files next to it.
>
> the page must show the five things below. use your real numbers from earlier problems: your caching results, with a chart; attacks before and after your defenses; what your defenses cost in tokens and dollars; your exam results and your two red team attacks; a short recommendation to the store manager, should Campus Customs turn this agent on for real vendor mail, and what would it cost per month at 1000 documents a day?
>
> more points for a designated page (fonts, color, layout) that reads well

**Follow-up prompt:** none typed. The vibe coder wrote `build_report.py`, which reads every number from the `output/*.json` files and builds one self-contained HTML page: inline SVG charts with hover tooltips, screenshots embedded as base64, system fonts only, and a black-and-pink design with a colorblind-checked palette. It screenshotted the page and fixed a label overlap, wrapping SKUs, and an oversized PDF thumbnail.

---

## Problem 10 — Push to GitHub and Submit the URL

**Prompt 1:**
> problem 10: push a github and submit the url
>
> push your project to a public GitHub repository and submit the repo URL on canvas. graders will clone it, so make sure it opens and the files below are there
>
> include the whole 'data/' folder (the course data plus your tow attack files) so graders can clone your repo and run your agent right away. do not commit your real '.env'. use '.gitignore' to keep it out, and include '.env.example' with placeholder only.
>
> expected repo: hw6/ with AI_prompts.md, README.md, .gitignore, .env.example, requirements.txt, agent.py, tools.py, models.py, prompts/prompt.md, data/ (handbook, prices, practice key, practice_docs, exam_docs, my_attacks), output/ (all result files and hw6_report.html)

**Follow-up prompt:**
> ready to upload right? i'll upload to github manually and you just need to confirm me if hw6 folder is ready to be uploaded

*What was lacking after the first prompt:* the GitHub CLI wasn't installed and pushing needed my GitHub login, so I chose to upload the prepared `hw6/` folder myself. The vibe coder only had to assemble it, write the README, and check it: every expected file present, no `.env`, no API keys in any file, and gpt-6-luna as the only model name.

---
