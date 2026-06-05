"""T1 프론트엔드 best-effort 컬럼 스캔: 명백한 불일치만 실패시킨다."""

import re
from pathlib import Path

import pytest

from tests.support.schema_contract import all_columns, parse_schema

SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "database_schema.sql"
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

_EQ_RE = re.compile(r"\.eq\(\s*['\"](\w+)['\"]")
_SELECT_RE = re.compile(r"\.select\(\s*['\"]([^'\"]+)['\"]")


def _scan(text: str) -> set[str]:
    cols: set[str] = set(_EQ_RE.findall(text))
    for sel in _SELECT_RE.findall(text):
        for tok in sel.split(","):
            tok = tok.strip()
            if not tok or tok == "*" or "(" in tok:
                continue
            cols.add(tok)
    return cols


@pytest.mark.skipif(not FRONTEND_SRC.exists(), reason="frontend/src 없음")
def test_frontend_column_references_exist_in_schema():
    known = all_columns(parse_schema(SCHEMA))
    unknown: set[str] = set()
    for path in list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.tsx")):
        unknown |= _scan(path.read_text(encoding="utf-8")) - known
    assert not unknown, f"프론트에서 계약에 없는 컬럼 참조: {unknown}"
