"""Точка входа демо (cds2ms.web): входы XML / zip раскладки / JSON раскладки, представление и детерминизм zip."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from cds2ms import web
from cds2ms.cli import main

ROOT = Path(__file__).resolve().parents[2]
CDS = ROOT / "corpus" / "udr1" / "source.cds.xml"


def test_run_xml_matches_cli(capsys: pytest.CaptureFixture[str]) -> None:
    res = json.loads(web.run("udr1.xml", CDS.read_bytes(), fix="safe"))
    assert main(["analyze", str(CDS), "--format", "json", "--fail-on", "never"]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert len(res["findings"]) == len(cli["findings"])
    assert res["report"]["totals"] == cli["totals"]
    z = base64.b64decode(res["zip"])
    assert hashlib.sha256(z).hexdigest() == res["zip_sha256"]
    assert {p["name"] for p in res["pous"]} >= {"PRG_FillSeq", "FB_DoseCtrl"}
    sfc = next(p for p in res["pous"] if p["name"] == "PRG_FillSeq")
    assert "MS-LANG-04" in sfc["original"] and sfc["fixed"]
    assert res["model"]["node"] == "PLC210" and "MANUAL" not in res["manual_steps"][:0]


def test_layout_zip_and_json() -> None:
    src = ROOT / "corpus" / "s7-chain" / "src"
    files = {p.relative_to(src).as_posix(): p.read_text(encoding="utf-8") for p in sorted(src.rglob("*.st"))}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, text in files.items():
            z.writestr(f"repo/src/{rel}", text)
    a = web.load_input("chain.zip", buf.getvalue())
    b = web.load_input("chain.json", json.dumps({"files": files}).encode("utf-8"))
    assert len(a.pous) == len(b.pous) > 10
    with pytest.raises(ValueError):
        web.load_input("empty.zip", _empty_zip())


def _empty_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("README.txt", "нет ST")
    return buf.getvalue()
