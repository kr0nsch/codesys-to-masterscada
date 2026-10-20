"""Ряды «Поведения» для демо и графиков: сценарий корпуса в режиме R2 — CODESYS (модель, 10 мс), MasterPLC (модель,
100 мс) и трасса CODESYS Control Win (oracle-codesys.csv), если снята; расхождения с правилами из
expected-divergences.toml."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cds2ms import api, profiles  # noqa: E402
from cds2ms.sim.runner import parse_value, read_csv, run, scenarios  # noqa: E402
from cds2ms.sim.semantics import codesys, masterplc  # noqa: E402
from cds2ms.sim.simulate import load_expected, machine_codesys, machine_masterplc, renames_for, simulate  # noqa: E402

LANG_DIR = {"st": "ST", "fbd": "FBD", "ld": "LD", "cfc": "CFC", "sfc": "SFC", "il": "IL", "oop": "ST (ООП)"}


def _num(v: Any) -> float:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def case_series(mig: api.Migration, case_dir: Path, max_signals: int = 3) -> dict[str, Any]:
    pou = case_dir.name
    csv_text = (case_dir / "scenario.csv").read_text(encoding="utf-8")
    rows = read_csv(csv_text)
    sc = scenarios(rows)[0]
    outs = list(sc[0].outputs.items())[:max_signals]
    signals = [{"name": name, "type": typ} for name, (typ, _v) in outs]
    prof = profiles.load(profiles.TARGET)
    sem_m = masterplc(prof.semantics, prof.variants)
    rc = run(machine_codesys(mig, codesys(10)), pou, sc, "R2", 10)
    rm = run(machine_masterplc(mig, sem_m), pou, sc, "R2", sem_m.period_ms, None, renames_for(mig, pou))
    series: dict[str, dict[str, list[list[float]]]] = {"codesys": {}, "masterplc": {}}
    for label, res in (("codesys", rc), ("masterplc", rm)):
        for s in signals:
            pts = [[float(r.t_ms), _num(v[s["name"]])] for r, v in zip(sc, res.values, strict=False) if v is not None]
            series[label][s["name"]] = pts
    oracle = None
    opath = case_dir / "oracle-codesys.csv"
    if opath.exists():
        orows = [r for r in read_csv(opath.read_text(encoding="utf-8")) if r.scenario == sc[0].scenario]
        oracle = {
            s["name"]: [
                [float(r.t_ms), _num(parse_value(*r.outputs[s["name"]]))] for r in orows if s["name"] in r.outputs
            ]
            for s in signals
        }
    exp_path = case_dir / "expected-divergences.toml"
    exp = load_expected(exp_path.read_text(encoding="utf-8")) if exp_path.exists() else []
    rep = simulate(mig, pou, csv_text, "R2", expected=exp, variants=False)
    divs = [
        {"t_ms": d.t_ms, "signal": d.signal, "codesys": d.codesys, "masterplc": d.masterplc, "rule": d.rule,
         "explanation": d.explanation}
        for d in rep.divergences if d.scenario == sc[0].scenario
    ]  # fmt: skip
    lang = LANG_DIR.get(case_dir.parent.name, case_dir.parent.name.upper())
    if oracle is not None:
        verified = f"сверено с трассой CODESYS Control Win 3.5.17.30 ({len(next(iter(oracle.values()), []))} циклов)"
    elif case_dir.parent.name == "il":
        verified = "сверено с собственным вычислителем (IL в CODESYS 3.5.17.30 без «Enable IL» не импортируется)"
    else:
        verified = "сверено с независимой моделью сценария"
    return {
        "pou": pou, "language": lang, "verified": verified, "scenario": sc[0].scenario, "signals": signals,
        "codesys": series["codesys"], "masterplc": series["masterplc"], "oracle": oracle, "divergences": divs,
    }  # fmt: skip


def udr1_behaviour(mig: api.Migration) -> dict[str, Any]:
    cases = sorted(p.parent for p in (ROOT / "corpus").glob("*/*/scenario.csv") if p.parent.parent.name != "s7-chain")
    have = {p.name.lower() for p in mig.project.pous}
    handmade = None
    out = []
    for c in cases:
        if c.name.lower() in have:
            out.append(case_series(mig, c))
            continue
        # IL в экспорте CODESYS нет (без «Enable IL» не импортируется) — те же POU из рукописного TC6 корпуса
        if handmade is None:
            handmade = api.migrate(
                api.load_path(ROOT / "corpus" / "udr1" / "source.handmade.xml"), api.Options(fix="safe")
            )
        out.append(case_series(handmade, c))
    verified: dict[str, str] = {}
    for c in out:
        lang = c["language"].split()[0]
        verified.setdefault(
            lang, "трасса CODESYS Control Win" if c["oracle"] is not None else c["verified"].split(" (")[0]
        )
    return {
        "note": "Режим R2 «фиксированный цикл»: CODESYS — задача 10 мс, MasterPLC — период задачи по умолчанию 100 мс "
        "(профиль masterscada-4d-1.3.10). Зелёная широкая линия — трасса стенда в CODESYS Control Win 3.5.17.30.",
        "verified": verified,
        "cases": out,
    }
