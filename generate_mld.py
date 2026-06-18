#!/usr/bin/env python3
"""
generate_mld.py
Reads Scripts/DBSetUp.sql and writes:
  UML/MLD.md   — relational text notation  (<u>PK</u>, FK shown as RefTable.col)
  UML/MLD.puml — PlantUML ERD

Column ordering follows Merise convention:
  PKs  →  regular attrs  →  non-PK FK refs  →  PK-FK refs

For tables where every PK column is also a FK (junction / subtype):
  PK section shows FK display names (<u>RefTable.col</u>) rather than column names.

Usage:
    python generate_mld.py
    python generate_mld.py path/to/DBSetUp.sql [out.md] [out.puml]
"""

import re
import sys
from collections import Counter
from pathlib import Path


_SKIP_KEYWORDS = {
    'PRIMARY', 'FOREIGN', 'UNIQUE', 'KEY',
    'INDEX', 'CHECK', 'CONSTRAINT', 'ENGINE',
}


# ── SQL parsing ────────────────────────────────────────────────────────────────

def _strip_comments(sql: str) -> str:
    sql = re.sub(r'--[^\n]*', ' ', sql)
    sql = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.DOTALL)
    return sql


def parse_schema(sql: str) -> list[dict]:
    sql = _strip_comments(sql)
    tables = []
    for m in re.finditer(
        r'CREATE\s+TABLE\s+`?(\w+)`?\s*\((.+?)\)\s*ENGINE\s*=',
        sql, re.IGNORECASE | re.DOTALL,
    ):
        tables.append(_parse_table(m.group(1), m.group(2)))
    return tables


def _parse_table(name: str, body: str) -> dict:
    columns:      list[tuple[str, str, bool]] = []
    primary_keys: list[str]                   = []
    foreign_keys: list[tuple]                 = []
    inline_pks:   list[str]                   = []

    for raw in body.split('\n'):
        line = raw.strip().rstrip(',')
        if not line:
            continue

        m = re.match(r'PRIMARY\s+KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
        if m:
            primary_keys = [c.strip().strip('`') for c in m.group(1).split(',')]
            continue

        m = re.match(
            r'FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+`?(\w+)`?\s*\(([^)]+)\)',
            line, re.IGNORECASE,
        )
        if m:
            local  = [c.strip().strip('`') for c in m.group(1).split(',')]
            ref    = m.group(2)
            remote = [c.strip().strip('`') for c in m.group(3).split(',')]
            foreign_keys.append((local, ref, remote))
            continue

        m = re.match(r'`?(\w+)`?\s+(\w+(?:\([^)]*\))?)(.*)', line, re.IGNORECASE)
        if not m:
            continue
        col_name = m.group(1)
        if col_name.upper() in _SKIP_KEYWORDS:
            continue
        col_type = m.group(2)
        rest     = m.group(3).upper()
        if 'PRIMARY KEY' in rest:
            inline_pks.append(col_name)
        nullable = 'NOT NULL' not in rest and 'PRIMARY KEY' not in rest
        columns.append((col_name, col_type, nullable))

    return {
        'name':         name,
        'columns':      columns,
        'primary_keys': primary_keys or inline_pks,
        'foreign_keys': foreign_keys,
    }


# ── FK display map ─────────────────────────────────────────────────────────────

def _fk_display_map(foreign_keys: list) -> dict[str, str]:
    """Map each local FK col → 'RefTable.remote_col'.
    Adds [label] suffix when two local cols resolve to the same display string
    (e.g. LootTableReference: parent_id and child_id both → LootTable.id)."""
    raw: dict[str, str] = {}
    for (local, ref_table, remote) in foreign_keys:
        for lc, rc in zip(local, remote):
            raw[lc] = f'{ref_table}.{rc}'

    counts = Counter(raw.values())
    result = {}
    for lc, display in raw.items():
        if counts[display] > 1:
            label = re.sub(r'_(namespace|name|id)$', '', lc)
            result[lc] = f'{display}[{label}]'
        else:
            result[lc] = display
    return result


# ── MLD HTML ──────────────────────────────────────────────────────────────────

_HTML_HEADER = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>MLD</title>
  <style>
    body  { font-family: monospace; font-size: 1rem; padding: 1.5em; }
    u     { text-decoration-skip-ink: none; }
    p     { margin: 0.3em 0; }
    .fk   { color: #1a56cc; }
    .attr { color: #cc2200; }
  </style>
</head>
<body>
"""

_HTML_FOOTER = """\
</body>
</html>
"""


def _fk(text: str) -> str:
    return f'<span class="fk">{text}</span>'

def _attr(text: str) -> str:
    return f'<span class="attr">{text}</span>'


def _table_line(t: dict) -> str:
    pk_set  = set(t['primary_keys'])
    fk_map  = _fk_display_map(t['foreign_keys'])
    fk_cols = set(fk_map.keys())
    all_pk_fk = bool(pk_set) and (pk_set <= fk_cols)

    parts: list[str] = []

    if all_pk_fk:
        # PK = FK refs → blue underlined
        pk_items = [fk_map.get(col, col) for col in t['primary_keys']]
        parts.append(_fk(f'<u>{", ".join(pk_items)}</u>'))
        for col, _, _ in t['columns']:
            if col not in pk_set and col not in fk_cols:
                parts.append(col)
        for col, _, _ in t['columns']:
            if col not in pk_set and col in fk_map:
                parts.append(_fk(fk_map[col]))
    else:
        # PK = column names → red underlined
        parts.append(_attr(f'<u>{", ".join(t["primary_keys"])}</u>'))
        for col, _, _ in t['columns']:
            if col not in pk_set and col not in fk_cols:
                parts.append(col)
        for col, _, _ in t['columns']:
            if col in fk_map and col not in pk_set:
                parts.append(_fk(fk_map[col]))
        for col, _, _ in t['columns']:
            if col in fk_map and col in pk_set:
                parts.append(_fk(fk_map[col]))

    inner = f'{t["name"]}({", ".join(parts)})'
    return f'  <p>{inner}</p>'


def render_mld_html(tables: list[dict]) -> str:
    lines = [_HTML_HEADER.rstrip()]
    for t in tables:
        lines.append(_table_line(t))
    lines.append('')
    lines.append(_HTML_FOOTER.rstrip())
    return '\n'.join(lines) + '\n'


# ── PlantUML ERD ───────────────────────────────────────────────────────────────

def render_puml(tables: list[dict]) -> str:
    lines = [
        '@startuml MLD',
        'skinparam linetype ortho',
        'hide empty methods',
        '',
    ]

    for t in tables:
        pk_set  = set(t['primary_keys'])
        fk_set  = {col for (local, _, _) in t['foreign_keys'] for col in local}
        col_map = {c: (typ, nul) for c, typ, nul in t['columns']}

        lines.append(f'entity "{t["name"]}" {{')

        pk_cols = [c for c in t['primary_keys'] if c in col_map]
        non_pk  = [c for c, _, _ in t['columns'] if c not in pk_set]

        for col in pk_cols:
            typ = col_map[col][0]
            tag = '<<PK,FK>>' if col in fk_set else '<<PK>>'
            lines.append(f'  * {col} : {typ} {tag}')

        if non_pk:
            lines.append('  --')
            for col in non_pk:
                if col not in col_map:
                    continue
                typ, nullable = col_map[col]
                tag    = ' <<FK>>' if col in fk_set else ''
                prefix = '  o ' if nullable else '  * '
                lines.append(f'{prefix}{col} : {typ}{tag}')

        lines.append('}')
        lines.append('')

    lines.append("' ── Relationships ──────────────────────────────────────────")
    for t in tables:
        for (local_cols, ref_table, _) in t['foreign_keys']:
            label = ', '.join(local_cols)
            lines.append(f'"{ref_table}" ||--o{{ "{t["name"]}" : "{label}"')

    lines += ['', '@enduml']
    return '\n'.join(lines)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: generate_mld.py <schema.sql> [out.html] [out.puml]')
        sys.exit(1)

    sql_path  = Path(sys.argv[1])
    mld_path  = Path(sys.argv[2]) if len(sys.argv) > 2 else sql_path.parent / 'MLD.html'
    puml_path = Path(sys.argv[3]) if len(sys.argv) > 3 else sql_path.parent / 'MLD.puml'

    sql    = sql_path.read_text(encoding='utf-8')
    tables = parse_schema(sql)
    print(f'Parsed {len(tables)} tables from {sql_path.name}')

    mld_path.parent.mkdir(parents=True, exist_ok=True)
    mld_path.write_text(render_mld_html(tables), encoding='utf-8')
    print(f'Written -> {mld_path}')

    puml_path.write_text(render_puml(tables), encoding='utf-8')
    print(f'Written -> {puml_path}')


if __name__ == '__main__':
    main()
