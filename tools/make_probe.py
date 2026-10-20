"""Комплект пробника в репозитории (probe/) для владельца MasterSCADA 4D 1.3.10.

    python tools/make_probe.py

= `cds2ms probe --out probe` (минимальные файлы на конструкции) + сырой экспорт CODESYS для P-IMP-05 (корпус УДР-1,
экспорт CODESYS 3.5.17.30) + скрипт C# УДР-1 для P-CS-01/02 и P-RT-13 (с XML, который импортируется перед ним).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cds2ms import api  # noqa: E402
from cds2ms.cli import main as cli  # noqa: E402

SCRIPT_README = """# Скрипт C# для проб P-CS-01, P-CS-02, P-RT-13

1. Узел ПЛК (PLC210) → «Импортирование PLCOpenXML» → `udr1.plcopen.xml` (корпус УДР-1 после cds2ms, только ST).
2. Библиотека проекта → элемент «Скрипт» → вставить `DoAction.body.cs` в метод `DoAction()` → «Выполнить программу».
3. P-CS-01: дерево узла против `expected-tree.json` (задачи TaskFast 10 мс, TaskSlow 200 мс, TaskAlarm 20 мс,
   программы-диспетчеры migTask_*, вызываемые программы — «По вызову»). Повторный запуск не должен ничего
   дублировать (скрипт идемпотентен). Консоль скрипта — дословно в notes.
4. P-CS-02: у любого параметра создать связь `AddLink` и посмотреть в дереве связей, в какую сторону идёт значение;
   то же для `DataSource` (справка описывает только одно направление).
5. P-RT-13: в эмуляции убедиться, что диспетчер migTask_TaskFast вызывает PRG_Main (счётчики PRG_Main растут).

`BuildProject.cs` — тот же скрипт с обёрткой для макета API (сборка в CI); в среду вставляется только тело.
"""


def main() -> int:
    probe = ROOT / "probe"
    if probe.exists():
        shutil.rmtree(probe)
    assert cli(["probe", "--out", str(probe)]) == 0
    src = ROOT / "corpus" / "udr1" / "source.cds.xml"
    shutil.copyfile(src, probe / "import" / "P-IMP-05-codesys-raw.xml")
    mig = api.migrate(api.load_path(src))
    script = probe / "script"
    script.mkdir(exist_ok=True)
    for name in ("DoAction.body.cs", "BuildProject.cs", "expected-tree.json"):
        (script / name).write_bytes(mig.files[f"script/{name}"])
    xml = next(k for k in mig.files if k.startswith("import/") and k.endswith(".plcopen.xml"))
    (script / "udr1.plcopen.xml").write_bytes(mig.files[xml])
    (script / "README.md").write_text(SCRIPT_README, encoding="utf-8", newline="\n")
    print(f"probe/: {sum(1 for p in probe.rglob('*') if p.is_file())} файлов")
    return 0


if __name__ == "__main__":
    sys.exit(main())
