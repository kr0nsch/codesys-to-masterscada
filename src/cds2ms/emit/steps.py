"""MANUAL_STEPS.md, tasks.md, mapping.{json,csv}, io-binding.csv.

Пункты меню — только со страниц справки (с адресом); где справка молчит — «сверить».
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .. import TOOL, __version__
from ..cdsfront.lower import LoweredProject
from ..rules.engine import Analysis
from ..rules.findings import Finding
from ..transform.master_st import FixedObject

HW = "https://help.iek-digital.ru/Help-web/"


def _minutes(fs: list[Finding]) -> int:
    return int(round(sum(f.minutes[1] for f in fs)))


def manual_steps(lp: LoweredProject, an: Analysis, fixed: dict[str, FixedObject], name: str, fix: str) -> str:
    p = lp.project
    fs = an.findings
    by_rule: dict[str, list[Finding]] = {}
    for f in fs:
        by_rule.setdefault(f.rule, []).append(f)
    out: list[str] = [
        f"# Ручные шаги переноса {p.name or name} в MasterSCADA 4D 1.3.10",
        "",
        f"создано {TOOL} {__version__} · {p.source_file.replace(chr(92), '/').rsplit('/', 1)[-1]} · SHA-256 {p.source_sha256}",
        "",
        "Пункты меню взяты со страниц справки 1.3.10 (адрес у шага). Где справка молчит — пометка «сверить». У шага —",
        "ожидаемый результат и минуты (оценка, не замер).",
        "",
        "## 1. Исполнительная система на ПЛК (≈30 мин)",
        "",
        "Если ПЛК ОВЕН работал под CODESYS RT: перепрошить на MasterPLC, получить лицензию RT, проверить поддержку",
        "модулей Mx210 — сверить по https://support.mps-soft.ru/PLC_Library/owen.html. Ожидаемо: узел ПЛК виден в",
        "MasterSCADA 4D Monitor.",
        "",
        f"## 2. Проект и узел (≈10 мин) — {HW}uzel.html",
        "",
        "Создать проект, добавить узел ПЛК из библиотеки вендора (ОВЕН ПЛК210/ПЛК200). Ожидаемо: узел в дереве «Система».",
        "",
        f"## 3. Импорт PLCopen XML (≈10 мин) — {HW}-plcopenxml.html (страница прочитана 19.10.2026)",
        "",
        f"Контекстное меню узла → «Импортирование PLCOpenXML» → `import/{name}.plcopen.xml`. Ожидаемо по справке: типы,",
        "ФБ и функции — в локальную библиотеку, программы и глобальные параметры — в узел. Куда лягут globalVars и в",
        "какой задаче окажутся программы — справка не описывает: сверить (пробы P-IMP-01…06, `probe/README.md`).",
        "",
        f"## 4. «Проверить» весь проект (≈5 мин) — {HW}globalnye_peremennye.html",
        "",
        "Проверять проект целиком: проверка одной программы даёт ложное «Неизвестная переменная» на глобальных.",
        "Ожидаемо: ошибки только в POU с пунктами «вручную» ниже. Ошибки записать дословно в probe/RESULTS.csv.",
        "",
    ]
    step = 5
    if p.tasks or len([x for x in p.pous if x.kind == "program"]) > 1:
        out += [
            f"## {step}. Задачи и порядок программ (≈{5 + 3 * len(p.tasks)} мин) — {HW}zadachi.html",
            "",
            "Вариант А: элемент «Скрипт» (библиотека) → вставить `script/DoAction.body.cs` в метод `DoAction()` → «Выполнить",
            "программу». Скрипт создаёт задачи и объекты-диспетчеры `migTask_<T>`, которые вызывают программы узла в",
            f"порядке CODESYS ({HW}vyzov_programm_obektov.html). Ожидаемо: дерево совпадает с `script/tree.json`.",
            "Вариант Б: задачи вручную по `tasks.md`, программы — «Назначить в задачу», порядок — Ctrl+↑/↓.",
            "Приоритет задачи скрипт не трогает: неверный приоритет может повесить ПЛК «вплоть до перепрошивки».",
            "",
        ]
        step += 1
    if an.io:
        out += [
            f"## {step}. Каналы и связи ввода-вывода (≈{3 * len(an.io)} мин) — {HW}variableitem.html",
            "",
            f"Создать протоколы и каналы модулей, связать с параметрами по `io-binding.csv` ({len(an.io)} строк). Вход:",
            "параметр получает значение от канала (DataSource), выход: AddLink — направление сверить (проба P-CS-02).",
            "",
        ]
        step += 1
    if any(f.rule in ("MS-RET-01", "MS-DECL-06") for f in fs):
        out += [
            f"## {step}. Сохранение состояния (≈10 мин) — {HW}sohranenie_sostoyania.html",
            "",
            "Для RETAIN-параметров — «Сохранять = Да»; способ записи (периодический/при остановке) и «время актуальности»",
            "выбрать по объекту. InOut-параметры программ не сохраняются.",
            "",
        ]
        step += 1
    out += [
        f"## {step}. Эмуляция (≈20 мин) — {HW}emulyacia.html",
        "",
        "Запустить эмуляцию с демо-RT (1 час) и прогнать сценарии (`trace/`, если есть). Ожидаемо: расхождения только из",
        "`expected-divergences` отчёта.",
        "",
    ]
    step += 1
    manual = [f for f in fs if f.outcome in ("manual", "impossible")]
    if manual:
        out += [f"## {step}. Пункты «вручную» и «невозможно» (≈{_minutes(manual)} мин, модель)", "",
                "| Правило | POU | Место | Что сделать |", "|---|---|---|---|"]  # fmt: skip
        for f in manual:
            place = f"{f.file}:{f.line}" if f.line else f.file
            out.append(f"| {f.rule} | {f.pou or ''} | {place} | {f.message} |")
        out.append("")
        step += 1
    verify = [f for f in fs if f.outcome == "verify"]
    if verify:
        out += [f"## {step}. Пункты «проверить» (≈{_minutes(verify)} мин)", "",
                "Поведение цели в справке не описано — проба в `probe/` даёт ответ за минуты.", "",
                "| Правило | POU | Что |", "|---|---|---|"]  # fmt: skip
        for f in verify:
            out.append(f"| {f.rule} | {f.pou or ''} | {f.message} |")
        out.append("")
        step += 1
    if an.renames:
        out += [
            f"## Переименования ({len(an.renames)})",
            "",
            "| Объект | Было | Стало | Правило |",
            "|---|---|---|---|",
        ]
        seen = set()
        for obj, old, new, rid in an.renames:
            if (obj, old) in seen:
                continue
            seen.add((obj, old))
            out.append(f"| {obj} | `{old}` | `{new}` | {rid} |")
        out.append("")
    out += [
        "## Не переносится",
        "",
        "- Визуализация CODESYS (MS-VISU-01, невозможно): окна MasterSCADA 4D рисуются заново.",
        "- Дерево устройств, Modbus/OPC UA-конфигураторы (MS-IO-01): каналы создаёт человек.",
        "- AlarmManager, тренды, рецептуры (MS-ALARM-01): по инвентарю.",
        "",
        f"Уровень правок: `--fix {fix}`.",
    ]
    return "\n".join(out) + "\n"


def tasks_md(lp: LoweredProject, period_default: int) -> str:
    p = lp.project
    out = ["# Задачи: CODESYS → MasterSCADA 4D", "",
           f"Период задачи MS4D по умолчанию {period_default} мс, транслятор Lua; приоритет не переносится (MS-EXEC-06).", "",
           "| Задача CODESYS | Вид | Период, мс | Приоритет | Программы по порядку | В MS4D |", "|---|---|---|---|---|---|"]  # fmt: skip
    for t in p.tasks:
        kind = t.kind
        if kind.lower() in ("event", "freewheeling", "status"):
            ms4d = f"циклическая {int(t.interval_ms or period_default)} мс + фронт{' ' + t.event if t.event else ''}"
        elif kind.lower() == "externalevent":
            ms4d = "невозможно (внешнее событие)"
        else:
            ms4d = f"задача {int(t.interval_ms or period_default)} мс, объект migTask_{t.name}"
        out.append(
            f"| {t.name} | {kind} | {t.interval_ms if t.interval_ms is not None else '—'} | "
            f"{t.priority if t.priority is not None else '—'} | {', '.join(t.pous) or '—'} | {ms4d} |"
        )
    if not p.tasks:
        out.append("| — | — | — | — | все программы | основная задача узла (программы прямо в узле) |")
    return "\n".join(out) + "\n"


def mapping(lp: LoweredProject, an: Analysis, fixed: dict[str, FixedObject]) -> list[dict[str, Any]]:
    p = lp.project
    rows: list[dict[str, Any]] = []
    worst: dict[str, str] = {}
    from ..rules.registry import SEVERITY

    for f in an.findings:
        if f.pou:
            k = f.pou.lower()
            if k not in worst or SEVERITY[f.outcome] > SEVERITY[worst[k]]:
                worst[k] = f.outcome
    for x in lp.pous:
        target = {
            "program": "программа узла",
            "functionBlock": "ФБ локальной библиотеки",
            "function": "функция локальной библиотеки",
        }[x.kind]
        rows.append({"codesys": f"{x.kind} {x.name}", "language": x.lang, "masterscada": target,
                     "channel": "PLCopen XML (types/pous)", "outcome": worst.get(x.name.lower(), "auto"),
                     "source": "https://help.iek-digital.ru/Help-web/-plcopenxml.html"})  # fmt: skip
    for g in p.gvls:
        rows.append({"codesys": f"GVL {g.name}", "language": "DECL", "masterscada": f"параметры узла {g.name}_<имя>",
                     "channel": "PLCopen XML (globalVars)", "outcome": worst.get(g.name.lower(), "auto"),
                     "source": "https://help.iek-digital.ru/Help-web/globalnye_peremennye.html"})  # fmt: skip
    for d in p.duts:
        rows.append({"codesys": f"DUT {d.name}", "language": "DECL", "masterscada": "тип данных локальной библиотеки",
                     "channel": "PLCopen XML (dataTypes)", "outcome": worst.get(d.name.lower(), "auto"),
                     "source": "https://help.iek-digital.ru/Help-web/noviy_tip_parametra.html"})  # fmt: skip
    for t in p.tasks:
        rows.append({"codesys": f"Task {t.name}", "language": "PROJECT", "masterscada": f"задача {t.name} + объект migTask_{t.name}",
                     "channel": "C#-скрипт (AddTask, AddObject, AddProgramST)", "outcome": "review",
                     "source": "https://help.iek-digital.ru/Help-web/controlleritem.html"})  # fmt: skip
    for b in an.io:
        rows.append({"codesys": f"{b.pou}.{b.var} AT {b.address}", "language": "DECL", "masterscada": f"параметр {b.param} ← канал",
                     "channel": "io-binding.csv (связь вручную)", "outcome": "review" if b.direction != "memory" else "manual",
                     "source": "https://help.iek-digital.ru/Help-web/variableitem.html"})  # fmt: skip
    return rows


def mapping_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps({"format": "cds2ms-mapping/1", "rows": rows}, ensure_ascii=False, indent=2) + "\n"


def mapping_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, ["codesys", "language", "masterscada", "channel", "outcome", "source"], lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def io_binding_csv(an: Analysis) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["object", "variable", "parameter", "address", "direction", "type", "channel", "source"])
    for b in an.io:
        w.writerow([b.pou, b.var, b.param, b.address, b.direction, b.type, "", f"{b.file}:{b.line}"])
    return buf.getvalue()
