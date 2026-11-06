import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Columns3, Search, Inbox } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function EmptyState({ title = "Nothing here yet", hint, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center" data-testid="empty-state">
      <Inbox className="h-8 w-8 text-zinc-300" strokeWidth={1.5} />
      <p className="text-sm font-semibold text-zinc-800">{title}</p>
      {hint && <p className="max-w-sm text-xs text-zinc-500">{hint}</p>}
      {action}
    </div>
  );
}

const val = (row, c) => (c.value ? c.value(row) : row[c.key]);

export function DataTable({ columns, data, loading, onRowClick, testid = "table", toolbar, pageSize = 15, emptyTitle, emptyHint, searchPlaceholder = "Search…", rowClass }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState({ key: null, dir: 1 });
  const [page, setPage] = useState(0);
  const [hidden, setHidden] = useState(() => new Set(columns.filter((c) => c.hidden).map((c) => c.key)));

  const rows = useMemo(() => {
    let r = data || [];
    if (q) {
      const s = q.toLowerCase();
      r = r.filter((row) => columns.some((c) => String(val(row, c) ?? "").toLowerCase().includes(s)));
    }
    if (sort.key) {
      const c = columns.find((x) => x.key === sort.key);
      r = [...r].sort((a, b) => {
        const x = val(a, c), y = val(b, c);
        if (x === y) return 0;
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * sort.dir;
      });
    }
    return r;
  }, [data, q, sort, columns]);

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const cur = Math.min(page, pages - 1);
  const visible = columns.filter((c) => !hidden.has(c.key));
  const slice = rows.slice(cur * pageSize, cur * pageSize + pageSize);
  const toggleSort = (k) => setSort((s) => ({ key: k, dir: s.key === k ? -s.dir : 1 }));

  return (
    <div className="rounded-xl border border-zinc-200 bg-white" data-testid={testid}>
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 p-3">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-zinc-400" />
          <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder={searchPlaceholder} className="h-9 pl-8" data-testid={`${testid}-search`} />
        </div>
        {toolbar}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="ml-auto h-9" data-testid={`${testid}-columns-btn`}><Columns3 className="mr-1.5 h-4 w-4" />Columns</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-80 overflow-auto">
            <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {columns.map((c) => (
              <DropdownMenuCheckboxItem key={c.key} checked={!hidden.has(c.key)} onSelect={(e) => e.preventDefault()}
                onCheckedChange={() => setHidden((h) => { const n = new Set(h); n.has(c.key) ? n.delete(c.key) : n.add(c.key); return n; })}>
                {c.label}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-100 bg-zinc-50/60">
              {visible.map((c) => (
                <th key={c.key} onClick={() => c.sortable !== false && toggleSort(c.key)}
                  className={cn("whitespace-nowrap px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-zinc-500", c.sortable !== false && "cursor-pointer select-none hover:text-zinc-900")}>
                  <span className="inline-flex items-center gap-1">{c.label}{sort.key === c.key && (sort.dir > 0 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && [...Array(5)].map((_, i) => (
              <tr key={i}><td colSpan={visible.length} className="px-4 py-3"><Skeleton className="h-5 w-full" /></td></tr>
            ))}
            {!loading && slice.map((row, i) => (
              <tr key={row.id || i} onClick={() => onRowClick?.(row)} data-testid={`${testid}-row-${row.code || row.id || i}`}
                className={cn("border-b border-zinc-100 transition-colors last:border-0", onRowClick && "cursor-pointer hover:bg-zinc-50", rowClass?.(row))}>
                {visible.map((c) => (
                  <td key={c.key} className={cn("px-4 py-3 align-middle text-zinc-700", c.className)}>{c.render ? c.render(row) : (val(row, c) ?? <span className="text-zinc-300">—</span>)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !rows.length && <EmptyState title={emptyTitle || (q ? "No matching records" : "No records yet")} hint={emptyHint} />}
      </div>
      <div className="flex items-center justify-between border-t border-zinc-100 px-4 py-2.5 text-xs text-zinc-500">
        <span data-testid={`${testid}-count`}>{rows.length} record{rows.length === 1 ? "" : "s"}</span>
        <div className="flex items-center gap-2">
          <span>Page {cur + 1} of {pages}</span>
          <Button variant="outline" size="icon" className="h-7 w-7" disabled={cur === 0} onClick={() => setPage(cur - 1)} data-testid={`${testid}-prev`}><ChevronLeft className="h-4 w-4" /></Button>
          <Button variant="outline" size="icon" className="h-7 w-7" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)} data-testid={`${testid}-next`}><ChevronRight className="h-4 w-4" /></Button>
        </div>
      </div>
    </div>
  );
}
