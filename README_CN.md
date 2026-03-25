# Cross-Review

[English](README.md) | [中文](README_CN.md)

多模型协作 Skill，适用于 AI 编程工具。编排 Claude、Codex、Gemini、GLM 等多个模型协同评审、设计和压力测试——产出比单模型更高质量的结果。

## 为什么需要 Cross-Review？

单模型评审有天然盲区：一套训练数据，一套思维偏好。Cross-Review 通过以下方式解决：

- **差异化视角**：不同模型能发现不同问题。实际使用中，Codex 发现了 Claude 遗漏的架构风险，Claude 捕获了 Codex 忽略的数据流问题。
- **对抗性验证**：Round 4 不只是评审——它主动*攻击*方案，用结构化的压力测试暴露隐含假设和过度设计。
- **反共识偏见**：当所有模型都同意时，恰恰最需要警惕。Cross-Review 明确防范共享训练数据带来的偏见。

## 工作原理

```
Round 1    独立工作       每个模型从分配的视角独立分析                 （并行）
Round 2    交叉验证       模型互相审查发现、标记分歧                   （并行）
Round 2.5  焦点反驳       解决关键冲突后再进入综合                     （可选）
Round 3    候选综合       主模型提出候选方案 + 假设账本                 （主模型主导）
Round 4    对抗性挑战     全量检查 + 侧重分配，压力测试方案             （并行）
```

**两种模式：**
- **快速模式**（2 轮）—— 多视角评审，无需深度对抗
- **完备模式**（4 轮，含可选 2.5 轮）—— 完整交叉验证 + 对抗性压力测试

**Round 4 的四项强制压力测试**是本 skill 的核心特色：

| 检查项 | 目的 |
|--------|------|
| 同类问题回环检测 | 方案是否重新引入了它试图解决的同类问题？ |
| 具体场景走查 | 构造 3+ 个具体用户场景，逐步推演寻找断裂点 |
| "去掉它试试"测试 | 方案中每个新组件，去掉后系统还能工作吗？ |
| 共识盲点检测 | 所有模型不约而同接受了哪些未经验证的假设？ |

## 安装

### Claude Code

```bash
/skill add JVever/cross-review
```

### Cursor / Windsurf

```bash
git clone https://github.com/JVever/cross-review.git
cp -r cross-review/skills/cross-review/ .cursor/rules/cross-review/
```

### 其他工具

```bash
git clone https://github.com/JVever/cross-review.git
# Claude Code 手动安装：
ln -s "$(pwd)/cross-review/skills/cross-review" ~/.claude/skills/cross-review
# 或复制到你使用的工具的 rules/skills 目录
```

## 使用方式

自然语言触发，中英文均可：

```
帮我交叉评审一下这个架构方案
```
```
和 Gemini 一起讨论一下这个设计
```
```
让 Codex 和 GLM 一起来评审 docs/prd.md
```

**首次使用**：自动检测 CLI 工具、确认调用方式、保存配置。**后续使用**：秒级热启动——加载配置、运行轻量健康检查、直接进入 Round 1。

## 适用场景

- **技术评审**：架构设计、代码审查、API 设计、迁移方案
- **产品/策略**：PRD、商业计划、GTM 策略、竞品分析
- **创作/探讨**：文章写作、头脑风暴、开放讨论、内容策略
- **重大决策**：任何单一视角不够的场景

## 核心特性

| 特性 | 说明 |
|------|------|
| **模型无关** | 适配任意 AI CLI：Codex、Gemini、Crush (GLM)、Claude Code 等 |
| **秒级热启动** | CLI 配置跨会话持久化；亚秒级健康检查；无需重复设置 |
| **输出质量控制** | 建议输出骨架 + 两层验证（传输校验 + 语义校验） |
| **Clean 输出** | Codex: `--output-last-message` 去噪；Crush: `--quiet` 隐藏 spinner |
| **优雅降级** | 从 3 个模型 → 2 → 1，自动调整策略 |
| **反模式防护** | 主动对抗共识偏见、橡皮图章评审、纯抽象讨论 |
| **断点续跑** | `manifest.json` 追踪进度，中断后从上次完成的步骤继续 |
| **对抗性 Round 4** | 4 项强制压力测试，侧重分配确保深度覆盖 |

## 文件结构

```
skills/cross-review/
  SKILL.md                                  核心工作流和指令
  references/
    prompt-templates.md                     各轮次的 Prompt 模板
    round4-attack-checklist.md              4 项强制对抗性检查（详细操作指南）
    evaluation-and-strategies.md            视角分配、降级策略、验证规则
```

## 环境要求

- **主工具**（运行 skill）：任何支持自定义 Skill 的 AI 编程工具 —— [Claude Code](https://claude.ai/code)、[Cursor](https://www.cursor.com/)、[Trae](https://www.trae.ai/)、[Windsurf](https://windsurf.com/) 等
- **外部模型**（通过 CLI 调用）：至少一个：
  - [Codex CLI](https://github.com/openai/codex) (OpenAI)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli) (Google)
  - [Crush CLI](https://charm.sh/crush) (GLM / 智谱 AI, by Charm)
  - 任何支持非交互模式的 AI CLI 工具

> 单模型也可使用（在不同轮次切换视角），但多模型协作效果显著更好。

## 许可证

[GPL-3.0](LICENSE)
