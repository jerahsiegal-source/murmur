"""Settings window: AI key/model, dictionary, meetings & calendar, history, general."""
from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import storage
from .config import PROVIDER_DEFAULTS, Store
from .llm import PROVIDERS, usage_summary

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command() -> str:
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe") if exe.name.lower() == "python.exe" else exe
    return f'"{pyw}" -m murmur'


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "Murmur")
            return True
    except OSError:
        return False


def set_startup(on: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, "Murmur", 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, "Murmur")
            except OSError:
                pass


class SettingsWindow:
    def __init__(self, root: tk.Tk, app):
        self.app = app
        self.store: Store = app.store
        s = self.store.settings
        self.win = tk.Toplevel(root)
        self.win.title("Murmur settings")
        self.win.geometry("640x520")
        self.win.minsize(560, 460)
        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.vars: dict[str, tk.Variable] = {}

        # ---------------- AI
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="AI cleanup")
        self.provider = s.llm_provider if s.llm_provider in PROVIDERS else "claude"
        self._keys = {p: Store.get_api_key(p) for p in PROVIDERS}  # what's stored, per provider
        self._initial_keys = dict(self._keys)
        self.provider_var = tk.StringVar(value=PROVIDERS[self.provider])
        combo = ttk.Combobox(f, textvariable=self.provider_var, values=list(PROVIDERS.values()), state="readonly", width=30)
        self._row(f, 0, "Provider", combo)
        combo.bind("<<ComboboxSelected>>", self._provider_changed)
        self.key_var = tk.StringVar(value=self._keys[self.provider])
        self._row(f, 1, "API key", ttk.Entry(f, textvariable=self.key_var, show="•", width=50))
        self.key_hint = ttk.Label(f, text="", foreground="#666", wraplength=430)
        self.key_hint.grid(row=2, column=1, columnspan=2, sticky="w")
        self.vars["llm_base_url"] = tk.StringVar(value=s.llm_base_url)
        self.base_entry = ttk.Entry(f, textvariable=self.vars["llm_base_url"], width=40)
        self._row(f, 3, "Base URL", self.base_entry, hint="(OpenAI-compatible only)")
        self._entry(f, 4, "Model", "llm_model", s.llm_model)
        self._provider_ui()
        self._entry(f, 5, "Summary model", "llm_summary_model", s.llm_summary_model, hint="(blank = same)")
        self._entry(f, 6, "$ / 1M input tokens", "price_in_per_m", s.price_in_per_m, kind=tk.DoubleVar, width=10)
        self._entry(f, 7, "$ / 1M output tokens", "price_out_per_m", s.price_out_per_m, kind=tk.DoubleVar, width=10)
        self._check(f, 8, "Use AI cleanup for dictation (otherwise local rules only)", "use_llm_cleanup", s.use_llm_cleanup)
        ttk.Button(f, text="Test connection", command=self._test_llm).grid(row=9, column=1, sticky="w", pady=6)
        self.test_lbl = ttk.Label(f, text="", wraplength=420)
        self.test_lbl.grid(row=10, column=1, sticky="w")
        u = usage_summary(self.store.root / "usage.jsonl")
        ttk.Label(f, text=(f"Last 30 days: {u['calls']} calls, ${u['usd']:.4f}  ·  projected per month: "
                           f"${u['projected_month_usd']:.2f}")).grid(row=11, column=1, sticky="w", pady=(12, 0))

        # ---------------- Dictionary
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="Dictionary")
        ttk.Label(f, text="Words to always spell your way. 'Sounds like' = what the transcript tends to write instead (comma-separated).",
                  wraplength=580).pack(anchor="w")
        self.tree = ttk.Treeview(f, columns=("word", "alias"), show="headings", height=10)
        self.tree.heading("word", text="Word")
        self.tree.heading("alias", text="Sounds like")
        self.tree.column("word", width=180)
        self.tree.pack(fill="both", expand=True, pady=6)
        for e in self.store.dictionary:
            self.tree.insert("", "end", values=(e["word"], ", ".join(e["sounds_like"])))
        labels = ttk.Frame(f)
        labels.pack(fill="x")
        ttk.Label(labels, text="Word", width=20).pack(side="left")
        ttk.Label(labels, text="Sounds like (optional, comma-separated)").pack(side="left", padx=6)
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.word_var, self.alias_var = tk.StringVar(), tk.StringVar()
        ttk.Entry(row, textvariable=self.word_var, width=20).pack(side="left")
        ttk.Entry(row, textvariable=self.alias_var, width=36).pack(side="left", padx=6)
        ttk.Button(row, text="Add / update", command=self._dict_add).pack(side="left")
        ttk.Button(row, text="Remove", command=self._dict_remove).pack(side="left", padx=6)
        self.tree.bind("<<TreeviewSelect>>", self._dict_select)

        # ---------------- Meetings
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="Meetings")
        self._entry(f, 0, "Notes folder", "meetings_dir", s.meetings_dir, width=46)
        ttk.Button(f, text="Browse…", command=self._browse).grid(row=0, column=2, padx=4)
        ttk.Label(f, text="Tip: pick a folder inside Google Drive for desktop to back notes up automatically.",
                  foreground="#666").grid(row=1, column=1, columnspan=2, sticky="w")
        self._entry(f, 2, "Keep notes & history (days)", "retention_days", s.retention_days, kind=tk.IntVar, width=8,
                    hint="minimum 1")
        self._entry(f, 3, "Calendar iCal address", "calendar_ics_url", s.calendar_ics_url, width=46, show="•")
        ttk.Label(f, text="Google Calendar → Settings → your calendar → 'Secret address in iCal format'.",
                  foreground="#666").grid(row=4, column=1, columnspan=2, sticky="w")
        self._entry(f, 5, "Prompt minutes before start", "calendar_prompt_min_before", s.calendar_prompt_min_before,
                    kind=tk.DoubleVar, width=8)
        self.mlist = tk.Listbox(f, height=8)
        self.mlist.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(10, 4))
        f.rowconfigure(6, weight=1)
        f.columnconfigure(1, weight=1)
        self._meeting_dirs = self.app.finished_meeting_dirs()[:50]
        for d in self._meeting_dirs:
            self.mlist.insert("end", d.name)
        row = ttk.Frame(f)
        row.grid(row=7, column=0, columnspan=3, sticky="w")
        ttk.Button(row, text="Open notes", command=self._open_meeting).pack(side="left")
        ttk.Button(row, text="Summarize again", command=self._resummarize).pack(side="left", padx=6)
        ttk.Button(row, text="Open folder", command=self.app.open_meetings_folder).pack(side="left")

        # ---------------- History
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="History")
        self.hist = storage.read_history(self.store.root, 100)
        self.hlist = tk.Listbox(f, height=8)
        self.hlist.pack(fill="x")
        for h in self.hist:
            self.hlist.insert("end", f"{h['ts'][:16].replace('T', ' ')}  ·  {h.get('text', '')[:70]}")
        self.htext = tk.Text(f, height=10, wrap="word")
        self.htext.pack(fill="both", expand=True, pady=6)
        self.hlist.bind("<<ListboxSelect>>", self._hist_select)
        ttk.Button(f, text="Copy cleaned text", command=self._hist_copy).pack(anchor="w")

        # ---------------- General
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="General")
        self.startup_var = tk.BooleanVar(value=startup_enabled())
        ttk.Checkbutton(f, text="Start Murmur when Windows starts", variable=self.startup_var).grid(row=0, column=0, columnspan=2, sticky="w")
        self._check(f, 1, "Show the floating bar", "show_bar", s.show_bar)
        mics = [""] + self._input_devices()
        self.vars["mic_device"] = tk.StringVar(value=s.mic_device)
        self._row(f, 2, "Microphone", ttk.Combobox(f, textvariable=self.vars["mic_device"], values=mics, width=44))
        ttk.Label(f, text="(blank = Windows default)", foreground="#666").grid(row=3, column=1, sticky="w")
        self._entry(f, 4, "Unload speech model after idle (min)", "stt_idle_unload_min", s.stt_idle_unload_min,
                    kind=tk.DoubleVar, width=8, hint="0 = keep loaded")
        ttk.Label(f, text=("Hotkeys: hold Ctrl+Win to dictate · Ctrl+Win then Space for hands-free · "
                           "Ctrl+Win to stop · Alt+Shift+Z pastes the last result"), wraplength=560,
                  foreground="#444").grid(row=6, column=0, columnspan=3, sticky="w", pady=(16, 0))

        bottom = ttk.Frame(self.win)
        bottom.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bottom, text="Save", command=self.save).pack(side="right")
        ttk.Button(bottom, text="Close", command=self.win.destroy).pack(side="right", padx=6)
        self.win.lift()
        self.win.focus_force()

    # ---- helpers
    def alive(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def focus(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def _row(self, f, r, label, widget, hint=""):
        ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
        widget.grid(row=r, column=1, sticky="w", pady=3)
        if hint:
            ttk.Label(f, text=hint, foreground="#666").grid(row=r, column=2, sticky="w")

    def _entry(self, f, r, label, name, value, kind=tk.StringVar, width=40, hint="", show=""):
        v = kind(value=value)
        self.vars[name] = v
        self._row(f, r, label, ttk.Entry(f, textvariable=v, width=width, show=show), hint)

    def _check(self, f, r, label, name, value):
        v = tk.BooleanVar(value=value)
        self.vars[name] = v
        ttk.Checkbutton(f, text=label, variable=v).grid(row=r, column=0, columnspan=2, sticky="w", pady=3)

    @staticmethod
    def _input_devices() -> list[str]:
        try:
            import sounddevice as sd

            api = next(i for i, a in enumerate(sd.query_hostapis()) if "MME" in a["name"])
            return sorted({f"{d['name']}, MME" for d in sd.query_devices() if d["max_input_channels"] > 0 and d["hostapi"] == api})
        except Exception:
            return []

    # ---- actions
    def save(self) -> None:
        s = self.store.settings
        try:
            for name, v in self.vars.items():
                setattr(s, name, v.get())
        except tk.TclError as e:
            messagebox.showerror("Murmur", f"Invalid value: {e}", parent=self.win)
            return
        s.retention_days = max(1, int(s.retention_days))
        if self.vars.get("retention_days") is not None:
            self.vars["retention_days"].set(s.retention_days)
        s.llm_provider = self.provider
        self.store.save_settings()
        self._keys[self.provider] = self.key_var.get().strip()
        for p, key in self._keys.items():  # only write keys the user actually changed
            if key != self._initial_keys.get(p):
                Store.set_api_key(key, p)
                self._initial_keys[p] = key
        set_startup(self.startup_var.get())
        entries = []
        for iid in self.tree.get_children():
            w, a = self.tree.item(iid, "values")
            entries.append({"word": w, "sounds_like": [x.strip() for x in str(a).split(",") if x.strip()]})
        self.store.save_dictionary(entries)
        if s.show_bar:
            self.app.bar.win.deiconify()
        else:
            self.app.bar.win.withdraw()
        self.app.reload_settings()
        self.win.title("Murmur settings — saved")

    def _test_llm(self) -> None:
        from .cleanup import SYSTEM_PROMPT
        from .llm import make_llm

        client = make_llm(self.provider, self.vars["llm_base_url"].get(), self.key_var.get().strip(),
                          self.vars["llm_model"].get(), self.vars["price_in_per_m"].get(),
                          self.vars["price_out_per_m"].get(), self.store.root / "usage.jsonl")
        self.test_lbl.config(text="Testing…")

        def run():
            t = time.monotonic()
            try:
                out = client.chat(SYSTEM_PROMPT.format(terms="(none)"),
                                  "<dictation>um so this is uh a quick test of the the cleanup</dictation>",
                                  kind="test", timeout=15)
                msg = f"OK in {time.monotonic() - t:.2f}s → {out}"
            except Exception as e:
                msg = f"Failed: {e}"
            self.app.bar.post(lambda: self.test_lbl.config(text=msg))

        threading.Thread(target=run, daemon=True).start()

    def _provider_ui(self) -> None:
        claude = self.provider == "claude"
        self.base_entry.configure(state="disabled" if claude else "normal")
        where = "console.anthropic.com → API keys" if claude else "your provider's dashboard"
        self.key_hint.config(text=f"Get one at {where}. Stored in Windows Credential Manager, never in a file.")

    def _provider_changed(self, _e=None) -> None:
        new = next(k for k, v in PROVIDERS.items() if v == self.provider_var.get())
        if new == self.provider:
            return
        self._keys[self.provider] = self.key_var.get().strip()  # keep what was typed for the old one
        old_default = PROVIDER_DEFAULTS[self.provider][0]
        self.provider = new
        self.key_var.set(self._keys.get(new, ""))
        model = self.vars["llm_model"].get().strip()
        if not model or model == old_default:  # switch model + prices to the new provider's defaults
            m, pin, pout = PROVIDER_DEFAULTS[new]
            self.vars["llm_model"].set(m)
            self.vars["price_in_per_m"].set(pin)
            self.vars["price_out_per_m"].set(pout)
        self._provider_ui()

    def _dict_select(self, _e=None):
        sel = self.tree.selection()
        if sel:
            w, a = self.tree.item(sel[0], "values")
            self.word_var.set(w)
            self.alias_var.set(a)

    def _dict_add(self):
        w = self.word_var.get().strip()
        if not w:
            return
        a = self.alias_var.get().strip()
        for iid in self.tree.get_children():
            if self.tree.item(iid, "values")[0].lower() == w.lower():
                self.tree.item(iid, values=(w, a))
                break
        else:
            self.tree.insert("", "end", values=(w, a))
        self.word_var.set("")
        self.alias_var.set("")
        self.save()

    def _dict_remove(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
        self.save()

    def _browse(self):
        d = filedialog.askdirectory(parent=self.win, initialdir=self.vars["meetings_dir"].get())
        if d:
            self.vars["meetings_dir"].set(d)

    def _selected_meeting(self) -> Path | None:
        sel = self.mlist.curselection()
        return self._meeting_dirs[sel[0]] if sel else None

    def _open_meeting(self):
        d = self._selected_meeting()
        if d:
            target = d / "summary.md" if (d / "summary.md").exists() else d
            os.startfile(target)

    def _resummarize(self):
        d = self._selected_meeting()
        if not d:
            return
        from .meeting import summarize_folder

        def run():
            try:
                summarize_folder(d, self.app.llm, self.store.settings, [e['word'] for e in self.store.dictionary])
                self.app.bar.toast("Summary updated")
            except Exception as e:
                self.app.bar.toast(f"Summary failed: {e}"[:60], 4)

        threading.Thread(target=run, daemon=True).start()

    def _hist_select(self, _e=None):
        sel = self.hlist.curselection()
        if not sel:
            return
        h = self.hist[sel[0]]
        self.htext.delete("1.0", "end")
        self.htext.insert("end", f"CLEANED ({h.get('method')}, ready {h.get('ready_s')}s):\n{h.get('text', '')}\n\nRAW:\n{h.get('raw', '')}")

    def _hist_copy(self):
        sel = self.hlist.curselection()
        if sel:
            self.win.clipboard_clear()
            self.win.clipboard_append(self.hist[sel[0]].get("text", ""))
