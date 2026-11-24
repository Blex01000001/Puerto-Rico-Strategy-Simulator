import io
import json
import os
import urllib.error

import pytest

import llm


@pytest.fixture(autouse=True)
def no_key_in_the_environment(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # the tests decide where the key comes from


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def settings(name="gemini", **kw):
    """One provider's settings as chat / list_models / api_key take them (with a key from the file)."""
    return {**llm.provider_settings(llm.default_settings(), name), "apiKey": "SECRET-KEY-1234", **kw}


def test_settings_round_trip_keeps_the_key_private_and_claude_starts_disabled(tmp_path):
    path = str(tmp_path / "llm.json")
    defaults = llm.load_settings(path)                                    # no file: the defaults
    assert defaults["providers"]["gemini"]["enabled"] and not defaults["providers"]["claude"]["enabled"]   # the paid one is opt-in
    defaults["providers"]["gemini"].update(apiKey="SECRET-KEY-1234", model="gemini-x")
    defaults["primer"] = "bg"
    llm.save_settings(defaults, path)
    again = llm.load_settings(path)
    assert again["providers"]["gemini"]["model"] == "gemini-x" and again["providers"]["gemini"]["apiKey"] == "SECRET-KEY-1234" and again["primer"] == "bg"
    if os.name == "posix":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"             # only this user can read the key
    open(path, "w").write("{broken")
    assert llm.load_settings(path)["providers"]["gemini"]["model"] == llm.DEFAULT_MODEL   # a broken file does not crash the page


def test_a_file_from_before_there_were_several_providers_becomes_the_gemini_entry(tmp_path):
    path = str(tmp_path / "llm.json")
    open(path, "w", encoding="utf-8").write(json.dumps({"provider": "gemini", "apiKey": "old-key", "model": "gemini-old", "conversationLimit": 5000,
                                                        "primer": "my background", "questions": [{"name": "q", "text": "t"}]}))
    loaded = llm.load_settings(path)
    assert loaded["providers"]["gemini"]["apiKey"] == "old-key" and loaded["providers"]["gemini"]["model"] == "gemini-old"
    assert loaded["providers"]["gemini"]["conversationLimit"] == 5000 and loaded["primer"] == "my background" and loaded["questions"] == [{"name": "q", "text": "t"}]
    assert not loaded["providers"]["claude"]["enabled"] and loaded["providers"]["claude"]["apiKey"] == ""


def test_the_key_comes_from_the_provider_environment_variable_first_then_the_file():
    assert llm.api_key({"apiKey": "from-file"}, env={}) == ("from-file", "file")
    assert llm.api_key({"apiKey": "from-file"}, env={"GEMINI_API_KEY": " from-env "}) == ("from-env", "env")
    assert llm.api_key({"apiKey": ""}, env={}) == ("", "")
    claude = {"kind": "claude", "apiKey": "claude-file"}
    assert llm.api_key(claude, env={"GEMINI_API_KEY": "not-for-claude"}) == ("claude-file", "file")   # each provider has its own variable
    assert llm.api_key(claude, env={"ANTHROPIC_API_KEY": "claude-env"}) == ("claude-env", "env")
    with pytest.raises(llm.LlmError, match="GEMINI_API_KEY"):
        llm.chat(settings(apiKey=""), "s", [{"role": "user", "text": "q"}], opener=lambda *a, **k: None)
    with pytest.raises(llm.LlmError, match="ANTHROPIC_API_KEY"):
        llm.chat(settings("claude", apiKey=""), "s", [{"role": "user", "text": "q"}], opener=lambda *a, **k: None)


def test_chat_sends_the_whole_history_with_the_key_in_a_header_not_the_url():
    seen = {}

    def opener(req, timeout=None):
        seen["url"], seen["headers"], seen["body"] = req.full_url, dict(req.header_items()), json.loads(req.data)
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "answer "}, {"text": "two"}]}}], "usageMetadata": {"totalTokenCount": 42}})

    history = [{"role": "user", "text": "q1"}, {"role": "model", "text": "a1"}, {"role": "user", "text": "q2"}]
    reply = llm.chat(settings(model="models/gemini-x"), "system text", history, opener=opener)
    assert reply["text"] == "answer two" and reply["tokens"] == 42
    assert seen["url"].endswith("/models/gemini-x:generateContent") and "SECRET" not in seen["url"]
    assert seen["headers"]["X-goog-api-key"] == "SECRET-KEY-1234"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "system text"
    assert [(c["role"], c["parts"][0]["text"]) for c in seen["body"]["contents"]] == [("user", "q1"), ("model", "a1"), ("user", "q2")]


def test_errors_never_contain_the_key_and_a_missing_key_is_refused():
    def http_error(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b'{"error": {"message": "quota SECRET-KEY-1234 exceeded"}}'))

    with pytest.raises(llm.LlmError) as e:
        llm.chat(settings(), "s", [{"role": "user", "text": "q"}], opener=http_error)
    assert "429" in str(e.value) and "quota" in str(e.value) and "SECRET" not in str(e.value)

    def offline(req, timeout=None):
        raise urllib.error.URLError("no route to host ?key=SECRET-KEY-1234")

    with pytest.raises(llm.LlmError) as e:
        llm.chat(settings(), "s", [{"role": "user", "text": "q"}], opener=offline)
    assert "SECRET" not in str(e.value)
    with pytest.raises(llm.LlmError):
        llm.chat(settings(apiKey=""), "s", [{"role": "user", "text": "q"}], opener=offline)
    blocked = lambda req, timeout=None: FakeResponse({"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})  # noqa: E731
    with pytest.raises(llm.LlmError, match="SAFETY"):
        llm.chat(settings(), "s", [{"role": "user", "text": "q"}], opener=blocked)


def test_claude_adapter_uses_the_messages_api_format():
    seen = {}

    def opener(req, timeout=None):
        seen["url"], seen["headers"], seen["body"] = req.full_url, {k.lower(): v for k, v in req.header_items()}, json.loads(req.data)
        return FakeResponse({"content": [{"type": "text", "text": "claude "}, {"type": "tool_use"}, {"type": "text", "text": "says"}],
                             "usage": {"input_tokens": 30, "output_tokens": 12}, "stop_reason": "end_turn"})

    history = [{"role": "user", "text": "q1"}, {"role": "model", "text": "a1"}, {"role": "user", "text": "q2"}]
    reply = llm.chat(settings("claude"), "system text", history, opener=opener)
    assert reply["text"] == "claude says" and reply["tokens"] == 42
    assert seen["url"] == "https://api.anthropic.com/v1/messages" and "SECRET" not in seen["url"]
    assert seen["headers"]["x-api-key"] == "SECRET-KEY-1234" and seen["headers"]["anthropic-version"] == llm.CLAUDE_VERSION and "x-goog-api-key" not in seen["headers"]
    assert seen["body"]["system"] == "system text" and seen["body"]["max_tokens"] == llm.CLAUDE_MAX_TOKENS and seen["body"]["model"] == "claude-sonnet-5-5"
    assert [(m["role"], m["content"]) for m in seen["body"]["messages"]] == [("user", "q1"), ("assistant", "a1"), ("user", "q2")]   # "model" becomes "assistant"
    empty = lambda req, timeout=None: FakeResponse({"content": [], "stop_reason": "max_tokens"})  # noqa: E731
    with pytest.raises(llm.LlmError, match="max_tokens"):
        llm.chat(settings("claude"), "s", history, opener=empty)
    names = llm.list_models(settings("claude"), opener=lambda req, timeout=None: FakeResponse({"data": [{"id": "claude-b"}, {"id": "claude-a"}]}))
    assert names == ["claude-a", "claude-b"]


def test_list_models_keeps_only_the_ones_that_generate_text():
    reply = {"models": [{"name": "models/b", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]},
                        {"name": "models/a", "supportedGenerationMethods": ["generateContent", "countTokens"]}]}
    assert llm.list_models(settings(), opener=lambda req, timeout=None: FakeResponse(reply)) == ["a", "b"]


def test_first_message_and_export_show_the_question_not_the_data():
    first = llm.first_message("background", "D a.bin players=4", "which is better?")
    assert first.index("前情提要") < first.index("資料") < first.index("問題")
    assert llm.display_question(first) == "which is better?" and llm.display_question("follow-up") == "follow-up"
    history = [{"role": "user", "text": first}, {"role": "model", "text": "the second", "model": "gemini-x"}]
    conversations = [{"label": "Gemini", "history": history}, {"label": "Claude", "history": [{"role": "user", "text": first}, {"role": "model", "text": "the first"}]}]
    md = llm.export_markdown(["4p-v3.txt"], conversations, when="2026-11-24 10:00")
    assert "4p-v3.txt" in md and "which is better?" in md and "the second" in md and "the first" in md and "## Gemini" in md and "## Claude" in md
    assert "D a.bin" not in md and "background" not in md and "答（gemini-x）" in md      # no data, no background; each answer names its model
    assert llm.history_chars(history) == len(first) + len("the second")
