"""Понижение SFC CODESYS в ST-автомат с порядком обработки CODESYS за цикл.

Порядок (https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_sequence_of_processing.html):
копия ``_x`` → ``x`` в начале цикла → время шагов → блоки управления IEC-действий → IEC-действия по алфавиту
в два прохода (сначала деактивированные в этом цикле — последний вызов, затем активные) → переходы.

IEC-квалификаторы: N, P, S, R, L, D (CODESYS 3.5.17) и P0, P1 (экспорты других сред; CODESYS 3.5.17.30 их
отвергает: «is not a valid qualifier»). SD, DS, SL — вручную (срез P2). Действия шагов entry/exit
в экспорте 3.5.17.30 не сняты (``docs/FORMAT-OUT.md``) — находка manual, если встречаются.
Неявные переменные ``шаг.x``, ``шаг._x``, ``шаг.t`` → ``migS_<шаг>_x``, ``…_xn``, ``…_t``; ``_действие.x``
(выполняется, в том числе в последнем вызове — по трассе Control Win 3.5.17.30) → ``migA_<действие>_x``,
``_действие._x`` (активно) → ``migA_<действие>_q``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ...ir.model import Body, GElem, Pou, SfcAction
from ..st.lexer import Kind, tokenize
from ..st.parser import ParseError, parse_expression
from ..st.printer import fmt_expr
from .common import LowerNote, LowerResult, Names, paren

SUPPORTED = frozenset({"N", "P", "P0", "P1", "S", "R", "L", "D"})
_STEP_FLAGS = ("SFCInit", "SFCReset", "SFCPause", "SFCError", "SFCTrans", "SFCErrorStep", "SFCErrorPOU",
               "SFCCurrentStep", "SFCTip", "SFCTipMode", "SFCQuitError", "SFCEnableLimit", "SFCErrorAnalyzation")  # fmt: skip


@dataclass
class _Trans:
    elem: GElem
    preds: list[str]
    succs: list[str]
    cond: str


def _ident(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name) or "S"


def rename_implicit(
    text: str, steps: dict[str, str], actions: dict[str, str], active: dict[str, str] | None = None
) -> str:
    """Замена ``шаг.x|_x|t``, ``_действие.x|_x`` по границам токенов (строки и комментарии не трогаются)."""
    active = active if active is not None else actions
    toks = tokenize(text)
    out: list[str] = []
    sig = [k for k, t in enumerate(toks) if t.kind not in (Kind.WS, Kind.COMMENT, Kind.PRAGMA)]
    pos = {k: n for n, k in enumerate(sig)}
    skip_until = -1
    for k, t in enumerate(toks):
        if k < skip_until:
            continue
        if t.kind is Kind.IDENT and k in pos:
            n = pos[k]
            if n + 2 < len(sig):
                dot, mem = toks[sig[n + 1]], toks[sig[n + 2]]
                if dot.is_op(".") and mem.kind is Kind.IDENT:
                    base = t.text.lower()
                    m = mem.text.lower()
                    if base in steps and m in ("x", "_x", "t"):
                        suffix = {"x": "x", "_x": "xn", "t": "t"}[m]
                        out.append(f"{steps[base]}_{suffix}")
                        skip_until = sig[n + 2] + 1
                        continue
                    # CODESYS 3.5: «_действие.x» — выполняется, «_действие._x» — активно (справка «Implicit
                    # Variables»). Трасса Control Win 3.5.17.30: в последнем вызове после деактивации .x = TRUE
                    # (docs/ORACLES.md). «действие.x» без подчёркивания 3.5.17.30 отвергает; встречается в
                    # экспортах других сред — читается как «_действие.x».
                    abase = base[1:] if base.startswith("_") and base[1:] in actions else base
                    if abase in actions and (m == "x" or (m == "_x" and abase != base)):
                        out.append(actions[abase] if m == "x" else active[abase])
                        skip_until = sig[n + 2] + 1
                        continue
        out.append(t.text)
    return "".join(out)


def lower_sfc(
    pou: Pou,
    body: Body,
    names: Names,
    lower_action: Callable[[str, Body], str],
) -> LowerResult:
    notes: list[LowerNote] = []
    elems = body.elems
    by_id = {e.local_id: e for e in elems}
    steps = [e for e in elems if e.kind == "step"]
    macro = [e for e in elems if e.kind == "macroStep"]
    for m in macro:
        notes.append(LowerNote("MS-SFC-02", "manual", f"макрошаг {m.name} не понижается", m.line, local_id=m.local_id))
    step_var = {s.name.lower(): names.new(f"migS_{_ident(s.name)}") for s in steps}
    consumers: dict[str, list[GElem]] = {}
    for e in elems:
        for pin in e.inputs:
            for c in pin.conns:
                consumers.setdefault(c.ref, []).append(e)

    def back(ref: str, depth: int = 0) -> list[str]:
        e = by_id.get(ref)
        if e is None or depth > 64:
            return []
        if e.kind in ("step", "macroStep"):
            return [e.name]
        if e.kind in ("selectionDivergence", "simultaneousConvergence", "selectionConvergence"):
            out: list[str] = []
            for pin in e.inputs:
                for c in pin.conns:
                    out.extend(back(c.ref, depth + 1))
            return out
        return []

    def fwd(ref: str, depth: int = 0) -> list[str]:
        out: list[str] = []
        if depth > 64:
            return out
        for e in consumers.get(ref, []):
            if e.kind in ("step", "macroStep"):
                out.append(e.name)
            elif e.kind == "jumpStep":
                out.append(e.expr)
            elif e.kind in ("selectionConvergence", "simultaneousDivergence", "simultaneousConvergence"):
                out.extend(fwd(e.local_id, depth + 1))
        return out

    trans_objs = {t.name.lower(): t for t in pou.transitions}
    transitions: list[_Trans] = []
    for t in (e for e in elems if e.kind == "transition"):
        preds: list[str] = []
        for pin in t.inputs:
            for c in pin.conns:
                preds.extend(back(c.ref))
        succs = fwd(t.local_id)
        cond = "FALSE"
        if t.condition_ref:
            src = by_id.get(t.condition_ref)
            cond = src.expr if src is not None and src.expr else "FALSE"
        elif t.call_type == "reference":
            obj = trans_objs.get(t.condition.lower())
            if obj is None or obj.body.lang != "ST":
                notes.append(LowerNote("MS-SFC-02", "manual", f"переход {t.condition}: объект не на ST", t.line))
            else:
                txt = obj.body.text.strip().rstrip(";")
                try:
                    cond = fmt_expr(parse_expression(txt))
                except ParseError:
                    mm = re.match(r"(?is)^\s*\w+\s*:=\s*(.+)$", txt)
                    if mm:
                        cond = mm.group(1).strip()
                    else:
                        notes.append(LowerNote("MS-SFC-02", "manual", f"переход {t.condition}: не выражение", t.line))
        elif t.condition:
            cond = t.condition
        else:
            notes.append(LowerNote("MS-SFC-02", "manual", "переход без условия", t.line, local_id=t.local_id))
        if not preds or not succs:
            notes.append(LowerNote("MS-SFC-02", "manual", "переход без шагов до/после", t.line, local_id=t.local_id))
            continue
        transitions.append(_Trans(t, preds, succs, cond))

    # IEC-действия: имя -> [(шаг, квалификатор, длительность)]
    iec: dict[str, list[tuple[str, SfcAction]]] = {}
    inline_bodies: dict[str, Body] = {}
    for ab in (e for e in elems if e.kind == "actionBlock"):
        stp = None
        for pin in ab.inputs:
            for c in pin.conns:
                se = by_id.get(c.ref)
                if se is not None and se.kind == "step":
                    stp = se.name
        if stp is None:
            notes.append(LowerNote("MS-SFC-02", "manual", "блок действий не привязан к шагу", ab.line))
            continue
        for a in ab.actions:
            q = (a.qualifier or "N").upper()
            name = a.name
            if not name and a.inline is not None:
                name = names.new(f"migInl{len(inline_bodies) + 1}")
                inline_bodies[name.lower()] = a.inline
            if q not in SUPPORTED:
                notes.append(
                    LowerNote("MS-SFC-01", "manual", f"квалификатор {q} у действия {name}: вручную (SD/DS/SL)", a.line)
                )
                continue
            iec.setdefault(name, []).append((stp, a))
    act_var = {a.lower(): names.new(f"migA_{_ident(a)}") for a in iec}
    step_map = dict(step_var.items())
    act_map = {k: f"{v}_x" for k, v in act_var.items()}  # _действие.x — «выполняется» (и в последнем вызове)
    act_map_active = {k: f"{v}_q" for k, v in act_var.items()}  # _действие._x — «активно» (выход блока управления)

    vars_: list[tuple[str, str]] = [("migSfcInit", "BOOL"), ("migSfcPass", "INT")]
    for s in steps:
        v = step_var[s.name.lower()]
        vars_ += [(f"{v}_x", "BOOL"), (f"{v}_xn", "BOOL"), (f"{v}_xp", "BOOL"), (f"{v}_tmr", "TON"), (f"{v}_t", "TIME")]
    for aname in sorted(iec, key=str.lower):
        v = act_var[aname.lower()]
        vars_ += [(f"{v}_q", "BOOL"), (f"{v}_qp", "BOOL"), (f"{v}_s", "BOOL"), (f"{v}_x", "BOOL")]

    out: list[str] = []
    out.append("(* cds2ms: MS-LANG-04 SFC → ST-автомат с порядком обработки CODESYS *)\n")
    out.append("IF NOT migSfcInit THEN\n    migSfcInit := TRUE;\n")
    inits = [s for s in steps if s.initial]
    if not inits:
        notes.append(LowerNote("MS-SFC-02", "manual", "нет начального шага", body.line))
    for s in inits:
        out.append(f"    {step_var[s.name.lower()]}_xn := TRUE;\n")
    out.append("END_IF;\n(* копия _x -> x и время шагов *)\n")
    for s in steps:
        v = step_var[s.name.lower()]
        out.append(f"{v}_xp := {v}_x;\n{v}_x := {v}_xn;\n")
    for s in steps:
        v = step_var[s.name.lower()]
        out.append(f"{v}_tmr(IN := {v}_x, PT := T#24D);\n{v}_t := {v}_tmr.ET;\n")
    if iec:
        out.append("(* блоки управления IEC-действий *)\n")
    for aname in sorted(iec, key=str.lower):
        v = act_var[aname.lower()]
        terms: list[str] = []
        sets: list[str] = []
        resets: list[str] = []
        for stp, act in iec[aname]:
            sv = step_var.get(stp.lower())
            if sv is None:
                continue
            q = act.qualifier.upper() or "N"
            dur = act.duration.strip() or "T#0MS"
            if q == "N":
                terms.append(f"{sv}_x")
            elif q in ("P", "P1"):
                terms.append(f"({sv}_x AND NOT {sv}_xp)")
            elif q == "P0":
                terms.append(f"({sv}_xp AND NOT {sv}_x)")
            elif q == "L":
                terms.append(f"({sv}_x AND {sv}_t < {dur})")
            elif q == "D":
                terms.append(f"({sv}_x AND {sv}_t >= {dur})")
            elif q == "S":
                sets.append(f"{sv}_x")
            elif q == "R":
                resets.append(f"{sv}_x")
        if sets or resets:
            expr = f"{v}_s"
            if sets:
                expr = f"({expr} OR {' OR '.join(sets)})"
            if resets:
                expr = f"{expr} AND NOT ({' OR '.join(resets)})"
            out.append(f"{v}_s := {expr};\n")
            terms.append(f"{v}_s")
        q_expr = " OR ".join(terms) if terms else "FALSE"
        out.append(f"{v}_q := {q_expr};\n")
        out.append(f"{v}_x := {v}_q OR {v}_qp;\n")  # выполняется: активно или последний вызов после деактивации
    if iec:
        out.append("(* IEC-действия по алфавиту: проход 1 — последний вызов деактивированных, проход 2 — активные *)\n")
        out.append("FOR migSfcPass := 1 TO 2 DO\n")
        acts = {x.name.lower(): x for x in pou.actions}
        for aname in sorted(iec, key=str.lower):
            v = act_var[aname.lower()]
            act_obj = acts.get(aname.lower())
            body_a = act_obj.body if act_obj is not None else inline_bodies.get(aname.lower())
            if body_a is None:
                notes.append(LowerNote("MS-SFC-02", "manual", f"действие {aname} не найдено в POU", body.line))
                code = f"(* cds2ms: MS-SFC-02 действие {aname} не найдено *)\n"
            else:
                code = lower_action(aname, body_a)
            code = rename_implicit(code, step_map, act_map, act_map_active)
            ind = "".join("        " + ln if ln.strip() else ln for ln in code.splitlines(keepends=True))
            out.append(
                f"    IF (migSfcPass = 1 AND {v}_qp AND NOT {v}_q) OR (migSfcPass = 2 AND {v}_q) THEN\n{ind}    END_IF;\n"
            )
        out.append("END_FOR;\n")
        for aname in sorted(iec, key=str.lower):
            v = act_var[aname.lower()]
            out.append(f"{v}_qp := {v}_q;\n")
    out.append("(* переходы *)\n")
    for tr in transitions:
        pv = [step_var.get(p.lower()) for p in tr.preds]
        svs = [step_var.get(x.lower()) for x in tr.succs]
        if any(x is None for x in pv + svs):
            notes.append(LowerNote("MS-SFC-02", "manual", "переход на неизвестный шаг", tr.elem.line))
            continue
        guard = " AND ".join(f"{p}_x AND {p}_xn" for p in pv if p)
        cond = rename_implicit(tr.cond, step_map, act_map, act_map_active)
        lines = "".join(f"    {p}_xn := FALSE;\n" for p in pv if p) + "".join(
            f"    {x}_xn := TRUE;\n" for x in svs if x
        )
        out.append(f"IF {guard} AND {paren(cond)} THEN\n{lines}END_IF;\n")
    quals = {act.qualifier.upper() for lst in iec.values() for _, act in lst}
    if quals <= {"N", "P1"}:
        notes.append(
            LowerNote(
                "MS-SFC-01", "info",
                "рецепт перерисовки в SFC MasterSCADA 4D возможен (только N/P1), но N там пропускает первый цикл и "
                "выполняется ещё раз после деактивации — сдвиг на цикл", body.line,
            )
        )  # fmt: skip
    else:
        notes.append(
            LowerNote("MS-SFC-01", "info", f"квалификаторы {sorted(quals)} вне N/P1: в SFC MasterSCADA 4D только ST-автомат",
                      body.line)
        )  # fmt: skip
    notes.append(LowerNote("MS-LANG-04", "review", f"SFC: {len(steps)} шагов, {len(transitions)} переходов", body.line))
    return LowerResult("".join(out), vars_, notes)


def uses_sfc_flags(decl_text: str, body_texts: list[str]) -> list[str]:
    found = []
    blob = "\n".join(body_texts)
    for f in _STEP_FLAGS:
        if re.search(rf"(?i)\b{f}\b", blob) or re.search(rf"(?i)\b{f}\b", decl_text):
            found.append(f)
    return found
