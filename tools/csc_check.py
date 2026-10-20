"""Проверка C#-скрипта: сборка против макета API (csc C# 5 или dotnet), прогон FakeRunner, сверка tree.json;
локально — сборка тела DoAction() против настоящей MasterSCADA.Scripts.Model.dll из установки MasterSCADA 4D.

    python tools/csc_check.py <out-каталог migrate> [--node PLC210] [--dotnet] [--real [--ms4d-bin DIR]]

Код 0 — собрано и дерево совпало с script/expected-tree.json; 1 — расхождение или ошибка сборки; 3 — нет
компилятора (пропуск). ``--real`` компилирует тело против сборки внешней объектной модели 1.3.10 — только сборка,
скрипт не запускается (объект RootItemModel создаёт среда разработки).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
MS4D_BIN = Path(os.environ.get("MS4D_BIN", r"C:\Program Files\MPSSoft\MasterSCADA 4D 1.3\bin"))
BUILD = ROOT / "build" / "csharp"


def stub_sources() -> list[Path]:
    return [*sorted((ROOT / "csharp" / "Stub").glob("*.cs")), ROOT / "csharp" / "FakeRunner" / "Program.cs"]


def build_csc(build_project: Path, exe: Path) -> tuple[bool, str]:
    srcs = [str(p) for p in stub_sources()] + [str(build_project)]
    cmd = [str(CSC), "/nologo", "/langversion:5", "/target:exe", f"/out:{exe}", "/warn:4", *srcs]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="cp866", errors="replace")
    return p.returncode == 0, p.stdout + p.stderr


CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <LangVersion>5</LangVersion>
    <Nullable>disable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <AssemblyName>FakeRunner</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
{items}
  </ItemGroup>
</Project>
"""


def build_dotnet(build_project: Path, outdir: Path) -> tuple[bool, str, Path]:
    proj = outdir / "stub.csproj"
    items = "\n".join(f'    <Compile Include="{p}" />' for p in [*stub_sources(), build_project])
    proj.write_text(CSPROJ.format(items=items), encoding="utf-8")
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_CLI_UI_LANGUAGE="en")
    p = subprocess.run(["dotnet", "build", str(proj), "-c", "Release", "-o", str(outdir / "bin"), "-nologo"],
                       capture_output=True, text=True, errors="replace", env=env)  # fmt: skip
    dll = outdir / "bin" / "FakeRunner.dll"
    return p.returncode == 0, p.stdout + p.stderr, dll


def compare(tree: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    system = next((c for c in tree.get("children", []) if c["type"] == "SystemItem"), None)
    objects = next((c for c in tree.get("children", []) if c["type"] == "ObjectsItem"), None)
    if system is None or objects is None:
        return ["в дереве нет System/Objects"]
    node = next((c for c in system.get("children", []) if c["name"] == expected["node"]), None)
    if node is None:
        return [f"нет узла {expected['node']}"]
    tasks = {c["name"]: c for c in node.get("children", []) if c["type"] == "TaskItem"}
    for t in expected["tasks"]:
        got = tasks.get(t["name"])
        if got is None:
            errs.append(f"нет задачи {t['name']}")
        elif got.get("props", {}).get("Period") != t["Period"]:
            errs.append(f"задача {t['name']}: Period {got.get('props', {}).get('Period')} != {t['Period']}")
    objs = {c["name"]: c for c in objects.get("children", [])}
    for d in expected["dispatchers"]:
        o = objs.get(d["name"])
        if o is None:
            errs.append(f"нет объекта {d['name']}")
            continue
        if o.get("props", {}).get("TaskRef") != "@" + d["TaskRef"]:
            errs.append(f"{d['name']}: TaskRef {o.get('props', {}).get('TaskRef')} != @{d['TaskRef']}")
        prg = next((c for c in o.get("children", []) if c["type"] == "ProgramSTItem"), None)
        text = prg.get("props", {}).get("Text", "") if prg else ""
        calls = re.findall(r"\.(\w+)\(\);", text)
        if calls != d["calls"]:
            errs.append(f"{d['name']}: вызовы {calls} != {d['calls']}")
    return errs


HARNESS = """// Проверка тела DoAction() против настоящей сборки MasterSCADA.Scripts.Model.dll (только компиляция).
using System;
using System.Linq;
using MasterSCADA.Scripts.Model;
{usings}
public class RealScriptHarness
{{
    public RootItem RootItemModel {{ get {{ return null; }} }}
    public void WriteConsole(string text) {{ }}
    public void DoAction()
    {{
{body}
    }}
}}
"""

REAL_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Library</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <LangVersion>5</LangVersion>
    <Nullable>disable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <UseWPF>true</UseWPF>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="Harness.g.cs" />
{refs}
  </ItemGroup>
</Project>
"""
# Пространства имён перечислений модели (TranslatorType, FBExecuteTypes …) лежат вне MasterSCADA.Scripts.Model;
# редактор скриптов добавляет using сам (HW:script_c). Пространство MasterSCADA.Scheme.Types взято из сообщения
# компилятора CS0266 при сборке против MasterSCADA.Scripts.Model.dll 1.3.10 (тип свойства ExecutionMethod).
REAL_USINGS = os.environ.get("MS4D_USINGS", "MasterSCADA.Scheme.Types").split(";")


def build_real(body: Path, outdir: Path, bin_dir: Path) -> tuple[bool, str]:
    outdir.mkdir(parents=True, exist_ok=True)
    model = bin_dir / "MasterSCADA.Scripts.Model.dll"
    if not model.exists():
        return False, f"нет {model}"
    text = body.read_text(encoding="utf-8")
    ind = "".join("        " + ln if ln.strip() else ln for ln in text.splitlines(keepends=True))
    usings = "\n".join(f"using {u};" for u in REAL_USINGS if u.strip())
    (outdir / "Harness.g.cs").write_text(HARNESS.format(body=ind, usings=usings), encoding="utf-8")
    dlls = [
        "MasterSCADA.Scripts.Model.dll",
        *sorted(
            p.name
            for p in bin_dir.glob("*.dll")
            if p.name.startswith(("InSAT.", "MasterSCADA.")) and p.name != model.name
        ),
    ]
    refs = "\n".join(f'    <Reference Include="{Path(d).stem}"><HintPath>{bin_dir / d}</HintPath><Private>false</Private></Reference>'
                     for d in dlls)  # fmt: skip
    (outdir / "real.csproj").write_text(REAL_CSPROJ.format(refs=refs), encoding="utf-8")
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_CLI_UI_LANGUAGE="en")
    p = subprocess.run(["dotnet", "build", str(outdir / "real.csproj"), "-nologo", "-v", "q"], capture_output=True, text=True,
                       errors="replace", env=env)  # fmt: skip
    out = p.stdout + p.stderr
    errs = [ln for ln in out.splitlines() if ": error " in ln]
    return p.returncode == 0, "\n".join(errs[:40]) if errs else out[-2000:]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", help="каталог migrate (script/BuildProject.cs, script/expected-tree.json)")
    ap.add_argument("--node", default="PLC210")
    ap.add_argument("--dotnet", action="store_true")
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--ms4d-bin", default=str(MS4D_BIN))
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    bp = out / "script" / "BuildProject.cs"
    expected = json.loads((out / "script" / "expected-tree.json").read_text(encoding="utf-8"))
    if BUILD.exists():
        shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    tree_path = BUILD / "tree.json"
    if a.dotnet:
        if shutil.which("dotnet") is None:
            print("нет dotnet — пропуск")
            return 3
        ok, log, dll = build_dotnet(bp, BUILD)
        if not ok:
            print(log[-3000:])
            return 1
        run = subprocess.run(["dotnet", str(dll), a.node, str(tree_path)], capture_output=True, text=True, encoding="utf-8",
                             errors="replace")  # fmt: skip
    else:
        if not CSC.exists():
            print("нет csc.exe — пропуск")
            return 3
        exe = BUILD / "fake.exe"
        ok, log = build_csc(bp, exe)
        if not ok:
            print(log)
            return 1
        run = subprocess.run(
            [str(exe), a.node, str(tree_path)], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    if run.returncode != 0:
        print(run.stdout + run.stderr)
        return 1
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    errs = compare(tree, expected)
    (out / "script" / "tree.json").write_text(tree_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    print(f"макет: собрано ({'dotnet' if a.dotnet else 'csc C# 5'}), дерево {'совпало' if not errs else 'НЕ совпало'} "
          f"с expected-tree.json; консоль: {run.stdout.strip()}")  # fmt: skip
    for e in errs:
        print("  " + e)
    code = 1 if errs else 0
    if a.real:
        ok, log = build_real(out / "script" / "DoAction.body.cs", BUILD / "real", Path(a.ms4d_bin))
        print(f"MasterSCADA.Scripts.Model.dll: {'собрано без ошибок' if ok else 'ОШИБКИ сборки'}")
        if not ok:
            print(log)
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
