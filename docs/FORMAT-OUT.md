# Форматы: вход CODESYS 3.5.17 и выход для MasterSCADA 4D 1.3.10

Две половины: что cds2ms читает (и в какой форме его отдаёт CODESYS — этап 0, пробы 20.10.2026) и что пишет для
MasterSCADA 4D. Всё, что не подтверждено экспортом или справкой, помечено [L].

## 1. Этап 0: импорт PLCopen XML в CODESYS 3.5.17.30 по языкам

Стенд: CODESYS 3.5.17.30 x86 (сборка ОВЕН), профиль «CODESYS V3.5 SP17 Patch 3», устройство CODESYS Control Win V3
(4096 / 0000 0001 / 3.5.17.30), `--noUI --runscript`, вызов `application.import_xml(None, путь)` по одному файлу на
POU, затем `app.build()` и `proj.export_xml(...)`. Скрипт — `tools/codesys/cds_corpus_ide.py`, хост —
`tools/codesys/corpus.py` (под блокировкой рантайма). Итог прогона — `build/corpus/stage0.json` (не в git), экспорты —
`corpus/udr1/source.cds.xml` (приложение целиком) и `tests/fixtures/sp17/form_*.xml` (объект за объектом).

**Критерий «годится» (G):** импорт без ошибок, сборка 0 ошибок, экспорт даёт тело того же языка; отличия формы —
только `localId`, порядок атрибутов и addData из раздела 2. Иначе N.

| Язык / форма | Итог | Что показал прогон |
|---|---|---|
| ST (POU, DUT, GVL, интерфейс, методы, свойства) | **G** | создаётся текстовым API (`create_pou`, `create_method`, `create_property`, `create_interface`); экспорт — `interfaceasplaintext` + `<ST>` |
| FBD | **G** | сети по `localId` N·10^10, `jump`/`label`, `return`, экземпляры RS, SR, TON (addData `…/fbdcalltype` = `functionblock`), операторы (`operator`). CODESYS сам добавляет `vendorElement` 10000000000 в первую сеть |
| FBD, бокс с EN/ENO | не входит в корпус | после первого прогона (сборка упала на отсутствии Standard) убран из корпуса; понижение EN → `IF` проверяется на рукописном TC6 (`tests/unit/test_lower.py`) |
| LD: контакты НО/НЗ, фронт, катушки обычная/S/R, параллель, несколько сетей | **G** | одна `leftPowerRail localId="0"`, сквозная нумерация, сеть — с пары `comment` + `vendorElement networktitle`. Своя левая шина у каждой сети — объект создаётся, но остаётся только первая сеть |
| LD: один оператор на сеть (ADD, SEL), входы и выход — переменные | **G** | экспорт превращает первый BOOL-вход SEL в контакт, а `outVariable` — в катушку; правая шина `localId 2147483646` |
| LD: бокс ФБ (TON, CTU) с входом-переменной; TON без PT; цепочка ADD → SEL; `inVariable` → `outVariable` напрямую | **N** | объект появляется, но POU «битый»: «Идентификатор 'PRG_…' не задан», в экспорте его нет; цепочка и прямой провод — объект не создаётся. R_TRIG только с входом от цепи — объект создаётся (сборку с экземпляром не проверяли) |
| LD: катушка → катушка с отводом после первой | меняет смысл | import_xml сводит отвод в общий узел перед обеими катушками; трасса показала: «тест лампы» включал насос. В корпусе лампа вынесена в свою сеть; понижение по IEC (катушка передаёт поток) проверяется на рукописном TC6 |
| CFC | **G** | провода — через безымянные `connector` (вход блока ссылается на connector без `formalParameter`; у входа connector'а `formalParameter` = выражение входной переменной, `""` у выхода оператора, имя выхода у ФБ). Без addData `…/cfccalltype` — «'SUB' не является вызовом программы, функции…»; прямые соединения и именованные метки соединения в форме без проводов молча теряются |
| CFC: обратная связь, page-oriented | **G** | вход ADD (порядок 4) от LIMIT (порядок 5) — значение прошлого цикла; `page-oriented="true"` |
| SFC: шаги, альтернатива, параллель, прыжок, переход через `inVariable`, IEC-действия N, P, S, R, L, D | **G** | нужна ссылка-плейсхолдер `IecSfc`; переход по `Шаг.t` |
| SFC: квалификаторы P0, P1 | **N** | «'P1' is not a valid qualifier.», «'P0' is not a valid qualifier.» — в 3.5.17 их нет (справка: N, R, S, L, D, P, SD, DS, SL) |
| SFC: `Действие.x` | **N** | «'x' не является компонентом 'ActCount'»; правильно `_Действие.x` (справка «Implicit Variables») |
| IL | **N** | `import_xml` не создаёт объект и не бросает исключение (FB_PulseCount, F_ScaleIL): опция «Enable IL» выключена, скриптингом не включается |
| Задачи | **G** | `create_task_configuration`, `create_task`, `KindOfTask` Cyclic/Event; в экспорте — `task@interval` + addData `tasksettings` |

Библиотеки. Новый проект с Control Win получает ссылки `#IoStandard`, `#3SLicense`, `#CAA Device Diagnosis`,
`#BreakpointLogging`; Standard в их числе нет — код с TON не собирается («Неизвестный тип: 'TON'»). Корпус добавляет
`add_placeholder("Standard", "Standard, * (System)")` и `add_placeholder("IecSfc", "IecSfc, * (System)")`; в
экспорте появляется ещё `#Analyzation`. Предупреждение сборки: «Неявная конверсия из 'LREAL' в 'REAL'» в FB_DoseCtrl.

Решения по N (ASSUMPTIONS A2–A4): IL — вход по тексту (`<IL>` из публичных экспортов, `.il`), сверка — собственный
вычислитель; формы LD/SFC, которых import_xml не принимает, в корпус CODESYS не входят, их понижение проверяется на
рукописном TC6 (unit- и property-тесты), а языки по-прежнему сверяются трассами на тех формах, что принимаются.

## 2. Что cds2ms читает

**Размещения POU** (все три): `types/pous` и `types/dataTypes` (экспорт выбранных объектов);
`instances/configurations/…/resource/addData/data[…/pou]` (полный экспорт); `project/addData/data[…/application]/resource`
(экспорт узла Application — так снят `source.cds.xml`). GVL выбранных объектов — `project/addData/data[…/globalvars]`.

**Объявления** — addData `…/interfaceasplaintext` (если есть: комментарии, прагмы, AT — без потерь), иначе
структурный `<interface>`. Методы и свойства — addData `…/method`, `…/property` (Get/Set), действия — `pou/actions`,
переходы — `pou/transitions`.

**Тела:**

- **FBD** — сети по `localId div 10^10`, иначе по `vendorElement networktitle`; `block@typeName[@instanceName]`,
  `jump@label`, `return`, `label`. Порядок — топологический, ничьи — по файлу.
- **LD** — одна левая шина на всё тело доступна каждой сети; `contact@negated/edge`, `coil@negated/storage`; параллель —
  несколько `connection` в одном `connectionPointIn`.
- **CFC** — пустое `<ST>` + addData `…/cfc/CFC`; порядок — `executionOrderId`; безымянный `connector` — узел провода,
  именованные `connector`/`continuation` — метка соединения.
- **SFC** — `step`, `transition` (`condition` встроенным ST, через `inVariable` или ссылкой на переход),
  `selection*`/`simultaneous*`, `jumpStep`, `actionBlock/action@qualifier@duration`.
- **IL** — `<IL><xhtml>` или текст.

Задачи — `task@interval@priority` + addData `tasksettings` (`KindOfTask`, `Interval`, `IntervalUnit`), порядок
программ — `pouInstance`. Библиотеки — addData `…/libraries`. Ввод-вывод — `AT` в объявлениях GVL.

ST-раскладка (`src/POUs/<имя>/<имя>.decl.st` + `.impl.st`, `src/GVLs/*.gvl.st`, `src/DUTs/*.dut.st`, методы
`*.method.decl.st`) — контракт `docs/LAYOUT.md` s7-to-codesys.

## 3. Что cds2ms пишет (`cds2ms migrate <вход> --out <каталог>`)

| Файл | Что | Основание |
|---|---|---|
| `import/<имя>.plcopen.xml` | TC6 2.01 без addData, указателей и методов: `types/dataTypes` (struct, enum, массивы ≤ 3 осей), `types/pous` (тело — только `<ST><xhtml xmlns="http://www.w3.org/1999/xhtml">…</xhtml></ST>`), `configuration migConfig / resource migResource / globalVars` — по элементу на вид секции (обычные, `constant`, `retain`); без `task` и `pouInstance` | импорт берёт только ST (`HW:-plcopenxml`); схема — XSD TC6 2.01 (проверка в CI, `REQUIRE_XSD=1`) |
| `st/<POU>.ST` | тот же POU файлом `.ST` по `templates/st_file.txt` — **формат черновой [L]**: справка его не описывает, правится по пробе P-CS-03 | `HW:export_i_import_programm_st` |
| `script/DoAction.body.cs` | тело `DoAction()` для элемента «Скрипт»: задачи узла, программы-диспетчеры `migTask_<задача>`, режим «По вызову»; C# 5, идемпотентно, журнал `this.WriteConsole` | `HW:auto_develop_project`, `HW:controlleritem`, `HW:taskitem`, `HW:programitem` |
| `script/BuildProject.cs`, `script/expected-tree.json` | то же с обёрткой для макета API; дерево, которое построит скрипт (предпросмотр) | `csharp/api-snapshot.tsv` |
| `MANUAL_STEPS.md`, `tasks.md` | ручные шаги с ожидаемым результатом и минутами; задачи и порядок программ | — |
| `mapping.{json,csv}`, `io-binding.csv` | CODESYS → MasterSCADA по объектам; адреса `AT` → параметры узла | — |
| `MIGRATION_REPORT.{json,md,html}` | находки, матрица, трудоёмкость P50/P90 (модель); JSON содержит ядро семейства (`schemas/report-core.schema.json`) | — |
| `original/`, `fixed/`, `changes.diff` | ST после понижения (CODESYS), Master ST после правок, разница | — |
| `probe/` | варианты XML этого проекта для пробника | раздел 4 |

`--zip`: `ZIP_STORED`, сортировка, `date_time=(1980,1,1,0,0,0)`, атрибуты 0644 — побайтно одинаково на ubuntu,
windows и в браузере (страница демо сверяет SHA-256). В заголовках — «создано cds2ms 0.1.0».

## 4. Варианты XML для пробника

`P-IMP-01` — как в `import/` (ns `tc6_0201`, `globalVars` в `resource`); `-02` — `globalVars` в `configuration`;
`-03` — с `task` + `pouInstance`; `-04` — ns `tc6_0200`; `-05` — сырой экспорт CODESYS с addData; `-06` — тело в
`xhtml:p`; `-07` — глобальные с именами `GVL_x` без папки. Порядок проб и время — `probe/README.md`.
