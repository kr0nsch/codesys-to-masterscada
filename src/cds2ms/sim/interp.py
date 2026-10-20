"""Интерпретатор ST над AST cdsfront с виртуальным временем (целые мс) и профилем семантики.

Исполняет понижённый ST (без методов: ООП уже сплющено): ПРОГРАММЫ, ФБ, функции, GVL, структуры, массивы,
перечисления, стандартные ФБ (TON, TOF, TP, R_TRIG, F_TRIG, RS, SR, CTU, CTD, CTUD) и функции Standard.
Настенные часы не читаются: время задаёт вызывающий (``now_ms``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..cdsfront.st import ast as A
from ..cdsfront.st.parser import parse_body, parse_decl
from ..cdsfront.stdlib import INT_TYPES, STD_FBS, is_conversion
from .semantics import Semantics, SimError, coerce, f32, real_to_int, wrap_int


class _Exit(Exception):
    pass


class _Continue(Exception):
    pass


class _Return(Exception):
    pass


@dataclass
class Arr:
    low: int
    high: int
    elem: A.TypeRef
    items: list[Any]

    def idx(self, i: int, sem: Semantics) -> int | None:
        if not self.low <= i <= self.high:
            if sem.array_oob == "null":
                return None
            raise SimError(f"индекс {i} вне [{self.low}..{self.high}]")
        return i - self.low


@dataclass
class Obj:
    """Экземпляр ФБ/программы, структура или набор глобальных."""

    type_name: str
    kind: str  # fb | program | struct | std
    vars: dict[str, Any] = field(default_factory=dict)
    types: dict[str, A.TypeRef] = field(default_factory=dict)
    sections: dict[str, str] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class PouDef:
    name: str
    kind: str  # program | functionBlock | function
    decl: A.Declaration
    body: list[A.Stmt]
    return_type: A.TypeRef | None


def literal_value(lit: A.Literal, sem: Semantics) -> Any:
    k, t = lit.kind, lit.text
    if k == "bool":
        return t.upper() == "TRUE"
    if k == "int":
        return _int_text(t)
    if k == "real":
        return float(t.replace("_", ""))
    if k in ("string", "wstring"):
        return _unescape(t[1:-1])
    if k in ("time", "ltime"):
        val = t.split("#", 1)[1]
        ms = parse_duration_ms(val)
        return int(round(ms * 1_000_000)) if k == "ltime" else int(round(ms))
    if k == "dt" or k == "date" or k == "tod":
        return _parse_dt(k, t.split("#", 1)[1])
    if k == "typed":
        prefix, _, val = t.partition("#")
        up = prefix.upper()
        if up in INT_TYPES:
            return _int_text(val)
        if up in ("REAL", "LREAL"):
            return float(val.replace("_", ""))
        if up == "BOOL":
            return val.upper() in ("TRUE", "1")
        return ("enum", prefix, val)
    if k == "null":
        return None
    raise SimError(f"литерал {t}")


def _int_text(t: str) -> int:
    t = t.replace("_", "")
    neg = t.startswith("-")
    t = t.lstrip("+-")
    if "#" in t:
        base, val = t.split("#", 1)
        v = int(val, int(base))
    else:
        v = int(t)
    return -v if neg else v


def _unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "$" and i + 1 < len(s):
            n = s[i + 1]
            m = {"$": "$", "'": "'", '"': '"', "N": "\n", "n": "\n", "L": "\n", "l": "\n", "R": "\r", "r": "\r",
                 "T": "\t", "t": "\t", "P": "\f", "p": "\f"}.get(n)  # fmt: skip
            if m is not None:
                out.append(m)
                i += 2
                continue
            if i + 2 < len(s):
                try:
                    out.append(chr(int(s[i + 1 : i + 3], 16)))
                    i += 3
                    continue
                except ValueError:
                    pass
        out.append(c)
        i += 1
    return "".join(out)


def parse_duration_ms(val: str) -> float:
    import re

    v = val.replace("_", "")
    neg = v.startswith("-")
    v = v.lstrip("+-")
    total = 0.0
    for num, unit in re.findall(r"(?i)(\d+(?:\.\d+)?)(ms|us|ns|d|h|m|s)", v):
        total += float(num) * {"d": 86_400_000, "h": 3_600_000, "m": 60_000, "s": 1000, "ms": 1, "us": 0.001,
                               "ns": 1e-6}[unit.lower()]  # fmt: skip
    return -total if neg else total


def _parse_dt(kind: str, val: str) -> int:
    import datetime as dt

    v = val.replace("_", "")
    try:
        if kind == "date":
            d = dt.datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=dt.UTC)
            return int(d.timestamp() * 1000)
        if kind == "tod":
            parts = v.split(":")
            h, m = int(parts[0]), int(parts[1])
            s = float(parts[2]) if len(parts) > 2 else 0.0
            return int(round((h * 3600 + m * 60 + s) * 1000))
        date_part, _, time_part = v.rpartition("-")
        d = dt.datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=dt.UTC)
        parts = time_part.split(":")
        secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + (float(parts[2]) if len(parts) > 2 else 0.0)
        return int(d.timestamp() * 1000 + secs * 1000)
    except (ValueError, IndexError) as exc:
        raise SimError(f"литерал {kind}#{val}") from exc


class Machine:
    """Набор POU, глобальных и типов; исполнение вызовов с часами ``now_ms``."""

    def __init__(
        self,
        pous: dict[str, tuple[str, str]],
        gvls: list[tuple[str, str]],
        duts: list[str],
        sem: Semantics,
        global_alias: dict[tuple[str, str], str] | None = None,
        dialect: str = "codesys",
    ) -> None:
        self.sem = sem
        self.now_ms = 0
        self.defs: dict[str, PouDef] = {}
        self.types: dict[str, A.TypeDecl] = {}
        self.enum_values: dict[str, dict[str, int]] = {}
        for text in duts:
            for td in parse_decl(text, dialect).decl.types:
                self.types[td.name.lower()] = td
                if td.kind == "ENUM":
                    vals: dict[str, int] = {}
                    nxt = 0
                    for ev in td.values:
                        if ev.value is not None:
                            nxt = int(self._const(ev.value))
                        vals[ev.name.lower()] = nxt
                        nxt += 1
                    self.enum_values[td.name.lower()] = vals
        for name, (decl, body) in pous.items():
            pd = parse_decl(decl, dialect)
            pb = parse_body(body, dialect)
            if pb.diagnostics:
                diag = pb.diagnostics[0]
                raise SimError(f"{name}: ошибка разбора тела ({diag.line}:{diag.col}) {diag.message}")
            h = pd.decl.header
            kind = {"PROGRAM": "program", "FUNCTION_BLOCK": "functionBlock", "FUNCTION": "function"}.get(
                h.kind if h else "PROGRAM", "program"
            )
            self.defs[name.lower()] = PouDef(name, kind, pd.decl, pb.stmts, h.return_type if h else None)
        self.globals = Obj("GLOBALS", "struct")
        self.gvl_objs: dict[str, Obj] = {}
        alias = global_alias or {}
        for gname, text in gvls:
            g = Obj(gname, "struct")
            for sec in parse_decl(text, dialect).decl.sections:
                for d in sec.decls:
                    for n in d.names:
                        val = self.init_value(d.type, d.init)
                        g.vars[n.lower()] = val
                        g.types[n.lower()] = d.type
            self.gvl_objs[gname.lower()] = g
            for n, v in g.vars.items():
                self.globals.vars.setdefault(n, v)
                self.globals.types.setdefault(n, g.types[n])
                key = alias.get((gname.lower(), n))
                if key:
                    self.globals.vars[key.lower()] = v
                    self.globals.types[key.lower()] = g.types[n]
        self._alias_links = {(gname.lower(), n): alias.get((gname.lower(), n), "").lower() for gname, _ in gvls
                             for n in self.gvl_objs[gname.lower()].vars}  # fmt: skip
        self.programs: dict[str, Obj] = {}

    # ------------------------------------------------------------ значения и типы

    def _const(self, e: A.Expr) -> Any:
        return self.eval(e, None, {})

    def init_value(self, t: A.TypeRef, init: A.Expr | None) -> Any:
        v = self.default(t)
        if init is not None:
            if isinstance(init, A.ArrayInit) and isinstance(v, Arr):
                flat: list[Any] = []
                for rep, val in init.items:
                    n = int(self._const(rep)) if rep is not None else 1
                    flat.extend([self._const(val)] * n)
                for i, x in enumerate(flat[: len(v.items)]):
                    v.items[i] = coerce(self.sem, v.elem.name, x)
            elif isinstance(init, A.StructInit) and isinstance(v, Obj):
                for fname, fval in init.fields:
                    ft = v.types.get(fname.lower())
                    v.vars[fname.lower()] = self.init_value(ft, fval) if ft else self._const(fval)
            else:
                v = self.assign_conv(t, self._const(init))
        return v

    def assign_conv(self, t: A.TypeRef, val: Any) -> Any:
        if isinstance(val, tuple) and val and val[0] == "enum":
            return self.enum_value(val[1], val[2])
        if t.name in ("STRING", "WSTRING") and isinstance(val, str):
            if self.sem.string_bounded:
                n = int(self._const(t.length)) if t.length is not None else 80
                return val[:n]
            return val
        if t.name.lower() in self.types:
            td = self.types[t.name.lower()]
            if td.kind == "ENUM":
                return int(val) if not isinstance(val, int) else val
            if td.kind in ("ALIAS", "SUBRANGE") and td.base is not None:
                return self.assign_conv(td.base, val)
        if t.subrange is not None:
            return coerce(self.sem, t.name, val)
        return coerce(self.sem, t.name, val)

    def enum_value(self, enum: str, name: str) -> int:
        vals = self.enum_values.get(enum.lower())
        if vals is None or name.lower() not in vals:
            raise SimError(f"нет значения {enum}.{name}")
        return vals[name.lower()]

    def default(self, t: A.TypeRef) -> Any:
        n = t.name.upper()
        if n == "BOOL":
            return False
        if n in INT_TYPES:
            return 0
        if n in ("REAL", "LREAL"):
            return 0.0
        if n in ("TIME", "LTIME", "TOD", "TIME_OF_DAY", "DATE"):
            return 0
        if n in ("DT", "DATE_AND_TIME"):
            return self.sem.dt_default
        if n in ("STRING", "WSTRING"):
            return ""
        if n == "ARRAY" and t.elem is not None:
            return self._array(t.dims, t.elem)
        if n in STD_FBS:
            o = Obj(n, "std")
            ins, outs = STD_FBS[n]
            for pn, pt in ins + outs:
                o.vars[pn.lower()] = self.default(A.TypeRef(pt, pt))
                o.types[pn.lower()] = A.TypeRef(pt, pt)
            return o
        td = self.types.get(t.name.lower())
        if td is not None:
            if td.kind in ("STRUCT", "UNION"):
                o = Obj(td.name, "struct")
                for f in td.fields:
                    for fn in f.names:
                        o.vars[fn.lower()] = self.init_value(f.type, f.init)
                        o.types[fn.lower()] = f.type
                return o
            if td.kind == "ENUM":
                if td.init is not None:
                    return self.eval(td.init, None, {})
                first = next(iter(self.enum_values.get(td.name.lower(), {}).values()), 0)
                return first
            if td.base is not None:
                return self.init_value(td.base, td.init)
        d = self.defs.get(t.name.lower().split(".")[-1])
        if d is not None and d.kind == "functionBlock":
            return self.new_instance(d)
        if n in ("POINTER", "REFERENCE"):
            return None
        raise SimError(f"тип {t.name} не поддерживается симулятором")

    def _array(self, dims: list[tuple[A.Expr, A.Expr]], elem: A.TypeRef) -> Arr:
        lo = int(self._const(dims[0][0]))
        hi = int(self._const(dims[0][1]))
        if len(dims) == 1:
            return Arr(lo, hi, elem, [self.default(elem) for _ in range(hi - lo + 1)])
        sub_t = A.TypeRef("ARRAY", "", dims=dims[1:], elem=elem)
        return Arr(lo, hi, sub_t, [self._array(dims[1:], elem) for _ in range(hi - lo + 1)])

    def new_instance(self, d: PouDef) -> Obj:
        o = Obj(d.name, "fb" if d.kind == "functionBlock" else "program")
        for sec in d.decl.sections:
            for vd in sec.decls:
                for n in vd.names:
                    o.vars[n.lower()] = self.init_value(vd.type, vd.init)
                    o.types[n.lower()] = vd.type
                    o.sections[n.lower()] = sec.kind
        return o

    def program(self, name: str) -> Obj:
        key = name.lower()
        if key not in self.programs:
            d = self.defs.get(key)
            if d is None:
                raise SimError(f"нет программы {name}")
            self.programs[key] = self.new_instance(d)
        return self.programs[key]

    # ------------------------------------------------------------ исполнение

    def call_instance(self, inst: Obj, now_ms: int | None = None) -> None:
        if now_ms is not None:
            self.now_ms = now_ms
        if inst.kind == "std":
            self.std_fb(inst)
            return
        d = self.defs[inst.type_name.lower()]
        temps: dict[str, Any] = {}
        types: dict[str, A.TypeRef] = {}
        for sec in d.decl.sections:
            if sec.kind == "VAR_TEMP":
                for vd in sec.decls:
                    for n in vd.names:
                        temps[n.lower()] = self.init_value(vd.type, vd.init)
                        types[n.lower()] = vd.type
        frame = _Frame(inst, temps, d, types)
        try:
            self.exec_list(d.body, frame)
        except _Return:
            pass

    def exec_list(self, body: list[A.Stmt], f: _Frame) -> None:
        labels = {s.name.lower(): i for i, s in enumerate(body) if isinstance(s, A.Label)}
        i = 0
        steps = 0
        while i < len(body):
            s = body[i]
            steps += 1
            if steps > 1_000_000:
                raise SimError("слишком много шагов (бесконечный цикл?)")
            if isinstance(s, A.Jmp):
                if s.label.lower() not in labels:
                    raise SimError(f"JMP {s.label}: метка не на верхнем уровне")
                i = labels[s.label.lower()]
                continue
            if (
                isinstance(s, A.If)
                and len(s.branches) == 1
                and s.else_body is None
                and len(s.branches[0][1]) == 1
                and isinstance(s.branches[0][1][0], A.Jmp)
            ):
                if self.truth(self.eval(s.branches[0][0], f.inst, f.local, f)):
                    jl = s.branches[0][1][0]
                    assert isinstance(jl, A.Jmp)
                    if jl.label.lower() in labels:
                        i = labels[jl.label.lower()]
                        continue
                    raise SimError(f"JMP {jl.label}: метка не на верхнем уровне")
                i += 1
                continue
            self.exec(s, f)
            i += 1

    def truth(self, v: Any) -> bool:
        return bool(v)

    def exec(self, s: A.Stmt, f: _Frame) -> None:
        if isinstance(s, A.Assign):
            val = self.eval(s.value, f.inst, f.local, f)
            if s.op == "S=":
                if self.truth(val):
                    self.store(s.target, True, f)
                return
            if s.op == "R=":
                if self.truth(val):
                    self.store(s.target, False, f)
                return
            if s.op == "REF=":
                raise SimError("REF= не поддерживается")
            self.store(s.target, val, f)
        elif isinstance(s, A.CallStmt):
            self.eval(s.call, f.inst, f.local, f, statement=True)
        elif isinstance(s, A.If):
            for cond, body in s.branches:
                if self.truth(self.eval(cond, f.inst, f.local, f)):
                    self.exec_list(body, f)
                    return
            if s.else_body is not None:
                self.exec_list(s.else_body, f)
        elif isinstance(s, A.Case):
            sel = self.eval(s.selector, f.inst, f.local, f)
            for labels, body in s.branches:
                for lab in labels:
                    lo = self.eval(lab.low, f.inst, f.local, f)
                    if lab.high is None:
                        if sel == lo:
                            self.exec_list(body, f)
                            return
                    else:
                        hi = self.eval(lab.high, f.inst, f.local, f)
                        if lo <= sel <= hi:
                            self.exec_list(body, f)
                            return
            if s.else_body is not None:
                self.exec_list(s.else_body, f)
        elif isinstance(s, A.For):
            var = A.Name(s.var)
            first = self.eval(s.first, f.inst, f.local, f)
            step = self.eval(s.step, f.inst, f.local, f) if s.step is not None else 1
            last = self.eval(s.last, f.inst, f.local, f)
            if step == 0:
                raise SimError("FOR с шагом 0")
            self.store(var, first, f)
            n = 0
            while True:
                cur = self.eval(var, f.inst, f.local, f)
                if self.sem.for_bounds == "each":
                    last = self.eval(s.last, f.inst, f.local, f)
                if (step > 0 and cur > last) or (step < 0 and cur < last):
                    break
                try:
                    self.exec_list(s.body, f)
                except _Exit:
                    break
                except _Continue:
                    pass
                n += 1
                if n > 1_000_000:
                    raise SimError("FOR: слишком много итераций")
                self.store(var, self.eval(var, f.inst, f.local, f) + step, f)
        elif isinstance(s, A.While):
            n = 0
            while self.truth(self.eval(s.cond, f.inst, f.local, f)):
                try:
                    self.exec_list(s.body, f)
                except _Exit:
                    break
                except _Continue:
                    pass
                n += 1
                if n > 1_000_000:
                    raise SimError("WHILE: слишком много итераций")
        elif isinstance(s, A.Repeat):
            n = 0
            while True:
                try:
                    self.exec_list(s.body, f)
                except _Exit:
                    break
                except _Continue:
                    pass
                if self.truth(self.eval(s.cond, f.inst, f.local, f)):
                    break
                n += 1
                if n > 1_000_000:
                    raise SimError("REPEAT: слишком много итераций")
        elif isinstance(s, A.Exit):
            raise _Exit()
        elif isinstance(s, A.Continue):
            raise _Continue()
        elif isinstance(s, A.Return):
            raise _Return()
        elif isinstance(s, A.Empty | A.Label):
            return
        elif isinstance(s, A.Jmp):
            raise SimError("JMP вне верхнего уровня")
        elif isinstance(s, A.ErrorStmt):
            raise SimError(f"оператор с ошибкой разбора: {s.message}")

    # ------------------------------------------------------------ места хранения

    def _lookup(
        self, name: str, f: _Frame | None, inst: Obj | None, local: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, A.TypeRef] | None, str]:
        key = name.lower()
        if key in local:
            return local, f.types if f is not None else None, key
        if inst is not None and key in inst.vars:
            return inst.vars, inst.types, key
        if key in self.globals.vars:
            return self.globals.vars, self.globals.types, key
        raise SimError(f"неизвестная переменная {name}")

    def store(self, target: A.Expr, val: Any, f: _Frame) -> None:
        if isinstance(target, A.Name):
            d, types, key = self._lookup(target.id, f, f.inst, f.local)
            t = types.get(key) if types is not None else None
            if t is None and f.def_ is not None and f.def_.return_type is not None and key == f.def_.name.lower():
                t = f.def_.return_type
            v = self.assign_conv(t, val) if t is not None else val
            d[key] = v
            if d is self.globals.vars:
                self._mirror_global(key, v)
            return
        if isinstance(target, A.Member):
            if target.name.isdigit():
                base = self.eval(target.obj, f.inst, f.local, f)
                bit = int(target.name)
                nv = (int(base) | (1 << bit)) if self.truth(val) else (int(base) & ~(1 << bit))
                self.store(target.obj, nv, f)
                return
            if (
                isinstance(target.obj, A.Name)
                and target.obj.id.lower() in self.gvl_objs
                and target.obj.id.lower() not in f.local
                and (f.inst is None or target.obj.id.lower() not in f.inst.vars)
            ):
                g = self.gvl_objs[target.obj.id.lower()]
                key = target.name.lower()
                v = self.assign_conv(g.types[key], val)
                g.vars[key] = v
                self.globals.vars[key] = v
                alias = self._alias_links.get((target.obj.id.lower(), key))
                if alias:
                    self.globals.vars[alias] = v
                return
            obj = self.eval(target.obj, f.inst, f.local, f)
            if not isinstance(obj, Obj):
                raise SimError(f"{target.name}: не структура")
            key = target.name.lower()
            t = obj.types.get(key)
            obj.vars[key] = self.assign_conv(t, val) if t is not None else val
            return
        if isinstance(target, A.Index):
            arr = self.eval(target.obj, f.inst, f.local, f)
            idx = [int(self.eval(i, f.inst, f.local, f)) for i in target.indices]
            for k, i in enumerate(idx):
                if not isinstance(arr, Arr):
                    raise SimError("индексация не массива")
                pos = arr.idx(i, self.sem)
                if pos is None:
                    return
                if k == len(idx) - 1:
                    arr.items[pos] = self.assign_conv(arr.elem, val)
                    return
                arr = arr.items[pos]
            return
        raise SimError(f"нельзя присвоить {type(target).__name__}")

    def _mirror_global(self, key: str, v: Any) -> None:
        for (g, n), alias in self._alias_links.items():
            if n == key and g in self.gvl_objs:
                self.gvl_objs[g].vars[n] = v
                if alias:
                    self.globals.vars[alias] = v
            elif alias == key and g in self.gvl_objs:
                self.gvl_objs[g].vars[n] = v
                self.globals.vars[n] = v

    # ------------------------------------------------------------ выражения

    def eval(self, e: A.Expr | None, inst: Obj | None, local: dict[str, Any], f: _Frame | None = None,
             statement: bool = False) -> Any:  # fmt: skip
        sem = self.sem
        if e is None:
            return None
        if isinstance(e, A.Literal):
            v = literal_value(e, sem)
            if isinstance(v, tuple) and v and v[0] == "enum":
                return self.enum_value(v[1], v[2])
            return v
        if isinstance(e, A.Name):
            key = e.id.lower()
            if key in local:
                return local[key]
            if inst is not None and key in inst.vars:
                return inst.vars[key]
            if key in self.globals.vars:
                return self.globals.vars[key]
            if key in self.defs and self.defs[key].kind == "program":
                return self.program(key)
            raise SimError(f"неизвестная переменная {e.id}")
        if isinstance(e, A.Member):
            if isinstance(e.obj, A.Name):
                base = e.obj.id.lower()
                in_scope = base in local or (inst is not None and base in inst.vars) or base in self.globals.vars
                if not in_scope:
                    if base in self.enum_values:
                        return self.enum_value(e.obj.id, e.name)
                    if base in self.gvl_objs:
                        g = self.gvl_objs[base]
                        if e.name.lower() in g.vars:
                            return g.vars[e.name.lower()]
            obj = self.eval(e.obj, inst, local, f)
            if e.name.isdigit():
                return bool((int(obj) >> int(e.name)) & 1)
            if isinstance(obj, Obj):
                key = e.name.lower()
                if key in obj.vars:
                    return obj.vars[key]
                raise SimError(f"нет члена {e.name} у {obj.type_name}")
            raise SimError(f".{e.name} у не структуры")
        if isinstance(e, A.Index):
            arr = self.eval(e.obj, inst, local, f)
            for i in e.indices:
                if not isinstance(arr, Arr):
                    raise SimError("индексация не массива")
                pos = arr.idx(int(self.eval(i, inst, local, f)), sem)
                if pos is None:
                    return None
                arr = arr.items[pos]
            return arr
        if isinstance(e, A.Unary):
            v = self.eval(e.operand, inst, local, f)
            if e.op == "NOT":
                if isinstance(v, bool):
                    return not v
                return ~int(v)
            if e.op == "-":
                return -v
            return v
        if isinstance(e, A.Binary):
            return self.binary(e, inst, local, f)
        if isinstance(e, A.Call):
            return self.call(e, inst, local, f)
        if isinstance(e, A.Deref):
            raise SimError("указатели не поддерживаются симулятором")
        raise SimError(f"выражение {type(e).__name__}")

    def binary(self, e: A.Binary, inst: Obj | None, local: dict[str, Any], f: _Frame | None) -> Any:
        op = e.op
        if op == "AND_THEN":
            return self.truth(self.eval(e.left, inst, local, f)) and self.truth(self.eval(e.right, inst, local, f))
        if op == "OR_ELSE":
            return self.truth(self.eval(e.left, inst, local, f)) or self.truth(self.eval(e.right, inst, local, f))
        a = self.eval(e.left, inst, local, f)
        b = self.eval(e.right, inst, local, f)
        if op in ("AND", "&"):
            return (a and b) if isinstance(a, bool) and isinstance(b, bool) else int(a) & int(b)
        if op == "OR":
            return (a or b) if isinstance(a, bool) and isinstance(b, bool) else int(a) | int(b)
        if op == "XOR":
            return (a != b) if isinstance(a, bool) and isinstance(b, bool) else int(a) ^ int(b)
        if op == "=":
            return a == b
        if op == "<>":
            return a != b
        if a is None or b is None:
            if self.sem.array_oob == "null":
                return None
            raise SimError("операция с NULL")
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        if op == "<=":
            return a <= b
        if op == ">=":
            return a >= b
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                if self.sem.div_zero == "zero":
                    return 0 if isinstance(a, int) and isinstance(b, int) else 0.0
                raise SimError("деление на ноль")
            if isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool):
                if self.sem.int_overflow == "float64":
                    return a / b
                q = abs(a) // abs(b)
                return q if (a >= 0) == (b >= 0) else -q
            return a / b
        if op == "MOD":
            if b == 0:
                if self.sem.div_zero == "zero":
                    return 0
                raise SimError("MOD на ноль")
            r = abs(int(a)) % abs(int(b))
            return r if a >= 0 else -r
        if op == "**":
            return float(a) ** float(b)
        raise SimError(f"оператор {op}")

    def call(self, e: A.Call, inst: Obj | None, local: dict[str, Any], f: _Frame | None) -> Any:
        func = e.func
        # вызов экземпляра ФБ (имя, член, элемент массива)
        target_obj: Any = None
        fname = ""
        if isinstance(func, A.Name):
            key = func.id.lower()
            if key in local or (inst is not None and key in inst.vars) or key in self.globals.vars:
                target_obj = self.eval(func, inst, local, f)
            else:
                fname = func.id
        else:
            target_obj = self.eval(func, inst, local, f)
        if isinstance(target_obj, Obj):
            self._call_obj(target_obj, e, inst, local, f)
            return None
        up = fname.upper()
        args = e.args
        if fname.lower() in self.defs:
            d = self.defs[fname.lower()]
            if d.kind == "program":
                prg = self.program(fname)
                self._call_obj(prg, e, inst, local, f)
                return None
            return self._call_function(d, e, inst, local, f)
        vals = [self.eval(a.value, inst, local, f) for a in args if not a.output]
        return self.std_func(up, vals, args)

    def _call_obj(self, obj: Obj, e: A.Call, inst: Obj | None, local: dict[str, Any], f: _Frame | None) -> None:
        outs: list[tuple[str, A.Expr]] = []
        positional = (
            [n for n, s in obj.sections.items() if s == "VAR_INPUT"]
            if obj.kind != "std"
            else [p.lower() for p, _ in STD_FBS[obj.type_name][0]]
        )
        pi = 0
        for a in e.args:
            if a.output:
                if a.name:
                    outs.append((a.name.lower(), a.value))
                continue
            name = a.name.lower() if a.name else (positional[pi] if pi < len(positional) else None)
            if a.name is None:
                pi += 1
            if name is None:
                raise SimError("лишний позиционный аргумент")
            if name in ("en",) and name not in obj.vars:
                continue
            val = self.eval(a.value, inst, local, f)
            t = obj.types.get(name)
            if name not in obj.vars:
                raise SimError(f"нет входа {a.name} у {obj.type_name}")
            obj.vars[name] = self.assign_conv(t, val) if t is not None else val
        self.call_instance(obj)
        for name, tgt in outs:
            if isinstance(tgt, A.Name) and tgt.id == "":
                continue
            if f is None:
                raise SimError("выход => вне тела")
            self.store(tgt, obj.vars[name], f)

    def _call_function(self, d: PouDef, e: A.Call, inst: Obj | None, local: dict[str, Any], f: _Frame | None) -> Any:
        fr: dict[str, Any] = {}
        types: dict[str, A.TypeRef] = {}
        inputs: list[str] = []
        for sec in d.decl.sections:
            for vd in sec.decls:
                for n in vd.names:
                    fr[n.lower()] = self.init_value(vd.type, vd.init)
                    types[n.lower()] = vd.type
                    if sec.kind in ("VAR_INPUT", "VAR_IN_OUT"):
                        inputs.append(n.lower())
        rt = d.return_type
        if rt is not None:
            fr[d.name.lower()] = self.default(rt)
            types[d.name.lower()] = rt
        outs: list[tuple[str, A.Expr]] = []
        pi = 0
        for a in e.args:
            if a.output:
                if a.name:
                    outs.append((a.name.lower(), a.value))
                continue
            name = a.name.lower() if a.name else (inputs[pi] if pi < len(inputs) else None)
            if a.name is None:
                pi += 1
            if name is None:
                raise SimError(f"{d.name}: лишний аргумент")
            fr[name] = self.assign_conv(types[name], self.eval(a.value, inst, local, f))
        frame = _Frame(None, fr, d)
        frame.types = types
        try:
            self.exec_list(d.body, frame)
        except _Return:
            pass
        for name, tgt in outs:
            if f is not None:
                self.store(tgt, fr[name], f)
        return fr.get(d.name.lower())

    # ------------------------------------------------------------ Standard

    def std_fb(self, o: Obj) -> None:
        v = o.vars
        st = o.state
        now = self.now_ms
        t = o.type_name
        if t == "TON":
            if v["in"]:
                if not st.get("prev"):
                    st["start"] = now
                el = now - st.get("start", now)
                v["q"] = el >= v["pt"]
                v["et"] = min(el, v["pt"])
            else:
                v["q"] = False
                v["et"] = 0
            st["prev"] = v["in"]
        elif t == "TOF":
            if v["in"]:
                v["q"] = True
                v["et"] = 0
            else:
                if st.get("prev", False):
                    st["start"] = now
                if v["q"] or st.get("running"):
                    el = now - st.get("start", now)
                    st["running"] = el < v["pt"]
                    v["q"] = el < v["pt"]
                    v["et"] = min(el, v["pt"])
            st["prev"] = v["in"]
        elif t == "TP":
            if v["in"] and not st.get("prev") and not v["q"]:
                st["start"] = now
                v["q"] = True
            if v["q"]:
                el = now - st.get("start", now)
                if el >= v["pt"]:
                    v["q"] = False
                    v["et"] = v["pt"]
                else:
                    v["et"] = el
            elif not v["in"]:
                v["et"] = 0
            st["prev"] = v["in"]
        elif t == "R_TRIG":
            v["q"] = bool(v["clk"]) and not st.get("m", False)
            st["m"] = bool(v["clk"])
        elif t == "F_TRIG":
            # Standard 3.5.17.0: на первом вызове с CLK = FALSE спада нет (проверено в CODESYS 3.5.17.30 —
            # s7-to-codesys docs/methodology.md, тест StandardFTrigMatchesS7)
            v["q"] = (not v["clk"]) and st.get("m", False)
            st["m"] = bool(v["clk"])
        elif t == "RS":
            v["q1"] = (not v["reset1"]) and (v["q1"] or v["set"])
        elif t == "SR":
            v["q1"] = v["set1"] or ((not v["reset"]) and v["q1"])
        elif t == "CTU":
            if v["reset"]:
                v["cv"] = 0
            elif v["cu"] and not st.get("m", False) and v["cv"] < 65535:
                v["cv"] = v["cv"] + 1
            st["m"] = bool(v["cu"])
            v["q"] = v["cv"] >= v["pv"]
        elif t == "CTD":
            if v["load"]:
                v["cv"] = v["pv"]
            elif v["cd"] and not st.get("m", False) and v["cv"] > 0:
                v["cv"] = v["cv"] - 1
            st["m"] = bool(v["cd"])
            v["q"] = v["cv"] <= 0
        elif t == "CTUD":
            if v["reset"]:
                v["cv"] = 0
            elif v["load"]:
                v["cv"] = v["pv"]
            else:
                if v["cu"] and not st.get("mu", False) and v["cv"] < 65535:
                    v["cv"] += 1
                if v["cd"] and not st.get("md", False) and v["cv"] > 0:
                    v["cv"] -= 1
            st["mu"] = bool(v["cu"])
            st["md"] = bool(v["cd"])
            v["qu"] = v["cv"] >= v["pv"]
            v["qd"] = v["cv"] <= 0
        else:
            raise SimError(f"ФБ {t}")

    def std_func(self, up: str, vals: list[Any], args: list[A.Arg]) -> Any:
        sem = self.sem
        conv = is_conversion(up)
        if conv is not None:
            src, dst = conv
            x = vals[0]
            if dst in INT_TYPES:
                if isinstance(x, float):
                    x = real_to_int(sem, x)
                elif isinstance(x, bool):
                    x = int(x)
                bits, signed = INT_TYPES[dst]
                if src in ("TIME", "LTIME", "DT", "DATE", "TOD"):
                    x = int(x)
                return wrap_int(int(x), bits, signed) if sem.int_overflow != "float64" else int(x)
            if dst in ("REAL", "LREAL"):
                return f32(float(x)) if dst == "REAL" and sem.real_arith == "float32" else float(x)
            if dst == "BOOL":
                return bool(x)
            if dst in ("TIME", "LTIME"):
                return int(x)
            if dst in ("STRING", "WSTRING"):
                if isinstance(x, bool):
                    return "TRUE" if x else "FALSE"
                if isinstance(x, float):
                    return repr(x)
                return str(x)
            return x
        if up == "LIMIT":
            mn, x, mx = vals
            return max(mn, min(x, mx))
        if up == "MIN":
            return min(vals)
        if up == "MAX":
            return max(vals)
        if up == "SEL":
            return vals[2] if vals[0] else vals[1]
        if up == "MUX":
            k = int(vals[0])
            return vals[1 + k]
        if up == "ABS":
            return abs(vals[0])
        if up == "SQRT":
            return math.sqrt(vals[0])
        if up == "EXPT":
            return float(vals[0]) ** float(vals[1])
        if up == "LN":
            return math.log(vals[0])
        if up == "LOG":
            return math.log10(vals[0])
        if up == "EXP":
            return math.exp(vals[0])
        if up in ("SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN"):
            return getattr(math, up.lower())(vals[0])
        if up == "TRUNC":
            return int(vals[0])
        if up == "MOVE":
            return vals[0]
        if up == "NOT":
            return not vals[0] if isinstance(vals[0], bool) else ~int(vals[0])
        if up == "LEN":
            return len(vals[0]) if sem.string_bounded is False else len(vals[0].encode("cp1251", "replace"))
        if up == "CONCAT":
            return "".join(vals)
        if up == "LEFT":
            return vals[0][: int(vals[1])]
        if up == "RIGHT":
            n = int(vals[1])
            return vals[0][-n:] if n else ""
        if up == "MID":
            s, n, p = vals[0], int(vals[1]), int(vals[2])
            return s[p - 1 : p - 1 + n]
        if up == "FIND":
            return vals[0].find(vals[1]) + 1
        if up in ("SHL", "SHR", "ROL", "ROR"):
            x, n = int(vals[0]), int(vals[1])
            return x << n if up == "SHL" else x >> n
        if up == "TIME":
            return self.now_ms
        if up in ("AND", "OR", "XOR"):
            r = vals[0]
            for x in vals[1:]:
                r = (r and x) if up == "AND" else (r or x) if up == "OR" else (r != x)
            return r
        raise SimError(f"функция {up} не поддерживается симулятором")


@dataclass
class _Frame:
    inst: Obj | None
    local: dict[str, Any]
    def_: PouDef | None
    types: dict[str, A.TypeRef] = field(default_factory=dict)
