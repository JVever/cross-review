---
name: jvever-cross-review
description: "Multi-model collaboration: orchestrate multiple AI models to review, discuss, analyze, or co-design together. 当用户希望与其他模型协作时使用，如「和 Gemini 一起讨论」「让 Claude 和 Codex 一起看看这个方案」「用多个 AI 帮我分析」「和其他模型一起审一下」「交叉评审」「多模型协作」「多模型讨论」「multi-model review」「collaborative review」「discuss with Gemini」「review with multiple models」。适用于方案评审、架构设计、代码审查、问题探讨、内容创作等需要多视角或交叉验证的场景。"
---

# 多模型协作方法论

## 方法论概述

### 核心理念

通过编排多个 AI 模型协同工作，利用不同模型的差异化能力，实现比单模型更高质量的输出。

适用于任何需要多模型协同的任务，包括但不限于：
- 评审已有方案（技术方案、产品 PRD、架构设计等）
- 从零设计方案（运营计划、产品方案、技术架构等）
- 探讨问题（技术选型、方向决策、方案对比等）
- 内容创作（文章写作、营销方案等）

### 两种模式

| 模式 | 轮次 | 适用场景 |
|------|------|----------|
| 快速模式 | 2 轮 | 相对明确的任务，需要多视角但不需要深度对抗 |
| 完备模式 | 4 轮（含可选 2.5 轮） | 复杂/高风险/高不确定性任务，需要充分的交叉验证和对抗性检验 |

**模式选择逻辑：**

1. **用户明确表达意向** → 直接采用
   - "完备的""充分讨论""深入设计""全面评审""好好设计一下" → 完备模式
   - "快速""简单看看""帮我过一下""简要评审" → 快速模式
2. **无法从用户表达判断** → 主模型基于任务复杂度给出建议，由用户确认

### 快速模式流程

| 轮次 | 名称 | 目的 | 模式 |
|------|------|------|------|
| Round 1 | 独立工作 | 多视角并行完成任务 | 并行 |
| Round 2 | 交叉验证与综合 | 互相验证补充 + 综合最终输出 | 并行 + 主模型综合 |

### 完备模式流程

| 轮次 | 名称 | 目的 | 模式 |
|------|------|------|------|
| Round 1 | 独立工作 | 多视角并行完成任务 | 并行 |
| Round 2 | 交叉验证 | 互相质疑与补充 | 并行 |
| Round 2.5 | 焦点反驳（可选） | 解决 Round 2 中的关键冲突 | 并行，仅在有未解决关键冲突时触发 |
| Round 3 | 候选综合 | 综合候选方案 + 假设账本 + 未解冲突 | 主模型主导 |
| Round 4 | 对抗性挑战 | 分工攻破方案，找出遗漏 | 并行，对抗性，按检查项分工 |

### 三大反模式警示

1. **共识偏见**：多个模型得出相同结论 ≠ 结论正确。共识可能来自相同的训练数据偏见。
2. **确认式终审**：终审轮只做"我同意"式确认，没有新的发现 → 终审形同虚设。
3. **纯抽象讨论**：只在抽象层面讨论，不落地到具体场景和操作路径 → 遗漏实际问题。

### 交付目标（所有轮次为此服务）

用户从 cross-review 拿走的东西只有三件：
1. **决策**：最终做什么、不做什么、为什么
2. **行动**：下一步具体执行项
3. **溯源能力**：想追问"为什么这么决定"时能翻回讨论

`final.md` 必须自包含地回答这三件事——读完它用户不应再需要让模型口头解释。所有流程改动以此为目标函数。

---

## 前置准备

### Step 1：理解任务 + 任务对齐卡

请用户描述任务目标。任务可以是：
- 评审已有的文档、方案或代码（提供文件路径、文本内容或其他材料）
- 从零设计一个方案（描述需求和约束）
- 探讨一个问题（描述问题背景和期望产出）
- 其他任何需要多模型协同的工作

阅读并充分理解任务目标、背景和约束条件。

**任务对齐卡（非阻塞展示给用户）**：主模型读完任务后，输出一张对齐卡直接展示给用户，**不等待用户确认，立即进入 Step 2**。用户若要调整只需打断或追加说明：

```markdown
## 任务对齐
- **目标**：[一句话]
- **关键约束**：[≤ 3 条]
- **成功标准**：[final.md 要回答什么问题——这是整个流程的目标函数]
- **任务类型**：[review | design | discuss | create]
- **模式建议**：[quick | full] — 理由
- **视角分配**：A=... / B=... / C=...
- **预期产出**：final.md（强模板）+ action.md（仅当长清单时）
- **同项目历史**：[检测到的 run-xxx，提议 supersedes 关系 | 无历史]
```

**关键字段**：
- **成功标准** 将被嵌入每个外部模型的 R1 prompt 中（见 `references/prompt-templates.md`），让所有模型从第一轮起服务于同一目标。
- **任务类型** 决定 final.md 第 3 节的字段名（决策 / 修复 / 方案要点 / 结构要点）。
- **同项目历史** 若存在更早的 run 且未被 supersede，询问用户是否标记为 `superseded_by` 当前 run（见 §supersedes 机制）。

对齐卡保存到 `run-*/task-alignment.md`，并作为 `final.md` §1 的数据源。

### Step 2：确认参与协作的模型（含 CLI 配置持久化）

> **核心原则：模型无关。** 不假设当前主模型是谁，不假设外部模型是谁。

#### 2a. 启动路径选择

首先检查是否存在已保存的 CLI 配置文件 `~/.config/cross-review/models.yaml`。如存在 `~/.config/cross-review/registry.json`，一并读取其中的运行时记忆（已验证模型路径、CLI 版本、catalog 刷新时间）：

**路径 A — 热启动**（配置存在 + healthcheck 通过）：
1. 读取配置文件
2. 对每个模型执行配置中记录的 `healthcheck` 命令（纯本地检查，不调用模型，<1 秒完成）
3. 如果某个 CLI 的版本发生变化，或 registry 中的模型 catalog 已过期，则刷新对应的运行时记忆
4. 全部通过 → **非阻塞通知**用户：`已加载 CLI 配置：codex, gemini, crush。如需更换请直接说。`
5. 直接跳到 Step 2d，不等待用户确认

**路径 B — 冷启动**（配置不存在）：
- 进入 Step 2b（首次使用的完整引导流程）

**路径 C — 异常回退**（配置存在但 healthcheck 失败 / 用户指定了配置中没有的模型）：
1. 告知用户哪个 CLI 检查失败
2. 仅对失败的 CLI 重新引导（不影响其他已通过的 CLI）
3. 更新配置文件

#### 2b. 检测与确认 CLI 工具

1. **用户已指定模型**（如"用 Codex 和 GLM-4.7"）→ 确认对应 CLI 命令
2. **用户未指定** → 自动检测 + 询问：
   - 运行 `which codex gemini crush aider` 等命令探测可用的 CLI 工具
   - 展示检测结果，请用户确认使用哪些

3. **确认调用方式**：对每个外部 CLI 工具，确认其非交互模式的调用格式：

| CLI 工具 | 推荐调用格式 |
|----------|-------------|
| Codex CLI | 由 `scripts/cross_review_runtime.py execute --model codex` 统一封装 |
| Gemini CLI | 由 `scripts/cross_review_runtime.py execute --model gemini` 统一封装 |
| Crush CLI | 由 `scripts/cross_review_runtime.py execute --model crush --requested-model <alias>` 统一封装 |
| 其他工具 | 由用户提供调用格式，必要时通过 `invoke` 模板兜底 |

> **Codex 专用说明**：必须使用 `--output-last-message` 只提取最终回答，避免 session 元数据、thinking blocks、命令日志混入输出。`--ephemeral` 避免留下无用 session 文件。
> **Crush 专用说明**：使用 `--quiet` 隐藏 spinner，确保输出为纯文本。

#### 2c. 保存 CLI 配置

将确认后的配置保存到 `~/.config/cross-review/models.yaml`。运行时记忆单独保存在 `~/.config/cross-review/registry.json`，用于记录 canonical model path、CLI 版本和 catalog 刷新结果：

```yaml
# cross-review CLI 配置
# 由 cross-review skill 自动生成，用户可手动编辑
schema_version: 2
last_updated: 2026-03-25
last_verified: 2026-03-25T10:00:00+08:00

models:
  codex:
    cli_path: /opt/homebrew/bin/codex
    invoke: 'echo "{prompt}" | codex exec --full-auto --output-last-message {output_file} --color never --ephemeral'
    healthcheck: 'codex exec --help >/dev/null 2>&1'
    notes: "OpenAI Codex CLI"

  gemini:
    cli_path: /opt/homebrew/bin/gemini
    model_name: gemini-3.1-pro-preview
    invoke: 'gemini -m gemini-3.1-pro-preview -p "{prompt}" > {output_file}'
    healthcheck: 'gemini -v >/dev/null 2>&1'
    notes: "Google Gemini CLI pinned to Gemini 3.1 Pro Preview"

  # 用户自定义示例：
  # crush:
  #   cli_path: /opt/homebrew/bin/crush
  #   model_name: GLM-4.7
  #   catalog: 'crush models'
  #   invoke: 'crush run --quiet "{prompt}" > {output_file}'
  #   healthcheck: 'crush models >/dev/null 2>&1'
  #   notes: "智谱 GLM via Crush CLI"
```

告知用户：`CLI 配置已保存到 ~/.config/cross-review/models.yaml，运行时记忆会保存到 ~/.config/cross-review/registry.json。后续使用将自动加载，无需重复确认。如需修改，直接编辑该文件或告知我即可。`

#### 2d. 设定模型变量

将确认后的调用方式记录为变量，后续流程统一使用：
- `MODEL_A_NAME` / `MODEL_A_CMD` — 主模型（即当前执行本 skill 的模型）
- `MODEL_B_NAME` / `MODEL_B_CMD` — 外部模型 1
- `MODEL_C_NAME` / `MODEL_C_CMD` — 外部模型 2

> **模型名 → CLI 映射规则**：当用户说"用 GLM-5.1"或"用 GLM5.1"时，主模型应先查阅配置文件中哪个 CLI 对应该模型（如 `crush`），再查阅 `registry.json` 中最近一次验证成功的 canonical target（如 `zai/glm-5.1`）。只有在记忆缺失、catalog 过期或 CLI 版本变化时，才重新探测并更新记忆。Gemini 这类已有稳定目标模型的 CLI，优先在 `models.yaml` 里显式写 `model_name` 并通过 `-m` 锁定，避免 CLI 默认 routing 把请求切到其他模型。

### Step 3：协作视角分配

主模型根据任务类型，动态确定各模型的主责视角。以下为不同任务类型的参考示例：

**技术类任务**（代码评审、架构设计、API 设计等）：
- 视角 A：架构一致性与数据流分析
- 视角 B：技术实现可行性与风险
- 视角 C：边界条件、用户体验与替代方案

**产品/策略类任务**（PRD、运营计划、商业策略等）：
- 视角 A：逻辑自洽性与论证完备性
- 视角 B：可行性与资源风险
- 视角 C：用户影响与替代路径

**创作/探讨类任务**（文章写作、方案设计、开放讨论等）：
- 视角 A：结构完整性与核心论点
- 视角 B：受众适配性与表达效果
- 视角 C：创新性与差异化视角

以上仅为参考。主模型应根据具体任务动态调整视角定义，用户也可直接指定自定义视角。

> **关键原则：** 视角分配是"主责重点"，不是"唯一视角"。每个模型在优先覆盖主责视角的同时，应自由报告任何它发现的重要内容，不因"这不是我的主责"而忽略。

**分配规则：**

| 模型数量 | 分配策略 |
|----------|----------|
| 3 个模型 | 主模型 → 视角 A，外部模型 1 → 视角 B，外部模型 2 → 视角 C |
| 2 个模型 | 主模型 → 视角 A + C，外部模型 → 视角 B |
| 1 个模型 | 主模型在不同轮次中切换视角 |

### Step 4：创建输出目录 + 检查历史 run

在当前工作目录或项目根目录下创建带时间戳的运行目录：

```
cross-review-records/run-{YYYYMMDD-HHmm}/
```

**启动时做两件事**：

1. **历史残留归档**（F3）：检测 `cross-review-records/` 根目录下非 `run-*/` 格式的老文件（如 `final-output-ws.md`、`round1-claude.md` 等早期命名），自动移入 `cross-review-records/_archive/` 子目录。向用户报告一次："已归档 N 个早期文件到 _archive/"，不阻塞。

2. **supersedes 关系**（Q5 盲点补救）：扫描 `cross-review-records/run-*/final.md`，找出最新的、`status: active` 的 run。若存在且其任务与当前任务主题相关：
   - 询问用户："检测到 `run-xxxxxx` 讨论的是同主题。要将其标记为已被本 run 取代吗？（default: yes）"
   - 用户确认后：旧 run 的 `final.md` frontmatter 更新 `status: superseded`、`superseded_by: run-<new>`，文件顶部插入红框提示
   - 新 run 的 `final.md` frontmatter 写入 `supersedes: run-<old>`
   - 维护 `cross-review-records/current.md`（或 symlink）指向最新有效 run 的 final.md

这两步可通过 `scripts/cross_review_runtime.py run-init --dir cross-review-records/` 统一执行。

如用户在**同一任务**上重新运行，**永远创建新的 `run-*` 目录**（不覆盖历史），通过 supersedes 关系链接。

---

## 输出契约（所有外部模型调用必须遵守）

### 格式约束

所有发给外部模型的 prompt 必须包含以下约束（在 prompt 模板的末尾追加）：

```
## 输出格式要求
- 只输出最终分析结果。禁止输出思考过程、命令日志、前言后记。
- 建议使用下方的输出骨架，但如果任务需要其他结构，可以调整。
- 简洁优于冗长，但深度优于简洁。宁可分析透彻写 3000 字，也不要为了控制篇幅而省略重要发现。
```

### 输出骨架（评审类）

```markdown
## 结论摘要
[2-3 句话概括核心判断]

## 发现
### [Critical|Major|Minor]-1：[标题]
- **证据**：[具体引用位置或段落]
- **影响**：[不修复会怎样]
- **建议**：[具体改法]

### [Critical|Major|Minor]-2：[标题]
...

## 未决问题
- [不确定但值得关注的点]

## 一句话结论
[整体判断]
```

### 输出骨架（设计/创作类）

```markdown
## 结论摘要
[2-3 句话概括方案核心]

## 方案
### 方案要点 1：[标题]
- **内容**：[具体描述]
- **决策理由**：[为什么这样选]

### 方案要点 2：[标题]
...

## 替代方案与权衡
- [被否决的路径及理由]

## 未决问题
- [不确定但值得关注的点]

## 一句话结论
[整体判断]
```

> Prompt 模板：Read `references/prompt-templates.md` 获取各轮次的完整 prompt 模板。

---

## 输出验证（每次外部模型返回后执行）

> **实现方式**：优先使用 `scripts/cross_review_runtime.py` 的 `execute` 子命令统一执行外部模型调用。该运行层负责记录 stdout、stderr、退出码、耗时、重试次数、校验结果，并强制生成 `status.json`、`logs/`、`invalid/`。

### 两层校验

**传输校验**（自动执行，不通过则标记为失败）：
1. 文件非空且 > 200 字节
2. 不包含认证/登录关键词（`Opening authentication`、`Do you want to continue`、`Y/n`）
3. 不包含 ANSI 转义序列或 JSONL 格式噪声
4. 不包含 CLI 帮助文本（`Usage:`、`--help`）

**语义校验**（自动执行，不通过则标记为低质量）：
1. 包含至少一个预期标题（`## 结论摘要` 或 `## 发现` 或 `## 方案`）
2. 包含至少 1 条发现或 1 个方案要点
3. 包含 `## 一句话结论`

### 失败处理

1. 传输校验失败 → 自动重试一次（使用精简版 prompt）→ 再失败 → 降级（减少该模型）+ 告知用户
2. 语义校验失败 → 标记为低质量输出，告知用户，但仍纳入后续流程（作为弱信号）
3. 无效输出保存到 `invalid/` 子目录，不污染主流程文件；stdout/stderr 原始证据保存在 `logs/` 中

---

## Preflight 检查（每次 run 启动时执行一次，不按轮次重复）

Preflight 在 Step 2a 的热启动路径中自动完成。使用**配置文件中记录的 healthcheck 命令**，仅做 CLI 级检查，不调用模型；CLI 版本变化和 catalog 过期仅触发 registry 刷新，不直接判定模型不可用：

| CLI | Healthcheck 命令 | 验证内容 | 耗时 |
|-----|-----------------|---------|------|
| Codex | `codex exec --help >/dev/null 2>&1` | CLI + 子命令存在 | <1s |
| Gemini | `gemini -v >/dev/null 2>&1` | CLI 存在 + 版本可读 | <1s |
| Crush | `crush models >/dev/null 2>&1` | CLI 存在 + 模型已配置 | <1s |

> **设计原则**：Preflight 只验证"CLI 可执行"。认证和网络问题由首次正式调用 + 输出验证兜底，不在 preflight 中做模型级测试（避免浪费 tokens 和时间）。

- 全部通过 → 进入 Round 1
- 部分失败 → 仅对失败的 CLI 告知用户并降级，不影响已通过的 CLI
- 全部失败 → 告知用户，等待指示

---

## 快速模式（2 轮 + 轻量对抗 + 独立 review）

### Round 1：独立工作（并行）

**目标：** 每个模型以自己的主责视角为重点，独立完成任务。

1. 主模型直接开始工作，产出自己视角的结果
2. 同时用 CLI 命令并行调用外部模型（后台运行）
3. 所有外部模型的 R1 prompt 都必须嵌入 `success_criteria`（从任务对齐卡带入）

> Prompt 模板：Read `references/prompt-templates.md` → "Round 1: Independent Work"

**R1 完成后向用户输出阶段简报**（≤5 行，非阻塞）：
```
R1 完成。{N} 个模型产出有效输出。
核心共识：{一句}
核心分歧：{1-2 条}
下一步：进入 R2 交叉验证
```

**输出文件：** `r1.{model_name}.md`

---

### Round 2：交叉验证

**目标：** 每个模型阅读其他模型的 Round 1 输出，进行验证、质疑和补充。

1. 主模型阅读外部模型的 Round 1 成果（已通过 `--output-last-message` 等方式清洗掉元数据噪声）
2. 将其他模型的 Round 1 clean 输出发送给外部模型做交叉验证
3. **仅当某个 Round 1 输出超过 5000 字时**，主模型制作 digest 替代原始输出传递，并在 digest 中标注"完整内容见 r1.{model}.md"

> Prompt 模板：Read `references/prompt-templates.md` → "Round 2: Cross-Validation"

**R2 完成后向用户输出阶段简报**：
```
R2 完成。{关键增量 1-2 条}。
下一步：主模型综合 → 30 秒对抗 → 生成 final.md
```

**输出文件：** `r2.{model_name}.md`

---

### Round 2.5：30 秒轻量对抗（D1，防共识偏见）

**目标：** 快速模式只有 2 轮，无对抗环节。在主模型写完综合草稿后、落盘 final.md 前，用一个外部模型做 ≤500 字的攻击，防止"共识偏见"反模式。

1. 主模型基于 R1 + R2 写一份综合草稿（**在内存中**，不落盘）
2. 把草稿发给一个外部模型（优先选择 R2 阶段发现最多的模型），用精简 prompt 要求"指出最致命的 1-2 个攻击点"
3. 主模型根据攻击点修订草稿

> Prompt 模板：Read `references/prompt-templates.md` → "Quick Mode: 30-Second Devil's Advocate"

**输出文件：** `r2.attack.{model_name}.md`

---

### Round 3：主模型综合 + 独立 Final Review（C1）

**目标：** 生成符合强模板的 `final.md`，并经外部模型独立复核。

1. 主模型按 `templates/final.md.tmpl` 生成 `final.md`（见 §final.md 强模板）
2. 主模型自检硬校验清单 8 项，全部通过才进入下一步
3. 可选自动化校验：`scripts/cross_review_runtime.py check-final --file final.md`
4. **独立 Final Review（C1）**：把 `final.md` 发给一个外部模型，要求回答"是否自包含（TL;DR + 决策 + 行动）"
5. 如 review 结论为 `returned-for-rework`：主模型根据反馈修订 final.md，再次自检，不重新跑 review
6. review 通过后，final.md 标记 `independent_review: pass` 并落盘

> Prompt 模板：Read `references/prompt-templates.md` → "Independent Final Review"

**快速模式综合要求**：不要简单罗列合并各方观点。必须对分歧点做明确裁决并说明理由，对共识点做简要确认。final.md §2 的"分歧与裁决"表格必须反映真实分歧，不可粉饰。

**输出文件：**
- `r2.{model_name}.md` — 各模型的交叉验证
- `r2.attack.{model_name}.md` — 30 秒对抗产出
- `r3.review.{model_name}.md` — 独立 Final Review 产出
- `final.md` — 最终交付文档（硬模板）
- `action.md` — 行动清单（仅当 P0+P1+P2 总数 ≥ 3 条时生成，否则全部内嵌 final.md §5）

---

## 完备模式（4 轮）

### Round 1-2：与快速模式相同

**输出文件：** `r{N}.{model_name}.md`

---

### Round 2.5：焦点反驳（可选，仅在有未解决关键冲突时触发）

**触发条件：** 主模型在 Round 2 综合时发现以下情况之一：
- 两个模型在 Critical/Major 级问题上持相反意见且均有论据
- 某个核心设计决策存在两个以上互斥的合理路径
- Round 2 各方补充后出现了新的重大分歧

**目标：** 针对性解决关键冲突，不做全面重审。

1. 主模型列出 1-3 个未解决的关键冲突点
2. 针对每个冲突点，构造一个聚焦的 prompt，要求各模型**只回应该冲突点**
3. 并行调用外部模型

**输出文件：** `r2.5.{model_name}.md`

---

### Round 3：候选综合（主模型主导）

**目标：** 综合所有发现，提出**候选方案**（非定案），并明确列出待检验的假设和未解冲突。

> **姿态要求**：Round 3 的产出是"候选综合"，不是"最优方案已形成"。措辞上使用"候选""建议""待验证"，避免使用"最终""最优""结论"。

1. 主模型阅读所有 Round 1 + Round 2（+ Round 2.5）输出
2. 按主题聚类，对每个主题综合各方观点
3. 提出候选方案
4. **关键步骤**：为每个方案列出"待检验的假设"和"未解冲突"
5. 将候选综合发送给外部模型做初步审阅（如文档过长，制作 digest 传递）

> 文档结构模板：Read `references/prompt-templates.md` → "Round 3: Candidate Synthesis Structure"

**输出文件：** `r3.synthesis.md`

---

### Round 4：对抗性挑战（并行，全量检查 + 侧重分配）← 核心轮次

**目标：** 对 Round 3 候选方案进行对抗性攻击，尝试找出缺陷。前三轮是"完成任务"，Round 4 是"攻击我们自己的成果"。

1. Read `references/round4-attack-checklist.md` 获取四项强制检查
2. **每个模型都执行全部四项检查**，但通过"侧重分配"确保深度覆盖：

| 模型数量 | 侧重分配 |
|----------|----------|
| 3 个模型 | 模型 B（魔鬼代言人）→ 重点深入 回环检测 + 共识盲点，快速扫描另两项；模型 C → 重点深入 场景走查 + 去掉它试试，快速扫描另两项；主模型 → 综合复核全部四项 |
| 2 个模型 | 外部模型（魔鬼代言人）→ 重点深入全部四项；主模型 → 独立做全部四项 + 综合复核 |

3. 并行调用外部模型，每个模型交付全部四项检查结果（侧重项深入分析，非侧重项快速扫描）

> Prompt 模板：Read `references/prompt-templates.md` → "Round 4: Focused Attack"

**输出文件：**
- `r4.{model_name}.md` — 各模型的对抗性挑战报告

**Round 4 发现 Critical/Major 级问题时的回路机制：**
- 发现 Critical → 回到 Round 3b（只重跑受影响主题），产出 `r3b.synthesis.md`，然后重新进入 Round 4
- 发现 Major → 记录为遗留风险，评估是否需要回路
- 回路最多执行 1 次，避免无限循环

---

### Round 5：生成 final.md + 独立 Final Review（C1，完备模式必做）

**目标：** 完备模式也必须通过独立 Final Review 才能交付 final.md。流程与快速模式 Round 3 相同，只是输入材料多了 R4 对抗结果。

1. 主模型按 `templates/final.md.tmpl` 生成 `final.md`，整合 R4 对抗结果
2. 自检硬校验清单 8 项
3. 把 `final.md` 发给一个外部模型做独立 Final Review
4. 如 `returned-for-rework` → 主模型修订 → 再次自检 → 落盘

> Prompt 模板：Read `references/prompt-templates.md` → "Independent Final Review"

**final.md 必须包含：**
- 经过对抗性挑战后保留的方案（及理由，标注 "R4 未攻破"）
- 被攻破而修改/放弃的方案（及理由，标注 "R4 攻击 N 导致修正"）
- 遗留风险清单（已知但接受的风险）
- 独立 review 结论（`independent_review: pass`）

**输出文件：**
- `r5.review.{model_name}.md` — 独立 Final Review 产出
- `final.md` — 最终交付文档
- `action.md` — 行动清单（条件生成）

---

## final.md 强模板（交付物核心）

**设计理念**：final.md 不是"模型自由写的综合报告"，而是"硬约束下的编译产物"。缺字段即视为未完成，必须返工。目的是让用户拿到 final.md 即可独立回答三个问题，不再需要让模型解释。

### 模板位置

`templates/final.md.tmpl` — 强约束骨架，所有任务类型共用。

### 必填字段

**Frontmatter（8 项）**：
- `task` — 任务一句话
- `mode` — quick / full
- `task_type` — review / design / discuss / create
- `models` — lead + external 列表
- `run_id` — run-YYYYMMDD-HHmm
- `created_at` — ISO8601
- `status` — active / superseded
- `success_criteria` — 直接摘自任务对齐卡

**Frontmatter 可选**：
- `supersedes` / `superseded_by` — supersedes 链
- `synthesis_bias_note` — 主模型 R1 立场与裁决关系一句（C2 压缩版，可留 null）
- `independent_review` — C1 结论（pass / returned-for-rework）

**正文 8 节**：
1. **TL;DR** — 3-5 句，回答"任务/决策/下一步/取舍"四项
2. **任务与约束** — 含成功标准
3. **核心分歧与裁决** — 至少 1 行表格，或显式"无关键分歧"+ R2 补充清单
4. **最终方案** — ≥ 1 个决策，每个含"做什么/为什么/来源"
5. **行动项** — P0 至少 1 条（或显式"无需行动"+ 理由）
6. **被否决的替代路径** — 或写"无"
7. **遗留风险与未决问题** — 或写"无"
8. **附录：讨论脉络** — 折叠摘要

### 硬校验清单（8 项）

主模型交付 final.md 前必须自检（任何一项不通过则必须返工）。可运行 `scripts/cross_review_runtime.py check-final --file final.md` 做结构化校验：

1. frontmatter 8 个必填字段齐全
2. TL;DR ≥ 3 句，四项问题全覆盖
3. §2 分歧表 ≥ 1 行（或显式"无关键分歧"+ R2 补充）
4. 每个决策都含"做什么/为什么/来源"三子字段
5. §5 P0 行动项 ≥ 1 条（或显式"无需行动"+ 理由）
6. §6 遗留风险字段显式填写（没有就写"无"）
7. `task_type` 与模板骨架一致
8. 总行数 ≤ 800（超出则内容下沉 action.md 或附录）

### 任务类型的字段变体

| task_type | §3 字段名 | §5 典型长度 | action.md 何时独立生成 |
|-----------|-----------|-----------|---------------------|
| review | "修复 N" | 5-20 条 | P0+P1 ≥ 3 条 |
| design | "方案要点 N" | 3-10 条 | 总条数 ≥ 3 |
| discuss | "决策 N" | 1-5 条 | 有明确后续动作时 |
| create | "结构要点 N" | 0-3 条 | 极少独立生成 |

---

## supersedes 机制（多次重跑的权威性）

**问题**：同一任务重跑多次会产生多个 `run-*/final.md`，用户无法判断"哪份是权威"。

**解决**：通过 frontmatter 的 `supersedes` / `superseded_by` 链显式标注版本关系。

### 机制细节

1. **Run 启动时检测**（Step 4 的第 2 项）：扫描 `cross-review-records/run-*/` 下 `status: active` 的 final.md
2. **询问用户**：如发现相关历史 run（同一主题），询问是否标记为 superseded
3. **新旧文件更新**：
   - 新 final.md：`supersedes: run-<old>`
   - 旧 final.md：`status: superseded`, `superseded_by: run-<new>`，顶部插入红框 "⚠️ 本 run 已被 run-xxx 取代"
4. **快捷指针**：`cross-review-records/current.md` 作为 symlink（或文本文件）指向最新 active final.md，方便 `cat current.md` 找到权威结论

### 用户操作
- 不想标记 supersedes（比如两次讨论是不同子问题）：回答 "no"，两个 run 都保持 active
- 要回溯旧方案：`status: superseded` 的 run 仍然保留，可直接 cat 查看

### 脚本支持

```bash
python3 scripts/cross_review_runtime.py mark-superseded \
  --old run-20260410-0915 \
  --new run-20260415-1535
```

---

## 降级策略

| 模型数量 | Round 1-2 | Round 3 | Round 4 |
|----------|-----------|---------|---------|
| 3 个（最佳） | 各自独立主责视角 | 主模型综合 | 按检查项分工 + 魔鬼代言人 |
| 2 个 | 主模型承担视角 A+C，外部模型承担视角 B | 主模型综合，外部模型审阅 | 外部模型做魔鬼代言人 |
| 1 个（最低） | 主模型在不同 prompt 中切换主责视角 | 主模型综合 | 用显式对抗性 prompt 做自我攻击 |

---

## 中间结果管理

### 目录结构

```
cross-review-records/
  current.md              # 最新 active run 的快捷指针
  _archive/               # 老格式文件自动归档（F3）

  run-20260323-1640/
    task-alignment.md     # 任务对齐卡（Step 1 产出，驱动全流程）
    status.json           # 每次外部调用的结构化状态
    manifest.json         # 运行元数据（不负责状态机续跑）
    logs/                 # stdout / stderr / attempt output
    invalid/              # 验证失败的输出

    r1.claude.md          # Round 1 各模型输出
    r1.codex.md
    r1.gemini.md
    r1.digest.md          # （可选）当某输出 >5000 字时的摘要

    r2.claude.md          # Round 2 各模型输出
    r2.codex.md
    r2.attack.codex.md    # 快速模式：30 秒对抗（D1）
    r2.5.codex.md         # 完备模式：焦点反驳（如有）

    r3.synthesis.md       # 完备模式：候选综合
    r3.review.codex.md    # 快速模式：独立 Final Review（C1）
    r3b.synthesis.md      # 完备模式：R4 回路后修订

    r4.codex.md           # 完备模式：对抗性挑战
    r4.gemini.md
    r5.review.gemini.md   # 完备模式：独立 Final Review（C1）

    final.md              # 最终交付文档（硬模板，自包含）
    action.md             # （可选）完整行动清单，仅当 ≥ 3 条时生成
```

### 文件角色

| 文件 | 谁读 | 何时读 | 必读？ |
|------|------|--------|-------|
| `final.md` | 用户 + 下游 AI | 想知道决策/行动 | 必读 |
| `action.md` | 执行者 | 照单执行 | 仅当长清单 |
| `task-alignment.md` | 流程内部 | R1 prompt 生成时 | AI 读 |
| `r*.md` | 流程内部 + 想追溯的用户 | 想追问"为什么" | 可选 |
| `current.md` | 用户 | 快速定位权威 run | 经常 |

### 文件命名规范

**严格格式**：`r{轮次}.{模型名}.md`。禁止自由添加后缀（如 `-ws`、`-session-fix`、`-v2`）。

特殊文件：
- `status.json` — 外部调用状态、重试和校验记录
- `r{N}.digest.md` — （可选）当某轮输出 >5000 字时的摘要
- `r3.synthesis.md` — Round 3 候选综合
- `r3b.synthesis.md` — Round 4 回路后的修订综合（如有）
- `final.md` — 最终方案
- `manifest.json` — 运行元数据

### manifest.json

每次运行开始时创建，每轮完成后更新：

```json
{
  "run_id": "run-20260323-1640",
  "mode": "full",
  "task_summary": "评审 LightCraft iOS 架构方案",
  "models": {
    "lead": "claude",
    "external": ["codex", "gemini"]
  },
  "steps": {
    "r1": { "status": "completed", "models_completed": ["claude", "codex", "gemini"] },
    "r2": { "status": "completed", "models_completed": ["claude", "codex"] },
    "r3": { "status": "completed" },
    "r4": { "status": "in_progress", "models_completed": ["codex"] }
  },
  "retries": { "r1.gemini": 1 },
  "created_at": "2026-03-23T16:40:00+08:00",
  "updated_at": "2026-03-23T17:15:00+08:00"
}
```

**断点续跑**：如果流程中断，下次启动时检查最近的 `manifest.json`，从上次完成的步骤继续。

### 保存与清理

- **默认保存**：每轮完成后，将各模型的输出保存到运行目录
- **跨轮传递**：传递给外部模型的上下文使用 clean 输出（已通过 `--output-last-message` 等方式清洗掉元数据噪声）。仅当某个输出超过 5000 字时，主模型制作 digest 替代传递
- **结束后处理**：全部完成后，询问用户是否保留中间过程文档，还是只保留 `final.md`
- **用户主动跳过**：如果用户在启动时明确表示不需要保存过程，则只输出最终结果

---

## 执行检查清单

### 每轮完成后，主模型自检

- [ ] 所有输出已保存到运行目录
- [ ] 文件命名遵循 `r{N}.{model_name}.md` 格式
- [ ] 外部模型输出已通过传输校验和语义校验
- [ ] 当前轮次的所有模型都已完成（后台任务已返回结果）
- [ ] 已向用户报告**阶段简报**（共识 + 分歧 + 下一步，≤5 行，非阻塞）
- [ ] `manifest.json` 已更新

### final.md 交付前，主模型必须过硬校验 8 项

见 §final.md 强模板 中的"硬校验清单"。任何一项不通过 → 返工。
可运行：`python3 scripts/cross_review_runtime.py check-final --file <path-to-final.md>`

### 独立 Final Review 通过后

- [ ] `final.md` frontmatter `independent_review: pass`
- [ ] 若长行动清单已拆出 → `action.md` 已落盘
- [ ] `cross-review-records/current.md` 指向本 run
- [ ] 若存在 supersedes 关系，旧 run 已更新 `status: superseded`
- [ ] 向用户提供**总结**（TL;DR 的简化版）+ 下一步动作的 CTA（"建议先执行 P0-1 到 P0-N"）
- [ ] 询问用户是否保留中间过程文档（r1/r2/r3 系列）
