# dataShield — Full Feature Demo Pipeline

Run these in order from the folder containing `dataShield.py`, `engine.py`, `report.py`, `convert.py`, `test_broken.csv`, and `test_broken.jsonc`. Each command is in its own block so it can be copied individually.

---

## 0. Clean slate — delete all existing DB versions

```powershell
Remove-Item data.db, manifest.json -ErrorAction SilentlyContinue
```

---

## 1. CSV Engine — inspect the broken file

```powershell
python dataShield.py inspect test_broken.csv
```

Shows: `duplicate_header`, two `ragged_row` errors, `empty_required_field`, `unclosed_quoted_field`.

---

## 2. CSV Engine — repair it

```powershell
python dataShield.py repair test_broken.csv --output test_fixed.csv
```

5 fixes applied, 0 remaining errors, all 10 rows preserved.

---

## 3. JSON/JSONC Engine — inspect the broken file

```powershell
python dataShield.py inspect test_broken.jsonc
```

Shows: two `jsonc_comment` notices, `unterminated_string`, `unterminated_array`.

---

## 4. JSON/JSONC Engine — repair it

```powershell
python dataShield.py repair test_broken.jsonc --output test_fixed.json
```

4 fixes applied, 0 remaining errors, all 10 users preserved.

---

## 5. Convert — CSV → SQLite (creates version 1)

```powershell
python dataShield.py convert test_fixed.csv --to sqlite --db data.db
```

Creates table `test_fixed_v1` with inferred column types.

---

## 6. Edit a value, then reimport (creates version 2)

Open `test_fixed.csv`, change Grace Taylor's age from `31` to `32`, save — then run:

```powershell
python dataShield.py convert test_fixed.csv --to sqlite --db data.db
```

Creates `test_fixed_v2`; `manifest.json` now tracks both versions with content hashes.

---

## 7. Diff — compare the two versions

```powershell
python dataShield.py diff test_fixed_v1 test_fixed_v2 --db data.db --key id
```

Reports the exact change: `age: 31 → 32` for `id=7` (Grace).

---

## 8. Convert — CSV → JSON

```powershell
python dataShield.py convert test_fixed.csv --to json -o users.json
```

---

## 9. Convert — JSON → CSV (round trip)

```powershell
python dataShield.py convert test_fixed.json --to csv -o users_roundtrip.csv
```

---

## 10. Prove it's a real, query-able database

```powershell
sqlite3 data.db "SELECT * FROM test_fixed_v1;"
```

```powershell
sqlite3 data.db ".schema test_fixed_v1"
```

```powershell
type manifest.json
```

---

### Suggested narrative order for judges

Broken file → **inspect** (diagnose) → **repair** (fix, show before/after) → **convert --to sqlite** (typed, queryable) → edit + reimport → **diff** (prove versioning has teeth) → **convert --to json / --to csv** (format flexibility) → close by querying the raw `.db` file live.
