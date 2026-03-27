"""Database models and operations for the display server.

SQLite database for storing and retrieving visualization requests,
with FTS5 full-text search support.
"""

import json
import logging
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Generator
from typing import Literal
from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

from holoviz_mcp_server.config import get_config
from holoviz_mcp_server.utils import find_extensions
from holoviz_mcp_server.utils import find_requirements
from holoviz_mcp_server.utils import validate_code
from holoviz_mcp_server.utils import validate_extension_availability
from holoviz_mcp_server.validation import ast_check
from holoviz_mcp_server.validation import check_packages
from holoviz_mcp_server.validation import ruff_check
from holoviz_mcp_server.validation import ruff_format

logger = logging.getLogger(__name__)


class Snippet(BaseModel):
    """Model for a code snippet stored in the database."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    app: str = Field(..., description="Python code to execute")
    name: str = Field(default="", description="User-provided name")
    description: str = Field(default="", description="Short description of the app")
    readme: str = Field(default="", description="Longer documentation")
    method: Literal["jupyter", "panel", "pyodide"] = Field(..., description="Execution method")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["pending", "success", "error"] = Field(default="pending")
    error_message: Optional[str] = Field(default=None, description="Error details if status='error'")
    execution_time: Optional[float] = Field(default=None, description="Execution time in seconds")
    requirements: list[str] = Field(default_factory=list, description="Inferred required packages")
    extensions: list[str] = Field(default_factory=list, description="Inferred Panel extensions")
    user: str = Field(default="guest", description="User who created the snippet")
    tags: list[str] = Field(default_factory=list, description="List of tags")
    slug: str = Field(default="", description="URL-friendly slug for persistent links")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if v == "":
            return v
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v


class SnippetDatabase:
    """SQLite database manager for code snippets."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    def _initialize_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS snippets (
                    id TEXT PRIMARY KEY,
                    app TEXT NOT NULL,
                    name TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    readme TEXT DEFAULT '',
                    method TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    execution_time REAL,
                    requirements TEXT,
                    extensions TEXT,
                    user TEXT DEFAULT 'guest',
                    tags TEXT,
                    slug TEXT DEFAULT ''
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON snippets(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON snippets(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_method ON snippets(method)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_slug ON snippets(slug)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user ON snippets(user)")
            cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS snippets_fts
                USING fts5(name, description, readme, app, content=snippets)
                """
            )
            conn.commit()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def create_snippet(self, snippet: Snippet) -> Snippet:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO snippets
                (id, app, name, description, readme, method, created_at, updated_at, status,
                 error_message, execution_time, requirements, extensions, user, tags, slug)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snippet.id,
                    snippet.app,
                    snippet.name,
                    snippet.description,
                    snippet.readme,
                    snippet.method,
                    snippet.created_at.isoformat(),
                    snippet.updated_at.isoformat(),
                    snippet.status,
                    snippet.error_message,
                    snippet.execution_time,
                    json.dumps(snippet.requirements),
                    json.dumps(snippet.extensions),
                    snippet.user,
                    json.dumps(snippet.tags),
                    snippet.slug,
                ),
            )
            cursor.execute(
                """
                INSERT INTO snippets_fts(rowid, name, description, readme, app)
                VALUES ((SELECT rowid FROM snippets WHERE id = ?), ?, ?, ?, ?)
                """,
                (snippet.id, snippet.name, snippet.description, snippet.readme, snippet.app),
            )
            conn.commit()
        return snippet

    def get_snippet(self, snippet_id: str) -> Optional[Snippet]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM snippets WHERE id = ?", (snippet_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_snippet(dict(row))
            return None

    def get_snippet_by_slug(self, slug: str) -> Optional[Snippet]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM snippets WHERE slug = ? ORDER BY created_at DESC LIMIT 1",
                (slug,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_snippet(dict(row))
            return None

    def update_snippet(
        self,
        snippet_id: str,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        execution_time: Optional[float] = None,
        requirements: Optional[list[str]] = None,
        extensions: Optional[list[str]] = None,
    ) -> bool:
        updates = []
        params: list[str] = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if execution_time is not None:
            updates.append("execution_time = ?")
            params.append(str(execution_time))
        if requirements is not None:
            updates.append("requirements = ?")
            params.append(json.dumps(requirements))
        if extensions is not None:
            updates.append("extensions = ?")
            params.append(json.dumps(extensions))

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(snippet_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE snippets SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_visualization(
        self,
        app: str,
        name: str = "",
        description: str = "",
        readme: str = "",
        method: Literal["jupyter", "panel", "pyodide"] = "jupyter",
    ) -> Snippet:
        """Create a visualization request — core business logic with 5-layer validation."""
        if not app:
            raise ValueError("App code is required")

        supported_methods = {"jupyter", "panel", "pyodide"}
        if method not in supported_methods:
            supported_text = ", ".join(sorted(supported_methods))
            raise ValueError(f"Unsupported method '{method}'. Supported: {supported_text}")

        # Layer 1 — Syntax
        if err := ast_check(app):
            raise SyntaxError(err)

        # Layer 2 — Security
        ruff_check(app)

        # Layer 3 — Package availability
        if err := check_packages(app):
            raise ValueError(err)

        # Layer 4 — Panel extension availability
        if method == "panel":
            validate_extension_availability(app)

        # Format before storage
        app = ruff_format(app)

        # Layer 5 — Runtime execution
        validation_result = validate_code(app)

        requirements = find_requirements(app)
        extensions = find_extensions(app) if method == "jupyter" else []

        snippet_obj = Snippet(
            app=app,
            name=name,
            description=description,
            readme=readme,
            method=method,
            requirements=requirements,
            extensions=extensions,
            status="success" if not validation_result else "error",
            error_message=validation_result if validation_result else None,
        )

        return self.create_snippet(snippet_obj)

    @staticmethod
    def _row_to_snippet(row: dict) -> Snippet:
        return Snippet(
            id=row["id"],
            app=row["app"],
            name=row["name"] or "",
            description=row["description"] or "",
            readme=row.get("readme", ""),
            method=row["method"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            status=row["status"],
            error_message=row["error_message"],
            execution_time=row["execution_time"],
            requirements=json.loads(row["requirements"]) if row["requirements"] else [],
            extensions=json.loads(row["extensions"]) if row["extensions"] else [],
            user=row.get("user", "guest"),
            tags=json.loads(row["tags"]) if row.get("tags") else [],
            slug=row.get("slug", ""),
        )


_db_instance: Optional[SnippetDatabase] = None


def get_db(db_path: Optional[Path] = None) -> SnippetDatabase:
    """Get or create the SnippetDatabase instance."""
    global _db_instance

    if _db_instance is None:
        if db_path is None:
            env_path = os.getenv("HOLOVIZ_MCP_SERVER_DB_PATH", "")
            if env_path:
                db_path = Path(env_path)
            else:
                db_path = get_config().db_path

        logger.info(f"Initializing database at: {db_path}")
        _db_instance = SnippetDatabase(db_path)

    return _db_instance


def reset_db() -> None:
    """Reset the database instance (for testing)."""
    global _db_instance
    _db_instance = None
