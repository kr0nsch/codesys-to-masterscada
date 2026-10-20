"""Общие фикстуры тестов cds2ms."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
XSD_SHA = "591b92ba65018a77c32ab9e606abf27bd810cb1f7761d972a85689531c51e20f"


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def handmade_bytes() -> bytes:
    return (CORPUS / "udr1" / "source.handmade.xml").read_bytes()


@pytest.fixture(scope="session")
def udr1_migration():  # type: ignore[no-untyped-def]
    from cds2ms import api

    proj = api.load_path(CORPUS / "udr1" / "source.handmade.xml")
    return api.migrate(proj, api.Options(fix="review"))


@pytest.fixture(scope="session")
def cds_migration():  # type: ignore[no-untyped-def]
    """Тот же корпус после CODESYS: экспорт приложения 3.5.17.30 (import_xml → сборка → export_xml)."""
    from cds2ms import api

    proj = api.load_path(CORPUS / "udr1" / "source.cds.xml")
    return api.migrate(proj, api.Options(fix="review"))


@pytest.fixture(scope="session")
def chain_migration():  # type: ignore[no-untyped-def]
    from cds2ms import api

    proj = api.load_path(CORPUS / "s7-chain")
    return api.migrate(proj, api.Options(fix="review"))


@pytest.fixture(scope="session")
def xsd_path() -> Path | None:
    """Официальная XSD TC6 2.01 (plcopen.org) из .cache/ по SHA-256; в git её нет (условия распространения не указаны)."""
    p = ROOT / ".cache" / "xsd" / "tc6_xml_v201.xsd"
    if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == XSD_SHA:
        return p
    try:
        import sys

        sys.path.insert(0, str(ROOT / "tools"))
        import fetch_xsd

        got = fetch_xsd.fetch()
        if got is not None:
            return got
    except Exception:
        pass
    if os.environ.get("REQUIRE_XSD") == "1":
        pytest.fail("REQUIRE_XSD=1, но XSD TC6 2.01 не загружена")
    return None
