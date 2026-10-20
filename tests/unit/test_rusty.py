"""RuSTy 1.0.6 ``plc --check`` над Master ST кейсов: 0 неожиданных и 0 пропавших диагностик (tools/rusty_check.py).

Без компилятора тест пропускается; в CI (job rusty) ``REQUIRE_RUSTY=1`` делает его обязательным.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import rusty_check  # noqa: E402


def test_expected_have_reasons() -> None:
    for case in ("udr1", "cds", "chain"):
        data = json.loads((ROOT / "tests" / "golden" / case / "rusty-expected.json").read_text(encoding="utf-8"))
        assert data["rusty"] == "1.0.6"
        for d in data["diagnostics"]:
            assert d["reason"], d  # у каждой ожидаемой диагностики — причина


def test_adapter() -> None:
    src = "VAR_GLOBAL\n    x AT %IX0.0 : BOOL;\n    s : ST := (a := 1,\n        b := 2);\nEND_VAR\n"
    out = rusty_check.adapt(src, "G")
    assert "    G_x AT %IX0.0 : BOOL;" in out and "    G_s : ST := (a := 1," in out and "        b := 2);" in out
    assert (
        rusty_check.adapt("TYPE U : UNION\n    a : INT;\nEND_UNION\nEND_TYPE\n")
        == "TYPE U : STRUCT\n    a : INT;\nEND_STRUCT\nEND_TYPE\n"
    )
    assert rusty_check.adapt("VAR_INOUT\nEND_VAR") == "VAR_IN_OUT\nEND_VAR"


@pytest.mark.slow
def test_rusty_clean(capsys: pytest.CaptureFixture[str]) -> None:
    plc = rusty_check.find_plc()
    if plc is None or rusty_check.find_include(plc) is None:
        if os.environ.get("REQUIRE_RUSTY") == "1":
            pytest.fail("REQUIRE_RUSTY=1, но RuSTy не найден")
        pytest.skip("RuSTy не найден (RUSTY_PLC, RUSTY_STDLIB_INCLUDE)")
    code = rusty_check.main([])
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.count("неожиданных 0, пропавших 0") == 3
