"""MIGRATION_REPORT.{json,md,html}: ядро семейства (schemas/report-core.schema.json) и расширения cds2ms."""

from __future__ import annotations

import html
import json
from collections import Counter
from typing import Any

from .. import TOOL, __version__
from ..cdsfront.lower import LoweredProject
from ..rules.findings import Finding
from ..rules.registry import BY_ID, OUTCOMES, SEVERITY

HW = "https://help.iek-digital.ru/Help-web/"
OUTCOME_RU = {"auto": "авто", "review": "сверить", "verify": "проверить", "manual": "вручную", "impossible": "невозможно",
              "info": "сведения"}  # fmt: skip

# Матрица автоматизируемости: конструкция × канал × исход × уверенность (H/M/L) × источник
MATRIX: list[tuple[str, str, str, str, str, str]] = [
    (
        "POU на ST (PROGRAM, FB, FUNCTION)",
        "ST",
        "PLCopen XML (types/pous) или .ST",
        "auto",
        "H",
        HW + "-plcopenxml.html",
    ),
    ("Тело FBD", "FBD", "понижение в ST → PLCopen XML", "review", "H", HW + "-plcopenxml.html"),
    ("Тело LD", "LD", "понижение в ST → PLCopen XML", "review", "H", HW + "programlditem.html"),
    ("Тело CFC", "CFC", "понижение в ST → PLCopen XML", "review", "H", HW + "programmirovanie_v_masterscada_4d.html"),
    (
        "Тело SFC",
        "SFC",
        "ST-автомат → PLCopen XML; SFC MS4D — вручную",
        "review",
        "H",
        HW + "dialog_redaktirovaniya_sfc-deystviya.html",
    ),
    ("Тело IL", "IL", "понижение в ST → PLCopen XML", "review", "H", HW + "programmirovanie_v_masterscada_4d.html"),
    ("METHOD", "ST", "режим вызова migCall → PLCopen XML", "review", "M", HW + "klyuchevye_slova.html"),
    ("PROPERTY", "ST", "GET → VAR_OUTPUT, SET → ветка migCall", "review", "M", HW + "klyuchevye_slova.html"),
    (
        "INTERFACE и полиморфизм",
        "ST",
        "подстановка экземпляра или вручную",
        "manual",
        "M",
        HW + "klyuchevye_slova.html",
    ),
    ("EXTENDS", "ST", "копия членов предка", "review", "M", HW + "klyuchevye_slova.html"),
    ("GVL", "DECL", "globalVars → параметры узла GVL_x", "auto", "M", HW + "globalnye_peremennye.html"),
    ("VAR_GLOBAL CONSTANT", "DECL", "globalVars constant", "review", "L", HW + "constanty.html"),
    ("RETAIN", "DECL", "retain в XML / Saving = RETAIN скриптом", "review", "M", HW + "sohranenie_sostoyania.html"),
    ("PERSISTENT", "DECL", "→ RETAIN", "review", "M", HW + "sohranenie_sostoyania.html"),
    ("STRUCT, ENUM, ARRAY ≤ 3", "DECL", "types/dataTypes", "auto", "H", HW + "noviy_tip_parametra.html"),
    ("Псевдоним, поддиапазон", "DECL", "подстановка базового типа", "auto", "M", HW + "noviy_tip_parametra.html"),
    ("UNION", "DECL", "—", "manual", "M", HW + "noviy_tip_parametra.html"),
    ("POINTER, REFERENCE, ADR", "ST", "—", "manual", "M", HW + "specialnye_tipy_dannyh.html"),
    ("Задача циклическая", "PROJECT", "C#-скрипт AddTask / tasks.md", "review", "H", HW + "taskitem.html"),
    ("Задача событийная, freewheeling", "PROJECT", "циклическая + фронт", "review", "M", HW + "zadachi.html"),
    (
        "Порядок программ в задаче",
        "PROJECT",
        "диспетчер migTask_<T> скриптом",
        "review",
        "H",
        HW + "vyzov_programm_obektov.html",
    ),
    ("AT %I/%Q", "DECL", "параметр + io-binding.csv, связь — вручную", "review", "H", HW + "variableitem.html"),
    ("Standard: TON, R_TRIG, CTU …", "ST", "одноимённые блоки «Стандартной»", "auto", "H", HW + "hmcontent.html"),
    ("Util, CAA, SysLib, ОВЕН", "ST", "—", "manual", "H", HW + "hmcontent.html"),
    ("Устройства, Modbus, модули", "PROJECT", "каналы создаёт человек", "manual", "H", HW + "ob_ekt.html"),
    ("Визуализация", "PROJECT", "—", "impossible", "H", HW + "programmirovanie_v_masterscada_4d.html"),
]


def counts(findings: list[Finding]) -> dict[str, int]:
    c = Counter(f.outcome for f in findings)
    return {o: int(c.get(o, 0)) for o in OUTCOMES}


def build_json(
    lp: LoweredProject,
    findings: list[Finding],
    effort: dict[str, Any],
    profile_id: str,
    fix: str,
    equivalence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p = lp.project
    by_lang: dict[str, list[Finding]] = {}
    for f in findings:
        by_lang.setdefault(f.language, []).append(f)
    pous = []
    for x in lp.pous:
        fs = [f for f in findings if (f.pou or "").lower() == x.name.lower()]
        worst = max((f.outcome for f in fs), key=lambda o: SEVERITY[o], default="auto")
        pous.append({
            "name": x.name, "kind": x.kind, "language": x.lang, "outcome": worst, "findings": len(fs),
            "methods": x.had_methods, "properties": x.had_properties,
            "effort_h": effort.get("by_pou", {}).get(x.name, {"p50_h": 0.0, "p90_h": 0.0}),
        })  # fmt: skip
    core: dict[str, Any] = {
        "format": "plc-migration-report/1",
        "tool": {"name": TOOL, "version": __version__},
        "source": {"kind": p.source_kind, "sha256": p.source_sha256},
        "target": {"profile": profile_id, "version": "1.3.10"},
        "totals": {
            "by_outcome": counts(findings),
            "by_language": {k: counts(v) for k, v in sorted(by_lang.items())},
        },
        "findings": [f.to_json() for f in findings],
        "effort": {
            k: v
            for k, v in effort.items()
            if k in ("model", "runs", "seed", "p50_h", "p90_h", "calibrated", "calibration")
        },
    }
    if p.ide:
        core["source"]["ide"] = p.ide
    if p.ide_version:
        core["source"]["ide_version"] = p.ide_version
    if equivalence is not None:
        core["equivalence"] = equivalence
    core["project"] = {
        "name": p.name,
        "file": p.source_file.replace("\\", "/").rsplit("/", 1)[-1],
        "placements": p.placements,
        "languages": p.languages(),
        "pous": pous,
        "gvls": [g.name for g in p.gvls],
        "duts": [d.name for d in p.duts],
        "tasks": [
            {"name": t.name, "kind": t.kind, "interval_ms": t.interval_ms, "priority": t.priority, "pous": t.pous}
            for t in p.tasks
        ],
    }
    core["effort_by_pou"] = effort.get("by_pou", {})
    core["fix"] = fix
    core["automatability"] = [
        {"construct": c, "language": lang, "channel": ch, "outcome": o, "confidence": conf, "source": src}
        for c, lang, ch, o, conf, src in MATRIX
    ]
    return core


def to_json_text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def build_md(data: dict[str, Any]) -> str:
    t = data["totals"]["by_outcome"]
    e = data["effort"]
    pr = data["project"]
    lines = [
        f"# Отчёт о переносе: {pr['name'] or pr['file']} → MasterSCADA 4D 1.3.10",
        "",
        f"создано {data['tool']['name']} {data['tool']['version']} · {pr['file']} · SHA-256 {data['source']['sha256']}",
        "",
        "| Исход | Находок |",
        "|---|---|",
    ]
    lines += [f"| {OUTCOME_RU[o]} ({o}) | {t[o]} |" for o in OUTCOMES]
    lines += [
        "",
        f"Трудоёмкость: P50 {e['p50_h']} ч, P90 {e['p90_h']} ч — {e.get('calibration', 'модель')}"
        f" ({e.get('runs', 0)} проб, seed {e.get('seed', 0)}).",
        "",
        "## POU",
        "",
        "| POU | Вид | Язык | Тяжелейший исход | Находок | P50 / P90, ч |",
        "|---|---|---|---|---|---|",
    ]
    for p in pr["pous"]:
        eh = p["effort_h"]
        lines.append(
            f"| {p['name']} | {p['kind']} | {p['language']} | {OUTCOME_RU[p['outcome']]} | {p['findings']} | "
            f"{eh['p50_h']} / {eh['p90_h']} |"
        )
    lines += ["", "## Находки", "", "| Правило | Исход | Язык | POU | Место | Что |", "|---|---|---|---|---|---|"]
    for f in data["findings"]:
        o = f["origin"]
        place = f"{o['file']}:{o.get('line', '')}" if o.get("line") else o["file"]
        msg = f["message"].replace("|", "\\|")
        lines.append(
            f"| {f['rule']} | {OUTCOME_RU[f['outcome']]} | {f['language']} | {f.get('pou', '')} | {place} | {msg} |"
        )
    lines += [
        "",
        "## Матрица автоматизируемости",
        "",
        "| Конструкция | Канал | Исход | Ув. | Источник |",
        "|---|---|---|---|---|",
    ]
    for m in data["automatability"]:
        lines.append(
            f"| {m['construct']} | {m['channel']} | {OUTCOME_RU[m['outcome']]} | {m['confidence']} | {m['source']} |"
        )
    if "equivalence" in data:
        eq = data["equivalence"]
        lines += ["", "## Поведение (симулятор)", "", f"Сценариев {eq['scenarios']}, строк {eq.get('rows', 0)}, совпало "
                  f"{eq['passed']}, объяснённых расхождений {eq.get('xfail', 0)}. Оракулы: {', '.join(eq['oracles'])}."]  # fmt: skip
    return "\n".join(lines) + "\n"


_CSS = """
:root{--bg:#0f1720;--panel:#16212d;--ink:#e6edf3;--mute:#8b9bb0;--line:#26364a;--acc:#ea580c;
--auto:#3d8b6e;--review:#c08a2e;--verify:#b4682a;--manual:#c2410c;--impossible:#9b1c1c;--info:#56677d}
@media (prefers-color-scheme: light){:root{--bg:#f6f7f9;--panel:#fff;--ink:#1b2736;--mute:#56677d;--line:#d7dde5}}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.sub{color:var(--mute);font-size:12px;word-break:break-all}
.tiles{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--c);padding:8px 12px;min-width:110px}
.tile b{display:block;font-size:22px}.tile span{color:var(--mute);font-size:12px}
table{border-collapse:collapse;width:100%;background:var(--panel);font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
th{color:var(--mute);font-weight:600}.o{font-weight:600;color:var(--c)}
.wrap{overflow-x:auto}a{color:var(--acc)}
"""


def build_html(data: dict[str, Any]) -> str:
    t = data["totals"]["by_outcome"]
    e = data["effort"]
    pr = data["project"]
    esc = html.escape
    tiles = "".join(
        f'<div class="tile" style="--c:var(--{o})"><b>{t[o]}</b><span>{OUTCOME_RU[o]}</span></div>' for o in OUTCOMES
    )
    tiles += (
        f'<div class="tile" style="--c:var(--acc)"><b>{e["p50_h"]} / {e["p90_h"]}</b>'
        f"<span>P50 / P90, ч — {esc(str(e.get('calibration', 'модель')))}</span></div>"
    )
    rows = "".join(
        f"<tr><td>{esc(p['name'])}</td><td>{p['kind']}</td><td>{p['language']}</td>"
        f'<td class="o" style="--c:var(--{p["outcome"]})">{OUTCOME_RU[p["outcome"]]}</td><td>{p["findings"]}</td>'
        f"<td>{p['effort_h']['p50_h']} / {p['effort_h']['p90_h']}</td></tr>"
        for p in pr["pous"]
    )
    frows = ""
    for f in data["findings"]:
        o = f["origin"]
        place = f"{o['file']}:{o.get('line', '')}" if o.get("line") else o["file"]
        r = BY_ID[f["rule"]]
        frows += (
            f'<tr><td><a href="{esc(f["source_ref"])}">{f["rule"]}</a></td>'
            f'<td class="o" style="--c:var(--{f["outcome"]})">{OUTCOME_RU[f["outcome"]]}</td>'
            f"<td>{f['language']}</td><td>{esc(f.get('pou', ''))}</td><td>{esc(place)}</td>"
            f'<td>{esc(f["message"])}<br><span class="sub">{esc(r.title)}</span></td></tr>'
        )
    mrows = "".join(
        f"<tr><td>{esc(m['construct'])}</td><td>{esc(m['channel'])}</td>"
        f'<td class="o" style="--c:var(--{m["outcome"]})">{OUTCOME_RU[m["outcome"]]}</td><td>{m["confidence"]}</td>'
        f'<td><a href="{esc(m["source"])}">справка</a></td></tr>'
        for m in data["automatability"]
    )
    title = esc(pr["name"] or pr["file"])
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Отчёт о переносе — {title}</title><style>{_CSS}</style></head>
<body><main>
<h1>Перенос {title} → MasterSCADA 4D 1.3.10</h1>
<div class="sub">создано {data["tool"]["name"]} {data["tool"]["version"]} · {esc(pr["file"])} · SHA-256 {data["source"]["sha256"]}</div>
<div class="tiles">{tiles}</div>
<h2>POU</h2><div class="wrap"><table><tr><th>POU</th><th>Вид</th><th>Язык</th><th>Исход</th><th>Находок</th><th>P50 / P90, ч</th></tr>{rows}</table></div>
<h2>Находки</h2><div class="wrap"><table><tr><th>Правило</th><th>Исход</th><th>Язык</th><th>POU</th><th>Место</th><th>Что</th></tr>{frows}</table></div>
<h2>Матрица автоматизируемости</h2><div class="wrap"><table><tr><th>Конструкция</th><th>Канал</th><th>Исход</th><th>Ув.</th><th>Источник</th></tr>{mrows}</table></div>
<p class="sub">Трудоёмкость — модель семейства (треугольное распределение, Монте-Карло), не замер. Исходы «проверить» —
поведение цели в справке 1.3.10 не описано, проба — probe/README.md.</p>
</main></body></html>
"""
