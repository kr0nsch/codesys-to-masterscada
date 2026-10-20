# Changelog

Все заметные изменения проекта записываются в этот файл.

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — по
[Semantic Versioning](https://semver.org/lang/ru/spec/v2.0.0.html).

## [0.1.0] — 2026-10-20

Первый выпуск.

### Added

- Импорт PLCopen XML CODESYS 3.5 (TC6 0200/0201, addData 3S) в трёх размещениях: шесть языков (CFC в addData),
  действия, переходы, методы, свойства, интерфейсы, GVL, DUT, задачи с `TaskSettings`, библиотеки; ST-раскладка `src/`.
  Номера строк у каждого объекта.
- Лексер ST без потерь, парсер с восстановлением, печать; диалект `masterst` (`var_inout`, `NULL`, `Библиотека.ФБ`).
- Понижение в ST: FBD, LD, CFC (порядок `executionOrderId`, обратные связи), SFC (ST-автомат с порядком обработки
  CODESYS, IEC-действия N, P, S, R, L, D, последний вызов), IL (стековая машина CR), структурировщик переходов,
  ООП «режимом вызова» (методы, свойства, EXTENDS, `SUPER^`, интерфейсные переменные).
- Профили `masterscada-4d-1.3.10` и `codesys-3.5.17`: статус, уверенность и источник у каждой возможности.
- 54 правила MS-* с корпусом pos/neg и источником; исходы семейства; трудоёмкость P50/P90 (модель).
- Правки Master ST по уровням `--fix none|safe|review|all`, идемпотентно.
- Выходы: PLCopen XML (только ST, валиден по XSD TC6 2.01), файлы `.ST` (черновой формат), C#-скрипт `DoAction()`
  (задачи и программы-диспетчеры; собирается против макета API и против `MasterSCADA.Scripts.Model.dll` 1.3.10),
  `MANUAL_STEPS.md`, `tasks.md`, `mapping`, `io-binding.csv`, `MIGRATION_REPORT.{json,md,html}`, детерминированный zip.
- Симулятор ST с профилями `codesys` и `masterplc`, режимы R1/R2, объяснённые расхождения.
- Корпус «УДР-1» (19 POU на ST, FBD, LD, CFC, SFC, IL, ООП; 16 приняты CODESYS 3.5.17.30, IL — нет): трассы 12 POU в
  CODESYS Control Win совпали с понижением. Цепочка S7 → CODESYS → MasterPLC, кейс plc-process-lib.
- Пробник для владельца MasterSCADA 4D (`probe/`, ≈ 2,5 ч) и `profiles apply-probe`.
- CLI `cds2ms inventory | analyze | migrate | simulate | explain | profiles | roundtrip | probe`.
- Демо на GitHub Pages: тот же код в браузере (Pyodide 314.0.7), примеры, сверка SHA-256 zip с CLI.
