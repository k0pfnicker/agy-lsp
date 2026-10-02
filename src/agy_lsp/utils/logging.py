"""Safe logging utilities for agy-lsp.

Logs exclusively to stderr to avoid polluting stdout (which is reserved for MCP JSON-RPC).
Includes redaction for sensitive patterns (passwords, tokens, keys).
"""

from __future__ import annotations

import logging
import re
import sys

# Sensitive patterns to redact
_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[a-z0-9_\-\.~+/]+=*", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key[\s:=]+)[a-z0-9_\-\.~+/]+", re.IGNORECASE),
    re.compile(r"(?i)(password[\s:=]+)[^\s,;]+", re.IGNORECASE),
    re.compile(r"(?i)(token[\s:=]+)[a-z0-9_\-\.~+/]+", re.IGNORECASE),
    re.compile(r"(?i)(secret[\s:=]+)[a-z0-9_\-\.~+/]+", re.IGNORECASE),
]


def redact_sensitive(text: str) -> str:
    """Redact known sensitive tokens and credentials from log strings."""
    result = text
    for pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub(r"\1[REDACTED]", result)
    return result


class RedactingFormatter(logging.Formatter):
    """Logging formatter that strips credentials and keeps messages clean."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_sensitive(original)


def get_logger(name: str = "agy-lsp") -> logging.Logger:
    """Get or configure a logger instance writing solely to stderr."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = RedactingFormatter(
            fmt="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
