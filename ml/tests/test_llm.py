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


def settings(**kw):
    return {**llm.default_settings(), "apiKey": "SECRET-KEY-1234", **kw}


def test_settings_round_trip_keeps_the_key_private(tmp_path):
    path = str(tmp_path / "llm.json")
    assert llm.load_settings(path)["apiKey"] == ""                       # no file: the defaults
    s = settings(model="gemini-x", primer="bg")
    llm.save_settings(s, path)
    assert llm.load_settings(path)["model"] == "gemini-x" and llm.load_settings(path)["apiKey"] == "SECRET-KEY-1234"
    if os.name == "posix":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"             # only this user can read the key
    open(path, "w").write("{broken")
    assert llm.load_settings(path)["model"] == llm.DEFAULT_MODEL         # a broken file does not crash the page


def test_the_key_comes_from_the_environment_first_then_the_file():
    assert llm.api_key({"apiKey": "from-file"}, env={}) == ("from-file", "file")
    assert llm.api_key({"apiKey": "from-file"}, env={"GEMINI_API_KEY": " from-env "}) == ("from-env", "env")
    assert llm.api_key({"apiKey": ""}, env={}) == ("", "")
    with pytest.raises(llm.LlmError, match="GEMINI_API_KEY"):
        llm.chat({**llm.default_settings(), "apiKey": ""}, "s", [{"role": "user", "text": "q"}], opener=lambda *a, **k: None)


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
    md = llm.export_markdown("gemini-x", ["4p-v3.txt"], history, when="2026-11-24 10:00")
    assert "4p-v3.txt" in md and "which is better?" in md and "the second" in md and "D a.bin" not in md and "background" not in md
    assert llm.history_chars(history) == len(first) + len("the second")
