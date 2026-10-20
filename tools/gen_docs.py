"""docs/RULES.md из реестра правил (src/cds2ms/rules/registry.py) и модели трудоёмкости.

python tools/gen_docs.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from cds2ms import profiles  # noqa: E402
from cds2ms.rules.registry import RULES  # noqa: E402

RU = {
    "auto": "авто",
    "review": "сверить",
    "verify": "проверить",
    "manual": "вручную",
    "impossible": "невозможно",
    "info": "сведения",
}
FIX = {
    "none": "нет",
    "auto": "`--fix safe`",
    "review": "`--fix review`",
    "verify": "`--fix all` + `--rewrite-undocumented`",
}


def render() -> str:
    out = [
        "# Правила MS-*",
        "",
        "Каждое правило — находка с исходом из словаря семейства (`auto | review | verify | manual | impossible | info`),",
        "источник в справке MasterSCADA 4D 1.3.10 или CODESYS и корпус `tests/rules/<ID>/` (pos/neg). Нумерация совпадает с",
        "конспектом исследования там, где ID оттуда. «Описано» — есть ли поведение цели в справке 1.3.10; «нет» означает",
        "исход не легче verify или ручной шаг. Минуты — модель трудоёмкости (`data/effort.toml`), не замер.",
        "Файл строится `tools/gen_docs.py` из `src/cds2ms/rules/registry.py`.",
        "",
        "| ID | Что | Исход | Описано | Правка | Минуты (min/mode/max) |",
        "|---|---|---|---|---|---|",
    ]
    for r in RULES:
        mins = profiles.effort(r.id, r.outcome)
        out.append(f"| [{r.id}](#{r.id.lower()}) | {r.title} | {RU[r.outcome]} | {'да' if r.documented else 'нет'} | "
                   f"{FIX[r.fix]} | {mins[0]:g}/{mins[1]:g}/{mins[2]:g} |")  # fmt: skip
    out.append("")
    for r in RULES:
        out += [f"### {r.id}", "", f"**{r.title}.** {r.description}", "", f"Исход по умолчанию — {RU[r.outcome]}; правка — {FIX[r.fix]}.",
                f"Корпус: `tests/rules/{r.id}/`.", "", "Источники:", ""]  # fmt: skip
        out += [f"- {s}" for s in r.sources]
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    path = ROOT / "docs" / "RULES.md"
    text = render()
    if a.check:
        ok = path.exists() and path.read_text(encoding="utf-8") == text
        print("docs/RULES.md " + ("актуален" if ok else "устарел: python tools/gen_docs.py"))
        return 0 if ok else 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"docs/RULES.md: {len(RULES)} правил")
    return 0


if __name__ == "__main__":
    sys.exit(main())
