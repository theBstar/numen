"""Safety harness for chat responses - prevents leaking internal information."""

from __future__ import annotations

import re

# Patterns that should be redacted from LLM responses
_DANGEROUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    # System prompt leaks
    (re.compile(r"You are Numen AI[^.]*\.?", re.IGNORECASE), "[redacted]"),
    # Tool/function definition leaks (JSON-like)
    (re.compile(r'"tools"\s*:\s*\[.*?\]', re.DOTALL), "[redacted]"),
    (re.compile(r'"functions"\s*:\s*\[.*?\]', re.DOTALL), "[redacted]"),
    # Internal source paths
    (re.compile(r"src/\S+"), "[redacted]"),
    # Config/settings references
    (re.compile(r"settings\.\w+"), "[redacted]"),
    # Environment variable values with API keys
    (re.compile(r"\bsk-[a-zA-Z0-9_-]{3,}\b"), "[redacted]"),
    (re.compile(r"\bre_[a-zA-Z0-9_-]{3,}\b"), "[redacted]"),
    # ENV var assignments with keys
    (re.compile(r"[A-Z_]*API_KEY\s*=\s*\S+"), "[redacted]"),
    (re.compile(r"[A-Z_]*SECRET\s*=\s*\S+"), "[redacted]"),
]


def sanitize_response(text: str) -> str:
    """Strip dangerous patterns from LLM output before sending to client."""
    if not text:
        return text

    result = text
    for pattern, replacement in _DANGEROUS_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_tool_calls(tool_calls: list[dict] | None) -> list[dict]:
    """Remove input parameters from tool calls, keeping only tool names."""
    if not tool_calls:
        return []
    return [{"tool": tc.get("tool", "unknown")} for tc in tool_calls]
