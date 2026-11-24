from types import SimpleNamespace

from murmur.cleanup import Cleaner, apply_dictionary, rule_clean, _looks_like_cleanup
from murmur.llm import LLMError

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
    assert "Acme, Siobhan" in llm.calls[0][0]


def test_llm_failure_falls_back_to_rules():
    text, how = Cleaner(FakeLLM(exc=LLMError("timeout")), store()).clean("uh send the report to akmi today please")
    assert how == "rules" and text == "Send the report to Acme today please"


def test_llm_answering_instead_of_cleaning_is_rejected():
    llm = FakeLLM("Sure! " + "Here is a detailed prompt you could use. " * 10)
    text, how = Cleaner(llm, store()).clean("write a prompt for Claude that summarizes my emails")
    assert how == "rules"


def test_short_text_skips_llm():
    llm = FakeLLM("x")
    text, how = Cleaner(llm, store()).clean("sounds good")
    assert how == "rules" and text == "Sounds good" and not llm.calls
