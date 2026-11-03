"""Tiny additive schema migrations.

`Base.metadata.create_all` creates missing tables but never alters existing ones, so
databases created by an earlier version would lack newer columns. Each entry below adds
a column if it is missing. Only backwards-compatible additions belong here; a bigger
schema change would justify adopting Alembic.
"""

import logging

from sqlalchemy import Engine, inspect, text

logger = logging.getLogger(__name__)

# table -> {column: SQL type/default clause}; works on SQLite and PostgreSQL.
ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "questions": {"source_ref": "VARCHAR(300) NOT NULL DEFAULT ''"},
    "attempt_answers": {"source_ref": "VARCHAR(300) NOT NULL DEFAULT ''"},
}


def upgrade(engine: Engine) -> list[str]:
    """Add any missing columns. Returns the list of columns that were added."""
    added: list[str] = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in present:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
                    added.append(f"{table}.{name}")
    if added:
        logger.info("Database upgraded: added %s", ", ".join(added))
    return added
