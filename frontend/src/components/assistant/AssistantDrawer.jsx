import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowUp, ExternalLink, Loader2, MessageSquarePlus, Sparkles, X } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { api, errMsg, fmtDateTime } from "@/lib/api";
import { cn } from "@/lib/utils";

const MAX_CHARS = 1000;
const STARTERS = ["Give me an update on BA requirements.", "Show the current recruitment pipeline.", "What is the interview status?", "Summarise the latest offers."];

/* Minimal, safe rendering of the assistant's text: paragraphs, "- " bullets and **bold** (no HTML is ever injected). */
function RichText({ text }) {
  const inline = (s, k) => s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") && p.endsWith("**") ? <b key={`${k}-${i}`} className="font-semibold">{p.slice(2, -2)}</b> : <Fragment key={`${k}-${i}`}>{p}</Fragment>));
  const out = [];
  let list = [];
  const flush = (k) => { if (list.length) { out.push(<ul key={`ul-${k}`} className="my-1.5 list-disc space-y-1 pl-5">{list}</ul>); list = []; } };
  text.split("\n").forEach((line, i) => {
    const t = line.trim();
    if (/^[-•*]\s+/.test(t)) list.push(<li key={i}>{inline(t.replace(/^[-•*]\s+/, ""), i)}</li>);
    else { flush(i); if (t) out.push(<p key={i} className="my-1.5 first:mt-0">{inline(t.replace(/^#+\s*/, ""), i)}</p>); }
  });
  flush("end");
  return <div className="text-[14px] leading-relaxed text-ink">{out}</div>;
}

function Block({ b }) {
  if (b.type === "kpis") {
    return (
      <div className="mt-3">
        <p className="mb-1.5 text-[12px] font-medium text-subtle">{b.title}</p>
        <div className="grid grid-cols-2 gap-2">
          {b.items.map((k) => (
            <div key={k.label} className="rounded-[10px] border border-line bg-white px-3 py-2">
              <p className="text-[12px] text-subtle">{k.label}</p>
              <p className="text-[18px] font-semibold tabular-nums text-ink">{k.value}</p>
              {k.hint && <p className="truncate text-[11.5px] text-subtle">{k.hint}</p>}
            </div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="mt-3 overflow-hidden rounded-[10px] border border-line bg-white">
      <p className="border-b border-line bg-canvas px-3 py-1.5 text-[12px] font-medium text-[#4B5361]">{b.title}</p>
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-[12.5px]">
          <thead><tr>{b.columns.map((c, i) => <th key={c} className={cn("whitespace-nowrap px-3 py-1.5 font-medium text-subtle", (b.numeric || []).includes(i) ? "text-right" : "text-left")}>{c}</th>)}</tr></thead>
          <tbody>{b.rows.map((r, ri) => (
            <tr key={ri} className="border-t border-[#EEF1F5]">{r.map((v, i) => <td key={i} className={cn("px-3 py-1.5", (b.numeric || []).includes(i) ? "text-right tabular-nums" : "text-ink")}>{v === null || v === undefined || v === "" ? "—" : v}</td>)}</tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AssistantMessage({ m, onAsk, busy }) {
  if (m.error) {
    return (
      <div className="flex items-start gap-2 rounded-[12px] border border-[#F1D2D0] bg-[#FBEDEC] px-3 py-2.5 text-[13.5px] text-[#9E3B37]" data-testid="assistant-error">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span>{m.content}</span>
      </div>
    );
  }
  return (
    <div className="space-y-2" data-testid="assistant-message">
      <div className="rounded-[14px] rounded-tl-[6px] border border-line bg-white px-3.5 py-3 shadow-[0_1px_2px_rgba(32,36,43,0.04)]">
        <RichText text={m.content} />
        {m.observations?.length > 0 && (
          <div className="mt-2 rounded-[10px] bg-brand-mist px-3 py-2">
            <p className="text-[12px] font-medium text-brand-deep">Key observations</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[13px] text-ink">{m.observations.map((o) => <li key={o}>{o}</li>)}</ul>
          </div>
        )}
        {m.blocks?.map((b, i) => <Block key={i} b={b} />)}
        {m.links?.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {m.links.map((l) => (
              <Link key={l.to + l.label} to={l.to} className="inline-flex items-center gap-1 rounded-[8px] border border-line px-2 py-1 text-[12px] font-medium text-brand-royal hover:border-[#CFE3FB] hover:bg-brand-mist hover:text-brand-deep">
                {l.label}<ExternalLink className="h-3 w-3" />
              </Link>))}
          </div>
        )}
        {m.retrieved_at && <p className="mt-2 text-[11px] text-subtle">From portal data · {fmtDateTime(m.retrieved_at)}</p>}
      </div>
      {m.follow_ups?.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid="assistant-followups">
          {m.follow_ups.map((f) => (
            <button key={f} type="button" disabled={busy} onClick={() => onAsk(f)}
              className="rounded-full border border-[#CFE3FB] bg-white px-3 py-1 text-left text-[12.5px] text-brand-deep transition-colors hover:bg-brand-pale disabled:opacity-50">{f}</button>))}
        </div>
      )}
    </div>
  );
}

/**
 * Ask MMS AI. The conversation lives only in this component's state while the drawer is open:
 * closing the drawer, "New chat", signing out or switching user clears it. Nothing is written to storage.
 */
export function AssistantDrawer({ open, onOpenChange }) {
  const [messages, setMessages] = useState([]);
  const [context, setContext] = useState(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const reqId = useRef(0);

  const reset = useCallback(() => { reqId.current += 1; setMessages([]); setContext(null); setDraft(""); setBusy(false); }, []);
  useEffect(() => {
    if (!open) { reset(); return; }
    api.get("/ai-assistant/status").then(({ data }) => setStatus(data)).catch(() => setStatus(null));
    setTimeout(() => inputRef.current?.focus(), 150);
  }, [open, reset]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, busy]);

  const ask = async (text) => {
    const q = (text ?? draft).trim();
    if (!q || busy) return;
    if (q.length > MAX_CHARS) return;
    const history = messages.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content })).slice(-10);
    const mine = ++reqId.current;
    setMessages((ms) => [...ms, { role: "user", content: q }]);
    setDraft("");
    setBusy(true);
    try {
      const { data } = await api.post("/ai-assistant/chat", { question: q, conversation_context: history, context });
      if (mine !== reqId.current) return;  // chat was reset while waiting
      setMessages((ms) => [...ms, { role: "assistant", content: data.answer, observations: data.observations, blocks: data.blocks,
        follow_ups: data.follow_up_suggestions, links: data.related_links, retrieved_at: data.retrieved_at }]);
      if (data.context !== undefined) setContext(data.context);
    } catch (e) {
      if (mine !== reqId.current) return;
      setMessages((ms) => [...ms, { role: "assistant", error: true, content: errMsg(e) }]);
    } finally {
      if (mine === reqId.current) setBusy(false);
    }
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); ask(); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange} modal={false}>
      <SheetContent side="right" overlay={false} hideClose onInteractOutside={(e) => e.preventDefault()}
        className="flex w-full flex-col gap-0 border-l border-line bg-canvas p-0 shadow-[0_0_60px_-18px_rgba(32,36,43,0.35)] sm:w-[460px] sm:max-w-[460px]" data-testid="assistant-drawer">
        <header className="flex items-center gap-3 border-b border-line bg-white px-4 py-3">
          <span className="grid h-9 w-9 place-items-center rounded-[10px] bg-brand-deep text-white"><Sparkles className="h-[18px] w-[18px]" strokeWidth={1.8} /></span>
          <div className="min-w-0 flex-1">
            <SheetTitle className="text-[15px] font-semibold leading-tight text-ink">Recruitment Assistant</SheetTitle>
            <SheetDescription className="text-[12px] text-subtle">MMS AI · read-only</SheetDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={reset} disabled={!messages.length && !busy} data-testid="assistant-new-chat"><MessageSquarePlus className="h-4 w-4" />New chat</Button>
          <button type="button" onClick={() => onOpenChange(false)} className="grid h-8 w-8 place-items-center rounded-[8px] text-subtle hover:bg-[#F3F6FA] hover:text-ink" aria-label="Close assistant" data-testid="assistant-close"><X className="h-4 w-4" /></button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 scroll-thin" data-testid="assistant-conversation" aria-live="polite">
          {status && !status.configured && (
            <p className="rounded-[10px] border border-[#F0DFBD] bg-[#FBF4E6] px-3 py-2 text-[12.5px] text-[#8A6420]" data-testid="assistant-not-configured">
              The assistant isn't configured on the server yet. An administrator needs to set OPENAI_API_KEY.</p>
          )}
          {!messages.length && (
            <div className="pt-2" data-testid="assistant-welcome">
              <div className="rounded-[14px] border border-line bg-white p-4">
                <p className="text-[15px] font-semibold text-ink">Hello! I'm your MMS Recruitment Assistant.</p>
                <p className="mt-1 text-[13.5px] leading-relaxed text-[#4B5361]">Ask me anything about recruitment requirements, candidate pipelines, interviews, offers and joining progress.</p>
              </div>
              <p className="mb-2 mt-4 text-[12px] font-medium text-subtle">Try asking</p>
              <div className="space-y-1.5">
                {STARTERS.map((s) => (
                  <button key={s} type="button" onClick={() => ask(s)} disabled={busy} data-testid="assistant-starter"
                    className="block w-full rounded-[10px] border border-line bg-white px-3 py-2 text-left text-[13.5px] text-ink transition-colors hover:border-[#CFE3FB] hover:bg-brand-mist">{s}</button>))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (m.role === "user" ? (
            <div key={i} className="flex justify-end" data-testid="user-message">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-[14px] rounded-tr-[6px] bg-brand-deep px-3.5 py-2 text-[14px] text-white">{m.content}</p>
            </div>
          ) : <AssistantMessage key={i} m={m} onAsk={ask} busy={busy} />))}
          {busy && (
            <div className="flex items-center gap-2 text-[13px] text-subtle" data-testid="assistant-loading">
              <Loader2 className="h-4 w-4 animate-spin text-brand-royal" />Checking portal data and preparing an answer…
            </div>
          )}
          <div ref={endRef} />
        </div>

        <footer className="border-t border-line bg-white px-3 py-3">
          <div className="flex items-end gap-2 rounded-[12px] border border-[#DCE1E7] bg-white px-2 py-1.5 focus-within:border-brand-royal focus-within:ring-2 focus-within:ring-brand-royal/20">
            <textarea ref={inputRef} rows={1} value={draft} maxLength={MAX_CHARS} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey}
              placeholder="Ask about requirements, pipeline, interviews…" aria-label="Ask the assistant" data-testid="assistant-input"
              className="max-h-32 min-h-[36px] flex-1 resize-none bg-transparent px-1.5 py-1.5 text-[14px] text-ink outline-none placeholder:text-[#9AA2AE]"
              style={{ height: "auto" }} onInput={(e) => { e.target.style.height = "auto"; e.target.style.height = `${Math.min(e.target.scrollHeight, 128)}px`; }} />
            <Button size="sm" className="h-9 w-9 shrink-0 p-0" onClick={() => ask()} disabled={busy || !draft.trim()} aria-label="Send" data-testid="assistant-send">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            </Button>
          </div>
          <p className="mt-1.5 flex justify-between px-1 text-[11px] text-subtle">
            <span>Enter to send · Shift + Enter for a new line · read-only</span><span className="tabular-nums">{draft.length}/{MAX_CHARS}</span>
          </p>
        </footer>
      </SheetContent>
    </Sheet>
  );
}

export function AssistantLauncher() {
  const [open, setOpen] = useState(false);
  return (
    <>
      {!open && (
        <button type="button" onClick={() => setOpen(true)} data-testid="ask-mms-ai"
          className="group fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-brand-deep py-2.5 pl-3.5 pr-4 text-[14px] font-medium text-white shadow-[0_10px_28px_-10px_rgba(34,101,200,0.65)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-0.5 hover:bg-[#1D58AF] hover:shadow-[0_14px_32px_-10px_rgba(34,101,200,0.7)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-royal/50 focus-visible:ring-offset-2 sm:bottom-6 sm:right-6">
          <Sparkles className="h-[18px] w-[18px] transition-transform duration-300 group-hover:rotate-12" strokeWidth={1.9} />Ask MMS AI
        </button>
      )}
      <AssistantDrawer open={open} onOpenChange={setOpen} />
    </>
  );
}
