# Cross-Review

[English](README.md) | [中文](README_CN.md)

Multi-model collaboration skill for AI coding tools. Orchestrate Claude, Codex, Gemini, GLM and others to collaboratively review, design, and stress-test — producing higher quality output than any single model alone.

## Why Cross-Review?

Single-model reviews have a fundamental limit: one set of training data, one set of blind spots. Cross-Review solves this by:

- **Diverse perspectives**: Different models catch different issues. In real-world testing, Codex found architecture risks that Claude missed, while Claude caught data flow issues Codex overlooked.
- **Adversarial verification**: Round 4 doesn't just review — it actively *attacks* the proposed solution with structured stress tests, exposing hidden assumptions and over-engineering.
- **Anti-consensus bias**: When all models agree, that's when you should worry most. Cross-Review explicitly guards against shared training data biases.

## How It Works

```
Round 1  Independent Work      Each model analyzes from its assigned perspective     (parallel)
Round 2  Cross-Validation      Models review each other's findings, flag conflicts   (parallel)
Round 2.5 Focused Rebuttal     Resolve critical conflicts before synthesis           (optional)
Round 3  Candidate Synthesis   Lead model proposes candidates + assumption ledger    (lead model)
Round 4  Adversarial Attack    All models stress-test with emphasis assignments      (parallel)
```

**Two modes:**
- **Quick mode** (2 rounds) — multi-perspective review without deep adversarial testing
- **Full mode** (4 rounds, with optional 2.5) — complete cross-validation + adversarial stress test

**Round 4's four mandatory stress tests** make this skill unique:

| Check | Purpose |
|-------|---------|
| Loop Detection | Does the solution re-introduce the same type of problem it solves? |
| Scenario Walkthrough | Construct 3+ concrete user scenarios and step through them |
| Removal Test | For each new component: what happens if we remove it? |
| Consensus Blind Spot | What did all models assume without questioning? |

## Quick Start

### Claude Code

```bash
/skill add JVever/cross-review
```

### Cursor / Windsurf

```bash
git clone https://github.com/JVever/cross-review.git
cp -r cross-review/skills/cross-review/ .cursor/rules/cross-review/
```

### Other Tools

```bash
git clone https://github.com/JVever/cross-review.git
# Claude Code manual install:
ln -s "$(pwd)/cross-review/skills/cross-review" ~/.claude/skills/cross-review
# Or copy to your tool's rules/skills directory
```

## Usage

Trigger with natural language — works in both English and Chinese:

```
cross review this architecture design with Codex
```
```
和 Gemini 一起讨论一下这个架构
```
```
让几个模型一起评审 docs/prd.md
```

**First use**: the skill detects your CLI tools, confirms invocation methods, and saves the config. **Every use after**: instant warm start — loads saved config, runs sub-second healthchecks, and goes straight to Round 1.

## Applicable Scenarios

- **Technical reviews**: Architecture designs, code reviews, API designs, migration plans
- **Product/strategy**: PRDs, business plans, go-to-market strategies, competitive analysis
- **Creative/exploratory**: Article writing, brainstorming, open-ended discussions, content strategies
- **High-stakes decisions**: Any decision where a single perspective isn't enough

## Key Features

| Feature | Description |
|---------|-------------|
| **Model-agnostic** | Works with any AI CLI: Codex, Gemini, Crush (GLM), Claude Code, and more |
| **Warm start** | CLI config persisted across sessions; sub-second healthcheck; no repeated setup |
| **Structured runtime wrapper** | Every external call can emit `status.json`, `logs/`, and `invalid/` artifacts with stdout/stderr, exit code, duration, retries, and validation results |
| **Learnable model registry** | `~/.config/cross-review/registry.json` remembers verified model paths and refreshes when catalog data gets stale or a CLI version changes |
| **Output quality control** | Suggested output skeleton + two-layer validation (transport + semantic) |
| **Clean outputs** | Codex: `--output-last-message` strips noise; Crush: `--quiet` hides spinner |
| **Graceful degradation** | Adapts from 3 models → 2 → 1 with adjusted strategies |
| **Anti-pattern guards** | Fights consensus bias, rubber-stamp reviews, and abstract-only discussion |
| **Checkpoint/resume** | `manifest.json` tracks progress; interrupted sessions continue from last step |
| **Adversarial Round 4** | 4 mandatory stress tests with emphasis-based division of labor |

## File Structure

```
skills/cross-review/
  SKILL.md                                  Core workflow and instructions
  scripts/
    cross_review_runtime.py                 Runtime wrapper for external CLI execution and model resolution
  references/
    prompt-templates.md                     Prompt templates for all rounds
    round4-attack-checklist.md              4 mandatory adversarial checks (detailed)
    evaluation-and-strategies.md            Perspectives, degradation, validation rules
tests/
  test_cross_review_runtime.py              Regression tests for wrapper logging and registry learning
```

## Requirements

- **Primary tool** (runs the skill): Any AI coding tool that supports custom skills — [Claude Code](https://claude.ai/code), [Cursor](https://www.cursor.com/), [Trae](https://www.trae.ai/), [Windsurf](https://windsurf.com/), etc.
- **External models** (called via CLI): At least one of:
  - [Codex CLI](https://github.com/openai/codex) (OpenAI)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli) (Google)
  - [Crush CLI](https://charm.sh/crush) (GLM / Zhipu AI, by Charm)
  - Any AI tool with a non-interactive CLI mode

> Works with a single model too (switches perspectives across rounds), but multi-model setups produce significantly better results.

## License

[GPL-3.0](LICENSE)
