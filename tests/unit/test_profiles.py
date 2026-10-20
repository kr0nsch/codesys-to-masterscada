"""Профили: загрузка, переопределения --set, модель трудоёмкости, правка статусов по RESULTS.csv пробника."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from cds2ms import profiles
from cds2ms.cdsfront.stdlib import common_type, is_conversion
from cds2ms.cli import main

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "src" / "cds2ms" / "profiles" / "masterscada-4d-1.3.10.toml"


def test_load_and_overrides() -> None:
    assert profiles.available() == ["codesys-3.5.17", "masterscada-4d-1.3.10"]
    p = profiles.load()
    assert p.semantics["task_period_default_ms"] == 100
    q = profiles.load(profiles.TARGET, ["semantics.task_period_default_ms=10", "semantics.real_arith=float32"])
    assert q.semantics["task_period_default_ms"] == 10 and q.semantics["real_arith"] == "float32"
    with pytest.raises((FileNotFoundError, ValueError, KeyError)):
        profiles.load("нет-такого")


def test_effort_model() -> None:
    lo, mode, hi = profiles.effort("MS-LANG-04", "review")
    assert 0 < lo <= mode <= hi
    assert profiles.effort("MS-ST-08", "auto")[1] <= profiles.effort("MS-LANG-04", "manual")[1]


RESULTS = """probe_id,construct,file,expected,observed,ide,ide_version,date,notes
P-RT-01,32767 + 1,runtime/P-RT.xml,value:?,value:-32768,MasterSCADA 4D,1.3.10,2026-11-01,
P-ST-07,retain,dialect/P-ST.xml,ok,error:Неизвестный атрибут,MasterSCADA 4D,1.3.10,2026-11-01,
P-RT-03,REAL_TO_INT,runtime/P-RT.xml,value:?,not-run,MasterSCADA 4D,1.3.10,,
"""


def test_apply_probe() -> None:
    text = PROFILE.read_text(encoding="utf-8")
    new, changed = profiles.apply_probe(text, RESULTS)
    assert changed == ["INT_OVERFLOW: supported", "RETAIN: unsupported"]
    data = tomllib.loads(new)
    assert data["features"]["INT_OVERFLOW"]["status"] == "supported"
    assert "проверено вручную 2026-11-01" in data["features"]["INT_OVERFLOW"]["verified"]
    assert data["features"]["RETAIN"]["status"] == "unsupported"
    assert profiles.apply_probe(text, RESULTS.splitlines()[0] + "\n") == (text, [])


def test_cli_apply_probe(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    csv_path = tmp_path / "RESULTS.csv"
    csv_path.write_text(RESULTS, encoding="utf-8")
    assert main(["profiles", "apply-probe", str(csv_path)]) == 0  # без --write профиль не меняется
    assert "INT_OVERFLOW" in capsys.readouterr().out


def test_stdlib_types() -> None:
    assert is_conversion("REAL_TO_INT") == ("REAL", "INT") and is_conversion("TO_INT") == ("ANY", "INT")
    assert is_conversion("FB_TO_X") is None
    assert common_type("INT", "DINT") == "DINT" and common_type(None, "REAL") == "REAL"
    assert common_type("INT", "REAL") in ("REAL", "LREAL")
