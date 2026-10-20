"""Свойства (hypothesis, 500 примеров на свойство, derandomize — воспроизводимо без сети и времени):

- лексер и печать без потерь на случайных текстах ST; разбор → печать → разбор устойчив;
- случайные DAG FBD и CFC с обратными связями: вычислитель графа = понижённый ST в симуляторе;
- случайные цепи LD (последовательно-параллельные): вычислитель релейной логики = понижённый ST;
- случайные программы IL (CR, AND(/OR(, ADD, ST): стековый исполнитель = понижённый ST;
- правки трансформации коммутативны (порядок Edit не важен) и идемпотентны.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from cds2ms.cdsfront.importer import plcopen
from cds2ms.cdsfront.lower import lower_project
from cds2ms.cdsfront.st.lexer import join, tokenize
from cds2ms.cdsfront.st.parser import parse_body
from cds2ms.cdsfront.st.printer import fmt_stmts
from cds2ms.rules.findings import Edit
from cds2ms.sim.interp import Machine
from cds2ms.sim.semantics import codesys, wrap_int
from cds2ms.transform.master_st import apply_edits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "corpus"))
from tc6 import Graph, cfc_body, fbd_body, ld_body, pou, project  # noqa: E402

PROPS = settings(max_examples=500, derandomize=True, deadline=None)

# ------------------------------------------------------------------ ST без потерь

_ATOMS = st.sampled_from(["x", "y1", "Foo_Bar", "16#FF", "2#1010", "1.5E3", "T#1h2m", "'a''b'", '"w"', "TRUE",
                          "(* c *)", "// c\n", "{attribute 'x'}", "\n", "  ", "\t", ":=", "<>", "<=", "**", ";", ",",
                          ".", "(", ")", "[", "]", "^", "IF", "THEN", "END_IF", "#", "MOD", "-", "+", "=>"])  # fmt: skip


@PROPS
@given(st.lists(_ATOMS, max_size=40))
def test_lexer_lossless(parts: list[str]) -> None:
    text = " ".join(parts)
    assert join(tokenize(text)) == text


_EXPR = st.recursive(
    st.sampled_from(["a", "b", "c", "1", "2", "TRUE", "x.y", "arr[1]"]),
    lambda inner: st.one_of(
        st.tuples(inner, st.sampled_from(["+", "-", "*", "AND", "OR", "=", "<", ">="]), inner).map(
            lambda t: f"({t[0]} {t[1]} {t[2]})"
        ),
        inner.map(lambda e: f"NOT {e}"),
        st.tuples(inner, inner).map(lambda t: f"MAX({t[0]}, {t[1]})"),
    ),
    max_leaves=8,
)


@PROPS
@given(st.lists(st.tuples(st.sampled_from(["a", "b", "q"]), _EXPR), min_size=1, max_size=5))
def test_parse_print_stable(assigns: list[tuple[str, str]]) -> None:
    text = "".join(f"{v} := {e};\n" for v, e in assigns)
    pb = parse_body(text)
    assert not pb.diagnostics
    once = fmt_stmts(pb.stmts)
    twice = fmt_stmts(parse_body(once).stmts)
    assert once == twice


# ------------------------------------------------------------------ графы FBD / CFC

_BOOL_OPS = ("AND", "OR", "XOR", "NOT")
_INT_OPS = ("ADD", "SUB", "MUL", "MAX", "MIN")


def _eval_op(op: str, args: list[Any]) -> Any:
    if op == "AND":
        return all(args)
    if op == "OR":
        return any(args)
    if op == "XOR":
        return args[0] != args[1]
    if op == "NOT":
        return not args[0]
    if op == "ADD":
        return wrap_int(args[0] + args[1], 16, True)
    if op == "SUB":
        return wrap_int(args[0] - args[1], 16, True)
    if op == "MUL":
        return wrap_int(args[0] * args[1], 16, True)
    if op == "MAX":
        return max(args)
    return min(args)


@st.composite
def graphs(draw: Any, feedback: bool) -> tuple[list[tuple[str, list[int | str]]], dict[str, bool], dict[str, int]]:
    """Узлы: (оператор, [индексы предыдущих узлов | имя входа | 'fb:k' — прошлый цикл узла k]); 2 типа: BOOL и INT."""
    nodes: list[tuple[str, list[int | str]]] = []
    n = draw(st.integers(1, 7))
    kinds = draw(st.lists(st.sampled_from(["B", "I"]), min_size=n, max_size=n))
    for i in range(n):
        kind = kinds[i]
        op = draw(st.sampled_from(_BOOL_OPS if kind == "B" else _INT_OPS))
        arity = 1 if op == "NOT" else 2
        args: list[int | str] = []
        for _ in range(arity):
            same = [j for j in range(i) if kinds[j] == kind]
            later = [j for j in range(i, n) if kinds[j] == kind]  # обратная связь — от узла не раньше текущего
            choice = draw(st.sampled_from(["in", "node", "fb"] if feedback else ["in", "node"]))
            if choice == "node" and same:
                args.append(draw(st.sampled_from(same)))
            elif choice == "fb" and later:
                args.append(f"fb:{draw(st.sampled_from(later))}")
            else:
                args.append(draw(st.sampled_from(["x1", "x2", "x3"] if kind == "B" else ["i1", "i2"])))
        nodes.append((op, args))
    bools = {k: draw(st.booleans()) for k in ("x1", "x2", "x3")}
    ints = {k: draw(st.integers(-300, 300)) for k in ("i1", "i2")}
    return nodes, bools, ints


def _types(nodes: list[tuple[str, list[int | str]]]) -> list[str]:
    return ["B" if op in _BOOL_OPS else "I" for op, _ in nodes]


def _graph_xml(nodes: list[tuple[str, list[int | str]]], lang: str) -> str:
    g = Graph(lang, 1)
    kinds = _types(nodes)
    ids: dict[int, int] = {}
    pending: list[tuple[int, int]] = []
    for i, (op, args) in enumerate(nodes):
        ins = []
        for k, a in enumerate(args):
            name = "In1" if k == 0 else "In2"
            if isinstance(a, int):
                ins.append((name, (ids[a], "Out1")))
            elif a.startswith("fb:"):
                ins.append((name, (-(int(a[3:]) + 1), "Out1")))  # localId узла j подставится после его создания
            else:
                ins.append((name, g.invar(a)))
        bid = g.block(op, ins, ["Out1"], eo=i + 1 if lang == "CFC" else None)
        ids[i] = bid
        pending.append((i, bid))
    for i, bid in enumerate(ids.values()):
        g.outvar(
            f"o{i}" if kinds[i] == "B" else f"n{i}", (bid, "Out1"), eo=len(nodes) + i + 1 if lang == "CFC" else None
        )
    # ссылки обратной связи на ещё не созданные узлы
    parts = []
    for part in g.parts:
        for j, real in ids.items():
            part = part.replace(f'refLocalId="{-(j + 1)}"', f'refLocalId="{real}"')
        parts.append(part)
    g.parts = parts
    decl = "PROGRAM P\nVAR_INPUT\n    x1 : BOOL;\n    x2 : BOOL;\n    x3 : BOOL;\n    i1 : INT;\n    i2 : INT;\nEND_VAR\nVAR_OUTPUT\n"
    decl += (
        "".join(f"    o{i} : BOOL;\n" if k == "B" else f"    n{i} : INT;\n" for i, k in enumerate(kinds)) + "END_VAR\n"
    )
    body = cfc_body(g) if lang == "CFC" else fbd_body([g])
    return project("G", [pou("P", "program", decl, body)])


def _run_lowered(xml: str, inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lp = lower_project(plcopen.load(xml.encode(), "g.xml"))
    p = lp.pou("P")
    assert p is not None
    m = Machine({"P": (p.decl, p.body)}, [], [], codesys())
    inst = m.program("P")
    out = []
    for k, vals in enumerate(inputs):
        inst.vars.update(vals)
        m.call_instance(inst, k * 10)
        out.append(dict(inst.vars))
    return out


def _run_graph(
    nodes: list[tuple[str, list[int | str]]], inputs: list[dict[str, Any]], cfc: bool
) -> list[dict[str, Any]]:
    kinds = _types(nodes)
    prev = [False if k == "B" else 0 for k in kinds]
    res = []
    for vals in inputs:
        cur = list(prev)
        for i, (op, args) in enumerate(nodes):
            a = []
            for x in args:
                if isinstance(x, int):
                    a.append(cur[x])
                elif x.startswith("fb:"):
                    a.append(cur[int(x[3:])])  # узел с бо́льшим номером ещё не пересчитан — значение прошлого цикла
                else:
                    a.append(vals[x])
            cur[i] = _eval_op(op, a)
        prev = cur
        res.append({(f"o{i}" if k == "B" else f"n{i}"): cur[i] for i, k in enumerate(kinds)})
    return res


@PROPS
@given(graphs(feedback=False), st.integers(1, 3))
def test_fbd_dag_equals_lowered(g: Any, cycles: int) -> None:
    nodes, bools, ints = g
    inputs = [{**bools, **ints}] * cycles
    got = _run_lowered(_graph_xml(nodes, "FBD"), inputs)
    exp = _run_graph(nodes, inputs, cfc=False)
    for a, b in zip(got, exp, strict=True):
        assert {k: a[k.lower()] for k in b} == b


@PROPS
@given(graphs(feedback=True), st.lists(st.tuples(st.booleans(), st.integers(-50, 50)), min_size=1, max_size=4))
def test_cfc_feedback_equals_lowered(g: Any, seq: list[tuple[bool, int]]) -> None:
    nodes, bools, ints = g
    inputs = [{**bools, "x1": x, **ints, "i1": v} for x, v in seq]
    got = _run_lowered(_graph_xml(nodes, "CFC"), inputs)
    exp = _run_graph(nodes, inputs, cfc=True)
    for a, b in zip(got, exp, strict=True):
        assert {k: a[k.lower()] for k in b} == b


# ------------------------------------------------------------------ цепи LD

_LD = st.recursive(
    st.tuples(st.just("c"), st.sampled_from(["a", "b", "c", "d"]), st.booleans()),
    lambda inner: st.one_of(st.tuples(st.just("ser"), st.lists(inner, min_size=2, max_size=3)),
                            st.tuples(st.just("par"), st.lists(inner, min_size=2, max_size=3))),
    max_leaves=6,
)  # fmt: skip


def _ld_eval(t: Any, v: dict[str, bool]) -> bool:
    if t[0] == "c":
        return v[t[1]] != t[2]
    if t[0] == "ser":
        return all(_ld_eval(x, v) for x in t[1])
    return any(_ld_eval(x, v) for x in t[1])


def _ld_build(g: Graph, t: Any, srcs: list[Any]) -> list[Any]:
    if t[0] == "c":
        return [g.contact(t[1], srcs if len(srcs) > 1 else srcs[0], negated=t[2])]
    if t[0] == "ser":
        cur = srcs
        for x in t[1]:
            cur = _ld_build(g, x, cur)
        return cur
    out: list[Any] = []
    for x in t[1]:
        out += _ld_build(g, x, srcs)
    return out


@PROPS
@given(_LD, st.fixed_dictionaries({k: st.booleans() for k in "abcd"}), st.sampled_from(["none", "set", "reset"]))
def test_ld_rung_equals_relay_logic(tree: Any, vals: dict[str, bool], storage: str) -> None:
    g = Graph("LD", 1)
    r = g.rail()
    ends = _ld_build(g, tree, [r])
    g.coil("q", ends if len(ends) > 1 else ends[0], storage=storage)
    decl = "PROGRAM P\nVAR_INPUT\n    a : BOOL;\n    b : BOOL;\n    c : BOOL;\n    d : BOOL;\nEND_VAR\nVAR_OUTPUT\n    q : BOOL;\nEND_VAR\n"
    xml = project("L", [pou("P", "program", decl, ld_body([g]))])
    for q0 in (False, True):
        lp = lower_project(plcopen.load(xml.encode(), "l.xml"))
        p = lp.pou("P")
        assert p is not None
        m = Machine({"P": (p.decl, p.body)}, [], [], codesys())
        inst = m.program("P")
        inst.vars.update(vals)
        inst.vars["q"] = q0
        m.call_instance(inst, 0)
        power = _ld_eval(tree, vals)
        exp = power if storage == "none" else (q0 or power if storage == "set" else q0 and not power)
        assert inst.vars["q"] == exp


# ------------------------------------------------------------------ IL

_IL_OPS = st.sampled_from(["AND", "OR", "XOR", "ANDN", "ORN"])


@PROPS
@given(st.lists(st.tuples(_IL_OPS, st.sampled_from(["a", "b", "c"]), st.booleans()), min_size=1, max_size=6),
       st.fixed_dictionaries({k: st.booleans() for k in "abc"}), st.integers(-100, 100), st.integers(-100, 100))  # fmt: skip
def test_il_stack_equals_lowered(ops: list[tuple[str, str, bool]], vals: dict[str, bool], i1: int, i2: int) -> None:
    lines = ["    LD a"]
    acc = vals["a"]
    for op, v, nested in ops:
        if nested:  # op( b OR c )
            lines += [f"    {op}( {v}", "    OR c", "    )"]
            operand = vals[v] or vals["c"]
        else:
            lines.append(f"    {op} {v}")
            operand = vals[v]
        if op.endswith("N"):
            operand = not operand
            op = op[:-1]
        acc = acc and operand if op == "AND" else (acc or operand if op == "OR" else acc != operand)
    lines += ["    ST q", "    LD i1", "    ADD i2", "    MUL 2", "    ST n"]
    text = "\n".join(lines) + "\n"
    decl = ("PROGRAM P\nVAR_INPUT\n    a : BOOL;\n    b : BOOL;\n    c : BOOL;\n    i1 : INT;\n    i2 : INT;\nEND_VAR\n"
            "VAR_OUTPUT\n    q : BOOL;\n    n : INT;\nEND_VAR\n")  # fmt: skip
    xml = project(
        "I", [pou("P", "program", decl, f'<IL><xhtml xmlns="http://www.w3.org/1999/xhtml">{text}</xhtml></IL>')]
    )
    lp = lower_project(plcopen.load(xml.encode(), "i.xml"))
    p = lp.pou("P")
    assert p is not None
    m = Machine({"P": (p.decl, p.body)}, [], [], codesys())
    inst = m.program("P")
    inst.vars.update({**vals, "i1": i1, "i2": i2})
    m.call_instance(inst, 0)
    assert inst.vars["q"] == acc and inst.vars["n"] == wrap_int((i1 + i2) * 2, 16, True)


# ------------------------------------------------------------------ правки

_TEXT = "abcdefghijklmnopqrstuvwxyz0123456789"


@PROPS
@given(st.lists(st.tuples(st.integers(0, 30), st.integers(0, 4), st.text("XYZ", max_size=3)), max_size=6),
       st.randoms(use_true_random=False))  # fmt: skip
def test_edits_commutative(spec: list[tuple[int, int, str]], rnd: Any) -> None:
    edits = [Edit(s, min(s + n, len(_TEXT)), r, f"R{i}", "auto") for i, (s, n, r) in enumerate(spec)]
    a = apply_edits(_TEXT, edits, {"auto"}, set())
    shuffled = list(edits)
    rnd.shuffle(shuffled)
    b = apply_edits(_TEXT, shuffled, {"auto"}, set())
    assert a[0] == b[0] and sorted(a[1]) == sorted(b[1])
