# Источники

Справка MasterSCADA 4D 1.3.10 сверялась 19–20.10.2026; `HW:<страница>` = `https://help.iek-digital.ru/Help-web/<страница>.html`.
Текст справки в репозиторий не копируется — только ссылки и снимок сигнатур API (`csharp/api-snapshot.tsv`).

## Зачем инструмент (рынок и нормы)

- ОВЕН о CODESYS V3.5 на ПЛК210/ПЛК200: https://ftp.owen.ru/CoDeSys3/99_ForumFiles/webinar_CodesysFaq_dec2021.pdf
- ПЛК ОВЕН в MasterSCADA 4D: https://support.mps-soft.ru/PLC_Library/owen.html
- MasterPLC в реестре отечественного ПО: https://iek-digital.ru/products/masterplc/
- Поставки CODESYS в РФ: https://forge.codesys.com/forge/talk/Engineering/thread/a642d5cb92/
- История выпусков MasterSCADA 4D (1.3.10, PLCopen-импорт с 1.2.15): https://iek-digital.ru/products/release-history/
- Жалоба на документацию: https://habr.com/ru/post/469407

## MasterSCADA 4D 1.3.10

| Тема | Страницы |
|---|---|
| Языки, компиляция, Lua 5.4 / C# | `HW:programmirovanie_v_masterscada_4d`, `HW:kompilyaciya_programm` |
| Импорт PLCopen XML, `.ST` | `HW:-plcopenxml`, `HW:export_i_import_programm_st` |
| ST: редактор, объявления, ключевые слова, идентификаторы, EN/ENO | `HW:redaktor_st`, `HW:osnovnye_tipy_obavleniy`, `HW:klyuchevye_slova`, `HW:identifikatory`, `HW:obrabotka_en_eno` |
| LD, SFC, FBD | `HW:redaktor_ld`, `HW:ld-blok`, `HW:dialog_redaktirovaniya_sfc-deystviya`, `HW:poryadok_ispolnenia_fbd-blokov`, `HW:fbd_c` |
| Задачи, порядок вычислений | `HW:zadachi`, `HW:poryadok_vychislniy_i_peredachi`, `HW:vyzov_programm_obektov` |
| Глобальные, константы, сохранение | `HW:globalnye_peremennye`, `HW:constanty`, `HW:sohranenie_sostoyania` |
| Типы | `HW:noviy_tip_parametra`, `HW:specialnye_tipy_dannyh` |
| Скрипты C#: объектная модель | `HW:script_c`, `HW:obshie_svedenia_c`, `HW:auto_develop_project`, `HW:item`, `HW:controlleritem`, `HW:taskitem`, `HW:attributeitem`, `HW:programparamitem`, `HW:localvaritem`, `HW:variableitem`, `HW:programitem`, `HW:programstitem`, `HW:programlditem`, `HW:objectitem`, `HW:objectsitem`, `HW:objectortagbase`, `HW:alarmusageitem` |
| Библиотеки | `HW:hmcontent` |
| Установка, эмуляция, лицензия | `HW:ustanovka_sredw_razrabotki_masterscada_4d`, `HW:emulyacia`, `HW:licenzionnaya_politika` |
| API веб-сервера (на будущее) | https://support.mps-soft.ru/API_MS4_web/methodscallpou.html |

Установка 1.3.10 Demo — официальный FTP ОВЕН: https://ftp.owen.ru/MasterSCADA_4D/ (документация — `11_Documentation`,
прошивки — `10_Firmware`).

## CODESYS 3.5.17

- PLCopen XML: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_cmd_export_plcopenxml.html
- SFC: квалификаторы — https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_action_qualifier.html ;
  неявные переменные — https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_implicit_variables.html ;
  порядок обработки — https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_sequence_of_processing.html
  (те же страницы — в локальной справке `codesys.chm` 3.5.17.30)
- TIME/LTIME: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_time.html
- REAL_TO_*: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_operator_real_to.html
- STRING: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_string.html
- Задачи: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_f_task_configuration.html

## Форматы и инструменты

- XSD PLCopen TC6 2.01 (85 975 байт, SHA-256 `591b92ba65018a77c32ab9e606abf27bd810cb1f7761d972a85689531c51e20f`):
  https://www.plcopen.org/download_file/force/d397ab98-6a21-47d5-9fb1-37da9e94ef34/342/
- RuSTy v1.0.6: https://github.com/PLC-lang/rusty/releases/tag/v1.0.6
- Pyodide 314.0.7 (MPL-2.0): https://registry.npmjs.org/pyodide/-/pyodide-314.0.7.tgz , https://github.com/pyodide/pyodide
- Сценарии и формат трасс семейства: s7-to-codesys `scenarios/README.md`

## Кейсы

- s7-to-codesys @2285760c1c99ce4218d5356c75e93111828f8e3b (MIT): https://github.com/kr0nsch/s7-to-codesys
- plc-process-lib @a321ad01f47eae4f5c29ed46d9764a2d738c2dd4 (MIT): https://github.com/kr0nsch/plc-process-lib
