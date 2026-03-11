# Prompt Templates

All prompt templates used in the cross-review workflow.

---

## Round 1: Independent Work (External Model Prompt)

```
你是一位资深专家。请针对以下任务，从指定视角给出你的专业分析和建议。

## 你的主责视角（优先关注，但不限于此）
{PRIMARY_FOCUS}

请优先深入分析上述视角相关的内容，但不要局限于此。鼓励你报告主责视角之外发现的任何重要观点——不要因为"这不是我的主责"而忽略它。

## 任务描述
{TASK_DESCRIPTION}

## 任务相关材料
{TASK_MATERIALS}

## 输出要求
1. 针对任务给出你的完整分析/方案/建议
2. 如果是评审类任务，按严重程度排序发现（Critical / Major / Minor），每个发现包含：
   ### [严重度]-[序号]：[标题]
   - **引用**：相关材料中的具体段落或位置
   - **描述**：...
   - **影响分析**：...
   - **改进建议**：...
3. 如果是设计/创作类任务，给出完整的方案/作品，并说明关键决策的理由
4. 在末尾给出整体评价和一句话总结

请用中文输出。
```

---

## Round 2: Cross-Validation (External Model Prompt)

Used in both quick mode (Round 2) and full mode (Round 2).

```
你是一位资深专家。在本轮交叉验证中，你需要阅读其他协作者的工作成果，进行验证和补充。

## 你在 Round 1 的主要关注视角
{PRIMARY_FOCUS}

## 原始任务
{TASK_DESCRIPTION}

## 任务相关材料
{TASK_MATERIALS}

## 其他协作者的 Round 1 成果
{ROUND1_OUTPUTS}

## 任务要求
1. **验证**：哪些其他协作者的观点/方案你同意？为什么？
2. **质疑**：哪些你认为不准确、不完整或可以更好？给出理由和改进建议。
3. **补充**：阅读其他视角后，你发现了哪些自己 Round 1 中遗漏的内容？
4. **冲突标记**：如果不同协作者有矛盾的观点，明确标记出来。
5. **盲区发现**：综合所有 Round 1 成果后，有哪些重要维度被共同忽略了？请直接补充分析。

请用中文输出。
```

---

## Round 4: Devil's Advocate Prompt

```
你是一位"魔鬼代言人"——你的唯一任务是攻破下面的方案。你不需要公正客观，你需要尽一切努力找出方案的漏洞。

## 原始任务
{TASK_DESCRIPTION}

## 任务相关材料
{TASK_MATERIALS}

## Round 3 提出的方案
{PROPOSED_SOLUTIONS}

## 强制检查清单
{ATTACK_CHECKLIST}

## 你的任务
对每个方案执行以下四项强制检查：

1. **同类问题回环检测**：这个方案是否重新引入了它试图解决的同类问题？
2. **具体场景走查**：构造至少 3 个具体的使用场景，逐步推演，寻找断裂点。
3. **"去掉它试试"测试**：方案中的每个新组件，如果去掉它，系统是否仍能工作？
4. **共识盲点检测**：前三轮讨论中有哪些被当成事实但实际上是可选择的隐含假设？

对每项检查，给出：通过 / 未通过 / 存疑，并附详细分析。

请用中文输出。务必做一个严厉的、对抗性的评审者。
```

---

## Round 4: Stress Test Prompt (Non-Devil's Advocate)

```
你是一位严格的方案评审者。请对方案进行压力测试。

## 原始任务
{TASK_DESCRIPTION}

## 任务相关材料
{TASK_MATERIALS}

## Round 3 提出的方案
{PROPOSED_SOLUTIONS}

## 强制检查清单
{ATTACK_CHECKLIST}

## 你的任务
对每个方案执行以下四项强制检查：

1. **同类问题回环检测**：这个方案是否重新引入了它试图解决的同类问题？
2. **具体场景走查**：构造至少 2 个具体的使用场景，逐步推演。
3. **"去掉它试试"测试**：方案中的每个新组件是否真正必要？
4. **共识盲点检测**：前几轮讨论中有哪些隐含假设值得质疑？

请用中文输出。
```

---

## Round 3: Synthesis Document Structure

The Round 3 synthesis document must include this structure for each topic:

```markdown
## 主题 N：[主题名称]

### 概述
[综合各方的核心观点]

### 方案
[具体的方案/建议]

### 待检验的假设
- 假设 1：[这个方案假设了 X 成立]
- 假设 2：[这个方案假设了 Y 不会发生]
```
