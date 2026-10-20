"""Разборщик ST CODESYS 3.5 (и диалекта Master ST для разбора выхода).

Работает поверх лексера без потерь: AST хранит индексы токенов, поэтому печать ``join(tokens)`` даёт
исходный текст байт в байт, а правки делаются по границам токенов. Ошибки не прерывают разбор:
оператор с ошибкой становится ``ErrorStmt`` до ``;`` или ``END_*`` (находка MS-PARSE-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import ast as A
from .lexer import TRIVIA, Kind, Token, tokenize

POU_KINDS = ("PROGRAM", "FUNCTION_BLOCK", "FUNCTION", "METHOD", "PROPERTY", "INTERFACE", "ACTION")
SECTION_KINDS = (
    "VAR",
    "VAR_INPUT",
    "VAR_OUTPUT",
    "VAR_IN_OUT",
    "VAR_INOUT",
    "VAR_GLOBAL",
    "VAR_TEMP",
    "VAR_STAT",
    "VAR_EXTERNAL",
    "VAR_INST",
    "VAR_CONFIG",
)
QUALIFIERS = ("CONSTANT", "RETAIN", "PERSISTENT", "NON_RETAIN")
MODIFIERS = ("ABSTRACT", "FINAL", "PUBLIC", "PRIVATE", "PROTECTED", "INTERNAL")
STMT_END = frozenset({"END_IF", "ELSIF", "ELSE", "END_CASE", "END_FOR", "END_WHILE", "UNTIL", "END_REPEAT"})
KEYWORDS = frozenset(
    {
        "IF", "THEN", "ELSIF", "ELSE", "END_IF", "CASE", "OF", "END_CASE", "FOR", "TO", "BY", "DO", "END_FOR",
        "WHILE", "END_WHILE", "REPEAT", "UNTIL", "END_REPEAT", "EXIT", "CONTINUE", "RETURN", "JMP",
        "AND", "OR", "XOR", "NOT", "MOD", "AND_THEN", "OR_ELSE", "TRUE", "FALSE",
        "VAR", "END_VAR", "TYPE", "END_TYPE", "STRUCT", "END_STRUCT", "UNION", "END_UNION",
        *POU_KINDS, *SECTION_KINDS,
    }
)  # fmt: skip

_BIN_PREC: dict[str, int] = {
    "OR": 1,
    "OR_ELSE": 1,
    "XOR": 2,
    "AND": 3,
    "&": 3,
    "AND_THEN": 3,
    "=": 4,
    "<>": 4,
    "<": 5,
    ">": 5,
    "<=": 5,
    ">=": 5,
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
    "MOD": 7,
}


@dataclass
class Diagnostic:
    message: str
    line: int
    col: int


@dataclass
class Parsed:
    text: str
    tokens: list[Token]
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def span_text(self, node: A.Node) -> str:
        """Исходный текст узла без тривиа по краям."""
        if node.end <= node.start:
            return ""
        a = self.tokens[node.start].offset
        b = self.tokens[node.end - 1].end
        return self.text[a:b]

    def pos(self, node: A.Node) -> tuple[int, int]:
        t = self.tokens[min(node.start, len(self.tokens) - 1)]
        return t.line, t.col


@dataclass
class ParsedBody(Parsed):
    stmts: list[A.Stmt] = field(default_factory=list)


@dataclass
class ParsedDecl(Parsed):
    decl: A.Declaration = field(default_factory=lambda: A.Declaration(header=None))


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, text: str, dialect: str = "codesys") -> None:
        self.text = text
        self.dialect = dialect
        self.tokens = tokenize(text)
        self.sig = [i for i, t in enumerate(self.tokens) if t.kind not in TRIVIA]
        self.p = 0
        self.diags: list[Diagnostic] = []

    # ------------------------------------------------------------ навигация

    def tok(self, k: int = 0) -> Token:
        j = min(self.p + k, len(self.sig) - 1)
        return self.tokens[self.sig[j]]

    def idx(self, k: int = 0) -> int:
        return self.sig[min(self.p + k, len(self.sig) - 1)]

    def advance(self) -> Token:
        t = self.tok()
        if t.kind is not Kind.EOF:
            self.p += 1
        return t

    def last_end(self) -> int:
        """Индекс (в полном списке) токена после последнего прочитанного значимого."""
        return self.sig[self.p - 1] + 1 if self.p > 0 else 0

    def at_eof(self) -> bool:
        return self.tok().kind is Kind.EOF

    def at_kw(self, *words: str) -> bool:
        return self.tok().is_kw(*words)

    def at_op(self, *ops: str) -> bool:
        return self.tok().is_op(*ops)

    def expect_op(self, op: str) -> Token:
        t = self.tok()
        if not t.is_op(op):
            raise ParseError(f"ожидалось «{op}», найдено «{t.text or 'конец текста'}»")
        return self.advance()

    def expect_kw(self, *words: str) -> Token:
        t = self.tok()
        if not t.is_kw(*words):
            raise ParseError(f"ожидалось {'/'.join(words)}, найдено «{t.text or 'конец текста'}»")
        return self.advance()

    def expect_ident(self) -> Token:
        t = self.tok()
        if t.kind is not Kind.IDENT:
            raise ParseError(f"ожидался идентификатор, найдено «{t.text or 'конец текста'}»")
        return self.advance()

    def error(self, message: str, t: Token | None = None) -> None:
        t = t or self.tok()
        self.diags.append(Diagnostic(message, t.line, t.col))

    def pragmas_before(self, k: int = 0) -> list[str]:
        """Прагмы между предыдущим значимым токеном и текущим."""
        j = self.p + k
        lo = self.sig[j - 1] + 1 if j > 0 else 0
        hi = self.sig[min(j, len(self.sig) - 1)]
        return [t.text for t in self.tokens[lo:hi] if t.kind is Kind.PRAGMA]

    # ------------------------------------------------------------ выражения

    def parse_expr(self, min_prec: int = 1) -> A.Expr:
        left = self.parse_unary()
        while True:
            t = self.tok()
            op = t.upper if t.kind is Kind.IDENT else (t.text if t.kind is Kind.OP else "")
            prec = _BIN_PREC.get(op)
            if prec is None or prec < min_prec:
                return left
            start = left.start
            self.advance()
            right = self.parse_expr(prec + 1)
            left = A.Binary(op, left, right, start=start, end=self.last_end())

    def parse_unary(self) -> A.Expr:
        t = self.tok()
        if t.is_kw("NOT") or t.is_op("-", "+"):
            start = self.idx()
            self.advance()
            operand = self.parse_unary()
            op = "NOT" if t.is_kw("NOT") else t.text
            return A.Unary(op, operand, start=start, end=self.last_end())
        return self.parse_power()

    def parse_power(self) -> A.Expr:
        left = self.parse_postfix()
        while self.at_op("**"):
            self.advance()
            right = self.parse_unary()
            left = A.Binary("**", left, right, start=left.start, end=self.last_end())
        return left

    def parse_postfix(self) -> A.Expr:
        e = self.parse_primary()
        while True:
            if self.at_op("."):
                self.advance()
                t = self.tok()
                if t.kind in (Kind.IDENT, Kind.INT):
                    self.advance()
                    e = A.Member(e, t.text, start=e.start, end=self.last_end())
                else:
                    raise ParseError(f"после «.» ожидалось имя, найдено «{t.text}»")
            elif self.at_op("["):
                self.advance()
                indices = [self.parse_expr()]
                while self.at_op(","):
                    self.advance()
                    indices.append(self.parse_expr())
                self.expect_op("]")
                e = A.Index(e, indices, start=e.start, end=self.last_end())
            elif self.at_op("^"):
                self.advance()
                e = A.Deref(e, start=e.start, end=self.last_end())
            elif self.at_op("(") and not isinstance(e, A.Literal):  # 3(0) в инициализаторе — повтор, не вызов
                self.advance()
                args = self.parse_args()
                self.expect_op(")")
                e = A.Call(e, args, start=e.start, end=self.last_end())
            else:
                return e

    def parse_args(self) -> list[A.Arg]:
        args: list[A.Arg] = []
        if self.at_op(")"):
            return args
        while True:
            start = self.idx()
            negated = False
            if self.at_kw("NOT") and self.tok(1).kind is Kind.IDENT and self.tok(2).is_op("=>"):
                self.advance()
                negated = True
            t = self.tok()
            val: A.Expr
            if t.kind is Kind.IDENT and self.tok(1).is_op(":="):
                self.advance()
                self.advance()
                val = self.parse_expr()
                args.append(A.Arg(t.text, val, start=start, end=self.last_end()))
            elif t.kind is Kind.IDENT and self.tok(1).is_op("=>"):
                self.advance()
                self.advance()
                if self.at_op(",", ")"):
                    val = A.Name("", start=self.idx(), end=self.idx())
                else:
                    val = self.parse_expr()
                args.append(A.Arg(t.text, val, output=True, negated=negated, start=start, end=self.last_end()))
            else:
                val = self.parse_expr()
                args.append(A.Arg(None, val, start=start, end=self.last_end()))
            if self.at_op(","):
                self.advance()
                continue
            return args

    def parse_primary(self) -> A.Expr:
        t = self.tok()
        start = self.idx()
        if t.kind is Kind.INT:
            self.advance()
            return A.Literal("int", t.text, start=start, end=self.last_end())
        if t.kind is Kind.REAL:
            self.advance()
            return A.Literal("real", t.text, start=start, end=self.last_end())
        if t.kind is Kind.STRING:
            self.advance()
            return A.Literal("string", t.text, start=start, end=self.last_end())
        if t.kind is Kind.WSTRING:
            self.advance()
            return A.Literal("wstring", t.text, start=start, end=self.last_end())
        if t.kind is Kind.TYPED:
            self.advance()
            prefix, _, _ = t.text.partition("#")
            return A.Literal(typed_kind(prefix), t.text, type_prefix=prefix, start=start, end=self.last_end())
        if t.kind is Kind.ADDR:
            self.advance()
            return A.Name(t.text, start=start, end=self.last_end())
        if t.kind is Kind.IDENT:
            if t.is_kw("TRUE", "FALSE"):
                self.advance()
                return A.Literal("bool", t.text, start=start, end=self.last_end())
            if self.dialect == "masterst" and t.is_kw("NULL"):
                self.advance()
                return A.Literal("null", t.text, start=start, end=self.last_end())
            if t.upper in KEYWORDS and t.upper not in ("FUNCTION",):
                raise ParseError(f"ключевое слово «{t.text}» на месте выражения")
            self.advance()
            return A.Name(t.text, start=start, end=self.last_end())
        if t.is_op("("):
            # инициализатор структуры (a := 1, b := 2)
            if self.tok(1).kind is Kind.IDENT and self.tok(2).is_op(":="):
                self.advance()
                fields: list[tuple[str, A.Expr]] = []
                while True:
                    name = self.expect_ident().text
                    self.expect_op(":=")
                    fields.append((name, self.parse_init()))
                    if self.at_op(","):
                        self.advance()
                        continue
                    break
                self.expect_op(")")
                return A.StructInit(fields, start=start, end=self.last_end())
            self.advance()
            e = self.parse_expr()
            self.expect_op(")")
            # скобки сохраняются диапазоном токенов; узел — внутреннее выражение
            e.start, e.end = start, self.last_end()
            return e
        if t.is_op("["):
            self.advance()
            items: list[tuple[A.Expr | None, A.Expr]] = []
            if not self.at_op("]"):
                while True:
                    val = self.parse_init()
                    if self.at_op("("):  # повтор: 3(0)
                        self.advance()
                        inner = self.parse_init() if not self.at_op(")") else val
                        self.expect_op(")")
                        items.append((val, inner))
                    else:
                        items.append((None, val))
                    if self.at_op(","):
                        self.advance()
                        continue
                    break
            self.expect_op("]")
            return A.ArrayInit(items, start=start, end=self.last_end())
        raise ParseError(f"неожиданный токен «{t.text or 'конец текста'}»")

    def parse_init(self) -> A.Expr:
        return self.parse_expr()

    # ------------------------------------------------------------ операторы

    def parse_stmts(self, terminators: frozenset[str] = STMT_END, in_case: bool = False) -> list[A.Stmt]:
        out: list[A.Stmt] = []
        while not self.at_eof():
            t = self.tok()
            if t.kind is Kind.IDENT and t.upper in terminators:
                break
            if in_case and self.looks_like_case_label():
                break
            out.append(self.parse_stmt_safe())
        return out

    def parse_stmt_safe(self) -> A.Stmt:
        save = self.p
        start = self.idx()
        try:
            return self.parse_stmt()
        except ParseError as exc:
            self.error(str(exc))
            self.p = max(self.p, save)
            # восстановление: до ; или до ключевого слова конца блока
            while not self.at_eof():
                t = self.tok()
                if t.is_op(";"):
                    self.advance()
                    break
                if t.kind is Kind.IDENT and t.upper in STMT_END and self.p > save:
                    break
                self.advance()
            if self.p == save:
                self.advance()
            return A.ErrorStmt(str(exc), start=start, end=self.last_end())

    def parse_stmt(self) -> A.Stmt:
        t = self.tok()
        start = self.idx()
        if t.is_op(";"):
            self.advance()
            return A.Empty(start=start, end=self.last_end())
        if t.kind is Kind.IDENT:
            u = t.upper
            if u == "IF":
                return self.parse_if()
            if u == "CASE":
                return self.parse_case()
            if u == "FOR":
                return self.parse_for()
            if u == "WHILE":
                self.advance()
                cond = self.parse_expr()
                self.expect_kw("DO")
                body = self.parse_stmts(frozenset({"END_WHILE"}))
                self.expect_kw("END_WHILE")
                self.skip_semicolon()
                return A.While(cond, body, start=start, end=self.last_end())
            if u == "REPEAT":
                self.advance()
                body = self.parse_stmts(frozenset({"UNTIL"}))
                self.expect_kw("UNTIL")
                cond = self.parse_expr()
                self.expect_kw("END_REPEAT")
                self.skip_semicolon()
                return A.Repeat(body, cond, start=start, end=self.last_end())
            if u in ("EXIT", "CONTINUE", "RETURN"):
                self.advance()
                self.expect_op(";")
                cls = {"EXIT": A.Exit, "CONTINUE": A.Continue, "RETURN": A.Return}[u]
                return cls(start=start, end=self.last_end())
            if u == "JMP":
                self.advance()
                label = self.expect_ident().text
                self.expect_op(";")
                return A.Jmp(label, start=start, end=self.last_end())
            if self.tok(1).is_op(":") and u not in KEYWORDS:
                self.advance()
                self.advance()
                return A.Label(t.text, start=start, end=self.last_end())
        target = self.parse_expr()
        if self.at_op(":="):
            self.advance()
            value = self.parse_expr()
            self.expect_op(";")
            return A.Assign(target, value, ":=", start=start, end=self.last_end())
        nt = self.tok()
        if nt.is_kw("S", "R", "REF") and self.tok(1).is_op("=") and self.tok(1).offset == nt.end:
            self.advance()
            self.advance()
            value = self.parse_expr()
            self.expect_op(";")
            return A.Assign(target, value, nt.upper + "=", start=start, end=self.last_end())
        if isinstance(target, A.Call):
            self.expect_op(";")
            return A.CallStmt(target, start=start, end=self.last_end())
        raise ParseError(f"ожидалось «:=» или вызов, найдено «{self.tok().text or 'конец текста'}»")

    def skip_semicolon(self) -> None:
        if self.at_op(";"):
            self.advance()

    def parse_if(self) -> A.If:
        start = self.idx()
        self.expect_kw("IF")
        branches: list[tuple[A.Expr, list[A.Stmt]]] = []
        cond = self.parse_expr()
        self.expect_kw("THEN")
        branches.append((cond, self.parse_stmts(frozenset({"ELSIF", "ELSE", "END_IF"}))))
        else_body: list[A.Stmt] | None = None
        while True:
            if self.at_kw("ELSIF"):
                self.advance()
                cond = self.parse_expr()
                self.expect_kw("THEN")
                branches.append((cond, self.parse_stmts(frozenset({"ELSIF", "ELSE", "END_IF"}))))
            elif self.at_kw("ELSE"):
                self.advance()
                else_body = self.parse_stmts(frozenset({"END_IF"}))
            else:
                break
        self.expect_kw("END_IF")
        self.skip_semicolon()
        return A.If(branches, else_body, start=start, end=self.last_end())

    def looks_like_case_label(self) -> bool:
        k = 0
        seen = False
        while k < 40:
            t = self.tok(k)
            if t.kind is Kind.EOF:
                return False
            if t.is_op(":"):
                return seen
            if t.kind in (Kind.INT, Kind.TYPED) or t.is_op("..", ",", "-", "+", "."):
                seen = True
                k += 1
                continue
            if t.kind is Kind.IDENT and t.upper not in KEYWORDS:
                seen = True
                k += 1
                continue
            return False
        return False

    def parse_case_labels(self) -> list[A.CaseLabel]:
        labels: list[A.CaseLabel] = []
        while True:
            s = self.idx()
            low = self.parse_expr()
            high = None
            if self.at_op(".."):
                self.advance()
                high = self.parse_expr()
            labels.append(A.CaseLabel(low, high, start=s, end=self.last_end()))
            if self.at_op(","):
                self.advance()
                continue
            break
        self.expect_op(":")
        return labels

    def parse_case(self) -> A.Case:
        start = self.idx()
        self.expect_kw("CASE")
        sel = self.parse_expr()
        self.expect_kw("OF")
        branches: list[tuple[list[A.CaseLabel], list[A.Stmt]]] = []
        else_body: list[A.Stmt] | None = None
        while not self.at_eof() and not self.at_kw("END_CASE"):
            if self.at_kw("ELSE"):
                self.advance()
                else_body = self.parse_stmts(frozenset({"END_CASE"}))
                break
            if not self.looks_like_case_label():
                raise ParseError(f"ожидалась метка CASE, найдено «{self.tok().text}»")
            labels = self.parse_case_labels()
            body = self.parse_stmts(frozenset({"END_CASE", "ELSE"}), in_case=True)
            branches.append((labels, body))
        self.expect_kw("END_CASE")
        self.skip_semicolon()
        return A.Case(sel, branches, else_body, start=start, end=self.last_end())

    def parse_for(self) -> A.For:
        start = self.idx()
        self.expect_kw("FOR")
        var = self.expect_ident().text
        self.expect_op(":=")
        first = self.parse_expr()
        self.expect_kw("TO")
        last = self.parse_expr()
        step = None
        if self.at_kw("BY"):
            self.advance()
            step = self.parse_expr()
        self.expect_kw("DO")
        body = self.parse_stmts(frozenset({"END_FOR"}))
        self.expect_kw("END_FOR")
        self.skip_semicolon()
        return A.For(var, first, last, step, body, start=start, end=self.last_end())

    # ------------------------------------------------------------ объявления

    def parse_type(self) -> A.TypeRef:
        start = self.idx()
        t = self.tok()
        if t.is_kw("ARRAY"):
            self.advance()
            self.expect_op("[")
            dims: list[tuple[A.Expr, A.Expr]] = []
            while True:
                if self.at_op("*"):
                    s = self.idx()
                    self.advance()
                    star = A.Name("*", start=s, end=self.last_end())
                    dims.append((star, star))
                else:
                    lo = self.parse_expr()
                    self.expect_op("..")
                    hi = self.parse_expr()
                    dims.append((lo, hi))
                if self.at_op(","):
                    self.advance()
                    continue
                break
            self.expect_op("]")
            self.expect_kw("OF")
            elem = self.parse_type()
            return self._typeref("ARRAY", start, dims=dims, elem=elem)
        if t.is_kw("POINTER", "REFERENCE"):
            self.advance()
            self.expect_kw("TO")
            elem = self.parse_type()
            return self._typeref(t.upper, start, elem=elem)
        if t.is_kw("STRING", "WSTRING"):
            self.advance()
            length = None
            if self.at_op("(", "["):
                close = ")" if self.at_op("(") else "]"
                self.advance()
                length = self.parse_expr()
                self.expect_op(close)
            return self._typeref(t.upper, start, length=length)
        if t.is_kw("STRUCT"):
            self.advance()
            while not self.at_eof() and not self.at_kw("END_STRUCT"):
                self.parse_var_decl()
            self.expect_kw("END_STRUCT")
            return self._typeref("STRUCT", start)
        name_tok = self.expect_ident()
        name = name_tok.text
        while self.at_op(".") and self.tok(1).kind is Kind.IDENT:  # Библиотека.Тип
            self.advance()
            name += "." + self.advance().text
        sub = None
        if self.at_op("(") and not self.tok(1).is_op(")"):
            save = self.p
            try:
                self.advance()
                lo = self.parse_expr()
                self.expect_op("..")
                hi = self.parse_expr()
                self.expect_op(")")
                sub = (lo, hi)
            except ParseError:
                self.p = save
        return self._typeref(name, start, subrange=sub)

    def _typeref(self, name: str, start: int, **kw: Any) -> A.TypeRef:
        end = self.last_end()
        a = self.tokens[start].offset
        b = self.tokens[end - 1].end if end > start else a
        return A.TypeRef(
            name.upper() if name.upper() in _ELEMENTARY else name, self.text[a:b], start=start, end=end, **kw
        )

    def parse_var_decl(self) -> A.VarDecl:
        pragmas = self.pragmas_before()
        start = self.idx()
        names: list[str] = []
        name_tokens: list[int] = []
        while True:
            names.append(self.expect_ident().text)
            name_tokens.append(self.sig[self.p - 1])
            if self.at_op(","):
                self.advance()
                continue
            break
        at = None
        if self.at_kw("AT"):
            self.advance()
            t = self.advance()
            if t.kind is not Kind.ADDR:
                raise ParseError(f"после AT ожидался адрес, найдено «{t.text}»")
            at = t.text
        self.expect_op(":")
        typ = self.parse_type()
        init = None
        if self.at_op(":="):
            self.advance()
            init = self.parse_init()
        # Master ST: «Переключение» R_EDGE / F_EDGE после типа
        if self.dialect == "masterst" and self.at_kw("R_EDGE", "F_EDGE"):
            self.advance()
        self.expect_op(";")
        return A.VarDecl(names, name_tokens, typ, init, at, pragmas, start=start, end=self.last_end())

    def parse_section(self) -> A.VarSection:
        pragmas = self.pragmas_before()
        start = self.idx()
        kind = self.advance().upper
        if kind == "VAR_INOUT":
            kind = "VAR_IN_OUT"
        quals: list[str] = []
        while self.at_kw(*QUALIFIERS):
            quals.append(self.advance().upper)
        decls: list[A.VarDecl] = []
        while not self.at_eof() and not self.at_kw("END_VAR"):
            if self.at_kw(*SECTION_KINDS, *POU_KINDS, "TYPE"):
                raise ParseError("нет END_VAR")
            try:
                decls.append(self.parse_var_decl())
            except ParseError as exc:
                self.error(str(exc))
                while not self.at_eof() and not self.at_op(";") and not self.at_kw("END_VAR"):
                    self.advance()
                if self.at_op(";"):
                    self.advance()
        self.expect_kw("END_VAR")
        return A.VarSection(kind, quals, decls, pragmas, start=start, end=self.last_end())

    def parse_header(self) -> A.PouHeader:
        pragmas = self.pragmas_before()
        start = self.idx()
        kind = self.advance().upper
        mods: list[str] = []
        while self.at_kw(*MODIFIERS):
            mods.append(self.advance().upper)
        name = self.expect_ident().text
        h = A.PouHeader(kind, name, modifiers=mods, pragmas=pragmas, start=start)
        if self.at_op(":") and kind in ("FUNCTION", "METHOD", "PROPERTY"):
            self.advance()
            h.return_type = self.parse_type()
        while True:
            if self.at_kw("EXTENDS"):
                self.advance()
                h.extends.append(self._qualified())
                while self.at_op(","):
                    self.advance()
                    h.extends.append(self._qualified())
            elif self.at_kw("IMPLEMENTS"):
                self.advance()
                h.implements.append(self._qualified())
                while self.at_op(","):
                    self.advance()
                    h.implements.append(self._qualified())
            else:
                break
        self.skip_semicolon()
        h.end = self.last_end()
        return h

    def _qualified(self) -> str:
        name = self.expect_ident().text
        while self.at_op(".") and self.tok(1).kind is Kind.IDENT:
            self.advance()
            name += "." + self.advance().text
        return name

    def parse_type_decl(self) -> A.TypeDecl:
        pragmas = self.pragmas_before()
        start = self.idx()
        name = self.expect_ident().text
        extends = None
        if self.at_kw("EXTENDS"):
            self.advance()
            extends = self._qualified()
        self.expect_op(":")
        td = A.TypeDecl(name, "ALIAS", extends=extends, pragmas=pragmas, start=start)
        if self.at_kw("STRUCT", "UNION"):
            kw = self.advance().upper
            td.kind = kw
            close = "END_" + kw
            while not self.at_eof() and not self.at_kw(close):
                td.fields.append(self.parse_var_decl())
            self.expect_kw(close)
        elif self.at_op("("):
            td.kind = "ENUM"
            self.advance()
            while True:
                s = self.idx()
                vname = self.expect_ident().text
                val = None
                if self.at_op(":="):
                    self.advance()
                    val = self.parse_expr()
                td.values.append(A.EnumValue(vname, val, start=s, end=self.last_end()))
                if self.at_op(","):
                    self.advance()
                    continue
                break
            self.expect_op(")")
            if self.tok().kind is Kind.IDENT and not self.at_kw("END_TYPE"):
                td.base = self.parse_type()
            if self.at_op(":="):
                self.advance()
                td.init = self.parse_expr()
        else:
            td.base = self.parse_type()
            td.kind = "SUBRANGE" if td.base.subrange is not None else "ALIAS"
            if self.at_op(":="):
                self.advance()
                td.init = self.parse_expr()
        self.skip_semicolon()
        td.end = self.last_end()
        return td

    def parse_declaration(self) -> A.Declaration:
        start = self.idx()
        decl = A.Declaration(header=None, start=start)
        while not self.at_eof():
            try:
                if self.at_kw(*POU_KINDS) and decl.header is None:
                    decl.header = self.parse_header()
                elif self.at_kw("TYPE"):
                    self.advance()
                    while not self.at_eof() and not self.at_kw("END_TYPE"):
                        decl.types.append(self.parse_type_decl())
                    self.expect_kw("END_TYPE")
                    self.skip_semicolon()
                elif self.at_kw(*SECTION_KINDS):
                    decl.sections.append(self.parse_section())
                elif self.tok().kind is Kind.IDENT and self.tok().upper.startswith("END_"):
                    self.advance()
                    self.skip_semicolon()
                else:
                    raise ParseError(f"неожиданный токен в объявлении «{self.tok().text}»")
            except ParseError as exc:
                self.error(str(exc))
                self.advance()
        decl.end = self.last_end()
        return decl


_ELEMENTARY = frozenset(
    {
        "BOOL", "BYTE", "WORD", "DWORD", "LWORD", "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT",
        "ULINT", "REAL", "LREAL", "TIME", "LTIME", "DATE", "TOD", "TIME_OF_DAY", "DT", "DATE_AND_TIME",
        "STRING", "WSTRING", "BIT", "__UXINT", "__XINT", "__XWORD", "ANY", "ANY_NUM", "ANY_INT", "ANY_REAL",
    }
)  # fmt: skip


def typed_kind(prefix: str) -> str:
    p = prefix.upper()
    if p in ("T", "TIME"):
        return "time"
    if p in ("LT", "LTIME"):
        return "ltime"
    if p in ("D", "DATE", "LD", "LDATE"):
        return "date"
    if p in ("TOD", "TIME_OF_DAY", "LTOD", "LTIME_OF_DAY"):
        return "tod"
    if p in ("DT", "DATE_AND_TIME", "LDT", "LDATE_AND_TIME"):
        return "dt"
    return "typed"


def parse_body(text: str, dialect: str = "codesys") -> ParsedBody:
    p = Parser(text, dialect)
    stmts = p.parse_stmts(frozenset())
    return ParsedBody(text, p.tokens, p.diags, stmts)


def parse_decl(text: str, dialect: str = "codesys") -> ParsedDecl:
    p = Parser(text, dialect)
    decl = p.parse_declaration()
    return ParsedDecl(text, p.tokens, p.diags, decl)


def parse_expression(text: str) -> A.Expr:
    p = Parser(text)
    e = p.parse_expr()
    if not p.at_eof():
        raise ParseError(f"лишний текст после выражения: «{p.tok().text}»")
    return e
