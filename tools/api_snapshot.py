"""Снимок документированных членов внешней объектной модели MasterSCADA 4D 1.3.10 со страниц справки.

Читает раздел «Автоматизированная разработка проектов» (https://help.iek-digital.ru/Help-web/) по списку
страниц, разбирает таблицы «Название / Значение свойства или тип возвращаемого значения» и пишет
``csharp/api-snapshot.tsv``: страница, вид (base/property/method/enum), член, сигнатура, тип, дата.
Текст описаний не копируется — только имена, сигнатуры и типы. Сеть нужна; в CI — джоб extras.

    python tools/api_snapshot.py [--out csharp/api-snapshot.tsv] [--cache .cache/help]
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import sys
import urllib.request
from pathlib import Path

BASE = "https://help.iek-digital.ru/Help-web/"
PAGES = [
    "item", "rootitem", "systemitem", "objectsitem", "objectitem", "objectortagbase", "objectfolder", "controlleritem",
    "taskitem", "variableitem", "attributeitem", "programitem", "programstitem", "programfbditem", "programparamitem",
    "localvaritem", "taginstanceitem", "channelitem", "librariesitem", "programlditem", "programsfcitem",
]  # fmt: skip
ROOT = Path(__file__).resolve().parent.parent


def fetch(page: str, cache: Path) -> str:
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{page}.html"
    if f.exists():
        return f.read_text(encoding="utf-8")
    req = urllib.request.Request(BASE + page + ".html", headers={"User-Agent": "cds2ms-api-snapshot"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text: str = r.read().decode("utf-8", "replace")
    f.write_text(text, encoding="utf-8")
    return text


def cell_text(raw: str) -> str:
    t = re.sub(r"<br\s*/?>", " ", raw)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def parse(page: str, text: str) -> list[tuple[str, str, str, str, str]]:
    """[(вид, член, сигнатура, тип, заметка)]."""
    out: list[tuple[str, str, str, str, str]] = []
    m = re.search(r"Унаследован от (?:класса|типа)\s*(?:<[^>]+>\s*)*<a[^>]*>([^<]+)</a>", text)
    if m:
        out.append(("base", html.unescape(m.group(1)).strip(), "", "", ""))
    kind = "property"
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = [cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if not cells:
            continue
        head = cells[0]
        if len(cells) == 1 or (len(cells) >= 1 and all(not c for c in cells[1:])):
            if "Свойства" in head:
                kind = "property"
            elif "Методы" in head:
                kind = "method"
            continue
        if head in ("Название",) or len(cells) < 2:
            continue
        name_m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(\(.*?\))?", head)
        if not name_m:
            continue
        member = name_m.group(1)
        params = name_m.group(2)
        if params is not None:
            inner = params.strip("()")
            types = [p.strip().split(" ")[0] for p in inner.split(",") if p.strip()] if inner.strip() else []
            sig = f"{member}({','.join(types)})"
        else:
            sig = member
        tm = re.match(r"\s*([A-Za-z_][A-Za-z0-9_.]*(?:\s*<\s*[A-Za-z_][A-Za-z0-9_.]*\s*>)?)", cells[1])
        typ = re.sub(r"\s+", "", tm.group(1)) if tm else ""
        k = "method" if params is not None else kind
        out.append((k, member, sig, typ, ""))
        desc = cells[2] if len(cells) > 2 else ""
        em = re.search(r"\(\s*([A-Za-z]+)\s*\)\s*:\s*(.*)", desc)
        if em and "•" in em.group(2):
            names = re.findall(r"•\s*([A-Za-z_][A-Za-z0-9_]*)", em.group(2))
            if names:
                out.append(("enum", em.group(1), ",".join(names), "", ""))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "csharp" / "api-snapshot.tsv"))
    ap.add_argument("--cache", default=str(ROOT / ".cache" / "help"))
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    rows: list[str] = ["page\tkind\tmember\tsignature\ttype\tdate"]
    for page in PAGES:
        try:
            text = fetch(page, Path(a.cache))
        except OSError as exc:
            print(f"{page}: {exc}", file=sys.stderr)
            return 2
        seen = set()
        for kind, member, sig, typ, _ in parse(page, text):
            key = (kind, member, sig)
            if key in seen:
                continue
            seen.add(key)
            rows.append("\t".join([page, kind, member, sig, typ, a.date]))
    Path(a.out).write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(rows) - 1} членов → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
