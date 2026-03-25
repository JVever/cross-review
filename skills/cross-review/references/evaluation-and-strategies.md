# Evaluation Criteria & Advanced Strategies

Detailed evaluation criteria, degradation strategies, and execution checklists.

---

## Perspective Assignment by Task Type

The lead model dynamically assigns focus perspectives based on task type. These are reference examples:

**Technical Tasks** (code review, architecture design, API design, etc.):
- Perspective A: Architecture consistency & data flow analysis
- Perspective B: Technical implementation feasibility & risk
- Perspective C: Edge cases, user experience & alternative approaches

**Product/Strategy Tasks** (PRD, operations plan, business strategy, etc.):
- Perspective A: Logical consistency & argument completeness
- Perspective B: Feasibility & resource risk
- Perspective C: User impact & alternative paths

**Creative/Exploratory Tasks** (article writing, plan design, open discussion, etc.):
- Perspective A: Structural completeness & core arguments
- Perspective B: Audience fit & expression effectiveness
- Perspective C: Innovation & differentiated perspectives

> These are references only. The lead model should dynamically adjust perspective definitions based on the specific task. Users can also specify custom perspectives.

### Assignment Rules

| Model Count | Strategy |
|-------------|----------|
| 3 models | Lead model -> Perspective A, External 1 -> Perspective B, External 2 -> Perspective C |
| 2 models | Lead model -> Perspective A + C, External -> Perspective B |
| 1 model | Lead model switches perspectives across rounds |

---

## Degradation Strategy

| Model Count | Round 1-2 | Round 3 | Round 4 |
|-------------|-----------|---------|---------|
| 3 (optimal) | Each with independent focus perspective | Lead model synthesizes | All models do all 4 checks with emphasis assignments |
| 2 | Lead model takes Perspective A+C, external takes B | Lead model synthesizes, external reviews | Both do all 4 checks; external emphasizes attack, lead emphasizes synthesis |
| 1 (minimum) | Lead model switches perspectives via different prompts | Lead model synthesizes | Use explicit adversarial prompt for self-attack |

---

## CLI Configuration Persistence

### Config File Location

`~/.config/cross-review/models.yaml`

### Three-Path Startup

1. **Warm start** (config exists + healthcheck passes): Load config → run `healthcheck` per model → non-blocking notification → proceed to Round 1. No user confirmation needed.
2. **Cold start** (no config): Run `which` detection → confirm with user → save config.
3. **Fallback** (config exists but healthcheck fails / user requests new model): Re-guide only for the affected CLI → update config.

### Healthcheck Commands (CLI-level, no model calls)

| CLI | Command | Verifies |
|-----|---------|----------|
| Codex | `codex exec --help >/dev/null 2>&1` | CLI + subcommand exist |
| Gemini | `gemini -v >/dev/null 2>&1` | CLI exists + version readable |
| Crush | `crush models >/dev/null 2>&1` | CLI exists + models configured |

Auth/network issues are caught by output validation on first real call, not by preflight.

### Model Name Resolution

When a user references a model by name (e.g., "GLM-4.7"), the lead model should:
1. Check config for a CLI with matching `model_name` field
2. If found, use that CLI's `invoke` command
3. If not found, ask user which CLI to use for that model, then save the mapping

---

## Output Contract Enforcement

### For Codex CLI

**Required flags**: `--full-auto --output-last-message {file} --color never --ephemeral`

- `--output-last-message`: Extracts only the final message, filtering out session metadata, thinking blocks, and command logs
- `--ephemeral`: No session files persisted
- `--color never`: No ANSI escape sequences

### For Gemini CLI

**Recommended**: `gemini -p "{prompt}" > {file}`

Note: `-p` requires the prompt as a string argument. Do NOT use `echo | gemini -p` (leaving `-p` without a value).

### For Crush CLI (GLM)

**Recommended**: `crush run --quiet "{prompt}" > {file}`

- `--quiet`: Hides spinner, ensures clean text output
- Subcommand is `run`, not `chat`

### For Other CLIs

Confirm non-interactive invocation format with user on first use. Store in config.

---

## Output Validation

### Layer 1: Transport Validation (auto, hard fail)

| Check | Fail Condition | Action |
|-------|---------------|--------|
| Non-empty | File is 0 bytes | Retry once → degrade |
| Minimum size | < 200 bytes | Retry once → degrade |
| No auth prompts | Contains `Opening authentication`, `Y/n`, `Do you want to continue` | Retry once → degrade |
| No ANSI noise | Contains escape sequences `\x1b[` | Strip sequences, then validate |
| No help text | Contains `Usage:` and `--help` | Retry once → degrade |

### Layer 2: Semantic Validation (auto, soft fail)

| Check | Fail Condition | Action |
|-------|---------------|--------|
| Has expected headings | Missing all of: `## 结论摘要`, `## 发现`, `## 方案` | Mark as low-quality |
| Has substance | Zero findings or proposals | Mark as low-quality |
| Has conclusion | Missing `## 一句话结论` | Mark as low-quality |

### Retry Strategy

1. First retry: Use a shortened prompt (remove task materials, keep only task description + focus)
2. If retry also fails: Degrade (remove this model from current round), inform user
3. Failed outputs saved to `invalid/` subdirectory

---

## Cross-Round Context: Digest Protocol

### Default: Pass Clean Outputs

External model outputs cleaned via `--output-last-message` (Codex) or equivalent methods are passed directly to subsequent rounds. Clean outputs preserve full information fidelity.

### Optional Digest (When Output > 5000 Words)

When a clean output exceeds ~5000 words, the lead model creates a digest:

1. Extract key findings (with severity ratings)
2. Extract disagreements and conflicts
3. Extract open questions
4. Remove redundant/duplicate points
5. Save as `r{N}.digest.md`
6. **Include note**: "This is a summary. Full content available in r{N}.{model}.md"

The digest is sent to external models; the lead model itself reads the full output.

---

## Intermediate Results Management

### Directory Structure

```
cross-review-records/
  run-{YYYYMMDD-HHmm}/
    r1.{model}.md         # Round 1 outputs
    r1.digest.md          # Lead model's digest of Round 1
    r2.{model}.md         # Round 2 outputs
    r2.5.{model}.md       # Round 2.5 (if triggered)
    r3.synthesis.md       # Round 3 candidate synthesis
    r3b.synthesis.md      # Round 3b revision (if Round 4 found Critical)
    r4.{model}.attack.md  # Round 4 attack reports
    final.md              # Final output
    manifest.json         # Run metadata & checkpoint
    invalid/              # Failed validation outputs
```

### File Naming Convention

**Strict format**: `r{round}.{model_name}.md`

Forbidden patterns:
- No free-form suffixes: `-ws`, `-v2`, `-session-fix`, `-raw`
- No prompt files in the output directory
- No `.txt` or `.raw.txt` files (always `.md`)

Special files:
- `r{N}.digest.md` — Digest for round N
- `r3.synthesis.md` / `r3b.synthesis.md` — Synthesis documents
- `final.md` — Final output
- `manifest.json` — Run metadata

### manifest.json

Created at run start, updated after each step. Used for checkpoint/resume.

---

## Execution Checklist

After each round, lead model self-checks:

- [ ] All outputs saved to run directory
- [ ] File naming follows `r{N}.{model_name}.md` format
- [ ] External model outputs passed transport validation
- [ ] External model outputs passed semantic validation (or marked low-quality)
- [ ] Digest created for cross-round context
- [ ] All models in current round have completed
- [ ] Key findings summary reported to user
- [ ] `manifest.json` updated

After all rounds complete:

- [ ] `final.md` contains the final plan/conclusion
- [ ] User provided with summary and suggested next steps
- [ ] User asked whether to keep intermediate documents
