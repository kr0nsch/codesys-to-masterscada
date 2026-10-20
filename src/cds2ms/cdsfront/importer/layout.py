"""Импорт раскладки ST plc-repo-template (контракт ``docs/LAYOUT.md`` s7-to-codesys).

``POUs/<Name>/<Name>.decl.st`` + ``.impl.st``, методы ``<M>.method.{decl,impl}.st``, свойства
``<P>.prop.decl.st`` + ``<P>.{get,set}.{decl,impl}.st``, ``DUTs/*.dut.st``, ``GVLs/*.gvl.st`` и ``*.pvl.st``,
``Interfaces/<I>/<I>.itf.st``. Пути в происхождении — относительно корня раскладки, через ``/``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath

from ...ir.model import Body, Dut, Gvl, Interface, Method, Origin, Pou, Project, Property
from ..st.parser import parse_decl

_KIND = {"PROGRAM": "program", "FUNCTION_BLOCK": "functionBlock", "FUNCTION": "function"}


def read_tree(root: Path) -> dict[str, str]:
    """Все *.st под корнем: относительный POSIX-путь → текст (UTF-8, BOM снимается)."""
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*.st")):
        rel = p.relative_to(root).as_posix()
        out[rel] = p.read_bytes().decode("utf-8-sig")
    return out


def load_files(files: Mapping[str, str], name: str = "layout", base: str = "") -> Project:
    """Проект из словаря «путь → текст» (так же работает в браузере)."""
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8") + b"\0" + files[rel].encode("utf-8") + b"\0")
    proj = Project(name=name, source_kind="st-layout", source_file=base or name, source_sha256=h.hexdigest())
    proj.placements.append("layout")

    def org(rel: str) -> Origin:
        return Origin(f"{base}/{rel}" if base else rel, 1, 1)

    by_dir: dict[str, dict[str, str]] = {}
    for rel, text in files.items():
        pp = PurePosixPath(rel)
        by_dir.setdefault(str(pp.parent), {})[pp.name] = text

    for rel in sorted(files):
        pp = PurePosixPath(rel)
        fname = pp.name
        text = files[rel]
        if fname.endswith(".dut.st"):
            proj.duts.append(Dut(fname[: -len(".dut.st")], text, org(rel), 1))
        elif fname.endswith(".gvl.st"):
            proj.gvls.append(Gvl(fname[: -len(".gvl.st")], text, org(rel), False, 1))
        elif fname.endswith(".pvl.st"):
            proj.gvls.append(Gvl(fname[: -len(".pvl.st")], text, org(rel), True, 1))
        elif fname.endswith(".itf.st"):
            iname = fname[: -len(".itf.st")]
            siblings = by_dir.get(str(pp.parent), {})
            methods, props = _members(siblings, str(pp.parent), org, interface=True)
            pd = parse_decl(text)
            ext = pd.decl.header.extends if pd.decl.header else []
            proj.interfaces.append(Interface(iname, text, methods, props, org(rel), ext))
        elif fname.endswith(".decl.st") and fname.count(".") == 2 and pp.parent.name == fname[: -len(".decl.st")]:
            pname = fname[: -len(".decl.st")]
            siblings = by_dir.get(str(pp.parent), {})
            impl_name = f"{pname}.impl.st"
            impl = siblings.get(impl_name, "")
            impl_rel = str(pp.parent / impl_name)
            hdr = parse_decl(text).decl.header
            kind = _KIND.get(hdr.kind, "program") if hdr else "program"
            folder = "/".join(pp.parent.parts[:-1][1:]) if len(pp.parent.parts) > 2 else ""
            body = Body("ST", text=impl, line=1, col=1, file=org(impl_rel).file)
            pou = Pou(pname, kind, text, body, org(rel), 1, folder=folder, placement="layout")
            methods, props = _members(siblings, str(pp.parent), org, interface=False)
            pou.methods = methods
            pou.properties = props
            proj.pous.append(pou)
    return proj


def _members(
    siblings: Mapping[str, str], d: str, o: Callable[[str], Origin], interface: bool
) -> tuple[list[Method], list[Property]]:
    methods: list[Method] = []
    props: list[Property] = []
    for fname in sorted(siblings, key=str.lower):
        if fname.endswith(".method.decl.st"):
            m = fname[: -len(".method.decl.st")]
            impl = siblings.get(f"{m}.method.impl.st")
            body = None
            if not interface and impl is not None:
                body = Body("ST", text=impl, line=1, col=1, file=o(f"{d}/{m}.method.impl.st").file)
            methods.append(Method(m, siblings[fname], body, o(f"{d}/{fname}"), 1))
    for fname in sorted(siblings, key=str.lower):
        if fname.endswith(".prop.decl.st"):
            pn = fname[: -len(".prop.decl.st")]
            acc: dict[str, Method | None] = {}
            for a in ("get", "set"):
                dfile, ifile = f"{pn}.{a}.decl.st", f"{pn}.{a}.impl.st"
                if dfile in siblings or ifile in siblings:
                    impl = siblings.get(ifile)
                    acc[a] = Method(
                        a.capitalize(),
                        siblings.get(dfile, "VAR\nEND_VAR\n"),
                        None
                        if interface or impl is None
                        else Body("ST", text=impl, line=1, col=1, file=o(f"{d}/{ifile}").file),
                        o(f"{d}/{ifile if ifile in siblings else dfile}"),
                        1,
                    )
                else:
                    acc[a] = None
            props.append(Property(pn, siblings[fname], acc["get"], acc["set"], o(f"{d}/{fname}"), 1))
    return methods, props


def load(root: Path, base: str | None = None) -> Project:
    files = read_tree(root)
    return load_files(files, name=root.name, base=base if base is not None else root.name)
