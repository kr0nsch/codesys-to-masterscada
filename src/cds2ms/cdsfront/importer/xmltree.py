"""Лёгкое дерево XML на ``xml.parsers.expat`` с номерами строк и столбцов.

``xml.etree`` номеров строк не даёт, а происхождение находок требует строку и столбец каждого элемента и
начала текста (тела ST в ``xhtml``). expat есть и в Pyodide.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from xml.parsers import expat

PLCOPEN_NS = ("http://www.plcopen.org/xml/tc6_0200", "http://www.plcopen.org/xml/tc6_0201")
XHTML_NS = "http://www.w3.org/1999/xhtml"


@dataclass(eq=False)
class El:
    tag: str  # локальное имя
    ns: str
    attrs: dict[str, str]
    line: int
    col: int
    parent: El | None = None
    children: list[El] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)  # текстовые узлы непосредственно в элементе
    text_line: int = 0
    text_col: int = 0

    @property
    def text(self) -> str:
        return "".join(self.parts)

    def all_text(self) -> str:
        """Текст элемента и всех потомков по порядку (xhtml с <p>, <br/>)."""
        out: list[str] = []

        def rec(e: El) -> None:
            out.append(e.text)
            for c in e.children:
                rec(c)
                if c.tag in ("p", "br"):
                    out.append("\n")

        rec(self)
        return "".join(out)

    def child(self, tag: str) -> El | None:
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def kids(self, tag: str) -> list[El]:
        return [c for c in self.children if c.tag == tag]

    def iter(self, tag: str | None = None) -> Iterator[El]:
        stack = [self]
        while stack:
            e = stack.pop()
            if tag is None or e.tag == tag:
                yield e
            stack.extend(reversed(e.children))

    def datas(self, short: str) -> list[El]:
        """addData/data, имя которого оканчивается на ``/<short>`` (без учёта регистра)."""
        add = self.child("addData")
        if add is None:
            return []
        s = short.lower()
        return [d for d in add.kids("data") if d.attrs.get("name", "").lower().rsplit("/", 1)[-1] == s]

    def data(self, short: str) -> El | None:
        ds = self.datas(short)
        return ds[0] if ds else None

    def path(self) -> str:
        parts = []
        e: El | None = self
        while e is not None:
            nm = e.attrs.get("name")
            parts.append(f"{e.tag}[{nm}]" if nm else e.tag)
            e = e.parent
        return "/".join(reversed(parts))


@dataclass
class Document:
    root: El
    has_bom: bool
    encoding: str


class XmlError(Exception):
    def __init__(self, message: str, line: int, col: int) -> None:
        super().__init__(f"{message} (строка {line}, столбец {col})")
        self.line = line
        self.col = col


def parse(raw: bytes) -> Document:
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    p = expat.ParserCreate(namespace_separator=" ")
    p.buffer_text = True
    stack: list[El] = []
    root: list[El] = []

    def split(name: str) -> tuple[str, str]:
        if " " in name:
            ns, local = name.split(" ", 1)
            return ns, local
        return "", name

    def start(name: str, attrs: dict[str, str]) -> None:
        ns, local = split(name)
        clean = {split(k)[1]: v for k, v in attrs.items()}
        e = El(local, ns, clean, p.CurrentLineNumber, p.CurrentColumnNumber + 1)
        if stack:
            e.parent = stack[-1]
            stack[-1].children.append(e)
        else:
            root.append(e)
        stack.append(e)

    def end(name: str) -> None:
        stack.pop()

    def chars(data: str) -> None:
        if stack:
            e = stack[-1]
            if not e.parts:
                e.text_line = p.CurrentLineNumber
                e.text_col = p.CurrentColumnNumber + 1
            e.parts.append(data)

    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = chars
    try:
        p.Parse(raw, True)
    except expat.ExpatError as exc:
        raise XmlError(expat.errors.messages[exc.code], exc.lineno, exc.offset + 1) from exc
    if not root:
        raise XmlError("пустой документ", 1, 1)
    return Document(root[0], has_bom, "utf-8")
