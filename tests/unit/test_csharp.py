"""C#-скрипт построения проекта: снимок API, сгенерированный макет, сборка C# 5 / dotnet, дерево против mapping.

Сборка против настоящей ``MasterSCADA.Scripts.Model.dll`` 1.3.10 — маркер ms4d (только машина с установленной
MasterSCADA 4D); сборка csc — Windows с .NET Framework; dotnet — где есть SDK (job csharp в CI).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import csc_check  # noqa: E402
import gen_stub  # noqa: E402


def test_snapshot_and_stub_members_have_sources() -> None:
    rows = (ROOT / "csharp" / "api-snapshot.tsv").read_text(encoding="utf-8").splitlines()
    head, body = rows[0].split("\t"), rows[1:]
    assert head[:3] == ["page", "kind", "member"] and len(body) >= 200
    assert all(r.split("\t")[0] for r in body)  # у каждого члена — страница справки
    lines = (ROOT / "csharp" / "Stub" / "Api.g.cs").read_text(encoding="utf-8").splitlines()
    assert not any("ItemInstance" in ln or "?." in ln for ln in lines)
    for i, ln in enumerate(lines):
        if ln.strip().startswith(("public class", "public partial class", "public enum")):
            prev = next(x for x in reversed(lines[:i]) if x.strip())
            assert prev.strip().startswith(("// https://help.iek-digital.ru/", "// [L]")), ln


def test_stub_up_to_date() -> None:
    assert gen_stub.main(["--check"]) == 0


def test_script_matches_tasks(cds_migration) -> None:  # type: ignore[no-untyped-def]
    """expected-tree.json (что построит скрипт) = задачи и программы проекта (mapping, tasks.md)."""
    tree = json.loads(cds_migration.files["script/expected-tree.json"])
    want = {t.name: list(t.pous) for t in cds_migration.project.tasks}
    got = {d["name"].removeprefix("migTask_"): d["calls"] for d in tree["dispatchers"]}
    assert got == want
    assert [t["name"] for t in tree["tasks"]] == list(want)
    rows = json.loads(cds_migration.files["mapping.json"])["rows"]
    assert {r["codesys"].split()[-1] for r in rows if r["codesys"].startswith("program ")} >= {
        p for v in want.values() for p in v
    }


def _migrate(tmp_path: Path) -> Path:
    from cds2ms.cli import main

    out = tmp_path / "out"
    assert (
        main(["migrate", str(ROOT / "corpus" / "udr1" / "source.cds.xml"), "--out", str(out), "--fail-on", "never"])
        == 0
    )
    return out


@pytest.mark.skipif(not csc_check.CSC.exists(), reason="нет csc .NET Framework 4 (Windows)")
def test_csc_build_and_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert csc_check.main([str(_migrate(tmp_path))]) == 0, capsys.readouterr().out


@pytest.mark.skipif(shutil.which("dotnet") is None, reason="нет dotnet SDK")
@pytest.mark.slow
def test_dotnet_build_and_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert csc_check.main([str(_migrate(tmp_path)), "--dotnet"]) == 0, capsys.readouterr().out


@pytest.mark.ms4d
@pytest.mark.skipif(not (csc_check.MS4D_BIN / "MasterSCADA.Scripts.Model.dll").exists() or not csc_check.CSC.exists(),
                    reason="нет установки MasterSCADA 4D 1.3.10 или csc")  # fmt: skip
def test_real_model_compile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Тело DoAction() собирается против настоящей MasterSCADA.Scripts.Model.dll 1.3.10 (запуск — только в среде)."""
    assert csc_check.main([str(_migrate(tmp_path)), "--real"]) == 0, capsys.readouterr().out


def test_ms4d_env_documented() -> None:
    assert "MS4D_BIN" in (ROOT / "tools" / "csc_check.py").read_text(encoding="utf-8")
    assert os.environ.get("MS4D_BIN", "") == "" or Path(os.environ["MS4D_BIN"]).name == "bin"


@pytest.mark.ms4d
def test_shipped_doc_covers_snapshot(capsys: pytest.CaptureFixture[str]) -> None:
    """Члены снимка справки есть в XML-документации поставки 1.3.10 (bin/MasterSCADA.Scripts.Model.xml)."""
    import ms4d_check

    code = ms4d_check.main([])
    if code == 3:
        pytest.skip("MasterSCADA 4D 1.3.10 не установлена")
    out = capsys.readouterr().out
    assert code == 0 and "нет: 0" in out, out
