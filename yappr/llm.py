"""Minimal OpenAI-compatible chat client (text only) with a local usage/cost log."""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def base_url_problem(url: str) -> str | None:
    """Why the API key must not be sent to this base URL, or None if it's fine.

    The key travels in a request header, so it needs an encrypted connection. Plain http is allowed
    only for a model server on this computer (Ollama, LM Studio, ...), where nothing crosses the network.
    """
    try:
        u = urllib.parse.urlsplit((url or "").strip())
        host = (u.hostname or "").lower()
    except ValueError:
        return "Base URL is not a valid address"
    if not host:
        return "Base URL is not a valid address"
    if u.scheme == "https":
        return None
    if u.scheme == "http" and host in _LOCAL_HOSTS:
        return None
    return "Base URL must start with https:// (plain http is allowed only for localhost)"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would re-send the Authorization header to wherever a redirect points, even another host
    or plain http. API endpoints don't redirect, so treat any redirect as an error instead."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.URLError(f"the server tried to redirect (HTTP {code}); not following it with your API key")


_opener = urllib.request.build_opener(_NoRedirect)


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, price_in: float, price_out: float, usage_log: Path):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.price_in = price_in
        self.price_out = price_out
        self.usage_log = usage_log
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def chat(self, system: str | list[str], user: str, *, kind: str, timeout: float, model: str | None = None,
             max_tokens: int | None = None) -> str:
        """`system` may be a list of parts: the first is the long, fixed part (cached where the provider
        supports it), the rest change between calls (e.g. the user's dictionary)."""
        if not self.available:
            raise LLMError("no API key configured")
        if isinstance(system, list):
            system = "\n\n".join(p for p in system if p)
        problem = base_url_problem(self.base_url)
        if problem:
            raise LLMError(problem)
        model = model or self.model
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        t = time.monotonic()
        try:
            with _opener.open(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise LLMError(f"HTTP {e.code}: {detail}") from e
        except Exception as e:
            raise LLMError(str(e)) from e
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            raise LLMError(f"unexpected response: {str(data)[:200]}") from e
        usage = data.get("usage") or {}
        self._log_usage(kind, model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), time.monotonic() - t)
        return text.strip()

    def _log_usage(self, kind: str, model: str, tin: int, tout: int, secs: float,
                   cache_read: int = 0, cache_write: int = 0) -> None:
        # cached input is billed at 0.1x to read and 1.25x to write (5-minute cache)
        cost = (tin + cache_read * 0.1 + cache_write * 1.25) / 1e6 * self.price_in + tout / 1e6 * self.price_out
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "model": model,
            "in": tin,
            "out": tout,
            "usd": round(cost, 6),
            "secs": round(secs, 2),
        }
        if cache_read or cache_write:
            rec["cache_read"], rec["cache_write"] = cache_read, cache_write
        with self._lock:
            with open(self.usage_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")


class ClaudeClient(LLMClient):
    """Claude through Anthropic's official SDK (Messages API). Text in, text out.

    `kind` decides how much the model thinks: dictation cleanup is a quick rewrite, so thinking is
    off and effort low (fast); meeting summaries keep adaptive thinking on.
    """

    def __init__(self, api_key: str, model: str, price_in: float, price_out: float, usage_log: Path):
        super().__init__("https://api.anthropic.com", api_key, model, price_in, price_out, usage_log)
        self._client = None

    def _sdk(self):
        if self._client is None:
            import anthropic

            # retries: the SDK already retries 429/5xx/connection errors; keep it short for dictation
            self._client = anthropic.Anthropic(api_key=self.api_key, max_retries=1)
        return self._client

    def chat(self, system: str | list[str], user: str, *, kind: str, timeout: float, model: str | None = None,
             max_tokens: int | None = None) -> str:
        if not self.available:
            raise LLMError("no API key configured")
        import anthropic

        model = model or self.model
        quick = kind in ("dictation", "test")
        if isinstance(system, list):
            # cache the long fixed part: dictations come in bursts, so most calls read it at 0.1x
            system = [{"type": "text", "text": system[0], "cache_control": {"type": "ephemeral"}}] + [
                {"type": "text", "text": part} for part in system[1:] if part]
        params = {
            "model": model,
            "max_tokens": max_tokens or 16000,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if quick:
            params["thinking"] = {"type": "disabled"}
            params["output_config"] = {"effort": "low"}
        t = time.monotonic()
        try:
            resp = self._sdk().with_options(timeout=timeout).messages.create(**params)
        except anthropic.AuthenticationError as e:
            raise LLMError("Claude rejected the API key") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Claude rate limit reached") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude HTTP {e.status_code}: {e.message}"[:300]) from e
        except anthropic.APIError as e:  # connection errors, timeouts
            raise LLMError(f"Claude request failed: {e}") from e
        if resp.stop_reason == "refusal":
            raise LLMError("Claude declined this request")
        text = "".join(b.text for b in resp.content if b.type == "text")
        u = resp.usage
        self._log_usage(kind, model, u.input_tokens, u.output_tokens, time.monotonic() - t,
                        getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0)
        return text.strip()


PROVIDERS = {"claude": "Claude (Anthropic)", "openai": "OpenAI-compatible"}


def make_llm(provider: str, base_url: str, api_key: str, model: str, price_in: float, price_out: float,
             usage_log: Path) -> LLMClient:
    if provider == "claude":
        return ClaudeClient(api_key, model, price_in, price_out, usage_log)
    return LLMClient(base_url, api_key, model, price_in, price_out, usage_log)


def usage_summary(usage_log: Path, days: int = 30) -> dict:
    """Totals over the last `days` days plus a 30-day projection based on the days with data."""
    now = datetime.now(timezone.utc)
    total_usd, calls, tin, tout = 0.0, 0, 0, 0
    active_days: set[str] = set()
    first = None
    try:
        lines = usage_log.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        try:
            r = json.loads(line)
            ts = datetime.fromisoformat(r["ts"])
        except Exception:
            continue
        if (now - ts).days >= days:
            continue
        first = ts if first is None or ts < first else first
        total_usd += r.get("usd", 0)
        calls += 1
        tin += r.get("in", 0)
        tout += r.get("out", 0)
        active_days.add(ts.date().isoformat())
    span_days = max(1.0, (now - first).total_seconds() / 86400) if first else 1.0
    return {
        "calls": calls,
        "tokens_in": tin,
        "tokens_out": tout,
        "usd": round(total_usd, 4),
        "days_with_use": len(active_days),
        "span_days": round(span_days, 1),
        "projected_month_usd": round(total_usd / span_days * 30, 2) if calls else 0.0,
    }
