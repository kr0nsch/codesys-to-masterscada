"""Пробник для владельца MasterSCADA 4D: минимальный файл на каждую конструкцию с исходом verify или
статусом unknown, ``README.md`` (порядок, минуты) и ``RESULTS.csv`` (столбцы семейства, 00-INDEX §4.9)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .. import __version__
from ..ir.model import Body, Dut, Gvl, Origin, Pou, Project, Task
from ..transform.master_st import FixedObject
from . import plcopen as emit_xml

_ORIGIN = Origin("probe")

# (probe_id, конструкция, файл, ожидание) — порядок как в README
PROBES: list[tuple[str, str, str, str]] = [
    ("P-IMP-01", "импорт: ns tc6_0201, globalVars в resource", "import/P-IMP-01.xml", "place:<узел> — ФБ/функции в локальной библиотеке, программы и глобальные в узле"),
    ("P-IMP-02", "импорт: globalVars в configuration", "import/P-IMP-02-config-globals.xml", "place:<куда легли глобальные>"),
    ("P-IMP-03", "импорт: task + pouInstance", "import/P-IMP-03-tasks.xml", "place:<в какой задаче программы>"),
    ("P-IMP-04", "импорт: ns tc6_0200", "import/P-IMP-04-ns0200.xml", "ok или error:<текст>"),
    ("P-IMP-05", "импорт: сырой экспорт CODESYS с addData", "import/P-IMP-05-codesys-raw.xml", "error или ok с потерями — записать дословно"),
    ("P-IMP-06", "импорт: тело в xhtml:p", "import/P-IMP-06-xhtml-p.xml", "ok или error:<текст>"),
    ("P-IMP-07", "импорт: глобальные GVL_x без папки", "import/P-IMP-07-flat-globals.xml", "place:<имя параметра>"),
    ("P-ST-01", "var_inout", "dialect/P-ST.xml: FB_ProbeInOut", "ok; значение iCount после вызова = 1"),
    ("P-ST-02", "CASE по ENUM, явные значения, E_ProbeState.Run", "dialect/P-ST.xml: PRG_ProbeEnum", "ok; iOut = 10"),
    ("P-ST-03", "EN как имя входа ФБ", "dialect/P-ST.xml: FB_ProbeEn", "error (EN — ключевое слово) или ok"),
    ("P-ST-04", "имена a__b, local, end", "dialect/P-ST.xml: PRG_ProbeNames", "error на a__b; local/end — сверить"),
    ("P-ST-05", "префикс Локальная.", "dialect/P-ST.xml: PRG_ProbePrefix", "ok"),
    ("P-ST-06", "экземпляр ФБ в GVL, ARRAY OF FB, ФБ как var_inout", "dialect/P-ST.xml: PRG_ProbeFbArray", "сверить"),
    ("P-ST-07", "retain-атрибут XML", "dialect/P-ST.xml: GVL_ProbeRetain", "Сохранять = Да у параметра"),
    ("P-ST-08", "globalVars constant", "dialect/P-ST.xml: GVL_ProbeConst", "place:<куда легла константа>"),
    ("P-RT-01", "32767 + 1 в INT", "runtime/P-RT.xml: PRG_ProbeInt", "value:<iOvf> (CODESYS: -32768)"),
    ("P-RT-02", "-7 / 2, -7 MOD 2, /0 для INT и REAL", "runtime/P-RT.xml: PRG_ProbeDiv", "value:<iDiv;iMod> (CODESYS: -3; -1); /0 — отдельно PRG_ProbeDivZero"),
    ("P-RT-03", "REAL_TO_INT(-1.5), (2.5), REAL 16777217.0", "runtime/P-RT.xml: PRG_ProbeReal", "value:<iM15;iP25;rBig> (CODESYS: -2; 3; 16777216)"),
    ("P-RT-04", "T#0ms - T#1ms, T#25d", "runtime/P-RT.xml: PRG_ProbeTime", "value:<tNeg;tBig> (CODESYS: T#49d17h2m47s295ms; T#25d)"),
    ("P-RT-05", "LEN('Привет')", "runtime/P-RT.xml: PRG_ProbeLen", "value:<iLen> (CODESYS: 6)"),
    ("P-RT-06", "DT по умолчанию", "runtime/P-RT.xml: PRG_ProbeDt", "value:<dtDefault> (справка MS4D: DT#0001-01-01-00:00:00)"),
    ("P-RT-07", "[10] у ARRAY[0..9]", "runtime/P-RT.xml: PRG_ProbeArray", "value:<xIsNull> (справка: NULL)"),
    ("P-RT-08", "FOR: BY -1, счётчик после цикла, изменение границы в теле", "runtime/P-RT.xml: PRG_ProbeFor", "value:<iSum;iAfter;iIter> (CODESYS: 55; 0; 11)"),
    ("P-RT-09", "TON 150 мс в задаче 100 мс", "runtime/P-RT.xml: PRG_ProbeTon", "value:<tFirstQ> — ожидаемо 200 мс (MS-EXEC-01)"),
    ("P-RT-10", "METHOD в режиме вызова", "runtime/P-RT.xml: PRG_ProbeMethod", "value:<rOut> = 4.0"),
    ("P-RT-11", "SFC N/P1 по циклам", "runtime/SFC-recipe.md", "value:<счётчики по циклам> — сдвиг на цикл по справке"),
    ("P-RT-12", "TON на цепи Master LD при падении цепи", "runtime/LD-recipe.md", "value:<Q/ET после падения цепи>"),
    ("P-RT-13", "диспетчер: объект вызывает OnCall-программу узла", "script/DoAction.body.cs", "ok; синтаксис полного имени программы"),
    ("P-CS-01", "вставка DoAction.body.cs, дерево против tree.json", "script/DoAction.body.cs", "ok; дерево = script/expected-tree.json"),
    ("P-CS-02", "направление AddLink / DataSource", "script/README.md", "сверить по дереву связей"),
    ("P-CS-03", "экспорт .ST как образец формата", "—", "файл .ST приложить к RESULTS (формат заголовка)"),
]  # fmt: skip

_DIALECT: list[tuple[str, str, str, str]] = [
    ("FB_ProbeInOut", "functionBlock", "FUNCTION_BLOCK FB_ProbeInOut\nVAR_INOUT\n    iCount : INT;\nEND_VAR\n", "iCount := iCount + 1;\n"),
    ("PRG_ProbeInOut", "program", "PROGRAM PRG_ProbeInOut\nVAR\n    fb : FB_ProbeInOut;\n    iCount : INT;\nEND_VAR\n", "fb(iCount := iCount);\n"),
    ("PRG_ProbeEnum", "program", "PROGRAM PRG_ProbeEnum\nVAR\n    eState : E_ProbeState := E_ProbeState.Run;\n    iOut : INT;\nEND_VAR\n",
     "CASE eState OF\n    E_ProbeState.Idle:\n        iOut := 0;\n    E_ProbeState.Run:\n        iOut := 10;\nELSE\n    iOut := -1;\nEND_CASE;\n"),
    ("FB_ProbeEn", "functionBlock", "FUNCTION_BLOCK FB_ProbeEn\nVAR_INPUT\n    EN : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xQ : BOOL;\nEND_VAR\n", "xQ := EN;\n"),
    ("PRG_ProbeNames", "program", "PROGRAM PRG_ProbeNames\nVAR\n    a__b : INT;\n    local : INT;\n    end : INT;\nEND_VAR\n", "a__b := 1;\nlocal := 2;\nend := a__b + local;\n"),
    ("PRG_ProbePrefix", "program", "PROGRAM PRG_ProbePrefix\nVAR\n    fb : Локальная.FB_ProbeEn;\n    xOut : BOOL;\nEND_VAR\n", "fb(EN := TRUE);\nxOut := fb.xQ;\n"),
    ("PRG_ProbeFbArray", "program", "PROGRAM PRG_ProbeFbArray\nVAR\n    aFb : ARRAY[0..1] OF FB_ProbeEn;\n    xOut : BOOL;\nEND_VAR\n", "aFb[1](EN := TRUE);\nxOut := aFb[1].xQ AND GVL_ProbeFb_fbShared.xQ;\n"),
]  # fmt: skip

_RUNTIME: list[tuple[str, str, str, str]] = [
    ("PRG_ProbeInt", "program", "PROGRAM PRG_ProbeInt\nVAR\n    iMax : INT := 32767;\n    iOvf : INT;\nEND_VAR\n", "iOvf := iMax + 1;\n"),
    ("PRG_ProbeDiv", "program", "PROGRAM PRG_ProbeDiv\nVAR\n    iA : INT := -7;\n    iB : INT := 2;\n    iDiv : INT;\n    iMod : INT;\nEND_VAR\n", "iDiv := iA / iB;\niMod := iA MOD iB;\n"),
    ("PRG_ProbeDivZero", "program", "PROGRAM PRG_ProbeDivZero\nVAR\n    iA : INT := 7;\n    iZero : INT;\n    iRes : INT;\n    rRes : REAL;\nEND_VAR\n", "iRes := iA / iZero;\nrRes := 1.0 / INT_TO_REAL(iZero);\n"),
    ("PRG_ProbeReal", "program", "PROGRAM PRG_ProbeReal\nVAR\n    iM15 : INT;\n    iP25 : INT;\n    rBig : REAL;\nEND_VAR\n", "iM15 := REAL_TO_INT(-1.5);\niP25 := REAL_TO_INT(2.5);\nrBig := 16777217.0;\n"),
    ("PRG_ProbeTime", "program", "PROGRAM PRG_ProbeTime\nVAR\n    tZero : TIME := T#0MS;\n    tNeg : TIME;\n    tBig : TIME;\nEND_VAR\n", "tNeg := tZero - T#1MS;\ntBig := T#25D;\n"),
    ("PRG_ProbeLen", "program", "PROGRAM PRG_ProbeLen\nVAR\n    iLen : INT;\nEND_VAR\n", "iLen := LEN('Привет');\n"),
    ("PRG_ProbeDt", "program", "PROGRAM PRG_ProbeDt\nVAR\n    dtDefault : DT;\n    xIs1970 : BOOL;\nEND_VAR\n", "xIs1970 := dtDefault = DT#1970-01-01-00:00:00;\n"),
    ("PRG_ProbeArray", "program", "PROGRAM PRG_ProbeArray\nVAR\n    aVal : ARRAY[0..9] OF INT;\n    i : INT := 10;\n    xIsNull : BOOL;\nEND_VAR\n", "xIsNull := aVal[i] = NULL;\n"),
    ("PRG_ProbeFor", "program", "PROGRAM PRG_ProbeFor\nVAR\n    i : INT;\n    iSum : INT;\n    iAfter : INT;\n    iIter : INT;\n    iLast : INT := 5;\nEND_VAR\n",
     "iSum := 0;\nFOR i := 10 TO 0 BY -1 DO\n    iSum := iSum + i;\nEND_FOR;\niAfter := i;\niIter := 0;\nFOR i := 1 TO iLast DO\n    iIter := iIter + 1;\n    iLast := 3;\nEND_FOR;\n"),
    ("PRG_ProbeTon", "program", "PROGRAM PRG_ProbeTon\nVAR\n    fbTon : TON;\n    tStart : TIME;\n    tFirstQ : TIME;\n    xDone : BOOL;\nEND_VAR\n",
     "fbTon(IN := TRUE, PT := T#150MS);\nIF fbTon.Q AND NOT xDone THEN\n    tFirstQ := fbTon.ET;\n    xDone := TRUE;\nEND_IF;\n"),
    ("FB_ProbeMethod", "functionBlock", "FUNCTION_BLOCK FB_ProbeMethod\nVAR_INPUT\n    migCall : INT;\n    Scale_rIn : REAL;\nEND_VAR\nVAR_OUTPUT\n    Scale_ret : REAL;\nEND_VAR\nVAR\n    rGain : REAL := 2.0;\nEND_VAR\n",
     "IF migCall <> 0 THEN\n    CASE migCall OF\n        1:\n            Scale_ret := Scale_rIn * rGain;\n    END_CASE;\n    migCall := 0;\n    RETURN;\nEND_IF;\n"),
    ("PRG_ProbeMethod", "program", "PROGRAM PRG_ProbeMethod\nVAR\n    fb : FB_ProbeMethod;\n    rOut : REAL;\nEND_VAR\n", "fb(migCall := 1, Scale_rIn := 2.0);\nrOut := fb.Scale_ret;\n"),
]  # fmt: skip


def _project(
    name: str, items: list[tuple[str, str, str, str]], gvls: list[tuple[str, str]], duts: list[tuple[str, str]]
) -> tuple[Project, dict[str, FixedObject]]:
    p = Project(name, "plcopen-xml", name, "0" * 64)
    fixed: dict[str, FixedObject] = {}
    for n, kind, decl, body in items:
        p.pous.append(Pou(n, kind, decl, Body("ST", text=body), _ORIGIN))
        fixed[n.lower()] = FixedObject(n, "pou", decl, body, pou_kind=kind)
    for n, text in gvls:
        p.gvls.append(Gvl(n, text, _ORIGIN))
        fixed[f"gvl:{n.lower()}"] = FixedObject(n, "gvl", text, "")
    for n, text in duts:
        p.duts.append(Dut(n, text, _ORIGIN))
        fixed[f"dut:{n.lower()}"] = FixedObject(n, "dut", text, "")
    return p, fixed


def results_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["probe_id", "construct", "file", "expected", "observed", "ide", "ide_version", "date", "notes"])
    for pid, construct, file, expected in PROBES:
        w.writerow([pid, construct, file, expected, "not-run", "MasterSCADA 4D", "1.3.10", "", ""])
    return buf.getvalue()


README = """# Пробник MasterSCADA 4D 1.3.10 (cds2ms {version})

Каждая проба — минимальный файл на конструкцию, поведение которой справка 1.3.10 не описывает (исход
«проверить» в отчёте). Результат — строка в `RESULTS.csv`: `observed` = `ok`, `error:<текст дословно>`,
`value:<значение>`, `place:<путь в дереве>` или `not-run`. Затем `cds2ms profiles apply-probe RESULTS.csv --write`
меняет статусы профиля (отдельным коммитом). Время — без установки DT и регистрации.

## 1. Импорт (≈35 мин)

Узел ПЛК → «Импортирование PLCOpenXML» (https://help.iek-digital.ru/Help-web/-plcopenxml.html) — по очереди
файлы `import/P-IMP-0N*.xml`, каждый в новый проект. Записать: что и куда легло в дереве, пункт меню дословно, в
какой задаче оказались программы. P-IMP-05 — сырой экспорт CODESYS с addData (как есть).

## 2. Диалект и «Проверить» (≈40 мин)

Импорт `dialect/P-ST.xml`, затем «Проверить» проект целиком (проверка одной программы даёт ложное «Неизвестная
переменная» на глобальных). Ошибки — дословно, по POU: P-ST-01…08. Те же POU лежат файлами `.ST` в `dialect/st/`
для «Импорт ST текста».

## 3. Исполнение в эмуляции, одна сессия демо-RT 1 ч (≈45 мин)

Импорт `runtime/P-RT.xml`, программы — в основную задачу узла (100 мс), эмуляция
(https://help.iek-digital.ru/Help-web/emulyacia.html). Значения выходов (P-RT-01…10) — в `value:`. PRG_ProbeDivZero
запускать последним: деление на ноль может остановить задачу. P-RT-11 (SFC N/P1) и P-RT-12 (TON на цепи Master
LD) рисуются вручную по `runtime/SFC-recipe.md` и `runtime/LD-recipe.md`. P-RT-13 — после скрипта (раздел 4).

## 4. Скрипт C# (≈20 мин)

Элемент «Скрипт» в библиотеке → вставить `script/DoAction.body.cs` в метод `DoAction()` → «Выполнить программу».
P-CS-01: дерево против `script/expected-tree.json`. P-CS-02: создать канал и проверить, в какую сторону идёт
значение у `AddLink` и `DataSource`. P-CS-03: «Экспорт ST текста» любой проверенной программы — файл приложить.
"""

SFC_RECIPE = """# P-RT-11: SFC N/P1 по циклам (рисуется вручную)

Программа SFC: шаг Init → переход `xGo` → шаг S1 → переход `xBack` → Init. У S1 два действия на ST:
`iN := iN + 1;` с квалификатором N и `iP := iP + 1;` с квалификатором P1. Задача 100 мс.
Включить `xGo` и записать по циклам iN, iP; затем `xBack`. По справке (HW:dialog_redaktirovaniya_sfc-deystviya):
N в первом цикле не выполняется и выполняется ещё раз после деактивации, P1 — один раз с задержкой на цикл.
В CODESYS main-действие шага выполняется с первого цикла и не выполняется после деактивации (MS-SFC-01).
"""

LD_RECIPE = """# P-RT-12: TON на цепи Master LD при падении цепи (рисуется вручную)

Цепь: контакт `xIn` → ФБ TON (PT = T#1S) → катушка `xQ`. Включить `xIn` на 0,5 с и выключить. Записать Q и ET
после падения цепи. По справке (HW:ld-blok) «in» ФБ на цепи — это En: при ложной цепи блок, вероятно, не
вызывается и ET замирает; в CODESYS TON на цепи без EN вызывается каждый цикл с IN := FALSE и сбрасывается (MS-LD-01).
"""


def write_probe_kit(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {}
    dutl = [("E_ProbeState", "TYPE E_ProbeState :\n(\n    Idle := 0,\n    Run := 10,\n    Fault := 20\n);\nEND_TYPE\n")]
    gv = [
        ("GVL_ProbeRetain", "VAR_GLOBAL RETAIN\n    iRetained : INT;\nEND_VAR\n"),
        ("GVL_ProbeConst", "VAR_GLOBAL CONSTANT\n    iLimit : INT := 100;\nEND_VAR\n"),
        ("GVL_ProbeFb", "VAR_GLOBAL\n    fbShared : FB_ProbeEn;\nEND_VAR\n"),
    ]
    p, fixed = _project("P_ST", _DIALECT, gv, dutl)
    files["dialect/P-ST.xml"] = emit_xml.build(p, fixed, "0" * 64)
    for n, _k, decl, body in _DIALECT:
        end = "END_FUNCTION_BLOCK" if decl.startswith("FUNCTION_BLOCK") else "END_PROGRAM"
        files[f"dialect/st/{n}.ST"] = f"{decl}{body}{end}\n".encode()
    pr, fixed_r = _project("P_RT", _RUNTIME, [], [])
    files["runtime/P-RT.xml"] = emit_xml.build(pr, fixed_r, "0" * 64)
    files["runtime/SFC-recipe.md"] = SFC_RECIPE.encode("utf-8")
    files["runtime/LD-recipe.md"] = LD_RECIPE.encode("utf-8")
    base, fixed_b = _project("P_IMP", _DIALECT[:2], gv[:2], [])
    files["import/P-IMP-01.xml"] = emit_xml.build(base, fixed_b, "0" * 64)
    files["import/P-IMP-02-config-globals.xml"] = emit_xml.build(base, fixed_b, "0" * 64, variant="config-globals")
    base.tasks = [Task("MainTask", "Cyclic", 100.0, 1, ["PRG_ProbeInOut"], _ORIGIN)]
    files["import/P-IMP-03-tasks.xml"] = emit_xml.build(base, fixed_b, "0" * 64, variant="tasks")
    files["import/P-IMP-04-ns0200.xml"] = emit_xml.build(base, fixed_b, "0" * 64, ns=emit_xml.NS_0200)
    files["import/P-IMP-06-xhtml-p.xml"] = emit_xml.build(base, fixed_b, "0" * 64, variant="xhtml-p")
    files["import/P-IMP-07-flat-globals.xml"] = emit_xml.build(base, fixed_b, "0" * 64, variant="flat-globals")
    files["README.md"] = README.format(version=__version__).encode("utf-8")
    files["RESULTS.csv"] = results_csv().encode("utf-8")
    for name, data in files.items():
        f = out / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    return len(files)
