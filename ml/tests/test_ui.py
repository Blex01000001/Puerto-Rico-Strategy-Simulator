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
    assert [t.label for t in at.tabs] == ["資料", "訓練", "對戰驗證", "模型清單", "工作"]
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
    assert any("局數要是 24 的倍數" in c.value for c in at.caption)


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
