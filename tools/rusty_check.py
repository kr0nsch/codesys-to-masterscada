"""RuSTy v1.0.6 ``plc --check`` над Master ST (``fixed/``) кейсов: 0 неожиданных и 0 пропавших диагностик.

Адаптер masterst → IEC: ``VAR_INOUT`` → ``VAR_IN_OUT`` (единственное отличие диалекта в выходе ``fixed/``; имена
библиотек MasterSCADA в выход не попадают). Ожидаемые диагностики — ``tests/golden/<кейс>/rusty-expected.json``:
у каждой код RuSTy, файл, строка и причина (известный пробел RuSTy 1.0.6 или находка cds2ms).

    python tools/rusty_check.py [--update] [--case udr1|cds|chain|processlib]

Компилятор: ``RUSTY_PLC``, ``PATH`` (plc), ``~/.local/plc-tools/rusty/plc[.exe]``; объявления stdlib —
``RUSTY_STDLIB_INCLUDE`` или каталог ``include`` рядом с компилятором. Нет инструмента — код 0 с сообщением,
при ``REQUIRE_RUSTY=1`` — код 1. Коды: 0 — совпало, 1 — расхождение или нет инструмента при REQUIRE_RUSTY.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cds2ms import api  # noqa: E402

CASES = {
    "udr1": ROOT / "corpus" / "udr1" / "source.handmade.xml",
    "cds": ROOT / "corpus" / "udr1" / "source.cds.xml",
    "chain": ROOT / "corpus" / "s7-chain",
}
_DIAG = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<col>\d+):\{[^}]*\}: (?P<sev>error|warning)\[(?P<code>E\d+)\]: (?P<msg>.*)$"
)
# Известные пробелы RuSTy 1.0.6 на корректном для CODESYS/MasterSCADA коде (не находки cds2ms)
KNOWN = {
    "E014": "RuSTy 1.0.6: STRING(n) и некоторые объявления строк",
}
KNOWN_MESSAGES = {
    "Could not resolve reference to TIME_TO_REAL": "в stdlib RuSTy 1.0.6 нет TIME_TO_REAL (в CODESYS есть)",
    "Could not resolve reference to TIME_TO_DINT": "в stdlib RuSTy 1.0.6 нет TIME_TO_DINT (в CODESYS есть)",
    "Could not resolve reference to RESET": "CTU в stdlib RuSTy — вход R по IEC 61131-3, в CODESYS Standard — RESET (MS-LIB-01: сверить в MasterSCADA)",
    "Invalid call parameters": "следствие предыдущей: вызов CTU с RESET",
}


def find_plc() -> str | None:
    env = os.environ.get("RUSTY_PLC")
    if env and Path(env).exists():
        return env
    which = shutil.which("plc")
    if which:
        return which
    for name in ("plc.exe", "plc"):
        p = Path.home() / ".local" / "plc-tools" / "rusty" / name
        if p.exists():
            return str(p)
    return None


def find_include(plc: str) -> str | None:
    env = os.environ.get("RUSTY_STDLIB_INCLUDE")
    if env and Path(env).is_dir():
        return env
    for p in sorted(Path(plc).resolve().parent.rglob("include")):
        if p.is_dir() and any(p.glob("*.st")):
            return str(p)
    return None


def adapt(text: str, gvl: str | None = None) -> str:
    """masterst → IEC для RuSTy. UNION → STRUCT: RuSTy 1.0.6 не разбирает UNION (критическая ошибка разбора
    останавливает проверку всего набора), для проверки типов раскладка не важна. Глобальные: в MasterSCADA это
    параметры узла с именем «Папка_Имя» (MS-ST-08), тела ``fixed/`` обращаются к ним так — объявления GVL получают
    тот же префикс."""
    text = re.sub(r"\bVAR_INOUT\b", "VAR_IN_OUT", text)
    text = re.sub(r"\bEND_UNION\b", "END_STRUCT", text)
    text = re.sub(r"(:\s*)UNION\b", r"\1STRUCT", text)
    if gvl:
        text = re.sub(r"(?m)^(\s+)([A-Za-z_]\w*)(\s*(?::(?!=)|AT\b))", lambda m: f"{m[1]}{gvl}_{m[2]}{m[3]}", text)
    return text


def case_files(case: str) -> dict[str, str]:
    path = CASES.get(case)
    if case == "processlib":
        sys.path.insert(0, str(ROOT / "tools"))
        import fetch_processlib

        path = fetch_processlib.fetch()
    assert path is not None
    mig = api.migrate(api.load_path(path), api.Options(fix="review"))
    out = {}
    for k, v in mig.files.items():
        if k.startswith("fixed/"):
            name = k.removeprefix("fixed/")
            gvl = name.removesuffix(".gvl.st") if name.endswith(".gvl.st") else None
            out[name] = adapt(v.decode("utf-8"), gvl)
    return out


def run_check(plc: str, include: str, files: dict[str, str]) -> list[dict[str, object]]:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        paths = []
        for name, text in sorted(files.items()):
            p = d / name
            p.write_text(text, encoding="utf-8", newline="\n")
            paths.append(str(p))
        cmd = [plc, "--check", *paths, "-i", str(Path(include) / "*.st"), "--error-format", "clang"]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        out: list[dict[str, object]] = []
        for line in (proc.stdout + proc.stderr).splitlines():
            m = _DIAG.match(line.strip())
            if not m or m["sev"] != "error":
                continue
            fname = Path(m["path"]).name
            if fname not in files:
                continue  # stdlib
            out.append({"code": m["code"], "file": fname, "line": int(m["line"]), "message": m["msg"].strip()})
        out.sort(key=lambda x: (str(x["file"]), int(x["line"]), str(x["code"])))  # type: ignore[call-overload]
        return out


def key(d: dict[str, object]) -> tuple[str, str, int]:
    return (str(d["code"]), str(d["file"]), int(d["line"]))  # type: ignore[call-overload]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="переписать rusty-expected.json (причины сохраняются)")
    ap.add_argument("--case", action="append", choices=[*CASES, "processlib"])
    a = ap.parse_args(argv)
    plc = find_plc()
    include = find_include(plc) if plc else None
    if not plc or not include:
        msg = "RuSTy не найден (RUSTY_PLC, RUSTY_STDLIB_INCLUDE)"
        print(msg)
        return 1 if os.environ.get("REQUIRE_RUSTY") == "1" else 0
    bad = 0
    for case in a.case or list(CASES):
        got = run_check(plc, include, case_files(case))
        gpath = ROOT / "tests" / "golden" / case / "rusty-expected.json"
        old = json.loads(gpath.read_text(encoding="utf-8")) if gpath.exists() else {"diagnostics": []}
        reasons = {key(d): d.get("reason", "") for d in old["diagnostics"]}
        if a.update:
            for d in got:
                d["reason"] = (
                    reasons.get(key(d)) or KNOWN_MESSAGES.get(str(d["message"]), "") or KNOWN.get(str(d["code"]), "")
                )
            gpath.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "rusty": "1.0.6",
                "adapter": "VAR_INOUT -> VAR_IN_OUT; UNION -> STRUCT",
                "case": case,
                "diagnostics": got,
            }
            gpath.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
            print(f"{case}: записано {len(got)} ожидаемых диагностик")
            continue
        exp = {key(d) for d in old["diagnostics"]}
        now = {key(d) for d in got}
        unexpected = sorted(now - exp)
        missing = sorted(exp - now)
        print(
            f"{case}: диагностик {len(now)}, ожидаемых {len(exp)}, неожиданных {len(unexpected)}, пропавших {len(missing)}"
        )
        for k in unexpected:
            print("  неожиданная", k, next(d["message"] for d in got if key(d) == k))
        for k in missing:
            print("  пропавшая", k)
        bad += len(unexpected) + len(missing)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
