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
| 3 (optimal) | Each with independent focus perspective | Lead model synthesizes | Dedicated devil's advocate |
| 2 | Lead model takes Perspective A+C, external takes B | Lead model synthesizes, external reviews | External as devil's advocate |
| 1 (minimum) | Lead model switches perspectives via different prompts | Lead model synthesizes | Use explicit adversarial prompt for self-attack |

---

## Error Handling Principles

- Before calling an external model, do a brief connectivity test
- If a model fails or times out in a round, use degradation strategy to continue with fewer models
- Lead model should verify external model output is valid (non-empty, not error messages)
- Completed round reports are saved in the output directory; process can resume from last completed round after interruption
- Any degradation or anomaly must be clearly communicated to the user

---

## Intermediate Results Management

- **Default: save** -- after each round, save each model's output to `cross-review-records/`
- **Purpose:**
  - Ensure process can recover after interruption (find context from existing files)
  - Allow user to review each model's output during the process
  - Serve as audit trail for final decisions
- **Post-completion:** Ask user whether to keep intermediate documents or only the final result
- **User opt-out:** If user explicitly says no saving at startup, only output final result

---

## Execution Checklist

After each round, lead model self-checks:

- [ ] All outputs saved to `cross-review-records/`
- [ ] File naming follows `round{N}-{model_name}.md` format
- [ ] All models in current round have completed (background tasks returned)
- [ ] Key findings summary reported to user

After all rounds complete:

- [ ] `final-output.md` contains the final plan/conclusion
- [ ] User provided with summary and suggested next steps
- [ ] User asked whether to keep intermediate documents
