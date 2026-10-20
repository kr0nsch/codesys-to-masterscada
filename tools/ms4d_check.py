"""Снимок API (csharp/api-snapshot.tsv, со страниц справки) против XML-документации, которая поставляется с
MasterSCADA 4D 1.3.10 (bin/MasterSCADA.Scripts.Model.xml): какие члены из справки есть в поставке и чего нет.

    python tools/ms4d_check.py [--ms4d-bin DIR]

Только чтение документации из установки (не декомпиляция). Код 0 — все члены снимка, которыми пользуется
сгенерированный скрипт, есть в поставке; 1 — нет; 3 — MasterSCADA 4D не установлена (пропуск).
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MS4D_BIN = Path(os.environ.get("MS4D_BIN", r"C:\Program Files\MPSSoft\MasterSCADA 4D 1.3\bin"))
# члены, которыми пользуется emit/csharp.py (скрипт DoAction / BuildProject)
USED = ("FindController", "AddTask", "Period", "ResetTranslatorType", "ResetPriority", "AddProgramST", "Text",
        "ExecutionMethod", "Childs", "Name")  # fmt: skip
# метод среды скриптов редактора (примеры справки), не объектной модели: в MasterSCADA.Scripts.Model.xml его нет
HOST = ("WriteConsole",)


def shipped_members(xml_path: Path) -> dict[str, set[str]]:
    """{имя члена: {типы}} из <member name="P:NS.Type.Member"> и "M:NS.Type.Member(...)"."""
    out: dict[str, set[str]] = {}
    for m in ET.parse(xml_path).getroot().iter("member"):
        name = m.get("name", "")
        mm = re.match(r"^([PMFE]):[\w.]+\.(\w+)\.(\w+)", name)
        if mm:
            out.setdefault(mm.group(3), set()).add(mm.group(2))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ms4d-bin", default=str(MS4D_BIN))
    a = ap.parse_args(argv)
    xml_path = Path(a.ms4d_bin) / "MasterSCADA.Scripts.Model.xml"
    if not xml_path.exists():
        print(f"нет {xml_path} — MasterSCADA 4D 1.3.10 не установлена, пропуск")
        return 3
    shipped = shipped_members(xml_path)
    with (ROOT / "csharp" / "api-snapshot.tsv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t") if r["kind"] in ("property", "method")]
    names = sorted({r["member"] for r in rows})
    have = [n for n in names if n in shipped]
    missing = [n for n in names if n not in shipped]
    print(
        f"снимок: {len(names)} имён членов (свойства и методы); в XML-документации поставки: {len(have)}, нет: {len(missing)}"
    )
    if missing:
        print(
            "  нет в поставке (или не документированы): "
            + ", ".join(missing[:40])
            + (" …" if len(missing) > 40 else "")
        )
    used_missing = [n for n in USED if n not in shipped]
    print(
        f"члены модели, которыми пользуется скрипт: {len(USED)}, нет в документации поставки: {used_missing or 'нет'}"
    )
    print(f"метод среды скриптов (из примеров справки, вне документации модели): {', '.join(HOST)}")
    return 0 if not used_missing else 1


if __name__ == "__main__":
    sys.exit(main())
