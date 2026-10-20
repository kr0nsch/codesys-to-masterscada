"""Корпус УДР-1 и цепочка S7 → CODESYS → MasterPLC: сценарии в режимах R1/R2, ожидаемые расхождения, трассы CODESYS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cds2ms.sim.simulate import load_expected, simulate

ROOT = Path(__file__).resolve().parents[2]
CASES = sorted(p.parent for p in (ROOT / "corpus").glob("*/*/scenario.csv") if p.parent.parent.name != "s7-chain")
IDS = [f"{c.parent.name}/{c.name}" for c in CASES]


def test_case_count() -> None:
    langs = {c.parent.name for c in CASES}
    assert len(CASES) == 14 and langs == {"st", "fbd", "ld", "cfc", "sfc", "il", "oop"}


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_r1_matches_reference(case: Path, udr1_migration) -> None:  # type: ignore[no-untyped-def]
    """R1 «строка = вызов»: перевод (профиль codesys) совпадает с независимой моделью, а MasterPLC — с CODESYS."""
    rep = simulate(udr1_migration, case.name, (case / "scenario.csv").read_text(encoding="utf-8"), "R1", variants=False)
    assert not rep.errors, rep.errors
    assert not rep.mismatches, rep.mismatches[:5]
    assert not rep.divergences, [d.__dict__ for d in rep.divergences[:5]]
    assert rep.rows > 0


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_r2_divergences_explained(case: Path, udr1_migration) -> None:  # type: ignore[no-untyped-def]
    """R2 «фиксированный цикл»: CODESYS 10 мс против MasterPLC 100 мс; каждое расхождение — из expected-divergences.toml."""
    exp_path = case / "expected-divergences.toml"
    exp = load_expected(exp_path.read_text(encoding="utf-8")) if exp_path.exists() else []
    rep = simulate(udr1_migration, case.name, (case / "scenario.csv").read_text(encoding="utf-8"), "R2", expected=exp,
                   variants=False)  # fmt: skip
    assert not rep.errors, rep.errors
    unexplained = [d for d in rep.divergences if not d.rule]
    assert not unexplained, [d.__dict__ for d in unexplained[:5]]
    assert all(d.rule == "MS-EXEC-01" for d in rep.divergences)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_r2_same_period_no_divergence(case: Path, udr1_migration) -> None:  # type: ignore[no-untyped-def]
    """Тот же период задачи (10 мс) на MasterPLC — расхождений нет: в R2 они только от периода (MS-EXEC-01)."""
    rep = simulate(udr1_migration, case.name, (case / "scenario.csv").read_text(encoding="utf-8"), "R2",
                   period_masterplc=10, variants=False)  # fmt: skip
    assert not rep.errors and not rep.divergences, [d.__dict__ for d in rep.divergences[:5]]


def _real_close(m: dict[str, str]) -> bool:
    """REAL в трассе CODESYS напечатан с 7 значащими цифрами: разница в последнем знаке — не расхождение."""
    try:
        a, b = float(m["expected"]), float(m["codesys"])
    except ValueError:
        return False
    return abs(a - b) <= 1e-6 * max(1.0, abs(a))


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_oracle_replay(case: Path, udr1_migration) -> None:  # type: ignore[no-untyped-def]
    """Трасса стенда CODESYS Control Win (oracle-codesys.csv): по тем же входам и t_ms циклов модель перевода
    (профиль codesys) даёт те же выходы, что рантайм. Источник трассы должен совпадать с корпусом (SHA-256)."""
    oracle = case / "oracle-codesys.csv"
    if not oracle.exists():
        pytest.skip("трасса CODESYS не снята (tools/codesys/corpus.py, docs/ORACLES.md)")
    import hashlib

    meta = json.loads((case / "oracle-codesys.json").read_text(encoding="utf-8"))
    assert meta["format"] == "oracle-codesys/1" and meta["codesys"] == "3.5.17.30" and meta["pou"] == case.name
    src = (ROOT / "corpus" / "udr1" / "source.cds.xml").read_bytes()
    assert hashlib.sha256(src).hexdigest() == meta["source_sha256"], "трасса снята с другого source.cds.xml"
    rep = simulate(udr1_migration, case.name, oracle.read_text(encoding="utf-8"), "R1", variants=False)
    assert not rep.errors, rep.errors
    real = [m for m in rep.mismatches if not _real_close(m)]
    assert not real, real[:6]


CDS_CASES = [c for c in CASES if c.parent.name != "il"]  # IL в 3.5.17.30 без «Enable IL» не импортируется


@pytest.mark.parametrize("case", CDS_CASES, ids=[f"{c.parent.name}/{c.name}" for c in CDS_CASES])
def test_cds_export_r1_and_oracle(case: Path, cds_migration) -> None:  # type: ignore[no-untyped-def]
    """Вход — экспорт самого CODESYS (source.cds.xml, форма проводов CFC и LD — как в среде): сценарий R1 и трасса
    Control Win совпадают с переводом."""
    rep = simulate(cds_migration, case.name, (case / "scenario.csv").read_text(encoding="utf-8"), "R1", variants=False)
    assert not rep.errors and not rep.mismatches and not rep.divergences, (rep.errors, rep.mismatches[:3])
    oracle = case / "oracle-codesys.csv"
    if oracle.exists():
        rep2 = simulate(cds_migration, case.name, oracle.read_text(encoding="utf-8"), "R1", variants=False)
        assert not rep2.errors and not [m for m in rep2.mismatches if not _real_close(m)], rep2.mismatches[:3]


def test_cds_export_contents(cds_migration) -> None:  # type: ignore[no-untyped-def]
    p = cds_migration.project
    names = {x.name for x in p.pous}
    assert {"PRG_FillSeq", "FB_DoseCtrl", "PRG_PumpInterlock", "FB_DosingPump"} <= names
    assert not names & {"FB_PulseCount", "F_ScaleIL", "PRG_IlHost"}  # IL не создан (N)
    assert [t.name for t in p.tasks] == ["TaskFast", "TaskSlow", "TaskAlarm"]
    assert {"#Standard", "#IecSfc"} <= {lib.name for lib in p.libraries}


CHAIN = sorted((ROOT / "corpus" / "s7-chain" / "scenarios").glob("*.csv"))


@pytest.mark.parametrize("csv_path", CHAIN, ids=[p.stem for p in CHAIN])
def test_s7_chain(csv_path: Path, chain_migration) -> None:  # type: ignore[no-untyped-def]
    """Цепочка S7 → s7conv → CODESYS → cds2ms → MasterPLC: сценарии s7-to-codesys (R1) без расхождений."""
    rep = simulate(chain_migration, csv_path.stem, csv_path.read_text(encoding="utf-8"), "R1", variants=False)
    assert not rep.errors, rep.errors
    assert not rep.mismatches, rep.mismatches[:5]
    assert not rep.divergences, [d.__dict__ for d in rep.divergences[:5]]


def test_s7_chain_size(chain_migration) -> None:  # type: ignore[no-untyped-def]
    assert len(CHAIN) == 6
    rows = sum(len((p.read_text(encoding="utf-8")).splitlines()) - 1 for p in CHAIN)
    assert rows >= 250
    lic = (ROOT / "corpus" / "s7-chain" / "LICENSE").read_text(encoding="utf-8")
    assert "MIT" in lic
