"""Temporary conversation context. Nothing is stored on the server: the browser keeps the conversation in component
state while the drawer is open and sends a trimmed copy with each question. The server only cleans it up here.

The context is a conversational aid — earlier answers are never treated as facts; every answer re-reads the database."""
from .config import load_config

ALLOWED_KEYS = ("requisition_query", "department", "recruiter", "intent", "focus", "matched_titles")


def clean_history(history):
    cfg = load_config()
    out = []
    for m in (history or [])[-cfg.max_context_messages:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            out.append({"role": m["role"], "content": m["content"][: cfg.max_context_chars]})
    return out


def clean_context(ctx):
    """Only short scope hints are accepted; record IDs or roles sent by the browser are ignored (scope is re-resolved server-side)."""
    if not isinstance(ctx, dict):
        return None
    out = {}
    for k in ALLOWED_KEYS:
        v = ctx.get(k)
        if isinstance(v, str):
            out[k] = v[:80]
        elif isinstance(v, list):
            out[k] = [str(x)[:80] for x in v[:10]]
    return out or None


def next_context(plan, scope, reqs):
    return {"intent": plan.get("intent"), "focus": plan.get("focus"), **{k: v for k, v in scope.items() if v},
            "matched_titles": sorted({r.get("title") for r in reqs if r.get("title")})[:10]}
