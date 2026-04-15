import json
import os
import re
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = REPO_ROOT / "skills/cross-review/scripts/cross_review_runtime.py"


VALID_MARKDOWN = """## 结论摘要
这是一份结构化的验证输出，用来模拟真实模型返回结果。
为了满足最小字节数要求，这里补充一段较长的分析说明，覆盖背景、判断、约束和风险。
这段文字会重复几次，以确保包装器不会把它误判成过短输出。

## 发现
### Major-1: 输出结构完整
- **证据**：包含结论摘要、发现、结论三个关键区块。
- **影响**：运行层可以通过语义校验，不会被误标为低质量。
- **建议**：继续沿用统一输出骨架，并把失败证据单独落盘。

## 一句话结论
包装器可以稳定识别有效输出。
"""

VALID_NUMBERED_MARKDOWN = """## 结论摘要
这是一份针对语义校验的额外验证输出。它故意不使用三级标题，而是使用编号列表来表达发现，以覆盖 Gemini 这类常见的输出风格。
内容同样足够长，避免被运输层因为长度不足而误杀，同时确保结构依然清晰可读。

## 发现
1. 第一条发现通过编号列表呈现，说明校验器不应该把编号列表误判为缺少实质内容。
2. 第二条发现补充说明：只要标题和条目都在，输出就应被视为合格，而不该强依赖 `###` 或特定加粗字段。

## 一句话结论
语义校验应接受编号列表形式的有效发现。
"""


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_config(path: Path, models: dict) -> None:
    payload = {
        "schema_version": 2,
        "last_updated": "2026-04-03",
        "last_verified": "2026-04-03T21:00:00+08:00",
        "models": models,
    }
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def run_runtime(args, env=None, cwd=None):
    return subprocess.run(
        ["python3", str(RUNTIME), *args],
        cwd=str(cwd or REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class CrossReviewRuntimeTests(unittest.TestCase):
    def test_gemini_uses_model_name_from_config_when_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_gemini = temp / "fake_gemini.py"
            prompt_file = temp / "prompt.md"
            config_path = temp / "models.yaml"
            registry_path = temp / "registry.json"
            run_dir = temp / "run-20260403-2200"
            prompt_file.write_text("请给出结构化评审结果。", encoding="utf-8")

            write_executable(
                fake_gemini,
                f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if "-v" in sys.argv or "--version" in sys.argv:
    print("0.35.3")
    raise SystemExit(0)

Path({str((temp / "argv.json"))!r}).write_text(json.dumps(sys.argv), encoding="utf-8")
print({VALID_MARKDOWN!r})
""",
            )

            write_config(
                config_path,
                {
                    "gemini": {
                        "cli_path": str(fake_gemini),
                        "model_name": "gemini-3.1-pro-preview",
                        "invoke": 'gemini -m gemini-3.1-pro-preview -p "{prompt}" > {output_file}',
                        "healthcheck": "gemini -v >/dev/null 2>&1",
                        "notes": "Fake Gemini",
                    }
                },
            )

            result = run_runtime(
                [
                    "execute",
                    "--config",
                    str(config_path),
                    "--registry",
                    str(registry_path),
                    "--run-dir",
                    str(run_dir),
                    "--call-id",
                    "r1.gemini",
                    "--model",
                    "gemini",
                    "--prompt-file",
                    str(prompt_file),
                    "--output-file",
                    "r1.gemini.md",
                ]
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            call = status["calls"]["r1.gemini"]
            self.assertEqual(call["requested_model"], "gemini-3.1-pro-preview")
            self.assertEqual(call["resolved_model"], "gemini-3.1-pro-preview")
            self.assertEqual(call["attempts"][0]["command"][1:3], ["-m", "gemini-3.1-pro-preview"])

    def test_execute_success_writes_status_logs_and_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_gemini = temp / "fake_gemini.py"
            prompt_file = temp / "prompt.md"
            config_path = temp / "models.yaml"
            registry_path = temp / "registry.json"
            run_dir = temp / "run-20260403-2100"
            workspace = temp / "workspace"
            workspace.mkdir()
            prompt_file.write_text("请给出结构化评审结果。", encoding="utf-8")

            write_executable(
                fake_gemini,
                f"""#!/usr/bin/env python3
import sys

if "-v" in sys.argv or "--version" in sys.argv:
    print("0.35.3")
    raise SystemExit(0)

if "--help" in sys.argv:
    print("Usage: gemini")
    raise SystemExit(0)

print({VALID_MARKDOWN!r})
""",
            )

            write_config(
                config_path,
                {
                    "gemini": {
                        "cli_path": str(fake_gemini),
                        "invoke": 'gemini -p "{prompt}" > {output_file}',
                        "healthcheck": "gemini -v >/dev/null 2>&1",
                        "notes": "Fake Gemini",
                    }
                },
            )

            result = run_runtime(
                [
                    "execute",
                    "--config",
                    str(config_path),
                    "--registry",
                    str(registry_path),
                    "--run-dir",
                    str(run_dir),
                    "--call-id",
                    "r1.gemini",
                    "--model",
                    "gemini",
                    "--prompt-file",
                    str(prompt_file),
                    "--output-file",
                    "r1.gemini.md",
                    "--cwd",
                    str(workspace),
                ]
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            output_path = run_dir / "r1.gemini.md"
            status_path = run_dir / "status.json"
            self.assertTrue(output_path.exists())
            self.assertTrue(status_path.exists())
            self.assertIn("## 结论摘要", output_path.read_text(encoding="utf-8"))

            status = json.loads(status_path.read_text(encoding="utf-8"))
            call = status["calls"]["r1.gemini"]
            self.assertEqual(call["final_status"], "succeeded")
            self.assertEqual(call["retries_used"], 0)
            self.assertEqual(len(call["attempts"]), 1)
            self.assertTrue((run_dir / call["attempts"][0]["stdout_path"]).exists())
            self.assertTrue((run_dir / call["attempts"][0]["stderr_path"]).exists())
            self.assertEqual(call["validation"]["transport"]["passed"], True)
            self.assertEqual(call["validation"]["semantic"]["passed"], True)

    def test_semantic_validation_accepts_numbered_findings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_gemini = temp / "fake_gemini.py"
            prompt_file = temp / "prompt.md"
            config_path = temp / "models.yaml"
            registry_path = temp / "registry.json"
            run_dir = temp / "run-20260403-2201"
            prompt_file.write_text("请给出结构化评审结果。", encoding="utf-8")

            write_executable(
                fake_gemini,
                f"""#!/usr/bin/env python3
import sys

if "-v" in sys.argv or "--version" in sys.argv:
    print("0.35.3")
    raise SystemExit(0)

print({VALID_NUMBERED_MARKDOWN!r})
""",
            )

            write_config(
                config_path,
                {
                    "gemini": {
                        "cli_path": str(fake_gemini),
                        "model_name": "gemini-3.1-pro-preview",
                        "invoke": 'gemini -m gemini-3.1-pro-preview -p "{prompt}" > {output_file}',
                        "healthcheck": "gemini -v >/dev/null 2>&1",
                        "notes": "Fake Gemini",
                    }
                },
            )

            result = run_runtime(
                [
                    "execute",
                    "--config",
                    str(config_path),
                    "--registry",
                    str(registry_path),
                    "--run-dir",
                    str(run_dir),
                    "--call-id",
                    "r1.gemini",
                    "--model",
                    "gemini",
                    "--prompt-file",
                    str(prompt_file),
                    "--output-file",
                    "r1.gemini.md",
                ]
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            call = status["calls"]["r1.gemini"]
            self.assertEqual(call["final_status"], "succeeded")
            self.assertEqual(call["validation"]["semantic"]["passed"], True)

    def test_execute_failure_creates_invalid_artifacts_and_records_retry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_gemini = temp / "fake_gemini.py"
            prompt_file = temp / "prompt.md"
            retry_prompt_file = temp / "retry.md"
            config_path = temp / "models.yaml"
            registry_path = temp / "registry.json"
            run_dir = temp / "run-20260403-2101"
            prompt_file.write_text("请输出结果。", encoding="utf-8")
            retry_prompt_file.write_text("请精简后重试。", encoding="utf-8")

            write_executable(
                fake_gemini,
                """#!/usr/bin/env python3
import sys

if "-v" in sys.argv or "--version" in sys.argv:
    print("0.35.3")
    raise SystemExit(0)

print("Usage: gemini --help")
""",
            )

            write_config(
                config_path,
                {
                    "gemini": {
                        "cli_path": str(fake_gemini),
                        "invoke": 'gemini -p "{prompt}" > {output_file}',
                        "healthcheck": "gemini -v >/dev/null 2>&1",
                        "notes": "Fake Gemini",
                    }
                },
            )

            result = run_runtime(
                [
                    "execute",
                    "--config",
                    str(config_path),
                    "--registry",
                    str(registry_path),
                    "--run-dir",
                    str(run_dir),
                    "--call-id",
                    "r1.gemini",
                    "--model",
                    "gemini",
                    "--prompt-file",
                    str(prompt_file),
                    "--retry-prompt-file",
                    str(retry_prompt_file),
                    "--output-file",
                    "r1.gemini.md",
                    "--max-retries",
                    "1",
                ]
            )

            self.assertEqual(result.returncode, 1)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            call = status["calls"]["r1.gemini"]
            self.assertEqual(call["final_status"], "transport_failed")
            self.assertEqual(call["retries_used"], 1)
            self.assertEqual(len(call["attempts"]), 2)
            self.assertTrue((run_dir / "invalid").exists())
            invalid_outputs = list((run_dir / "invalid").glob("*.output.md"))
            self.assertEqual(len(invalid_outputs), 2)
            self.assertEqual(call["validation"]["transport"]["passed"], False)

    def test_crush_resolution_learns_canonical_target_after_provider_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_crush = temp / "fake_crush.py"
            prompt_file = temp / "prompt.md"
            config_path = temp / "models.yaml"
            registry_path = temp / "registry.json"
            models_file = temp / "crush-models.txt"
            version_file = temp / "crush-version.txt"
            run_dir_1 = temp / "run-20260403-2102"
            run_dir_2 = temp / "run-20260403-2103"
            prompt_file.write_text("请给出结构化评审。", encoding="utf-8")
            models_file.write_text("zhipu/glm-5.1\nzai/glm-5.1\n", encoding="utf-8")
            version_file.write_text("v0.51.2\n", encoding="utf-8")

            write_executable(
                fake_crush,
                f"""#!/usr/bin/env python3
import os
import sys
from pathlib import Path

version = Path(os.environ["FAKE_CRUSH_VERSION"]).read_text(encoding="utf-8").strip()
models = Path(os.environ["FAKE_CRUSH_MODELS"]).read_text(encoding="utf-8")

if "--version" in sys.argv:
    print(version)
    raise SystemExit(0)

if len(sys.argv) > 1 and sys.argv[1] == "models":
    print(models, end="")
    raise SystemExit(0)

if len(sys.argv) > 1 and sys.argv[1] == "run":
    model = None
    for index, arg in enumerate(sys.argv):
        if arg in ("-m", "--model"):
            model = sys.argv[index + 1]
            break
    if model == "zhipu/glm-5.1":
        print("permission denied for model", file=sys.stderr)
        raise SystemExit(1)
    print({VALID_MARKDOWN!r})
    raise SystemExit(0)

raise SystemExit(2)
""",
            )

            write_config(
                config_path,
                {
                    "crush": {
                        "cli_path": str(fake_crush),
                        "model_name": "GLM-4.7",
                        "invoke": 'crush run --quiet "{prompt}" > {output_file}',
                        "healthcheck": "crush models >/dev/null 2>&1",
                        "catalog": "crush models",
                        "notes": "Fake Crush",
                    }
                },
            )

            env = os.environ.copy()
            env["FAKE_CRUSH_MODELS"] = str(models_file)
            env["FAKE_CRUSH_VERSION"] = str(version_file)

            first = run_runtime(
                [
                    "execute",
                    "--config",
                    str(config_path),
                    "--registry",
                    str(registry_path),
                    "--run-dir",
                    str(run_dir_1),
                    "--call-id",
                    "r1.crush",
                    "--model",
                    "crush",
                    "--prompt-file",
                    str(prompt_file),
                    "--output-file",
                    "r1.crush.md",
                    "--requested-model",
                    "GLM5.1",
                ],
                env=env,
            )

            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            alias = registry["tools"]["crush"]["aliases"]["glm51"]
            self.assertEqual(alias["canonical_target"], "zai/glm-5.1")
            self.assertEqual(alias["candidates"]["zhipu/glm-5.1"]["last_status"], "permission_denied")
            self.assertEqual(alias["candidates"]["zai/glm-5.1"]["last_status"], "success")

            second = run_runtime(
                [
                    "execute",
                    "--config",
                    str(config_path),
                    "--registry",
                    str(registry_path),
                    "--run-dir",
                    str(run_dir_2),
                    "--call-id",
                    "r2.crush",
                    "--model",
                    "crush",
                    "--prompt-file",
                    str(prompt_file),
                    "--output-file",
                    "r2.crush.md",
                    "--requested-model",
                    "GLM5.1",
                ],
                env=env,
            )

            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)
            second_status = json.loads((run_dir_2 / "status.json").read_text(encoding="utf-8"))
            second_call = second_status["calls"]["r2.crush"]
            self.assertEqual(second_call["resolved_model"], "zai/glm-5.1")
            self.assertEqual(len(second_call["attempts"]), 1)

    def test_resolve_model_refreshes_registry_when_cli_version_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_crush = temp / "fake_crush.py"
            config_path = temp / "models.yaml"
            registry_path = temp / "registry.json"
            models_file = temp / "crush-models.txt"
            version_file = temp / "crush-version.txt"
            models_file.write_text("zai/glm-5.1\n", encoding="utf-8")
            version_file.write_text("v0.51.2\n", encoding="utf-8")

            write_executable(
                fake_crush,
                """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

version = Path(os.environ["FAKE_CRUSH_VERSION"]).read_text(encoding="utf-8").strip()
models = Path(os.environ["FAKE_CRUSH_MODELS"]).read_text(encoding="utf-8")

if "--version" in sys.argv:
    print(version)
    raise SystemExit(0)

if len(sys.argv) > 1 and sys.argv[1] == "models":
    print(models, end="")
    raise SystemExit(0)

raise SystemExit(0)
""",
            )

            write_config(
                config_path,
                {
                    "crush": {
                        "cli_path": str(fake_crush),
                        "model_name": "GLM-4.7",
                        "invoke": 'crush run --quiet "{prompt}" > {output_file}',
                        "healthcheck": "crush models >/dev/null 2>&1",
                        "catalog": "crush models",
                        "notes": "Fake Crush",
                    }
                },
            )

            env = os.environ.copy()
            env["FAKE_CRUSH_MODELS"] = str(models_file)
            env["FAKE_CRUSH_VERSION"] = str(version_file)

            first = run_runtime(
                [
                    "resolve-model",
                    "--config",
                    str(config_path),
                    "--registry",
                    str(registry_path),
                    "--model",
                    "crush",
                    "--requested-model",
                    "GLM5.1",
                ],
                env=env,
            )
            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            first_payload = json.loads(first.stdout)
            self.assertEqual(first_payload["refresh_reason"], "missing_catalog")
            self.assertEqual(first_payload["resolved_model"], "zai/glm-5.1")

            models_file.write_text("zai/glm-5.2\n", encoding="utf-8")
            version_file.write_text("v0.52.0\n", encoding="utf-8")

            second = run_runtime(
                [
                    "resolve-model",
                    "--config",
                    str(config_path),
                    "--registry",
                    str(registry_path),
                    "--model",
                    "crush",
                    "--requested-model",
                    "GLM5.2",
                ],
                env=env,
            )
            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)
            second_payload = json.loads(second.stdout)
            self.assertEqual(second_payload["refresh_reason"], "version_changed")
            self.assertEqual(second_payload["resolved_model"], "zai/glm-5.2")


VALID_FINAL_MD = """---
task: "修复 im2cc update 的 dirty tree 问题"
mode: "full"
task_type: "design"
models:
  lead: "claude"
  external: ["codex", "crush"]
run_id: "run-20260415-1535"
created_at: "2026-04-15T15:35:00+08:00"
status: "active"
supersedes: null
superseded_by: null
success_criteria: "让 im2cc update 在 dirty tree 上也能完成，且用户改动可恢复"
synthesis_bias_note: null
independent_review: "pass"
---

# im2cc update — Dirty Tree 处理方案

## TL;DR
目标是修复 im2cc update 命令在 dirty tree 下失败的问题。最终决策：先备份到 repo 外，再确定性覆盖。下一步立即执行 P0-1 到 P0-5。核心取舍：采纳轻量备份方案，拒绝 SRE 化 staging。

## 1. 任务与约束
- **目标**：让 im2cc update 在 dirty tree 上可完成
- **关键约束**：
  - 不丢失用户改动
  - 命令可被 AI 调用（非交互）
- **成功标准**：普通用户永远 update 成功，开发者不丢工作

## 2. 核心分歧与裁决

| # | 议题 | claude | codex | crush | 裁决 | 依据 |
|---|------|--------|-------|-------|------|------|
| D1 | 备份位置 | git stash | repo 外完整备份 | repo 外轻量 manifest | **repo 外** | stash 绑定 .git，不安全 |

## 3. 最终方案

### 决策 1：用 preserveLocalChanges 替换 ensureCleanGitCheckout
- **做什么**：新增函数，签名为 (root, isGitCheckout) => SaveResult
- **为什么**：消除 git 路径和 tarball 路径的不对称
- **来源**：R3 候选 #1

## 4. 被否决的替代路径
- **路径 git stash**（claude）：stash 绑定 .git，update 时会被破坏 → 否决理由：不安全

## 5. 行动项

### P0 — 立即执行
- [ ] **P0-1** 实现 preserveLocalChanges
  - 文件：src/upgrade.ts
  - 依赖：无
  - 来源：决策 1
- [ ] **P0-2** 修改 cmdUpdate 调用新函数
  - 文件：bin/im2cc.ts
  - 依赖：P0-1
  - 来源：决策 1

## 6. 遗留风险与未决问题
- **风险 R1**：fork-remote 检测精度 — 缓解方式：正则匹配

## 7. 附录：讨论脉络
<details>
<summary>展开</summary>
详细脉络见 r1/r2/r3/r4 各模型输出。
</details>
"""


INVALID_FINAL_MD_NO_FRONTMATTER = """# 没有 frontmatter 的文档

## TL;DR
这份文档缺少 frontmatter。它只有正文，不符合强模板。

## 1. 任务与约束
...

## 2. 核心分歧与裁决
无

## 3. 最终方案
### 决策 1: 不重要
"""


class FinalMdValidationTests(unittest.TestCase):
    def test_valid_final_md_passes_all_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            final_md = Path(temp_dir) / "final.md"
            final_md.write_text(VALID_FINAL_MD, encoding="utf-8")
            result = run_runtime(["check-final", "--file", str(final_md)])
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["passed"], payload)
            for name, check in payload["checks"].items():
                self.assertTrue(check["passed"], f"{name} failed: {check}")

    def test_missing_frontmatter_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            final_md = Path(temp_dir) / "final.md"
            final_md.write_text(INVALID_FINAL_MD_NO_FRONTMATTER, encoding="utf-8")
            result = run_runtime(["check-final", "--file", str(final_md)])
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["passed"])
            self.assertFalse(payload["checks"]["frontmatter_fields"]["passed"])
            self.assertEqual(
                set(payload["checks"]["frontmatter_fields"]["missing"]),
                {"task", "mode", "task_type", "models", "run_id", "created_at", "status", "success_criteria"},
            )

    def test_missing_decision_field_fails(self):
        broken = VALID_FINAL_MD.replace(
            "- **做什么**：新增函数，签名为 (root, isGitCheckout) => SaveResult\n", ""
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            final_md = Path(temp_dir) / "final.md"
            final_md.write_text(broken, encoding="utf-8")
            result = run_runtime(["check-final", "--file", str(final_md)])
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["checks"]["decision_fields"]["passed"])
            self.assertTrue(
                any("做什么" in issue for issue in payload["checks"]["decision_fields"]["issues"])
            )

    def test_tldr_too_short_fails(self):
        broken = VALID_FINAL_MD.replace(
            "## TL;DR\n目标是修复 im2cc update 命令在 dirty tree 下失败的问题。最终决策：先备份到 repo 外，再确定性覆盖。下一步立即执行 P0-1 到 P0-5。核心取舍：采纳轻量备份方案，拒绝 SRE 化 staging。",
            "## TL;DR\n太短了。",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            final_md = Path(temp_dir) / "final.md"
            final_md.write_text(broken, encoding="utf-8")
            result = run_runtime(["check-final", "--file", str(final_md)])
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["checks"]["tldr_sufficient"]["passed"])
            self.assertLess(payload["checks"]["tldr_sufficient"]["sentence_count"], 3)

    def test_no_p0_actions_fails(self):
        broken = re.sub(
            r"### P0 — 立即执行\n.*?(?=\n## 6\.)",
            "### P0 — 立即执行\n\n（待补）\n",
            VALID_FINAL_MD,
            flags=re.DOTALL,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            final_md = Path(temp_dir) / "final.md"
            final_md.write_text(broken, encoding="utf-8")
            result = run_runtime(["check-final", "--file", str(final_md)])
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["checks"]["p0_actions"]["passed"])
            self.assertEqual(payload["checks"]["p0_actions"]["count"], 0)


class ArchiveLegacyTests(unittest.TestCase):
    def test_archives_non_run_files_and_skips_run_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            records = Path(temp_dir) / "cross-review-records"
            records.mkdir()
            # legacy files
            (records / "final-output-ws.md").write_text("old", encoding="utf-8")
            (records / "round1-claude.md").write_text("old", encoding="utf-8")
            # modern run dir
            run_dir = records / "run-20260415-1535"
            run_dir.mkdir()
            (run_dir / "final.md").write_text("modern", encoding="utf-8")
            # current.md pointer should be preserved
            (records / "current.md").write_text("run-20260415-1535/final.md\n", encoding="utf-8")

            result = run_runtime(["archive-legacy", "--dir", str(records)])
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(len(payload["moved"]), 2)
            self.assertTrue((records / "_archive" / "final-output-ws.md").exists())
            self.assertTrue((records / "_archive" / "round1-claude.md").exists())
            # run dir untouched
            self.assertTrue((records / "run-20260415-1535" / "final.md").exists())
            # current.md untouched
            self.assertTrue((records / "current.md").exists())


class SupersedesTests(unittest.TestCase):
    def test_mark_superseded_updates_both_files_and_writes_pointer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            records = Path(temp_dir) / "cross-review-records"
            old_run = records / "run-20260410-0915"
            new_run = records / "run-20260415-1535"
            old_run.mkdir(parents=True)
            new_run.mkdir(parents=True)
            old_final = old_run / "final.md"
            new_final = new_run / "final.md"
            old_final.write_text(VALID_FINAL_MD.replace('run_id: "run-20260415-1535"', 'run_id: "run-20260410-0915"'), encoding="utf-8")
            new_final.write_text(VALID_FINAL_MD, encoding="utf-8")

            result = run_runtime([
                "mark-superseded",
                "--records-dir", str(records),
                "--old", "run-20260410-0915",
                "--new", "run-20260415-1535",
            ])
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

            old_text = old_final.read_text(encoding="utf-8")
            self.assertIn('status: "superseded"', old_text)
            self.assertIn('superseded_by: "run-20260415-1535"', old_text)
            self.assertIn("本 run 已被 run-20260415-1535 取代", old_text)

            new_text = new_final.read_text(encoding="utf-8")
            self.assertIn('supersedes: "run-20260410-0915"', new_text)

            pointer = records / "current.md"
            self.assertTrue(pointer.exists())
            self.assertIn("run-20260415-1535/final.md", pointer.read_text(encoding="utf-8"))


class RunInitTests(unittest.TestCase):
    def test_run_init_reports_archived_and_active_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            records = Path(temp_dir) / "cross-review-records"
            records.mkdir()
            (records / "old-format.md").write_text("legacy", encoding="utf-8")
            active_run = records / "run-20260415-1535"
            active_run.mkdir()
            (active_run / "final.md").write_text(VALID_FINAL_MD, encoding="utf-8")
            superseded_run = records / "run-20260410-0915"
            superseded_run.mkdir()
            superseded_fm = VALID_FINAL_MD.replace('status: "active"', 'status: "superseded"')
            (superseded_run / "final.md").write_text(superseded_fm, encoding="utf-8")

            result = run_runtime(["run-init", "--dir", str(records)])
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(len(payload["archived"]["moved"]), 1)
            active_ids = [r["run_id"] for r in payload["active_runs"]]
            self.assertIn("run-20260415-1535", active_ids)
            self.assertNotIn("run-20260410-0915", active_ids)


if __name__ == "__main__":
    unittest.main()
