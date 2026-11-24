"""Test target: a focused text box that records when text arrives (wall-clock) to a JSON file."""
import json, sys, time, tkinter as tk

out = sys.argv[1]
root = tk.Tk()
root.title("Murmur paste target")
root.geometry("700x300+200+200")
t = tk.Text(root, wrap="word", font=("Segoe UI", 11))
t.pack(fill="both", expand=True)
state = {"first_change": None, "text": ""}

def poll():
    txt = t.get("1.0", "end-1c")
    if txt != state["text"]:
        if state["first_change"] is None:
            state["first_change"] = time.time()
        state["text"] = txt
        json.dump(state, open(out, "w"))
    root.after(5, poll)

def grab():
    root.lift(); root.attributes("-topmost", True); root.focus_force(); t.focus_set()
root.after(200, grab)
root.after(5, poll)
root.mainloop()
