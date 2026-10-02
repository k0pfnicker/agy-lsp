"""Tests for LSP protocol encoding, decoding, and enumeration mappings."""

import json

from agy_lsp.lsp.protocol import (
    DiagnosticSeverity,
    encode_lsp_message,
    format_symbol_kind,
)


def test_encode_lsp_message():
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    encoded = encode_lsp_message(payload)

    assert encoded.startswith(b"Content-Length: ")
    header_end = encoded.find(b"\r\n\r\n")
    assert header_end != -1

    body = encoded[header_end + 4 :]
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["id"] == 1
    assert parsed["method"] == "initialize"


def test_symbol_kind_mapping():
    assert format_symbol_kind(5) == "Class"
    assert format_symbol_kind(6) == "Method"
    assert format_symbol_kind(12) == "Function"
    assert format_symbol_kind(999) == "Symbol(999)"


def test_diagnostic_severity():
    assert DiagnosticSeverity(1).to_string() == "Error"
    assert DiagnosticSeverity(2).to_string() == "Warning"
    assert DiagnosticSeverity(3).to_string() == "Information"
    assert DiagnosticSeverity(4).to_string() == "Hint"
