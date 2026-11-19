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


def _texts(at):
    """Everything the page draws as text (markdown, captions, buttons, labels, tables' headers) except the page's own data."""
    out = [m.value for m in at.main.markdown if not m.value.lstrip().startswith("<style>")] + [c.value for c in at.main.caption] + [b.label for b in at.main.button]
    out += [e.label for e in at.main.expander] + [m.label for m in at.main.metric] + [s.label for s in at.main.selectbox]
    out += [w.value for w in at.main.warning] + [w.value for w in at.main.success]
    return out


@pytest.mark.parametrize("active", [0, 2])  # a running job, then a lost one
def test_queue_page_has_no_chinese_in_english(monkeypatch, tmp_path, active):
    import jobs
    rows = [{"id": "r", "title": "running job", "kind": "dump", "state": "running", "spec": {}, "created": "2026-01-01T00:00:00Z"},
            {"id": "w", "title": "waiting job", "kind": "match", "state": "waiting", "spec": {}, "created": "2026-01-01T00:00:00Z"},
            {"id": "l", "title": "lost job", "kind": "train_mlp", "state": "lost", "spec": {}, "created": "2026-01-01T00:00:00Z"},
            {"id": "i", "title": "dead job", "kind": "train_lgbm", "state": "interrupted", "spec": {}, "created": "2026-01-01T00:00:00Z"}]
    monkeypatch.delenv("PR_LANG", raising=False)
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(jobs, "list_jobs", lambda: rows)
    monkeypatch.setattr(jobs, "active_job", lambda: rows[active])
    monkeypatch.setattr(jobs, "waiting_jobs", lambda: rows[1:2])
    monkeypatch.setattr(jobs, "events", lambda job_id: [])
    monkeypatch.setattr(jobs, "queue_position", lambda job_id: 1)
    monkeypatch.setattr(jobs, "log_tail", lambda job_id, *a, **k: "")
    monkeypatch.setattr(jobs, "read_job", lambda job_id: next((r for r in rows if r["id"] == job_id), None))
    at = AppTest.from_file(UI, default_timeout=60).run()
    at.button(key="nav-queue").click().run()
    assert not at.exception, at.exception
    texts = _texts(at) + [m.value for m in at.sidebar.markdown]
    assert any("Job list" in x for x in texts)
    bad = [x for x in texts if CJK.search(x)]
    assert not bad, bad
    for job in (r for r in rows if r["state"] not in jobs.BUSY or r is rows[active]):  # every listed job's detail view
        at.session_state["job-select"] = job["id"]
        at.run()
        assert not at.exception, at.exception
        bad = [x for x in _texts(at) + [w.value for w in at.info] if CJK.search(x)]
        assert not bad, (job["state"], bad)


def test_versions_page_chrome_is_english(monkeypatch, tmp_path):
    monkeypatch.delenv("PR_LANG", raising=False)
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path))
    at = AppTest.from_file(UI, default_timeout=60).run()
    at.button(key="nav-versions").click().run()
    assert not at.exception, at.exception
    html = " ".join(m.value for m in at.main.markdown if not m.value.lstrip().startswith("<style>"))
    for text in ("Rules version", "Engine version", "Feature version", "Data format version", "Strategy", "Current version", "When to bump"):
        assert text in html, text
    # the version list itself (docs/versions.json: titles, meanings, changes) is project data and stays Chinese; the labels around it are translated
    assert "什麼時候加" not in html and "目前：" not in html and "來源：" not in html
