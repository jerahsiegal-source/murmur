"""The Yappr window: Today, Notes, My words, Settings and the welcome.

Runs as its own process (`python -m yappr.window`), started by the app when you open it and gone when you
close it, so Yappr stays light while it sits in the background. The page is plain HTML/CSS/JS from
yappr/web, inlined into one document (no local web server, nothing loaded from the internet), shown with
the Edge WebView2 that comes with Windows. Every call goes back to the app over a named pipe (see api.py).
"""
from __future__ import annotations

import base64
import os
import sys
import threading
import time
from pathlib import Path

WEB = Path(__file__).with_name("web")
ASSETS = Path(__file__).with_name("assets")
TITLE = "Yappr"


def build_html(page: str = "today") -> str:
    """One self-contained document: CSS, JS and Skip's images inlined."""
    html = (WEB / "app.html").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    skip = "data:image/svg+xml;base64," + base64.b64encode((ASSETS / "skip.svg").read_bytes()).decode()
    return (html.replace("/*CSS*/", css).replace("/*JS*/", js).replace("{{SKIP}}", skip)
            .replace("{{PAGE}}", page if page.isalpha() else "today"))


class Bridge:
    """Exposed to the page as window.pywebview.api. Forwards each call to the app."""

    def __init__(self, conn):
        self._conn = conn
        self._lock = threading.Lock()

    def call(self, method: str, args: list | None = None):
        with self._lock:
            self._conn.send((method, list(args or [])))
            status, value = self._conn.recv()
        if status != "ok":
            raise RuntimeError(value)
        return value

    def browse_folder(self):
        """Folder picker for the notes folder (runs here: it's a dialog of this window)."""
        import webview

        picked = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        return picked[0] if picked else None


def set_icon(title: str) -> None:
    """Yappr's icon in the title bar and taskbar (instead of Python's)."""
    import ctypes

    user32 = ctypes.WinDLL("user32")
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    hwnd = user32.FindWindowW(None, title)
    ico = str(ASSETS / "yappr.ico")
    for kind, size in ((1, 32), (0, 16)):  # ICON_BIG, ICON_SMALL
        h = user32.LoadImageW(None, ico, 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        if hwnd and h:
            user32.SendMessageW(hwnd, 0x80, kind, h)  # WM_SETICON


def _test_driver(win, folder: Path) -> None:
    """End-to-end tests drop <n>.js into `folder`; the result of running it lands in <n>.out."""
    import json

    while True:
        for f in sorted(folder.glob("*.js")):
            try:
                out = {"ok": True, "value": win.evaluate_js(f.read_text(encoding="utf-8"))}
            except Exception as e:
                out = {"ok": False, "value": str(e)}
            f.with_suffix(".out").write_text(json.dumps(out, default=str), encoding="utf-8")
            f.unlink()
        time.sleep(0.2)


# The window shows only Yappr's own page, so WebView2 has no reason to go online. These switch off its
# background traffic (updater, SmartScreen, diagnostics, pings), which otherwise starts on its own.
# The environment variable takes precedence over the arguments pywebview sets, so keep its one flag too.
BROWSER_ARGS = " ".join([
    "--disable-features=ElasticOverscroll,msSmartScreenProtection,msEdgeEnhanceSecurityMode",
    "--disable-background-networking", "--disable-component-update", "--disable-domain-reliability",
    "--disable-client-side-phishing-detection", "--no-pings", "--disable-sync", "--metrics-recording-only",
    "--disable-breakpad", "--no-first-run",
])


def no_reputation_checks(win) -> None:
    """Tell WebView2 not to send page addresses to SmartScreen (newer runtimes only)."""
    try:
        win.native.browser.webview.CoreWebView2.Settings.IsReputationCheckingRequired = False
    except Exception:
        pass


def main() -> None:
    import webview
    from multiprocessing.connection import Client

    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = BROWSER_ARGS
    page = sys.argv[1] if len(sys.argv) > 1 else "today"
    try:  # group with Yappr on the taskbar
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Yappr.Dictation")
    except Exception:
        pass
    conn = Client(os.environ["YAPPR_WINDOW_PIPE"], family="AF_PIPE", authkey=bytes.fromhex(os.environ["YAPPR_WINDOW_KEY"]))
    win = webview.create_window(TITLE, html=build_html(page), js_api=Bridge(conn), width=1040, height=700,
                                min_size=(760, 540), background_color="#fbf8f3", text_select=True,
                                on_top=page == "welcome")

    def shown():
        set_icon(TITLE)
        no_reputation_checks(win)
        if page == "welcome":  # opened by the app on first run, not by a click: come to the front once
            time.sleep(1.5)
            win.on_top = False

    win.events.shown += lambda: threading.Thread(target=shown, daemon=True).start()
    if os.environ.get("YAPPR_WINDOW_TEST_DIR"):  # set only by tools/e2e_window.py, never by the app
        threading.Thread(target=_test_driver, args=(win, Path(os.environ["YAPPR_WINDOW_TEST_DIR"])), daemon=True).start()
    webview.start(private_mode=True)


if __name__ == "__main__":
    main()
