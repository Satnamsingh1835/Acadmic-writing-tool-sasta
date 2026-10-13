from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 4
_ALLOWED_SORTS = {
    "relevance": "updated_at DESC",
    "newest": "year DESC, title COLLATE NOCASE ASC",
    "oldest": "year ASC, title COLLATE NOCASE ASC",
    "title": "title COLLATE NOCASE ASC",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any, default: Any) -> str:
    try:
        return json.dumps(default if value is None else value, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(default, ensure_ascii=False)


def _decode(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def normalize_doi(value: str | None) -> str:
    doi = (value or "").strip()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    return doi.rstrip(" .").lower()


def _normalise_title(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold(), flags=re.UNICODE).strip()


def default_data_dir() -> Path:
    override = os.getenv("SCHOLARFLOW_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "ScholarFlow"


class ResearchLibrary:
    """Small local SQLite catalogue with optional FTS5 indexes.

    All persistent data lives outside the source checkout by default. Network
    discovery is implemented separately and runs only on an explicit request.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else default_data_dir() / "research-library.sqlite3"
        self.db_path = self.db_path.expanduser().resolve()
        self.data_dir = self.db_path.parent
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.fts5_available = False
        self.schema_version = SCHEMA_VERSION
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS works (
                    id TEXT PRIMARY KEY,
                    zotero_key TEXT,
                    doi TEXT,
                    title TEXT NOT NULL,
                    authors_json TEXT NOT NULL DEFAULT '[]',
                    year INTEGER,
                    item_type TEXT NOT NULL DEFAULT 'article',
                    publication TEXT NOT NULL DEFAULT '',
                    abstract TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'manual',
                    source_url TEXT NOT NULL DEFAULT '',
                    licence TEXT NOT NULL DEFAULT '',
                    access_status TEXT NOT NULL DEFAULT 'metadata_only',
                    metadata_verified INTEGER NOT NULL DEFAULT 0,
                    research_method TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    subjects_json TEXT NOT NULL DEFAULT '[]',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS works_doi_unique
                    ON works(doi) WHERE doi IS NOT NULL AND doi <> '';
                CREATE INDEX IF NOT EXISTS works_year_idx ON works(year);
                CREATE INDEX IF NOT EXISTS works_type_idx ON works(item_type);
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS work_collections (
                    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
                    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                    PRIMARY KEY (work_id, collection_id)
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    work_id TEXT REFERENCES works(id) ON DELETE SET NULL,
                    filename TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    licence TEXT NOT NULL DEFAULT '',
                    access_status TEXT NOT NULL DEFAULT 'local_full_text',
                    sha256 TEXT NOT NULL UNIQUE,
                    parser_status TEXT NOT NULL,
                    indexed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS passages (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    work_id TEXT REFERENCES works(id) ON DELETE SET NULL,
                    page_number INTEGER,
                    passage_index INTEGER NOT NULL,
                    text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS passages_work_idx ON passages(work_id);
                CREATE TABLE IF NOT EXISTS literature_matrix (
                    id TEXT PRIMARY KEY,
                    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
                    research_question TEXT NOT NULL,
                    claim TEXT NOT NULL DEFAULT '',
                    method TEXT NOT NULL DEFAULT '',
                    supporting_passage TEXT NOT NULL DEFAULT '',
                    page_number INTEGER,
                    evidence_level TEXT NOT NULL DEFAULT 'candidate',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS discovery_cache (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                """
            )
            # FTS5 is bundled with most Windows/Python distributions, but it is
            # optional; LIKE-based search remains available if it is missing.
            try:
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5("
                    "work_id UNINDEXED, title, authors, abstract, subjects)"
                )
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5("
                    "passage_id UNINDEXED, work_title, text)"
                )
                self.fts5_available = True
                connection.execute("DELETE FROM works_fts")
                connection.execute(
                    "INSERT INTO works_fts(work_id, title, authors, abstract, subjects) "
                    "SELECT id, title, authors_json, abstract, subjects_json FROM works"
                )
                connection.execute("DELETE FROM passages_fts")
                connection.execute(
                    """
                    INSERT INTO passages_fts(passage_id, work_title, text)
                    SELECT p.id, COALESCE(w.title, d.filename), p.text
                    FROM passages p
                    JOIN documents d ON d.id = p.document_id
                    LEFT JOIN works w ON w.id = p.work_id
                    """
                )
            except sqlite3.OperationalError:
                self.fts5_available = False
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for field, default in (
            ("authors_json", []),
            ("tags_json", []),
            ("subjects_json", []),
            ("raw_json", {}),
        ):
            data[field.removesuffix("_json")] = _decode(data.pop(field), default)
        data["metadata_verified"] = bool(data["metadata_verified"])
        return data

    def count_works(self) -> int:
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM works").fetchone()[0])

    def count_documents(self) -> int:
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])

    def add_work(self, record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise ValueError("A work must be a JSON object.")
        title = str(record.get("title") or "").strip()
        if not title:
            raise ValueError("A title is required.")
        doi = normalize_doi(str(record.get("doi") or ""))
        authors = record.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        if not isinstance(authors, list):
            authors = []
        authors = [str(a.get("name") or a.get("literal") or a.get("family") or "")
                   if isinstance(a, dict) else str(a) for a in authors]
        authors = [a.strip() for a in authors if a.strip()]
        year = record.get("year")
        try:
            year = int(year) if year not in (None, "") else None
        except (ValueError, TypeError):
            year = None
        if year is not None and not (1000 <= year <= 2200):
            year = None
        record_id = str(record.get("id") or uuid.uuid4().hex)
        now = _utc_now()
        cleaned = {
            "zotero_key": str(record.get("zotero_key") or ""),
            "doi": doi or None,
            "title": title,
            "authors_json": _json(authors, []),
            "year": year,
            "item_type": str(record.get("item_type") or "article")[:100],
            "publication": str(record.get("publication") or "")[:1000],
            "abstract": str(record.get("abstract") or "")[:20000],
            "url": str(record.get("url") or "")[:2000],
            "source": str(record.get("source") or "manual")[:100],
            "source_url": str(record.get("source_url") or "")[:2000],
            "licence": str(record.get("licence") or "")[:500],
            "access_status": str(record.get("access_status") or "metadata_only")[:100],
            "metadata_verified": int(bool(record.get("metadata_verified", False))),
            "research_method": str(record.get("research_method") or "")[:1000],
            "tags_json": _json(record.get("tags") or [], []),
            "subjects_json": _json(record.get("subjects") or [], []),
            "raw_json": _json(record.get("raw") or {}, {}),
        }
        with closing(self._connect()) as connection:
            with connection:
                duplicate = None
                if cleaned["doi"]:
                    duplicate = connection.execute(
                        "SELECT id FROM works WHERE doi=?", (cleaned["doi"],)
                    ).fetchone()
                if duplicate is None:
                    candidates = connection.execute(
                        "SELECT id, authors_json FROM works WHERE lower(title)=lower(?) AND year IS ?",
                        (title, year),
                    ).fetchall()
                    first_author = authors[0].casefold() if authors else ""
                    for candidate in candidates:
                        saved_authors = _decode(candidate["authors_json"], [])
                        saved_first = str(saved_authors[0]).casefold() if saved_authors else ""
                        if saved_first == first_author:
                            duplicate = candidate
                            break
                if duplicate:
                    return {"id": duplicate["id"], "created": False, "duplicate": True}
                try:
                    connection.execute(
                        """
                        INSERT INTO works (
                            id, zotero_key, doi, title, authors_json, year, item_type,
                            publication, abstract, url, source, source_url, licence,
                            access_status, metadata_verified, research_method,
                            tags_json, subjects_json, raw_json, created_at, updated_at
                        ) VALUES (
                            :id, :zotero_key, :doi, :title, :authors_json, :year, :item_type,
                            :publication, :abstract, :url, :source, :source_url, :licence,
                            :access_status, :metadata_verified, :research_method,
                            :tags_json, :subjects_json, :raw_json, :created_at, :updated_at
                        )
                        """,
                        {**cleaned, "id": record_id, "created_at": now, "updated_at": now},
                    )
                except sqlite3.IntegrityError as exc:
                    if cleaned["doi"]:
                        duplicate = connection.execute(
                            "SELECT id FROM works WHERE doi=?", (cleaned["doi"],)
                        ).fetchone()
                        if duplicate:
                            return {"id": duplicate["id"], "created": False, "duplicate": True}
                    raise ValueError("The record could not be saved because of a database constraint.") from exc
                self._refresh_work_fts(connection, record_id)
        return {"id": record_id, "created": True, "duplicate": False}

    def _refresh_work_fts(self, connection: sqlite3.Connection, work_id: str) -> None:
        if not self.fts5_available:
            return
        row = connection.execute(
            "SELECT id,title,authors_json,abstract,subjects_json FROM works WHERE id=?",
            (work_id,),
        ).fetchone()
        if row is None:
            return
        connection.execute("DELETE FROM works_fts WHERE work_id=?", (work_id,))
        connection.execute(
            "INSERT INTO works_fts(work_id,title,authors,abstract,subjects) VALUES(?,?,?,?,?)",
            (row["id"], row["title"], row["authors_json"], row["abstract"], row["subjects_json"]),
        )

    def update_work(self, work_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "title", "authors", "year", "item_type", "publication", "abstract",
            "url", "source_url", "licence", "access_status", "research_method",
            "tags", "subjects", "doi",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError("Unsupported fields: " + ", ".join(sorted(unknown)))
        with closing(self._connect()) as connection:
            current = connection.execute("SELECT * FROM works WHERE id=?", (work_id,)).fetchone()
            if current is None:
                return None
            merged = self._record_from_row(current)
        merged.update(fields)
        merged["id"] = work_id
        # Keep source and original record provenance unless explicitly represented by an import.
        result = self.add_work(merged) if False else None
        title = str(merged.get("title") or "").strip()
        if not title:
            raise ValueError("A title is required.")
        authors = merged.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        authors_json = _json([str(x) for x in authors], [])
        year = merged.get("year")
        try:
            year = int(year) if year not in (None, "") else None
        except (ValueError, TypeError):
            year = None
        now = _utc_now()
        sql_values = {
            "title": title,
            "authors_json": authors_json,
            "year": year,
            "item_type": str(merged.get("item_type") or "article"),
            "publication": str(merged.get("publication") or ""),
            "abstract": str(merged.get("abstract") or ""),
            "url": str(merged.get("url") or ""),
            "source_url": str(merged.get("source_url") or ""),
            "licence": str(merged.get("licence") or ""),
            "access_status": str(merged.get("access_status") or "metadata_only"),
            "research_method": str(merged.get("research_method") or ""),
            "tags_json": _json(merged.get("tags") or [], []),
            "subjects_json": _json(merged.get("subjects") or [], []),
            "doi": normalize_doi(str(merged.get("doi") or "")) or None,
        }
        with closing(self._connect()) as connection:
            with connection:
                conflict = connection.execute(
                    "SELECT id FROM works WHERE doi=? AND id<>?",
                    (sql_values["doi"], work_id),
                ).fetchone() if sql_values["doi"] else None
                if conflict:
                    raise ValueError("Another record already uses this DOI.")
                connection.execute(
                    """
                    UPDATE works SET title=:title, authors_json=:authors_json, year=:year,
                    item_type=:item_type, publication=:publication, abstract=:abstract,
                    url=:url, source_url=:source_url, licence=:licence,
                    access_status=:access_status, research_method=:research_method,
                    tags_json=:tags_json, subjects_json=:subjects_json, doi=:doi,
                    updated_at=:updated_at WHERE id=:id
                    """,
                    {**sql_values, "updated_at": now, "id": work_id},
                )
                self._refresh_work_fts(connection, work_id)
        return self.get_work(work_id)

    def get_work(self, work_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM works WHERE id=?", (work_id,)).fetchone()
        return self._record_from_row(row) if row else None

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = re.findall(r"[\w-]+", query, flags=re.UNICODE)[:12]
        return " AND ".join('"' + term.replace('"', "") + '"*' for term in terms)

    def search_works(
        self, q: str = "", author: str = "", year: int | None = None,
        item_type: str = "", access_status: str = "", subject: str = "",
        sort: str = "relevance", limit: int = 50,
    ) -> list[dict[str, Any]]:
        sort_sql = _ALLOWED_SORTS.get(sort, _ALLOWED_SORTS["relevance"])
        filters = []
        parameters: list[Any] = []
        if author:
            filters.append("authors_json LIKE ?")
            parameters.append("%" + author[:200] + "%")
        if year is not None:
            filters.append("year=?")
            parameters.append(year)
        if item_type:
            filters.append("item_type=?")
            parameters.append(item_type[:100])
        if access_status:
            filters.append("access_status=?")
            parameters.append(access_status[:100])
        if subject:
            filters.append("(subjects_json LIKE ? OR tags_json LIKE ?)")
            parameters.extend(["%" + subject[:200] + "%", "%" + subject[:200] + "%"])
        query = self._fts_query(q.strip()) if q.strip() else ""
        with closing(self._connect()) as connection:
            rows = []
            if query and self.fts5_available:
                try:
                    sql = """
                    SELECT w.* FROM works w
                    JOIN works_fts f ON f.work_id=w.id
                    WHERE works_fts MATCH ?
                    """
                    values: list[Any] = [query]
                    if filters:
                        sql += " AND " + " AND ".join(filters)
                        values.extend(parameters)
                    sql += " ORDER BY " + sort_sql + " LIMIT ?"
                    values.append(max(1, min(limit, 100)))
                    rows = connection.execute(sql, values).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows and (not self.fts5_available or query):
                likes = []
                values = []
                if query:
                    tokens = re.findall(r"[\w-]+", q, flags=re.UNICODE)[:12]
                    for token in tokens:
                        likes.append("(title LIKE ? OR authors_json LIKE ? OR abstract LIKE ? OR subjects_json LIKE ?)")
                        values.extend(["%" + token + "%"] * 4)
                where = []
                if likes:
                    where.append("(" + " AND ".join(likes) + ")")
                where.extend(filters)
                sql = "SELECT * FROM works"
                if where:
                    sql += " WHERE " + " AND ".join(where)
                sql += " ORDER BY " + sort_sql + " LIMIT ?"
                values.extend(parameters)
                values.append(max(1, min(limit, 100)))
                rows = connection.execute(sql, values).fetchall()
            elif not query:
                sql = "SELECT * FROM works"
                if filters:
                    sql += " WHERE " + " AND ".join(filters)
                sql += " ORDER BY " + sort_sql + " LIMIT ?"
                rows = connection.execute(
                    sql, [*parameters, max(1, min(limit, 100))]
                ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def add_document(
        self, *, work_id: str | None, filename: str, stored_path: str,
        source_url: str, licence: str, sha256: str, parser_status: str,
    ) -> dict[str, Any]:
        if work_id and self.get_work(work_id) is None:
            raise ValueError("The linked research record does not exist.")
        document_id = uuid.uuid4().hex
        with closing(self._connect()) as connection:
            with connection:
                existing = connection.execute(
                    "SELECT id FROM documents WHERE sha256=?", (sha256,)
                ).fetchone()
                if existing:
                    return {"id": existing["id"], "duplicate": True}
                connection.execute(
                    """
                    INSERT INTO documents(id,work_id,filename,stored_path,source_url,licence,
                    access_status,sha256,parser_status,indexed_at)
                    VALUES(?,?,?,?,?,?, 'local_full_text_indexed',?,?,?)
                    """,
                    (document_id, work_id, filename, stored_path, source_url, licence,
                     sha256, parser_status, _utc_now()),
                )
        return {"id": document_id, "duplicate": False}

    def add_passage(
        self, document_id: str, text: str, *, page_number: int | None = None,
        passage_index: int = 0, work_id: str | None = None,
    ) -> str:
        passage_id = uuid.uuid4().hex
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO passages(id,document_id,work_id,page_number,passage_index,text) "
                    "VALUES(?,?,?,?,?,?)",
                    (passage_id, document_id, work_id, page_number, passage_index, text),
                )
                if self.fts5_available:
                    title = connection.execute(
                        """
                        SELECT COALESCE(w.title,d.filename) AS title
                        FROM documents d LEFT JOIN works w ON w.id=?
                        WHERE d.id=?
                        """,
                        (work_id, document_id),
                    ).fetchone()
                    connection.execute(
                        "INSERT INTO passages_fts(passage_id,work_title,text) VALUES(?,?,?)",
                        (passage_id, title["title"] if title else "", text),
                    )
        return passage_id

    def search_passages(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        fts_query = self._fts_query(query)
        with closing(self._connect()) as connection:
            rows = []
            if self.fts5_available and fts_query:
                try:
                    rows = connection.execute(
                        """
                        SELECT p.id,p.page_number,p.text,d.filename,d.source_url,d.licence,
                               w.id AS work_id,w.title,w.authors_json,w.year,w.doi,
                               snippet(passages_fts,2,'[',']','…',18) AS excerpt
                        FROM passages_fts f
                        JOIN passages p ON p.id=f.passage_id
                        JOIN documents d ON d.id=p.document_id
                        LEFT JOIN works w ON w.id=p.work_id
                        WHERE passages_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_query, max(1, min(limit, 20))),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                rows = connection.execute(
                    """
                    SELECT p.id,p.page_number,p.text,d.filename,d.source_url,d.licence,
                           w.id AS work_id,w.title,w.authors_json,w.year,w.doi
                    FROM passages p
                    JOIN documents d ON d.id=p.document_id
                    LEFT JOIN works w ON w.id=p.work_id
                    WHERE p.text LIKE ?
                    LIMIT ?
                    """,
                    ("%" + query[:200] + "%", max(1, min(limit, 20))),
                ).fetchall()
        results = []
        for row in rows:
            data = dict(row)
            data["authors"] = _decode(data.pop("authors_json", None), [])
            data["supporting_passage"] = data.get("excerpt") or data["text"]
            data["evidence_status"] = "candidate_passage"
            data["warning"] = "Verify context and page location in the original source."
            results.append(data)
        return results

    def add_note(self, work_id: str, content: str) -> str:
        if self.get_work(work_id) is None:
            raise ValueError("The linked research record does not exist.")
        note_id = uuid.uuid4().hex
        now = _utc_now()
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO notes(id,work_id,content,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (note_id, work_id, content[:100000], now, now),
                )
        return note_id

    def add_matrix_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        if self.get_work(entry["work_id"]) is None:
            raise ValueError("The linked research record does not exist.")
        entry_id = uuid.uuid4().hex
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO literature_matrix(
                        id,work_id,research_question,claim,method,supporting_passage,
                        page_number,evidence_level,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (entry_id, entry["work_id"], entry["research_question"],
                     entry.get("claim", ""), entry.get("method", ""),
                     entry.get("supporting_passage", ""), entry.get("page_number"),
                     entry.get("evidence_level", "candidate"), _utc_now()),
                )
        return {"id": entry_id, **entry}

    def list_matrix_entries(self, limit: int = 500) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT m.*,w.title,w.authors_json,w.year,w.doi
                FROM literature_matrix m JOIN works w ON w.id=m.work_id
                ORDER BY m.created_at DESC LIMIT ?
                """,
                (max(1, min(limit, 1000)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["authors"] = _decode(item.pop("authors_json"), [])
            result.append(item)
        return result

    def get_cache(self, cache_key: str, *, allow_stale: bool = True) -> Any | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload_json FROM discovery_cache WHERE cache_key=?", (cache_key,)
            ).fetchone()
        if row is None:
            return None
        return _decode(row["payload_json"], None)

    def put_cache(self, cache_key: str, provider: str, payload: Any) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO discovery_cache(cache_key,provider,payload_json,cached_at)
                    VALUES(?,?,?,?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                    provider=excluded.provider,payload_json=excluded.payload_json,cached_at=excluded.cached_at
                    """,
                    (cache_key, provider, _json(payload, {}), _utc_now()),
                )

    def get_settings(self) -> dict[str, Any]:
        defaults = {"crossref_enabled": True, "openalex_enabled": True, "offline": False}
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT key,value_json FROM settings").fetchall()
        for row in rows:
            if row["key"] in defaults:
                defaults[row["key"]] = _decode(row["value_json"], defaults[row["key"]])
        return defaults

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        allowed = {"crossref_enabled", "openalex_enabled", "offline"}
        if set(values) - allowed:
            raise ValueError("Unsupported settings field.")
        with closing(self._connect()) as connection:
            with connection:
                for key, value in values.items():
                    connection.execute(
                        """
                        INSERT INTO settings(key,value_json) VALUES(?,?)
                        ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json
                        """,
                        (key, _json(bool(value), False)),
                    )
        return self.get_settings()

    def create_backup(self, destination: str | Path) -> Path:
        """Create a consistent SQLite backup using the SQLite backup API."""
        target = Path(destination).expanduser().resolve()
        if target == self.db_path:
            raise ValueError("Backup destination must differ from the active database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        try:
            with closing(self._connect()) as source, closing(
                sqlite3.connect(temporary, timeout=10)
            ) as backup:
                source.backup(backup)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target
