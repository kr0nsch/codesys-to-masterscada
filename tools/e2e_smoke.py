"""e2e демо: Playwright (Python) против статики site/ на ThreadingHTTPServer (порт 0, префикс /codesys-to-masterscada/).

Проверки: Pyodide грузится из своего каталога; пример УДР-1 пересчитывается в браузере и SHA-256 zip совпадает с
предрасчётом CLI; число находок на странице = `cds2ms analyze` (тот же --fix safe); вкладки открываются; zip
скачивается; ни одного запроса к чужим доменам. Скриншоты — в --shots (dark и light).

    python tools/build_site.py && python tools/e2e_smoke.py --site site --shots build/e2e
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/codesys-to-masterscada/"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map: ClassVar[dict[str, str]] = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
        ".js": "text/javascript",
        ".wasm": "application/wasm",
        ".json": "application/json",
    }

    def translate_path(self, path: str) -> str:
        if path.startswith(PREFIX):
            path = "/" + path[len(PREFIX) :]
        return super().translate_path(path)

    def log_message(self, *args: object) -> None:  # тихо
        pass


def cli_findings() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "cds2ms", "analyze", str(ROOT / "corpus" / "udr1" / "source.cds.xml"), "--format", "json",
         "--fail-on", "never"],
        capture_output=True, text=True, encoding="utf-8", check=True, cwd=ROOT,
    ).stdout  # fmt: skip
    return len(json.loads(out)["findings"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default=str(ROOT / "site"))
    ap.add_argument("--shots", default=str(ROOT / "build" / "e2e"))
    ap.add_argument("--timeout-s", type=float, default=180)
    a = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright

    shots = Path(a.shots)
    shots.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(Handler, directory=a.site)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{srv.server_address[1]}"
    url = origin + PREFIX
    expected = cli_findings()
    foreign: list[str] = []
    errors: list[str] = []
    ok = True
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for scheme in ("dark", "light"):
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1000}, color_scheme=scheme, accept_downloads=True
                )
                page.on(
                    "request",
                    lambda r: foreign.append(r.url) if not r.url.startswith((origin, "data:", "blob:")) else None,
                )
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(url)
                page.wait_for_selector("body[data-ready='1']", timeout=a.timeout_s * 1000)
                page.click("button[data-example='udr1']")
                page.wait_for_selector("body[data-done='1']", timeout=a.timeout_s * 1000)
                n = int(page.inner_text("#n-findings"))
                match = page.get_attribute("body", "data-zip-match")
                print(f"[{scheme}] находок на странице {n}, CLI {expected}; SHA-256 zip совпал: {match == '1'}")
                ok &= n == expected and match == "1"
                page.screenshot(path=str(shots / f"shot-demo-pous-{scheme}.png"))
                for tab in ("langs", "behaviour", "model", "matrix", "steps"):
                    page.click(f"#tabs button[data-tab='{tab}']")
                    page.wait_for_timeout(150)
                    if tab == "behaviour":
                        page.screenshot(path=str(shots / f"shot-demo-behaviour-{scheme}.png"), full_page=False)
                page.click("#tabs button[data-tab='zip']")
                with page.expect_download() as dl:
                    page.click("#dl")
                path = dl.value.path()
                size = Path(path).stat().st_size if path else 0
                print(f"[{scheme}] zip скачан: {dl.value.suggested_filename}, {size} байт")
                ok &= size > 1000
                page.close()
            browser.close()
    finally:
        srv.shutdown()
    if foreign:
        print("запросы к чужим доменам:", sorted(set(foreign))[:10])
        ok = False
    if errors:
        print("ошибки страницы:", errors[:5])
        ok = False
    print("e2e: OK" if ok else "e2e: ОШИБКА")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
