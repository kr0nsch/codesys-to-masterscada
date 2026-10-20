"""Сценарии CSV (диалект s7-to-codesys) и режимы времени R1/R2 (00-INDEX §4.5, ТЗ §8.1).

R1 «строка = вызов»: строка — один вызов блока, время = ``t_ms``. R2 «фиксированный цикл» ``--cycle-ms P``:
цикл k начинается в k·P; строка i применяется в цикле ``k_i = ceil(t_i / P)``, между строками — циклы с
удержанными входами; выходы снимаются после цикла ``k_i``; несколько строк в одном цикле — применяется
последняя, остальные ``collapsed`` и не сравниваются. Трасса рантайма (``oracle-codesys.csv``) задаёт
фактическое ``t_ms`` каждого цикла — тогда R2 повторяет прогон с этими часами.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from typing import Any

from ..cdsfront.st import ast as A
from ..cdsfront.st.parser import parse_expression
from .interp import Arr, Machine, Obj, parse_duration_ms
from .semantics import SimError

_PATH_RE = re.compile(r"^(in|out|tol)\.(.+?)(?::([A-Z]+))?$")


@dataclass
class Row:
    scenario: str
    cycle: int
    t_ms: int
    inputs: dict[str, tuple[str, str]]
    outputs: dict[str, tuple[str, str]]
    tol: dict[str, float] = field(default_factory=dict)
    boundary: bool = False
    comment: str = ""


def read_csv(text: str) -> list[Row]:
    rows: list[Row] = []
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(reader)
    cols = []
    for h in header:
        m = _PATH_RE.match(h)
        cols.append((m.group(1), m.group(2), m.group(3) or "") if m else (h, "", ""))
    for rec in reader:
        if not rec or not any(x.strip() for x in rec):
            continue
        d = dict(zip(header, rec, strict=False))
        r = Row(d.get("scenario", "S"), int(d.get("cycle", "1") or 1), int(float(d.get("t_ms", "0") or 0)), {}, {})
        r.boundary = d.get("boundary", "FALSE").upper() == "TRUE"
        r.comment = d.get("comment", "")
        for (kind, path, typ), val in zip(cols, rec, strict=False):
            if kind == "in":
                r.inputs[path] = (typ, val)
            elif kind == "out":
                r.outputs[path] = (typ, val)
            elif kind == "tol" and val.strip():
                r.tol[path] = float(val)
        rows.append(r)
    return rows


def scenarios(rows: list[Row]) -> list[list[Row]]:
    out: list[list[Row]] = []
    cur = ""
    for r in rows:
        if not out or r.scenario != cur:
            out.append([])
            cur = r.scenario
        out[-1].append(r)
    return out


def parse_value(typ: str, text: str) -> Any:
    t = typ.upper()
    s = text.strip()
    if t == "BOOL":
        return s.upper() in ("TRUE", "1")
    if t in ("TIME", "LTIME"):
        if "#" in s:
            ms = parse_duration_ms(s.split("#", 1)[1])
        else:
            ms = float(s)
        return int(round(ms * 1_000_000)) if t == "LTIME" else int(round(ms))
    if t in ("REAL", "LREAL"):
        return float(s)
    if t == "STRING" or t == "WSTRING":
        return s.strip("'")
    if s.upper() in ("TRUE", "FALSE"):
        return s.upper() == "TRUE"
    if "#" in s:  # 16#00C1, WORD#16#FF, INT#-5
        parts = s.split("#")
        try:
            if len(parts) == 3:
                return int(parts[2].replace("_", ""), int(parts[1]))
            if parts[0].isdigit():
                return int(parts[1].replace("_", ""), int(parts[0]))
            return parse_value(t, parts[1])
        except ValueError:
            pass
    try:
        return int(s, 0) if not s.startswith("0") or s == "0" else int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s


def _path_expr(path: str, rename: dict[str, str]) -> A.Expr:
    parts = re.split(r"(\.|\[)", path)
    text = ""
    for p in parts:
        key = p.lower()
        text += rename.get(key, p) if re.fullmatch(r"[A-Za-z_]\w*", p) else p
    return parse_expression(text)


def get_path(m: Machine, inst: Obj, path: str, rename: dict[str, str]) -> Any:
    return m.eval(_path_expr(path, rename), inst, {})


def set_path(m: Machine, inst: Obj, path: str, typ: str, val: Any, rename: dict[str, str]) -> None:
    from .interp import _Frame

    e = _path_expr(path, rename)
    m.store(e, val, _Frame(inst, {}, None))


@dataclass
class RunResult:
    values: list[dict[str, Any] | None]  # по строке: значения выходов или None (collapsed)
    error: str | None = None


def run(
    m: Machine,
    pou: str,
    rows: list[Row],
    regime: str = "R1",
    period_ms: int = 10,
    clocks: list[int] | None = None,
    rename: dict[str, str] | None = None,
) -> RunResult:
    rn = rename or {}
    d = m.defs.get(pou.lower())
    if d is None:
        raise SimError(f"нет POU {pou}")
    inst = m.program(pou) if d.kind == "program" else m.new_instance(d)
    out: list[dict[str, Any] | None] = []
    try:
        if regime == "R1":
            for r in rows:
                for path, (typ, val) in r.inputs.items():
                    set_path(m, inst, path, typ, parse_value(typ, val), rn)
                m.call_instance(inst, r.t_ms)
                out.append({p: get_path(m, inst, p, rn) for p in r.outputs})
            return RunResult(out)
        ks = [math.ceil(r.t_ms / period_ms) for r in rows]
        last_for_k: dict[int, int] = {}
        for i, k in enumerate(ks):
            last_for_k[k] = i
        result: list[dict[str, Any] | None] = [None] * len(rows)
        max_k = max(ks) if ks else 0
        for k in range(0, max_k + 1):
            if k in last_for_k:
                i = last_for_k[k]
                for j, kk in enumerate(ks):
                    if kk == k and j <= i:
                        for path, (typ, val) in rows[j].inputs.items():
                            set_path(m, inst, path, typ, parse_value(typ, val), rn)
            now = clocks[k] if clocks is not None and k < len(clocks) else k * period_ms
            m.call_instance(inst, now)
            if k in last_for_k:
                i = last_for_k[k]
                result[i] = {p: get_path(m, inst, p, rn) for p in rows[i].outputs}
        return RunResult(result)
    except SimError as exc:
        return RunResult(out, str(exc))


def same(a: Any, b: Any, tol: float = 0.0) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return bool(abs(float(a) - float(b)) <= max(float(tol), 1e-9 * max(1.0, abs(float(a)))))
        except (TypeError, ValueError):
            return bool(a == b)
    if isinstance(a, Arr) or isinstance(b, Arr):
        return False
    return bool(a == b)


def show(v: Any) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return f"{v:.7g}"
    return str(v)
