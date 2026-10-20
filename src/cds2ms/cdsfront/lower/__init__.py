"""Понижение проекта CODESYS в ST: графика, SFC, IL, действия, ООП. Выполняется всегда; исходы — в заметках."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...ir.model import Body, Origin, Pou, Project
from ..st import ast as A
from ..st.parser import parse_body, parse_decl
from ..symbols import Symbols, VarInfo, collect_vars
from .common import LowerNote, LowerResult, Names
from .graph import lower_graph
from .il import lower_il
from .oop import OopLowering
from .sfc import lower_sfc, uses_sfc_flags

__all__ = ["LowerNote", "LoweredPou", "LoweredProject", "lower_project"]


@dataclass
class LoweredPou:
    name: str
    kind: str
    lang: str  # язык исходного тела
    decl: str  # объявление (CODESYS ST) после понижения
    body: str  # тело (CODESYS ST) после понижения
    origin: Origin
    body_file: str
    body_line: int
    decl_line: int
    notes: list[LowerNote] = field(default_factory=list)
    had_methods: int = 0
    had_properties: int = 0
    source: Pou | None = None

    @property
    def text(self) -> str:
        end = {"program": "END_PROGRAM", "functionBlock": "END_FUNCTION_BLOCK", "function": "END_FUNCTION"}[self.kind]
        decl = self.decl if self.decl.endswith("\n") else self.decl + "\n"
        body = self.body if self.body.endswith("\n") or not self.body else self.body + "\n"
        return f"{decl}{body}{end}\n"


@dataclass
class LoweredProject:
    project: Project
    pous: list[LoweredPou]
    syms: Symbols

    def pou(self, name: str) -> LoweredPou | None:
        for p in self.pous:
            if p.name.lower() == name.lower():
                return p
        return None


def add_vars(decl: str, sections: dict[str, list[tuple[str, str]]]) -> str:
    """Дописать секции переменных в конец объявления."""
    text = decl.rstrip()
    for kind in ("VAR_INPUT", "VAR_OUTPUT", "VAR"):
        items = sections.get(kind) or []
        if not items:
            continue
        seen: set[str] = set()
        lines = []
        for name, typ in items:
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            lines.append(f"    {name} : {typ};")
        text += f"\n{kind}\n" + "\n".join(lines) + "\nEND_VAR"
    return text + "\n"


class _Lowerer:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.syms = Symbols(project)
        self.names: dict[str, Names] = {}
        taken = {p.name for p in project.pous} | {g.name for g in project.gvls} | {d.name for d in project.duts}
        self.global_taken = taken

    def names_for(self, pou: str) -> Names:
        if pou.lower() not in self.names:
            ps = self.syms.pous.get(pou.lower())
            local = set(ps.vars) if ps else set()
            self.names[pou.lower()] = Names(local | {t.lower() for t in self.global_taken})
        return self.names[pou.lower()]

    def lower_body(
        self, pou: Pou, body: Body, local: dict[str, VarInfo], extra: LowerResult | None = None
    ) -> LowerResult:
        names = self.names_for(pou.name)
        if body.lang == "ST":
            return LowerResult(body.text)
        if body.lang in ("FBD", "LD", "CFC"):
            return lower_graph(body, self.syms, local, names)
        if body.lang == "IL":
            return lower_il(body.text, self.syms, local, names, body.line - 1)
        if body.lang == "SFC":
            sub_vars: list[tuple[str, str]] = []
            sub_notes: list[LowerNote] = []

            def lower_action(name: str, b: Body) -> str:
                r = self.lower_body(pou, b, local)
                sub_vars.extend(r.vars)
                sub_notes.extend(r.notes)
                return r.body

            r = lower_sfc(pou, body, names, lower_action)
            r.vars = sub_vars + r.vars
            r.notes = sub_notes + r.notes
            texts = [e.condition or e.expr for e in body.elems if e.kind in ("transition", "inVariable")]
            texts += [a.body.text for a in pou.actions] + [t.body.text for t in pou.transitions]
            flags = uses_sfc_flags(pou.decl_text, texts)
            for f in flags:
                r.notes.append(LowerNote("MS-SFC-02", "manual", f"неявная переменная SFC {f}: вручную", body.line))
            return r
        return LowerResult(body.text, notes=[LowerNote("MS-PARSE-01", "manual", f"язык {body.lang} не понижается")])

    def inline_actions(self, pou: Pou, text: str, local: dict[str, VarInfo], res: LowerResult) -> str:
        if not pou.actions or pou.lang == "SFC":
            return text
        acts = {a.name.lower(): a for a in pou.actions}
        pb = parse_body(text)
        repl: dict[int, tuple[int, str]] = {}
        called: set[str] = set()
        for s in A.walk_stmts(pb.stmts):
            if isinstance(s, A.CallStmt) and isinstance(s.call.func, A.Name) and s.call.func.id.lower() in acts:
                a = acts[s.call.func.id.lower()]
                r = self.lower_body(pou, a.body, local)
                res.vars.extend(r.vars)
                res.notes.extend(r.notes)
                if any(isinstance(x, A.Return) for x in A.walk_stmts(parse_body(r.body).stmts)):
                    res.notes.append(
                        LowerNote("MS-LANG-07", "manual", f"действие {a.name} с RETURN — вручную", a.origin.line)
                    )
                    continue
                repl[s.start] = (s.end, f"(* действие {a.name} встроено *)\n{r.body.strip()}\n")
                called.add(a.name.lower())
                res.notes.append(LowerNote("MS-LANG-07", "review", f"действие {a.name} встроено", a.origin.line))
        for a in pou.actions:
            if a.name.lower() not in called:
                res.notes.append(
                    LowerNote(
                        "MS-LANG-07",
                        "manual",
                        f"действие {a.name} вызывается не из своего тела — вручную",
                        a.origin.line,
                    )
                )
        if not repl:
            return text
        out = []
        skip = -1
        for i, t in enumerate(pb.tokens):
            if i < skip:
                continue
            if i in repl:
                end, s_text = repl[i]
                out.append(s_text.rstrip("\n"))
                skip = end
                continue
            out.append(t.text)
        return "".join(out)

    def run(self) -> LoweredProject:
        oop = OopLowering(self.project, lambda p, b, loc: self.lower_body(p, b, loc).body, self.names_for)
        oop.build()
        out: list[LoweredPou] = []
        for pou in self.project.pous:
            local = collect_vars(parse_decl(pou.decl_text).decl)
            res = LowerResult("")
            if pou.body is None:
                res.body = ""
                res.notes.append(LowerNote("MS-PARSE-01", "manual", "у POU нет тела", pou.origin.line))
            else:
                r = self.lower_body(pou, pou.body, local)
                res.body, res.vars, res.notes = r.body, list(r.vars), list(r.notes)
            res.body = self.inline_actions(pou, res.body, local, res)
            decl = pou.decl_text
            fb = oop.lowered_fb(pou, res.body) if pou.kind == "functionBlock" else None
            if fb is not None:
                decl, res.body = fb
                if pou.methods:
                    res.notes.append(LowerNote("MS-LANG-06", "review",
                                               f"методы ({len(pou.methods)}) → режим вызова migCall", pou.origin.line))  # fmt: skip
            local2 = collect_vars(parse_decl(decl).decl)
            names = self.names_for(pou.name)
            rw_body = oop.rewrite_calls(pou.name, res.body, {**local2}, names)
            if rw_body != res.body:
                res.body = rw_body
                res.notes.append(
                    LowerNote("MS-LANG-06", "review", "вызовы методов экземпляров → режим вызова", pou.origin.line)
                )
            res.notes.extend(oop.notes.pop(pou.name, []))
            aliased = oop.aliased_vars(pou.name)
            if aliased:
                decl = drop_vars(decl, aliased)
            decl = add_vars(decl, {"VAR": res.vars + _rewriter_temps(oop, pou.name)})
            body_file = pou.body.file if pou.body is not None and pou.body.file else pou.origin.file
            out.append(
                LoweredPou(
                    pou.name, pou.kind, pou.lang, decl, res.body, pou.origin, body_file,
                    pou.body.line if pou.body is not None else pou.origin.line, pou.decl_line, res.notes,
                    len(pou.methods), len(pou.properties), pou,
                )
            )  # fmt: skip
        lp = LoweredProject(self.project, out, self.syms)
        return lp


def _rewriter_temps(oop: OopLowering, pou: str) -> list[tuple[str, str]]:
    return oop.temps.pop(pou.lower(), [])


def drop_vars(decl: str, names: list[str]) -> str:
    """Убрать объявления переменных (интерфейсные переменные, заменённые экземпляром)."""
    pd = parse_decl(decl)
    low = {n.lower() for n in names}
    cuts: list[tuple[int, int]] = []
    for sec in pd.decl.sections:
        for d in sec.decls:
            if all(n.lower() in low for n in d.names):
                a = pd.tokens[d.start].offset
                b = pd.tokens[d.end - 1].end
                line_start = decl.rfind(chr(10), 0, a) + 1
                if not decl[line_start:a].strip():
                    a = line_start
                nl = decl.find(chr(10), b)
                if nl >= 0 and not decl[b:nl].strip():
                    b = nl + 1
                cuts.append((a, b))
    out = decl
    for a, b in sorted(cuts, reverse=True):
        out = out[:a] + out[b:]
    return out


def lower_project(project: Project) -> LoweredProject:
    return _Lowerer(project).run()


def strip_mig_comments(text: str) -> str:
    return re.sub(r"\(\* cds2ms:[^*]*\*\)\n?", "", text)
