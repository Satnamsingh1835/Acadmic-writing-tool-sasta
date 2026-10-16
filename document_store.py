"""Local, offline document store for the ScholarFlow writing workspace.

Documents are academic papers held as plain text with Markdown-style
structure. Everything lives in a user-local SQLite database next to the
research library, so nothing leaves the computer and the packaged desktop
application needs no extra service.

The store is deliberately conservative:

* every save bumps an integer ``revision`` so clients can detect conflicts
  instead of overwriting newer text,
* each save keeps a bounded history entry that can be restored,
* deleting a document archives it rather than destroying text.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_library.store import default_data_dir
from text_parser import normalize_text, words

SCHEMA_VERSION = 1
MAX_TITLE_CHARS = 300
MAX_TEXT_CHARS = 2_000_000
MAX_REVISIONS_PER_DOCUMENT = 50
DEFAULT_TITLE = "Untitled document"

REASON_MANUAL = "manual"
REASON_AUTOSAVE = "autosave"
REASON_RESTORE = "restore"
REASON_BEFORE_RESTORE = "before-restore"
_ALLOWED_REASONS = {REASON_MANUAL, REASON_AUTOSAVE, REASON_RESTORE, REASON_BEFORE_RESTORE}


class DocumentNotFoundError(LookupError):
    """The requested document does not exist (or is archived)."""


class DocumentConflictError(RuntimeError):
    """The stored revision is newer than the caller expected."""

    def __init__(self, current_revision: int, updated_at: str) -> None:
        super().__init__(
            "This document was changed elsewhere. Reload it before saving again."
        )
        self.current_revision = int(current_revision)
        self.updated_at = updated_at


class DocumentValidationError(ValueError):
    """Input that cannot be stored."""


def _utc_now() -> str:
    """Timestamp with microsecond precision.

    Second-granularity timestamps made "most recently updated first" unstable
    when several documents were written within the same second.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def count_words(text: str) -> int:
    """Count words with the shared academic tokenizer."""
    return len(words(text))


def derive_title(text: str) -> str:
    """Derive a readable title from the first heading or text line."""
    for line in normalize_text(text).splitlines():
        candidate = line.strip().lstrip("#").strip()
        if candidate:
            return candidate[:MAX_TITLE_CHARS]
    return DEFAULT_TITLE


class DocumentStore:
    """Small SQLite-backed store for long-form writing."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = (
            Path(db_path).expanduser()
            if db_path is not None
            else default_data_dir() / "writing-documents.sqlite3"
        )
        self.db_path = self.db_path.resolve()
        self.data_dir = self.db_path.parent
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.schema_version = SCHEMA_VERSION
        self.initialize()

    # -- infrastructure ---------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        text TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        revision INTEGER NOT NULL DEFAULT 1,
                        word_count INTEGER NOT NULL DEFAULT 0,
                        character_count INTEGER NOT NULL DEFAULT 0,
                        archived_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS documents_updated_idx
                        ON documents(updated_at DESC);
                    CREATE TABLE IF NOT EXISTS document_revisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        revision INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        text TEXT NOT NULL,
                        word_count INTEGER NOT NULL,
                        character_count INTEGER NOT NULL,
                        reason TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS document_revisions_document_idx
                        ON document_revisions(document_id, revision DESC);
                    """
                )
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    # -- validation helpers ----------------------------------------------
    @staticmethod
    def _clean_title(title: str | None, *, fallback_text: str = "") -> str:
        if title is None:
            return derive_title(fallback_text)
        if not isinstance(title, str):
            raise DocumentValidationError("A title must be text.")
        cleaned = " ".join(title.split())
        if not cleaned:
            return derive_title(fallback_text)
        if len(cleaned) > MAX_TITLE_CHARS:
            raise DocumentValidationError(
                f"A title may contain at most {MAX_TITLE_CHARS} characters."
            )
        return cleaned

    @staticmethod
    def _clean_text(text: str | None) -> str:
        if text is None:
            return ""
        if not isinstance(text, str):
            raise DocumentValidationError("Document text must be a string.")
        if len(text) > MAX_TEXT_CHARS:
            raise DocumentValidationError(
                f"A document may contain at most {MAX_TEXT_CHARS:,} characters."
            )
        return normalize_text(text)

    @classmethod
    def _summary_from_row(cls, row: sqlite3.Row, *, include_text: bool) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "revision": int(row["revision"]),
            "word_count": int(row["word_count"]),
            "character_count": int(row["character_count"]),
            "archived": row["archived_at"] is not None,
        }
        if include_text:
            data["text"] = row["text"]
        return data

    @staticmethod
    def _snapshot(connection: sqlite3.Connection, document_id: str, reason: str) -> None:
        row = connection.execute(
            "SELECT id,title,text,revision,word_count,character_count FROM documents WHERE id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            return
        connection.execute(
            """
            INSERT INTO document_revisions(
                document_id, revision, title, text, word_count, character_count, reason, created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                int(row["revision"]),
                row["title"],
                row["text"],
                int(row["word_count"]),
                int(row["character_count"]),
                reason,
                _utc_now(),
            ),
        )
        connection.execute(
            """
            DELETE FROM document_revisions
            WHERE document_id=? AND id NOT IN (
                SELECT id FROM document_revisions WHERE document_id=?
                ORDER BY revision DESC, id DESC LIMIT ?
            )
            """,
            (document_id, document_id, MAX_REVISIONS_PER_DOCUMENT),
        )

    # -- public API -------------------------------------------------------
    def create(self, title: str | None = None, text: str = "") -> dict[str, Any]:
        cleaned_text = self._clean_text(text)
        cleaned_title = self._clean_title(title, fallback_text=cleaned_text)
        document_id = uuid.uuid4().hex
        now = _utc_now()
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO documents(
                        id, title, text, created_at, updated_at, revision,
                        word_count, character_count, archived_at
                    ) VALUES(?,?,?,?,?,1,?,?,NULL)
                    """,
                    (
                        document_id,
                        cleaned_title,
                        cleaned_text,
                        now,
                        now,
                        count_words(cleaned_text),
                        len(cleaned_text),
                    ),
                )
        return self.get(document_id)

    def get(self, document_id: str, *, include_text: bool = True) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id=?", (document_id,)
            ).fetchone()
        if row is None:
            raise DocumentNotFoundError("That document does not exist.")
        return self._summary_from_row(row, include_text=include_text)

    def list(
        self, *, limit: int = 200, query: str = "", include_archived: bool = False
    ) -> list[dict[str, Any]]:
        clauses = []
        parameters: list[Any] = []
        if not include_archived:
            clauses.append("archived_at IS NULL")
        if query.strip():
            clauses.append("(title LIKE ? OR text LIKE ?)")
            like = "%" + query.strip()[:200] + "%"
            parameters.extend([like, like])
        sql = "SELECT * FROM documents"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC, rowid DESC LIMIT ?"
        parameters.append(max(1, min(int(limit), 500)))
        with closing(self._connect()) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [self._summary_from_row(row, include_text=False) for row in rows]

    def save(
        self,
        document_id: str,
        *,
        title: str | None = None,
        text: str | None = None,
        expected_revision: int | None = None,
        reason: str = REASON_MANUAL,
    ) -> dict[str, Any]:
        """Store a new revision of an existing document.

        ``expected_revision`` turns the write into a compare-and-set so two
        windows (or a stale browser tab) cannot overwrite newer text.
        """
        if reason not in _ALLOWED_REASONS:
            raise DocumentValidationError("Unsupported save reason.")
        cleaned_text = self._clean_text(text) if text is not None else None
        with closing(self._connect()) as connection:
            with connection:
                current = connection.execute(
                    "SELECT * FROM documents WHERE id=?", (document_id,)
                ).fetchone()
                if current is None or current["archived_at"] is not None:
                    raise DocumentNotFoundError("That document does not exist.")
                if expected_revision is not None and int(expected_revision) != int(
                    current["revision"]
                ):
                    raise DocumentConflictError(
                        int(current["revision"]), str(current["updated_at"])
                    )
                new_text = cleaned_text if cleaned_text is not None else current["text"]
                new_title = (
                    self._clean_title(title, fallback_text=new_text)
                    if title is not None
                    else current["title"]
                )
                unchanged = new_text == current["text"] and new_title == current["title"]
                if unchanged:
                    return self._summary_from_row(current, include_text=True)
                self._snapshot(connection, document_id, reason)
                connection.execute(
                    """
                    UPDATE documents
                    SET title=?, text=?, updated_at=?, revision=revision+1,
                        word_count=?, character_count=?
                    WHERE id=?
                    """,
                    (
                        new_title,
                        new_text,
                        _utc_now(),
                        count_words(new_text),
                        len(new_text),
                        document_id,
                    ),
                )
        return self.get(document_id)

    def delete(self, document_id: str) -> dict[str, Any]:
        """Archive a document. Text is retained and can be restored."""
        with closing(self._connect()) as connection:
            with connection:
                current = connection.execute(
                    "SELECT * FROM documents WHERE id=?", (document_id,)
                ).fetchone()
                if current is None:
                    raise DocumentNotFoundError("That document does not exist.")
                connection.execute(
                    "UPDATE documents SET archived_at=? WHERE id=?",
                    (_utc_now(), document_id),
                )
        return self.get(document_id)

    def restore_document(self, document_id: str) -> dict[str, Any]:
        """Bring an archived document back into the list."""
        with closing(self._connect()) as connection:
            with connection:
                current = connection.execute(
                    "SELECT * FROM documents WHERE id=?", (document_id,)
                ).fetchone()
                if current is None:
                    raise DocumentNotFoundError("That document does not exist.")
                connection.execute(
                    "UPDATE documents SET archived_at=NULL WHERE id=?", (document_id,)
                )
        return self.get(document_id)

    def revisions(self, document_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        self.get(document_id, include_text=False)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, revision, title, word_count, character_count, reason, created_at
                FROM document_revisions WHERE document_id=?
                ORDER BY revision DESC, id DESC LIMIT ?
                """,
                (document_id, max(1, min(int(limit), MAX_REVISIONS_PER_DOCUMENT))),
            ).fetchall()
        return [dict(row) for row in rows]

    def restore_revision(self, document_id: str, revision: int) -> dict[str, Any]:
        """Roll a document back to a stored revision."""
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    """
                    SELECT * FROM document_revisions
                    WHERE document_id=? AND revision=?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (document_id, int(revision)),
                ).fetchone()
                if row is None:
                    raise DocumentNotFoundError(
                        "That revision is no longer available in the history."
                    )
        # Snapshot the current text first so a rollback is itself reversible.
        # save() treats identical text as a no-op, so the snapshot is written here.
        with closing(self._connect()) as connection:
            with connection:
                self._snapshot(connection, document_id, REASON_BEFORE_RESTORE)
        return self.save(
            document_id,
            title=row["title"],
            text=row["text"],
            reason=REASON_RESTORE,
        )

    def count(self, *, include_archived: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM documents"
        if not include_archived:
            sql += " WHERE archived_at IS NULL"
        with closing(self._connect()) as connection:
            return int(connection.execute(sql).fetchone()[0])
