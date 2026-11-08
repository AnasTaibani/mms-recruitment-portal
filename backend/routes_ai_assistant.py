"""Phase 2 — AI Recruitment Assistant API (read-only).

POST /api/ai-assistant/chat     ask a question (any signed-in user; answers are limited to what that user can see)
GET  /api/ai-assistant/status   whether the assistant is configured (never returns the key)

Nothing is stored: no conversation collection, no transcript logging. Each request re-checks the user's
permissions and re-reads the database."""
import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import get_user, now_iso
from ai.config import load_config
from ai.openai_service import AIError, status as ai_status
from ai.intent_service import plan_question, merge_scope
from ai.query_service import recruitment_snapshot, candidate_lookup, metrics_for, resolve_requisitions
from ai.response_service import build_blocks, build_links, write_answer
from ai.context_service import clean_context, clean_history, next_context

router = APIRouter(prefix="/api/ai-assistant")
log = logging.getLogger("mms.ai")
_in_flight: set = set()


class ChatIn(BaseModel):
    question: str
    conversation_context: Optional[list] = None
    context: Optional[dict] = None


@router.get("/status")
async def assistant_status(user=Depends(get_user)):
    return ai_status()


def _err(e: AIError):
    return JSONResponse(status_code=e.status, content={"detail": e.message, "code": e.code})


@router.post("/chat")
async def chat(body: ChatIn, user=Depends(get_user)):
    cfg = load_config()
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(400, "Please type a question")
    if len(q) > cfg.max_question_chars:
        raise HTTPException(400, f"Questions are limited to {cfg.max_question_chars} characters")
    if user["id"] in _in_flight:
        raise HTTPException(429, "Your previous question is still being answered")
    _in_flight.add(user["id"])
    t0 = time.monotonic()
    try:
        history, prev = clean_history(body.conversation_context), clean_context(body.context)
        plan, u1 = await plan_question(q, history, prev)
        intent = plan["intent"]
        base = {"retrieved_at": now_iso(), "blocks": [], "related_links": [], "observations": []}
        if intent == "greeting":
            return base | {"answer": "Hello! Ask me about requirements, candidate pipelines, interviews, offers or joining progress.",
                           "follow_up_suggestions": ["Show the current recruitment pipeline", "What is the interview status?", "Summarise the latest offers"],
                           "context": prev, "intent": intent}
        if intent == "out_of_scope":
            return base | {"answer": "I can only answer questions about MMS recruitment data, and I can't create or change records. "
                                     "Try asking about a requirement, the pipeline, interviews, offers or joining.",
                           "follow_up_suggestions": ["Give me an update on BA requirements", "Show the current recruitment pipeline"], "context": prev, "intent": intent}
        if intent == "clarify":
            return base | {"answer": plan["clarification_question"], "follow_up_suggestions": [], "context": prev, "intent": intent, "clarification": True}

        scope = merge_scope(plan, prev)
        if plan.get("stage"):
            scope["stage"] = plan["stage"]
        if intent == "candidate_lookup":
            data, reqs = await candidate_lookup(user, plan.get("candidate_name")), []
            snap = {}
        else:
            focus = plan["focus"] + (["metrics"] if intent == "metrics" and "metrics" not in plan["focus"] else [])
            snap, reqs, _missing = await recruitment_snapshot(user, scope, focus)
            data = snap
        out, u2 = await write_answer(q, history, data, plan["focus"])
        blocks = build_blocks(snap) if snap and not snap.get("no_match") else {}
        ctx_scope = {k: v for k, v in scope.items() if k != "stage"}
        log.info("ai_chat role=%s intent=%s reqs=%s latency_ms=%s tokens=%s", user["role"], intent, len(reqs),
                 round((time.monotonic() - t0) * 1000), sum((u or {}).get("total_tokens") or 0 for u in (u1, u2)))
        return {"answer": out["answer"], "observations": out["observations"],
                "blocks": [blocks[k] for k in out["show_blocks"] if k in blocks],
                "follow_up_suggestions": out["follow_ups"], "related_links": build_links(snap, reqs) if snap else [],
                "retrieved_at": (data or {}).get("retrieved_at") or now_iso(), "intent": intent,
                "context": next_context(plan, ctx_scope, reqs)}
    except AIError as e:
        log.warning("ai_chat_error code=%s role=%s", e.code, user["role"])
        return _err(e)
    finally:
        _in_flight.discard(user["id"])
