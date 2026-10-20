"""Пороги покрытия src/cds2ms: строки ≥ 85 %, ветви ≥ 75 % (pytest --cov=cds2ms --cov-branch --cov-report=json).

python tools/check_coverage.py build/coverage.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LINES, BRANCHES = 85.0, 75.0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    data = json.loads(Path(args[0] if args else "build/coverage.json").read_text(encoding="utf-8"))
    t = data["totals"]
    lines = 100.0 * t["covered_lines"] / max(1, t["num_statements"])
    branches = 100.0 * t["covered_branches"] / max(1, t["num_branches"])
    ok = lines >= LINES and branches >= BRANCHES
    print(
        f"покрытие: строки {lines:.1f} % (порог {LINES:g}), ветви {branches:.1f} % (порог {BRANCHES:g}) — {'OK' if ok else 'ниже порога'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
