#!/usr/bin/env python3
"""
generate_mcd.py
Reads Scripts/DBSetUp.sql and writes UML/MCD_generated.puml
(Merise Conceptual Data Model, PlantUML class-diagram notation).

Classification rules:
  subtype        — entire PK covered by a single FK to another table
  pure junction  — all PK cols are FK cols, no own attributes  → simple M:M line
  assoc class    — all PK cols are FK cols, has own attributes  → (A,B)..Class notation
  entity         — everything else

Usage:
    python generate_mcd.py
    python generate_mcd.py path/to/DBSetUp.sql [out.puml]
"""

import re
import sys
from pathlib import Path


_TYPE_MAP = {
    'int': 'int', 'bigint': 'int', 'smallint': 'int', 'tinyint': 'int',
    'float': 'float', 'double': 'float', 'decimal': 'float', 'numeric': 'float',
    'varchar': 'string', 'char': 'string',
    'text': 'text', 'mediumtext': 'text', 'longtext': 'text', 'tinytext': 'text',
    'boolean': 'bool', 'bool': 'bool',
    'date': 'date', 'datetime': 'datetime', 'timestamp': 'datetime',
}

_SKIP_KEYWORDS = {
    'PRIMARY', 'FOREIGN', 'UNIQUE', 'KEY',
    'INDEX', 'CHECK', 'CONSTRAINT', 'ENGINE',
}

_SKINPARAM = """\
skinparam classAttributeIconSize 0
skinparam shadowing false
skinparam nodesep 80
skinparam ranksep 100
hide empty methods
hide circle

skinparam class {
  BackgroundColor #FEFECE
  BorderColor #555555
}
"""


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


# ── Classification ─────────────────────────────────────────────────────────────

def _mcd_type(raw_type: str) -> str:
    base = raw_type.lower().split('(')[0]
    return _TYPE_MAP.get(base, raw_type.lower())


def _detect_subtype(table: dict, table_map: dict) -> str | None:
    """Return parent name if entire PK is covered by one FK to a known table."""
    pk_set = set(table['primary_keys'])
    if not pk_set:
        return None
    for (local, ref_table, _) in table['foreign_keys']:
        if set(local) == pk_set and ref_table in table_map:
            return ref_table
    return None


def classify_tables(tables: list[dict]) -> tuple:
    table_map = {t['name']: t for t in tables}
    entities  = []
    subtypes  = {}   # name → parent_name
    junctions = []   # pure M:M, no own attrs
    assoc     = []   # M:M with own attrs

    for t in tables:
        pk_set  = set(t['primary_keys'])
        fk_cols = {col for (local, _, _) in t['foreign_keys'] for col in local}

        parent = _detect_subtype(t, table_map)
        if parent:
            subtypes[t['name']] = parent
            entities.append(t)
            continue

        if pk_set and pk_set <= fk_cols:
            non_pk_non_fk = [
                c for c, _, _ in t['columns']
                if c not in pk_set and c not in fk_cols
            ]
            (assoc if non_pk_non_fk else junctions).append(t)
        else:
            entities.append(t)

    return entities, subtypes, junctions, assoc


# ── Relationship helpers ───────────────────────────────────────────────────────

def _fk_card(table: dict, fk_local_cols: list[str]) -> str:
    """Return '"1"' or '"0..1"' for the referenced (one) side of a FK."""
    pk_set   = set(table['primary_keys'])
    col_null = {c: nullable for c, _, nullable in table['columns']}
    nullable = any(
        col_null.get(c, True)
        for c in fk_local_cols
        if c not in pk_set
    )
    return '"0..1"' if nullable else '"1"'


def _entity_fk_rels(table: dict, subtypes: dict) -> list[tuple[str, str, str]]:
    """Return (ref_table, card, fk_label) for non-subtype-covering FKs."""
    pk_set = set(table['primary_keys'])
    rels   = []
    for (local, ref_table, _) in table['foreign_keys']:
        if set(local) == pk_set:
            continue   # subtype-covering FK
        card = _fk_card(table, local)
        rels.append((ref_table, card))
    return rels


def _junction_endpoints(table: dict) -> list[str]:
    return [ref for (_, ref, _) in table['foreign_keys']]


# ── PlantUML rendering ─────────────────────────────────────────────────────────

def render_mcd(tables: list[dict]) -> str:
    entities, subtypes, junctions, assoc_tables = classify_tables(tables)

    lines: list[str] = ['@startuml MCD', '', _SKINPARAM]

    # ── Entity class blocks ───────────────────────────────────────────────────
    for t in entities:
        name    = t['name']
        pk_set  = set(t['primary_keys'])
        fk_cols = {col for (local, _, _) in t['foreign_keys'] for col in local}
        is_sub  = name in subtypes

        if is_sub:
            own_attrs = [
                (c, typ) for c, typ, _ in t['columns']
                if c not in pk_set and c not in fk_cols
            ]
        else:
            pk_attrs  = [(c, typ) for c, typ, _ in t['columns'] if c in pk_set]
            reg_attrs = [
                (c, typ) for c, typ, _ in t['columns']
                if c not in pk_set and c not in fk_cols
            ]
            own_attrs = pk_attrs + reg_attrs

        lines.append(f'class {name}')
        lines.append('{')
        for col, typ in own_attrs:
            lines.append(f'  {col} : {_mcd_type(typ)}')
        lines.append('}')
        lines.append('')

    # ── Association class blocks ──────────────────────────────────────────────
    for t in assoc_tables:
        pk_set  = set(t['primary_keys'])
        fk_cols = {col for (local, _, _) in t['foreign_keys'] for col in local}
        own_attrs = [
            (c, typ) for c, typ, _ in t['columns']
            if c not in pk_set and c not in fk_cols
        ]
        lines.append(f'class {t["name"]}')
        lines.append('{')
        for col, typ in own_attrs:
            lines.append(f'  {col} : {_mcd_type(typ)}')
        lines.append('}')
        lines.append('')

    # ── Inheritance ───────────────────────────────────────────────────────────
    lines.append("' ── Inheritance ─────────────────────────────────────────────")
    for sub, parent in sorted(subtypes.items()):
        lines.append(f'{sub} --|> {parent}')
    lines.append('')

    # ── Entity FK relationships ───────────────────────────────────────────────
    lines.append("' ── Entity relationships ────────────────────────────────────")
    for t in entities:
        if t['name'] in subtypes:
            continue
        for ref_table, card in _entity_fk_rels(t, subtypes):
            lines.append(f'{t["name"]} "*" -- {card} {ref_table}')
    lines.append('')

    # ── Pure M:M junctions ────────────────────────────────────────────────────
    lines.append("' ── M:M junctions ───────────────────────────────────────────")
    for t in junctions:
        eps = _junction_endpoints(t)
        if len(eps) == 2:
            lines.append(f'{eps[0]} "*" -- "*" {eps[1]}')
        else:
            for ep in eps:
                lines.append(f'{t["name"]} "*" -- "*" {ep}')
    lines.append('')

    # ── Association classes ───────────────────────────────────────────────────
    lines.append("' ── Association classes ─────────────────────────────────────")
    for t in assoc_tables:
        eps = _junction_endpoints(t)
        if len(eps) == 2:
            lines.append(f'({eps[0]}, {eps[1]}) .. {t["name"]}')
        else:
            for ep in eps:
                lines.append(f'{t["name"]} "*" -- "*" {ep}')
    lines.append('')

    lines.append('@enduml')
    return '\n'.join(lines)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: generate_mcd.py <schema.sql> [out.puml]')
        sys.exit(1)

    sql_path  = Path(sys.argv[1])
    puml_path = Path(sys.argv[2]) if len(sys.argv) > 2 else sql_path.parent / 'MCD.puml'

    sql    = sql_path.read_text(encoding='utf-8')
    tables = parse_schema(sql)
    print(f'Parsed {len(tables)} tables from {sql_path.name}')

    entities, subtypes, junctions, assoc = classify_tables(tables)
    print(
        f'  {len(entities)} entities  '
        f'({len(subtypes)} subtypes),  '
        f'{len(junctions)} pure junctions,  '
        f'{len(assoc)} association classes'
    )

    puml_path.parent.mkdir(parents=True, exist_ok=True)
    puml_path.write_text(render_mcd(tables), encoding='utf-8')
    print(f'Written -> {puml_path}')


if __name__ == '__main__':
    main()
