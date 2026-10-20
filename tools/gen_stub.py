"""Макет внешней объектной модели MasterSCADA 4D из снимка ``csharp/api-snapshot.tsv``.

Макет строится только из снимка: у каждого члена — адрес страницы справки в комментарии; класс, на который
ссылается справка, но страницы в снимке нет, помечен ``[L]``. Члены — «модель-запись»: Add* создают дочерние
элементы, свойства пишутся в словарь, Find* ищут по имени — дерево потом выгружает FakeRunner в tree.json.
C# 5 (без ``?.``, интерполяции и инициализаторов авто-свойств).

    python tools/gen_stub.py            # пишет csharp/Stub/Api.g.cs
    python tools/gen_stub.py --check    # код 1, если файл устарел
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TSV = ROOT / "csharp" / "api-snapshot.tsv"
OUT = ROOT / "csharp" / "Stub" / "Api.g.cs"
BASE = "https://help.iek-digital.ru/Help-web/"
PAGE_CLASS = {
    "item": "Item", "rootitem": "RootItem", "systemitem": "SystemItem", "objectsitem": "ObjectsItem",
    "objectitem": "ObjectItem", "objectortagbase": "ObjectOrTagBase", "objectfolder": "ObjectFolder",
    "controlleritem": "ControllerItem", "taskitem": "TaskItem", "variableitem": "VariableItem",
    "attributeitem": "AttributeItem", "programitem": "ProgramItem", "programstitem": "ProgramSTItem",
    "programfbditem": "ProgramFBDItem", "programparamitem": "ProgramParamItem", "localvaritem": "LocalVarItem",
    "taginstanceitem": "TagInstanceItem", "channelitem": "ChannelItem", "librariesitem": "LibrariesItem",
    "programlditem": "ProgramLDItem", "programsfcitem": "ProgramSFCItem",
}  # fmt: skip
GUESSED_BASES = {"ObjectOrTagItem": "ObjectOrTagBase", "ObjectOrTagInstanceItem": "ObjectOrTagBase"}
INTERNAL = ("ItemInstance", "ItemType", "PropertyType", "LinkType")
PRIMITIVE = {"string": "string", "int": "int", "bool": "bool", "object": "object", "long": "long", "double": "double"}


def load() -> list[dict[str, str]]:
    with TSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def cs_type(t: str, enums: set[str]) -> str:
    t = t.strip().rstrip("?")
    m = re.match(r"IEnumerable<(\w+)>", t)
    if m:
        return f"IEnumerable<{m.group(1)}>"
    return PRIMITIVE.get(t, t) if t else "void"


def generate() -> str:
    rows = load()
    enums: dict[str, list[str]] = {}
    bases: dict[str, str] = {}
    members: dict[str, list[dict[str, str]]] = {}
    referenced: set[str] = set()
    for r in rows:
        cls = PAGE_CLASS.get(r["page"])
        if cls is None:
            continue
        if r["kind"] == "enum":
            enums.setdefault(r["member"], r["signature"].split(","))
        elif r["kind"] == "base":
            bases[cls] = r["member"]
        else:
            blob = r["type"] + " " + (r["signature"].split("(", 1)[-1] if r["kind"] == "method" else "")
            if any(x in blob for x in INTERNAL) or r["member"] in INTERNAL:
                continue  # внутренняя модель MasterSCADA 4D в скриптах запрещена (HW:auto_develop_project)
            members.setdefault(cls, []).append(r)
            for t in re.findall(r"\b([A-Z]\w+)\b", blob):
                referenced.add(t)
    for cls in PAGE_CLASS.values():
        members.setdefault(cls, [])
    known = set(PAGE_CLASS.values()) | set(enums) | {"IEnumerable", "Item"}
    referenced |= set(bases.values())
    extra = sorted(t for t in referenced if t not in known and t not in PRIMITIVE and t not in ("String",))
    out: list[str] = [
        "// Макет внешней объектной модели MasterSCADA 4D 1.3.10 — построен tools/gen_stub.py из csharp/api-snapshot.tsv.",
        "// Не править вручную. Члены — по страницам справки https://help.iek-digital.ru/Help-web/ (адрес у члена).",
        "// [L] — класс, на который ссылается справка, без своей страницы в снимке: пустой наследник Item.",
        "using System;",
        "using System.Collections.Generic;",
        "",
        "namespace MasterSCADA.Scripts.Model",
        "{",
    ]
    for name in sorted(enums):
        out.append(f"    // {BASE} (возможные значения из таблицы свойства)")
        out.append(f"    public enum {name} {{ {', '.join(enums[name])} }}")
        out.append("")
    for name in extra:
        base = GUESSED_BASES.get(name, bases.get(name, "Item"))
        why = (
            " (наследование выведено из имени: AddProgramST и др. — у ObjectOrTagBase)" if name in GUESSED_BASES else ""
        )
        out.append(f"    // [L] страницы в снимке нет{why}")
        out.append(f"    public class {name} : {base if base != name else 'Item'} {{ }}")
        out.append("")
    # порядок: Item первым, затем по алфавиту
    order = ["Item", *sorted(c for c in members if c != "Item")]
    inherited: dict[str, set[str]] = {}

    def chain_sigs(cls: str) -> set[str]:
        sigs: set[str] = set()
        b = bases.get(cls)
        seen = 0
        while b and seen < 10:
            seen += 1
            for r in members.get(b, []):
                sigs.add(r["signature"])
            b = bases.get(b)
        return sigs

    for cls in order:
        base = bases.get(cls, "Item") if cls != "Item" else None
        if base is not None and base not in members and base not in extra:
            base = "Item"
        page = next((p for p, c in PAGE_CLASS.items() if c == cls), "")
        decl = f"    public partial class {cls}" + (f" : {base}" if base else "")
        out.append(f"    // {BASE}{page}.html")
        out.append(decl)
        out.append("    {")
        inh = chain_sigs(cls)
        inherited[cls] = inh
        emitted: set[str] = set()
        for r in sorted(members[cls], key=lambda x: (x["kind"], x["signature"])):
            sig = r["signature"]
            if sig in emitted:
                continue
            emitted.add(sig)
            new = "new " if sig in inh else ""
            url = f"{BASE}{r['page']}.html"
            typ = cs_type(r["type"], set(enums))
            member = r["member"]
            if r["kind"] == "property":
                if not r["type"]:
                    out.append("        // [L] тип свойства на странице не указан — object")
                    typ = "object"
                if cls == "Item" and member in (
                    "Name",
                    "Parent",
                    "Childs",
                    "FullName",
                    "Id",
                    "TypeName",
                    "OrderedChilds",
                ):
                    continue  # реализованы в Item.Core.cs
                m = re.match(r"IEnumerable<(\w+)>", typ)
                if m:
                    out.append(
                        f"        public {new}{typ} {member} {{ get {{ return ChildrenOf<{m.group(1)}>(); }} }} // {url}"
                    )
                else:
                    out.append(
                        f'        public {new}{typ} {member} {{ get {{ return GetProp<{typ}>("{member}"); }} set {{ SetProp("{member}", value); }} }} // {url}'
                    )
                continue
            params = sig[len(member) + 1 : -1]
            ptypes = [p for p in params.split(",") if p] if params else []
            if cls == "Item" and member in (
                "FindChildByName",
                "GetChildByName",
                "FindChildByNamePath",
                "GetChildByNamePath",
                "Delete",
            ):
                continue
            plist = ", ".join(f"{cs_type(p, set(enums))} a{i}" + (" = null" if len(ptypes) == 1 and (p.endswith("?") or (p == "string" and member.startswith("Add"))) else "")
                              for i, p in enumerate(ptypes))  # fmt: skip
            ret = typ if r["type"] else "void"
            if member.startswith("Add") and ret not in ("void", "bool") and ptypes[:1] in (["string"], ["string?"]):
                body = f'return AddChild<{ret}>("{member}", a0);'
            elif member.startswith("Add") and ret == "void":
                body = f'RecordLink("{member}", a0);'
            elif member.startswith("TryAddLink"):
                body = 'RecordLink("TryAddLink", a0);'
            elif member.startswith("Find") and ptypes[:1] == ["string"] and ret not in ("void", "bool"):
                body = f"return FindDeep<{ret}>(a0);"
            elif member.startswith("Get") and ptypes[:1] == ["string"] and ret not in ("void", "bool"):
                body = f'{ret} x = FindDeep<{ret}>(a0); if (x == null) throw new InvalidOperationException("не найден: " + a0); return x;'
            elif member.startswith(("Reset", "Delete")) and not ptypes:
                prop = member[5:] if member.startswith("Reset") else member[6:]
                body = f'ResetProp("{prop}");' + (" return true;" if ret == "bool" else "")
            elif member == "ChangeType":
                body = 'SetProp("ValueType", a0);'
            else:
                body = f'Unsupported("{member}");' + ("" if ret == "void" else f" return default({ret});")
            if ret == "bool" and "return" not in body:
                body += " return true;"
            out.append(f"        public {new}{ret} {member}({plist}) {{ {body} }} // {url}")
        out.append("    }")
        out.append("")
    out.append("}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = generate()
    if a.check:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != text:
            print("csharp/Stub/Api.g.cs устарел: python tools/gen_stub.py", file=sys.stderr)
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"{OUT.relative_to(ROOT)}: {text.count(chr(10))} строк")
    return 0


if __name__ == "__main__":
    sys.exit(main())
