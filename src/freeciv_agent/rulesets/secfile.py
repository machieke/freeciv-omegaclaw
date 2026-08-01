"""Strict parser for the FreeCiv secfile subset used by game rulesets."""

import ast
import csv
import re
from dataclasses import dataclass, field


class SecfileError(ValueError):
    def __init__(self, path, line, message):
        self.path = path
        self.line = int(line)
        self.message = message
        super().__init__("{}:{}: {}".format(path, line, message))


@dataclass(frozen=True)
class SourceLocation:
    path: str
    line: int
    section: str
    field: str = ""

    def to_dict(self):
        return {"file": self.path, "line": self.line, "section": self.section,
                "field": self.field}


@dataclass(frozen=True)
class TableRow:
    values: tuple
    line: int


@dataclass(frozen=True)
class SecTable:
    columns: tuple
    rows: tuple

    def dictionaries(self):
        return [dict(zip(self.columns, row.values)) for row in self.rows]


@dataclass(frozen=True)
class SecField:
    name: str
    value: object
    raw: str
    location: SourceLocation


@dataclass
class SecSection:
    name: str
    line: int
    fields: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Secfile:
    path: str
    sections: tuple

    def matching(self, prefix):
        return [section for section in self.sections if section.name.startswith(prefix)]


_SECTION = re.compile(r"^\[([^\]]+)\]\s*$")
_ASSIGNMENT = re.compile(r"^([-A-Za-z0-9_.]+)\s*=\s*(.*)$")


def _without_comment(text):
    quote = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quote = not quote
        elif char in (";", "#") and not quote:
            return text[:index]
    return text


def _balanced(text):
    quote = False
    escaped = False
    parens = 0
    for char in text:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quote = not quote
        elif not quote and char == "(":
            parens += 1
        elif not quote and char == ")":
            parens -= 1
            if parens < 0:
                return False
    return not quote and parens == 0


def _value_complete(text):
    return _balanced(text) and not text.rstrip().endswith(",")


def _split_top_level(text):
    result = []
    start = 0
    quote = False
    escaped = False
    depth = 0
    for index, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quote = not quote
        elif not quote and char == "(":
            depth += 1
        elif not quote and char == ")":
            depth -= 1
        elif not quote and depth == 0 and char == ",":
            result.append(text[start:index].strip())
            start = index + 1
    result.append(text[start:].strip())
    return result


def _decode_scalar(token):
    token = token.strip()
    if token.startswith("_(") and token.endswith(")"):
        return _decode_value(token[2:-1])
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        try:
            return ast.literal_eval(token)
        except (SyntaxError, ValueError):
            # FreeCiv continuation escapes are a line-joining mechanism rather than
            # Python syntax. Their display text is not compiler-semantic.
            return token[1:-1].replace("\\\n", "")
    upper = token.upper()
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    if re.match(r"^[+-]?\d+$", token):
        return int(token)
    if re.match(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)$", token):
        return float(token)
    return token


def _decode_value(text):
    pieces = _split_top_level(text)
    decoded = [_decode_scalar(piece) for piece in pieces]
    return decoded[0] if len(decoded) == 1 else decoded


def _table_cells(text, path, line):
    try:
        return tuple(_decode_scalar(value) for value in
                     next(csv.reader([text], skipinitialspace=True)))
    except (csv.Error, StopIteration) as exc:
        raise SecfileError(path, line, "invalid table row: {}".format(exc))


def _consume_table(lines, probe, path, start_line, name, initial=None):
    table_lines = []
    closed = False
    if initial is not None:
        part = initial[1:].strip()
        if part.endswith("}"):
            part = part[:-1].strip()
            closed = True
        if part:
            table_lines.append((start_line, part))
    while not closed and probe < len(lines):
        part = _without_comment(lines[probe]).strip()
        row_line = probe + 1
        probe += 1
        if not part:
            continue
        if part.startswith("{"):
            part = part[1:].strip()
        if part == "}":
            closed = True
            break
        if part.endswith("}"):
            part = part[:-1].strip()
            closed = True
        if part:
            table_lines.append((row_line, part))
    if not closed:
        raise SecfileError(
            path, start_line, "unterminated table {}".format(name))
    if not table_lines:
        raise SecfileError(
            path, start_line, "table {} has no header".format(name))
    header_line, header = table_lines[0]
    columns = _table_cells(header, path, header_line)
    if not all(isinstance(column, str) and column for column in columns):
        raise SecfileError(path, header_line, "invalid table header")
    rows = []
    for row_line, row_text in table_lines[1:]:
        values = _table_cells(row_text, path, row_line)
        if len(values) > len(columns):
            raise SecfileError(
                path, row_line,
                "table {} has {} columns, got {}".format(
                    name, len(columns), len(values)))
        values = values + (None,) * (len(columns) - len(values))
        rows.append(TableRow(values, row_line))
    return (
        SecTable(columns, tuple(rows)),
        "\n".join(part for _, part in table_lines),
        probe,
    )


def parse(path):
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    sections = []
    current = None
    index = 0
    while index < len(lines):
        line_number = index + 1
        cleaned = _without_comment(lines[index]).strip()
        if not cleaned:
            index += 1
            continue
        section_match = _SECTION.match(cleaned)
        if section_match:
            current = SecSection(section_match.group(1), line_number)
            sections.append(current)
            index += 1
            continue
        if cleaned.startswith("*include "):
            # Include resolution belongs to the compiler so its source hashes
            # and coverage report can expose uncompiled external semantics.
            index += 1
            continue
        if current is None:
            raise SecfileError(path, line_number, "content before first section")
        assignment = _ASSIGNMENT.match(cleaned)
        if not assignment:
            raise SecfileError(path, line_number, "expected field assignment")
        name, rhs = assignment.groups()
        if name in current.fields:
            raise SecfileError(path, line_number, "duplicate field {}".format(name))
        start_line = line_number
        if rhs.startswith("{"):
            value, raw, index = _consume_table(
                lines, index + 1, path, start_line, name, rhs)
        elif not rhs:
            probe = index + 1
            while probe < len(lines) and not _without_comment(lines[probe]).strip():
                probe += 1
            if probe < len(lines) and _without_comment(lines[probe]).strip().startswith("{"):
                value, raw, index = _consume_table(
                    lines, probe, path, start_line, name)
            elif (probe < len(lines)
                  and not _SECTION.match(_without_comment(lines[probe]).strip())
                  and not _ASSIGNMENT.match(_without_comment(lines[probe]).strip())):
                parts = []
                while probe < len(lines):
                    part = _without_comment(lines[probe]).strip()
                    probe += 1
                    if not part:
                        continue
                    parts.append(part)
                    if _value_complete("\n".join(parts)):
                        break
                if not parts or not _value_complete("\n".join(parts)):
                    raise SecfileError(path, start_line,
                                       "unterminated value for {}".format(name))
                raw = "\n".join(parts)
                value = _decode_value(raw)
                index = probe
            else:
                value = ""
                raw = ""
                index += 1
        else:
            parts = [rhs]
            probe = index + 1
            while not _value_complete("\n".join(parts)):
                if probe >= len(lines):
                    raise SecfileError(path, start_line, "unterminated value for {}".format(name))
                parts.append(_without_comment(lines[probe]).strip())
                probe += 1
            raw = "\n".join(parts)
            value = _decode_value(raw)
            index = probe
        location = SourceLocation(path, start_line, current.name, name)
        current.fields[name] = SecField(name, value, raw, location)
    return Secfile(path, tuple(sections))
