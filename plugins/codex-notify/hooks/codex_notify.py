#!/usr/bin/env python3
"""Codex Notify Stop hook entrypoint.

This script is intentionally fail-open: every path returns 0 and writes
diagnostics to the plugin data log instead of stdout/stderr.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import tomllib
from typing import Any
from urllib import parse, request


UTC = dt.timezone.utc
PLUGIN_ROOT = Path(os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
PLUGIN_DATA = Path(
    os.environ.get(
        "PLUGIN_DATA",
        str(Path.home() / ".codex" / "codex-notify"),
    )
).expanduser()
USER_DATA = Path.home() / ".codex" / "codex-notify"
LEGACY_USER_DATA = Path.home() / ".codex" / "codex-pushover-notify"
LOG_PATH = PLUGIN_DATA / "notify.log"
DEFAULT_CONFIG_PATH = PLUGIN_DATA / "config.toml"
DEFAULT_ENV_PATH = PLUGIN_DATA / ".pushover.env"
DEFAULT_STATE_DB_PATH = PLUGIN_DATA / "notify_state.sqlite3"
DEFAULT_HISTORY_DB_PATH = PLUGIN_DATA / "notify_history.sqlite3"
PUSHOVER_TITLE_LIMIT = 250
PUSHOVER_MESSAGE_LIMIT = 1024
PUSHOVER_URL_LIMIT = 512
PUSHOVER_URL_TITLE_LIMIT = 100


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "default_policy": "always",
    "notify_on_failure": False,
    "notify_subagents": False,
    "long_run_seconds": 300,
    "dedupe_enabled": True,
    "max_title_chars": 160,
    "max_message_chars": 1024,
    "max_outcome_chars": 560,
    "max_task_chars": 220,
    "task_summary_mode": "local",
    "task_summary_max_chars": 120,
    "task_summary_codex_command": "",
    "task_summary_codex_model": "",
    "task_summary_timeout_seconds": 8,
    "max_verification_chars": 180,
    "fallback_scope_label": "workspace",
    "title_template": "{headline}",
    "message_template": "{details}",
    "include_duration": True,
    "include_host": True,
    "include_model": True,
    "include_task": True,
    "include_verification": True,
    "include_git": True,
    "git_check_timeout_seconds": 1,
    "pushover_html": True,
    "attention_status_terms": [
        "failed",
        "failure",
        "error",
        "errors",
        "blocked",
        "unable",
        "exception",
        "traceback",
        "cancelled",
        "canceled",
        "could not",
        "cannot",
        "can't",
    ],
    "negated_status_terms": [
        "no error",
        "no errors",
        "no failure",
        "no failures",
        "no issue",
        "no issues",
        "no blocker",
        "no blockers",
        "without error",
        "without errors",
        "without failure",
        "without failures",
        "without issue",
        "without issues",
        "without blocker",
        "without blockers",
        "failure mode",
        "failure modes",
        "not blocked",
        "not unable",
    ],
    "always_tags": ["[notify]", "[long-run]"],
    "skip_tags": ["[no-notify]", "[notify:none]"],
    "include_cwds": [],
    "exclude_cwds": [],
    "focus_policy": "always",
    "focus_app_names": ["Codex"],
    "focus_unknown_policy": "send",
    "focus_check_timeout_seconds": 1,
    "retry_attempts": 2,
    "retry_backoff_seconds": [1, 2],
    "http_timeout_seconds": 5,
    "pushover_priority": 0,
    "pushover_sound": "",
    "pushover_device": "",
    "pushover_env_path": "",
    "state_db_path": "",
    "history_enabled": True,
    "history_db_path": "",
    "history_store_messages": True,
    "history_retention_days": 90,
}

NOTIFICATION_HISTORY_COLUMNS: list[tuple[str, str]] = [
    ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("created_at", "INTEGER NOT NULL DEFAULT 0"),
    ("turn_id", "TEXT NOT NULL DEFAULT ''"),
    ("session_id", "TEXT"),
    ("request_id", "TEXT"),
    ("sample", "INTEGER NOT NULL DEFAULT 0"),
    ("dry_run", "INTEGER NOT NULL DEFAULT 0"),
    ("policy", "TEXT"),
    ("reason", "TEXT"),
    ("status", "TEXT"),
    ("duration_seconds", "REAL"),
    ("title", "TEXT NOT NULL DEFAULT ''"),
    ("message", "TEXT NOT NULL DEFAULT ''"),
    ("url", "TEXT"),
    ("url_title", "TEXT"),
    ("title_chars", "INTEGER NOT NULL DEFAULT 0"),
    ("message_chars", "INTEGER NOT NULL DEFAULT 0"),
    ("message_html", "INTEGER NOT NULL DEFAULT 0"),
    ("cwd", "TEXT"),
    ("repo", "TEXT"),
    ("branch", "TEXT"),
    ("git_sha", "TEXT"),
    ("git_dirty", "TEXT"),
    ("model", "TEXT"),
    ("permission_mode", "TEXT"),
    ("thread_source", "TEXT"),
    ("subagent_name", "TEXT"),
    ("originator", "TEXT"),
    ("focus_reason", "TEXT"),
    ("frontmost_app", "TEXT"),
    ("payload_json", "TEXT"),
]
NOTIFICATION_HISTORY_INSERT_COLUMNS = [
    column
    for column, _definition in NOTIFICATION_HISTORY_COLUMNS
    if column != "id"
]

MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
MARKDOWN_BOLD_RE = re.compile(r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)")
MARKDOWN_STRONG_UNDERSCORE_RE = re.compile(r"(?<!_)__([^_\n]+)__(?!_)")
MARKDOWN_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
MARKDOWN_ITALIC_UNDERSCORE_RE = re.compile(r"(?<!\w)_([^_\n]+)_(?!\w)")
MARKDOWN_STRIKE_RE = re.compile(r"~~([^~\n]+)~~")
PUSHOVER_HTML_TAG_RE = re.compile(r"<\s*(/?)\s*(b|i|u|font|a|br)\b[^>]*>", re.IGNORECASE)
GITHUB_PR_URL_RE = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([0-9]+)"
)
PR_LINK_CONTEXT_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:"
    r"(?:pr|pull\s+request)\b\s*(?::|#|https?://)"
    r"|(?:opened|created|published|merged|updated|ready|draft)\b[^\n]*"
    r"(?:\bpr\b|\bpull\s+request\b)"
    r"|merged\s*:"
    r")",
    re.IGNORECASE,
)
HTTP_URL_RE = re.compile(r"https?://[^\s)>\]]+")
VERIFICATION_HINT_RE = re.compile(
    r"\b(pytest|unittest|py_compile|npm test|npm run build|pnpm test|"
    r"pnpm run build|ruff|mypy|tsc|cargo test|go test)\b",
    re.IGNORECASE,
)
INTERNAL_CONTEXT_RE = re.compile(
    r"(?:# AGENTS\.md instructions[^\n]*\n)?<INSTRUCTIONS>.*?</INSTRUCTIONS>",
    re.DOTALL,
)
ENVIRONMENT_CONTEXT_RE = re.compile(
    r"<environment_context>.*?</environment_context>",
    re.DOTALL,
)
SKILL_BLOCK_RE = re.compile(r"<skill\b[^>]*>.*?(?:</skill>|$)", re.DOTALL | re.IGNORECASE)
INLINE_SKILL_LINK_RE = re.compile(r"\[\$([^\]\n]+)\]\([^)]+\)")
SELECTED_TEXT_REQUEST_RE = re.compile(
    r"(?ims)(?:^|\n)\s*# Selected text:\s*.*^\s*## My request for Codex:\s*(?P<request>.*)$"
)


def log_event(event: str, **fields: Any) -> None:
    try:
        PLUGIN_DATA.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": dt.datetime.now(tz=UTC).isoformat(),
            "event": event,
            **fields,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")
    except Exception:
        pass


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def is_truthy_env(name: str) -> bool:
    return is_truthy(os.environ.get(name, ""))


def safe_int(value: Any, default: int, *, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        return max(minimum, parsed)
    return parsed


def bounded_int(
    value: Any,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    return min(maximum, safe_int(value, default, minimum=minimum))


def safe_float(value: Any, default: float, *, minimum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        return max(minimum, parsed)
    return parsed


def safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def safe_float_list(value: Any, default: list[float]) -> list[float]:
    if not isinstance(value, list):
        return default
    parsed: list[float] = []
    for item in value:
        try:
            parsed.append(max(0.0, float(item)))
        except (TypeError, ValueError):
            continue
    return parsed or default


def term_regex(terms: list[str]) -> re.Pattern[str] | None:
    patterns: list[str] = []
    for term in terms:
        normalized = str(term).strip()
        if not normalized:
            continue
        prefix = r"(?<!\w)" if normalized[0].isalnum() else ""
        suffix = r"(?!\w)" if normalized[-1].isalnum() else ""
        patterns.append(prefix + re.escape(normalized) + suffix)
    if not patterns:
        return None
    return re.compile("|".join(patterns), re.IGNORECASE)


def remove_terms(text: str, terms: list[str]) -> str:
    regex = term_regex(terms)
    if not regex:
        return text
    return regex.sub(" ", text)


def has_term(text: str, terms: list[str]) -> bool:
    regex = term_regex(terms)
    return bool(regex and regex.search(text))


class SafeFormatValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def render_template(template: Any, values: dict[str, Any], fallback: str) -> str:
    normalized_values = SafeFormatValues(
        {key: "" if value is None else str(value) for key, value in values.items()}
    )
    raw = str(template or fallback)
    try:
        rendered = raw.format_map(normalized_values).strip()
    except ValueError as exc:
        log_event("template_render_failed", template=raw, error=str(exc))
        rendered = ""
    if rendered:
        return rendered
    return fallback.format_map(normalized_values).strip()


def html_escape_text(value: str) -> str:
    return html.escape(str(value), quote=False)


def clean_url(value: str) -> str:
    return value.rstrip(".,;:!?")


def github_pr_label_from_url(url: str) -> str:
    match = GITHUB_PR_URL_RE.search(clean_url(url))
    if not match:
        return clean_url(url)
    owner, repo, number = match.groups()
    return f"{owner}/{repo}#{number}"


def previous_nonempty_line(lines: list[str], index: int) -> str:
    for line in reversed(lines[:index]):
        if line.strip():
            return line
    return ""


def has_pr_link_context(line: str, previous_line: str) -> bool:
    return bool(
        PR_LINK_CONTEXT_RE.search(line)
        or (GITHUB_PR_URL_RE.search(line) and PR_LINK_CONTEXT_RE.search(previous_line))
    )


def notification_link_from_message(message: str) -> tuple[str, str] | None:
    lines = message.splitlines()
    for index, line in enumerate(lines):
        if not has_pr_link_context(line, previous_nonempty_line(lines, index)):
            continue
        for match in MARKDOWN_LINK_RE.finditer(line):
            label, url = match.groups()
            if GITHUB_PR_URL_RE.search(url):
                return clean_url(url), label.strip() or github_pr_label_from_url(url)

    for index, line in enumerate(lines):
        if not has_pr_link_context(line, previous_nonempty_line(lines, index)):
            continue
        pr_match = GITHUB_PR_URL_RE.search(line)
        if pr_match:
            url = clean_url(pr_match.group(0))
            return url, github_pr_label_from_url(url)

    return None


def plain_notification_text(text: str) -> str:
    def replace_markdown_link(match: re.Match[str]) -> str:
        label, url = match.groups()
        if label.strip():
            return label.strip()
        return github_pr_label_from_url(url)

    without_markdown = MARKDOWN_LINK_RE.sub(replace_markdown_link, text)
    without_github_urls = GITHUB_PR_URL_RE.sub(
        lambda match: github_pr_label_from_url(match.group(0)),
        without_markdown,
    )
    return strip_markdown_markup(without_github_urls)


def strip_markdown_markup(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"(?m)^\s*```[A-Za-z0-9_-]*\s*$", "", cleaned)
    cleaned = cleaned.replace("```", "")
    cleaned = MARKDOWN_INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", cleaned)
    cleaned = re.sub(r"(?m)^\s{0,3}>\s?", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", cleaned)
    for pattern in (
        MARKDOWN_BOLD_RE,
        MARKDOWN_STRONG_UNDERSCORE_RE,
        MARKDOWN_ITALIC_RE,
        MARKDOWN_ITALIC_UNDERSCORE_RE,
        MARKDOWN_STRIKE_RE,
    ):
        cleaned = pattern.sub(r"\1", cleaned)
    return cleaned


def load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    return payload if isinstance(payload, dict) else {}


def load_simple_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    config_override = os.environ.get("CODEX_PUSHOVER_CONFIG", "").strip()
    if config_override:
        config_path = Path(config_override).expanduser()
    else:
        config_candidates = [
            DEFAULT_CONFIG_PATH,
            USER_DATA / "config.toml",
            LEGACY_USER_DATA / "config.toml",
        ]
        config_path = next(
            (candidate for candidate in config_candidates if candidate.exists()),
            USER_DATA / "config.toml",
        )
    config.update(load_toml(config_path))
    config["loaded_config_path"] = str(config_path) if config_path.exists() else None

    env_paths: list[Path] = []
    env_override = os.environ.get("CODEX_PUSHOVER_ENV", "").strip()
    if env_override:
        env_paths.append(Path(env_override).expanduser())
    configured_env = str(config.get("pushover_env_path") or "").strip()
    if configured_env:
        env_paths.append(Path(configured_env).expanduser())
    env_paths.extend(
        [
            DEFAULT_ENV_PATH,
            USER_DATA / ".pushover.env",
            LEGACY_USER_DATA / ".pushover.env",
        ]
    )

    for env_path in env_paths:
        values = load_simple_env(env_path)
        if values.get("PUSHOVER_USER_KEY") and values.get("PUSHOVER_APP_TOKEN"):
            config.update(values)
            config["loaded_pushover_env_path"] = str(env_path)
            break

    return config


def parse_hook_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError as exc:
        log_event("invalid_payload_json", error=str(exc))
        return {}


def normalize_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("hook_event_name") == "Stop":
        return {
            "source": "stop",
            "session_id": payload.get("session_id"),
            "turn_id": payload.get("turn_id"),
            "transcript_path": payload.get("transcript_path"),
            "cwd": payload.get("cwd") or "",
            "model": payload.get("model"),
            "permission_mode": payload.get("permission_mode"),
            "thread_source": payload.get("thread_source") or "",
            "subagent_name": payload.get("subagent_name") or "",
            "originator": payload.get("originator") or "",
            "stop_hook_active": bool(payload.get("stop_hook_active")),
            "last_assistant_message": payload.get("last_assistant_message") or "",
            "latest_input": "",
        }

    return None


def parse_iso8601(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def transcript_items(transcript_path: str | None) -> list[dict[str, Any]]:
    if not transcript_path:
        return []
    path = Path(transcript_path).expanduser()
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    item = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    items.append(item)
    except OSError:
        return []
    return items


def session_meta_from_transcript(transcript_path: str | None) -> dict[str, Any]:
    if not transcript_path:
        return {}
    path = Path(transcript_path).expanduser()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            first_line = handle.readline().strip()
    except OSError:
        return {}
    if not first_line:
        return {}
    try:
        first_item = json.loads(first_line)
    except json.JSONDecodeError:
        return {}
    if not isinstance(first_item, dict) or first_item.get("type") != "session_meta":
        return {}
    payload = first_item.get("payload")
    return payload if isinstance(payload, dict) else {}


def subagent_name_from_source(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    subagent = source.get("subagent")
    if isinstance(subagent, str):
        return subagent
    if not isinstance(subagent, dict):
        return ""
    for key in ("name", "type", "id", "other"):
        value = subagent.get(key)
        if value:
            return str(value)
    for key, value in subagent.items():
        if value:
            return str(value)
        return str(key)
    return ""


def apply_session_metadata(event: dict[str, Any], metadata: dict[str, Any]) -> None:
    source = metadata.get("source")
    thread_source = str(
        event.get("thread_source")
        or metadata.get("thread_source")
        or ("subagent" if isinstance(source, dict) and "subagent" in source else "")
    )
    event["thread_source"] = thread_source
    event["subagent_name"] = str(
        event.get("subagent_name") or subagent_name_from_source(source)
    )
    event["originator"] = str(event.get("originator") or metadata.get("originator") or "")


def is_subagent_event(event: dict[str, Any]) -> bool:
    return str(event.get("thread_source") or "").strip().lower() == "subagent"


def extract_text_parts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(extract_text_parts(item))
        return parts
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("text", "content", "message"):
            if key in value:
                parts.extend(extract_text_parts(value[key]))
        return parts
    return []


def latest_user_input_from_transcript(items: list[dict[str, Any]]) -> str:
    latest = ""
    for item in items:
        payload = item.get("payload") or {}
        if item.get("type") != "response_item":
            continue
        if payload.get("type") != "message" or payload.get("role") != "user":
            continue
        text = "\n".join(extract_text_parts(payload.get("content"))).strip()
        if text and not text.startswith("<hook_prompt"):
            candidate = strip_internal_context(text).strip()
            if candidate:
                latest = candidate
    return latest


def extract_turn_duration(items: list[dict[str, Any]], turn_id: str | None) -> float | None:
    if not turn_id:
        return None
    start: dt.datetime | None = None
    end: dt.datetime | None = None
    for item in items:
        payload = item.get("payload") or {}
        timestamp = parse_iso8601(item.get("timestamp"))
        if not timestamp:
            continue
        if payload.get("turn_id") != turn_id:
            continue
        if payload.get("type") == "task_started":
            start = timestamp
        elif payload.get("type") == "task_complete":
            end = timestamp
    if start and end:
        return max(0.0, (end - start).total_seconds())
    if start:
        return max(0.0, (dt.datetime.now(tz=UTC) - start).total_seconds())
    return None


def truncate_text(text: str, max_chars: int) -> str:
    return shorten_text(text, max_chars, ellipsis=True)


def shorten_text(text: str, max_chars: int, *, ellipsis: bool = False) -> str:
    lines = [" ".join(line.split()) for line in str(text).splitlines()]
    compact = "\n".join(line for line in lines if line)
    if len(compact) <= max_chars:
        return compact
    suffix = "..." if ellipsis else ""
    if max_chars <= len(suffix):
        return "." * max(0, max_chars)

    budget = max_chars - len(suffix)
    candidate = compact[:budget].rstrip()
    newline_index = candidate.rfind("\n")
    if newline_index >= max(20, int(budget * 0.65)):
        candidate = candidate[:newline_index].rstrip()
    else:
        whitespace_indexes = [match.start() for match in re.finditer(r"\s+", candidate)]
        minimum_index = max(10, int(budget * 0.65))
        word_index = next(
            (index for index in reversed(whitespace_indexes) if index >= minimum_index),
            -1,
        )
        if word_index >= 0:
            candidate = candidate[:word_index].rstrip()

    candidate = candidate.rstrip(" .,;:-")
    if candidate:
        return f"{candidate}{suffix}"
    return suffix or compact[:max_chars].strip()


def format_duration(duration_seconds: float | None) -> str:
    if duration_seconds is None:
        return "duration unknown"
    total = int(round(duration_seconds))
    if total < 60:
        return f"{total}s"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m" if seconds == 0 else f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def classify_status(message: str, config: dict[str, Any] | None = None) -> str:
    source_config = config or DEFAULT_CONFIG
    negated_terms = safe_string_list(source_config.get("negated_status_terms"))
    attention_terms = safe_string_list(source_config.get("attention_status_terms"))
    cleaned = remove_terms(message, negated_terms)
    if has_term(cleaned, attention_terms):
        return "Needs attention"
    return "Done"


def is_verification_heading(line: str) -> bool:
    normalized = line.strip("#*: ").casefold()
    return normalized in {
        "test",
        "tests",
        "verification",
        "verified",
        "validation",
    } or normalized.startswith(
        (
            "test:",
            "tests:",
            "verification:",
            "verified:",
            "validated:",
            "validation:",
        )
    )


def strip_verification_sections(text: str) -> str:
    kept: list[str] = []
    skipping = False
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip(" -*`").split())
        if not line:
            if not skipping:
                kept.append(raw_line)
            skipping = False
            continue
        if is_verification_heading(line):
            skipping = True
            continue
        if skipping:
            if len(line) <= 32 and line.endswith(":") and not VERIFICATION_HINT_RE.search(line):
                skipping = False
                kept.append(raw_line)
            continue
        kept.append(raw_line)
    return "\n".join(kept)


def extract_outcome(message: str, max_chars: int) -> str:
    text = plain_notification_text(strip_verification_sections(message)).strip()
    if not text:
        text = plain_notification_text(message).strip() or "Codex finished."
    return shorten_text(text, max_chars)


def strip_internal_context(text: str) -> str:
    without_skills = SKILL_BLOCK_RE.sub(" ", text)
    without_skill_links = INLINE_SKILL_LINK_RE.sub(r"\1", without_skills)
    without_instructions = INTERNAL_CONTEXT_RE.sub(" ", without_skill_links)
    without_environment = ENVIRONMENT_CONTEXT_RE.sub(" ", without_instructions)
    selected_request = SELECTED_TEXT_REQUEST_RE.search(without_environment)
    if selected_request:
        return selected_request.group("request")
    return without_environment


def strip_config_tags(text: str, config: dict[str, Any]) -> str:
    cleaned = text
    for tag in safe_string_list(config.get("always_tags")) + safe_string_list(
        config.get("skip_tags")
    ):
        cleaned = re.sub(re.escape(tag), " ", cleaned, flags=re.IGNORECASE)
    return cleaned


def normalize_task_summary(summary: str, max_chars: int) -> str:
    line = next((line.strip() for line in str(summary).splitlines() if line.strip()), "")
    line = re.sub(r"^(?:task|summary)\s*:\s*", "", line, flags=re.IGNORECASE)
    line = line.strip(" \t\r\n\"'`*_")
    line = " ".join(line.split())
    line = line.rstrip(" .,:;!?-")
    return shorten_text(line, max_chars).strip(" .,:;!?-")


def local_task_summary(text: str, max_chars: int) -> str:
    lowered = text.casefold()
    if lowered.startswith("<subagent_notification"):
        return "review subagent completion"

    has_prod = any(term in lowered for term in ("prod rollout", "production rollout", "roll it out"))
    has_terraform = "terraform" in lowered
    if has_prod and has_terraform:
        topic = "prod rollout and terraform gaps" if "gap" in lowered else "prod rollout and terraform"
        if any(term in lowered for term in ("question", "next step", "what", "how", "gap")):
            return shorten_text(f"find next steps for {topic}", max_chars)
        return shorten_text(topic, max_chars)

    cleaned = re.sub(
        r"\b(?:please|can you|could you|will you|would you|i think|i was under|"
        r"we did a bunch of work|it's about time|some questions about this though)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.split(r"(?<=[.!?])\s+|\s+(?:but|though|however)\s+", cleaned, maxsplit=1)[0]
    cleaned = " ".join(cleaned.split())
    return normalize_task_summary(cleaned, max_chars)


def codex_command_path(config: dict[str, Any]) -> str:
    configured = str(config.get("task_summary_codex_command") or "").strip()
    candidates = [configured] if configured else [
        "codex",
        "/Applications/Codex.app/Contents/Resources/codex",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if "/" in candidate:
            if Path(candidate).exists():
                return candidate
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return ""


def codex_task_summary(text: str, config: dict[str, Any], max_chars: int) -> str:
    command = codex_command_path(config)
    if not command:
        return ""

    prompt = (
        "Summarize the user task for a push notification.\n"
        "Return exactly one short action phrase, 4 to 10 words.\n"
        "Do not use markdown, quotes, explanations, labels, or trailing punctuation.\n"
        "Focus on the objective, not background details.\n\n"
        f"User task:\n{shorten_text(text, 4000)}\n"
    )
    timeout = safe_float(config.get("task_summary_timeout_seconds"), 8.0, minimum=0.5)
    model = str(config.get("task_summary_codex_model") or "").strip()

    with tempfile.TemporaryDirectory(prefix="codex-notify-summary-") as temp_dir:
        output_path = Path(temp_dir) / "summary.txt"
        args = [
            command,
            "-c",
            'model_reasoning_effort="none"',
            "--disable",
            "hooks",
            "--sandbox",
            "read-only",
            "-a",
            "never",
        ]
        if model:
            args.extend(["--model", model])
        args.extend(
            [
                "exec",
                "--ignore-user-config",
                "--ephemeral",
                "--skip-git-repo-check",
                "--ignore-rules",
                "-C",
                tempfile.gettempdir(),
                "-o",
                str(output_path),
            ]
        )
        args.append("-")
        try:
            completed = subprocess.run(
                args,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except Exception as exc:
            log_event("task_summary_failed", provider="codex", error=str(exc))
            return ""

        if completed.returncode != 0:
            log_event(
                "task_summary_failed",
                provider="codex",
                returncode=completed.returncode,
                stderr=shorten_text(completed.stderr or "", 300),
            )
            return ""

        try:
            summary = output_path.read_text(encoding="utf-8")
        except OSError:
            summary = completed.stdout or ""
    return normalize_task_summary(summary, max_chars)


def task_summary(text: str, config: dict[str, Any], max_chars: int) -> str:
    mode = str(config.get("task_summary_mode") or "auto").strip().lower()
    if mode in {"off", "none", "false", "0"}:
        return ""
    if mode in {"auto", "codex", "llm"}:
        summary = codex_task_summary(text, config, max_chars)
        if summary:
            return summary
    return local_task_summary(text, max_chars)


def extract_task(latest_input: str, config: dict[str, Any], max_chars: int) -> str:
    text = plain_notification_text(strip_internal_context(latest_input))
    text = strip_config_tags(text, config)
    text = " ".join(text.split())
    if not text:
        return ""
    summary_chars = bounded_int(
        config.get("task_summary_max_chars"),
        min(max_chars, 120),
        minimum=24,
        maximum=max_chars,
    )
    summary = task_summary(text, config, summary_chars)
    return summary or shorten_text(text, max_chars)


def extract_verification_summary(message: str, max_chars: int) -> str:
    plain = plain_notification_text(message)
    candidates: list[str] = []
    capture_following = False
    for raw_line in plain.splitlines():
        line = " ".join(raw_line.strip(" -*`").split())
        if not line:
            capture_following = False
            continue

        if is_verification_heading(line):
            if ":" in line:
                value = line.split(":", 1)[1].strip()
                if value:
                    candidates.append(value)
            capture_following = True
            continue

        if capture_following:
            if len(line) <= 32 and line.endswith(":") and not VERIFICATION_HINT_RE.search(line):
                capture_following = False
            else:
                candidates.append(line)
                if len(candidates) >= 3:
                    capture_following = False
            continue

        if VERIFICATION_HINT_RE.search(line) or (
            "test" in line.casefold()
            and has_term(line, ["passed", "failed", "skipped", "not run"])
        ):
            candidates.append(line)

    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return shorten_text("; ".join(unique[:3]), max_chars) if unique else ""


def format_scope(cwd: str, fallback: str) -> str:
    if cwd:
        name = Path(cwd).expanduser().name
        if name:
            return name
    return fallback


def contains_any_tag(text: str, tags: list[str]) -> bool:
    lowered = text.lower()
    return any(str(tag).lower() in lowered for tag in tags)


def path_matches(cwd: str, prefixes: list[str]) -> bool:
    if not prefixes or not cwd:
        return False
    cwd_path = Path(cwd).expanduser()
    for prefix in prefixes:
        try:
            cwd_path.relative_to(Path(str(prefix)).expanduser())
            return True
        except ValueError:
            continue
    return False


def run_git(cwd: str, args: list[str], timeout_seconds: float) -> str:
    if not cwd:
        return ""
    try:
        completed = subprocess.run(
            ["git", "-C", cwd, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def parse_git_branch(status_header: str) -> str:
    if not status_header.startswith("## "):
        return ""
    branch = status_header[3:].strip()
    branch = branch.split("...", 1)[0].strip()
    branch = branch.split(" [", 1)[0].strip()
    if branch.startswith("HEAD "):
        return "detached"
    return branch


def git_context(cwd: str, timeout_seconds: float) -> dict[str, str]:
    status = run_git(cwd, ["status", "--short", "--branch"], timeout_seconds)
    if not status:
        return {}
    lines = status.splitlines()
    root = run_git(cwd, ["rev-parse", "--show-toplevel"], timeout_seconds)
    sha = run_git(cwd, ["rev-parse", "--short", "HEAD"], timeout_seconds)
    changed_count = max(0, len(lines) - 1)
    repo = Path(root).name if root else format_scope(cwd, "")
    return {
        "repo": repo,
        "branch": parse_git_branch(lines[0]) if lines else "",
        "git_sha": sha.splitlines()[0] if sha else "",
        "git_root": root,
        "git_changed_count": str(changed_count),
        "git_dirty": "clean" if changed_count == 0 else f"{changed_count} changed",
    }


def always_tag_present(config: dict[str, Any], latest_input: str) -> bool:
    return contains_any_tag(latest_input, safe_string_list(config.get("always_tags")))


def choose_policy(config: dict[str, Any], latest_input: str) -> str:
    policy = os.environ.get("CODEX_NOTIFY", str(config.get("default_policy", "always")))
    policy = policy.strip().lower()
    if contains_any_tag(latest_input, safe_string_list(config.get("skip_tags"))):
        return "none"
    if always_tag_present(config, latest_input):
        return "always"
    if policy not in {"always", "long", "none"}:
        return "always"
    return policy


def frontmost_app_name(timeout_seconds: float) -> str | None:
    script = (
        'tell application "System Events" to get name of '
        "first application process whose frontmost is true"
    )
    try:
        completed = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_event("focus_check_failed", error=str(exc))
        return None
    if completed.returncode != 0:
        log_event("focus_check_failed", error=completed.stderr.strip())
        return None
    name = completed.stdout.strip()
    return name or None


def should_skip_for_focus(
    config: dict[str, Any],
    latest_input: str,
    *,
    sample: bool = False,
) -> tuple[bool, str, str | None]:
    policy = str(config.get("focus_policy", "always")).strip().lower()
    if policy in {"always", "off", "disabled", "none"}:
        return False, "focus_policy_always", None
    if policy not in {"when_codex_unfocused", "when_app_unfocused"}:
        return False, "focus_policy_invalid", None
    if sample or always_tag_present(config, latest_input):
        return False, "focus_bypassed", None

    timeout = safe_float(config.get("focus_check_timeout_seconds"), 1.0, minimum=0.1)
    frontmost = frontmost_app_name(timeout)
    if not frontmost:
        unknown_policy = str(config.get("focus_unknown_policy", "send")).strip().lower()
        if unknown_policy == "skip":
            return True, "focus_unknown", None
        return False, "focus_unknown", None

    configured_names = safe_string_list(config.get("focus_app_names")) or ["Codex"]
    configured = {name.casefold() for name in configured_names}
    is_focused = frontmost.casefold() in configured
    return is_focused, "app_focused" if is_focused else "app_unfocused", frontmost


def state_db_path(config: dict[str, Any]) -> Path:
    configured = str(config.get("state_db_path") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_STATE_DB_PATH


def history_db_path(config: dict[str, Any]) -> Path:
    configured = str(config.get("history_db_path") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_HISTORY_DB_PATH


def acquire_turn_lock(path: Path, turn_id: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_turns (
                turn_id TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO processed_turns (turn_id, created_at) VALUES (?, ?)",
            (turn_id, int(time.time())),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def release_turn_lock(path: Path, turn_id: str) -> None:
    try:
        conn = sqlite3.connect(path)
        try:
            conn.execute("DELETE FROM processed_turns WHERE turn_id = ?", (turn_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log_event("turn_lock_release_failed", error=str(exc), turn_id=turn_id)


def prune_notification_history(conn: sqlite3.Connection, retention_days: int) -> None:
    if retention_days <= 0:
        return
    cutoff = int(time.time()) - (retention_days * 86400)
    conn.execute("DELETE FROM notification_history WHERE created_at < ?", (cutoff,))


def ensure_notification_history_schema(conn: sqlite3.Connection) -> None:
    columns_sql = ",\n                    ".join(
        f"{name} {definition}" for name, definition in NOTIFICATION_HISTORY_COLUMNS
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS notification_history (
            {columns_sql}
        )
        """
    )
    existing = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(notification_history)").fetchall()
    }
    for name, definition in NOTIFICATION_HISTORY_COLUMNS:
        if name == "id" or name in existing:
            continue
        conn.execute(f"ALTER TABLE notification_history ADD COLUMN {name} {definition}")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_history_created_at
        ON notification_history (created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_history_turn_id
        ON notification_history (turn_id)
        """
    )


def record_notification_history(
    config: dict[str, Any],
    event: dict[str, Any],
    *,
    title: str,
    message: str,
    request_id: str | None,
    url: str,
    url_title: str,
    policy: str,
    reason: str,
    status: str,
    sample: bool,
    focus_reason: str,
    frontmost_app: str | None,
    duration_seconds: float | None,
    git_info: dict[str, str] | None = None,
) -> int | None:
    if not is_truthy(config.get("history_enabled", True)):
        return None

    path = history_db_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    cwd = str(event.get("cwd") or "")
    resolved_git_info = (
        git_info
        if git_info is not None
        else git_context(
            cwd,
            safe_float(config.get("git_check_timeout_seconds"), 1.0, minimum=0.1),
        )
    )
    store_messages = is_truthy(config.get("history_store_messages", True))
    payload = {
        "schema_version": 1,
        "permission_mode": str(event.get("permission_mode") or ""),
        "template": {
            "title": str(config.get("title_template") or ""),
            "message": str(config.get("message_template") or ""),
        },
    }

    try:
        conn = sqlite3.connect(path)
        try:
            ensure_notification_history_schema(conn)
            placeholders = ", ".join(["?"] * len(NOTIFICATION_HISTORY_INSERT_COLUMNS))
            cursor = conn.execute(
                f"""
                INSERT INTO notification_history (
                    {", ".join(NOTIFICATION_HISTORY_INSERT_COLUMNS)}
                ) VALUES ({placeholders})
                """,
                (
                    int(time.time()),
                    str(event.get("turn_id") or ""),
                    str(event.get("session_id") or ""),
                    request_id or "",
                    1 if sample else 0,
                    1 if request_id == "dry-run" else 0,
                    policy,
                    reason,
                    status,
                    duration_seconds,
                    title,
                    message if store_messages else "",
                    url,
                    url_title,
                    len(title),
                    len(message),
                    1 if is_truthy(config.get("pushover_html", True)) else 0,
                    cwd,
                    resolved_git_info.get("repo", ""),
                    resolved_git_info.get("branch", ""),
                    resolved_git_info.get("git_sha", ""),
                    resolved_git_info.get("git_dirty", ""),
                    str(event.get("model") or ""),
                    str(event.get("permission_mode") or ""),
                    str(event.get("thread_source") or ""),
                    str(event.get("subagent_name") or ""),
                    str(event.get("originator") or ""),
                    focus_reason,
                    frontmost_app or "",
                    json.dumps(payload, sort_keys=True),
                ),
            )
            prune_notification_history(
                conn,
                safe_int(config.get("history_retention_days"), 90, minimum=0),
            )
            conn.commit()
            row_id = cursor.lastrowid
            return int(row_id) if row_id is not None else None
        finally:
            conn.close()
    except Exception as exc:
        log_event("history_write_failed", error=str(exc), turn_id=event.get("turn_id"))
        return None


def join_parts(parts: list[str]) -> str:
    return " | ".join(part for part in parts if part)


def styled_value(label: str, value: str, *, html_enabled: bool, value_is_html: bool = False) -> str:
    if not value:
        return ""
    if not html_enabled:
        return f"{label}: {value}"
    rendered_value = value if value_is_html else html_escape_text(value)
    return f"<b>{html_escape_text(label)}</b>: {rendered_value}"


def styled_status(status: str, *, html_enabled: bool) -> str:
    if not html_enabled:
        return status
    color = "#c62828" if status == "Needs attention" else "#2e7d32"
    return f'<font color="{color}">{html_escape_text(status)}</font>'


def build_headline(status: str, scope: str, duration: str, branch: str, config: dict[str, Any]) -> str:
    parts = [scope]
    if branch:
        parts.append(branch)
    if is_truthy(config.get("include_duration", True)):
        parts.append(duration)
    return f"{status}: {join_parts(parts)}"


def render_detail_line(
    label: str,
    value: str,
    *,
    html_enabled: bool,
    value_is_html: bool = False,
) -> str:
    return styled_value(
        label,
        value,
        html_enabled=html_enabled,
        value_is_html=value_is_html,
    )


def render_detail_lines(
    fields: list[dict[str, Any]],
    *,
    html_enabled: bool,
) -> str:
    lines: list[str] = []
    for field in fields:
        line = render_detail_line(
            str(field["label"]),
            str(field.get("value") or ""),
            html_enabled=html_enabled,
            value_is_html=bool(field.get("value_is_html")),
        )
        if line:
            lines.append(line)
    return "\n".join(lines)


def fit_detail_fields(
    fields: list[dict[str, Any]],
    *,
    html_enabled: bool,
    max_chars: int | None,
) -> list[dict[str, Any]]:
    fitted = [dict(field) for field in fields]
    if not max_chars:
        return fitted

    def rendered() -> str:
        return render_detail_lines(fitted, html_enabled=html_enabled)

    if len(rendered()) <= max_chars:
        return fitted

    preferred_caps = {
        "Result": 360,
        "Prompt": 160,
        "Verified": 160,
    }
    for field in fitted:
        label = str(field["label"])
        cap = preferred_caps.get(label)
        if cap and field.get("value"):
            field["value"] = shorten_text(str(field["value"]), cap)
    if len(rendered()) <= max_chars:
        return fitted

    for label in ("Runtime",):
        for field in fitted:
            if field["label"] == label:
                field["value"] = ""
        if len(rendered()) <= max_chars:
            return fitted

    minimum_caps = {
        "Result": 120,
        "Prompt": 80,
        "Verified": 80,
    }
    for label in ("Result", "Prompt", "Verified"):
        for field in fitted:
            if field["label"] != label or not field.get("value"):
                continue
            overage = len(rendered()) - max_chars
            if overage <= 0:
                return fitted
            current = str(field["value"])
            target = max(minimum_caps[label], len(current) - overage - 6)
            field["value"] = shorten_text(current, target)
        if len(rendered()) <= max_chars:
            return fitted

    for label in ("Prompt", "Verified", "Runtime", "Repo"):
        for field in fitted:
            if field["label"] == label:
                field["value"] = ""
        if len(rendered()) <= max_chars:
            return fitted

    return fitted


def truncate_complete_lines(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return "." * max(0, max_chars)
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        candidate_lines = [*kept, line]
        candidate = "\n".join(candidate_lines)
        if len(candidate) <= max_chars:
            kept.append(line)
            continue
        break
    if kept:
        return "\n".join(kept)
    return shorten_text(text, max_chars)


def balanced_pushover_html(text: str, max_chars: int) -> str:
    cleaned = text
    dangling_tag_start = cleaned.rfind("<")
    if dangling_tag_start > cleaned.rfind(">"):
        cleaned = cleaned[:dangling_tag_start].rstrip()

    def open_tags(value: str) -> list[str]:
        stack: list[str] = []
        for match in PUSHOVER_HTML_TAG_RE.finditer(value):
            closing, raw_tag = match.groups()
            tag = raw_tag.lower()
            if tag == "br":
                continue
            if closing:
                for index in range(len(stack) - 1, -1, -1):
                    if stack[index] == tag:
                        del stack[index:]
                        break
            else:
                stack.append(tag)
        return stack

    stack = open_tags(cleaned)
    while stack:
        closing = f"</{stack[-1]}>"
        if len(cleaned) + len(closing) <= max_chars:
            cleaned += closing
        else:
            opener = list(
                re.finditer(rf"<\s*{re.escape(stack[-1])}\b[^>]*>", cleaned, re.IGNORECASE)
            )
            if not opener:
                break
            match = opener[-1]
            cleaned = (cleaned[: match.start()] + cleaned[match.end() :]).rstrip()
        stack = open_tags(cleaned)
    return cleaned


def shorten_message_text(text: str, max_chars: int, *, html_enabled: bool) -> str:
    shortened = shorten_text(text, max_chars)
    if html_enabled:
        return balanced_pushover_html(shortened, max_chars)
    return shortened


def build_details(
    *,
    status: str,
    task: str,
    outcome: str,
    verification: str,
    duration: str,
    repo_parts: list[str],
    runtime_parts: list[str],
    pr_label: str,
    html_enabled: bool,
    include_duration: bool,
    max_chars: int | None = None,
) -> str:
    status_parts = [styled_status(status, html_enabled=html_enabled)]
    if include_duration:
        status_parts.append(duration)
    fields = [
        {
            "label": "Status",
            "value": join_parts(status_parts),
            "value_is_html": html_enabled,
        },
        {"label": "Prompt", "value": task},
        {"label": "Result", "value": outcome},
        {"label": "Verified", "value": verification},
        {"label": "PR", "value": pr_label},
        {"label": "Repo", "value": join_parts(repo_parts)},
        {"label": "Runtime", "value": join_parts(runtime_parts)},
    ]
    fitted = fit_detail_fields(fields, html_enabled=html_enabled, max_chars=max_chars)
    return truncate_complete_lines(
        render_detail_lines(fitted, html_enabled=html_enabled),
        max_chars,
    ) if max_chars else render_detail_lines(fitted, html_enabled=html_enabled)


def template_values_for_html(values: dict[str, Any], html_fields: dict[str, str]) -> dict[str, Any]:
    escaped = {key: html_escape_text(str(value)) for key, value in values.items()}
    escaped.update(html_fields)
    return escaped


def build_notification(
    config: dict[str, Any],
    event: dict[str, Any],
    duration_seconds: float | None,
    *,
    sample: bool = False,
    status: str | None = None,
    git_info: dict[str, str] | None = None,
) -> tuple[str, str]:
    cwd = str(event.get("cwd") or "")
    resolved_git_info = (
        git_info
        if git_info is not None
        else (
            git_context(
                cwd,
                safe_float(config.get("git_check_timeout_seconds"), 1.0, minimum=0.1),
            )
            if is_truthy(config.get("include_git", True))
            else {}
        )
    )
    scope = resolved_git_info.get("repo") or format_scope(
        cwd,
        str(config.get("fallback_scope_label", "workspace")),
    )
    host = socket.gethostname().split(".")[0]
    if sample:
        title = "Sample: Codex plugin"
        body = (
            "This sample push came from the installed Codex plugin Stop hook.\n"
            f"{scope} | {host}"
        )
        return title, body

    status = status or classify_status(str(event.get("last_assistant_message") or ""), config)
    assistant_message = str(event.get("last_assistant_message") or "")
    outcome = extract_outcome(
        assistant_message,
        bounded_int(config.get("max_outcome_chars"), 560, minimum=20, maximum=900),
    )
    task = (
        extract_task(
            str(event.get("latest_input") or ""),
            config,
            bounded_int(config.get("max_task_chars"), 220, minimum=20, maximum=500),
        )
        if is_truthy(config.get("include_task", True))
        else ""
    )
    verification = (
        extract_verification_summary(
            assistant_message,
            bounded_int(
                config.get("max_verification_chars"),
                180,
                minimum=20,
                maximum=400,
            ),
        )
        if is_truthy(config.get("include_verification", True))
        else ""
    )
    duration = format_duration(duration_seconds)
    model = str(event.get("model") or "")
    link = notification_link_from_message(assistant_message)
    pr_label = link[1] if link else ""
    meta_parts: list[str] = []
    if is_truthy(config.get("include_duration", True)):
        meta_parts.append(duration)
    if is_truthy(config.get("include_host", True)):
        meta_parts.append(host)
    if model and is_truthy(config.get("include_model", True)):
        meta_parts.append(model)
    repo_parts = [
        scope,
        resolved_git_info.get("branch", ""),
        resolved_git_info.get("git_sha", ""),
        resolved_git_info.get("git_dirty", ""),
    ]
    runtime_parts: list[str] = []
    if model and is_truthy(config.get("include_model", True)):
        runtime_parts.append(model)
    if is_truthy(config.get("include_host", True)):
        runtime_parts.append(host)
    html_enabled = is_truthy(config.get("pushover_html", True))
    message_limit = bounded_int(
        config.get("max_message_chars"),
        1024,
        minimum=80,
        maximum=PUSHOVER_MESSAGE_LIMIT,
    )
    plain_details = build_details(
        status=status,
        task=task,
        outcome=outcome,
        verification=verification,
        duration=duration,
        repo_parts=repo_parts,
        runtime_parts=runtime_parts,
        pr_label=pr_label,
        html_enabled=False,
        include_duration=is_truthy(config.get("include_duration", True)),
        max_chars=message_limit,
    )
    html_details = build_details(
        status=status,
        task=task,
        outcome=outcome,
        verification=verification,
        duration=duration,
        repo_parts=repo_parts,
        runtime_parts=runtime_parts,
        pr_label=pr_label,
        html_enabled=True,
        include_duration=is_truthy(config.get("include_duration", True)),
        max_chars=message_limit,
    )
    headline = build_headline(
        status,
        scope,
        duration,
        resolved_git_info.get("branch", ""),
        config,
    )
    values = {
        "status": status,
        "status_styled": status,
        "scope": scope,
        "headline": headline,
        "duration": duration,
        "duration_seconds": "" if duration_seconds is None else str(round(duration_seconds, 1)),
        "host": host,
        "model": model,
        "meta": " | ".join(meta_parts),
        "outcome": outcome,
        "task": task,
        "prompt": task,
        "verification": verification,
        "details": plain_details,
        "repo": resolved_git_info.get("repo", scope),
        "branch": resolved_git_info.get("branch", ""),
        "git_sha": resolved_git_info.get("git_sha", ""),
        "git_dirty": resolved_git_info.get("git_dirty", ""),
        "git_changed_count": resolved_git_info.get("git_changed_count", ""),
        "git_root": resolved_git_info.get("git_root", ""),
        "pr": pr_label,
        "cwd": cwd,
        "session_id": str(event.get("session_id") or ""),
        "turn_id": str(event.get("turn_id") or ""),
        "permission_mode": str(event.get("permission_mode") or ""),
        "thread_source": str(event.get("thread_source") or ""),
        "subagent_name": str(event.get("subagent_name") or ""),
        "originator": str(event.get("originator") or ""),
    }
    body_values = (
        template_values_for_html(
            values,
            {
                "details": html_details,
                "status_styled": styled_status(status, html_enabled=True),
            },
        )
        if html_enabled
        else values
    )
    title = truncate_text(
        render_template(
            config.get("title_template"),
            values,
            str(DEFAULT_CONFIG["title_template"]),
        ),
        bounded_int(
            config.get("max_title_chars"),
            160,
            minimum=20,
            maximum=PUSHOVER_TITLE_LIMIT,
        ),
    )
    body = shorten_message_text(
        render_template(
            config.get("message_template"),
            body_values,
            str(DEFAULT_CONFIG["message_template"]),
        ),
        message_limit,
        html_enabled=html_enabled,
    )
    return title, body


def publish_pushover(
    config: dict[str, Any],
    title: str,
    message: str,
    *,
    url: str = "",
    url_title: str = "",
) -> str | None:
    if is_truthy_env("CODEX_NOTIFY_DRY_RUN"):
        log_event("dry_run_publish", title=title, message=message, url=url, url_title=url_title)
        return "dry-run"

    user_key = str(config.get("PUSHOVER_USER_KEY", "")).strip()
    app_token = str(config.get("PUSHOVER_APP_TOKEN", "")).strip()
    if not user_key or not app_token:
        raise RuntimeError("Missing Pushover credentials")

    priority = config.get("PUSHOVER_PRIORITY", config.get("pushover_priority", 0))
    sound = str(config.get("PUSHOVER_SOUND", config.get("pushover_sound") or "") or "").strip()
    device = str(config.get("PUSHOVER_DEVICE", config.get("pushover_device") or "") or "").strip()

    data = {
        "token": app_token,
        "user": user_key,
        "title": truncate_text(title, PUSHOVER_TITLE_LIMIT),
        "message": shorten_message_text(
            message,
            PUSHOVER_MESSAGE_LIMIT,
            html_enabled=is_truthy(config.get("pushover_html", True)),
        ),
        "priority": str(priority),
    }
    if is_truthy(config.get("pushover_html", True)):
        data["html"] = "1"
    if sound:
        data["sound"] = sound
    if device:
        data["device"] = device
    if url:
        data["url"] = clean_url(url)[:PUSHOVER_URL_LIMIT]
    if url_title:
        data["url_title"] = truncate_text(url_title, PUSHOVER_URL_TITLE_LIMIT)

    attempts = safe_int(config.get("retry_attempts"), 2, minimum=1)
    backoffs = safe_float_list(config.get("retry_backoff_seconds"), [1.0])
    timeout = safe_float(config.get("http_timeout_seconds"), 5.0, minimum=0.5)
    encoded = parse.urlencode(data).encode("utf-8")

    for attempt in range(1, attempts + 1):
        try:
            req = request.Request(
                "https://api.pushover.net/1/messages.json",
                data=encoded,
                method="POST",
            )
            with request.urlopen(req, timeout=timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            if response_payload.get("status") != 1:
                raise RuntimeError(f"Pushover rejected request: {response_payload!r}")
            request_id = response_payload.get("request")
            return request_id if isinstance(request_id, str) else None
        except Exception as exc:
            log_event("publish_attempt_failed", attempt=attempt, error=str(exc))
            if attempt >= attempts:
                raise
            delay = backoffs[min(attempt - 1, len(backoffs) - 1)] if backoffs else 1
            time.sleep(max(0.0, float(delay)))
    return None


def should_send(
    config: dict[str, Any],
    policy: str,
    duration_seconds: float | None,
    status: str,
) -> tuple[bool, str]:
    if policy == "none":
        return False, "policy_none"
    if policy == "always":
        return True, "policy_always"
    if status == "Needs attention" and is_truthy(config.get("notify_on_failure", False)):
        return True, "attention_status"
    threshold = safe_float(config.get("long_run_seconds"), 300.0, minimum=0.0)
    if duration_seconds is not None and duration_seconds >= threshold:
        return True, "duration_threshold_met"
    return False, "duration_below_threshold"


def process_payload(payload: dict[str, Any]) -> None:
    config = load_config()
    if not is_truthy(config.get("enabled", True)):
        log_event("disabled")
        return

    event = normalize_event(payload)
    if not event:
        log_event("ignored_payload", keys=sorted(payload.keys()))
        return

    if event.get("stop_hook_active"):
        log_event("skip_stop_hook_active", turn_id=event.get("turn_id"))
        return

    turn_id = event.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id:
        log_event("missing_turn_id", source=event.get("source"))
        return

    sample = os.environ.get("CODEX_PUSHOVER_SAMPLE") == "1"
    apply_session_metadata(event, session_meta_from_transcript(event.get("transcript_path")))
    if is_subagent_event(event) and not sample and not is_truthy(config.get("notify_subagents", False)):
        log_event(
            "skipped",
            turn_id=turn_id,
            reason="subagent",
            thread_source=event.get("thread_source"),
            subagent_name=event.get("subagent_name"),
            originator=event.get("originator"),
        )
        return

    transcript = transcript_items(event.get("transcript_path"))
    if not event.get("latest_input"):
        event["latest_input"] = latest_user_input_from_transcript(transcript)
    latest_input = str(event.get("latest_input") or "")
    duration_seconds = extract_turn_duration(transcript, turn_id)
    status = classify_status(str(event.get("last_assistant_message") or ""), config)

    cwd = str(event.get("cwd") or "")
    include_cwds = safe_string_list(config.get("include_cwds"))
    exclude_cwds = safe_string_list(config.get("exclude_cwds"))
    if include_cwds and not path_matches(cwd, include_cwds):
        log_event("skipped", turn_id=turn_id, reason="cwd_not_included", cwd=cwd)
        return
    if path_matches(cwd, exclude_cwds):
        log_event("skipped", turn_id=turn_id, reason="cwd_excluded", cwd=cwd)
        return

    policy = "always" if sample else choose_policy(config, latest_input)
    send, reason = should_send(config, policy, duration_seconds, status)
    if not send:
        log_event(
            "skipped",
            turn_id=turn_id,
            reason=reason,
            policy=policy,
            duration_seconds=duration_seconds,
        )
        return

    skip_focus, focus_reason, frontmost = should_skip_for_focus(
        config,
        latest_input,
        sample=sample,
    )
    if skip_focus:
        log_event(
            "skipped",
            turn_id=turn_id,
            reason=focus_reason,
            policy=policy,
            duration_seconds=duration_seconds,
            frontmost_app=frontmost,
        )
        return

    git_info = (
        git_context(
            cwd,
            safe_float(config.get("git_check_timeout_seconds"), 1.0, minimum=0.1),
        )
        if is_truthy(config.get("include_git", True))
        else {}
    )
    title, message = build_notification(
        config,
        event,
        duration_seconds,
        sample=sample,
        status=status,
        git_info=git_info,
    )
    dedupe_enabled = is_truthy(config.get("dedupe_enabled", True))
    lock_path = state_db_path(config)
    lock_id = f"sample:{turn_id}" if sample else turn_id
    lock_acquired = False
    if dedupe_enabled and not acquire_turn_lock(lock_path, lock_id):
        log_event("duplicate_turn", turn_id=turn_id, sample=sample)
        return
    lock_acquired = dedupe_enabled
    link = None if sample else notification_link_from_message(
        str(event.get("last_assistant_message") or "")
    )
    try:
        request_id = publish_pushover(
            config,
            title,
            message,
            url=link[0] if link else "",
            url_title=link[1] if link else "",
        )
    except Exception:
        if lock_acquired:
            release_turn_lock(lock_path, lock_id)
        raise
    history_id = record_notification_history(
        config,
        event,
        title=title,
        message=message,
        request_id=request_id,
        url=link[0] if link else "",
        url_title=link[1] if link else "",
        policy=policy,
        reason=reason,
        status=status,
        sample=sample,
        focus_reason=focus_reason,
        frontmost_app=frontmost,
        duration_seconds=duration_seconds,
        git_info=git_info,
    )
    log_event(
        "sent",
        turn_id=turn_id,
        session_id=event.get("session_id"),
        sample=sample,
        request_id=request_id,
        history_id=history_id,
        title=title,
        notification_url=link[0] if link else "",
        notification_url_title=link[1] if link else "",
        policy=policy,
        reason=reason,
        status=status,
        dedupe_enabled=dedupe_enabled,
        thread_source=event.get("thread_source"),
        subagent_name=event.get("subagent_name"),
        originator=event.get("originator"),
        focus_reason=focus_reason,
        frontmost_app=frontmost,
        duration_seconds=duration_seconds,
        env_path=config.get("loaded_pushover_env_path"),
    )


def main() -> int:
    try:
        process_payload(parse_hook_payload())
    except Exception:
        log_event("error", error=traceback.format_exc())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
