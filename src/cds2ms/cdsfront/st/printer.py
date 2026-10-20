"""Печать ST.

``print_tokens`` — печать без потерь (склейка токенов, round-trip байт в байт). ``fmt_expr`` и ``fmt_stmts`` —
канонический текст для кода, который строит понижение (графика, SFC, IL, ООП): одна запись на строку,
отступ 4 пробела, скобки только там, где их требует приоритет.
"""

from __future__ import annotations

from . import ast as A
from .lexer import Token

_PREC = {
    "OR": 1, "OR_ELSE": 1, "XOR": 2, "AND": 3, "&": 3, "AND_THEN": 3, "=": 4, "<>": 4,
    "<": 5, ">": 5, "<=": 5, ">=": 5, "+": 6, "-": 6, "*": 7, "/": 7, "MOD": 7, "**": 9,
}  # fmt: skip
_UNARY_PREC = 8


def print_tokens(tokens: list[Token]) -> str:
    return "".join(t.text for t in tokens)


def _prec(e: A.Expr) -> int:
    if isinstance(e, A.Binary):
        return _PREC.get(e.op, 1)
    if isinstance(e, A.Unary):
        return _UNARY_PREC
    return 10


def fmt_expr(e: A.Expr) -> str:
    if isinstance(e, A.Name):
        return e.id
    if isinstance(e, A.Literal):
        return e.text
    if isinstance(e, A.Unary):
        inner = fmt_expr(e.operand)
        if _prec(e.operand) < _UNARY_PREC:
            inner = f"({inner})"
        return f"NOT {inner}" if e.op == "NOT" else f"{e.op}{inner}"
    if isinstance(e, A.Binary):
        p = _PREC.get(e.op, 1)
        left = fmt_expr(e.left)
        right = fmt_expr(e.right)
        if _prec(e.left) < p:
            left = f"({left})"
        if isinstance(e.right, A.Binary | A.Unary) and _prec(e.right) <= p:
            right = f"({right})"
        return f"{left} {e.op} {right}"
    if isinstance(e, A.Member):
        return f"{fmt_expr(e.obj)}.{e.name}"
    if isinstance(e, A.Index):
        return f"{fmt_expr(e.obj)}[{', '.join(fmt_expr(i) for i in e.indices)}]"
    if isinstance(e, A.Deref):
        return f"{fmt_expr(e.obj)}^"
    if isinstance(e, A.Call):
        return f"{fmt_expr(e.func)}({', '.join(fmt_arg(a) for a in e.args)})"
    if isinstance(e, A.ArrayInit):
        parts = []
        for rep, val in e.items:
            parts.append(f"{fmt_expr(rep)}({fmt_expr(val)})" if rep is not None else fmt_expr(val))
        return "[" + ", ".join(parts) + "]"
    if isinstance(e, A.StructInit):
        return "(" + ", ".join(f"{n} := {fmt_expr(v)}" for n, v in e.fields) + ")"
    raise TypeError(f"нет печати для {type(e).__name__}")


def fmt_arg(a: A.Arg) -> str:
    if a.name is None:
        return fmt_expr(a.value)
    if a.output:
        return f"{'NOT ' if a.negated else ''}{a.name} => {fmt_expr(a.value)}"
    return f"{a.name} := {fmt_expr(a.value)}"


def fmt_stmts(body: list[A.Stmt], indent: int = 0) -> str:
    return "".join(fmt_stmt(s, indent) for s in body)


def fmt_stmt(s: A.Stmt, indent: int = 0) -> str:
    pad = "    " * indent
    if isinstance(s, A.Assign):
        return f"{pad}{fmt_expr(s.target)} {s.op} {fmt_expr(s.value)};\n"
    if isinstance(s, A.CallStmt):
        return f"{pad}{fmt_expr(s.call)};\n"
    if isinstance(s, A.If):
        out = ""
        for i, (cond, body) in enumerate(s.branches):
            kw = "IF" if i == 0 else "ELSIF"
            out += f"{pad}{kw} {fmt_expr(cond)} THEN\n{fmt_stmts(body, indent + 1)}"
        if s.else_body is not None:
            out += f"{pad}ELSE\n{fmt_stmts(s.else_body, indent + 1)}"
        return out + f"{pad}END_IF;\n"
    if isinstance(s, A.Case):
        out = f"{pad}CASE {fmt_expr(s.selector)} OF\n"
        for labels, body in s.branches:
            labs = ", ".join(
                fmt_expr(lab.low) + (f"..{fmt_expr(lab.high)}" if lab.high is not None else "") for lab in labels
            )
            out += f"{pad}    {labs}:\n{fmt_stmts(body, indent + 2)}"
        if s.else_body is not None:
            out += f"{pad}ELSE\n{fmt_stmts(s.else_body, indent + 2)}"
        return out + f"{pad}END_CASE;\n"
    if isinstance(s, A.For):
        by = f" BY {fmt_expr(s.step)}" if s.step is not None else ""
        return (
            f"{pad}FOR {s.var} := {fmt_expr(s.first)} TO {fmt_expr(s.last)}{by} DO\n"
            f"{fmt_stmts(s.body, indent + 1)}{pad}END_FOR;\n"
        )
    if isinstance(s, A.While):
        return f"{pad}WHILE {fmt_expr(s.cond)} DO\n{fmt_stmts(s.body, indent + 1)}{pad}END_WHILE;\n"
    if isinstance(s, A.Repeat):
        return f"{pad}REPEAT\n{fmt_stmts(s.body, indent + 1)}{pad}UNTIL {fmt_expr(s.cond)}\n{pad}END_REPEAT;\n"
    if isinstance(s, A.Exit):
        return f"{pad}EXIT;\n"
    if isinstance(s, A.Continue):
        return f"{pad}CONTINUE;\n"
    if isinstance(s, A.Return):
        return f"{pad}RETURN;\n"
    if isinstance(s, A.Jmp):
        return f"{pad}JMP {s.label};\n"
    if isinstance(s, A.Label):
        return f"{s.name}:\n"
    if isinstance(s, A.Empty):
        return f"{pad};\n"
    if isinstance(s, A.ErrorStmt):
        return f"{pad}(* ошибка разбора: {s.message} *)\n"
    raise TypeError(f"нет печати для {type(s).__name__}")
