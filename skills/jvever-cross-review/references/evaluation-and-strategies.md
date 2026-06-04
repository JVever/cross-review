# Evaluation Criteria & Strategies

Perspective assignment, output contract, validation, and degradation for the default **Claude (lead) + Codex (external)** pair.

> Why a fixed pair: in practice, the more CLIs you orchestrate, the more likely one stalls / times out / fails auth and drags the whole run out. Default to these two; keep them stable. Add a third model only on explicit request (see below) — do not build machinery for "arbitrary N models."

---

## Perspective Assignment

The lead assigns two focus perspectives by task type. Focus, not exclusive — each model should report anything important it finds.

| Task type | Claude (lead) | Codex (external) |
|-----------|---------------|------------------|
| Technical (code / architecture / API) | Architecture consistency, data flow, UX, alternatives | Implementation feasibility & risk |
| Product / strategy | Logical consistency, user impact, alternative paths | Feasibility & resource risk |
| Creative / exploratory | Structure, core arguments, audience fit | Differentiated angles, counterexamples, edges |

In full mode's Round 4, Codex plays devil's advocate (adversarial attack); the lead does the synthesis review. Users may specify custom perspectives.

**Adding a third model**: only if the user explicitly asks AND the CLI already has an `invoke` template in `models.yaml`. Assign it a third perspective inline. Otherwise stay on the pair.

---

## Output Contract Enforcement

Use `scripts/cross_review_runtime.py execute` for every external call. It captures stdout/stderr, exit code, duration, retries, and validation results; writes `status.json`, `logs/`, and `invalid/`.

### Codex (built-in)

Invoked by the runtime as `codex exec --full-auto --output-last-message {file} --color never --ephemeral` with the prompt on stdin:

- `--output-last-message`: only the final message (filters out session metadata, thinking blocks, command logs)
- `--ephemeral`: no session files persisted
- `--color never`: no ANSI escape sequences

### Any other CLI (via invoke template)

Add an `invoke` line to `models.yaml`, e.g. `'<cli> --model <id> "{prompt}" > {output_file}'`. Placeholders: `{prompt}` `{prompt_file}` `{output_file}` `{requested_model}` `{resolved_model}` (the same values are also exported as `CROSS_REVIEW_*` env vars). There is **no model auto-resolution** — write the exact model id you want directly into the template. If a CLI needs to bypass a proxy, put it in the template (e.g. `env HTTP_PROXY= HTTPS_PROXY= ...`).

---

## Output Validation

### Layer 1: Transport (hard fail)

Non-empty & > 200 bytes; no auth/interactive prompts (`Opening authentication`, `Y/n`, ...); ANSI stripped; not CLI help text. Fail → retry once (shortened prompt) → degrade.

This is the load-bearing guard against real CLI garbage (auth prompts, 0-byte output, 25–50KB session noise). Keep it.

### Layer 2: Semantic (soft — marks low quality, does NOT drop)

Has an expected heading (`## 结论摘要` / `## 发现` / `## 方案`); has ≥1 finding or proposal; has `## 一句话结论`. A low-quality output is still **kept** (status `semantic_low_quality`, counts as success, not moved to `invalid/`) — it's a weak signal, not a reason to throw away a possibly-fine review.

Failed (transport) outputs are saved under `invalid/`; raw stdout/stderr under `logs/`.

---

## Cross-Round Context: Digest

Default: pass clean outputs directly (Codex is already de-noised via `--output-last-message`). Only when an output exceeds ~5000 words does the lead make a digest (`r{N}.digest.md`) to pass to the next round, noting "full content in `r{N}.{model}.md`". The lead itself reads the full output.

---

## Degradation

| Available | Strategy |
|-----------|----------|
| Claude + Codex (normal) | Each takes its focus perspective; Codex is devil's advocate in R4 |
| Claude only (Codex unavailable) | Lead switches perspectives across rounds for self-adversarial review; **at wrap-up, tell the user Codex didn't run and confidence is reduced** |

Codex failing (after one retry) never aborts the run — degrade to single-model and reflect it honestly in the chat wrap-up and in `final.md`'s `models` field (list only models that actually produced output).

---

## Intermediate Results

```
cross-review-records/run-{YYYYMMDD-HHmm}/
  task-alignment.md            # alignment card (Step 1)
  status.json                  # per-call structured status
  logs/   invalid/             # raw evidence / failed outputs
  r1.claude.md  r1.codex.md
  r2.*.md   r2.attack.codex.md   r2.5.codex.md
  r3.synthesis.md   r3b.synthesis.md
  r4.*.md   r5.review.codex.md
  final.md                     # archive: ## 给你 + full process trail
  action.md                    # optional, long action lists only
```

Strict naming `r{round}.{model}.md`; no free-form suffixes (`-ws`, `-v2`, ...). Re-running the same task always creates a new `run-*` dir — timestamp ordering means `ls -t` gives the latest; no version-link machinery needed. **Keep process files by default** — they are the audit and future-optimization trail. Only drop them if the user explicitly says they don't want process docs.
