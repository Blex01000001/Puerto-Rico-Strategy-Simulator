import os
import re

import llm
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


def _english_app(monkeypatch, tmp_path, page):
    monkeypatch.delenv("PR_LANG", raising=False)
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path))
    at = AppTest.from_file(UI, default_timeout=60).run()
    if not any(b.key == f"navon-{page}" for b in at.button):  # the first page is already the current one
        at.button(key=f"nav-{page}").click().run()
    assert not at.exception, at.exception
    return at


def _page_text(at):
    out = _texts(at) + [i.value for i in at.info] + [r.label for r in at.main.radio] + [n.label for n in at.main.number_input]
    out += [x.label for x in at.main.text_input] + [c.label for c in at.main.checkbox]
    out += [o for r in at.main.radio for o in r.options if isinstance(o, str)]
    return out


def test_match_page_is_english(monkeypatch, tmp_path):
    at = _english_app(monkeypatch, tmp_path, "match")
    texts = _page_text(at)
    assert any("Match Validation" in x for x in texts) or at.title[0].value == "Match Validation"
    assert "Start match" in [b.label for b in at.main.button]
    bad = [x for x in texts if CJK.search(x)]
    assert not bad, bad
    for choice in ("default", "hand", "model"):  # every opponent table (the radio holds the keys, the labels are formatted)
        at.radio(key="m-table").set_value(choice).run()
        assert not at.exception, at.exception
        bad = [x for x in _page_text(at) if CJK.search(x)]
        assert not bad, (choice, bad)
    assert not at.exception, at.exception
    bad = [x for x in _page_text(at) if CJK.search(x)]
    assert not bad, bad
    # the matches already recorded on a model (table columns are translated; the values come from the model's .meta.json)
    frames = [d.value for d in at.dataframe]
    cols = [c for f in frames for c in f.columns]
    assert "Win rate" in cols and "Record kept in" in cols
    assert not [c for c in cols if CJK.search(str(c))], cols


def test_models_page_is_english(monkeypatch, tmp_path):
    at = _english_app(monkeypatch, tmp_path, "models")
    assert any("Value model list" in x for x in [c.value for c in at.main.caption] + [m.value for m in at.main.markdown])
    cols = [c for d in at.dataframe for c in d.value.columns]
    for name in ("Model", "Location", "Type", "Players", "Best win rate vs original MCTS", "Rules version"):
        assert name in cols, (name, cols)
    assert not [c for c in cols if CJK.search(str(c))], cols
    key = next(d.key for d in at.dataframe if (d.key or "").startswith("models-list-"))
    for rows in ([], [0], [0, 1]):  # nothing ticked, one model's details, two side by side
        at.session_state[key] = {"selection": {"rows": rows, "columns": []}}
        at.run()
        assert not at.exception, at.exception
        texts = _page_text(at) + [m.value for m in at.main.markdown if not m.value.lstrip().startswith("<style>")]
        bad = [x for x in texts if CJK.search(x)]
        assert not bad, (rows, bad[:3])
        cells = [str(v) for d in at.dataframe for v in list(d.value.columns) + list(d.value.to_numpy().ravel())]
        bad = [x for x in cells if CJK.search(x)]
        assert not bad, (rows, bad[:5])
    assert any("What R² and cross-entropy mean" in x for x in texts)


def test_training_data_page_is_english(monkeypatch, tmp_path):
    from conftest import write_dump
    os.makedirs(tmp_path / "ml", exist_ok=True)
    write_dump(str(tmp_path / "ml" / "4p-a.bin"), games=10)
    at = _english_app(monkeypatch, tmp_path, "datamanage")
    assert not at.exception, at.exception
    cols = [c for d in at.dataframe for c in d.value.columns]
    assert "Players" in cols and "Rules version" in cols, cols
    key = next(d.key for d in at.dataframe if (d.key or "").startswith("dumps-manage-"))
    at.session_state[key] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, at.exception
    texts = _page_text(at) + [m.value for m in at.main.markdown if not m.value.lstrip().startswith("<style>")]
    assert not [x for x in texts if CJK.search(x)], [x for x in texts if CJK.search(x)][:3]
    cells = [str(v) for d in at.dataframe for v in list(d.value.columns) + list(d.value.to_numpy().ravel())]
    assert not [x for x in cells if CJK.search(x)], [x for x in cells if CJK.search(x)][:5]


def test_every_page_is_english_and_switches_back(monkeypatch, tmp_path):
    """The whole UI, page by page, in English then Chinese: no Chinese in English (the data of docs/versions.json aside) and no
    English chrome left in Chinese on the navigation."""
    monkeypatch.delenv("PR_LANG", raising=False)
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path))
    at = AppTest.from_file(UI, default_timeout=60).run()
    for page in ("data", "train", "match", "datamanage", "models", "analysis", "queue", "hash", "versions"):
        if not any(b.key == f"navon-{page}" for b in at.button):
            at.button(key=f"nav-{page}").click().run()
        assert not at.exception, (page, at.exception)
        texts = [x for x in _page_text(at) + [m.value for m in at.sidebar.markdown] if not x.lstrip().startswith("<style>")]
        if page != "versions":  # the version list is project data in Chinese
            own = {q["text"] for q in llm.DEFAULT_QUESTIONS}   # the saved common questions are the user's own text (Chinese by default)
            bad = [x for x in texts if CJK.search(x) and x != "中文" and x not in own]
            assert not bad, (page, bad[:3])
    at.button(key="lang-toggle").click().run()
    assert at.title[0].value == "版本控管"


def test_every_training_parameter_has_a_label_and_a_guide_row():
    import train_lgbm
    import train_mlp
    for lang in i18n.LANGS:
        table = i18n.table(lang)
        for name in list(train_lgbm.DEFAULTS) + list(train_mlp.DEFAULTS):
            assert f"param.{name}" in table, (lang, name)


DASH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Dashboard")


def _dash_table(lang):
    import json
    with open(os.path.join(i18n.DIR, f"dash.{lang}.json"), encoding="utf-8") as f:
        return json.load(f)


def test_dashboard_files_have_the_same_keys_and_placeholders_and_english_has_no_chinese():
    en = _dash_table("en")
    for lang in i18n.LANGS:
        other = _dash_table(lang)
        assert set(other) == set(en), (lang, sorted(set(en) ^ set(other))[:5])
        for key in en:  # positional placeholders {0}, {1}
            assert sorted(re.findall(r"\{(\d+)\}", other[key])) == sorted(re.findall(r"\{(\d+)\}", en[key])), (lang, key)
    bad = {k: v for k, v in en.items() if CJK.search(v) and k != "lang.switch"}
    assert not bad, bad


def test_dashboard_code_only_uses_keys_that_exist():
    """Every literal key in Dashboard/*.razor and *.cs (L.T("…"), l.T("…"), Text.T("…")) is in both files."""
    keys = set()
    for root, dirs, files in os.walk(DASH_DIR):
        dirs[:] = [d for d in dirs if d not in ("bin", "obj")]
        for name in files:
            if name.endswith((".razor", ".cs")):
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    keys.update(re.findall(r'\b(?:L|l|Text)\.(?:T|Has)\("([A-Za-z0-9_.\-]+)"', f.read()))
    assert keys, "no keys found: the pattern no longer matches how the Dashboard calls the translator"
    for lang in i18n.LANGS:
        table = _dash_table(lang)  # a key ending in "." is a prefix the code completes ("good." + index): some key must start with it
        missing = sorted(k for k in keys if not (any(x.startswith(k) for x in table) if k.endswith(".") else k in table))
        assert not missing, (lang, missing)


def test_every_strategy_has_its_texts_and_a_colour():
    """A new strategy (ml/engine-info.json, from the engine's registry) must be added to the Dashboard's strategy guide and
    palette and to both UIs' text files; without this test a missing one only shows as a bare name or a grey line."""
    import fingerprint
    names = [n for n in fingerprint.engine_info()["strategies"] if n != "rule-based"]
    assert names
    services = os.path.join(DASH_DIR, "Services")
    with open(os.path.join(services, "StrategyInfo.cs"), encoding="utf-8") as f:
        guide = f.read()
    with open(os.path.join(services, "Palette.cs"), encoding="utf-8") as f:
        palette = f.read()
    for lang in i18n.LANGS:
        dash, ml = _dash_table(lang), i18n.table(lang)
        for n in names:
            assert f"strat.{n}.title" in dash, (lang, n, "i18n/dash.*.json strat.<id>.*")
            assert f"strategy.{n}" in ml, (lang, n, "i18n/ml.*.json strategy.<id>")
    no_own_colour = {"guided-random"}  # app.css has 12 series colours; guided-random is mostly a rollout strategy (fallback colour)
    for n in names:
        assert f'"{n}"' in guide, (n, "Dashboard/Services/StrategyInfo.cs Ids / GroupIds")
        assert n in no_own_colour or f'["{n}"]' in palette, (n, "Dashboard/Services/Palette.cs colour")
