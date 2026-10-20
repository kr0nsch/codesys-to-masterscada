"""Реестр правил MS-*: смысл, исход по умолчанию, описано ли поведение цели, источник.

Нумерация совпадает с конспектом (R§7) там, где ID оттуда; новые продолжают семейства. ``docs/RULES.md``
строится из этого реестра (``tools/gen_docs.py``); тест падает без корпуса, URL или описания.
"""

from __future__ import annotations

from dataclasses import dataclass

HW = "https://help.iek-digital.ru/Help-web/"
CDS = "https://content.helpme-codesys.com/en/CODESYS%20Development%20System/"

OUTCOMES = ("auto", "review", "verify", "manual", "impossible", "info")
SEVERITY = {"impossible": 5, "manual": 4, "verify": 3, "review": 2, "auto": 1, "info": 0}


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    outcome: str  # исход по умолчанию
    documented: bool  # описано ли поведение цели в справке 1.3.10
    sources: tuple[str, ...]
    description: str
    fix: str = "none"  # none | auto | review | verify — уровень --fix, на котором правка применяется
    note: str = ""


RULES: tuple[Rule, ...] = (
    Rule(
        "MS-PARSE-01",
        "ошибка разбора",
        "manual",
        True,
        (CDS + "_cds_st_editor.html",),
        "Текст не разобран (ST, IL, XML): оператор восстановлен до «;» или END_*, остальной текст перенесён.",
    ),
    Rule(
        "MS-LANG-01",
        "FBD → ST",
        "review",
        True,
        (HW + "programmirovanie_v_masterscada_4d.html",),
        "Тело FBD понижено в ST: сети по номеру, внутри — порядок потока данных, разветвлённый выход → migNetN_k, "
        "блок с EN → IF. PLCopen-импорт MS4D графику не берёт (HW:-plcopenxml).",
    ),
    Rule(
        "MS-LANG-02",
        "LD → ST",
        "review",
        True,
        (HW + "redaktor_ld.html", HW + "ld-blok.html"),
        "Тело LD понижено в ST: последовательно → AND, параллельно → OR, |P|/|N| → R_TRIG/F_TRIG, катушки (S)/(R) → IF. "
        "API скриптов для LD «будет добавлено позже» (HW:programlditem).",
    ),
    Rule(
        "MS-LANG-03",
        "CFC → ST",
        "review",
        True,
        (HW + "programmirovanie_v_masterscada_4d.html",),
        "CFC в MS4D нет: порядок executionOrderId, вход от блока с бо́льшим номером — значение прошлого цикла.",
    ),
    Rule(
        "MS-LANG-04",
        "SFC → ST-автомат",
        "review",
        True,
        (
            HW + "dialog_redaktirovaniya_sfc-deystviya.html",
            "https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_sequence_of_processing.html",
        ),
        "SFC понижен в ST-автомат с порядком обработки CODESYS; SFC MS4D допускает только N/P1 со сдвигом на цикл.",
    ),
    Rule(
        "MS-LANG-05",
        "IL → ST",
        "review",
        True,
        (HW + "programmirovanie_v_masterscada_4d.html",),
        "IL в MS4D нет: символьное исполнение текущего результата, переходы — структурировщик.",
    ),
    Rule(
        "MS-LANG-06",
        "ООП → режим вызова",
        "review",
        False,
        (HW + "klyuchevye_slova.html", CDS + "_cds_obj_method.html"),
        "METHOD, PROPERTY, INTERFACE, EXTENDS в справке Master ST не описаны: методы → вход migCall и ветки CASE, "
        "свойства GET → выходы, EXTENDS → копия членов предка; полиморфизм, рекурсия, FB_init с параметрами — вручную.",
    ),
    Rule(
        "MS-LANG-07",
        "ACTION",
        "review",
        True,
        (CDS + "_cds_obj_action.html",),
        "Действие, вызываемое только из своего POU и без RETURN, встраивается; иначе — вручную.",
    ),
    Rule(
        "MS-LD-01",
        "ФБ на цепи Master LD",
        "info",
        True,
        (HW + "ld-blok.html",),
        "В Master LD вход «in» ФБ на цепи — это En: перерисованный вручную TON при ложной цепи не вызывается "
        "(в CODESYS — вызывается с IN := FALSE). Проба P-RT-12.",
    ),
    Rule(
        "MS-SFC-01",
        "квалификаторы SFC",
        "review",
        True,
        (HW + "dialog_redaktirovaniya_sfc-deystviya.html",),
        "Только N и P1 «со сдвигом на один цикл»: N не выполняется в первом цикле и выполняется ещё раз после деактивации.",
    ),
    Rule(
        "MS-SFC-02",
        "неявные переменные SFC",
        "review",
        False,
        ("https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_implicit_variables.html",),
        "шаг.x/._x/.t переводятся в переменные автомата; SFCInit/SFCReset/SFCPause/SFCError*, макрошаги — вручную.",
    ),
    Rule(
        "MS-FBD-01",
        "порядок FBD MS4D",
        "info",
        True,
        (HW + "poryadok_ispolnenia_fbd-blokov.html",),
        "Порядок блоков FBD в MS4D — по потоку данных или геометрии, явной нумерации CFC нет.",
    ),
    Rule(
        "MS-ST-01",
        "EN/ENO в ST",
        "review",
        True,
        (HW + "obrabotka_en_eno.html",),
        "EN/ENO в исходнике ST — явные переменные ФБ; в MS4D это ключевые слова и En в ST не поддерживается: "
        "переименование в migEN/migENO в объявлении и вызовах.",
        fix="review",
    ),
    Rule(
        "MS-ST-02",
        "запрещённые «_» в именах",
        "auto",
        True,
        (HW + "identifikatory.html",),
        "Два и более «_» подряд в начале или внутри, «_» в конце запрещены: переименование.",
        fix="auto",
    ),
    Rule(
        "MS-ST-03",
        "тело отдельно от объявлений",
        "auto",
        True,
        (HW + "redaktor_st.html", HW + "legenda_vkladka_zagolovok_st.html"),
        "Редактор ST — только тело; объявления — дерево и «Заголовок ST». Переменным из текста «нельзя задать связь»: "
        "интерфейс POU переносится структурой PLCopen XML, а не текстом.",
        fix="auto",
    ),
    Rule(
        "MS-ST-04",
        "CASE по ENUM",
        "verify",
        False,
        (HW + "operator_case.html",),
        "CASE описан для целых; ENUM с явными значениями и литерал E_State.Run — проба P-ST-02.",
    ),
    Rule(
        "MS-ST-05",
        "указатели и ссылки",
        "manual",
        False,
        (HW + "klyuchevye_slova.html", HW + "specialnye_tipy_dannyh.html"),
        "POINTER, REFERENCE, ADR, __NEW, SIZEOF, MEMCPY в Master ST не описаны (REF_TO — не ссылка). REFERENCE TO в "
        "параметре → var_inout (review).",
    ),
    Rule(
        "MS-ST-07",
        "прямые адреса",
        "review",
        True,
        (HW + "ob_ekt.html", HW + "teg.html"),
        "AT %I/%Q → параметр без адреса + строка io-binding.csv (связь с каналом); %M-наложения — вручную.",
        fix="review",
    ),
    Rule(
        "MS-ST-08",
        "GVL → параметры узла",
        "auto",
        True,
        (HW + "globalnye_peremennye.html",),
        "Глобальные — параметры узла, в папке называются Папка_Имя: GVL.x → GVL_x.",
        fix="auto",
    ),
    Rule(
        "MS-ST-09",
        "VAR_TEMP",
        "info",
        True,
        (HW + "parametry_programm.html",),
        "VAR_TEMP ↔ доступ Temp; в «Отладочной конфигурации» Temp транслируется как Local.",
    ),
    Rule(
        "MS-ST-10",
        "«Переключение» BOOL-параметров",
        "info",
        True,
        (HW + "parametry_programm.html",),
        "У BOOL-параметров программ MS4D есть «Переключение» R_EDGE/F_EDGE — неявный фронт на входе.",
    ),
    Rule(
        "MS-ST-11",
        "S= / R=",
        "auto",
        True,
        (CDS + "_cds_operator_set_reset.html",),
        "Присваивания S=/R= → IF … THEN x := TRUE/FALSE.",
        fix="auto",
    ),
    Rule(
        "MS-ST-12",
        "REF=",
        "manual",
        False,
        (CDS + "_cds_datatype_reference.html",),
        "Присваивание ссылки REF= — вручную.",
    ),
    Rule(
        "MS-ST-13",
        "JMP и метки",
        "review",
        False,
        (HW + "operatory_master_st.html",),
        "JMP в операторах Master ST нет: переходы вперёд → IF над хвостом, иначе автомат migPc.",
        fix="review",
    ),
    Rule(
        "MS-NAME-01",
        "нормализация и коллизии имён",
        "auto",
        True,
        (HW + "parametry_programm.html", HW + "globalnye_peremennye.html"),
        "Спецсимволы в именах дерева → «_»; коллизия после префиксов и GVL_x → суффикс (review).",
        fix="auto",
    ),
    Rule(
        "MS-NAME-02",
        "ключевые слова MS4D и Lua",
        "auto",
        True,
        (HW + "klyuchevye_slova.html", "https://www.lua.org/manual/5.4/manual.html#3.1"),
        "Имя CODESYS — ключевое слово MS4D (NULL, R_EDGE, STEP, TASK, EN, …) → переименование (auto); слово Lua "
        "(local, nil, end, goto, …) → verify, проба P-ST-04.",
        fix="auto",
    ),
    Rule(
        "MS-DECL-01",
        "VAR_IN_OUT",
        "verify",
        True,
        (HW + "osnovnye_tipy_obavleniy.html",),
        "VAR_IN_OUT → var_inout (auto); передаётся ли ссылкой — в справке не описано (verify).",
        fix="auto",
    ),
    Rule(
        "MS-DECL-02",
        "VAR_STAT",
        "review",
        False,
        (HW + "osnovnye_tipy_obavleniy.html",),
        "VAR_STAT (общая для экземпляров ФБ, в FUNCTION хранит значение между вызовами) → глобальный параметр "
        "узла mig<POU>_<имя>.",
        fix="review",
    ),
    Rule(
        "MS-DECL-04",
        "VAR_GLOBAL CONSTANT",
        "review",
        True,
        (HW + "constanty.html",),
        'Список констант → globalVars constant="true" (куда ляжет — проба P-ST-08); запасной путь — «Константа» библиотеки.',
    ),
    Rule(
        "MS-DECL-06",
        "PERSISTENT",
        "review",
        False,
        (HW + "sohranenie_sostoyania.html", CDS + "_cds_var_persistent.html"),
        "PERSISTENT → RETAIN: аналога «переживает загрузку» нет.",
        fix="review",
    ),
    Rule(
        "MS-RET-01",
        "хранение retain",
        "info",
        True,
        (HW + "sohranenie_sostoyania.html",),
        "Retain пишется периодически или при остановке, есть «время актуальности»; InOut-параметры программ не сохраняются.",
    ),
    Rule(
        "MS-RET-02",
        "холодный рестарт",
        "verify",
        False,
        (HW + "modifikatory_operatorov_opredeleniya_peremennyh.html",),
        "Справка описывает RETAIN как восстановление «при холодном рестарте» — термины CODESYS не совпадают.",
    ),
    Rule(
        "MS-TYPE-02",
        "LTIME, WSTRING, STRING(n)",
        "review",
        False,
        (HW + "elementarnye_tipy_dannyh.html",),
        "LTIME → TIME (точность мс), WSTRING → STRING, STRING(n) → STRING (без длины, UTF-8); LEN над кириллицей — verify.",
        fix="review",
    ),
    Rule(
        "MS-TYPE-03", "UNION", "manual", False, (HW + "noviy_tip_parametra.html",), "UNION в типах MS4D нет — вручную."
    ),
    Rule(
        "MS-TYPE-04",
        "alias, subrange, ENUM с базой",
        "auto",
        True,
        (HW + "noviy_tip_parametra.html",),
        "Псевдоним → базовый тип, поддиапазон → базовый тип (диапазон — в комментарии), базовый тип ENUM снимается.",
        fix="auto",
    ),
    Rule(
        "MS-TYPE-05",
        "массивы",
        "review",
        True,
        (HW + "redaktor_tipa_massiv.html",),
        "Не больше трёх осей; выход за границы даёт NULL, а не исключение.",
    ),
    Rule(
        "MS-TYPE-06",
        "DT по умолчанию",
        "review",
        True,
        (HW + "inicializaciya_peremennyh.html",),
        "DT по умолчанию DT#0001-01-01-00:00:00, в CODESYS — 1970: сравнение с DT#1970… ломается молча.",
    ),
    Rule(
        "MS-TYPE-07",
        "целочисленная арифметика в Lua",
        "verify",
        False,
        (HW + "osobennosti_bitovyh_strok.html",),
        "Переполнение знаковых, деление целых и /0 в трансляторе Lua 5.4 не описаны — пробы P-RT-01, P-RT-02.",
    ),
    Rule(
        "MS-TYPE-08",
        "TIME со знаком",
        "verify",
        False,
        (HW + "vremennye_konstanty.html", CDS + "_cds_datatype_time.html"),
        "В CODESYS TIME — DWORD мс без знака (переход через 0 в tNow - tStart), в MS4D — со знаком, разрядность не описана.",
    ),
    Rule(
        "MS-TYPE-09",
        "REAL и REAL_TO_*",
        "verify",
        False,
        (HW + "funkcii_preobrazovaniya_tipa.html", CDS + "_cds_operator_real_to.html"),
        "REAL float32 против double Lua; REAL_TO_* на половинах (CODESYS: −1.5 → −2) — проба P-RT-03.",
    ),
    Rule(
        "MS-EXEC-01",
        "квантование таймеров",
        "review",
        True,
        (HW + "zadachi.html",),
        "Задача MS4D по умолчанию 100 мс: таймер срабатывает в первом цикле после уставки (150 мс → 200 мс).",
    ),
    Rule(
        "MS-EXEC-02",
        "событийные задачи",
        "review",
        False,
        (HW + "zadachi.html", CDS + "_cds_f_task_configuration.html"),
        "Event/freewheeling/status → циклическая задача + фронт; external event — невозможно.",
    ),
    Rule(
        "MS-EXEC-03",
        "порядок программ",
        "review",
        True,
        (HW + "poryadok_vychislniy_i_peredachi.html", HW + "vyzov_programm_obektov.html"),
        "Порядок программ — дерево узла (Item.Position только чтение): диспетчер migTask_<T> вызывает программы в порядке CODESYS.",
    ),
    Rule(
        "MS-EXEC-04",
        "связи и прямой доступ",
        "info",
        True,
        (HW + "poryadok_vychislniy_i_peredachi.html",),
        "Связи отрабатываются до программ, прямой доступ из ST — в момент обращения.",
    ),
    Rule(
        "MS-EXEC-05",
        "выход вызываемой программы",
        "info",
        True,
        (HW + "peredacha_znacheniy_iz_vyzyvaemoy_programmy.html",),
        "Выход вызываемой программы через связь не доходит — нужен прямой доступ.",
    ),
    Rule(
        "MS-EXEC-06",
        "приоритеты задач",
        "verify",
        False,
        (HW + "zadachi.html",),
        "Приоритеты 0–31 CODESYS → MS4D: направление шкалы не описано, неверный приоритет может повесить ПЛК.",
    ),
    Rule(
        "MS-EXEC-07",
        "период и производительность",
        "info",
        True,
        ("https://support.mps-soft.ru/PLC_Library/zadachi_isp_sistemi_owen.html",),
        "Задача 10 мс на ПЛК210-0x (Cortex-A8, Lua) — укладывание в период сверить; C# только на ПЛК210-1x.",
    ),
    Rule(
        "MS-LIB-01",
        "библиотека Standard",
        "auto",
        True,
        (HW + "hmcontent.html",),
        "TON/TOF/TP/R_TRIG/F_TRIG/RS/SR/CTU/CTD/CTUD есть в «Стандартной»; типы PV/CV счётчиков — verify.",
    ),
    Rule(
        "MS-LIB-02",
        "прочие библиотеки",
        "manual",
        True,
        (HW + "hmcontent.html",),
        "Util, CAA, SysLib, библиотеки ОВЕН — вручную, замены — data/lib-map.toml.",
    ),
    Rule(
        "MS-ASYNC-01",
        "асинхронные ФБ",
        "manual",
        True,
        (HW + "rabota_s_asinchronnymi_fb.html",),
        "CAA-стиль xExecute/xDone/xBusy против Run/Running/Completed MS4D — вручную с картой сигналов.",
    ),
    Rule(
        "MS-IO-01",
        "устройства и ввод-вывод",
        "manual",
        True,
        (HW + "ob_ekt.html",),
        "Дерево устройств CODESYS в PLCopen XML не попадает: каналы MS4D создаёт человек, связи — по io-binding.csv.",
    ),
    Rule(
        "MS-VISU-01",
        "визуализация",
        "impossible",
        True,
        (HW + "programmirovanie_v_masterscada_4d.html",),
        "Визуализация CODESYS в PLCopen XML не экспортируется; окна MS4D рисуются заново.",
    ),
    Rule("MS-ALARM-01", "AlarmManager", "manual", True, (HW + "trevoga.html",), "Тревоги — вручную по инвентарю."),
    Rule(
        "MS-MARK-01",
        "маркеры s7conv",
        "info",
        True,
        ("https://github.com/kr0nsch/s7-to-codesys",),
        "Входные маркеры // MIGRATION-TODO: и // MIGRATION-CHECK: цепочки S7 → CODESYS — сведения с исходной причиной.",
    ),
)

BY_ID: dict[str, Rule] = {r.id: r for r in RULES}


def rule(rid: str) -> Rule:
    return BY_ID[rid]


def heavier(a: str, b: str) -> str:
    return a if SEVERITY[a] >= SEVERITY[b] else b
