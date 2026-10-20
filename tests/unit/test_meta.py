"""Сквозные требования: пакет только на stdlib (работает в Pyodide), профили с источниками, реестр правил с
корпусом и описанием, сгенерированные файлы не устарели, в репозитории нет абсолютных путей машины."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "src" / "cds2ms"


def test_package_imports_stdlib_only() -> None:
    allowed = set(sys.stdlib_module_names) | {"cds2ms"}
    bad = []
    for py in PKG.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for n in names:
                if n.split(".")[0] not in allowed:
                    bad.append(f"{py.relative_to(ROOT)}: {n}")
    assert not bad, bad


def test_profiles_have_sources() -> None:
    p = tomllib.loads((PKG / "profiles" / "masterscada-4d-1.3.10.toml").read_text(encoding="utf-8"))
    assert p["profile"]["version"] == "1.3.10"
    feats = p["features"]
    assert len(feats) >= 30
    for name, f in feats.items():
        assert f["status"] in ("supported", "unsupported", "unknown"), name
        assert f["confidence"] in ("H", "M", "L"), name
        assert f["source"].startswith("https://"), name
    for key, opts in p["variants"].items():
        assert p["semantics"][key] == "unknown" and len(opts) >= 2, key
    c = tomllib.loads((PKG / "profiles" / "codesys-3.5.17.toml").read_text(encoding="utf-8"))
    assert all(u.startswith("https://content.helpme-codesys.com/") for u in c["sources"].values())


def test_rules_registry_complete() -> None:
    from cds2ms.rules.registry import RULES

    ids = [r.id for r in RULES]
    assert len(ids) == len(set(ids)) >= 50
    rules_md = (ROOT / "docs" / "RULES.md").read_text(encoding="utf-8")
    for r in RULES:
        assert r.sources and all(s.startswith("https://") for s in r.sources), r.id
        assert len(r.description) > 20, r.id
        assert (ROOT / "tests" / "rules" / r.id / "expected.json").exists(), r.id
        assert f"### {r.id}" in rules_md, r.id


def test_generated_up_to_date() -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    import gen_docs

    assert gen_docs.render() == (ROOT / "docs" / "RULES.md").read_text(encoding="utf-8")


def _repo_files() -> list[Path]:
    """Файлы, которые попадут в git (с учётом .gitignore и .git/info/exclude)."""
    import shutil
    import subprocess

    if shutil.which("git") and (ROOT / ".git").exists():
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", check=True).stdout  # fmt: skip
        return [ROOT / x for x in out.splitlines() if x]
    return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


def test_no_machine_paths_in_repo() -> None:
    pat = re.compile(r"[A-Za-z]:\\Users\\|/c/Users/|[\\/]Desktop[\\/]", re.IGNORECASE)
    hits = []
    for p in _repo_files():
        rel = p.relative_to(ROOT)
        if rel.parts[0] in ("web",) or p.suffix.lower() not in (
            ".py",
            ".md",
            ".toml",
            ".json",
            ".csv",
            ".xml",
            ".yml",
            ".cs",
            ".st",
            ".txt",
            ".ps1",
        ):
            continue
        if not p.exists() or p == Path(__file__).resolve():
            continue
        if pat.search(p.read_text(encoding="utf-8", errors="replace")):
            hits.append(rel.as_posix())
    assert not hits, hits
