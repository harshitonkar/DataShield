"""
engine.py — the plugin contract.

Every file-format engine (CSV, JSON, later Markdown/Log) implements this
same interface: Parse, Repair, Serialize. dataShield.py never needs to know
which engine it's talking to — it just picks one from EXTENSION_MAP and
calls the three methods below.

Phase 1 has no real engines yet — just the interface and a placeholder so
the CLI has something to route to and print "not implemented" from.
"""

from abc import ABC, abstractmethod
from report import Report


class Engine(ABC):
    """Base class every format engine must implement."""

    name = "base"  # override in subclasses, e.g. "csv", "json"

    @abstractmethod
    def parse(self, path: str):
        """
        Read the file at `path`.
        Returns (data, report): `data` is whatever internal representation
        the engine wants (rows, an AST, ...); `report` is a Report full of
        Issues found while parsing.
        """
        raise NotImplementedError

    @abstractmethod
    def repair(self, path: str, output_path: str):
        """
        Parse `path`, fix what can be fixed, write the corrected file to
        `output_path`. Returns a Report whose `corrections` list records
        every fix that was applied.
        """
        raise NotImplementedError

    @abstractmethod
    def serialize(self, data, output_path: str):
        """Write `data` (as produced by parse) back out to `output_path`."""
        raise NotImplementedError


class NotImplementedEngine(Engine):
    """
    Placeholder engine. Used for any extension we don't have a real engine
    for yet, and as the Phase-1 stand-in for csv/json before Person A/B
    build the real thing. Every command still runs end-to-end, it just says
    so plainly instead of crashing.
    """

    name = "not_implemented"

    def parse(self, path: str):
        report = Report(source=path)
        print(f"[{self.name}] parse: not implemented yet for {path}")
        return None, report

    def repair(self, path: str, output_path: str):
        report = Report(source=path)
        print(f"[{self.name}] repair: not implemented yet for {path}")
        return report

    def serialize(self, data, output_path: str):
        print(f"[{self.name}] serialize: not implemented yet for {output_path}")


# Maps file extension -> Engine instance.
# Person A/B will replace these two lines with CSVEngine() / JSONEngine()
# once those exist. Everything else in the CLI stays the same.
EXTENSION_MAP = {
    ".csv": NotImplementedEngine(),
    ".json": NotImplementedEngine(),
    ".jsonc": NotImplementedEngine(),
}


def get_engine(path: str) -> Engine:
    """Pick the right engine for a file based on its extension."""
    for ext, engine in EXTENSION_MAP.items():
        if path.endswith(ext):
            return engine
    raise ValueError(
        f"No engine registered for '{path}'. "
        f"Supported extensions: {', '.join(EXTENSION_MAP)}"
    )
