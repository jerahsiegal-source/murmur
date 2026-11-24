"""Record every network connection opened by a process tree (and by process name match) until killed.

Usage: python tools/netwatch.py <seconds> <out.json> <cmdline substring>...
"""
import json
import sys
import time

import psutil

secs, out, needles = float(sys.argv[1]), sys.argv[2], sys.argv[3:]
seen = {}
end = time.time() + secs
while time.time() < end:
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
            if not any(n in cmd for n in needles) or "netwatch.py" in cmd:
                continue
            for c in p.net_connections(kind="inet"):
                if c.raddr:
                    key = f"{c.raddr.ip}:{c.raddr.port}"
                    seen.setdefault(key, {"pid": p.pid, "cmd": cmd[-60:], "status": c.status, "first": time.strftime("%H:%M:%S")})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.05)
json.dump(seen, open(out, "w"), indent=1)
print(json.dumps(seen, indent=1))
