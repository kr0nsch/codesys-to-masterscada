"""Корпус «узел дозирования реагента УДР-1» (вымышленный объект): исходники на шести языках CODESYS и ООП.

ST и ООП создаются в CODESYS текстовым API, графика (FBD, LD, CFC, SFC) и IL — рукописным TC6 (tools/corpus/tc6.py)
через import_xml. Логику каждого блока описывает строка в docstring модели ``corpus/reference/model_*.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "corpus"))
from tc6 import Graph, Sfc, cfc_body, fbd_body, il_body, ld_body, pou

# ------------------------------------------------------------------ типы и глобальные

DUTS = {
    "E_DoseState": "TYPE E_DoseState :\n(\n    Idle := 0,\n    Priming := 10,\n    Dosing := 20,\n    Fault := 99\n) INT;\nEND_TYPE\n",
    "ST_Recipe": "TYPE ST_Recipe :\nSTRUCT\n    rRatio : REAL := 0.02;\n    tMix : TIME := T#500MS;\n    sName : STRING(20) := 'NaOCl';\nEND_STRUCT\nEND_TYPE\n",
    "U_RawWord": "TYPE U_RawWord :\nUNION\n    wRaw : WORD;\n    abByte : ARRAY[0..1] OF BYTE;\nEND_UNION\nEND_TYPE\n",
    "T_Percent": "TYPE T_Percent : INT(0..100);\nEND_TYPE\n",
}

GVLS = {
    "GVL_IO": "VAR_GLOBAL\n    xLevelLow AT %IX0.0 : BOOL;\n    xLevelHigh AT %IX0.1 : BOOL;\n    iFlowRaw AT %IW2 : INT;\n    xPumpOut AT %QX0.0 : BOOL;\n    xAlarmLamp AT %QX0.1 : BOOL;\nEND_VAR\n",
    "GVL_Retain": "VAR_GLOBAL RETAIN\n    rTotalDosed : REAL;\n    udiStarts : UDINT;\nEND_VAR\n",
    "GVL_Const": "VAR_GLOBAL CONSTANT\n    c_rRawFull : REAL := 27648.0;\n    c_tPrime : TIME := T#2S;\nEND_VAR\n",
}

# ------------------------------------------------------------------ ST

ST_POUS: list[tuple[str, str, str, str]] = [
    ("F_Clamp", "function",
     "// Ограничение значения пределами; пределы, заданные наоборот, меняются местами\nFUNCTION F_Clamp : REAL\nVAR_INPUT\n    rIn : REAL;\n    rMin : REAL;\n    rMax : REAL;\nEND_VAR\nVAR\n    rLo : REAL;\n    rHi : REAL;\nEND_VAR\n",
     "IF rMin <= rMax THEN\n    rLo := rMin;\n    rHi := rMax;\nELSE\n    rLo := rMax;\n    rHi := rMin;\nEND_IF\nF_Clamp := LIMIT(rLo, rIn, rHi);\n"),
    ("FB_AnalogScale", "functionBlock",
     "// Масштабирование 0..27648 → rLo..rHi; вне диапазона — неисправность, значение удерживается\nFUNCTION_BLOCK FB_AnalogScale\nVAR_INPUT\n    iRaw : INT;\n    rLo : REAL := 0.0;\n    rHi : REAL := 100.0;\nEND_VAR\nVAR_OUTPUT\n    rValue : REAL;\n    xFault : BOOL;\nEND_VAR\n",
     "IF iRaw < 0 OR iRaw > 27648 THEN\n    xFault := TRUE;\nELSE\n    xFault := FALSE;\n    rValue := F_Clamp(rIn := rLo + (rHi - rLo) * INT_TO_REAL(iRaw) / 27648.0, rMin := rLo, rMax := rHi);\nEND_IF\n"),
    ("FB_FlowTotal", "functionBlock",
     "// Интегрирование расхода (м3/ч) по времени цикла; сброс уровнем; импульсы — округление до целого (REAL_TO_DINT)\nFUNCTION_BLOCK FB_FlowTotal\nVAR_INPUT\n    rFlow_m3h : REAL;\n    tCycle : TIME := T#100MS;\n    xReset : BOOL;\nEND_VAR\nVAR_OUTPUT\n    rTotal_m3 : REAL;\n    diPulses : DINT;\nEND_VAR\n",
     "IF xReset THEN\n    rTotal_m3 := 0.0;\nELSIF rFlow_m3h > 0.0 THEN\n    rTotal_m3 := rTotal_m3 + rFlow_m3h * TIME_TO_REAL(tCycle) / 3600000.0;\nEND_IF\ndiPulses := REAL_TO_DINT(rTotal_m3);\n"),
    ("PRG_TonQuant", "program",
     "// TON 150 мс: на нём видно квантование таймера периодом задачи (MS-EXEC-01)\nPROGRAM PRG_TonQuant\nVAR_INPUT\n    xStart : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xQ : BOOL;\n    tEt : TIME;\nEND_VAR\nVAR\n    fbTon : TON;\nEND_VAR\n",
     "fbTon(IN := xStart, PT := T#150MS);\nxQ := fbTon.Q;\ntEt := fbTon.ET;\n"),
    ("PRG_Main", "program",
     "// Главная программа УДР-1: вызовы и конструкции диалекта, которые перенос меняет\nPROGRAM PRG_Main\nVAR\n    fbScale : FB_AnalogScale;\n    fbTotal : FB_FlowTotal;\n    eState : E_DoseState := E_DoseState.Idle;\n    stRecipe : ST_Recipe;\n    sMsg : STRING(40);\n    ltUptime : LTIME;\n    dtLastStart : DT;\n    rLevel_ : REAL;\n    iStep : INT;\n    pRaw : POINTER TO INT;\nEND_VAR\n",
     "fbScale(iRaw := GVL_IO.iFlowRaw, rLo := 0.0, rHi := 120.0);\nfbTotal(rFlow_m3h := fbScale.rValue, tCycle := T#10MS);\nGVL_Retain.rTotalDosed := fbTotal.rTotal_m3;\nGVL_IO.xPumpOut S= eState = E_DoseState.Dosing;\nGVL_IO.xPumpOut R= GVL_IO.xLevelLow;\nCASE eState OF\n    E_DoseState.Idle:\n        IF NOT GVL_IO.xLevelLow THEN\n            eState := E_DoseState.Priming;\n            dtLastStart := DT#1970-01-01-00:00:00;\n        END_IF\n    E_DoseState.Priming:\n        eState := E_DoseState.Dosing;\n    E_DoseState.Dosing:\n        IF GVL_IO.xLevelLow THEN\n            eState := E_DoseState.Idle;\n        END_IF\nELSE\n    eState := E_DoseState.Fault;\nEND_CASE\nltUptime := ltUptime + LTIME#10MS;\nsMsg := stRecipe.sName;\nrLevel_ := fbScale.rValue;\npRaw := ADR(iStep);\nIF iStep > 3 THEN\n    JMP lblEnd;\nEND_IF\niStep := iStep + 1;\nlblEnd:\n;\n"),
]  # fmt: skip

# ------------------------------------------------------------------ ООП (текстовым API CODESYS)

I_DEVICE = {
    "name": "I_Device",
    "methods": [("Start", "METHOD Start : BOOL\n")],
    "properties": [("State", "PROPERTY State : INT\n")],
}

FB_DEVICE_BASE = {
    "name": "FB_DeviceBase",
    "decl": "// Базовый ФБ устройства: пуск, останов, счёт тиков в работе\nFUNCTION_BLOCK FB_DeviceBase\nVAR_OUTPUT\n    xRunning : BOOL;\n    udiTicks : UDINT;\nEND_VAR\nVAR\n    iState : INT;\nEND_VAR\n",
    "body": "IF xRunning THEN\n    udiTicks := udiTicks + 1;\nEND_IF\n",
    "methods": [
        ("Start", "METHOD Start : BOOL\nVAR_INPUT\nEND_VAR\n", "xRunning := TRUE;\niState := 1;\nStart := TRUE;\n"),
        ("Stop", "METHOD Stop\nVAR_INPUT\nEND_VAR\n", "xRunning := FALSE;\niState := 0;\n"),
    ],
    "properties": [("State", "PROPERTY State : INT\n", "State := iState;\n", None)],
}

FB_DOSING_PUMP = {
    "name": "FB_DosingPump",
    "decl": "// Насос-дозатор: наследует FB_DeviceBase, реализует I_Device; доза — метод с VAR_IN_OUT\nFUNCTION_BLOCK FB_DosingPump EXTENDS FB_DeviceBase IMPLEMENTS I_Device\nVAR_INPUT\n    rStroke_ml : REAL := 0.5;\nEND_VAR\nVAR_OUTPUT\n    rDosed_ml : REAL;\nEND_VAR\n",
    "body": "SUPER^();\nIF xRunning THEN\n    rDosed_ml := rDosed_ml + rStroke_ml;\nEND_IF\n",
    "methods": [
        (
            "Dose",
            "METHOD Dose : BOOL\nVAR_INPUT\n    rAmount_ml : REAL;\nEND_VAR\nVAR_IN_OUT\n    rTotal_ml : REAL;\nEND_VAR\n",
            "IF xRunning THEN\n    rTotal_ml := rTotal_ml + rAmount_ml;\n    Dose := TRUE;\nELSE\n    Dose := FALSE;\nEND_IF\n",
        ),
        (
            "NeedsMore",
            "METHOD NeedsMore : BOOL\nVAR_INPUT\n    rTarget_ml : REAL;\nEND_VAR\n",
            "NeedsMore := rDosed_ml < rTarget_ml;\n",
        ),
        ("Prime", "METHOD Prime\nVAR_INPUT\nEND_VAR\n", "THIS^.Start();\nrDosed_ml := 0.0;\n"),
    ],
    "properties": [("Dosed", "PROPERTY Dosed : REAL\n", "Dosed := rDosed_ml;\n", None)],
}

PRG_OOP = (
    "PRG_OopDemo", "program",
    "// Вызовы методов экземпляра, интерфейсная переменная, свойство, метод в условии WHILE\nPROGRAM PRG_OopDemo\nVAR_INPUT\n    xRun : BOOL;\n    xStop : BOOL;\nEND_VAR\nVAR_OUTPUT\n    rTotal_ml : REAL;\n    iState : INT;\n    rPumped_ml : REAL;\n    iLoops : INT;\nEND_VAR\nVAR\n    fbPump : FB_DosingPump;\n    itfDev : I_Device;\n    xOk : BOOL;\nEND_VAR\n",
    "itfDev := fbPump;\nIF xRun AND NOT fbPump.xRunning THEN\n    xOk := itfDev.Start();\nEND_IF\nIF xStop THEN\n    fbPump.Stop();\nEND_IF\nfbPump(rStroke_ml := 0.5);\nxOk := fbPump.Dose(rAmount_ml := 0.25, rTotal_ml := rTotal_ml);\niState := fbPump.State;\niLoops := 0;\nWHILE fbPump.NeedsMore(rTarget_ml := 2.0) AND iLoops < 3 DO\n    fbPump(rStroke_ml := 0.5);\n    iLoops := iLoops + 1;\nEND_WHILE\nrPumped_ml := fbPump.Dosed;\n",
)  # fmt: skip

# ------------------------------------------------------------------ FBD


def fb_level_alarm() -> str:
    decl = ("// Сигнализация уровня: Hi, HiHi, защёлка тревоги с квитированием; байпас пропускает защёлку\n"
            "FUNCTION_BLOCK FB_LevelAlarm\nVAR_INPUT\n    rLevel : REAL;\n    rHi : REAL := 80.0;\n    rHiHi : REAL := 90.0;\n"
            "    xAck : BOOL;\n    xBypass : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xHi : BOOL;\n    xHiHi : BOOL;\n    xAlarm : BOOL;\nEND_VAR\n"
            "VAR\n    fbLatch : RS;\nEND_VAR\n")  # fmt: skip
    n1 = Graph("FBD", 1)
    gt = n1.block("GT", [("In1", n1.invar("rLevel")), ("In2", n1.invar("rHi"))], ["Out1"])
    n1.outvar("xHi", (gt, "Out1"))
    n2 = Graph("FBD", 2)
    n2.jump("lblEnd", n2.invar("xBypass"))
    n3 = Graph("FBD", 3)
    gt2 = n3.block("GT", [("In1", n3.invar("rLevel")), ("In2", n3.invar("rHiHi"))], ["Out1"])
    rs = n3.block("RS", [("SET", (gt2, "Out1")), ("RESET1", n3.invar("xAck"))], ["Q1"], instance="fbLatch")
    n3.outvar("xAlarm", (rs, "Q1"))
    n4 = Graph("FBD", 4)
    n4.label("lblEnd")
    gt3 = n4.block("GT", [("In1", n4.invar("rLevel")), ("In2", n4.invar("rHiHi"))], ["Out1"])
    n4.outvar("xHiHi", (gt3, "Out1"))
    return pou("FB_LevelAlarm", "functionBlock", decl, fbd_body([n1, n2, n3, n4]))


def fb_valve_cmd() -> str:
    decl = ("// Команда клапана: блокировка возвращает без изменений; задержка контроля обратной связи — TON\n"
            "FUNCTION_BLOCK FB_ValveCmd\nVAR_INPUT\n    xOpenCmd : BOOL;\n    xCloseCmd : BOOL;\n    xInterlock : BOOL;\n"
            "    xFbOpen : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xOpen : BOOL;\n    xFault : BOOL;\n    xMonitor : BOOL;\nEND_VAR\n"
            "VAR\n    fbState : SR;\n    fbFbDelay : TON;\nEND_VAR\n")  # fmt: skip
    n1 = Graph("FBD", 1)
    n1.ret(n1.invar("xInterlock"))
    n2 = Graph("FBD", 2)
    sr = n2.block("SR", [("SET1", n2.invar("xOpenCmd")), ("RESET", n2.invar("xCloseCmd"))], ["Q1"], instance="fbState")
    n2.outvar("xOpen", (sr, "Q1"))
    n3 = Graph("FBD", 3)
    nfb = n3.block("NOT", [("In1", n3.invar("xFbOpen"))], ["Out1"])
    andb = n3.block("AND", [("In1", n3.invar("xOpen")), ("In2", (nfb, "Out1"))], ["Out1"])
    ton = n3.block("TON", [("IN", (andb, "Out1")), ("PT", n3.invar("T#40MS"))], ["Q", "ET"], instance="fbFbDelay")
    n3.outvar("xFault", (ton, "Q"))
    n4 = Graph("FBD", 4)
    nfb4 = n4.block("NOT", [("In1", n4.invar("xFbOpen"))], ["Out1"])
    and4 = n4.block("AND", [("In1", n4.invar("xOpen")), ("In2", (nfb4, "Out1"))], ["Out1"])
    n4.outvar("xMonitor", (and4, "Out1"))
    return pou("FB_ValveCmd", "functionBlock", decl, fbd_body([n1, n2, n3, n4]))


# ------------------------------------------------------------------ LD


def prg_permissives() -> str:
    # Боксы ФБ в LD (TON, CTU) import_xml 3.5.17.30 создаёт «битыми» (docs/FORMAT-OUT.md) — в LD корпуса их нет
    decl = ("// Разрешения пуска: защёлка пуска по фронту кнопки, отключение по давлению (S), квитирование (R)\n"
            "PROGRAM PRG_Permissives\nVAR_INPUT\n    xLowLevel : BOOL;\n    xHighPress : BOOL;\n    xStartPb : BOOL;\n"
            "    xStopPb : BOOL;\n    xReset : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xPermit : BOOL;\n    xRunLatch : BOOL;\n    xTrip : BOOL;\n"
            "END_VAR\n")  # fmt: skip
    nets = []
    n = Graph("LD", 1)
    r = n.rail()
    c = n.contact("xLowLevel", r, negated=True)
    co = n.coil("xPermit", c)
    n.rail_right([co])
    nets.append(n)
    n = Graph("LD", 2)
    r = n.rail()
    c = n.contact("xHighPress", r)
    co = n.coil("xTrip", c, storage="set")
    n.rail_right([co])
    nets.append(n)
    n = Graph("LD", 3)
    r = n.rail()
    c = n.contact("xReset", r)
    co = n.coil("xTrip", c, storage="reset")
    n.rail_right([co])
    nets.append(n)
    n = Graph("LD", 4)
    r = n.rail()
    c1 = n.contact("xStartPb", r, edge="rising")
    c2 = n.contact("xTrip", c1, negated=True)
    c3 = n.contact("xPermit", c2)
    co = n.coil("xRunLatch", c3, storage="set")
    n.rail_right([co])
    nets.append(n)
    n = Graph("LD", 5)
    r = n.rail()
    a = n.contact("xStopPb", r)
    b = n.contact("xTrip", r)
    co = n.coil("xRunLatch", [a, b], storage="reset")
    n.rail_right([co])
    nets.append(n)
    return pou("PRG_Permissives", "program", decl, ld_body(nets))


def prg_pump_interlock() -> str:
    decl = ("// Блокировка насоса: (авто И разрешение) ИЛИ ручной; лампа — параллель; счёт пусков по фронту — SEL и ADD\n"
            "PROGRAM PRG_PumpInterlock\nVAR_INPUT\n    xAuto : BOOL;\n    xPermit : BOOL;\n    xManual : BOOL;\n    xLampTest : BOOL;\n"
            "END_VAR\nVAR_OUTPUT\n    xPumpCmd : BOOL;\n    xLamp : BOOL;\n    iStarts : INT;\nEND_VAR\nVAR\n    xStartPulse : BOOL;\n    iNext : INT;\nEND_VAR\n")  # fmt: skip
    nets = []
    n = Graph("LD", 1)
    r = n.rail()
    a = n.contact("xAuto", r)
    b = n.contact("xPermit", a)
    m = n.contact("xManual", r)
    c1 = n.coil("xPumpCmd", [b, m])
    n.rail_right([c1])
    nets.append(n)
    # Параллель после катушки (катушка → катушка с отводом) import_xml сводит в один узел перед обеими
    # катушками (проверено трассой: «тест лампы» включал насос) — поэтому лампа в своей сети
    n = Graph("LD", 2)
    r = n.rail()
    pc = n.contact("xPumpCmd", r)
    lt = n.contact("xLampTest", r)
    n.coil("xLamp", [pc, lt])
    nets.append(n)
    n = Graph("LD", 3)
    r = n.rail()
    e = n.contact("xPumpCmd", r, edge="rising")
    n.coil("xStartPulse", e)
    nets.append(n)
    # операторы — по одному на сеть, входы и выход — переменные: так import_xml принимает бокс в LD
    # (цепочку боксов ADD → SEL и боксы ФБ не принимает, docs/FORMAT-OUT.md)
    n = Graph("LD", 4)
    add = n.block("ADD", [("In1", n.invar("iStarts")), ("In2", n.invar("1"))], ["Out1"])
    n.outvar("iNext", (add, "Out1"))
    nets.append(n)
    n = Graph("LD", 5)
    sel = n.block(
        "SEL", [("G", n.invar("xStartPulse")), ("IN0", n.invar("iStarts")), ("IN1", n.invar("iNext"))], ["Out1"]
    )
    n.outvar("iStarts", (sel, "Out1"))
    nets.append(n)
    return pou("PRG_PumpInterlock", "program", decl, ld_body(nets))


# ------------------------------------------------------------------ CFC


def fb_dose_ctrl() -> str:
    decl = ("// ПИ-регулятор дозы: обратная связь интегратора, ограничение 0..100, выбор по разрешению\n"
            "FUNCTION_BLOCK FB_DoseCtrl\nVAR_INPUT\n    xEnable : BOOL;\n    rSp : REAL;\n    rPv : REAL;\n    rKp : REAL := 2.0;\n"
            "    rKi : REAL := 0.1;\nEND_VAR\nVAR_OUTPUT\n    rOut : REAL;\n    rErr : REAL;\nEND_VAR\n")  # fmt: skip
    g = Graph("CFC")
    sp, pv = g.invar("rSp"), g.invar("rPv")
    sub = g.block("SUB", [("In1", sp), ("In2", pv)], ["Out1"], eo=1)
    g.connector("E", (sub, "Out1"))
    ce1, kp = g.continuation("E"), g.invar("rKp")
    p = g.block("MUL", [("In1", ce1), ("In2", kp)], ["Out1"], eo=2)
    ce2, kiv = g.continuation("E"), g.invar("rKi")
    ki = g.block("MUL", [("In1", ce2), ("In2", kiv)], ["Out1"], eo=3)
    mn, mx, mn2, mx2 = g.invar("0.0"), g.invar("100.0"), g.invar("0.0"), g.invar("100.0")
    lim_id = g.peek(2)  # интегратор: ADD (4) читает выход LIMIT (5) прошлого цикла
    add_i = g.block("ADD", [("In1", (lim_id, "Out1")), ("In2", (ki, "Out1"))], ["Out1"], eo=4)
    lim_i = g.block("LIMIT", [("MN", mn), ("IN", (add_i, "Out1")), ("MX", mx)], ["Out1"], eo=5)
    assert lim_i == lim_id
    tot = g.block("ADD", [("In1", (p, "Out1")), ("In2", (lim_i, "Out1"))], ["Out1"], eo=6)
    lim = g.block("LIMIT", [("MN", mn2), ("IN", (tot, "Out1")), ("MX", mx2)], ["Out1"], eo=7)
    en, zero = g.invar("xEnable"), g.invar("0.0")
    sel = g.block("SEL", [("G", en), ("IN0", zero), ("IN1", (lim, "Out1"))], ["Out1"], eo=8)
    g.outvar("rOut", (sel, "Out1"), eo=9)
    g.outvar("rErr", (sub, "Out1"), eo=10)
    return pou("FB_DoseCtrl", "functionBlock", decl, cfc_body(g))


def fb_ratio_calc() -> str:
    decl = ("// Уставка расхода реагента по соотношению с фильтром: вход от блока с бо́льшим номером — прошлый цикл\n"
            "FUNCTION_BLOCK FB_RatioCalc\nVAR_INPUT\n    rFlowA : REAL;\n    rRatio : REAL := 0.02;\nEND_VAR\nVAR_OUTPUT\n"
            "    rFlowBSp : REAL;\n    rFilt : REAL;\nEND_VAR\n")  # fmt: skip
    g = Graph("CFC")
    fa, ra, c05 = g.invar("rFlowA"), g.invar("rRatio"), g.invar("0.5")
    raw = g.block("MUL", [("In1", fa), ("In2", ra)], ["Out1"], eo=1)
    flt_id = g.peek(3)  # SUB (2) читает выход фильтра ADD (4) — значение прошлого цикла
    dif = g.block("SUB", [("In1", (raw, "Out1")), ("In2", (flt_id, "Out1"))], ["Out1"], eo=2)
    half = g.block("MUL", [("In1", (dif, "Out1")), ("In2", c05)], ["Out1"], eo=3)
    flt = g.block("ADD", [("In1", (flt_id, "Out1")), ("In2", (half, "Out1"))], ["Out1"], eo=4)
    assert flt == flt_id, (flt, flt_id)
    g.outvar("rFilt", (flt, "Out1"), eo=5)
    g.outvar("rFlowBSp", (raw, "Out1"), eo=6)
    return pou("FB_RatioCalc", "functionBlock", decl, cfc_body(g, page_oriented=True))


# ------------------------------------------------------------------ SFC


def prg_fill_seq() -> str:
    decl = ("// Наполнение и нагрев бака: параллельные ветви, IEC-действия N, P, S/R, L, D, переход по времени шага\n"
            "PROGRAM PRG_FillSeq\nVAR_INPUT\n    xStart : BOOL;\n    xLevelHi : BOOL;\n    xTempOk : BOOL;\nEND_VAR\nVAR_OUTPUT\n"
            "    xValveIn : BOOL;\n    xHeater : BOOL;\n    xMixer : BOOL;\n    xAlarm : BOOL;\n    iBatches : INT;\n    iSeq : INT;\n"
            "    xFlush : BOOL;\nEND_VAR\n")  # fmt: skip
    s = Sfc()
    init = s.step("Init", None, initial=True)
    t1 = s.transition(init, "xStart")
    div = s.sim_div(t1)
    fill = s.step("Fill", (div, "0"))
    s.actions(fill, [("N", "ActFill", ""), ("L", "ActFlush", "T#30MS")])
    t2 = s.transition(fill, "xLevelHi")
    wf = s.step("WaitFill", t2)
    heat = s.step("Heat", (div, "1"))
    s.actions(heat, [("N", "ActZeta", ""), ("N", "ActHeat", ""), ("D", "ActAlarm", "T#50MS")])
    t3 = s.transition(heat, "xTempOk")
    wh = s.step("WaitHeat", t3)
    conv = s.sim_conv([wf, wh])
    t4 = s.transition(conv, "TRUE")
    mix = s.step("Mix", t4)
    s.actions(mix, [("S", "ActMixer", ""), ("P", "ActCount", ""), ("N", "ActAlpha", "")])
    t5 = s.transition(mix, "Mix.t >= T#40MS")
    done = s.step("Done", t5)
    s.actions(done, [("R", "ActMixer", "")])
    t6 = s.transition(done, "NOT xStart")
    s.jump_step(t6, "Init")
    actions = {
        "ActFill": "xValveIn := _ActFill.x;\n",
        "ActFlush": "xFlush := _ActFlush.x;\n",
        "ActHeat": "xHeater := _ActHeat.x;\n",
        "ActAlarm": "xAlarm := _ActAlarm.x;\n",
        "ActMixer": "xMixer := _ActMixer.x;\n",
        "ActCount": "IF _ActCount.x THEN\n    iBatches := iBatches + 1;\nEND_IF\n",
        "ActZeta": "IF _ActZeta.x THEN\n    iSeq := (iSeq * 10 + 2) MOD 10000;\nEND_IF\n",
        "ActAlpha": "IF _ActAlpha.x THEN\n    iSeq := (iSeq * 10 + 1) MOD 10000;\nEND_IF\n",
    }
    return pou("PRG_FillSeq", "program", decl, s.body(), actions)


def prg_cip_seq() -> str:
    decl = ("// Мойка CIP: выбор кислоты или щёлочи (альтернативные ветви), ополаскивание P и N, прыжок в начало\n"
            "PROGRAM PRG_CipSeq\nVAR_INPUT\n    xAcid : BOOL;\n    xCaustic : BOOL;\n    xDone : BOOL;\nEND_VAR\nVAR_OUTPUT\n"
            "    xAcidPump : BOOL;\n    xCausticPump : BOOL;\n    iRinseIn : INT;\n    xRinseValve : BOOL;\nEND_VAR\n")  # fmt: skip
    s = Sfc()
    idle = s.step("Idle", None, initial=True)
    div = s.sel_div(idle)
    ta = s.transition((div, "0"), "xAcid")
    acid = s.step("Acid", ta)
    s.actions(acid, [("N", "ActAcid", "")])
    tb = s.transition((div, "1"), "xCaustic")
    caus = s.step("Caustic", tb)
    s.actions(caus, [("N", "ActCaustic", "")])
    ta2 = s.transition(acid, "xDone")
    tb2 = s.transition(caus, "xDone")
    conv = s.sel_conv([ta2, tb2])
    rinse = s.step("Rinse", conv)
    s.actions(rinse, [("P", "ActRinseIn", ""), ("N", "ActRinseOut", "")])
    tr = s.transition(rinse, "NOT xDone")
    s.jump_step(tr, "Idle")
    actions = {
        "ActAcid": "xAcidPump := _ActAcid.x;\n",
        "ActCaustic": "xCausticPump := _ActCaustic.x;\n",
        "ActRinseIn": "IF _ActRinseIn.x THEN\n    iRinseIn := iRinseIn + 1;\nEND_IF\n",
        "ActRinseOut": "xRinseValve := _ActRinseOut.x;\n",
    }
    return pou("PRG_CipSeq", "program", decl, s.body(), actions)


# ------------------------------------------------------------------ IL

IL_POUS: list[tuple[str, str, str, str]] = [
    ("FB_PulseCount", "functionBlock",
     "// Счёт импульсов по фронту до предела; сброс уровнем\nFUNCTION_BLOCK FB_PulseCount\nVAR_INPUT\n    xPulse : BOOL;\n    xReset : BOOL;\n    iLimit : INT := 5;\nEND_VAR\nVAR_OUTPUT\n    iCount : INT;\n    xDone : BOOL;\nEND_VAR\nVAR\n    fbEdge : R_TRIG;\nEND_VAR\n",
     "    LD      xReset\n    JMPCN   lblCount\n    LD      0\n    ST      iCount\n    JMP     lblCheck\nlblCount:\n    CAL     fbEdge(CLK := xPulse)\n    LD      fbEdge.Q\n    AND(    iCount\n    LT      iLimit\n    )\n    JMPCN   lblCheck\n    LD      iCount\n    ADD     1\n    ST      iCount\nlblCheck:\n    LD      iCount\n    GE      iLimit\n    ST      xDone\n"),
    ("F_ScaleIL", "function",
     "// Масштаб с ограничением через F_Clamp (вызов функции с CR) и цикл JMPC назад\nFUNCTION F_ScaleIL : REAL\nVAR_INPUT\n    rIn : REAL;\nEND_VAR\nVAR\n    i : INT;\n    rAcc : REAL;\nEND_VAR\n",
     "    LD      0\n    ST      i\n    LD      0.0\n    ST      rAcc\nlblLoop:\n    LD      rAcc\n    ADD     rIn\n    ST      rAcc\n    LD      i\n    ADD     1\n    ST      i\n    LT      3\n    JMPC    lblLoop\n    LD      rAcc\n    F_Clamp 0.0, 100.0\n    ST      F_ScaleIL\n"),
]  # fmt: skip

PRG_IL_HOST = (
    "PRG_IlHost",
    "program",
    "// Обвязка для F_ScaleIL в сценарии\nPROGRAM PRG_IlHost\nVAR_INPUT\n    rIn : REAL;\nEND_VAR\nVAR_OUTPUT\n    rOut : REAL;\nEND_VAR\n",
    "rOut := F_ScaleIL(rIn := rIn);\n",
)


def graphics() -> list[str]:
    return [fb_level_alarm(), fb_valve_cmd(), prg_permissives(), prg_pump_interlock(), fb_dose_ctrl(), fb_ratio_calc(),
            prg_fill_seq(), prg_cip_seq()]  # fmt: skip


def il_pous() -> list[str]:
    return [pou(n, k, d, il_body(t)) for n, k, d, t in IL_POUS]


TASKS = [
    {
        "name": "TaskFast",
        "kind": "Cyclic",
        "interval": "T#10MS",
        "priority": 1,
        "pous": ["PRG_Main", "PRG_Permissives", "PRG_PumpInterlock"],
    },
    {"name": "TaskSlow", "kind": "Cyclic", "interval": "T#200MS", "priority": 5, "pous": ["PRG_FillSeq", "PRG_CipSeq"]},
    {
        "name": "TaskAlarm",
        "kind": "Event",
        "interval": "",
        "priority": 3,
        "event": "GVL_IO.xLevelHigh",
        "pous": ["PRG_OopDemo"],
    },
]

# Случаи со сценариями: (каталог, POU, язык, период стенда, мс)
CASES = [
    ("st/FB_AnalogScale", "FB_AnalogScale", "ST"),
    ("st/FB_FlowTotal", "FB_FlowTotal", "ST"),
    ("st/PRG_TonQuant", "PRG_TonQuant", "ST"),
    ("fbd/FB_LevelAlarm", "FB_LevelAlarm", "FBD"),
    ("fbd/FB_ValveCmd", "FB_ValveCmd", "FBD"),
    ("ld/PRG_Permissives", "PRG_Permissives", "LD"),
    ("ld/PRG_PumpInterlock", "PRG_PumpInterlock", "LD"),
    ("cfc/FB_DoseCtrl", "FB_DoseCtrl", "CFC"),
    ("cfc/FB_RatioCalc", "FB_RatioCalc", "CFC"),
    ("sfc/PRG_FillSeq", "PRG_FillSeq", "SFC"),
    ("sfc/PRG_CipSeq", "PRG_CipSeq", "SFC"),
    ("il/FB_PulseCount", "FB_PulseCount", "IL"),
    ("il/PRG_IlHost", "PRG_IlHost", "IL"),
    ("oop/PRG_OopDemo", "PRG_OopDemo", "OOP"),
]
