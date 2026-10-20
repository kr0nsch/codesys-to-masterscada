"""Сборка демо для GitHub Pages: статика web/, Pyodide 314.0.7 (npm-архив по SHA-512), пакет cds2ms zip-архивом и
примеры с предрасчётом CLI (страница показывает его сразу, затем пересчитывает в браузере и сверяет SHA-256 zip).

    python tools/build_site.py [--out site] [--no-processlib]

Pyodide берётся из npm-реестра (registry.npmjs.org, тот же архив, что у `npm i pyodide@314.0.7`) в .cache/ и
проверяется по SHA-512 из метаданных пакета; на страницу копируется только ядро (ни одного чужого домена).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from behaviour import udr1_behaviour  # noqa: E402

from cds2ms import api, web  # noqa: E402

PYODIDE_VERSION = "314.0.7"
PYODIDE_URL = f"https://registry.npmjs.org/pyodide/-/pyodide-{PYODIDE_VERSION}.tgz"
PYODIDE_SHA512 = "0YvXxEhfEdpLfb/XkM2BFAeMROq0iMUX2bzzH9pOttyMcWkwq+HbE5uyuGD82LN7y2q+SNvi/6V5JEsOlD2R1A=="
PYODIDE_FILES = ("pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")


def pyodide_tgz() -> Path:
    cache = ROOT / ".cache" / f"pyodide-{PYODIDE_VERSION}.tgz"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(PYODIDE_URL, timeout=120) as r:  # фиксированный https-адрес npm
            data = r.read()
        cache.write_bytes(data)
    data = cache.read_bytes()
    got = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != PYODIDE_SHA512:
        cache.unlink()
        raise SystemExit(f"Pyodide {PYODIDE_VERSION}: SHA-512 не совпал ({got})")
    return cache


def copy_pyodide(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(pyodide_tgz(), "r:gz") as tf:
        for name in PYODIDE_FILES:
            member = tf.getmember(f"package/{name}")
            f = tf.extractfile(member)
            assert f is not None
            (dest / name).write_bytes(f.read())
    (dest / "LICENSE.txt").write_text(
        f"Pyodide {PYODIDE_VERSION} — файлы npm-пакета pyodide@{PYODIDE_VERSION} без изменений.\n"
        "Лицензия: Mozilla Public License 2.0 (поле license в package.json пакета), полный текст:\n"
        "https://www.mozilla.org/en-US/MPL/2.0/ ; исходный код: https://github.com/pyodide/pyodide\n"
        "python_stdlib.zip — стандартная библиотека CPython, лицензия PSF: https://docs.python.org/3/license.html\n",
        encoding="utf-8",
        newline="\n",
    )


def package_zip(dest: Path) -> None:
    src = ROOT / "src"
    files = sorted(p for p in (src / "cds2ms").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_STORED) as zf:
        for p in files:
            info = zipfile.ZipInfo(p.relative_to(src).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes())


def layout_json(root: Path, title: str, source: str) -> bytes:
    files = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.st"))}
    return json.dumps({"title": title, "source": source, "files": files}, ensure_ascii=False, indent=0).encode("utf-8")


def example(
    out: Path, eid: str, title: str, fname: str, data: bytes, note: str, behaviour: bool = False
) -> dict[str, object]:
    d = out / "examples" / eid
    d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_bytes(data)
    mig = api.migrate(web.load_input(fname, data), api.Options(fix="safe"))
    view = web.view(mig)
    zipped = base64.b64decode(view.pop("zip"))  # zip — отдельным файлом рядом, в JSON только имя и SHA-256
    (d / str(view["zip_name"])).write_bytes(zipped)
    view["zip_url"] = f"examples/{eid}/{view['zip_name']}"
    (d / "result.json").write_text(json.dumps(view, ensure_ascii=False), encoding="utf-8", newline="\n")
    if behaviour:
        (d / "behaviour.json").write_text(
            json.dumps(udr1_behaviour(mig), ensure_ascii=False), encoding="utf-8", newline="\n"
        )
    return {"id": eid, "title": title, "file": fname, "note": note, "behaviour": behaviour}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--no-processlib", action="store_true", help="без примера plc-process-lib (нет сети)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in ("index.html", "app.js", "worker.js", "styles.css"):
        shutil.copyfile(ROOT / "web" / name, out / name)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    copy_pyodide(out / "pyodide")
    package_zip(out / "cds2ms.zip")
    idx = [
        example(out, "udr1", "УДР-1 (экспорт CODESYS)", "udr1.xml", (ROOT / "corpus" / "udr1" / "source.cds.xml").read_bytes(),
                "корпус: ST, FBD, LD, CFC, SFC, ООП — экспорт CODESYS 3.5.17.30 после import_xml и сборки", behaviour=True),
        example(out, "s7-chain", "Цепочка S7 → CODESYS", "s7-chain.json",
                layout_json(ROOT / "corpus" / "s7-chain" / "src", "s7-chain", "kr0nsch/s7-to-codesys@2285760 (MIT)"),
                "выход s7-to-codesys @2285760 (MIT): 66 файлов ST-раскладки"),
    ]  # fmt: skip
    if not a.no_processlib:
        import fetch_processlib

        lib = fetch_processlib.fetch()
        if lib is not None:
            idx.append(
                example(
                    out,
                    "processlib",
                    "plc-process-lib",
                    "plc-process-lib.json",
                    layout_json(lib / "src", "plc-process-lib", "kr0nsch/plc-process-lib@a321ad01 (MIT)"),
                    "библиотека ФБ с ООП (MIT): методы, свойства, интерфейсы, EXTENDS",
                )
            )
        else:
            print("plc-process-lib недоступен (нет сети) — пример пропущен")
    (out / "examples" / "index.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"site: {len(idx)} примера, {size / 1e6:.1f} МБ → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
