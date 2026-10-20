"""Промежуточное представление проекта CODESYS (не зависит от цели).

Объявления хранятся текстом ST (из ``interfaceasplaintext`` или восстановленные из структуры TC6), тела —
текстом ST/IL или графом (FBD, LD, CFC, SFC). У каждого объекта — происхождение (файл, строка, столбец).
"""

from __future__ import annotations

from dataclasses import dataclass, field

LANGS = ("ST", "FBD", "LD", "CFC", "SFC", "IL")


@dataclass
class Origin:
    file: str
    line: int = 0
    col: int = 0
    local_id: str | None = None
    exec_order: int | None = None

    def shifted(self, line: int, col: int = 0) -> Origin:
        return Origin(self.file, line, col, self.local_id, self.exec_order)


@dataclass
class Conn:
    ref: str  # localId источника
    formal: str | None = None  # имя выхода источника (formalParameter)


@dataclass
class Pin:
    formal: str
    conns: list[Conn] = field(default_factory=list)
    negated: bool = False
    edge: str = "none"  # rising | falling (вход блока FBD/CFC)


@dataclass
class GElem:
    """Элемент графического тела (FBD, LD, CFC, SFC)."""

    local_id: str
    kind: str  # inVariable outVariable inOutVariable block contact coil leftPowerRail rightPowerRail connector
    # continuation jump label return comment vendorElement step transition actionBlock jumpStep
    # selectionDivergence selectionConvergence simultaneousDivergence simultaneousConvergence macroStep
    line: int = 0
    col: int = 0
    type_name: str = ""  # block: typeName
    instance: str = ""  # block: instanceName
    expr: str = ""  # переменная/выражение; метка перехода; имя шага; цель jumpStep
    negated: bool = False
    edge: str = "none"  # contact: rising | falling
    storage: str = "none"  # coil: set | reset
    inputs: list[Pin] = field(default_factory=list)  # connectionPointIn (у контакта/катушки — formal "")
    outputs: list[Pin] = field(default_factory=list)
    inouts: list[Pin] = field(default_factory=list)
    exec_order: int | None = None
    call_type: str = ""  # operator function functionblock localaction ...
    initial: bool = False  # шаг SFC
    actions: list[SfcAction] = field(default_factory=list)  # actionBlock
    condition: str = ""  # переход SFC: ST-выражение или имя объекта-перехода
    condition_ref: str | None = None  # localId inVariable условия
    name: str = ""  # connector/continuation/label name, step name
    vendor_type: str = ""  # ElementType vendorElement (networktitle, ...)


@dataclass
class SfcAction:
    qualifier: str
    name: str  # ссылка на действие (reference name) или пусто
    duration: str = ""
    indicator: str = ""
    inline: Body | None = None
    line: int = 0


@dataclass
class Body:
    lang: str  # ST FBD LD CFC SFC IL
    text: str = ""  # ST / IL
    line: int = 0  # строка первого символа текста в исходном файле
    col: int = 0
    elems: list[GElem] = field(default_factory=list)  # графические языки
    page_oriented: bool = False
    file: str = ""  # файл тела, если отличается от файла POU (раскладка: <Name>.impl.st)


@dataclass
class Action:
    name: str
    body: Body
    origin: Origin


@dataclass
class Method:
    name: str
    decl_text: str
    body: Body | None
    origin: Origin
    decl_line: int = 0


@dataclass
class Property:
    name: str
    decl_text: str
    get: Method | None
    set: Method | None
    origin: Origin
    decl_line: int = 0


@dataclass
class Pou:
    name: str
    kind: str  # program | functionBlock | function
    decl_text: str
    body: Body | None
    origin: Origin
    decl_line: int = 0  # строка первого символа объявления в исходном файле
    actions: list[Action] = field(default_factory=list)
    transitions: list[Action] = field(default_factory=list)
    methods: list[Method] = field(default_factory=list)
    properties: list[Property] = field(default_factory=list)
    folder: str = ""
    placement: str = "types"  # types | resource | application | layout

    @property
    def lang(self) -> str:
        return self.body.lang if self.body is not None else "ST"


@dataclass
class Interface:
    name: str
    decl_text: str
    methods: list[Method]
    properties: list[Property]
    origin: Origin
    extends: list[str] = field(default_factory=list)


@dataclass
class Dut:
    name: str
    decl_text: str
    origin: Origin
    decl_line: int = 0


@dataclass
class Gvl:
    name: str
    decl_text: str
    origin: Origin
    persistent: bool = False
    decl_line: int = 0


@dataclass
class Task:
    name: str
    kind: str  # Cyclic | Event | Freewheeling | Status | ExternalEvent | unknown
    interval_ms: float | None
    priority: int | None
    pous: list[str]
    origin: Origin
    event: str = ""
    interval_raw: str = ""


@dataclass
class Library:
    name: str
    title: str
    version: str
    company: str
    namespace: str = ""


@dataclass
class ImportIssue:
    rule: str
    message: str
    origin: Origin


@dataclass
class Project:
    name: str
    source_kind: str  # plcopen-xml | st-layout
    source_file: str
    source_sha256: str
    ide: str = ""
    ide_version: str = ""
    pous: list[Pou] = field(default_factory=list)
    interfaces: list[Interface] = field(default_factory=list)
    duts: list[Dut] = field(default_factory=list)
    gvls: list[Gvl] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    libraries: list[Library] = field(default_factory=list)
    placements: list[str] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    has_bom: bool = False

    def pou(self, name: str) -> Pou | None:
        low = name.lower()
        for p in self.pous:
            if p.name.lower() == low:
                return p
        return None

    def languages(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.pous:
            out[p.lang] = out.get(p.lang, 0) + 1
            for a in p.actions:
                out[a.body.lang] = out.get(a.body.lang, 0) + 1
            for m in p.methods:
                if m.body is not None:
                    out[m.body.lang] = out.get(m.body.lang, 0) + 1
        return dict(sorted(out.items()))
