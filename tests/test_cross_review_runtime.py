import json
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = REPO_ROOT / "skills/jvever-cross-review/scripts/cross_review_runtime.py"


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
这是一份针对语义校验的额外验证输出。它故意不使用三级标题，而是使用编号列表来表达发现，以覆盖 Codex 这类常见的输出风格。
内容同样足够长，避免被运输层因为长度不足而误杀，同时确保结构依然清晰可读。

## 发现
1. 第一条发现通过编号列表呈现，说明校验器不应该把编号列表误判为缺少实质内容。
2. 第二条发现补充说明：只要标题和条目都在，输出就应被视为合格。

## 一句话结论
语义校验应接受编号列表形式的有效发现。
"""


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_config(path: Path, models: dict) -> None:
    path.write_text(
        yaml.safe_dump({"models": models}, allow_unicode=True, sort_keys=False),
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


class ExecuteTests(unittest.TestCase):
    """The external-call wrapper: success path, retry-on-failure, codex built-in."""

    def _run_external(self, temp, invoke_template, fake_source, call_extra=None):
        temp = Path(temp)
        fake_cli = temp / "fake_cli.py"
        prompt_file = temp / "prompt.md"
        config_path = temp / "models.yaml"
        run_dir = temp / "run-20260605-1200"
        prompt_file.write_text("请给出结构化评审结果。", encoding="utf-8")
        write_executable(fake_cli, fake_source)
        write_config(
            config_path,
            {"ext": {"cli_path": str(fake_cli), "invoke": invoke_template.format(cli=fake_cli)}},
        )
        args = [
            "execute",
            "--config", str(config_path),
            "--run-dir", str(run_dir),
            "--call-id", "r1.ext",
            "--model", "ext",
            "--prompt-file", str(prompt_file),
            "--output-file", "r1.ext.md",
        ]
        if call_extra:
            args += call_extra
        return run_runtime(args), run_dir

    def test_execute_success_writes_status_logs_and_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result, run_dir = self._run_external(
                temp_dir,
                "{cli} > {{output_file}}",
                f"""#!/usr/bin/env python3
print({VALID_MARKDOWN!r})
""",
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertTrue((run_dir / "r1.ext.md").exists())
            self.assertIn("## 结论摘要", (run_dir / "r1.ext.md").read_text(encoding="utf-8"))
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            call = status["calls"]["r1.ext"]
            self.assertEqual(call["final_status"], "succeeded")
            self.assertEqual(call["retries_used"], 0)
            self.assertEqual(len(call["attempts"]), 1)
            self.assertTrue((run_dir / call["attempts"][0]["stdout_path"]).exists())
            self.assertEqual(call["validation"]["transport"]["passed"], True)
            self.assertEqual(call["validation"]["semantic"]["passed"], True)
            self.assertEqual(call["resolution"]["strategy"], "static")

    def test_semantic_validation_accepts_numbered_findings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result, run_dir = self._run_external(
                temp_dir,
                "{cli} > {{output_file}}",
                f"""#!/usr/bin/env python3
print({VALID_NUMBERED_MARKDOWN!r})
""",
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            call = status["calls"]["r1.ext"]
            self.assertEqual(call["final_status"], "succeeded")
            self.assertEqual(call["validation"]["semantic"]["passed"], True)

    def test_execute_failure_creates_invalid_artifacts_and_records_retry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            retry_prompt_file = temp / "retry.md"
            retry_prompt_file.write_text("请精简后重试。", encoding="utf-8")
            result, run_dir = self._run_external(
                temp_dir,
                "{cli} > {{output_file}}",
                """#!/usr/bin/env python3
print("Usage: fake --help")
""",
                call_extra=["--retry-prompt-file", str(retry_prompt_file), "--max-retries", "1"],
            )
            self.assertEqual(result.returncode, 1)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            call = status["calls"]["r1.ext"]
            self.assertEqual(call["final_status"], "transport_failed")
            self.assertEqual(call["retries_used"], 1)
            self.assertEqual(len(call["attempts"]), 2)
            self.assertTrue((run_dir / "invalid").exists())
            invalid_outputs = list((run_dir / "invalid").glob("*.output.md"))
            self.assertEqual(len(invalid_outputs), 2)
            self.assertEqual(call["validation"]["transport"]["passed"], False)

    def test_codex_builtin_uses_stdin_and_output_last_message(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_codex = temp / "fake_codex.py"
            prompt_file = temp / "prompt.md"
            config_path = temp / "models.yaml"
            run_dir = temp / "run-20260605-1300"
            prompt_file.write_text("请给出结构化评审结果。", encoding="utf-8")
            write_executable(
                fake_codex,
                f"""#!/usr/bin/env python3
import sys
from pathlib import Path
argv = sys.argv
out = argv[argv.index("--output-last-message") + 1]
_ = sys.stdin.read()  # consume the piped prompt
Path(out).write_text({VALID_MARKDOWN!r}, encoding="utf-8")
""",
            )
            write_config(config_path, {"codex": {"cli_path": str(fake_codex)}})
            result = run_runtime(
                [
                    "execute",
                    "--config", str(config_path),
                    "--run-dir", str(run_dir),
                    "--call-id", "r1.codex",
                    "--model", "codex",
                    "--prompt-file", str(prompt_file),
                    "--output-file", "r1.codex.md",
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            call = status["calls"]["r1.codex"]
            self.assertEqual(call["final_status"], "succeeded")
            self.assertIn("--output-last-message", call["attempts"][0]["command"])
            self.assertIn("## 结论摘要", (run_dir / "r1.codex.md").read_text(encoding="utf-8"))


VALID_FINAL_MD = """---
task: "修复 im2cc update 的 dirty tree 问题"
mode: "full"
task_type: "design"
models:
  lead: "claude"
  external: ["codex"]
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

## 给你
说人话：update 在有未提交改动时也能跑完，你的改动不会丢。下一步执行 P0-1 到 P0-2。

## TL;DR
目标是修复 im2cc update 命令在 dirty tree 下失败的问题。最终决策：先备份到 repo 外，再确定性覆盖。下一步立即执行 P0。

## 1. 任务与约束
- **目标**：让 im2cc update 在 dirty tree 上可完成

## 5. 行动项
- [ ] **P0-1** 实现 preserveLocalChanges

## 7. 附录：溯源
<details><summary>展开</summary>详细脉络见 r1/r2/r3 各模型输出。</details>
"""


class FinalMdValidationTests(unittest.TestCase):
    def _check(self, text):
        with tempfile.TemporaryDirectory() as temp_dir:
            final_md = Path(temp_dir) / "final.md"
            final_md.write_text(text, encoding="utf-8")
            result = run_runtime(["check-final", "--file", str(final_md)])
            return result, json.loads(result.stdout)

    def test_valid_final_md_passes_all_checks(self):
        result, payload = self._check(VALID_FINAL_MD)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertTrue(payload["passed"], payload)
        for name, check in payload["checks"].items():
            self.assertTrue(check["passed"], f"{name} failed: {check}")

    def test_missing_frontmatter_fails(self):
        result, payload = self._check("# 没有 frontmatter 的文档\n\n## TL;DR\n只有正文。")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(payload["passed"])
        self.assertFalse(payload["checks"]["frontmatter_fields"]["passed"])
        self.assertEqual(
            set(payload["checks"]["frontmatter_fields"]["missing"]),
            {"task", "mode", "task_type", "models", "run_id", "created_at", "status", "success_criteria"},
        )

    def test_unexpected_frontmatter_field_fails_closed_set(self):
        # review_notes is exactly the overload field that must never leak back in.
        broken = VALID_FINAL_MD.replace(
            'independent_review: "pass"\n',
            'independent_review: "pass"\nreview_notes: "R5 返工 6 项；R5b 修订 16 项……"\n',
        )
        result, payload = self._check(broken)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(payload["checks"]["frontmatter_closed_set"]["passed"])
        self.assertIn("review_notes", payload["checks"]["frontmatter_closed_set"]["unexpected"])

    def test_bad_task_type_fails(self):
        broken = VALID_FINAL_MD.replace('task_type: "design"', 'task_type: "whatever"')
        result, payload = self._check(broken)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(payload["checks"]["task_type_valid"]["passed"])


if __name__ == "__main__":
    unittest.main()
