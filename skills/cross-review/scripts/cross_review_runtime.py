#!/usr/bin/env python3
"""Cross Review runtime wrapper with structured status and learnable model registry."""

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

import yaml


STATUS_SCHEMA_VERSION = 1
REGISTRY_SCHEMA_VERSION = 1
DEFAULT_MIN_OUTPUT_BYTES = 200
DEFAULT_MAX_RETRIES = 1
CATALOG_TTL_SECONDS = 24 * 60 * 60

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
RETRY_NEXT_CANDIDATE_STATUSES = {"permission_denied", "model_not_found"}
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
    if not path.exists():
        raise CrossReviewRuntimeError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CrossReviewRuntimeError(f"Config file is not a mapping: {path}")
    return data


def load_registry(path: Path) -> Dict:
    if not path.exists():
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "updated_at": now_iso(),
            "tools": {},
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CrossReviewRuntimeError(f"Registry file is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise CrossReviewRuntimeError(f"Registry file is not a mapping: {path}")
    data.setdefault("schema_version", REGISTRY_SCHEMA_VERSION)
    data.setdefault("tools", {})
    return data


def save_registry(path: Path, registry: Dict) -> None:
    registry["updated_at"] = now_iso()
    atomic_write_json(path, registry)


def ensure_tool_state(registry: Dict, tool_key: str) -> Dict:
    tools = registry.setdefault("tools", {})
    tool_state = tools.setdefault(
        tool_key,
        {
            "version": None,
            "version_checked_at": None,
            "catalog": {
                "items": [],
                "refreshed_at": None,
                "refresh_reason": None,
            },
            "aliases": {},
        },
    )
    tool_state.setdefault("catalog", {"items": [], "refreshed_at": None, "refresh_reason": None})
    tool_state.setdefault("aliases", {})
    return tool_state


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


def normalize_alias(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def command_for_version(tool_key: str, cli_path: str, model_cfg: Dict) -> Optional[Sequence[str]]:
    if model_cfg.get("version_command"):
        return None
    if tool_key == "codex":
        return [cli_path, "--version"]
    if tool_key == "gemini":
        return [cli_path, "-v"]
    if tool_key == "crush":
        return [cli_path, "--version"]
    return None


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


def detect_cli_version(tool_key: str, model_cfg: Dict) -> Optional[str]:
    cli_path = model_cfg.get("cli_path") or tool_key
    if model_cfg.get("version_command"):
        result = run_process(shell_command(model_cfg["version_command"]), cwd=Path.cwd())
    else:
        argv = command_for_version(tool_key, cli_path, model_cfg)
        if not argv:
            return None
        result = run_process(argv, cwd=Path.cwd())
    if result["exit_code"] != 0:
        return None
    version = (result["stdout_text"] or result["stderr_text"]).strip()
    return version.splitlines()[0] if version else None


def parse_catalog_items(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def refresh_catalog(tool_key: str, model_cfg: Dict, tool_state: Dict, reason: str) -> Dict:
    cli_path = model_cfg.get("cli_path") or tool_key
    if tool_key == "crush":
        result = run_process([cli_path, "models"], cwd=Path.cwd())
    elif model_cfg.get("catalog"):
        result = run_process(shell_command(model_cfg["catalog"]), cwd=Path.cwd())
    else:
        return {
            "refreshed": False,
            "reason": None,
            "items": [],
            "error": None,
        }
    if result["exit_code"] != 0:
        return {
            "refreshed": False,
            "reason": reason,
            "items": tool_state.get("catalog", {}).get("items", []),
            "error": result["stderr_text"] or result["stdout_text"],
        }
    items = parse_catalog_items(result["stdout_text"])
    tool_state["catalog"] = {
        "items": items,
        "refreshed_at": now_iso(),
        "refresh_reason": reason,
    }
    return {
        "refreshed": True,
        "reason": reason,
        "items": items,
        "error": None,
    }


def needs_catalog_refresh(tool_state: Dict, version: Optional[str], force: bool = False) -> Optional[str]:
    if force:
        return "forced"
    if version and tool_state.get("version") and tool_state.get("version") != version:
        return "version_changed"
    catalog = tool_state.get("catalog", {})
    if not catalog.get("items"):
        return "missing_catalog"
    refreshed_at = catalog.get("refreshed_at")
    if not refreshed_at:
        return "missing_catalog"
    try:
        refreshed = datetime.fromisoformat(refreshed_at)
    except ValueError:
        return "stale_catalog"
    age = datetime.now().astimezone() - refreshed
    if age.total_seconds() >= CATALOG_TTL_SECONDS:
        return "stale_catalog"
    return None


def matching_candidates(items: Sequence[str], requested_model: str) -> List[str]:
    requested_norm = normalize_alias(requested_model)
    if not requested_norm:
        return []
    exact_matches: List[str] = []
    soft_matches: List[str] = []
    for item in items:
        normalized_item = normalize_alias(item)
        model_part = item.split("/", 1)[1] if "/" in item else item
        normalized_model = normalize_alias(model_part)
        if requested_norm in (normalized_item, normalized_model):
            exact_matches.append(item)
            continue
        if normalized_model.startswith(requested_norm) or requested_norm.startswith(normalized_model):
            soft_matches.append(item)
    return exact_matches or soft_matches


def ordered_candidates(alias_state: Dict, candidates: Sequence[str]) -> List[str]:
    canonical_target = alias_state.get("canonical_target")
    observations = alias_state.get("candidates", {})
    success_targets: List[str] = []
    unknown_targets: List[str] = []
    failed_targets: List[str] = []
    ordered: List[str] = []
    if canonical_target in candidates:
        ordered.append(canonical_target)
    for target in candidates:
        if target == canonical_target:
            continue
        status = observations.get(target, {}).get("last_status")
        if status == "success":
            success_targets.append(target)
        elif status in RETRY_NEXT_CANDIDATE_STATUSES:
            failed_targets.append(target)
        else:
            unknown_targets.append(target)
    return ordered + success_targets + unknown_targets + failed_targets


def resolve_model_target(
    tool_key: str,
    model_cfg: Dict,
    registry: Dict,
    requested_model: Optional[str],
    force_refresh: bool = False,
) -> Dict:
    tool_state = ensure_tool_state(registry, tool_key)
    cli_version = detect_cli_version(tool_key, model_cfg)
    if cli_version:
        tool_state["version_checked_at"] = now_iso()
    refresh_reason = None
    catalog_error = None
    if cli_version:
        refresh_reason = needs_catalog_refresh(tool_state, cli_version, force=force_refresh)
        if refresh_reason:
            refresh_result = refresh_catalog(tool_key, model_cfg, tool_state, refresh_reason)
            catalog_error = refresh_result["error"]
            if not refresh_result["refreshed"]:
                refresh_reason = refresh_result["reason"]
    tool_state["version"] = cli_version

    if not requested_model:
        requested_model = model_cfg.get("model_name")

    if not requested_model:
        return {
            "tool_key": tool_key,
            "requested_model": None,
            "resolved_model": None,
            "candidates": [],
            "cli_version": cli_version,
            "refresh_reason": refresh_reason,
            "catalog_error": catalog_error,
            "strategy": "static",
        }

    catalog_items = tool_state.get("catalog", {}).get("items", [])
    if not catalog_items:
        return {
            "tool_key": tool_key,
            "requested_model": requested_model,
            "resolved_model": requested_model,
            "candidates": [requested_model],
            "cli_version": cli_version,
            "refresh_reason": refresh_reason,
            "catalog_error": catalog_error,
            "strategy": "static",
        }

    alias_key = normalize_alias(requested_model)
    alias_state = tool_state.setdefault("aliases", {}).setdefault(
        alias_key,
        {
            "requested_model": requested_model,
            "canonical_target": None,
            "last_verified_at": None,
            "source": None,
            "candidates": {},
        },
    )
    alias_state["requested_model"] = requested_model

    candidates = matching_candidates(catalog_items, requested_model)
    if not candidates and requested_model in catalog_items:
        candidates = [requested_model]
    candidates = ordered_candidates(alias_state, candidates)
    resolved_model = candidates[0] if candidates else requested_model
    if not candidates:
        candidates = [requested_model]
    return {
        "tool_key": tool_key,
        "requested_model": requested_model,
        "resolved_model": resolved_model,
        "candidates": list(candidates),
        "cli_version": cli_version,
        "refresh_reason": refresh_reason,
        "catalog_error": catalog_error,
        "strategy": "catalog",
    }


def observation_error_excerpt(stdout_text: str, stderr_text: str) -> str:
    excerpt = "\n".join(part for part in [stderr_text.strip(), stdout_text.strip()] if part)
    excerpt = excerpt.strip()
    return excerpt[:500]


def record_model_observation(
    registry: Dict,
    tool_key: str,
    requested_model: Optional[str],
    resolved_model: Optional[str],
    outcome: str,
    error_excerpt: str,
) -> None:
    if not requested_model or not resolved_model:
        return
    tool_state = ensure_tool_state(registry, tool_key)
    alias_key = normalize_alias(requested_model)
    alias_state = tool_state.setdefault("aliases", {}).setdefault(
        alias_key,
        {
            "requested_model": requested_model,
            "canonical_target": None,
            "last_verified_at": None,
            "source": None,
            "candidates": {},
        },
    )
    alias_state["requested_model"] = requested_model
    candidate = alias_state.setdefault("candidates", {}).setdefault(resolved_model, {})
    candidate["last_status"] = outcome
    candidate["last_seen_at"] = now_iso()
    if error_excerpt:
        candidate["last_error"] = error_excerpt
    if outcome == "success":
        candidate["last_success_at"] = now_iso()
        alias_state["canonical_target"] = resolved_model
        alias_state["last_verified_at"] = now_iso()
        alias_state["source"] = "learned_from_success"
    elif alias_state.get("canonical_target") == resolved_model and outcome in RETRY_NEXT_CANDIDATE_STATUSES:
        alias_state["canonical_target"] = None


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

    if tool_key == "gemini":
        argv = [cli_path]
        if requested_model:
            argv.extend(["-m", requested_model])
        argv.extend(["-p", prompt_text])
        return CommandSpec(argv=argv, stdin_text=None, output_mode="stdout")

    if tool_key == "crush":
        argv = [cli_path, "run", "--quiet"]
        model_target = resolved_model or requested_model or model_cfg.get("model_name")
        if model_target:
            argv.extend(["--model", model_target])
        argv.append(prompt_text)
        return CommandSpec(argv=argv, stdin_text=None, output_mode="stdout")

    invoke_template = model_cfg.get("invoke")
    if not invoke_template:
        raise CrossReviewRuntimeError(
            f"Model '{tool_key}' is not supported by the structured runtime and has no invoke template."
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
    registry_path = expand_path(args.registry)
    run_dir = expand_path(args.run_dir)
    runtime_paths = prepare_run_dirs(run_dir)
    status = load_status(runtime_paths["status_file"], run_dir.name)

    model_key = args.model
    prompt_file = expand_path(args.prompt_file)
    retry_prompt_file = expand_path(args.retry_prompt_file) if args.retry_prompt_file else None
    output_path = output_file_path(run_dir, args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = expand_path(args.cwd) if args.cwd else Path.cwd()

    call_record = {
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
    status["calls"][args.call_id] = call_record
    save_status(runtime_paths["status_file"], status)

    config = load_yaml(config_path)
    models = config.get("models") or {}
    if model_key not in models:
        raise CrossReviewRuntimeError(f"Model '{model_key}' not found in config: {config_path}")
    model_cfg = models[model_key]
    registry = load_registry(registry_path)
    prompt_text = read_text_file(prompt_file)
    retry_prompt_text = read_text_file(retry_prompt_file) if retry_prompt_file else prompt_text

    resolution = resolve_model_target(
        tool_key=model_key,
        model_cfg=model_cfg,
        registry=registry,
        requested_model=args.requested_model,
        force_refresh=args.force_refresh,
    )
    save_registry(registry_path, registry)

    candidates = resolution["candidates"] or [resolution["resolved_model"]]
    attempts: List[Dict] = []
    final_status = "transport_failed"
    final_validation = None
    retries_used = 0
    successful_output = None
    resolved_model = resolution["resolved_model"]

    prompt_variants = [("primary", prompt_text)]
    if args.max_retries > 0:
        prompt_variants.append(("retry", retry_prompt_text))

    for candidate_index, candidate in enumerate(candidates):
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
                requested_model=resolution["requested_model"],
                resolved_model=candidate,
                min_output_bytes=args.min_output_bytes,
            )
            attempts.append(
                {
                    "attempt": attempt_number,
                    "prompt_variant": prompt_variant,
                    "resolved_model": candidate,
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
            retries_used = max(0, len(attempts) - 1)

            record_model_observation(
                registry=registry,
                tool_key=model_key,
                requested_model=resolution["requested_model"],
                resolved_model=candidate,
                outcome="success"
                if attempt_result["transport_validation"]["passed"]
                else attempt_result["failure_class"],
                error_excerpt=observation_error_excerpt(
                    stdout_text=attempt_result["output_path"].read_text(encoding="utf-8"),
                    stderr_text=attempt_result["stderr_path"].read_text(encoding="utf-8"),
                ),
            )
            save_registry(registry_path, registry)

            if attempt_result["transport_validation"]["passed"]:
                successful_output = attempt_result["output_path"]
                resolved_model = candidate
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

            failure_class = attempt_result["failure_class"]
            should_try_next_candidate = (
                failure_class in RETRY_NEXT_CANDIDATE_STATUSES
                and candidate_index < len(candidates) - 1
            )
            if should_try_next_candidate:
                break

            if prompt_index >= args.max_retries:
                break

        if final_status in SUCCESS_STATUSES:
            break
        if candidate_index >= len(candidates) - 1:
            continue

    if successful_output:
        output_path.write_text(successful_output.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        output_path.write_text("", encoding="utf-8")
        final_validation = final_validation or {
            "transport": {"passed": False, "issues": ["all_attempts_failed"]},
            "semantic": {"passed": False, "issues": ["transport_validation_failed"]},
        }

    call_record = {
        "call_id": args.call_id,
        "model_key": model_key,
        "requested_model": resolution["requested_model"],
        "resolved_model": resolved_model,
        "output_file": relpath(output_path, run_dir),
        "cwd": str(cwd),
        "attempts": attempts,
        "retries_used": retries_used,
        "final_status": final_status,
        "validation": final_validation,
        "resolution": resolution,
        "updated_at": now_iso(),
    }
    status = load_status(runtime_paths["status_file"], run_dir.name)
    status["calls"][args.call_id] = call_record
    save_status(runtime_paths["status_file"], status)
    return 0 if final_status in SUCCESS_STATUSES else 1


def sync_registry(args: argparse.Namespace) -> int:
    config_path = expand_path(args.config)
    registry_path = expand_path(args.registry)
    config = load_yaml(config_path)
    registry = load_registry(registry_path)
    models = config.get("models") or {}
    results: List[Dict] = []
    for model_key, model_cfg in models.items():
        if args.model and model_key != args.model:
            continue
        tool_state = ensure_tool_state(registry, model_key)
        version = detect_cli_version(model_key, model_cfg)
        tool_state["version_checked_at"] = now_iso()
        if version:
            refresh_reason = needs_catalog_refresh(tool_state, version, force=args.force_refresh)
            if refresh_reason:
                refresh_result = refresh_catalog(model_key, model_cfg, tool_state, refresh_reason)
            else:
                refresh_result = {"refreshed": False, "reason": None, "items": tool_state["catalog"]["items"], "error": None}
            tool_state["version"] = version
        else:
            refresh_result = {"refreshed": False, "reason": None, "items": tool_state["catalog"]["items"], "error": "version_check_failed"}
        results.append(
            {
                "model": model_key,
                "version": tool_state.get("version"),
                "catalog_size": len(tool_state.get("catalog", {}).get("items", [])),
                "refresh_reason": refresh_result["reason"],
                "catalog_error": refresh_result["error"],
            }
        )
    save_registry(registry_path, registry)
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


def resolve_model(args: argparse.Namespace) -> int:
    config_path = expand_path(args.config)
    registry_path = expand_path(args.registry)
    config = load_yaml(config_path)
    models = config.get("models") or {}
    if args.model not in models:
        raise CrossReviewRuntimeError(f"Model '{args.model}' not found in config: {config_path}")
    registry = load_registry(registry_path)
    resolution = resolve_model_target(
        tool_key=args.model,
        model_cfg=models[args.model],
        registry=registry,
        requested_model=args.requested_model,
        force_refresh=args.force_refresh,
    )
    save_registry(registry_path, registry)
    print(json.dumps(resolution, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    default_config = str(Path.home() / ".config" / "cross-review" / "models.yaml")
    default_registry = str(Path.home() / ".config" / "cross-review" / "registry.json")
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    execute_parser = subparsers.add_parser("execute", help="Run one external model call through the runtime wrapper.")
    execute_parser.add_argument("--config", default=default_config, help="Path to models.yaml")
    execute_parser.add_argument("--registry", default=default_registry, help="Path to registry.json")
    execute_parser.add_argument("--run-dir", required=True, help="Run directory for status.json, logs/, invalid/")
    execute_parser.add_argument("--call-id", required=True, help="Stable call id such as r1.gemini")
    execute_parser.add_argument("--model", required=True, help="Model key from models.yaml")
    execute_parser.add_argument("--prompt-file", required=True, help="Prompt file path")
    execute_parser.add_argument("--retry-prompt-file", help="Optional retry prompt file path")
    execute_parser.add_argument("--output-file", required=True, help="Output file path, relative to run dir or absolute")
    execute_parser.add_argument("--cwd", help="Working directory for the external CLI")
    execute_parser.add_argument("--requested-model", help="Requested model alias such as GLM5.1")
    execute_parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help="Prompt retries per candidate")
    execute_parser.add_argument("--min-output-bytes", type=int, default=DEFAULT_MIN_OUTPUT_BYTES, help="Minimum sanitized output size")
    execute_parser.add_argument("--force-refresh", action="store_true", help="Force a catalog refresh before resolution")
    execute_parser.set_defaults(func=execute_call)

    sync_parser = subparsers.add_parser("sync-registry", help="Refresh CLI versions and model catalogs into registry.json")
    sync_parser.add_argument("--config", default=default_config, help="Path to models.yaml")
    sync_parser.add_argument("--registry", default=default_registry, help="Path to registry.json")
    sync_parser.add_argument("--model", help="Optional single model key to sync")
    sync_parser.add_argument("--force-refresh", action="store_true", help="Force catalog refresh")
    sync_parser.set_defaults(func=sync_registry)

    resolve_parser = subparsers.add_parser("resolve-model", help="Resolve a requested model alias using the registry.")
    resolve_parser.add_argument("--config", default=default_config, help="Path to models.yaml")
    resolve_parser.add_argument("--registry", default=default_registry, help="Path to registry.json")
    resolve_parser.add_argument("--model", required=True, help="Model key from models.yaml")
    resolve_parser.add_argument("--requested-model", required=True, help="Requested model alias")
    resolve_parser.add_argument("--force-refresh", action="store_true", help="Force catalog refresh")
    resolve_parser.set_defaults(func=resolve_model)

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
