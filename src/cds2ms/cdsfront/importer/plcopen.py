"""Импорт PLCopen XML CODESYS 3.5 (TC6 2.00/2.01 с addData 3S).

Три размещения POU: ``types/pous`` (экспорт объектов), ``instances/.../resource`` (экспорт с устройством),
``addData/data[…/application]/resource`` (экспорт приложения). Тела ST, IL, FBD, LD, SFC и CFC (пустое ST +
``addData/data[…/cfc]``). Методы, свойства, действия, переходы, интерфейсы, GVL, DUT, задачи, библиотеки.
"""

from __future__ import annotations

import hashlib
import re

from ...ir.model import (
    Action,
    Body,
    Conn,
    Dut,
    GElem,
    Gvl,
    ImportIssue,
    Interface,
    Library,
    Method,
    Origin,
    Pin,
    Pou,
    Project,
    Property,
    SfcAction,
    Task,
)
from .xmltree import El, parse

_ELEMENTARY_TAGS = {
    "BOOL", "BYTE", "WORD", "DWORD", "LWORD", "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT",
    "REAL", "LREAL", "TIME", "DATE", "DT", "TOD", "LTIME",
}  # fmt: skip
_SECTION_TAGS = {
    "inputVars": "VAR_INPUT",
    "outputVars": "VAR_OUTPUT",
    "inOutVars": "VAR_IN_OUT",
    "localVars": "VAR",
    "tempVars": "VAR_TEMP",
    "externalVars": "VAR_EXTERNAL",
    "globalVars": "VAR_GLOBAL",
    "accessVars": "VAR_ACCESS",
}
_POU_KW = {"program": "PROGRAM", "functionBlock": "FUNCTION_BLOCK", "function": "FUNCTION"}
_INTERVAL_RE = re.compile(r"(?i)^(?:L?T(?:IME)?#)?\s*(.*)$")
_DUR_PART = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(ms|us|ns|d|h|m|s)")
GRAPH_CHILDREN = frozenset(
    {
        "inVariable", "outVariable", "inOutVariable", "block", "contact", "coil", "leftPowerRail", "rightPowerRail",
        "connector", "continuation", "jump", "label", "return", "comment", "vendorElement", "step", "transition",
        "actionBlock", "jumpStep", "selectionDivergence", "selectionConvergence", "simultaneousDivergence",
        "simultaneousConvergence", "macroStep",
    }
)  # fmt: skip


def parse_interval_ms(text: str | None, unit: str | None = None) -> float | None:
    """``t#1000ms``, ``T#1s500ms``, ``100`` (+ IntervalUnit ms/us) → миллисекунды."""
    if text is None:
        return None
    raw = text.strip().replace("_", "")
    if not raw:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        v = float(raw)
        u = (unit or "ms").lower()
        return v / 1000.0 if u == "us" else v * 1000.0 if u == "s" else v
    m = _INTERVAL_RE.match(raw)
    body = m.group(1) if m else raw
    total = 0.0
    found = False
    for num, u in _DUR_PART.findall(body):
        found = True
        f = float(num)
        total += {"d": 86_400_000.0, "h": 3_600_000.0, "m": 60_000.0, "s": 1000.0, "ms": 1.0, "us": 0.001, "ns": 1e-6}[
            u.lower()
        ] * f
    return total if found else None


def type_text(t: El | None) -> str:
    """Тип TC6 (<INT/>, <derived>, <array>, <string length>, <pointer>) → текст ST."""
    if t is None or not t.children:
        return "INT"
    c = t.children[0]
    if c.tag in _ELEMENTARY_TAGS:
        return c.tag
    if c.tag in ("string", "wstring"):
        ln = c.attrs.get("length")
        base = c.tag.upper()
        return f"{base}({ln})" if ln else base
    if c.tag == "derived":
        return c.attrs.get("name", "INT")
    if c.tag == "array":
        dims = ", ".join(f"{d.attrs.get('lower', '0')}..{d.attrs.get('upper', '0')}" for d in c.kids("dimension"))
        return f"ARRAY[{dims}] OF {type_text(c.child('baseType'))}"
    if c.tag == "pointer":
        return f"POINTER TO {type_text(c.child('baseType'))}"
    if c.tag in ("subrangeSigned", "subrangeUnsigned"):
        rng = c.child("range")
        lo = rng.attrs.get("lower", "0") if rng else "0"
        hi = rng.attrs.get("upper", "0") if rng else "0"
        return f"{type_text(c.child('baseType'))}({lo}..{hi})"
    return c.tag.upper()


def value_text(v: El | None) -> str | None:
    if v is None or not v.children:
        return None
    c = v.children[0]
    if c.tag == "simpleValue":
        return c.attrs.get("value")
    if c.tag == "arrayValue":
        parts = []
        for item in c.kids("value"):
            rep = item.attrs.get("repetitionValue")
            inner = value_text(item) or "0"
            parts.append(f"{rep}({inner})" if rep else inner)
        return "[" + ", ".join(parts) + "]"
    if c.tag == "structValue":
        parts = [f"{item.attrs.get('member', '')} := {value_text(item) or '0'}" for item in c.kids("value")]
        return "(" + ", ".join(parts) + ")"
    return None


def _short(name: str) -> str:
    return name.lower().rsplit("/", 1)[-1]


class _Importer:
    def __init__(self, raw: bytes, file: str) -> None:
        self.doc = parse(raw)
        self.file = file
        self.p = Project(
            name="",
            source_kind="plcopen-xml",
            source_file=file,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            has_bom=self.doc.has_bom,
        )

    def origin(self, el: El, local_id: str | None = None) -> Origin:
        return Origin(self.file, el.line, el.col, local_id)

    # ------------------------------------------------------------ тексты

    def plaintext(self, el: El) -> tuple[str, int] | None:
        d = el.data("interfaceasplaintext")
        if d is None:
            return None
        iap = d.child("InterfaceAsPlainText")
        x = iap.child("xhtml") if iap is not None else None
        if x is None:
            return None
        return x.all_text(), x.text_line or x.line

    def decl_from_structure(self, el: El, kind_kw: str, name: str) -> str:
        """Объявление из <interface> TC6 (если плоского текста нет)."""
        itf = el.child("interface")
        head = f"{kind_kw} {name}"
        if itf is not None:
            rt = itf.child("returnType")
            if rt is not None:
                head += f" : {type_text(rt)}"
        lines = [head]
        if itf is not None:
            for sec in itf.children:
                kw = _SECTION_TAGS.get(sec.tag)
                if kw is None:
                    continue
                lines.append(kw + self._quals(sec))
                lines.extend(self._vars(sec))
                lines.append("END_VAR")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _quals(sec: El) -> str:
        q = ""
        for attr, kw in (("constant", "CONSTANT"), ("retain", "RETAIN"), ("persistent", "PERSISTENT")):
            if sec.attrs.get(attr) == "true":
                q += " " + kw
        return q

    @staticmethod
    def _vars(sec: El) -> list[str]:
        out = []
        for v in sec.kids("variable"):
            line = f"    {v.attrs.get('name', '')}"
            if v.attrs.get("address"):
                line += f" AT {v.attrs['address']}"
            line += f" : {type_text(v.child('type'))}"
            iv = value_text(v.child("initialValue"))
            if iv is not None:
                line += f" := {iv}"
            out.append(line + ";")
        return out

    # ------------------------------------------------------------ тела

    def body(self, el: El, owner: str) -> Body | None:
        b = el.child("body")
        if b is None:
            return None
        for c in b.children:
            if c.tag == "ST":
                x = c.child("xhtml")
                text = x.all_text() if x is not None else c.all_text()
                line = (x.text_line or x.line) if x is not None else c.line
                col = (x.text_col or x.col) if x is not None else c.col
                cfc = b.data("cfc")
                if cfc is not None and not text.strip():
                    holder = cfc.child("CFC") or cfc
                    body = Body("CFC", line=holder.line, col=holder.col, elems=self.graph(holder))
                    body.page_oriented = holder.attrs.get("page-oriented") == "true"
                    return body
                return Body("ST", text=text, line=line, col=col)
            if c.tag == "IL":
                x = c.child("xhtml")
                text = x.all_text() if x is not None else c.all_text()
                return Body("IL", text=text, line=(x.text_line or x.line) if x is not None else c.line)
            if c.tag in ("FBD", "LD", "SFC", "CFC"):
                return Body(c.tag, line=c.line, col=c.col, elems=self.graph(c))
        self.p.issues.append(ImportIssue("MS-PARSE-01", f"{owner}: тело без известного языка", self.origin(b)))
        return None

    def conns(self, cpi: El | None) -> list[Conn]:
        if cpi is None:
            return []
        return [Conn(c.attrs.get("refLocalId", ""), c.attrs.get("formalParameter")) for c in cpi.kids("connection")]

    def pins(self, holder: El | None) -> list[Pin]:
        out: list[Pin] = []
        if holder is None:
            return out
        for v in holder.kids("variable"):
            out.append(
                Pin(
                    v.attrs.get("formalParameter", ""),
                    self.conns(v.child("connectionPointIn")),
                    v.attrs.get("negated") == "true",
                    v.attrs.get("edge", "none"),
                )
            )
        return out

    def graph(self, container: El) -> list[GElem]:
        out: list[GElem] = []
        for c in container.children:
            if c.tag not in GRAPH_CHILDREN:
                continue
            lid = c.attrs.get("localId", "")
            eo = c.attrs.get("executionOrderId")
            g = GElem(lid, c.tag, line=c.line, col=c.col, exec_order=int(eo) if eo and eo.isdigit() else None)
            g.negated = c.attrs.get("negated") == "true"
            ex = c.child("expression")
            if ex is not None:
                g.expr = ex.all_text().strip()
            var = c.child("variable")
            if var is not None and c.tag in ("contact", "coil"):
                g.expr = var.all_text().strip()
            if c.tag == "block":
                g.type_name = c.attrs.get("typeName", "")
                g.instance = c.attrs.get("instanceName", "")
                g.inputs = self.pins(c.child("inputVariables"))
                g.outputs = self.pins(c.child("outputVariables"))
                g.inouts = self.pins(c.child("inOutVariables"))
                for name in ("fbdcalltype", "cfccalltype", "ldcalltype"):
                    d = c.data(name)
                    if d is not None:
                        ct = d.child("CallType")
                        g.call_type = (ct.all_text() if ct is not None else d.all_text()).strip()
            elif c.tag == "contact":
                g.edge = c.attrs.get("edge", "none")
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            elif c.tag == "coil":
                g.storage = c.attrs.get("storage", "none")
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            elif c.tag in ("jump", "label"):
                g.expr = c.attrs.get("label", "")
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            elif c.tag in ("connector", "continuation"):
                g.name = c.attrs.get("name", "")
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            elif c.tag == "vendorElement":
                d = c.data("fbdelementtype")
                if d is not None:
                    et = d.child("ElementType")
                    g.vendor_type = (et.all_text() if et is not None else "").strip()
            elif c.tag == "step":
                g.name = c.attrs.get("name", "")
                g.initial = c.attrs.get("initialStep") == "true"
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            elif c.tag == "macroStep":
                g.name = c.attrs.get("name", "")
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            elif c.tag == "jumpStep":
                g.expr = c.attrs.get("targetName", "")
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            elif c.tag == "transition":
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
                cond = c.child("condition")
                if cond is not None:
                    inline = cond.child("inline")
                    ref = cond.child("reference")
                    cpi = cond.child("connectionPointIn")
                    if inline is not None:
                        g.condition = inline.all_text().strip()
                    elif ref is not None:
                        g.condition = ref.attrs.get("name", "")
                        g.call_type = "reference"
                    elif cpi is not None:
                        cs = self.conns(cpi)
                        g.condition_ref = cs[0].ref if cs else None
            elif c.tag == "actionBlock":
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
                for a in c.kids("action"):
                    ref = a.child("reference")
                    inline = a.child("inline")
                    ib = None
                    if inline is not None:
                        st = inline.child("ST")
                        x = st.child("xhtml") if st is not None else None
                        ib = Body("ST", text=x.all_text() if x is not None else inline.all_text(), line=a.line)
                    g.actions.append(
                        SfcAction(
                            a.attrs.get("qualifier", "N"),
                            ref.attrs.get("name", "") if ref is not None else "",
                            a.attrs.get("duration", ""),
                            a.attrs.get("indicator", ""),
                            ib,
                            a.line,
                        )
                    )
            elif c.tag in ("selectionDivergence", "simultaneousDivergence"):
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            elif c.tag in ("selectionConvergence", "simultaneousConvergence"):
                g.inputs = [Pin(str(i), self.conns(cp)) for i, cp in enumerate(c.kids("connectionPointIn"))]
            else:
                g.inputs = [Pin("", self.conns(c.child("connectionPointIn")))]
            out.append(g)
        return out

    # ------------------------------------------------------------ объекты

    def method(self, el: El, kw: str, owner: str) -> Method:
        name = el.attrs.get("name", "")
        pt = self.plaintext(el)
        decl, line = pt if pt else (self.decl_from_structure(el, kw, name), el.line)
        return Method(name, decl, self.body(el, owner), self.origin(el), line)

    def prop(self, el: El, owner: str) -> Property:
        name = el.attrs.get("name", "")
        pt = self.plaintext(el)
        decl, line = pt if pt else (self.decl_from_structure(el, "PROPERTY", name), el.line)
        get = el.child("GetAccessor")
        set_ = el.child("SetAccessor")
        return Property(
            name,
            decl,
            self.method(get, "METHOD", f"{owner}.{name}.Get") if get is not None else None,
            self.method(set_, "METHOD", f"{owner}.{name}.Set") if set_ is not None else None,
            self.origin(el),
            line,
        )

    def pou(self, el: El, placement: str) -> Pou:
        name = el.attrs.get("name", "")
        kind = el.attrs.get("pouType", "program")
        pt = self.plaintext(el)
        decl, line = pt if pt else (self.decl_from_structure(el, _POU_KW.get(kind, "PROGRAM"), name), el.line)
        pou = Pou(name, kind, decl, self.body(el, name), self.origin(el), line, placement=placement)
        acts = el.child("actions")
        for a in acts.kids("action") if acts is not None else []:
            b = self.body(a, f"{name}.{a.attrs.get('name', '')}")
            if b is not None:
                pou.actions.append(Action(a.attrs.get("name", ""), b, self.origin(a)))
        trans = el.child("transitions")
        for t in trans.kids("transition") if trans is not None else []:
            b = self.body(t, f"{name}.{t.attrs.get('name', '')}")
            if b is not None:
                pou.transitions.append(Action(t.attrs.get("name", ""), b, self.origin(t)))
        for d in el.datas("method"):
            for m in d.kids("Method"):
                pou.methods.append(self.method(m, "METHOD", name))
        for d in el.datas("property"):
            for pr in d.kids("Property"):
                pou.properties.append(self.prop(pr, name))
        return pou

    def interface(self, el: El) -> Interface:
        name = el.attrs.get("name", "")
        pt = self.plaintext(el)
        decl = pt[0] if pt else f"INTERFACE {name}\n"
        methods = []
        ms = el.child("Methods")
        for m in ms.kids("Method") if ms is not None else []:
            methods.append(self.method(m, "METHOD", name))
        props = []
        ps = el.child("Properties")
        for pr in ps.kids("Property") if ps is not None else []:
            props.append(self.prop(pr, name))
        ext: list[str] = []
        inh = el.child("Inheritance")
        if inh is not None:
            ext = [e.all_text().strip() for e in inh.kids("Extends")]
        return Interface(name, decl, methods, props, self.origin(el), ext)

    def gvl(self, el: El) -> Gvl:
        name = el.attrs.get("name", "")
        pt = self.plaintext(el)
        persistent = el.attrs.get("persistent") == "true"
        if pt:
            decl, line = pt
        else:
            kw = "VAR_GLOBAL" + self._quals(el)
            decl = "\n".join([kw, *self._vars(el), "END_VAR"]) + "\n"
            line = el.line
        return Gvl(name, decl, self.origin(el), persistent, line)

    def dut(self, el: El) -> Dut:
        name = el.attrs.get("name", "")
        pt = self.plaintext(el)
        if pt:
            return Dut(name, pt[0], self.origin(el), pt[1])
        base = el.child("baseType")
        text = f"TYPE {name} :\n"
        c = base.children[0] if base is not None and base.children else None
        if c is not None and c.tag == "struct":
            text += "STRUCT\n" + "\n".join(self._vars(c)) + "\nEND_STRUCT\nEND_TYPE\n"
        elif c is not None and c.tag == "enum":
            vals = c.child("values")
            items = []
            for v in vals.kids("value") if vals is not None else []:
                vv = v.attrs.get("value")
                items.append(f"{v.attrs.get('name', '')} := {vv}" if vv else v.attrs.get("name", ""))
            bt = c.child("baseType")
            text += "(" + ", ".join(items) + ")" + (f" {type_text(bt)}" if bt is not None else "") + ";\nEND_TYPE\n"
        else:
            text += f"{type_text(base)};\nEND_TYPE\n"
        return Dut(name, text, self.origin(el), el.line)

    def task(self, el: El) -> Task:
        prio = el.attrs.get("priority")
        interval_raw = el.attrs.get("interval", "")
        interval = parse_interval_ms(interval_raw) if interval_raw else None
        kind = "Cyclic" if interval_raw else "unknown"
        event = el.attrs.get("single", "")
        if event:
            kind = "Event"
        d = el.data("tasksettings")
        ts = d.child("TaskSettings") if d is not None else None
        if ts is not None:
            kind = ts.attrs.get("KindOfTask", kind)
            raw = ts.attrs.get("Interval")
            if raw:
                interval_raw = raw
                interval = parse_interval_ms(raw, ts.attrs.get("IntervalUnit"))
            event = ts.attrs.get("Event", event) or event
        pous = [pi.attrs.get("name", "") or pi.attrs.get("typeName", "") for pi in el.kids("pouInstance")]
        return Task(
            el.attrs.get("name", ""),
            kind,
            interval,
            int(prio) if prio and prio.lstrip("-").isdigit() else None,
            pous,
            self.origin(el),
            event,
            interval_raw,
        )

    def libraries(self, d: El) -> None:
        libs = d.child("Libraries")
        for lib in libs.kids("Library") if libs is not None else []:
            name = lib.attrs.get("Name", "")
            m = re.match(r"^#?(.+?),\s*([^\s(]+)\s*\((.+)\)\s*$", name)
            title, version, company = (m.group(1), m.group(2), m.group(3)) if m else (name.lstrip("#"), "", "")
            self.p.libraries.append(Library(name, title, version, company, lib.attrs.get("Namespace", "")))

    def container(self, el: El, placement: str) -> None:
        found = False
        for c in el.children:
            if c.tag == "pou":
                self.p.pous.append(self.pou(c, placement))
                found = True
            elif c.tag == "dataType":
                self.p.duts.append(self.dut(c))
                found = True
            elif c.tag == "globalVars":
                self.p.gvls.append(self.gvl(c))
                found = True
            elif c.tag == "task":
                self.p.tasks.append(self.task(c))
        add = el.child("addData")
        for d in add.kids("data") if add is not None else []:
            short = _short(d.attrs.get("name", ""))
            if short == "pou":
                for c in d.kids("pou"):
                    self.p.pous.append(self.pou(c, placement))
                    found = True
            elif short in ("datatype", "union"):
                for c in d.children:
                    if c.tag in ("dataType", "union"):
                        self.p.duts.append(self.dut(c))
                        found = True
            elif short == "interface":
                for c in d.kids("Interface"):
                    self.p.interfaces.append(self.interface(c))
                    found = True
            elif short == "globalvars":
                for c in d.kids("globalVars"):
                    self.p.gvls.append(self.gvl(c))
                    found = True
            elif short == "libraries":
                self.libraries(d)
        if found and placement not in self.p.placements:
            self.p.placements.append(placement)

    def run(self) -> Project:
        root = self.doc.root
        if root.tag != "project":
            raise ValueError(f"корневой элемент «{root.tag}», ожидался «project» (PLCopen XML)")
        fh = root.child("fileHeader")
        if fh is not None:
            self.p.ide = fh.attrs.get("productName", "")
            self.p.ide_version = fh.attrs.get("productVersion", "")
        ch = root.child("contentHeader")
        if ch is not None:
            self.p.name = ch.attrs.get("name", "")
        types = root.child("types")
        if types is not None:
            for sec in types.children:
                self.container(sec, "types")
        self.container(root, "types")
        app = root.data("application")
        if app is not None:
            for res in app.kids("resource"):
                self.container(res, "application")
        inst = root.child("instances")
        confs = inst.child("configurations") if inst is not None else None
        for conf in confs.kids("configuration") if confs is not None else []:
            self.container(conf, "resource")
            for res in conf.kids("resource"):
                self.container(res, "resource")
        return self.p


def load(raw: bytes, file: str = "<вход>") -> Project:
    return _Importer(raw, file).run()
