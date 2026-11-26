from types import SimpleNamespace

from yappr.cleanup import Cleaner, apply_dictionary, rule_clean, _looks_like_cleanup
from yappr.llm import LLMError

DICT = [{"word": "Acme", "sounds_like": ["akmi"]}, {"word": "Siobhan", "sounds_like": ["shivawn", "shiv on"]}]


def test_fillers_and_stutters_removed():
    raw = "Um, so I was thinking that uh we should move the the meeting, uh, to Thursday."
    assert rule_clean(raw, []) == "So I was thinking that we should move the meeting, to Thursday."


def test_dictionary_aliases_and_casing():
    assert apply_dictionary("email ACME and shiv on about akmi", DICT) == "email Acme and Siobhan about Acme"


def test_dictionary_respects_word_boundaries():
    assert apply_dictionary("the acmeist", DICT) == "the acmeist"


def test_grammatical_repeats_kept():
    assert rule_clean("I had had enough", []) == "I had had enough"


def test_length_guard():
    src = "can you write a prompt for Claude that summarizes the last three emails"
    assert _looks_like_cleanup(src, "Can you write a prompt for Claude that summarizes the last three emails?")
    assert not _looks_like_cleanup(src, "Sure! Here is a prompt you can use with Claude to summarize your last three emails from Jordan. " * 3)


ONBOARDING = ("Okay so I've been working on the onboarding flow and there's a bunch of stuff going on. The sign-up page "
              "loads slowly on mobile, the welcome email sometimes doesn't send, and people get stuck connecting their "
              "calendar. My budget is about two weeks. Based on all of that, can you create a checklist and make a plan?")

# Real outputs that are not cleanups of what was said: each must be rejected so the rule-pass text is pasted.
NOT_CLEANUPS = [
    (ONBOARDING,  # what the old prompt returned: the spoken sentence turned into a checklist
     "Okay, so I've been working on the onboarding flow, and there's a bunch of stuff going on:\n\n"
     "- The sign-up page loads slowly on mobile.\n- The welcome email sometimes doesn't send.\n"
     "- People get stuck connecting their calendar.\n\nMy budget is about two weeks. Based on all of that, "
     "can you create a checklist and make a plan?"),
    (ONBOARDING,  # carried out the request
     "## Plan (2 weeks)\n**Week 1**\n- [ ] Speed up the mobile sign-up page\n- [ ] Fix welcome email delivery\n"
     "**Week 2**\n- [ ] Make calendar connection easier\n- [ ] Test the whole flow"),
    ("Summarize the following in three bullet points. Revenue was up 12%. Churn dropped to 3%. We closed two deals.",
     "Summarize the following in three bullet points:\n\n- Revenue was up 12%.\n- Churn dropped to 3%.\n- We closed two deals."),
    ("What's the capital of Australia and how many people live there?",
     "The capital of Australia is Canberra, and roughly 26 million people live in Australia."),
    ("Translate this into Spanish. I'll be at the office at noon and I'll bring the contracts with me.",
     "Estaré en la oficina al mediodía y llevaré los contratos conmigo."),
    ("Can you fix the login bug where the password field clears itself when you tab out?",
     "Sure! Here's a fix for the login bug where the password field clears on blur."),
    ("Write a SQL query that gets every customer who signed up in the last thirty days.",
     "```sql\nSELECT * FROM customers WHERE signup_date > NOW() - INTERVAL '30 days';\n```"),
    (  # obeyed by deleting the request (seen 1 in 5 runs)
     "Put this into bullet points. The office move is on the 12th. Everyone needs to pack their desk by the 10th.",
     "The office move is on the 12th. Everyone needs to pack their desk by the 10th."),
]

REAL_CLEANUPS = [
    # a correction can delete more than half of what was said
    ("The report is basically finished. I just need the charts. Strike that last bit, the charts are done too, I just need the summary.",
     "The report is basically finished. I just need the summary."),
    # a list the speaker counted out
    ("There are three things. First, update the README. Second, fix the login bug. Third, ship the release notes.",
     "There are three things:\n\n1. Update the README.\n2. Fix the login bug.\n3. Ship the release notes."),
    # the speaker said "here's", so it is not an assistant opener
    ("Okay so here's the thing, right, the server keeps crashing every night around 2 a.m.",
     "Here's the thing: the server keeps crashing every night around 2 a.m."),
    ("Okay I need to prep for the trip. Can you turn that into a to-do list with deadlines?",
     "Okay, I need to prep for the trip. Can you turn that into a to-do list with deadlines?"),
]


def test_outputs_that_act_on_the_dictation_are_rejected():
    for src, out in NOT_CLEANUPS:
        assert not _looks_like_cleanup(src, out), out


def test_real_cleanups_pass_the_guard():
    for src, out in REAL_CLEANUPS:
        assert _looks_like_cleanup(src, out), out


def test_checklist_from_llm_falls_back_to_the_spoken_words():
    text, how = Cleaner(FakeLLM(NOT_CLEANUPS[1][1]), store()).clean(ONBOARDING)
    assert how == "rules" and "create a checklist and make a plan" in text and "- [ ]" not in text


class FakeLLM:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, []
        self.available = True

    def chat(self, system, user, **kw):
        self.calls.append((system, user))
        if self.exc:
            raise self.exc
        return self.reply


def store(**kw):
    s = SimpleNamespace(use_llm_cleanup=True, llm_timeout_s=3)
    s.__dict__.update(kw)
    return SimpleNamespace(settings=s, dictionary=DICT)


def test_llm_used_and_dictionary_reapplied():
    llm = FakeLLM("We should email ACME about the proposal on Thursday.")
    text, how = Cleaner(llm, store()).clean("um we should email akmi about the proposal on thursday")
    assert how == "llm" and text == "We should email Acme about the proposal on Thursday."
    fixed, terms = llm.calls[0][0]
    assert "Acme, Siobhan" in terms and "Siobhan" not in fixed  # dictionary goes after the cached part
    assert llm.calls[0][1].startswith("<transcript>We should email Acme about the proposal on thursday</transcript>")


def test_llm_failure_falls_back_to_rules():
    text, how = Cleaner(FakeLLM(exc=LLMError("timeout")), store()).clean("uh send the report to akmi today please")
    assert how == "rules" and text == "Send the report to Acme today please"


def test_llm_answering_instead_of_cleaning_is_rejected():
    llm = FakeLLM("Sure! " + "Here is a detailed prompt you could use. " * 10)
    text, how = Cleaner(llm, store()).clean("um write a prompt for Claude that summarizes my emails")
    assert how == "rules" and llm.calls


def test_short_clean_dictation_skips_llm_but_anything_to_fix_does_not():
    llm = FakeLLM("Can you fix the conflict that I just created?")
    text, how = Cleaner(llm, store()).clean("Can you fix the conflict that I just created?")
    assert how == "rules" and text == "Can you fix the conflict that I just created?" and not llm.calls
    for raw in ["Send it to John, no, to Maria.", "I was like thinking about it.", "Do a P R and merge.",
                "Call it flow hyphen ux please.", "We should we should go now.",
                "Please send the final invoice to the client before the end of this week so they can pay us."]:  # 18 words
        llm = FakeLLM(raw)
        Cleaner(llm, store()).clean(raw)
        assert llm.calls, raw


def test_short_text_skips_llm():
    llm = FakeLLM("x")
    text, how = Cleaner(llm, store()).clean("sounds good")
    assert how == "rules" and text == "Sounds good" and not llm.calls
