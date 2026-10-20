# Правила разработки

## Контекст

- Репозиторий — часть открытого портфолио инженера АСУ ТП (kr0nsch, github.com/kr0nsch), серия
  «Миграция ПЛК-проектов». Честность важнее объёма: в README и docs — только то, что проверено, с датой и
  версией среды; неописанное справкой — «не описано», а не догадка.
- Источник: CODESYS 3.5 (ОВЕН ПЛК2xx на SP17 Patch 3). Цель: MasterSCADA 4D 1.3.10 / MasterPLC.
- Инструмент неофициальный. Проект не связан с компаниями ОВЕН, Прософт-Системы, РегЛаб, ООО «ИЭК ДИДЖИТАЛ» и
  CODESYS GmbH; названия продуктов — товарные знаки их владельцев.

## Язык и оформление

- Идентификаторы — ASCII, по-английски. Комментарии, docstring, сообщения и документация — по-русски.
- UTF-8 без BOM, LF (`.gitattributes`); экспорты CODESYS (`corpus/udr1/source.cds.xml`, `tests/fixtures/sp17/`)
  хранятся байт в байт.
- Python 3.11+, пакет `src/cds2ms/` — только стандартная библиотека (работает в Pyodide; это проверяет тест).
  `ruff check`, `ruff format`, `mypy --strict`, pytest; покрытие `cds2ms` — строки ≥ 85 %, ветви ≥ 75 %.

## Данные о MasterSCADA 4D

- Нет источника — нет строки. У каждой возможности профиля (`src/cds2ms/profiles/*.toml`) — статус
  (`supported | unsupported | unknown`), уверенность H/M/L и URL страницы справки; у правила — источник и описание.
- Текст справки не копируется — только ссылки и снимок сигнатур API (`csharp/api-snapshot.tsv`).
- Файлы проекта MasterSCADA (`.fdb`, `.json`, `.ms4proj`) не пишутся и не разбираются; DT и RT не декомпилируются;
  внутренняя объектная модель (`ItemInstance` и др.) не используется — только внешняя.
- XSD TC6 2.01 и чужие файлы без лицензии в git не кладутся: только `.cache/` по SHA-256.

## Как добавить правило

1. Строка в `src/cds2ms/rules/registry.py`: ID `MS-…`, заголовок, исход по умолчанию, описано ли поведение в
   справке, URL, описание, уровень правки.
2. Детектор в `src/cds2ms/rules/engine.py`; правка — `Edit` по диапазону токенов (форматирование не трогается).
3. Случаи pos/neg — `tools/gen_rule_corpus.py`; минуты — `src/cds2ms/data/effort.toml`.
4. `python tools/gen_docs.py` (обновит `docs/RULES.md`).
5. Если правка меняет поведение — сценарий в корпусе и запись в `expected-divergences.toml` с объяснением.

## Проверки перед коммитом

```bash
python -m ruff check . && python -m ruff format --check . && python -m mypy
python -m pytest --cov=cds2ms --cov-branch --cov-report=json:build/coverage.json && python tools/check_coverage.py
python tools/gen_docs.py --check
python tools/rusty_check.py          # если установлен RuSTy 1.0.6
```

С CODESYS 3.5.17.30 на машине — `python tools/codesys/corpus.py` (корпус, экспорт, трассы; под блокировкой
рантайма, чужой рантайм не останавливается). С MasterSCADA 4D — `python tools/csc_check.py out/<имя> --real` и
`python tools/ms4d_check.py`.

## Git

- Conventional Commits по-русски (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`), небольшие осмысленные
  коммиты, без служебных трейлеров.
- В `main` — только зелёные проверки; golden пересобираются отдельным коммитом.
