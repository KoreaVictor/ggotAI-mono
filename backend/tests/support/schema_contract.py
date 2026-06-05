"""docs/database_schema.sql 을 단일 기준 계약으로 파싱한다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", re.S | re.I
)
_CONSTRAINT_PREFIXES = ("FOREIGN KEY", "PRIMARY KEY", "UNIQUE", "CHECK", "CONSTRAINT")
_IDENT_RE = re.compile(r"^\w+$")


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    nullable: bool
    has_default: bool


def parse_schema(path: Path | str) -> dict[str, dict[str, ColumnSpec]]:
    text = Path(path).read_text(encoding="utf-8")
    tables: dict[str, dict[str, ColumnSpec]] = {}
    for m in _TABLE_RE.finditer(text):
        table = m.group(1)
        body = m.group(2)
        cols: dict[str, ColumnSpec] = {}
        for raw in body.splitlines():
            line = raw.split("--", 1)[0].strip().rstrip(",").strip()
            if not line:
                continue
            upper = line.upper()
            if upper.startswith(_CONSTRAINT_PREFIXES):
                continue
            name = line.split()[0]
            if not _IDENT_RE.match(name):
                continue
            nullable = "NOT NULL" not in upper
            has_default = "DEFAULT" in upper or "SERIAL" in upper
            cols[name] = ColumnSpec(name=name, nullable=nullable, has_default=has_default)
        tables[table] = cols
    return tables


def required_columns(
    tables: dict[str, dict[str, ColumnSpec]], table: str
) -> set[str]:
    """INSERT 시 반드시 채워야 하는 컬럼(NOT NULL 이면서 DEFAULT 없음)."""
    return {
        c.name for c in tables[table].values()
        if not c.nullable and not c.has_default
    }


def all_columns(tables: dict[str, dict[str, ColumnSpec]]) -> set[str]:
    """모든 테이블 컬럼의 합집합(약식 참조 검사용)."""
    return {col for cols in tables.values() for col in cols}
