"""Кейс M12-1: plc-process-lib @ a321ad01 (MIT) — клон по SHA в .cache/. Истина «правило × POU» —
tests/golden/processlib/truth.json (закоммичена до правил); FP ≤ 5 %, FN перечислены в docs/CASE_PROCESSLIB.md.
Без сети и без клона — пропуск."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cds2ms import api
from cds2ms.cdsfront.st.lexer import Kind, tokenize

ROOT = Path(__file__).resolve().parents[2]
TRUTH = json.loads((ROOT / "tests" / "golden" / "processlib" / "truth.json").read_text(encoding="utf-8"))
KNOWN_FN = {("MS-DECL-01", "FB_DeviceBase")}  # VAR_IN_OUT метода → копия в режиме вызова, отдельной находки нет

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def lib() -> Path:
    sys.path.insert(0, str(ROOT / "tools"))
    import fetch_processlib

    p = fetch_processlib.fetch()
    if p is None:
        pytest.skip("plc-process-lib не клонирован (нет сети): python tools/fetch_processlib.py")
    return p


@pytest.fixture(scope="module")
def mig(lib: Path):  # type: ignore[no-untyped-def]
    return api.migrate(api.load_path(lib), api.Options(fix="review"))


def test_truth_committed_shape() -> None:
    assert TRUTH["source"].endswith("a321ad01f47eae4f5c29ed46d9764a2d738c2dd4")
    assert len(TRUTH["rows"]) >= 100 and all(r["why"] for r in TRUTH["rows"])


def test_false_positives_and_negatives(mig) -> None:  # type: ignore[no-untyped-def]
    truth = {(r["rule"], r["pou"]) for r in TRUTH["rows"]}
    found = {(f.rule, f.pou or "") for f in mig.findings} | {(r, f.pou or "") for f in mig.findings for r in f.related}
    fp = sorted(found - truth)
    fn = sorted(truth - found)
    assert len(fp) / max(1, len(mig.findings)) <= 0.05, fp[:10]
    assert set(fn) <= KNOWN_FN, fn


def test_inventory_counts_by_parser(lib: Path, mig) -> None:  # type: ignore[no-untyped-def]
    """Числа M12-1 — счёт токенов парсером без комментариев (grep — справочно: docs/CASE_PROCESSLIB.md)."""
    counts: dict[str, int] = {}
    for p in sorted((lib / "src").rglob("*.st")):
        for t in tokenize(p.read_text(encoding="utf-8")):
            if t.kind is Kind.IDENT:
                counts[t.text.upper()] = counts.get(t.text.upper(), 0) + 1
    assert counts["FUNCTION_BLOCK"] >= 14 and counts["INTERFACE"] >= 7
    assert counts.get("POINTER", 0) == 0 and counts.get("REFERENCE", 0) == 0
    kinds = [x.kind for x in mig.project.pous]
    assert kinds.count("functionBlock") == 14 and len(mig.project.interfaces) == 7


def test_roundtrip_all_texts(lib: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from cds2ms.cli import main

    assert main(["roundtrip", str(lib)]) == 0
    out = capsys.readouterr().out
    n, _, total = out.split(":")[1].split()[:3]
    assert n == total
