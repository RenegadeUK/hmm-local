#!/usr/bin/env python3
"""
Generate idempotent PostgreSQL schema-reconciliation SQL by diffing live DB schema
against current SQLAlchemy models.

Usage:
  python scripts/generate_schema_reconcile_sql.py
  python scripts/generate_schema_reconcile_sql.py --output /tmp/reconcile.sql

Notes:
- Designed for manual review before execution.
- Focuses on missing tables, columns, and indexes.
- Does not drop anything.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from importlib import import_module


def _qi(name: str) -> str:
    return f'"{name}"'


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _column_default(column: Any) -> str | None:
    if column.server_default is not None and getattr(column.server_default, "arg", None) is not None:
        arg = column.server_default.arg
        if hasattr(arg, "text"):
            return str(arg.text)
        return str(arg)

    if column.default is not None and getattr(column.default, "is_scalar", False):
        return _sql_literal(column.default.arg)

    return None


async def _build_diff_sql() -> str:
    db_module = import_module("core.database")
    Base = db_module.Base
    engine = db_module.engine

    lines: list[str] = []
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    lines.append("-- Auto-generated schema reconciliation SQL")
    lines.append(f"-- Generated at: {ts}")
    lines.append("-- Review before execution in production.")
    lines.append("")
    lines.append("BEGIN;")
    lines.append("")

    async with engine.begin() as conn:

        def _sync_diff(sync_conn) -> None:
            insp = inspect(sync_conn)
            existing_tables = set(insp.get_table_names())
            dialect = postgresql.dialect()

            for table in Base.metadata.sorted_tables:
                table_name = table.name

                # Missing table
                if table_name not in existing_tables:
                    create_stmt = str(CreateTable(table).compile(dialect=dialect)).strip().rstrip(";")
                    create_stmt = create_stmt.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
                    lines.append(f"-- Missing table: {table_name}")
                    lines.append(create_stmt + ";")

                    for idx in table.indexes:
                        if not idx.name:
                            continue
                        cols = ", ".join(_qi(col.name) for col in idx.columns)
                        unique = "UNIQUE " if idx.unique else ""
                        lines.append(
                            f"CREATE {unique}INDEX IF NOT EXISTS {_qi(idx.name)} "
                            f"ON {_qi(table_name)} ({cols});"
                        )

                    lines.append("")
                    continue

                # Existing table: diff columns
                existing_cols = {c["name"] for c in insp.get_columns(table_name)}
                missing_cols = [c for c in table.columns if c.name not in existing_cols]

                if missing_cols:
                    lines.append(f"-- Missing columns on table: {table_name}")

                for col in missing_cols:
                    col_type = col.type.compile(dialect=dialect)
                    default_sql = _column_default(col)

                    # For safety on existing rows: if NOT NULL and no default, add nullable first.
                    add_nullable_only = (not col.nullable) and (default_sql is None)

                    stmt = (
                        f"ALTER TABLE {_qi(table_name)} "
                        f"ADD COLUMN IF NOT EXISTS {_qi(col.name)} {col_type}"
                    )

                    if default_sql is not None:
                        stmt += f" DEFAULT {default_sql}"

                    if col.nullable or add_nullable_only:
                        stmt += " NULL"
                    else:
                        stmt += " NOT NULL"

                    lines.append(stmt + ";")

                    if add_nullable_only:
                        lines.append(
                            f"-- TODO: Backfill {_qi(table_name)}.{_qi(col.name)} then enforce NOT NULL manually."
                        )

                if missing_cols:
                    lines.append("")

                # Existing table: diff indexes
                existing_index_names = {idx["name"] for idx in insp.get_indexes(table_name)}
                missing_indexes = [idx for idx in table.indexes if idx.name and idx.name not in existing_index_names]

                if missing_indexes:
                    lines.append(f"-- Missing indexes on table: {table_name}")

                for idx in missing_indexes:
                    cols = ", ".join(_qi(col.name) for col in idx.columns)
                    unique = "UNIQUE " if idx.unique else ""
                    lines.append(
                        f"CREATE {unique}INDEX IF NOT EXISTS {_qi(idx.name)} "
                        f"ON {_qi(table_name)} ({cols});"
                    )

                if missing_indexes:
                    lines.append("")

        await conn.run_sync(_sync_diff)

    lines.append("COMMIT;")
    lines.append("")
    lines.append("-- Post-apply recommendation:")
    lines.append("-- 1) Restart container")
    lines.append("-- 2) Verify /api/operations/status")

    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate schema reconciliation SQL from live DB vs models")
    parser.add_argument("--output", type=Path, default=None, help="Output SQL file path")
    args = parser.parse_args()

    output = args.output
    if output is None:
        output = Path("/tmp") / f"hmm_schema_reconcile_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.sql"

    sql_text = await _build_diff_sql()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sql_text, encoding="utf-8")

    print(f"Generated: {output}")
    print("Review SQL before execution.")


if __name__ == "__main__":
    asyncio.run(main())
