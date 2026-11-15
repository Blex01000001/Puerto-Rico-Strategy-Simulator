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


def test_ui_renders_without_data(results):
    at = run_app()
    assert [t.label for t in at.tabs] == ["模擬對局採樣", "模型訓練/蒸餾", "對戰驗證", "模型清單", "排程佇列"]
    assert any("還沒有訓練資料" in i.value for i in at.info)


def test_ui_lists_dumps_and_models(results):
    from conftest import write_dump
    write_dump(str(results / "ml" / "4p-test.bin"), games=10)
    at = run_app()
    players = next(r for r in at.radio if r.label.startswith("人數（模型依人數分開）"))
    assert players.options == ["4 人局"]
    assert any("results/ml/4p-test.bin" in str(d.value.index.tolist()) for d in at.dataframe)  # training tab table
    start = next(b for b in at.button if b.label == "開始訓練")
    assert start.disabled  # nothing selected yet
    assert next(b for b in at.button if b.label == "開始對戰")  # match tab offers the repo models (they carry .meta.json)
    assert any(s.label == "模型" for s in at.selectbox)


def test_match_tab_refuses_game_counts_that_break_seat_balance(results):
    at = run_app()
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
    assert not at.tabs  # nothing else is drawn


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
    assert sum(b.label == "加入排隊" for b in at.button) == 3


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
