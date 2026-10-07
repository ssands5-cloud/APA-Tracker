"""A deliberately small evaluator for the exact Excel formula subset the
Ultimate Coach workbook uses, so tests can compute Match Day / Match Night
results end to end without Excel, COM, pywin32 or macros.

It models the Excel behaviours that matter for correctness here:
- a reference (or INDEX result) landing on a BLANK cell is blank: it
  compares equal to "" and concatenates as "", but a cell whose whole
  formula evaluates to a bare blank displays 0 -- the bug class behind the
  old Match Day B19/B26/B31 cells;
- errors (#N/A from a failed MATCH, #REF!, #VALUE!) propagate until IFERROR;
- text comparison is case-insensitive.

Anything outside the supported subset raises NotImplementedError, so a new
formula shape can never silently "pass" here.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries

BLANK = None


class ExcelError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<string>"(?:[^"]|"")*")
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<sheetcell>(?:'[^']+'|[A-Za-z_][A-Za-z0-9_]*)!\$?[A-Z]{1,3}\$?\d+)
  | (?P<structured>[A-Za-z_][A-Za-z0-9_]*\[[^\]]+\])
  | (?P<range>\$?[A-Z]{1,3}\$?\d+:\$?[A-Z]{1,3}\$?\d+)
  | (?P<cell>\$?[A-Z]{1,3}\$?\d+(?![A-Za-z0-9_(]))
  | (?P<func>[A-Z][A-Z0-9.]*(?=\())
  | (?P<bool>TRUE|FALSE)
  | (?P<op><>|<=|>=|[=<>&+\-*/(),])
""", re.VERBOSE)


def _tokenize(text: str) -> list[tuple[str, str]]:
    pos, out = 0, []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise NotImplementedError(f"cannot tokenize {text[pos:pos + 30]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind != "ws":
            out.append((kind, m.group()))
    return out


def _excel_serial_to_date(serial: float) -> date:
    return date(1899, 12, 30) + timedelta(days=int(serial))


class Workbook:
    """Wrap an openpyxl workbook (loaded WITHOUT data_only) for evaluation."""

    def __init__(self, wb):
        self.wb = wb
        self.inputs: dict[tuple[str, str], Any] = {}
        self.cache: dict[tuple[str, str], Any] = {}
        self.tables: dict[str, tuple[Any, dict[str, list[str]]]] = {}
        for ws in wb.worksheets:
            for name, ref in ws.tables.items():
                min_col, min_row, max_col, max_row = range_boundaries(ref)
                columns = {}
                for col in range(min_col, max_col + 1):
                    header = ws.cell(row=min_row, column=col).value
                    letter = get_column_letter(col)
                    columns[header] = [f"{letter}{r}" for r in range(min_row + 1, max_row + 1)]
                self.tables[name] = (ws, columns)

    def set(self, sheet: str, ref: str, value: Any) -> None:
        self.inputs[(sheet, ref.replace("$", ""))] = value
        self.cache.clear()

    # -- cell values --
    def raw(self, sheet: str, ref: str) -> Any:
        key = (sheet, ref.replace("$", ""))
        if key in self.inputs:
            return self.inputs[key]
        value = self.wb[sheet][key[1]].value
        if isinstance(value, datetime):
            return float((value.date() - date(1899, 12, 30)).days)
        if isinstance(value, date):
            return float((value - date(1899, 12, 30)).days)
        if value == "":
            return BLANK
        return value

    def value(self, sheet: str, ref: str) -> Any:
        """Evaluated value of a cell, as a formula elsewhere would see it."""
        key = (sheet, ref.replace("$", ""))
        if key in self.cache:
            result = self.cache[key]
        else:
            raw = self.raw(sheet, ref)
            if isinstance(raw, str) and raw.startswith("="):
                try:
                    result = _Parser(self, sheet, raw[1:]).parse()
                except ExcelError as exc:
                    result = exc
                if isinstance(result, list):
                    raise NotImplementedError("formula returned a range")
            else:
                result = raw
            self.cache[key] = result
        if isinstance(result, ExcelError):
            raise result
        return result

    def display(self, sheet: str, ref: str) -> Any:
        """What Excel shows in the cell: a whole-formula blank displays 0."""
        try:
            value = self.value(sheet, ref)
        except ExcelError as exc:
            return exc.code
        raw = self.raw(sheet, ref)
        if value is BLANK and isinstance(raw, str) and raw.startswith("="):
            return 0
        return value


def _is_blank(v: Any) -> bool:
    return v is BLANK


def _to_text(v: Any) -> str:
    if v is BLANK:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _to_number(v: Any) -> float:
    if v is BLANK:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ExcelError("#VALUE!")


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is BLANK:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    raise ExcelError("#VALUE!")


def _compare(a: Any, b: Any, op: str) -> bool:
    if a is BLANK and isinstance(b, str):
        a = ""
    if b is BLANK and isinstance(a, str):
        b = ""
    if a is BLANK:
        a = 0.0 if not isinstance(b, bool) else False
    if b is BLANK:
        b = 0.0 if not isinstance(a, bool) else False
    num = (int, float)
    if isinstance(a, str) and isinstance(b, str):
        a, b = a.lower(), b.lower()
    elif isinstance(a, num) and isinstance(b, num) and not isinstance(a, bool) and not isinstance(b, bool):
        a, b = float(a), float(b)
    elif type(a) is not type(b):
        # Excel orders numbers < text < booleans; equality across types is false.
        rank = lambda v: 0 if isinstance(v, num) and not isinstance(v, bool) else (1 if isinstance(v, str) else 2)
        a, b = rank(a), rank(b)
    return {"=": a == b, "<>": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]


class _Parser:
    def __init__(self, book: Workbook, sheet: str, text: str):
        self.book, self.sheet = book, sheet
        self.tokens = _tokenize(text)
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self, expected: str | None = None):
        tok = self.peek()
        if expected is not None and tok[1] != expected:
            raise NotImplementedError(f"expected {expected!r}, got {tok!r}")
        self.i += 1
        return tok

    def parse(self):
        result = self.comparison()
        if self.i != len(self.tokens):
            raise NotImplementedError(f"trailing tokens {self.tokens[self.i:]}")
        return result

    # Lazy evaluation: each grammar level returns a thunk-free value, but IF /
    # IFERROR / AND / OR take raw token spans so untaken branches never error.
    def comparison(self):
        left = self.concat()
        while self.peek()[1] in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take()[1]
            right = self.concat()
            left = _compare(self.scalar(left), self.scalar(right), op)
        return left

    def concat(self):
        left = self.additive()
        while self.peek()[1] == "&":
            self.take()
            right = self.additive()
            left = _to_text(self.scalar(left)) + _to_text(self.scalar(right))
        return left

    def additive(self):
        left = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            right = self.term()
            a, b = _to_number(self.scalar(left)), _to_number(self.scalar(right))
            left = a + b if op == "+" else a - b
        return left

    def term(self):
        left = self.unary()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            right = self.unary()
            a, b = _to_number(self.scalar(left)), _to_number(self.scalar(right))
            if op == "/" and b == 0:
                raise ExcelError("#DIV/0!")
            left = a * b if op == "*" else a / b
        return left

    def unary(self):
        if self.peek()[1] == "-":
            self.take()
            return -_to_number(self.scalar(self.unary()))
        return self.primary()

    def scalar(self, v):
        if isinstance(v, list):
            raise ExcelError("#VALUE!")
        return v

    def primary(self):
        kind, text = self.take()
        if kind == "number":
            return float(text)
        if kind == "string":
            return text[1:-1].replace('""', '"')
        if kind == "bool":
            return text == "TRUE"
        if kind == "cell":
            return self.book.value(self.sheet, text)
        if kind == "sheetcell":
            sheet_name, ref = text.rsplit("!", 1)
            return self.book.value(sheet_name.strip("'"), ref)
        if kind == "range":
            return self.range_cells(text)
        if kind == "structured":
            name, column = text[:-1].split("[", 1)
            ws, columns = self.book.tables[name]
            if column not in columns:
                raise ExcelError("#REF!")
            return [(ws.title, ref) for ref in columns[column]]
        if kind == "func":
            return self.function(text)
        if text == "(":
            value = self.comparison()
            self.take(")")
            return value
        raise NotImplementedError(f"unexpected token {text!r}")

    def range_cells(self, text: str):
        min_col, min_row, max_col, max_row = range_boundaries(text.replace("$", ""))
        if min_col != max_col:
            raise NotImplementedError("only single-column ranges are supported")
        letter = get_column_letter(min_col)
        return [(self.sheet, f"{letter}{r}") for r in range(min_row, max_row + 1)]

    def skip_arg(self):
        depth = 0
        while True:
            kind, text = self.peek()
            if text is None:
                raise NotImplementedError("unbalanced")
            if depth == 0 and text in (",", ")"):
                return
            if text == "(":
                depth += 1
            elif text == ")":
                depth -= 1
            self.i += 1

    def arg_value(self):
        try:
            return self.comparison()
        except ExcelError as exc:
            self.skip_arg()
            return exc

    def function(self, name: str):
        self.take("(")
        if name == "IF":
            cond = self.arg_value()
            if isinstance(cond, ExcelError):
                raise cond
            truthy = _to_bool(self.scalar(cond))
            self.take(",")
            if truthy:
                result = self.arg_value()
                if self.peek()[1] == ",":
                    self.take(",")
                    self.skip_arg()
            else:
                self.skip_arg()
                result = False
                if self.peek()[1] == ",":
                    self.take(",")
                    result = self.arg_value()
            self.take(")")
            if isinstance(result, ExcelError):
                raise result
            return result
        if name == "IFERROR":
            first = self.arg_value()
            self.take(",")
            if isinstance(first, ExcelError):
                result = self.arg_value()
            else:
                self.skip_arg()
                result = first
            self.take(")")
            if isinstance(result, ExcelError):
                raise result
            return result
        args = []
        while self.peek()[1] != ")":
            args.append(self.arg_value())
            if self.peek()[1] == ",":
                self.take(",")
        self.take(")")
        for a in args:
            if isinstance(a, ExcelError):
                raise a
        return self.call(name, args)

    def cells(self, ref_list):
        return [self.book.value(s, r) for s, r in ref_list]

    def call(self, name: str, args: list[Any]):
        if name in ("OR", "AND"):
            values = [_to_bool(self.scalar(a)) for a in args]
            return any(values) if name == "OR" else all(values)
        if name == "INDEX":
            refs, n = args[0], int(_to_number(self.scalar(args[1])))
            if not isinstance(refs, list) or n < 1 or n > len(refs):
                raise ExcelError("#REF!")
            sheet, ref = refs[n - 1]
            return self.book.value(sheet, ref)
        if name == "MATCH":
            needle, refs = self.scalar(args[0]), args[1]
            if len(args) < 3 or _to_number(args[2]) != 0:
                raise NotImplementedError("only exact MATCH(...,0) is supported")
            for i, v in enumerate(self.cells(refs), start=1):
                if v is not BLANK and _compare(v, needle, "="):
                    return float(i)
            raise ExcelError("#N/A")
        if name == "COUNTIF":
            refs, criterion = args[0], self.scalar(args[1])
            return float(sum(1 for v in self.cells(refs) if v is not BLANK and _compare(v, criterion, "=")))
        if name == "COUNTIFS":
            raise NotImplementedError("COUNTIFS")
        if name == "ISNUMBER":
            v = self.scalar(args[0])
            return isinstance(v, (int, float)) and not isinstance(v, bool)
        if name == "INT":
            import math
            return float(math.floor(_to_number(self.scalar(args[0]))))
        if name == "MIN":
            return min(_to_number(self.scalar(a)) for a in args)
        if name == "TRIM":
            return " ".join(_to_text(self.scalar(args[0])).split())
        if name == "TEXT":
            value, fmt = self.scalar(args[0]), self.scalar(args[1])
            if fmt == "0":
                return str(int(round(_to_number(value))))
            if fmt == "dddd, mmm d, yyyy":
                d = _excel_serial_to_date(_to_number(value))
                return f"{d.strftime('%A')}, {d.strftime('%b')} {d.day}, {d.year}"
            if fmt == "0.0%":
                return f"{_to_number(value) * 100:.1f}%"
            raise NotImplementedError(f"TEXT format {fmt!r}")
        if name == "DATEVALUE":
            text = _to_text(self.scalar(args[0])).strip()
            for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
                try:
                    return float((datetime.strptime(text, pattern).date() - date(1899, 12, 30)).days)
                except ValueError:
                    continue
            raise ExcelError("#VALUE!")
        raise NotImplementedError(f"function {name}")


def serial(d: date) -> float:
    return float((d - date(1899, 12, 30)).days)


__all__ = ["Workbook", "ExcelError", "serial", "column_index_from_string"]
