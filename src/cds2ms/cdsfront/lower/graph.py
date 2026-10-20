"""Понижение FBD, LD и CFC в ST (общий вычислитель потока данных).

- FBD: сети по ``localId div 10^10`` (форма экспорта CODESYS), внутри сети — топологический порядок с
  разрешением ничьих по порядку элементов в файле; разветвлённый выход → ``migNetN_k``; блок с EN → ``IF``,
  ENO → ``migEnoN_k``; jump/label/return — структурировщик.
- LD: последовательно → ``AND``, параллельно → ``OR``, ``|/|`` → ``NOT``, ``|P|``/``|N|`` → ``R_TRIG``/``F_TRIG``;
  катушки ``( )``, ``(/)``, ``(S)``, ``(R)``; блок без EN вызывается каждый цикл (цепь идёт на вход, к которому
  она подключена в XML), блок с EN — под ``IF``. Сети — по левым шинам в порядке файла.
- CFC: порядок ``executionOrderId``; вход от блока с бо́льшим номером — значение прошлого цикла (выход
  экземпляра или переменная ``migCfcN``); безымянные ``connector`` — промежуточные узлы провода, именованные
  ``connector``/``continuation`` — рёбра.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...ir.model import Body, Conn, GElem, Pin
from ..st.parser import ParseError, parse_expression
from ..stdlib import BOOL_RESULT_OPS, INFIX_OPS, STD_FBS, STD_FUNCS, is_conversion
from ..symbols import Symbols, VarInfo
from .common import LowerNote, LowerResult, Names, paren
from .jumps import Seg, structure

_SKIP = frozenset({"comment", "vendorElement", "rightPowerRail"})
_NET_BASE = 10**10


@dataclass
class _Net:
    number: int
    elems: list[GElem] = field(default_factory=list)


@dataclass
class _Ctx:
    lang: str
    syms: Symbols | None
    local: dict[str, VarInfo]
    names: Names
    vars: list[tuple[str, str]] = field(default_factory=list)
    notes: list[LowerNote] = field(default_factory=list)


def split_networks(body: Body) -> list[_Net]:
    elems = [e for e in body.elems if e.kind not in ("comment",)]
    if body.lang == "CFC":
        return [_Net(1, [e for e in elems if e.kind not in _SKIP])]
    ids = [int(e.local_id) for e in elems if e.local_id.isdigit()]
    if body.lang == "FBD" and ids and min(ids) >= _NET_BASE:
        nets: dict[int, _Net] = {}
        for e in elems:
            n = int(e.local_id) // _NET_BASE if e.local_id.isdigit() else 0
            nets.setdefault(n, _Net(n)).elems.append(e)
        return [nets[k] for k in sorted(nets)]
    # LD (и FBD без схемы номеров): новая сеть — на заголовке сети или на левой шине после элементов
    out: list[_Net] = [_Net(1)]
    for e in elems:
        boundary = e.kind == "leftPowerRail" or (e.kind == "vendorElement" and e.vendor_type == "networktitle")
        cur = out[-1]
        has_content = any(x.kind not in _SKIP and x.kind != "leftPowerRail" for x in cur.elems)
        if boundary and has_content:
            out.append(_Net(len(out) + 1))
        out[-1].elems.append(e)
    # одна левая шина на всё тело (экспорт CODESYS, localId 0): доступна каждой сети
    rails = [e for e in elems if e.kind == "leftPowerRail"]
    for net in out:
        if rails and not any(x.kind == "leftPowerRail" for x in net.elems):
            net.elems = rails + net.elems
    return out


def lower_graph(body: Body, syms: Symbols | None, local: dict[str, VarInfo], names: Names) -> LowerResult:
    ctx = _Ctx(body.lang, syms, local, names)
    segs: list[Seg] = []
    rule = {"FBD": "MS-LANG-01", "LD": "MS-LANG-02", "CFC": "MS-LANG-03"}[body.lang]
    nets = split_networks(body)
    for net in nets:
        lowered = _NetLowering(ctx, net, body).run()
        segs.extend(x for x in lowered if x.kind == "label")  # метка сети — до комментария сети
        if len(nets) > 1 or body.lang != "CFC":
            segs.append(Seg("stmt", f"(* cds2ms: {rule} {body.lang} → ST, сеть {net.number} *)\n"))
        segs.extend(x for x in lowered if x.kind != "label")
    try:
        st = structure(segs)
    except ValueError as exc:
        ctx.notes.append(LowerNote("MS-ST-13", "manual", str(exc), body.line))
        st = structure([s for s in segs if s.kind == "stmt"])
    if st.mode == "machine":
        ctx.notes.append(
            LowerNote("MS-ST-13", "review", "переходы назад или с пересечением → автомат migPc", body.line)
        )
    elif st.mode == "if":
        ctx.notes.append(LowerNote("MS-ST-13", "review", "переходы вперёд → IF над хвостом", body.line))
    blocks = sum(1 for e in body.elems if e.kind == "block")
    what = (
        f"{len(nets)} сет{'ь' if len(nets) == 1 else 'и' if len(nets) < 5 else 'ей'}"
        if body.lang != "CFC"
        else "порядок executionOrderId"
    )
    ctx.notes.insert(0, LowerNote(rule, "review", f"{body.lang} → ST: {what}, блоков {blocks}", body.line))
    vars_ = ctx.vars + st.extra_vars
    return LowerResult(st.text, vars_, ctx.notes)


class _NetLowering:
    def __init__(self, ctx: _Ctx, net: _Net, body: Body) -> None:
        self.ctx = ctx
        self.net = net
        self.lang = body.lang
        self.elems = [e for e in net.elems if e.kind not in _SKIP]
        self.by_id: dict[str, GElem] = {e.local_id: e for e in self.elems}
        self.doc_index = {e.local_id: i for i, e in enumerate(self.elems)}
        self.values: dict[tuple[str, str], str] = {}  # (id, выход) -> выражение или имя
        self.emitted: set[str] = set()
        self.segs: list[Seg] = []
        self.named_connectors = {e.name.lower(): e for e in self.elems if e.kind == "connector" and e.name}
        self.uses = self._count_uses()

    # ------------------------------------------------------------ граф

    def _resolve(self, ref: str) -> GElem | None:
        e = self.by_id.get(ref)
        # промежуточные коннекторы провода и метки соединения
        seen = 0
        while e is not None and e.kind in ("connector", "continuation") and seen < 64:
            seen += 1
            if e.kind == "continuation" or (e.kind == "connector" and e.name and not e.inputs[0].conns):
                src = self.named_connectors.get(e.name.lower())
                if src is None or src is e:
                    return e
                e = src
                continue
            conns = e.inputs[0].conns if e.inputs else []
            if not conns:
                return e
            e = self.by_id.get(conns[0].ref)
        return e

    def _producer(self, c: Conn) -> tuple[GElem | None, str | None]:
        """Источник соединения с учётом коннекторов; formal — имя выхода у источника."""
        e = self.by_id.get(c.ref)
        formal = c.formal
        if e is not None and e.kind in ("connector", "continuation"):
            # formal у соединения с коннектором относится к коннектору; берём formal входа коннектора
            inner: GElem | None = e
            seen = 0
            while inner is not None and inner.kind in ("connector", "continuation") and seen < 64:
                seen += 1
                if inner.kind == "continuation" or (inner.name and not inner.inputs[0].conns):
                    inner = self.named_connectors.get(inner.name.lower())
                    continue
                cc = inner.inputs[0].conns
                if not cc:
                    break
                formal = cc[0].formal
                inner = self.by_id.get(cc[0].ref)
            e = inner
        return e, formal

    def _deps(self, e: GElem) -> list[GElem]:
        out = []
        for pin in [*e.inputs, *e.inouts]:
            for c in pin.conns:
                p, _ = self._producer(c)
                if p is not None and p is not e:
                    out.append(p)
        return out

    def _count_uses(self) -> dict[tuple[str, str], int]:
        cnt: dict[tuple[str, str], int] = {}
        for e in self.elems:
            if e.kind in ("connector", "continuation"):
                continue  # промежуточный узел провода: использование считается у потребителя
            for pin in [*e.inputs, *e.inouts]:
                for c in pin.conns:
                    p, formal = self._producer(c)
                    if p is not None:
                        key = (p.local_id, self._out_name(p, formal))
                        cnt[key] = cnt.get(key, 0) + 1
        return cnt

    def _out_name(self, p: GElem, formal: str | None) -> str:
        if p.kind == "block":
            if formal:
                return formal
            return p.outputs[0].formal if p.outputs else ""
        return ""

    def order(self) -> list[GElem]:
        if self.lang == "CFC":
            ordered = [e for e in self.elems if e.exec_order is not None]
            ordered.sort(key=lambda e: (e.exec_order or 0, self.doc_index[e.local_id]))
            rest = [e for e in self.elems if e.exec_order is None]
            return ordered + rest
        # топологический порядок, ничьи — по положению в файле
        indeg: dict[str, int] = {e.local_id: 0 for e in self.elems}
        succ: dict[str, list[str]] = {e.local_id: [] for e in self.elems}
        for e in self.elems:
            for d in self._deps(e):
                if d.local_id in indeg:
                    indeg[e.local_id] += 1
                    succ[d.local_id].append(e.local_id)
        ready = sorted((k for k, v in indeg.items() if v == 0), key=lambda k: self.doc_index[k])
        out: list[GElem] = []
        while ready:
            k = ready.pop(0)
            out.append(self.by_id[k])
            for s in succ[k]:
                indeg[s] -= 1
                if indeg[s] == 0:
                    ready.append(s)
                    ready.sort(key=lambda x: self.doc_index[x])
        if len(out) < len(self.elems):  # цикл в FBD/LD: добавить оставшиеся по файлу
            left = [e for e in self.elems if e not in out]
            self.ctx.notes.append(
                LowerNote("MS-LANG-01", "verify", "в сети есть обратная связь: порядок по файлу", left[0].line)
            )
            out.extend(left)
        return out

    # ------------------------------------------------------------ значения

    def value(self, c: Conn) -> str:
        p, formal = self._producer(c)
        if p is None:
            self.ctx.notes.append(LowerNote("MS-PARSE-01", "manual", f"соединение с несуществующим {c.ref}"))
            return "FALSE"
        key = (p.local_id, self._out_name(p, formal))
        if key in self.values:
            return self.values[key]
        if p.kind in ("inVariable", "inOutVariable"):
            return p.expr
        if p.kind == "leftPowerRail":
            return "TRUE"
        if p.kind == "contact":
            return self._contact(p)
        if p.kind == "coil":
            return self.power(p.inputs[0]) if p.inputs else "TRUE"
        if p.kind == "block":
            if self._is_fb(p):
                return f"{p.instance}.{key[1]}"
            if p.local_id not in self.emitted:
                # блок ещё не исполнен (обратная связь CFC или порядок): значение прошлого цикла
                return self._block_var(p)
            return self.values.get(key, self._block_var(p))
        if p.kind in ("connector", "continuation"):
            return self.power(p.inputs[0]) if p.inputs else "FALSE"
        return "FALSE"

    def power(self, pin: Pin) -> str:
        vals = [self.value(c) for c in pin.conns]
        if not vals:
            return "FALSE"
        if len(vals) == 1:
            v = vals[0]
        else:
            uniq = []
            for x in vals:
                if x not in uniq:
                    uniq.append(x)
            v = " OR ".join(paren(x) for x in uniq) if len(uniq) > 1 else uniq[0]
        if pin.negated:
            v = f"NOT {paren(v)}"
        return v

    def _contact(self, e: GElem) -> str:
        key = (e.local_id, "")
        if key in self.values:
            return self.values[key]
        pw = self.power(e.inputs[0]) if e.inputs else "TRUE"
        var = e.expr
        if e.edge in ("rising", "falling"):
            trig = self._edge_trigger(e, var)
            term = f"{trig}.Q"
        else:
            term = f"NOT {paren(var)}" if e.negated else var
        expr = term if pw == "TRUE" else f"{paren(pw)} AND {paren(term)}" if " OR " in pw else f"{pw} AND {term}"
        return expr

    def _edge_trigger(self, e: GElem, var: str) -> str:
        key = (e.local_id, "#trig")
        if key in self.values:
            return self.values[key]
        kind = "R_TRIG" if e.edge == "rising" else "F_TRIG"
        name = self.ctx.names.new(f"migTrig{self.net.number}_{len(self.ctx.vars) + 1}")
        self.ctx.vars.append((name, kind))
        self.values[key] = name
        self.segs.append(Seg("stmt", f"{name}(CLK := {var});\n"))
        self.ctx.notes.append(
            LowerNote(
                "MS-LANG-02", "review", f"контакт |{'P' if kind == 'R_TRIG' else 'N'}| {var} → {kind} {name}", e.line,
                local_id=e.local_id,
            )
        )  # fmt: skip
        return name

    def _is_fb(self, e: GElem) -> bool:
        if e.instance:
            return True
        ct = e.call_type.lower()
        return ct in ("functionblock", "fb") and bool(e.instance)

    def _block_var(self, e: GElem) -> str:
        key = (e.local_id, "#var")
        if key in self.values:
            return self.values[key]
        prefix = "migCfc" if self.lang == "CFC" else f"migNet{self.net.number}_"
        name = self.ctx.names.new(f"{prefix}{e.local_id if self.lang != 'CFC' else (e.exec_order or e.local_id)}")
        self.values[key] = name
        typ = self._block_type(e)
        self.ctx.vars.append((name, typ))
        return name

    def _block_type(self, e: GElem, quiet: bool = False) -> str:
        up = e.type_name.upper().split(".")[-1]
        if up in BOOL_RESULT_OPS:
            return "BOOL"
        conv = is_conversion(up)
        if conv:
            return conv[1]
        if self.ctx.syms is not None:
            rt = self.ctx.syms.function_return(e.type_name.split(".")[-1])
            if rt:
                return rt
            # тип по входам
            t: str | None = None
            from ..stdlib import common_type

            pins = e.inputs[1:] if up in ("SEL", "MUX") else e.inputs
            typing_now: set[str] = getattr(self, "_typing", set())
            self._typing = typing_now
            typing_now.add(e.local_id)
            for pin in pins:
                for c in pin.conns:
                    src = self._resolve(c.ref)
                    if src is not None and src.kind in ("inVariable", "inOutVariable"):
                        try:
                            t = common_type(t, self.ctx.syms.expr_type(parse_expression(src.expr), self.ctx.local))
                        except ParseError:
                            pass
                    elif src is not None and src.kind == "block" and src.local_id not in self._typing:
                        if self._is_fb(src):
                            pins_fb = self.ctx.syms.fb_pins(src.type_name)
                            if pins_fb is not None:
                                for n_, t_ in pins_fb[1]:
                                    if c.formal and n_.lower() == c.formal.lower():
                                        t = common_type(t, t_)
                        else:
                            t = common_type(t, self._block_type(src, quiet=True))
            self._typing.discard(e.local_id)
            if t:
                return t
        if not quiet:
            self.ctx.notes.append(
                LowerNote("MS-LANG-01", "verify", f"тип выхода блока {e.type_name} не выведен: принят REAL", e.line,
                          local_id=e.local_id)
            )  # fmt: skip
        return "REAL" if not quiet else ""

    def _call_expr(self, e: GElem) -> str:
        up = e.type_name.upper().split(".")[-1]
        args = [(p.formal, self.power(p)) for p in e.inputs if p.formal.upper() not in ("EN",)]
        if up in INFIX_OPS and len(args) >= 2:
            op = INFIX_OPS[up]
            return f" {op} ".join(paren(v) for _, v in args)
        if up == "NOT" and len(args) == 1:
            return f"NOT {paren(args[0][1])}"
        if up == "MOVE" and len(args) == 1:
            return args[0][1]
        if up in STD_FUNCS or up in INFIX_OPS or is_conversion(up) or up in ("NOT",):
            return f"{e.type_name}({', '.join(v for _, v in args)})"
        return f"{e.type_name}({', '.join(f'{f} := {v}' for f, v in args)})"

    # ------------------------------------------------------------ обход

    def run(self) -> list[Seg]:
        order = self.order()
        labels = [e for e in self.elems if e.kind == "label"]
        for lab in labels:
            self.segs.append(Seg("label", lab.expr))
        for e in order:
            self._emit(e)
        return self.segs

    def _is_pure_single_use(self, e: GElem, order: list[GElem] | None = None) -> bool:
        if self._is_fb(e) or any(p.formal.upper() == "EN" for p in e.inputs):
            return False
        outs = [(e.local_id, p.formal) for p in e.outputs] or [(e.local_id, "")]
        total = sum(self.uses.get(k, 0) for k in outs)
        if total != 1:
            return False
        if self.lang != "CFC":
            return True
        # CFC: потребитель исполняется позже, и между ними нет элементов с побочным эффектом
        consumer = None
        for x in self.elems:
            if x.kind in ("connector", "continuation"):
                continue
            for pin in [*x.inputs, *x.inouts]:
                for c in pin.conns:
                    pr, _ = self._producer(c)
                    if pr is e:
                        consumer = x
        if consumer is None or consumer.exec_order is None or e.exec_order is None:
            return False
        if consumer.exec_order <= e.exec_order:
            return False
        # вход e от блока с номером не меньше (обратная связь, значение прошлого цикла): между e и потребителем этот
        # блок может обновить свою переменную — встраивать нельзя (найдено property-тестом)
        for pin in [*e.inputs, *e.inouts]:
            for c in pin.conns:
                pr, _ = self._producer(c)
                if (
                    pr is not None
                    and pr.kind == "block"
                    and pr.exec_order is not None
                    and pr.exec_order >= e.exec_order
                ):
                    if pr.exec_order < consumer.exec_order or pr is e:
                        return False
        for x in self.elems:
            if x.exec_order is not None and e.exec_order < x.exec_order < consumer.exec_order:
                if x.kind in ("outVariable", "inOutVariable", "coil") or (x.kind == "block" and self._is_fb(x)):
                    return False
        return True

    def _emit(self, e: GElem) -> None:
        k = e.kind
        if k == "block":
            self._emit_block(e)
        elif k == "outVariable" or (k == "inOutVariable" and e.inputs and e.inputs[0].conns):
            if e.inputs and e.inputs[0].conns:
                v = self.power(e.inputs[0])
                if e.negated:
                    v = f"NOT {paren(v)}"
                self.segs.append(Seg("stmt", f"{e.expr} := {v};\n"))
        elif k == "coil":
            pw = self.power(e.inputs[0]) if e.inputs else "TRUE"
            key = (e.local_id, "")
            if self.uses.get(key, 0) > 0 and not _simple(pw):
                tmp = self.ctx.names.new(f"migNet{self.net.number}_{e.local_id}")
                self.ctx.vars.append((tmp, "BOOL"))
                self.segs.append(Seg("stmt", f"{tmp} := {pw};\n"))
                pw = tmp
                self.values[key] = tmp
            if e.storage == "set":
                self.segs.append(Seg("stmt", f"IF {pw} THEN\n    {e.expr} := TRUE;\nEND_IF;\n"))
            elif e.storage == "reset":
                self.segs.append(Seg("stmt", f"IF {pw} THEN\n    {e.expr} := FALSE;\nEND_IF;\n"))
            elif e.negated:
                self.segs.append(Seg("stmt", f"{e.expr} := NOT {paren(pw)};\n"))
            else:
                self.segs.append(Seg("stmt", f"{e.expr} := {pw};\n"))
        elif k == "contact":
            key = (e.local_id, "")
            if self.uses.get(key, 0) > 1:
                expr = self._contact(e)
                if not _simple(expr):
                    tmp = self.ctx.names.new(f"migNet{self.net.number}_{e.local_id}")
                    self.ctx.vars.append((tmp, "BOOL"))
                    self.segs.append(Seg("stmt", f"{tmp} := {expr};\n"))
                    self.values[key] = tmp
            elif e.edge in ("rising", "falling"):
                self._edge_trigger(e, e.expr)
        elif k == "jump":
            cond = self.power(e.inputs[0]) if e.inputs and e.inputs[0].conns else None
            self.segs.append(Seg("jmp", e.expr, None if cond in (None, "TRUE") else cond))
        elif k == "return":
            cond = self.power(e.inputs[0]) if e.inputs and e.inputs[0].conns else None
            self.segs.append(Seg("ret", "", None if cond in (None, "TRUE") else cond))
        elif k == "label":
            pass

    def _emit_block(self, e: GElem) -> None:
        en_pin = next((p for p in e.inputs if p.formal.upper() == "EN"), None)
        en = self.power(en_pin) if en_pin is not None and en_pin.conns else None
        eno_used = any(p.formal.upper() == "ENO" for p in e.outputs) and self.uses.get((e.local_id, "ENO"), 0) > 0
        if self._is_fb(e):
            args = []
            for p in e.inputs:
                if p.formal.upper() == "EN" or not p.conns:
                    continue
                v = self.power(p)
                if p.edge in ("rising", "falling"):
                    trig = self.ctx.names.new(f"migTrig{self.net.number}_{len(self.ctx.vars) + 1}")
                    self.ctx.vars.append((trig, "R_TRIG" if p.edge == "rising" else "F_TRIG"))
                    self.segs.append(Seg("stmt", f"{trig}(CLK := {v});\n"))
                    v = f"{trig}.Q"
                args.append(f"{p.formal} := {v}")
            for p in e.inouts:
                if p.conns:
                    args.append(f"{p.formal} := {self.power(p)}")
            call = f"{e.instance}({', '.join(args)});\n"
            if (
                e.type_name.upper() not in STD_FBS
                and self.ctx.syms is not None
                and not self.ctx.syms.is_fb_type(e.type_name)
            ):
                self.ctx.notes.append(
                    LowerNote("MS-LIB-02", "verify", f"тип блока {e.type_name} не найден в проекте", e.line,
                              local_id=e.local_id)
                )  # fmt: skip
            for p in e.outputs:
                if p.formal.upper() != "ENO":
                    v = f"{e.instance}.{p.formal}"
                    self.values[(e.local_id, p.formal)] = f"NOT {v}" if p.negated else v
        else:
            expr = self._call_expr(e)
            out_formal = next((p.formal for p in e.outputs if p.formal.upper() != "ENO"), "")
            negated = next((p.negated for p in e.outputs if p.formal.upper() != "ENO"), False)
            if en is None and self._is_pure_single_use(e):
                v = f"NOT {paren(expr)}" if negated else expr
                self.values[(e.local_id, out_formal)] = v
                self.values[(e.local_id, "")] = v
                self.emitted.add(e.local_id)
                return
            var = self._block_var(e)
            call = f"{var} := {expr};\n"
            v = f"NOT {var}" if negated else var
            self.values[(e.local_id, out_formal)] = v
            self.values[(e.local_id, "")] = v
        self.emitted.add(e.local_id)
        if en is not None:
            self.ctx.notes.append(
                LowerNote("MS-LANG-01", "review", f"блок {e.type_name} с EN → IF", e.line, local_id=e.local_id)
            )
            text = f"IF {en} THEN\n    {call}END_IF;\n"
            if eno_used:
                eno = self.ctx.names.new(f"migEno{self.net.number}_{e.local_id}")
                self.ctx.vars.append((eno, "BOOL"))
                text += f"{eno} := {en};\n"
                self.values[(e.local_id, "ENO")] = eno
            self.segs.append(Seg("stmt", text))
        else:
            if eno_used:
                self.values[(e.local_id, "ENO")] = "TRUE"
            self.segs.append(Seg("stmt", call))


def _simple(expr: str) -> bool:
    return all(ch.isalnum() or ch in "_.[]" for ch in expr.strip())
