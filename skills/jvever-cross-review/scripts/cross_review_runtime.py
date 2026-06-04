#!/usr/bin/env python3
"""Cross Review runtime wrapper: structured external-model execution + final.md frontmatter validation.

Scope (v3.1): the skill orchestrates a fixed pair — Claude (lead, runs the skill) + Codex (external).
Any other CLI can still be driven via a models.yaml `invoke` template, but there is no model
auto-routing / learnable registry / version-drift machinery anymore (removed as over-engineering).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence


STATUS_SCHEMA_VERSION = 1
DEFAULT_MIN_OUTPUT_BYTES = 200
DEFAULT_MAX_RETRIES = 1

AUTH_PROMPT_PATTERNS = (
    "opening authentication",
    "do you want to continue",
    "y/n",
    "login",
    "sign in",
    "authenticate",
)
HELP_TEXT_MARKERS = ("usage:", "--help")
PERMISSION_PATTERNS = (
    "permission",
    "forbidden",
    "unauthorized",
    "not allowed",
    "access denied",
)
MODEL_NOT_FOUND_PATTERNS = (
    "unknown model",
    "model not found",
    "unsupported model",
    "invalid model",
    "no such model",
)
SUCCESS_STATUSES = {"succeeded", "semantic_low_quality"}
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
EXPECTED_HEADINGS = ("## 结论摘要", "## 发现", "## 方案")


class CrossReviewRuntimeError(RuntimeError):
    """Raised when runtime execution cannot proceed."""


@dataclass
class CommandSpec:
    argv: List[str]
    stdin_text: Optional[str]
    output_mode: str  # "stdout" or "file"
    env: Optional[Dict[str, str]] = None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def expand_path(value: str) -> Path:
    return Path(value).expanduser()


def relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def atomic_write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_yaml(path: Path) -> Dict:
    import yaml

    if not path.exists():
        raise CrossReviewRuntimeError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CrossReviewRuntimeError(f"Config file is not a mapping: {path}")
    return data


def load_status(path: Path, run_id: str) -> Dict:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise CrossReviewRuntimeError(f"Status file is not a mapping: {path}")
        data.setdefault("schema_version", STATUS_SCHEMA_VERSION)
        data.setdefault("run_id", run_id)
        data.setdefault("created_at", now_iso())
        data.setdefault("calls", {})
        return data
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "calls": {},
    }


def save_status(path: Path, status: Dict) -> None:
    status["updated_at"] = now_iso()
    atomic_write_json(path, status)


def prepare_run_dirs(run_dir: Path) -> Dict[str, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    invalid_dir = run_dir / "invalid"
    logs_dir = run_dir / "logs"
    invalid_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "invalid_dir": invalid_dir,
        "logs_dir": logs_dir,
        "status_file": run_dir / "status.json",
    }


def decode_output(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def shell_command(command: str) -> List[str]:
    return [os.environ.get("SHELL", "/bin/zsh"), "-lc", command]


def run_process(
    argv: Sequence[str],
    cwd: Path,
    stdin_text: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict:
    started_at = now_iso()
    started_monotonic = time.monotonic()
    payload = stdin_text.encode("utf-8") if stdin_text is not None else None
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd),
            input=payload,
            capture_output=True,
            check=False,
            env=env,
        )
        stdout_text = decode_output(completed.stdout)
        stderr_text = decode_output(completed.stderr)
        exit_code = completed.returncode
    except FileNotFoundError as exc:
        stdout_text = ""
        stderr_text = str(exc)
        exit_code = 127
    except Exception as exc:  # pragma: no cover - defensive
        stdout_text = ""
        stderr_text = str(exc)
        exit_code = 70
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    return {
        "started_at": started_at,
        "duration_ms": duration_ms,
        "stdout_text": stdout_text,
        "stderr_text": stderr_text,
        "exit_code": exit_code,
    }


def validate_transport(raw_output_text: str, stderr_text: str, exit_code: int, min_bytes: int) -> Dict:
    sanitized_output = strip_ansi(raw_output_text)
    warnings: List[str] = []
    if sanitized_output != raw_output_text:
        warnings.append("ansi_sequences_stripped")

    issues: List[str] = []
    if exit_code != 0:
        issues.append("non_zero_exit")
    encoded_size = len(sanitized_output.encode("utf-8"))
    if not sanitized_output.strip():
        issues.append("empty_output")
    elif encoded_size < min_bytes:
        issues.append("below_min_bytes")

    combined = "\n".join([sanitized_output, stderr_text]).lower()
    if any(marker in combined for marker in AUTH_PROMPT_PATTERNS):
        issues.append("auth_or_interactive_prompt")
    if all(marker in combined for marker in HELP_TEXT_MARKERS):
        issues.append("help_text_detected")
    return {
        "passed": not issues,
        "issues": issues,
        "warnings": warnings,
        "output_bytes": encoded_size,
        "sanitized_output": sanitized_output,
    }


def validate_semantic(output_text: str) -> Dict:
    issues: List[str] = []
    if not any(marker in output_text for marker in EXPECTED_HEADINGS):
        issues.append("missing_expected_heading")
    if "## 一句话结论" not in output_text:
        issues.append("missing_one_line_conclusion")
    has_structured_items = bool(
        re.search(r"(?m)^(?:###\s+|\d+\.\s+|- \*\*证据\*\*|- \*\*内容\*\*|- )", output_text)
    )
    if not has_structured_items:
        issues.append("missing_substance_markers")
    return {
        "passed": not issues,
        "issues": issues,
    }


def classify_failure(
    stdout_text: str,
    stderr_text: str,
    transport_validation: Dict,
    exit_code: int,
) -> str:
    if transport_validation["passed"]:
        return "success"
    combined = "\n".join([stdout_text, stderr_text]).lower()
    if any(marker in combined for marker in PERMISSION_PATTERNS):
        return "permission_denied"
    if any(marker in combined for marker in MODEL_NOT_FOUND_PATTERNS):
        return "model_not_found"
    if "rate limit" in combined or "quota" in combined:
        return "rate_limited"
    if "timeout" in combined or "timed out" in combined:
        return "timeout"
    if any(marker in combined for marker in AUTH_PROMPT_PATTERNS):
        return "auth_required"
    if exit_code != 0:
        return "process_failed"
    return "transport_failed"


def copy_to_invalid(attempt_paths: Dict[str, Path], invalid_dir: Path) -> Dict[str, str]:
    invalid_output = invalid_dir / attempt_paths["output"].name
    invalid_stdout = invalid_dir / attempt_paths["stdout"].name
    invalid_stderr = invalid_dir / attempt_paths["stderr"].name
    invalid_output.write_text(attempt_paths["output"].read_text(encoding="utf-8"), encoding="utf-8")
    invalid_stdout.write_text(attempt_paths["stdout"].read_text(encoding="utf-8"), encoding="utf-8")
    invalid_stderr.write_text(attempt_paths["stderr"].read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "output": str(invalid_output),
        "stdout": str(invalid_stdout),
        "stderr": str(invalid_stderr),
    }


def build_command_spec(
    tool_key: str,
    model_cfg: Dict,
    prompt_text: str,
    prompt_file: Path,
    output_file: Path,
    requested_model: Optional[str],
    resolved_model: Optional[str],
) -> CommandSpec:
    """Build the external CLI invocation.

    `codex` is built in (the default external model): stdin prompt + --output-last-message.
    Any other CLI is driven by its models.yaml `invoke` template — that is the single,
    zero-machinery extension point for adding more models later.
    """
    cli_path = model_cfg.get("cli_path") or tool_key
    if tool_key == "codex":
        argv = [
            cli_path,
            "exec",
            "--full-auto",
            "--output-last-message",
            str(output_file),
            "--color",
            "never",
            "--ephemeral",
        ]
        return CommandSpec(argv=argv, stdin_text=prompt_text, output_mode="file")

    invoke_template = model_cfg.get("invoke")
    if not invoke_template:
        raise CrossReviewRuntimeError(
            f"Model '{tool_key}' has no invoke template in config and is not the built-in 'codex'. "
            f"Add an `invoke:` line to models.yaml for this CLI."
        )
    substitutions = {
        "prompt": shlex.quote(prompt_text),
        "prompt_file": shlex.quote(str(prompt_file)),
        "output_file": shlex.quote(str(output_file)),
        "requested_model": shlex.quote(requested_model or ""),
        "resolved_model": shlex.quote(resolved_model or ""),
    }
    command = invoke_template.format(**substitutions)
    env = os.environ.copy()
    env["CROSS_REVIEW_PROMPT"] = prompt_text
    env["CROSS_REVIEW_PROMPT_FILE"] = str(prompt_file)
    env["CROSS_REVIEW_OUTPUT_FILE"] = str(output_file)
    if requested_model:
        env["CROSS_REVIEW_REQUESTED_MODEL"] = requested_model
    if resolved_model:
        env["CROSS_REVIEW_RESOLVED_MODEL"] = resolved_model
    return CommandSpec(argv=shell_command(command), stdin_text=None, output_mode="file", env=env)


def run_attempt(
    tool_key: str,
    model_cfg: Dict,
    prompt_text: str,
    prompt_file: Path,
    attempt_number: int,
    call_id: str,
    cwd: Path,
    logs_dir: Path,
    requested_model: Optional[str],
    resolved_model: Optional[str],
    min_output_bytes: int,
) -> Dict:
    attempt_output = logs_dir / f"{call_id}.attempt{attempt_number}.output.md"
    attempt_stdout = logs_dir / f"{call_id}.attempt{attempt_number}.stdout.log"
    attempt_stderr = logs_dir / f"{call_id}.attempt{attempt_number}.stderr.log"
    spec = build_command_spec(
        tool_key=tool_key,
        model_cfg=model_cfg,
        prompt_text=prompt_text,
        prompt_file=prompt_file,
        output_file=attempt_output,
        requested_model=requested_model,
        resolved_model=resolved_model,
    )
    process_result = run_process(spec.argv, cwd=cwd, stdin_text=spec.stdin_text, env=spec.env)

    attempt_stdout.write_text(process_result["stdout_text"], encoding="utf-8")
    attempt_stderr.write_text(process_result["stderr_text"], encoding="utf-8")

    if spec.output_mode == "stdout":
        attempt_output.write_text(process_result["stdout_text"], encoding="utf-8")
        raw_output_text = process_result["stdout_text"]
    else:
        raw_output_text = attempt_output.read_text(encoding="utf-8") if attempt_output.exists() else ""

    transport_validation = validate_transport(
        raw_output_text=raw_output_text,
        stderr_text=process_result["stderr_text"],
        exit_code=process_result["exit_code"],
        min_bytes=min_output_bytes,
    )
    sanitized_output = transport_validation.pop("sanitized_output")
    attempt_output.write_text(sanitized_output, encoding="utf-8")
    semantic_validation = (
        validate_semantic(sanitized_output)
        if transport_validation["passed"]
        else {"passed": False, "issues": ["transport_validation_failed"]}
    )
    failure_class = classify_failure(
        stdout_text=process_result["stdout_text"],
        stderr_text=process_result["stderr_text"],
        transport_validation=transport_validation,
        exit_code=process_result["exit_code"],
    )

    return {
        "attempt": attempt_number,
        "command": spec.argv,
        "started_at": process_result["started_at"],
        "duration_ms": process_result["duration_ms"],
        "exit_code": process_result["exit_code"],
        "stdout_path": attempt_stdout,
        "stderr_path": attempt_stderr,
        "output_path": attempt_output,
        "transport_validation": transport_validation,
        "semantic_validation": semantic_validation,
        "failure_class": failure_class,
        "resolved_model": resolved_model,
    }


def output_file_path(run_dir: Path, value: str) -> Path:
    candidate = expand_path(value)
    if candidate.is_absolute():
        return candidate
    return run_dir / value


def read_text_file(path: Path) -> str:
    if not path.exists():
        raise CrossReviewRuntimeError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def execute_call(args: argparse.Namespace) -> int:
    config_path = expand_path(args.config)
    run_dir = expand_path(args.run_dir)
    runtime_paths = prepare_run_dirs(run_dir)
    status = load_status(runtime_paths["status_file"], run_dir.name)

    model_key = args.model
    prompt_file = expand_path(args.prompt_file)
    retry_prompt_file = expand_path(args.retry_prompt_file) if args.retry_prompt_file else None
    output_path = output_file_path(run_dir, args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = expand_path(args.cwd) if args.cwd else Path.cwd()

    # Write an initial record so a mid-run crash still leaves a trace.
    status["calls"][args.call_id] = {
        "call_id": args.call_id,
        "model_key": model_key,
        "requested_model": args.requested_model,
        "resolved_model": None,
        "output_file": relpath(output_path, run_dir),
        "cwd": str(cwd),
        "attempts": [],
        "retries_used": 0,
        "final_status": "not_started",
        "validation": None,
        "resolution": None,
        "updated_at": now_iso(),
    }
    save_status(runtime_paths["status_file"], status)

    config = load_yaml(config_path)
    models = config.get("models") or {}
    if model_key not in models:
        raise CrossReviewRuntimeError(f"Model '{model_key}' not found in config: {config_path}")
    model_cfg = models[model_key]
    prompt_text = read_text_file(prompt_file)
    retry_prompt_text = read_text_file(retry_prompt_file) if retry_prompt_file else prompt_text

    # No dynamic routing: use the requested alias if given, else the config's model_name.
    resolved_model = args.requested_model or model_cfg.get("model_name")

    prompt_variants = [("primary", prompt_text)]
    if args.max_retries > 0:
        prompt_variants.append(("retry", retry_prompt_text))

    attempts: List[Dict] = []
    final_status = "transport_failed"
    final_validation: Optional[Dict] = None
    successful_output: Optional[Path] = None

    for prompt_index, (prompt_variant, active_prompt) in enumerate(prompt_variants):
        attempt_number = len(attempts) + 1
        attempt_result = run_attempt(
            tool_key=model_key,
            model_cfg=model_cfg,
            prompt_text=active_prompt,
            prompt_file=retry_prompt_file if prompt_variant == "retry" and retry_prompt_file else prompt_file,
            attempt_number=attempt_number,
            call_id=args.call_id,
            cwd=cwd,
            logs_dir=runtime_paths["logs_dir"],
            requested_model=args.requested_model,
            resolved_model=resolved_model,
            min_output_bytes=args.min_output_bytes,
        )
        attempts.append(
            {
                "attempt": attempt_number,
                "prompt_variant": prompt_variant,
                "resolved_model": resolved_model,
                "command": attempt_result["command"],
                "started_at": attempt_result["started_at"],
                "duration_ms": attempt_result["duration_ms"],
                "exit_code": attempt_result["exit_code"],
                "stdout_path": relpath(attempt_result["stdout_path"], run_dir),
                "stderr_path": relpath(attempt_result["stderr_path"], run_dir),
                "output_path": relpath(attempt_result["output_path"], run_dir),
                "transport_validation": attempt_result["transport_validation"],
                "semantic_validation": attempt_result["semantic_validation"],
                "failure_class": attempt_result["failure_class"],
            }
        )

        if attempt_result["transport_validation"]["passed"]:
            successful_output = attempt_result["output_path"]
            final_validation = {
                "transport": attempt_result["transport_validation"],
                "semantic": attempt_result["semantic_validation"],
            }
            final_status = (
                "succeeded"
                if attempt_result["semantic_validation"]["passed"]
                else "semantic_low_quality"
            )
            break

        invalid_paths = copy_to_invalid(
            {
                "output": attempt_result["output_path"],
                "stdout": attempt_result["stdout_path"],
                "stderr": attempt_result["stderr_path"],
            },
            runtime_paths["invalid_dir"],
        )
        attempts[-1]["invalid_artifacts"] = {
            key: relpath(Path(value), run_dir) for key, value in invalid_paths.items()
        }

        if prompt_index >= args.max_retries:
            break

    retries_used = max(0, len(attempts) - 1)

    if successful_output:
        output_path.write_text(successful_output.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        output_path.write_text("", encoding="utf-8")
        final_validation = final_validation or {
            "transport": {"passed": False, "issues": ["all_attempts_failed"]},
            "semantic": {"passed": False, "issues": ["transport_validation_failed"]},
        }

    status = load_status(runtime_paths["status_file"], run_dir.name)
    status["calls"][args.call_id] = {
        "call_id": args.call_id,
        "model_key": model_key,
        "requested_model": args.requested_model,
        "resolved_model": resolved_model,
        "output_file": relpath(output_path, run_dir),
        "cwd": str(cwd),
        "attempts": attempts,
        "retries_used": retries_used,
        "final_status": final_status,
        "validation": final_validation,
        "resolution": {
            "strategy": "static",
            "requested_model": args.requested_model,
            "resolved_model": resolved_model,
        },
        "updated_at": now_iso(),
    }
    save_status(runtime_paths["status_file"], status)
    return 0 if final_status in SUCCESS_STATUSES else 1


# --------------------------------------------------------------------------
# final.md frontmatter validation (lightweight; structure of body is the lead
# model's self-check responsibility, see SKILL.md). We only validate the
# machine-readable frontmatter here — that is the one piece worth a hard gate,
# and it is parsed via YAML (not brittle Chinese-markdown regex).
# --------------------------------------------------------------------------

FINAL_REQUIRED_FRONTMATTER = (
    "task",
    "mode",
    "task_type",
    "models",
    "run_id",
    "created_at",
    "status",
    "success_criteria",
)
# Closed set: anything outside this is rejected, so process scaffolding like
# `review_notes` (a 22-item changelog) or `unavailable` can never leak back into
# the header. Keep this in sync with templates/final.md.tmpl.
FINAL_ALLOWED_FRONTMATTER = set(FINAL_REQUIRED_FRONTMATTER) | {
    "supersedes",
    "superseded_by",
    "synthesis_bias_note",
    "independent_review",
}
FINAL_MAX_LINES = 800
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_frontmatter(text: str) -> Dict:
    import yaml

    match = FRONTMATTER_RE.match(text)
    if not match:
        return {"_raw_body": text, "_has_frontmatter": False}
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        return {"_raw_body": match.group(2), "_has_frontmatter": True, "_parse_error": str(exc)}
    if not isinstance(data, dict):
        return {"_raw_body": match.group(2), "_has_frontmatter": True, "_parse_error": "frontmatter is not a mapping"}
    data["_raw_body"] = match.group(2)
    data["_has_frontmatter"] = True
    return data


def check_final_md(path: Path) -> Dict:
    if not path.exists():
        return {"passed": False, "errors": [f"file not found: {path}"], "checks": {}}
    text = path.read_text(encoding="utf-8")
    line_count = text.count("\n") + 1
    fm = parse_frontmatter(text)
    errors: List[str] = []
    checks: Dict[str, Dict] = {}

    # Check 1: required frontmatter fields present
    missing: List[str] = []
    if not fm.get("_has_frontmatter"):
        errors.append("frontmatter 缺失（文件必须以 `---\\n...\\n---\\n` 开头）")
        missing = list(FINAL_REQUIRED_FRONTMATTER)
    else:
        if fm.get("_parse_error"):
            errors.append(f"frontmatter YAML 解析失败: {fm['_parse_error']}")
        for field in FINAL_REQUIRED_FRONTMATTER:
            if field not in fm:
                missing.append(field)
    checks["frontmatter_fields"] = {"passed": not missing, "missing": missing}

    # Check 2: closed set — no fields outside the allow-list (blocks header overload)
    unexpected: List[str] = []
    if fm.get("_has_frontmatter") and not fm.get("_parse_error"):
        unexpected = sorted(
            key for key in fm if not key.startswith("_") and key not in FINAL_ALLOWED_FRONTMATTER
        )
    checks["frontmatter_closed_set"] = {"passed": not unexpected, "unexpected": unexpected}

    # Check 3: task_type is one of the known kinds
    task_type = fm.get("task_type") if fm.get("_has_frontmatter") else None
    checks["task_type_valid"] = {
        "passed": task_type in ("review", "design", "discuss", "create"),
        "task_type": task_type,
    }

    # Check 4: total line count under the cap (overflow → push detail into trace/appendix)
    checks["line_count"] = {
        "passed": line_count <= FINAL_MAX_LINES,
        "lines": line_count,
        "max": FINAL_MAX_LINES,
    }

    all_passed = all(c.get("passed") for c in checks.values()) and not errors
    return {
        "passed": all_passed,
        "errors": errors,
        "checks": checks,
        "path": str(path),
    }


def check_final_command(args: argparse.Namespace) -> int:
    result = check_final_md(Path(args.file).expanduser())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    default_config = str(Path.home() / ".config" / "cross-review" / "models.yaml")
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    execute_parser = subparsers.add_parser("execute", help="Run one external model call through the runtime wrapper.")
    execute_parser.add_argument("--config", default=default_config, help="Path to models.yaml")
    execute_parser.add_argument("--run-dir", required=True, help="Run directory for status.json, logs/, invalid/")
    execute_parser.add_argument("--call-id", required=True, help="Stable call id such as r1.codex")
    execute_parser.add_argument("--model", required=True, help="Model key from models.yaml")
    execute_parser.add_argument("--prompt-file", required=True, help="Prompt file path")
    execute_parser.add_argument("--retry-prompt-file", help="Optional retry prompt file path")
    execute_parser.add_argument("--output-file", required=True, help="Output file path, relative to run dir or absolute")
    execute_parser.add_argument("--cwd", help="Working directory for the external CLI")
    execute_parser.add_argument("--requested-model", help="Optional model id passed through to the CLI invoke template")
    execute_parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help="Prompt retries on failure")
    execute_parser.add_argument("--min-output-bytes", type=int, default=DEFAULT_MIN_OUTPUT_BYTES, help="Minimum sanitized output size")
    execute_parser.set_defaults(func=execute_call)

    check_final_parser = subparsers.add_parser("check-final", help="Validate final.md frontmatter (required fields + closed set + line cap).")
    check_final_parser.add_argument("--file", required=True, help="Path to final.md")
    check_final_parser.set_defaults(func=check_final_command)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CrossReviewRuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
