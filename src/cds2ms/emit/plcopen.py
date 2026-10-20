"""PLCopen XML для «Импортирование PLCOpenXML» MasterSCADA 4D: подмножество TC6 2.01 без addData.

Раскладка: ``fileHeader``, ``contentHeader``; ``types/dataTypes`` (struct, enum, array ≤ 3 осей);
``types/pous`` (FUNCTION, FUNCTION_BLOCK, PROGRAM; тело только ``<ST><xhtml>``, как у CODESYS);
``instances/configurations/configuration[@name="migConfig"]/resource[@name="migResource"]/globalVars`` — по
элементу на вид секции (обычные, ``constant``, ``retain``); без ``task`` и ``pouInstance``. Варианты для
пробника — ``variant``: ``config-globals`` (globalVars в configuration), ``tasks`` (с task + pouInstance),
``xhtml-p`` (тело в ``xhtml:p``), ``flat-globals`` (параметры с именами GVL_x без папки).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .. import __version__
from ..cdsfront.st import ast as A
from ..cdsfront.st.parser import parse_decl
from ..cdsfront.st.printer import fmt_expr
from ..ir.model import Project, Task
from ..transform.master_st import FixedObject

NS_0201 = "http://www.plcopen.org/xml/tc6_0201"
NS_0200 = "http://www.plcopen.org/xml/tc6_0200"
XHTML = "http://www.w3.org/1999/xhtml"
CREATION = "1980-01-01T00:00:00"
_TC6_ELEMENTARY = {
    "BOOL", "BYTE", "WORD", "DWORD", "LWORD", "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT",
    "REAL", "LREAL", "TIME", "DATE", "DT", "TOD",
}  # fmt: skip
_ALIASES = {"TIME_OF_DAY": "TOD", "DATE_AND_TIME": "DT"}
_SECTIONS = {
    "VAR_INPUT": "inputVars",
    "VAR_OUTPUT": "outputVars",
    "VAR_IN_OUT": "inOutVars",
    "VAR": "localVars",
    "VAR_TEMP": "tempVars",
    "VAR_EXTERNAL": "externalVars",
    "VAR_INST": "localVars",
}
_POU_TYPES = {"program": "program", "functionBlock": "functionBlock", "function": "function"}


def _section_attrs(sec: A.VarSection) -> dict[str, str]:
    out = {}
    if "CONSTANT" in sec.qualifiers:
        out["constant"] = "true"
    if "RETAIN" in sec.qualifiers or "PERSISTENT" in sec.qualifiers:
        out["retain"] = "true"
    if "NON_RETAIN" in sec.qualifiers:
        out["nonretain"] = "true"
    return out


def _xhtml(parent: ET.Element, text: str, variant: str) -> None:
    x = ET.SubElement(parent, f"{{{XHTML}}}xhtml")
    if variant == "xhtml-p":
        p = ET.SubElement(x, f"{{{XHTML}}}p")
        p.text = text
    else:
        x.text = text


def build(
    project: Project,
    fixed: dict[str, FixedObject],
    sha256: str,
    variant: str = "default",
    ns: str = NS_0201,
) -> bytes:
    ET.register_namespace("", ns)
    ET.register_namespace("xhtml", XHTML)
    q = f"{{{ns}}}"
    root = ET.Element(f"{q}project")
    fh = ET.SubElement(root, f"{q}fileHeader", {
        "companyName": "kr0nsch",
        "productName": "cds2ms",
        "productVersion": __version__,
        "creationDateTime": CREATION,
        "contentDescription": f"создано cds2ms {__version__} · {project.source_file.replace(chr(92), '/').rsplit('/', 1)[-1]} · SHA-256 {sha256}",
    })  # fmt: skip
    del fh
    ch = ET.SubElement(root, f"{q}contentHeader", {"name": project.name or "migProject"})
    ci = ET.SubElement(ch, f"{q}coordinateInfo")
    for tag in ("fbd", "ld", "sfc"):
        sc = ET.SubElement(ET.SubElement(ci, f"{q}{tag}"), f"{q}scaling", {"x": "1", "y": "1"})
        del sc
    types = ET.SubElement(root, f"{q}types")
    dts = ET.SubElement(types, f"{q}dataTypes")
    for key in sorted(k for k in fixed if k.startswith("dut:")):
        dobj = fixed[key]
        for td in parse_decl(dobj.decl, "masterst").decl.types:
            if td.kind in ("ALIAS", "SUBRANGE", "UNION"):
                continue
            dt = ET.SubElement(dts, f"{q}dataType", {"name": td.name})
            bt = ET.SubElement(dt, f"{q}baseType")
            if td.kind == "STRUCT":
                st = ET.SubElement(bt, f"{q}struct")
                for f in td.fields:
                    for name in f.names:
                        v = ET.SubElement(st, f"{q}variable", {"name": name})
                        _ns_type(v, f.type, q)
                        if f.init is not None:
                            _ns_value(ET.SubElement(v, f"{q}initialValue"), f.init, q)
            elif td.kind == "ENUM":
                en = ET.SubElement(bt, f"{q}enum")
                vals = ET.SubElement(en, f"{q}values")
                for ev in td.values:
                    attrs = {"name": ev.name}
                    if ev.value is not None:
                        attrs["value"] = fmt_expr(ev.value)
                    ET.SubElement(vals, f"{q}value", attrs)
    pous = ET.SubElement(types, f"{q}pous")
    order = [p.name.lower() for p in project.pous]
    for name in order:
        obj = fixed.get(name)
        if obj is None or obj.kind != "pou":
            continue
        pd = parse_decl(obj.decl, "masterst")
        h = pd.decl.header
        pou = ET.SubElement(pous, f"{q}pou", {"name": obj.name, "pouType": _POU_TYPES.get(obj.pou_kind, "program")})
        itf = ET.SubElement(pou, f"{q}interface")
        if h is not None and h.return_type is not None:
            _ns_type(ET.SubElement(itf, f"{q}returnType"), h.return_type, q, wrap=False)
        for sec in pd.decl.sections:
            sec_tag = _SECTIONS.get(sec.kind)
            if sec_tag is None:
                continue
            el = ET.SubElement(itf, f"{q}{sec_tag}", _section_attrs(sec))
            for d in sec.decls:
                for vname in d.names:
                    attrs = {"name": vname}
                    if d.at:
                        attrs["address"] = d.at
                    v = ET.SubElement(el, f"{q}variable", attrs)
                    _ns_type(v, d.type, q)
                    if d.init is not None:
                        _ns_value(ET.SubElement(v, f"{q}initialValue"), d.init, q)
        body = ET.SubElement(pou, f"{q}body")
        st = ET.SubElement(body, f"{q}ST")
        _xhtml(st, obj.body, variant)
    inst = ET.SubElement(root, f"{q}instances")
    confs = ET.SubElement(inst, f"{q}configurations")
    conf = ET.SubElement(confs, f"{q}configuration", {"name": "migConfig"})
    holder = conf if variant == "config-globals" else None
    res = ET.SubElement(conf, f"{q}resource", {"name": "migResource"})
    if holder is None:
        holder = res
    for key in sorted(k for k in fixed if k.startswith("gvl:")):
        obj = fixed[key]
        pd = parse_decl(obj.decl, "masterst")
        for sec in pd.decl.sections:
            attrs = {"name": obj.name, **_section_attrs(sec)}
            gv = ET.SubElement(holder, f"{q}globalVars", attrs)
            for d in sec.decls:
                for vname in d.names:
                    vn = f"{obj.name}_{vname}" if variant == "flat-globals" else vname
                    va = {"name": vn}
                    if d.at:
                        va["address"] = d.at
                    v = ET.SubElement(gv, f"{q}variable", va)
                    _ns_type(v, d.type, q)
                    if d.init is not None:
                        _ns_value(ET.SubElement(v, f"{q}initialValue"), d.init, q)
    if variant == "tasks":
        for i, t in enumerate(project.tasks):
            res.insert(i, _task(t, q))
    ET.indent(root, space="  ")
    data: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    text = data.decode("utf-8").replace(
        "<?xml version='1.0' encoding='utf-8'?>", '<?xml version="1.0" encoding="utf-8"?>'
    )
    # тело — как у CODESYS: <xhtml xmlns="http://www.w3.org/1999/xhtml">…</xhtml>
    text = text.replace(f' xmlns:xhtml="{XHTML}"', "")
    text = text.replace("<xhtml:xhtml>", f'<xhtml xmlns="{XHTML}">').replace("</xhtml:xhtml>", "</xhtml>")
    text = text.replace("<xhtml:p>", "<p>").replace("</xhtml:p>", "</p>")
    return (text.replace("\r\n", "\n") + "\n").encode("utf-8")


def _task(t: Task, q: str) -> ET.Element:
    ms = int(t.interval_ms) if t.interval_ms else 100
    attrs = {
        "name": t.name,
        "interval": f"PT{ms / 1000:g}S",
        "priority": str(t.priority if t.priority is not None else 1),
    }
    te = ET.Element(f"{q}task", attrs)
    for p in t.pous:
        ET.SubElement(te, f"{q}pouInstance", {"name": p, "typeName": p})
    return te


def _ns_type(parent: ET.Element, t: A.TypeRef, q: str, wrap: bool = True) -> None:
    holder = ET.SubElement(parent, f"{q}type") if wrap else parent
    name = _ALIASES.get(t.name.upper(), t.name.upper())
    if t.name == "ARRAY" and t.elem is not None:
        arr = ET.SubElement(holder, f"{q}array")
        for lo, hi in t.dims:
            ET.SubElement(arr, f"{q}dimension", {"lower": fmt_expr(lo), "upper": fmt_expr(hi)})
        _ns_type(ET.SubElement(arr, f"{q}baseType"), t.elem, q, wrap=False)
    elif name in ("STRING", "WSTRING"):
        ET.SubElement(holder, f"{q}{name.lower()}", {"length": fmt_expr(t.length)} if t.length is not None else {})
    elif name in _TC6_ELEMENTARY:
        ET.SubElement(holder, f"{q}{name}")
    elif t.name in ("POINTER", "REFERENCE") and t.elem is not None:
        p = ET.SubElement(holder, f"{q}pointer")
        _ns_type(ET.SubElement(p, f"{q}baseType"), t.elem, q, wrap=False)
    else:
        ET.SubElement(holder, f"{q}derived", {"name": t.name})


def _ns_value(parent: ET.Element, e: A.Expr, q: str) -> None:
    if isinstance(e, A.ArrayInit):
        av = ET.SubElement(parent, f"{q}arrayValue")
        for rep, val in e.items:
            v = ET.SubElement(av, f"{q}value", {"repetitionValue": fmt_expr(rep)} if rep is not None else {})
            _ns_value(v, val, q)
    elif isinstance(e, A.StructInit):
        sv = ET.SubElement(parent, f"{q}structValue")
        for name, val in e.fields:
            v = ET.SubElement(sv, f"{q}value", {"member": name})
            _ns_value(v, val, q)
    else:
        ET.SubElement(parent, f"{q}simpleValue", {"value": fmt_expr(e)})
