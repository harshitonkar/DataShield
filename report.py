"""
report.py — shared vocabulary every engine (CSV, JSON, ...) reports problems in.

Nothing here knows about CSV or JSON specifically. An engine just creates
Issue objects and hands them to a Report. This is what lets `inspect` and
`repair` print in one consistent format no matter which file type you fed in.
"""

from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    def __str__(self):
        return self.value


@dataclass
class Issue:
    """One problem found in a file."""
    line: int              # 1-indexed line number, 0 if not applicable
    column: int            # 1-indexed column number, 0 if not applicable
    kind: str              # short machine-friendly tag, e.g. "ragged_row"
    severity: Severity
    message: str           # human-readable description

    def __str__(self):
        loc = f"{self.line}:{self.column}" if self.line else "-"
        return f"[{self.severity}] {loc}  {self.kind}: {self.message}"


@dataclass
class Correction:
    """One fix a repair pass actually applied."""
    line: int
    kind: str               # e.g. "padded_missing_field"
    message: str

    def __str__(self):
        loc = self.line if self.line else "-"
        return f"[fixed] {loc}  {self.kind}: {self.message}"


@dataclass
class Report:
    """Collects Issues (and, during repair, Corrections) for one file."""
    source: str = ""
    issues: list = field(default_factory=list)
    corrections: list = field(default_factory=list)

    def add_issue(self, issue: Issue):
        self.issues.append(issue)

    def add_correction(self, correction: Correction):
        self.corrections.append(correction)

    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    def summary_line(self) -> str:
        errors = sum(1 for i in self.issues if i.severity == Severity.ERROR)
        warnings = sum(1 for i in self.issues if i.severity == Severity.WARNING)
        infos = sum(1 for i in self.issues if i.severity == Severity.INFO)
        return (f"{self.source}: {errors} error(s), {warnings} warning(s), "
                f"{infos} info(s), {len(self.corrections)} fix(es) applied")

    def print_report(self):
        print(f"--- Report: {self.source} ---")
        if not self.issues and not self.corrections:
            print("  No issues found.")
        for issue in self.issues:
            print(f"  {issue}")
        for correction in self.corrections:
            print(f"  {correction}")
        print(self.summary_line())
