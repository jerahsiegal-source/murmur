"""Run a Python module/script while logging every outgoing network connection it makes.

Usage: python tools/sockspy.py <log.jsonl> -m <module> [args...]
       python tools/sockspy.py <log.jsonl> <script.py> [args...]
"""
import json
import runpy
import socket
import sys
import threading
import time

log_path = sys.argv[1]
_lock = threading.Lock()
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_gai = socket.getaddrinfo


def _log(kind, target):
    with _lock, open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "kind": kind, "target": str(target),
                            "thread": threading.current_thread().name}) + "\n")


def connect(self, addr):
    _log("connect", addr)
    return _orig_connect(self, addr)


def connect_ex(self, addr):
    _log("connect", addr)
    return _orig_connect_ex(self, addr)


def getaddrinfo(host, *a, **k):
    _log("dns", host)
    return _orig_gai(host, *a, **k)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = getaddrinfo

args = sys.argv[2:]
if args[0] == "-m":
    sys.argv = [args[1]] + args[2:]
    runpy.run_module(args[1], run_name="__main__", alter_sys=True)
else:
    sys.argv = args
    runpy.run_path(args[0], run_name="__main__")
