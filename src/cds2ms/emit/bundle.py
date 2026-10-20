"""Сборка выходного каталога: детерминированный zip (ZIP_STORED), changes.diff, файлы .ST."""

from __future__ import annotations

import difflib
import io
import zipfile
from importlib import resources

from .. import __version__

ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            z.writestr(info, files[name])
    return buf.getvalue()


def unified(original: dict[str, str], fixed: dict[str, str]) -> str:
    out: list[str] = []
    for name in sorted(set(original) | set(fixed)):
        a = original.get(name, "").splitlines(keepends=True)
        b = fixed.get(name, "").splitlines(keepends=True)
        if a == b:
            continue
        out.extend(difflib.unified_diff(a, b, f"a/{name}", f"b/{name}", n=2))
    text = "".join(x if x.endswith("\n") else x + "\n" for x in out)
    return text


def st_file(text: str, source: str, sha256: str) -> str:
    tpl = (resources.files("cds2ms") / "templates" / "st_file.txt").read_text(encoding="utf-8")
    return tpl.format(version=__version__, source=source, sha256=sha256, text=text.rstrip("\n"))
