"""Start Yappr from this checkout on a clean, throwaway profile (first run), with a fake mic and the
Ctrl+Shift test chord so other dictation apps aren't triggered. Stops any running Yappr first.

    python tools/run_fresh.py <data dir> <fake mic wav>
"""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from measure_quick import VENV_PYW, yappr_procs  # noqa: E402

data, wav = sys.argv[1], sys.argv[2]
for p in yappr_procs() + yappr_procs("yappr.hotkey_host") + yappr_procs("yappr.window"):
    p.kill()
time.sleep(1)
import tempfile  # noqa: E402

env = dict(os.environ, YAPPR_DATA_DIR=data, YAPPR_FAKE_MIC=wav, YAPPR_TEST_CHORD="ctrl+shift",
           YAPPR_WINDOW_TEST_DIR=str(Path(tempfile.gettempdir()) / "yappr-window-test"))
subprocess.Popen([VENV_PYW, "-m", "yappr"], cwd=str(Path(__file__).resolve().parents[1]), env=env,
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
print("started")
