"""Сценарии корпуса УДР-1: входы по строкам и ожидания эталонных моделей (corpus/reference/models.py).

Пишет ``corpus/<язык>/<случай>/scenario.csv`` в диалекте s7-to-codesys: ``scenario,cycle,t_ms,in.*,out.*,tol.*,
boundary,comment``. Все t_ms кратны 10 мс (период стенда в Control Win).

    python tools/corpus/gen_scenarios.py [--check]
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus" / "reference"))
import models as M  # noqa: E402


def steps(seq: list[tuple[int, dict[str, Any]]], base: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """Строки с удержанием: каждая строка дополняет предыдущие входы."""
    cur = dict(base)
    out = []
    for t, d in seq:
        cur.update(d)
        out.append((t, dict(cur)))
    return out


B = "BOOL"
CASES: dict[str, dict[str, Any]] = {
    "st/FB_AnalogScale": {
        "model": M.m_analog_scale,
        "inputs": {"iRaw": "INT", "rLo": "REAL", "rHi": "REAL"},
        "outputs": {"rValue": "REAL", "xFault": B},
        "scenarios": [
            ("Normal", steps([(0, {"iRaw": 0}), (10, {"iRaw": 13824}), (20, {"iRaw": 27648}), (30, {"iRaw": 6912}),
                              (40, {"iRaw": 30000}), (50, {"iRaw": -5}), (60, {"iRaw": 20736})], {"rLo": 0.0, "rHi": 120.0})),
            ("Swapped", steps([(0, {"iRaw": 0}), (10, {"iRaw": 27648}), (20, {"iRaw": 13824})], {"rLo": 100.0, "rHi": 0.0})),
        ],
    },
    "st/FB_FlowTotal": {
        "model": M.m_flow_total,
        "inputs": {"rFlow_m3h": "REAL", "tCycle": "TIME", "xReset": B},
        "outputs": {"rTotal_m3": "REAL", "diPulses": "DINT"},
        "scenarios": [
            ("HalfSteps", steps([(t * 10, {}) for t in range(8)] + [(80, {"xReset": True}), (90, {"xReset": False})],
                                {"rFlow_m3h": 18000.0, "tCycle": 100, "xReset": False})),
            ("NoFlow", steps([(0, {}), (10, {"rFlow_m3h": -5.0}), (20, {"rFlow_m3h": 36000.0})],
                             {"rFlow_m3h": 0.0, "tCycle": 100, "xReset": False})),
        ],
    },
    "st/PRG_TonQuant": {
        "model": M.m_ton_quant,
        "inputs": {"xStart": B},
        "outputs": {"xQ": B, "tEt": "TIME"},
        "scenarios": [("Ton150", steps([(t, {"xStart": 50 <= t < 450}) for t in range(0, 600, 50)], {"xStart": False}))],
    },
    "fbd/FB_LevelAlarm": {
        "model": M.m_level_alarm,
        "inputs": {"rLevel": "REAL", "rHi": "REAL", "rHiHi": "REAL", "xAck": B, "xBypass": B},
        "outputs": {"xHi": B, "xHiHi": B, "xAlarm": B},
        "scenarios": [
            ("RiseAck", steps([(0, {}), (10, {"rLevel": 85.0}), (20, {"rLevel": 95.0}), (30, {"rLevel": 70.0}),
                               (40, {"xAck": True}), (50, {"xAck": False})],
                              {"rLevel": 50.0, "rHi": 80.0, "rHiHi": 90.0, "xAck": False, "xBypass": False})),
            ("Bypass", steps([(0, {"xBypass": True}), (10, {"rLevel": 95.0}), (20, {"xBypass": False}), (30, {"rLevel": 60.0})],
                             {"rLevel": 50.0, "rHi": 80.0, "rHiHi": 90.0, "xAck": False, "xBypass": False})),
        ],
    },
    "fbd/FB_ValveCmd": {
        "model": M.m_valve_cmd,
        "inputs": {"xOpenCmd": B, "xCloseCmd": B, "xInterlock": B, "xFbOpen": B},
        "outputs": {"xOpen": B, "xFault": B, "xMonitor": B},
        "scenarios": [
            ("OpenNoFeedback", steps([(0, {}), (10, {"xOpenCmd": True}), (20, {"xOpenCmd": False}), (40, {}), (60, {}),
                                      (70, {"xFbOpen": True}), (80, {"xFbOpen": False}), (90, {}), (100, {"xCloseCmd": True}),
                                      (110, {"xCloseCmd": False})],
                                     {"xOpenCmd": False, "xCloseCmd": False, "xInterlock": False, "xFbOpen": False})),
            ("Interlock", steps([(0, {"xInterlock": True}), (10, {"xOpenCmd": True}), (20, {"xInterlock": False}), (30, {})],
                                {"xOpenCmd": False, "xCloseCmd": False, "xInterlock": False, "xFbOpen": False})),
        ],
    },
    "ld/PRG_Permissives": {
        "model": M.m_permissives,
        "inputs": {"xLowLevel": B, "xHighPress": B, "xStartPb": B, "xStopPb": B, "xReset": B},
        "outputs": {"xPermit": B, "xRunLatch": B, "xTrip": B},
        "scenarios": [
            ("Sequence", steps([(0, {}), (10, {"xStartPb": True}), (20, {"xStartPb": False}), (30, {"xHighPress": True}),
                                (50, {}), (60, {}), (70, {"xHighPress": False}), (80, {"xStartPb": True}), (90, {"xReset": True}),
                                (100, {"xReset": False, "xStartPb": False}), (110, {"xStartPb": True}), (120, {"xLowLevel": True}),
                                (130, {"xStopPb": True}), (140, {"xStopPb": False, "xLowLevel": False})],
                               {"xLowLevel": False, "xHighPress": False, "xStartPb": False, "xStopPb": False, "xReset": False})),
        ],
    },
    "ld/PRG_PumpInterlock": {
        "model": M.m_pump_interlock,
        "inputs": {"xAuto": B, "xPermit": B, "xManual": B, "xLampTest": B},
        "outputs": {"xPumpCmd": B, "xLamp": B, "iStarts": "INT"},
        "scenarios": [
            ("Modes", steps([(0, {}), (10, {"xAuto": True}), (20, {"xPermit": True}), (30, {"xPermit": False}),
                             (40, {"xManual": True}), (50, {"xManual": False}), (60, {"xLampTest": True}),
                             (70, {"xLampTest": False, "xPermit": True})],
                            {"xAuto": False, "xPermit": False, "xManual": False, "xLampTest": False})),
        ],
    },
    "cfc/FB_DoseCtrl": {
        "model": M.m_dose_ctrl,
        "inputs": {"xEnable": B, "rSp": "REAL", "rPv": "REAL", "rKp": "REAL", "rKi": "REAL"},
        "outputs": {"rOut": "REAL", "rErr": "REAL"},
        "scenarios": [
            ("Step", steps([(t * 10, {"rPv": 10.0 + t}) for t in range(12)] + [(120, {"xEnable": False})],
                           {"xEnable": True, "rSp": 20.0, "rPv": 10.0, "rKp": 2.0, "rKi": 0.5})),
        ],
    },
    "cfc/FB_RatioCalc": {
        "model": M.m_ratio_calc,
        "inputs": {"rFlowA": "REAL", "rRatio": "REAL"},
        "outputs": {"rFilt": "REAL", "rFlowBSp": "REAL"},
        "scenarios": [("Filter", steps([(t * 10, {"rFlowA": 100.0 if t < 6 else 50.0}) for t in range(10)],
                                       {"rFlowA": 0.0, "rRatio": 0.02}))],
    },
    "sfc/PRG_FillSeq": {
        "model": M.m_fill_seq,
        "inputs": {"xStart": B, "xLevelHi": B, "xTempOk": B},
        "outputs": {"xValveIn": B, "xHeater": B, "xMixer": B, "xAlarm": B, "iBatches": "INT", "iSeq": "INT", "xFlush": B},
        "scenarios": [
            ("Batch", steps([(t * 10, {}) for t in range(2)] + [(20, {"xStart": True})] + [(t * 10, {}) for t in range(3, 9)]
                            + [(90, {"xLevelHi": True})] + [(100, {})] + [(110, {"xTempOk": True})] + [(t * 10, {}) for t in range(12, 20)]
                            + [(200, {"xStart": False, "xLevelHi": False, "xTempOk": False})] + [(t * 10, {}) for t in range(21, 25)],
                            {"xStart": False, "xLevelHi": False, "xTempOk": False})),
        ],
    },
    "sfc/PRG_CipSeq": {
        "model": M.m_cip_seq,
        "inputs": {"xAcid": B, "xCaustic": B, "xDone": B},
        "outputs": {"xAcidPump": B, "xCausticPump": B, "iRinseIn": "INT", "xRinseValve": B},
        "scenarios": [
            ("TwoWashes", steps([(0, {}), (10, {"xAcid": True}), (20, {"xAcid": False}), (30, {}), (40, {"xDone": True}),
                                 (50, {}), (60, {}), (70, {"xDone": False}), (80, {}), (90, {"xCaustic": True}),
                                 (100, {"xCaustic": False}), (110, {"xDone": True}), (120, {}), (130, {"xDone": False}),
                                 (140, {}), (150, {})],
                                {"xAcid": False, "xCaustic": False, "xDone": False})),
        ],
    },
    "il/FB_PulseCount": {
        "model": M.m_pulse_count,
        "inputs": {"xPulse": B, "xReset": B, "iLimit": "INT"},
        "outputs": {"iCount": "INT", "xDone": B},
        "scenarios": [
            ("Pulses", steps([(t * 10, {"xPulse": t % 2 == 1}) for t in range(14)] + [(140, {"xReset": True, "xPulse": True}),
                             (150, {"xReset": False, "xPulse": True}), (160, {"xPulse": False}), (170, {"xPulse": True})],
                             {"xPulse": False, "xReset": False, "iLimit": 5})),
        ],
    },
    "il/PRG_IlHost": {
        "model": M.m_il_host,
        "inputs": {"rIn": "REAL"},
        "outputs": {"rOut": "REAL"},
        "scenarios": [("Scale", steps([(0, {"rIn": 1.5}), (10, {"rIn": 20.0}), (20, {"rIn": 40.0}), (30, {"rIn": -2.0})], {"rIn": 0.0}))],
    },
    "oop/PRG_OopDemo": {
        "model": M.m_oop_demo,
        "inputs": {"xRun": B, "xStop": B},
        "outputs": {"rTotal_ml": "REAL", "iState": "INT", "rPumped_ml": "REAL", "iLoops": "INT"},
        "scenarios": [("RunStop", steps([(0, {}), (10, {"xRun": True}), (20, {"xRun": False}), (30, {}), (40, {"xStop": True}),
                                         (50, {"xStop": False}), (60, {"xRun": True}), (70, {})], {"xRun": False, "xStop": False}))],
    },
}  # fmt: skip


def fmt(v: Any, typ: str) -> str:
    if typ == "BOOL":
        return "TRUE" if v else "FALSE"
    if typ == "TIME":
        return f"T#{int(v)}MS"
    if typ in ("REAL", "LREAL"):
        return repr(float(v))
    return str(int(v))


def render(case: str) -> str:
    spec = CASES[case]
    ins, outs = spec["inputs"], spec["outputs"]
    header = ["scenario", "cycle", "t_ms"] + [f"in.{k}:{t}" for k, t in ins.items()]
    for k, t in outs.items():
        header.append(f"out.{k}:{t}")
        if t in ("REAL", "LREAL"):
            header.append(f"tol.{k}")
    header += ["boundary", "comment"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for name, rows in spec["scenarios"]:
        exp = spec["model"](rows)
        for n, ((t, i), o) in enumerate(zip(rows, exp, strict=True), 1):
            rec = [name, n, t] + [fmt(i[k], typ) for k, typ in ins.items()]
            for k, typ in outs.items():
                rec.append(fmt(o[k], typ))
                if typ in ("REAL", "LREAL"):
                    rec.append("0.001")
            rec += ["FALSE", ""]
            w.writerow(rec)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    bad = 0
    for case in CASES:
        path = ROOT / "corpus" / case / "scenario.csv"
        text = render(case)
        if a.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print(f"устарел: {path.relative_to(ROOT)}")
                bad += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"сценариев: {len(CASES)}" + (f", устаревших {bad}" if a.check else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
