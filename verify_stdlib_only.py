"""
verify_stdlib_only.py — automated proof that dataShield's source files
import nothing but the Python standard library.

Walks every submitted .py file, parses its import statements with the
`ast` module (no execution, no false negatives from conditional imports),
and cross-checks each top-level module name against
`sys.stdlib_module_names` (Python's own authoritative list of standard
library module names, available since Python 3.10).
"""

import ast
import sys

SUBMITTED_FILES = ["dataShield.py", "engine.py", "convert.py", "report.py"]

# Local project modules import each other; that's not a third-party
# dependency, it's the project's own code.
LOCAL_MODULES = {"engine", "convert", "report", "dataShield"}


def top_level_imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])

    return names


def main():
    print(f"Python version: {sys.version}")
    print(f"Checking files:  {', '.join(SUBMITTED_FILES)}")
    print()

    all_clean = True

    for path in SUBMITTED_FILES:
        imports = sorted(top_level_imports(path))
        print(f"--- {path} ---")

        for name in imports:
            if name in LOCAL_MODULES:
                verdict = "LOCAL PROJECT MODULE"
            elif name in sys.stdlib_module_names:
                verdict = "STANDARD LIBRARY"
            else:
                verdict = "*** THIRD-PARTY *** "
                all_clean = False

            print(f"  {name:<20} {verdict}")

        print()

    print("=" * 60)
    if all_clean:
        print("RESULT: PASS — every import is either the Python standard")
        print("library or this project's own local modules. ")
        print("Zero third-party dependencies detected.")
    else:
        print("RESULT: FAIL — third-party import(s) detected above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
