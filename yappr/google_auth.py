"""Sign in with Google, read-only, so Yappr can see your calendar.

This is Google's standard flow for desktop apps ("installed apps"):
1. Yappr opens Google's sign-in page in your normal browser (never inside the Yappr window).
2. You approve. Google sends the browser back to http://127.0.0.1:<random port>, where Yappr is
   listening for that one request. A random `state` and PKCE stop anyone else from finishing it.
3. Yappr swaps the one-time code for a refresh token, which goes to Windows Credential Manager
   (`Yappr / google-refresh-token`). Short-lived access tokens are kept in memory only.

Access asked for: your email address (to show "Connected as ...") and read-only calendar events.
Addresses contacted: accounts.google.com (in your browser), oauth2.googleapis.com and
www.googleapis.com. Nothing is contacted unless you have connected.

The client ID comes from (first found): the YAPPR_GOOGLE_CLIENT_ID / YAPPR_GOOGLE_CLIENT_SECRET
environment variables, `google-client.json` in the Yappr data folder (the file Google Cloud lets you
download for a "Desktop app" client), or one shipped with Yappr. For desktop apps Google says the
"client secret" is not actually secret; your refresh token is what must be protected.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import logging
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable

from .config import KEYRING_SERVICE, getenv

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
SCOPES = ("openid", "email", CALENDAR_SCOPE)
KEYRING_USER = "google-refresh-token"
CLIENT_FILE = "google-client.json"
BUNDLED_CLIENT = Path(__file__).parent / "assets" / CLIENT_FILE

DONE_PAGE = """<!doctype html><meta charset="utf-8"><title>Yappr</title>
<body style="font:16px 'Segoe UI',sans-serif;background:#fffaf0;color:#3a2418;display:grid;place-items:center;height:90vh">
<div style="text-align:center"><h2 style="margin:0 0 8px">{title}</h2><p style="margin:0">{text}</p></div></body>"""


class GoogleError(Exception):
    """Something went wrong, said in words people can act on (str(e) is shown in the window)."""


class NeedsReconnect(GoogleError):
    """Google no longer accepts the saved sign-in (revoked, expired or changed password)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # never carry a token elsewhere
        raise urllib.error.URLError(f"Google tried to redirect (HTTP {code}); not following it")


_opener = urllib.request.build_opener(_NoRedirect)


def load_client(root: Path | None) -> tuple[str, str] | None:
    """(client_id, client_secret) or None when Yappr has no Google client set up."""
    cid = getenv("YAPPR_GOOGLE_CLIENT_ID")
    if cid:
        return cid.strip(), (getenv("YAPPR_GOOGLE_CLIENT_SECRET") or "").strip()
    for p in ([root / CLIENT_FILE] if root else []) + [BUNDLED_CLIENT]:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except Exception:
            log.warning("%s isn't a valid Google client file", p.name)
            continue
        c = raw.get("installed") or raw  # the downloaded file wraps it in {"installed": {...}}
        if c.get("client_id"):
            return str(c["client_id"]), str(c.get("client_secret", ""))
    return None


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _email_from_id_token(id_token: str) -> str:
    """The id_token came straight from Google's token endpoint over HTTPS, so reading it is enough."""
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("email", ""))
    except Exception:
        return ""


def _post(url: str, data: dict, timeout: float = 20) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with _opener.open(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except Exception:
            body = {}
        body.setdefault("error", f"http_{e.code}")
        return body
    except (urllib.error.URLError, OSError) as e:  # offline, DNS, TLS
        return {"error": "network", "detail": type(e).__name__}


class _Catcher(http.server.BaseHTTPRequestHandler):
    """Takes the one redirect from Google's sign-in page."""

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        srv = self.server
        if urllib.parse.urlparse(self.path).path != "/" or "state" not in q:
            self.send_error(404)  # favicon and anything else
            return
        if q["state"][0] != srv.expected_state:
            self._page("That sign-in link is out of date", "Go back to Yappr and click Connect again.")
            return  # keep waiting for the real one
        srv.result = {"code": q.get("code", [""])[0], "error": q.get("error", [""])[0]}
        if srv.result["code"]:
            self._page("Yappr is connected to Google", "You can close this tab and go back to Yappr.")
        else:
            self._page("Not connected", "Nothing was shared with Yappr. You can close this tab.")

    def _page(self, title: str, text: str) -> None:
        body = DONE_PAGE.format(title=title, text=text).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # the query string holds the one-time code: keep it out of the log
        pass


class GoogleAccount:
    """The signed-in Google account, if any. Thread-safe."""

    def __init__(self, root: Path | None, keyring_mod=None, open_browser: Callable[[str], object] = webbrowser.open,
                 post: Callable[[str, dict], dict] = _post, auth_url: str = AUTH_URL):
        self.root = root
        self._kr = keyring_mod
        self.open_browser = open_browser
        self.post = post
        self.auth_url = auth_url
        self._lock = threading.Lock()
        self._access: tuple[str, float] | None = None  # (token, expires at monotonic)
        self._cancel = threading.Event()
        self.problem = ""  # set when Google stopped accepting the saved sign-in

    # ---- token storage
    @property
    def kr(self):
        if self._kr is None:
            import keyring

            self._kr = keyring
        return self._kr

    def _refresh_token(self) -> str:
        try:
            return self.kr.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
        except Exception:
            return ""

    @property
    def configured(self) -> bool:
        return load_client(self.root) is not None

    @property
    def connected(self) -> bool:
        return bool(self._refresh_token())

    # ---- connect
    def connect(self, timeout: float = 300) -> str:
        """Run the sign-in; returns the account's email. Raises GoogleError with a plain message."""
        client = load_client(self.root)
        if client is None:
            raise GoogleError("Google sign-in isn't set up in this copy of Yappr yet. See the README, under Google Calendar.")
        cid, csecret = client
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        self._cancel.clear()
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Catcher)
        srv.expected_state, srv.result, srv.timeout = state, None, 0.5
        redirect = f"http://127.0.0.1:{srv.server_address[1]}"
        url = self.auth_url + "?" + urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": " ".join(SCOPES),
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
            "access_type": "offline", "prompt": "consent",
        })
        try:
            self.open_browser(url)
            end = time.monotonic() + timeout
            while srv.result is None:
                if self._cancel.is_set():
                    raise GoogleError("Connecting was cancelled.")
                if time.monotonic() > end:
                    raise GoogleError("Google didn't answer in time. Click Connect to try again.")
                srv.handle_request()
        finally:
            srv.server_close()
        if not srv.result["code"]:
            if srv.result["error"] == "access_denied":
                raise GoogleError("Not connected: Google sign-in was cancelled.")
            raise GoogleError("Google didn't let Yappr connect. Try again.")
        tok = self.post(TOKEN_URL, {
            "code": srv.result["code"], "client_id": cid, "client_secret": csecret, "redirect_uri": redirect,
            "grant_type": "authorization_code", "code_verifier": verifier,
        })
        if tok.get("error") == "network":
            raise GoogleError("Couldn't reach Google. Check your internet connection and try again.")
        if tok.get("error") or not tok.get("refresh_token"):
            log.warning("google token exchange failed: %s", tok.get("error"))
            raise GoogleError("Google didn't finish connecting. Click Connect to try again.")
        if CALENDAR_SCOPE not in str(tok.get("scope", "")).split():
            self._revoke(tok["refresh_token"])  # partial grant: don't keep something that can't do the job
            raise GoogleError("Yappr needs the box that lets it see your calendar ticked. Click Connect and tick it.")
        try:
            self.kr.set_password(KEYRING_SERVICE, KEYRING_USER, tok["refresh_token"])
        except Exception:
            raise GoogleError("Windows wouldn't let Yappr save the sign-in in Credential Manager.")
        with self._lock:
            self._access = (tok["access_token"], time.monotonic() + float(tok.get("expires_in", 3600)) - 60) \
                if tok.get("access_token") else None
            self.problem = ""
        return _email_from_id_token(tok.get("id_token", ""))

    def cancel(self) -> None:
        self._cancel.set()

    # ---- use
    def access_token(self) -> str:
        with self._lock:
            if self._access and time.monotonic() < self._access[1]:
                return self._access[0]
        rt = self._refresh_token()
        if not rt:
            raise GoogleError("Not connected to Google.")
        client = load_client(self.root)
        if client is None:
            raise GoogleError("Google sign-in isn't set up in this copy of Yappr.")
        tok = self.post(TOKEN_URL, {"refresh_token": rt, "client_id": client[0], "client_secret": client[1],
                                    "grant_type": "refresh_token"})
        if tok.get("error") == "invalid_grant":
            self.problem = "Google stopped accepting Yappr's sign-in. Click Connect to sign in again."
            raise NeedsReconnect(self.problem)
        if tok.get("error") or not tok.get("access_token"):
            raise GoogleError("Couldn't reach Google. Check your internet connection.")
        with self._lock:
            self._access = (tok["access_token"], time.monotonic() + float(tok.get("expires_in", 3600)) - 60)
            self.problem = ""
            return self._access[0]

    def get_json(self, url: str, params: dict, timeout: float = 20) -> dict:
        full = url + "?" + urllib.parse.urlencode(params)
        for attempt in (0, 1):
            req = urllib.request.Request(full, headers={"Authorization": f"Bearer {self.access_token()}"})
            try:
                with _opener.open(req, timeout=timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 0:
                    with self._lock:
                        self._access = None  # expired early: refresh once and retry
                    continue
                if e.code == 403:
                    raise GoogleError("Google says Yappr can't read this calendar. Click Connect and allow calendar access.")
                raise GoogleError(f"Google Calendar answered with an error (HTTP {e.code}).")
            except (urllib.error.URLError, OSError):
                raise GoogleError("Couldn't reach Google. Check your internet connection.")
        raise GoogleError("Google didn't accept Yappr's sign-in.")

    # ---- disconnect
    def _revoke(self, token: str) -> None:
        try:
            self.post(REVOKE_URL, {"token": token})
        except Exception as e:  # offline: still forget it locally
            log.warning("google revoke failed: %s", type(e).__name__)

    def disconnect(self) -> None:
        rt = self._refresh_token()
        if rt:
            self._revoke(rt)  # revoking the refresh token also ends its access tokens
        try:
            self.kr.delete_password(KEYRING_SERVICE, KEYRING_USER)
        except Exception:
            pass
        with self._lock:
            self._access = None
            self.problem = ""
