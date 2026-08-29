"""
DataShield CLI
==============

Hack n Achieve
Data Quality • Detection • Repair

Supported engines:
    CSV
    JSON
    JSONC

Commands:

    python dataShield.py inspect <file>
    python dataShield.py repair <file> --output <output>

The CLI is responsible only for presentation and orchestration.
Actual parsing and repair logic lives inside engine.py.
"""

import argparse
import os
import sys
import time

from engine import get_engine


# ============================================================
# TERMINAL COLORS
# ============================================================

class Color:
    RESET = "\033[0m"

    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"


def color(text, colour):
    """Apply ANSI colour when running in an interactive terminal."""

    if not sys.stdout.isatty():
        return text

    return f"{colour}{text}{Color.RESET}"


# ============================================================
# SYMBOLS
# ============================================================

CHECK = "✓"
CROSS = "✖"
WARN = "⚠"
INFO = "●"
SHIELD = "🛡"
ARROW = "→"


# ============================================================
# BANNER
# ============================================================

def print_banner():
    """Display the Hack n Achieve DataShield banner."""

    print()

    lines = [
        "╔══════════════════════════════════════════════════════════╗",
        "║                                                          ║",
        "║              🛡  D A T A S H I E L D                    ║",
        "║                                                          ║",
        "║          Data Quality • Detection • Repair              ║",
        "║                                                          ║",
        "║                 H A C K  N  A C H I E V E               ║",
        "║                                                          ║",
        "║        ─────────────────────────────────────             ║",
        "║          Custom State-Machine Data Engine                ║",
        "║        ─────────────────────────────────────             ║",
        "║                                                          ║",
        "╚══════════════════════════════════════════════════════════╝",
    ]

    for i, line in enumerate(lines):

        if i in (2, 4):
            print(color(line, Color.BOLD + Color.WHITE))

        elif i == 6:
            print(color(line, Color.BOLD + Color.YELLOW))

        else:
            print(color(line, Color.CYAN))

    print()


# ============================================================
# GENERAL UI HELPERS
# ============================================================

def print_section(title):
    """Print a consistent CLI section."""

    print()

    print(
        color(
            f"  {title}",
            Color.BOLD + Color.WHITE,
        )
    )

    print(
        color(
            "  " + "─" * 54,
            Color.DIM,
        )
    )


def print_status(label, value):
    """Print a label/value pair."""

    print(
        f"  {color(label.ljust(15), Color.DIM)}"
        f"{value}"
    )


def spinner(message, duration=0.45):
    """Display a short terminal processing animation."""

    if not sys.stdout.isatty():
        print(f"  {message}")
        return

    frames = [
        "⠋",
        "⠙",
        "⠹",
        "⠸",
        "⠼",
        "⠴",
        "⠦",
        "⠧",
    ]

    end_time = time.time() + duration
    index = 0

    while time.time() < end_time:

        frame = frames[index % len(frames)]

        print(
            f"\r  {color(frame, Color.CYAN)} "
            f"{message}",
            end="",
            flush=True,
        )

        time.sleep(0.06)

        index += 1

    print(
        f"\r  {color(CHECK, Color.GREEN)} "
        f"{message}"
    )


def get_filename(path):
    """Return only the ffilename."""

    return os.path.basename(path)


def get_file_size(path):
    """Return human-readable file size."""

    try:
        size = os.path.getsize(path)

    except OSError:
        return "unknown"

    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


# ============================================================
# ENGINE INFORMATION
# ============================================================

def get_engine_display_name(engine):
    """Return a human-friendly engine name."""

    name = getattr(engine, "name", "unknown").lower()

    if name == "csv":
        return "CSV State Machine"

    if name == "json":
        return "JSON Recursive Descent"

    return name.upper()


def get_parser_description(engine, path):
    """Return parser description based on the active engine."""

    name = getattr(engine, "name", "").lower()

    extension = os.path.splitext(path)[1].lower()

    if name == "csv":
        return "Character-by-character State Machine"

    if name == "json":

        if extension == ".jsonc":
            return "Tokenizer + Recursive-Descent Parser"

        return "Tokenizer + Recursive-Descent Parser"

    return "Format-specific Engine"


def get_format_label(engine, path):
    """Return a clean format label."""

    extension = os.path.splitext(path)[1].lower()

    if extension == ".jsonc":
        return "JSONC"

    if extension == ".json":
        return "JSON"

    if extension == ".csv":
        return "CSV"

    return extension.upper().lstrip(".") or "UNKNOWN"


# ============================================================
# REPORT HELPERS
# ============================================================

def get_issue_severity(issue):
    """Safely extract severity from a Report Issue."""

    severity = getattr(issue, "severity", "")

    return getattr(
        severity,
        "value",
        str(severity),
    ).lower()


def count_issues(report):
    """
    Count report issues without assuming Report exposes
    error_count/warning_count/info_count properties.
    """

    errors = 0
    warnings = 0
    infos = 0

    for issue in getattr(report, "issues", []):

        severity = get_issue_severity(issue)

        if severity == "error":
            errors += 1

        elif severity == "warning":
            warnings += 1

        elif severity == "info":
            infos += 1

    return errors, warnings, infos


def get_issue_location(issue):
    """Return issue location as line:column."""

    line = getattr(issue, "line", 0)
    column = getattr(issue, "column", 0)

    return f"{line}:{column}"


# ============================================================
# ISSUE DISPLAY
# ============================================================

def severity_icon(issue):
    """Return coloured icon for an issue."""

    severity = get_issue_severity(issue)

    if severity == "error":
        return color(CROSS, Color.RED)

    if severity == "warning":
        return color(WARN, Color.YELLOW)

    return color(INFO, Color.BLUE)


def severity_colour(issue):
    """Return colour for an issue."""

    severity = get_issue_severity(issue)

    if severity == "error":
        return Color.RED

    if severity == "warning":
        return Color.YELLOW

    return Color.BLUE


def print_issues(report):
    """Display all issues found by an engine."""

    issues = getattr(report, "issues", [])

    if not issues:

        print()

        print(
            f"  {color(CHECK, Color.GREEN)} "
            f"{color('No issues detected.', Color.GREEN)}"
        )

        return

    print_section("ISSUES FOUND")

    for issue in issues:

        icon = severity_icon(issue)
        colour = severity_colour(issue)

        location = get_issue_location(issue)

        kind = getattr(
            issue,
            "kind",
            "unknown_issue",
        )

        message = getattr(
            issue,
            "message",
            "",
        )

        print(
            f"  {icon} "
            f"{color(location.ljust(8), Color.DIM)}"
            f"{color(kind, colour)}"
        )

        print(
            f"      {message}"
        )

        print()


# ============================================================
# CORRECTION DISPLAY
# ============================================================

def print_corrections(report):
    """Display automatic repairs."""

    corrections = getattr(
        report,
        "corrections",
        [],
    )

    if not corrections:

        print()

        print(
            f"  {color(INFO, Color.BLUE)} "
            "No automatic corrections were required."
        )

        return

    print_section("CORRECTIONS APPLIED")

    for correction in corrections:

        kind = getattr(
            correction,
            "kind",
            "repair",
        )

        message = getattr(
            correction,
            "message",
            "",
        )

        line = getattr(
            correction,
            "line",
            0,
        )

        if line:
            location = f"{line}"
        else:
            location = "global"

        print(
            f"  {color(CHECK, Color.GREEN)} "
            f"{color(location.ljust(8), Color.DIM)}"
            f"{color(kind, Color.GREEN)}"
        )

        print(
            f"      {message}"
        )

        print()


# ============================================================
# SUMMARY
# ============================================================

def print_summary(report, mode):
    """Display the final DataShield summary."""

    errors, warnings, infos = count_issues(report)

    corrections = getattr(
        report,
        "corrections",
        [],
    )

    fixes = len(corrections)

    print_section("SUMMARY")

    print_status(
        "Errors",
        color(
            str(errors),
            Color.RED if errors else Color.GREEN,
        ),
    )

    print_status(
        "Warnings",
        color(
            str(warnings),
            Color.YELLOW if warnings else Color.GREEN,
        ),
    )

    print_status(
        "Info",
        color(
            str(infos),
            Color.BLUE if infos else Color.DIM,
        ),
    )

    print_status(
        "Fixes",
        color(
            str(fixes),
            Color.GREEN if fixes else Color.DIM,
        ),
    )

    print()

    # --------------------------------------------------------
    # INSPECT RESULT
    # --------------------------------------------------------

    if mode == "inspect":

        if errors:

            print(
                f"  {color(CROSS, Color.RED)} "
                f"{color('File requires attention.', Color.RED)}"
            )

        elif warnings:

            print(
                f"  {color(WARN, Color.YELLOW)} "
                f"{color('File is valid but has warnings.', Color.YELLOW)}"
            )

        else:

            print(
                f"  {color(CHECK, Color.GREEN)} "
                f"{color('File passed inspection.', Color.GREEN)}"
            )

    # --------------------------------------------------------
    # REPAIR RESULT
    # --------------------------------------------------------

    elif mode == "repair":

        if errors:

            print(
                f"  {color(WARN, Color.YELLOW)} "
                f"{color('Repair completed with remaining issues.', Color.YELLOW)}"
            )

        elif fixes:

            print(
                f"  {color(CHECK, Color.GREEN)} "
                f"{color('Repair process completed successfully.', Color.GREEN)}"
            )

        else:

            print(
                f"  {color(CHECK, Color.GREEN)} "
                f"{color('No repairs were necessary.', Color.GREEN)}"
            )


# ============================================================
# INSPECT COMMAND
# ============================================================

def inspect_file(path):
    """Inspect a file using the registered engine."""

    print_banner()

    try:
        engine = get_engine(path)

    except ValueError as error:

        print(
            f"  {color(CROSS, Color.RED)} "
            f"{color(str(error), Color.RED)}"
        )

        print()

        return 1

    format_name = get_format_label(
        engine,
        path,
    )

    print(
        f"  {color(SHIELD, Color.CYAN)} "
        f"{color('Inspecting:', Color.BOLD)} "
        f"{get_filename(path)}"
    )

    print()

    print_status(
        "File",
        get_filename(path),
    )

    print_status(
        "Format",
        color(
            format_name,
            Color.CYAN,
        ),
    )

    print_status(
        "Size",
        get_file_size(path),
    )

    print_status(
        "Engine",
        color(
            get_engine_display_name(engine),
            Color.CYAN,
        ),
    )

    print_status(
        "Parser",
        get_parser_description(
            engine,
            path,
        ),
    )

    print()

    spinner(
        f"Analyzing {format_name} file..."
    )

    try:

        data, report = engine.parse(path)

    except Exception as error:

        print()

        print(
            f"  {color(CROSS, Color.RED)} "
            f"{color('Engine failure:', Color.RED)} "
            f"{error}"
        )

        print()

        return 1

    print_issues(report)

    print_summary(
        report,
        "inspect",
    )

    print()

    return 0


# ============================================================
# REPAIR COMMAND
# ============================================================

def repair_file(path, output_path):
    """Repair a file using the registered engine."""

    print_banner()

    try:
        engine = get_engine(path)

    except ValueError as error:

        print(
            f"  {color(CROSS, Color.RED)} "
            f"{color(str(error), Color.RED)}"
        )

        print()

        return 1

    format_name = get_format_label(
        engine,
        path,
    )

    print(
        f"  {color(SHIELD, Color.CYAN)} "
        f"{color('DataShield Repair', Color.BOLD + Color.WHITE)}"
    )

    print()

    print_status(
        "Input",
        get_filename(path),
    )

    print_status(
        "Output",
        get_filename(output_path),
    )

    print_status(
        "Format",
        color(
            format_name,
            Color.CYAN,
        ),
    )

    print_status(
        "Engine",
        color(
            get_engine_display_name(engine),
            Color.CYAN,
        ),
    )

    print_status(
        "Parser",
        get_parser_description(
            engine,
            path,
        ),
    )

    print()

    spinner(
        f"Scanning {format_name} file..."
    )

    try:

        report = engine.repair(
            path,
            output_path,
        )

    except Exception as error:

        print()

        print(
            f"  {color(CROSS, Color.RED)} "
            f"{color('Repair failed:', Color.RED)} "
            f"{error}"
        )

        print()

        return 1

    print_corrections(report)

    # --------------------------------------------------------
    # OUTPUT INFORMATION
    # --------------------------------------------------------

    if os.path.exists(output_path):

        print_section("OUTPUT")

        print_status(
            "File",
            get_filename(output_path),
        )

        print_status(
            "Size",
            get_file_size(output_path),
        )

        print_status(
            "Status",
            color(
                "READY",
                Color.GREEN,
            ),
        )

    else:

        print()

        print(
            f"  {color(CROSS, Color.RED)} "
            f"{color('Output file was not created.', Color.RED)}"
        )

        print()

        return 1

    print_summary(
        report,
        "repair",
    )

    print()

    return 0


# ============================================================
# ARGUMENT PARSER
# ============================================================

def build_parser():
    """Create the DataShield command-line parser."""

    parser = argparse.ArgumentParser(
        prog="dataShield",
        description=(
            "DataShield — inspect, detect and repair "
            "messy data files."
        ),
        epilog=(
            "Examples:\n"
            "  python dataShield.py inspect test_broken.csv\n"
            "  python dataShield.py inspect test_broken.json\n"
            "  python dataShield.py inspect test_broken.jsonc\n"
            "  python dataShield.py repair test_broken.csv "
            "--output test_fixed.csv\n"
            "  python dataShield.py repair test_broken.jsonc "
            "--output test_fixed.json"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
    )

    # ========================================================
    # INSPECT
    # ========================================================

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect a file for data-quality problems.",
        description=(
            "Analyze a file without modifying the original."
        ),
    )

    inspect_parser.add_argument(
        "file",
        help="Path to the file to inspect.",
    )

    # ========================================================
    # REPAIR
    # ========================================================

    repair_parser = subparsers.add_parser(
        "repair",
        help="Repair a file and write a corrected copy.",
        description=(
            "Analyze a file, automatically repair supported "
            "problems, and write the result."
        ),
    )

    repair_parser.add_argument(
        "file",
        help="Path to the input file.",
    )

    repair_parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Path where the repaired file will be written.",
    )

    return parser


# ============================================================
# MAIN
# ============================================================

def main():
    """DataShield CLI entry point."""

    parser = build_parser()

    args = parser.parse_args()

    # ========================================================
    # NO COMMAND
    # ========================================================

    if args.command is None:

        print_banner()

        parser.print_help()

        print()

        print(
            color(
                "  Supported formats: CSV • JSON • JSONC",
                Color.DIM,
            )
        )

        print()

        return 0

    # ========================================================
    # INPUT VALIDATION
    # ========================================================

    if not os.path.isfile(args.file):

        print_banner()

        print(
            f"  {color(CROSS, Color.RED)} "
            f"{color('File not found:', Color.RED)} "
            f"{args.file}"
        )

        print()

        return 1

    # ========================================================
    # INSPECT
    # ========================================================

    if args.command == "inspect":

        return inspect_file(
            args.file
        )

    # ========================================================
    # REPAIR
    # ========================================================

    if args.command == "repair":

        # Never overwrite the original input file.
        if os.path.abspath(args.file) == os.path.abspath(
            args.output
        ):

            print_banner()

            print(
                f"  {color(CROSS, Color.RED)} "
                f"{color('Input and output files must be different.', Color.RED)}"
            )

            print()

            return 1

        return repair_file(
            args.file,
            args.output,
        )

    return 0


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
