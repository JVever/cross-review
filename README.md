# Cross-Review

Multi-model collaboration skill for [Claude Code](https://claude.ai/code), [Codex CLI](https://github.com/openai/codex), [Gemini CLI](https://github.com/google-gemini/gemini-cli), and other AI coding tools.

Orchestrate multiple AI models to collaboratively review designs, audit code, critique proposals, and stress-test solutions -- producing higher quality output than any single model alone.

## How It Works

```
Round 1: Independent Work     Each model analyzes from its assigned perspective (parallel)
Round 2: Cross-Validation     Models review each other's findings, flag disagreements (parallel)
Round 3: Synthesis            Lead model merges all insights into a unified proposal
Round 4: Adversarial Attack   "Devil's advocate" tries to break the proposal (parallel)
```

Two modes available:
- **Quick mode** (2 rounds) -- for straightforward tasks needing multiple viewpoints
- **Full mode** (4 rounds) -- for complex/high-risk tasks needing adversarial testing

## Installation

### Claude Code

```bash
/plugin marketplace add JVStop/cross-review
```

### Manual Installation

Clone and symlink to your skills directory:

```bash
git clone https://github.com/JVStop/cross-review.git
ln -s "$(pwd)/cross-review/skills/cross-review" ~/.claude/skills/cross-review
```

## Usage

In Claude Code, trigger the skill with natural language:

```
cross review this architecture design
```

```
帮我交叉评审一下这个方案
```

```
multi-model review of the PRD at docs/prd.md
```

The skill will:
1. Ask you to describe the task and materials
2. Detect available AI CLI tools (or ask you to specify)
3. Assign differentiated perspectives to each model
4. Run the review rounds and produce a final synthesis

## Key Features

- **Model-agnostic**: Works with any combination of AI CLI tools
- **Graceful degradation**: Adapts from 3 models down to 1 with adjusted strategies
- **Anti-pattern guards**: Actively fights consensus bias, rubber-stamp reviews, and abstract-only discussion
- **Resumable**: Saves intermediate outputs so interrupted sessions can continue
- **Bilingual triggers**: Responds to both English and Chinese commands

## File Structure

```
skills/cross-review/
  SKILL.md                                  Core workflow and instructions
  references/
    prompt-templates.md                     All prompt templates for external models
    round4-attack-checklist.md              4 mandatory adversarial checks
    evaluation-and-strategies.md            Perspective assignment and degradation strategy
```

## Requirements

- [Claude Code](https://claude.ai/code) (primary)
- At least one additional AI CLI tool for multi-model collaboration:
  - [Codex CLI](https://github.com/openai/codex)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli)
  - [Aider](https://github.com/paul-gauthier/aider)
  - Or any AI tool with a non-interactive CLI mode

> The skill also works with a single model by switching perspectives across rounds, but multi-model setups produce significantly better results.

## License

[MIT](LICENSE)
