# Cross-Review

[English](README.md) | [中文](README_CN.md)

Multi-model collaboration skill for AI coding tools. By default it pairs **Claude (lead) + Codex (external)** to review, design, and stress-test together — producing higher-quality conclusions than any single model. Other CLIs can be added via a one-line `invoke` template when you actually need them.

## Why Cross-Review?

Single-model reviews have a fundamental limit: one set of training data, one set of blind spots. Cross-Review solves this by:

- **Diverse perspectives**: Different models catch different issues. In real-world testing, Codex found architecture risks Claude missed, while Claude caught data-flow issues Codex overlooked.
- **Adversarial verification**: Round 4 doesn't just review — it actively *attacks* the proposal with structured stress tests, exposing hidden assumptions and over-engineering.
- **Anti-consensus bias**: When all models agree, that's when to worry most. Cross-Review explicitly guards against shared-training-data bias.

## How It Works

```
Step 1     Task Alignment Card   Lead drafts goal/constraints/success criteria + decision mode  (non-blocking)
Round 1    Independent Work      Each model analyzes from its perspective (success_criteria injected)
Round 2    Cross-Validation      Models validate / challenge / supplement each other
Round 2.5  30s Devil's Advocate  (quick) one attack to break consensus bias
           Focused Rebuttal      (full) resolve critical conflicts
Round 3    Candidate Synthesis   (full) lead proposes candidates + assumptions to test
Round 4    Adversarial Attack    (full) Codex plays devil's advocate; loop back once on Critical
Wrap-up    Chat summary + archive Lead reports the conclusion in chat; final.md saved as the trail
```

**Two modes:**
- **Quick** (2 rounds + 30s attack) — multi-perspective with a lightweight adversarial check
- **Full** (4 rounds) — complete cross-validation + adversarial stress test

### What you actually get: a plain-language wrap-up in chat

The main deliverable is **what the lead says in the chat window when the run finishes** — four things, in plain language, no round codes or jargon:

1. **What was done** — how it was reviewed
2. **Review conclusion** — the cross-model findings, consensus and disagreements
3. **The lead's judgment** — what to adopt / reject and why
4. **Next step** — then either wait for your go-ahead, or (if you authorized autonomy) just do it and report back

`final.md` and the round files (`r1~r5*.md`) are kept as an **audit / trace archive** — for when you want to revisit *why* a decision was made, for a downstream AI picking up the task, or for tuning the process later. You don't need to read them to get the result; if you do open `final.md`, its top `## 给你` section mirrors the chat wrap-up.

**Round 4's four mandatory stress tests** are the core:

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
cp -r cross-review/skills/jvever-cross-review/ .cursor/rules/jvever-cross-review/
```

### Other Tools

```bash
git clone https://github.com/JVever/cross-review.git
ln -s "$(pwd)/cross-review/skills/jvever-cross-review" ~/.claude/skills/jvever-cross-review
```

Then make sure the Codex CLI is available (`codex exec --help`). That's the only external dependency for the default pair.

## Usage

Trigger with natural language — English or Chinese:

```
cross review this architecture design with Codex
```
```
让 Claude 和 Codex 一起评审 docs/prd.md
```

If you want the lead to act on the result without asking, say so up front ("you decide" / "just do it") — it runs autonomously and reports back. Otherwise it pauses for your go-ahead after the wrap-up.

## Applicable Scenarios

- **Technical reviews**: architecture, code review, API design, migration plans
- **Product / strategy**: PRDs, business plans, GTM, competitive analysis
- **Creative / exploratory**: writing, brainstorming, open-ended discussion
- **High-stakes decisions**: anywhere a single perspective isn't enough

## Key Features

| Feature | Description |
|---------|-------------|
| **Fixed, reliable pair** | Claude + Codex by default — the more CLIs you add, the more likely one stalls and drags the run out. Add others via a `models.yaml` `invoke` template only when needed |
| **Plain-language wrap-up** | The result is delivered as a chat summary (done / conclusion / judgment / next step), not a document you must open |
| **Autonomous or confirm** | Chosen up front: the lead acts on the result automatically, or pauses for your go-ahead |
| **Adversarial Round 4** | 4 mandatory stress tests — the part that actually reshapes proposals |
| **Audit / trace archive** | `final.md` + round files keep the full reasoning trail (positions, source anchors) for revisiting and future tuning |
| **Output quality control** | Two-layer validation (transport + semantic) catches CLI garbage: auth prompts, empty / noisy output |
| **Graceful degradation** | If Codex is down, falls back to single-model and says so honestly |
| **Anti-pattern guards** | Fights consensus bias, rubber-stamp reviews, abstract-only discussion |

## File Structure

```
skills/jvever-cross-review/
  SKILL.md                        Core workflow and instructions
  scripts/
    cross_review_runtime.py       External-CLI execution wrapper + final.md frontmatter check
  references/
    prompt-templates.md           Prompt templates for all rounds
    round4-attack-checklist.md    4 mandatory adversarial checks (detailed)
    evaluation-and-strategies.md  Perspectives, validation, degradation
  templates/
    final.md.tmpl                 Archive template (## 给你 + full trail)
    action.md.tmpl                Optional action list
tests/
  test_cross_review_runtime.py    Regression tests for the wrapper and final.md check
```

## Requirements

- **Primary tool** (runs the skill): any AI coding tool with custom-skill support — [Claude Code](https://claude.ai/code), [Cursor](https://www.cursor.com/), [Trae](https://www.trae.ai/), [Windsurf](https://windsurf.com/)
- **External model**: [Codex CLI](https://github.com/openai/codex) (the default). Any other non-interactive AI CLI can be added via a `models.yaml` `invoke` template.

> Works with Claude alone too (switches perspectives across rounds), but the Claude + Codex pair is the recommended baseline.

## License

[GPL-3.0](LICENSE)
