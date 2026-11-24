"""The Yappr product video: what is said, what is shown, in order. Everything else reads this."""

NARRATOR = "am_michael"   # Kokoro voice (Apache-2.0), the same engine Yappr ships
SPEAKER = "af_bella"      # the person dictating in the demo
SPEED = 1.05

# What the person says into Yappr in the dictation scene (fed to the real app as microphone audio).
DICTATION = ("Hey Sam, um, thanks for the quick turnaround. "
             "Let's lock the launch for Friday, and I'll send the deck before standup.")

# What is on screen, highlighted, and read aloud by the real app in the read-aloud scene.
READ_TEXT = ("Yappr reads anything you highlight, in a natural voice that runs "
             "entirely on your own computer.")

# Made up, and deliberately not shaped like a real key (the repo's secret scan rejects anything that is).
# The recorded take pasted an earlier made-up value; it only ever shows as dots.
DUMMY_KEY = "demo-key-0000-not-a-real-key-0000"

REPO_URL = "github.com/jerahsiegal-source/yappr"

# id, narration, caption shown on screen (must make sense with the sound off)
SCENES = [
    ("intro", "Meet Yappr.", "Meet Yappr"),
    ("pitch", "An open source Wispr Flow and Speechify, in one app.",
     "An open source Wispr Flow + Speechify, in one app"),
    ("dictate_a", "Hold a hotkey and talk.", "Hold Ctrl+Win and talk"),
    ("dictate_b", "Let go, and it's typed, wherever your cursor is.", "Let go. It's typed where your cursor is."),
    ("read", "Highlight anything, and Yappr reads it back to you.", "Highlight anything. Yappr reads it to you."),
    ("key", "Bring your own A.I. key. Paste it in once, and it's stored only on your PC.",
     "Bring your own AI key. Paste it in once."),
    ("outro", "Free, open source, and your voice never leaves your computer.",
     "Free. Open source. Your voice stays on your computer."),
]

# A second, shorter dictation into a different program (shows it works anywhere, and the tidy-up).
DICTATION_2 = "Sounds good. I'll, uh, send the the invite list by Friday."
