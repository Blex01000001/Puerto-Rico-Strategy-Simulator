import json
import os

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui.py")


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path / "results"))
    os.makedirs(tmp_path / "results" / "ml")
    return tmp_path / "results"


def run_app():
    at = AppTest.from_file(UI, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def goto(at, page):
    """Click a left-navigation entry (keys nav-<page>; the current page's entry is navon-<page>)."""
    if not any(b.key == f"navon-{page}" for b in at.button):  # already there otherwise
        at.button(key=f"nav-{page}").click().run()
    assert not at.exception, at.exception
    return at


def nav_labels(at):
    return [b.label.split("\u2003", 1)[1] for b in at.button if (b.key or "").startswith(("nav-", "navon-"))]


def test_ui_renders_without_data(results):
    at = run_app()
    assert nav_labels(at) == ["模擬對局採樣", "模型訓練/蒸餾", "對戰驗證", "管線", "模型清單", "模型詳細資料", "排程佇列", "hash 說明", "版本控管"]
    assert at.button(key="navon-data")  # the first page is the current one
    goto(at, "train")
    assert at.button(key="navon-train")
    assert any("還沒有訓練資料" in i.value for i in at.info)


def test_ui_lists_dumps_and_models(results):
    from conftest import write_dump
    write_dump(str(results / "ml" / "4p-test.bin"), games=10)
    at = goto(run_app(), "train")
    players = next(r for r in at.radio if r.label.startswith("人數（模型依人數分開）"))
    assert players.options == ["4 人局"]
    assert any(d.value.index.tolist() == ["4p-test.bin"] for d in at.dataframe)  # training tab table: file names only, the folder is a small line below
    assert any(b.label == "開啟資料夾" for b in at.button)
    start = next(b for b in at.button if b.label == "開始訓練")
    assert start.disabled  # nothing selected yet
    goto(at, "match")
    assert next(b for b in at.button if b.label == "開始對戰")  # match tab offers the repo models (they carry .meta.json)
    assert any(s.label == "模型" for s in at.selectbox)


def test_typed_model_name_survives_a_rerun_in_a_later_minute(results, monkeypatch):
    """The default name has the time in it; it used to be the widget's `value`, so a new minute made a new widget and the typed name was lost."""
    import datetime
    from conftest import write_dump
    write_dump(str(results / "ml" / "4p-test.bin"), games=10)
    at = goto(run_app(), "train")
    name = lambda: next(t for t in at.text_input if t.label.startswith("模型名稱"))  # noqa: E731
    first_default = name().value
    name().set_value("my-own-name").run()

    class Later(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return super().now(tz) + datetime.timedelta(minutes=7)
    monkeypatch.setattr(datetime, "datetime", Later)
    at.run()
    assert name().value == "my-own-name" and first_default != "my-own-name"


def test_each_page_has_its_own_english_title(results, monkeypatch):
    monkeypatch.setenv("PR_LANG", "en")
    at = run_app()
    titles = {"data": "Data Sampling", "train": "Model Training", "match": "Match Validation", "pipeline": "Pipeline", "modellist": "Model List", "models": "Model Details",
              "queue": "Job Queue", "hash": "Hash Guide", "versions": "Version Control"}
    for pid, title in titles.items():
        goto(at, pid)
        assert [t.value for t in at.title] == [title]


def test_match_page_offers_a_model_versus_model_table(results):
    at = goto(run_app(), "match")
    radio = next(r for r in at.radio if r.label == "對手")
    assert "model" in radio.options or any("另一個估值模型" in o for o in radio.options)
    radio.set_value("model").run()
    assert not at.exception, at.exception
    rival = next(s for s in at.selectbox if s.label == "對手模型")
    model = next(s for s in at.selectbox if s.label == "模型")
    assert rival.value != model.value and rival.value in rival.options and model.value not in rival.options
    assert any("對手模型模擬次數" in n.label for n in at.number_input)
    assert next(n for n in at.number_input if n.label.startswith("局數")).value == 480
    assert any(f"MCTS＋{rival.value}" in c.value for c in at.caption)  # the table is spelled out under the form


def test_model_list_has_place_kind_and_player_count_filters(results):
    at = goto(run_app(), "modellist")  # the list lives on its own page
    assert [g.key for g in at.get("button_group")] == ["mf-place", "mf-kind", "mf-players"]
    goto(at, "models")
    assert not at.get("button_group")


def test_match_tab_refuses_game_counts_that_break_seat_balance(results):
    at = goto(run_app(), "match")
    games = next(n for n in at.number_input if n.label.startswith("局數（24 的倍數"))
    games.set_value(250).run()
    assert not at.exception
    assert next(b for b in at.button if b.label == "開始對戰").disabled
    # the reason is shown in red next to the locked button
    assert any("局數要是 24 的倍數" in m.value and "act-err" in m.value for m in at.markdown)


def test_missing_packages_show_the_fix_command(results, monkeypatch):
    import check_env
    monkeypatch.setattr(check_env, "missing_modules", lambda: ["lightgbm"])
    at = run_app()
    assert any("lightgbm" in e.value for e in at.error)
    assert any("-m pip install -r" in c.value for c in at.code)
    assert not nav_labels(at)  # nothing else is drawn


def test_start_buttons_while_jobs_are_queued(results, monkeypatch):
    # every start button reads 加入排隊 then: they must not collide (duplicate element ids)
    import jobs
    from conftest import write_dump
    write_dump(str(results / "ml" / "4p-test.bin"), games=10)  # the training tab shows its button only with data
    fake = {"id": "x", "title": "running job", "kind": "dump", "state": "running", "spec": {"out": "results/ml/a.bin"}}
    monkeypatch.setattr(jobs, "active_job", lambda: fake)
    monkeypatch.setattr(jobs, "waiting_jobs", lambda: [])
    monkeypatch.setattr(jobs, "list_jobs", lambda: [fake])
    monkeypatch.setattr(jobs, "events", lambda job_id: [])
    monkeypatch.setattr(jobs, "read_job", lambda job_id: fake if job_id == "x" else None)
    at = run_app()
    count = 0
    for page in ("data", "train", "match"):
        goto(at, page)
        count += sum(b.label == "加入排隊" for b in at.button)
    assert count == 3
    # the navigation shows only the running job; the queue length is a small note
    assert any("running job" in m.value for m in at.sidebar.markdown)


def test_custom_combination_writes_a_config_and_queues_a_dump(results, monkeypatch):
    import jobs
    started = {}
    monkeypatch.setattr(jobs, "start", lambda kind, title, spec, *key: started.update(kind=kind, title=title, spec=spec, key=key) or "job-1")
    written = {}
    at = AppTest.from_file(UI, default_timeout=60)
    at.run()
    mode = next(r for r in at.radio if r.label == "採樣來源模型")
    mode.set_value("custom").run()
    assert not at.exception, at.exception
    seat_boxes = [s for s in at.selectbox if s.label.startswith("座位 ")]
    assert len(seat_boxes) == 4
    shown = [o.split("（")[0] for o in seat_boxes[0].options]  # options are displayed as "name（說明）"
    assert "mcts" in shown and "cheap-engine" in shown and "corn-monopoly-hoard" in shown
    assert "rule-based" not in shown  # needs params.profile: not offered
    seat_boxes[0].set_value("mcts").run()
    assert any(n.label == "模擬次數" for n in at.number_input)
    name = next(t for t in at.text_input if t.label.startswith("輸出名稱"))
    name.set_value("pytest-custom-config").run()
    params = [t for t in at.text_input if t.label.startswith("參數（選填")]
    params[0].set_value("buildThreshold=3.5").run()
    import os
    cfg_path = os.path.join(os.path.dirname(UI), "local", "data-configs", "pytest-custom-config.json")
    try:
        next(b for b in at.button if b.label in ("開始產生資料", "加入排隊")).click().run()
        assert not at.exception, at.exception
        assert started["kind"] == "dump" and started["spec"]["config"] == "ml/local/data-configs/pytest-custom-config.json"
        import json
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        assert [s["strategy"] for s in cfg["seats"]] == ["mcts", "build-first", "harbor-rush", "corn-to-premium"]
        assert cfg["seats"][0]["params"] == {"simulations": 100}
        assert cfg["seats"][1]["params"] == {"buildThreshold": 3.5}
        assert cfg["seatOrder"] == "random" and cfg["players"] == 4
    finally:
        if os.path.exists(cfg_path):
            os.remove(cfg_path)


def test_parse_params():
    import importlib
    import sys
    import pytest as _pt
    sys.modules.pop("ui", None)
    # parse_params is a plain function: import it without running the Streamlit page
    import ast
    src = open(UI, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "parse_params")
    ns = {"re": importlib.import_module("re"), "t": lambda key, **kw: key}  # the function only needs the translator to word its error
    exec(compile(ast.Module(body=[fn], type_ignores=[]), UI, "exec"), ns)
    assert ns["parse_params"]("a=3, b=2.5; c=text") == {"a": 3, "b": 2.5, "c": "text"}
    assert ns["parse_params"]("") == {}
    with _pt.raises(ValueError):
        ns["parse_params"]("nonsense")


def test_save_config_only_writes_the_config(results, monkeypatch):
    import json
    import os
    import jobs
    monkeypatch.setattr(jobs, "start", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no job may start")))
    at = run_app()
    next(r for r in at.radio if r.label == "採樣來源模型").set_value("custom").run()
    next(t for t in at.text_input if t.label.startswith("輸出名稱")).set_value("pytest-saved-only").run()
    cfg_path = os.path.join(os.path.dirname(UI), "local", "data-configs", "pytest-saved-only.json")
    try:
        next(b for b in at.button if b.label == "新增設定").click().run()
        assert not at.exception, at.exception
        with open(cfg_path, encoding="utf-8") as f:
            assert json.load(f)["players"] == 4
        # the same name cannot be saved twice (existing configs are never overwritten)
        assert next(b for b in at.button if b.label == "新增設定").disabled
    finally:
        if os.path.exists(cfg_path):
            os.remove(cfg_path)


def test_deleting_closes_the_dialog_and_clears_the_selection(results):
    from conftest import write_dump
    write_dump(str(results / "ml" / "4p-a.bin"), games=10)
    write_dump(str(results / "ml" / "4p-b.bin"), games=10)
    at = goto(run_app(), "data")  # data are deleted on the sampling page; the training page only selects
    table = next(d for d in at.dataframe if (d.key or "").startswith("dumps-manage-"))
    assert table.key == "dumps-manage-0"
    assert any(b.label.startswith("🗑 刪除勾選") for b in at.button)
    # deleting is done in a dialog (AppTest cannot click inside it): emulate the confirmed deletion's bookkeeping
    at.session_state["del-gen"] = 1
    os.remove(results / "ml" / "4p-a.bin")
    at.run()
    table = next(d for d in at.dataframe if (d.key or "").startswith("dumps-manage-"))
    assert table.key == "dumps-manage-1"  # a new key: the old row selection is gone
    goto(at, "train")
    assert not any(b.label.startswith("🗑 刪除勾選") for b in at.button)  # selecting only


def test_queue_rows_are_framed_cards(results, monkeypatch):
    import jobs
    rows = [{"id": "r", "title": "running job", "kind": "dump", "state": "running", "spec": {}},
            {"id": "w", "title": "waiting job", "kind": "match", "state": "waiting", "spec": {}}]
    monkeypatch.setattr(jobs, "list_jobs", lambda: rows)
    monkeypatch.setattr(jobs, "active_job", lambda: rows[0])
    monkeypatch.setattr(jobs, "waiting_jobs", lambda: rows[1:])
    monkeypatch.setattr(jobs, "events", lambda job_id: [])
    monkeypatch.setattr(jobs, "read_job", lambda job_id: next((r for r in rows if r["id"] == job_id), None))
    at = goto(run_app(), "queue")
    assert any("還有 1 項排隊中" in m.value for m in at.sidebar.markdown)
    assert not any("waiting job" in m.value for m in at.sidebar.markdown)  # only the running job in the navigation


def _config_dump(results, name, **meta):
    """A dump file whose metadata is exactly what the built-in 3p-hand-a config would produce."""
    import json
    from conftest import write_dump
    cfg_path = os.path.join(os.path.dirname(UI), "data-configs", "3p-hand-a.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    import fingerprint
    fields = {"games": cfg["games"], "seed": cfg["seed"], "rate": 0.01, "featureVersion": fingerprint.current_feature_version(),  # the form's default: the newest
              "seats": [{"id": s["id"], "strategy": s["strategy"], "params": s.get("params", {})} for s in cfg["seats"]]}
    fields.update(meta)
    return write_dump(str(results / "ml" / name), per_game=2, players=cfg["players"], **fields)


def test_same_name_data_shows_whether_the_recipe_is_the_same_or_what_differs(results):
    _config_dump(results, "3p-hand-a.bin")  # the default output name of the first config
    at = goto(run_app(), "data")
    assert any("完全相同" in i.value for i in at.info)
    next(n for n in at.number_input if n.label == "局數").set_value(200000).run()
    text = " ".join(w.value for w in at.warning)
    assert "參數**不同**" in text and "局數：20,000 → 200,000" in text
    next(n for n in at.number_input if n.label.startswith("抽樣率")).set_value(0.001).run()
    assert "抽樣率：0.01 → 0.001" in " ".join(w.value for w in at.warning)


def test_the_feature_version_of_new_data_is_chosen_on_the_sampling_page(results):
    import fingerprint
    _config_dump(results, "3p-hand-a.bin")  # newest version: same recipe
    at = goto(run_app(), "data")
    pick = next(x for x in at.selectbox if x.label == "特徵版本")
    assert pick.options == [str(v) for v in fingerprint.feature_versions()] and pick.value == fingerprint.current_feature_version()
    assert any("完全相同" in i.value for i in at.info)
    pick.select(1).run()  # an older feature set is another recipe: the existing data differ in the feature version
    assert "特徵版本：" in " ".join(w.value for w in at.warning)


def test_other_name_with_the_same_recipe_is_reported_as_a_duplicate(results):
    _config_dump(results, "copy-of-hand-a.bin")
    at = goto(run_app(), "data")
    assert any("已經有相同配方" in i.value and "copy-of-hand-a" in i.value for i in at.info)


def test_overwriting_an_input_of_a_queued_job_is_refused(results, monkeypatch):
    import jobs
    _config_dump(results, "3p-hand-a.bin")
    fake = {"id": "x", "title": "訓練 4p-x", "kind": "train_lgbm", "state": "running",
            "spec": {"data": [str(results / "ml" / "3p-hand-a.bin").replace(os.sep, "/")], "out": "ml/local/models/x.txt"}}  # as rel() writes it
    monkeypatch.setattr(jobs, "active_job", lambda: fake)
    monkeypatch.setattr(jobs, "waiting_jobs", lambda: [])
    monkeypatch.setattr(jobs, "list_jobs", lambda: [fake])
    monkeypatch.setattr(jobs, "events", lambda job_id: [])
    at = goto(run_app(), "data")
    start = next(b for b in at.button if b.label == "加入排隊")
    assert start.disabled
    assert any("要讀這個檔案" in m.value and "act-err" in m.value for m in at.markdown)


def test_hash_page_lists_what_counts_and_what_does_not(results):
    import fingerprint
    at = goto(run_app(), "hash")
    text = " ".join(m.value for m in at.markdown) + " ".join(t.value.to_csv() for t in at.table)
    assert "不計入" in text and "估值模型" in text and "座位 id" in text
    for key in fingerprint.LGBM_OPTIONS + fingerprint.MLP_OPTIONS:  # the option lists on the page come from the code
        assert f"`{key}`" in text, key
    assert "指紋" not in text  # the UI says hash


def test_versions_page_shows_the_list_and_matches_the_code(results):
    import fingerprint
    at = goto(run_app(), "versions")
    assert not at.exception
    assert not at.warning  # docs/versions.json names the current numbers
    text = " ".join(m.value for m in at.markdown)
    now = fingerprint.rules_name(fingerprint.current_rules_revision())
    assert f'<div class="l">規則版本</div><div class="v">{now}</div>' in text  # the tile
    assert "<th>版本</th><th>日期</th><th>commit</th><th>修改內容</th>" in text  # tables like the Dashboard's
    # one row per strategy, its current version as in the code
    rev = fingerprint.current_strategy_revision("harbor-rush")
    assert f'<td class="l nw">harbor-rush</td><td class="c">harbor-rush-v{rev}</td><td class="c">v{rev}</td>' in text

# ---------------------------------------------------------------- pipeline page

@pytest.fixture
def no_spawn(monkeypatch):
    """Jobs are created and queued but no process starts (the page is what is tested, not the work)."""
    import jobs
    monkeypatch.setattr(jobs, "_spawn", lambda job_id: job_id)
    return jobs


def _cleanup(paths):
    for p in paths:
        if p and os.path.exists(p):
            os.remove(p)


@pytest.fixture
def inline(monkeypatch):
    """AppTest cannot rerun a dialog on its own: the forms of the pipeline page are drawn in the page (PR_UI_INLINE_DIALOGS)."""
    monkeypatch.setenv("PR_UI_INLINE_DIALOGS", "1")


def _blocked(at):
    return [m.value for m in at.markdown if "act-err" in m.value]


def _add(at, kind, **widgets):
    """Opens the form of "d" data / "t" model / "m" match, sets the given widgets (pld-<name>=value) and presses Add."""
    at.button(key=f"pl-btn-add-{kind}").click().run()
    assert not at.exception, at.exception
    for name, value in widgets.items():
        widget = next(w for w in (at.number_input, at.text_input, at.selectbox, at.multiselect) if any(x.key == f"pld-{name}" for x in w))
        widget(key=f"pld-{name}").set_value(value)
    at.run()
    assert not at.exception, at.exception
    assert not at.button(key="pld-ok").disabled, _blocked(at)
    at.button(key="pld-ok").click().run()
    assert not at.exception, at.exception


def test_pipeline_page_starts_empty_and_an_item_is_added_through_its_form(results, inline):
    at = goto(run_app(), "pipeline")
    assert at.session_state["pl-data"] == [] and at.session_state["pl-train"] == [] and at.session_state["pl-match"] == []
    assert at.button(key="pl-btn-start").disabled          # nothing to run yet
    at.button(key="pl-btn-add-d").click().run()
    assert at.session_state["pl-inline"] == "d" and any(b.key == "pld-ok" for b in at.button)   # the form is open
    at.button(key="pld-cancel").click().run()
    assert at.session_state["pl-data"] == [] and "pl-inline" not in at.session_state              # cancel adds nothing
    _add(at, "d", seed=5)
    item = at.session_state["pl-data"][0]
    assert item["mode"] == "config" and item["seed"] == 5 and item["name"] and "pl-inline" not in at.session_state
    assert any(m.value for m in at.markdown if "pl-detail" in m.value and item["name"] in m.value)   # its details are on the page, read-only
    assert not any(w.key.startswith("pld-") for w in at.number_input)                               # and the form is gone


def test_a_name_that_exists_locks_the_add_button(results, inline):
    os.makedirs(results / "ml", exist_ok=True)
    (results / "ml" / "taken.bin").write_bytes(b"x")
    at = goto(run_app(), "pipeline")
    at.button(key="pl-btn-add-d").click().run()
    at.text_input(key="pld-name").set_value("taken").run()
    assert at.button(key="pld-ok").disabled and any("taken.bin" in m for m in _blocked(at))


def test_pipeline_page_with_data_training_and_a_match(results, no_spawn, inline):
    jobs = no_spawn
    at = goto(run_app(), "pipeline")
    _add(at, "d")
    _add(at, "t")
    _add(at, "m", seed=424242)
    created = []
    try:
        assert at.session_state["pl-train"][0]["data"] == ["new:0"] and at.session_state["pl-match"][0]["model"] == "new:0"
        assert not at.button(key="pl-btn-start").disabled, _blocked(at)
        at.button(key="pl-btn-start").click().run()
        assert not at.exception, at.exception
        listed = sorted(jobs.list_jobs(), key=lambda j: j["pipeline"]["index"])
        assert [j["kind"] for j in listed] == ["dump", "train_lgbm", "match"]
        assert len({j["pipeline"]["id"] for j in listed}) == 1 and [j["pipeline"]["index"] for j in listed] == [0, 1, 2]
        dump_job, train_job, match_job = listed
        created = [os.path.join(jobs.ROOT, j["spec"]["config"]) for j in listed if j["kind"] == "match"]
        assert train_job["spec"]["data"] == [dump_job["spec"]["out"]]                     # the training reads what step 1 will write
        assert match_job["spec"]["model"] == train_job["spec"]["out"]                      # the match plays what step 2 will train
        cfg = json.load(open(created[0], encoding="utf-8"))
        assert cfg["seats"][0]["params"]["valueModel"] == train_job["spec"]["out"]
        assert cfg["seats"][0]["params"]["leafRollout"] == 40 and cfg["seed"] == 424242
        assert jobs.read_job(dump_job["id"])["state"] == "queued" and jobs.read_job(match_job["id"])["state"] == "waiting"
    finally:
        _cleanup(created)


def test_pipeline_of_matches_only_uses_existing_models(results, no_spawn, inline):
    jobs = no_spawn
    at = goto(run_app(), "pipeline")
    at.button(key="pl-btn-standard").click().run()
    assert not at.exception, at.exception
    items = at.session_state["pl-match"]
    assert len(items) >= 2 and all(not str(m["model"]).startswith("new:") for m in items)
    at.button(key="pl-btn-standard").click().run()                   # pressing it again adds nothing that is already there
    assert len(at.session_state["pl-match"]) == len(items)
    at.session_state["pl-match"] = [{**m, "seed": 424242 + i} for i, m in enumerate(items)]   # names that cannot collide with a real result
    at.run()
    created = []
    try:
        assert not at.button(key="pl-btn-start").disabled, _blocked(at)
        at.button(key="pl-btn-start").click().run()
        listed = sorted(jobs.list_jobs(), key=lambda j: j["pipeline"]["index"])
        created = [os.path.join(jobs.ROOT, j["spec"]["config"]) for j in listed]
        assert len(listed) == len(items) and all(j["kind"] == "match" for j in listed)
    finally:
        _cleanup(created)


def test_pipeline_with_several_data_sets_and_models_runs_each_model_with_its_matches(results, no_spawn, inline):
    jobs = no_spawn
    at = goto(run_app(), "pipeline")
    _add(at, "d")
    _add(at, "d")
    _add(at, "t")
    _add(at, "t")
    assert at.session_state["pl-train"][1]["data"] == ["new:0", "new:1"] and at.session_state["pl-train"][0]["name"] != at.session_state["pl-train"][1]["name"]
    _add(at, "m", model="new:1", seed=424242)         # tests the second model
    _add(at, "m", model="new:0", seed=424243)
    created = []
    try:
        assert not at.button(key="pl-btn-start").disabled, _blocked(at)
        at.button(key="pl-btn-start").click().run()
        listed = sorted(jobs.list_jobs(), key=lambda j: j["pipeline"]["index"])
        created = [os.path.join(jobs.ROOT, j["spec"]["config"]) for j in listed if j["kind"] == "match"]
        # all the data first, then each model followed by its own matches
        assert [j["kind"] for j in listed] == ["dump", "dump", "train_lgbm", "match", "train_lgbm", "match"]
        d0, d1, t0, m_of_0, t1, m_of_1 = listed
        assert t0["spec"]["data"] == [d0["spec"]["out"], d1["spec"]["out"]] and t1["spec"]["data"] == [d0["spec"]["out"], d1["spec"]["out"]]
        assert m_of_0["spec"]["model"] == t0["spec"]["out"] and m_of_1["spec"]["model"] == t1["spec"]["out"]
        assert t0["spec"]["out"] != t1["spec"]["out"] and d0["spec"]["out"] != d1["spec"]["out"]
        assert json.load(open(created[0], encoding="utf-8"))["seed"] == 424243   # the match of model 1 was added second
    finally:
        _cleanup(created)


def test_removing_an_item_removes_what_depends_on_it(results, inline):
    at = goto(run_app(), "pipeline")
    _add(at, "d")
    _add(at, "d")
    _add(at, "t")
    _add(at, "m", seed=424242)
    assert at.session_state["pl-train"][0]["data"] == ["new:0", "new:1"]
    at.button(key="stop-pl-rm-d0").click().run()                     # the first data set goes away: the model keeps the other one
    assert not at.exception, at.exception
    assert len(at.session_state["pl-data"]) == 1 and at.session_state["pl-train"][0]["data"] == ["new:0"]
    at.button(key="stop-pl-rm-t0").click().run()                     # the model goes away: its match goes with it
    assert at.session_state["pl-train"] == [] and at.session_state["pl-match"] == [] and len(at.session_state["pl-data"]) == 1
    at.button(key="stop-pl-clear-d").click().run()
    assert at.session_state["pl-data"] == []


def test_a_template_of_the_earlier_pipeline_pages_loads_as_items(results):
    tpl = os.path.join(os.path.dirname(UI), "local", "pipelines", "pytest-old.json")
    os.makedirs(os.path.dirname(tpl), exist_ok=True)
    old = {"pl-players": 4, "pl-d-n": 1, "pl-d0-mode": "config", "pl-d0-config": "ml/data-configs/4p-hand-a.json", "pl-d0-name": "pytest-old-data",
           "pl-d0-games": 100, "pl-d0-seed": 1, "pl-d0-rate": 0.01, "pl-d0-feature": 1, "pl-d0-threads": 0,
           "pl-t-n": 1, "pl-t0-kind": "train_lgbm", "pl-t0-name": "pytest-old-model", "pl-t0-data": ["new:0"],
           "pl-m-n": 1, "pl-m-sims": 300, "pl-m-leaf": 40, "pl-m0-model": "new:0", "pl-m0-seed": 99}
    json.dump({"schemaVersion": 2, "name": "pytest-old", "settings": old}, open(tpl, "w", encoding="utf-8"))
    try:
        at = goto(run_app(), "pipeline")
        at.selectbox(key="pl-tpl-pick").set_value("pytest-old").run()
        at.button(key="pl-btn-load").click().run()
        assert not at.exception, at.exception
        assert [d["name"] for d in at.session_state["pl-data"]] == ["pytest-old-data"]
        assert [x["name"] for x in at.session_state["pl-train"]] == ["pytest-old-model"] and at.session_state["pl-train"][0]["data"] == ["new:0"]
        m = at.session_state["pl-match"][0]
        assert m["model"] == "new:0" and m["seed"] == 99 and m["sims"] == 300 and m["leaf"] == 40
    finally:
        _cleanup([tpl])


def test_pipeline_form_is_kept_when_another_page_is_visited_and_saved_as_a_template(results, inline):
    tpl = os.path.join(os.path.dirname(UI), "local", "pipelines", "pytest-tpl.json")
    try:
        at = goto(run_app(), "pipeline")
        _add(at, "d", seed=777)
        goto(at, "queue")
        goto(at, "pipeline")
        assert at.session_state["pl-data"][0]["seed"] == 777                  # still as it was left
        at.text_input(key="pl-tpl-name").set_value("pytest-tpl").run()
        at.button(key="pl-btn-save").click().run()
        assert os.path.exists(tpl)
        saved = json.load(open(tpl, encoding="utf-8"))["settings"]
        assert saved["pl-data"][0]["seed"] == 777 and saved["pl-train"] == [] and saved["pl-match"] == []
        at.button(key="stop-pl-clear-d").click().run()
        assert at.session_state["pl-data"] == []
        at.selectbox(key="pl-tpl-pick").set_value("pytest-tpl").run()
        at.button(key="pl-btn-load").click().run()
        assert at.session_state["pl-data"][0]["seed"] == 777
    finally:
        _cleanup([tpl])


def test_pipeline_custom_combination_prefills_defaults_keeps_params_collapsed_and_stores_only_changes(results, no_spawn, inline):
    jobs = no_spawn
    at = goto(run_app(), "pipeline")
    at.button(key="pl-btn-add-d").click().run()
    at.radio(key="pld-mode").set_value("custom").run()
    assert not at.exception, at.exception
    assert len(at.session_state["pld-cs0"]) > 0 and at.session_state["pld-cs0"] == "cheap-engine"
    # every parameter box of the seats holds the engine's default
    boxes = [w for w in at.text_input if w.key.startswith("pld-cp0-cheap-engine-")]
    assert boxes and all(w.value != "" for w in boxes)                                     # filled with the defaults
    assert not any("tie" in w.key or "randomTies" in w.key for w in at.text_input if w.key.startswith("pld-cp"))   # only the strategy's own parameters
    assert [w.key.rsplit("-", 1)[1] for w in at.text_input if w.key.startswith("pld-cp1-")] == ["buildThreshold", "quarryTarget"]   # build-first
    # same strategy names as the Dashboard's drop-down
    assert at.selectbox(key="pld-cs0").options[0] == "Build-First" or "Build-First" in at.selectbox(key="pld-cs0").options
    assert at.selectbox(key="pld-cs0").options[-1] == "Full-Random"
    key = next(w.key for w in boxes if w.key.endswith("buildThreshold"))
    default = float(at.text_input(key=key).value)
    at.text_input(key=key).set_value(str(default + 1)).run()
    at.text_input(key="pld-name").set_value("custom-test-a").run()
    assert not at.button(key="pld-ok").disabled, _blocked(at)
    at.button(key="pld-ok").click().run()
    item = at.session_state["pl-data"][0]
    assert item["mode"] == "custom" and len(item["seats"]) == 4
    assert item["seats"][0]["params"] == {"buildThreshold": default + 1}      # only the changed one
    assert all(s_["params"] == {} for s_ in item["seats"][1:])
    at.button(key="pl-btn-start").click().run()
    assert not at.exception, at.exception
    job = jobs.list_jobs()[0]
    cfg_path = os.path.join(jobs.ROOT, job["spec"]["config"])
    try:
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        assert [s_["strategy"] for s_ in cfg["seats"]] == ["cheap-engine", "build-first", "harbor-rush", "corn-to-premium"]
        assert cfg["seats"][0]["params"] == {"buildThreshold": default + 1} and cfg["players"] == 4
    finally:
        _cleanup([cfg_path])


def test_pipeline_custom_combination_blocks_a_text_in_a_numeric_parameter(results, inline):
    at = goto(run_app(), "pipeline")
    at.button(key="pl-btn-add-d").click().run()
    at.radio(key="pld-mode").set_value("custom").run()
    key = next(w.key for w in at.text_input if w.key.startswith("pld-cp0-") and w.key.endswith("buildThreshold"))
    at.text_input(key=key).set_value("abc").run()
    assert at.button(key="pld-ok").disabled and any("buildThreshold" in m for m in _blocked(at))


def test_pipeline_custom_mcts_seat_lists_its_parameters_in_the_dashboard_order(results, inline):
    at = goto(run_app(), "pipeline")
    at.button(key="pl-btn-add-d").click().run()
    at.radio(key="pld-mode").set_value("custom").run()
    at.selectbox(key="pld-cs0").set_value("mcts").run()
    assert not at.exception, at.exception
    keys = [w.key for w in [*at.selectbox, *at.text_input] if w.key and (w.key.startswith("pld-cm0") or w.key.startswith("pld-cp0-mcts-"))]
    order = {k: i for i, k in enumerate(["pld-cm0", "pld-cp0-mcts-simulations", "pld-cp0-mcts-leafRollout", "pld-cp0-mcts-rolloutRounds", "pld-cp0-mcts-rolloutStrategy"])}
    assert sorted(keys, key=lambda k: order.get(k, 99))[:5] == list(order)
    assert not any("tie" in k for k in keys)


def test_pipeline_custom_combination_seat_order_goes_into_the_config(results, no_spawn, inline):
    jobs = no_spawn
    at = goto(run_app(), "pipeline")
    at.button(key="pl-btn-add-d").click().run()
    at.radio(key="pld-mode").set_value("custom").run()
    assert at.selectbox(key="pld-seatorder").value == "random"
    at.selectbox(key="pld-seatorder").set_value("balanced").run()
    at.text_input(key="pld-name").set_value("custom-order-test").run()
    at.button(key="pld-ok").click().run()
    assert at.session_state["pl-data"][0]["seat_order"] == "balanced"
    at.button(key="pl-btn-start").click().run()
    cfg_path = os.path.join(jobs.ROOT, jobs.list_jobs()[0]["spec"]["config"])
    try:
        assert json.load(open(cfg_path, encoding="utf-8"))["seatOrder"] == "balanced"
    finally:
        _cleanup([cfg_path])


def test_pipeline_custom_seat_boxes_are_filled_for_every_strategy_also_after_switching_back(results, inline):
    at = goto(run_app(), "pipeline")
    at.button(key="pl-btn-add-d").click().run()
    at.radio(key="pld-mode").set_value("custom").run()
    names = list(at.selectbox(key="pld-cs1").options)
    for turn in range(2):                                     # the second pass comes back to strategies whose boxes were dropped meanwhile
        for n in at.selectbox(key="pld-cs1").options:
            raw = {"Full-Random": "random", "MCTS": "mcts"}.get(n) or n.lower()
            at.selectbox(key="pld-cs1").set_value(raw).run()
            assert not at.exception, at.exception
            boxes = [w for w in at.text_input if w.key.startswith("pld-cp1-")]
            assert all(w.value != "" for w in boxes), (raw, [w.key for w in boxes if w.value == ""])
    assert len(names) > 5


def test_pipeline_training_data_is_chosen_from_a_filterable_table(results, no_spawn, inline):
    at = goto(run_app(), "pipeline")
    _add(at, "d")
    at.button(key="pl-btn-add-t").click().run()
    assert not at.exception, at.exception
    assert at.session_state["pld-data"] == ["new:0"]                              # the pipeline's own data starts chosen
    assert any(p.key == "pld-tf-kind" for p in at.get("pills"))                   # quick filters like the training page
    key = next(k for k in at.session_state.to_dict() if str(k).startswith("pld-dtable-"))
    at.session_state[key] = {"selection": {"rows": [], "columns": []}}             # unticking the row (the user's click)
    at.run()
    assert at.session_state["pld-data"] == [] and at.button(key="pld-ok").disabled
