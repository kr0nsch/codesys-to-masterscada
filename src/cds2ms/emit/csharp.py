"""C#-скрипт для элемента «Скрипт» MasterSCADA 4D: тело ``DoAction()`` и обёртка для макета.

Только внешняя объектная модель (``RootItemModel.System/Objects``), у каждого вызова — адрес страницы
справки. C# 5: без ``?.``, интерполяции строк и ``string?`` (в примерах справки они есть — не копируются).
Идемпотентно: поиск перед созданием (``FindChildByName``, ``FindController``, ``FindObject``).

Что делает: задачи CODESYS → ``AddTask`` + ``Period`` (приоритет не трогает, ``ResetPriority``); программы,
вызываемые диспетчером, → ``ExecutionMethod = OnCall``; на задачу — объект ``migTask_<T>`` с ``TaskRef``,
``ControllerRef`` и ST-программой, вызывающей программы узла в порядке CODESYS (синтаксис полного имени
программы узла — [L], проба P-RT-13).
"""

from __future__ import annotations

import json
from typing import Any

from .. import TOOL, __version__
from ..ir.model import Project

HW = "https://help.iek-digital.ru/Help-web/"


def _cs(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _ident(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s)


def plan(project: Project, node: str, period_default: int = 100) -> dict[str, Any]:
    """Ожидаемое дерево (предпросмотр): задачи, диспетчеры, программы OnCall."""
    tasks = []
    for t in project.tasks:
        if t.kind.lower() == "externalevent":
            continue
        period = int(t.interval_ms) if t.interval_ms else period_default
        progs = [p for p in t.pous if project.pou(p) is not None]
        tasks.append({"name": t.name, "period": period, "kind": t.kind, "programs": progs})
    if not tasks:
        progs = [p.name for p in project.pous if p.kind == "program"]
        if len(progs) > 1:
            tasks.append({"name": "Main", "period": period_default, "kind": "Cyclic", "programs": progs})
    return {"node": node, "tasks": tasks}


def body(project: Project, node: str, sha256: str, period_default: int = 100) -> str:
    pl = plan(project, node, period_default)
    src = project.source_file.replace("\\", "/").rsplit("/", 1)[-1]
    out: list[str] = [
        f"// создано {TOOL} {__version__} · {src} · SHA-256 {sha256}",
        "// Тело метода DoAction() элемента «Скрипт» MasterSCADA 4D (" + HW + "script_c.html).",
        "// Идемпотентно: повторный запуск ничего не дублирует. Приоритеты задач не трогает (" + HW + "zadachi.html).",
        "var root = this.RootItemModel; // " + HW + "obshie_svedenia_c.html",
        f'ControllerItem node = root.System.FindController("{_cs(node)}"); // {HW}systemitem.html',
        "if (node == null)",
        "{",
        f'    this.WriteConsole("cds2ms: узел {_cs(node)} не найден — добавьте узел ПЛК из библиотеки вендора (MANUAL_STEPS, шаг 2)");',
        "    return;",
        "}",
        "int created = 0;",
    ]
    oncall: list[str] = []
    for i, t in enumerate(pl["tasks"], 1):
        tv = f"task{i}"
        out += [
            f"// задача {t['name']} (CODESYS: {t['kind']}, {t['period']} мс)",
            f'TaskItem {tv} = node.FindChildByName("{_cs(t["name"])}") as TaskItem; // {HW}item.html',
            f'if ({tv} == null) {{ {tv} = node.AddTask("{_cs(t["name"])}"); created++; }} // {HW}controlleritem.html',
            f"{tv}.Period = {t['period']}; // {HW}taskitem.html",
            f"{tv}.ResetTranslatorType(); // по умолчанию Lua ({HW}zadachi.html)",
            f"{tv}.ResetPriority(); // приоритет не переносится: неверный может повесить ПЛК",
        ]
        dname = f"migTask_{_ident(t['name'])}"
        ov = f"disp{i}"
        sv = f"prg{i}"
        calls = "".join(f"{node}.{p}();" + "\n" for p in t["programs"])
        out += [
            f'ObjectItem {ov} = root.Objects.FindObject("{dname}"); // {HW}objectsitem.html',
            f'if ({ov} == null) {{ {ov} = root.Objects.AddObject("{dname}"); created++; }}',
            f"{ov}.TaskRef = {tv}; // {HW}objectitem.html",
            f"{ov}.ControllerRef = node;",
            f'ProgramSTItem {sv} = {ov}.FindChildByName("migDispatch") as ProgramSTItem;',
            f'if ({sv} == null) {{ {sv} = {ov}.AddProgramST("migDispatch"); created++; }} // {HW}objectortagbase.html',
            f'{sv}.Text = "{_cs(calls)}"; // {HW}programstitem.html; вызов программы узла — {HW}vyzov_programm_obektov.html [L]',
        ]
        oncall += t["programs"]
    for j, p in enumerate(dict.fromkeys(oncall), 1):
        pv = f"call{j}"
        out += [
            f'ProgramItem {pv} = node.FindChildByName("{_cs(p)}") as ProgramItem;',
            f"if ({pv} != null) {{ {pv}.ExecutionMethod = FBExecuteTypes.OnCall; }} // {HW}programitem.html",
            f'else {{ this.WriteConsole("cds2ms: программа {_cs(p)} не найдена — сначала импорт PLCopen XML (шаг 3)"); }}',
        ]
    out.append(f'this.WriteConsole("cds2ms: задач {len(pl["tasks"])}, создано элементов " + created);')
    return "\n".join(out) + "\n"


def wrapper(body_text: str) -> str:
    """BuildProject.cs: тело в классе-наследнике ScriptHost (для макета и FakeRunner)."""
    ind = "".join("        " + ln if ln.strip() else ln for ln in body_text.splitlines(keepends=True))
    return (
        "// Обёртка для макета API (csharp/Stub) и FakeRunner. В MasterSCADA 4D вставляется только тело\n"
        "// DoAction() из DoAction.body.cs — класс редактора задаёт среда.\n"
        "using System;\nusing MasterSCADA.Scripts.Model;\n\n"
        "public class BuildProject : ScriptHost\n{\n    public void DoAction()\n    {\n"
        f"{ind}    }}\n}}\n"
    )


def tree_preview(project: Project, node: str, period_default: int = 100) -> str:
    """Ожидаемые узлы дерева — для сверки с tree.json FakeRunner (tools/csc_check.py)."""
    pl = plan(project, node, period_default)
    exp = {
        "node": node,
        "tasks": [{"name": t["name"], "Period": t["period"]} for t in pl["tasks"]],
        "dispatchers": [
            {"name": f"migTask_{_ident(t['name'])}", "TaskRef": f"Система.{node}.{t['name']}", "calls": t["programs"]}
            for t in pl["tasks"]
        ],
    }
    return json.dumps(exp, ensure_ascii=False, indent=2) + "\n"
