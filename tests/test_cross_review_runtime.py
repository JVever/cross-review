import json
import os
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


if __name__ == "__main__":
    unittest.main()
