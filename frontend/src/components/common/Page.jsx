import { cn } from "@/lib/utils";

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4 fade-up">
      <div>
        {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-[-0.02em] text-[#18181B] sm:text-[30px]" data-testid="page-title">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-zinc-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Kpi({ label, value, hint, testid, accent }) {
  return (
    <div className="group relative overflow-hidden rounded-[20px] border border-[#E7E5E4] bg-white p-4 shadow-[0_1px_2px_rgba(24,24,27,0.04)] transition duration-300 hover:-translate-y-0.5 hover:border-[#D6D3D1] hover:shadow-[0_14px_30px_-18px_rgba(24,24,27,0.35)]" data-testid={testid}>
      <p className="text-[12px] font-medium text-zinc-500">{label}</p>
      <p className={cn("mt-2 font-mono text-[26px] font-semibold leading-none tracking-[-0.03em] text-[#18181B] tabular-nums", accent)}>{value}</p>
      {hint && <p className="mt-1 text-[11px] text-zinc-400">{hint}</p>}
    </div>
  );
}

export function Section({ title, actions, children, className, testid }) {
  return (
    <section className={cn("rounded-[22px] border border-[#E7E5E4] bg-white shadow-[0_1px_2px_rgba(24,24,27,0.04)]", className)} data-testid={testid}>
      {title && (
        <div className="flex items-center justify-between gap-3 px-5 pb-1 pt-4">
          <h3 className="text-[13px] font-medium text-zinc-500">{title}</h3>
          {actions}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Info({ label, children }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <div className="mt-1 text-sm text-zinc-800">{children ?? <span className="text-zinc-300">—</span>}</div>
    </div>
  );
}

export function Timeline({ items }) {
  if (!items?.length) return <p className="text-sm text-zinc-400">No history yet.</p>;
  return (
    <ol className="relative space-y-4 border-l border-zinc-200 pl-5" data-testid="timeline">
      {items.map((i, k) => (
        <li key={k} className="relative">
          <span className="absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-[#18181B]" />
          <p className="text-sm font-medium text-zinc-900">{i.title}</p>
          {i.details && <p className="text-xs text-zinc-600">{i.details}</p>}
          <p className="text-[11px] text-zinc-400">{i.meta}</p>
        </li>
      ))}
    </ol>
  );
}
