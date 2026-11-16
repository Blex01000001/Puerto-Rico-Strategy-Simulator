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
    assert nav_labels(at) == ["模擬對局採樣", "模型訓練/蒸餾", "對戰驗證", "模型清單", "排程佇列", "hash 說明", "版本控管"]
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
    assert any("results/ml/4p-test.bin" in str(d.value.index.tolist()) for d in at.dataframe)  # training tab table
    start = next(b for b in at.button if b.label == "開始訓練")
    assert start.disabled  # nothing selected yet
    goto(at, "match")
    assert next(b for b in at.button if b.label == "開始對戰")  # match tab offers the repo models (they carry .meta.json)
    assert any(s.label == "模型" for s in at.selectbox)


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
    monkeypatch.setattr(jobs, "start", lambda kind, title, spec: started.update(kind=kind, title=title, spec=spec) or "job-1")
    written = {}
    at = AppTest.from_file(UI, default_timeout=60)
    at.run()
    mode = next(r for r in at.radio if r.label == "採樣來源模型")
    mode.set_value("自訂組合（自己選每個座位的策略）").run()
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
    ns = {"re": importlib.import_module("re")}
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
    next(r for r in at.radio if r.label == "採樣來源模型").set_value("自訂組合（自己選每個座位的策略）").run()
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
    at = goto(run_app(), "train")
    table = next(d for d in at.dataframe if (d.key or "").startswith("dumps-"))
    assert table.key == "dumps-0"
    # deleting is done in a dialog (AppTest cannot click inside it): emulate the confirmed deletion's bookkeeping
    at.session_state["del-gen"] = 1
    os.remove(results / "ml" / "4p-a.bin")
    at.run()
    table = next(d for d in at.dataframe if (d.key or "").startswith("dumps-"))
    assert table.key == "dumps-1"  # a new key: the old row selection is gone


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
    fields = {"games": cfg["games"], "seed": cfg["seed"], "rate": 0.01,
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
    assert "不計入" in text and "價值模型" in text and "座位 id" in text
    for key in fingerprint.LGBM_OPTIONS + fingerprint.MLP_OPTIONS:  # the option lists on the page come from the code
        assert f"`{key}`" in text, key
    assert "指紋" not in text  # the UI says hash


def test_versions_page_shows_the_list_and_matches_the_code(results):
    import fingerprint
    at = goto(run_app(), "versions")
    assert not at.exception
    assert not at.warning  # docs/versions.json names the current numbers
    assert any(m.label == "規則版本" and m.value == fingerprint.rules_name(fingerprint.current_rules_revision()) for m in at.metric)
    text = " ".join(m.value for m in at.markdown)
    assert "base-v" in text
    # one row per strategy, its current version as in the code
    table = next(t for t in at.table if "目前版本" in t.value.columns)
    assert "harbor-rush" in table.value.index and table.value.loc["harbor-rush", "目前版本"] == f"harbor-rush-v{fingerprint.current_strategy_revision('harbor-rush')}"
