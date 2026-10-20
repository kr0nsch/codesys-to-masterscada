"""Программный интерфейс cds2ms: загрузка входа, анализ, перенос, симуляция (тот же код — CLI и браузер)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import profiles
from .cdsfront.importer import layout, plcopen
from .cdsfront.lower import LoweredProject, lower_project
from .ir.model import Project
from .rules.engine import Analysis, analyze
from .rules.findings import Finding
from .transform.master_st import FixedObject, transform


@dataclass
class Options:
    target: str = profiles.TARGET
    fix: str = "safe"
    rewrite: set[str] = field(default_factory=set)
    node: str = "PLC210"
    plcopen_ns: str = "0201"
    overrides: list[str] = field(default_factory=list)


@dataclass
class Migration:
    project: Project
    lowered: LoweredProject
    analysis: Analysis
    fixed: dict[str, FixedObject]
    report: dict[str, Any]
    files: dict[str, bytes]
    name: str

    @property
    def findings(self) -> list[Finding]:
        return self.analysis.findings


def load_path(path: Path) -> Project:
    if path.is_dir():
        root = path / "src" if (path / "src").is_dir() else path
        return layout.load(root, base=path.name)
    return plcopen.load(path.read_bytes(), path.name)


def load_bytes(name: str, data: bytes) -> Project:
    return plcopen.load(data, name)


def load_files(name: str, files: dict[str, str]) -> Project:
    return layout.load_files(files, name=name, base=name)


def safe_name(project: Project) -> str:
    base = project.name or Path(project.source_file.replace("\\", "/")).stem or "project"
    base = re.sub(r"\.(project|library)$", "", base, flags=re.IGNORECASE)  # contentHeader экспорта CODESYS: «x.project»
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", base).strip("_") or "project"


def run_analysis(project: Project, opts: Options) -> tuple[LoweredProject, Analysis, profiles.Profile]:
    prof = profiles.load(opts.target, opts.overrides)
    lp = lower_project(project)
    an = analyze(lp, prof, opts.rewrite)
    return lp, an, prof


def migrate(project: Project, opts: Options | None = None, equivalence: dict[str, Any] | None = None) -> Migration:
    from .emit import bundle, csharp, report, steps
    from .emit import plcopen as emit_xml
    from .emit.effort import monte_carlo

    opts = opts or Options()
    lp, an, prof = run_analysis(project, opts)
    fixed = transform(an, opts.fix, opts.rewrite)
    name = safe_name(project)
    sha = project.source_sha256
    effort = monte_carlo(an.findings)
    rep = report.build_json(lp, an.findings, effort, prof.id, opts.fix, equivalence)
    period = int(prof.semantics.get("task_period_default_ms", 100))
    files: dict[str, bytes] = {}

    def put(path: str, text: str) -> None:
        files[path] = text.encode("utf-8")

    ns = emit_xml.NS_0200 if opts.plcopen_ns == "0200" else emit_xml.NS_0201
    files[f"import/{name}.plcopen.xml"] = emit_xml.build(project, fixed, sha, ns=ns)
    src = project.source_file.replace("\\", "/").rsplit("/", 1)[-1]
    original: dict[str, str] = {}
    fixed_texts: dict[str, str] = {}
    for x in lp.pous:
        original[f"{x.name}.st"] = x.text
    for g in project.gvls:
        original[f"{g.name}.gvl.st"] = g.decl_text if g.decl_text.endswith("\n") else g.decl_text + "\n"
    for d in project.duts:
        original[f"{d.name}.dut.st"] = d.decl_text if d.decl_text.endswith("\n") else d.decl_text + "\n"
    for _key, obj in sorted(fixed.items()):
        fname = f"{obj.name}.st" if obj.kind == "pou" else f"{obj.name}.{obj.kind}.st"
        fixed_texts[fname] = obj.text
        if obj.kind == "pou":
            put(f"st/{obj.name}.ST", bundle.st_file(obj.text, src, sha))
    for k, v in original.items():
        put(f"original/{k}", v)
    for k, v in fixed_texts.items():
        put(f"fixed/{k}", v)
    put("changes.diff", bundle.unified(original, fixed_texts))
    body = csharp.body(project, opts.node, sha, period)
    put("script/DoAction.body.cs", body)
    put("script/BuildProject.cs", csharp.wrapper(body))
    put("script/expected-tree.json", csharp.tree_preview(project, opts.node, period))
    put("MANUAL_STEPS.md", steps.manual_steps(lp, an, fixed, name, opts.fix))
    put("tasks.md", steps.tasks_md(lp, period))
    rows = steps.mapping(lp, an, fixed)
    put("mapping.json", steps.mapping_json(rows))
    put("mapping.csv", steps.mapping_csv(rows))
    put("io-binding.csv", steps.io_binding_csv(an))
    put("MIGRATION_REPORT.json", report.to_json_text(rep))
    put("MIGRATION_REPORT.md", report.build_md(rep))
    put("MIGRATION_REPORT.html", report.build_html(rep))
    for pid, variant, nsv in (
        ("P-IMP-02-config-globals", "config-globals", emit_xml.NS_0201),
        ("P-IMP-03-tasks", "tasks", emit_xml.NS_0201),
        ("P-IMP-04-ns0200", "default", emit_xml.NS_0200),
        ("P-IMP-06-xhtml-p", "xhtml-p", emit_xml.NS_0201),
        ("P-IMP-07-flat-globals", "flat-globals", emit_xml.NS_0201),
    ):
        files[f"probe/{pid}.xml"] = emit_xml.build(project, fixed, sha, variant=variant, ns=nsv)
    put("probe/README.md", _probe_readme(name))
    return Migration(project, lp, an, fixed, rep, files, name)


def _probe_readme(name: str) -> str:
    return (
        f"# Варианты PLCopen XML для пробы импорта ({name})\n\n"
        f"Основной файл — `import/{name}.plcopen.xml` (P-IMP-01: TC6 2.01, globalVars в resource). Варианты:\n\n"
        "| Проба | Файл | Что меняется |\n|---|---|---|\n"
        "| P-IMP-02 | P-IMP-02-config-globals.xml | globalVars в configuration |\n"
        "| P-IMP-03 | P-IMP-03-tasks.xml | с task и pouInstance |\n"
        "| P-IMP-04 | P-IMP-04-ns0200.xml | namespace tc6_0200 (как у CODESYS) |\n"
        "| P-IMP-06 | P-IMP-06-xhtml-p.xml | тело ST в xhtml:p |\n"
        "| P-IMP-07 | P-IMP-07-flat-globals.xml | глобальные с именами GVL_x без папки |\n\n"
        "Порядок, минуты и запись результата — `probe/README.md` репозитория cds2ms и `probe/RESULTS.csv`.\n"
    )


def inventory(project: Project) -> dict[str, Any]:
    pous = []
    for p in project.pous:
        pous.append({
            "name": p.name, "kind": p.kind, "language": p.lang, "actions": len(p.actions), "methods": len(p.methods),
            "properties": len(p.properties), "transitions": len(p.transitions), "file": p.origin.file, "line": p.origin.line,
        })  # fmt: skip
    return {
        "file": project.source_file.replace("\\", "/").rsplit("/", 1)[-1],
        "kind": project.source_kind,
        "ide": project.ide,
        "ide_version": project.ide_version,
        "sha256": project.source_sha256,
        "placements": project.placements,
        "languages": project.languages(),
        "pous": pous,
        "interfaces": [i.name for i in project.interfaces],
        "gvls": [{"name": g.name, "persistent": g.persistent} for g in project.gvls],
        "duts": [d.name for d in project.duts],
        "tasks": [
            {"name": t.name, "kind": t.kind, "interval_ms": t.interval_ms, "priority": t.priority, "pous": t.pous}
            for t in project.tasks
        ],
        "libraries": [lib.title for lib in project.libraries],
        "issues": [{"rule": i.rule, "message": i.message, "line": i.origin.line} for i in project.issues],
    }


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
