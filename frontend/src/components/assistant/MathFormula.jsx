import { Fragment } from "react";

/*
 * Small, dependency-free renderer for the LaTeX subset the assistant uses in $$ ... $$ lines:
 * \text{..}, \frac{a}{b}, \sum, \times, \div, \approx, \cdot, \le, \ge, \neq, \pm, sub/superscripts, { } groups.
 * It builds React elements (never HTML strings), so model output can't inject markup.
 */
const SYMBOLS = {
  sum: "Σ", times: "×", div: "÷", approx: "≈", cdot: "·", le: "≤", leq: "≤", ge: "≥", geq: "≥", neq: "≠", ne: "≠",
  pm: "±", rightarrow: "→", to: "→", Rightarrow: "⇒", infty: "∞", Delta: "Δ", delta: "δ", mu: "μ", sigma: "σ", percent: "%",
  "%": "%", "&": "&", "#": "#", "$": "$", "_": "_", "{": "{", "}": "}", ldots: "…", dots: "…", cdots: "⋯", minus: "−",
};
const SPACES = { ",": " ", ";": " ", ":": " ", " ": " ", quad: "  ", qquad: "    ", "!": "" };
const OPERATORS = new Set(["=", "+", "−", "-", "×", "÷", "≈", "≤", "≥", "≠", "±", "→", "⇒", "·"]);
const TEXT_CMDS = new Set(["text", "mathrm", "textrm", "textbf", "mathbf", "operatorname", "textit", "mathit"]);

function parse(src) {
  let i = 0;
  const readGroup = () => {
    while (src[i] === " ") i += 1;
    if (src[i] !== "{") { const ch = src[i] ?? ""; i += 1; return ch === "\\" ? [readCommand()] : [ch]; }
    i += 1;
    const out = parseSeq("}");
    i += 1;
    return out;
  };
  const readRaw = () => {  // raw text inside \text{...}
    while (src[i] === " ") i += 1;
    if (src[i] !== "{") return "";
    let depth = 0, s = "";
    for (i += 1; i < src.length; i += 1) {
      const c = src[i];
      if (c === "{") depth += 1;
      if (c === "}") { if (depth === 0) { i += 1; break; } depth -= 1; }
      s += c === "\\" && /[%&#$_{} ]/.test(src[i + 1] || "") ? "" : c;
    }
    return s;
  };
  function readCommand() {
    let name = "";
    if (/[a-zA-Z]/.test(src[i] || "")) { while (/[a-zA-Z]/.test(src[i] || "")) { name += src[i]; i += 1; } }
    else { name = src[i] ?? ""; i += 1; }
    if (TEXT_CMDS.has(name)) return { t: "text", v: readRaw(), bold: name.includes("bf") };
    if (name === "frac" || name === "dfrac" || name === "tfrac") return { t: "frac", n: readGroup(), d: readGroup() };
    if (name === "sqrt") return { t: "sqrt", v: readGroup() };
    if (name === "left" || name === "right") { const c = src[i]; i += 1; return c === "." ? "" : c; }
    if (name in SPACES) return { t: "space", v: SPACES[name] };
    if (name in SYMBOLS) return SYMBOLS[name];
    return name;  // unknown command: show its name rather than failing
  }
  function parseSeq(stop) {
    const out = [];
    while (i < src.length && src[i] !== stop) {
      const c = src[i];
      if (c === "\\") { i += 1; out.push(readCommand()); }
      else if (c === "{") out.push({ t: "group", v: readGroup() });
      else if (c === "_" || c === "^") { i += 1; out.push({ t: c === "_" ? "sub" : "sup", v: readGroup() }); }
      else { out.push(c === "-" ? "−" : c === "*" ? "×" : c); i += 1; }
    }
    return out;
  }
  return parseSeq(null);
}

function Nodes({ nodes }) {
  const out = [];
  let buf = "";
  const flush = (k) => { if (buf) { out.push(<Fragment key={`s${k}`}>{buf}</Fragment>); buf = ""; } };
  nodes.forEach((n, k) => {
    if (typeof n === "string") {
      if (OPERATORS.has(n)) { flush(k); out.push(<span key={k} className="mx-[0.28em] text-[#4B5361]">{n}</span>); }
      else if (n !== " ") buf += n;
      else if (buf && !buf.endsWith(" ")) buf += " ";  // keep word spacing if the model wrote names without \text{}
      return;
    }
    flush(k);
    if (n.t === "text") out.push(<span key={k} className={n.bold ? "font-semibold" : undefined}>{n.v}</span>);
    else if (n.t === "space") out.push(<Fragment key={k}>{n.v}</Fragment>);
    else if (n.t === "group") out.push(<Nodes key={k} nodes={n.v} />);
    else if (n.t === "sub") out.push(<sub key={k} className="text-[0.72em]"><Nodes nodes={n.v} /></sub>);
    else if (n.t === "sup") out.push(<sup key={k} className="text-[0.72em]"><Nodes nodes={n.v} /></sup>);
    else if (n.t === "sqrt") out.push(<span key={k}>√<span className="border-t border-current pl-0.5"><Nodes nodes={n.v} /></span></span>);
    else if (n.t === "frac") {
      out.push(
        <span key={k} className="mx-[0.15em] inline-flex flex-col items-center align-middle leading-tight">
          <span className="border-b border-ink px-1 pb-0.5"><Nodes nodes={n.n} /></span>
          <span className="px-1 pt-0.5"><Nodes nodes={n.d} /></span>
        </span>);
    }
  });
  flush("end");
  return <>{out}</>;
}

export function MathFormula({ tex }) {
  let nodes;
  try { nodes = parse(tex.trim()); } catch { nodes = null; }
  return (
    <div className="my-2 overflow-x-auto rounded-[10px] border border-[#DCEBFB] bg-[#F6FAFE] px-3 py-2.5 text-center" data-testid="assistant-formula" role="math" aria-label={tex}>
      <span className="inline-flex flex-wrap items-center justify-center whitespace-nowrap font-[450] text-[14px] text-ink">
        {nodes ? <Nodes nodes={nodes} /> : tex}
      </span>
    </div>
  );
}

/** Splits text into plain parts and formula parts. Accepts $$...$$ and \[...\] delimiters. */
export function splitFormulas(text) {
  const norm = text.replace(/\\\[([\s\S]+?)\\\]/g, (_, f) => `$$${f}$$`);
  const parts = norm.split(/\$\$([\s\S]+?)\$\$/g);
  return parts.map((v, idx) => ({ formula: idx % 2 === 1, v })).filter((p) => p.v.trim() || p.formula);
}
