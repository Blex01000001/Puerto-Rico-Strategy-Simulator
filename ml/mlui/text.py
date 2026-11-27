"""Language of the ML UI: lang() and t() (texts in i18n/ml.<language>.json, see ml/i18n.py)."""

import os

import streamlit as st

import i18n


LANG_ENV = "PR_LANG"  # default language when neither the session nor ?lang= chose one (tests set zh-TW)


def lang():
    """Active language: the sidebar toggle (session), then ?lang= in the URL, then PR_LANG, then English."""
    for choice in (st.session_state.get("lang"), st.query_params.get("lang"), os.environ.get(LANG_ENV)):
        if choice in i18n.LANGS:
            return choice
    return i18n.DEFAULT


def t(key, **values):
    return i18n.translate(lang(), key, **values)
