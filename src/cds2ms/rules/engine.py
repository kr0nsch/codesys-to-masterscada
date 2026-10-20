"""Анализ понижённого проекта правилами MS-* и план правок Master ST.

Вход — ``LoweredProject`` (ST CODESYS после понижения графики, SFC, IL, ООП). Выход — находки с исходом,
происхождением и минутами плюс правки по границам токенов для трансформаций (``transform/``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..cdsfront.lower import LoweredPou, LoweredProject
from ..cdsfront.st import ast as A
from ..cdsfront.st.lexer import TRIVIA, Kind, Token
from ..cdsfront.st.parser import KEYWORDS as _ST_KEYWORDS
from ..cdsfront.st.parser import Parsed, ParsedBody, ParsedDecl, parse_body, parse_decl
from ..cdsfront.stdlib import FUNC_OPS, INFIX_OPS, INT_TYPES, STD_FBS, STD_FUNCS, is_conversion
from ..cdsfront.symbols import VarInfo, collect_vars
from ..ir.model import Origin
from ..profiles import Profile, effort, load_data
from .findings import Edit, Finding, dedupe
from .registry import rule

_Add = Callable[..., None]
_TIMERS = frozenset({"TON", "TOF", "TP"})
_PTR_FUNCS = frozenset({"ADR", "__NEW", "__DELETE", "SIZEOF", "MEMCPY", "MEMSET", "__QUERYINTERFACE", "__ISVALIDREF"})
_CAA_PINS = frozenset({"xexecute", "xdone", "xbusy", "xerror", "eerror", "xabort"})
_MARK_RE = re.compile(r"//\s*MIGRATION-(TODO|CHECK):\s*(.*)")


def norm02(name: str) -> str:
    """MS-ST-02: два и более «_» подряд → один, «_» в конце снимается."""
    out = re.sub(r"_{2,}", "_", name)
    out = out.rstrip("_")
    return out or "mig"


def violates02(name: str) -> bool:
    return "__" in name or name.endswith("_")


@dataclass
class NameRules:
    keywords: frozenset[str]
    lua: frozenset[str]
    rewrite_lua: bool

    def rename(self, name: str) -> tuple[str, list[tuple[str, str]]]:
        """Новое имя и [(правило, уровень)] — что сработало."""
        hits: list[tuple[str, str]] = []
        new = name
        up = name.upper()
        if up in ("EN", "ENO"):
            return f"mig{up}", [("MS-ST-01", "review")]
        if violates02(new):
            new = norm02(new)
            hits.append(("MS-ST-02", "auto"))
        if new.upper() in self.keywords:
            new = f"mig{new}"
            hits.append(("MS-NAME-02", "auto"))
        elif new in self.lua:  # Lua различает регистр: слово — только в нижнем регистре
            hits.append(("MS-NAME-02", "verify"))
            if self.rewrite_lua:
                new = f"mig{new}"
        return new, hits


@dataclass
class PouPlan:
    """Правки одного объекта: объявление и тело (тексты после понижения)."""

    name: str
    kind: str  # pou | gvl | dut
    decl_text: str
    body_text: str
    decl_edits: list[Edit] = field(default_factory=list)
    body_edits: list[Edit] = field(default_factory=list)
    stmt_rules: set[str] = field(default_factory=set)  # S=/R=, JMP — второй проход
    stat_vars: list[tuple[str, str, str]] = field(default_factory=list)  # (новое имя, тип, инициализация)
    manual_markers: list[tuple[str, int, str]] = field(default_factory=list)  # (часть, смещение, текст)
    lowered: LoweredPou | None = None


@dataclass
class IoBinding:
    pou: str
    var: str
    param: str
    address: str
    direction: str  # in | out | memory
    type: str
    file: str
    line: int


@dataclass
class Analysis:
    findings: list[Finding]
    plans: dict[str, PouPlan]
    io: list[IoBinding]
    gvl_renames: dict[tuple[str, str], str]  # (GVL, var) -> имя параметра узла
    renames: list[tuple[str, str, str, str]]  # (объект, было, стало, правило)
    names: NameRules
    profile: Profile


class _Ctx:
    def __init__(self, lp: LoweredProject, profile: Profile, rewrite: set[str]) -> None:
        self.lp = lp
        self.project = lp.project
        self.syms = lp.syms
        self.profile = profile
        self.rewrite = rewrite
        self.names = NameRules(
            frozenset(n.upper() for n in profile.names("keywords")),
            frozenset(n.lower() for n in profile.names("lua")),
            "MS-NAME-02" in rewrite,
        )
        self.findings: list[Finding] = []
        self.plans: dict[str, PouPlan] = {}
        self.io: list[IoBinding] = []
        self.renames: list[tuple[str, str, str, str]] = []
        self.period = int(profile.semantics.get("task_period_default_ms", 100))
        libmap = load_data("lib-map.toml")
        self.lib_same = {x.upper() for x in libmap["standard"]["same"]}
        self.lib_verify = {x.upper() for x in libmap["standard"]["verify"]}
        self.lib_util = {x.upper() for x in libmap["util"]["manual"]}
        self.lib_prefixes = tuple(p.upper() for p in libmap["caa"]["prefixes"])
        # глобальные переменные → параметры узла GVL_x
        self.gvl_map: dict[tuple[str, str], str] = {}
        self.global_unqualified: dict[str, str] = {}
        taken = {p.name.lower() for p in self.project.pous} | {d.name.lower() for d in self.project.duts}
        for g in self.project.gvls:
            gname = self.names.rename(g.name)[0]
            for k, v in self.syms.gvls.get(g.name.lower(), {}).items():
                base = f"{gname}_{self.names.rename(v.name)[0]}"
                new = base
                n = 1
                while new.lower() in taken:
                    n += 1
                    new = f"{base}{n}"
                if new != base:
                    self._add(Finding("MS-NAME-01", "review", "DECL", None, g.origin.file, g.origin.line, 0,
                                      f"{g.name}.{v.name} → {new}: коллизия имени параметра узла", part="gvl"))  # fmt: skip
                taken.add(new.lower())
                self.gvl_map[(g.name.lower(), k)] = new
                self.global_unqualified.setdefault(k, new)
        self.gvl_lower = {g.name.lower() for g in self.project.gvls}
        self.enum_types = {k for k, td in self.syms.types.items() if td.kind == "ENUM"}
        self.alias_types = {
            k: td for k, td in self.syms.types.items() if td.kind in ("ALIAS", "SUBRANGE") and td.base is not None
        }
        self.program_names = {p.name.lower() for p in self.project.pous if p.kind == "program"}
        self.function_names = {p.name.lower() for p in self.project.pous if p.kind == "function"}
        self.declared = self._declared_names()
        self.pou_task: dict[str, str] = {}
        for t in self.project.tasks:
            for pn in t.pous:
                self.pou_task.setdefault(pn.lower(), t.name)

    def _declared_names(self) -> set[str]:
        """Имена, объявленные в проекте: правила имён не трогают пины стандартных блоков и ключевые слова."""
        out: set[str] = set()
        for p in self.project.pous:
            out.add(p.name.lower())
            for m in p.methods:
                out.add(m.name.lower())
            for pr in p.properties:
                out.add(pr.name.lower())
            for a in p.actions:
                out.add(a.name.lower())
        for ps in self.syms.pous.values():
            out.update(ps.vars)
        for lpou in self.lp.pous:
            out.update(collect_vars(parse_decl(lpou.decl).decl))
        for d in self.project.duts:
            out.add(d.name.lower())
        for k, td in self.syms.types.items():
            out.add(k)
            out.update(v.name.lower() for v in td.values)
            for f in td.fields:
                out.update(n.lower() for n in f.names)
        for g in self.project.gvls:
            out.add(g.name.lower())
            out.update(self.syms.gvls.get(g.name.lower(), {}))
        for i in self.project.interfaces:
            out.add(i.name.lower())
        return {n for n in out if n.upper() not in _ST_KEYWORDS}

    # ------------------------------------------------------------ находки

    def _add(self, f: Finding) -> Finding:
        r = rule(f.rule)
        assert f.outcome in ("auto", "review", "verify", "manual", "impossible", "info"), f.outcome
        if f.fix == "none" and r.fix != "none" and f.outcome not in ("info",):
            f.fix = "available"
        f.minutes = effort(f.rule, f.outcome)
        self.findings.append(f)
        return f

    def pos(self, parsed: Parsed, tok_index: int, origin_file: str, base_line: int, base_col: int) -> tuple[int, int]:
        t = parsed.tokens[min(tok_index, len(parsed.tokens) - 1)]
        line = base_line + t.line - 1 if base_line else t.line
        col = (base_col + t.col - 1) if (t.line == 1 and base_col) else t.col
        return line, col

    # ------------------------------------------------------------ переименования

    def rename_edits(
        self, parsed: Parsed, local: dict[str, VarInfo], plan: PouPlan, part: str, origin: tuple[str, int, int],
        lang: str, stat_map: dict[str, str],
    ) -> list[Edit]:  # fmt: skip
        toks = parsed.tokens
        sig = [i for i, t in enumerate(toks) if t.kind not in TRIVIA]
        edits: list[Edit] = []
        seen: set[tuple[str, str]] = set()
        skip: set[int] = set()
        _file, _bline, _bcol = origin
        for n, i in enumerate(sig):
            if i in skip:
                continue
            t = toks[i]
            if t.kind is Kind.TYPED and t.text.upper().startswith(("LTIME#", "LT#")):
                edits.append(Edit(t.offset, t.end, "T#" + t.text.split("#", 1)[1], "MS-TYPE-02", "review"))
                self._once(seen, ("MS-TYPE-02", "ltime-literal"), parsed, i, plan, part, origin, lang,
                           "литерал LTIME# → T# (точность до мс)", "review")  # fmt: skip
                continue
            if t.kind is not Kind.IDENT:
                continue
            prev = toks[sig[n - 1]] if n > 0 else None
            nxt = toks[sig[n + 1]] if n + 1 < len(sig) else None
            nxt2 = toks[sig[n + 2]] if n + 2 < len(sig) else None
            after_dot = prev is not None and prev.is_op(".")
            low = t.text.lower()
            # GVL.x → GVL_x
            if (
                not after_dot
                and low in self.gvl_lower
                and low not in local
                and nxt is not None
                and nxt.is_op(".")
                and nxt2 is not None
                and nxt2.kind is Kind.IDENT
                and (low, nxt2.text.lower()) in self.gvl_map
            ):
                new = self.gvl_map[(low, nxt2.text.lower())]
                edits.append(Edit(t.offset, nxt2.end, new, "MS-ST-08", "auto"))
                skip.update({sig[n + 1], sig[n + 2]})
                self._once(seen, ("MS-ST-08", new), parsed, i, plan, part, origin, lang,
                           f"{t.text}.{nxt2.text} → {new} (параметр узла)", "auto", fix="applied")  # fmt: skip
                self.renames.append((plan.name, f"{t.text}.{nxt2.text}", new, "MS-ST-08"))
                continue
            if not after_dot and low in stat_map and part == "body":
                edits.append(Edit(t.offset, t.end, stat_map[low], "MS-DECL-02", "review"))
                continue
            formal_name = (
                nxt is not None and (nxt.is_op(":=") or nxt.is_op("=>"))
                and prev is not None and (prev.is_op("(") or prev.is_op(","))
            )  # имя формального параметра в вызове «f(имя := …)» — не обращение к глобальной  # fmt: skip
            if (
                not after_dot
                and not formal_name
                and low not in local
                and low in self.global_unqualified
                and part == "body"
            ):
                new = self.global_unqualified[low]
                edits.append(Edit(t.offset, t.end, new, "MS-ST-08", "auto"))
                self._once(seen, ("MS-ST-08", new), parsed, i, plan, part, origin, lang,
                           f"{t.text} → {new} (параметр узла)", "auto", fix="applied")  # fmt: skip
                continue
            if not after_dot and part == "decl" and low in self.alias_types and _in_type_position(toks, sig, n):
                td = self.alias_types[low]
                assert td.base is not None
                base_text = td.base.name if td.kind == "SUBRANGE" else td.base.text
                edits.append(Edit(t.offset, t.end, base_text, "MS-TYPE-04", "auto"))
                self._once(seen, ("MS-TYPE-04", low), parsed, i, plan, part, origin, lang,
                           f"тип {t.text} → {base_text}", "auto", fix="applied")  # fmt: skip
                continue
            if t.upper in ("LTIME", "WSTRING") and part in ("decl",) and _in_type_position(toks, sig, n):
                repl = "TIME" if t.upper == "LTIME" else "STRING"
                edits.append(Edit(t.offset, t.end, repl, "MS-TYPE-02", "review"))
                self._once(seen, ("MS-TYPE-02", t.upper), parsed, i, plan, part, origin, lang,
                           f"{t.upper} → {repl}" + (" (точность до мс)" if repl == "TIME" else " (UTF-8)"), "review")  # fmt: skip
                continue
            if low not in self.declared:
                continue
            new, hits = self.names.rename(t.text)
            if not hits:
                continue
            for rid, level in hits:
                outcome = {"auto": "auto", "review": "review", "verify": "verify"}[level]
                applied = level == "auto" or (level == "verify" and self.names.rewrite_lua)
                self._once(seen, (rid, low), parsed, i, plan, part, origin, lang,
                           f"имя {t.text} → {new}" if new != t.text else f"имя {t.text}: слово Lua (проба P-ST-04)",
                           outcome, fix="applied" if applied else "available")  # fmt: skip
            if new != t.text:
                level = max((lv for _, lv in hits), key=lambda x: {"auto": 0, "review": 1, "verify": 2}[x])
                edits.append(Edit(t.offset, t.end, new, hits[0][0], level))
                if (plan.name, t.text, new) not in {(a, b, c) for a, b, c, _ in self.renames}:
                    self.renames.append((plan.name, t.text, new, hits[0][0]))
        return edits

    def _once(
        self, seen: set[tuple[str, str]], key: tuple[str, str], parsed: Parsed, tok: int, plan: PouPlan, part: str,
        origin: tuple[str, int, int], lang: str, msg: str, outcome: str, fix: str = "none",
    ) -> None:  # fmt: skip
        if key in seen:
            return
        seen.add(key)
        file, bline, bcol = origin
        line, col = self.pos(parsed, tok, file, bline, bcol)
        self._add(Finding(key[0], outcome, "DECL" if part in ("decl", "gvl", "dut") else lang, plan.name, file, line, col,
                          msg, fix=fix, text_offset=parsed.tokens[tok].offset, part=part))  # fmt: skip

    # ------------------------------------------------------------ объявления

    def check_decl(self, pd: ParsedDecl, plan: PouPlan, origin: tuple[str, int, int], kind: str) -> dict[str, str]:
        """Проверки секций и типов; возвращает карту VAR_STAT → глобальное имя."""
        file, bline, bcol = origin
        stat_map: dict[str, str] = {}
        h = pd.decl.header
        if h is not None:
            if h.implements or h.extends:
                line, col = self.pos(pd, h.start, file, bline, bcol)
                self._add(Finding("MS-LANG-06", "review", "DECL", plan.name, file, line, col,
                                  f"{'EXTENDS ' + ', '.join(h.extends) if h.extends else ''}"
                                  f"{' IMPLEMENTS ' + ', '.join(h.implements) if h.implements else ''} снимается",
                                  fix="available", part="decl"))  # fmt: skip
                # правка: убрать EXTENDS/IMPLEMENTS из заголовка
                toks = pd.tokens
                for j in range(h.start, h.end):
                    if toks[j].is_kw("EXTENDS", "IMPLEMENTS"):
                        a = toks[j].offset
                        b = toks[h.end - 1].end
                        plan.decl_edits.append(Edit(a, b, "", "MS-LANG-06", "review"))
                        break
        has_bool_input = False
        for sec in pd.decl.sections:
            line, col = self.pos(pd, sec.start, file, bline, bcol)
            if sec.kind == "VAR_IN_OUT":
                kw = pd.tokens[sec.start]
                plan.decl_edits.append(Edit(kw.offset, kw.end, "VAR_INOUT", "MS-DECL-01", "auto"))
                self._add(Finding("MS-DECL-01", "verify", "DECL", plan.name, file, line, col,
                                  "VAR_IN_OUT → var_inout; ссылочная ли передача в MS4D — проба P-ST-01", fix="applied",
                                  part="decl"))  # fmt: skip
            if sec.kind == "VAR_STAT":
                self._add(Finding("MS-DECL-02", "review", "DECL", plan.name, file, line, col,
                                  f"VAR_STAT ({len(sec.decls)}) → глобальные параметры узла mig{plan.name}_<имя>",
                                  part="decl"))  # fmt: skip
                a = pd.tokens[sec.start].offset
                b = pd.tokens[sec.end - 1].end
                plan.decl_edits.append(Edit(a, b, "", "MS-DECL-02", "review"))
                for d in sec.decls:
                    for nm in d.names:
                        g = f"mig{plan.name}_{nm}"
                        stat_map[nm.lower()] = g
                        init = pd.span_text(d.init) if d.init is not None else ""
                        plan.stat_vars.append((g, d.type.text, init))
            if sec.kind == "VAR_TEMP":
                self._add(Finding("MS-ST-09", "info", "DECL", plan.name, file, line, col,
                                  "VAR_TEMP ↔ доступ Temp (в отладочной конфигурации — Local)", part="decl"))  # fmt: skip
            if "PERSISTENT" in sec.qualifiers:
                for j in range(sec.start, sec.end):
                    tk = pd.tokens[j]
                    if tk.is_kw("PERSISTENT"):
                        repl = "" if "RETAIN" in sec.qualifiers else "RETAIN"
                        a = tk.offset
                        b = tk.end
                        if not repl and a > 0 and pd.text[a - 1] == " ":
                            a -= 1
                        plan.decl_edits.append(Edit(a, b, repl, "MS-DECL-06", "review"))
                        break
                self._add(Finding("MS-DECL-06", "review", "DECL", plan.name, file, line, col,
                                  "PERSISTENT → RETAIN: «переживает загрузку» в MS4D нет", part="decl"))  # fmt: skip
            if "RETAIN" in sec.qualifiers or "PERSISTENT" in sec.qualifiers:
                self._add(Finding("MS-RET-01", "info", "DECL", plan.name, file, line, col + 1,
                                  "retain пишется периодически или при остановке, есть «время актуальности»", part="decl"))  # fmt: skip
            if "CONSTANT" in sec.qualifiers and sec.kind == "VAR_GLOBAL":
                self._add(Finding("MS-DECL-04", "review", "DECL", plan.name, file, line, col,
                                  "VAR_GLOBAL CONSTANT → globalVars constant=\"true\" (проба P-ST-08)", part="decl"))  # fmt: skip
            for d in sec.decls:
                dl, dc = self.pos(pd, d.start, file, bline, bcol)
                if sec.kind == "VAR_INPUT" and d.type.name == "BOOL" and kind == "program":
                    has_bool_input = True
                if d.at:
                    up = d.at.upper()
                    direction = "in" if up.startswith("%I") else "out" if up.startswith("%Q") else "memory"
                    for nm in d.names:
                        param = self.gvl_map.get((plan.name.lower(), nm.lower()), f"{plan.name}_{nm}")
                        self.io.append(IoBinding(plan.name, nm, param, d.at, direction, d.type.text, file, dl))
                    if direction == "memory":
                        self._add(Finding("MS-ST-07", "manual", "DECL", plan.name, file, dl, dc,
                                          f"{', '.join(d.names)} AT {d.at}: наложение %M — вручную", part="decl"))  # fmt: skip
                    else:
                        self._add(Finding("MS-ST-07", "review", "DECL", plan.name, file, dl, dc,
                                          f"{', '.join(d.names)} AT {d.at} → параметр и строка io-binding.csv", part="decl"))  # fmt: skip
                    for j in range(d.start, d.end):
                        tk = pd.tokens[j]
                        if tk.is_kw("AT"):
                            nxt = next(k for k in range(j + 1, d.end) if pd.tokens[k].kind is Kind.ADDR)
                            a = tk.offset
                            if a > 0 and pd.text[a - 1] == " ":
                                a -= 1
                            plan.decl_edits.append(Edit(a, pd.tokens[nxt].end, "", "MS-ST-07",
                                                        "review" if direction != "memory" else "manual"))  # fmt: skip
                            break
                self.check_type(pd, d.type, plan, file, dl, dc, sec.kind, d)
        if has_bool_input:
            line, col = self.pos(pd, h.start if h else 0, file, bline, bcol)
            self._add(Finding("MS-ST-10", "info", "DECL", plan.name, file, line, col + 2,
                              "BOOL-входы программы: в MS4D у параметра есть «Переключение» R_EDGE/F_EDGE", part="decl"))  # fmt: skip
        return stat_map

    def check_type(self, pd: ParsedDecl, t: A.TypeRef, plan: PouPlan, file: str, line: int, col: int, section: str,
                   d: A.VarDecl | None) -> None:  # fmt: skip
        if t.name in ("POINTER", "REFERENCE"):
            if t.name == "REFERENCE" and section in ("VAR_INPUT", "VAR_IN_OUT"):
                self._add(Finding("MS-ST-05", "review", "DECL", plan.name, file, line, col,
                                  "REFERENCE TO в параметре → var_inout", part="decl"))  # fmt: skip
            else:
                self._add(Finding("MS-ST-05", "manual", "DECL", plan.name, file, line, col,
                                  f"{t.text}: указатели и ссылки в Master ST не описаны", part="decl"))  # fmt: skip
        elif t.name == "STRING" and t.length is not None:
            self._add(Finding("MS-TYPE-02", "review", "DECL", plan.name, file, line, col,
                              f"{t.text} → STRING (переменной длины, UTF-8): обрезка по длине теряется", fix="available",
                              part="decl"))  # fmt: skip
            a = pd.tokens[t.start].offset
            b = pd.tokens[t.end - 1].end
            plan.decl_edits.append(Edit(a, b, "STRING", "MS-TYPE-02", "review"))
        elif t.name == "ARRAY":
            if len(t.dims) > 3:
                self._add(Finding("MS-TYPE-05", "review", "DECL", plan.name, file, line, col,
                                  f"массив {len(t.dims)} осей > 3 — сплющить индекс", part="decl"))  # fmt: skip
            if t.elem is not None:
                self.check_type(pd, t.elem, plan, file, line, col, section, None)
        elif t.name == "DT" and d is not None and d.init is None:
            self._add(Finding("MS-TYPE-06", "review", "DECL", plan.name, file, line, col,
                              "DT без инициализации: в MS4D по умолчанию DT#0001-01-01, в CODESYS 1970", part="decl"))  # fmt: skip
        elif t.subrange is not None:
            self._add(Finding("MS-TYPE-04", "auto", "DECL", plan.name, file, line, col,
                              f"поддиапазон {t.text} → {t.name}", fix="applied", part="decl"))  # fmt: skip
            a = pd.tokens[t.start].offset
            b = pd.tokens[t.end - 1].end
            plan.decl_edits.append(Edit(a, b, t.name, "MS-TYPE-04", "auto"))
        else:
            up = t.name.upper().split(".")[-1]
            if up in self.lib_verify:
                self._add(Finding("MS-LIB-01", "verify", "DECL", plan.name, file, line, col,
                                  f"{t.name}: в MS4D есть, типы PV/CV сверить", part="decl"))  # fmt: skip
            elif (
                up in self.lib_same
                or t.name.lower() in self.syms.pous
                or t.name.lower() in self.syms.types
                or up in _ELEMENTARY_OK
                or t.name.lower() in self.syms.interfaces
            ):
                pass
            elif up in self.lib_util or up.startswith(self.lib_prefixes) or "." in t.name:
                self._add(Finding("MS-LIB-02", "manual", "DECL", plan.name, file, line, col,
                                  f"{t.name}: библиотечный блок без замены в MS4D (data/lib-map.toml)", part="decl"))  # fmt: skip
            else:
                self._add(Finding("MS-LIB-02", "manual", "DECL", plan.name, file, line, col,
                                  f"тип {t.name} не найден в проекте и в «Стандартной» MS4D", part="decl"))  # fmt: skip

    # ------------------------------------------------------------ тела

    def check_body(self, pb: ParsedBody, local: dict[str, VarInfo], plan: PouPlan, origin: tuple[str, int, int],
                   lang: str, lowered_from_graph: bool) -> None:  # fmt: skip
        file, bline, bcol = origin
        seen: set[tuple[str, str]] = set()

        def at(node: A.Node) -> tuple[int, int]:
            if lowered_from_graph:
                return bline, bcol
            return self.pos(pb, node.start, file, bline, bcol)

        def add(rid: str, outcome: str, node: A.Node, msg: str, key: str | None = None, fix: str = "none") -> None:
            k = (rid, key or msg)
            if k in seen:
                return
            seen.add(k)
            line, col = at(node)
            self._add(Finding(rid, outcome, lang, plan.name, file, line, col, msg, fix=fix,
                              text_offset=pb.tokens[node.start].offset, part="body"))  # fmt: skip

        for d in pb.diagnostics:
            line = bline + d.line - 1 if bline else d.line
            self._add(Finding("MS-PARSE-01", "manual", lang, plan.name, file, line, d.col, d.message, part="body"))
        for t in pb.tokens:
            if t.kind is Kind.COMMENT:
                m = _MARK_RE.search(t.text)
                if m:
                    line = bline + t.line - 1 if bline else t.line
                    self._add(Finding("MS-MARK-01", "info", lang, plan.name, file, line, t.col,
                                      f"маркер s7conv MIGRATION-{m.group(1)}: {m.group(2).strip()[:120]}", part="body"))  # fmt: skip
        for s in A.walk_stmts(pb.stmts):
            if isinstance(s, A.Assign) and s.op in ("S=", "R="):
                add("MS-ST-11", "auto", s, f"{s.op} → IF", key=f"{s.start}", fix="applied")
                plan.stmt_rules.add("MS-ST-11")
            elif isinstance(s, A.Assign) and s.op == "REF=":
                add("MS-ST-12", "manual", s, "REF= — присваивание ссылки", key=f"{s.start}")
            elif isinstance(s, A.Jmp | A.Label) and not lowered_from_graph:
                add("MS-ST-13", "review", s, "JMP/метка → структурировщик (IF или автомат migPc)", key="jmp")
                plan.stmt_rules.add("MS-ST-13")
            elif isinstance(s, A.Case):
                st = self.syms.expr_typeref(s.selector, local)
                if st is not None and st.name.lower() in self.enum_types:
                    add("MS-ST-04", "verify", s, f"CASE по перечислению {st.name} (проба P-ST-02)", key=st.name)
            if isinstance(s, A.CallStmt):
                self.check_call(s.call, local, plan, add, s)
            for e in A.stmt_exprs(s):
                for x in A.walk_expr(e):
                    self.check_expr(x, local, plan, add, s)

    def check_call(self, call: A.Call, local: dict[str, VarInfo], plan: PouPlan, fn: _Add, node: A.Node) -> None:
        func = call.func
        if isinstance(func, A.Name | A.Index):
            base = func if isinstance(func, A.Name) else func.obj
            if isinstance(base, A.Name):
                v = local.get(base.id.lower())
                tname = v.type.name if v is not None else None
                if v is not None and v.type.name == "ARRAY" and v.type.elem is not None:
                    tname = v.type.elem.name
                if tname is not None and tname.upper() in _TIMERS:
                    for a in call.args:
                        if a.name is not None and a.name.upper() == "PT" and isinstance(a.value, A.Literal):
                            ms = _time_ms(a.value.text)
                            if ms is not None and ms % self.period:
                                q = math.ceil(ms / self.period) * self.period
                                fn(
                                    "MS-EXEC-01",
                                    "review",
                                    node,
                                    f"{base.id}: PT {a.value.text} при задаче {self.period} мс срабатывает через {q} мс",
                                    key=f"pt{base.id}",
                                )
                        elif a.name is not None and a.name.upper() == "PT":
                            fn(
                                "MS-EXEC-01",
                                "review",
                                node,
                                f"{base.id}: уставка {a.name} квантуется периодом задачи ({self.period} мс по умолчанию)",
                                key=f"pt{base.id}",
                            )
                for a in call.args:
                    if a.name is not None and a.name.lower() in _CAA_PINS:
                        fn(
                            "MS-ASYNC-01",
                            "manual",
                            node,
                            f"{base.id}: асинхронный ФБ в стиле CAA ({a.name})",
                            key=f"caa{base.id}",
                        )
                        break
            if (
                isinstance(func, A.Name)
                and func.id.lower() in self.program_names
                and func.id.lower() != plan.name.lower()
            ):
                fn(
                    "MS-EXEC-05",
                    "info",
                    node,
                    f"вызов программы {func.id}: выход через связь не доходит — прямой доступ",
                    key=f"prg{func.id}",
                )

    def check_expr(self, x: A.Expr, local: dict[str, VarInfo], plan: PouPlan, fn: _Add, node: A.Node) -> None:
        if isinstance(x, A.Deref) and not (isinstance(x.obj, A.Name) and x.obj.id.upper() in ("THIS", "SUPER")):
            fn("MS-ST-05", "manual", node, "разыменование ^ — указатели", key="deref")
        elif (
            isinstance(x, A.Call)
            and isinstance(x.func, A.Member)
            and isinstance(x.func.obj, A.Name)
            and x.func.obj.id.lower() not in local
            and x.func.obj.id.lower() not in self.gvl_lower
            and x.func.obj.id.lower() not in self.syms.global_vars
            and x.func.obj.id.upper() not in ("THIS", "SUPER")
        ):
            fn(
                "MS-LIB-02",
                "manual",
                node,
                f"{x.func.obj.id}.{x.func.name}: функция библиотеки {x.func.obj.id} — замены нет",
                key=f"lib{x.func.obj.id}.{x.func.name}",
            )
        elif isinstance(x, A.Call) and isinstance(x.func, A.Name):
            up = x.func.id.upper()
            if (
                up not in _KNOWN_FUNCS
                and not is_conversion(up)
                and x.func.id.lower() not in self.function_names
                and x.func.id.lower() not in local
                and x.func.id.lower() not in self.program_names
                and x.func.id.lower() not in self.syms.global_vars
                and not up.startswith("MIG")
            ):
                fn(
                    "MS-LIB-02",
                    "manual",
                    node,
                    f"{x.func.id}(): функция не найдена в проекте и в «Стандартной» MS4D",
                    key=f"fn{up}",
                )
            if up in _PTR_FUNCS:
                fn("MS-ST-05", "manual", node, f"{x.func.id}() — работа с памятью", key=up)
            elif (up.startswith("REAL_TO_") or up.startswith("LREAL_TO_")) and up.split("_TO_", 1)[1] in INT_TYPES:
                fn("MS-TYPE-09", "verify", node, f"{x.func.id}: округление на половинах (проба P-RT-03)", key=up)
            elif up == "LTIME":
                fn("MS-TYPE-02", "review", node, "LTIME(): в MS4D нет LTIME — время в мс (TIME)", key="ltime()")
            elif up == "TIME":
                fn("MS-TYPE-08", "verify", node, "TIME(): разрядность и знак TIME в MS4D (проба P-RT-04)", key="time()")
            for a in x.args:
                if a.name is not None and a.name.upper() in ("EN", "ENO"):
                    fn("MS-ST-01", "review", node, f"{a.name} в вызове ST → migEN/migENO", key="en-arg")
        elif isinstance(x, A.Binary):
            if x.op == "/":
                lt = self.syms.expr_type(x.left, local)
                rt = self.syms.expr_type(x.right, local)
                if lt in INT_TYPES and rt in INT_TYPES:
                    fn("MS-TYPE-07", "verify", node, "деление целых и /0 в Lua (проба P-RT-02)", key="idiv")
            elif x.op == "-":
                lt = self.syms.expr_type(x.left, local)
                if lt == "TIME":
                    fn(
                        "MS-TYPE-08",
                        "verify",
                        node,
                        "разность TIME: переход через 0 и знак (проба P-RT-04)",
                        key="tsub",
                    )
        elif isinstance(x, A.Literal) and x.kind == "dt" and "1970-01-01" in x.text:
            fn("MS-TYPE-06", "review", node, f"{x.text}: «не задано» в MS4D — DT#0001-01-01", key="dt1970")
        elif isinstance(x, A.Member) and isinstance(x.obj, A.Name) and x.obj.id.lower() in self.enum_types:
            fn("MS-ST-04", "verify", node, f"литерал {x.obj.id}.{x.name} (проба P-ST-02)", key=f"enum{x.obj.id}")

    # ------------------------------------------------------------ обход проекта

    def run(self) -> None:
        for lp in self.lp.pous:
            self.analyze_pou(lp)
        for g in self.project.gvls:
            self.analyze_gvl(g.name, g.decl_text, g.origin, g.decl_line, g.persistent)
        for d in self.project.duts:
            self.analyze_dut(d.name, d.decl_text, d.origin, d.decl_line)
        self.analyze_project()

    def analyze_pou(self, lp: LoweredPou) -> None:
        src = lp.source
        plan = PouPlan(lp.name, "pou", lp.decl, lp.body, lowered=lp)
        self.plans[lp.name.lower()] = plan
        pd = parse_decl(lp.decl)
        pb = parse_body(lp.body)
        local = collect_vars(pd.decl)
        decl_file = lp.origin.file
        decl_origin = (decl_file, lp.decl_line, 0) if lp.decl_line else (decl_file, lp.origin.line, 0)
        same_text = src is not None and src.body is not None and src.body.lang == "ST" and src.body.text == lp.body
        graph = not same_text
        body_origin = (lp.body_file, lp.body_line, (src.body.col if src and src.body else 0) if same_text else 0)
        for n in lp.notes:
            outcome = n.outcome
            lang = lp.lang
            self._add(Finding(n.rule, outcome, lang if lang in _LANGS else "ST", lp.name, lp.body_file,
                              n.line or lp.body_line, n.col, n.message, local_id=n.local_id, part="body",
                              fix="applied" if outcome == "review" and n.rule.startswith("MS-LANG") else "none"))  # fmt: skip
        stat_map = self.check_decl(pd, plan, decl_origin, lp.kind)
        self.check_body(pb, local, plan, body_origin, lp.lang if lp.lang in _LANGS else "ST", graph)
        plan.decl_edits.extend(self.rename_edits(pd, local, plan, "decl", decl_origin, lp.lang, {}))
        plan.body_edits.extend(self.rename_edits(pb, local, plan, "body", body_origin, lp.lang, stat_map))
        if lp.lang == "LD" and "(IN :=" in lp.body:
            self._add(Finding("MS-LD-01", "info", "LD", lp.name, lp.body_file, lp.body_line, 1,
                              "при перерисовке в Master LD вход ФБ на цепи станет En: TON при ложной цепи не вызывается"))  # fmt: skip

    def analyze_gvl(self, name: str, text: str, origin: Origin, line: int, persistent: bool) -> None:
        plan = PouPlan(name, "gvl", text, "")
        self.plans[f"gvl:{name.lower()}"] = plan
        pd = parse_decl(text)
        o = (origin.file, line or origin.line, 0)
        self.check_decl(pd, plan, o, "gvl")
        local = collect_vars(pd.decl)
        plan.decl_edits.extend(self.rename_edits(pd, local, plan, "decl", o, "DECL", {}))
        for d in pd.diagnostics:
            self._add(
                Finding("MS-PARSE-01", "manual", "DECL", name, origin.file, (line or 1) + d.line - 1, d.col, d.message)
            )

    def analyze_dut(self, name: str, text: str, origin: Origin, line: int) -> None:
        plan = PouPlan(name, "dut", text, "")
        self.plans[f"dut:{name.lower()}"] = plan
        pd = parse_decl(text)
        o = (origin.file, line or origin.line, 0)
        for td in pd.decl.types:
            tl, tc = self.pos(pd, td.start, origin.file, o[1], 0)
            if td.kind == "UNION":
                self._add(Finding("MS-TYPE-03", "manual", "DECL", name, origin.file, tl, tc, f"UNION {td.name} — вручную",
                                  part="dut"))  # fmt: skip
            elif td.kind in ("ALIAS", "SUBRANGE"):
                self._add(Finding("MS-TYPE-04", "auto", "DECL", name, origin.file, tl, tc,
                                  f"{td.name}: {'поддиапазон' if td.kind == 'SUBRANGE' else 'псевдоним'} → базовый тип "
                                  f"{td.base.text if td.base else ''} в местах использования", fix="applied", part="dut"))  # fmt: skip
            elif td.kind == "ENUM":
                if any(v.value is not None for v in td.values):
                    self._add(Finding("MS-ST-04", "verify", "DECL", name, origin.file, tl, tc,
                                      f"перечисление {td.name} с явными значениями (проба P-ST-02)", part="dut"))  # fmt: skip
                if td.base is not None:
                    self._add(Finding("MS-TYPE-04", "auto", "DECL", name, origin.file, tl, tc + 1,
                                      f"базовый тип перечисления {td.base.text} снимается", fix="applied", part="dut"))  # fmt: skip
                    a = pd.tokens[td.base.start].offset
                    b = pd.tokens[td.base.end - 1].end
                    plan.decl_edits.append(Edit(a, b, "", "MS-TYPE-04", "auto"))
            for f in td.fields:
                fl, fc = self.pos(pd, f.start, origin.file, o[1], 0)
                self.check_type(pd, f.type, plan, origin.file, fl, fc, "STRUCT", f)
        local: dict[str, VarInfo] = {}
        plan.decl_edits.extend(self.rename_edits(pd, local, plan, "decl", o, "DECL", {}))

    def analyze_project(self) -> None:
        p = self.project
        f0 = p.source_file
        self._add(Finding("MS-ST-03", "auto", "PROJECT", None, f0, 0, 0,
                          "тело отделено от объявлений: интерфейс POU — структурой PLCopen XML, тело — <ST>", fix="applied",
                          part="project"))  # fmt: skip
        if self.io:
            if any(b.direction != "memory" for b in self.io):
                self._add(Finding("MS-IO-01", "manual", "PROJECT", None, f0, 0, 0,
                                  f"{len(self.io)} адресных переменных: каналы MS4D и связи — по io-binding.csv", part="project"))  # fmt: skip
        retain = any(f.rule in ("MS-RET-01", "MS-DECL-06") for f in self.findings)
        if retain:
            self._add(Finding("MS-RET-02", "verify", "PROJECT", None, f0, 0, 0,
                              "RETAIN в справке — «при холодном рестарте»: поведение при Reset cold CODESYS не отображается",
                              part="project"))  # fmt: skip
        if any(lp.lang in ("FBD", "CFC") for lp in self.lp.pous):
            self._add(Finding("MS-FBD-01", "info", "PROJECT", None, f0, 0, 0,
                              "при перерисовке в FBD MS4D порядок — по потоку данных или геометрии", part="project"))  # fmt: skip
        has_arrays = any(v.type.name == "ARRAY" for ps in self.syms.pous.values() for v in ps.vars.values())
        if has_arrays:
            self._add(Finding("MS-TYPE-05", "info", "PROJECT", None, f0, 0, 0,
                              "выход за границы массива в MS4D даёт NULL, а не исключение", part="project"))  # fmt: skip
        if len([q for q in self.project.pous if q.kind == "program"]) > 0:
            self._add(Finding("MS-EXEC-04", "info", "PROJECT", None, f0, 0, 0,
                              "связи отрабатываются до программ, прямой доступ — в момент обращения", part="project"))  # fmt: skip
        for t in p.tasks:
            o = t.origin
            k = t.kind.lower()
            if k in ("event", "freewheeling", "status"):
                self._add(Finding("MS-EXEC-02", "review", "PROJECT", None, o.file, o.line, o.col,
                                  f"задача {t.name} ({t.kind}) → циклическая задача + фронт {t.event or ''}".rstrip(),
                                  part="project"))  # fmt: skip
            elif k == "externalevent":
                self._add(Finding("MS-EXEC-02", "impossible", "PROJECT", None, o.file, o.line, o.col,
                                  f"задача {t.name}: внешнее событие — в MS4D нет", part="project"))  # fmt: skip
            if len(t.pous) > 1 or len(p.tasks) > 1:
                self._add(Finding("MS-EXEC-03", "review", "PROJECT", None, o.file, o.line, o.col + 1,
                                  f"задача {t.name}: порядок {', '.join(t.pous) or '—'} → диспетчер migTask_{t.name}",
                                  part="project"))  # fmt: skip
            if t.priority is not None:
                self._add(Finding("MS-EXEC-06", "verify", "PROJECT", None, o.file, o.line, o.col + 2,
                                  f"задача {t.name}: приоритет {t.priority} — направление шкалы MS4D не описано; Priority не "
                                  "записывается (ResetPriority)", part="project"))  # fmt: skip
            if t.interval_ms is not None and t.interval_ms < self.period:
                self._add(Finding("MS-EXEC-07", "info", "PROJECT", None, o.file, o.line, o.col + 3,
                                  f"задача {t.name} {t.interval_ms:g} мс < {self.period} мс по умолчанию: укладывание в период "
                                  "на ПЛК210-0x сверить", part="project"))  # fmt: skip


_LANGS = frozenset({"ST", "IL", "LD", "FBD", "CFC", "SFC", "DECL", "PROJECT"})
_KNOWN_FUNCS = frozenset({*STD_FUNCS, *FUNC_OPS, *INFIX_OPS, "NOT", "TIME", "LTIME", "LOWER_BOUND", "UPPER_BOUND"})
_ELEMENTARY_OK = frozenset(
    {*INT_TYPES, "BOOL", "REAL", "LREAL", "TIME", "LTIME", "DATE", "TOD", "DT", "TIME_OF_DAY", "DATE_AND_TIME",
     "STRING", "WSTRING", "ARRAY", "POINTER", "REFERENCE", "STRUCT", "BIT", "ANY", *STD_FBS}
)  # fmt: skip


def _in_type_position(toks: list[Token], sig: list[int], n: int) -> bool:
    """Токен стоит после «:» объявления или после OF/TO (тип элемента), а не в инициализации."""
    k = n - 1
    while k >= 0:
        t = toks[sig[k]]
        if t.is_op(":") or t.is_kw("OF", "TO"):
            return True
        if t.is_op(":=", ";", "(", ",") or (t.kind is Kind.IDENT and t.is_kw("END_VAR", "VAR")):
            return False
        if t.is_op("[", "]", ".."):
            k -= 1
            continue
        if t.kind in (Kind.IDENT, Kind.INT):
            k -= 1
            continue
        return False
    return False


def _time_ms(text: str) -> float | None:
    m = re.match(r"(?i)^(?:L?T(?:IME)?)#(-)?(.*)$", text.replace("_", ""))
    if not m:
        return None
    total = 0.0
    found = False
    for num, u in re.findall(r"(?i)(\d+(?:\.\d+)?)(ms|us|ns|d|h|m|s)", m.group(2)):
        found = True
        total += (
            float(num)
            * {"d": 86_400_000, "h": 3_600_000, "m": 60_000, "s": 1000, "ms": 1, "us": 0.001, "ns": 1e-6}[u.lower()]
        )
    if not found:
        return None
    return -total if m.group(1) else total


def analyze(lp: LoweredProject, profile: Profile, rewrite: set[str] | None = None) -> Analysis:
    ctx = _Ctx(lp, profile, rewrite or set())
    ctx.run()
    findings = dedupe(ctx.findings)
    return Analysis(findings, ctx.plans, ctx.io, ctx.gvl_map, ctx.renames, ctx.names, profile)
