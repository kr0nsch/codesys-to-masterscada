"""Узлы AST ST CODESYS 3.5.

У каждого узла — диапазон значимых токенов ``[start, end)`` в списке токенов разборщика (``Parsed.tokens``),
по которому строятся правки по границам токенов и происхождение находок.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(eq=False)
class Node:
    start: int = field(default=0, kw_only=True)  # индекс первого токена (в полном списке токенов)
    end: int = field(default=0, kw_only=True)  # индекс токена после последнего


# ---------------------------------------------------------------- выражения


@dataclass(eq=False)
class Expr(Node):
    pass


@dataclass(eq=False)
class Name(Expr):
    id: str


@dataclass(eq=False)
class Literal(Expr):
    kind: str  # int real bool string wstring time ltime date tod dt typed
    text: str
    type_prefix: str = ""  # INT в INT#5, имя перечисления в E_State#Run


@dataclass(eq=False)
class Unary(Expr):
    op: str  # NOT, -, +
    operand: Expr


@dataclass(eq=False)
class Binary(Expr):
    op: str  # OR XOR AND AND_THEN OR_ELSE = <> < > <= >= + - * / MOD **
    left: Expr
    right: Expr


@dataclass(eq=False)
class Member(Expr):
    obj: Expr
    name: str  # имя поля или номер бита


@dataclass(eq=False)
class Index(Expr):
    obj: Expr
    indices: list[Expr]


@dataclass(eq=False)
class Deref(Expr):
    obj: Expr


@dataclass(eq=False)
class Arg(Node):
    name: str | None
    value: Expr
    output: bool = False  # name => var
    negated: bool = False  # NOT name => var


@dataclass(eq=False)
class Call(Expr):
    func: Expr
    args: list[Arg]


@dataclass(eq=False)
class ArrayInit(Expr):
    """Инициализатор [1, 2(3), 4] — элементы с повторами."""

    items: list[tuple[Expr | None, Expr]]  # (повтор, значение)


@dataclass(eq=False)
class StructInit(Expr):
    fields: list[tuple[str, Expr]]


# ---------------------------------------------------------------- операторы


@dataclass(eq=False)
class Stmt(Node):
    pass


@dataclass(eq=False)
class Assign(Stmt):
    target: Expr
    value: Expr
    op: str = ":="  # := S= R= REF=


@dataclass(eq=False)
class CallStmt(Stmt):
    call: Call


@dataclass(eq=False)
class If(Stmt):
    branches: list[tuple[Expr, list[Stmt]]]
    else_body: list[Stmt] | None = None


@dataclass(eq=False)
class CaseLabel(Node):
    low: Expr
    high: Expr | None = None


@dataclass(eq=False)
class Case(Stmt):
    selector: Expr
    branches: list[tuple[list[CaseLabel], list[Stmt]]]
    else_body: list[Stmt] | None = None


@dataclass(eq=False)
class For(Stmt):
    var: str
    first: Expr
    last: Expr
    step: Expr | None
    body: list[Stmt]


@dataclass(eq=False)
class While(Stmt):
    cond: Expr
    body: list[Stmt]


@dataclass(eq=False)
class Repeat(Stmt):
    body: list[Stmt]
    cond: Expr


@dataclass(eq=False)
class Exit(Stmt):
    pass


@dataclass(eq=False)
class Continue(Stmt):
    pass


@dataclass(eq=False)
class Return(Stmt):
    pass


@dataclass(eq=False)
class Jmp(Stmt):
    label: str


@dataclass(eq=False)
class Label(Stmt):
    name: str


@dataclass(eq=False)
class Empty(Stmt):
    pass


@dataclass(eq=False)
class ErrorStmt(Stmt):
    message: str


# ---------------------------------------------------------------- объявления


@dataclass(eq=False)
class TypeRef(Node):
    """Тип в объявлении. ``text`` — исходный текст типа (без тривиа по краям)."""

    name: str  # INT, STRING, ARRAY, POINTER, REFERENCE, имя пользовательского типа, STRUCT (встроенный)
    text: str
    length: Expr | None = None  # STRING(n)
    dims: list[tuple[Expr, Expr]] = field(default_factory=list)  # ARRAY [lo..hi, ...]
    elem: TypeRef | None = None  # ARRAY OF / POINTER TO / REFERENCE TO
    subrange: tuple[Expr, Expr] | None = None  # INT(0..100)


@dataclass(eq=False)
class VarDecl(Node):
    names: list[str]
    name_tokens: list[int]
    type: TypeRef
    init: Expr | None = None
    at: str | None = None
    pragmas: list[str] = field(default_factory=list)


@dataclass(eq=False)
class VarSection(Node):
    kind: str  # VAR VAR_INPUT VAR_OUTPUT VAR_IN_OUT VAR_GLOBAL VAR_TEMP VAR_STAT VAR_EXTERNAL VAR_INST VAR_CONFIG
    qualifiers: list[str]  # CONSTANT RETAIN PERSISTENT NON_RETAIN
    decls: list[VarDecl]
    pragmas: list[str] = field(default_factory=list)


@dataclass(eq=False)
class PouHeader(Node):
    kind: str  # PROGRAM FUNCTION_BLOCK FUNCTION METHOD PROPERTY INTERFACE ACTION
    name: str
    return_type: TypeRef | None = None
    extends: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)  # ABSTRACT FINAL PUBLIC PRIVATE PROTECTED INTERNAL
    pragmas: list[str] = field(default_factory=list)


@dataclass(eq=False)
class EnumValue(Node):
    name: str
    value: Expr | None = None


@dataclass(eq=False)
class TypeDecl(Node):
    name: str
    kind: str  # STRUCT UNION ENUM ALIAS SUBRANGE
    fields: list[VarDecl] = field(default_factory=list)  # STRUCT / UNION
    values: list[EnumValue] = field(default_factory=list)  # ENUM
    base: TypeRef | None = None  # ENUM с базовым типом, ALIAS, SUBRANGE, STRUCT EXTENDS
    extends: str | None = None
    init: Expr | None = None
    pragmas: list[str] = field(default_factory=list)


@dataclass(eq=False)
class Declaration(Node):
    """Разобранная часть объявлений: заголовок (если есть), секции переменных, типы."""

    header: PouHeader | None
    sections: list[VarSection] = field(default_factory=list)
    types: list[TypeDecl] = field(default_factory=list)

    def all_vars(self) -> list[tuple[VarSection, VarDecl, str]]:
        out: list[tuple[VarSection, VarDecl, str]] = []
        for sec in self.sections:
            for d in sec.decls:
                for n in d.names:
                    out.append((sec, d, n))
        return out


def walk_expr(e: Expr | None) -> list[Expr]:
    """Все подвыражения в порядке обхода (сначала узел, потом дети)."""
    out: list[Expr] = []
    stack: list[Expr] = [e] if e is not None else []
    while stack:
        x = stack.pop()
        out.append(x)
        kids: list[Expr] = []
        if isinstance(x, Unary):
            kids = [x.operand]
        elif isinstance(x, Binary):
            kids = [x.left, x.right]
        elif isinstance(x, Member | Deref):
            kids = [x.obj]
        elif isinstance(x, Index):
            kids = [x.obj, *x.indices]
        elif isinstance(x, Call):
            kids = [x.func, *(a.value for a in x.args)]
        elif isinstance(x, ArrayInit):
            for rep, val in x.items:
                if rep is not None:
                    kids.append(rep)
                kids.append(val)
        elif isinstance(x, StructInit):
            kids = [v for _, v in x.fields]
        stack.extend(reversed(kids))
    return out


def stmt_exprs(s: Stmt) -> list[Expr]:
    """Выражения, непосредственно принадлежащие оператору (без вложенных операторов)."""
    if isinstance(s, Assign):
        return [s.target, s.value]
    if isinstance(s, CallStmt):
        return [s.call]
    if isinstance(s, If):
        return [c for c, _ in s.branches]
    if isinstance(s, Case):
        out: list[Expr] = [s.selector]
        for labels, _ in s.branches:
            for lab in labels:
                out.append(lab.low)
                if lab.high is not None:
                    out.append(lab.high)
        return out
    if isinstance(s, For):
        return [x for x in (s.first, s.last, s.step) if x is not None]
    if isinstance(s, While | Repeat):
        return [s.cond]
    return []


def child_bodies(s: Stmt) -> list[list[Stmt]]:
    if isinstance(s, If):
        out = [b for _, b in s.branches]
        if s.else_body is not None:
            out.append(s.else_body)
        return out
    if isinstance(s, Case):
        out = [b for _, b in s.branches]
        if s.else_body is not None:
            out.append(s.else_body)
        return out
    if isinstance(s, For | While | Repeat):
        return [s.body]
    return []


def walk_stmts(body: list[Stmt]) -> list[Stmt]:
    out: list[Stmt] = []
    stack = list(reversed(body))
    while stack:
        s = stack.pop()
        out.append(s)
        for b in reversed(child_bodies(s)):
            stack.extend(reversed(b))
    return out
