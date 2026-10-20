"""Понижение графики, SFC, IL, ООП и структурировщик переходов."""

from __future__ import annotations

from cds2ms.cdsfront.lower.common import Names, paren
from cds2ms.cdsfront.lower.graph import lower_graph
from cds2ms.cdsfront.lower.il import lower_il, parse_il
from cds2ms.cdsfront.lower.jumps import Seg, segments_from_body, structure
from cds2ms.cdsfront.lower.oop import rename_idents
from cds2ms.cdsfront.st.parser import parse_body


def test_structure_forward_if() -> None:
    segs = [
        Seg("stmt", "a := 1;\n"),
        Seg("jmp", "L", "x"),
        Seg("stmt", "b := 2;\n"),
        Seg("label", "L"),
        Seg("stmt", "c := 3;\n"),
    ]
    st = structure(segs)
    assert st.mode == "if"
    assert st.text == "a := 1;\nIF NOT x THEN\n    b := 2;\nEND_IF;\nc := 3;\n"
    assert not parse_body(st.text).diagnostics


def test_structure_backward_machine() -> None:
    segs = [Seg("label", "L"), Seg("stmt", "i := i + 1;\n"), Seg("jmp", "L", "i < 3"), Seg("stmt", "done := TRUE;\n")]
    st = structure(segs)
    assert st.mode == "machine" and ("migPc", "INT") in st.extra_vars
    assert "WHILE migPc >= 0 DO" in st.text and "CONTINUE;" in st.text
    assert not parse_body(st.text).diagnostics


def test_structure_crossing_is_machine() -> None:
    segs = [
        Seg("jmp", "A", "c1"),
        Seg("jmp", "B", "c2"),
        Seg("label", "A"),
        Seg("stmt", "x := 1;\n"),
        Seg("label", "B"),
    ]
    assert structure(segs).mode == "machine"


def test_structure_missing_label() -> None:
    import pytest

    with pytest.raises(ValueError):
        structure([Seg("jmp", "Nowhere")])


def test_segments_from_body() -> None:
    pb = parse_body("x := 1;\nIF a THEN\n    JMP L;\nEND_IF\ny := 2;\nL:\nz := 3;\n")
    segs = segments_from_body(pb)
    assert segs is not None and [s.kind for s in segs] == ["stmt", "jmp", "stmt", "label", "stmt"]
    assert segments_from_body(parse_body("FOR i := 1 TO 2 DO JMP L; END_FOR\nL:\n")) is None


def test_paren() -> None:
    assert paren("a") == "a"
    assert paren("F(x, y)") == "F(x, y)"
    assert paren("a + b") == "(a + b)"
    assert paren("(a) + (b)") == "((a) + (b))"
    assert paren("NOT x") == "NOT x"


def test_names_unique() -> None:
    n = Names({"migNet1_1"})
    assert n.new("migNet1_1") == "migNet1_12"
    assert n.new("migX") == "migX"


def test_rename_idents_skips_members_and_this() -> None:
    out = rename_idents("THIS^.a := a + inst.a; b := a;", {"a": "M_a"})
    assert out == "M_a := M_a + inst.a; b := M_a;"


def test_fbd_networks_and_jump(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    x = udr1_migration.lowered.pou("FB_LevelAlarm")
    assert "IF NOT xBypass THEN" in x.body and "fbLatch(SET := rLevel > rHiHi, RESET1 := xAck);" in x.body
    assert x.body.index("сеть 4") > x.body.index("END_IF;")  # метка сети 4 — после хвоста перехода


def test_fbd_return(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    x = udr1_migration.lowered.pou("FB_ValveCmd")
    assert "IF xInterlock THEN\n    RETURN;\nEND_IF;" in x.body
    assert "fbFbDelay(IN := xOpen AND NOT xFbOpen, PT := T#40MS);" in x.body


def _en_eno_project(root) -> bytes:  # type: ignore[no-untyped-def]
    """Боксы с EN/ENO (FBD и LD): в корпус CODESYS не входят (импорт PLCopen их не принимает, docs/FORMAT-OUT.md),
    понижение проверяется на рукописном TC6."""
    import sys

    sys.path.insert(0, str(root / "tools" / "corpus"))
    from tc6 import Graph, fbd_body, ld_body, pou, project

    d1 = ("FUNCTION_BLOCK FB_En\nVAR_INPUT\n    xA : BOOL;\n    xB : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xQ : BOOL;\n"
          "    xEno : BOOL;\nEND_VAR\nVAR\n    fbT : TON;\nEND_VAR\n")  # fmt: skip
    n = Graph("FBD", 1)
    a = n.block("AND", [("In1", n.invar("xA")), ("In2", n.invar("xB"))], ["Out1"])
    t = n.block("TON", [("EN", (a, "Out1")), ("IN", n.invar("TRUE")), ("PT", n.invar("T#40MS"))], ["ENO", "Q", "ET"],
                instance="fbT")  # fmt: skip
    n.outvar("xQ", (t, "Q"))
    n.outvar("xEno", (t, "ENO"))
    d2 = "PROGRAM PRG_En\nVAR_INPUT\n    xA : BOOL;\nEND_VAR\nVAR_OUTPUT\n    iCnt : INT;\nEND_VAR\n"
    g = Graph("LD", 1)
    r = g.rail()
    e = g.contact("xA", r, edge="rising")
    add = g.block("ADD", [("EN", e), ("In1", g.invar("iCnt")), ("In2", g.invar("1"))], ["Out1"])
    g.outvar("iCnt", (add, "Out1"))
    return project(
        "EN", [pou("FB_En", "functionBlock", d1, fbd_body([n])), pou("PRG_En", "program", d2, ld_body([g]))]
    ).encode()


def test_fbd_ld_en_eno(root) -> None:  # type: ignore[no-untyped-def]
    from cds2ms import api

    m = api.migrate(api.load_bytes("en.xml", _en_eno_project(root)))
    fb = m.lowered.pou("FB_En")
    assert fb is not None
    assert "IF xA AND xB THEN\n    fbT(IN := TRUE, PT := T#40MS);\nEND_IF;" in fb.body
    assert "xEno := migEno" in fb.body
    prg = m.lowered.pou("PRG_En")
    assert prg is not None
    assert "IF migTrig1_1.Q THEN" in prg.body and ":= iCnt + 1;" in prg.body


def test_ld_edges_set_reset(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    x = udr1_migration.lowered.pou("PRG_Permissives")
    assert "IF xHighPress THEN\n    xTrip := TRUE;" in x.body
    assert "migTrig4_1(CLK := xStartPb);" in x.body and "R_TRIG" in x.decl
    assert "IF xStopPb OR xTrip THEN\n    xRunLatch := FALSE;" in x.body


def test_ld_parallel_and_operator_boxes(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    x = udr1_migration.lowered.pou("PRG_PumpInterlock")
    assert "xPumpCmd := (xAuto AND xPermit) OR xManual;" in x.body
    assert "xLamp := xPumpCmd OR xLampTest;" in x.body
    assert "iStarts := SEL(xStartPulse, iStarts, iNext);" in x.body


def test_ld_coil_chain_temp(root) -> None:  # type: ignore[no-untyped-def]
    """Катушка → катушка с отводом по IEC (катушка передаёт поток): временная переменная сети. В экспортах CODESYS
    такой формы нет — import_xml сводит отвод в общий узел перед катушками (docs/FORMAT-OUT.md)."""
    import sys

    sys.path.insert(0, str(root / "tools" / "corpus"))
    from cds2ms import api
    from tc6 import Graph, ld_body, pou, project

    g = Graph("LD", 1)
    r = g.rail()
    a = g.contact("xA", r)
    b = g.contact("xB", a)
    m = g.contact("xM", r)
    c1 = g.coil("xQ1", [b, m])
    t = g.contact("xT", r)
    g.coil("xQ2", [c1, t])
    decl = "PROGRAM PRG_C\nVAR\n    xA : BOOL;\n    xB : BOOL;\n    xM : BOOL;\n    xT : BOOL;\n    xQ1 : BOOL;\n    xQ2 : BOOL;\nEND_VAR\n"
    m2 = api.migrate(api.load_bytes("c.xml", project("C", [pou("PRG_C", "program", decl, ld_body([g]))]).encode()))
    body = m2.lowered.pou("PRG_C").body  # type: ignore[union-attr]
    assert ":= (xA AND xB) OR xM;" in body and "xQ2 := migNet1_" in body


def test_cfc_order_and_feedback(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    x = udr1_migration.lowered.pou("FB_DoseCtrl")
    lines = [ln for ln in x.body.splitlines() if ln.strip()]
    assert lines[0] == "migCfc1 := rSp - rPv;"
    assert "migCfc5 := LIMIT(0.0, migCfc5 + (migCfc1 * rKi), 100.0);" in x.body  # вход от блока 5 — прошлый цикл
    r = udr1_migration.lowered.pou("FB_RatioCalc")
    assert "migCfc4 := migCfc4 + ((migCfc1 - migCfc4) * 0.5);" in r.body


def test_sfc_automaton(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    x = udr1_migration.lowered.pou("PRG_FillSeq")
    b = x.body
    assert b.index("migS_Init_x := migS_Init_xn;") < b.index("FOR migSfcPass := 1 TO 2 DO") < b.index("(* переходы *)")
    assert "migA_ActFlush_q := (migS_Fill_x AND migS_Fill_t < T#30MS);" in b
    assert "migA_ActAlarm_q := (migS_Heat_x AND migS_Heat_t >= T#50MS);" in b
    assert "migA_ActMixer_s := (migA_ActMixer_s OR migS_Mix_x) AND NOT (migS_Done_x);" in b
    assert b.index("ActAlpha") < b.index("ActZeta")  # алфавитный порядок действий
    assert "(migS_Mix_t >= T#40MS)" in b  # шаг.t в условии перехода
    c = udr1_migration.lowered.pou("PRG_CipSeq")
    assert "migA_ActRinseIn_q := (migS_Rinse_x AND NOT migS_Rinse_xp);" in c.body
    assert "migA_ActRinseOut_q := migS_Rinse_x;" in c.body


def test_sfc_p0_p1(root) -> None:  # type: ignore[no-untyped-def]
    """P1/P0 (вход и выход шага) CODESYS 3.5.17 не принимает («is not a valid qualifier», docs/FORMAT-OUT.md);
    понижение остаётся для экспортов других сред и проверяется на рукописном TC6."""
    import sys

    sys.path.insert(0, str(root / "tools" / "corpus"))
    from cds2ms import api
    from tc6 import Sfc, pou, project

    s = Sfc()
    a = s.step("A", None, initial=True)
    t = s.transition(a, "xGo")
    b = s.step("B", t)
    s.actions(b, [("P1", "ActIn", ""), ("P0", "ActOut", "")])
    t2 = s.transition(b, "NOT xGo")
    s.jump_step(t2, "A")
    decl = "PROGRAM PRG_P\nVAR_INPUT\n    xGo : BOOL;\nEND_VAR\nVAR_OUTPUT\n    iIn : INT;\n    iOut : INT;\nEND_VAR\n"
    acts = {"ActIn": "iIn := iIn + 1;\n", "ActOut": "iOut := iOut + 1;\n"}
    m = api.migrate(api.load_bytes("p.xml", project("P", [pou("PRG_P", "program", decl, s.body(), acts)]).encode()))
    body = m.lowered.pou("PRG_P").body  # type: ignore[union-attr]
    assert "migA_ActIn_q := (migS_B_x AND NOT migS_B_xp);" in body
    assert "migA_ActOut_q := (migS_B_xp AND NOT migS_B_x);" in body


def test_il_cr_and_function_call() -> None:
    from cds2ms.cdsfront.importer.plcopen import load

    lr = lower_il("    LD a\n    AND( b\n    OR c\n    )\n    ST q\n    LD x\n    ADD 1\n    ST x\n", None, {}, Names())
    assert "q := a AND (b OR c);" in lr.body
    assert "x := migCr" in lr.body or "x := x + 1;" in lr.body
    assert [i.op for i in parse_il("lbl: LD a\n CAL fb(\n IN := a,\n PT := T#1s)\n")] == ["LD", "CAL"]
    del load


def test_il_corpus(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    f = udr1_migration.lowered.pou("F_ScaleIL")
    assert "F_Clamp(rAcc, 0.0, 100.0)" in f.body and "WHILE migPc >= 0 DO" in f.body
    p = udr1_migration.lowered.pou("FB_PulseCount")
    assert "fbEdge(CLK := xPulse);\n" in p.body


def test_oop_dispatch(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    fb = udr1_migration.lowered.pou("FB_DosingPump")
    assert "migCall : INT;" in fb.decl and "Dose_rTotal_mlOut : REAL;" in fb.decl
    assert "IF migCall <> 0 THEN" in fb.body and "(* SUPER^() *)" in fb.body
    assert "EXTENDS" not in fb.decl
    prg = udr1_migration.lowered.pou("PRG_OopDemo")
    assert "fbPump(migCall := 3, Dose_rAmount_ml := 0.25, Dose_rTotal_ml := rTotal_ml);" in prg.body
    assert "rTotal_ml := fbPump.Dose_rTotal_mlOut;" in prg.body
    assert "WHILE TRUE DO" in prg.body and "itfDev" not in prg.decl


def test_lowered_text_parses(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    for x in udr1_migration.lowered.pous:
        assert not parse_body(x.body).diagnostics, x.name


def test_graph_without_symbols() -> None:
    from cds2ms.ir.model import Body, Conn, GElem, Pin

    elems = [
        GElem("1", "inVariable", expr="a"),
        GElem("2", "inVariable", expr="b"),
        GElem(
            "3",
            "block",
            type_name="AND",
            inputs=[Pin("In1", [Conn("1")]), Pin("In2", [Conn("2")])],
            outputs=[Pin("Out")],
        ),
        GElem("4", "outVariable", expr="q", inputs=[Pin("", [Conn("3", "Out")])]),
    ]
    lr = lower_graph(Body("FBD", elems=elems), None, {}, Names())
    assert "q := a AND b;" in lr.body
