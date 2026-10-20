# Правила MS-*

Каждое правило — находка с исходом из словаря семейства (`auto | review | verify | manual | impossible | info`),
источник в справке MasterSCADA 4D 1.3.10 или CODESYS и корпус `tests/rules/<ID>/` (pos/neg). Нумерация совпадает с
конспектом исследования там, где ID оттуда. «Описано» — есть ли поведение цели в справке 1.3.10; «нет» означает
исход не легче verify или ручной шаг. Минуты — модель трудоёмкости (`data/effort.toml`), не замер.
Файл строится `tools/gen_docs.py` из `src/cds2ms/rules/registry.py`.

| ID | Что | Исход | Описано | Правка | Минуты (min/mode/max) |
|---|---|---|---|---|---|
| [MS-PARSE-01](#ms-parse-01) | ошибка разбора | вручную | да | нет | 10/30/90 |
| [MS-LANG-01](#ms-lang-01) | FBD → ST | сверить | да | нет | 5/10/30 |
| [MS-LANG-02](#ms-lang-02) | LD → ST | сверить | да | нет | 5/12/30 |
| [MS-LANG-03](#ms-lang-03) | CFC → ST | сверить | да | нет | 5/15/40 |
| [MS-LANG-04](#ms-lang-04) | SFC → ST-автомат | сверить | да | нет | 20/45/120 |
| [MS-LANG-05](#ms-lang-05) | IL → ST | сверить | да | нет | 5/15/45 |
| [MS-LANG-06](#ms-lang-06) | ООП → режим вызова | сверить | нет | нет | 10/30/90 |
| [MS-LANG-07](#ms-lang-07) | ACTION | сверить | да | нет | 3/8/20 |
| [MS-LD-01](#ms-ld-01) | ФБ на цепи Master LD | сведения | да | нет | 0/0/0 |
| [MS-SFC-01](#ms-sfc-01) | квалификаторы SFC | сверить | да | нет | 3/8/20 |
| [MS-SFC-02](#ms-sfc-02) | неявные переменные SFC | сверить | нет | нет | 3/8/20 |
| [MS-FBD-01](#ms-fbd-01) | порядок FBD MS4D | сведения | да | нет | 0/0/0 |
| [MS-ST-01](#ms-st-01) | EN/ENO в ST | сверить | да | `--fix review` | 3/8/20 |
| [MS-ST-02](#ms-st-02) | запрещённые «_» в именах | авто | да | `--fix safe` | 0/1/3 |
| [MS-ST-03](#ms-st-03) | тело отдельно от объявлений | авто | да | `--fix safe` | 0/1/3 |
| [MS-ST-04](#ms-st-04) | CASE по ENUM | проверить | нет | нет | 5/10/30 |
| [MS-ST-05](#ms-st-05) | указатели и ссылки | вручную | нет | нет | 30/60/180 |
| [MS-ST-07](#ms-st-07) | прямые адреса | сверить | да | `--fix review` | 3/6/15 |
| [MS-ST-08](#ms-st-08) | GVL → параметры узла | авто | да | `--fix safe` | 0/1/3 |
| [MS-ST-09](#ms-st-09) | VAR_TEMP | сведения | да | нет | 0/0/0 |
| [MS-ST-10](#ms-st-10) | «Переключение» BOOL-параметров | сведения | да | нет | 0/0/0 |
| [MS-ST-11](#ms-st-11) | S= / R= | авто | да | `--fix safe` | 0/1/3 |
| [MS-ST-12](#ms-st-12) | REF= | вручную | нет | нет | 20/45/120 |
| [MS-ST-13](#ms-st-13) | JMP и метки | сверить | нет | `--fix review` | 5/15/40 |
| [MS-NAME-01](#ms-name-01) | нормализация и коллизии имён | авто | да | `--fix safe` | 0/1/3 |
| [MS-NAME-02](#ms-name-02) | ключевые слова MS4D и Lua | авто | да | `--fix safe` | 0/1/3 |
| [MS-DECL-01](#ms-decl-01) | VAR_IN_OUT | проверить | да | `--fix safe` | 5/15/40 |
| [MS-DECL-02](#ms-decl-02) | VAR_STAT | сверить | нет | `--fix review` | 5/10/30 |
| [MS-DECL-04](#ms-decl-04) | VAR_GLOBAL CONSTANT | сверить | да | нет | 3/8/20 |
| [MS-DECL-06](#ms-decl-06) | PERSISTENT | сверить | нет | `--fix review` | 3/8/20 |
| [MS-RET-01](#ms-ret-01) | хранение retain | сведения | да | нет | 0/0/0 |
| [MS-RET-02](#ms-ret-02) | холодный рестарт | проверить | нет | нет | 5/15/40 |
| [MS-TYPE-02](#ms-type-02) | LTIME, WSTRING, STRING(n) | сверить | нет | `--fix review` | 3/8/20 |
| [MS-TYPE-03](#ms-type-03) | UNION | вручную | нет | нет | 30/60/180 |
| [MS-TYPE-04](#ms-type-04) | alias, subrange, ENUM с базой | авто | да | `--fix safe` | 0/1/3 |
| [MS-TYPE-05](#ms-type-05) | массивы | сверить | да | нет | 3/8/20 |
| [MS-TYPE-06](#ms-type-06) | DT по умолчанию | сверить | да | нет | 3/8/20 |
| [MS-TYPE-07](#ms-type-07) | целочисленная арифметика в Lua | проверить | нет | нет | 5/15/40 |
| [MS-TYPE-08](#ms-type-08) | TIME со знаком | проверить | нет | нет | 5/15/40 |
| [MS-TYPE-09](#ms-type-09) | REAL и REAL_TO_* | проверить | нет | нет | 2/5/15 |
| [MS-EXEC-01](#ms-exec-01) | квантование таймеров | сверить | да | нет | 5/10/30 |
| [MS-EXEC-02](#ms-exec-02) | событийные задачи | сверить | нет | нет | 15/30/90 |
| [MS-EXEC-03](#ms-exec-03) | порядок программ | сверить | да | нет | 5/10/20 |
| [MS-EXEC-04](#ms-exec-04) | связи и прямой доступ | сведения | да | нет | 0/0/0 |
| [MS-EXEC-05](#ms-exec-05) | выход вызываемой программы | сведения | да | нет | 0/0/0 |
| [MS-EXEC-06](#ms-exec-06) | приоритеты задач | проверить | нет | нет | 5/15/40 |
| [MS-EXEC-07](#ms-exec-07) | период и производительность | сведения | да | нет | 0/0/0 |
| [MS-LIB-01](#ms-lib-01) | библиотека Standard | авто | да | нет | 0/1/3 |
| [MS-LIB-02](#ms-lib-02) | прочие библиотеки | вручную | да | нет | 20/60/240 |
| [MS-ASYNC-01](#ms-async-01) | асинхронные ФБ | вручную | да | нет | 20/45/120 |
| [MS-IO-01](#ms-io-01) | устройства и ввод-вывод | вручную | да | нет | 30/90/240 |
| [MS-VISU-01](#ms-visu-01) | визуализация | невозможно | да | нет | 120/480/1440 |
| [MS-ALARM-01](#ms-alarm-01) | AlarmManager | вручную | да | нет | 20/45/120 |
| [MS-MARK-01](#ms-mark-01) | маркеры s7conv | сведения | да | нет | 0/0/0 |

### MS-PARSE-01

**ошибка разбора.** Текст не разобран (ST, IL, XML): оператор восстановлен до «;» или END_*, остальной текст перенесён.

Исход по умолчанию — вручную; правка — нет.
Корпус: `tests/rules/MS-PARSE-01/`.

Источники:

- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_st_editor.html

### MS-LANG-01

**FBD → ST.** Тело FBD понижено в ST: сети по номеру, внутри — порядок потока данных, разветвлённый выход → migNetN_k, блок с EN → IF. PLCopen-импорт MS4D графику не берёт (HW:-plcopenxml).

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-LANG-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/programmirovanie_v_masterscada_4d.html

### MS-LANG-02

**LD → ST.** Тело LD понижено в ST: последовательно → AND, параллельно → OR, |P|/|N| → R_TRIG/F_TRIG, катушки (S)/(R) → IF. API скриптов для LD «будет добавлено позже» (HW:programlditem).

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-LANG-02/`.

Источники:

- https://help.iek-digital.ru/Help-web/redaktor_ld.html
- https://help.iek-digital.ru/Help-web/ld-blok.html

### MS-LANG-03

**CFC → ST.** CFC в MS4D нет: порядок executionOrderId, вход от блока с бо́льшим номером — значение прошлого цикла.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-LANG-03/`.

Источники:

- https://help.iek-digital.ru/Help-web/programmirovanie_v_masterscada_4d.html

### MS-LANG-04

**SFC → ST-автомат.** SFC понижен в ST-автомат с порядком обработки CODESYS; SFC MS4D допускает только N/P1 со сдвигом на цикл.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-LANG-04/`.

Источники:

- https://help.iek-digital.ru/Help-web/dialog_redaktirovaniya_sfc-deystviya.html
- https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_sequence_of_processing.html

### MS-LANG-05

**IL → ST.** IL в MS4D нет: символьное исполнение текущего результата, переходы — структурировщик.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-LANG-05/`.

Источники:

- https://help.iek-digital.ru/Help-web/programmirovanie_v_masterscada_4d.html

### MS-LANG-06

**ООП → режим вызова.** METHOD, PROPERTY, INTERFACE, EXTENDS в справке Master ST не описаны: методы → вход migCall и ветки CASE, свойства GET → выходы, EXTENDS → копия членов предка; полиморфизм, рекурсия, FB_init с параметрами — вручную.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-LANG-06/`.

Источники:

- https://help.iek-digital.ru/Help-web/klyuchevye_slova.html
- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_obj_method.html

### MS-LANG-07

**ACTION.** Действие, вызываемое только из своего POU и без RETURN, встраивается; иначе — вручную.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-LANG-07/`.

Источники:

- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_obj_action.html

### MS-LD-01

**ФБ на цепи Master LD.** В Master LD вход «in» ФБ на цепи — это En: перерисованный вручную TON при ложной цепи не вызывается (в CODESYS — вызывается с IN := FALSE). Проба P-RT-12.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-LD-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/ld-blok.html

### MS-SFC-01

**квалификаторы SFC.** Только N и P1 «со сдвигом на один цикл»: N не выполняется в первом цикле и выполняется ещё раз после деактивации.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-SFC-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/dialog_redaktirovaniya_sfc-deystviya.html

### MS-SFC-02

**неявные переменные SFC.** шаг.x/._x/.t переводятся в переменные автомата; SFCInit/SFCReset/SFCPause/SFCError*, макрошаги — вручную.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-SFC-02/`.

Источники:

- https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_implicit_variables.html

### MS-FBD-01

**порядок FBD MS4D.** Порядок блоков FBD в MS4D — по потоку данных или геометрии, явной нумерации CFC нет.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-FBD-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/poryadok_ispolnenia_fbd-blokov.html

### MS-ST-01

**EN/ENO в ST.** EN/ENO в исходнике ST — явные переменные ФБ; в MS4D это ключевые слова и En в ST не поддерживается: переименование в migEN/migENO в объявлении и вызовах.

Исход по умолчанию — сверить; правка — `--fix review`.
Корпус: `tests/rules/MS-ST-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/obrabotka_en_eno.html

### MS-ST-02

**запрещённые «_» в именах.** Два и более «_» подряд в начале или внутри, «_» в конце запрещены: переименование.

Исход по умолчанию — авто; правка — `--fix safe`.
Корпус: `tests/rules/MS-ST-02/`.

Источники:

- https://help.iek-digital.ru/Help-web/identifikatory.html

### MS-ST-03

**тело отдельно от объявлений.** Редактор ST — только тело; объявления — дерево и «Заголовок ST». Переменным из текста «нельзя задать связь»: интерфейс POU переносится структурой PLCopen XML, а не текстом.

Исход по умолчанию — авто; правка — `--fix safe`.
Корпус: `tests/rules/MS-ST-03/`.

Источники:

- https://help.iek-digital.ru/Help-web/redaktor_st.html
- https://help.iek-digital.ru/Help-web/legenda_vkladka_zagolovok_st.html

### MS-ST-04

**CASE по ENUM.** CASE описан для целых; ENUM с явными значениями и литерал E_State.Run — проба P-ST-02.

Исход по умолчанию — проверить; правка — нет.
Корпус: `tests/rules/MS-ST-04/`.

Источники:

- https://help.iek-digital.ru/Help-web/operator_case.html

### MS-ST-05

**указатели и ссылки.** POINTER, REFERENCE, ADR, __NEW, SIZEOF, MEMCPY в Master ST не описаны (REF_TO — не ссылка). REFERENCE TO в параметре → var_inout (review).

Исход по умолчанию — вручную; правка — нет.
Корпус: `tests/rules/MS-ST-05/`.

Источники:

- https://help.iek-digital.ru/Help-web/klyuchevye_slova.html
- https://help.iek-digital.ru/Help-web/specialnye_tipy_dannyh.html

### MS-ST-07

**прямые адреса.** AT %I/%Q → параметр без адреса + строка io-binding.csv (связь с каналом); %M-наложения — вручную.

Исход по умолчанию — сверить; правка — `--fix review`.
Корпус: `tests/rules/MS-ST-07/`.

Источники:

- https://help.iek-digital.ru/Help-web/ob_ekt.html
- https://help.iek-digital.ru/Help-web/teg.html

### MS-ST-08

**GVL → параметры узла.** Глобальные — параметры узла, в папке называются Папка_Имя: GVL.x → GVL_x.

Исход по умолчанию — авто; правка — `--fix safe`.
Корпус: `tests/rules/MS-ST-08/`.

Источники:

- https://help.iek-digital.ru/Help-web/globalnye_peremennye.html

### MS-ST-09

**VAR_TEMP.** VAR_TEMP ↔ доступ Temp; в «Отладочной конфигурации» Temp транслируется как Local.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-ST-09/`.

Источники:

- https://help.iek-digital.ru/Help-web/parametry_programm.html

### MS-ST-10

**«Переключение» BOOL-параметров.** У BOOL-параметров программ MS4D есть «Переключение» R_EDGE/F_EDGE — неявный фронт на входе.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-ST-10/`.

Источники:

- https://help.iek-digital.ru/Help-web/parametry_programm.html

### MS-ST-11

**S= / R=.** Присваивания S=/R= → IF … THEN x := TRUE/FALSE.

Исход по умолчанию — авто; правка — `--fix safe`.
Корпус: `tests/rules/MS-ST-11/`.

Источники:

- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_operator_set_reset.html

### MS-ST-12

**REF=.** Присваивание ссылки REF= — вручную.

Исход по умолчанию — вручную; правка — нет.
Корпус: `tests/rules/MS-ST-12/`.

Источники:

- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_reference.html

### MS-ST-13

**JMP и метки.** JMP в операторах Master ST нет: переходы вперёд → IF над хвостом, иначе автомат migPc.

Исход по умолчанию — сверить; правка — `--fix review`.
Корпус: `tests/rules/MS-ST-13/`.

Источники:

- https://help.iek-digital.ru/Help-web/operatory_master_st.html

### MS-NAME-01

**нормализация и коллизии имён.** Спецсимволы в именах дерева → «_»; коллизия после префиксов и GVL_x → суффикс (review).

Исход по умолчанию — авто; правка — `--fix safe`.
Корпус: `tests/rules/MS-NAME-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/parametry_programm.html
- https://help.iek-digital.ru/Help-web/globalnye_peremennye.html

### MS-NAME-02

**ключевые слова MS4D и Lua.** Имя CODESYS — ключевое слово MS4D (NULL, R_EDGE, STEP, TASK, EN, …) → переименование (auto); слово Lua (local, nil, end, goto, …) → verify, проба P-ST-04.

Исход по умолчанию — авто; правка — `--fix safe`.
Корпус: `tests/rules/MS-NAME-02/`.

Источники:

- https://help.iek-digital.ru/Help-web/klyuchevye_slova.html
- https://www.lua.org/manual/5.4/manual.html#3.1

### MS-DECL-01

**VAR_IN_OUT.** VAR_IN_OUT → var_inout (auto); передаётся ли ссылкой — в справке не описано (verify).

Исход по умолчанию — проверить; правка — `--fix safe`.
Корпус: `tests/rules/MS-DECL-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/osnovnye_tipy_obavleniy.html

### MS-DECL-02

**VAR_STAT.** VAR_STAT (общая для экземпляров ФБ, в FUNCTION хранит значение между вызовами) → глобальный параметр узла mig<POU>_<имя>.

Исход по умолчанию — сверить; правка — `--fix review`.
Корпус: `tests/rules/MS-DECL-02/`.

Источники:

- https://help.iek-digital.ru/Help-web/osnovnye_tipy_obavleniy.html

### MS-DECL-04

**VAR_GLOBAL CONSTANT.** Список констант → globalVars constant="true" (куда ляжет — проба P-ST-08); запасной путь — «Константа» библиотеки.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-DECL-04/`.

Источники:

- https://help.iek-digital.ru/Help-web/constanty.html

### MS-DECL-06

**PERSISTENT.** PERSISTENT → RETAIN: аналога «переживает загрузку» нет.

Исход по умолчанию — сверить; правка — `--fix review`.
Корпус: `tests/rules/MS-DECL-06/`.

Источники:

- https://help.iek-digital.ru/Help-web/sohranenie_sostoyania.html
- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_var_persistent.html

### MS-RET-01

**хранение retain.** Retain пишется периодически или при остановке, есть «время актуальности»; InOut-параметры программ не сохраняются.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-RET-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/sohranenie_sostoyania.html

### MS-RET-02

**холодный рестарт.** Справка описывает RETAIN как восстановление «при холодном рестарте» — термины CODESYS не совпадают.

Исход по умолчанию — проверить; правка — нет.
Корпус: `tests/rules/MS-RET-02/`.

Источники:

- https://help.iek-digital.ru/Help-web/modifikatory_operatorov_opredeleniya_peremennyh.html

### MS-TYPE-02

**LTIME, WSTRING, STRING(n).** LTIME → TIME (точность мс), WSTRING → STRING, STRING(n) → STRING (без длины, UTF-8); LEN над кириллицей — verify.

Исход по умолчанию — сверить; правка — `--fix review`.
Корпус: `tests/rules/MS-TYPE-02/`.

Источники:

- https://help.iek-digital.ru/Help-web/elementarnye_tipy_dannyh.html

### MS-TYPE-03

**UNION.** UNION в типах MS4D нет — вручную.

Исход по умолчанию — вручную; правка — нет.
Корпус: `tests/rules/MS-TYPE-03/`.

Источники:

- https://help.iek-digital.ru/Help-web/noviy_tip_parametra.html

### MS-TYPE-04

**alias, subrange, ENUM с базой.** Псевдоним → базовый тип, поддиапазон → базовый тип (диапазон — в комментарии), базовый тип ENUM снимается.

Исход по умолчанию — авто; правка — `--fix safe`.
Корпус: `tests/rules/MS-TYPE-04/`.

Источники:

- https://help.iek-digital.ru/Help-web/noviy_tip_parametra.html

### MS-TYPE-05

**массивы.** Не больше трёх осей; выход за границы даёт NULL, а не исключение.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-TYPE-05/`.

Источники:

- https://help.iek-digital.ru/Help-web/redaktor_tipa_massiv.html

### MS-TYPE-06

**DT по умолчанию.** DT по умолчанию DT#0001-01-01-00:00:00, в CODESYS — 1970: сравнение с DT#1970… ломается молча.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-TYPE-06/`.

Источники:

- https://help.iek-digital.ru/Help-web/inicializaciya_peremennyh.html

### MS-TYPE-07

**целочисленная арифметика в Lua.** Переполнение знаковых, деление целых и /0 в трансляторе Lua 5.4 не описаны — пробы P-RT-01, P-RT-02.

Исход по умолчанию — проверить; правка — нет.
Корпус: `tests/rules/MS-TYPE-07/`.

Источники:

- https://help.iek-digital.ru/Help-web/osobennosti_bitovyh_strok.html

### MS-TYPE-08

**TIME со знаком.** В CODESYS TIME — DWORD мс без знака (переход через 0 в tNow - tStart), в MS4D — со знаком, разрядность не описана.

Исход по умолчанию — проверить; правка — нет.
Корпус: `tests/rules/MS-TYPE-08/`.

Источники:

- https://help.iek-digital.ru/Help-web/vremennye_konstanty.html
- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_time.html

### MS-TYPE-09

**REAL и REAL_TO_*.** REAL float32 против double Lua; REAL_TO_* на половинах (CODESYS: −1.5 → −2) — проба P-RT-03.

Исход по умолчанию — проверить; правка — нет.
Корпус: `tests/rules/MS-TYPE-09/`.

Источники:

- https://help.iek-digital.ru/Help-web/funkcii_preobrazovaniya_tipa.html
- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_operator_real_to.html

### MS-EXEC-01

**квантование таймеров.** Задача MS4D по умолчанию 100 мс: таймер срабатывает в первом цикле после уставки (150 мс → 200 мс).

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-EXEC-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/zadachi.html

### MS-EXEC-02

**событийные задачи.** Event/freewheeling/status → циклическая задача + фронт; external event — невозможно.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-EXEC-02/`.

Источники:

- https://help.iek-digital.ru/Help-web/zadachi.html
- https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_f_task_configuration.html

### MS-EXEC-03

**порядок программ.** Порядок программ — дерево узла (Item.Position только чтение): диспетчер migTask_<T> вызывает программы в порядке CODESYS.

Исход по умолчанию — сверить; правка — нет.
Корпус: `tests/rules/MS-EXEC-03/`.

Источники:

- https://help.iek-digital.ru/Help-web/poryadok_vychislniy_i_peredachi.html
- https://help.iek-digital.ru/Help-web/vyzov_programm_obektov.html

### MS-EXEC-04

**связи и прямой доступ.** Связи отрабатываются до программ, прямой доступ из ST — в момент обращения.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-EXEC-04/`.

Источники:

- https://help.iek-digital.ru/Help-web/poryadok_vychislniy_i_peredachi.html

### MS-EXEC-05

**выход вызываемой программы.** Выход вызываемой программы через связь не доходит — нужен прямой доступ.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-EXEC-05/`.

Источники:

- https://help.iek-digital.ru/Help-web/peredacha_znacheniy_iz_vyzyvaemoy_programmy.html

### MS-EXEC-06

**приоритеты задач.** Приоритеты 0–31 CODESYS → MS4D: направление шкалы не описано, неверный приоритет может повесить ПЛК.

Исход по умолчанию — проверить; правка — нет.
Корпус: `tests/rules/MS-EXEC-06/`.

Источники:

- https://help.iek-digital.ru/Help-web/zadachi.html

### MS-EXEC-07

**период и производительность.** Задача 10 мс на ПЛК210-0x (Cortex-A8, Lua) — укладывание в период сверить; C# только на ПЛК210-1x.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-EXEC-07/`.

Источники:

- https://support.mps-soft.ru/PLC_Library/zadachi_isp_sistemi_owen.html

### MS-LIB-01

**библиотека Standard.** TON/TOF/TP/R_TRIG/F_TRIG/RS/SR/CTU/CTD/CTUD есть в «Стандартной»; типы PV/CV счётчиков — verify.

Исход по умолчанию — авто; правка — нет.
Корпус: `tests/rules/MS-LIB-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/hmcontent.html

### MS-LIB-02

**прочие библиотеки.** Util, CAA, SysLib, библиотеки ОВЕН — вручную, замены — data/lib-map.toml.

Исход по умолчанию — вручную; правка — нет.
Корпус: `tests/rules/MS-LIB-02/`.

Источники:

- https://help.iek-digital.ru/Help-web/hmcontent.html

### MS-ASYNC-01

**асинхронные ФБ.** CAA-стиль xExecute/xDone/xBusy против Run/Running/Completed MS4D — вручную с картой сигналов.

Исход по умолчанию — вручную; правка — нет.
Корпус: `tests/rules/MS-ASYNC-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/rabota_s_asinchronnymi_fb.html

### MS-IO-01

**устройства и ввод-вывод.** Дерево устройств CODESYS в PLCopen XML не попадает: каналы MS4D создаёт человек, связи — по io-binding.csv.

Исход по умолчанию — вручную; правка — нет.
Корпус: `tests/rules/MS-IO-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/ob_ekt.html

### MS-VISU-01

**визуализация.** Визуализация CODESYS в PLCopen XML не экспортируется; окна MS4D рисуются заново.

Исход по умолчанию — невозможно; правка — нет.
Корпус: `tests/rules/MS-VISU-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/programmirovanie_v_masterscada_4d.html

### MS-ALARM-01

**AlarmManager.** Тревоги — вручную по инвентарю.

Исход по умолчанию — вручную; правка — нет.
Корпус: `tests/rules/MS-ALARM-01/`.

Источники:

- https://help.iek-digital.ru/Help-web/trevoga.html

### MS-MARK-01

**маркеры s7conv.** Входные маркеры // MIGRATION-TODO: и // MIGRATION-CHECK: цепочки S7 → CODESYS — сведения с исходной причиной.

Исход по умолчанию — сведения; правка — нет.
Корпус: `tests/rules/MS-MARK-01/`.

Источники:

- https://github.com/kr0nsch/s7-to-codesys
