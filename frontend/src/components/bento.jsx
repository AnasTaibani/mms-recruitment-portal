import { useEffect, useState } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { BRAND, NEUTRAL, STATUS } from "@/lib/brand";

/* Bento dashboard primitives in the MMS design system (white cards, brand-blue accents, IBM Plex Sans). */
export const TONE = { up: STATUS.positive, down: STATUS.negative, warn: STATUS.warning, muted: NEUTRAL.grey };
// trend series: primary → secondary → supporting; Joined (a positive outcome) in muted green
export const SERIES = { added: BRAND.deep, shortlisted: BRAND.royal, interviews_completed: BRAND.blue, offers_released: BRAND.sky, joined: STATUS.positive };
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

/** Animated number (ease-out), respects reduced motion. */
export function CountUp({ value, format = (v) => Math.round(v).toLocaleString("en-IN"), duration = 1000, className, testid }) {
  const reduced = useReducedMotion();
  const [v, setV] = useState(reduced || value == null ? value : 0);
  useEffect(() => {
    if (value == null || reduced) { setV(value); return undefined; }
    let raf = 0;
    const t0 = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / duration);
      setV(value * (1 - Math.pow(1 - p, 4)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, reduced, duration]);
  return <span className={cn("tabular-nums", className)} data-testid={testid}>{value == null ? "—" : format(v)}</span>;
}

/** Card shell: white surface, light-grey border, 16px radius, minimal shadow, 15px semibold heading. */
export function Tile({ title, info, action, className, children, testid }) {
  return (
    <section data-testid={testid}
      className={cn("relative flex min-w-0 flex-col rounded-2xl border border-line bg-white p-5 text-ink shadow-[0_1px_2px_rgba(32,36,43,0.04)] transition-[box-shadow,border-color] duration-200 hover:border-[#DCE2E9] hover:shadow-[0_10px_28px_-20px_rgba(34,101,200,0.45)] sm:p-6", className)}>
      {(title || action) && (
        <header className="mb-4 flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2">
          {title && (
            <h3 className="flex min-w-0 items-center gap-1.5 text-[16px] font-semibold text-ink">
              {title}
              {info && <span title={info} className="cursor-help text-[#AEB5BF] hover:text-brand-royal"><Info className="h-4 w-4" strokeWidth={1.8} /></span>}
            </h3>
          )}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/** Segmented toggle (Weekly / Monthly etc.): pale-blue selected state with deep-blue text. */
export function Pills({ value, options, onChange, label, testid }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap rounded-[10px] border border-line bg-white p-0.5" data-testid={testid}>
      {options.map((o) => {
        const [v, l] = Array.isArray(o) ? o : [o, o];
        return (
          <button key={v} type="button" role="radio" aria-checked={v === value} onClick={() => onChange(v)} data-testid={testid ? `${testid}-${v}` : undefined}
            className={cn("rounded-[8px] px-3 py-1 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-royal/40",
              v === value ? "bg-brand-pale text-brand-deep" : "text-subtle hover:text-ink")}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

/** Change vs the previous period. null → "—" (no comparable data); never invented. */
export function Delta({ pct, className }) {
  if (pct === null || pct === undefined) return <span className={cn("text-[12px] text-[#AEB5BF]", className)} title="No data in the previous period to compare with">—</span>;
  const up = pct > 0, flat = pct === 0;
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-[12px] font-medium tabular-nums", className)}
      style={{ color: flat ? NEUTRAL.subtle : up ? STATUS.positive : STATUS.negative }}>
      {flat ? "—" : up ? "↑" : "↓"} {flat ? "0%" : `${up ? "+" : "−"}${Math.abs(pct).toFixed(0)}%`}
    </span>
  );
}

/** Horizontal segmented bar with hover focus. */
export function SegBar({ items, height = 32, colorOf, onSelect, testid }) {
  const mounted = useMounted();
  const [hover, setHover] = useState(null);
  const total = items.reduce((s, x) => s + x.value, 0);
  if (!total) return null;
  return (
    <div className="flex gap-1" style={{ height }} onPointerLeave={() => setHover(null)} data-testid={testid}>
      {items.filter((x) => x.value > 0).map((x, i) => (
        <button key={x.key} type="button" title={`${x.label}: ${x.value}`} aria-label={`${x.label}: ${x.value}`}
          onPointerEnter={() => setHover(x.key)} onFocus={() => setHover(x.key)} onClick={() => onSelect?.(x)}
          className={cn("min-w-[6px] rounded-[6px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-royal/40", onSelect ? "cursor-pointer" : "cursor-default")}
          style={{ flexBasis: mounted ? `${(x.value / total) * 100}%` : `${100 / items.length}%`, flexGrow: 0, flexShrink: 1,
            background: colorOf(x, i), opacity: hover === null || hover === x.key ? 1 : 0.35,
            transition: `flex-basis 800ms ${EASE} ${100 + i * 40}ms, opacity 180ms ease` }} />
      ))}
    </div>
  );
}

export function ChartTip({ active, payload, label, labelFormat = (l) => l, valueFormat = (v) => v }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[10px] border border-line bg-white px-3 py-2 text-[12px] shadow-[0_12px_30px_-14px_rgba(32,36,43,0.35)]">
      <p className="mb-1 font-medium text-ink">{labelFormat(label)}</p>
      {payload.filter((p) => p.value !== null && p.value !== undefined).map((p) => (
        <p key={p.dataKey} className="flex items-center justify-between gap-5">
          <span className="flex items-center gap-1.5 text-subtle"><i className="h-2 w-2 rounded-full" style={{ background: p.color || p.stroke || p.payload?.fill }} />{p.name}</span>
          <b className="font-semibold tabular-nums text-ink">{valueFormat(p.value, p)}</b>
        </p>
      ))}
    </div>
  );
}

export function Unavailable({ children = "Not enough data for this period", className }) {
  return <div className={cn("flex flex-1 items-center justify-center rounded-xl border border-dashed border-line bg-canvas/60 px-4 py-8 text-center text-[13px] text-subtle", className)}>{children}</div>;
}

export const bucketLabel = (k, gran) => {
  if (!k) return "";
  if (gran === "month") return new Date(`${k}-01T00:00:00`).toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
  return new Date(`${k}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
};
