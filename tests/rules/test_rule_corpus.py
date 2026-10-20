"""Корпус правил: у каждого правила реестра — случаи pos/neg (или кейс корпуса УДР-1), URL и описание в docs/RULES.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cds2ms import api, profiles
from cds2ms.rules.registry import RULES

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def findings_for(case_dir: Path) -> list[tuple[str, str, list[str]]]:
    xml = case_dir / "input.xml"
    proj = api.load_bytes("input.xml", xml.read_bytes()) if xml.exists() else api.load_path(case_dir)
    m = api.migrate(proj, api.Options(fix="review"))
    return [(f.rule, f.outcome, f.related) for f in m.findings]


@pytest.mark.parametrize("rule", [r.id for r in RULES])
def test_rule_has_corpus_and_docs(rule: str) -> None:
    exp_path = HERE / rule / "expected.json"
    assert exp_path.exists(), f"нет корпуса для {rule}: python tools/gen_rule_corpus.py"
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    r = next(x for x in RULES if x.id == rule)
    assert r.description and r.sources and all(s.startswith("https://") for s in r.sources)
    docs = (ROOT / "docs" / "RULES.md").read_text(encoding="utf-8")
    assert f"### {rule}" in docs, f"{rule} нет в docs/RULES.md (python tools/gen_docs.py)"
    assert exp["rule"] == rule


CASE_RULES = sorted(p.parent.name for p in HERE.glob("*/expected.json") if (p.parent / "pos").exists())


@pytest.mark.parametrize("rule", CASE_RULES)
def test_rule_pos_neg(rule: str) -> None:
    exp = json.loads((HERE / rule / "expected.json").read_text(encoding="utf-8"))
    pos = findings_for(HERE / rule / "pos")
    hits = [(r, o) for r, o, rel in pos if r == rule] + [(rule, o) for r, o, rel in pos if rule in rel]
    assert hits, f"{rule}: позитивный случай без находки; есть {sorted({r for r, _, _ in pos})}"
    assert any(o == exp["pos"]["outcome"] for _, o in hits) or not exp.get("match_outcome", True), hits
    if exp.get("neg"):
        neg = findings_for(HERE / rule / "neg")
        assert not any(r == rule or rule in rel for r, _, rel in neg), f"{rule}: ложное срабатывание на negative"


@pytest.mark.parametrize(
    "rule", sorted(p.parent.name for p in HERE.glob("*/expected.json") if "corpus" in p.read_text(encoding="utf-8"))
)
def test_lowering_rules_in_corpus(rule: str, udr1_migration) -> None:  # type: ignore[no-untyped-def]
    exp = json.loads((HERE / rule / "expected.json").read_text(encoding="utf-8"))
    found = {f.rule for f in udr1_migration.findings} | {r for f in udr1_migration.findings for r in f.related}
    notes = {n.rule for x in udr1_migration.lowered.pous for n in x.notes}
    assert rule in found or rule in notes, rule
    if exp.get("pou"):
        assert any(n.rule == rule for n in udr1_migration.lowered.pou(exp["pou"]).notes) or rule in found


def test_not_emitted_rules_in_manual_steps(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    text = udr1_migration.files["MANUAL_STEPS.md"].decode("utf-8")
    for rule in ("MS-VISU-01", "MS-ALARM-01", "MS-IO-01"):
        assert rule in text


def test_effort_rows_have_reason() -> None:
    data = profiles.load_data("effort.toml")
    ids = {r.id for r in RULES}
    for rid, row in data["rules"].items():
        assert (
            rid in ids
            and row["why"]
            and len(row["minutes"]) == 3
            and row["minutes"][0] <= row["minutes"][1] <= row["minutes"][2]
        )
