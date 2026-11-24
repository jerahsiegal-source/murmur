"""Murmur — local-first hotkey dictation and meeting notes for Windows."""
import os

# numpy's BLAS would otherwise reserve a buffer per CPU thread (~500 MB of committed memory);
# Murmur's numpy work is tiny, and the speech engine has its own thread pool.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

__version__ = "0.1.0"
