"""Симулятор: семантика профилей, интерпретатор ST, режимы R1/R2, разбор значений сценариев."""

from __future__ import annotations

import math

import pytest

from cds2ms import profiles
from cds2ms.sim.interp import Machine, parse_duration_ms
from cds2ms.sim.runner import parse_value, read_csv, run, same, scenarios
from cds2ms.sim.semantics import SimError, all_variants, codesys, coerce, f32, masterplc, real_to_int, wrap_int


def machine(body: str, decl: str, sem=None) -> Machine:  # type: ignore[no-untyped-def]
    return Machine({"P": (decl, body)}, [], [], sem or codesys())


def run_once(body: str, decl: str, sem=None) -> dict:  # type: ignore[no-untyped-def,type-arg]
    m = machine(body, decl, sem)
    inst = m.program("P")
    m.call_instance(inst, 0)
    return dict(inst.vars)


DECL = "PROGRAM P\nVAR\n    i : INT;\n    r : REAL;\n    t : TIME;\n    x : BOOL;\n    d : DINT;\n    s : STRING(10);\nEND_VAR\n"


def test_wrap_and_coerce() -> None:
    assert wrap_int(32768, 16, True) == -32768 and wrap_int(-1, 16, False) == 65535
    c = codesys()
    assert coerce(c, "INT", 40000) == 40000 - 65536 and coerce(c, "BOOL", 1) is True
    assert coerce(c, "REAL", 16777217.0) == 16777216.0  # float32
    assert coerce(c, "TIME", -1) == 2**32 - 1  # TIME в CODESYS беззнаковый 32 бит
    assert f32(0.1) != 0.1 and math.isinf(f32(1e300))


def test_real_to_int_rounding() -> None:
    c = codesys()
    assert real_to_int(c, 2.5) == 3 and real_to_int(c, -1.5) == -2
    even = c.variant(real_to_int_half="even")
    assert real_to_int(even, 2.5) == 2
    with pytest.raises(SimError):
        real_to_int(c, math.nan)


def test_masterplc_profile_variants() -> None:
    prof = profiles.load(profiles.TARGET)
    base = masterplc(prof.semantics, prof.variants)
    assert base.name == "masterplc" and base.period_ms == int(prof.semantics["task_period_default_ms"])
    vs = all_variants(base, prof.variants)
    assert vs[0] == base and len(vs) >= 2
    labels = [v.label() for v in vs]
    assert len(set(labels)) == len(labels)


def test_interp_arithmetic_and_overflow() -> None:
    v = run_once("i := 32767;\ni := i + 1;\nd := -7 / 2;\nr := 1.0 / 3.0;\nx := 5 MOD 3 = 2;\n", DECL)
    assert v["i"] == -32768 and v["d"] == -3 and v["x"] is True
    assert v["r"] == f32(1.0 / 3.0)


def test_interp_div_zero_profiles() -> None:
    with pytest.raises(SimError):
        run_once("i := 0;\ni := 1 / i;\n", DECL)
    v = run_once("i := 0;\ni := 1 / i;\n", DECL, codesys().variant(div_zero="zero"))
    assert v["i"] == 0


def test_interp_control_flow() -> None:
    body = ("d := 0;\nFOR i := 1 TO 10 BY 3 DO\n    d := d + i;\nEND_FOR;\nWHILE d < 30 DO\n    d := d + 1;\n"
            "    IF d = 25 THEN\n        EXIT;\n    END_IF;\nEND_WHILE;\nCASE d OF\n    25: x := TRUE;\nELSE\n    x := FALSE;\nEND_CASE;\n")  # fmt: skip
    v = run_once(body, DECL)
    assert v["d"] == 25 and v["x"] is True


def test_interp_strings_and_time() -> None:
    v = run_once("s := CONCAT('abc', 'defghijkl');\nt := T#1S + T#250MS;\n", DECL)
    assert v["s"] == "abcdefghij" and v["t"] == 1250  # STRING(10) усекает
    assert parse_duration_ms("T#1h2m3s4ms") == 3723004 and parse_duration_ms("TIME#1.5s") == 1500


def test_ton_timing() -> None:
    decl = "PROGRAM P\nVAR\n    fb : TON;\n    q : BOOL;\n    et : TIME;\nEND_VAR\n"
    m = machine("fb(IN := TRUE, PT := T#150MS);\nq := fb.Q;\net := fb.ET;\n", decl)
    inst = m.program("P")
    seen = []
    for t in range(0, 300, 50):
        m.call_instance(inst, t)
        seen.append((t, inst.vars["q"], inst.vars["et"]))
    assert seen[3] == (150, True, 150) and seen[2] == (100, False, 100)


def test_r_trig_first_call() -> None:
    decl = "PROGRAM P\nVAR\n    r : R_TRIG;\n    f : F_TRIG;\n    q : BOOL;\n    qf : BOOL;\n    c : BOOL;\nEND_VAR\n"
    m = machine("r(CLK := c);\nf(CLK := c);\nq := r.Q;\nqf := f.Q;\n", decl)
    inst = m.program("P")
    inst.vars["c"] = True
    m.call_instance(inst, 0)
    assert inst.vars["q"] is True and inst.vars["qf"] is False  # F_TRIG без фронта в первом вызове
    inst.vars["c"] = False
    m.call_instance(inst, 10)
    assert inst.vars["q"] is False and inst.vars["qf"] is True


def test_parse_values_and_same() -> None:
    assert parse_value("BOOL", "TRUE") is True and parse_value("INT", "-3") == -3
    assert parse_value("WORD", "16#00C1") == 0xC1 and parse_value("TIME", "T#150MS") == 150
    assert parse_value("REAL", "1.5") == 1.5
    assert same(1.0, 1.0004, 0.001) and not same(1.0, 1.1, 0.001) and same(True, True, 0.0)


CSV = """scenario,cycle,t_ms,in.xIn:BOOL,out.xQ:BOOL,boundary,comment
A,1,0,FALSE,FALSE,FALSE,
A,2,40,TRUE,FALSE,FALSE,
A,3,120,TRUE,FALSE,FALSE,
A,4,250,TRUE,TRUE,FALSE,
B,1,0,FALSE,FALSE,FALSE,
"""


def test_regimes_r1_r2() -> None:
    decl = "PROGRAM P\nVAR_INPUT\n    xIn : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xQ : BOOL;\nEND_VAR\nVAR\n    fb : TON;\nEND_VAR\n"
    rows = read_csv(CSV)
    sc = scenarios(rows)
    assert [s[0].scenario for s in sc] == ["A", "B"]
    r1 = run(machine("fb(IN := xIn, PT := T#150MS);\nxQ := fb.Q;\n", decl), "P", sc[0], "R1")
    assert [v["xQ"] for v in r1.values if v] == [False, False, False, True]
    r2 = run(machine("fb(IN := xIn, PT := T#150MS);\nxQ := fb.Q;\n", decl), "P", sc[0], "R2", period_ms=100)
    assert r2.values[0] is not None and len(r2.values) == 4
    assert r2.values[3] is not None and r2.values[3]["xQ"] is True  # цикл 3 (300 мс): TON с 100 мс истёк
