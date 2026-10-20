"""Трансформации в Master ST: правки по границам токенов в три прохода.

1. Имена и типы (MS-ST-02, MS-ST-08, MS-NAME-02, MS-ST-01, MS-TYPE-02/04, MS-DECL-01/02/06, MS-ST-07, EXTENDS).
2. Операторы: ``S=``/``R=`` → ``IF`` (MS-ST-11).
3. Поток управления: ``JMP`` → структурировщик (MS-ST-13).

``--fix none|safe|review|all``: none — только находки и предлагаемый diff; safe — правки auto; review — плюс
review (с маркером в теле); all — плюс verify правил из ``--rewrite-undocumented``. manual/impossible/info
не применяются никогда: маркер ``MIGRATION-TODO`` и шаг MANUAL_STEPS. Повторный прогон — ноль auto,
``fix(fix(x)) == fix(x)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..cdsfront.lower.jumps import has_jumps, segments_from_body, structure
from ..cdsfront.st import ast as A
from ..cdsfront.st.parser import parse_body
from ..cdsfront.st.printer import fmt_expr
from ..rules.engine import Analysis, PouPlan
from ..rules.findings import Edit, Finding

FIX_LEVELS = ("none", "safe", "review", "all")
MARK = "cds2ms:"


@dataclass
class FixedObject:
    name: str
    kind: str  # pou | gvl | dut
    decl: str
    body: str
    applied: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    pou_kind: str = ""

    @property
    def text(self) -> str:
        if self.kind != "pou":
            return self.decl if self.decl.endswith("\n") else self.decl + "\n"
        end = {"program": "END_PROGRAM", "functionBlock": "END_FUNCTION_BLOCK", "function": "END_FUNCTION"}.get(
            self.pou_kind, "END_PROGRAM"
        )
        decl = self.decl if self.decl.endswith("\n") else self.decl + "\n"
        body = self.body if (self.body.endswith("\n") or not self.body) else self.body + "\n"
        return f"{decl}{body}{end}\n"


def levels_for(fix: str, rewrite: set[str]) -> tuple[set[str], set[str]]:
    """(уровни правок, правила verify к применению)."""
    if fix == "none":
        return set(), set()
    if fix == "safe":
        return {"auto"}, set()
    if fix == "review":
        return {"auto", "review"}, set()
    if fix == "all":
        return {"auto", "review", "verify"}, set(rewrite)
    raise ValueError(f"--fix: {fix}")


def apply_edits(
    text: str, edits: list[Edit], levels: set[str], verify_rules: set[str]
) -> tuple[str, list[str], list[str]]:
    chosen = [e for e in edits if e.level in levels and (e.level != "verify" or e.rule in verify_rules)]
    chosen.sort(key=lambda e: (e.start, e.end, e.rule, e.text))  # полный ключ: результат не зависит от порядка правил
    out: list[str] = []
    pos = 0
    applied: list[str] = []
    conflicts: list[str] = []
    last: Edit | None = None
    for e in chosen:
        if last is not None and e.start == last.start and e.end == last.end and e.text == last.text:
            continue
        if e.start < pos:
            conflicts.append(f"{e.rule}@{e.start}")
            continue
        out.append(text[pos : e.start])
        out.append(e.text)
        pos = e.end
        applied.append(e.rule)
        last = e
    out.append(text[pos:])
    return "".join(out), applied, conflicts


def set_reset(body: str) -> tuple[str, bool]:
    pb = parse_body(body)
    targets = [s for s in A.walk_stmts(pb.stmts) if isinstance(s, A.Assign) and s.op in ("S=", "R=")]
    if not targets:
        return body, False
    out: list[str] = []
    pos = 0
    for s in sorted(targets, key=lambda x: x.start):
        a = pb.tokens[s.start].offset
        b = pb.tokens[s.end - 1].end
        if a < pos:
            continue
        line_start = body.rfind("\n", 0, a) + 1
        pad = body[line_start:a] if not body[line_start:a].strip() else ""
        val = "TRUE" if s.op == "S=" else "FALSE"
        out.append(body[pos:a])
        out.append(f"IF {fmt_expr(s.value)} THEN\n{pad}    {fmt_expr(s.target)} := {val};\n{pad}END_IF;")
        pos = b
    out.append(body[pos:])
    return "".join(out), True


def restructure(body: str) -> tuple[str, str]:
    pb = parse_body(body)
    if not has_jumps(pb):
        return body, "none"
    segs = segments_from_body(pb)
    if segs is None:
        return body, "manual"
    try:
        st = structure(segs)
    except ValueError:
        return body, "manual"
    return st.text, st.mode


def transform(an: Analysis, fix: str = "safe", rewrite: set[str] | None = None) -> dict[str, FixedObject]:
    levels, verify_rules = levels_for(fix, rewrite or set())
    out: dict[str, FixedObject] = {}
    manual_by_obj: dict[str, list[Finding]] = {}
    for f in an.findings:
        if f.outcome in ("manual", "impossible") and f.pou:
            manual_by_obj.setdefault(f.pou.lower(), []).append(f)
    for key, plan in an.plans.items():
        decl, ad, cd = apply_edits(plan.decl_text, plan.decl_edits, levels, verify_rules)
        body, ab, cb = apply_edits(plan.body_text, plan.body_edits, levels, verify_rules)
        applied = ad + ab
        conflicts = cd + cb
        if "auto" in levels and "MS-ST-11" in plan.stmt_rules:
            body, done = set_reset(body)
            if done:
                applied.append("MS-ST-11")
        if "review" in levels and "MS-ST-13" in plan.stmt_rules:
            body2, mode = restructure(body)
            if mode in ("if", "machine"):
                body = body2
                applied.append("MS-ST-13")
                if mode == "machine":
                    decl = _add_local(decl, "migPc", "INT")
        if plan.stat_vars and "review" in levels:
            applied.append("MS-DECL-02")
        obj = FixedObject(plan.name, plan.kind, decl, body, applied, conflicts,
                          plan.lowered.kind if plan.lowered else "")  # fmt: skip
        if plan.kind == "pou":
            obj.body = _markers(obj.body, plan, applied, manual_by_obj.get(plan.name.lower(), []), levels)
        out[key] = obj
    stat = [(n, t, i) for p in an.plans.values() for (n, t, i) in p.stat_vars]
    if stat and "review" in levels:
        lines = ["(* cds2ms: MS-DECL-02 VAR_STAT → параметры узла *)", "VAR_GLOBAL"]
        for n, t, i in stat:
            lines.append(f"    {n} : {t}{' := ' + i if i else ''};")
        lines.append("END_VAR")
        out["gvl:migstat"] = FixedObject("migStat", "gvl", "\n".join(lines) + "\n", "", ["MS-DECL-02"])
    return out


def _add_local(decl: str, name: str, typ: str) -> str:
    text = decl.rstrip()
    return text + f"\nVAR\n    {name} : {typ};\nEND_VAR\n"


def _markers(body: str, plan: PouPlan, applied: list[str], manual: list[Finding], levels: set[str]) -> str:
    head: list[str] = []
    review = sorted({r for r in applied if r in _REVIEW_RULES})
    if review and f"{MARK} сверить" not in body:
        head.append(f"(* {MARK} сверить правки review: {', '.join(review)} *)\n")
    todo = sorted({f.rule for f in manual})
    if todo and f"{MARK} MIGRATION-TODO" not in body:
        head.append(f"(* {MARK} MIGRATION-TODO вручную: {', '.join(todo)} — см. MANUAL_STEPS.md *)\n")
    return "".join(head) + body


_REVIEW_RULES = frozenset({"MS-ST-01", "MS-ST-07", "MS-ST-13", "MS-DECL-02", "MS-DECL-06", "MS-TYPE-02", "MS-LANG-06"})
