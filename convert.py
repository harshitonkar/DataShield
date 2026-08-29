"""
convert.py — DataShield conversion layer.

Hack n Achieve
Data Quality • Detection • Repair

Handles everything downstream of parse():

    CSV  records  \
                    -->  SQLite (typed, versioned tables + manifest.json)
    JSON records   /

    CSV  -> JSON
    JSON -> CSV

    diff between two versioned SQLite tables of the same dataset

Standard library only: sqlite3, hashlib, json, datetime, re, os.

dataShield.py only needs the public functions below:
    to_records()
    export_to_sqlite()
    diff_tables()
    convert_csv_to_json()
    convert_json_to_csv()
"""

import hashlib
import json as std_json
import os
import re
import sqlite3
from datetime import datetime, timezone

from engine import CSVEngine, JSONEngine, get_engine


# ============================================================
# ERRORS
# ============================================================

class ConvertError(Exception):
    """Raised for any conversion-layer failure the CLI should report cleanly."""


# ============================================================
# RECORD NORMALIZATION
# ============================================================
#
# Both engines hand back very different shapes:
#   CSVEngine.parse()  -> (rows, report)          rows[0] is the header row
#   JSONEngine.parse()  -> (data, report)          data is arbitrary Python
#
# to_records() turns either into a common (fieldnames, records) pair:
#   fieldnames: list[str]           column order, first-seen
#   records:    list[dict[str, str or None]]
#
# Everything downstream (type inference, SQLite export, CSV/JSON writers)
# only ever deals with that common shape.

def _dedupe_headers(raw_headers):
    """Fill blank headers and disambiguate duplicates, same policy as repair()."""

    seen = {}
    headers = []

    for idx, header in enumerate(raw_headers):
        name = header.strip() if header and header.strip() else f"col_{idx + 1}"

        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1

        headers.append(name)

    return headers


def _csv_rows_to_records(rows):
    """Turn parsed CSV rows (list-of-lists, header first) into (fieldnames, records)."""

    if not rows:
        return [], []

    fieldnames = _dedupe_headers(rows[0])
    width = len(fieldnames)
    records = []

    for row in rows[1:]:
        row = list(row)

        # Defensive: pad/truncate ragged rows rather than crash on messy input.
        if len(row) < width:
            row = row + [""] * (width - len(row))
        elif len(row) > width:
            row = row[:width - 1] + [",".join(row[width - 1:])]

        record = {}
        for name, value in zip(fieldnames, row):
            record[name] = value if value != "" else None

        records.append(record)

    return fieldnames, records


def _flatten(value, prefix=""):
    """Flatten one level of nested dicts using dot-notation keys."""

    flat = {}

    if isinstance(value, dict):
        for key, sub_value in value.items():
            full_key = f"{prefix}.{key}" if prefix else str(key)

            if isinstance(sub_value, dict):
                flat.update(_flatten(sub_value, full_key))
            elif isinstance(sub_value, list):
                flat[full_key] = std_json.dumps(sub_value)
            else:
                flat[full_key] = sub_value
    else:
        flat[prefix or "value"] = value

    return flat


def _json_data_to_records(data):
    """
    Turn parsed JSON into (fieldnames, records).

    Accepts three tabular shapes:
      - an array of objects:              [{...}, {...}]
      - a single object (one-row table):  {...}
      - a single-key wrapper around an
        array of objects, a common API
        response shape:                   {"users": [{...}, {...}]}
    """

    if isinstance(data, dict):

        # Common API-response wrapper: one key holding the real array.
        if len(data) == 1:
            ((only_key, only_value),) = data.items()

            if (
                isinstance(only_value, list)
                and only_value
                and all(isinstance(item, dict) for item in only_value)
            ):
                data = only_value

        # Still a dict (no wrapper matched) -> treat as a single-row table.
        if isinstance(data, dict):
            data = [data]

    if not isinstance(data, list):
        raise ConvertError(
            "JSON data is not tabular: expected an array of objects, a "
            "single object, or a {key: [objects]} wrapper at the root, "
            f"got {type(data).__name__}."
        )

    if not data:
        return [], []

    if not all(isinstance(item, dict) for item in data):
        raise ConvertError(
            "JSON data is not tabular: array elements must all be objects."
        )

    fieldnames = []
    records = []

    for item in data:
        flat = _flatten(item)

        for key in flat:
            if key not in fieldnames:
                fieldnames.append(key)

        records.append(flat)

    # Normalize every record to the full column set, stringify scalars so
    # the type-inference step below always works from strings (matches the
    # CSV path, which is string-only by nature).
    normalized = []

    for record in records:
        row = {}
        for name in fieldnames:
            value = record.get(name, None)

            if value is None:
                row[name] = None
            elif isinstance(value, bool):
                row[name] = "true" if value else "false"
            else:
                row[name] = str(value)

        normalized.append(row)

    return fieldnames, normalized


def to_records(path):
    """
    Parse `path` with the appropriate engine and return (fieldnames, records,
    report). `records` is a list of dicts of strings (or None for empty/null).

    Raises ConvertError if the file can't be parsed or JSON isn't tabular.
    """

    engine = get_engine(path)
    data, report = engine.parse(path)

    if data is None:
        raise ConvertError(f"Could not parse '{path}' (see inspect report).")

    if isinstance(engine, CSVEngine):
        fieldnames, records = _csv_rows_to_records(data)
    elif isinstance(engine, JSONEngine):
        fieldnames, records = _json_data_to_records(data)
    else:
        raise ConvertError(f"No conversion support for engine '{engine.name}'.")

    return fieldnames, records, report


# ============================================================
# TYPE INFERENCE
# ============================================================

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y",
    "%d/%m/%Y",
]


def _try_int(value):
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _try_float(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _try_date(value):
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return fmt
        except (TypeError, ValueError):
            continue
    return None


def infer_column_types(fieldnames, records, sample_size=100):
    """
    Sample the first `sample_size` records and infer a type per column.

    Returns dict: column -> {"sql_type": "INTEGER"|"REAL"|"TEXT",
                              "kind": "int"|"float"|"date"|"string",
                              "date_format": str or None}
    """

    sample = records[:sample_size]
    columns = {}

    for name in fieldnames:
        values = [r[name] for r in sample if r.get(name) not in (None, "")]

        if not values:
            columns[name] = {"sql_type": "TEXT", "kind": "string", "date_format": None}
            continue

        if all(_try_int(v) for v in values):
            columns[name] = {"sql_type": "INTEGER", "kind": "int", "date_format": None}
            continue

        if all(_try_float(v) for v in values):
            columns[name] = {"sql_type": "REAL", "kind": "float", "date_format": None}
            continue

        date_fmt = _try_date(values[0])
        if date_fmt and all(_try_date(v) == date_fmt for v in values):
            columns[name] = {"sql_type": "TEXT", "kind": "date", "date_format": date_fmt}
            continue

        columns[name] = {"sql_type": "TEXT", "kind": "string", "date_format": None}

    return columns


def _cast_value(value, column_info):
    if value in (None, ""):
        return None

    kind = column_info["kind"]

    try:
        if kind == "int":
            return int(value)
        if kind == "float":
            return float(value)
        if kind == "date":
            return datetime.strptime(value, column_info["date_format"]).isoformat()
    except (TypeError, ValueError):
        return str(value)

    return str(value)


# ============================================================
# IDENTIFIER SAFETY
# ============================================================

def sanitize_identifier(name):
    """Make `name` safe to use unquoted as a SQLite table/dataset name."""

    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(name))

    if not cleaned or cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"

    return cleaned


def _q(identifier):
    """Double-quote a SQL identifier, escaping embedded quotes."""

    return '"' + identifier.replace('"', '""') + '"'


def dataset_name_from_path(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return sanitize_identifier(stem)


# ============================================================
# MANIFEST
# ============================================================

def _default_manifest_path(db_path):
    return os.path.join(os.path.dirname(os.path.abspath(db_path)) or ".", "manifest.json")


def load_manifest(manifest_path):
    if not os.path.exists(manifest_path):
        return {"datasets": {}}

    with open(manifest_path, "r", encoding="utf-8") as f:
        try:
            return std_json.load(f)
        except std_json.JSONDecodeError:
            return {"datasets": {}}


def save_manifest(manifest_path, manifest):
    with open(manifest_path, "w", encoding="utf-8") as f:
        std_json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


def content_hash(records):
    """sha256 over the row data, order-preserving and deterministic."""

    payload = std_json.dumps(records, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ============================================================
# SQLITE EXPORT
# ============================================================

class SqliteExportResult:
    def __init__(self, dataset, table, version, parent_table, record_count,
                 content_hash, columns, unchanged):
        self.dataset = dataset
        self.table = table
        self.version = version
        self.parent_table = parent_table
        self.record_count = record_count
        self.content_hash = content_hash
        self.columns = columns
        self.unchanged = unchanged


def export_to_sqlite(path, db_path, manifest_path=None, sample_size=100):
    """
    Parse `path`, infer column types, and bulk-insert into a new versioned
    table (dataset_vN) inside `db_path`. Updates manifest.json alongside it.

    Returns SqliteExportResult.
    """

    fieldnames, records, _report = to_records(path)

    if not fieldnames:
        raise ConvertError(f"'{path}' produced no columns to export.")

    columns = infer_column_types(fieldnames, records, sample_size=sample_size)

    dataset = dataset_name_from_path(path)
    manifest_path = manifest_path or _default_manifest_path(db_path)
    manifest = load_manifest(manifest_path)

    dataset_entry = manifest["datasets"].setdefault(dataset, {"versions": []})
    prior_versions = dataset_entry["versions"]

    version = len(prior_versions) + 1
    parent_table = prior_versions[-1]["table"] if prior_versions else None
    table = f"{dataset}_v{version}"

    row_hash = content_hash(records)
    unchanged = bool(prior_versions) and prior_versions[-1]["content_hash"] == row_hash

    # --- build & execute the SQL ---
    col_defs = ", ".join(f"{_q(name)} {columns[name]['sql_type']}" for name in fieldnames)
    create_sql = f"CREATE TABLE {_q(table)} ({col_defs})"

    placeholders = ", ".join("?" for _ in fieldnames)
    col_list = ", ".join(_q(name) for name in fieldnames)
    insert_sql = f"INSERT INTO {_q(table)} ({col_list}) VALUES ({placeholders})"

    insert_rows = [
        tuple(_cast_value(record.get(name), columns[name]) for name in fieldnames)
        for record in records
    ]

    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(create_sql)
        conn.executemany(insert_sql, insert_rows)
        conn.commit()
    finally:
        conn.close()

    # --- update manifest ---
    entry = {
        "version": version,
        "table": table,
        "parent": parent_table,
        "content_hash": row_hash,
        "record_count": len(records),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_file": os.path.abspath(path),
        "columns": {name: columns[name]["sql_type"] for name in fieldnames},
    }

    prior_versions.append(entry)
    save_manifest(manifest_path, manifest)

    return SqliteExportResult(
        dataset=dataset,
        table=table,
        version=version,
        parent_table=parent_table,
        record_count=len(records),
        content_hash=row_hash,
        columns={name: columns[name]["sql_type"] for name in fieldnames},
        unchanged=unchanged,
    )


# ============================================================
# DIFF
# ============================================================

class DiffResult:
    def __init__(self, key, columns_a, columns_b, added, removed, modified):
        self.key = key
        self.columns_a = columns_a
        self.columns_b = columns_b
        self.added = added        # list of dict rows (new rows, from table_b)
        self.removed = removed    # list of dict rows (old rows, from table_a)
        self.modified = modified  # list of (key_value, [(field, old, new), ...])

    @property
    def has_changes(self):
        return bool(self.added or self.removed or self.modified)


def _table_columns(conn, table):
    cursor = conn.execute(f"PRAGMA table_info({_q(table)})")
    cols = [row[1] for row in cursor.fetchall()]
    if not cols:
        raise ConvertError(f"Table '{table}' does not exist in this database.")
    return cols


def _table_rows_by_key(conn, table, columns, key):
    if key not in columns:
        raise ConvertError(f"Key column '{key}' not found in table '{table}'.")

    cursor = conn.execute(f"SELECT {', '.join(_q(c) for c in columns)} FROM {_q(table)}")
    rows = {}
    for raw in cursor.fetchall():
        record = dict(zip(columns, raw))
        rows[record[key]] = record
    return rows


def diff_tables(db_path, table_a, table_b, key):
    """Compare two versioned tables by primary key. Returns a DiffResult."""

    conn = sqlite3.connect(db_path)
    try:
        columns_a = _table_columns(conn, table_a)
        columns_b = _table_columns(conn, table_b)

        rows_a = _table_rows_by_key(conn, table_a, columns_a, key)
        rows_b = _table_rows_by_key(conn, table_b, columns_b, key)
    finally:
        conn.close()

    shared_columns = [c for c in columns_a if c in columns_b and c != key]

    keys_a = set(rows_a)
    keys_b = set(rows_b)

    added = [rows_b[k] for k in sorted(keys_b - keys_a, key=str)]
    removed = [rows_a[k] for k in sorted(keys_a - keys_b, key=str)]

    modified = []
    for k in sorted(keys_a & keys_b, key=str):
        row_a, row_b = rows_a[k], rows_b[k]
        changes = [
            (col, row_a[col], row_b[col])
            for col in shared_columns
            if row_a[col] != row_b[col]
        ]
        if changes:
            modified.append((k, changes))

    return DiffResult(key, columns_a, columns_b, added, removed, modified)


# ============================================================
# CSV <-> JSON CONVERSION
# ============================================================

def convert_csv_to_json(path, output_path):
    """Parse a CSV file and write it out as a JSON array of objects."""

    fieldnames, records, report = to_records(path)

    with open(output_path, "w", encoding="utf-8") as f:
        std_json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return len(records), report


def convert_json_to_csv(path, output_path):
    """Parse a tabular JSON file (array of flat objects) and write CSV."""

    fieldnames, records, report = to_records(path)

    rows = [fieldnames]
    for record in records:
        rows.append(["" if record.get(name) is None else str(record[name]) for name in fieldnames])

    CSVEngine().serialize(rows, output_path)

    return len(records), report