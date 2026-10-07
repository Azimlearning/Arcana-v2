// The fixed template of a VerifiedLab (P4 V6, D-36): the document the sandboxed iframe shows.
//
// WE wrote this; it is never generated. The only generated part is the verified function `lab(p)`, whose text the server verified and whose
// SHA-256 the block carries. This module builds the iframe's `srcdoc` from the template plus that function and refuses to build one unless
// the function's hash matches, the template version is the one this client holds, and the source holds no markup sequence that could close
// the inline <script> (the checker already forbids them; this is the second line).
//
// The iframe is rendered with `sandbox="allow-scripts"` and no other token (so an opaque origin: no cookies, storage, parent access, forms,
// popups or navigation), and the document carries a Content-Security-Policy that forbids every network and resource load. Libraries would
// come from a local vendor directory; none is used, and a URL or an unlisted library has no way in (the template loads nothing).

import type { VerifiedLabData } from "@arcana/schema";

/** Bumped when the template changes in a way that could change what a verified function does. A block for another version is refused. */
export const LAB_TEMPLATE_VERSION = 2;

/** The attribute value the iframe gets: exactly this and nothing else. A test pins it. */
export const LAB_SANDBOX = "allow-scripts";

export const LAB_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";

const MARKUP = /<!--|-->|<\/script/i;

export type FrameResult = { ok: true; srcdoc: string } | { ok: false; reason: string };

/** The hex SHA-256 of `text` (UTF-8). */
export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Everything the template needs about the lab, as data; embedded as JSON with `<` escaped so it cannot close the script element. */
function config(data: VerifiedLabData): string {
  const cfg = {
    title: data.title,
    parameters: data.parameters,
    sweep: data.sweep,
    gridSteps: data.gridSteps,
    outputLabel: data.outputLabel,
  };
  const separators = new RegExp("[" + String.fromCharCode(0x2028) + String.fromCharCode(0x2029) + "]", "g");
  const BS = String.fromCharCode(92); // a backslash
  return JSON.stringify(cfg)
    .replace(/</g, `${BS}u003c`)
    .replace(separators, (c) => `${BS}u${c.charCodeAt(0).toString(16)}`);
}

const STYLE = `
  :root { color-scheme: light; }
  body { margin: 0; padding: 12px; font: 14px/1.4 system-ui, sans-serif; color: #1c1917; background: #fff; }
  .row { display: grid; grid-template-columns: 11rem 1fr 4.5rem; gap: 8px; align-items: center; margin: 4px 0; }
  label { font-weight: 500; }
  input[type=range] { width: 100%; }
  output { font-variant-numeric: tabular-nums; text-align: right; }
  #readout { margin: 10px 0 6px; font-weight: 600; }
  canvas { width: 100%; height: 220px; border: 1px solid #d6d3d1; border-radius: 6px; display: block; }
  details { margin-top: 8px; }
  table { border-collapse: collapse; font-size: 12px; }
  td, th { border: 1px solid #e7e5e4; padding: 2px 8px; text-align: right; }
`;

/** The host code: sliders for the declared parameters, the function's value at them, a plot of the value as the swept parameter runs across
 * its range, and a table of the same numbers. It reads `lab` (the verified function, defined above it) and CONFIG; it writes only text. */
const HOST = `
(function () {
  var cfg = CONFIG;
  var values = {};
  var app = document.getElementById("app");
  var title = document.createElement("h2");
  title.textContent = cfg.title;
  title.style.cssText = "font-size:15px;margin:0 0 8px";
  app.appendChild(title);
  var group = document.createElement("div");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "Parameters");
  app.appendChild(group);
  var readout = document.createElement("p");
  readout.id = "readout";
  readout.setAttribute("role", "status");
  readout.setAttribute("aria-live", "polite");
  app.appendChild(readout);
  var canvas = document.createElement("canvas");
  canvas.width = 640; canvas.height = 220;
  canvas.setAttribute("role", "img");
  app.appendChild(canvas);
  var details = document.createElement("details");
  var summary = document.createElement("summary");
  summary.textContent = "Values as a table";
  details.appendChild(summary);
  var table = document.createElement("table");
  details.appendChild(table);
  app.appendChild(details);

  function call(p) {
    var frozen = Object.freeze(Object.assign(Object.create(null), p));
    var out = lab(frozen);
    return typeof out === "number" && isFinite(out) ? out : null;
  }
  // The only values the function is ever called with: grid points. This is the expression the verifier uses to build the grid it ran in full.
  function at(prm, k) { return prm.min + (prm.max - prm.min) * k / cfg.gridSteps; }
  function fmt(x) { return Math.abs(x) >= 1000 || (x !== 0 && Math.abs(x) < 0.001) ? x.toExponential(3) : String(Math.round(x * 10000) / 10000); }

  var outputs = [];
  cfg.parameters.forEach(function (prm) {
    var k0 = Math.round((prm.default - prm.min) / (prm.max - prm.min) * cfg.gridSteps);
    values[prm.name] = at(prm, k0);
    var row = document.createElement("div");
    row.className = "row";
    var lbl = document.createElement("label");
    lbl.htmlFor = "p-" + prm.name;
    lbl.textContent = prm.label + (prm.unit ? " (" + prm.unit + ")" : "");
    var input = document.createElement("input");
    input.type = "range"; input.id = "p-" + prm.name;
    input.min = "0"; input.max = String(cfg.gridSteps); input.step = "1"; input.value = String(k0);
    input.setAttribute("aria-valuetext", fmt(values[prm.name]));
    var out = document.createElement("output");
    out.htmlFor = input.id; out.textContent = fmt(values[prm.name]);
    input.addEventListener("input", function () { values[prm.name] = at(prm, Number(input.value)); out.textContent = fmt(values[prm.name]); input.setAttribute("aria-valuetext", fmt(values[prm.name])); draw(); });
    row.appendChild(lbl); row.appendChild(input); row.appendChild(out);
    group.appendChild(row);
    outputs.push(out);
  });

  function draw() {
    var swept = cfg.parameters.filter(function (q) { return q.name === cfg.sweep; })[0];
    var here = call(values);
    readout.textContent = here === null ? "The function gave no number here." : cfg.outputLabel + " = " + fmt(here);
    var xs = [], ys = [];
    for (var i = 0; i <= cfg.gridSteps; i++) {
      var x = at(swept, i);
      var p = Object.assign({}, values); p[cfg.sweep] = x;
      var y = call(p);
      if (y !== null) { xs.push(x); ys.push(y); }
    }
    var ctx = canvas.getContext("2d");
    var W = canvas.width, H = canvas.height, pad = 34;
    ctx.clearRect(0, 0, W, H);
    ctx.font = "11px system-ui, sans-serif"; ctx.fillStyle = "#57534e"; ctx.strokeStyle = "#a8a29e";
    if (ys.length > 1) {
      var lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
      if (hi === lo) { hi = lo + 1; }
      var sx = function (x) { return pad + (x - swept.min) / (swept.max - swept.min) * (W - 2 * pad); };
      var sy = function (y) { return H - pad - (y - lo) / (hi - lo) * (H - 2 * pad); };
      ctx.beginPath(); ctx.moveTo(pad, pad / 2); ctx.lineTo(pad, H - pad); ctx.lineTo(W - pad / 2, H - pad); ctx.stroke();
      ctx.fillText(fmt(hi), 2, pad / 2 + 8); ctx.fillText(fmt(lo), 2, H - pad);
      ctx.fillText(fmt(swept.min), pad, H - pad + 14); ctx.fillText(fmt(swept.max), W - pad - 24, H - pad + 14);
      ctx.fillText(swept.label, W / 2 - 60, H - 4);
      ctx.strokeStyle = "#0f766e"; ctx.lineWidth = 2; ctx.beginPath();
      ys.forEach(function (y, k) { if (k === 0) { ctx.moveTo(sx(xs[k]), sy(y)); } else { ctx.lineTo(sx(xs[k]), sy(y)); } });
      ctx.stroke();
      if (here !== null) { ctx.fillStyle = "#b45309"; ctx.beginPath(); ctx.arc(sx(values[cfg.sweep]), sy(here), 5, 0, 6.2832); ctx.fill(); }
    }
    canvas.setAttribute("aria-label", "Plot of " + cfg.outputLabel + " as " + swept.label + " runs from " + fmt(swept.min) + " to " + fmt(swept.max));
    table.textContent = "";
    var head = document.createElement("tr");
    [swept.name, cfg.outputLabel].forEach(function (h) { var th = document.createElement("th"); th.textContent = h; head.appendChild(th); });
    table.appendChild(head);
    var step = Math.max(1, Math.floor(xs.length / 16));
    for (var j = 0; j < xs.length; j += step) {
      var tr = document.createElement("tr");
      [xs[j], ys[j]].forEach(function (v) { var td = document.createElement("td"); td.textContent = fmt(v); tr.appendChild(td); });
      table.appendChild(tr);
    }
  }
  draw();
})();
`;

/** The iframe's `srcdoc` for a lab, or the reason it must not be built. Checks, in order: the template version, a markup sequence in the source, the source's
 * SHA-256 against the block's. */
export async function buildFrame(data: VerifiedLabData): Promise<FrameResult> {
  if (data.templateVersion !== LAB_TEMPLATE_VERSION) {
    return { ok: false, reason: "This lab was verified for another version of the lab template, so it is not shown." };
  }
  if (MARKUP.test(data.source)) {
    return { ok: false, reason: "The lab's source holds a markup sequence, so it is not shown." };
  }
  let actual: string;
  try {
    actual = await sha256Hex(data.source);
  } catch {
    return { ok: false, reason: "This browser cannot check the lab's hash, so it is not shown." };
  }
  if (actual !== data.sourceSha256) {
    return { ok: false, reason: "The lab's code does not match the hash the server verified, so it is not shown." };
  }
  const srcdoc =
    `<!doctype html><html lang="en"><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${LAB_CSP}">` +
    `<title>${"Lab"}</title><style>${STYLE}</style></head><body><div id="app"></div>` +
    `<script>\n"use strict";\nvar CONFIG = ${config(data)};\n${data.source}\n${HOST}\n</script></body></html>`;
  return { ok: true, srcdoc };
}
