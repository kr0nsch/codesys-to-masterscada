"""XSD TC6 2.01 — официальный архив plcopen.org (00-INDEX §4.8): загрузка в .cache/xsd/ с проверкой SHA-256.

Схема в git не кладётся: условия распространения на странице не указаны.

    python tools/fetch_xsd.py
"""

from __future__ import annotations

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://www.plcopen.org/download_file/force/d397ab98-6a21-47d5-9fb1-37da9e94ef34/342/"
SHA256 = "591b92ba65018a77c32ab9e606abf27bd810cb1f7761d972a85689531c51e20f"
SIZE = 85975
ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / ".cache" / "xsd" / "tc6_xml_v201.xsd"


def fetch() -> Path | None:
    if DEST.exists() and hashlib.sha256(DEST.read_bytes()).hexdigest() == SHA256:
        return DEST
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "cds2ms-xsd"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except OSError:
        return None
    if data[:2] == b"PK":  # сайт отдаёт zip с одной схемой
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            data = z.read("tc6_xml_v201.xsd")
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256:
        return None
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(data)
    return DEST


def main() -> int:
    p = fetch()
    if p is None:
        print("XSD TC6 2.01: не загружена или SHA-256 не совпал", file=sys.stderr)
        return 2
    print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
