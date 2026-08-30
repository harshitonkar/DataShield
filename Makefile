# dataShield — Makefile
#
# Python needs no compilation step, so there is no "build" in the
# traditional sense — the interpreter running the script *is* the
# runnable artifact. What this Makefile provides instead is the
# one-command entry point a judge actually needs: `make demo` runs
# every feature (CSV Engine, JSON/JSONC Engine, inspect, repair,
# convert to sqlite/json/csv, versioning, diff) against the included
# sample data, end to end, with zero manual typing beyond that one
# command.

PYTHON := python3

.PHONY: all demo run test clean

all: demo

# One command, full feature tour.
demo:
	@echo "============================================================"
	@echo " 1/9  CSV Engine — inspect (finds duplicate header, ragged"
	@echo "      rows, empty field, unclosed quote)"
	@echo "============================================================"
	$(PYTHON) dataShield.py inspect test_broken.csv
	@echo ""
	@echo "============================================================"
	@echo " 2/9  CSV Engine — repair (fixes everything above)"
	@echo "============================================================"
	$(PYTHON) dataShield.py repair test_broken.csv --output test_fixed.csv
	@echo ""
	@echo "============================================================"
	@echo " 3/9  JSON/JSONC Engine — inspect (finds comments,"
	@echo "      unterminated string, unterminated array)"
	@echo "============================================================"
	$(PYTHON) dataShield.py inspect test_broken.jsonc
	@echo ""
	@echo "============================================================"
	@echo " 4/9  JSON/JSONC Engine — repair"
	@echo "============================================================"
	$(PYTHON) dataShield.py repair test_broken.jsonc --output test_fixed.json
	@echo ""
	@echo "============================================================"
	@echo " 5/9  Convert — CSV to SQLite (creates version 1)"
	@echo "============================================================"
	$(PYTHON) dataShield.py convert test_fixed.csv --to sqlite --db demo_data.db --manifest demo_manifest.json
	@echo ""
	@echo "============================================================"
	@echo " 6/9  Re-import the same file (creates version 2)"
	@echo "============================================================"
	$(PYTHON) dataShield.py convert test_fixed.csv --to sqlite --db demo_data.db --manifest demo_manifest.json
	@echo ""
	@echo "============================================================"
	@echo " 7/9  Diff — compare version 1 and version 2 by key"
	@echo "============================================================"
	$(PYTHON) dataShield.py diff test_fixed_v1 test_fixed_v2 --db demo_data.db --key id
	@echo ""
	@echo "============================================================"
	@echo " 8/9  Convert — CSV to JSON"
	@echo "============================================================"
	$(PYTHON) dataShield.py convert test_fixed.csv --to json -o demo_users.json
	@echo ""
	@echo "============================================================"
	@echo " 9/9  Convert — JSON to CSV (round trip)"
	@echo "============================================================"
	$(PYTHON) dataShield.py convert demo_users.json --to csv -o demo_users_roundtrip.csv
	@echo ""
	@echo "============================================================"
	@echo " Demo complete. Real, query-able database at demo_data.db"
	@echo " Try:  sqlite3 demo_data.db \"SELECT * FROM test_fixed_v1;\""
	@echo "============================================================"

# Prints CLI usage — the closest thing to "just run it".
run:
	$(PYTHON) dataShield.py --help

# Re-runs the automated zero-dependency proof.
test:
	$(PYTHON) verify_stdlib_only.py

# Removes every artifact the demo generates, leaving only source + samples.
clean:
	rm -f demo_data.db demo_manifest.json test_fixed.csv test_fixed.json
	rm -f demo_users.json demo_users_roundtrip.csv
	rm -rf __pycache__
