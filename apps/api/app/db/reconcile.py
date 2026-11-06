"""Bring the local SQLite database up to the current models.

`init_models()` uses ``create_all``, which (correctly) never alters existing tables. For the local
development database we reconcile additive changes: new tables are created and missing columns are
added with their defaults. Destructive changes are *not* applied — production uses Alembic.

This runs only for SQLite (development / tests) and is safe to call on every boot.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.core.logging import get_logger

log = get_logger("factory.db.reconcile")


def _column_sql(column: Any, dialect: Any) -> str:
    compiled = column.type.compile(dialect=dialect)
    clause = f'"{column.name}" {compiled}'
    default = column.default
    if default is not None and getattr(default, "is_scalar", False):
        value = default.arg
        if isinstance(value, bool):
            clause += f" NOT NULL DEFAULT {1 if value else 0}"
        elif isinstance(value, (int, float)):
            clause += f" NOT NULL DEFAULT {value}"
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            clause += f" NOT NULL DEFAULT '{escaped}'"
    elif getattr(column, "nullable", True) is False and not column.primary_key:
        # Required but without a Python default: give existing rows a neutral value.
        if "JSON" in compiled.upper():
            clause += " NOT NULL DEFAULT '{}'"
    return clause


def reconcile(conn: Connection) -> list[str]:
    """Create missing tables and add missing columns. Returns a log of what changed."""
    from app import models  # noqa: F401  (register metadata)
    from app.db.base import Base

    metadata = Base.metadata
    inspector = inspect(conn)
    existing = set(inspector.get_table_names())
    changes: list[str] = []

    for table in metadata.sorted_tables:
        if table.name not in existing:
            table.create(bind=conn, checkfirst=True)
            changes.append(f"created {table.name}")
            continue
        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            sql = f'ALTER TABLE "{table.name}" ADD COLUMN {_column_sql(column, conn.dialect)}'
            conn.execute(text(sql))
            changes.append(f"added {table.name}.{column.name}")

    if changes:
        log.info("db.reconcile changes=%s", len(changes))
    return changes
