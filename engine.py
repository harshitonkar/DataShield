"""
engine.py — DataShield format engine layer.

Hack n Achieve
Data Quality • Detection • Repair

Engines:
    CSV  -> custom character-by-character state machine
    JSON -> custom tokenizer + recursive-descent parser
    JSONC -> same JSON engine with comment support

dataShield.py only needs get_engine(path).
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
import json as std_json
import os

from report import Report, Issue, Correction, Severity


# ============================================================
# BASE ENGINE CONTRACT
# ============================================================

class Engine(ABC):
    """Base class every file-format engine must implement."""

    name = "base"

    @abstractmethod
    def parse(self, path: str):
        raise NotImplementedError

    @abstractmethod
    def repair(self, path: str, output_path: str):
        raise NotImplementedError

    @abstractmethod
    def serialize(self, data, output_path: str):
        raise NotImplementedError


# ============================================================
# CSV ENGINE
# ============================================================

class CSVState(Enum):
    FIELD_START = 1
    IN_UNQUOTED = 2
    IN_QUOTED = 3
    QUOTE_IN_QUOTED = 4


class CSVEngine(Engine):
    """
    Custom character-by-character CSV parser.

    Intentionally does not use Python's csv module.
    """

    name = "csv"

    def _parse_core(self, text: str, report: Report):
        rows = []
        current_row = []
        current_field = []

        state = CSVState.FIELD_START
        line_num = 1
        col_num = 0

        idx = 0
        n = len(text)

        field_start_line = 1
        field_start_col = 1

        while idx < n:
            ch = text[idx]
            col_num += 1

            if state == CSVState.FIELD_START:

                field_start_line = line_num
                field_start_col = col_num

                if ch == '"':
                    state = CSVState.IN_QUOTED

                elif ch == ',':
                    current_row.append("")

                elif ch == '\n':
                    current_row.append("")
                    rows.append(current_row)
                    current_row = []
                    line_num += 1
                    col_num = 0

                elif ch == '\r':
                    if idx + 1 < n and text[idx + 1] == '\n':
                        idx += 1

                    current_row.append("")
                    rows.append(current_row)
                    current_row = []
                    line_num += 1
                    col_num = 0

                else:
                    current_field.append(ch)
                    state = CSVState.IN_UNQUOTED

            elif state == CSVState.IN_UNQUOTED:

                if ch == ',':
                    current_row.append("".join(current_field))
                    current_field = []
                    state = CSVState.FIELD_START

                elif ch == '\n':
                    current_row.append("".join(current_field))
                    current_field = []
                    rows.append(current_row)
                    current_row = []
                    line_num += 1
                    col_num = 0
                    state = CSVState.FIELD_START

                elif ch == '\r':
                    if idx + 1 < n and text[idx + 1] == '\n':
                        idx += 1

                    current_row.append("".join(current_field))
                    current_field = []
                    rows.append(current_row)
                    current_row = []
                    line_num += 1
                    col_num = 0
                    state = CSVState.FIELD_START

                else:
                    current_field.append(ch)

            elif state == CSVState.IN_QUOTED:

                if ch == '"':
                    state = CSVState.QUOTE_IN_QUOTED

                elif ch == '\n':
                    current_field.append(ch)
                    line_num += 1
                    col_num = 0

                elif ch == '\r':
                    if idx + 1 < n and text[idx + 1] == '\n':
                        idx += 1
                        current_field.append('\n')
                    else:
                        current_field.append('\r')

                    line_num += 1
                    col_num = 0

                else:
                    current_field.append(ch)

            elif state == CSVState.QUOTE_IN_QUOTED:

                if ch == '"':
                    current_field.append('"')
                    state = CSVState.IN_QUOTED

                elif ch == ',':
                    current_row.append("".join(current_field))
                    current_field = []
                    state = CSVState.FIELD_START

                elif ch == '\n':
                    current_row.append("".join(current_field))
                    current_field = []
                    rows.append(current_row)
                    current_row = []
                    line_num += 1
                    col_num = 0
                    state = CSVState.FIELD_START

                elif ch == '\r':
                    if idx + 1 < n and text[idx + 1] == '\n':
                        idx += 1

                    current_row.append("".join(current_field))
                    current_field = []
                    rows.append(current_row)
                    current_row = []
                    line_num += 1
                    col_num = 0
                    state = CSVState.FIELD_START

                else:
                    report.add_issue(
                        Issue(
                            line=line_num,
                            column=col_num,
                            kind="malformed_quoting",
                            severity=Severity.WARNING,
                            message=(
                                "Character directly after a closing quote "
                                "without separator"
                            ),
                        )
                    )

                    current_field.append(ch)
                    state = CSVState.IN_UNQUOTED

            idx += 1

        # EOF handling
        if state == CSVState.IN_QUOTED:
            report.add_issue(
                Issue(
                    line=field_start_line,
                    column=field_start_col,
                    kind="unclosed_quoted_field",
                    severity=Severity.ERROR,
                    message=(
                        "Reached end-of-file before finding closing quote"
                    ),
                )
            )

            current_row.append("".join(current_field))

            if current_row:
                rows.append(current_row)

        elif state in (
            CSVState.IN_UNQUOTED,
            CSVState.QUOTE_IN_QUOTED,
        ):
            current_row.append("".join(current_field))

            if current_row:
                rows.append(current_row)

        elif state == CSVState.FIELD_START and current_row:
            current_row.append("")
            rows.append(current_row)

        return rows

    def parse(self, path: str):
        report = Report(source=path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            report.add_issue(
                Issue(
                    0,
                    0,
                    "file_read_error",
                    Severity.ERROR,
                    str(e),
                )
            )
            return None, report

        rows = self._parse_core(content, report)

        if not rows:
            return rows, report

        headers = rows[0]
        seen_headers = set()

        for idx, header in enumerate(headers):

            if not header.strip():
                report.add_issue(
                    Issue(
                        1,
                        idx + 1,
                        "empty_header",
                        Severity.WARNING,
                        f"Header at column {idx + 1} is empty",
                    )
                )

            elif header in seen_headers:
                report.add_issue(
                    Issue(
                        1,
                        idx + 1,
                        "duplicate_header",
                        Severity.WARNING,
                        f"Duplicate header found: '{header}'",
                    )
                )

            seen_headers.add(header)

        expected_cols = len(headers)

        for row_idx, row in enumerate(rows[1:], start=2):

            if len(row) != expected_cols:
                report.add_issue(
                    Issue(
                        row_idx,
                        0,
                        "ragged_row",
                        Severity.ERROR,
                        (
                            "Row has inconsistent column count "
                            f"(Expected {expected_cols}, got {len(row)})"
                        ),
                    )
                )

            for col_idx, field_value in enumerate(row):

                if not field_value.strip():
                    report.add_issue(
                        Issue(
                            row_idx,
                            col_idx + 1,
                            "empty_required_field",
                            Severity.INFO,
                            (
                                f"Field at row {row_idx}, "
                                f"column {col_idx + 1} is empty"
                            ),
                        )
                    )

        return rows, report

    def repair(self, path: str, output_path: str):
        report = Report(source=path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            report.add_issue(
                Issue(
                    0,
                    0,
                    "file_read_error",
                    Severity.ERROR,
                    str(e),
                )
            )
            return report

        if "\r\n" in content:
            report.add_correction(
                Correction(
                    0,
                    "normalized_line_endings",
                    "Converted Windows CRLF to standard LF line endings",
                )
            )

        raw_rows = self._parse_core(content, report)

        # _parse_core() always recovers a usable value for these two issue
        # kinds (it never raises) — it just also flags them as Issues while
        # doing so. Since repair() actually keeps that recovered value in the
        # output, these are repairs, not remaining problems. Promote them to
        # Corrections instead of leaving them as unresolved errors/warnings.
        remaining_issues = []

        for issue in report.issues:

            if issue.kind == "unclosed_quoted_field":
                report.add_correction(
                    Correction(
                        issue.line,
                        "closed_unclosed_quote",
                        (
                            "Closed a quoted field that ran to "
                            "end-of-file, using the remaining text "
                            "as its content"
                        ),
                    )
                )

            elif issue.kind == "malformed_quoting":
                report.add_correction(
                    Correction(
                        issue.line,
                        "recovered_malformed_quoting",
                        (
                            "Recovered a field with an unexpected "
                            "character immediately after a closing quote"
                        ),
                    )
                )

            else:
                remaining_issues.append(issue)

        report.issues = remaining_issues

        if not raw_rows:
            self.serialize([], output_path)
            return report

        headers = raw_rows[0]
        repaired_headers = []
        seen_headers = {}

        for idx, header in enumerate(headers):

            original = (
                header
                if header.strip()
                else f"empty_col_{idx + 1}"
            )

            if original != header:
                report.add_correction(
                    Correction(
                        1,
                        "filled_empty_header",
                        (
                            f"Assigned name to empty header "
                            f"at column {idx + 1}"
                        ),
                    )
                )

            if original in seen_headers:

                seen_headers[original] += 1
                new_header = (
                    f"{original}_{seen_headers[original]}"
                )

                report.add_correction(
                    Correction(
                        1,
                        "rename_duplicate_header",
                        (
                            f"Renamed duplicate header "
                            f"'{original}' to '{new_header}'"
                        ),
                    )
                )

                repaired_headers.append(new_header)

            else:
                seen_headers[original] = 1
                repaired_headers.append(original)

        fixed_rows = [repaired_headers]
        expected_cols = len(repaired_headers)

        for row_idx, row in enumerate(raw_rows[1:], start=2):

            repaired_row = list(row)

            if len(repaired_row) < expected_cols:

                difference = expected_cols - len(repaired_row)
                repaired_row.extend([""] * difference)

                report.add_correction(
                    Correction(
                        row_idx,
                        "padded_missing_field",
                        (
                            f"Padded row with {difference} "
                            "missing empty fields"
                        ),
                    )
                )

            elif len(repaired_row) > expected_cols:

                excess = repaired_row[expected_cols - 1:]
                merged_value = ",".join(excess)

                repaired_row = (
                    repaired_row[:expected_cols - 1]
                    + [merged_value]
                )

                report.add_correction(
                    Correction(
                        row_idx,
                        "merge_excess_fields",
                        (
                            f"Merged {len(excess)} overflow "
                            "fields into final column"
                        ),
                    )
                )

            fixed_rows.append(repaired_row)

        self.serialize(fixed_rows, output_path)
        return report

    def serialize(self, data, output_path: str):

        with open(
            output_path,
            "w",
            encoding="utf-8",
            newline="",
        ) as f:

            for row in data:

                escaped_fields = []

                for value in row:

                    value = str(value)

                    if (
                        '"' in value
                        or "," in value
                        or "\n" in value
                        or "\r" in value
                    ):
                        safe_value = (
                            '"'
                            + value.replace('"', '""')
                            + '"'
                        )
                    else:
                        safe_value = value

                    escaped_fields.append(safe_value)

                f.write(",".join(escaped_fields) + "\n")


# ============================================================
# JSON / JSONC ENGINE
# ============================================================

class TokenType(Enum):
    LEFT_BRACE = auto()
    RIGHT_BRACE = auto()
    LEFT_BRACKET = auto()
    RIGHT_BRACKET = auto()
    COMMA = auto()
    COLON = auto()
    STRING = auto()
    NUMBER = auto()
    TRUE = auto()
    FALSE = auto()
    NULL = auto()
    EOF = auto()


class Token:
    def __init__(self, type_: TokenType, value, line: int, col: int):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return (
            f"Token({self.type.name}, "
            f"{self.value!r}, {self.line}:{self.col})"
        )


class JSONEngine(Engine):
    """
    Custom JSON/JSONC engine.

    Pipeline:
        raw text
            ↓
        tokenizer
            ↓
        recursive-descent parser
            ↓
        Python data structure
            ↓
        strict JSON serializer
    """

    name = "json"

    # --------------------------------------------------------
    # TOKENIZER
    # --------------------------------------------------------

    def _tokenize(self, text: str, report: Report):
        """Tokenize JSON/JSONC while preserving line/column positions."""

        tokens = []

        idx = 0
        n = len(text)

        line = 1
        col = 0

        while idx < n:

            ch = text[idx]

            # ------------------------------------------------
            # NEWLINES
            # ------------------------------------------------

            if ch == "\r":

                if idx + 1 < n and text[idx + 1] == "\n":
                    idx += 1

                line += 1
                col = 0
                idx += 1
                continue

            if ch == "\n":
                line += 1
                col = 0
                idx += 1
                continue

            col += 1

            # ------------------------------------------------
            # WHITESPACE
            # ------------------------------------------------

            if ch.isspace():
                idx += 1
                continue

            # ------------------------------------------------
            # STRUCTURAL TOKENS
            # ------------------------------------------------

            structural = {
                "{": TokenType.LEFT_BRACE,
                "}": TokenType.RIGHT_BRACE,
                "[": TokenType.LEFT_BRACKET,
                "]": TokenType.RIGHT_BRACKET,
                ",": TokenType.COMMA,
                ":": TokenType.COLON,
            }

            if ch in structural:
                tokens.append(
                    Token(
                        structural[ch],
                        ch,
                        line,
                        col,
                    )
                )
                idx += 1
                continue

            # ------------------------------------------------
            # JSONC COMMENTS
            # ------------------------------------------------

            if ch == "/" and idx + 1 < n:

                # Single-line comment
                if text[idx + 1] == "/":

                    report.add_issue(
                        Issue(
                            line,
                            col,
                            "jsonc_comment",
                            Severity.INFO,
                            "Found inline single line comment (//)",
                        )
                    )

                    idx += 2
                    col += 1

                    while (
                        idx < n
                        and text[idx] not in "\r\n"
                    ):
                        idx += 1
                        col += 1

                    continue

                # Multi-line comment
                if text[idx + 1] == "*":

                    start_line = line
                    start_col = col

                    report.add_issue(
                        Issue(
                            start_line,
                            start_col,
                            "jsonc_comment",
                            Severity.INFO,
                            "Found multiline block comment (/* */)",
                        )
                    )

                    idx += 2
                    col += 1
                    closed = False

                    while idx < n:

                        if (
                            text[idx] == "*"
                            and idx + 1 < n
                            and text[idx + 1] == "/"
                        ):
                            idx += 2
                            col += 2
                            closed = True
                            break

                        if text[idx] == "\r":

                            if (
                                idx + 1 < n
                                and text[idx + 1] == "\n"
                            ):
                                idx += 1

                            line += 1
                            col = 0
                            idx += 1
                            continue

                        if text[idx] == "\n":
                            line += 1
                            col = 0
                            idx += 1
                            continue

                        idx += 1
                        col += 1

                    if not closed:
                        report.add_issue(
                            Issue(
                                start_line,
                                start_col,
                                "unterminated_comment",
                                Severity.ERROR,
                                "Block comment missing closing marker '*/'",
                            )
                        )

                    continue

            # ------------------------------------------------
            # STRINGS
            # ------------------------------------------------

            if ch == '"':

                start_line = line
                start_col = col

                chars = []
                idx += 1
                col += 1
                closed = False

                while idx < n:

                    c = text[idx]

                    if c == '"':
                        closed = True
                        idx += 1
                        col += 1
                        break

                    if c == "\\":
                        chars.append(c)
                        idx += 1
                        col += 1

                        if idx < n:
                            chars.append(text[idx])

                            if text[idx] in "\r\n":
                                # Invalid escaped newline.
                                report.add_issue(
                                    Issue(
                                        line,
                                        col,
                                        "invalid_escape",
                                        Severity.ERROR,
                                        "Invalid newline inside string escape",
                                    )
                                )

                            idx += 1
                            col += 1

                        continue

                    if c == "\r" or c == "\n":

                        report.add_issue(
                            Issue(
                                start_line,
                                start_col,
                                "unterminated_string",
                                Severity.ERROR,
                                "String literal missing closing quote",
                            )
                        )

                        break

                    chars.append(c)
                    idx += 1
                    col += 1

                if not closed:
                    tokens.append(
                        Token(
                            TokenType.STRING,
                            "".join(chars),
                            start_line,
                            start_col,
                        )
                    )
                    continue

                raw_string = "".join(chars)

                # Decode JSON escapes where possible.
                try:
                    decoded = std_json.loads(
                        '"' + raw_string + '"'
                    )
                except Exception:
                    report.add_issue(
                        Issue(
                            start_line,
                            start_col,
                            "invalid_string_escape",
                            Severity.ERROR,
                            "Invalid escape sequence in string literal",
                        )
                    )
                    decoded = raw_string

                tokens.append(
                    Token(
                        TokenType.STRING,
                        decoded,
                        start_line,
                        start_col,
                    )
                )

                continue

            # ------------------------------------------------
            # NUMBERS
            # ------------------------------------------------

            if ch == "-" or ch.isdigit():

                start_line = line
                start_col = col

                start_idx = idx

                # Consume a broad numeric candidate.
                while (
                    idx < n
                    and (
                        text[idx].isdigit()
                        or text[idx] in ".-+eE"
                    )
                ):
                    idx += 1
                    col += 1

                raw_number = text[start_idx:idx]

                tokens.append(
                    Token(
                        TokenType.NUMBER,
                        raw_number,
                        start_line,
                        start_col,
                    )
                )

                continue

            # ------------------------------------------------
            # KEYWORDS
            # ------------------------------------------------

            matched_keyword = False

            for keyword, token_type, value in (
                ("true", TokenType.TRUE, True),
                ("false", TokenType.FALSE, False),
                ("null", TokenType.NULL, None),
            ):

                if text.startswith(keyword, idx):

                    tokens.append(
                        Token(
                            token_type,
                            value,
                            line,
                            col,
                        )
                    )

                    idx += len(keyword)
                    col += len(keyword)

                    matched_keyword = True
                    break

            if matched_keyword:
                continue

            # ------------------------------------------------
            # UNKNOWN CHARACTER
            # ------------------------------------------------

            report.add_issue(
                Issue(
                    line,
                    col,
                    "illegal_token",
                    Severity.ERROR,
                    (
                        "Illegal character reference detected: "
                        f"'{ch}'"
                    ),
                )
            )

            idx += 1

        tokens.append(
            Token(
                TokenType.EOF,
                None,
                line,
                col,
            )
        )

        return tokens

    # --------------------------------------------------------
    # RECURSIVE-DESCENT PARSER
    # --------------------------------------------------------

    def _parse_tokens(self, tokens: list, report: Report):

        idx = 0
        n = len(tokens)

        def peek():
            if idx < n:
                return tokens[idx]

            return Token(
                TokenType.EOF,
                None,
                0,
                0,
            )

        def advance():
            nonlocal idx

            token = peek()

            if idx < n:
                idx += 1

            return token

        def parse_value():
            token = peek()

            if token.type == TokenType.LEFT_BRACE:
                return parse_object()

            if token.type == TokenType.LEFT_BRACKET:
                return parse_array()

            if token.type == TokenType.STRING:
                advance()
                return token.value

            if token.type == TokenType.NUMBER:

                advance()

                raw = token.value

                # Strict JSON number grammar.
                import re

                valid_number = re.fullmatch(
                    r"-?(?:0|[1-9]\d*)"
                    r"(?:\.\d+)?"
                    r"(?:[eE][+-]?\d+)?",
                    raw,
                )

                if not valid_number:
                    report.add_issue(
                        Issue(
                            token.line,
                            token.col,
                            "malformed_number",
                            Severity.ERROR,
                            f"Invalid number literal: {raw}",
                        )
                    )
                    return 0

                try:
                    if (
                        "." not in raw
                        and "e" not in raw.lower()
                    ):
                        return int(raw)

                    return float(raw)

                except ValueError:
                    report.add_issue(
                        Issue(
                            token.line,
                            token.col,
                            "malformed_number",
                            Severity.ERROR,
                            f"Invalid number literal: {raw}",
                        )
                    )
                    return 0

            if token.type == TokenType.TRUE:
                advance()
                return True

            if token.type == TokenType.FALSE:
                advance()
                return False

            if token.type == TokenType.NULL:
                advance()
                return None

            report.add_issue(
                Issue(
                    token.line,
                    token.col,
                    "unexpected_token",
                    Severity.ERROR,
                    (
                        "Expected value structure, "
                        f"got '{token.value}'"
                    ),
                )
            )

            # Consume unexpected token to prevent parser loops.
            if token.type != TokenType.EOF:
                advance()

            return None

        def parse_object():

            start_token = advance()
            obj = {}

            if peek().type == TokenType.RIGHT_BRACE:
                advance()
                return obj

            while True:

                token = peek()

                if token.type == TokenType.EOF:

                    report.add_issue(
                        Issue(
                            start_token.line,
                            start_token.col,
                            "unterminated_object",
                            Severity.ERROR,
                            "Object missing terminal right brace '}'",
                        )
                    )

                    break

                if token.type == TokenType.RIGHT_BRACE:
                    advance()
                    break

                if token.type != TokenType.STRING:

                    report.add_issue(
                        Issue(
                            token.line,
                            token.col,
                            "missing_object_key",
                            Severity.ERROR,
                            (
                                "Expected string dictionary key, "
                                f"got '{token.value}'"
                            ),
                        )
                    )

                    # Recovery: skip until a useful boundary.
                    if token.type not in (
                        TokenType.COMMA,
                        TokenType.RIGHT_BRACE,
                    ):
                        advance()
                        continue

                if token.type == TokenType.STRING:
                    key = advance().value
                else:
                    key = f"implicit_key_{idx}"

                colon = peek()

                if colon.type == TokenType.COLON:
                    advance()
                else:

                    report.add_issue(
                        Issue(
                            colon.line,
                            colon.col,
                            "missing_colon",
                            Severity.ERROR,
                            "Expected structural colon divider (:)",
                        )
                    )

                value = parse_value()
                obj[str(key)] = value

                next_token = peek()

                if next_token.type == TokenType.COMMA:

                    comma_token = advance()

                    if peek().type == TokenType.RIGHT_BRACE:

                        report.add_issue(
                            Issue(
                                comma_token.line,
                                comma_token.col,
                                "trailing_comma",
                                Severity.WARNING,
                                "Trailing comma detected inside map object",
                            )
                        )

                        advance()
                        break

                    continue

                if next_token.type == TokenType.RIGHT_BRACE:
                    advance()
                    break

                if next_token.type == TokenType.EOF:

                    report.add_issue(
                        Issue(
                            start_token.line,
                            start_token.col,
                            "unterminated_object",
                            Severity.ERROR,
                            "Object missing terminal right brace '}'",
                        )
                    )

                    break

                report.add_issue(
                    Issue(
                        next_token.line,
                        next_token.col,
                        "missing_comma",
                        Severity.ERROR,
                        "Expected structural comma separation divider",
                    )
                )

                # Recovery:
                # continue parsing if another key starts.
                if next_token.type == TokenType.STRING:
                    continue

                if next_token.type != TokenType.EOF:
                    advance()

            return obj

        def parse_array():

            start_token = advance()
            arr = []

            if peek().type == TokenType.RIGHT_BRACKET:
                advance()
                return arr

            while True:

                if peek().type == TokenType.EOF:

                    report.add_issue(
                        Issue(
                            start_token.line,
                            start_token.col,
                            "unterminated_array",
                            Severity.ERROR,
                            "Array missing terminal right bracket ']'",
                        )
                    )

                    break

                if peek().type == TokenType.RIGHT_BRACKET:
                    advance()
                    break

                arr.append(parse_value())

                next_token = peek()

                if next_token.type == TokenType.COMMA:

                    comma_token = advance()

                    if peek().type == TokenType.RIGHT_BRACKET:

                        report.add_issue(
                            Issue(
                                comma_token.line,
                                comma_token.col,
                                "trailing_comma",
                                Severity.WARNING,
                                "Trailing comma detected inside array list",
                            )
                        )

                        advance()
                        break

                    continue

                if next_token.type == TokenType.RIGHT_BRACKET:
                    advance()
                    break

                if next_token.type == TokenType.EOF:

                    report.add_issue(
                        Issue(
                            start_token.line,
                            start_token.col,
                            "unterminated_array",
                            Severity.ERROR,
                            "Array missing terminal right bracket ']'",
                        )
                    )

                    break

                report.add_issue(
                    Issue(
                        next_token.line,
                        next_token.col,
                        "missing_comma",
                        Severity.ERROR,
                        "Expected comma separation between array values",
                    )
                )

                if next_token.type != TokenType.EOF:
                    advance()

            return arr

        result = parse_value()

        # Anything after the root value is suspicious.
        if peek().type != TokenType.EOF:

            token = peek()

            report.add_issue(
                Issue(
                    token.line,
                    token.col,
                    "trailing_garbage",
                    Severity.WARNING,
                    (
                        "Extra data elements found after "
                        "root JSON node parsing finished"
                    ),
                )
            )

        return result

    # --------------------------------------------------------
    # PARSE
    # --------------------------------------------------------

    def parse(self, path: str):

        report = Report(source=path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        except Exception as e:

            report.add_issue(
                Issue(
                    0,
                    0,
                    "file_read_error",
                    Severity.ERROR,
                    str(e),
                )
            )

            return None, report

        tokens = self._tokenize(
            content,
            report,
        )

        data = self._parse_tokens(
            tokens,
            report,
        )

        return data, report

    # --------------------------------------------------------
    # REPAIR
    # --------------------------------------------------------

    def repair(self, path: str, output_path: str):

        report = Report(source=path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        except Exception as e:

            report.add_issue(
                Issue(
                    0,
                    0,
                    "file_read_error",
                    Severity.ERROR,
                    str(e),
                )
            )

            return report

        # Tokenize first. This detects JSONC comments,
        # trailing commas and lexical problems.
        tokens = self._tokenize(
            content,
            report,
        )

        # Parse into a clean Python structure.
        data = self._parse_tokens(
            tokens,
            report,
        )

        # Record repairs that the parser can safely normalize.
        comment_lines = set()
        remaining_issues = []

        for issue in report.issues:

            if issue.kind == "jsonc_comment":
                comment_lines.add(issue.line)

                report.add_correction(
                    Correction(
                        issue.line,
                        "strip_comment",
                        (
                            "Removed JSONC comment segment "
                            "from output serialization stream"
                        ),
                    )
                )

                remaining_issues.append(issue)

            elif issue.kind == "trailing_comma":

                report.add_correction(
                    Correction(
                        issue.line,
                        "remove_trailing_comma",
                        (
                            "Stripped out structural "
                            "trailing comma syntax"
                        ),
                    )
                )

                remaining_issues.append(issue)

            elif issue.kind == "unterminated_string":

                # The tokenizer always recovers a usable value here (the
                # text up to the line break becomes the string's content),
                # so this is a repair, not a remaining error.
                report.add_correction(
                    Correction(
                        issue.line,
                        "closed_unterminated_string",
                        (
                            "Closed a string literal that was missing "
                            "its closing quote, using the text up to "
                            "the line break as its content"
                        ),
                    )
                )

            else:
                remaining_issues.append(issue)

        report.issues = remaining_issues

        # Calculate actual nesting balance from tokens.
        brace_depth = 0
        bracket_depth = 0

        for token in tokens:

            if token.type == TokenType.LEFT_BRACE:
                brace_depth += 1

            elif token.type == TokenType.RIGHT_BRACE:
                brace_depth = max(
                    0,
                    brace_depth - 1,
                )

            elif token.type == TokenType.LEFT_BRACKET:
                bracket_depth += 1

            elif token.type == TokenType.RIGHT_BRACKET:
                bracket_depth = max(
                    0,
                    bracket_depth - 1,
                )

        if brace_depth > 0:

            report.add_correction(
                Correction(
                    0,
                    "balanced_unclosed_braces",
                    (
                        f"Appended {brace_depth} missing "
                        "closing object braces ('}')"
                    ),
                )
            )

            # The correction above is exactly what resolves any
            # "unterminated_object" errors the parser raised, so they're
            # no longer unresolved problems.
            report.issues = [
                issue
                for issue in report.issues
                if issue.kind != "unterminated_object"
            ]

        if bracket_depth > 0:

            report.add_correction(
                Correction(
                    0,
                    "balanced_unclosed_brackets",
                    (
                        f"Appended {bracket_depth} missing "
                        "closing array brackets (']')"
                    ),
                )
            )

            # Same reasoning for arrays.
            report.issues = [
                issue
                for issue in report.issues
                if issue.kind != "unterminated_array"
            ]

        # Write normalized strict JSON.
        self.serialize(
            data,
            output_path,
        )

        # If the source had serious unrecoverable lexical problems,
        # keep those issues visible in the report rather than hiding them.
        return report

    # --------------------------------------------------------
    # SERIALIZE
    # --------------------------------------------------------

    def serialize(self, data, output_path: str):

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as f:

            std_json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False,
            )

            f.write("\n")


# ============================================================
# PLACEHOLDER ENGINE
# ============================================================

class NotImplementedEngine(Engine):

    name = "not_implemented"

    def parse(self, path: str):

        report = Report(source=path)

        print(
            f"[{self.name}] parse: "
            f"not implemented yet for {path}"
        )

        return None, report

    def repair(self, path: str, output_path: str):

        report = Report(source=path)

        print(
            f"[{self.name}] repair: "
            f"not implemented yet for {path}"
        )

        return report

    def serialize(self, data, output_path: str):

        print(
            f"[{self.name}] serialize: "
            f"not implemented yet for {output_path}"
        )


# ============================================================
# EXTENSION ROUTING
# ============================================================

EXTENSION_MAP = {
    ".csv": CSVEngine(),
    ".json": JSONEngine(),
    ".jsonc": JSONEngine(),
}


def get_engine(path: str) -> Engine:
    """
    Select the correct engine using the file extension.
    """

    normalized_path = os.fspath(path).lower()

    for extension, engine in EXTENSION_MAP.items():

        if normalized_path.endswith(extension):
            return engine

    raise ValueError(
        f"No engine registered for '{path}'. "
        f"Supported extensions: "
        f"{', '.join(EXTENSION_MAP)}"
    )