"""Лексер, разборщик и печать ST: round-trip байт в байт, приоритеты, восстановление после ошибок."""

from __future__ import annotations

import pytest

from cds2ms.cdsfront.st import ast as A
from cds2ms.cdsfront.st.lexer import Kind, significant, tokenize
from cds2ms.cdsfront.st.parser import parse_body, parse_decl, parse_expression
from cds2ms.cdsfront.st.printer import fmt_expr, fmt_stmts, print_tokens

SAMPLE = """(* заголовок (* вложенный *) *)
IF xStart AND NOT xStop THEN
    fbTon(IN := xRun, PT := T#150MS);   // таймер
    xOut S= fbTon.Q;
ELSIF a.3 THEN
    arr[i, j] := -2 ** 2;
END_IF
CASE eState OF
  E_State.Idle, E_State.Run: x := 16#FF;
  10..20: y := DT#2020-01-01-12:00:00;
ELSE
  JMP lbl;
END_CASE
lbl:
FOR i := 10 TO 0 BY -1 DO x := x + REAL_TO_INT(1.5E3); END_FOR
WHILE x > 0 AND_THEN y DO x := x - 1; END_WHILE
REPEAT x := x + 1; UNTIL x > 10 END_REPEAT
y := inst.Start(a := 1, q => z);
THIS^.M();
{attribute 'x'} s := 'a$'b"' + "w";
"""


def test_lossless_roundtrip() -> None:
    assert print_tokens(tokenize(SAMPLE)) == SAMPLE
    pb = parse_body(SAMPLE)
    assert print_tokens(pb.tokens) == SAMPLE
    assert not pb.diagnostics


def test_statement_kinds() -> None:
    pb = parse_body(SAMPLE)
    kinds = [type(s).__name__ for s in pb.stmts]
    assert kinds == ["If", "Case", "Label", "For", "While", "Repeat", "Assign", "CallStmt", "Assign"]
    first = pb.stmts[0]
    assert isinstance(first, A.If)
    set_stmt = first.branches[0][1][1]
    assert isinstance(set_stmt, A.Assign) and set_stmt.op == "S="


@pytest.mark.parametrize(
    ("src", "kind"),
    [("T#1s500ms", "time"), ("LTIME#5ns", "ltime"), ("D#2020-01-01", "date"), ("TOD#12:00:00.5", "tod"),
     ("DT#2020-01-01-00:00:00", "dt"), ("INT#16#FF", "typed"), ("E_State#Run", "typed")],
)  # fmt: skip
def test_typed_literals(src: str, kind: str) -> None:
    toks = significant(tokenize(src))
    assert toks[0].kind is Kind.TYPED and toks[0].text == src
    e = parse_expression(src)
    assert isinstance(e, A.Literal) and e.kind == kind


def test_range_is_not_real() -> None:
    toks = [t.text for t in significant(tokenize("ARRAY[1..10] OF INT"))]
    assert toks[:6] == ["ARRAY", "[", "1", "..", "10", "]"]


def test_precedence_power_binds_tighter_than_unary() -> None:
    e = parse_expression("-2 ** 2")
    assert isinstance(e, A.Unary) and isinstance(e.operand, A.Binary)
    assert fmt_expr(parse_expression("(a + b) * c")) == "(a + b) * c"
    assert fmt_expr(parse_expression("a - (b - c)")) == "a - (b - c)"
    assert fmt_expr(parse_expression("a OR b AND c")) == "a OR b AND c"


def test_error_recovery() -> None:
    pb = parse_body("x := 1;\nbad := := ;\ny := 2;\n")
    assert [type(s).__name__ for s in pb.stmts] == ["Assign", "ErrorStmt", "Assign"]
    assert pb.diagnostics and pb.diagnostics[0].line == 2


def test_declaration() -> None:
    pd = parse_decl(
        "{attribute 'qualified_only'}\nFUNCTION_BLOCK PUBLIC FB_X EXTENDS FB_Base IMPLEMENTS I_A, I_B\n"
        "VAR_INPUT\n    xEn AT %IX0.1 : BOOL := TRUE;\nEND_VAR\nVAR_IN_OUT CONSTANT\n    st : ST_Cfg;\nEND_VAR\n"
        "VAR PERSISTENT RETAIN\n    a : ARRAY[0..9, 1..2] OF INT := [1, 2(3), 4];\n    s : STRING(20);\n"
        "    p : POINTER TO INT;\n    pct : INT(0..100);\nEND_VAR\n"
    )
    h = pd.decl.header
    assert h is not None and h.kind == "FUNCTION_BLOCK" and h.extends == ["FB_Base"] and h.implements == ["I_A", "I_B"]
    assert h.pragmas == ["{attribute 'qualified_only'}"]
    secs = pd.decl.sections
    assert [s.kind for s in secs] == ["VAR_INPUT", "VAR_IN_OUT", "VAR"]
    assert secs[2].qualifiers == ["PERSISTENT", "RETAIN"]
    assert secs[0].decls[0].at == "%IX0.1"
    arr = secs[2].decls[0]
    assert arr.type.name == "ARRAY" and len(arr.type.dims) == 2 and isinstance(arr.init, A.ArrayInit)
    assert arr.init.items[1][0] is not None  # повтор 2(3)
    assert secs[2].decls[1].type.length is not None
    assert secs[2].decls[3].type.subrange is not None


def test_types_decl() -> None:
    pd = parse_decl("TYPE E : (A := 0, B := 10, C) INT := A; END_TYPE\nTYPE U : UNION w : WORD; END_UNION END_TYPE")
    kinds = [(t.name, t.kind) for t in pd.decl.types]
    assert kinds == [("E", "ENUM"), ("U", "UNION")]
    assert pd.decl.types[0].base is not None and pd.decl.types[0].values[1].value is not None


def test_masterst_dialect() -> None:
    pd = parse_decl(
        "FUNCTION_BLOCK F\nVAR_INOUT\n    x : INT;\nEND_VAR\nVAR\n    fb : Локальная.FB_X;\nEND_VAR\n", "masterst"
    )
    assert pd.decl.sections[0].kind == "VAR_IN_OUT"
    assert pd.decl.sections[1].decls[0].type.name == "Локальная.FB_X"
    pb = parse_body("y := x = NULL;\n", "masterst")
    assert not pb.diagnostics


def test_fmt_stmts_reparses() -> None:
    pb = parse_body(SAMPLE)
    text = fmt_stmts(pb.stmts)
    again = parse_body(text)
    assert not again.diagnostics
    assert fmt_stmts(again.stmts) == text


def test_case_label_detection_inside_branch() -> None:
    pb = parse_body("CASE x OF\n1:\n  a := 1;\n  b := 2;\n2, 3:\n  c := 3;\nEND_CASE\n")
    case = pb.stmts[0]
    assert isinstance(case, A.Case) and len(case.branches) == 2
    assert len(case.branches[0][1]) == 2
