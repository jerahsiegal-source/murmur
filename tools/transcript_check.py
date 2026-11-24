"""Compare a meeting transcript.md against the synthetic script.json.

Reports word accuracy per speaker (1 - WER, via difflib alignment), whether the planted
first/last facts are present, and the transcript's time span.

Usage: python tools/transcript_check.py <script.json> <transcript.md>
"""
import difflib
import json
import re
import sys

script = json.load(open(sys.argv[1], encoding="utf-8"))
text = open(sys.argv[2], encoding="utf-8").read()


def words(s):
    s = s.lower().replace("-", " ")
    return re.findall(r"[a-z0-9']+", s)


NUM = {"3": "third", "3rd": "third", "12": "twelfth", "12th": "twelfth", "2": "second", "2nd": "second"}
ref = {"Me": [], "Others": []}
for t in script:
    ref["Me" if t["who"] == "me" else "Others"] += words(t["text"])
hyp = {"Me": [], "Others": []}
times = []
for m in re.finditer(r"^\[(\d+):(\d\d):(\d\d)\] \*\*(Me|Others):\*\* (.*)$", text, re.M):
    h, mi, se, who, body = m.groups()
    times.append(int(h) * 3600 + int(mi) * 60 + int(se))
    hyp[who] += words(body)

for who in ("Me", "Others"):
    r, h = ref[who], [NUM.get(w, w) for w in hyp[who]]
    sm = difflib.SequenceMatcher(None, r, h, autojunk=False)
    match = sum(b.size for b in sm.get_matching_blocks())
    print(f"{who}: ref {len(r)} words, hyp {len(h)} words, matched {match} -> word accuracy ~{match / max(1, len(r)):.1%}")

low = text.lower()
for fact in ["statement of work", "northwind", "forty two thousand|42,000|42 thousand|\\$42", "denver",
             "okafor|okefor|okafa", "january 12", "february 2", "lisbon"]:
    print(f"  fact {fact!r}: {'present' if re.search(fact, low) else 'MISSING'}")
print(f"transcript spans {min(times) // 60}:{min(times) % 60:02d} -> {max(times) // 60}:{max(times) % 60:02d} (mm:ss), {len(times)} paragraphs")
