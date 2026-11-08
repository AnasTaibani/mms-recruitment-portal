"""The only place the portal talks to OpenAI. Uses the official SDK with the key from OPENAI_API_KEY.

Errors are mapped to controlled AIError codes; the key, prompts and candidate data are never logged — only
model, token usage, latency and the internal purpose of the call."""
import json
import logging
import time

import openai
from openai import AsyncOpenAI

from .config import load_config

log = logging.getLogger("mms.ai")


class AIError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


_client = None
_client_key = None


def _get_client(cfg):
    global _client, _client_key
    if not cfg.api_key:
        raise AIError("not_configured", "The AI assistant is not configured yet (OPENAI_API_KEY is not set on the server).", 503)
    sig = (cfg.api_key, cfg.base_url, cfg.timeout, cfg.max_retries)
    if _client is None or _client_key != sig:
        _client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=cfg.timeout, max_retries=cfg.max_retries)
        _client_key = sig
    return _client


def status():
    cfg = load_config()
    return {"configured": bool(cfg.api_key), "model": cfg.model}


async def complete_json(messages, purpose: str, max_tokens: int = 1200, temperature: float = 0.1):
    """Chat completion that must return a JSON object. Returns (parsed_dict, usage_dict)."""
    cfg = load_config()
    client = _get_client(cfg)
    t0 = time.monotonic()
    try:
        resp = await client.chat.completions.create(
            model=cfg.model, messages=messages, temperature=temperature, max_tokens=max_tokens,
            response_format={"type": "json_object"})
    except openai.AuthenticationError:
        raise AIError("invalid_key", "The AI service rejected the configured API key. Ask the administrator to check OPENAI_API_KEY.", 503)
    except openai.PermissionDeniedError:
        raise AIError("permission_denied", "The configured OpenAI account cannot use this model. Check OPENAI_MODEL and the account's access.", 503)
    except openai.NotFoundError:
        raise AIError("model_not_found", "The configured model is not available. Check OPENAI_MODEL on the server.", 503)
    except openai.RateLimitError as e:
        body = getattr(e, "body", None) or {}
        code = (body.get("code") if isinstance(body, dict) else None) or (body.get("error", {}).get("code") if isinstance(body, dict) else None)
        if code == "insufficient_quota" or "quota" in str(e).lower():
            raise AIError("quota_exhausted", "The AI service quota for this account is used up. Please contact the administrator.", 503)
        raise AIError("rate_limited", "The AI service is busy right now. Please try again in a moment.", 429)
    except openai.APITimeoutError:
        raise AIError("timeout", "The AI service took too long to respond. Please try again.", 504)
    except (openai.APIConnectionError, openai.InternalServerError):
        raise AIError("unavailable", "The AI assistant is temporarily unavailable. Please try again shortly.", 503)
    except openai.APIError:
        raise AIError("provider_error", "The AI service returned an error. Please try again.", 502)
    latency = round((time.monotonic() - t0) * 1000)
    u = getattr(resp, "usage", None)
    usage = {"model": getattr(resp, "model", cfg.model), "prompt_tokens": getattr(u, "prompt_tokens", None),
             "completion_tokens": getattr(u, "completion_tokens", None), "total_tokens": getattr(u, "total_tokens", None), "latency_ms": latency}
    log.info("ai_call purpose=%s model=%s prompt_tokens=%s completion_tokens=%s latency_ms=%s",
             purpose, usage["model"], usage["prompt_tokens"], usage["completion_tokens"], latency)
    try:
        content = resp.choices[0].message.content or ""
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (ValueError, IndexError, AttributeError, TypeError):
        raise AIError("bad_response", "The AI service returned an unexpected response. Please try again.", 502)
    return data, usage
