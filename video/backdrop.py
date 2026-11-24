"""A plain full-screen backdrop that hides the desktop while recording. Closes itself after a time
limit or on Escape. A small square in the top-left corner flips colour when <trigger> appears, and the
moment is written to <trigger>.time, so the recording can be lined up with the event log."""
import ctypes
import sys
import time
import tkinter as tk
from pathlib import Path

ctypes.windll.shcore.SetProcessDpiAwareness(2)
trigger, limit = Path(sys.argv[1]), float(sys.argv[2])
root = tk.Tk()
root.title("Yappr demo backdrop")
root.overrideredirect(True)
w, h = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{w}x{h}+0+0")
root.configure(bg="#f3e6c9")
root.attributes("-topmost", True)
sq = tk.Frame(root, bg="#000000", width=24, height=24)
sq.place(x=0, y=0)
t0 = time.time()


def poll():
    if trigger.exists() and sq["bg"] == "#000000":
        sq.configure(bg="#ffffff")
        root.update_idletasks()
        Path(str(trigger) + ".time").write_text(repr(time.time()))
    if time.time() - t0 > limit:
        root.destroy()
        return
    root.after(4, poll)


root.bind("<Escape>", lambda e: root.destroy())
root.after(4, poll)
root.mainloop()
