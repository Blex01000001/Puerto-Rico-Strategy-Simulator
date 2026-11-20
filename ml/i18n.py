"""UI strings looked up by key from the shared i18n/ folder (ml.<lang>.json; the Dashboard will read the same folder).

English is the default language and the fallback: a key missing from another language shows the English text, a key
missing everywhere shows the key itself (tests/test_i18n.py checks that neither happens). No Streamlit import: ui.py
decides which language is active (session, ?lang=, PR_LANG) and passes it in.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "i18n")
DEFAULT = "en"
LANGS = {"en": "English", "zh-TW": "中文"}
_cache = {}


def table(lang):
    if lang not in _cache:
        with open(os.path.join(DIR, f"ml.{lang}.json"), encoding="utf-8") as f:
            _cache[lang] = json.load(f)
    return _cache[lang]


def translate(lang, key, **values):
    text = table(lang).get(key)
    if text is None:
        text = table(DEFAULT).get(key, key)
    return text.format(**values) if values else text
