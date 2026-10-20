"""Формы экспорта CODESYS 3.5.17.30 по языкам (tests/fixtures/sp17, снятые tools/codesys/corpus.py) читаются и
понижаются; форма — та, что описана в docs/FORMAT-OUT.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from cds2ms import api
from cds2ms.cdsfront.importer import plcopen

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sp17"


def load(name: str):  # type: ignore[no-untyped-def]
    return plcopen.load((FIX / f"form_{name}.xml").read_bytes(), f"form_{name}.xml")


def kinds(pou) -> dict[str, int]:  # type: ignore[no-untyped-def]
    out: dict[str, int] = {}
    for e in pou.body.elems:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out


def test_fixture_set() -> None:
    names = sorted(p.name for p in FIX.glob("form_*.xml"))
    assert len(names) == 15
    for p in FIX.glob("form_*.xml"):
        raw = p.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf<?xml") and b'productVersion="CODESYS V3.5 SP17 Patch 3"' in raw


def test_fbd_form() -> None:
    p = load("FB_LevelAlarm")
    k = kinds(p.pous[0])
    assert p.pous[0].lang == "FBD" and k["jump"] == 1 and k["label"] == 1 and k["vendorElement"] == 1
    ids = [int(e.local_id) for e in p.pous[0].body.elems if e.local_id.isdigit()]
    assert min(ids) >= 10**10  # сети по localId div 10^10


def test_ld_form() -> None:
    p = load("PRG_PumpInterlock")
    k = kinds(p.pous[0])
    assert k["leftPowerRail"] == 1 and k["rightPowerRail"] == 1 and k["vendorElement"] == 5 and k["block"] == 2
    rail = next(e for e in p.pous[0].body.elems if e.kind == "leftPowerRail")
    assert rail.local_id == "0"


def test_cfc_form() -> None:
    p = load("FB_DoseCtrl")
    pou = p.pous[0]
    assert pou.lang == "CFC" and pou.body.lang == "CFC"
    wires = [e for e in pou.body.elems if e.kind == "connector"]
    assert len(wires) == 21 and all(not e.name for e in wires)  # провода — безымянные connector
    assert sorted(e.exec_order for e in pou.body.elems if e.kind == "block") == list(range(1, 9))


def test_sfc_form() -> None:
    p = load("PRG_CipSeq")
    pou = p.pous[0]
    assert pou.lang == "SFC" and [a.name for a in pou.actions] == ["ActAcid", "ActCaustic", "ActRinseIn", "ActRinseOut"]
    quals = sorted({a.qualifier for e in pou.body.elems if e.kind == "actionBlock" for a in e.actions})
    assert quals == ["N", "P"]
    assert "_ActRinseOut.x" in pou.actions[3].body.text


def test_oop_form() -> None:
    p = load("FB_DosingPump")
    pou = p.pous[0]
    assert [m.name for m in pou.methods] == ["Dose", "NeedsMore", "Prime"] and [x.name for x in pou.properties] == [
        "Dosed"
    ]
    assert "EXTENDS FB_DeviceBase IMPLEMENTS I_Device" in pou.decl_text
    assert load("I_Device").interfaces[0].name == "I_Device"


def test_gvl_dut_form() -> None:
    assert load("GVL_Retain").gvls[0].decl_text.startswith("VAR_GLOBAL RETAIN")
    assert "AT %QX0.0" in load("GVL_IO").gvls[0].decl_text
    assert load("ST_Recipe").duts[0].name == "ST_Recipe" and load("E_DoseState").duts[0].name == "E_DoseState"


@pytest.mark.parametrize("name", ["FB_LevelAlarm", "FB_ValveCmd", "PRG_Permissives", "PRG_PumpInterlock", "FB_DoseCtrl",
                                  "FB_RatioCalc", "PRG_FillSeq", "PRG_CipSeq"])  # fmt: skip
def test_lowering_without_manual(name: str) -> None:
    m = api.migrate(load(name))
    lp = m.lowered.pous[0]
    assert not [n for n in lp.notes if n.outcome == "manual"], [n.message for n in lp.notes]
    assert lp.body.strip()
