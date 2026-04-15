# Changelog

## [3.0.0] - 2026-04-15

### Breaking: final.md 改为硬约束编译产物

`final.md` 不再是"模型自由写的综合报告"。现在是**强模板下的编译产物**——缺字段则校验失败，必须返工。目的：解决"每次 final.md 结构都不同、用户需要让模型再解释一遍"的痛点。

### Added

- `skills/cross-review/templates/final.md.tmpl` — final.md 强模板（8 节 + frontmatter 8 字段 + 8 项硬校验清单）
- `skills/cross-review/templates/action.md.tmpl` — 行动清单模板（仅当 ≥ 3 条行动时独立生成，否则内嵌 final.md §5）
- `cross_review_runtime.py check-final` — 对 final.md 做 8 项结构化校验（frontmatter/TL;DR/分歧表/决策字段/P0/风险/task_type/行数）
- `cross_review_runtime.py archive-legacy` — 自动把非 `run-*/` 的老格式文件归档到 `_archive/`
- `cross_review_runtime.py mark-superseded` — 标注旧 run 被新 run 取代，更新 frontmatter + 插入顶部红框
- `cross_review_runtime.py run-init` — 启动时归档 + 检测历史 active run（供 SKILL.md Step 4 调用）
- **任务对齐卡**（SKILL.md Step 1）：主模型读完任务后输出对齐卡（目标/约束/成功标准/视角/模式），非阻塞
- **成功标准嵌入 R1 prompt**（A2）：所有外部模型从第一轮起就知道 final.md 要回答什么
- **快速模式 30 秒对抗**（D1）：R2 综合后、落盘前用一个外部模型做 ≤500 字攻击，防共识偏见
- **独立 Final Review**（C1）：final.md 落盘前必须过外部模型的独立复核（"是否自包含"）
- **supersedes 机制**（Q5）：多次重跑的 run 通过 `supersedes`/`superseded_by` frontmatter 字段链接；`current.md` 指向最新 active run
- **阶段简报**（B2）：R1/R2 结束后主模型输出 3-5 行非阻塞简报给用户
- 5 类新单元测试：final.md 校验、归档、supersedes、run-init

### Changed

- `prompt-templates.md` R1 模板新增 `{SUCCESS_CRITERIA}` 字段
- `SKILL.md` 主流程整合：Step 1 加任务对齐卡、Step 4 加归档+supersedes 检测、快速模式加 R2.5 对抗 + R3 独立 review、完备模式加 R5 独立 review
- 目录结构新增 `current.md` 快捷指针 + `_archive/` 子目录

### Removed / Demoted

- **divergence-ledger.md 独立文件**（合并进 final.md §2 分歧表，避免"三份文档同步漂移"）
- **综合者自披露独立章节 §7**（压缩为 frontmatter 中可选 `synthesis_bias_note` 一行）
- **manifest 状态机/续跑**（不命中"交付清晰度"目标，延后）

### 迁移说明

老 `run-*/final.md` 不会被自动转换。如需校验老 final：
```bash
python3 scripts/cross_review_runtime.py check-final --file run-xxx/final.md
```
大概率会 fail，这正确反映"老版本不符合新模板"。新 run 自动走新流程。

## [2.2.1] - 2026-04-03

### Added
- Regression coverage for config-driven Gemini model pinning (`model_name` + `-m`)

### Changed
- Documentation now recommends explicitly pinning Gemini to `gemini-3.1-pro-preview` instead of relying on CLI default routing

## [2.2.0] - 2026-04-03

### Added
- `skills/cross-review/scripts/cross_review_runtime.py` as a structured runtime wrapper for external model calls
- `status.json` per run with stdout/stderr log paths, exit code, duration, retries, resolved model, and validation summaries
- `~/.config/cross-review/registry.json` as learnable model memory for canonical model resolution
- Regression tests covering success, failed validation capture, canonical target learning, and version-triggered registry refresh

### Changed
- Crush model discovery now prefers the configured `cli_path` adapter over shell-level catalog commands
- Model alias resolution now reuses remembered successful targets and refreshes when catalog data gets stale or CLI versions drift
- Failure handling now preserves invalid outputs and stderr evidence instead of relying on silent redirection

## [2.1.0] - 2026-03-25

### Added
- Three-path startup: warm start (config + healthcheck → instant), cold start (first-time guide), fallback (partial re-guide)
- CLI-level healthcheck commands per model in config (`healthcheck` field), verified: `codex exec --help`, `gemini -v`, `crush models`
- `schema_version` and `last_verified` fields in config for future-proofing
- Crush CLI section in docs with `--quiet` flag for clean output

### Changed
- Preflight downgraged from model-level (`echo "ping" | codex exec`) to CLI-level (help/version checks), runs once per session not per round
- Warm start skips user confirmation — non-blocking notification only
- Fixed Gemini invoke example: `gemini -p "{prompt}"` (not `echo | gemini -p` which leaves `-p` without a value)
- Fixed Crush invoke example: `crush run --quiet` (not `crush chat`)

### Fixed
- Gemini CLI syntax error in SKILL.md that caused 2-3 rounds of trial-and-error on first use
- Crush CLI subcommand error (`chat` → `run`) in config template
- Preflight wasting tokens by calling models to respond to "ping"

## [2.0.0] - 2026-03-23

### Added
- CLI configuration persistence (`~/.config/cross-review/models.yaml`): remember user's CLI tools and invocation methods across sessions
- Model name → CLI mapping: say "GLM-4.7" and it auto-resolves to the right CLI (e.g., `crush`)
- Output contract: suggested output skeleton + "no thinking/logs" constraint for all external model prompts
- Two-layer output validation: transport validation (non-empty, no auth noise) + semantic validation (expected headings, substance)
- Digest protocol (optional): lead model creates digests only when output exceeds 5000 words; default passes clean outputs directly
- Round 2.5 focused rebuttal (full mode): resolves critical conflicts before synthesis
- Round 4 emphasis assignment: all models do all 4 checks, but each has designated emphasis items for deeper analysis
- Round 4 → Round 3b loop: Critical findings trigger targeted revision instead of restarting
- `manifest.json` for checkpoint/resume across interruptions
- Preflight checks before each external model call
- `invalid/` subdirectory for failed validation outputs

### Changed
- Codex invocation: `--output-last-message` + `--ephemeral` + `--color never` to eliminate output bloat
- Round 3 reframed from "optimal solution" to "candidate synthesis" with assumption ledger
- Quick mode synthesis now requires explicit verdict on disagreements (not just listing)
- Round 2 prompt prohibits restating Round 1 content; only incremental contributions allowed
- Directory structure: timestamped run directories (`run-YYYYMMDD-HHmm/`) instead of flat directory
- File naming: strict `r{N}.{model}.md` format, no free-form suffixes

### Fixed
- Output bloat from Codex (25-50KB of session noise → clean final message via `--output-last-message`)
- Empty/corrupted files from Gemini (auth prompts, 0-byte outputs) caught by transport validation
- Naming chaos (free-form suffixes like `-ws`, `-session-fix`, `-v2`) prevented by strict naming rules
- Noise amplification across rounds (raw outputs with metadata fed to next round → now clean outputs via `--output-last-message`, with optional digest for very long outputs)
- Premature synthesis in Round 3 (presented as "final" → now explicitly "candidate")

## [1.0.0] - 2026-03-11

### Added
- Initial open-source release
- Quick mode (2-round) and Full mode (4-round) workflows
- Model-agnostic design supporting Claude, Codex, Gemini, and other AI CLI tools
- Perspective-based task assignment for technical, product, and creative tasks
- Adversarial Round 4 with devil's advocate and stress testing
- 4 mandatory attack checks: loop detection, scenario walkthrough, removal test, consensus blind spot detection
- Graceful degradation from 3 models to 1
- Bilingual trigger support (English + Chinese)
- Intermediate result management with session resume capability
