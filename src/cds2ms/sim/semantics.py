"""Семантика профиля для симулятора: разрядности, REAL, TIME, деление, округление, DT по умолчанию."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, replace
from typing import Any

from ..cdsfront.stdlib import INT_TYPES

DT_0001 = -62_135_596_800_000  # мс от 1970-01-01 до 0001-01-01 (пролептический григорианский календарь)


class SimError(Exception):
    """Конструкция вне подмножества или ошибка исполнения (деление на ноль в CODESYS и т. п.)."""


@dataclass(frozen=True)
class Semantics:
    name: str  # codesys | masterplc
    int_overflow: str = "wrap"  # wrap | int64 | float64
    real_arith: str = "float32"  # float32 | float64
    real_to_int_half: str = "away"  # away | even
    div_zero: str = "error"  # error | zero
    time_bits: int = 32
    time_signed: bool = False
    for_bounds: str = "each"  # each | once
    dt_default: int = 0
    array_oob: str = "error"  # error | null
    string_bounded: bool = True
    period_ms: int = 10

    def variant(self, **kw: Any) -> Semantics:
        return replace(self, **kw)

    def label(self) -> str:
        return (
            f"{self.name}(int={self.int_overflow},real={self.real_arith},half={self.real_to_int_half},"
            f"div0={self.div_zero},time={self.time_bits}{'s' if self.time_signed else 'u'},for={self.for_bounds})"
        )


def codesys(period_ms: int = 10) -> Semantics:
    return Semantics("codesys", period_ms=period_ms)


def masterplc(profile_sem: dict[str, Any], variants: dict[str, list[str]], period_ms: int | None = None) -> Semantics:
    """Базовый вариант masterplc: для unknown — первый вариант из [variants] профиля."""

    def pick(key: str, default: str) -> str:
        v = str(profile_sem.get(key, default))
        if v == "unknown":
            opts = variants.get(key) or [default]
            return str(opts[0])
        return v

    return Semantics(
        "masterplc",
        int_overflow=pick("int_overflow", "wrap"),
        real_arith=pick("real_arith", "float64"),
        real_to_int_half=pick("real_to_int_half", "away"),
        div_zero=pick("div_zero", "zero"),
        time_bits=int(pick("time_bits", "64")),
        time_signed=bool(profile_sem.get("time_signed", True)),
        for_bounds=pick("for_bounds", "once"),
        dt_default=DT_0001,
        array_oob="null" if profile_sem.get("array_oob") == "null" else "error",
        string_bounded=False,
        period_ms=int(period_ms if period_ms is not None else profile_sem.get("task_period_default_ms", 100)),
    )


def all_variants(base: Semantics, variants: dict[str, list[str]]) -> list[Semantics]:
    """База плюс по одной альтернативе на каждую неизвестную (один фактор за раз)."""
    out = [base]
    field_of = {"int_overflow": "int_overflow", "real_arith": "real_arith", "real_to_int_half": "real_to_int_half",
                "div_zero": "div_zero", "time_bits": "time_bits", "for_bounds": "for_bounds"}  # fmt: skip
    for key, opts in sorted(variants.items()):
        f = field_of.get(key)
        if f is None:
            continue
        for o in opts:
            val: Any = int(o) if f == "time_bits" else o
            if getattr(base, f) != val:
                out.append(base.variant(**{f: val}))
    return out


def f32(x: float) -> float:
    try:
        return float(struct.unpack("<f", struct.pack("<f", x))[0])
    except OverflowError:
        return math.copysign(math.inf, x)


def wrap_int(v: int, bits: int, signed: bool) -> int:
    mask = (1 << bits) - 1
    v &= mask
    if signed and v >> (bits - 1):
        v -= 1 << bits
    return v


def coerce(sem: Semantics, type_name: str, v: Any) -> Any:
    """Значение при присваивании переменной типа ``type_name``."""
    t = type_name.upper()
    if v is None:
        return None
    if t == "BOOL":
        return bool(v)
    if t in INT_TYPES:
        bits, signed = INT_TYPES[t]
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, float):
            if sem.int_overflow == "float64":
                return v
            v = int(v)
        if sem.int_overflow == "wrap":
            return wrap_int(int(v), bits, signed)
        if sem.int_overflow == "int64":
            return wrap_int(int(v), 64, True)
        return v
    if t == "REAL":
        x = float(v)
        return f32(x) if sem.real_arith == "float32" else x
    if t == "LREAL":
        return float(v)
    if t in ("TIME", "TOD", "TIME_OF_DAY"):
        return wrap_int(int(v), sem.time_bits, sem.time_signed)
    if t in ("LTIME",):
        return wrap_int(int(v), 64, sem.time_signed)
    if t in ("DATE", "DT", "DATE_AND_TIME"):
        return int(v)
    return v


def real_to_int(sem: Semantics, x: float) -> int:
    if math.isnan(x) or math.isinf(x):
        raise SimError("REAL_TO_INT от NaN/Inf")
    if sem.real_to_int_half == "even":
        return int(round(x))
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)
