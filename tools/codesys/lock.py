"""Блокировка рантайма CODESYS Control Win (один рантайм на машину, 00-INDEX §4.4).

Класс ``FileLock`` — точная копия из s7-to-codesys ``tools/codesys/cdshost/cli.py`` @ 2285760c1c99ce4218d5356c75e93111828f8e3b
(MIT, тот же автор): блокировка первого байта файла (``msvcrt.locking`` / ``fcntl.flock``), владелец — JSON
``{pid, host, purpose, since}`` в ``<lock>.owner``, снимается ОС при смерти процесса, файл не удаляется.
Своя реализация через ``O_EXCL`` с этим протоколом несовместима.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import socket
import sys
import time
from pathlib import Path
from types import TracebackType
from typing import IO

EXIT_LOCK = 4


class CdsError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def runtime_lock_path() -> Path:
    env = os.environ.get("CDS_RUNTIME_LOCK")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local")
    return Path(base) / "plc-tools" / "codesys-runtime.lock"


def lock_timeout_s() -> float:
    return float(os.environ.get("CDS_LOCK_TIMEOUT_S", "1800"))


class FileLock:
    """Межпроцессная блокировка файлом (msvcrt.locking / fcntl.flock); снимается и при смерти процесса."""

    def __init__(self, path: Path, timeout_s: float, poll_s: float = 0.5, purpose: str = "") -> None:
        self.path = path
        self.timeout_s = timeout_s
        self.poll_s = poll_s
        self.purpose = purpose
        self._handle: IO[bytes] | None = None

    @property
    def owner_path(self) -> Path:
        return self.path.with_name(self.path.name + ".owner")

    def _try_lock(self, handle: IO[bytes]) -> bool:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return False
            return True
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return False
            return True

    def _unlock(self, handle: IO[bytes]) -> None:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            with contextlib.suppress(OSError):
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            with contextlib.suppress(OSError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def owner(self) -> str:
        try:
            return self.owner_path.read_text(encoding="utf-8").strip()
        except OSError:
            return "неизвестно"

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        deadline = time.monotonic() + self.timeout_s
        announced = False
        while not self._try_lock(handle):
            if time.monotonic() >= deadline:
                handle.close()
                raise CdsError(
                    f"блокировка {self.path} занята дольше {self.timeout_s:.0f} с (владелец: {self.owner()}) "
                    "/ lock timeout",
                    EXIT_LOCK,
                )
            if not announced:
                print(f"[cds] ожидание блокировки {self.path} (владелец: {self.owner()}) ...", flush=True)
                announced = True
            time.sleep(self.poll_s)
        self._handle = handle
        info = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "purpose": self.purpose,
            "since": dt.datetime.now().isoformat(timespec="seconds"),
        }
        with contextlib.suppress(OSError):
            self.owner_path.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")

    def release(self) -> None:
        if self._handle is None:
            return
        with contextlib.suppress(OSError):
            self.owner_path.unlink()
        self._unlock(self._handle)
        self._handle.close()
        self._handle = None

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.release()


def runtime_lock(purpose: str) -> FileLock:
    return FileLock(runtime_lock_path(), lock_timeout_s(), purpose=purpose)
