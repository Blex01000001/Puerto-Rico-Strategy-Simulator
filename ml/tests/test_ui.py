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
    assert [t.label for t in at.tabs] == ["訓練", "模型清單"]
    assert any("還沒有訓練資料" in i.value for i in at.info)


def test_ui_lists_dumps_and_models(results):
    from conftest import write_dump
    write_dump(str(results / "ml" / "4p-test.bin"), games=10)
    at = run_app()
    assert at.radio[0].options == ["4 人局"]
    assert "results/ml/4p-test.bin" in str(at.dataframe[0].value.index.tolist())
    assert at.button[0].label == "開始訓練" and at.button[0].disabled  # nothing selected yet
    assert at.selectbox  # the model tab lists ml/models (repo models carry .meta.json)
