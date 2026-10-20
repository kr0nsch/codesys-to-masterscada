"""Точка входа веб-демо (Pyodide): тот же ``api.migrate``, что у CLI, и представление для страницы.

Вход — PLCopen XML (экспорт CODESYS 3.5), zip с ST-раскладкой (``src/POUs/…``) или JSON-словарь раскладки
``{путь: текст}`` (примеры). Выход — JSON: отчёт, дерево POU, тексты original/fixed, ручные шаги, план дерева
MasterSCADA (предпросмотр по плану переноса), файлы и zip в base64. Только stdlib: работает в браузере.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from typing import Any

from . import __version__, api
from .emit.bundle import make_zip
from .ir.model import Project
from .rules.registry import BY_ID

_TEXT = (".st", ".ST", ".md", ".json", ".csv", ".cs", ".xml", ".html", ".diff", ".txt", ".toml")


def load_input(name: str, data: bytes) -> Project:
    """Проект из байтов файла: PLCopen XML, zip раскладки или JSON раскладки."""
    low = name.lower()
    if low.endswith(".zip"):
        files: dict[str, str] = {}
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".st"):
                    continue
                rel = info.filename.split("src/", 1)[1] if "src/" in info.filename else info.filename
                files[rel] = z.read(info).decode("utf-8-sig")
        if not files:
            raise ValueError("в zip нет файлов .st раскладки (src/POUs/…, src/GVLs/…)")
        return api.load_files(name.rsplit(".", 1)[0], files)
    if low.endswith(".json"):
        layout = json.loads(data.decode("utf-8"))
        return api.load_files(name.rsplit(".", 1)[0], {str(k): str(v) for k, v in layout["files"].items()})
    return api.load_bytes(name, data)


def view(mig: api.Migration) -> dict[str, Any]:
    rep = json.loads(mig.files["MIGRATION_REPORT.json"])
    findings = []
    for f in rep["findings"]:
        rule = BY_ID.get(f["rule"])
        findings.append(
            {
                **f,
                "title": rule.title if rule else f["rule"],
                "confidence": "H" if f.get("documented") else "L",
            }
        )
    pous = []
    for p in rep["project"]["pous"]:
        src = mig.files.get(f"original/{p['name']}.st", b"").decode("utf-8")
        fixed = mig.files.get(f"fixed/{p['name']}.st", b"").decode("utf-8")
        pous.append({**p, "original": src, "fixed": fixed})
    zipped = make_zip(mig.files)
    return {
        "tool": {"name": "cds2ms", "version": __version__},
        "report": {k: rep[k] for k in ("source", "target", "totals", "effort", "fix", "automatability")},
        "project": {k: v for k, v in rep["project"].items() if k != "pous"},
        "pous": pous,
        "findings": findings,
        "manual_steps": mig.files["MANUAL_STEPS.md"].decode("utf-8"),
        "tasks": mig.files["tasks.md"].decode("utf-8"),
        "model": json.loads(mig.files["script/expected-tree.json"]),
        "files": sorted(mig.files),
        "zip_name": f"{api.safe_name(mig.project)}-masterscada.zip",
        "zip": base64.b64encode(zipped).decode("ascii"),
        "zip_sha256": hashlib.sha256(zipped).hexdigest(),
    }


def run(name: str, data: bytes, fix: str = "review") -> str:
    """Перенос для страницы: JSON-строка (вызывается из воркера Pyodide)."""
    mig = api.migrate(load_input(name, data), api.Options(fix=fix))
    return json.dumps(view(mig), ensure_ascii=False)
