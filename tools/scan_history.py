"""Scan every blob in git history for secrets, personal data, recordings and user data files.

Usage: python tools/scan_history.py   (exit code 1 if anything is found)
"""
import re
import subprocess
import sys

PATTERNS = {
    "OpenAI-style key": r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "Google API key": r"AIza[0-9A-Za-z_\-]{35}",
    "AWS key": r"AKIA[0-9A-Z]{16}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "Slack token": r"xox[abpr]-[A-Za-z0-9\-]{10,}",
    "Bearer token literal": r"Bearer [A-Za-z0-9_\-\.]{20,}",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "Google iCal secret URL": r"calendar\.google\.com/calendar/ical/[^\s\"']+/private-[0-9a-f]+",
    "email address": r"[A-Za-z0-9._%+\-]+@(?!anthropic\.com|local\b|example\.com)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
    "Windows user path": r"[Cc]:[\/]+Users[\/]+(?!<|\{)[A-Za-z0-9_.\-]+",
}
BAD_FILES = re.compile(r"\.(wav|flac|mp3|ogg|m4a)$|(^|/)(history\.jsonl|usage\.jsonl|dictionary\.json|settings\.json|transcript\.md|summary\.md|\.env)$|(^|/)data/")

objs = subprocess.run(["git", "rev-list", "--objects", "--all"], capture_output=True, text=True, check=True).stdout.splitlines()
findings = []
seen = set()
for line in objs:
    sha, _, path = line.partition(" ")
    if not path or sha in seen:
        continue
    seen.add(sha)
    if BAD_FILES.search(path):
        findings.append(("user-data/recording file", path, ""))
        continue
    if subprocess.run(["git", "cat-file", "-t", sha], capture_output=True, text=True).stdout.strip() != "blob":
        continue
    data = subprocess.run(["git", "cat-file", "-p", sha], capture_output=True).stdout.decode("utf-8", "replace")
    for name, pat in PATTERNS.items():
        for m in re.finditer(pat, data):
            findings.append((name, path, m.group(0)[:12] + "…"))
authors = set(subprocess.run(["git", "log", "--all", "--format=%an <%ae>|%cn <%ce>"], capture_output=True, text=True).stdout.replace("|", "\n").split("\n")) - {""}
print(f"scanned {len(seen)} objects across all commits")
for f in findings:
    print("FOUND", *f)
print("commit identities in history:", sorted(authors))
sys.exit(1 if findings else 0)
