"""Сплющивание ООП CODESYS в «режим вызова» (MS4D: методов, свойств, интерфейсов, EXTENDS нет).

В ФБ — вход ``migCall : INT``, входы ``<M>_<арг>``, выходы ``<M>_ret`` и ``<M>_<вых>``; в начале тела::

    IF migCall <> 0 THEN
        CASE migCall OF 1: <тело Start> … END_CASE;
        migCall := 0;
        RETURN;
    END_IF;

Вызов ``y := inst.Start(a := x)`` → ``inst(migCall := 1, Start_a := x); y := inst.Start_ret;``. Вызов своего
метода (``M()``, ``THIS^.M()``, ``SUPER^.M()``) — встраивание тела; рекурсия — вручную. Вызов в выражении —
подъём во временные ``migT<n>`` слева направо; в условии ``WHILE`` — пересчёт на каждой итерации.
``VAR_IN_OUT`` метода — копия во вход ``<M>_<арг>`` и обратно из выхода ``<M>_<арг>Out``.
PROPERTY GET без побочных эффектов → ``VAR_OUTPUT``, обновляемый в каждой точке выхода тела; SET → ветка
``migCall``. EXTENDS → копирование членов предка, ``SUPER^()`` → встраивание тела предка. Переменная
интерфейсного типа, которой по проекту присваивается один экземпляр, → подстановка экземпляра, иначе вручную.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ...ir.model import Body, Method, Pou, Project, Property
from ..st import ast as A
from ..st.lexer import TRIVIA, Kind, tokenize
from ..st.parser import ParsedBody, ParseError, parse_body, parse_decl, parse_expression
from ..st.printer import fmt_expr, fmt_stmts
from ..symbols import VarInfo, collect_vars
from .common import LowerNote, Names


@dataclass
class MethodInfo:
    name: str
    owner: str
    index: int
    ret_type: str | None
    inputs: list[VarInfo]
    outputs: list[VarInfo]
    inouts: list[VarInfo]
    locals: list[VarInfo]
    body: str  # тело ST (графика уже понижена)
    origin_line: int = 0
    renamed: str = ""  # тело в именах ФБ


@dataclass
class PropInfo:
    name: str
    type: str
    get_expr: str | None
    get_ok: bool
    set_body: str | None
    set_index: int = 0


@dataclass
class ClassInfo:
    name: str
    parent: str | None
    implements: list[str]
    methods: dict[str, MethodInfo] = field(default_factory=dict)
    props: dict[str, PropInfo] = field(default_factory=dict)
    own_decl: A.Declaration | None = None
    fb_init: MethodInfo | None = None
    special: list[str] = field(default_factory=list)  # FB_exit, FB_reinit, FB_init с параметрами

    @property
    def needs_dispatch(self) -> bool:
        return bool(self.methods) or any(p.set_body is not None for p in self.props.values())


_SPECIAL = ("fb_init", "fb_exit", "fb_reinit")


def rename_idents(text: str, mapping: dict[str, str], drop_this: bool = True) -> str:
    """Переименование идентификаторов по границам токенов; члены после «.» не трогаются; ``THIS^.`` снимается."""
    toks = tokenize(text)
    sig = [i for i, t in enumerate(toks) if t.kind not in TRIVIA]
    prev_sig: dict[int, int] = {}
    for n, i in enumerate(sig):
        prev_sig[i] = sig[n - 1] if n > 0 else -1
    out: list[str] = []
    skip: set[int] = set()
    for n, i in enumerate(sig):
        t = toks[i]
        if (
            drop_this
            and t.is_kw("THIS")
            and n + 2 < len(sig)
            and toks[sig[n + 1]].is_op("^")
            and toks[sig[n + 2]].is_op(".")
        ):
            skip.update(range(i, sig[n + 2] + 1))
    for i, t in enumerate(toks):
        if i in skip:
            continue
        if t.kind is Kind.IDENT:
            p = prev_sig.get(i, -1)
            after_dot = p >= 0 and toks[p].is_op(".") and p not in skip
            if not after_dot and t.text.lower() in mapping:
                out.append(mapping[t.text.lower()])
                continue
        out.append(t.text)
    return "".join(out)


class OopLowering:
    def __init__(
        self,
        project: Project,
        lower_body: Callable[[Pou, Body, dict[str, VarInfo]], str],
        names_for: Callable[[str], Names],
    ) -> None:
        self.project = project
        self.lower_body = lower_body
        self.names_for = names_for
        self.notes: dict[str, list[LowerNote]] = {}
        self.classes: dict[str, ClassInfo] = {}
        self.extra_vars: dict[str, list[tuple[str, str]]] = {}
        self.itf_alias: dict[tuple[str, str], str] = {}  # (POU, переменная) -> экземпляр
        self.fbs = {p.name.lower(): p for p in project.pous if p.kind == "functionBlock"}
        self.itf_names = {i.name.lower() for i in project.interfaces}
        self.temps: dict[str, list[tuple[str, str]]] = {}
        self.extra_locals: dict[str, list[tuple[str, str]]] = {}

    def note(self, pou: str, rule: str, outcome: str, msg: str, line: int = 0) -> None:
        self.notes.setdefault(pou, []).append(LowerNote(rule, outcome, msg, line))

    # ------------------------------------------------------------ классы

    def build(self) -> None:
        for name in self.fbs:
            self._class(name, set())
        self._interface_aliases()

    def _class(self, lname: str, stack: set[str]) -> ClassInfo | None:
        if lname in self.classes:
            return self.classes[lname]
        pou = self.fbs.get(lname)
        if pou is None or lname in stack:
            return None
        pd = parse_decl(pou.decl_text)
        h = pd.decl.header
        parent = h.extends[0] if h is not None and h.extends else None
        ci = ClassInfo(pou.name, parent, list(h.implements) if h else [], own_decl=pd.decl)
        if parent is not None:
            pc = self._class(parent.lower(), stack | {lname})
            if pc is None:
                self.note(pou.name, "MS-LANG-06", "manual", f"предок {parent} не найден в проекте", pou.origin.line)
            else:
                for k, inherited in pc.methods.items():
                    ci.methods[k] = inherited
                ci.props.update(pc.props)
        own_vars = collect_vars(pd.decl)
        idx = len(ci.methods)
        for m in pou.methods:
            if m.name.lower() in _SPECIAL:
                self._special(pou, ci, m)
                continue
            mi = self._method(pou, m, own_vars)
            if mi is None:
                continue
            if m.name.lower() in ci.methods:
                mi.index = ci.methods[m.name.lower()].index
            else:
                idx += 1
                mi.index = idx
            ci.methods[m.name.lower()] = mi
        for pr in pou.properties:
            ci.props[pr.name.lower()] = self._prop(pou, pr)
        # переиндексация: устойчиво 1..N по порядку объявления (предок первым)
        for n, k in enumerate(ci.methods, 1):
            ci.methods[k] = MethodInfo(**{**ci.methods[k].__dict__, "index": n})
        nxt = len(ci.methods)
        for p in ci.props.values():
            if p.set_body is not None:
                nxt += 1
                p.set_index = nxt
        self.classes[lname] = ci
        if h is not None:
            mods = [m for m in h.modifiers if m != "PUBLIC"]
            if mods:
                self.note(
                    pou.name,
                    "MS-LANG-06",
                    "info",
                    f"модификаторы {', '.join(mods)}: в MS4D всё открыто",
                    pou.origin.line,
                )
        return ci

    def _special(self, pou: Pou, ci: ClassInfo, m: Method) -> None:
        pd = parse_decl(m.decl_text)
        vs = collect_vars(pd.decl)
        params = [v for v in vs.values() if v.section in ("VAR_INPUT", "VAR_IN_OUT")]
        low = m.name.lower()
        if low == "fb_init" and not params and m.body is not None and m.body.lang == "ST":
            ci.fb_init = MethodInfo(m.name, pou.name, 0, None, [], [], [], list(vs.values()), m.body.text)
            self.note(pou.name, "MS-LANG-06", "verify",
                      "FB_init без параметров → ветка первого цикла IF NOT migInit (в CODESYS — при загрузке)", m.origin.line)  # fmt: skip
        else:
            ci.special.append(m.name)
            self.note(
                pou.name,
                "MS-LANG-06",
                "manual",
                f"{m.name}{' с параметрами' if params else ''}: вручную",
                m.origin.line,
            )

    def _method(self, pou: Pou, m: Method, own_vars: dict[str, VarInfo]) -> MethodInfo | None:
        pd = parse_decl(m.decl_text)
        h = pd.decl.header
        vs = collect_vars(pd.decl)
        if m.body is None:
            return None
        local_scope = {**own_vars, **vs}
        body = m.body.text if m.body.lang == "ST" else self.lower_body(pou, m.body, local_scope)
        rt = h.return_type.name if h is not None and h.return_type is not None else None
        if h is not None and h.return_type is not None:
            rt = h.return_type.text
        mi = MethodInfo(
            m.name,
            pou.name,
            0,
            rt,
            [v for v in vs.values() if v.section == "VAR_INPUT"],
            [v for v in vs.values() if v.section == "VAR_OUTPUT"],
            [v for v in vs.values() if v.section == "VAR_IN_OUT"],
            [v for v in vs.values() if v.section in ("VAR", "VAR_TEMP", "VAR_INST", "VAR_STAT")],
            body,
            m.origin.line,
        )
        for v in mi.inouts:
            if "CONSTANT" not in v.qualifiers and v.type.name == "ARRAY":
                self.note(pou.name, "MS-LANG-06", "review",
                          f"{m.name}: VAR_IN_OUT {v.name} — массив копируется при каждом вызове (цена копии в Lua)", m.origin.line)  # fmt: skip
        return mi

    def _prop(self, pou: Pou, pr: Property) -> PropInfo:
        pd = parse_decl(pr.decl_text)
        h = pd.decl.header
        typ = h.return_type.text if h is not None and h.return_type is not None else "INT"
        get_expr = None
        ok = False
        if pr.get is not None and pr.get.body is not None and pr.get.body.lang == "ST":
            pb = parse_body(pr.get.body.text)
            stmts = [s for s in pb.stmts if not isinstance(s, A.Empty)]
            if (
                len(stmts) == 1
                and isinstance(stmts[0], A.Assign)
                and isinstance(stmts[0].target, A.Name)
                and stmts[0].target.id.lower() == pr.name.lower()
                and not any(isinstance(x, A.Call) for x in A.walk_expr(stmts[0].value))
            ):
                get_expr = fmt_expr(stmts[0].value)
                ok = True
            else:
                self.note(pou.name, "MS-LANG-06", "manual", f"свойство {pr.name}: GET с побочными эффектами или не одно присваивание", pr.origin.line)  # fmt: skip
        set_body = None
        if pr.set is not None and pr.set.body is not None and pr.set.body.lang == "ST":
            set_body = pr.set.body.text
        return PropInfo(pr.name, typ, get_expr, ok, set_body)

    def _interface_aliases(self) -> None:
        """Переменные интерфейсного типа: подстановка экземпляра, если по проекту присваивается один."""
        if not self.itf_names:
            return
        assigned: dict[tuple[str, str], set[str]] = {}
        declared: list[tuple[str, str, int]] = []
        itf_types: dict[tuple[str, str], str] = {}
        for pou in self.project.pous:
            vs = collect_vars(parse_decl(pou.decl_text).decl)
            itf_vars = {k: v for k, v in vs.items() if v.type.name.lower() in self.itf_names}
            for k in itf_vars:
                declared.append((pou.name, k, pou.origin.line))
                itf_types[(pou.name.lower(), k)] = itf_vars[k].type.name
                assigned.setdefault((pou.name.lower(), k), set())
            if not itf_vars or pou.body is None or pou.body.lang != "ST":
                continue
            for s in A.walk_stmts(parse_body(pou.body.text).stmts):
                if isinstance(s, A.Assign) and isinstance(s.target, A.Name) and s.target.id.lower() in itf_vars:
                    assigned[(pou.name.lower(), s.target.id.lower())].add(fmt_expr(s.value))
        for pou_name, var, line in declared:
            vals = assigned.get((pou_name.lower(), var), set())
            if len(vals) == 1:
                inst = next(iter(vals))
                self.itf_alias[(pou_name.lower(), var)] = inst
                self.note(pou_name, "MS-LANG-06", "review", f"интерфейсная переменная {var} → экземпляр {inst}", line)
            else:
                itf_type = itf_types.get((pou_name.lower(), var), "")
                impl = [c for c, ci in self.classes.items() if itf_type.lower() in (i.lower() for i in ci.implements)]
                why = (f"{len(vals)} присваиваний разных экземпляров" if vals else
                       f"экземпляр передаётся извне, {itf_type} реализуют {len(impl)} ФБ")  # fmt: skip
                self.note(
                    pou_name,
                    "MS-LANG-06",
                    "manual",
                    f"интерфейсная переменная {var}: {why} — полиморфизм вручную",
                    line,
                )

    # ------------------------------------------------------------ тело ФБ

    def method_mapping(self, ci: ClassInfo, mi: MethodInfo) -> dict[str, str]:
        mp: dict[str, str] = {}
        for v in mi.inputs + mi.inouts:
            mp[v.name.lower()] = f"{mi.name}_{v.name}"
        for v in mi.outputs:
            mp[v.name.lower()] = f"{mi.name}_{v.name}"
        for v in mi.locals:
            mp[v.name.lower()] = f"mig{mi.name}_{v.name}"
        if mi.ret_type:
            mp[mi.name.lower()] = f"{mi.name}_ret"
        return mp

    def class_members(self, ci: ClassInfo) -> tuple[list[A.VarSection], A.Declaration | None]:
        """Секции переменных с учётом предков (предок первым)."""
        sections: list[A.VarSection] = []
        chain: list[ClassInfo] = []
        c: ClassInfo | None = ci
        while c is not None:
            chain.append(c)
            c = self.classes.get(c.parent.lower()) if c.parent else None
        for c in reversed(chain):
            if c.own_decl is not None:
                sections.extend(c.own_decl.sections)
        return sections, ci.own_decl

    def lowered_fb(self, pou: Pou, body_text: str) -> tuple[str, str] | None:
        """(объявление, тело) ФБ в режиме вызова; None — ООП нет."""
        ci = self.classes.get(pou.name.lower())
        if ci is None:
            return None
        has_oop = ci.needs_dispatch or ci.parent is not None or ci.props or ci.fb_init is not None
        if not has_oop:
            return None
        names = self.names_for(pou.name)
        sections, _ = self.class_members(ci)
        pd_text = pou.decl_text
        decl_lines = self._decl_header(pou, pd_text)
        inputs: list[str] = []
        outputs: list[str] = []
        locs: list[str] = []
        if ci.needs_dispatch:
            inputs.append("migCall : INT;")
        for mi in ci.methods.values():
            for v in mi.inputs + mi.inouts:
                inputs.append(f"{mi.name}_{v.name} : {v.type.text};")
            if mi.ret_type:
                outputs.append(f"{mi.name}_ret : {mi.ret_type};")
            for v in mi.outputs:
                outputs.append(f"{mi.name}_{v.name} : {v.type.text};")
            for v in mi.inouts:
                if "CONSTANT" not in v.qualifiers:
                    outputs.append(f"{mi.name}_{v.name}Out : {v.type.text};")
            for v in mi.locals:
                init = f" := {fmt_expr(v.decl.init)}" if v.decl.init is not None else ""
                locs.append(f"mig{mi.name}_{v.name} : {v.type.text}{init};")
        for p in ci.props.values():
            if p.get_expr is not None:
                outputs.append(f"{p.name} : {p.type};")
            if p.set_body is not None:
                inputs.append(f"{p.name}_in : {p.type};")
        if ci.fb_init is not None:
            locs.append("migInit : BOOL;")
            for v in ci.fb_init.locals:
                locs.append(f"migFB_init_{v.name} : {v.type.text};")
        decl = decl_lines
        src_text = pd_text
        for sec in sections:
            decl += self._section_text(sec, src_text if sec in (ci.own_decl.sections if ci.own_decl else []) else None)
        if inputs:
            decl += "VAR_INPUT\n" + "".join(f"    {x}\n" for x in inputs) + "END_VAR\n"
        if outputs:
            decl += "VAR_OUTPUT\n" + "".join(f"    {x}\n" for x in outputs) + "END_VAR\n"
        if locs:
            decl += "VAR\n" + "".join(f"    {x}\n" for x in locs) + "END_VAR\n"

        prop_update = "".join(f"{p.name} := {p.get_expr};\n" for p in ci.props.values() if p.get_expr is not None)
        out = ""
        if ci.fb_init is not None:
            init_body = rename_idents(
                ci.fb_init.body, {v.name.lower(): f"migFB_init_{v.name}" for v in ci.fb_init.locals}
            )
            out += "IF NOT migInit THEN\n    migInit := TRUE;\n" + _indent(init_body.strip() + "\n") + "END_IF;\n"
        if ci.needs_dispatch:
            out += "(* cds2ms: MS-LANG-06 режим вызова методов *)\nIF migCall <> 0 THEN\n    CASE migCall OF\n"
            for mi in sorted(ci.methods.values(), key=lambda m: m.index):
                mp = self.method_mapping(ci, mi)
                code = self._own_calls(pou, ci, rename_idents(mi.body, mp), names, stack=[f"{mi.owner}.{mi.name}".lower()],
                                       owner=self.classes.get(mi.owner.lower()))  # fmt: skip
                copy_back = "".join(
                    f"{mi.name}_{v.name}Out := {mi.name}_{v.name};\n"
                    for v in mi.inouts
                    if "CONSTANT" not in v.qualifiers
                )
                code = self._returns(code, copy_back + prop_update + "migCall := 0;\n")
                reinit = ""
                for v in mi.locals:
                    init_val = fmt_expr(v.decl.init) if v.decl.init is not None else _default(v.type.name)
                    if init_val is not None:
                        reinit += f"mig{mi.name}_{v.name} := {init_val};\n"
                out += f"        {mi.index}: (* {mi.name} *)\n" + _indent(reinit + code.strip() + "\n" + copy_back, 3)
            for p in ci.props.values():
                if p.set_body is not None:
                    code = rename_idents(p.set_body, {p.name.lower(): f"{p.name}_in"})
                    code = self._own_calls(pou, ci, code, names, stack=[])
                    out += f"        {p.set_index}: (* {p.name} SET *)\n" + _indent(code.strip() + "\n", 3)
            out += "    END_CASE;\n" + _indent(prop_update) + "    migCall := 0;\n    RETURN;\nEND_IF;\n"
        main = body_text
        if ci.parent is not None:
            main = self._super_body(pou, ci, main)
        main = self._own_calls(pou, ci, main, names, stack=[])
        main = self._returns(main, prop_update)
        out += main
        if prop_update:
            out += ("" if out.endswith("\n") else "\n") + prop_update
        for sp in ci.special:
            out = f"(* cds2ms: MS-LANG-06 {sp} не перенесён — вручную *)\n" + out
        extra = self.extra_locals.pop(pou.name.lower(), [])
        if extra:
            uniq = list(dict.fromkeys(extra))
            decl += "VAR\n" + "".join(f"    {n} : {t};\n" for n, t in uniq) + "END_VAR\n"
        return decl, out

    def _decl_header(self, pou: Pou, text: str) -> str:
        pd = parse_decl(text)
        h = pd.decl.header
        lead = text[: pd.tokens[h.start].offset] if h is not None else ""
        return f"{lead}FUNCTION_BLOCK {pou.name}\n"

    @staticmethod
    def _section_text(sec: A.VarSection, _src: str | None) -> str:
        quals = "".join(f" {q}" for q in sec.qualifiers)
        out = f"{sec.kind}{quals}\n"
        for d in sec.decls:
            at = f" AT {d.at}" if d.at else ""
            init = f" := {fmt_expr(d.init)}" if d.init is not None else ""
            out += f"    {', '.join(d.names)}{at} : {d.type.text}{init};\n"
        return out + "END_VAR\n"

    def _super_body(self, pou: Pou, ci: ClassInfo, body: str) -> str:
        parent = self.fbs.get(ci.parent.lower()) if ci.parent else None
        if parent is None or parent.body is None:
            return body
        pbody = parent.body.text if parent.body.lang == "ST" else self.lower_body(parent, parent.body, {})
        pb = parse_body(body)
        calls = [
            s for s in A.walk_stmts(pb.stmts)
            if isinstance(s, A.CallStmt) and isinstance(s.call.func, A.Deref) and isinstance(s.call.func.obj, A.Name)
            and s.call.func.obj.id.upper() == "SUPER"
        ]  # fmt: skip
        if not calls:
            return body
        if any(isinstance(x, A.Return) for x in A.walk_stmts(parse_body(pbody).stmts)):
            self.note(pou.name, "MS-LANG-06", "manual", f"SUPER^(): в теле {parent.name} есть RETURN — встраивание вручную",
                      pou.origin.line)  # fmt: skip
            return body
        self.note(pou.name, "MS-LANG-06", "review", f"SUPER^() → тело {parent.name} встроено", pou.origin.line)
        repl: dict[int, tuple[int, str]] = {}
        for s in calls:
            assigns = "".join(
                f"{a.name} := {fmt_expr(a.value)};\n" for a in s.call.args if a.name and not a.output
                and fmt_expr(a.value).lower() != a.name.lower()
            )  # fmt: skip
            outs = "".join(f"{fmt_expr(a.value)} := {a.name};\n" for a in s.call.args if a.name and a.output)
            repl[s.start] = (s.end, f"(* SUPER^() *)\n{assigns}{pbody.strip()}\n{outs}")
        out = []
        skip_to = -1
        for i, t in enumerate(pb.tokens):
            if i < skip_to:
                continue
            if i in repl:
                end, text = repl[i]
                out.append(text.rstrip("\n"))
                skip_to = end
                continue
            out.append(t.text)
        return "".join(out)

    def _returns(self, code: str, before: str) -> str:
        if not before:
            return code
        pb = parse_body(code)
        if not any(isinstance(s, A.Return) for s in A.walk_stmts(pb.stmts)):
            return code
        toks = pb.tokens
        out = []
        idx = {s.start: s for s in A.walk_stmts(pb.stmts) if isinstance(s, A.Return)}
        skip_to = -1
        for i, t in enumerate(toks):
            if i < skip_to:
                continue
            if i in idx:
                s = idx[i]
                out.append(before.replace("\n", " ") + "RETURN;")
                skip_to = s.end
                continue
            out.append(t.text)
        return "".join(out)

    def _own_calls(
        self, pou: Pou, ci: ClassInfo, code: str, names: Names, stack: list[str], owner: ClassInfo | None = None
    ) -> str:
        """Встраивание вызовов своих методов (M(), THIS^.M(), SUPER^.M()) — только операторами-вызовами."""
        pb = parse_body(code)
        edits: list[tuple[int, int, str]] = []  # (токен начала, токен конца, текст); вставка — start == end
        for s in A.walk_stmts(pb.stmts):
            if isinstance(s, A.CallStmt):
                m = self._own_method(ci, s.call.func, owner)
                if m is not None:
                    text = self._inline(pou, ci, m[0], m[1], s.call, names, stack)
                    if text is not None:
                        outs = "".join(
                            f"{fmt_expr(a.value)} := {m[0].name}_{a.name};\n" for a in s.call.args if a.output and a.name
                        )  # fmt: skip
                        edits.append((s.start, s.end, (text + outs).rstrip("\n")))
                continue
            exprs: list[A.Expr]
            if isinstance(s, A.Assign):
                exprs = [s.target, s.value]
            elif isinstance(s, A.If):
                exprs = [s.branches[0][0]]
            elif isinstance(s, A.Case):
                exprs = [s.selector]
            else:
                exprs = []
            own = [
                x
                for ex in exprs
                for x in A.walk_expr(ex)
                if isinstance(x, A.Call) and self._own_method(ci, x.func, owner)
            ]
            other = [
                x for ex in A.stmt_exprs(s) for x in A.walk_expr(ex)
                if isinstance(x, A.Call) and self._own_method(ci, x.func, owner) and x not in own
            ]  # fmt: skip
            for x in other:
                self.note(pou.name, "MS-LANG-06", "manual",
                          f"вызов своего метода в условии ELSIF/WHILE/REPEAT: {fmt_expr(x)} — вручную", pou.origin.line)  # fmt: skip
            if not own:
                continue
            outer = [c for c in own if not any(c is not o and o.start <= c.start and c.end <= o.end for o in own)]
            pre = ""
            local_edits: list[tuple[int, int, str]] = []
            ok = True
            for c in outer:
                m = self._own_method(ci, c.func, owner)
                assert m is not None
                text = self._inline(pou, ci, m[0], m[1], c, names, stack)
                if text is None:
                    ok = False
                    break
                pre += text
                local_edits.append((c.start, c.end, f"{m[0].name}_ret" if m[0].ret_type else "TRUE"))
            if ok:
                edits.append((s.start, s.start, pre))
                edits.extend(local_edits)
        if not edits:
            return code
        return _apply_token_edits(pb, edits)

    def _inline(
        self, pou: Pou, ci: ClassInfo, mi: MethodInfo, is_super: bool, call: A.Call, names: Names, stack: list[str]
    ) -> str | None:
        """Текст встраивания своего метода: входы, тело в именах ФБ; None — вручную (рекурсия, RETURN)."""
        key = f"{mi.owner}.{mi.name}".lower()
        if key in stack:
            self.note(pou.name, "MS-LANG-06", "manual", f"рекурсия метода {mi.name}", pou.origin.line)
            return None
        mp = self.method_mapping(ci, mi)
        if is_super:  # тело предка: свои локальные имена, чтобы не столкнуться с переопределением
            for v in mi.locals:
                mp[v.name.lower()] = f"migSuper{mi.name}_{v.name}"
                self.extra_locals.setdefault(pou.name.lower(), []).append((mp[v.name.lower()], v.type.text))
        assigns = ""
        ins = mi.inputs + mi.inouts
        pos = 0
        for a in call.args:
            if a.output:
                continue
            if a.name is None:
                if pos < len(ins):
                    assigns += f"{mi.name}_{ins[pos].name} := {fmt_expr(a.value)};\n"
                pos += 1
            else:
                assigns += f"{mi.name}_{a.name} := {fmt_expr(a.value)};\n"
        body = rename_idents(mi.body, mp)
        if any(isinstance(x, A.Return) for x in A.walk_stmts(parse_body(body).stmts)):
            self.note(
                pou.name, "MS-LANG-06", "manual", f"встраивание {mi.name}: RETURN в теле — вручную", pou.origin.line
            )
            return None
        mowner = self.classes.get(mi.owner.lower())
        inner = self._own_calls(pou, ci, assigns + body.strip() + "\n", names, [*stack, key], mowner)
        self.note(pou.name, "MS-LANG-06", "review", f"вызов своего метода {mi.name} встроен", pou.origin.line)
        return f"(* {'SUPER^.' if is_super else ''}{mi.name}() встроен *)\n{inner}"

    def _own_method(
        self, ci: ClassInfo, func: A.Expr, owner: ClassInfo | None = None
    ) -> tuple[MethodInfo, bool] | None:
        """M() и THIS^.M() — самое производное переопределение (ci); SUPER^.M() — предок класса-владельца тела."""
        if isinstance(func, A.Name):
            m = ci.methods.get(func.id.lower())
            return (m, False) if m is not None else None
        if isinstance(func, A.Member) and isinstance(func.obj, A.Deref) and isinstance(func.obj.obj, A.Name):
            base = func.obj.obj.id.upper()
            if base == "THIS":
                m = ci.methods.get(func.name.lower())
                return (m, False) if m is not None else None
            own_cls = owner or ci
            if base == "SUPER" and own_cls.parent:
                pc = self.classes.get(own_cls.parent.lower())
                m = pc.methods.get(func.name.lower()) if pc else None
                return (m, True) if m is not None else None
        return None

    # ------------------------------------------------------------ места вызова

    def aliased_vars(self, pou_name: str) -> list[str]:
        return [v for (p, v) in self.itf_alias if p == pou_name.lower()]

    def rewrite_calls(self, pou_name: str, body: str, local: dict[str, VarInfo], names: Names) -> str:
        """Вызовы методов чужих экземпляров и запись свойств → режим вызова."""
        if not self.classes:
            return body
        rw = _CallRewriter(self, pou_name, local, names)
        out = rw.run(body)
        if rw.temps:
            self.temps.setdefault(pou_name.lower(), []).extend(rw.temps)
        return out


class _CallRewriter:
    def __init__(self, low: OopLowering, pou: str, local: dict[str, VarInfo], names: Names) -> None:
        self.low = low
        self.pou = pou
        self.local = local
        self.names = names
        self.temps: list[tuple[str, str]] = []

    def inst_class(self, e: A.Expr) -> ClassInfo | None:
        if isinstance(e, A.Name):
            alias = self.low.itf_alias.get((self.pou.lower(), e.id.lower()))
            if alias is not None:
                try:
                    return self.inst_class(parse_expression(alias))
                except ParseError:
                    return None
            v = self.local.get(e.id.lower())
            if v is None:
                return None
            return self.low.classes.get(v.type.name.lower())
        if isinstance(e, A.Index) and isinstance(e.obj, A.Name):
            v = self.local.get(e.obj.id.lower())
            if v is not None and v.type.name == "ARRAY" and v.type.elem is not None:
                return self.low.classes.get(v.type.elem.name.lower())
        return None

    def obj_text(self, e: A.Expr) -> str:
        if isinstance(e, A.Name):
            alias = self.low.itf_alias.get((self.pou.lower(), e.id.lower()))
            if alias is not None:
                return alias
        return fmt_expr(e)

    def method_call(self, e: A.Expr) -> tuple[A.Expr, ClassInfo, MethodInfo, A.Call] | None:
        if isinstance(e, A.Call) and isinstance(e.func, A.Member):
            obj = e.func.obj
            ci = self.inst_class(obj)
            if ci is not None:
                mi = ci.methods.get(e.func.name.lower())
                if mi is not None:
                    return obj, ci, mi, e
        return None

    def has_oop(self, s: A.Stmt) -> bool:
        for st in A.walk_stmts([s]):
            if isinstance(st, A.Assign) and self.prop_set(st.target) is not None:
                return True
            for ex in A.stmt_exprs(st):
                for x in A.walk_expr(ex):
                    if self.method_call(x) is not None:
                        return True
                    if isinstance(x, A.Name) and (self.pou.lower(), x.id.lower()) in self.low.itf_alias:
                        return True
        return False

    def prop_set(self, target: A.Expr) -> tuple[A.Expr, ClassInfo, PropInfo] | None:
        if isinstance(target, A.Member):
            ci = self.inst_class(target.obj)
            if ci is not None:
                p = ci.props.get(target.name.lower())
                if p is not None and p.set_body is not None:
                    return target.obj, ci, p
        return None

    def call_text(self, obj: A.Expr, mi: MethodInfo, call: A.Call, pre: list[str]) -> tuple[str, list[str]]:
        args = [f"migCall := {mi.index}"]
        post: list[str] = []
        ins = mi.inputs + mi.inouts
        pos = 0
        for a in call.args:
            if a.output:
                if a.name:
                    post.append(f"{fmt_expr(a.value)} := {self.obj_text(obj)}.{mi.name}_{a.name};")
                continue
            val = self.expr(a.value, pre)
            if a.name is None:
                if pos < len(ins):
                    tgt = ins[pos]
                    args.append(f"{mi.name}_{tgt.name} := {fmt_expr(val)}")
                    if tgt in mi.inouts and "CONSTANT" not in tgt.qualifiers:
                        post.append(f"{fmt_expr(a.value)} := {self.obj_text(obj)}.{mi.name}_{tgt.name}Out;")
                pos += 1
            else:
                args.append(f"{mi.name}_{a.name} := {fmt_expr(val)}")
                tgt2 = next((v for v in mi.inouts if v.name.lower() == a.name.lower()), None)
                if tgt2 is not None and "CONSTANT" not in tgt2.qualifiers:
                    post.append(f"{fmt_expr(a.value)} := {self.obj_text(obj)}.{mi.name}_{tgt2.name}Out;")
        return f"{self.obj_text(obj)}({', '.join(args)});", post

    def expr(self, e: A.Expr, pre: list[str]) -> A.Expr:
        """Подъём вызовов методов из выражения в ``pre`` слева направо."""
        mc = self.method_call(e)
        if mc is not None:
            obj, _ci, mi, call = mc
            text, post = self.call_text(obj, mi, call, pre)
            pre.append(text)
            pre.extend(post)
            if not mi.ret_type:
                return A.Literal("bool", "TRUE")
            tmp = self.names.new(f"migT{len(self.temps) + 1}")
            self.temps.append((tmp, mi.ret_type))
            pre.append(f"{tmp} := {self.obj_text(obj)}.{mi.name}_ret;")
            return A.Name(tmp)
        if isinstance(e, A.Name):
            alias = self.low.itf_alias.get((self.pou.lower(), e.id.lower()))
            if alias is not None:
                try:
                    return parse_expression(alias)
                except ParseError:
                    return e
            return e
        if isinstance(e, A.Binary):
            if e.op in ("AND_THEN", "OR_ELSE") and _has_call(e.right, self):
                self.low.note(self.pou, "MS-LANG-06", "manual", f"вызов метода справа от {e.op}: вручную")
            left = self.expr(e.left, pre)
            right = self.expr(e.right, pre)
            return A.Binary(e.op, left, right)
        if isinstance(e, A.Unary):
            return A.Unary(e.op, self.expr(e.operand, pre))
        if isinstance(e, A.Member):
            return A.Member(self.expr(e.obj, pre), e.name)
        if isinstance(e, A.Index):
            return A.Index(self.expr(e.obj, pre), [self.expr(i, pre) for i in e.indices])
        if isinstance(e, A.Call):
            args = [
                A.Arg(a.name, self.expr(a.value, pre) if not a.output else a.value, a.output, a.negated) for a in e.args
            ]
            return A.Call(self.expr(e.func, pre), args)
        return e

    def stmts(self, body: list[A.Stmt]) -> list[str]:
        out: list[str] = []
        for s in body:
            out.extend(self.stmt(s))
        return out

    def stmt(self, s: A.Stmt) -> list[str]:
        pre: list[str] = []
        if isinstance(s, A.Assign):
            if isinstance(s.target, A.Name) and (self.pou.lower(), s.target.id.lower()) in self.low.itf_alias:
                return [f"(* {s.target.id} := {fmt_expr(s.value)}: интерфейс заменён экземпляром (MS-LANG-06) *)"]
            ps = self.prop_set(s.target)
            if ps is not None:
                obj, _ci, p = ps
                val = self.expr(s.value, pre)
                return [*pre, f"{self.obj_text(obj)}(migCall := {p.set_index}, {p.name}_in := {fmt_expr(val)});"]
            mc = self.method_call(s.value)
            if mc is not None and s.op == ":=":
                obj, _ci, mi, call = mc
                text, post = self.call_text(obj, mi, call, pre)
                tgt = fmt_expr(self.expr(s.target, pre))
                return [*pre, text, *post, f"{tgt} := {self.obj_text(obj)}.{mi.name}_ret;"]
            val = self.expr(s.value, pre)
            tgt = fmt_expr(self.expr(s.target, pre))
            return [*pre, f"{tgt} {s.op} {fmt_expr(val)};"]
        if isinstance(s, A.CallStmt):
            mc = self.method_call(s.call)
            if mc is not None:
                obj, _ci, mi, call = mc
                text, post = self.call_text(obj, mi, call, pre)
                return [*pre, text, *post]
            e = self.expr(s.call, pre)
            return [*pre, f"{fmt_expr(e)};"]
        if isinstance(s, A.If):
            return self._if(s.branches, s.else_body)
        if isinstance(s, A.While):
            cond = self.expr(s.cond, pre)
            body = self.stmts(s.body)
            if pre:
                return ["WHILE TRUE DO", *_ind(pre), f"    IF NOT ({fmt_expr(cond)}) THEN", "        EXIT;", "    END_IF;",
                        *_ind(body), "END_WHILE;"]  # fmt: skip
            return [f"WHILE {fmt_expr(cond)} DO", *_ind(body), "END_WHILE;"]
        if isinstance(s, A.Repeat):
            body = self.stmts(s.body)
            cond = self.expr(s.cond, pre)
            return ["REPEAT", *_ind(body), *_ind(pre), f"UNTIL {fmt_expr(cond)}", "END_REPEAT;"]
        if isinstance(s, A.For):
            first = self.expr(s.first, pre)
            last = self.expr(s.last, pre)
            step = self.expr(s.step, pre) if s.step is not None else None
            by = f" BY {fmt_expr(step)}" if step is not None else ""
            return [
                *pre,
                f"FOR {s.var} := {fmt_expr(first)} TO {fmt_expr(last)}{by} DO",
                *_ind(self.stmts(s.body)),
                "END_FOR;",
            ]
        if isinstance(s, A.Case):
            sel = self.expr(s.selector, pre)
            out = [*pre, f"CASE {fmt_expr(sel)} OF"]
            for labels, br_body in s.branches:
                labs = ", ".join(
                    fmt_expr(lab.low) + (f"..{fmt_expr(lab.high)}" if lab.high is not None else "") for lab in labels
                )
                out.append(f"    {labs}:")
                out.extend(_ind(self.stmts(br_body), 2))
            if s.else_body is not None:
                out.append("ELSE")
                out.extend(_ind(self.stmts(s.else_body), 2))
            out.append("END_CASE;")
            return out
        return fmt_stmts([s]).rstrip("\n").split("\n")

    def _if(self, branches: list[tuple[A.Expr, list[A.Stmt]]], else_body: list[A.Stmt] | None) -> list[str]:
        cond0, body0 = branches[0]
        pre: list[str] = []
        c = self.expr(cond0, pre)
        out = [*pre, f"IF {fmt_expr(c)} THEN", *_ind(self.stmts(body0))]
        rest = branches[1:]
        if rest:
            pre2: list[str] = []
            c2 = self.expr(rest[0][0], pre2)
            if pre2:
                out.append("ELSE")
                out.extend(_ind(self._if(rest, else_body)))
                out.append("END_IF;")
                return out
            out.append(f"ELSIF {fmt_expr(c2)} THEN")
            out.extend(_ind(self.stmts(rest[0][1])))
            for cond, body in rest[1:]:
                p3: list[str] = []
                c3 = self.expr(cond, p3)
                if p3:
                    out.append("ELSE")
                    out.extend(_ind(self._if([(cond, body), *rest[rest.index((cond, body)) + 1 :]], else_body)))
                    out.append("END_IF;")
                    return out
                out.append(f"ELSIF {fmt_expr(c3)} THEN")
                out.extend(_ind(self.stmts(body)))
        if else_body is not None:
            out.append("ELSE")
            out.extend(_ind(self.stmts(else_body)))
        out.append("END_IF;")
        return out

    def run(self, body: str) -> str:
        pb: ParsedBody = parse_body(body)
        if not any(self.has_oop(s) for s in pb.stmts):
            return body
        out: list[str] = []
        prev_end = 0
        for s in pb.stmts:
            if not self.has_oop(s):
                continue
            a = pb.tokens[s.start].offset
            b = pb.tokens[s.end - 1].end
            out.append(body[prev_end:a])
            line_start = body.rfind("\n", 0, a) + 1
            pad = body[line_start:a] if body[line_start:a].strip() == "" else ""
            lines = self.stmt(s)
            out.append(("\n" + pad).join(lines))
            prev_end = b
        out.append(body[prev_end:])
        return "".join(out)


def _has_call(e: A.Expr, rw: _CallRewriter) -> bool:
    return any(rw.method_call(x) is not None for x in A.walk_expr(e))


def _ind(lines: list[str], n: int = 1) -> list[str]:
    return ["    " * n + ln for ln in lines]


def _indent(text: str, n: int = 1) -> str:
    pad = "    " * n
    return "".join(pad + ln if ln.strip() else ln for ln in text.splitlines(keepends=True))


def _default(type_name: str) -> str | None:
    up = type_name.upper()
    if up == "BOOL":
        return "FALSE"
    if up in ("REAL", "LREAL"):
        return "0.0"
    if up in ("TIME",):
        return "T#0MS"
    if up in ("LTIME",):
        return "LTIME#0NS"
    if up in ("STRING", "WSTRING"):
        return "''" if up == "STRING" else '""'
    from ..stdlib import INT_TYPES

    if up in INT_TYPES:
        return "0"
    return None


def _apply_token_edits(pb: ParsedBody, edits: list[tuple[int, int, str]]) -> str:
    """Правки по индексам токенов: (start, end, текст); start == end — вставка перед токеном start."""
    by_start: dict[int, list[tuple[int, str]]] = {}
    for a, b, t in edits:
        by_start.setdefault(a, []).append((b, t))
    out: list[str] = []
    skip_to = -1
    for i, tok in enumerate(pb.tokens):
        if i in by_start:
            for b, t in sorted(by_start[i], key=lambda x: x[0]):
                if b == i:
                    out.append(t)
                elif i >= skip_to:
                    out.append(t)
                    skip_to = b
        if i < skip_to:
            continue
        out.append(tok.text)
    return "".join(out)
