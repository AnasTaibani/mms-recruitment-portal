import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

const NONE = "__none";

export function SelectField({ value, onChange, options, placeholder = "Select…", testid, allowNone = true, className }) {
  return (
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? null : v)}>
      <SelectTrigger className={cn("h-9", className)} data-testid={testid}><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent className="max-h-72">
        {allowNone && <SelectItem value={NONE}>{placeholder}</SelectItem>}
        {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

export function MultiSelect({ value = [], onChange, options, placeholder = "Select…", testid }) {
  const [q, setQ] = useState("");
  const shown = options.filter((o) => o.label.toLowerCase().includes(q.toLowerCase()));
  const labels = options.filter((o) => value.includes(o.value)).map((o) => o.label);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" className="h-auto min-h-9 w-full justify-between font-normal" data-testid={testid}>
          <span className="truncate text-left">{labels.length ? labels.join(", ") : <span className="text-zinc-400">{placeholder}</span>}</span>
          <ChevronsUpDown className="h-4 w-4 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-2" align="start">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" className="mb-2 h-8" />
        <div className="max-h-60 overflow-auto">
          {shown.map((o) => {
            const on = value.includes(o.value);
            return (
              <button type="button" key={o.value} data-testid={`${testid}-opt-${o.label}`} onClick={() => onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-zinc-100">
                <span className={cn("flex h-4 w-4 items-center justify-center rounded border", on ? "border-[#18181B] bg-[#18181B] text-white" : "border-zinc-300")}>{on && <Check className="h-3 w-3" />}</span>
                {o.label}{o.hint && <span className="ml-auto text-[11px] text-zinc-400">{o.hint}</span>}
              </button>
            );
          })}
          {!shown.length && <p className="p-2 text-xs text-zinc-500">No options</p>}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function buildSchema(fields) {
  const shape = {};
  fields.forEach((f) => {
    let s;
    if (f.type === "number") {
      s = z.preprocess((v) => (v === "" || v === null || v === undefined ? null : Number(v)), z.number({ invalid_type_error: "Must be a number" }).min(f.min ?? 0, `Min ${f.min ?? 0}`).max(f.max ?? Number.MAX_SAFE_INTEGER, f.maxMessage || `Max ${f.max}`).nullable());
      if (f.required) s = s.refine((v) => v !== null, "Required");
    } else if (f.type === "multi") {
      s = z.array(z.string()).default([]);
      if (f.required) s = s.refine((v) => v.length > 0, "Select at least one");
    } else if (f.type === "email") {
      s = z.string().email("Invalid email").or(z.literal("")).nullable().optional();
      if (f.required) s = z.string().email("Invalid email");
    } else {
      s = z.string().nullable().optional();
      if (f.required) s = z.string({ required_error: "Required", invalid_type_error: "Required" }).trim().min(1, "Required");
    }
    shape[f.name] = s;
  });
  return z.object(shape);
}

function FieldInput({ f, field, list, testid }) {
  const person = (m) => [m.designation, m.role_label && m.role_label !== "Interviewer" && m.role_label !== "Recruiter" ? m.role_label : null].filter(Boolean).join(", ");
  const options = f.options || (f.master ? list(f.master).map((m) => ({ value: m.id, label: person(m) ? `${m.name} — ${person(m)}` : m.name, hint: m.skill_area })) : []);
  if (f.type === "textarea") return <Textarea {...field} value={field.value ?? ""} rows={f.rows || 3} data-testid={testid} />;
  if (f.type === "select" || f.master && f.type !== "multi") return <SelectField value={field.value} onChange={field.onChange} options={options} testid={testid} placeholder={f.placeholder || "Select…"} />;
  if (f.type === "multi") return <MultiSelect value={field.value || []} onChange={field.onChange} options={options} testid={testid} placeholder={f.placeholder} />;
  if (f.suggest) return (
    <>
      <Input {...field} value={field.value ?? ""} list={`${testid}-list`} placeholder={f.placeholder} data-testid={testid} />
      <datalist id={`${testid}-list`}>{list(f.suggest).map((m) => <option key={m.id} value={m.name} />)}</datalist>
    </>
  );
  return <Input type={f.type === "number" ? "number" : f.type === "date" ? "date" : f.type === "time" ? "time" : "text"} step={f.type === "number" ? "any" : undefined}
    {...field} value={field.value ?? ""} placeholder={f.placeholder} data-testid={testid} />;
}

export function FormDialog({ open, onOpenChange, title, description, fields, initial, onSubmit, submitLabel = "Save", testid = "form", wide, children }) {
  const { list } = useAuth();
  const schema = useMemo(() => buildSchema(fields), [fields]);
  const { control, handleSubmit, reset, watch, setValue, formState: { errors, isSubmitting } } = useForm({ resolver: zodResolver(schema) });
  const values = watch();
  // fields with `derive` recalculate only when a field they depend on changes (e.g. Amount = CTC × Fee %)
  const depKey = JSON.stringify(fields.filter((f) => f.derive).map((f) => f.derive.from.map((k) => values?.[k] ?? "")));
  const lastDeps = useRef(null);
  useEffect(() => {
    if (lastDeps.current !== null && lastDeps.current !== depKey) {
      fields.filter((f) => f.derive).forEach((f) => {
        const v = f.derive.fn(values || {});
        if (v !== undefined && v !== values?.[f.name]) setValue(f.name, v);
      });
    }
    lastDeps.current = depKey;
  }, [depKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (open) {
      lastDeps.current = null; // opening the form never recalculates saved values
      reset(Object.fromEntries(fields.map((f) => [f.name, initial?.[f.name] ?? (f.type === "multi" ? [] : f.default ?? "")])));
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const submit = async (vals) => {
    const out = Object.fromEntries(Object.entries(vals).map(([k, v]) => [k, v === "" ? null : v]));
    await onSubmit(out);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto", wide ? "sm:max-w-3xl" : "sm:max-w-lg")} data-testid={`${testid}-dialog`}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <form onSubmit={handleSubmit(submit)} className="space-y-4">
          <div className={cn("grid gap-4", wide && "sm:grid-cols-2")}>
            {fields.map((f) => (
              <div key={f.name} className={cn("space-y-1.5", (f.full || f.type === "textarea") && "sm:col-span-2")}>
                <Label className="text-xs font-semibold text-zinc-600">{f.label}{f.required && <span className="text-rose-600"> *</span>}</Label>
                <Controller name={f.name} control={control} render={({ field }) => <FieldInput f={f} field={field} list={list} testid={`${testid}-${f.name}`} />} />
                {f.help && <p className="text-[11px] text-zinc-400">{typeof f.help === "function" ? f.help(values || {}) : f.help}</p>}
                {errors[f.name] && <p className="text-xs text-rose-600" data-testid={`${testid}-${f.name}-error`}>{errors[f.name].message}</p>}
              </div>
            ))}
          </div>
          {children}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} data-testid={`${testid}-cancel`}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting} data-testid={`${testid}-submit`}>{isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{submitLabel}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
