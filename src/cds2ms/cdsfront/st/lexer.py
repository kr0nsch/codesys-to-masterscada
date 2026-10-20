"""Лексер ST CODESYS 3.5 без потерь.

Каждый символ входа попадает ровно в один токен, поэтому ``"".join(t.text for t in tokens) == source``.
Пробелы, комментарии ``(* *)`` (с вложением), ``/* */``, ``//`` и прагмы ``{…}`` — «тривиа»: разборщик их
пропускает, печать и правки по границам токенов их сохраняют.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    WS = "ws"
    COMMENT = "comment"
    PRAGMA = "pragma"
    IDENT = "ident"
    INT = "int"
    REAL = "real"
    TYPED = "typed"  # T#1s, INT#5, DT#..., E_State#Run
    STRING = "string"
    WSTRING = "wstring"
    OP = "op"
    ADDR = "addr"  # %IX0.0, %QW10, %MD3
    ERROR = "error"
    EOF = "eof"


TRIVIA = frozenset({Kind.WS, Kind.COMMENT, Kind.PRAGMA})

_TWO_CHAR = (":=", "=>", "<=", ">=", "<>", "**", "..")
_ONE_CHAR = "+-*/()[],;:.^=<>&#"

_TIME_PREFIX = frozenset({"T", "TIME", "LT", "LTIME"})
_DATE_PREFIX = frozenset({"D", "DATE", "LD", "LDATE"})
_TOD_PREFIX = frozenset({"TOD", "TIME_OF_DAY", "LTOD", "LTIME_OF_DAY"})
_DT_PREFIX = frozenset({"DT", "DATE_AND_TIME", "LDT", "LDATE_AND_TIME"})


@dataclass(frozen=True, slots=True)
class Token:
    kind: Kind
    text: str
    offset: int  # смещение в символах от начала текста
    line: int  # с 1
    col: int  # с 1

    @property
    def upper(self) -> str:
        return self.text.upper()

    @property
    def end(self) -> int:
        return self.offset + len(self.text)

    def is_op(self, *ops: str) -> bool:
        return self.kind is Kind.OP and self.text in ops

    def is_kw(self, *words: str) -> bool:
        return self.kind is Kind.IDENT and self.text.upper() in words


def _is_ident_start(c: str) -> bool:
    return c == "_" or c.isalpha()


def _is_ident_char(c: str) -> bool:
    return c == "_" or c.isalnum()


class _Scanner:
    def __init__(self, text: str) -> None:
        self.s = text
        self.n = len(text)
        self.i = 0
        self.line = 1
        self.col = 1
        self.out: list[Token] = []

    def emit(self, kind: Kind, start: int, line: int, col: int) -> None:
        text = self.s[start : self.i]
        self.out.append(Token(kind, text, start, line, col))

    def advance_to(self, j: int) -> None:
        seg = self.s[self.i : j]
        nl = seg.count("\n")
        if nl:
            self.line += nl
            self.col = len(seg) - seg.rfind("\n")
        else:
            self.col += len(seg)
        self.i = j

    def peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.s[j] if j < self.n else ""

    def run(self) -> list[Token]:
        s = self.s
        while self.i < self.n:
            start, line, col = self.i, self.line, self.col
            c = s[self.i]
            if c.isspace():
                j = self.i
                while j < self.n and s[j].isspace():
                    j += 1
                self.advance_to(j)
                self.emit(Kind.WS, start, line, col)
            elif c == "(" and self.peek(1) == "*":
                self.advance_to(self._block_comment(self.i))
                self.emit(Kind.COMMENT, start, line, col)
            elif c == "/" and self.peek(1) == "*":
                j = s.find("*/", self.i + 2)
                self.advance_to(self.n if j < 0 else j + 2)
                self.emit(Kind.COMMENT, start, line, col)
            elif c == "/" and self.peek(1) == "/":
                j = s.find("\n", self.i)
                self.advance_to(self.n if j < 0 else j)
                self.emit(Kind.COMMENT, start, line, col)
            elif c == "{":
                j = s.find("}", self.i)
                self.advance_to(self.n if j < 0 else j + 1)
                self.emit(Kind.PRAGMA, start, line, col)
            elif c == "'" or c == '"':
                self.advance_to(self._string_end(self.i, c))
                self.emit(Kind.STRING if c == "'" else Kind.WSTRING, start, line, col)
            elif c == "%" and self.peek(1).upper() in ("I", "Q", "M"):
                j = self.i + 2
                while j < self.n and (s[j].isalnum() or s[j] in "._*"):
                    j += 1
                self.advance_to(j)
                self.emit(Kind.ADDR, start, line, col)
            elif c.isdigit():
                kind, j = self._number(self.i)
                self.advance_to(j)
                self.emit(kind, start, line, col)
            elif _is_ident_start(c):
                j = self.i
                while j < self.n and _is_ident_char(s[j]):
                    j += 1
                word = s[self.i : j]
                if j < self.n and s[j] == "#":
                    j = self._typed_value(word.upper(), j + 1)
                    self.advance_to(j)
                    self.emit(Kind.TYPED, start, line, col)
                else:
                    self.advance_to(j)
                    self.emit(Kind.IDENT, start, line, col)
            else:
                two = s[self.i : self.i + 2]
                if two in _TWO_CHAR:
                    self.advance_to(self.i + 2)
                    self.emit(Kind.OP, start, line, col)
                elif c in _ONE_CHAR:
                    self.advance_to(self.i + 1)
                    self.emit(Kind.OP, start, line, col)
                else:
                    self.advance_to(self.i + 1)
                    self.emit(Kind.ERROR, start, line, col)
        self.out.append(Token(Kind.EOF, "", self.n, self.line, self.col))
        return self.out

    def _block_comment(self, i: int) -> int:
        """Конец комментария (* … *) с учётом вложения (CODESYS допускает вложенные комментарии)."""
        s, depth, j = self.s, 0, i
        while j < self.n:
            if s.startswith("(*", j):
                depth += 1
                j += 2
            elif s.startswith("*)", j):
                depth -= 1
                j += 2
                if depth == 0:
                    return j
            else:
                j += 1
        return self.n

    def _string_end(self, i: int, quote: str) -> int:
        s, j = self.s, i + 1
        while j < self.n:
            if s[j] == "$":
                j += 2
                continue
            if s[j] == quote:
                return j + 1
            if s[j] == "\n":
                return j
            j += 1
        return self.n

    def _number(self, i: int) -> tuple[Kind, int]:
        s, j = self.s, i
        while j < self.n and (s[j].isdigit() or s[j] == "_"):
            j += 1
        if j < self.n and s[j] == "#":  # 16#FF, 2#1010
            j += 1
            while j < self.n and (s[j].isalnum() or s[j] == "_"):
                j += 1
            return Kind.INT, j
        kind = Kind.INT
        if j + 1 < self.n and s[j] == "." and s[j + 1].isdigit():
            kind = Kind.REAL
            j += 1
            while j < self.n and (s[j].isdigit() or s[j] == "_"):
                j += 1
        if j < self.n and s[j] in "eE":
            k = j + 1
            if k < self.n and s[k] in "+-":
                k += 1
            if k < self.n and s[k].isdigit():
                kind = Kind.REAL
                j = k
                while j < self.n and s[j].isdigit():
                    j += 1
        return kind, j

    def _typed_value(self, prefix: str, j: int) -> int:
        s = self.s
        if prefix in _TIME_PREFIX:
            if j < self.n and s[j] in "+-":
                j += 1
            while j < self.n and (s[j].isalnum() or s[j] in "_."):
                j += 1
            return j
        if prefix in _DATE_PREFIX:
            while j < self.n and (s[j].isdigit() or s[j] in "-_"):
                j += 1
            return j
        if prefix in _TOD_PREFIX:
            while j < self.n and (s[j].isdigit() or s[j] in ":._"):
                j += 1
            return j
        if prefix in _DT_PREFIX:
            while j < self.n and (s[j].isdigit() or s[j] in ":.-_"):
                j += 1
            return j
        if j < self.n and s[j] in "'\"":
            return self._string_end(j, s[j])
        if j < self.n and s[j] in "+-":
            j += 1
        while j < self.n and (s[j].isalnum() or s[j] == "_"):
            j += 1
        if j < self.n and s[j] == "#":
            j += 1
            while j < self.n and (s[j].isalnum() or s[j] == "_"):
                j += 1
        elif j + 1 < self.n and s[j] == "." and s[j + 1].isdigit():
            j += 1
            while j < self.n and (s[j].isalnum() or s[j] in "_"):
                j += 1
        return j


def tokenize(text: str) -> list[Token]:
    """Токены без потерь; последний — EOF с пустым текстом."""
    return _Scanner(text).run()


def significant(tokens: list[Token]) -> list[Token]:
    """Токены без тривиа (EOF остаётся последним)."""
    return [t for t in tokens if t.kind not in TRIVIA]


def join(tokens: list[Token]) -> str:
    return "".join(t.text for t in tokens)
