#!/usr/bin/env python3
"""Дописать пиктограмму mig_mscada в конец pictograms.py медиа-кита портфолио (общая процедура семейства).

Блокировка %LOCALAPPDATA%/plc-tools/media-kit.lock (тот же FileLock, что у рантайма: tools/codesys/lock.py) ->
перечитать файл -> если `def mig_mscada` уже есть, только проверить -> временный файл рядом, сверка SHA-256 с
прочитанным, os.replace (файл изменился — повтор) -> `import pictograms` в отдельном процессе и тесты кита ->
снять блокировку. Литерал REGISTRY и чужие функции не трогаются: в конец файла дописываются функция и строка
`REGISTRY["mig_mscada"] = mig_mscada` с теми же переводами строк, что в файле.

    python tools/media/add_pictogram.py [--kit DIR] [--check | --update]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "codesys"))

from lock import FileLock  # noqa: E402

KIT_DEFAULT = Path(
    os.environ.get("MEDIA_KIT", str(REPO.parent / "asu_TP" / "domestic-plc-gaps" / "_shared" / "media-kit"))
)
FRAGMENT = Path(__file__).with_name("mig_mscada.pyfrag")
PID = "mig_mscada"
LOCK = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "plc-tools" / "media-kit.lock"


def addition(nl: bytes) -> bytes:
    body = FRAGMENT.read_text(encoding="utf-8").strip("\n").replace("\n", "\r\n" if nl == b"\r\n" else "\n")
    reg = f'REGISTRY["{PID}"] = {PID}'
    return nl * 2 + body.encode("utf-8") + nl * 3 + reg.encode("utf-8") + nl


def verify(kit: Path) -> bool:
    code = f"import pictograms, brand; g = pictograms.build('{PID}', brand.theme('dark')); print(min(g.sizes))"
    imp = subprocess.run([sys.executable, "-c", code], cwd=kit, capture_output=True, text=True)
    print(f"[picto] import pictograms: {'OK' if imp.returncode == 0 else 'ОШИБКА'} {imp.stdout.strip()}")
    if imp.returncode:
        print(imp.stderr[-2000:], file=sys.stderr)
        return False
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", str(kit / "tests"), "-q", "-p", "no:cacheprovider"], cwd=kit
    )
    print(f"[picto] тесты кита: {'OK' if tests.returncode == 0 else 'ОШИБКА'}")
    return tests.returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="пиктограмма mig_mscada в медиа-ките")
    ap.add_argument("--kit", type=Path, default=KIT_DEFAULT)
    ap.add_argument("--check", action="store_true", help="только проверить, ничего не писать")
    ap.add_argument("--update", action="store_true", help="заменить текст своей функции mig_mscada")
    args = ap.parse_args(argv)
    target = args.kit / "pictograms.py"
    lock = FileLock(LOCK, timeout_s=900, purpose="codesys-to-masterscada: пиктограмма mig_mscada")
    lock.acquire()
    try:
        for _attempt in range(5):
            raw = target.read_bytes()
            if f"def {PID}(".encode() in raw:
                if not args.update:
                    print(f"[picto] {PID} уже есть — проверка")
                    return 0 if verify(args.kit) else 1
                # своя функция: заменить её текст (от «def mig_mscada(» до строки REGISTRY) — чужое не трогаем
                nl = b"\r\n" if b"\r\n" in raw else b"\n"
                start = raw.index(f"def {PID}(".encode())
                reg = f'REGISTRY["{PID}"] = {PID}'.encode()
                end = raw.index(reg, start)
                body = addition(nl).strip(b"\r\n").split(nl * 3)[0]
                new = raw[:start] + body + nl * 3 + raw[end:]
                if new == raw:
                    print(f"[picto] {PID} не изменилась")
                    return 0 if verify(args.kit) else 1
            elif args.update:
                print(f"[picto] {PID} нет — сначала без --update", file=sys.stderr)
                return 1
            else:
                if args.check:
                    print(f"[picto] {PID} нет", file=sys.stderr)
                    return 1
                nl = b"\r\n" if b"\r\n" in raw else b"\n"
                new = raw + addition(nl) if raw.endswith(nl) else raw + nl + addition(nl)
            tmp = target.with_name(target.name + f".{os.getpid()}.tmp")
            tmp.write_bytes(new)
            if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(raw).digest():
                tmp.unlink()
                print("[picto] файл изменился во время записи — повтор")
                continue
            os.replace(tmp, target)
            print(f"[picto] {PID} дописана в {target}")
            if verify(args.kit):
                return 0
            if target.read_bytes() == new:  # сломали импорт — вернуть как было
                target.write_bytes(raw)
                print("[picto] проверка не прошла — файл возвращён", file=sys.stderr)
            return 1
        print("[picto] файл всё время меняется — отказ", file=sys.stderr)
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
