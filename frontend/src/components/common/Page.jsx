import { cn } from "@/lib/utils";

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 fade-up">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
        <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink sm:text-[30px]" data-testid="page-title">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-[14px] text-subtle">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** KPI card: compact label, prominent tabular value, optional icon and supporting text. */
export function Kpi({ label, value, hint, testid, accent, icon: Icon }) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-line bg-white p-4 shadow-[0_1px_2px_rgba(32,36,43,0.04)] transition-[border-color,box-shadow] duration-200 hover:border-[#D5DBE3] hover:shadow-[0_8px_24px_-16px_rgba(34,101,200,0.35)] sm:p-5" data-testid={testid}>
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-[13px] font-medium leading-snug text-subtle">{label}</p>
        {Icon && <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[9px] bg-brand-pale text-brand-deep"><Icon className="h-4 w-4" strokeWidth={1.8} /></span>}
      </div>
      <p className={cn("mt-1 whitespace-nowrap text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink tabular-nums", accent)}>{value}</p>
      {hint && <p className="mt-0.5 text-[12px] leading-snug text-subtle">{hint}</p>}
    </div>
  );
}

export function Section({ title, actions, children, className, testid }) {
  return (
    <section className={cn("rounded-2xl border border-line bg-white shadow-[0_1px_2px_rgba(32,36,43,0.04)]", className)} data-testid={testid}>
      {title && (
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-0 pt-5 sm:px-6">
          <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
          {actions}
        </div>
      )}
      <div className="p-5 sm:px-6">{children}</div>
    </section>
  );
}

export function Info({ label, children }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <div className="mt-1 text-sm text-ink">{children ?? <span className="text-[#C6CDD6]">—</span>}</div>
    </div>
  );
}

export function Timeline({ items }) {
  if (!items?.length) return <p className="text-sm text-[#9AA2AE]">No history yet.</p>;
  return (
    <ol className="relative space-y-4 border-l border-line pl-5" data-testid="timeline">
      {items.map((i, k) => (
        <li key={k} className="relative">
          <span className="absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand-deep" />
          <p className="text-sm font-medium text-ink">{i.title}</p>
          {i.details && <p className="text-xs text-[#4B5361]">{i.details}</p>}
          <p className="text-[11px] text-[#9AA2AE]">{i.meta}</p>
        </li>
      ))}
    </ol>
  );
}
