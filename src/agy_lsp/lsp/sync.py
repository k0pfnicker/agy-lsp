"""Document synchronization and cache management.

Tracks open documents, versions, and filesystem modification timestamps to keep
the Language Server state consistent with disk files without unnecessary re-reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agy_lsp.utils.logging import get_logger
from agy_lsp.utils.paths import detect_language_from_path, normalize_path, path_to_uri

logger = get_logger("agy-lsp.sync")


@dataclass
class DocumentState:
    file_path: str
    uri: str
    version: int
    content: str
    mtime: float
    language_id: str


class DocumentManager:
    """Manages document state and tracks didOpen/didChange synchronization with LSP."""

    def __init__(self) -> None:
        self._documents: dict[str, DocumentState] = {}

    def get_document(self, file_path: str) -> Optional[DocumentState]:
        norm = normalize_path(file_path)
        return self._documents.get(norm)

    def prepare_sync(
        self,
        file_path: str,
        explicit_content: Optional[str] = None,
        language_id: Optional[str] = None,
    ) -> tuple[str, DocumentState, Optional[dict]]:
        """Prepare synchronization for a file.

        Returns:
            (action, doc_state, lsp_notification_payload)
            action is one of: "noop", "open", "change"
        """
        norm = normalize_path(file_path)
        uri = path_to_uri(norm)
        p = Path(norm)

        if not p.is_file() and explicit_content is None:
            raise FileNotFoundError(f"File not found: {norm}")

        mtime = p.stat().st_mtime if p.exists() else 0.0

        if explicit_content is not None:
            content = explicit_content
        else:
            content = p.read_text(encoding="utf-8", errors="replace")

        lang = language_id or detect_language_from_path(norm) or "plaintext"

        existing = self._documents.get(norm)
        if existing is None:
            # First time opening this document
            new_doc = DocumentState(
                file_path=norm,
                uri=uri,
                version=1,
                content=content,
                mtime=mtime,
                language_id=lang,
            )
            self._documents[norm] = new_doc
            payload = {
                "textDocument": {
                    "uri": uri,
                    "languageId": lang,
                    "version": 1,
                    "text": content,
                }
            }
            return ("open", new_doc, payload)

        # Document was already opened. Check if content or disk mtime changed
        if existing.content != content:
            existing.version += 1
            existing.content = content
            existing.mtime = mtime
            payload = {
                "textDocument": {
                    "uri": uri,
                    "version": existing.version,
                },
                "contentChanges": [{"text": content}],
            }
            return ("change", existing, payload)

        return ("noop", existing, None)

    def close_document(self, file_path: str) -> Optional[dict]:
        """Mark document as closed and return didClose payload."""
        norm = normalize_path(file_path)
        existing = self._documents.pop(norm, None)
        if existing:
            return {
                "textDocument": {
                    "uri": existing.uri,
                }
            }
        return None

    def invalidate(self, file_path: str) -> None:
        """Invalidate cache entry for a file."""
        norm = normalize_path(file_path)
        self._documents.pop(norm, None)

    def clear(self) -> None:
        """Clear all cached document states."""
        self._documents.clear()
