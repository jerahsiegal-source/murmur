"""Score dictation cleanup against the real model.

Two sets:
  cases    tools/cleanup_eval/cases.json (made-up dictations with pass/fail checks; safe to commit)
  history  your own dictation history (%LOCALAPPDATA%\\Yappr\\history.jsonl). Results stay in
           data/eval/, which git ignores. Nothing from this set is ever written into the repo.

Each run can use the current code or the cleanup module from any git ref, so before/after can be
measured back to back on the same network:

  python tools/cleanup_eval/run.py cases --impl HEAD --label new --repeat 3
  python tools/cleanup_eval/run.py cases --impl ref:origin/main --label old --repeat 3
  python tools/cleanup_eval/run.py history --impl ref:origin/main --label old
  python tools/cleanup_eval/run.py compare old new

Uses the API key Yappr already has (Windows Credential Manager). Cost is about $0.0001 per call.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "eval"

FILLER_PATTERNS = {
    "um/uh": r"\b(?:u+m+|u+h+|e+r+m+)\b",
    "you know": r"\byou know\b(?!\s+(?:what|how|when|where|who|why|that|if|the|a|my|your|his|her|their|our|it|this|[A-Z]))",
    "basically": r"\bbasically\b",
    "sort of": r"\bsort of\b",
    "kind of (filler)": r"\bkind of\b(?=\s*,|\s+(?:like|just|maybe|really))",
    "like (filler)": r"(?:^|[.,!?]\s*)like,|,\s*like,|\blike,\s",
    "I mean (filler)": r"(?:^|[.!?]\s+)I mean,",
    "so yeah": r"\bso yeah\b",
    "repeated word": r"\b(\w+)\s+\1\b",
}
OPENER = re.compile(r"^\s*(sure|certainly|of course|here(?:'s| is| are)|i can(?:'t| not)|i'm sorry|as an ai|okay, here)\b", re.I)
LIST_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)]|\[[ x]\])\s+", re.M)
ENUM_CUES = re.compile(r"\b(first|second|third|step one|step two|number one|one,|two,|three,)\b", re.I)
STOP = set("""a an the and or but if then so to of in on at for with from by as is are was were be been it its this that
these those i you he she we they me my your our their them us do does did have has had will would can could should
just really very also not no yes there here what which who whom when where why how all any some about into out up
down over again more most other such only own same than too s t don't i'm it's that's i've we're you're""".split())


def norm(s: str) -> str:
    return s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def content_words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9'%$,.]*[a-z0-9%]|[a-z0-9]", norm(s).lower()) if w not in STOP and len(w) > 2]


def numbers(s: str) -> set[str]:
    return set(re.findall(r"\d[\d,.]*\d|\d", s))


def load_cleanup(impl: str) -> types.ModuleType:
    if impl == "HEAD" or impl == "working":
        import yappr.cleanup as m
        return m
    ref = impl.removeprefix("ref:")
    src = subprocess.run(["git", "show", f"{ref}:yappr/cleanup.py"], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    mod = types.ModuleType(f"cleanup_{re.sub(r'\W', '_', ref)}")
    mod.__dict__["__name__"] = mod.__name__
    sys.modules[mod.__name__] = mod
    exec(compile(src, f"{ref}:yappr/cleanup.py", "exec"), mod.__dict__)
    return mod


def make_cleaner(mod):
    from yappr.config import Store
    from yappr.llm import make_llm

    store = Store()
    s = store.settings
    s.use_llm_cleanup = True
    key = Store.get_api_key(s.llm_provider)
    if not key:
        sys.exit("No API key in Yappr's key store; add one in Settings first.")
    usage = OUT / "usage.jsonl"  # keep eval spend out of the app's own usage log
    llm = make_llm(s.llm_provider, s.llm_base_url, key, s.llm_model, s.price_in_per_m, s.price_out_per_m, usage)
    return mod.Cleaner(llm, store), s


def said_opener(raw: str, out: str) -> bool:
    """Output opens like an assistant reply ("Sure, here's...") and the speaker never said those words."""
    m = OPENER.search(norm(out))
    return bool(m) and m.group(0).strip().lower() not in norm(raw).lower()


def check_case(case: dict, text: str, how: str) -> list[str]:
    t = norm(text)
    fails = []
    for p in case.get("must", []):
        if not re.search(p, t, re.I):
            fails.append(f"missing /{p}/")
    for p in case.get("must_not", []):
        if re.search(p, t, re.I | re.M):
            fails.append(f"has /{p}/")
    lines = len(LIST_LINE.findall(t))
    if case.get("list") is True and lines < 2:
        fails.append("expected a list")
    if case.get("list") is False and lines >= 2:
        fails.append("made a list")
    if case.get("paras") is True and "\n\n" not in t:
        fails.append("expected paragraph breaks")
    if case.get("paras") is False and "\n\n" in t:
        fails.append("unexpected paragraph breaks")
    if said_opener(case["raw"], t):
        fails.append("answered instead of cleaning")
    return fails


def acted_on(raw: str, out: str) -> list[str]:
    """Signs the output is not a cleanup of the input (independent of the app's own guard)."""
    why = []
    if said_opener(raw, out):
        why.append("assistant opener")
    if len(LIST_LINE.findall(out)) >= 3 and not ENUM_CUES.search(raw):
        why.append("list not dictated")
    rw, ow = set(content_words(raw)), content_words(out)
    if ow:
        novel = sum(1 for w in ow if w not in rw) / len(ow)
        if novel > 0.35 and len(ow) >= 8:
            why.append(f"{novel:.0%} new words")
    return why


def lost(raw: str, out: str) -> list[str]:
    why = []
    miss_num = numbers(raw) - numbers(out)
    if miss_num:
        why.append(f"numbers missing: {sorted(miss_num)}")
    rw = [w for w in content_words(raw) if not w.isdigit()]
    if len(rw) >= 8:
        ow = set(content_words(out))
        recall = sum(1 for w in rw if w in ow) / len(rw)
        if recall < 0.75:
            why.append(f"only {recall:.0%} of content words kept")
    return why


def filler_count(s: str) -> dict:
    return {k: len(re.findall(p, norm(s), re.I | re.M)) for k, p in FILLER_PATTERNS.items()}


def run_cases(cleaner, repeat: int, file: str = "cases.json") -> dict:
    cases = json.loads((Path(__file__).parent / file).read_text(encoding="utf-8"))
    rows = []
    for rep in range(repeat):
        for c in cases:
            t = time.perf_counter()
            text, how = cleaner.clean(c["raw"])
            dt = time.perf_counter() - t
            fails = check_case(c, text, how)
            rows.append({"id": c["id"], "cat": c["cat"], "rep": rep, "how": how, "secs": round(dt, 3),
                         "words": len(c["raw"].split()), "fails": fails, "text": text})
            mark = "ok " if not fails else "FAIL"
            print(f"{mark} {c['id']:<24} {how:<5} {dt:5.2f}s {'; '.join(fails)}", flush=True)
    return {"set": "cases", "rows": rows}


def run_history(cleaner, limit: int) -> dict:
    p = Path(os.path.expandvars(r"%LOCALAPPDATA%\Yappr\history.jsonl"))
    hist = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    hist = [h for h in hist if len(h["raw"].split()) >= 4][-limit:]
    rows = []
    for i, h in enumerate(hist):
        t = time.perf_counter()
        text, how = cleaner.clean(h["raw"])
        dt = time.perf_counter() - t
        rows.append({"i": i, "how": how, "secs": round(dt, 3), "words": len(h["raw"].split()),
                     "fill_raw": filler_count(h["raw"]), "fill_out": filler_count(text),
                     "acted": acted_on(h["raw"], text), "lost": lost(h["raw"], text),
                     "raw": h["raw"], "text": text})
        flag = " ".join(rows[-1]["acted"] + rows[-1]["lost"])
        print(f"{i:3d} {how:<5} {dt:5.2f}s {len(h['raw'].split()):4d}w {flag}", flush=True)
    return {"set": "history", "rows": rows}


def run_speed(impls: list[str], repeat: int, limit: int) -> None:
    """Old and new alternate on every input, so network drift hits both equally."""
    cleaners = [make_cleaner(load_cleanup(i))[0] for i in impls]
    cases = [c["raw"] for c in json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))]
    p = Path(os.path.expandvars(r"%LOCALAPPDATA%\Yappr\history.jsonl"))
    if p.exists():
        cases += [json.loads(l)["raw"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()][-limit:]
    cases = [c for c in cases if len(c.split()) >= 4]
    times = {i: [] for i in impls}
    for rep in range(repeat):
        for n, raw in enumerate(cases):
            order = impls if (n + rep) % 2 == 0 else impls[::-1]
            for impl in order:
                cl = cleaners[impls.index(impl)]
                t = time.perf_counter()
                _, how = cl.clean(raw)
                times[impl].append({"n": n, "rep": rep, "secs": time.perf_counter() - t, "words": len(raw.split()), "how": how})
    res = {i: timing(v) for i, v in times.items()}
    # paired: per input, new minus old (median over repeats), so drift between inputs cancels out
    a, b = impls[0], impls[-1]
    for name, keep in (("short <40w", lambda w: w < 40), ("long >=40w", lambda w: w >= 40)):
        diffs = []
        for n in {r["n"] for r in times[a] if keep(r["words"])}:
            ta = statistics.median(r["secs"] for r in times[a] if r["n"] == n)
            tb = statistics.median(r["secs"] for r in times[b] if r["n"] == n)
            diffs.append(tb - ta)
        res.setdefault("paired new-old", {})[name] = {"n": len(diffs), "median_diff_s": round(statistics.median(diffs), 3),
                                                      "mean_diff_s": round(statistics.mean(diffs), 3)}
    res["raw"] = times
    (OUT / "speed.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "raw"}, indent=1))


def timing(rows: list[dict]) -> dict:
    out = {}
    for name, sel in (("all", rows), ("short <40w", [r for r in rows if r["words"] < 40]),
                      ("long >=40w", [r for r in rows if r["words"] >= 40])):
        xs = sorted(r["secs"] for r in sel if r["how"] != "empty")  # what the user waits for, fast path included
        if xs:
            out[name] = {"n": len(xs), "median": round(statistics.median(xs), 2),
                         "p90": round(xs[min(len(xs) - 1, int(len(xs) * 0.9))], 2), "max": round(xs[-1], 2)}
    return out


def summarize(res: dict) -> dict:
    rows = res["rows"]
    s = {"set": res["set"], "n": len(rows), "fallbacks": sum(r["how"] != "llm" for r in rows), "timing": timing(rows)}
    if res["set"] == "cases":
        cats = {}
        for r in rows:
            c = cats.setdefault(r["cat"], [0, 0])
            c[0] += not r["fails"]
            c[1] += 1
        s["pass"] = {k: f"{a}/{b}" for k, (a, b) in cats.items()}
        s["pass_total"] = f"{sum(not r['fails'] for r in rows)}/{len(rows)}"
    else:
        tot = {}
        for r in rows:
            for k, v in r["fill_out"].items():
                tot[k] = tot.get(k, 0) + v
        s["filler_left"] = tot
        s["filler_left_total"] = sum(tot.values())
        s["filler_in_raw_total"] = sum(sum(r["fill_raw"].values()) for r in rows)
        s["acted_on"] = sum(bool(r["acted"]) for r in rows)
        s["lost_flags"] = sum(bool(r["lost"]) for r in rows)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set", choices=["cases", "history", "compare", "speed"])
    ap.add_argument("labels", nargs="*")
    ap.add_argument("--impl", default="HEAD", help="HEAD (working tree) or ref:<git ref>")
    ap.add_argument("--label", default="run")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--file", default="cases.json", help="cases file in this folder (cases.json or holdout.json)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.set == "compare":
        for st in ("cases", "history"):
            for lab in a.labels:
                f = OUT / f"{lab}-{st}.json"
                if f.exists():
                    print(st, lab, json.dumps(summarize(json.loads(f.read_text(encoding="utf-8"))), indent=1))
        return
    if a.set == "speed":
        return run_speed(a.labels or ["ref:origin/main", "HEAD"], a.repeat, a.limit)
    cleaner, _ = make_cleaner(load_cleanup(a.impl))
    res = run_cases(cleaner, a.repeat, a.file) if a.set == "cases" else run_history(cleaner, a.limit)
    res["impl"] = a.impl
    (OUT / f"{a.label}-{a.set}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(summarize(res), indent=1))


if __name__ == "__main__":
    main()
