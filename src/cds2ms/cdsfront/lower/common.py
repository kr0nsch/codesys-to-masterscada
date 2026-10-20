"""Общие структуры понижения: заметки (будущие находки), результат, генератор служебных имён."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LowerNote:
    rule: str
    outcome: str  # auto review verify manual impossible info
    message: str
    line: int = 0
    col: int = 0
    local_id: str | None = None
    exec_order: int | None = None


@dataclass
class LowerResult:
    body: str
    vars: list[tuple[str, str]] = field(default_factory=list)  # (имя, тип) — добавить в VAR
    notes: list[LowerNote] = field(default_factory=list)
    inputs: list[tuple[str, str]] = field(default_factory=list)  # добавить в VAR_INPUT (режим вызова)
    outputs: list[tuple[str, str]] = field(default_factory=list)  # добавить в VAR_OUTPUT


class Names:
    """Служебные имена ``mig…``: без ``__`` и без ``_`` по краям (MS-ST-02), без коллизий с именами POU."""

    def __init__(self, taken: set[str] | None = None) -> None:
        self.taken = {t.lower() for t in (taken or set())}

    def new(self, base: str) -> str:
        name = base
        k = 1
        while name.lower() in self.taken:
            k += 1
            name = f"{base}{k}"
        self.taken.add(name.lower())
        return name


def paren(expr: str) -> str:
    e = expr.strip()
    if all(ch.isalnum() or ch in "_.[]^#'" for ch in e):
        return e
    if e.startswith("NOT ") and all(ch.isalnum() or ch in "_.[]^" for ch in e[4:]):
        return e
    depth = 0
    j = 0
    while j < len(e) and (e[j].isalnum() or e[j] in "_."):
        j += 1
    if 0 < j < len(e) and e[j] == "(" and e.endswith(")"):  # вызов F(…) — атом, если скобка закрывается в конце
        for i in range(j, len(e)):
            depth += e[i] == "("
            depth -= e[i] == ")"
            if depth == 0:
                if i == len(e) - 1:
                    return e
                break
        depth = 0
    if e.startswith("(") and e.endswith(")"):
        for i, ch in enumerate(e):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(e) - 1:
                break
        else:
            return e
    return f"({e})"
