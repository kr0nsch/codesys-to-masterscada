"""Структурировщик переходов — один для ST ``JMP``, переходов FBD/LD (jump/label/return) и IL ``JMP*``.

Вход — плоский список сегментов: текст оператора, метка, (условный) переход, (условный) возврат.
Переходы только вперёд и без пересечений превращаются в ``IF NOT усл THEN <хвост> END_IF`` (читаемо).
Любой другой граф меток — в автомат ``migPc``::

    migPc := 0;
    WHILE migPc >= 0 DO
        CASE migPc OF
            0: …; migPc := 1;
            1: …; migPc := -1;
        END_CASE;
    END_WHILE;

Бесконечный цикл источника остаётся бесконечным: поведение не «чинится».
"""

from __future__ import annotations

from dataclasses import dataclass

from ..st import ast as A
from ..st.parser import ParsedBody
from ..st.printer import fmt_expr


@dataclass
class Seg:
    kind: str  # stmt | label | jmp | ret
    text: str = ""  # stmt: текст с переводом строки; label/jmp: имя метки
    cond: str | None = None  # jmp/ret: условие (None — безусловно)


@dataclass
class Structured:
    text: str
    mode: str  # none | if | machine
    extra_vars: list[tuple[str, str]]


def _indent(text: str, n: int = 1) -> str:
    pad = "    " * n
    return "".join(pad + ln if ln.strip() else ln for ln in text.splitlines(keepends=True))


def _paren(cond: str) -> str:
    c = cond.strip()
    simple = all(ch.isalnum() or ch in "_.[]^" for ch in c)
    return c if simple else f"({c})"


def structure(segs: list[Seg]) -> Structured:
    labels = {s.text.lower(): i for i, s in enumerate(segs) if s.kind == "label"}
    jumps = [(i, labels.get(s.text.lower(), -1)) for i, s in enumerate(segs) if s.kind == "jmp"]
    if not jumps:
        return Structured(_emit_plain(segs, 0, len(segs)), "none", [])
    if any(t < 0 for _, t in jumps):
        missing = [segs[i].text for i, t in jumps if t < 0]
        raise ValueError(f"переход на несуществующую метку: {', '.join(missing)}")
    if _forward_nested(jumps):
        return Structured(_emit_if(segs, 0, len(segs)), "if", [])
    return Structured(_emit_machine(segs), "machine", [("migPc", "INT")])


def _forward_nested(jumps: list[tuple[int, int]]) -> bool:
    if any(t <= i for i, t in jumps):
        return False
    for a, b in jumps:
        for c, d in jumps:
            if a < c < b < d:
                return False
    return True


def _emit_plain(segs: list[Seg], lo: int, hi: int) -> str:
    out = []
    for s in segs[lo:hi]:
        if s.kind == "stmt":
            out.append(s.text)
        elif s.kind == "ret":
            out.append("RETURN;\n" if s.cond is None else f"IF {s.cond} THEN\n    RETURN;\nEND_IF;\n")
    return "".join(out)


def _emit_if(segs: list[Seg], lo: int, hi: int) -> str:
    labels = {s.text.lower(): i for i, s in enumerate(segs) if s.kind == "label"}
    out: list[str] = []
    k = lo
    while k < hi:
        s = segs[k]
        if s.kind == "jmp":
            t = labels[s.text.lower()]
            if s.cond is None:
                out.append(f"(* cds2ms: MS-ST-13 переход на {s.text}: участок до метки не исполняется *)\n")
            else:
                inner = _emit_if(segs, k + 1, t)
                out.append(f"IF NOT {_paren(s.cond)} THEN\n{_indent(inner)}END_IF;\n")
            k = t
            continue
        if s.kind == "stmt":
            out.append(s.text)
        elif s.kind == "ret":
            out.append("RETURN;\n" if s.cond is None else f"IF {s.cond} THEN\n    RETURN;\nEND_IF;\n")
        k += 1
    return "".join(out)


def _emit_machine(segs: list[Seg]) -> str:
    blocks: list[list[Seg]] = [[]]
    names: list[str] = [""]
    for s in segs:
        if s.kind == "label":
            blocks.append([])
            names.append(s.text.lower())
        else:
            blocks[-1].append(s)
    index = {n: i for i, n in enumerate(names) if n}
    out = ["migPc := 0;\n", "WHILE migPc >= 0 DO\n", "    CASE migPc OF\n"]
    for bi, block in enumerate(blocks):
        lines: list[str] = []
        for s in block:
            if s.kind == "stmt":
                lines.append(s.text)
            elif s.kind == "jmp":
                tgt = index[s.text.lower()]
                if s.cond is None:
                    lines.append(f"migPc := {tgt};\nCONTINUE;\n")
                else:
                    lines.append(f"IF {s.cond} THEN\n    migPc := {tgt};\n    CONTINUE;\nEND_IF;\n")
            elif s.kind == "ret":
                lines.append("RETURN;\n" if s.cond is None else f"IF {s.cond} THEN\n    RETURN;\nEND_IF;\n")
        nxt = bi + 1 if bi + 1 < len(blocks) else -1
        lines.append(f"migPc := {nxt};\n")
        out.append(f"        {bi}:\n")
        out.append(_indent("".join(lines), 3))
    out.append("    END_CASE;\nEND_WHILE;\n")
    return "".join(out)


def segments_from_body(pb: ParsedBody) -> list[Seg] | None:
    """Сегменты верхнего уровня тела ST; ``None``, если переход стоит глубже ``IF c THEN JMP L; END_IF``."""
    segs: list[Seg] = []
    for s in pb.stmts:
        if isinstance(s, A.Label):
            segs.append(Seg("label", s.name))
        elif isinstance(s, A.Jmp):
            segs.append(Seg("jmp", s.label))
        elif (
            isinstance(s, A.If)
            and len(s.branches) == 1
            and s.else_body is None
            and len(s.branches[0][1]) == 1
            and isinstance(s.branches[0][1][0], A.Jmp)
        ):
            jmp = s.branches[0][1][0]
            assert isinstance(jmp, A.Jmp)
            segs.append(Seg("jmp", jmp.label, fmt_expr(s.branches[0][0])))
        else:
            for sub in A.walk_stmts([s]):
                if isinstance(sub, A.Jmp | A.Label):
                    return None
            segs.append(Seg("stmt", pb.span_text(s) + "\n"))
    return segs


def has_jumps(pb: ParsedBody) -> bool:
    return any(isinstance(s, A.Jmp | A.Label) for s in A.walk_stmts(pb.stmts))
