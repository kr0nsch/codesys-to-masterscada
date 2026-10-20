"""Независимые эталонные модели корпуса УДР-1: ожидания сценариев считаются по описанию логики блока
(docstring в corpus/udr1/sources.py), а не по коду конвертера. Режим R1 «строка = вызов» (время = t_ms).

Модели не импортируют cds2ms: SFC считается собственным маленьким исполнителем по документации CODESYS
(порядок обработки за цикл, IEC-квалификаторы), а не ST-автоматом понижения.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from typing import Any

Row = tuple[int, dict[str, Any]]  # (t_ms, входы)


def f32(x: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", x))[0])


def round_away(x: float) -> int:
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


class Ton:
    def __init__(self) -> None:
        self.prev = False
        self.start = 0
        self.q = False
        self.et = 0

    def __call__(self, inp: bool, pt: int, now: int) -> None:
        if inp:
            if not self.prev:
                self.start = now
            el = now - self.start
            self.q = el >= pt
            self.et = min(el, pt)
        else:
            self.q = False
            self.et = 0
        self.prev = inp


# ------------------------------------------------------------------ ST


def m_analog_scale(rows: list[Row]) -> list[dict[str, Any]]:
    out = []
    value = 0.0
    for _t, i in rows:
        raw, lo, hi = i["iRaw"], i["rLo"], i["rHi"]
        if raw < 0 or raw > 27648:
            fault = True
        else:
            fault = False
            v = lo + (hi - lo) * raw / 27648.0
            a, b = (lo, hi) if lo <= hi else (hi, lo)
            value = f32(max(a, min(v, b)))
        out.append({"rValue": value, "xFault": fault})
    return out


def m_flow_total(rows: list[Row]) -> list[dict[str, Any]]:
    out = []
    total = 0.0
    for _t, i in rows:
        if i["xReset"]:
            total = 0.0
        elif i["rFlow_m3h"] > 0:
            total = f32(total + i["rFlow_m3h"] * i["tCycle"] / 3600000.0)
        out.append({"rTotal_m3": total, "diPulses": round_away(total)})
    return out


def m_ton_quant(rows: list[Row]) -> list[dict[str, Any]]:
    ton = Ton()
    out = []
    for t, i in rows:
        ton(i["xStart"], 150, t)
        out.append({"xQ": ton.q, "tEt": ton.et})
    return out


# ------------------------------------------------------------------ FBD


def m_level_alarm(rows: list[Row]) -> list[dict[str, Any]]:
    q1 = False
    hihi = False
    alarm = False
    out = []
    for _t, i in rows:
        hi = i["rLevel"] > i["rHi"]
        if not i["xBypass"]:
            q1 = (not i["xAck"]) and (q1 or i["rLevel"] > i["rHiHi"])
            alarm = q1
        hihi = i["rLevel"] > i["rHiHi"]
        out.append({"xHi": hi, "xHiHi": hihi, "xAlarm": alarm})
    return out


def m_valve_cmd(rows: list[Row]) -> list[dict[str, Any]]:
    q1 = False
    ton = Ton()
    s = {"xOpen": False, "xFault": False, "xMonitor": False}
    out = []
    for t, i in rows:
        if not i["xInterlock"]:
            q1 = i["xOpenCmd"] or ((not i["xCloseCmd"]) and q1)
            s["xOpen"] = q1
            en = q1 and not i["xFbOpen"]
            ton(en, 40, t)
            s["xFault"] = ton.q
            s["xMonitor"] = en
        out.append(dict(s))
    return out


# ------------------------------------------------------------------ LD


def m_permissives(rows: list[Row]) -> list[dict[str, Any]]:
    trip = False
    latch = False
    prev_start = False
    out = []
    for _t, i in rows:
        permit = not i["xLowLevel"]
        if i["xHighPress"]:
            trip = True
        if i["xReset"]:
            trip = False
        edge = i["xStartPb"] and not prev_start
        prev_start = i["xStartPb"]
        if edge and not trip and permit:
            latch = True
        if i["xStopPb"] or trip:
            latch = False
        out.append({"xPermit": permit, "xRunLatch": latch, "xTrip": trip})
    return out


def m_pump_interlock(rows: list[Row]) -> list[dict[str, Any]]:
    prev = False
    starts = 0
    out = []
    for _t, i in rows:
        cmd = (i["xAuto"] and i["xPermit"]) or i["xManual"]
        lamp = cmd or i["xLampTest"]
        if cmd and not prev:
            starts += 1
        prev = cmd
        out.append({"xPumpCmd": cmd, "xLamp": lamp, "iStarts": starts})
    return out


# ------------------------------------------------------------------ CFC


def m_dose_ctrl(rows: list[Row]) -> list[dict[str, Any]]:
    integ = 0.0
    out = []
    for _t, i in rows:
        e = f32(i["rSp"] - i["rPv"])
        p = e * i["rKp"]
        integ = f32(max(0.0, min(integ + e * i["rKi"], 100.0)))
        tot = max(0.0, min(p + integ, 100.0))
        o = f32(tot) if i["xEnable"] else 0.0
        out.append({"rOut": o, "rErr": e})
    return out


def m_ratio_calc(rows: list[Row]) -> list[dict[str, Any]]:
    flt = 0.0
    out = []
    for _t, i in rows:
        raw = f32(i["rFlowA"] * i["rRatio"])
        flt = f32(flt + (raw - flt) * 0.5)
        out.append({"rFilt": flt, "rFlowBSp": raw})
    return out


# ------------------------------------------------------------------ SFC (свой исполнитель по справке CODESYS, уточнён трассой Control Win 3.5.17.30)


class SfcModel:
    """steps: имена; init: начальный; trans: [(из [шагов], в [шаги], условие(входы, t шагов))];
    acts: {действие: [(шаг, квалификатор, длительность_мс)]}; bodies: {действие: f(state, x)}."""

    def __init__(self, steps: list[str], init: str, trans: list[tuple[list[str], list[str], Callable[..., bool]]],
                 acts: dict[str, list[tuple[str, str, int]]], bodies: dict[str, Callable[[dict[str, Any], bool], None]],
                 outputs: dict[str, Any]) -> None:  # fmt: skip
        self.steps = steps
        self.active = {s: s == init for s in steps}
        self.prev = dict.fromkeys(steps, False)
        self.since = dict.fromkeys(steps, 0)
        self.trans = trans
        self.acts = acts
        self.bodies = bodies
        self.stored = dict.fromkeys(acts, False)
        self.q_prev = dict.fromkeys(acts, False)
        self.state = dict(outputs)

    def cycle(self, inputs: dict[str, Any], now: int) -> dict[str, Any]:
        cur = dict(self.active)
        for s in self.steps:
            if cur[s] and not self.prev[s]:
                self.since[s] = now
        t = {s: (now - self.since[s]) if cur[s] else 0 for s in self.steps}
        q: dict[str, bool] = {}
        for a in sorted(self.acts):
            on = False
            for s, qual, dur in self.acts[a]:
                if (
                    (qual == "N" and cur[s])
                    or (qual in ("P", "P1") and cur[s] and not self.prev[s])
                    or (qual == "P0" and self.prev[s] and not cur[s])
                    or (qual == "L" and cur[s] and t[s] < dur)
                    or (qual == "D" and cur[s] and t[s] >= dur)
                ):
                    on = True
            sets = any(cur[s] for s, qual, _ in self.acts[a] if qual == "S")
            resets = any(cur[s] for s, qual, _ in self.acts[a] if qual == "R")
            self.stored[a] = (self.stored[a] or sets) and not resets
            q[a] = on or self.stored[a]
        for a in sorted(self.acts):  # проход 1: последний вызов деактивированных
            if self.q_prev[a] and not q[a]:
                self.bodies[a](self.state, True)  # _действие.x = TRUE и в последнем вызове (трасса Control Win)
        for a in sorted(self.acts):  # проход 2: активные
            if q[a]:
                self.bodies[a](self.state, True)
        self.q_prev = q
        nxt = dict(cur)
        for frm, to, cond in self.trans:
            if all(cur[s] and nxt[s] for s in frm) and cond(inputs, t):
                for s in frm:
                    nxt[s] = False
                for s in to:
                    nxt[s] = True
        self.prev = cur
        self.active = nxt
        return dict(self.state)


def m_fill_seq(rows: list[Row]) -> list[dict[str, Any]]:
    def setb(name: str) -> Callable[[dict[str, Any], bool], None]:
        def f(st: dict[str, Any], x: bool) -> None:
            st[name] = x

        return f

    def count(st: dict[str, Any], x: bool) -> None:
        if x:
            st["iBatches"] += 1

    def seq(d: int) -> Callable[[dict[str, Any], bool], None]:
        def f(st: dict[str, Any], x: bool) -> None:
            if x:
                st["iSeq"] = (st["iSeq"] * 10 + d) % 10000

        return f

    inp: dict[str, Any] = {}
    m = SfcModel(
        ["Init", "Fill", "WaitFill", "Heat", "WaitHeat", "Mix", "Done"], "Init",
        [(["Init"], ["Fill", "Heat"], lambda i, t: i["xStart"]),
         (["Fill"], ["WaitFill"], lambda i, t: i["xLevelHi"]),
         (["Heat"], ["WaitHeat"], lambda i, t: i["xTempOk"]),
         (["WaitFill", "WaitHeat"], ["Mix"], lambda i, t: True),
         (["Mix"], ["Done"], lambda i, t: t["Mix"] >= 40),
         (["Done"], ["Init"], lambda i, t: not i["xStart"])],
        {"ActFill": [("Fill", "N", 0)], "ActFlush": [("Fill", "L", 30)], "ActZeta": [("Heat", "N", 0)],
         "ActHeat": [("Heat", "N", 0)], "ActAlarm": [("Heat", "D", 50)], "ActMixer": [("Mix", "S", 0), ("Done", "R", 0)],
         "ActCount": [("Mix", "P", 0)], "ActAlpha": [("Mix", "N", 0)]},
        {"ActFill": setb("xValveIn"), "ActFlush": setb("xFlush"), "ActHeat": setb("xHeater"), "ActAlarm": setb("xAlarm"),
         "ActMixer": setb("xMixer"), "ActCount": count, "ActZeta": seq(2), "ActAlpha": seq(1)},
        {"xValveIn": False, "xHeater": False, "xMixer": False, "xAlarm": False, "iBatches": 0, "iSeq": 0, "xFlush": False},
    )  # fmt: skip
    del inp
    return [m.cycle(i, t) for t, i in rows]


def m_cip_seq(rows: list[Row]) -> list[dict[str, Any]]:
    def setb(name: str) -> Callable[[dict[str, Any], bool], None]:
        def f(st: dict[str, Any], x: bool) -> None:
            st[name] = x

        return f

    def inc(name: str) -> Callable[[dict[str, Any], bool], None]:
        def f(st: dict[str, Any], x: bool) -> None:
            if x:
                st[name] += 1

        return f

    m = SfcModel(
        ["Idle", "Acid", "Caustic", "Rinse"], "Idle",
        [(["Idle"], ["Acid"], lambda i, t: i["xAcid"]),
         (["Idle"], ["Caustic"], lambda i, t: i["xCaustic"]),
         (["Acid"], ["Rinse"], lambda i, t: i["xDone"]),
         (["Caustic"], ["Rinse"], lambda i, t: i["xDone"]),
         (["Rinse"], ["Idle"], lambda i, t: not i["xDone"])],
        {"ActAcid": [("Acid", "N", 0)], "ActCaustic": [("Caustic", "N", 0)], "ActRinseIn": [("Rinse", "P", 0)],
         "ActRinseOut": [("Rinse", "N", 0)]},
        {"ActAcid": setb("xAcidPump"), "ActCaustic": setb("xCausticPump"), "ActRinseIn": inc("iRinseIn"),
         "ActRinseOut": setb("xRinseValve")},
        {"xAcidPump": False, "xCausticPump": False, "iRinseIn": 0, "xRinseValve": False},
    )  # fmt: skip
    return [m.cycle(i, t) for t, i in rows]


# ------------------------------------------------------------------ IL


def m_pulse_count(rows: list[Row]) -> list[dict[str, Any]]:
    count = 0
    mem = False
    out = []
    for _t, i in rows:
        if i["xReset"]:
            count = 0
        else:
            edge = i["xPulse"] and not mem
            mem = i["xPulse"]
            if edge and count < i["iLimit"]:
                count += 1
        out.append({"iCount": count, "xDone": count >= i["iLimit"]})
    return out


def m_il_host(rows: list[Row]) -> list[dict[str, Any]]:
    out = []
    for _t, i in rows:
        acc = 0.0
        for _ in range(3):
            acc = f32(acc + i["rIn"])
        out.append({"rOut": max(0.0, min(acc, 100.0))})
    return out


# ------------------------------------------------------------------ ООП


def m_oop_demo(rows: list[Row]) -> list[dict[str, Any]]:
    running = False
    istate = 0
    dosed = 0.0
    total = 0.0
    out = []
    for _t, i in rows:
        if i["xRun"] and not running:
            running, istate = True, 1
        if i["xStop"]:
            running, istate = False, 0
        if running:
            dosed += 0.5
        if running:
            total += 0.25
        loops = 0
        while dosed < 2.0 and loops < 3:
            if running:
                dosed += 0.5
            loops += 1
        out.append({"rTotal_ml": total, "iState": istate, "rPumped_ml": dosed, "iLoops": loops})
    return out
