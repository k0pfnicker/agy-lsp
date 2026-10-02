"""LSP protocol definitions, constants, and framing utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Optional


class DiagnosticSeverity(IntEnum):
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4

    def to_string(self) -> str:
        return {
            DiagnosticSeverity.ERROR: "Error",
            DiagnosticSeverity.WARNING: "Warning",
            DiagnosticSeverity.INFORMATION: "Information",
            DiagnosticSeverity.HINT: "Hint",
        }.get(self, "Unknown")


SYMBOL_KIND_NAMES: dict[int, str] = {
    1: "File",
    2: "Module",
    3: "Namespace",
    4: "Package",
    5: "Class",
    6: "Method",
    7: "Property",
    8: "Field",
    9: "Constructor",
    10: "Enum",
    11: "Interface",
    12: "Function",
    13: "Variable",
    14: "Constant",
    15: "String",
    16: "Number",
    17: "Boolean",
    18: "Array",
    19: "Object",
    20: "Key",
    21: "Null",
    22: "EnumMember",
    23: "Struct",
    24: "Event",
    25: "Operator",
    26: "TypeParameter",
}


def format_symbol_kind(kind: int) -> str:
    """Convert LSP SymbolKind integer into human-readable string."""
    return SYMBOL_KIND_NAMES.get(kind, f"Symbol({kind})")


def encode_lsp_message(payload: dict[str, Any]) -> bytes:
    """Encode a Python dictionary as a standard LSP JSON-RPC message with Content-Length."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


@dataclass
class JsonRpcResponse:
    id: Optional[int | str]
    result: Any = None
    error: Optional[dict[str, Any]] = None

    @property
    def is_error(self) -> bool:
        return self.error is not None
