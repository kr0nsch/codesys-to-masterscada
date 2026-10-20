"""Медиа README из реальных прогонов (медиа-кит портфолио, MEDIA_KIT или domestic-plc-gaps/_shared/media-kit).

    python tools/make_media.py [chart] [gif] [shots] [banner]

- chart: chart-ton-quantization-{dark,light}.png — PRG_TonQuant в режиме R2: трасса CODESYS Control Win 3.5.17.30
  (oracle-codesys.csv), модель CODESYS (10 мс) и модель MasterPLC (100 мс) — tools/behaviour.py;
- gif: demo-cli.gif — снятая term2gif сессия (inventory → analyze → migrate → simulate → csc_check --real → RuSTy);
  сессия сохраняется в tools/media/sessions/cli.json;
- shots: shot-demo-*-{dark,light}.png и demo-web.gif — демо (site/) в Chromium, тот же сервер, что у e2e;
- banner: баннеры и social preview по repos-migration.json (пиктограмма mig_mscada).
"""

from __future__ import annotations

import functools
import http.server
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
KIT = Path(os.environ.get("MEDIA_KIT", str(ROOT.parent / "asu_TP" / "domestic-plc-gaps" / "_shared" / "media-kit")))
MEDIA = ROOT / "docs" / "media"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(KIT))


def chart() -> None:
    import charts  # медиа-кит
    from behaviour import case_series

    from cds2ms import api

    mig = api.migrate(api.load_path(ROOT / "corpus" / "udr1" / "source.cds.xml"))
    s = case_series(mig, ROOT / "corpus" / "st" / "PRG_TonQuant", max_signals=2)
    for theme in ("dark", "light"):
        with charts.style(theme) as c:
            fig, axes = charts.figure(rows=2, height_ratios=[1, 1.6], size=(10, 5.4))
            series = [
                ("трасса CODESYS Control Win 3.5.17.30 (10 мс)", s["oracle"], c["series"][2], 5.0, 0.45, "-"),
                ("CODESYS, модель (10 мс)", s["codesys"], c["series"][0], 1.8, 1.0, "-"),
                ("MasterPLC, модель (100 мс)", s["masterplc"], c["accent"], 2.0, 1.0, (0, (5, 3))),
            ]
            for ax, sig in zip(axes, ("xQ", "tEt"), strict=True):
                for label, data, col, lw, alpha, ls in series:
                    pts = (data or {}).get(sig, [])
                    if not pts:
                        continue
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    ax.step(
                        xs, ys, where="post", color=col, lw=lw, alpha=alpha, ls=ls, label=label if sig == "xQ" else None
                    )
                ax.set_ylabel("Q" if sig == "xQ" else "ET, мс")
            axes[0].set_yticks([0, 1], ["FALSE", "TRUE"])
            axes[1].set_xlabel("время сценария, мс")
            for x, txt in ((50, "IN := TRUE"), (200, "CODESYS: Q"), (300, "MasterPLC: Q")):
                for ax in axes:
                    ax.axvline(x, color=c["neutral"], lw=1, ls=":")
                axes[0].annotate(
                    txt, xy=(x + 6, 0.5), xycoords=("data", "data"), ha="left", fontsize=9.5, color=c["muted"]
                )
            charts.header(
                fig,
                "TON 150 мс: задача CODESYS 10 мс против задачи MasterPLC 100 мс",
                "PRG_TonQuant, режим R2; MS-EXEC-01 — уставка таймера квантуется периодом задачи",
                c,
                ax=axes[0],
            )
            h, labels = axes[0].get_legend_handles_labels()
            fig.legend(h, labels, loc="lower center", ncols=3, bbox_to_anchor=(0.5, -0.04), fontsize=10)
            charts.save(fig, MEDIA / f"chart-ton-quantization-{theme}.png")
    print("chart: chart-ton-quantization-{dark,light}.png")


def gif() -> None:
    sessions = ROOT / "tools" / "media" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    venv = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    if venv.exists():
        key = next((k for k in env if k.upper() == "PATH"), "PATH")  # в Windows ключ «Path»
        env[key] = str(venv) + os.pathsep + env.get(key, "")
    if (ROOT / "out" / "udr1").exists():
        shutil.rmtree(ROOT / "out" / "udr1")
    cmds = [
        r"cds2ms inventory corpus\udr1\source.cds.xml",
        r"cds2ms analyze corpus\udr1\source.cds.xml --top 6 --fail-on never",
        r"cds2ms migrate corpus\udr1\source.cds.xml --out out\udr1 --fail-on never",
        r"cds2ms simulate corpus\udr1\source.cds.xml --pou PRG_TonQuant --scenario corpus\st\PRG_TonQuant\scenario.csv --regime R2 --expected corpus\st\PRG_TonQuant\expected-divergences.toml",
        r"python tools\csc_check.py out\udr1 --real",
        r"python tools\rusty_check.py --case udr1",
    ]  # fmt: skip
    session = sessions / "cli.json"
    subprocess.run([sys.executable, str(KIT / "term2gif.py"), "capture", "-o", str(session), "--cwd", str(ROOT), "--shell", "cmd",
                    "--title", "cmd", "--prompt", "codesys-to-masterscada> ", "--cols", "132", "--", *cmds],
                   check=True, env=env)  # fmt: skip
    import json

    data = json.loads(session.read_text(encoding="utf-8"))
    data.setdefault("meta", {})["cwd"] = ROOT.name  # путь рабочего места в репозиторий не кладём
    session.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    subprocess.run([sys.executable, str(KIT / "term2gif.py"), "render", str(session), str(MEDIA / "demo-cli.gif"),
                    "--speed", "1.8", "--colors", "64"], check=True, env=env)  # fmt: skip
    print("gif: demo-cli.gif")


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map: ClassVar[dict[str, str]] = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript",
                      ".js": "text/javascript", ".wasm": "application/wasm"}  # fmt: skip

    def translate_path(self, path: str) -> str:
        prefix = "/codesys-to-masterscada/"
        return super().translate_path("/" + path[len(prefix) :] if path.startswith(prefix) else path)

    def log_message(self, *args: object) -> None:
        pass


def shots() -> None:
    import shot  # медиа-кит
    from PIL import Image
    from playwright.sync_api import sync_playwright

    site = ROOT / "site"
    if not site.exists():
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_site.py")], check=True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Handler, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/codesys-to-masterscada/"
    frames: list[Image.Image] = []
    tmp = ROOT / "build" / "media"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for theme in ("dark", "light"):
                page = browser.new_page(
                    viewport={"width": 1440, "height": 900}, color_scheme=theme, device_scale_factor=1
                )
                page.goto(url)
                page.wait_for_selector("body[data-ready='1']", timeout=180_000)
                page.click("button[data-example='udr1']")
                page.wait_for_selector("body[data-done='1']", timeout=180_000)
                page.click("#tree li:nth-child(15)")  # PRG_FillSeq (SFC)
                page.evaluate(  # тела, а не объявления: прокрутить оба окна кода к началу автомата SFC
                    """() => { for (const id of ['code-src', 'code-dst']) { const el = document.getElementById(id);
                       const lines = el.textContent.split('\\n'); const i = lines.findIndex(l => l.includes('MS-LANG-04'));
                       if (i > 0) el.scrollTop = el.scrollHeight * i / lines.length; } }"""
                )
                page.evaluate("window.scrollTo(0, 360)")
                page.screenshot(path=str(MEDIA / f"shot-demo-pous-{theme}.png"))
                page.evaluate("window.scrollTo(0, 0)")
                for tab in ("behaviour", "model"):
                    page.click(f"#tabs button[data-tab='{tab}']")
                    page.wait_for_timeout(200)
                    page.evaluate("window.scrollTo(0, 360)")
                    page.screenshot(path=str(MEDIA / f"shot-demo-{tab}-{theme}.png"))
                    page.evaluate("window.scrollTo(0, 0)")
                if theme == "dark":  # кадры GIF: пример → POU на SFC → «Поведение» → «Модель» → zip
                    page.reload()
                    page.wait_for_selector("body[data-ready='1']", timeout=180_000)
                    steps = [("button[data-example='udr1']", 2200), ("#tree li:nth-child(15)", 2200),
                             ("#tabs button[data-tab='behaviour']", 2400), ("#tabs button[data-tab='model']", 2000),
                             ("#tabs button[data-tab='zip']", 2200)]  # fmt: skip
                    page.screenshot(path=str(tmp / "f0.png"))
                    frames.append(Image.open(tmp / "f0.png").convert("RGB"))
                    durations = [1200]
                    for i, (sel, ms) in enumerate(steps, 1):
                        page.click(sel)
                        if i == 1:
                            page.wait_for_selector("body[data-done='1']", timeout=180_000)
                        page.wait_for_timeout(300)
                        page.screenshot(path=str(tmp / f"f{i}.png"))
                        frames.append(Image.open(tmp / f"f{i}.png").convert("RGB"))
                        durations.append(ms)
                page.close()
            browser.close()
    finally:
        srv.shutdown()
    small = [f.resize((1100, int(f.height * 1100 / f.width)), Image.LANCZOS) for f in frames]
    poster = small[-1]  # первый кадр — финальный экран (постер для читателей без автовоспроизведения)
    shot.frames_to_gif([poster, *small], MEDIA / "demo-web.gif", durations=[1500, *durations], colors=128)
    print("shots: shot-demo-*-{dark,light}.png, demo-web.gif")


def banner() -> None:
    subprocess.run([sys.executable, str(KIT / "banner.py"), "render", "--spec", str(KIT / "repos-migration.json"), "--repo",
                    "codesys-to-masterscada", "--repo-layout", "--out", str(MEDIA)], check=True)  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    what = (argv if argv is not None else sys.argv[1:]) or ["chart", "gif", "shots", "banner"]
    MEDIA.mkdir(parents=True, exist_ok=True)
    for w in what:
        {"chart": chart, "gif": gif, "shots": shots, "banner": banner}[w]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
