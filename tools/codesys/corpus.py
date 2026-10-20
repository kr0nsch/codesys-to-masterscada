"""Корпус УДР-1 в CODESYS 3.5.17.30: импорт, сборка, экспорт и трассы стендов в Control Win (этапы 0 и C).

    python tools/codesys/corpus.py [--no-run] [--keep]

1. ``tools/corpus/build_corpus.py`` → ``build/corpus/import.xml`` (графика и IL);
2. стенды ``PRG_Stand_<POU>`` по ``corpus/<язык>/<случай>/scenario.csv`` в режиме R2 (период 10 мс): входы по циклам
   из массивов, выходы и ``TIME()`` начала цикла — в массивы;
3. задание → ``CODESYS.exe --profile="…" --noUI --runscript=tools/codesys/cds_corpus_ide.py`` (одна строка,
   кавычки после «=» буквально, VERIFIED_codesys_env.md);
4. результат: ``corpus/udr1/source.cds.xml`` (экспорт приложения), ``corpus/<…>/oracle-codesys.csv`` и ``.json``,
   ``build/corpus/stage0.json`` (сборка, импорт по языкам).

Рантайм общий: вход в Control Win — только под блокировкой ``%LOCALAPPDATA%\\plc-tools\\codesys-runtime.lock``
(``lock.py``). Чужой рантайм не останавливается; если рантайм не запущен, скрипт запускает свой и останавливает
его в конце. Блокировку не дали за время ожидания — трассы пропускаются («runtime busy»).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "codesys"))
sys.path.insert(0, str(ROOT / "tools" / "corpus"))
sys.path.insert(0, str(ROOT / "corpus" / "udr1"))
sys.path.insert(0, str(ROOT / "src"))
import build_corpus  # noqa: E402
import sources as S  # noqa: E402
from lock import CdsError, runtime_lock  # noqa: E402

from cds2ms.sim.runner import parse_value, read_csv, scenarios  # noqa: E402

CODESYS_EXE = os.environ.get("CODESYS_EXE", r"C:\Program Files (x86)\CODESYS 3.5.17.30\CODESYS\Common\CODESYS.exe")
PROFILE = os.environ.get("CODESYS_PROFILE", "CODESYS V3.5 SP17 Patch 3")
RUNTIME_DIR = Path.home() / ".local" / "plc-tools" / "cds-runtime"
RUNTIME_EXE = Path(r"C:\Program Files (x86)\CODESYS 3.5.17.30\GatewayPLC\CODESYSControlService.exe")
STAND_MS = 10
DUT_KIND = {"E_DoseState": "enum", "ST_Recipe": "struct", "U_RawWord": "union", "T_Percent": "alias"}


def st_value(typ: str, v: Any) -> str:
    t = typ.upper()
    if t == "BOOL":
        return "TRUE" if v else "FALSE"
    if t == "TIME":
        return f"T#{int(v)}MS"
    if t in ("REAL", "LREAL"):
        s = repr(float(v))
        return s if ("." in s or "e" in s) else s + ".0"
    return str(int(v))


def compress(vals: list[str]) -> str:
    out: list[str] = []
    i = 0
    while i < len(vals):
        j = i
        while j < len(vals) and vals[j] == vals[i]:
            j += 1
        n = j - i
        out.append(f"{n}({vals[i]})" if n > 1 else vals[i])
        i = j
    return "[" + ", ".join(out) + "]"


def stand(case_dir: str, pou: str) -> dict[str, Any]:
    """Стенд R2: сценарии подряд, у ФБ — свой экземпляр на сценарий, у программы — один сценарий."""
    rows = read_csv((ROOT / "corpus" / case_dir / "scenario.csv").read_text(encoding="utf-8"))
    scs = scenarios(rows)
    is_prg = pou.startswith("PRG_")
    if is_prg and len(scs) > 1:
        raise SystemExit(f"{case_dir}: у программы допустим один сценарий")
    name = f"PRG_Stand_{pou}"
    decl = [
        f"PROGRAM {name}",
        "VAR",
        "    iScen : INT;",
        "    iCycle : INT;",
        "    tStart : TIME;",
        "    xDone : BOOL;",
    ]
    body = ["CASE iScen OF"]
    arrays: list[dict[str, Any]] = []
    meta = []
    for si, sc in enumerate(scs):
        ks = [math.ceil(r.t_ms / STAND_MS) for r in sc]
        k_max = max(ks) + 1
        inst = pou if is_prg else f"inst{si}"
        if not is_prg:
            decl.append(f"    {inst} : {pou};")
        ins = list(sc[0].inputs.items())
        outs = list(sc[0].outputs.items())
        per_cycle: dict[str, list[str]] = {p: [] for p, _ in ins}
        cur = dict(ins)
        ri = 0
        for k in range(k_max):
            while ri < len(sc) and ks[ri] <= k:
                for p, tv in sc[ri].inputs.items():
                    cur[p] = tv
                ri += 1
            for p, (typ, val) in cur.items():
                per_cycle[p].append(st_value(typ, parse_value(typ, val)))
        decl.append(f"    aT{si} : ARRAY[0..{k_max - 1}] OF TIME;")
        arrays.append({"name": f"aT{si}", "n": k_max})
        for p, (typ, _v) in ins:
            an = f"aIn{si}_{p.replace('.', '_')}"
            decl.append(f"    {an} : ARRAY[0..{k_max - 1}] OF {typ} := {compress(per_cycle[p])};")
        for p, (typ, _v) in outs:
            an = f"aOut{si}_{p.replace('.', '_')}"
            decl.append(f"    {an} : ARRAY[0..{k_max - 1}] OF {typ};")
            arrays.append({"name": an, "n": k_max})
        lines = ["    IF iCycle = 0 THEN", "        tStart := TIME();", "    END_IF"]
        lines.append(f"    aT{si}[iCycle] := TIME() - tStart;")
        for p, _tv in ins:
            lines.append(f"    {inst}.{p} := aIn{si}_{p.replace('.', '_')}[iCycle];")
        lines.append(f"    {inst}();")
        for p, _tv in outs:
            lines.append(f"    aOut{si}_{p.replace('.', '_')}[iCycle] := {inst}.{p};")
        lines += ["    iCycle := iCycle + 1;", f"    IF iCycle >= {k_max} THEN", f"        iScen := {si + 1};",
                  "        iCycle := 0;", "    END_IF"]  # fmt: skip
        body.append(f"{si}:")
        body += lines
        meta.append(
            {"scenario": sc[0].scenario, "cycles": k_max, "inputs": ins, "outputs": outs, "per_cycle": per_cycle}
        )
    body += ["ELSE", "    xDone := TRUE;", "END_CASE", ""]
    decl += ["END_VAR", ""]
    return {"name": name, "decl": "\n".join(decl), "body": "\n".join(body), "arrays": arrays, "meta": meta,
            "case": case_dir, "pou": pou}  # fmt: skip


def per_pou_xml(build: Path) -> list[list[str]]:
    """Графика и IL — по файлу на POU: ошибка импорта одного не скрывает остальные (проба по языкам)."""
    from tc6 import project

    out = []
    import re as _re

    for frag in S.graphics() + S.il_pous():
        name = _re.search(r'<pou name="([^"]+)"', frag)
        assert name is not None
        f = build / f"import_{name.group(1)}.xml"
        f.write_text(project(name.group(1), [frag]), encoding="utf-8", newline=chr(10))
        out.append([name.group(1), str(f)])
    return out


def plc_value(raw: str, typ: str) -> Any:
    s = raw.strip()
    if "#" in s and not s.startswith("'"):
        head, _, tail = s.partition("#")
        if head.upper() in ("T", "TIME"):
            from cds2ms.sim.interp import parse_duration_ms

            return int(round(parse_duration_ms(tail)))
        s = tail
    return parse_value(typ, s)


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def start_own_runtime() -> int | None:
    """Запуск своего рантайма (как cds.py runtime start соседей); возвращает pid или None."""
    boot = RUNTIME_DIR / "boot.cfg"
    if not boot.exists() or not RUNTIME_EXE.exists():
        return None
    cmd = (f"Start-Process -FilePath '{RUNTIME_EXE}' -ArgumentList '-d','\"{boot}\"' -WorkingDirectory '{RUNTIME_DIR / 'work'}' "
           "-WindowStyle Hidden -PassThru | Select-Object -ExpandProperty Id")  # fmt: skip
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60)
    try:
        pid = int(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    for _ in range(40):
        if port_open(11740):
            return pid
        time.sleep(0.5)
    return pid


def stop_runtime(pid: int) -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"], capture_output=True, timeout=60
    )


def other_codesys() -> list[str]:
    """Процессы CODESYS.exe соседних сеансов: IDE — общий ресурс, второй экземпляр не запускаем."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='CODESYS.exe'\" | ForEach-Object { $_.ProcessId }"],
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    return [x.strip() for x in out.stdout.splitlines() if x.strip()]


def wait_ide(max_wait_s: float = 1800) -> None:
    t0 = time.time()
    while other_codesys():
        if time.time() - t0 > max_wait_s:
            raise SystemExit("CODESYS занят соседним сеансом дольше 30 мин — повторите позже")
        time.sleep(10)


def visible_dialog(pid: int) -> str:
    """Текст видимых окон своего процесса CODESYS (в --noUI окон нет, кроме модальных диалогов)."""
    ps1 = ROOT / "tools" / "codesys" / "dialogs.ps1"
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), "-ProcessId", str(pid)],
                         capture_output=True, timeout=60)  # fmt: skip
    text = out.stdout.decode("utf-8", "replace").strip()
    return text if text.startswith("WIN:") else ""


def run_codesys(job: dict[str, Any], build: Path) -> dict[str, Any]:
    wait_ide()
    for stale in list(build.glob("udr1.project*")) + list(build.glob("*.opt")):
        stale.unlink()  # зависший .~u от убитого CODESYS даёт модальный диалог в --noUI
    res_old = Path(job["result"])
    if res_old.exists():
        res_old.unlink()
    jp = build / "job.json"
    jp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    script = ROOT / "tools" / "codesys" / "cds_corpus_ide.py"
    cmdline = f'"{CODESYS_EXE}" --profile="{PROFILE}" --noUI --runscript="{script}"'
    env = dict(os.environ)
    env["CDS_JOB"] = str(jp)
    t0 = time.time()
    proc = subprocess.Popen(cmdline, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(build))
    deadline = time.time() + float(os.environ.get("CDS_CORPUS_TIMEOUT_S", "600"))
    dialog = ""
    while proc.poll() is None:
        time.sleep(5)
        dialog = visible_dialog(proc.pid)
        if dialog or time.time() > deadline:
            # свой процесс (запущен этим скриптом): модальный диалог среды в --noUI — записать текст и снять
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            proc.wait()
            break
    res_path = Path(job["result"])
    if not res_path.exists():
        if dialog:
            (build / "dialog.txt").write_text(dialog, encoding="utf-8")
            raise SystemExit("CODESYS показал модальный диалог (build/corpus/dialog.txt): " + dialog[:1500])
        raise SystemExit(f"CODESYS не записал результат (код {proc.returncode}); журнал: {job['log']}")
    res: dict[str, Any] = json.loads(res_path.read_text(encoding="utf-8"))
    res["seconds_total"] = round(time.time() - t0, 1)
    return res


def write_oracles(
    stands: list[dict[str, Any]], traces: dict[str, Any], source_sha: str, date: str, runtime: str
) -> list[str]:
    written = []
    for st in stands:
        tr = traces.get(st["name"])
        if not tr:
            continue
        rows_out = []
        header: list[str] = []
        for si, m in enumerate(st["meta"]):
            if not header:
                header = ["scenario", "cycle", "t_ms"] + [f"in.{p}:{t}" for p, (t, _v) in m["inputs"]] + \
                         [f"out.{p}:{t}" for p, (t, _v) in m["outputs"]]  # fmt: skip
            ts = tr[f"aT{si}"]
            for k in range(m["cycles"]):
                rec = [m["scenario"], str(k + 1), str(plc_value(ts[k], "TIME"))]
                rec += [m["per_cycle"][p][k] for p, _tv in m["inputs"]]
                for p, (t, _v) in m["outputs"]:
                    raw = tr[f"aOut{si}_{p.replace('.', '_')}"][k]
                    v = plc_value(raw, t)
                    rec.append(
                        ("TRUE" if v else "FALSE")
                        if t == "BOOL"
                        else (f"T#{v}MS" if t == "TIME" else repr(v) if isinstance(v, float) else str(v))
                    )
                rows_out.append(rec)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows_out)
        d = ROOT / "corpus" / st["case"]
        (d / "oracle-codesys.csv").write_text(buf.getvalue(), encoding="utf-8", newline="\n")
        meta = {
            "format": "oracle-codesys/1", "tool": "cds2ms tools/codesys/corpus.py", "codesys": "3.5.17.30",
            "device": "CODESYS Control Win V3 (4096 / 0000 0001 / 3.5.17.30)", "runtime": runtime, "date": date,
            "source_sha256": source_sha, "task": "StandTask", "period_ms": STAND_MS,
            "cycles": sum(m["cycles"] for m in st["meta"]), "scenarios": [m["scenario"] for m in st["meta"]],
            "pou": st["pou"],
        }  # fmt: skip
        (d / "oracle-codesys.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        written.append(st["case"])
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-run", action="store_true", help="без рантайма: импорт, сборка, экспорт")
    a = ap.parse_args(argv)
    build = ROOT / "build" / "corpus"
    build.mkdir(parents=True, exist_ok=True)
    build_corpus.main([])
    # IL: импорт пробуется (итог — в stage0.json), но в 3.5.17.30 без опции «Enable IL» POU не создаётся, поэтому
    # обвязка PRG_IlHost и стенды IL в проект не входят (docs/FORMAT-OUT.md)
    stands = [stand(d, p) for d, p, lang in S.CASES if lang != "IL"]
    st_pous = [list(x) for x in S.ST_POUS] + [list(S.PRG_OOP)]
    job = {
        "project": str(build / "udr1.project"),
        "export": str(build / "export.xml"),
        "result": str(build / "result.json"),
        "log": str(build / "codesys.log"),
        "device": {"type": 4096, "id": "0000 0001", "version": "3.5.17.30"},
        "duts": {n: [DUT_KIND[n], t] for n, t in S.DUTS.items()},
        "gvls": S.GVLS,
        "interfaces": [S.I_DEVICE],
        "st_pous": st_pous,
        "oop": [S.FB_DEVICE_BASE, S.FB_DOSING_PUMP],
        "xml": per_pou_xml(build),
        "libraries": [
            {"placeholder": "Standard", "target": "Standard, * (System)"},
            {"placeholder": "IecSfc", "target": "IecSfc, * (System)"},
        ],
        "tasks": S.TASKS,
        # формы по языкам — экспорт объекта CODESYS (размещение types/pous): фикстуры tests/fixtures/sp17
        "export_each": [
            "FB_AnalogScale",
            "FB_LevelAlarm",
            "FB_ValveCmd",
            "PRG_Permissives",
            "PRG_PumpInterlock",
            "FB_DoseCtrl",
            "FB_RatioCalc",
            "PRG_FillSeq",
            "PRG_CipSeq",
            "FB_DosingPump",
            "I_Device",
            "GVL_IO",
            "GVL_Retain",
            "ST_Recipe",
            "E_DoseState",
        ],
        "export_dir": str(ROOT / "tests" / "fixtures" / "sp17"),
        "stands": [{"name": s["name"], "decl": s["decl"], "body": s["body"], "arrays": s["arrays"]} for s in stands],
        "stand_ms": f"T#{STAND_MS}MS",
        "run": not a.no_run,
        "runtime": {"credentials": str(RUNTIME_DIR / "credentials.json"), "timeout_s": 120},
    }
    own_pid = None
    lock = None
    runtime_info = "не запускался"
    if not a.no_run:
        lock = runtime_lock("codesys-to-masterscada: трассы корпуса УДР-1")
        try:
            lock.acquire()
        except CdsError as exc:
            print(f"runtime busy: {exc}")
            job["run"] = False
            lock = None
        if job["run"]:
            if port_open(11740):
                runtime_info = "рантайм соседнего сеанса (не перезапускался)"
            else:
                own_pid = start_own_runtime()
                runtime_info = f"свой рантайм pid {own_pid}" if own_pid else "рантайм не запущен"
                if own_pid is None:
                    job["run"] = False
    try:
        res = run_codesys(job, build)
    finally:
        if own_pid is not None:
            stop_runtime(own_pid)
        if lock is not None:
            lock.release()
    stage0 = {k: res.get(k) for k in ("libraries", "library_refs", "created", "import", "objects_after_import", "tasks",
                                      "build", "export_each", "stand_build", "run_done", "run_seconds", "error",
                                      "seconds_total")}  # fmt: skip
    stage0["runtime"] = runtime_info
    (build / "stage0.json").write_text(json.dumps(stage0, ensure_ascii=False, indent=1), encoding="utf-8")
    exp = Path(job["export"])
    if exp.exists():
        shutil.copyfile(exp, ROOT / "corpus" / "udr1" / "source.cds.xml")
    print(f"сборка: ошибок {res.get('build', {}).get('errors')}, стенды: {res.get('stand_build', {}).get('errors')}, "
          f"импорт: {res.get('import')}, рантайм: {runtime_info}, прогон: {res.get('run_done')}")  # fmt: skip
    if res.get("error"):
        print(res["error"])
    if res.get("traces"):
        sha = (
            hashlib.sha256((ROOT / "corpus" / "udr1" / "source.cds.xml").read_bytes()).hexdigest()
            if exp.exists()
            else ""
        )
        done = write_oracles(stands, res["traces"], sha, dt.date.today().isoformat(), runtime_info)
        print("трассы: " + ", ".join(done))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
