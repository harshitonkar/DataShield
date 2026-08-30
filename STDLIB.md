# STDLIB.md

Every place in this project where we'd normally reach for a third-party
package, and the standard-library module we used instead — organized
by the feature each substitution lives in.

## Summary table

| Feature | Would normally use | Used instead (stdlib) | Why (short) |
|---|---|---|---|
| CSV Engine | `csv` module / `pandas.read_csv` | Hand-rolled character-by-character state machine (`CSVEngine._parse_core`) | Need located, itemized errors (line:column), not a single pass/fail exception |
| JSON/JSONC Engine | `json` module / `commentjson`, `json5` | Hand-written tokenizer + recursive-descent parser (`JSONEngine`) | `json.loads()` can't parse comments or recover from broken input with per-issue detail |
| CSV → SQLite3 (export) | `SQLAlchemy` / `pandas.to_sql()` | `sqlite3` directly, hand-built `CREATE TABLE` + `executemany()` | Full control over inferred types, quoted identifiers, and versioned table names |
| CSV → SQLite3 (versioning) | `xxhash` / `blake3` | `hashlib.sha256()` over serialized row data | Stdlib hashing is already correct for this data size; speed isn't the bottleneck |
| CSV → SQLite3 (diff) | `deepdiff` / `pandas.DataFrame.compare()` | Plain `dict`/`set` comparison keyed by primary key (`diff_tables`) | Needed a diff scoped to "matched by key, list changed fields," not generic structural diffing |
| CSV → SQLite3 (type inference) | `python-dateutil` | `datetime.strptime()` against a fixed, explicit format list | Auto-guessing dates is genuinely ambiguous (`01/02/2024`?); one consistent format is more honest |
| CSV → JSON / JSON → CSV | A "csvtojson"-style conversion package | Shared `to_records()` step feeding the CSV Engine's `serialize()` or stdlib `json` | Both directions reuse the same engines' own parsed structures — no separate conversion library needed |
| CLI (all features) | `click` / `typer` | `argparse` with `add_subparsers()` | Covers subcommands, flags, choices, and `--help` with zero install step |
| CLI (all features) | `colorama` / `rich` | Hand-rolled ANSI escape codes (`Color` class) | The actual need was "colored terminal output," not a full rendering engine |

---

## CSV Engine

### CSV parsing/writing → hand-rolled state machine, not `csv`

**Would normally use:** the `csv` module (or `pandas.read_csv` for
anything beyond basic parsing).

**Used instead:** a character-by-character state machine in
`CSVEngine._parse_core()` (`engine.py`), with explicit states
(`FieldStart`, `InQuotedField`, `InUnquotedField`, `QuoteInQuotedField`,
`AfterField`).

**Why:** the entire premise of `inspect` is surfacing *specific,
located* problems — an unclosed quote at line 11, column 47; a ragged
row with 6 fields where 5 were expected. Python's `csv` module either
parses successfully or raises a generic exception; it has no concept
of "here are all five problems in this file, with locations, and here
is a report object I can also hand to `repair`." Writing the state
machine ourselves is also what lets `serialize()` do its own
RFC 4180-style quoting (`engine.py`, `CSVEngine.serialize()`) by hand
rather than via `csv.writer`.

---

## JSON/JSONC Engine

### JSON/JSONC parsing → hand-rolled tokenizer + recursive-descent parser, not `json`

**Would normally use:** the `json` module for parsing, or a
JSONC-aware third-party library (e.g. `commentjson`, `json5`) for the
comment/trailing-comma support.

**Used instead:** a hand-written tokenizer (`JSONEngine`, `engine.py`)
that walks the raw text character by character, followed by a
recursive-descent parser over the resulting tokens.

**Why:** `json.loads()` on a file with a `//` comment or trailing
comma simply throws `JSONDecodeError` with a single location and no
recovery — useless for a tool whose job is to report *every* issue and
then fix them. The standard library's `json` module *is* still used,
but only for the one place it's the right tool: emitting the final,
already-valid Python structure back out as strict JSON
(`std_json.dump(...)` in `convert.py` and the JSON writer in
`engine.py`).

---

## CSV → SQLite3

### SQLite export → `sqlite3` directly, not `SQLAlchemy`/`pandas.to_sql`

**Would normally use:** `SQLAlchemy` for the ORM/engine layer, or
`pandas.DataFrame.to_sql()` for a one-line dump.

**Used instead:** `sqlite3.connect()` with a hand-built `CREATE TABLE`
statement (column types inferred by sampling rows) and
`executemany()` for the bulk insert (`convert.py`,
`export_to_sqlite()`).

**Why:** an ORM is designed to abstract *away from* SQL — this project
needed the opposite: full control over type inference, quoted
identifiers, and versioned table names (`users_v1`, `users_v2`, ...),
which is simpler to reason about as literal SQL than through an
abstraction layer built for a different problem.

### Version content hashing → `hashlib.sha256`, not a checksum library

**Would normally use:** `xxhash` or `blake3` for speed on large
datasets.

**Used instead:** `hashlib.sha256()` directly over the serialized row
data (`convert.py`, `content_hash()`), to detect whether a re-imported
dataset actually changed before deciding on a version bump.

**Why:** `hashlib` is already the standard library's answer to exactly
this problem; the faster third-party hashers exist to solve a
performance problem this project's data sizes don't have.

### Table diffing → hand-rolled key/dict comparison, not `deepdiff`/`pandas`

**Would normally use:** `deepdiff` for structural diffing, or
`pandas.DataFrame.compare()` / a merge-based diff.

**Used instead:** two `dict`s keyed by the user-specified primary
key, compared with plain set operations for added/removed rows and a
per-field loop for modified rows (`convert.py`, `diff_tables()`).

**Why:** a generic structural-diff library reports *that* two
structures differ; this project needed a diff scoped specifically to
"matched by this key column, report only the fields that changed,"
which is a handful of lines of stdlib `dict`/`set` logic once the
matching key is known — no generic diffing engine required.

### Column type inference (dates) → `datetime.strptime` against a fixed format list, not `dateutil`

**Would normally use:** `python-dateutil`'s `parser.parse()`, which
guesses date formats automatically.

**Used instead:** `datetime.strptime()` tried against a short, explicit
list of common formats (`convert.py`, `_try_date()`), so a column is
only classified as a date if every sampled value matches the *same*
format consistently.

**Why:** `dateutil`'s auto-guessing is convenient but genuinely
ambiguous (is `01/02/2024` January 2nd or February 1st?) — requiring
one explicit, consistent format per column is more honest about what
the tool actually knows versus what it's guessing.

---

## CSV → JSON / JSON → CSV

Both directions are built on the same `to_records()` normalization
step (`convert.py`) that either engine's parsed output feeds into, so
no separate third-party conversion package (e.g. a "csvtojson"-style
library) is needed — it's the CSV Engine or JSON/JSONC Engine's own
parsed structure, re-serialized by the standard library's `json`
module or the CSV Engine's own `serialize()`.

---

## CLI (all features)

### CLI argument parsing → `argparse`, not `click`/`typer`

**Would normally use:** `click` or `typer` for subcommands, flags, and
`--help` generation.

**Used instead:** `argparse.ArgumentParser` with `add_subparsers()`
for `inspect` / `repair` / `convert` / `diff` (`dataShield.py`).

**Why:** `argparse` covers everything this CLI needs — subcommands,
required/optional flags, choices, auto-generated `--help` — with zero
install step, and the project never grew a requirement (shell
autocompletion, rich prompts) that would have justified reaching
outside it.

### Terminal color/formatting → hand-rolled ANSI codes, not `colorama`/`rich`

**Would normally use:** `colorama` (for Windows ANSI support) or
`rich` (for panels, tables, and styled text).

**Used instead:** a small `Color` class of raw ANSI escape sequences
and a `color()` helper (`dataShield.py`), plus manually aligned
`print()` calls for the report/summary boxes.

**Why:** the actual requirement was "colored, readable terminal
output" — a handful of ANSI codes and string formatting covers that
completely without a rendering engine.
