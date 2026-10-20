"""Python-DSL графических тел TC6 (FBD, LD, CFC, SFC) и IL для корпуса УДР-1.

Строит рукописный PLCopen XML в форме, которую принимает import_xml CODESYS 3.5.17.30 (проверено прогоном
tools/codesys/corpus.py, docs/FORMAT-OUT.md): позиции 0,0; сети FBD — localId N·10^10 + k; LD — одна левая шина
localId 0, сквозная нумерация, сеть начинается парой comment + vendorElement networktitle; у блоков FBD/LD/CFC —
addData …/fbdcalltype или …/cfccalltype (operator | function | functionblock); CFC — пустое ST + addData cfc,
провода через безымянные connector (именованные метки соединения разворачиваются в провода); условие перехода
SFC — через inVariable.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

NET = 10**10
# Операторы IEC в CODESYS (вызов «operator»), остальное без экземпляра — «function»
OPERATORS = {"ADD", "SUB", "MUL", "DIV", "MOD", "EXPT", "MOVE", "AND", "OR", "XOR", "NOT", "GT", "GE", "LT", "LE", "EQ",
             "NE", "SEL", "MAX", "MIN", "LIMIT", "MUX", "SHL", "SHR", "ROL", "ROR", "ABS", "SQRT", "LN", "LOG", "EXP",
             "SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN", "TRUNC"}  # fmt: skip


def _cpi(conns: list[tuple[int, str | None]]) -> str:
    if not conns:
        return "<connectionPointIn />"
    inner = "".join(
        f'<connection refLocalId="{r}"' + (f" formalParameter={quoteattr(f)}" if f else "") + " />" for r, f in conns
    )
    return f"<connectionPointIn>{inner}</connectionPointIn>"


Src = tuple[int, str | None]


@dataclass
class Graph:
    """Сеть или страница: элементы TC6 с connectionPointIn."""

    lang: str  # FBD LD CFC
    net: int = 1
    _next: int = 0
    parts: list[str] = field(default_factory=list)
    order: int = 0

    def _id(self) -> int:
        self._next += 1
        if self.lang == "FBD":
            return self.net * NET + self._next
        return self.net * 1000 + self._next

    def peek(self, k: int = 1) -> int:
        """localId, который получит k-й следующий элемент (для обратных связей CFC)."""
        n = self._next + k
        return self.net * NET + n if self.lang == "FBD" else self.net * 1000 + n

    def _eo(self, eo: int | None) -> str:
        if self.lang != "CFC":
            return ""
        if eo is None:
            self.order += 1
            eo = self.order
        return f' executionOrderId="{eo}"'

    def invar(self, expr: str) -> Src:
        i = self._id()
        self.parts.append(
            f'<inVariable localId="{i}"><position x="0" y="0" /><connectionPointOut /><expression>{escape(expr)}</expression></inVariable>'
        )
        return (i, expr if self.lang == "CFC" else None)

    def outvar(self, expr: str, src: Src, eo: int | None = None, negated: bool = False) -> int:
        i = self._id()
        neg = ' negated="true"' if negated else ""
        self.parts.append(
            f'<outVariable localId="{i}"{self._eo(eo)}{neg}><position x="0" y="0" />{_cpi([src])}<expression>{escape(expr)}</expression></outVariable>'
        )
        return i

    def block(
        self, type_name: str, inputs: list[tuple[str, Src | list[Src] | None]], outputs: list[str],
        instance: str = "", eo: int | None = None, negated_out: tuple[str, ...] = (), call: str | None = None,
    ) -> int:  # fmt: skip
        i = self._id()
        if call is None:
            call = (
                "functionblock"
                if instance
                else ("operator" if type_name.upper() in OPERATORS or "_TO_" in type_name.upper() else "function")
            )
        kind = "cfccalltype" if self.lang == "CFC" else "fbdcalltype"
        add = (f'<addData><data name="http://www.3s-software.com/plcopenxml/{kind}" handleUnknown="implementation">'
               f'<CallType xmlns="">{call}</CallType></data></addData>')  # fmt: skip
        inst = f" instanceName={quoteattr(instance)}" if instance else ""
        ins = ""
        for formal, src in inputs:
            conns = [] if src is None else (src if isinstance(src, list) else [src])
            ins += f"<variable formalParameter={quoteattr(formal)}>{_cpi(conns)}</variable>"
        outs = "".join(
            f"<variable formalParameter={quoteattr(o)}"
            + (' negated="true"' if o in negated_out else "")
            + "><connectionPointOut /></variable>"
            for o in outputs
        )
        self.parts.append(
            f'<block localId="{i}"{self._eo(eo)} typeName={quoteattr(type_name)}{inst}><position x="0" y="0" />'
            f"<inputVariables>{ins}</inputVariables><inOutVariables /><outputVariables>{outs}</outputVariables>{add}</block>"
        )
        return i

    def rail(self) -> Src:
        i = self._id()
        self.parts.append(
            f'<leftPowerRail localId="{i}"><position x="0" y="0" /><connectionPointOut formalParameter="none" /></leftPowerRail>'
        )
        return (i, None)

    def rail_right(self, srcs: list[Src]) -> int:
        i = self._id()
        self.parts.append(f'<rightPowerRail localId="{i}"><position x="0" y="0" />{_cpi(srcs)}</rightPowerRail>')
        return i

    def contact(self, var: str, srcs: Src | list[Src], negated: bool = False, edge: str = "none") -> Src:
        i = self._id()
        conns = srcs if isinstance(srcs, list) else [srcs]
        self.parts.append(
            f'<contact localId="{i}" negated="{str(negated).lower()}" storage="none" edge="{edge}"><position x="0" y="0" />'
            f"{_cpi(conns)}<connectionPointOut /><variable>{escape(var)}</variable></contact>"
        )
        return (i, None)

    def coil(self, var: str, srcs: Src | list[Src], storage: str = "none", negated: bool = False) -> Src:
        i = self._id()
        conns = srcs if isinstance(srcs, list) else [srcs]
        self.parts.append(
            f'<coil localId="{i}" negated="{str(negated).lower()}" storage="{storage}"><position x="0" y="0" />'
            f"{_cpi(conns)}<connectionPointOut /><variable>{escape(var)}</variable></coil>"
        )
        return (i, None)

    def jump(self, label: str, src: Src, eo: int | None = None) -> int:
        i = self._id()
        self.parts.append(
            f'<jump localId="{i}"{self._eo(eo)} label={quoteattr(label)}><position x="0" y="0" />{_cpi([src])}</jump>'
        )
        return i

    def label(self, name: str) -> int:
        i = self._id()
        self.parts.append(f'<label localId="{i}" label={quoteattr(name)}><position x="0" y="0" /></label>')
        return i

    def ret(self, src: Src, eo: int | None = None) -> int:
        i = self._id()
        self.parts.append(f'<return localId="{i}"{self._eo(eo)}><position x="0" y="0" />{_cpi([src])}</return>')
        return i

    def connector(self, name: str, src: Src) -> int:
        i = self._id()
        self.parts.append(
            f'<connector localId="{i}" name={quoteattr(name)}><position x="0" y="0" />{_cpi([src])}</connector>'
        )
        return i

    def continuation(self, name: str) -> Src:
        i = self._id()
        self.parts.append(
            f'<continuation localId="{i}" name={quoteattr(name)}><position x="0" y="0" /><connectionPointOut /></continuation>'
        )
        return (i, None)


def fbd_body(nets: list[Graph]) -> str:
    return "<FBD>" + "".join("".join(n.parts) for n in nets) + "</FBD>"


def _elems(parts: list[str]) -> list[ET.Element]:
    return list(ET.fromstring("<x>" + "".join(parts) + "</x>"))


def _text(e: ET.Element) -> str:
    # addData 3S пишет свои элементы с xmlns="" (вне пространства имён TC6) — сохраняем как в экспортах CODESYS
    t = ET.tostring(e, encoding="unicode", short_empty_elements=True)
    return t.replace("<CallType>", '<CallType xmlns="">').replace("<ElementType>", '<ElementType xmlns="">')


def ld_body(nets: list[Graph]) -> str:
    """Форма экспорта CODESYS: одна левая шина localId 0, сквозная нумерация, сеть — с пары comment + networktitle."""
    out = [
        '<leftPowerRail localId="0"><position x="0" y="0" /><connectionPointOut formalParameter="none" /></leftPowerRail>'
    ]
    nid = 0
    for n in nets:
        elems = [e for e in _elems(n.parts) if e.tag != "rightPowerRail"]
        ids: dict[str, str] = {}
        for e in elems:
            if e.tag == "leftPowerRail":
                ids[e.get("localId", "")] = "0"
        nid += 1
        out.append(f'<comment localId="{nid}" height="0" width="0"><position x="0" y="0" /><content>'
                   '<xhtml xmlns="http://www.w3.org/1999/xhtml" /></content></comment>')  # fmt: skip
        nid += 1
        out.append(
            f'<vendorElement localId="{nid}"><position x="0" y="0" /><alternativeText><xhtml xmlns="http://www.w3.org/1999/xhtml">'
            f'Сеть {n.net}</xhtml></alternativeText><addData><data name="http://www.3s-software.com/plcopenxml/fbdelementtype" '
            'handleUnknown="implementation"><ElementType xmlns="">networktitle</ElementType></data></addData></vendorElement>'
        )
        for e in elems:
            if e.tag != "leftPowerRail":
                nid += 1
                ids[e.get("localId", "")] = str(nid)
        for e in elems:
            if e.tag == "leftPowerRail":
                continue
            e.set("localId", ids[e.get("localId", "")])
            for c in e.iter("connection"):
                c.set("refLocalId", ids[c.get("refLocalId", "")])
            out.append(_text(e))
    # правая шина — одна, localId 2147483646, без соединений (так её принимает import_xml; без неё тело с боксом
    # или входной/выходной переменной создаётся «битым»: объект есть, POU не компилируется и не экспортируется)
    out.append('<rightPowerRail localId="2147483646"><position x="0" y="0" /><connectionPointIn /></rightPowerRail>')
    return "<LD>" + "".join(out) + "</LD>"


def _cfc_wires(parts: list[str]) -> str:
    """Провода CFC в форме CODESYS: каждый вход — через безымянный connector; formalParameter у входа connector'а —
    выражение входной переменной, "" у выхода оператора, имя выхода у ФБ. Именованные метки — в провода."""
    elems = _elems(parts)
    by_id = {e.get("localId", ""): e for e in elems}
    named = {}
    for e in elems:
        if e.tag == "connector" and e.get("name"):
            c = e.find("connectionPointIn/connection")
            assert c is not None
            named[e.get("name", "").lower()] = (c.get("refLocalId", ""), c.get("formalParameter"))
    cont = {e.get("localId", ""): e.get("name", "").lower() for e in elems if e.tag == "continuation"}
    keep = [e for e in elems if not (e.tag in ("connector", "continuation") and e.get("name"))]
    nxt = max(int(k) for k in by_id) + 1
    wires: list[ET.Element] = []
    for e in keep:
        for c in list(e.iter("connection")):
            ref, formal = c.get("refLocalId", ""), c.get("formalParameter")
            while ref in cont:
                ref, formal = named[cont[ref]]
            src = by_id[ref]
            if src.tag == "inVariable":
                f = src.findtext("expression") or ""
            elif src.tag == "block":
                ct = src.find("addData/data/CallType")
                f = "" if ct is not None and ct.text == "operator" else (formal or "")
            else:
                f = formal or ""
            w = ET.fromstring(f'<connector localId="{nxt}" name=""><position x="0" y="0" /><connectionPointIn>'
                              f'<connection refLocalId="{ref}" /></connectionPointIn></connector>')  # fmt: skip
            wc = w.find("connectionPointIn/connection")
            assert wc is not None
            wc.set("formalParameter", f)
            c.attrib.clear()
            c.set("refLocalId", str(nxt))
            nxt += 1
            wires.append(w)
    return "".join(_text(e) for e in keep + wires)


def cfc_body(g: Graph, page_oriented: bool = False) -> str:
    po = ' page-oriented="true"' if page_oriented else ""
    return (
        '<ST><xhtml xmlns="http://www.w3.org/1999/xhtml" /></ST>'
        f'<addData><data name="http://www.3s-software.com/plcopenxml/cfc" handleUnknown="implementation"><CFC{po}>'
        + _cfc_wires(g.parts)
        + "</CFC></data></addData>"
    )


SfcSrc = int | tuple[int, str]


def _sfc_conns(src: SfcSrc | list[SfcSrc] | None) -> list[tuple[int, str | None]]:
    if src is None:
        return []
    items = src if isinstance(src, list) else [src]
    out: list[tuple[int, str | None]] = []
    for x in items:
        out.append((x[0], x[1]) if isinstance(x, tuple) else (x, None))
    return out


@dataclass
class Sfc:
    _next: int = 0
    parts: list[str] = field(default_factory=list)

    def _id(self) -> int:
        self._next += 1
        return self._next

    def step(self, name: str, src: SfcSrc | list[SfcSrc] | None, initial: bool = False) -> int:
        i = self._id()
        init = ' initialStep="true"' if initial else ""
        self.parts.append(
            f'<step localId="{i}"{init} name={quoteattr(name)}><position x="0" y="0" />{_cpi(_sfc_conns(src))}'
            f'<connectionPointOut formalParameter="sfc" /></step>'
        )
        return i

    def transition(self, src: SfcSrc, cond: str) -> int:
        v = self._id()
        self.parts.append(
            f'<inVariable localId="{v}"><position x="0" y="0" /><connectionPointOut /><expression>{escape(cond)}</expression></inVariable>'
        )
        i = self._id()
        self.parts.append(
            f'<transition localId="{i}"><position x="0" y="0" />{_cpi(_sfc_conns(src))}<connectionPointOut />'
            f'<condition><connectionPointIn><connection refLocalId="{v}" /></connectionPointIn></condition></transition>'
        )
        return i

    def actions(self, step: int, acts: list[tuple[str, str, str]]) -> int:
        """acts: (квалификатор, имя действия, длительность)."""
        i = self._id()
        inner = ""
        for q, name, dur in acts:
            a = self._id()
            d = f" duration={quoteattr(dur)}" if dur else ""
            inner += f'<action localId="{a}" qualifier="{q}"{d}><relPosition x="0" y="0" /><reference name={quoteattr(name)} /></action>'
        self.parts.append(
            f'<actionBlock localId="{i}"><position x="0" y="0" />{_cpi([(step, None)])}{inner}</actionBlock>'
        )
        return i

    def sel_div(self, src: SfcSrc, n: int = 2) -> int:
        i = self._id()
        outs = "".join(f'<connectionPointOut formalParameter="{k}" />' for k in range(n))
        self.parts.append(
            f'<selectionDivergence localId="{i}"><position x="0" y="0" />{_cpi(_sfc_conns(src))}{outs}</selectionDivergence>'
        )
        return i

    def sel_conv(self, srcs: list[int]) -> int:
        i = self._id()
        cps = "".join(_cpi([(s, None)]) for s in srcs)
        self.parts.append(
            f'<selectionConvergence localId="{i}"><position x="0" y="0" />{cps}<connectionPointOut /></selectionConvergence>'
        )
        return i

    def sim_div(self, src: SfcSrc, n: int = 2) -> int:
        i = self._id()
        outs = "".join(f'<connectionPointOut formalParameter="{k}" />' for k in range(n))
        self.parts.append(
            f'<simultaneousDivergence localId="{i}"><position x="0" y="0" />{_cpi(_sfc_conns(src))}{outs}</simultaneousDivergence>'
        )
        return i

    def sim_conv(self, srcs: list[int]) -> int:
        i = self._id()
        cps = "".join(_cpi([(s, None)]) for s in srcs)
        self.parts.append(
            f'<simultaneousConvergence localId="{i}"><position x="0" y="0" />{cps}<connectionPointOut /></simultaneousConvergence>'
        )
        return i

    def jump_step(self, src: SfcSrc, target: str) -> int:
        i = self._id()
        self.parts.append(
            f'<jumpStep localId="{i}" targetName={quoteattr(target)}><position x="0" y="0" />{_cpi([(src, None)])}</jumpStep>'
        )
        return i

    def body(self) -> str:
        return "<SFC>" + "".join(self.parts) + "</SFC>"


_TC6_ELEM = {"BOOL", "BYTE", "WORD", "DWORD", "LWORD", "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT",
             "REAL", "LREAL", "TIME", "DATE", "DT", "TOD"}  # fmt: skip
_SEC = {"VAR_INPUT": "inputVars", "VAR_OUTPUT": "outputVars", "VAR_IN_OUT": "inOutVars", "VAR": "localVars",
        "VAR_TEMP": "tempVars"}  # fmt: skip


def _type_xml(t: object) -> str:
    from cds2ms.cdsfront.st.printer import fmt_expr

    name = t.name.upper()  # type: ignore[attr-defined]
    if name == "ARRAY":
        dims = "".join(f'<dimension lower="{fmt_expr(lo)}" upper="{fmt_expr(hi)}" />' for lo, hi in t.dims)  # type: ignore[attr-defined]
        return f"<array>{dims}<baseType>{_type_xml(t.elem)}</baseType></array>"  # type: ignore[attr-defined]
    if name in ("STRING", "WSTRING"):
        ln = t.length  # type: ignore[attr-defined]
        return f"<{name.lower()}" + (f' length="{fmt_expr(ln)}"' if ln is not None else "") + " />"
    if name in _TC6_ELEM:
        return f"<{name} />"
    return f"<derived name={quoteattr(t.name)} />"  # type: ignore[attr-defined]


def interface_xml(decl: str) -> str:
    """Структурный <interface> TC6 из текста объявления (для импорта CODESYS — вместе с плоским текстом)."""
    from cds2ms.cdsfront.st.parser import parse_decl
    from cds2ms.cdsfront.st.printer import fmt_expr

    pd = parse_decl(decl)
    out = "<interface>"
    h = pd.decl.header
    if h is not None and h.return_type is not None:
        out += f"<returnType>{_type_xml(h.return_type)}</returnType>"
    for sec in pd.decl.sections:
        tag = _SEC.get(sec.kind)
        if tag is None:
            continue
        attrs = ' constant="true"' if "CONSTANT" in sec.qualifiers else ""
        attrs += ' retain="true"' if "RETAIN" in sec.qualifiers else ""
        out += f"<{tag}{attrs}>"
        for d in sec.decls:
            for n in d.names:
                init = (
                    f"<initialValue><simpleValue value={quoteattr(fmt_expr(d.init))} /></initialValue>"
                    if d.init is not None
                    else ""
                )
                out += f"<variable name={quoteattr(n)}><type>{_type_xml(d.type)}</type>{init}</variable>"
        out += f"</{tag}>"
    return out + "</interface>"


def pou(name: str, kind: str, decl: str, body_xml: str, actions: dict[str, str] | None = None) -> str:
    """POU TC6: структурный интерфейс и плоский текст объявления (interfaceasplaintext)."""
    acts = ""
    if actions:
        acts = (
            "<actions>"
            + "".join(
                f'<action name={quoteattr(n)}><body><ST><xhtml xmlns="http://www.w3.org/1999/xhtml">{escape(t)}</xhtml></ST></body></action>'
                for n, t in actions.items()
            )
            + "</actions>"
        )
    return (
        f'<pou name={quoteattr(name)} pouType="{kind}">{interface_xml(decl)}{acts}<body>{body_xml}</body>'
        '<addData><data name="http://www.3s-software.com/plcopenxml/interfaceasplaintext" handleUnknown="implementation">'
        f'<InterfaceAsPlainText><xhtml xmlns="http://www.w3.org/1999/xhtml">{escape(decl)}</xhtml></InterfaceAsPlainText></data></addData></pou>'
    )


def il_body(text: str) -> str:
    return f'<IL><xhtml xmlns="http://www.w3.org/1999/xhtml">{escape(text)}</xhtml></IL>'


def project(name: str, pous: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<project xmlns="http://www.plcopen.org/xml/tc6_0200">'
        '<fileHeader companyName="kr0nsch" productName="cds2ms corpus" productVersion="0.1.0" creationDateTime="1980-01-01T00:00:00" />'
        f'<contentHeader name={quoteattr(name)}><coordinateInfo><fbd><scaling x="1" y="1" /></fbd><ld><scaling x="1" y="1" /></ld>'
        '<sfc><scaling x="1" y="1" /></sfc></coordinateInfo></contentHeader>'
        "<types><dataTypes /><pous>"
        + "".join(pous)
        + "</pous></types><instances><configurations /></instances></project>\n"
    )
