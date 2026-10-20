"""Корпус правил: ``tests/rules/<ID>/{pos,neg}/`` (раскладка src/ или input.xml) и ``expected.json``.

Позитивный случай должен дать находку правила с ожидаемым исходом (сама находка или в related), негативный —
не дать её. Правила, которые анализатор не выдаёт (визуализация, тревоги — их нет в PLCopen XML), помечены
``emitted: false`` и проверяются по тексту MANUAL_STEPS.md.

    python tools/gen_rule_corpus.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "rules"


def prg(name: str, decl_vars: str, body: str, kind: str = "PROGRAM") -> dict[str, str]:
    decl = f"{kind} {name}\n{decl_vars}"
    return {f"POUs/{name}/{name}.decl.st": decl, f"POUs/{name}/{name}.impl.st": body}


V = "VAR\n    x : INT;\n    b : BOOL;\nEND_VAR\n"


def task_xml(kind: str, interval: str, prio: str, extra: str = "") -> str:
    single = ' single="xEv"' if kind == "Event" else ""
    iv = f' interval="{interval}"' if interval else ""
    ts = (f'<addData><data name="http://www.3s-software.com/plcopenxml/tasksettings" handleUnknown="implementation">'
          f'<TaskSettings KindOfTask="{kind}" Interval="{interval}" IntervalUnit="ms" /></data></addData>')  # fmt: skip
    pou = (
        '<pou name="PRG_A" pouType="program"><interface><localVars><variable name="x"><type><INT/></type></variable>'
        '</localVars></interface><body><ST><xhtml xmlns="http://www.w3.org/1999/xhtml">x := x + 1;</xhtml></ST></body></pou>'
    )
    return ('<?xml version="1.0" encoding="utf-8"?><project xmlns="http://www.plcopen.org/xml/tc6_0200">'
            '<fileHeader companyName="c" productName="p" productVersion="1" creationDateTime="2026-01-01T00:00:00"/>'
            '<contentHeader name="T"><coordinateInfo><fbd><scaling x="1" y="1"/></fbd><ld><scaling x="1" y="1"/></ld>'
            f'<sfc><scaling x="1" y="1"/></sfc></coordinateInfo></contentHeader><types><dataTypes/><pous>{pou}</pous></types>'
            '<instances><configurations><configuration name="D"><resource name="A">'
            f'<task name="T1"{iv} priority="{prio}"{single}><pouInstance name="PRG_A" typeName="PRG_A"/>{ts}</task>{extra}'
            "</resource></configuration></configurations></instances></project>\n")  # fmt: skip


def sfc_xml(cond: str) -> str:
    sys.path.insert(0, str(ROOT / "tools" / "corpus"))
    sys.path.insert(0, str(ROOT / "src"))
    from tc6 import Sfc, pou, project

    s = Sfc()
    a = s.step("A", None, initial=True)
    t = s.transition(a, cond)
    s.jump_step(t, "A")
    decl = "PROGRAM PRG_S\nVAR\n    xGo : BOOL;\nEND_VAR\n"
    return project("S", [pou("PRG_S", "program", decl, s.body())])


def ld_xml(with_fb: bool) -> str:
    """LD с ФБ на цепи (TON) или только с контактами и катушкой; в корпус CODESYS такие тела не входят (боксы ФБ
    в LD import_xml 3.5.17.30 не принимает), правило проверяется на рукописном TC6."""
    sys.path.insert(0, str(ROOT / "tools" / "corpus"))
    sys.path.insert(0, str(ROOT / "src"))
    from tc6 import Graph, ld_body, pou, project

    g = Graph("LD", 1)
    r = g.rail()
    c = g.contact("xIn", r)
    if with_fb:
        t = g.block("TON", [("IN", c), ("PT", g.invar("T#30MS"))], ["Q", "ET"], instance="fbT")
        g.coil("xQ", (t, "Q"))
    else:
        g.coil("xQ", c)
    decl = "PROGRAM PRG_L\nVAR\n    xIn : BOOL;\n    xQ : BOOL;\n    fbT : TON;\nEND_VAR\n"
    return project("L", [pou("PRG_L", "program", decl, ld_body([g]))])


CASES: dict[str, dict] = {  # type: ignore[type-arg]
    "MS-PARSE-01": {"outcome": "manual", "pos": prg("PRG_A", V, "x := := 1;\n"), "neg": prg("PRG_A", V, "x := 1;\n")},
    "MS-ST-01": {"outcome": "review", "pos": prg("FB_A", "VAR_INPUT\n    EN : BOOL;\nEND_VAR\nVAR\n    x : INT;\nEND_VAR\n", "IF EN THEN\n    x := 1;\nEND_IF\n", "FUNCTION_BLOCK"),
                 "neg": prg("FB_A", "VAR_INPUT\n    xEnable : BOOL;\nEND_VAR\nVAR\n    x : INT;\nEND_VAR\n", "IF xEnable THEN\n    x := 1;\nEND_IF\n", "FUNCTION_BLOCK")},
    "MS-ST-02": {"outcome": "auto", "pos": prg("PRG_A", "VAR\n    rLevel_ : REAL;\nEND_VAR\n", "rLevel_ := 1.0;\n"), "neg": prg("PRG_A", "VAR\n    rLevel : REAL;\nEND_VAR\n", "rLevel := 1.0;\n")},
    "MS-ST-04": {"outcome": "verify", "pos": {**prg("PRG_A", "VAR\n    e : E_S;\n    x : INT;\nEND_VAR\n", "CASE e OF\n    E_S.Run:\n        x := 1;\nEND_CASE\n"),
                                              "DUTs/E_S.dut.st": "TYPE E_S : (Idle := 0, Run := 10); END_TYPE\n"},
                 "neg": prg("PRG_A", V, "CASE x OF\n    1:\n        b := TRUE;\nEND_CASE\n")},
    "MS-ST-05": {"outcome": "manual", "pos": prg("PRG_A", "VAR\n    p : POINTER TO INT;\n    x : INT;\nEND_VAR\n", "p := ADR(x);\n"), "neg": prg("PRG_A", V, "x := 1;\n")},
    "MS-ST-07": {"outcome": "review", "pos": {"GVLs/GVL_IO.gvl.st": "VAR_GLOBAL\n    xIn AT %IX0.0 : BOOL;\nEND_VAR\n"},
                 "neg": {"GVLs/GVL_IO.gvl.st": "VAR_GLOBAL\n    xIn : BOOL;\nEND_VAR\n"}},
    "MS-ST-08": {"outcome": "auto", "pos": {**prg("PRG_A", V, "x := GVL_X.g;\n"), "GVLs/GVL_X.gvl.st": "VAR_GLOBAL\n    g : INT;\nEND_VAR\n"},
                 "neg": prg("PRG_A", V, "x := 1;\n")},
    "MS-ST-09": {"outcome": "info", "pos": prg("FB_A", "VAR_TEMP\n    t : INT;\nEND_VAR\n", "t := 1;\n", "FUNCTION_BLOCK"), "neg": prg("FB_A", V, "x := 1;\n", "FUNCTION_BLOCK")},
    "MS-ST-10": {"outcome": "info", "pos": prg("PRG_A", "VAR_INPUT\n    xStart : BOOL;\nEND_VAR\n", ";\n"), "neg": prg("PRG_A", "VAR_INPUT\n    iMode : INT;\nEND_VAR\n", ";\n")},
    "MS-ST-11": {"outcome": "auto", "pos": prg("PRG_A", V, "b S= x > 0;\n"), "neg": prg("PRG_A", V, "IF x > 0 THEN\n    b := TRUE;\nEND_IF\n")},
    "MS-ST-12": {"outcome": "manual", "pos": prg("PRG_A", "VAR\n    r : REFERENCE TO INT;\n    x : INT;\nEND_VAR\n", "r REF= x;\n"), "neg": prg("PRG_A", V, "x := 2;\n")},
    "MS-ST-13": {"outcome": "review", "pos": prg("PRG_A", V, "IF b THEN\n    JMP L;\nEND_IF\nx := 1;\nL:\nx := x + 1;\n"), "neg": prg("PRG_A", V, "IF NOT b THEN\n    x := 1;\nEND_IF\n")},
    "MS-NAME-01": {"outcome": "review", "pos": {**prg("PRG_A", V, "x := GVL_X.g;\n"), "GVLs/GVL_X.gvl.st": "VAR_GLOBAL\n    g : INT;\nEND_VAR\n",
                                                "POUs/GVL_X_g/GVL_X_g.decl.st": "FUNCTION GVL_X_g : INT\n", "POUs/GVL_X_g/GVL_X_g.impl.st": "GVL_X_g := 1;\n"},
                   "neg": {**prg("PRG_A", V, "x := GVL_X.g;\n"), "GVLs/GVL_X.gvl.st": "VAR_GLOBAL\n    g : INT;\nEND_VAR\n"}},
    "MS-NAME-02": {"outcome": "auto", "pos": prg("PRG_A", "VAR\n    Step : INT;\nEND_VAR\n", "Step := 1;\n"), "neg": prg("PRG_A", "VAR\n    iStep : INT;\nEND_VAR\n", "iStep := 1;\n")},
    "MS-DECL-01": {"outcome": "verify", "pos": prg("FB_A", "VAR_IN_OUT\n    x : INT;\nEND_VAR\n", "x := x + 1;\n", "FUNCTION_BLOCK"), "neg": prg("FB_A", "VAR_INPUT\n    x : INT;\nEND_VAR\n", ";\n", "FUNCTION_BLOCK")},
    "MS-DECL-02": {"outcome": "review", "pos": prg("FB_A", "VAR_STAT\n    iCount : INT;\nEND_VAR\n", "iCount := iCount + 1;\n", "FUNCTION_BLOCK"), "neg": prg("FB_A", "VAR\n    iCount : INT;\nEND_VAR\n", "iCount := iCount + 1;\n", "FUNCTION_BLOCK")},
    "MS-DECL-04": {"outcome": "review", "pos": {"GVLs/GVL_C.gvl.st": "VAR_GLOBAL CONSTANT\n    c : INT := 5;\nEND_VAR\n"}, "neg": {"GVLs/GVL_C.gvl.st": "VAR_GLOBAL\n    c : INT := 5;\nEND_VAR\n"}},
    "MS-DECL-06": {"outcome": "review", "pos": {"GVLs/PV.pvl.st": "VAR_GLOBAL PERSISTENT RETAIN\n    p : INT;\nEND_VAR\n"}, "neg": {"GVLs/RV.gvl.st": "VAR_GLOBAL RETAIN\n    p : INT;\nEND_VAR\n"}},
    "MS-RET-01": {"outcome": "info", "pos": {"GVLs/RV.gvl.st": "VAR_GLOBAL RETAIN\n    p : INT;\nEND_VAR\n"}, "neg": {"GVLs/G.gvl.st": "VAR_GLOBAL\n    p : INT;\nEND_VAR\n"}},
    "MS-RET-02": {"outcome": "verify", "pos": {"GVLs/RV.gvl.st": "VAR_GLOBAL RETAIN\n    p : INT;\nEND_VAR\n"}, "neg": {"GVLs/G.gvl.st": "VAR_GLOBAL\n    p : INT;\nEND_VAR\n"}},
    "MS-TYPE-02": {"outcome": "review", "pos": prg("PRG_A", "VAR\n    s : STRING(20);\nEND_VAR\n", "s := 'a';\n"), "neg": prg("PRG_A", "VAR\n    s : STRING;\nEND_VAR\n", "s := 'a';\n")},
    "MS-TYPE-03": {"outcome": "manual", "pos": {"DUTs/U_W.dut.st": "TYPE U_W :\nUNION\n    w : WORD;\n    b : BYTE;\nEND_UNION\nEND_TYPE\n"},
                   "neg": {"DUTs/ST_W.dut.st": "TYPE ST_W :\nSTRUCT\n    w : WORD;\nEND_STRUCT\nEND_TYPE\n"}},
    "MS-TYPE-04": {"outcome": "auto", "pos": {"DUTs/T_P.dut.st": "TYPE T_P : INT(0..100); END_TYPE\n"}, "neg": {"DUTs/ST_W.dut.st": "TYPE ST_W :\nSTRUCT\n    w : WORD;\nEND_STRUCT\nEND_TYPE\n"}},
    "MS-TYPE-05": {"outcome": "review", "pos": prg("PRG_A", "VAR\n    a : ARRAY[0..1, 0..1, 0..1, 0..1] OF INT;\nEND_VAR\n", "a[0, 0, 0, 0] := 1;\n"),
                   "neg": prg("PRG_A", V, "x := 1;\n"), "match_outcome": True},
    "MS-TYPE-06": {"outcome": "review", "pos": prg("PRG_A", "VAR\n    d : DT;\nEND_VAR\n", ";\n"), "neg": prg("PRG_A", "VAR\n    d : DT := DT#2020-01-01-00:00:00;\nEND_VAR\n", ";\n")},
    "MS-TYPE-07": {"outcome": "verify", "pos": prg("PRG_A", "VAR\n    a : INT;\n    b : INT := 2;\nEND_VAR\n", "a := a / b;\n"), "neg": prg("PRG_A", "VAR\n    a : REAL;\n    b : REAL := 2.0;\nEND_VAR\n", "a := a / b;\n")},
    "MS-TYPE-08": {"outcome": "verify", "pos": prg("PRG_A", "VAR\n    t1 : TIME;\n    t2 : TIME;\n    d : TIME;\nEND_VAR\n", "d := t1 - t2;\n"), "neg": prg("PRG_A", V, "x := x - 1;\n")},
    "MS-TYPE-09": {"outcome": "verify", "pos": prg("PRG_A", "VAR\n    r : REAL;\n    i : INT;\nEND_VAR\n", "i := REAL_TO_INT(r);\n"), "neg": prg("PRG_A", "VAR\n    r : REAL;\n    i : INT;\nEND_VAR\n", "r := INT_TO_REAL(i);\n")},
    "MS-EXEC-01": {"outcome": "review", "pos": prg("PRG_A", "VAR\n    t : TON;\nEND_VAR\n", "t(IN := TRUE, PT := T#150MS);\n"), "neg": prg("PRG_A", "VAR\n    t : TON;\nEND_VAR\n", "t(IN := TRUE, PT := T#200MS);\n")},
    "MS-EXEC-02": {"outcome": "review", "pos": {"input.xml": task_xml("Event", "", "1")}, "neg": {"input.xml": task_xml("Cyclic", "100", "1")}},
    "MS-EXEC-03": {"outcome": "review", "pos": {"input.xml": task_xml("Cyclic", "100", "1", '<task name="T2" interval="t#200ms" priority="2"><pouInstance name="PRG_A" typeName="PRG_A"/></task>')},
                   "neg": {"input.xml": task_xml("Cyclic", "100", "1").replace(' priority="1"', "")}},
    "MS-EXEC-04": {"outcome": "info", "pos": prg("PRG_A", V, ";\n"), "neg": prg("FB_A", V, ";\n", "FUNCTION_BLOCK")},
    "MS-EXEC-05": {"outcome": "info", "pos": {**prg("PRG_A", V, "PRG_B();\n"), **prg("PRG_B", V, ";\n")}, "neg": {**prg("PRG_A", V, ";\n"), **prg("PRG_B", V, ";\n")}},
    "MS-EXEC-06": {"outcome": "verify", "pos": {"input.xml": task_xml("Cyclic", "100", "1")}, "neg": {"input.xml": task_xml("Cyclic", "100", "1").replace(' priority="1"', "")}},
    "MS-EXEC-07": {"outcome": "info", "pos": {"input.xml": task_xml("Cyclic", "10", "1")}, "neg": {"input.xml": task_xml("Cyclic", "100", "1")}},
    "MS-LIB-01": {"outcome": "verify", "pos": prg("PRG_A", "VAR\n    c : CTU;\nEND_VAR\n", "c(CU := TRUE, PV := 5);\n"), "neg": prg("PRG_A", "VAR\n    t : TON;\nEND_VAR\n", "t(IN := TRUE, PT := T#200MS);\n")},
    "MS-LIB-02": {"outcome": "manual", "pos": prg("PRG_A", "VAR\n    h : HYSTERESIS;\nEND_VAR\n", ";\n"), "neg": prg("PRG_A", "VAR\n    t : TON;\nEND_VAR\n", ";\n")},
    "MS-ASYNC-01": {"outcome": "manual", "pos": {**prg("PRG_A", "VAR\n    fb : FB_Read;\nEND_VAR\n", "fb(xExecute := TRUE);\n"),
                                                **prg("FB_Read", "VAR_INPUT\n    xExecute : BOOL;\nEND_VAR\n", ";\n", "FUNCTION_BLOCK")},
                    "neg": {**prg("PRG_A", "VAR\n    fb : FB_Read;\nEND_VAR\n", "fb(xRun := TRUE);\n"), **prg("FB_Read", "VAR_INPUT\n    xRun : BOOL;\nEND_VAR\n", ";\n", "FUNCTION_BLOCK")}},
    "MS-IO-01": {"outcome": "manual", "pos": {"GVLs/GVL_IO.gvl.st": "VAR_GLOBAL\n    q AT %QX0.0 : BOOL;\nEND_VAR\n"}, "neg": {"GVLs/GVL_IO.gvl.st": "VAR_GLOBAL\n    q : BOOL;\nEND_VAR\n"}},
    "MS-MARK-01": {"outcome": "info", "pos": prg("PRG_A", V, "// MIGRATION-TODO: GOTO не переведён\nx := 1;\n"), "neg": prg("PRG_A", V, "// обычный комментарий\nx := 1;\n")},
    "MS-ST-03": {"outcome": "auto", "pos": prg("PRG_A", V, ";\n"), "neg": None},
    "MS-SFC-02": {"outcome": "manual", "pos": {"input.xml": sfc_xml("xGo AND NOT SFCPause")}, "neg": {"input.xml": sfc_xml("xGo")}},
    "MS-LD-01": {"outcome": "info", "pos": {"input.xml": ld_xml(True)}, "neg": {"input.xml": ld_xml(False)}},
    "MS-LANG-06": {"outcome": "review", "pos": {"POUs/FB_A/FB_A.decl.st": "FUNCTION_BLOCK FB_A\nVAR_OUTPUT\n    x : INT;\nEND_VAR\n",
                                                "POUs/FB_A/FB_A.impl.st": ";\n", "POUs/FB_A/Inc.method.decl.st": "METHOD Inc\n",
                                                "POUs/FB_A/Inc.method.impl.st": "x := x + 1;\n"},
                   "neg": prg("FB_A", "VAR_OUTPUT\n    x : INT;\nEND_VAR\n", "x := x + 1;\n", "FUNCTION_BLOCK")},
    "MS-LANG-07": {"outcome": "review", "pos": None, "neg": None, "note": "действия есть только в PLCopen XML: корпус УДР-1 (SFC) и тесты test_lower"},
}  # fmt: skip

# Правила, которые выдаёт понижение графики/SFC/IL (проверяются корпусом УДР-1, tests/unit/test_lower.py)
LOWERING = {"MS-LANG-01": "FB_LevelAlarm", "MS-LANG-02": "PRG_Permissives", "MS-LANG-03": "FB_DoseCtrl", "MS-LANG-04": "PRG_FillSeq",
            "MS-LANG-05": "FB_PulseCount", "MS-SFC-01": "PRG_FillSeq", "MS-FBD-01": "",
            "MS-LANG-07": ""}  # fmt: skip
NOT_EMITTED = {"MS-VISU-01": "визуализация не попадает в PLCopen XML — пункт MANUAL_STEPS «Не переносится»",
               "MS-ALARM-01": "AlarmManager не попадает в PLCopen XML — пункт MANUAL_STEPS «Не переносится»"}  # fmt: skip


def render() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for rid, case in CASES.items():
        exp: dict[str, object] = {"rule": rid, "pos": {"outcome": case["outcome"]} if case.get("pos") else None,
                                  "neg": {"absent": True} if case.get("neg") else None}  # fmt: skip
        if case.get("note"):
            exp["note"] = case["note"]
        if case.get("match_outcome"):
            exp["match_outcome"] = True
        for part in ("pos", "neg"):
            for rel, text in (case.get(part) or {}).items():
                files[OUT / rid / part / rel] = text
        files[OUT / rid / "expected.json"] = json.dumps(exp, ensure_ascii=False, indent=1) + "\n"
    for rid, pou in LOWERING.items():
        if rid in CASES:
            continue
        files[OUT / rid / "expected.json"] = json.dumps({"rule": rid, "corpus": "corpus/udr1/source.handmade.xml", "pou": pou},
                                                        ensure_ascii=False, indent=1) + "\n"  # fmt: skip
    for rid, why in NOT_EMITTED.items():
        files[OUT / rid / "expected.json"] = (
            json.dumps({"rule": rid, "emitted": False, "why": why}, ensure_ascii=False, indent=1) + "\n"
        )
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    files = render()
    bad = 0
    for path, text in sorted(files.items()):
        if a.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print(f"устарел: {path.relative_to(ROOT)}")
                bad += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"файлов корпуса правил: {len(files)}" + (f", устаревших: {bad}" if a.check else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
