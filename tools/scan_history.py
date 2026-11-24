"""Scan for secrets, personal data, recordings and user data files before they reach GitHub.

Usage:
  python tools/scan_history.py            every blob in all of git history (CI runs this)
  python tools/scan_history.py --staged   only what is staged for the next commit (the pre-commit hook)

Exit code 1 if anything is found.
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
    "Google OAuth refresh token": r"1//0[0-9A-Za-z_\-]{30,}",
    "Google OAuth client secret": r"GOCSPX-[0-9A-Za-z_\-]{20,}",
    "Google iCal secret URL": r"calendar\.google\.com/calendar/ical/[^\s\"']+/private-[0-9a-f]+",
    "email address": r"[A-Za-z0-9._%+\-]+@(?!anthropic\.com|local\b|example\.com)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
    "Windows user path": r"[Cc]:[\/]+Users[\/]+(?!<|\{)[A-Za-z0-9_.\-]+",
}
BAD_FILES = re.compile(r"\.(wav|flac|mp3|ogg|m4a)$|(^|/)(history\.jsonl|usage\.jsonl|dictionary\.json|settings\.json|transcript\.md|summary\.md|\.env|google-client\.json|client_secret[^/]*\.json)$|(^|/)data/")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, check=True)


def scan_text(path: str, data: str, findings: list) -> None:
    for name, pat in PATTERNS.items():
        for m in re.finditer(pat, data):
            findings.append((name, path, m.group(0)[:12] + "..."))  # never print the whole secret


def scan_staged(findings: list) -> int:
    paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").stdout.decode("utf-8").split("\0")
    paths = [p for p in paths if p]
    for path in paths:
        if BAD_FILES.search(path):
            findings.append(("user-data/recording file", path, ""))
            continue
        scan_text(path, git("show", f":{path}").stdout.decode("utf-8", "replace"), findings)
    return len(paths)


def scan_history(findings: list) -> int:
    objs = git("rev-list", "--objects", "--all").stdout.decode("utf-8").splitlines()
    seen = set()
    for line in objs:
        sha, _, path = line.partition(" ")
        if not path or sha in seen:
            continue
        seen.add(sha)
        if BAD_FILES.search(path):
            findings.append(("user-data/recording file", path, ""))
            continue
        if git("cat-file", "-t", sha).stdout.decode().strip() != "blob":
            continue
        scan_text(path, git("cat-file", "-p", sha).stdout.decode("utf-8", "replace"), findings)
    return len(seen)


def main() -> int:
    findings: list = []
    if "--staged" in sys.argv[1:]:
        n = scan_staged(findings)
        print(f"scanned {n} staged files")
    else:
        n = scan_history(findings)
        authors = set(git("log", "--all", "--format=%an <%ae>|%cn <%ce>").stdout.decode("utf-8")
                      .replace("|", "\n").split("\n")) - {""}
        print(f"scanned {n} objects across all commits")
        print("commit identities in history:", sorted(authors))
    for f in findings:
        print("FOUND", *f)
    if findings:
        print("\nRemove these before committing. If one is a real API key, revoke it in your provider's console:"
              " deleting it from the file does not make a leaked key safe again.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
