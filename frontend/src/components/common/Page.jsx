import { cn } from "@/lib/utils";

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4 fade-up">
      <div>
        {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
        <h1 className="text-2xl font-bold tracking-tight text-[#0B1530] sm:text-3xl" data-testid="page-title">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-zinc-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Kpi({ label, value, hint, testid, accent }) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-[#DCE7F7] bg-white p-4 shadow-[0_1px_2px_rgba(11,21,48,0.04)] transition hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-12px_rgba(30,99,206,0.35)]" data-testid={testid}>
      <span className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#A3D3FA] via-[#67B3F2] to-[#1E63CE] opacity-0 transition group-hover:opacity-100" />
      <p className="eyebrow">{label}</p>
      <p className={cn("mt-2 text-2xl font-extrabold tracking-tight text-[#0B1530]", accent)}>{value}</p>
      {hint && <p className="mt-1 text-[11px] text-zinc-400">{hint}</p>}
    </div>
  );
}

export function Section({ title, actions, children, className, testid }) {
  return (
    <section className={cn("rounded-2xl border border-[#DCE7F7] bg-white shadow-[0_1px_2px_rgba(11,21,48,0.04)]", className)} data-testid={testid}>
      {title && (
        <div className="flex items-center justify-between border-b border-[#EEF3FB] px-5 py-3.5">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-[#0B1530]">
            <span className="h-4 w-1 rounded-full bg-gradient-to-b from-[#67B3F2] to-[#1E63CE]" />{title}
          </h3>
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
          <span className="absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-[#1E63CE]" />
          <p className="text-sm font-medium text-zinc-900">{i.title}</p>
          {i.details && <p className="text-xs text-zinc-600">{i.details}</p>}
          <p className="text-[11px] text-zinc-400">{i.meta}</p>
        </li>
      ))}
    </ol>
  );
}
