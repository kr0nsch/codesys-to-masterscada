"""Эталон «правило × POU» для plc-process-lib @ a321ad0 по чек-листу docs/RULES.md (M12-1).

Чек-лист применяется к исходникам регулярными выражениями — независимо от анализатора cds2ms (модуль cds2ms
не импортируется). Каждая запись — ожидаемый исход и строка-обоснование. Эталон коммитится до правил:
FP = находки вне эталона / все находки (порог 5 %), FN — отдельно (docs/CASE_PROCESSLIB.md).

    python tools/processlib_truth.py <src> > tests/golden/processlib/truth.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

NL = "\n"


def strip_comments(t: str) -> str:
    t = re.sub(r"\(\*.*?\*\)", " ", t, flags=re.S)
    t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)
    return re.sub(r"//[^\n]*", " ", t)


def objects(src: Path) -> dict[str, dict[str, str]]:
    """Объект (POU, DUT, GVL, интерфейс) → {kind, text} — склейка файлов объекта."""
    out: dict[str, dict[str, str]] = {}
    for f in sorted(src.rglob("*.st")):
        name = f.name.split(".")[0]
        rel = "/" + f.relative_to(src).as_posix()
        if "/POUs/" in rel:
            owner, kind = f.parent.name, "pou"
        elif "/Interfaces/" in rel:
            owner, kind = f.parent.name, "itf"
        elif f.name.endswith(".dut.st"):
            owner, kind = name, "dut"
        elif f.name.endswith((".gvl.st", ".pvl.st")):
            owner, kind = name, "gvl"
        else:
            continue
        o = out.setdefault(owner, {"kind": kind, "text": ""})
        o["text"] += NL + strip_comments(f.read_text(encoding="utf-8-sig"))
    return out


def truth(src: Path) -> list[dict[str, str]]:
    objs = objects(src)
    gvl_names = {n for n, o in objs.items() if o["kind"] == "gvl"}
    enum_types = {n for n, o in objs.items() if o["kind"] == "dut" and re.search(r":\s*\(", o["text"])}
    itf_impl: dict[str, int] = {}
    for o in objs.values():
        for itf in re.findall(r"IMPLEMENTS\s+([\w, ]+)", o["text"]):
            for i in itf.split(","):
                itf_impl[i.strip()] = itf_impl.get(i.strip(), 0) + 1
    parents: dict[str, str] = {}
    for n, o in objs.items():
        m = re.search(r"FUNCTION_BLOCK\s+(?:\w+\s+)*?\w+\s+EXTENDS\s+(\w+)", o["text"])
        if m:
            parents[n] = m.group(1)
    methods = {m for o in objs.values() for m in re.findall(r"(?m)^\s*METHOD\s+(?:\w+\s+)*?(\w+)\s*(?::|$)", o["text"])}
    rows: list[dict[str, str]] = []

    def chain_text(name: str) -> str:
        """Текст объекта с предками: EXTENDS копирует члены, SUPER^() встраивает тело предка."""
        out = objs[name]["text"]
        seen = 0
        while name in parents and seen < 8:
            seen += 1
            name = parents[name]
            if name in objs:
                out += NL + objs[name]["text"]
        return out

    def add(rule: str, pou: str, outcome: str, why: str) -> None:
        rows.append({"rule": rule, "pou": pou, "outcome": outcome, "why": why})

    add("MS-ST-03", "", "auto", "проект: тело отдельно от объявлений")
    add("MS-EXEC-04", "", "info", "проект: есть программа")
    add("MS-TYPE-05", "", "info", "проект: есть массивы")
    for name, o in sorted(objs.items()):
        t = o["text"]
        k = o["kind"]
        used = sorted(g for g in gvl_names if re.search(rf"\b{g}\s*\.", t))
        if k == "dut":
            if used:
                add("MS-ST-08", name, "auto", f"инициализация из {', '.join(used)}")
            if re.search(r"\bUNION\b", t):
                add("MS-TYPE-03", name, "manual", "DUT — UNION")
            if re.search(r":\s*\([^)]*\)\s*\w+\s*;", t, flags=re.S):
                add("MS-TYPE-04", name, "auto", "ENUM с базовым типом")
            if name in enum_types and re.search(r"\w+\s*:=\s*-?\d", t):
                add("MS-ST-04", name, "verify", "ENUM с явными значениями")
            if re.search(r"\bLTIME\b|STRING\s*\(\s*\d+\s*\)|\bWSTRING\b", t):
                add("MS-TYPE-02", name, "review", "LTIME/STRING(n)/WSTRING в DUT")
            continue
        if k == "gvl":
            if re.search(r"VAR_GLOBAL\s+CONSTANT", t):
                add("MS-DECL-04", name, "review", "GVL CONSTANT")
            if re.search(r"\bLTIME\b|STRING\s*\(\s*\d+\s*\)", t):
                add("MS-TYPE-02", name, "review", "LTIME/STRING(n) в GVL")
            continue
        if k == "itf":
            continue
        own = t
        t = chain_text(name)
        used = sorted(g for g in gvl_names if re.search(rf"\b{g}\s*\.", t))
        is_fb = bool(re.search(r"\bFUNCTION_BLOCK\b", own))
        if is_fb and re.search(r"\bMETHOD\b|\bPROPERTY\b|\bEXTENDS\b", t):
            add("MS-LANG-06", name, "review", "ФБ с методами/свойствами/EXTENDS → режим вызова")
        elif not is_fb and any(re.search(rf"\b\w+\.{m}\s*\(", own) for m in methods):
            add("MS-LANG-06", name, "review", "вызовы методов экземпляров → режим вызова")
        for v, typ in re.findall(r"(?m)^\s*(\w+)\s*:\s*(I_\w+)\s*;", own):
            if itf_impl.get(typ, 0) >= 2:
                add("MS-LANG-06", name, "manual", f"{v} : {typ} — интерфейс реализуют {itf_impl[typ]} ФБ")
        if re.search(r"\bVAR_IN_OUT\b", t):
            add("MS-DECL-01", name, "verify", "VAR_IN_OUT")
        if re.search(r"\bLTIME\b|STRING\s*\(\s*\d+\s*\)|\bWSTRING\b|LTIME#|LT#", t):
            add("MS-TYPE-02", name, "review", "LTIME/STRING(n)")
        if re.search(r"\bVAR_TEMP\b", t):
            add("MS-ST-09", name, "info", "VAR_TEMP")
        if re.search(r"\b(?:L?REAL)_TO_(?:U?S?D?L?INT|BYTE|U?D?L?WORD)\b", t):
            add("MS-TYPE-09", name, "verify", "REAL_TO_<целое>")
        if used:
            add("MS-ST-08", name, "auto", f"обращения к {', '.join(used)}")
        if re.search(r"\bCASE\b", t) and any(re.search(rf"\b{e}\.\w+\s*[,:]", t) for e in enum_types):
            add("MS-ST-04", name, "verify", "CASE по перечислению")
        elif any(re.search(rf"\b{e}\.\w+", t) for e in enum_types):
            add("MS-ST-04", name, "verify", "литерал перечисления")
        for prop_get in re.findall(r"(?ms)^\s*PROPERTY\s+(?:\w+\s+)*?(\w+)\s*:", own):
            del prop_get
    return rows


def main() -> int:
    src = Path(sys.argv[1])
    rows = truth(src)
    data = {"source": "plc-process-lib@a321ad01f47eae4f5c29ed46d9764a2d738c2dd4",
            "method": "чек-лист docs/RULES.md, регулярные выражения по исходникам с предками (EXTENDS)", "rows": rows}  # fmt: skip
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=1) + NL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
