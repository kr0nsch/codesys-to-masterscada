"""Находка и правка — общие типы правил и трансформаций."""

from __future__ import annotations

from dataclasses import dataclass, field

from .registry import SEVERITY, rule


@dataclass
class Finding:
    rule: str
    outcome: str
    language: str  # ST IL LD FBD CFC SFC DECL PROJECT
    pou: str | None
    file: str
    line: int
    col: int
    message: str
    local_id: str | None = None
    fix: str = "none"  # none | available | applied | conflict
    related: list[str] = field(default_factory=list)
    minutes: tuple[float, float, float] = (0.0, 0.0, 0.0)
    text_offset: int | None = None  # смещение в понижённом тексте (для маркера)
    part: str = ""  # decl | body | gvl | dut | project

    @property
    def documented(self) -> bool:
        return rule(self.rule).documented

    @property
    def family_outcome(self) -> str:
        return self.outcome

    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.file, self.line, self.col, self.rule)

    def to_json(self) -> dict[str, object]:
        r = rule(self.rule)
        origin: dict[str, object] = {"file": self.file}
        if self.line:
            origin["line"] = self.line
        if self.col:
            origin["column"] = self.col
        if self.local_id:
            origin["local_id"] = self.local_id
        out: dict[str, object] = {
            "rule": self.rule,
            "outcome": self.outcome,
            "family_outcome": self.outcome,
            "language": self.language,
            "origin": origin,
            "message": self.message,
            "documented": r.documented,
            "fix": self.fix,
            "minutes": {"min": self.minutes[0], "mode": self.minutes[1], "max": self.minutes[2]},
            "related": sorted(set(self.related)),
            "source_ref": r.sources[0] if r.sources else "",
        }
        if self.pou:
            out["pou"] = self.pou
        return out


@dataclass
class Edit:
    start: int  # смещение символа в тексте
    end: int
    text: str
    rule: str
    level: str  # auto | review | verify


def dedupe(findings: list[Finding]) -> list[Finding]:
    """На место — одна находка с тяжелейшим исходом, остальные ID — в related."""
    by_place: dict[tuple[str, int, int, str | None, str | None], list[Finding]] = {}
    order: list[tuple[str, int, int, str | None, str | None]] = []
    for f in findings:
        if f.line == 0 and f.col == 0:
            key = (f.file, f.line, id(f), f.pou, f.local_id)
        else:
            key = (f.file, f.line, f.col, f.pou, f.local_id)
        if key not in by_place:
            by_place[key] = []
            order.append(key)
        by_place[key].append(f)
    out: list[Finding] = []
    for key in order:
        group = by_place[key]
        if len(group) == 1:
            out.append(group[0])
            continue
        group.sort(key=lambda f: (-SEVERITY[f.outcome], f.rule))
        head = group[0]
        for other in group[1:]:
            for r in (other.rule, *other.related):
                if r != head.rule and r not in head.related:
                    head.related.append(r)
            if other.fix == "applied" and head.fix == "none":
                head.fix = "applied"
        out.append(head)
    out.sort(key=Finding.sort_key)
    return out
