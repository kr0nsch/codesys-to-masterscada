"""Клон опубликованной plc-process-lib (MIT) по SHA в .cache/ — реальный кейс ООП (M12-1).

python tools/fetch_processlib.py        # печатает путь к src/ или код 2 без сети
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

URL = "https://github.com/kr0nsch/plc-process-lib.git"
SHA = "a321ad01f47eae4f5c29ed46d9764a2d738c2dd4"
ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / ".cache" / f"plc-process-lib-{SHA[:12]}"


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, timeout=300
    ).stdout.strip()


def fetch() -> Path | None:
    if (DEST / "src").is_dir():
        try:
            if _git("rev-parse", "HEAD", cwd=DEST) == SHA:
                return DEST
        except (OSError, subprocess.CalledProcessError):
            pass
    try:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        if not (DEST / ".git").is_dir():
            _git("init", "-q", str(DEST))
            _git("remote", "add", "origin", URL, cwd=DEST)
        _git("fetch", "-q", "--depth", "1", "origin", SHA, cwd=DEST)
        _git("checkout", "-q", "FETCH_HEAD", cwd=DEST)
        if _git("rev-parse", "HEAD", cwd=DEST) != SHA:
            return None
        return DEST
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def main() -> int:
    p = fetch()
    if p is None:
        print("plc-process-lib: нет сети или SHA не найден", file=sys.stderr)
        return 2
    print(p / "src")
    return 0


if __name__ == "__main__":
    sys.exit(main())
