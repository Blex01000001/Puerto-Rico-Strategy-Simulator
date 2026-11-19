import os
import re

import pytest

import i18n

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui.py")
CJK = re.compile(r"[　-〿一-鿿＀-￯]")


def test_every_language_has_the_same_keys_and_placeholders():
    en = i18n.table("en")
    for lang in i18n.LANGS:
        other = i18n.table(lang)
        assert set(other) == set(en), (lang, set(en) ^ set(other))
        for key in en:
            assert re.findall(r"\{(\w+)\}", other[key]) == re.findall(r"\{(\w+)\}", en[key]), (lang, key)


def test_english_strings_have_no_chinese():
    bad = {k: v for k, v in i18n.table("en").items() if CJK.search(v) and k != "lang.switch"}
    assert not bad, bad


def test_missing_key_falls_back_to_english_then_to_the_key():
    assert i18n.translate("zh-TW", "no.such.key") == "no.such.key"
    assert i18n.translate("en", "side.queued", n=3) == "3 more waiting in the queue"


def test_shell_is_english_by_default_and_switches(monkeypatch, tmp_path):
    monkeypatch.delenv("PR_LANG", raising=False)
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path))
    at = AppTest.from_file(UI, default_timeout=60).run()
    assert not at.exception, at.exception
    shell = [b.label for b in at.button if (b.key or "").startswith(("nav", "lang", "side"))]
    assert not [x for x in shell if CJK.search(x) and x != "中文"], shell
    assert at.title[0].value == "Data Sampling"
    assert not CJK.search(at.caption[0].value)
    at.button(key="lang-toggle").click().run()
    assert at.title[0].value == "模擬對局採樣"
    assert any(b.label == "English" for b in at.button)
