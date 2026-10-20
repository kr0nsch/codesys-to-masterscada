"""``cds2ms simulate``: original/ в профиле ``codesys`` против fixed/ в профиле ``masterplc``.

Каждое расхождение должно быть записано в ``expected-divergences.toml`` (сигнал, правило, объяснение),
иначе оно «необъяснённое» и тест падает. Для статусов ``unknown`` профиля прогон повторяется с каждым
вариантом (один фактор за раз): расхождение только в варианте — исход verify.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import Any

from .. import profiles
from ..api import Migration
from .interp import Machine
from .runner import Row, read_csv, run, same, scenarios, show
from .semantics import Semantics, SimError, all_variants, codesys, masterplc


@dataclass
class Divergence:
    scenario: str
    row: int
    cycle: int
    t_ms: int
    signal: str
    codesys: str
    masterplc: str
    rule: str = ""
    explanation: str = ""
    variant: str = ""


@dataclass
class SimReport:
    case: str
    regime: str
    rows: int = 0
    collapsed: int = 0
    scenarios: int = 0
    mismatches: list[dict[str, Any]] = field(default_factory=list)  # codesys-модель против ожиданий сценария
    divergences: list[Divergence] = field(default_factory=list)
    variant_divergences: list[Divergence] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def unexplained(self) -> list[Divergence]:
        return [d for d in self.divergences if not d.rule]

    def to_json(self, profiles_used: dict[str, str]) -> dict[str, Any]:
        return {
            "case": self.case,
            "regime": self.regime,
            "profiles": profiles_used,
            "rows": [
                {
                    "scenario": d.scenario,
                    "row": d.row,
                    "cycle": d.cycle,
                    "t_ms": d.t_ms,
                    "signal": d.signal,
                    "codesys": d.codesys,
                    "masterplc": d.masterplc,
                    "rule": d.rule,
                    "explanation": d.explanation,
                }
                for d in self.divergences
            ],
            "variants": [
                {
                    "variant": d.variant,
                    "scenario": d.scenario,
                    "row": d.row,
                    "signal": d.signal,
                    "base": d.codesys,
                    "value": d.masterplc,
                }
                for d in self.variant_divergences
            ],
            "mismatches": self.mismatches,
            "errors": self.errors,
            "summary": {
                "scenarios": self.scenarios,
                "rows": self.rows,
                "collapsed": self.collapsed,
                "divergences": len(self.divergences),
                "unexplained": len(self.unexplained),
            },
        }


def load_expected(text: str) -> list[dict[str, str]]:
    data = tomllib.loads(text) if text.strip() else {}
    return [dict(x) for x in data.get("divergence", [])]


def _sources(mig: Migration) -> tuple[dict[str, tuple[str, str]], list[tuple[str, str]], list[str]]:
    pous = {x.name: (x.decl, x.body) for x in mig.lowered.pous}
    gvls = [(g.name, g.decl_text) for g in mig.project.gvls]
    duts = [d.decl_text for d in mig.project.duts]
    return pous, gvls, duts


def _fixed_sources(mig: Migration) -> tuple[dict[str, tuple[str, str]], list[tuple[str, str]], list[str]]:
    pous: dict[str, tuple[str, str]] = {}
    gvls: list[tuple[str, str]] = []
    duts: list[str] = []
    for obj in mig.fixed.values():
        if obj.kind == "pou":
            pous[obj.name] = (obj.decl, obj.body)
        elif obj.kind == "gvl":
            gvls.append((obj.name, obj.decl))
        elif obj.kind == "dut":
            duts.append(obj.decl)
    return pous, gvls, duts


def machine_codesys(mig: Migration, sem: Semantics) -> Machine:
    p, g, d = _sources(mig)
    return Machine(p, g, d, sem)


def machine_masterplc(mig: Migration, sem: Semantics) -> Machine:
    p, g, d = _fixed_sources(mig)
    alias = {(gv, var): new for (gv, var), new in mig.analysis.gvl_renames.items()}
    return Machine(p, g, d, sem, alias, dialect="masterst")


def renames_for(mig: Migration, pou: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for obj, old, new, _rule in mig.analysis.renames:
        if obj.lower() == pou.lower() and "." not in old:
            out[old.lower()] = new
    return out


def simulate(
    mig: Migration,
    pou: str,
    csv_text: str,
    regime: str = "R1",
    period_codesys: int = 10,
    clocks: dict[str, list[int]] | None = None,
    expected: list[dict[str, str]] | None = None,
    period_masterplc: int | None = None,
    variants: bool = True,
) -> SimReport:
    prof = profiles.load(profiles.TARGET)
    base_m = masterplc(prof.semantics, prof.variants, period_masterplc)
    sem_c = codesys(period_codesys)
    rows = read_csv(csv_text)
    rep = SimReport(pou, regime)
    rn = renames_for(mig, pou)
    exp = expected or []
    for sc in scenarios(rows):
        rep.scenarios += 1
        rep.rows += len(sc)
        ck = (clocks or {}).get(sc[0].scenario)
        try:
            rc = run(machine_codesys(mig, sem_c), pou, sc, regime, period_codesys, ck)
            rm = run(machine_masterplc(mig, base_m), pou, sc, regime, base_m.period_ms, None, rn)
        except SimError as exc:
            rep.errors.append(f"{sc[0].scenario}: {exc}")
            continue
        if rc.error:
            rep.errors.append(f"{sc[0].scenario} (codesys): {rc.error}")
        if rm.error:
            rep.errors.append(f"{sc[0].scenario} (masterplc): {rm.error}")
        _compare_expected(rep, sc, rc.values, regime)
        _diff(rep, sc, rc.values, rm.values, exp, pou, regime)
        if variants:
            for v in all_variants(base_m, prof.variants)[1:]:
                try:
                    rv = run(machine_masterplc(mig, v), pou, sc, regime, v.period_ms, None, rn)
                except SimError as exc:
                    rep.variant_divergences.append(
                        Divergence(sc[0].scenario, 0, 0, 0, "*", "", str(exc), variant=v.label())
                    )
                    continue
                for i, (a, b) in enumerate(zip(rm.values, rv.values, strict=False)):
                    if a is None or b is None:
                        continue
                    for sig in a:
                        if sig in b and not same(a[sig], b[sig], sc[i].tol.get(sig, 0.0)):
                            rep.variant_divergences.append(
                                Divergence(sc[i].scenario, i + 1, sc[i].cycle, sc[i].t_ms, sig, show(a[sig]), show(b[sig]),
                                           variant=v.label())
                            )  # fmt: skip
    return rep


def _compare_expected(rep: SimReport, sc: list[Row], vals: list[dict[str, Any] | None], regime: str) -> None:
    from .runner import parse_value

    for i, r in enumerate(sc):
        got = vals[i] if i < len(vals) else None
        if got is None:
            if regime == "R2":
                rep.collapsed += 1
            continue
        if regime != "R1":
            continue
        for sig, (typ, text) in r.outputs.items():
            exp = parse_value(typ, text)
            if not same(got.get(sig), exp, r.tol.get(sig, 0.0)):
                rep.mismatches.append({"scenario": r.scenario, "row": i + 1, "t_ms": r.t_ms, "signal": sig,
                                       "expected": show(exp), "codesys": show(got.get(sig))})  # fmt: skip


def _diff(rep: SimReport, sc: list[Row], a: list[dict[str, Any] | None], b: list[dict[str, Any] | None],
          exp: list[dict[str, str]], case: str, regime: str) -> None:  # fmt: skip
    for i, r in enumerate(sc):
        va = a[i] if i < len(a) else None
        vb = b[i] if i < len(b) else None
        if va is None or vb is None:
            continue
        for sig in r.outputs:
            x, y = va.get(sig), vb.get(sig)
            if same(x, y, r.tol.get(sig, 0.0)):
                continue
            d = Divergence(r.scenario, i + 1, r.cycle, r.t_ms, f"out.{sig}", show(x), show(y))
            for e in exp:
                if e.get("case", case).lower() != case.lower():
                    continue
                if e.get("regime") and e["regime"] != regime:
                    continue
                if e.get("signal") in (d.signal, sig, "*"):
                    d.rule = e.get("rule", "")
                    d.explanation = e.get("explanation", "")
                    break
            rep.divergences.append(d)
