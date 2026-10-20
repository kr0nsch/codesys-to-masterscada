// Страница демо cds2ms: примеры (предрасчёт CLI сразу, затем пересчёт в браузере), загрузка своего файла, вкладки.
const $ = (s) => document.querySelector(s);
const OUT = ["auto", "review", "verify", "manual", "impossible", "info"];
const OUT_RU = { auto: "авто", review: "сверить", verify: "проверить", manual: "вручную", impossible: "невозможно", info: "сведения" };
const LANG_NOTE = {
  ST: "без понижения; правки Master ST по правилам MS-*",
  FBD: "сети → ST по потоку данных; переходы — структурировщик (IF или автомат migPc)",
  LD: "цепи → булевы выражения, катушки S/R, фронты через R_TRIG/F_TRIG",
  CFC: "порядок executionOrderId, обратные связи — переменные migCfcN (значение прошлого цикла)",
  SFC: "ST-автомат с порядком обработки CODESYS: шаги, IEC-действия, последний вызов",
  IL: "стековая машина CR → ST, переходы — структурировщик",
};

let worker = null;
let workerReady = false;
let seq = 0;
const pending = new Map();
let current = null;

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function setStatus(text, cls = "") {
  const el = $("#status");
  el.textContent = text;
  el.className = "status " + cls;
}

function startWorker() {
  worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  worker.onmessage = (ev) => {
    const m = ev.data;
    if (m.type === "ready") {
      workerReady = true;
      document.body.dataset.ready = "1";
      setStatus(`Python готов (cds2ms ${m.version}). Выберите пример или перетащите файл.`, "ok");
      if (current && current.pendingInput) runInBrowser(current.pendingInput.name, current.pendingInput.data, true);
      return;
    }
    const p = pending.get(m.id);
    if (m.type === "error") {
      setStatus("Ошибка: " + m.message, "err");
      if (p) pending.delete(m.id);
      return;
    }
    if (p) {
      pending.delete(m.id);
      p(m);
    }
  };
}

function runInBrowser(name, data, isExample) {
  if (!workerReady) {
    current = current || {};
    current.pendingInput = { name, data };
    setStatus("Среда Python ещё загружается: перенос начнётся автоматически…");
    return;
  }
  const id = ++seq;
  setStatus(`Перенос «${name}» в браузере…`);
  pending.set(id, (m) => {
    const res = JSON.parse(m.json);
    const pre = current && current.precomputed;
    let note = `Готово за ${(m.ms / 1000).toFixed(1)} с в браузере.`;
    if (isExample && pre) {
      const same = pre.zip_sha256 === res.zip_sha256;
      note += same ? " SHA-256 zip совпал с предрасчётом CLI." : " SHA-256 zip отличается от предрасчёта CLI!";
      document.body.dataset.zipMatch = same ? "1" : "0";
    }
    render(res, current ? current.behaviour : null);
    document.body.dataset.done = "1";
    setStatus(note, "ok");
  });
  worker.postMessage({ id, name, data, fix: "safe" }, [data]);
}

async function loadExamples() {
  const idx = await (await fetch("examples/index.json")).json();
  const box = $("#examples");
  for (const ex of idx) {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = ex.title;
    b.title = ex.note;
    b.dataset.example = ex.id;
    b.onclick = () => openExample(ex);
    box.appendChild(b);
  }
}

async function openExample(ex) {
  setStatus(`Пример «${ex.title}»: предрасчёт командной строки…`);
  const [res, beh, input] = await Promise.all([
    fetch(`examples/${ex.id}/result.json`).then((r) => r.json()),
    ex.behaviour ? fetch(`examples/${ex.id}/behaviour.json`).then((r) => r.json()) : Promise.resolve(null),
    fetch(`examples/${ex.id}/${ex.file}`).then((r) => r.arrayBuffer()),
  ]);
  current = { precomputed: res, behaviour: beh };
  render(res, beh);
  runInBrowser(ex.file, input, true);
}

function onFile(file) {
  current = { precomputed: null, behaviour: null };
  file.arrayBuffer().then((buf) => runInBrowser(file.name, buf, false));
}

// ------------------------------------------------------------------ отрисовка

function ring(counts) {
  const total = OUT.reduce((a, k) => a + (counts[k] || 0), 0) || 1;
  let acc = 0;
  const r = 52, c = 2 * Math.PI * r;
  const segs = OUT.map((k) => {
    const v = counts[k] || 0;
    const len = (v / total) * c;
    const s = `<circle r="${r}" cx="64" cy="64" fill="none" class="o-${k}" stroke-width="18" stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-acc}" transform="rotate(-90 64 64)"><title>${OUT_RU[k]}: ${v}</title></circle>`;
    acc += len;
    return s;
  }).join("");
  const legend = OUT.filter((k) => counts[k]).map((k) => `<li><i class="o-${k}"></i>${OUT_RU[k]} <b>${counts[k]}</b></li>`).join("");
  return `<svg viewBox="0 0 128 128" width="128" height="128">${segs}<text x="64" y="70" text-anchor="middle" class="ring-n">${total}</text></svg><ul class="legend">${legend}</ul>`;
}

function render(res, beh) {
  $("#result").hidden = false;
  const tot = res.report.totals.by_outcome;
  $("#ring").innerHTML = ring(tot);
  const e = res.report.effort;
  const langs = Object.entries(res.project.languages || {}).map(([k, v]) => `${k} ${v}`).join(" · ");
  $("#kpis").innerHTML = `
    <div><span>POU</span><b>${res.pous.length}</b><small>${esc(langs)}</small></div>
    <div><span>находок</span><b id="n-findings">${res.findings.length}</b><small>одна на место, остальные — в связанных</small></div>
    <div><span>трудоёмкость P50 / P90</span><b>${e.p50_h} / ${e.p90_h} ч</b><small>модель: треугольное распределение, ${e.runs} проб, не калибрована</small></div>
    <div><span>цель</span><b>${esc(res.report.target.profile)}</b><small>правки Master ST: --fix ${esc(res.report.fix)}</small></div>`;
  renderTree(res);
  renderLangs(res, beh);
  renderBehaviour(beh);
  renderModel(res.model);
  renderMatrix(res.report.automatability);
  $("#steps").textContent = res.manual_steps;
  renderZip(res);
}

function worstClass(o) {
  return "o-" + (o || "auto");
}

function renderTree(res) {
  const ul = $("#tree");
  ul.innerHTML = "";
  for (const p of res.pous) {
    const li = document.createElement("li");
    li.innerHTML = `<i class="${worstClass(p.outcome)}"></i><span class="nm">${esc(p.name)}</span><span class="lang">${esc(p.language)}</span><span class="cnt">${p.findings || ""}</span>`;
    li.onclick = () => showPou(res, p, li);
    ul.appendChild(li);
  }
  const first = res.pous.find((p) => p.language !== "ST") || res.pous[0];
  if (first) showPou(res, first, ul.children[res.pous.indexOf(first)]);
}

function showPou(res, p, li) {
  for (const x of document.querySelectorAll("#tree li")) x.classList.remove("sel");
  if (li) li.classList.add("sel");
  $("#pou-title").textContent = `${p.name} · ${p.kind} · ${p.language}`;
  $("#code-src").textContent = p.original || "(нет текста)";
  $("#code-dst").textContent = p.fixed || "(нет текста)";
  const cards = res.findings.filter((f) => f.pou === p.name || (!f.pou && f.message.includes(p.name)));
  $("#cards").innerHTML = cards.map((f) => `
    <div class="fcard ${worstClass(f.outcome)}">
      <div class="fh"><b>${esc(f.rule)}</b> ${esc(f.title)} <span class="badge">${OUT_RU[f.outcome]}</span><span class="conf" title="H — поведение цели описано в справке 1.3.10, L — не описано">${f.confidence}</span></div>
      <div class="fm">${esc(f.message)}${f.origin.line ? ` <small>строка ${f.origin.line}</small>` : ""}</div>
      ${f.related && f.related.length ? `<div class="fr">связанные: ${esc([...new Set(f.related)].join(", "))}</div>` : ""}
      ${f.source_ref ? `<a href="${esc(f.source_ref)}" target="_blank" rel="noopener">источник</a>` : ""}
    </div>`).join("") || `<p class="muted">Находок по этому POU нет.</p>`;
}

function renderLangs(res, beh) {
  const by = res.project.languages || {};
  const verified = (beh && beh.verified) || {};
  const rows = Object.keys(LANG_NOTE).map((l) => `
    <tr><td><b>${l}</b></td><td>${by[l] || 0}</td><td>${esc(LANG_NOTE[l])}</td><td>${esc(verified[l] || "—")}</td></tr>`).join("");
  $("#tab-langs").innerHTML = `<table><thead><tr><th>Язык</th><th>POU</th><th>Как переносится</th><th>Чем сверено</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="muted">«Трасса CODESYS Control Win» — выходы стенда в рантайме 3.5.17.30 совпали с понижением в симуляторе; IL импорт
    CODESYS 3.5.17.30 без опции «Enable IL» не принимает — сверено с собственным вычислителем.</p>`;
}

function chart(series, signal, kind) {
  // series: [{label, cls, points:[[t, v]]}] — ступенчатые линии
  const all = series.flatMap((s) => s.points);
  if (!all.length) return "";
  const tmax = Math.max(...all.map((p) => p[0])) || 1;
  const vals = all.map((p) => Number(p[1]));
  let vmin = Math.min(...vals), vmax = Math.max(...vals);
  if (vmin === vmax) { vmin -= 1; vmax += 1; }
  const W = 560, H = kind === "BOOL" ? 70 : 120, L = 36, R = 8, T = 8, B = 18;
  const x = (t) => L + (t / tmax) * (W - L - R);
  const y = (v) => T + (1 - (v - vmin) / (vmax - vmin)) * (H - T - B);
  const paths = series.map((s, i) => {
    let d = "";
    s.points.forEach(([t, v], k) => {
      const yy = y(Number(v)) + i * 2;
      d += k === 0 ? `M${x(t)},${yy}` : `H${x(t)}V${yy}`;
    });
    d += `H${W - R}`;
    return `<path d="${d}" class="${s.cls}" fill="none"/>`;
  }).join("");
  const ticks = [0, tmax / 2, tmax].map((t) => `<text x="${x(t)}" y="${H - 4}" class="ax" text-anchor="middle">${Math.round(t)} мс</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart"><text x="2" y="${T + 8}" class="ax">${esc(signal)}</text>${paths}${ticks}</svg>`;
}

function renderBehaviour(beh) {
  const el = $("#tab-behaviour");
  if (!beh) {
    el.innerHTML = `<p class="muted">Поведение показывается для примеров со сценариями (УДР-1, цепочка S7). Для своего проекта —
      <code>cds2ms simulate &lt;вход&gt; --pou … --scenario сценарий.csv --regime R2</code>.</p>`;
    return;
  }
  el.innerHTML = `<p class="muted">${esc(beh.note)}</p>` + beh.cases.map((c) => `
    <div class="beh">
      <h3>${esc(c.pou)} <span class="lang">${esc(c.language)}</span> <small>${esc(c.verified)}</small></h3>
      ${c.signals.map((s) => chart([
        ...(c.oracle ? [{ label: "CODESYS Control Win", cls: "s-oracle", points: c.oracle[s.name] || [] }] : []),
        { label: "CODESYS (модель, 10 мс)", cls: "s-cds", points: c.codesys[s.name] || [] },
        { label: "MasterPLC (модель, 100 мс)", cls: "s-ms", points: c.masterplc[s.name] || [] },
      ], s.name, s.type)).join("")}
      <div class="leg"><i class="s-oracle"></i>${c.oracle ? "трасса CODESYS Control Win · " : ""}<i class="s-cds"></i>CODESYS, 10 мс · <i class="s-ms"></i>MasterPLC, 100 мс</div>
      ${c.divergences.length ? `<ul class="div">${c.divergences.slice(0, 4).map((d) => `<li><b>${esc(d.rule)}</b> t=${d.t_ms} мс ${esc(d.signal)}: CODESYS ${esc(d.codesys)}, MasterPLC ${esc(d.masterplc)} — ${esc(d.explanation)}</li>`).join("")}</ul>` : `<p class="muted">Расхождений нет.</p>`}
    </div>`).join("");
}

function renderModel(model) {
  const el = $("#tab-model");
  const tasks = (model.tasks || []).map((t) => `<li>задача <b>${esc(t.name)}</b> · период ${esc(t.Period)} мс</li>`).join("");
  const disp = (model.dispatchers || []).map((d) => `<li>программа <b>${esc(d.name)}</b> (диспетчер, задача ${esc(d.TaskRef)})<ul>${(d.calls || []).map((c) => `<li>${esc(c)} — режим «По вызову»</li>`).join("")}</ul></li>`).join("");
  el.innerHTML = `<p class="warn">Предпросмотр по плану переноса, не снимок MasterSCADA: так дерево построит скрипт
    <code>script/BuildProject.cs</code> (проверен сборкой против MasterSCADA.Scripts.Model.dll 1.3.10, запуск — в среде разработки).</p>
    <ul class="mtree"><li>Система<ul><li>узел ПЛК <b>${esc(model.node)}</b><ul>${tasks}${disp}</ul></li></ul></li></ul>`;
}

function renderMatrix(rows) {
  $("#tab-matrix").innerHTML = `<table><thead><tr><th>Конструкция</th><th>Язык</th><th>Канал</th><th>Исход</th><th>Уверенность</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td>${esc(r.construct)}</td><td>${esc(r.language)}</td><td>${esc(r.channel)}</td><td><span class="badge ${worstClass(r.outcome)}">${OUT_RU[r.outcome] || esc(r.outcome)}</span></td><td><a href="${esc(r.source)}" target="_blank" rel="noopener">${esc(r.confidence)}</a></td></tr>`).join("")}
  </tbody></table>`;
}

function renderZip(res) {
  const el = $("#tab-zip");
  el.innerHTML = `<p><button id="dl" class="primary">Скачать ${esc(res.zip_name)}</button></p>
    <p class="muted">SHA-256: <code id="zip-sha">${esc(res.zip_sha256)}</code> · ${res.files.length} файлов (ZIP без сжатия, фиксированные даты — побайтно как у CLI).</p>
    <pre class="files">${esc(res.files.join("\n"))}</pre>`;
  $("#dl").onclick = () => {
    if (!res.zip && res.zip_url) {
      const a = document.createElement("a");
      a.href = res.zip_url;
      a.download = res.zip_name;
      a.click();
      return;
    }
    const bin = Uint8Array.from(atob(res.zip), (c) => c.charCodeAt(0));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([bin], { type: "application/zip" }));
    a.download = res.zip_name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
}

// ------------------------------------------------------------------ события

for (const b of document.querySelectorAll("#tabs button")) {
  b.onclick = () => {
    for (const x of document.querySelectorAll("#tabs button")) x.classList.toggle("on", x === b);
    for (const t of document.querySelectorAll(".tab")) t.hidden = t.id !== "tab-" + b.dataset.tab;
  };
}
$("#file").onchange = (e) => e.target.files[0] && onFile(e.target.files[0]);
const drop = $("#drop");
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
};

startWorker();
loadExamples();
