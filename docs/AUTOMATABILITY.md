# Что автоматизируемо: конструкция × канал × исход

Матрица — та же, что в `MIGRATION_REPORT.{json,md,html}` (`src/cds2ms/emit/report.py`). Исходы — словарь семейства:
**авто** (переносится без человека), **сверить** (переносится, человек смотрит правку), **проверить** (поведение
цели в справке не описано — проба), **вручную**, **невозможно**. Уверенность H/M/L — насколько поведение цели
описано справкой 1.3.10: H — описано прямо, M — выведено из описания, L — не описано.

| Конструкция | Язык | Канал в MasterSCADA 4D | Исход | Ув. | Источник |
|---|---|---|---|---|---|
| POU на ST (PROGRAM, FB, FUNCTION) | ST | PLCopen XML (`types/pous`) или `.ST` | авто | H | [plcopenxml](https://help.iek-digital.ru/Help-web/-plcopenxml.html) |
| Тело FBD | FBD | понижение в ST → PLCopen XML | сверить | H | [plcopenxml](https://help.iek-digital.ru/Help-web/-plcopenxml.html) |
| Тело LD | LD | понижение в ST → PLCopen XML | сверить | H | [programlditem](https://help.iek-digital.ru/Help-web/programlditem.html) |
| Тело CFC | CFC | понижение в ST → PLCopen XML (CFC в MS4D нет) | сверить | H | [programmirovanie](https://help.iek-digital.ru/Help-web/programmirovanie_v_masterscada_4d.html) |
| Тело SFC | SFC | ST-автомат → PLCopen XML; SFC MS4D (только N/P1) — вручную | сверить | H | [sfc-deystviya](https://help.iek-digital.ru/Help-web/dialog_redaktirovaniya_sfc-deystviya.html) |
| Тело IL | IL | понижение в ST → PLCopen XML (IL в MS4D нет) | сверить | H | [programmirovanie](https://help.iek-digital.ru/Help-web/programmirovanie_v_masterscada_4d.html) |
| METHOD | ST | режим вызова `migCall` → PLCopen XML | сверить | M | [klyuchevye_slova](https://help.iek-digital.ru/Help-web/klyuchevye_slova.html) |
| PROPERTY | ST | GET → VAR_OUTPUT, SET → ветка `migCall` | сверить | M | [klyuchevye_slova](https://help.iek-digital.ru/Help-web/klyuchevye_slova.html) |
| INTERFACE и полиморфизм | ST | подстановка экземпляра или вручную | вручную | M | [klyuchevye_slova](https://help.iek-digital.ru/Help-web/klyuchevye_slova.html) |
| EXTENDS | ST | копия членов предка | сверить | M | [klyuchevye_slova](https://help.iek-digital.ru/Help-web/klyuchevye_slova.html) |
| GVL | DECL | `globalVars` → параметры узла `GVL_x` | авто | M | [globalnye_peremennye](https://help.iek-digital.ru/Help-web/globalnye_peremennye.html) |
| VAR_GLOBAL CONSTANT | DECL | `globalVars constant` | сверить | L | [constanty](https://help.iek-digital.ru/Help-web/constanty.html) |
| RETAIN | DECL | `retain` в XML / `Saving = RETAIN` скриптом | сверить | M | [sohranenie_sostoyania](https://help.iek-digital.ru/Help-web/sohranenie_sostoyania.html) |
| PERSISTENT | DECL | → RETAIN | сверить | M | [sohranenie_sostoyania](https://help.iek-digital.ru/Help-web/sohranenie_sostoyania.html) |
| STRUCT, ENUM, ARRAY ≤ 3 осей | DECL | `types/dataTypes` | авто | H | [noviy_tip_parametra](https://help.iek-digital.ru/Help-web/noviy_tip_parametra.html) |
| Псевдоним, поддиапазон | DECL | подстановка базового типа | авто | M | [noviy_tip_parametra](https://help.iek-digital.ru/Help-web/noviy_tip_parametra.html) |
| UNION | DECL | — | вручную | M | [noviy_tip_parametra](https://help.iek-digital.ru/Help-web/noviy_tip_parametra.html) |
| POINTER, REFERENCE, ADR | ST | — | вручную | M | [specialnye_tipy_dannyh](https://help.iek-digital.ru/Help-web/specialnye_tipy_dannyh.html) |
| Задача циклическая | PROJECT | C#-скрипт `AddTask` / `tasks.md` | сверить | H | [taskitem](https://help.iek-digital.ru/Help-web/taskitem.html) |
| Задача событийная, freewheeling | PROJECT | циклическая + фронт условия | сверить | M | [zadachi](https://help.iek-digital.ru/Help-web/zadachi.html) |
| Порядок программ в задаче | PROJECT | программа-диспетчер `migTask_<задача>` скриптом | сверить | H | [vyzov_programm_obektov](https://help.iek-digital.ru/Help-web/vyzov_programm_obektov.html) |
| AT %I/%Q | DECL | параметр + `io-binding.csv`, связь — вручную | сверить | H | [variableitem](https://help.iek-digital.ru/Help-web/variableitem.html) |
| Standard: TON, R_TRIG, CTU … | ST | одноимённые блоки «Стандартной» библиотеки | авто | H | [hmcontent](https://help.iek-digital.ru/Help-web/hmcontent.html) |
| Util, CAA, SysLib, библиотеки ОВЕН | ST | — | вручную | H | [hmcontent](https://help.iek-digital.ru/Help-web/hmcontent.html) |
| Устройства, Modbus, модули | PROJECT | каналы создаёт человек | вручную | H | [ob_ekt](https://help.iek-digital.ru/Help-web/ob_ekt.html) |
| Визуализация | PROJECT | — | невозможно | H | [programmirovanie](https://help.iek-digital.ru/Help-web/programmirovanie_v_masterscada_4d.html) |

## Что меняет поведение молча (правила, которые ловят)

| Ловушка | Правило | Что делает cds2ms |
|---|---|---|
| задачи только циклические, по умолчанию 100 мс; TON 150 мс в задаче 100 мс срабатывает через 200 мс | MS-EXEC-01 | находка «сверить» со временем; график и сценарий `PRG_TonQuant` |
| порядок программ задачи CODESYS не переносится | MS-EXEC-03 | программа-диспетчер `migTask_<задача>`, программы — «По вызову» |
| `DT` по умолчанию 0001-01-01 (в CODESYS 1970) | MS-TYPE-06 | находка; симулятор `masterplc` берёт дату профиля |
| деление целых и /0 в Lua 5.4 | MS-TYPE-07 | «проверить», проба P-RT-02 |
| SFC в MS4D — только N и P1 «со сдвигом на один цикл» | MS-SFC-01 | SFC переводится ST-автоматом с порядком обработки CODESYS |
| `EN` в ST не поддерживается | MS-ST-01 | `EN`/`ENO` → `migEN`/`migENO` |
| ФБ на цепи Master LD получает цепь на `En` | MS-LD-01 | сведения при перерисовке LD вручную |
| `GVL.x` → параметр узла `GVL_x` | MS-ST-08 | переименование в теле и `mapping` |
| имена с `__` и `_` в конце запрещены | MS-ST-02, MS-NAME-* | переименование с отчётом |

Полный реестр — [RULES.md](RULES.md) (54 правила, у каждого источник и корпус `tests/rules/<ID>/`).
