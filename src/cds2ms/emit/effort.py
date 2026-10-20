"""Модель трудоёмкости семейства (00-INDEX §4.3): треугольное распределение минут на находку, находки
независимы, Монте-Карло 10 000 проб, seed 20261019; итог — P50 и P90 по POU и проекту в часах.
Подпись — «модель, не калибрована»."""

from __future__ import annotations

import random

from ..rules.findings import Finding

RUNS = 10_000
SEED = 20261019


def _tri(rng: random.Random, a: float, m: float, b: float) -> float:
    if b <= a:
        return a
    return rng.triangular(a, b, m)


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def monte_carlo(findings: list[Finding], runs: int = RUNS, seed: int = SEED) -> dict[str, object]:
    rng = random.Random(seed)
    items = [f.minutes for f in findings if f.minutes[2] > 0]
    by_pou: dict[str, list[tuple[float, float, float]]] = {}
    for f in findings:
        if f.minutes[2] > 0:
            by_pou.setdefault(f.pou or "(проект)", []).append(f.minutes)
    totals: list[float] = []
    pou_totals: dict[str, list[float]] = {k: [] for k in by_pou}
    for _ in range(runs):
        s = 0.0
        for k, mins in by_pou.items():
            v = sum(_tri(rng, a, m, b) for a, m, b in mins)
            pou_totals[k].append(v)
            s += v
        totals.append(s)
    totals.sort()
    pou_out = {}
    for k, vals in sorted(pou_totals.items()):
        vals.sort()
        pou_out[k] = {"p50_h": round(percentile(vals, 0.5) / 60, 2), "p90_h": round(percentile(vals, 0.9) / 60, 2)}
    del items
    return {
        "model": "triangular-mc",
        "runs": runs,
        "seed": seed,
        "p50_h": round(percentile(totals, 0.5) / 60, 2),
        "p90_h": round(percentile(totals, 0.9) / 60, 2),
        "calibrated": False,
        "calibration": "модель, не калибрована",
        "by_pou": pou_out,
        "mode_sum_h": round(sum(f.minutes[1] for f in findings) / 60, 2),
    }
