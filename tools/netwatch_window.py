"""Every network connection made by the Yappr window and its WebView2 helpers, from the moment it opens.

    python tools/netwatch_window.py <seconds> <out.json>

Start it before opening the window: it waits up to 2 minutes for the window, then watches for <seconds>.
Follows the window's own process tree (by parent), so other apps' WebView2 processes aren't counted.
Loopback (127.0.0.1/::1) is listed separately.
"""
import json
import sys
import time

import psutil

secs, out = float(sys.argv[1]), sys.argv[2]


def window_roots():
    roots = []
    for p in psutil.process_iter(["name"]):  # names are cheap; command lines only for python processes
        if (p.info["name"] or "").lower() not in ("python.exe", "pythonw.exe"):
            continue
        try:
            if "yappr.window" in p.cmdline():
                roots.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return roots


# Watch every WebView2/python process from before the window opens (connections can start within a
# second or two), then keep only those that turn out to belong to the Yappr window's process tree.
conns: dict = {}
roots, give_up = [], time.time() + 120
end = None
while (end is None and time.time() < give_up) or (end is not None and time.time() < end):
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() not in ("msedgewebview2.exe", "pythonw.exe", "python.exe"):
            continue
        try:
            for c in p.net_connections(kind="inet"):
                if c.raddr:
                    conns.setdefault((p.pid, f"{c.raddr.ip}:{c.raddr.port}"), (p.info["name"], c.status, time.strftime("%H:%M:%S")))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if end is None:
        roots = window_roots()
        if roots:
            end = time.time() + secs
            t_found = time.strftime("%H:%M:%S")
    time.sleep(0.05)
if not roots:
    sys.exit("no Yappr window opened")
pids = set()
for r in roots:
    try:
        pids |= {r.pid} | {c.pid for c in r.children(recursive=True)}
    except psutil.NoSuchProcess:
        pass
seen = {k: {"pid": pid, "name": n, "status": st, "first": f} for (pid, k), (n, st, f) in conns.items() if pid in pids}
local = {k: v for k, v in seen.items() if k.startswith(("127.", "::1", "[::1]"))}
remote = {k: v for k, v in seen.items() if k not in local}
res = {"window_found": t_found, "seconds": secs, "processes_in_window_tree": len(pids), "remote": remote, "loopback": local}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res, indent=1))
