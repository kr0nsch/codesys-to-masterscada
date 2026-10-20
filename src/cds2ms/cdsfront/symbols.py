"""Таблица символов проекта: разобранные объявления POU, DUT, GVL и вывод типов выражений."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..ir.model import Pou, Project
from .st import ast as A
from .st.parser import ParsedDecl, parse_decl
from .stdlib import BOOL_RESULT_OPS, INT_TYPES, REAL_TYPES, STD_FBS, common_type, is_conversion


@dataclass
class VarInfo:
    name: str
    section: str  # VAR_INPUT ...
    type: A.TypeRef
    decl: A.VarDecl
    qualifiers: list[str] = field(default_factory=list)

    @property
    def type_name(self) -> str:
        return self.type.name


@dataclass
class PouSymbols:
    name: str
    kind: str
    parsed: ParsedDecl
    vars: dict[str, VarInfo]  # имя в нижнем регистре
    return_type: str | None = None

    def inputs(self) -> list[VarInfo]:
        return [v for v in self.vars.values() if v.section == "VAR_INPUT"]

    def outputs(self) -> list[VarInfo]:
        return [v for v in self.vars.values() if v.section == "VAR_OUTPUT"]


def collect_vars(decl: A.Declaration) -> dict[str, VarInfo]:
    out: dict[str, VarInfo] = {}
    for sec in decl.sections:
        for d in sec.decls:
            for n in d.names:
                out[n.lower()] = VarInfo(n, sec.kind, d.type, d, list(sec.qualifiers))
    return out


class Symbols:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.pous: dict[str, PouSymbols] = {}
        self.types: dict[str, A.TypeDecl] = {}
        self.gvls: dict[str, dict[str, VarInfo]] = {}
        self.gvl_parsed: dict[str, ParsedDecl] = {}
        self.global_vars: dict[str, tuple[str, VarInfo]] = {}
        self.interfaces = {i.name.lower(): i for i in project.interfaces}
        for d in project.duts:
            for td in parse_decl(d.decl_text).decl.types:
                self.types[td.name.lower()] = td
        for g in project.gvls:
            pd = parse_decl(g.decl_text)
            self.gvl_parsed[g.name.lower()] = pd
            vs = collect_vars(pd.decl)
            self.gvls[g.name.lower()] = vs
            for k, v in vs.items():
                self.global_vars.setdefault(k, (g.name, v))
        for p in project.pous:
            self.add_pou(p)

    def add_pou(self, p: Pou, decl_text: str | None = None) -> PouSymbols:
        pd = parse_decl(decl_text if decl_text is not None else p.decl_text)
        h = pd.decl.header
        rt = h.return_type.name if h is not None and h.return_type is not None else None
        ps = PouSymbols(p.name, p.kind, pd, collect_vars(pd.decl), rt)
        self.pous[p.name.lower()] = ps
        return ps

    # ------------------------------------------------------------ интерфейсы ФБ

    def fb_pins(self, type_name: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]] | None:
        up = type_name.upper().split(".")[-1]
        if up in STD_FBS:
            return STD_FBS[up]
        ps = self.pous.get(type_name.lower().split(".")[-1])
        if ps is None or ps.kind != "functionBlock":
            return None
        ins = [(v.name, v.type_name) for v in ps.vars.values() if v.section in ("VAR_INPUT", "VAR_IN_OUT")]
        outs = [(v.name, v.type_name) for v in ps.vars.values() if v.section in ("VAR_OUTPUT", "VAR_IN_OUT")]
        return ins, outs

    def is_fb_type(self, type_name: str) -> bool:
        up = type_name.upper().split(".")[-1]
        if up in STD_FBS:
            return True
        ps = self.pous.get(type_name.lower().split(".")[-1])
        return ps is not None and ps.kind == "functionBlock"

    def function_return(self, name: str) -> str | None:
        ps = self.pous.get(name.lower())
        if ps is not None and ps.kind == "function":
            return ps.return_type
        return None

    # ------------------------------------------------------------ вывод типов

    def var_type(self, name: str, local: dict[str, VarInfo]) -> A.TypeRef | None:
        v = local.get(name.lower())
        if v is not None:
            return v.type
        g = self.global_vars.get(name.lower())
        return g[1].type if g is not None else None

    def member_type(self, base: A.TypeRef | None, member: str) -> A.TypeRef | None:
        if base is None:
            return None
        if member.isdigit():
            return A.TypeRef("BOOL", "BOOL")
        tn = base.name
        pins = self.fb_pins(tn)
        if pins is not None:
            for n, t in pins[0] + pins[1]:
                if n.lower() == member.lower():
                    return A.TypeRef(t, t)
            ps = self.pous.get(tn.lower())
            if ps is not None and member.lower() in ps.vars:
                return ps.vars[member.lower()].type
            return None
        td = self.types.get(tn.lower())
        if td is not None and td.kind in ("STRUCT", "UNION"):
            for f in td.fields:
                if member.lower() in (n.lower() for n in f.names):
                    return f.type
        return None

    def expr_type(self, e: A.Expr, local: dict[str, VarInfo]) -> str | None:
        t = self.expr_typeref(e, local)
        return t.name if t is not None else None

    def expr_typeref(self, e: A.Expr, local: dict[str, VarInfo]) -> A.TypeRef | None:
        if isinstance(e, A.Literal):
            k = e.kind
            if k == "typed" and e.type_prefix:
                tp = e.type_prefix.upper()
                if tp in INT_TYPES or tp in REAL_TYPES or tp == "BOOL":
                    return A.TypeRef(tp, tp)
                return A.TypeRef(e.type_prefix, e.type_prefix)
            name = {
                "int": "INT",
                "real": "REAL",
                "bool": "BOOL",
                "string": "STRING",
                "wstring": "WSTRING",
                "time": "TIME",
                "ltime": "LTIME",
                "date": "DATE",
                "tod": "TOD",
                "dt": "DT",
            }.get(k)
            if k == "int":
                try:
                    v = int(e.text.replace("_", "").split("#")[-1], 0 if "#" not in e.text else 16)
                except ValueError:
                    v = 0
                name = "INT" if -32768 <= v <= 32767 else "DINT"
            return A.TypeRef(name, name) if name else None
        if isinstance(e, A.Name):
            return self.var_type(e.id, local)
        if isinstance(e, A.Member):
            if isinstance(e.obj, A.Name) and e.obj.id.lower() in self.types:
                return A.TypeRef(e.obj.id, e.obj.id)  # E_State.Run
            if isinstance(e.obj, A.Name) and e.obj.id.lower() in self.gvls:
                gv = self.gvls[e.obj.id.lower()].get(e.name.lower())
                return gv.type if gv is not None else None
            return self.member_type(self.expr_typeref(e.obj, local), e.name)
        if isinstance(e, A.Index):
            base = self.expr_typeref(e.obj, local)
            if base is not None and base.name == "ARRAY":
                return base.elem
            return None
        if isinstance(e, A.Unary):
            if e.op == "NOT":
                return self.expr_typeref(e.operand, local)
            return self.expr_typeref(e.operand, local)
        if isinstance(e, A.Binary):
            if e.op in ("=", "<>", "<", ">", "<=", ">=", "AND_THEN", "OR_ELSE"):
                return A.TypeRef("BOOL", "BOOL")
            a = self.expr_type(e.left, local)
            b = self.expr_type(e.right, local)
            if e.op in ("AND", "OR", "XOR", "&") and (a == "BOOL" or b == "BOOL"):
                return A.TypeRef("BOOL", "BOOL")
            c = common_type(a, b)
            return A.TypeRef(c, c) if c else None
        if isinstance(e, A.Call) and isinstance(e.func, A.Name):
            fn = e.func.id
            conv = is_conversion(fn)
            if conv is not None:
                return A.TypeRef(conv[1], conv[1])
            up = fn.upper()
            if up in BOOL_RESULT_OPS:
                return A.TypeRef("BOOL", "BOOL")
            if up in ("LIMIT", "MAX", "MIN", "SEL", "MUX", "ABS", "MOVE"):
                arg_exprs = [x.value for x in e.args]
                if up == "SEL" or up == "MUX":
                    arg_exprs = arg_exprs[1:]
                t: str | None = None
                for ax in arg_exprs:
                    t = common_type(t, self.expr_type(ax, local))
                return A.TypeRef(t, t) if t else None
            if up in ("SQRT", "LN", "LOG", "EXP", "SIN", "COS", "TAN", "EXPT"):
                return A.TypeRef("REAL", "REAL")
            if up == "TRUNC":
                return A.TypeRef("DINT", "DINT")
            if up == "LEN":
                return A.TypeRef("INT", "INT")
            if up in ("CONCAT", "LEFT", "RIGHT", "MID", "INSERT", "DELETE", "REPLACE"):
                return A.TypeRef("STRING", "STRING")
            rt = self.function_return(fn)
            return A.TypeRef(rt, rt) if rt else None
        return None
