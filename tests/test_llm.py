import json
from types import SimpleNamespace

import pytest

from murmur.config import Store
from murmur.llm import ClaudeClient, LLMClient, LLMError, make_llm, usage_summary


class FakeMessages:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def create(self, **params):
        self.calls.append(params)
        return self.resp


class FakeSDK:
    def __init__(self, resp):
        self.messages = FakeMessages(resp)
        self.options = []

    def with_options(self, **kw):
        self.options.append(kw)
        return self


def reply(text="Cleaned.", stop="end_turn", tin=120, tout=8):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop, usage=SimpleNamespace(input_tokens=tin, output_tokens=tout))


def client(tmp_path, resp):
    c = ClaudeClient("sk-ant-test", "claude-haiku-5-5", 0.10, 0.50, tmp_path / "usage.jsonl")
    sdk = FakeSDK(resp)
    c._client = sdk
    return c, sdk


def test_dictation_request_is_fast_and_text_only(tmp_path):
    c, sdk = client(tmp_path, reply(" Send the deck to Priya. "))
    out = c.chat("sys prompt", "<dictation>send the deck to priya</dictation>", kind="dictation", timeout=4, max_tokens=256)
    assert out == "Send the deck to Priya."
    p = sdk.messages.calls[0]
    assert p["model"] == "claude-haiku-5-5" and p["system"] == "sys prompt"
    assert p["messages"] == [{"role": "user", "content": "<dictation>send the deck to priya</dictation>"}]
    assert p["thinking"] == {"type": "disabled"} and p["output_config"] == {"effort": "low"}
    assert "temperature" not in p  # non-default sampling params are rejected by current Claude models
    assert sdk.options == [{"timeout": 4}]


def test_meeting_summary_keeps_thinking_and_logs_cost(tmp_path):
    c, sdk = client(tmp_path, reply("## Summary\n- ok", tin=20000, tout=1000))
    c.chat("summary prompt", "[0:00:01] Me: hi", kind="meeting-summary", timeout=120)
    p = sdk.messages.calls[0]
    assert "thinking" not in p and p["max_tokens"] == 16000
    rec = json.loads((tmp_path / "usage.jsonl").read_text())
    assert rec["model"] == "claude-haiku-5-5" and rec["in"] == 20000 and rec["out"] == 1000
    assert rec["usd"] == pytest.approx(20000 / 1e6 * 0.10 + 1000 / 1e6 * 0.50)
    assert usage_summary(tmp_path / "usage.jsonl")["calls"] == 1


def test_refusal_raises_so_dictation_falls_back_to_rules(tmp_path):
    c, _ = client(tmp_path, reply("", stop="refusal"))
    with pytest.raises(LLMError):
        c.chat("s", "u", kind="dictation", timeout=4)


def test_no_key_means_unavailable(tmp_path):
    c = ClaudeClient("", "claude-haiku-5-5", 0.1, 0.5, tmp_path / "u.jsonl")
    assert not c.available
    with pytest.raises(LLMError):
        c.chat("s", "u", kind="dictation", timeout=4)


def test_factory_picks_provider(tmp_path):
    assert isinstance(make_llm("claude", "", "k", "claude-haiku-5-5", 0.1, 0.5, tmp_path / "u"), ClaudeClient)
    o = make_llm("openai", "https://api.openai.com/v1", "k", "gpt-4.1-nano", 0.1, 0.4, tmp_path / "u")
    assert type(o) is LLMClient


def test_new_install_defaults_to_claude_haiku(tmp_path):
    s = Store(tmp_path).settings
    assert (s.llm_provider, s.llm_model) == ("claude", "claude-haiku-5-5")


def test_settings_saved_before_claude_support_keep_openai(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"llm_model": "gpt-4.1-nano", "llm_base_url": "https://api.openai.com/v1"}))
    s = Store(tmp_path).settings
    assert (s.llm_provider, s.llm_model) == ("openai", "gpt-4.1-nano")


def test_keys_are_stored_per_provider(monkeypatch):
    saved = {}
    fake = SimpleNamespace(set_password=lambda svc, user, key: saved.__setitem__(user, key),
                           get_password=lambda svc, user: saved.get(user),
                           delete_password=lambda svc, user: saved.pop(user))
    monkeypatch.setitem(__import__("sys").modules, "keyring", fake)
    monkeypatch.delenv("MURMUR_API_KEY", raising=False)
    Store.set_api_key("sk-ant-1", "claude")
    Store.set_api_key("sk-oa-1", "openai")
    assert Store.get_api_key("claude") == "sk-ant-1" and Store.get_api_key("openai") == "sk-oa-1"
