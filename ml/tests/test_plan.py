"""The pipeline's plans (mlui/plan.py) are widget-free: tests call them directly, without AppTest."""
import os

import pytest

from mlui import plan


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path / "results"))
    os.makedirs(tmp_path / "results" / "ml")
    return tmp_path / "results"


def test_match_plan_of_a_missing_model_says_so():
    p = plan.pl_match_plan({"model": "no-such-model.txt", "games": 48}, 4, [], [])
    assert p["problems"] and "no-such-model.txt" in p["problems"][0]
    assert "out" not in p


def test_match_plan_of_a_model_from_an_unplanned_training_item_is_gone():
    p = plan.pl_match_plan({"model": "new:0", "games": 48}, 4, [], [])
    assert len(p["problems"]) == 1


def test_match_plan_checks_the_game_count_and_names_the_result(results):
    model = os.path.join(plan.ROOT, "ml", "models", "4p-v1.txt")
    p = plan.pl_match_plan({"model": "4p-v1.txt", "games": 50, "sims": 100, "seed": 3}, 4, [], [])
    assert os.path.exists(model)
    assert any("24" in x for x in p["problems"]), p["problems"]   # 4 players: a multiple of the 24 seat orders
    assert p["name"] and p["out_rel"].endswith(p["name"] + ".json")
    assert p["seats"] and p["sims"] == 100 and p["seed"] == 3
    ok = plan.pl_match_plan({"model": "4p-v1.txt", "games": 48, "sims": 100, "seed": 3}, 4, [], [])
    assert not ok["problems"], ok["problems"]
    dup = plan.pl_match_plan({"model": "4p-v1.txt", "games": 48, "sims": 100, "seed": 3}, 4, [], [ok["name"]])
    assert dup["problems"]


def test_rows_estimate():
    assert plan.pl_rows(1000, 0.01, 4) == int(1000 * 0.01 * plan.ROWS_PER_GAME[4])
