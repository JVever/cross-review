# Cross-Review

[English](README.md) | [中文](README_CN.md)

多模型协作 Skill，适用于支持自定义 Skill 的 AI 编程工具，如 [Claude Code](https://claude.ai/code)、[Cursor](https://www.cursor.com/)、[Trae](https://www.trae.ai/)、[Windsurf](https://windsurf.com/) 等。

编排多个 AI 模型协同工作，通过交叉验证和对抗性测试，产出比单模型更高质量的结果。

## 工作原理

```
Round 1: 独立工作       每个模型从分配的视角独立分析（并行）
Round 2: 交叉验证       模型互相审查发现、标记分歧（并行）
Round 3: 方案综合       主模型整合所有洞察，形成统一方案
Round 4: 对抗性挑战     "魔鬼代言人"尝试攻破方案（并行）
```

两种模式：
- **快速模式**（2 轮）—— 相对明确的任务，需要多视角但不需要深度对抗
- **完备模式**（4 轮）—— 复杂/高风险任务，需要充分的交叉验证和对抗性检验

## 安装

### Claude Code

```bash
/plugin marketplace add JVever/cross-review
```

### Cursor / Windsurf

克隆仓库，将 skill 复制到项目的规则目录：

```bash
git clone https://github.com/JVever/cross-review.git
cp -r cross-review/skills/cross-review/ .cursor/rules/cross-review/
```

### 其他工具

克隆仓库后，将 skill 文件添加或链接到你的工具读取指令的目录：

```bash
git clone https://github.com/JVever/cross-review.git
# Claude Code 手动安装：
ln -s "$(pwd)/cross-review/skills/cross-review" ~/.claude/skills/cross-review
# 或复制到你使用的工具的 rules/skills 目录
```

## 使用方式

在你的 AI 编程工具中用自然语言触发：

```
帮我交叉评审一下这个方案
```

```
和 Gemini 一起讨论一下这个架构设计
```

```
让几个模型一起来评审一下 docs/prd.md
```

Skill 会自动：
1. 让你描述任务目标和材料
2. 检测已安装的 AI CLI 工具（或让你指定）
3. 为每个模型分配差异化视角
4. 执行评审轮次并输出最终综合方案

## 核心特性

- **模型无关**：适配任意 AI CLI 工具组合
- **优雅降级**：从 3 个模型降到 1 个，自动调整策略
- **反模式防护**：主动对抗共识偏见、橡皮图章式评审、纯抽象讨论
- **可恢复**：保存中间结果，中断后可从上次完成的轮次继续
- **双语触发**：同时支持中英文命令

## 文件结构

```
skills/cross-review/
  SKILL.md                                  核心工作流和指令
  references/
    prompt-templates.md                     外部模型的 Prompt 模板
    round4-attack-checklist.md              4 项强制对抗性检查
    evaluation-and-strategies.md            视角分配和降级策略
```

## 环境要求

- **主工具**（运行 skill）：任何支持自定义 Skill 的 AI 编程工具 —— [Claude Code](https://claude.ai/code)、[Cursor](https://www.cursor.com/)、[Trae](https://www.trae.ai/)、[Windsurf](https://windsurf.com/) 等
- **外部模型**（通过 CLI 调用，实现多模型协作）：至少一个：
  - [Codex CLI](https://github.com/openai/codex)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli)
  - [Claude Code](https://claude.ai/code)、[Kimi Code](https://github.com/anthropics/kimi-code)、[OpenCode](https://github.com/anthropics/opencode) 或任何支持非交互模式的 AI CLI 工具

> 单模型也可以使用（通过在不同轮次切换视角），但多模型协作效果显著更好。

## 许可证

[GPL-3.0](LICENSE)
