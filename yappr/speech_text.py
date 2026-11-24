"""Turn highlighted text (often AI output) into something pleasant to listen to.

- File paths are read as just the file name ("C:\\...\\yappr\\app.py:42" -> "app.py").
- URLs are read as the site name ("https://www.github.com/a/b" -> "github.com").
- Markdown symbols (**, #, bullets, table pipes, backticks, links) are not read out.
- Fenced code blocks inside prose are replaced by "Code block." (read in full if the
  whole selection is code).

`chunks()` then splits the result into short pieces so the first words can be spoken
almost immediately while the rest is synthesized in the background.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- paths + URLs
_EXT = r"\.[A-Za-z0-9]{1,8}"
_URL = re.compile(r"\b(?:https?://|ftp://|www\.)[^\s<>()\[\]\"'`]+", re.I)
# Windows drive or UNC path; may continue through spaces only if quoted (handled separately)
_WIN_PATH = re.compile(r"(?<![\w/])(?:[A-Za-z]:[\\/]|\\\\[\w.$-]+\\)[^\s\"'`<>|*?]*")
# Unix-ish: /a/b, ~/a, ./a, ../a  or  a/b/c  or  a/b.ext
_UNIX_PATH = re.compile(
    r"(?<![\w:/.\\-])"
    r"(?:"
    r"(?:~|\.{1,2})?/[\w.@+-]+(?:/[\w.@+-]*)+"  # /a/b, ~/a/b, ./a/b
    r"|(?:~|\.{1,2})/[\w.@+-]+"  # ~/a, ./a
    r"|[\w.@+-]+(?:/[\w.@+-]+)+/(?![\w.])"  # a/b/ (folder, trailing slash)
    # a/b.py, a/b/c.py -- needs a file extension, so prose like "pros/cons/risks" is left alone
    r"|[\w@+-][\w.@+-]*(?:/[\w.@+-]+)*/[\w.@+-]*" + _EXT + r"(?![\w/])"
    r")"
    r"(?::\d+(?::\d+)?(?:-\d+)?)?"  # :line[:col]
)
# relative Windows path: .venv\Scripts\Activate.ps1, src\app\main.py
_REL_WIN_PATH = re.compile(r"(?<![\w\\/:])(?:\.{1,2}\\|[\w.@+-]+\\)[^\s\"'`<>|*?]+")
_LINE_SUFFIX = re.compile(r":\d+(?::\d+)?(?:-\d+)?$")
_QUOTED = re.compile(r"(`+|\")([^`\"\n]{2,400}?)\1")


def _looks_like_path(s: str) -> bool:
    s = s.strip()
    if " " in s and not re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|~?/|\.{1,2}/)", s):
        return False
    return bool(_WIN_PATH.fullmatch(s) or re.fullmatch(r"(?:[A-Za-z]:[\\/]|\\\\)[^\n\"`<>|*?]*", s)
                or _UNIX_PATH.fullmatch(s))


def file_name(path: str) -> str:
    """Last meaningful component of a path, without :line suffixes or trailing separators."""
    p = _LINE_SUFFIX.sub("", path.strip()).rstrip("\\/")
    if re.fullmatch(r"[A-Za-z]:", p):  # bare drive
        return p[0] + " drive"
    p = p.rstrip(".,;:")
    parts = [x for x in re.split(r"[\\/]", p) if x]
    if not parts:
        return ""
    return parts[-1]


def site_name(url: str) -> str:
    u = re.sub(r"^(?:https?|ftp)://", "", url.strip(), flags=re.I)
    host = re.split(r"[/?#]", u, 1)[0]
    host = re.sub(r"^www\.", "", host, flags=re.I).split("@")[-1]
    host = re.sub(r":\d+$", "", host)
    return host.rstrip(".,;:")


def _paths_and_urls(text: str) -> str:
    # quoted / backticked paths may contain spaces: `D:\home\me\Text to speech tool`
    def quoted(m: re.Match) -> str:
        inner = m.group(2)
        if _URL.fullmatch(inner.strip()):
            return site_name(inner)
        if _looks_like_path(inner):
            return file_name(inner)
        return m.group(0)

    text = re.sub(r"<((?:https?|ftp)://[^>\s]+)>", r"\1", text)  # markdown autolinks
    text = _QUOTED.sub(quoted, text)
    text = _URL.sub(lambda m: site_name(m.group(0).rstrip(".,;:!?)")) + _trail(m.group(0)), text)
    text = _WIN_PATH.sub(lambda m: file_name(m.group(0)) + _trail(m.group(0)), text)
    text = _REL_WIN_PATH.sub(lambda m: file_name(m.group(0)) + _trail(m.group(0)), text)

    def unix(m: re.Match) -> str:
        s = m.group(0)
        core = _LINE_SUFFIX.sub("", s)
        # leave fractions/dates and "and/or" style word pairs alone
        if re.fullmatch(r"[\d/.-]+", core):
            return s
        return file_name(s) + _trail(s)

    return _UNIX_PATH.sub(unix, text)


def _trail(s: str) -> str:
    """Sentence punctuation that the path/URL regex swallowed."""
    m = re.search(r"[.,;:!?)]+$", s)
    if not m or _LINE_SUFFIX.search(s):
        return ""
    return m.group(0) if not re.search(r"\.[A-Za-z0-9]{1,8}$", s) else ""


# ---------------------------------------------------------------- markdown
_FENCE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n(.*?)(?:^[ \t]*\1[ \t]*$|\Z)", re.S | re.M)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2B00-\u2BFF\uFE0F\u200D\u20E3]"
)
_SYMBOLS = [
    (re.compile(r"\s*(?:->|→|=>|⇒|⟶)\s*"), " to "),
    (re.compile(r"\s*(?:<-|←)\s*"), " from "),
    (re.compile(r"(?<=\s)&(?=\s)"), "and"),
    (re.compile(r"\b([CF])#(?!\w)"), r"\1 sharp"),
    (re.compile(r"(?<=\d)\s*[*×]\s*(?=\d)"), " times "),
    (re.compile(r"(?<![\w~])~(?=\s?\$?\d)"), "about "),
    (re.compile(r"≈\s*"), "about "),
    (re.compile(r"\s*(?:≥|>=)\s*"), " at least "),
    (re.compile(r"\s*(?:≤|<=)\s*"), " at most "),
    (re.compile(r"(?<=\w)\s*<\s*(?=\d)"), " below "),  # numpy<2
    (re.compile(r"(?<=\w)\s*>\s*(?=\d)"), " above "),
    (re.compile(r"\s+/\s+(?=[$\d])"), " per "),  # $15 / 1M chars
    (re.compile(r"\s+/\s+"), " or "),
    (re.compile(r"[|*#_~^`<>{}\[\]\\]+"), " "),
]


def _markdown(text: str) -> str:
    # code blocks
    outside = _FENCE.sub("", text).strip()
    if outside:
        text = _FENCE.sub("\nCode block.\n", text)
    else:
        text = _FENCE.sub(lambda m: m.group(2), text)

    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)  # images -> alt text
    # links -> link text (a file link like [app.py:42](...) is read as "app.py")
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", lambda m: re.sub(r"(\w" + _EXT + r"):\d+(?::\d+)?$", r"\1", m.group(1)), text)
    text = re.sub(r"</?[A-Za-z][^>\n]{0,80}>", " ", text)  # html tags

    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", s):  # table separator
            continue
        if re.fullmatch(r"(?:[-*_]\s*){3,}", s):  # horizontal rule
            continue
        s = re.sub(r"^#{1,6}\s+", "", s)  # heading
        s = re.sub(r"^(?:>\s*)+", "", s)  # quote
        s = re.sub(r"^[-*+•▪◦]\s+", "", s)  # bullet
        s = re.sub(r"^\[[ xX]\]\s+", "", s)  # task box
        if s.startswith("|") or s.count("|") >= 2:  # table row -> comma separated cells
            cells = [c.strip() for c in s.strip("|").split("|")]
            s = ", ".join(c for c in cells if c)
        s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)
        s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
        s = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"\1", s)
        s = re.sub(r"`+([^`]*)`+", r"\1", s)
        if s:
            lines.append(s)
    # every line is its own phrase: add a full stop where a line ends without punctuation
    out = []
    for s in lines:
        if not re.search(r"[.!?:;,]$", s):
            s += "."
        out.append(s)
    return "\n".join(out)


def _wrap_long_line(line: str) -> str:
    """Break very long lines at sentence ends (else at spaces) so no regex sees a huge line."""
    if len(line) <= MAX_LINE:
        return line
    out, rest = [], line
    while len(rest) > MAX_LINE:
        window = rest[:MAX_LINE]
        cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        if cut < MAX_LINE // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = MAX_LINE - 1
        out.append(rest[:cut + 1])
        rest = rest[cut + 1:]
    out.append(rest)
    return "\n".join(out)


MAX_CHARS = 100_000  # ~15,000 words, over an hour of listening; keeps cleanup instant on huge selections
MAX_LINE = 2_000  # some rules are slow on pathological single lines; real prose lines are far shorter


def clean_for_speech(text: str) -> str:
    text = text[:MAX_CHARS]
    text = "\n".join(_wrap_long_line(x) for x in text.split("\n"))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = _paths_and_urls(text)  # before markdown, so backticked paths with spaces are seen whole
    text = _markdown(text)
    text = _EMOJI.sub("", text)
    for rx, rep in _SYMBOLS:
        text = rx.sub(rep, text)
    text = re.sub(r"(?<=[A-Za-z])_(?=[A-Za-z0-9])", " ", text)  # snake_case
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[ \u00a0]+", " ", text)
    text = re.sub(r"\s+([.,;:!?])(?=\s|$|[\"')\]])", r"\1", text)  # but keep "a .venv folder"
    text = re.sub(r"([.!?])[.]+", r"\1", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


# ---------------------------------------------------------------- chunking
@dataclass
class Chunk:
    text: str
    pause: float  # seconds of silence after it, at 1.0x


FIRST_MAX = 30  # first chunk: short, so the first words arrive in well under a second
CHUNK_MAX = 150  # later chunks: about a sentence, so speed changes land quickly
SENTENCE_PAUSE, CLAUSE_PAUSE, LINE_PAUSE = 0.22, 0.06, 0.32
_SENT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
_ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|Mr|Mrs|Ms|Dr|St|approx|No)\.$", re.I)


def _sentences(text: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts, buf = [], ""
        for piece in _SENT.split(line):
            buf = f"{buf} {piece}".strip() if buf else piece.strip()
            if not _ABBREV.search(buf):
                parts.append(buf)
                buf = ""
        if buf:
            parts.append(buf)
        for i, p in enumerate(parts):
            out.append((p, LINE_PAUSE if i == len(parts) - 1 else SENTENCE_PAUSE))
    return out


def _split_long(s: str, limit: int) -> list[str]:
    """Split one sentence at clause marks, then at spaces, into pieces of at most ~limit chars."""
    if len(s) <= limit:
        return [s]
    pieces, rest = [], s
    while len(rest) > limit:
        window = rest[: limit + 1]
        cut = max(window.rfind(", "), window.rfind("; "), window.rfind(": "), window.rfind(" - "), window.rfind(" — "))
        if cut < limit * 0.35:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        pieces.append(rest[: cut + 1].strip())
        rest = rest[cut + 1:].strip()
    if rest:
        pieces.append(rest)
    return pieces


FIRST_MIN = 20  # don't open with a lone "Done." and then make the listener wait for a long sentence
# Synthesis runs ~3x faster than speech, so the audio already queued covers the next chunk if it is
# no longer than ~1.2x everything before it (safe even if the CPU is busy and synthesis is 2x slower).
GROWTH = 1.2
NEXT_MIN = 60


def spoken_len(s: str) -> int:
    """Rough length of the speech: digits are read as whole words ("10.0.26300" -> "ten point zero point
    twenty-six thousand three hundred"), so they count four times."""
    return len(s) + 3 * sum(ch.isdigit() for ch in s)


def _head_within(s: str, room: int) -> str:
    r = room
    head = _split_long(s, r)[0]
    while spoken_len(head) > room and r > 12:
        r = int(r * 0.8)
        head = _split_long(s, r)[0]
    return head


def chunks(text: str, first_max: int = FIRST_MAX, chunk_max: int = CHUNK_MAX) -> list[Chunk]:
    """Short opener, then chunks that grow with the audio already queued, up to chunk_max, so
    playback never has to wait for the next chunk.

    Sizes are measured in spoken length (digits count extra). Whole sentences are packed together while they fit; a sentence is only cut (at a comma, else
    a space) when it doesn't fit on its own, or to fill out a too-short opener.
    """
    queue = [(s, p) for s, p in _sentences(text) if re.search(r"[A-Za-z0-9]", s)]
    out: list[Chunk] = []
    total = 0
    while queue:
        if not out:
            limit = first_max
        else:
            limit = min(chunk_max, max(NEXT_MIN, int(total * GROWTH)))
        parts: list[str] = []
        length, pause = 0, CLAUSE_PAUSE
        while queue:
            s, p = queue[0]
            sep = 1 if parts else 0
            if length + sep + spoken_len(s) <= limit:
                parts.append(s)
                length += sep + spoken_len(s)
                pause = p
                queue.pop(0)
                continue
            room = limit - length - sep
            if (not parts or (not out and length < FIRST_MIN)) and room >= 12:
                head = _head_within(s, room)
                rest = s[len(head):].strip()
                parts.append(head)
                pause = CLAUSE_PAUSE
                if rest:
                    queue[0] = (rest, p)
                else:
                    queue.pop(0)
                    pause = p
            elif not parts:  # limit too small to split sensibly: take the sentence whole
                parts.append(s)
                pause = p
                queue.pop(0)
            break
        out.append(Chunk(" ".join(parts), pause))
        total += spoken_len(out[-1].text)
    return out
