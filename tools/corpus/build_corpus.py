"""Сборка рукописного TC6 корпуса УДР-1.

- ``corpus/udr1/source.handmade.xml`` — весь корпус (ST, ООП в форме addData 3S, графика, IL, GVL, DUT, задачи):
  вход конвертера без CODESYS, в том числе для IL, который import_xml CODESYS не принимает;
- ``build/corpus/import.xml`` — только графика и IL для import_xml в CODESYS (ST и ООП там создаются текстом).

    python tools/corpus/build_corpus.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus" / "udr1"))
sys.path.insert(0, str(ROOT / "tools" / "corpus"))
sys.path.insert(0, str(ROOT / "src"))
import sources as S  # noqa: E402
from tc6 import interface_xml, pou, project  # noqa: E402

D3S = "http://www.3s-software.com/plcopenxml/"
X = "http://www.w3.org/1999/xhtml"


def _plain(text: str) -> str:
    return (f'<data name="{D3S}interfaceasplaintext" handleUnknown="implementation"><InterfaceAsPlainText>'
            f'<xhtml xmlns="{X}">{escape(text)}</xhtml></InterfaceAsPlainText></data>')  # fmt: skip


def _st(text: str) -> str:
    return f'<body><ST><xhtml xmlns="{X}">{escape(text)}</xhtml></ST></body>'


def oop_fb(fb: dict) -> str:  # type: ignore[type-arg]
    methods = "".join(
        f"<Method name={quoteattr(n)}>{interface_xml(d)}{_st(b)}<addData>{_plain(d)}</addData></Method>"
        for n, d, b in fb["methods"]
    )
    props = ""
    for n, d, get_b, set_b in fb["properties"]:
        acc = ""
        if get_b is not None:
            acc += f"<GetAccessor><interface />{_st(get_b)}<addData>{_plain('VAR' + chr(10) + 'END_VAR' + chr(10))}</addData></GetAccessor>"
        if set_b is not None:
            acc += f"<SetAccessor><interface />{_st(set_b)}<addData>{_plain('VAR' + chr(10) + 'END_VAR' + chr(10))}</addData></SetAccessor>"
        props += f"<Property name={quoteattr(n)}>{interface_xml('FUNCTION X : ' + d.split(':', 1)[1].strip())}{acc}<addData>{_plain(d)}</addData></Property>"
    return (
        f'<pou name={quoteattr(fb["name"])} pouType="functionBlock">{interface_xml(fb["decl"])}{_st(fb["body"])}<addData>'
        f'<data name="{D3S}method" handleUnknown="implementation">{methods}</data>'
        f'<data name="{D3S}property" handleUnknown="implementation">{props}</data>'
        f"{_plain(fb['decl'])}</addData></pou>"
    )


def interface(itf: dict) -> str:  # type: ignore[type-arg]
    methods = "".join(
        f"<Method name={quoteattr(n)}>{interface_xml(d)}<addData>{_plain(d)}</addData></Method>"
        for n, d in itf["methods"]
    )
    props = "".join(
        f"<Property name={quoteattr(n)}><GetAccessor><interface /></GetAccessor><addData>{_plain(d)}</addData></Property>"
        for n, d in itf["properties"]
    )
    return (f'<data name="{D3S}interface" handleUnknown="implementation"><Interface name={quoteattr(itf["name"])}>'
            f'<Methods>{methods}</Methods><Properties>{props}</Properties><addData>{_plain("INTERFACE " + itf["name"] + chr(10))}</addData>'
            "</Interface></data>")  # fmt: skip


def dut(name: str, text: str) -> str:
    return f'<dataType name={quoteattr(name)}><baseType><derived name="INT" /></baseType><addData>{_plain(text)}</addData></dataType>'


def gvl(name: str, text: str) -> str:
    attrs = ' constant="true"' if "CONSTANT" in text.split("\n", 1)[0] else ""
    attrs += ' retain="true"' if "RETAIN" in text.split("\n", 1)[0] else ""
    return f"<globalVars name={quoteattr(name)}{attrs}><addData>{_plain(text)}</addData></globalVars>"


def task(t: dict) -> str:  # type: ignore[type-arg]
    pous = "".join(f"<pouInstance name={quoteattr(p)} typeName={quoteattr(p)} />" for p in t["pous"])
    if t["kind"] == "Event":
        head = f'<task name={quoteattr(t["name"])} single={quoteattr(t["event"])} priority="{t["priority"]}">'
        ts = (f'<addData><data name="{D3S}tasksettings" handleUnknown="implementation"><TaskSettings KindOfTask="Event" '
              f'Event={quoteattr(t["event"])} /></data></addData>')  # fmt: skip
    else:
        head = f'<task name={quoteattr(t["name"])} interval={quoteattr(t["interval"])} priority="{t["priority"]}">'
        ts = ""
    return head + pous + ts + "</task>"


def handmade() -> str:
    pous = [pou(n, k, d, f'<ST><xhtml xmlns="{X}">{escape(b)}</xhtml></ST>') for n, k, d, b in S.ST_POUS]
    pous += [oop_fb(S.FB_DEVICE_BASE), oop_fb(S.FB_DOSING_PUMP)]
    n, k, d, b = S.PRG_OOP
    pous.append(pou(n, k, d, f'<ST><xhtml xmlns="{X}">{escape(b)}</xhtml></ST>'))
    pous += S.graphics() + S.il_pous()
    n, k, d, b = S.PRG_IL_HOST
    pous.append(pou(n, k, d, f'<ST><xhtml xmlns="{X}">{escape(b)}</xhtml></ST>'))
    text = project("UDR1", pous)
    dts = "".join(dut(n, t) for n, t in S.DUTS.items())
    text = text.replace("<types><dataTypes />", f"<types><dataTypes>{dts}</dataTypes>")
    gv = "".join(gvl(n, t) for n, t in S.GVLS.items())
    tasks = "".join(task(t) for t in S.TASKS)
    text = text.replace(
        "<instances><configurations /></instances></project>",
        f'<instances><configurations><configuration name="Device"><resource name="Application">{tasks}</resource>'
        f"</configuration></configurations></instances>"
        f'<addData><data name="{D3S}globalvars" handleUnknown="implementation">{gv}</data>{interface(S.I_DEVICE)}</addData></project>',
    )
    return text


def import_subset() -> str:
    return project("UDR1-graphics", S.graphics() + S.il_pous())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    hm = ROOT / "corpus" / "udr1" / "source.handmade.xml"
    text = handmade()
    if a.check:
        ok = hm.exists() and hm.read_text(encoding="utf-8") == text
        print("source.handmade.xml " + ("актуален" if ok else "устарел"))
        return 0 if ok else 1
    hm.write_text(text, encoding="utf-8", newline="\n")
    sub = ROOT / "build" / "corpus" / "import.xml"
    sub.parent.mkdir(parents=True, exist_ok=True)
    sub.write_text(import_subset(), encoding="utf-8", newline="\n")
    print(f"{hm.relative_to(ROOT)}: {len(text)} символов; {sub.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
