# Cross-Review

[English](README.md) | [中文](README_CN.md)

面向 AI 编程工具的多模型协作 Skill。默认编排 **Claude（主）+ Codex（外部）** 协同评审、设计、压力测试，得到比单模型更高质量的结论。需要时可通过一行 `invoke` 模板接入其它 CLI。

## 为什么需要 Cross-Review？

单模型评审有天然盲区：一套训练数据，一套思维偏好。Cross-Review 通过以下方式解决：

- **差异化视角**：不同模型发现不同问题。实际使用中，Codex 发现了 Claude 遗漏的架构风险，Claude 捕获了 Codex 忽略的数据流问题。
- **对抗性验证**：Round 4 不只是评审——它主动*攻击*方案，用结构化压力测试暴露隐含假设和过度设计。
- **反共识偏见**：当所有模型都同意时，恰恰最该警惕。Cross-Review 明确防范共享训练数据带来的偏见。

## 工作原理

```
Step 1     任务对齐卡    主模型输出目标/约束/成功标准 + 决策模式    （非阻塞）
Round 1    独立工作      各模型从分配视角独立分析（带成功标准）
Round 2    交叉验证      模型互相验证、质疑、补充
Round 2.5  30 秒对抗     （快速模式）一次攻击防共识偏见
           焦点反驳      （完备模式）解决关键冲突
Round 3    候选综合      （完备模式）主模型提候选方案 + 待检验假设
Round 4    对抗性挑战    （完备模式）Codex 当魔鬼代言人；发现 Critical 回路一次
收尾       聊天汇报 + 留痕  主模型在聊天里讲结论；final.md 存档留痕
```

**两种模式：**
- **快速模式**（2 轮 + 30 秒对抗）—— 多视角 + 轻量对抗
- **完备模式**（4 轮）—— 完整交叉验证 + 对抗性压力测试

### 你真正拿到的：聊天里一段人话收尾

主交付是**流程结束时主模型在聊天窗口说的那段话**——四件事，人话，无轮次代号无黑话：

1. **做了什么** —— 怎么 review 的
2. **评审结论** —— 多模型的核心发现、共识与分歧
3. **主模型的判断** —— 采纳什么、否决什么、为什么
4. **下一步** —— 然后要么等你拍板，要么（你已授权自主）直接去做并回报

`final.md` 和各轮文件（`r1~r5*.md`）作为**留痕档案**保留——给想回溯"为什么这么决定"的你、给接手任务的下游 AI、给未来优化流程的人。你不需要读它们才能拿到结论；真打开了 `final.md`，顶部 `## 给你` 那段就是聊天收尾的存档。

**Round 4 的四项强制压力测试**是核心：

| 检查项 | 目的 |
|--------|------|
| 同类问题回环检测 | 方案是否重新引入了它试图解决的同类问题？ |
| 具体场景走查 | 构造 3+ 个具体用户场景，逐步推演找断裂点 |
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
cp -r cross-review/skills/jvever-cross-review/ .cursor/rules/jvever-cross-review/
```

### 其他工具

```bash
git clone https://github.com/JVever/cross-review.git
ln -s "$(pwd)/cross-review/skills/jvever-cross-review" ~/.claude/skills/jvever-cross-review
```

确认 Codex CLI 可用（`codex exec --help`）即可——默认组合只依赖它这一个外部 CLI。

## 使用方式

自然语言触发，中英文均可：

```
帮我交叉评审一下这个架构方案
```
```
让 Claude 和 Codex 一起评审 docs/prd.md
```

如果想让主模型直接按结果执行、不用问你，开头说一声（"你决定 / 直接做"），它会自主跑完并回报；否则它在收尾后停下等你拍板。

## 适用场景

- **技术评审**：架构、代码审查、API 设计、迁移方案
- **产品/策略**：PRD、商业计划、GTM、竞品分析
- **创作/探讨**：写作、头脑风暴、开放讨论
- **重大决策**：任何单一视角不够的场景

## 核心特性

| 特性 | 说明 |
|------|------|
| **固定可靠的双模型** | 默认 Claude + Codex——CLI 越多越容易某个卡死、把流程拖长。需要时才用 `models.yaml` 的 `invoke` 模板加别的 |
| **人话收尾** | 结论以聊天汇报交付（做了什么 / 结论 / 判断 / 下一步），不是一份你得打开的文档 |
| **自主或确认** | 开头选定：主模型按结果自动执行，或停下等你拍板 |
| **对抗性 Round 4** | 4 项强制压力测试——真正重塑方案的环节 |
| **留痕档案** | `final.md` + 各轮文件保留完整推理链（各方立场、来源锚点），供回溯和未来优化 |
| **输出质量控制** | 两层校验（传输 + 语义）挡住 CLI 垃圾：认证提示、空输出、噪声 |
| **优雅降级** | Codex 挂了就降级为单模型，并如实说明 |
| **反模式防护** | 对抗共识偏见、橡皮图章评审、纯抽象讨论 |

## 文件结构

```
skills/jvever-cross-review/
  SKILL.md                        核心工作流和指令
  scripts/
    cross_review_runtime.py       外部 CLI 执行包装器 + final.md frontmatter 校验
  references/
    prompt-templates.md           各轮 Prompt 模板
    round4-attack-checklist.md    4 项强制对抗检查（详细）
    evaluation-and-strategies.md  视角分配、校验、降级
  templates/
    final.md.tmpl                 留痕档案模板（## 给你 + 完整脉络）
    action.md.tmpl                可选行动清单
tests/
  test_cross_review_runtime.py    包装器与 final.md 校验的回归测试
```

## 环境要求

- **主工具**（运行 skill）：任何支持自定义 Skill 的 AI 编程工具 —— [Claude Code](https://claude.ai/code)、[Cursor](https://www.cursor.com/)、[Trae](https://www.trae.ai/)、[Windsurf](https://windsurf.com/)
- **外部模型**：[Codex CLI](https://github.com/openai/codex)（默认）。其它非交互 AI CLI 可通过 `models.yaml` 的 `invoke` 模板接入。

> 也可仅用 Claude（在不同轮次切换视角），但推荐 Claude + Codex 这个基线组合。

## 许可证

[GPL-3.0](LICENSE)
