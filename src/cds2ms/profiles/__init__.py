"""Профили цели и источника (TOML, ``tomllib``): статусы возможностей с источниками и семантика симулятора."""

from __future__ import annotations

import csv
import io
import re
import tomllib
from dataclasses import dataclass
from importlib import resources
from typing import Any

TARGET = "masterscada-4d-1.3.10"
SOURCE = "codesys-3.5.17"


@dataclass
class Profile:
    id: str
    data: dict[str, Any]
    text: str

    @property
    def semantics(self) -> dict[str, Any]:
        return dict(self.data.get("semantics", {}))

    @property
    def features(self) -> dict[str, dict[str, Any]]:
        return dict(self.data.get("features", {}))

    @property
    def variants(self) -> dict[str, list[str]]:
        return dict(self.data.get("variants", {}))

    def names(self, key: str) -> list[str]:
        return [str(x) for x in self.data.get("names", {}).get(key, [])]

    def feature(self, key: str) -> dict[str, Any]:
        return dict(self.features.get(key, {"status": "unknown", "confidence": "L", "source": ""}))

    def status(self, key: str) -> str:
        return str(self.feature(key).get("status", "unknown"))


def available() -> list[str]:
    root = resources.files("cds2ms") / "profiles"
    return sorted(p.name[: -len(".toml")] for p in root.iterdir() if p.name.endswith(".toml"))


def load(pid: str = TARGET, overrides: list[str] | None = None) -> Profile:
    text = (resources.files("cds2ms") / "profiles" / f"{pid}.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    for ov in overrides or []:
        key, _, val = ov.partition("=")
        if not _:
            raise ValueError(f"--set ожидает k=v, получено «{ov}»")
        _set(data, key.strip(), _parse_value(val.strip()))
    return Profile(pid, data, text)


def _parse_value(v: str) -> Any:
    try:
        return tomllib.loads(f"x = {v}")["x"]
    except tomllib.TOMLDecodeError:
        return v


def _set(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    if len(parts) == 1:
        parts = ["semantics", parts[0]]
    cur = data
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def load_data(name: str) -> dict[str, Any]:
    return tomllib.loads((resources.files("cds2ms") / "data" / name).read_text(encoding="utf-8"))


def effort(rule: str, outcome: str) -> tuple[float, float, float]:
    data = load_data("effort.toml")
    r = data.get("rules", {}).get(rule)
    if r is not None and outcome not in ("info", "auto"):
        a, b, c = r["minutes"]
        return float(a), float(b), float(c)
    a, b, c = data["defaults"][outcome]
    return float(a), float(b), float(c)


# пробы → возможности профиля (для apply-probe)
PROBE_FEATURES = {
    "P-ST-01": "VAR_IN_OUT",
    "P-ST-02": "CASE_ENUM",
    "P-ST-07": "RETAIN",
    "P-RT-01": "INT_OVERFLOW",
    "P-RT-03": "REAL_TO_INT",
    "P-RT-04": "TIME_SIGNED",
    "P-RT-06": "DT_DEFAULT",
    "P-IMP-01": "PLCOPEN_IMPORT",
    "P-CS-03": "ST_FILE",
}


def apply_probe(profile_text: str, results_csv: str) -> tuple[str, list[str]]:
    """Статусы профиля по ``probe/RESULTS.csv``: ok → supported, error → unsupported (проверено вручную)."""
    changed: list[str] = []
    text = profile_text
    for row in csv.DictReader(io.StringIO(results_csv)):
        obs = (row.get("observed") or "not-run").strip()
        feat = PROBE_FEATURES.get((row.get("probe_id") or "").strip())
        if feat is None or obs == "not-run":
            continue
        status = "supported" if obs == "ok" or obs.startswith("value:") or obs.startswith("place:") else "unsupported"
        note = f"проверено вручную {row.get('date', '')}, {row.get('ide', '')} {row.get('ide_version', '')}: {obs}"
        pat = re.compile(rf"(\[features\.{re.escape(feat)}\]\n)(status = \"[a-z]+\"\n)")
        if pat.search(text):
            new_block = f'status = "{status}"\nverified = "{note}"\n'

            def _sub(m: re.Match[str], block: str = new_block) -> str:
                return m.group(1) + block

            text = pat.sub(_sub, text, count=1)
            changed.append(f"{feat}: {status}")
    return text, changed
