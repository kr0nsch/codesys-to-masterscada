// Воркер: Pyodide из ./pyodide/ (без CDN), пакет cds2ms — zip-архивом; перенос — cds2ms.web.run.
import { loadPyodide } from "./pyodide/pyodide.mjs";

let py = null;

async function init() {
  const base = new URL("./pyodide/", import.meta.url).href;
  py = await loadPyodide({ indexURL: base });
  const pkg = await fetch(new URL("./cds2ms.zip", import.meta.url));
  if (!pkg.ok) throw new Error("нет cds2ms.zip");
  py.unpackArchive(await pkg.arrayBuffer(), "zip", { extractDir: "/home/pyodide/pkg" });
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide/pkg'); import cds2ms.web");
  const ver = py.runPython("import cds2ms; cds2ms.__version__");
  postMessage({ type: "ready", version: ver });
}

const ready = init().catch((e) => postMessage({ type: "error", message: String(e) }));

onmessage = async (ev) => {
  await ready;
  const { id, name, data, fix } = ev.data;
  try {
    py.globals.set("_name", name);
    py.globals.set("_data", py.toPy(new Uint8Array(data)));
    py.globals.set("_fix", fix || "safe");
    const t0 = performance.now();
    const out = py.runPython("cds2ms.web.run(_name, bytes(_data), _fix)");
    postMessage({ type: "result", id, json: out, ms: Math.round(performance.now() - t0) });
  } catch (e) {
    postMessage({ type: "error", id, message: String(e).split("\n").slice(-3).join(" ") });
  }
};
