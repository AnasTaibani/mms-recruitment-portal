# Phase 2 — AI Recruitment Assistant ("Ask MMS AI")

Read-only assistant that answers questions about recruitment data the signed-in user is already allowed to see.
Uses OpenAI directly (official `openai` Python SDK) with your own `OPENAI_API_KEY`. No Emergent credentials, no other provider, no fallback model.

---

## 1. Architecture summary

```
Browser (drawer, React state only)
   │  POST /api/ai-assistant/chat  {question, conversation_context, context}   ← JWT; no key, no role, no IDs trusted
   ▼
FastAPI  routes_ai_assistant.py
   1. Auth (existing get_user) → the user's real role + scope come from the database, never from the request
   2. Planner call to OpenAI  → picks ONE allowlisted intent + filter words (JSON). It never writes queries.
      The backend validates the plan; unknown intents/fields are dropped.
   3. Retrieval (backend only) → existing portal functions list_requisitions / list_applications / list_candidates /
      list_interviews / list_offers / list_joinings / compute — the same permission-filtered functions the pages use.
      Sections the role can't view are left out entirely (not fetched, not sent).
   4. Answer call to OpenAI   → writes the explanation from a minimised <data> block only.
   5. Tables/KPI tiles/links are built by the backend from the same data — numbers are never taken from the model.
   ▼
Response {answer, observations, blocks, follow_up_suggestions, related_links, retrieved_at, intent, context}
```

OpenAI never touches MongoDB, never generates or runs queries, and never decides permissions.

## 2. Files

**New — backend**
| File | Purpose |
|---|---|
| `backend/ai/config.py` | Central config: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4.1-mini`), timeout, retries, input/context limits |
| `backend/ai/openai_service.py` | Only place that talks to OpenAI. Maps every SDK error to a controlled error code. Logs purpose/model/tokens/latency only |
| `backend/ai/intent_service.py` | Planner prompt, allowlisted intents, plan validation, follow-up scope carry-over |
| `backend/ai/query_service.py` | Permission-scoped retrieval + requirement-title matching ("BA" → Business Analyst) |
| `backend/ai/context_service.py` | Cleans/trims client-sent history and scope hints (IDs and roles ignored) |
| `backend/ai/response_service.py` | Answer prompt, tables/KPI blocks, related links |
| `backend/routes_ai_assistant.py` | `POST /api/ai-assistant/chat`, `GET /api/ai-assistant/status` |
| `backend/tests/test_ai_assistant.py` | 32 automated tests (section 9) |
| `backend/.env.example` | Template with every variable, no real values |

**New — frontend**
| File | Purpose |
|---|---|
| `frontend/src/components/assistant/AssistantDrawer.jsx` | Floating "Ask MMS AI" button + right-side drawer |

**Changed**
| File | Change |
|---|---|
| `backend/server.py` | Registers the new router (one import + one list entry) |
| `backend/req-render.txt` | Adds `openai==1.99.9` (already in `requirements.txt`) |
| `frontend/src/components/layout/AppShell.jsx` | Mounts the launcher on every signed-in page; extra bottom padding so the button never covers content |
| `frontend/src/components/ui/sheet.jsx` | Two optional props (`overlay`, `hideClose`); defaults unchanged, so existing sheets behave exactly as before |
| `.gitignore` | Ignores `.env` files (keeps `.env.example`) |

No workflow, calculation, permission or data-model code was changed. No new MongoDB collection is created.

## 3. SDK and configuration

- SDK: `openai==1.99.9` (official), `AsyncOpenAI`, Chat Completions with JSON output.
- Read in `backend/ai/config.py`:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | yes | — | Server-side only. Never returned, logged, or sent to the browser |
| `OPENAI_MODEL` | no | `gpt-4.1-mini` | Change without code edits |
| `OPENAI_TIMEOUT_SECONDS` | no | `30` | Per OpenAI call |
| `OPENAI_MAX_RETRIES` | no | `2` | SDK retries on transient errors |

If the key is missing the assistant returns a clear "not configured" error and the drawer shows a notice — it does **not** fall back to any other model.

## 4. `.env.example`

`backend/.env.example` lists all backend variables with placeholders, including:
```
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

## 5. API

### `POST /api/ai-assistant/chat`  (any signed-in user)
Request:
```json
{ "question": "Give me an update on BA requirements.",
  "conversation_context": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "context": {"requisition_query": "BA"} }
```
- `question`: 1–1000 characters.
- `conversation_context`: recent turns held by the browser; the server keeps only the last 10, each cut to 1,500 characters, and drops anything that isn't `user`/`assistant`.
- `context`: scope hint returned by the previous answer; only `requisition_query`, `department`, `recruiter` are read. Any IDs, roles or other fields are ignored.

Response 200:
```json
{ "answer": "...", "observations": ["..."],
  "blocks": [{"type": "kpis", ...}, {"type": "table", "title": "Candidate pipeline · 5 applications, 4 unique candidates", ...}],
  "follow_up_suggestions": ["..."], "related_links": [{"label": "REQ-0001 · Business Analyst", "to": "/requisitions/<id>"}],
  "retrieved_at": "2026-11-08T...", "intent": "recruitment_update", "context": {"requisition_query": "BA", ...} }
```

Errors (body `{"detail": "<friendly message>", "code": "<code>"}`):

| Status | code | When |
|---|---|---|
| 400 | — | Empty question or over 1000 characters |
| 401 | — | Not signed in |
| 429 | — | Same user already has a question being answered |
| 503 | `not_configured` | `OPENAI_API_KEY` not set |
| 503 | `invalid_key` | OpenAI rejected the key |
| 503 | `quota_exhausted` | OpenAI account out of credit |
| 429 | `rate_limited` | OpenAI rate limit |
| 504 | `timeout` | OpenAI too slow |
| 503 | `unavailable` | OpenAI unreachable / 5xx |
| 502 | `bad_response` | Model returned unusable output |

### `GET /api/ai-assistant/status`  (signed-in)
`{"configured": true, "model": "gpt-4.1-mini"}` — never includes the key.

There is no history/conversation endpoint.

## 6. Data reused (all read-only)

Through the existing permission-filtered functions: **requisitions, candidates, applications, interviews, offers, joinings**, and the analytics `compute()` used by the Analytics page (age per hire; cost per hire only for roles with cost access). Interview status counts for requisitions already in the user's view are read directly from **interviews**. **users** and **settings** are read by the existing auth/scope code. Nothing is written — verified by a test that compares every collection's document count before and after a series of questions.

## 7. Role-based access

The backend decides what each role sees; the model only receives what passed those checks.

| Role | What the assistant can use |
|---|---|
| Super Admin | Everything visible in the portal |
| Recruiter (HR Admin) | Same scope as in the portal today (full), incl. interviews they sit on |
| Management | Requisitions, pipeline, offers, joinings, metrics as in the portal; **interview details only for interviews they are on** (unless "Management can view all interviews" is switched on in Settings). Totals per requirement are shown as counts only |
| Interviewer | Requirements and their **own** interviews only; no pipeline, offers, costs or candidate lists |

When a section is left out the answer says it isn't available for the role, rather than reporting zero. Candidate contact details (email, phone), individual offer CTC and identity fields are never sent to OpenAI (the average cost per hire is sent only for roles that can already see costs). Requests to create/edit/delete/schedule/approve are declined.

## 8. Conversation context

- Lives only in the drawer's React state. Not stored in MongoDB, localStorage, sessionStorage or anywhere else.
- Cleared on **New chat**, closing the drawer, page refresh, sign-out, and when a different user signs in.
- Follow-ups ("How many are in screening?", "Who is handling these?") reuse the previous *scope words* (e.g. "BA"), but **every question re-reads the database** — nothing is cached.
- Server logs record role, intent, number of requisitions matched, latency and token counts — never the question, answer, names or data.

## 9. Test results (run on 8 Nov 2026)

**Important:** I could not reach OpenAI from my environment, so tests ran the real backend and the real OpenAI SDK against a local stand-in server that speaks the OpenAI API (it plans with fixed rules, echoes the data it receives, records every request, and can simulate errors). This proves the flow, permissions, data minimisation and error handling. It does **not** prove the wording quality of real GPT answers — please do the real-key check in section 11.

`backend/tests/test_ai_assistant.py` — **32 passed**
- BA conversation: update → "how many in screening?" → "who is handling these?" → "interview status?" → new candidate added mid-conversation and picked up on the next question → switch to another requirement. Counts match the database (5 applications vs 4 unique candidates; "Database Engineer" correctly NOT treated as "BA").
- No-match requirement (lists open titles instead), requirement with zero candidates (0, not "unavailable"), unrelated question, greeting, ambiguous question → clarification, write request refused.
- Candidate lookup sends no email or phone.
- RBAC: interviewer (no pipeline, only own interview), management (interview details only for assigned), recruiter (full), forged role/IDs in the request ignored, prompt-injection attempt leaks nothing, no candidate email/phone in any request sent to the provider.
- Errors: missing key, invalid key, quota, rate limit, provider 500, timeout, malformed model output, over-long question, oversized history trimmed, duplicate request blocked. Key never appears in responses.
- Read-only: no documents or collections added; no history endpoint; backend log contains no questions or data.

Browser check (built app, desktop 1440px and phone 390px) — **17 checks passed**: button on every page, welcome text and 4 prompts, answer with tables and links, follow-up chips, Enter sends / Shift+Enter new line, New chat clears, close-and-reopen clears, refresh clears, nothing in browser storage, key never in network traffic, friendly error message, full-width drawer on phone with no sideways scroll.

Regression: existing suites (workflow, cost per hire, management-as-interviewer, dashboard) — 45 passed, unchanged.

Bug found and fixed during testing: short requirement names like "BA" could match inside other words ("Data**ba**se Engineer"); short names now match whole words only.

## 10. Local setup

```bash
cd backend
pip install -r requirements.txt            # includes openai==1.99.9
cp .env.example .env                        # then fill in values
# in .env:
#   MONGO_URL=mongodb://127.0.0.1:27017     ← use a LOCAL database for development
#   OPENAI_API_KEY=sk-...                   ← your key
#   OPENAI_MODEL=gpt-4.1-mini
uvicorn server:app --port 8001

cd ../frontend && yarn install && yarn start
```
Sign in, click **Ask MMS AI** (bottom-right).

Run the assistant tests (local database only — the test refuses to run against a remote MONGO_URL). They need the stand-in OpenAI server; ask me for it if you want to run them yourself, or test manually with a real key.

## 11. Deployment (Render backend + Vercel frontend)

1. **Render → your backend service → Environment** — add:
   - `OPENAI_API_KEY` = your OpenAI key
   - `OPENAI_MODEL` = `gpt-4.1-mini` (optional; this is the default)
   Save → Render redeploys. `req-render.txt` now installs `openai`.
2. **Vercel** — nothing to add. The frontend never sees the key; just redeploy the new frontend build.
3. **Check**: sign in → Ask MMS AI → "Give me an update on BA requirements." Compare the numbers with the Requisitions and Pipeline pages. Then sign in as a Management user and an Interviewer and confirm they see less.
4. **Keep `.env` out of git.** `.gitignore` now ignores it, but if it was committed before, run once:
   `git rm --cached backend/.env frontend/.env` and commit. Because `backend/.env` holds your production database URL and admin password, consider rotating them if the repo was ever shared.

## 12. Limitations

- Real OpenAI not tested here (see section 9). Wording, tone and how well the model handles unusual phrasing need a check with your key.
- Each question makes two OpenAI calls (plan + answer), so expect answers to take a few seconds; cost is two small `gpt-4.1-mini` requests per question. Real latency was not measured here.
- Requirement matching is by title words and common abbreviations (BA, QA, PM, HR, UI, UX, Dev) and initials of the title. Unusual nicknames may need the full title.
- Large requirements: lists shown to the model and in tables are capped (about 10–25 rows); totals always cover everything.
- One question at a time per user (a second one while the first is answering gets a "please wait").
- English only.
- Not part of this change, but worth knowing: the portal's existing **file upload storage** (resumes/attachments) connects to Emergent's storage service using `EMERGENT_LLM_KEY` at start-up, and `requirements.txt` pins a `litellm` build from Emergent. The assistant uses neither. Moving file storage off Emergent would be a separate change.
