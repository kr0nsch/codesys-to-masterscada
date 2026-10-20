"""Трансформации Master ST (уровни, идемпотентность), выходы (XML, .ST, отчёт, zip, diff, ручные шаги)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO

import pytest

from cds2ms import api
from cds2ms.cdsfront.importer import layout
from cds2ms.cdsfront.st.parser import parse_body, parse_decl
from cds2ms.emit.bundle import make_zip, unified
from cds2ms.rules.findings import Edit
from cds2ms.transform.master_st import apply_edits, levels_for

LAYOUT = {
    "POUs/PRG_A/PRG_A.decl.st": "PROGRAM PRG_A\nVAR\n    rLevel_ : REAL;\n    b : BOOL;\n    s : STRING(10);\nEND_VAR\n",
    "POUs/PRG_A/PRG_A.impl.st": "rLevel_ := GVL_X.g;\nb S= rLevel_ > 1.0;\nIF b THEN\n    JMP L;\nEND_IF\nb := FALSE;\nL:\n;\n",
    "GVLs/GVL_X.gvl.st": "VAR_GLOBAL\n    g : REAL;\nEND_VAR\n",
}


def run(fix: str, files: dict[str, str] | None = None) -> api.Migration:
    return api.migrate(layout.load_files(files or LAYOUT, name="T"), api.Options(fix=fix))


def test_levels() -> None:
    assert levels_for("none", set()) == (set(), set())
    assert levels_for("safe", set())[0] == {"auto"}
    assert levels_for("review", set())[0] == {"auto", "review"}
    assert levels_for("all", {"MS-NAME-02"}) == ({"auto", "review", "verify"}, {"MS-NAME-02"})


def test_apply_edits_conflict() -> None:
    text, applied, conflicts = apply_edits(
        "abcdef", [Edit(0, 3, "X", "R1", "auto"), Edit(2, 4, "Y", "R2", "auto")], {"auto"}, set()
    )
    assert text == "Xdef" and applied == ["R1"] and conflicts == ["R2@2"]


def test_fix_safe_review() -> None:
    safe = run("safe").fixed["prg_a"]
    assert "rLevel :=" in safe.body and "GVL_X_g" in safe.body  # MS-ST-02, MS-ST-08 — auto
    assert "IF rLevel > 1.0 THEN" in safe.body  # MS-ST-11
    assert "JMP L" in safe.body and "STRING(10)" in safe.decl  # review-правки на safe не применяются
    rev = run("review").fixed["prg_a"]
    assert "JMP" not in rev.body and "IF NOT b THEN" in rev.body and "s : STRING;" in rev.decl
    assert "сверить правки review" in rev.body
    none = run("none")
    assert none.fixed["prg_a"].body == none.lowered.pou("PRG_A").body
    assert none.files["changes.diff"] == b""  # --fix none: правок нет, только отчёт и находки
    assert run("safe").files["changes.diff"].startswith(b"--- a/PRG_A.st")
    assert not parse_body(rev.body, "masterst").diagnostics


def test_idempotent_second_pass() -> None:
    first = run("review")
    files2 = {
        "POUs/PRG_A/PRG_A.decl.st": first.fixed["prg_a"].decl.replace("VAR_INOUT", "VAR_IN_OUT"),
        "POUs/PRG_A/PRG_A.impl.st": first.fixed["prg_a"].body,
        "GVLs/GVL_X.gvl.st": LAYOUT["GVLs/GVL_X.gvl.st"],
    }
    second = run("review", files2)
    autos = [f for f in second.findings if f.outcome == "auto" and f.pou == "PRG_A"]
    assert not autos, [(f.rule, f.message) for f in autos]
    assert second.fixed["prg_a"].body == first.fixed["prg_a"].body  # fix(fix(x)) == fix(x)


def test_xml_structure_and_xsd(udr1_migration, xsd_path) -> None:  # type: ignore[no-untyped-def]
    raw = udr1_migration.files["import/UDR1.plcopen.xml"]
    text = raw.decode("utf-8")
    assert "addData" not in text and '<xhtml xmlns="http://www.w3.org/1999/xhtml">' in text
    assert 'configuration name="migConfig"' in text and 'resource name="migResource"' in text
    assert "<task " not in text and "pouInstance" not in text
    for tag in ("<SFC>", "<FBD>", "<LD>", "<IL>", "<CFC", "<actions>", "<transitions>"):
        assert tag not in text, tag  # всё понижено в ST, методы и действия встроены
    if xsd_path is None:
        pytest.skip("XSD TC6 2.01 не загружена (нет сети): python tools/fetch_xsd.py")
    from lxml import etree

    schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    for name, data in udr1_migration.files.items():
        if name.endswith(".xml"):
            doc = etree.fromstring(data.replace(b"tc6_0200", b"tc6_0201"))
            assert schema.validate(doc), (name, [str(e) for e in schema.error_log][:3])


def test_st_files_and_template(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    st = udr1_migration.files["st/FB_DoseCtrl.ST"].decode("utf-8")
    assert st.startswith("(* создано cds2ms 0.1.0") and "черновой [L]" in st and "сгенерир" not in st
    body = st.split("*)", 1)[1]
    pd = parse_decl(body, "masterst")
    assert pd.decl.header is not None and pd.decl.header.name == "FB_DoseCtrl"


def test_report_core_schema(udr1_migration, root) -> None:  # type: ignore[no-untyped-def]
    import jsonschema

    schema = json.loads((root / "src" / "cds2ms" / "schemas" / "report-core.schema.json").read_text(encoding="utf-8"))
    rep = json.loads(udr1_migration.files["MIGRATION_REPORT.json"])
    jsonschema.validate(rep, schema)
    assert rep["effort"]["model"] == "triangular-mc" and rep["effort"]["seed"] == 20261019
    assert rep["effort"]["p50_h"] <= rep["effort"]["p90_h"]
    keys = [
        (f["origin"]["file"], f["origin"].get("line", 0), f["origin"].get("column", 0), f["rule"])
        for f in rep["findings"]
    ]
    assert keys == sorted(keys)


def test_effort_deterministic(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    from cds2ms.emit.effort import monte_carlo

    a = monte_carlo(udr1_migration.findings, runs=2000)
    b = monte_carlo(udr1_migration.findings, runs=2000)
    assert a == b


def test_zip_deterministic(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    z1 = make_zip(udr1_migration.files)
    z2 = make_zip(dict(reversed(list(udr1_migration.files.items()))))
    assert hashlib.sha256(z1).digest() == hashlib.sha256(z2).digest()
    with zipfile.ZipFile(BytesIO(z1)) as z:
        infos = z.infolist()
        assert all(i.compress_type == zipfile.ZIP_STORED and i.date_time == (1980, 1, 1, 0, 0, 0) for i in infos)
        assert [i.filename for i in infos] == sorted(i.filename for i in infos)


def test_outputs_complete(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    names = set(udr1_migration.files)
    for must in ("MANUAL_STEPS.md", "tasks.md", "mapping.json", "mapping.csv", "io-binding.csv", "MIGRATION_REPORT.json",
                 "MIGRATION_REPORT.md", "MIGRATION_REPORT.html", "changes.diff", "script/BuildProject.cs",
                 "script/DoAction.body.cs", "script/expected-tree.json", "probe/README.md"):  # fmt: skip
        assert must in names, must
    assert any(n.startswith("original/") for n in names) and any(n.startswith("fixed/") for n in names)
    io_csv = udr1_migration.files["io-binding.csv"].decode("utf-8")
    assert "GVL_IO_xPumpOut" in io_csv and "%QX0.0" in io_csv
    steps = udr1_migration.files["MANUAL_STEPS.md"].decode("utf-8")
    assert "Импортирование PLCOpenXML" in steps and "мин" in steps and "Проверить" in steps
    for name, data in udr1_migration.files.items():
        if name.endswith((".md", ".st", ".ST", ".cs", ".json", ".csv", ".xml", ".html")):
            t = data.decode("utf-8")
            assert "\r" not in t and "сгенерир" not in t.lower(), name


def test_csharp_no_internal_model(udr1_migration) -> None:  # type: ignore[no-untyped-def]
    cs = udr1_migration.files["script/DoAction.body.cs"].decode("utf-8")
    assert "ItemInstance" not in cs and "?." not in cs and '$"' not in cs and "string?" not in cs
    assert "ResetPriority()" in cs and "FindController(" in cs and "FBExecuteTypes.OnCall" in cs


def test_unified_diff() -> None:
    d = unified({"a.st": "x := 1;\n"}, {"a.st": "x := 2;\n"})
    assert d.startswith("--- a/a.st\n+++ b/a.st\n") and "-x := 1;" in d and "+x := 2;" in d


def test_formal_parameter_not_renamed_as_global() -> None:
    """Имя формального параметра, совпадающее с глобальной без квалификатора, не переименовывается (MS-ST-08);
    регрессия, найденная RuSTy на цепочке S7 (modeRequest := DB_Hmi.modeRequest)."""
    files = {
        "GVLs/G.gvl.st": "VAR_GLOBAL\n    req : INT;\nEND_VAR\n",
        "POUs/FB_M/FB_M.decl.st": "FUNCTION_BLOCK FB_M\nVAR_INPUT\n    req : INT;\nEND_VAR\n",
        "POUs/FB_M/FB_M.impl.st": ";\n",
        "POUs/PRG_A/PRG_A.decl.st": "PROGRAM PRG_A\nVAR\n    fb : FB_M;\nEND_VAR\n",
        "POUs/PRG_A/PRG_A.impl.st": "fb(req := req);\nreq := 0;\n",
    }
    body = run("safe", files).fixed["prg_a"].body
    assert "fb(req := G_req);" in body and "G_req := 0;" in body
