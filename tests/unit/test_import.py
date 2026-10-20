"""Импорт PLCopen XML (три размещения, CFC в addData, методы/свойства/интерфейсы, Interval) и раскладки src/."""

from __future__ import annotations

from pathlib import Path

import pytest

from cds2ms.cdsfront.importer import layout, plcopen
from cds2ms.cdsfront.importer.plcopen import parse_interval_ms
from cds2ms.cdsfront.importer.xmltree import XmlError, parse

ROOT = Path(__file__).resolve().parents[2]

POU = (
    '<pou name="PRG_A" pouType="program"><interface><localVars><variable name="x"><type><INT/></type>'
    '<initialValue><simpleValue value="5"/></initialValue></variable></localVars></interface>'
    '<body><ST><xhtml xmlns="http://www.w3.org/1999/xhtml">x := x + 1;</xhtml></ST></body></pou>'
)
HEAD = '<?xml version="1.0" encoding="utf-8"?><project xmlns="http://www.plcopen.org/xml/tc6_0200"><fileHeader companyName="c" productName="CODESYS" productVersion="CODESYS V3.5 SP17 Patch 3" creationDateTime="2026-01-01T00:00:00"/><contentHeader name="P"><coordinateInfo><fbd><scaling x="1" y="1"/></fbd><ld><scaling x="1" y="1"/></ld><sfc><scaling x="1" y="1"/></sfc></coordinateInfo></contentHeader>'


def test_types_placement() -> None:
    p = plcopen.load(
        (
            HEAD + f"<types><dataTypes/><pous>{POU}</pous></types><instances><configurations/></instances></project>"
        ).encode(),
        "a.xml",
    )
    assert p.placements == ["types"] and p.pous[0].name == "PRG_A"
    assert "x : INT := 5;" in p.pous[0].decl_text  # объявление из структуры TC6
    assert p.ide == "CODESYS" and p.ide_version.endswith("Patch 3")


def test_resource_placement_with_task() -> None:
    xml = (HEAD + '<types><dataTypes/><pous/></types><instances><configurations><configuration name="Dev"><resource name="App">'
           '<task name="T1" interval="t#20ms" priority="2"><pouInstance name="PRG_A" typeName="PRG_A"/></task>'
           f'<addData><data name="http://www.3s-software.com/plcopenxml/pou" handleUnknown="implementation">{POU}</data></addData>'
           "</resource></configuration></configurations></instances></project>")  # fmt: skip
    p = plcopen.load(xml.encode(), "r.xml")
    assert p.placements == ["resource"]
    t = p.tasks[0]
    assert (t.name, t.kind, t.interval_ms, t.priority, t.pous) == ("T1", "Cyclic", 20.0, 2, ["PRG_A"])


def test_application_placement() -> None:
    xml = (HEAD + '<types><dataTypes/><pous/></types><instances><configurations/></instances><addData>'
           '<data name="http://www.3s-software.com/plcopenxml/application" handleUnknown="implementation"><resource name="App">'
           f'<addData><data name="http://www.3s-software.com/plcopenxml/pou" handleUnknown="implementation">{POU}</data></addData>'
           "</resource></data></addData></project>")  # fmt: skip
    p = plcopen.load(xml.encode(), "app.xml")
    assert p.placements == ["application"] and p.pous[0].lang == "ST"


@pytest.mark.parametrize(
    ("raw", "unit", "ms"),
    [
        ("t#1000ms", None, 1000.0),
        ("T#1s500ms", None, 1500.0),
        ("100", "ms", 100.0),
        ("10000", "us", 10.0),
        ("", None, None),
    ],
)
def test_interval(raw: str, unit: str | None, ms: float | None) -> None:
    assert parse_interval_ms(raw, unit) == ms


def test_line_numbers_and_bom(handmade_bytes: bytes) -> None:
    p = plcopen.load(b"\xef\xbb\xbf" + handmade_bytes, "u.xml")
    assert p.has_bom
    f = p.pou("F_Clamp")
    assert f is not None and f.origin.line > 1 and f.body is not None and f.body.line >= f.origin.line


def test_corpus_languages(handmade_bytes: bytes) -> None:
    p = plcopen.load(handmade_bytes, "source.handmade.xml")
    langs = p.languages()
    for lang in ("ST", "FBD", "LD", "CFC", "SFC", "IL"):
        assert langs.get(lang, 0) >= 2, lang
    cfc = p.pou("FB_DoseCtrl")
    assert cfc is not None and cfc.lang == "CFC" and any(e.exec_order for e in cfc.body.elems)  # type: ignore[union-attr]
    pump = p.pou("FB_DosingPump")
    assert pump is not None and [m.name for m in pump.methods] == ["Dose", "NeedsMore", "Prime"]
    assert pump.properties[0].get is not None
    assert [i.name for i in p.interfaces] == ["I_Device"]
    assert {g.name for g in p.gvls} == {"GVL_IO", "GVL_Retain", "GVL_Const"}
    assert [t.kind for t in p.tasks] == ["Cyclic", "Cyclic", "Event"]
    sfc = p.pou("PRG_FillSeq")
    assert sfc is not None and len(sfc.actions) == 8


def test_bad_xml() -> None:
    with pytest.raises(XmlError):
        parse(b"<project><a></project>")
    with pytest.raises(ValueError):
        plcopen.load(b"<root/>", "x.xml")


def test_layout_loader() -> None:
    files = {
        "POUs/FB_A/FB_A.decl.st": "FUNCTION_BLOCK FB_A\nVAR_INPUT\n    x : INT;\nEND_VAR\n",
        "POUs/FB_A/FB_A.impl.st": "x := x + 1;\n",
        "POUs/FB_A/Run.method.decl.st": "METHOD Run : BOOL\n",
        "POUs/FB_A/Run.method.impl.st": "Run := TRUE;\n",
        "POUs/FB_A/Count.prop.decl.st": "PROPERTY Count : INT\n",
        "POUs/FB_A/Count.get.impl.st": "Count := x;\n",
        "DUTs/E_M.dut.st": "TYPE E_M : (A, B); END_TYPE\n",
        "GVLs/GVL_X.gvl.st": "VAR_GLOBAL\n    g : INT;\nEND_VAR\n",
        "GVLs/PV.pvl.st": "VAR_GLOBAL PERSISTENT RETAIN\n    p : INT;\nEND_VAR\n",
        "Interfaces/I_A/I_A.itf.st": "INTERFACE I_A\n",
        "Interfaces/I_A/Run.method.decl.st": "METHOD Run : BOOL\n",
    }
    p = layout.load_files(files, name="L")
    fb = p.pou("FB_A")
    assert fb is not None and fb.kind == "functionBlock" and fb.methods[0].name == "Run"
    assert fb.properties[0].get is not None and fb.properties[0].set is None
    assert fb.body is not None and fb.body.file.endswith("FB_A.impl.st")
    assert [g.persistent for g in p.gvls] == [False, True]
    assert p.interfaces[0].methods[0].body is None


def test_layout_s7_chain() -> None:
    p = layout.load(ROOT / "corpus" / "s7-chain" / "src")
    assert len(p.pous) == 26 and len(p.gvls) == 7 and len(p.duts) == 7
