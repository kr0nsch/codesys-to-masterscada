"""Сигнатуры стандартных ФБ и функций CODESYS (библиотека Standard и операторы МЭК).

Источник — справка CODESYS (Standard.library: TON, TOF, TP, R_TRIG, F_TRIG, RS, SR, CTU, CTD, CTUD) и
таблица операторов МЭК 61131-3. Используется понижением графики (имена и типы пинов), выводом типов и
симулятором.
"""

from __future__ import annotations

# имя ФБ -> (входы [(имя, тип)], выходы [(имя, тип)])
STD_FBS: dict[str, tuple[list[tuple[str, str]], list[tuple[str, str]]]] = {
    "TON": ([("IN", "BOOL"), ("PT", "TIME")], [("Q", "BOOL"), ("ET", "TIME")]),
    "TOF": ([("IN", "BOOL"), ("PT", "TIME")], [("Q", "BOOL"), ("ET", "TIME")]),
    "TP": ([("IN", "BOOL"), ("PT", "TIME")], [("Q", "BOOL"), ("ET", "TIME")]),
    "R_TRIG": ([("CLK", "BOOL")], [("Q", "BOOL")]),
    "F_TRIG": ([("CLK", "BOOL")], [("Q", "BOOL")]),
    "RS": ([("SET", "BOOL"), ("RESET1", "BOOL")], [("Q1", "BOOL")]),
    "SR": ([("SET1", "BOOL"), ("RESET", "BOOL")], [("Q1", "BOOL")]),
    "CTU": ([("CU", "BOOL"), ("RESET", "BOOL"), ("PV", "WORD")], [("Q", "BOOL"), ("CV", "WORD")]),
    "CTD": ([("CD", "BOOL"), ("LOAD", "BOOL"), ("PV", "WORD")], [("Q", "BOOL"), ("CV", "WORD")]),
    "CTUD": (
        [("CU", "BOOL"), ("CD", "BOOL"), ("RESET", "BOOL"), ("LOAD", "BOOL"), ("PV", "WORD")],
        [("QU", "BOOL"), ("QD", "BOOL"), ("CV", "WORD")],
    ),
}

# операторы-блоки FBD/CFC/LD -> инфиксная запись (n-арные) или функция
INFIX_OPS = {
    "AND": "AND",
    "OR": "OR",
    "XOR": "XOR",
    "ADD": "+",
    "SUB": "-",
    "MUL": "*",
    "DIV": "/",
    "MOD": "MOD",
    "EQ": "=",
    "NE": "<>",
    "LT": "<",
    "LE": "<=",
    "GT": ">",
    "GE": ">=",
}
BOOL_RESULT_OPS = frozenset({"AND", "OR", "XOR", "NOT", "EQ", "NE", "LT", "LE", "GT", "GE"})
FUNC_OPS = frozenset(
    {"LIMIT", "SEL", "MAX", "MIN", "MUX", "ABS", "SQRT", "MOVE", "NOT", "TRUNC", "EXPT", "SHL", "SHR", "ROL", "ROR"}
)

INT_TYPES = {
    "SINT": (8, True),
    "INT": (16, True),
    "DINT": (32, True),
    "LINT": (64, True),
    "USINT": (8, False),
    "UINT": (16, False),
    "UDINT": (32, False),
    "ULINT": (64, False),
    "BYTE": (8, False),
    "WORD": (16, False),
    "DWORD": (32, False),
    "LWORD": (64, False),
}
REAL_TYPES = frozenset({"REAL", "LREAL"})
TIME_TYPES = frozenset({"TIME", "LTIME"})
NUM_RANK = [
    "SINT",
    "USINT",
    "BYTE",
    "INT",
    "UINT",
    "WORD",
    "DINT",
    "UDINT",
    "DWORD",
    "LINT",
    "ULINT",
    "LWORD",
    "REAL",
    "LREAL",
]

STD_FUNCS = frozenset(
    {
        "LIMIT", "SEL", "MAX", "MIN", "MUX", "ABS", "SQRT", "LN", "LOG", "EXP", "SIN", "COS", "TAN", "ASIN", "ACOS",
        "ATAN", "EXPT", "TRUNC", "LEN", "LEFT", "RIGHT", "MID", "CONCAT", "INSERT", "DELETE", "REPLACE", "FIND",
        "SHL", "SHR", "ROL", "ROR", "MOVE", "TIME", "ADR", "SIZEOF", "__NEW", "__DELETE", "__QUERYINTERFACE",
        "__ISVALIDREF", "MEMCPY", "MEMSET",
    }
)  # fmt: skip


ELEMENTARY = frozenset(
    {*INT_TYPES, *REAL_TYPES, *TIME_TYPES, "BOOL", "STRING", "WSTRING", "DATE", "TOD", "DT", "TIME_OF_DAY",
     "DATE_AND_TIME", "BCD", "ANY"}
)  # fmt: skip


def is_conversion(name: str) -> tuple[str, str] | None:
    """``REAL_TO_INT`` → ("REAL", "INT"); ``TO_INT``/``ANY_TO_INT`` → ("ANY", "INT"). Только элементарные типы."""
    up = name.upper()
    if "." in up:
        return None
    if "_TO_" in up:
        a, _, b = up.partition("_TO_")
        a = a or "ANY"
        if a.endswith("_BCD"):
            a = a[:-4]
        if b.startswith("BCD_"):
            b = b[4:]
        if a in ELEMENTARY and b in ELEMENTARY:
            return (a, b)
        return None
    if up.startswith("TO_") and up[3:] in ELEMENTARY:
        return ("ANY", up[3:])
    return None


def common_type(a: str | None, b: str | None) -> str | None:
    if a is None:
        return b
    if b is None:
        return a
    if a == b:
        return a
    if a in TIME_TYPES or b in TIME_TYPES:
        return "LTIME" if "LTIME" in (a, b) else "TIME"
    ra = NUM_RANK.index(a) if a in NUM_RANK else -1
    rb = NUM_RANK.index(b) if b in NUM_RANK else -1
    if ra < 0 and rb < 0:
        return a
    return a if ra >= rb else b
