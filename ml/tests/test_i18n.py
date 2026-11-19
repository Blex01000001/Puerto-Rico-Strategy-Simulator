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


def test_model_list_page_is_english(monkeypatch, tmp_path):
    at = _english_app(monkeypatch, tmp_path, "modellist")
    assert any("Model List" in x for x in [c.value for c in at.main.caption] + [m.value for m in at.main.markdown])
    cols = [c for d in at.dataframe for c in d.value.columns]
    for name in ("Model", "Location", "Type", "Players", "Best win rate vs original MCTS", "Version status"):
        assert name in cols, (name, cols)
    assert not [c for c in cols if CJK.search(str(c))], cols
    cells = [str(v) for d in at.dataframe for v in d.value.to_numpy().ravel()]
    bad = [x for x in cells if CJK.search(x)]
    assert not bad, bad[:5]
    assert not [x for x in _page_text(at) if CJK.search(x)]


def test_model_details_page_is_english(monkeypatch, tmp_path):
    at = _english_app(monkeypatch, tmp_path, "models")
    texts = _page_text(at) + [m.value for m in at.main.markdown if not m.value.lstrip().startswith("<style>")]
    assert any("What R² and cross-entropy mean" in x for x in texts)
    assert any("Matches" in x or "No match records yet." in x for x in texts)
    bad = [x for x in texts if CJK.search(x)]
    assert not bad, bad[:3]
    cells = [str(v) for d in at.dataframe for v in list(d.value.columns) + list(d.value.to_numpy().ravel())]
    bad = [x for x in cells if CJK.search(x)]
    assert not bad, bad[:5]
    # side by side: pick the first two models
    names = list(at.selectbox(key="model-pick").options)
    at.radio(key="models-view").set_value("compare").run()
    assert not at.exception, at.exception
    at.multiselect[0].set_value(names[:2]).run()
    assert not at.exception, at.exception
    bad = [x for x in [m.value for m in at.main.markdown if not m.value.lstrip().startswith("<style>")] + [c.value for c in at.main.caption] if CJK.search(x)]
    assert not bad, bad[:3]


def test_fingerprint_texts_follow_the_language():
    import fingerprint
    old = {"hashFormat": 2, "players": 4, "games": 20000, "rate": 0.01, "rulesRevision": 1, "ruleset": "base",
           "seats": [{"strategy": "mcts", "revisions": {"mcts": 1}, "params": {"simulations": 300}}], "options": {"autoAdvanceForced": True}}
    new = {**old, "games": 200000, "rulesRevision": 2, "options": {"autoAdvanceForced": False, "x": 1},
           "seats": [{"strategy": "mcts", "revisions": {"mcts": 2}, "params": {"simulations": 100}}]}
    zh, en = fingerprint.describe(old, new), fingerprint.describe(old, new, lang="en")
    assert "局數：20,000 → 200,000" in zh  # the default stays Chinese (existing callers, tests)
    assert "Games: 20,000 → 200,000" in en and "Seat 1 simulations: 300 → 100" in en
    assert not [x for x in en if CJK.search(x)], en
    assert len(zh) == len(en)
    notes = fingerprint.stale_notes({"rulesRevision": 1, "ruleset": "base", "seats": []}, "en")
    assert all(n.startswith("Rules ") for n in notes)


def _no_chinese(at, where):
    texts = _page_text(at) + [x for s in at.main.selectbox for x in s.options] + [x.placeholder for x in at.main.text_input]
    texts += [e.label for e in at.main.expander]
    bad = [x for x in texts if isinstance(x, str) and CJK.search(x)]
    assert not bad, (where, bad[:4])


def test_data_page_is_english_in_every_mode(monkeypatch, tmp_path):
    from conftest import write_dump
    os.makedirs(tmp_path / "ml")
    write_dump(str(tmp_path / "ml" / "4p-test.bin"), games=10)  # the "existing data" table
    at = _english_app(monkeypatch, tmp_path, "data")
    assert at.title[0].value == "Data Sampling"
    assert "Start generating data" in [b.label for b in at.main.button]
    for mode in ("config", "custom", "selfplay"):
        radio = next(r for r in at.main.radio if r.label == "Sampling source")
        radio.set_value(mode).run()
        assert not at.exception, (mode, at.exception)
        _no_chinese(at, mode)
    cells = [str(v) for d in at.dataframe for v in list(d.value.columns) + list(d.value.index.names or []) + list(d.value.to_numpy().ravel())]
    assert "Sampling rate" in cells and "File" in cells
    assert not [x for x in cells if CJK.search(x)], [x for x in cells if CJK.search(x)][:4]


def test_job_titles_follow_the_language(monkeypatch, tmp_path):
    import jobs
    rows = [{"id": "a", "title": "資料（自訂：cheap-engine）→ x.bin", "titleKey": "job.title.dump_custom", "titleArgs": {"strategies": "cheap-engine", "name": "x"},
             "kind": "dump", "state": "running", "spec": {}, "created": "2026-01-01T00:00:00Z"},
            {"id": "b", "title": "舊的工作標題", "kind": "match", "state": "waiting", "spec": {}, "created": "2026-01-01T00:00:00Z"}]  # no key: keeps its text
    monkeypatch.delenv("PR_LANG", raising=False)
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(jobs, "list_jobs", lambda: rows)
    monkeypatch.setattr(jobs, "active_job", lambda: rows[0])
    monkeypatch.setattr(jobs, "waiting_jobs", lambda: rows[1:])
    monkeypatch.setattr(jobs, "events", lambda job_id: [])
    monkeypatch.setattr(jobs, "queue_position", lambda job_id: 1)
    at = AppTest.from_file(UI, default_timeout=60).run()
    side = " ".join(m.value for m in at.sidebar.markdown)
    assert "Data (custom: cheap-engine) → x.bin" in side
    at.button(key="lang-toggle").click().run()
    side = " ".join(m.value for m in at.sidebar.markdown)
    assert "資料（自訂：cheap-engine）→ x.bin" in side


def _table_cells(at):
    out = []
    for d in list(at.dataframe) + list(at.table):
        v = d.value
        out += [str(c) for c in v.columns] + [str(i) for i in v.index.names if i] + [str(x) for x in v.index] + [str(x) for x in v.to_numpy().ravel()]
    return out


def test_training_page_is_english(monkeypatch, tmp_path):
    from conftest import write_dump
    os.makedirs(tmp_path / "ml")
    write_dump(str(tmp_path / "ml" / "4p-test.bin"), games=10)
    at = _english_app(monkeypatch, tmp_path, "train")
    assert "Start training" in [b.label for b in at.main.button]
    for kind in ("train_lgbm", "train_mlp"):
        next(r for r in at.main.radio if r.label == "Model").set_value(kind).run()
        assert not at.exception, at.exception
        _no_chinese(at, kind)
        bad = [x for x in _table_cells(at) if CJK.search(x)]
        assert not bad, (kind, bad[:4])
    labels = [n.label for n in at.main.number_input] + [x.label for x in at.main.text_input]
    assert any(x.startswith("Maximum epochs (epochs)") for x in labels), labels


def test_hash_page_is_english(monkeypatch, tmp_path):
    at = _english_app(monkeypatch, tmp_path, "hash")
    texts = _page_text(at) + [m.value for m in at.main.markdown if not m.value.lstrip().startswith("<style>")]
    assert any("What a hash is" in x for x in texts)
    bad = [x for x in texts + _table_cells(at) if CJK.search(x)]
    assert not bad, bad[:4]
    assert any("LightGBM training parameters" in x for x in _table_cells(at))


def test_every_page_is_english_and_switches_back(monkeypatch, tmp_path):
    """The whole UI, page by page, in English then Chinese: no Chinese in English (the data of docs/versions.json aside) and no
    English chrome left in Chinese on the navigation."""
    monkeypatch.delenv("PR_LANG", raising=False)
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path))
    at = AppTest.from_file(UI, default_timeout=60).run()
    for page in ("data", "train", "match", "modellist", "models", "queue", "hash", "versions"):
        if not any(b.key == f"navon-{page}" for b in at.button):
            at.button(key=f"nav-{page}").click().run()
        assert not at.exception, (page, at.exception)
        texts = [x for x in _page_text(at) + [m.value for m in at.sidebar.markdown] if not x.lstrip().startswith("<style>")]
        if page != "versions":  # the version list is project data in Chinese
            bad = [x for x in texts if CJK.search(x) and x != "中文"]
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
