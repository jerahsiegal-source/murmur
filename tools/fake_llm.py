"""Local stand-in for an OpenAI-compatible API, for privacy/latency tests.

Logs every request (size, content type, whether it contains anything but JSON text) to a JSONL
file and replies with a trivially "cleaned" echo. Nothing leaves the machine.

Usage: python tools/fake_llm.py <port> <log.jsonl>
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port, log_path = int(sys.argv[1]), sys.argv[2]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        rec = {"path": self.path, "content_type": self.headers.get("Content-Type"), "bytes": n}
        try:
            body = json.loads(raw)
            msgs = body.get("messages", [])
            rec["json"] = True
            rec["keys"] = sorted(body)
            rec["message_types"] = sorted({type(m.get("content")).__name__ for m in msgs})
            rec["user_text"] = msgs[-1]["content"] if msgs else ""
        except Exception:
            rec["json"] = False
        rec["binary_bytes"] = sum(1 for b in raw if b < 9 or 13 < b < 32)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        user = rec.get("user_text", "")
        m = re.search(r"<dictation>(.*)</dictation>", user, re.S)
        reply = m.group(1).strip() if m else "## Summary\n- (fake summary)\n## Next steps\n- [ ] (fake)"
        out = json.dumps({"choices": [{"message": {"role": "assistant", "content": reply}}],
                          "usage": {"prompt_tokens": len(user) // 4, "completion_tokens": len(reply) // 4}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
