"""Командная строка cds2ms. Коды выхода: 0 — успех, 1 — есть находки не легче --fail-on (или необъяснённые
расхождения simulate), 2 — ошибка входа или аргументов."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import TOOL, __version__, api, profiles
from .cdsfront.importer.xmltree import XmlError
from .ir.model import Project
from .rules.findings import Finding
from .rules.registry import BY_ID, OUTCOMES, RULES, SEVERITY

OUTCOME_RU = {"auto": "авто", "review": "сверить", "verify": "проверить", "manual": "вручную", "impossible": "невозможно",
              "info": "сведения"}  # fmt: skip


def _print(text: str) -> None:
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.flush()


def _load(path: str) -> Project:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"нет файла или каталога: {path}")
    return api.load_path(p)


def _opts(a: argparse.Namespace) -> api.Options:
    rw = set()
    if getattr(a, "rewrite_undocumented", None):
        rw = {x.strip() for x in a.rewrite_undocumented.split(",") if x.strip()}
    fix = getattr(a, "fix", "safe")
    if fix == "none" and rw:
        raise ValueError("--rewrite-undocumented вместе с --fix none не имеет смысла")
    if fix == "all" and not rw:
        fix = "review"
    return api.Options(
        target=getattr(a, "target", profiles.TARGET),
        fix=fix,
        rewrite=rw,
        node=getattr(a, "node", "PLC210"),
        plcopen_ns=getattr(a, "plcopen_ns", "0201"),
        overrides=getattr(a, "set", None) or [],
    )


def _fail(findings: list[Finding], fail_on: str) -> int:
    if fail_on == "never":
        return 0
    lim = SEVERITY[fail_on]
    return 1 if any(SEVERITY[f.outcome] >= lim and f.outcome != "info" for f in findings) else 0


def cmd_inventory(a: argparse.Namespace) -> int:
    proj = _load(a.input)
    inv = api.inventory(proj)
    if a.format == "json":
        _print(api.dumps(inv))
        return 0
    out = [f"{inv['file']}: {inv['kind']}, {inv['ide']} {inv['ide_version']}".rstrip(", "), ""]
    out.append("языки: " + ", ".join(f"{k} {v}" for k, v in inv["languages"].items()))
    out.append(f"POU {len(inv['pous'])}, интерфейсов {len(inv['interfaces'])}, GVL {len(inv['gvls'])}, DUT {len(inv['duts'])}, "
               f"задач {len(inv['tasks'])}")  # fmt: skip
    for p in inv["pous"]:
        extra = []
        for k in ("methods", "properties", "actions", "transitions"):
            if p[k]:
                extra.append(f"{k} {p[k]}")
        out.append(f"  {p['name']:<24} {p['kind']:<14} {p['language']:<4} {', '.join(extra)}")
    for t in inv["tasks"]:
        out.append(
            f"  задача {t['name']}: {t['kind']} {t['interval_ms']} мс, приоритет {t['priority']}, {', '.join(t['pous'])}"
        )
    _print("\n".join(out) + "\n")
    return 0


def _summary(m: api.Migration) -> str:
    t = m.report["totals"]["by_outcome"]
    e = m.report["effort"]
    parts = ", ".join(f"{OUTCOME_RU[o]} {t[o]}" for o in OUTCOMES)
    return f"  {parts}; P50 {e['p50_h']} ч, P90 {e['p90_h']} ч (модель)\n"


def cmd_analyze(a: argparse.Namespace) -> int:
    proj = _load(a.input)
    m = api.migrate(proj, _opts(a))
    if a.format == "json":
        _print(json.dumps(m.report, ensure_ascii=False, indent=2) + "\n")
    elif a.format == "md":
        _print(m.files["MIGRATION_REPORT.md"].decode("utf-8"))
    elif a.format == "html":
        _print(m.files["MIGRATION_REPORT.html"].decode("utf-8"))
    else:
        out = [f"{TOOL} {__version__}: {Path(a.input).name} → MasterSCADA 4D 1.3.10", _summary(m).rstrip("\n")]
        shown = [f for f in m.findings if f.outcome != "info" or a.verbose]
        if a.top:  # самые тяжёлые исходы первыми
            shown = sorted(shown, key=lambda f: -SEVERITY[f.outcome])[: a.top]
        for f in shown:
            place = f"{f.file}:{f.line}" if f.line else f.file
            out.append(f"  {f.rule:<11} {OUTCOME_RU[f.outcome]:<10} {f.pou or '—':<20} {place:<28} {f.message}")
        rest = len([f for f in m.findings if f.outcome != "info" or a.verbose]) - len(shown)
        if rest > 0:
            out.append(f"  … ещё {rest} (без --top — все; --format md|html|json — отчёт целиком)")
        _print("\n".join(out) + "\n")
    return _fail(m.findings, a.fail_on)


def cmd_migrate(a: argparse.Namespace) -> int:
    from .emit.bundle import make_zip

    proj = _load(a.input)
    m = api.migrate(proj, _opts(a))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(m.files.items()):
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _print(
        f"{TOOL} {__version__}: {Path(a.input).name} -> {out.as_posix()}/ ({len(m.files)} файлов, --fix {m.report['fix']})\n"
    )
    _print(_summary(m))
    if a.zip:
        Path(a.zip).parent.mkdir(parents=True, exist_ok=True)
        Path(a.zip).write_bytes(make_zip(m.files))
        _print(f"  zip: {a.zip}\n")
    if a.diff:
        _print(m.files["changes.diff"].decode("utf-8"))
    return _fail(m.findings, a.fail_on)


def cmd_simulate(a: argparse.Namespace) -> int:
    from .sim.simulate import load_expected, simulate

    proj = _load(a.input)
    m = api.migrate(proj, _opts(a))
    csv_text = Path(a.scenario).read_text(encoding="utf-8")
    expected = load_expected(Path(a.expected).read_text(encoding="utf-8")) if a.expected else []
    clocks = None
    if a.oracle:
        clocks = clocks_from_oracle(Path(a.oracle).read_text(encoding="utf-8"))
    rep = simulate(m, a.pou, csv_text, a.regime, a.cycle_ms, clocks, expected, a.masterplc_ms)
    profs = {"codesys": "codesys-3.5.17", "masterplc": profiles.TARGET}
    data = rep.to_json(profs)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "diff.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    if a.format == "json":
        _print(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    else:
        s = data["summary"]
        _print(
            f"{TOOL} simulate {a.pou} {a.regime}: сценариев {s['scenarios']}, строк {s['rows']}, collapsed {s['collapsed']}\n"
        )
        _print(f"  codesys против ожиданий сценария: несовпадений {len(rep.mismatches)}\n")
        _print(f"  codesys против masterplc: расхождений {s['divergences']}, необъяснённых {s['unexplained']}\n")
        for d in rep.divergences[:20]:
            why = f"{d.rule}: {d.explanation}" if d.rule else "НЕОБЪЯСНЕНО"
            _print(
                f"    {d.scenario} строка {d.row} t={d.t_ms} {d.signal}: codesys {d.codesys}, masterplc {d.masterplc} — {why}\n"
            )
        if rep.variant_divergences:
            vs = sorted({d.variant for d in rep.variant_divergences})
            _print(f"  варианты unknown с расхождениями (verify): {len(vs)}\n")
            for v in vs:
                _print(f"    {v}\n")
        for e in rep.errors:
            _print(f"  ошибка: {e}\n")
    return 1 if rep.unexplained or rep.mismatches or rep.errors else 0


def clocks_from_oracle(text: str) -> dict[str, list[int]]:
    """``oracle-codesys.csv``: фактическое t_ms каждого цикла стенда по сценариям."""
    import csv
    import io

    out: dict[str, list[int]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        out.setdefault(row["scenario"], []).append(int(float(row["t_ms"])))
    return out


def cmd_explain(a: argparse.Namespace) -> int:
    r = BY_ID.get(a.rule.upper())
    if r is None:
        _print(f"нет правила {a.rule}; список: {', '.join(x.id for x in RULES)}\n")
        return 2
    _print(f"{r.id} — {r.title}\nисход по умолчанию: {OUTCOME_RU[r.outcome]} ({r.outcome}); описано в справке 1.3.10: "
           f"{'да' if r.documented else 'нет'}; правка: {r.fix}\n\n{r.description}\n\nисточники:\n")  # fmt: skip
    for s in r.sources:
        _print(f"  {s}\n")
    return 0


def cmd_profiles(a: argparse.Namespace) -> int:
    if a.action == "list":
        for pid in profiles.available():
            _print(pid + "\n")
        return 0
    if a.action == "show":
        _print(profiles.load(a.id or profiles.TARGET).text)
        return 0
    if a.action == "apply-probe":
        prof = profiles.load(profiles.TARGET)
        text, changed = profiles.apply_probe(prof.text, Path(a.id).read_text(encoding="utf-8"))
        for c in changed:
            _print(c + "\n")
        if a.write:
            target = Path(__file__).parent / "profiles" / f"{profiles.TARGET}.toml"
            target.write_text(text, encoding="utf-8", newline="\n")
        return 0
    return 2


def cmd_roundtrip(a: argparse.Namespace) -> int:
    from .cdsfront.st.parser import parse_body, parse_decl
    from .cdsfront.st.printer import print_tokens

    proj = _load(a.input)
    texts: list[tuple[str, str]] = []
    for p in proj.pous:
        texts.append((f"{p.name} (объявление)", p.decl_text))
        if p.body is not None and p.body.lang in ("ST", "IL"):
            texts.append((p.name, p.body.text))
        for m in p.methods:
            texts.append((f"{p.name}.{m.name}", m.decl_text))
            if m.body is not None and m.body.lang == "ST":
                texts.append((f"{p.name}.{m.name}", m.body.text))
    for g in proj.gvls:
        texts.append((g.name, g.decl_text))
    for d in proj.duts:
        texts.append((d.name, d.decl_text))
    bad = 0
    diags = 0
    for name, t in texts:
        pd = parse_decl(t)
        pb = parse_body(t)
        if print_tokens(pd.tokens) != t or print_tokens(pb.tokens) != t:
            bad += 1
            _print(f"  расхождение печати: {name}\n")
        diags += len(pd.diagnostics) if "объявление" in name or name in {g.name for g in proj.gvls} else 0
    _print(f"round-trip: {len(texts) - bad} из {len(texts)} текстов байт в байт\n")
    return 1 if bad else 0


def cmd_probe(a: argparse.Namespace) -> int:
    from .emit.probe import write_probe_kit

    n = write_probe_kit(Path(a.out))
    _print(f"пробник: {n} файлов → {a.out}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=TOOL, description="Перенос проектов CODESYS 3.5 в MasterSCADA 4D 1.3.10 / MasterPLC"
    )
    ap.add_argument("--version", action="version", version=f"{TOOL} {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("input", help="PLCopen XML CODESYS или каталог раскладки src/")
        p.add_argument("--target", default=profiles.TARGET)
        p.add_argument("--fix", choices=["none", "safe", "review", "all"], default="safe")
        p.add_argument("--rewrite-undocumented", dest="rewrite_undocumented", default="")
        p.add_argument("--node", default="PLC210", help="имя узла ПЛК в проекте MasterSCADA 4D (для скрипта)")
        p.add_argument("--plcopen-ns", dest="plcopen_ns", choices=["0201", "0200"], default="0201")
        p.add_argument("--set", action="append", help="переопределить значение профиля: k=v")

    p = sub.add_parser("inventory", help="что в проекте: POU по языкам, GVL, DUT, задачи")
    p.add_argument("input")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_inventory)

    p = sub.add_parser("analyze", help="находки и отчёт без записи файлов")
    common(p)
    p.add_argument("--format", choices=["text", "json", "md", "html"], default="text")
    p.add_argument("--fail-on", dest="fail_on", choices=[*OUTCOMES, "never"], default="manual")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--top", type=int, default=0, help="текст: только N самых тяжёлых находок")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("migrate", help="все выходы: PLCopen XML, .ST, скрипт C#, ручные шаги, отчёт")
    common(p)
    p.add_argument("--out", required=True)
    p.add_argument("--zip", default="")
    p.add_argument("--diff", action="store_true", help="напечатать changes.diff")
    p.add_argument("--fail-on", dest="fail_on", choices=[*OUTCOMES, "never"], default="manual")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("simulate", help="сценарий CSV: original/ (codesys) против fixed/ (masterplc)")
    common(p)
    p.add_argument("--pou", required=True)
    p.add_argument("--scenario", required=True)
    p.add_argument("--regime", choices=["R1", "R2"], default="R1")
    p.add_argument("--cycle-ms", dest="cycle_ms", type=int, default=10)
    p.add_argument("--masterplc-ms", dest="masterplc_ms", type=int, default=None)
    p.add_argument("--expected", default="")
    p.add_argument("--oracle", default="", help="oracle-codesys.csv: фактические часы циклов")
    p.add_argument("--out", default="")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("explain", help="описание правила и источники")
    p.add_argument("rule")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("profiles", help="профили: list | show [id] | apply-probe RESULTS.csv [--write]")
    p.add_argument("action", choices=["list", "show", "apply-probe"])
    p.add_argument("id", nargs="?", default="")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_profiles)

    p = sub.add_parser("roundtrip", help="печать разборщика ST байт в байт на всех текстах входа")
    p.add_argument("input")
    p.set_defaults(func=cmd_roundtrip)

    p = sub.add_parser("probe", help="пробник для владельца MasterSCADA 4D")
    p.add_argument("--out", default="probe")
    p.set_defaults(func=cmd_probe)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        code: int = a.func(a)
        return code
    except (FileNotFoundError, XmlError, ValueError) as exc:
        sys.stderr.write(f"{TOOL}: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
