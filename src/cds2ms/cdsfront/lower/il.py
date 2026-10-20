"""Понижение IL (список инструкций) в ST символьным исполнением текущего результата (CR).

``LD/LDN/ST/STN/S/R``, логика с ``N``, арифметика, сравнения, скобки ``AND(`` … ``)``, ``CAL/CALC/CALCN``,
``RET/RETC/RETCN``, ``JMP/JMPC/JMPCN``, вызов функции с CR первым аргументом
(``LD x / F_Clamp 0, 100 / ST y`` → ``y := F_Clamp(x, 0, 100);``). CR на метке — из всех входящих путей
через переменную ``migCrL_<метка>``; расхождение типов или неизвестный CR — вручную. Переходы — общий
структурировщик.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..st.parser import ParseError, parse_expression
from ..symbols import Symbols, VarInfo
from .common import LowerNote, LowerResult, Names, paren
from .jumps import Seg, structure

_LOGIC = {"AND": "AND", "OR": "OR", "XOR": "XOR", "&": "AND"}
_ARITH = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "MOD": "MOD"}
_CMP = {"GT": ">", "GE": ">=", "EQ": "=", "NE": "<>", "LE": "<=", "LT": "<"}
_USES_CR = frozenset(
    {"ST", "STN", "S", "R", "AND", "ANDN", "OR", "ORN", "XOR", "XORN", "NOT", "ADD", "SUB", "MUL", "DIV", "MOD",
     "GT", "GE", "EQ", "NE", "LE", "LT", "JMPC", "JMPCN", "CALC", "CALCN", "RETC", "RETCN", ")"}
)  # fmt: skip
_LINE = re.compile(r"^\s*(?:(?P<label>[A-Za-z_]\w*)\s*:(?!=))?\s*(?P<rest>.*)$")


@dataclass
class _Ins:
    op: str
    operand: str
    paren_open: bool
    line: int
    label: str | None


def _strip_comments(text: str) -> str:
    out = re.sub(r"\(\*.*?\*\)", lambda m: " " * len(m.group(0).replace("\n", "")) + "\n" * m.group(0).count("\n"),
                 text, flags=re.S)  # fmt: skip
    return re.sub(r"//[^\n]*", "", out)


def parse_il(text: str) -> list[_Ins]:
    lines = _strip_comments(text).split("\n")
    out: list[_Ins] = []
    buf = ""
    start = 0
    for no, raw in enumerate(lines, 1):
        if not buf:
            start = no
        buf = f"{buf} {raw}" if buf else raw
        if buf.count("(") > buf.count(")") and re.search(r"(?i)\bCAL[CN]*\b", buf):
            continue  # многострочный формальный вызов CAL fb(\n IN := …\n)
        line = buf
        buf = ""
        m = _LINE.match(line)
        if not m:
            continue
        label = m.group("label")
        rest = m.group("rest").strip()
        if label and label.upper() in ("LD", "ST"):  # «LD:»? — не метка
            rest = f"{label}:{rest}"
            label = None
        if not rest:
            if label:
                out.append(_Ins("", "", False, start, label))
            continue
        if rest == ")":
            out.append(_Ins(")", "", False, start, label))
            continue
        mm = re.match(r"^(?P<op>[A-Za-z_][\w.]*)\s*(?P<paren>\()?\s*(?P<arg>.*)$", rest)
        if not mm:
            out.append(_Ins("?", rest, False, start, label))
            continue
        op = mm.group("op")
        arg = mm.group("arg").strip()
        is_paren = mm.group("paren") is not None
        if is_paren and op.upper().startswith("CAL"):
            arg = "(" + arg  # CAL fb(...) — скобки аргументов, не вложенное выражение
            is_paren = False
        out.append(_Ins(op, arg, is_paren, start, label))
    return out


def lower_il(
    text: str, syms: Symbols | None, local: dict[str, VarInfo], names: Names, base_line: int = 0
) -> LowerResult:
    ins = parse_il(text)
    notes: list[LowerNote] = []
    vars_: list[tuple[str, str]] = []
    segs: list[Seg] = []

    def typeof(expr: str) -> str | None:
        if syms is None:
            return None
        try:
            return syms.expr_type(parse_expression(expr), local)
        except ParseError:
            return None

    # метки, на входе в которые используется CR
    needs_cr: set[str] = set()
    for i, x in enumerate(ins):
        if x.label:
            nxt = next((y for y in ins[i:] if y.op), None)
            if nxt is not None and nxt.op.upper() in _USES_CR:
                needs_cr.add(x.label.lower())
    label_var: dict[str, str] = {}
    label_type: dict[str, str] = {}

    def store_label_cr(label: str, cr: str | None, cr_t: str | None, line: int) -> None:
        key = label.lower()
        if key not in needs_cr:
            return
        if cr is None or cr_t is None:
            notes.append(LowerNote("MS-LANG-05", "manual", f"CR на метке {label} не определён", base_line + line))
            return
        if key in label_type and label_type[key] != cr_t:
            notes.append(
                LowerNote(
                    "MS-LANG-05", "manual", f"CR на метке {label}: типы {label_type[key]} и {cr_t}", base_line + line
                )
            )
            return
        if key not in label_var:
            label_var[key] = names.new(f"migCrL_{label}")
            label_type[key] = cr_t
            vars_.append((label_var[key], cr_t))
        segs.append(Seg("stmt", f"{label_var[key]} := {cr};\n"))

    cr: str | None = None
    cr_t: str | None = None
    stack: list[tuple[str, str | None, str | None]] = []
    tmp_by_type: dict[str, str] = {}

    def materialize() -> None:
        nonlocal cr
        if cr is None or all(ch.isalnum() or ch in "_.#" for ch in cr):
            return
        t = cr_t or "BOOL"
        if t not in tmp_by_type:
            tmp_by_type[t] = names.new(f"migCr{t.capitalize()}")
            vars_.append((tmp_by_type[t], t))
        segs.append(Seg("stmt", f"{tmp_by_type[t]} := {cr};\n"))
        cr = tmp_by_type[t]

    prev_falls = True
    for x in ins:
        if x.label:
            if prev_falls:
                store_label_cr(x.label, cr, cr_t, x.line)
            segs.append(Seg("label", x.label))
            key = x.label.lower()
            if key in label_var:
                cr, cr_t = label_var[key], label_type[key]
            else:
                cr, cr_t = None, None
        if not x.op:
            prev_falls = True
            continue
        prev_falls = True
        up = x.op.upper()
        arg = x.operand
        neg = False
        base = up
        if up.endswith("N") and up[:-1] in ("LD", "ST", "AND", "OR", "XOR", "JMPC", "CALC", "RETC"):
            base, neg = up[:-1], True
        if x.paren_open and base in (*_LOGIC, *_ARITH, *_CMP):
            stack.append((up, cr, cr_t))
            if arg:
                # «ORN( a …)»: a загружается во вложенный CR как есть, модификатор N — к результату скобок (на «)»)
                cr, cr_t = arg, typeof(arg)
            else:
                cr, cr_t = None, None
            continue
        if up == ")":
            if not stack:
                notes.append(LowerNote("MS-LANG-05", "manual", "лишняя «)»", base_line + x.line))
                continue
            sop, scr, sct = stack.pop()
            sbase, sneg = (sop[:-1], True) if sop.endswith("N") and sop[:-1] in _LOGIC else (sop, False)
            inner = f"NOT {paren(cr or 'FALSE')}" if sneg else paren(cr or "FALSE")
            if sbase in _LOGIC:
                cr = f"{paren(scr or 'FALSE')} {_LOGIC[sbase]} {inner}"
                cr_t = "BOOL" if (sct == "BOOL" or cr_t == "BOOL") else (sct or cr_t)
            elif sbase in _ARITH:
                cr = f"{paren(scr or '0')} {_ARITH[sbase]} {inner}"
                cr_t = sct or cr_t
            else:
                cr = f"{paren(scr or '0')} {_CMP[sbase]} {inner}"
                cr_t = "BOOL"
            continue
        if base == "LD":
            cr = f"NOT {paren(arg)}" if neg else arg
            cr_t = typeof(arg)
        elif base == "ST" or up in ("S", "R"):
            if cr is None:
                notes.append(LowerNote("MS-LANG-05", "manual", f"{up} {arg}: CR не определён", base_line + x.line))
                continue
            val = f"NOT {paren(cr)}" if neg else cr
            if re.search(rf"(?i)\b{re.escape(arg)}\b", cr) and not all(ch.isalnum() or ch in "_." for ch in cr):
                materialize()
                val = f"NOT {cr}" if neg else cr
            if up == "S":
                segs.append(Seg("stmt", f"IF {cr} THEN\n    {arg} := TRUE;\nEND_IF;\n"))
            elif up == "R":
                segs.append(Seg("stmt", f"IF {cr} THEN\n    {arg} := FALSE;\nEND_IF;\n"))
            else:
                segs.append(Seg("stmt", f"{arg} := {val};\n"))
        elif base in _LOGIC:
            term = f"NOT {paren(arg)}" if neg else paren(arg)
            cr = f"{paren(cr or 'FALSE')} {_LOGIC[base]} {term}"
            cr_t = cr_t or typeof(arg)
        elif up == "NOT":
            cr = f"NOT {paren(cr or 'FALSE')}"
        elif up in _ARITH:
            cr = f"{paren(cr or '0')} {_ARITH[up]} {paren(arg)}"
            cr_t = cr_t or typeof(arg)
        elif up in _CMP:
            cr = f"{paren(cr or '0')} {_CMP[up]} {paren(arg)}"
            cr_t = "BOOL"
        elif base in ("JMP", "JMPC"):
            if up == "JMP":
                store_label_cr(arg, cr, cr_t, x.line)
                segs.append(Seg("jmp", arg))
                prev_falls = False
                cr, cr_t = None, None
            else:
                if cr is None:
                    notes.append(LowerNote("MS-LANG-05", "manual", f"{up}: CR не определён", base_line + x.line))
                    continue
                materialize()
                store_label_cr(arg, cr, cr_t, x.line)
                segs.append(Seg("jmp", arg, f"NOT {cr}" if neg else cr))
        elif base in ("CAL", "CALC"):
            m = re.match(r"^([A-Za-z_][\w.]*)\s*(\((.*)\))?\s*$", arg, re.S)
            if not m:
                notes.append(LowerNote("MS-LANG-05", "manual", f"не разобран вызов {arg}", base_line + x.line))
                continue
            call = f"{m.group(1)}({(m.group(3) or '').strip()});"
            call = re.sub(r"\s+", " ", call).replace("( ", "(").replace(" )", ")") + "\n"
            if up == "CAL":
                segs.append(Seg("stmt", call))
            else:
                cond = f"NOT {paren(cr or 'FALSE')}" if neg else (cr or "FALSE")
                segs.append(Seg("stmt", f"IF {cond} THEN\n    {call}END_IF;\n"))
            cr, cr_t = None, None
        elif base in ("RET", "RETC"):
            if up == "RET":
                segs.append(Seg("ret"))
                prev_falls = False
            else:
                segs.append(Seg("ret", "", f"NOT {paren(cr or 'FALSE')}" if neg else (cr or "FALSE")))
        elif re.match(r"^[A-Za-z_][\w.]*$", x.op) and (
            syms is None
            or syms.function_return(x.op)
            or "_TO_" in up
            or up in ("LIMIT", "MAX", "MIN", "SEL", "ABS", "SQRT", "TRUNC")
        ):
            args = [a.strip() for a in arg.split(",")] if arg else []
            cr = f"{x.op}({', '.join([cr or '0', *args])})"
            rt = syms.function_return(x.op) if syms is not None else None
            cr_t = rt or typeof(cr)
        else:
            notes.append(LowerNote("MS-LANG-05", "manual", f"инструкция IL «{x.op} {arg}» не поддерживается",
                                   base_line + x.line))  # fmt: skip
    try:
        st = structure(segs)
    except ValueError as exc:
        notes.append(LowerNote("MS-LANG-05", "manual", str(exc), base_line))
        st = structure([s for s in segs if s.kind == "stmt"])
    if st.mode != "none":
        notes.append(LowerNote("MS-ST-13", "review", f"переходы IL → {'IF' if st.mode == 'if' else 'автомат migPc'}",
                               base_line))  # fmt: skip
    notes.append(LowerNote("MS-LANG-05", "review", f"IL → ST: {len(ins)} инструкций", base_line))
    body = "(* cds2ms: MS-LANG-05 IL → ST *)\n" + st.text
    return LowerResult(body, vars_ + st.extra_vars, notes)
