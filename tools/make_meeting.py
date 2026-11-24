"""Build a synthetic two-person meeting (mic.wav = "Me", sys.wav = "Others") for tests.

Uses the built-in Windows voices. Distinctive facts are planted at the start and the end so a
summary can be checked for coverage of the whole call.

Usage: python tools/make_meeting.py <minutes> <out_dir>
"""
import json
import os
import random
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

SR = 16000
minutes = float(sys.argv[1])
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
random.seed(7)

START = [
    ("me", "Okay, let's get started. Thanks for making time for the Northwind kickoff."),
    ("them", "Happy to be here. Before anything else, Dana will send the revised statement of work to Northwind by December third."),
    ("me", "Great. And I'll own the budget reconciliation, we agreed on forty two thousand dollars for phase one."),
    ("them", "Correct, forty two thousand for phase one, and the pilot starts with the Denver warehouse."),
]
END = [
    ("me", "Alright, we're almost out of time. Let's lock the final next steps."),
    ("them", "Final next step from our side: Okafor will run the security review on January twelfth."),
    ("me", "And I'll book the go-live rehearsal for February second with the Denver team."),
    ("them", "Perfect. One open question is whether the Lisbon office joins the pilot. We'll decide that next week."),
    ("me", "Sounds good. Thanks everyone, talk soon."),
]
TOPICS = [
    "the inventory sync between the warehouse system and the storefront",
    "the reporting dashboard for weekly shipment volume",
    "training sessions for the floor supervisors",
    "the barcode scanner rollout",
    "data migration from the legacy order database",
    "the returns workflow and refund approvals",
    "service level targets for support tickets",
    "the vendor onboarding checklist",
]
ME_T = [
    "On {t}, where are we at this week?",
    "I want to make sure {t} doesn't slip. What do you need from us?",
    "Can you walk me through the risks on {t}?",
    "My understanding is that {t} is about {p} percent done. Is that right?",
]
THEM_T = [
    "For {t}, we're roughly {p} percent through. The main blocker is waiting on test data from the client side.",
    "On {t}, the team finished the first pass last {d}, and we expect a second review in about {n} days.",
    "The risk with {t} is mostly scheduling. If we get access by {d}, we can stay on plan.",
    "We tested {t} with {n} users, and feedback was positive, though a couple of edge cases need fixing.",
]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def filler(i):
    t = TOPICS[i % len(TOPICS)]
    v = dict(t=t, p=random.choice([20, 35, 50, 65, 80]), d=random.choice(DAYS), n=random.choice([3, 5, 8, 12]))
    return [("me", random.choice(ME_T).format(**v)), ("them", random.choice(THEM_T).format(**v)),
            ("me", "Okay, that makes sense. Let's keep an eye on it."),]


# measured ~7.3 s per turn including gaps; build enough turns
turns = list(START)
need = int(minutes * 60 / 7.3) - len(START) - len(END)
i = 0
while len(turns) < need:
    turns += filler(i)
    i += 1
turns += END

tmp = tempfile.mkdtemp(prefix="murmur_meet_")
jobs = [{"voice": "Microsoft David Desktop" if who == "me" else "Microsoft Zira Desktop", "text": txt,
         "out": os.path.join(tmp, f"{k:05d}.wav")} for k, (who, txt) in enumerate(turns)]
jf = os.path.join(tmp, "jobs.json")
json.dump(jobs, open(jf, "w"))
ps = r"""
Add-Type -AssemblyName System.Speech
$jobs = Get-Content -Raw '%s' | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($j in $jobs) { try { $s.SelectVoice($j.voice) } catch {}; $s.SetOutputToWaveFile($j.out, $fmt); $s.Speak($j.text) }
$s.Dispose()
""" % jf.replace("'", "''")
subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)

me, them = [], []
gap = np.zeros(int(0.7 * SR), np.float32)
for job, (who, _) in zip(jobs, turns):
    a, _ = sf.read(job["out"], dtype="float32")
    sil = np.zeros_like(a)
    (me if who == "me" else them).extend([a, gap])
    (them if who == "me" else me).extend([sil, gap])
me, them = np.concatenate(me), np.concatenate(them)
sf.write(os.path.join(out_dir, "mic.wav"), me, SR)
sf.write(os.path.join(out_dir, "sys.wav"), them, SR)
json.dump([{"who": w, "text": t} for w, t in turns], open(os.path.join(out_dir, "script.json"), "w"), indent=1)
print(f"{len(turns)} turns, {len(me) / SR / 60:.1f} min -> {out_dir}")
