"""CLI: подкоманды, форматы, коды выхода 0/1/2."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from cds2ms.cli import main

ROOT = Path(__file__).resolve().parents[2]
SRC = str(ROOT / "corpus" / "udr1" / "source.handmade.xml")
CDS = str(ROOT / "corpus" / "udr1" / "source.cds.xml")


def test_inventory(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inventory", SRC, "--format", "json"]) == 0
    inv = json.loads(capsys.readouterr().out)
    langs = inv["languages"]
    assert {k: langs[k] for k in ("FBD", "LD", "CFC", "SFC", "IL")} == {"FBD": 2, "LD": 2, "CFC": 2, "SFC": 2, "IL": 2}
    assert main(["inventory", CDS]) == 0
    assert "SFC 2" in capsys.readouterr().out


def test_analyze_fail_on(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", SRC, "--format", "json", "--fail-on", "never"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["tool"]["name"] == "cds2ms" and rep["findings"]
    assert main(["analyze", SRC, "--fail-on", "manual"]) == 1  # IL и SFC-флаги дают manual
    capsys.readouterr()


def test_input_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", str(tmp_path / "нет.xml")]) == 2
    bad = tmp_path / "bad.xml"
    bad.write_text("<project><oops>", encoding="utf-8")
    assert main(["analyze", str(bad)]) == 2
    assert main(["explain", "MS-NOPE-99"]) == 2
    capsys.readouterr()


def test_migrate_zip_deterministic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    z1, z2 = tmp_path / "a.zip", tmp_path / "b.zip"
    assert main(["migrate", CDS, "--out", str(tmp_path / "a"), "--zip", str(z1), "--fail-on", "never"]) == 0
    assert main(["migrate", CDS, "--out", str(tmp_path / "b"), "--zip", str(z2), "--fail-on", "never", "--diff"]) == 0
    out = capsys.readouterr().out
    assert "--- a/" in out  # --diff печатает changes.diff
    assert hashlib.sha256(z1.read_bytes()).digest() == hashlib.sha256(z2.read_bytes()).digest()
    with zipfile.ZipFile(z1) as z:
        names = z.namelist()
    assert "import/udr1.plcopen.xml" in names and "MANUAL_STEPS.md" in names
    assert (tmp_path / "a" / "script" / "DoAction.body.cs").exists()


def test_simulate_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    case = ROOT / "corpus" / "st" / "PRG_TonQuant"
    args = ["simulate", SRC, "--pou", "PRG_TonQuant", "--scenario", str(case / "scenario.csv"), "--regime", "R2"]
    assert main([*args, "--expected", str(case / "expected-divergences.toml")]) == 0
    assert main(args) == 1  # без файла ожиданий расхождения R2 не объяснены
    out = tmp_path / "trace"
    assert (
        main([*args, "--expected", str(case / "expected-divergences.toml"), "--out", str(out), "--format", "json"]) == 0
    )
    capsys.readouterr()
    diff = json.loads((out / "diff.json").read_text(encoding="utf-8"))
    assert diff["case"] == "PRG_TonQuant" and all(r["rule"] == "MS-EXEC-01" for r in diff["rows"])


def test_explain_profiles_roundtrip_probe(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["explain", "MS-ST-08"]) == 0
    assert "https://help.iek-digital.ru/" in capsys.readouterr().out
    assert main(["profiles", "list"]) == 0
    assert "masterscada-4d-1.3.10" in capsys.readouterr().out
    assert main(["profiles", "show", "masterscada-4d-1.3.10"]) == 0
    capsys.readouterr()
    assert main(["roundtrip", SRC]) == 0
    assert "байт в байт" in capsys.readouterr().out
    assert main(["probe", "--out", str(tmp_path / "probe")]) == 0
    capsys.readouterr()
    head = (tmp_path / "probe" / "RESULTS.csv").read_text(encoding="utf-8").splitlines()[0]
    assert head == "probe_id,construct,file,expected,observed,ide,ide_version,date,notes"
