"""Helper process: owns the keyboard hook and prints events to stdout, one per line.

Reads commands from stdin ("reset", "copy <vk>"); exits when stdin closes (i.e. when Murmur exits).
"""
import sys
import threading

from .hotkeys import KeyboardHook


def main() -> None:
    out_lock = threading.Lock()

    def emit(e: str) -> None:
        with out_lock:
            sys.stdout.write(e + "\n")
            sys.stdout.flush()

    hook = KeyboardHook(emit)
    hook.start()
    emit("ready")
    for line in sys.stdin:
        cmd = line.split()
        if cmd == ["reset"]:
            hook.reset()
        elif len(cmd) == 2 and cmd[0] == "copy" and cmd[1].isdigit():
            try:
                hook.copy(int(cmd[1]))
            except Exception:
                pass
    hook.stop()


if __name__ == "__main__":
    main()
