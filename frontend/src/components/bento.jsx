import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/* Bento dashboard primitives — neutral palette (matte black / off-white / greys), colour only for outcomes. */
export const INK = "#18181B";
export const TONE = { up: "#3F7D58", down: "#B4534B", warn: "#B7791F", muted: "#A8A29E" };
export const SERIES = { added: "#18181B", shortlisted: "#78716C", interviews_completed: "#A8A29E", offers_released: "#B7791F", joined: "#3F7D58" };
export const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";

export function useReducedMotion() {
  const [r, setR] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return undefined;
    const u = () => setR(mq.matches);
    u();
    mq.addEventListener?.("change", u);
    return () => mq.removeEventListener?.("change", u);
  }, []);
  return r;
}

export function useMounted() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setOn(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return on;
}

/** Animated number (ease-out), respects reduced motion. `format` turns the number into display text. */
export function CountUp({ value, format = (v) => Math.round(v).toLocaleString("en-IN"), duration = 1100, className, testid }) {
  const reduced = useReducedMotion();
  const [v, setV] = useState(reduced || value == null ? value : 0);
  useEffect(() => {
    if (value == null || reduced) { setV(value); return undefined; }
    let raf = 0;
    const from = 0;
    const t0 = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / duration);
      setV(from + (value - from) * (1 - Math.pow(1 - p, 4)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, reduced, duration]);
  return <span className={cn("tabular-nums", className)} data-testid={testid}>{value == null ? "—" : format(v)}</span>;
}

export function Tile({ title, action, className, children, testid, pad = true, href }) {
  const body = (
    <section data-testid={testid}
      className={cn("group/tile relative flex min-w-0 flex-col overflow-hidden rounded-[24px] border border-[#E7E5E4] bg-white text-[#18181B] shadow-[0_1px_2px_rgba(24,24,27,0.04)] transition-[box-shadow,border-color] duration-300 hover:border-[#D6D3D1] hover:shadow-[0_18px_40px_-28px_rgba(24,24,27,0.45)]",
        pad && "p-5", className)}>
      {(title || action) && (
        <header className="mb-4 flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2">
          {title && <h3 className="min-w-0 text-[13px] font-medium text-zinc-500">{title}</h3>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
  return href ? <Link to={href} className="contents">{body}</Link> : body;
}

export function Pills({ value, options, onChange, label, testid, size = "sm" }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap rounded-full border border-[#E7E5E4] bg-white p-0.5" data-testid={testid}>
      {options.map((o) => {
        const [v, l] = Array.isArray(o) ? o : [o, o];
        return (
          <button key={v} type="button" role="radio" aria-checked={v === value} onClick={() => onChange(v)} data-testid={testid ? `${testid}-${v}` : undefined}
            className={cn("rounded-full font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400",
              size === "sm" ? "px-2.5 py-1 font-mono text-[11px]" : "px-3.5 py-1.5 text-[12.5px]",
              v === value ? "bg-[#18181B] text-white" : "text-zinc-500 hover:text-[#18181B]")}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

/** Change vs the previous period. null → "—" (no comparable data); never invented. */
export function Delta({ pct, className }) {
  if (pct === null || pct === undefined) return <span className={cn("font-mono text-[11px] text-zinc-400", className)} title="No data in the previous period to compare with">—</span>;
  const up = pct >= 0;
  return (
    <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums", className)}
      style={{ color: up ? TONE.up : TONE.down, background: up ? "rgba(63,125,88,0.09)" : "rgba(180,83,75,0.09)" }}>
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

/** Horizontal segmented bar with hover focus (like the reference's allocation bar). */
export function SegBar({ items, height = 36, colorOf, onSelect, testid }) {
  const mounted = useMounted();
  const [hover, setHover] = useState(null);
  const total = items.reduce((s, x) => s + x.value, 0);
  if (!total) return null;
  return (
    <div className="flex gap-1" style={{ height }} onPointerLeave={() => setHover(null)} data-testid={testid}>
      {items.filter((x) => x.value > 0).map((x, i) => (
        <button key={x.key} type="button" title={`${x.label}: ${x.value}`} aria-label={`${x.label}: ${x.value}`}
          onPointerEnter={() => setHover(x.key)} onFocus={() => setHover(x.key)} onClick={() => onSelect?.(x)}
          className={cn("min-w-[6px] rounded-[8px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400", onSelect ? "cursor-pointer" : "cursor-default")}
          style={{ flexBasis: mounted ? `${(x.value / total) * 100}%` : `${100 / items.length}%`, flexGrow: 0, flexShrink: 1,
            background: colorOf(x, i), opacity: hover === null || hover === x.key ? 1 : 0.3,
            transition: `flex-basis 900ms ${EASE} ${120 + i * 50}ms, opacity 200ms ease` }} />
      ))}
    </div>
  );
}

export function ChartTip({ active, payload, label, labelFormat = (l) => l, valueFormat = (v) => v }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-[#E7E5E4] bg-white/95 px-3 py-2 text-xs shadow-[0_12px_30px_-16px_rgba(24,24,27,0.5)] backdrop-blur">
      <p className="mb-1 font-mono text-[11px] text-zinc-500">{labelFormat(label)}</p>
      {payload.filter((p) => p.value !== null && p.value !== undefined).map((p) => (
        <p key={p.dataKey} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-zinc-600"><i className="h-2 w-2 rounded-full" style={{ background: p.color || p.stroke }} />{p.name}</span>
          <b className="font-mono tabular-nums text-[#18181B]">{valueFormat(p.value, p)}</b>
        </p>
      ))}
    </div>
  );
}

export function Unavailable({ children = "Not enough data for this period", className }) {
  return <div className={cn("flex flex-1 items-center justify-center rounded-2xl border border-dashed border-[#E7E5E4] px-4 py-8 text-center text-xs text-zinc-400", className)}>{children}</div>;
}

export const bucketLabel = (k, gran) => {
  if (!k) return "";
  if (gran === "month") return new Date(`${k}-01T00:00:00`).toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
  return new Date(`${k}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
};
